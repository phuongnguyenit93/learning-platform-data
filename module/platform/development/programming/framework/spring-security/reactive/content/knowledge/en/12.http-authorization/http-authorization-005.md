# Combining Permissions with ServerWebExchange Information in Spring Security WebFlux

## Objectives and Context

This lesson belongs to the **HTTP Authorization** section of **Spring Security - reactive**. In real-world applications, deciding whether to permit a request rarely depends solely on whether a user has `ROLE_USER` or `ROLE_ADMIN`. The same user might be allowed to view their own report but not someone else's; certain data representations may require a higher role; and the HTTP method, URL, query parameters, and verified data in the request can all affect access permissions.

Spring Security WebFlux supports combining **Authentication** with **ServerWebExchange** through `ReactiveAuthorizationManager<AuthorizationContext>`, typically wired into the `ServerHttpSecurity.authorizeExchange(...).access(...)` DSL.

After this lesson, you will:

1. Distinguish **authentication**, **authorization**, **request matching**, **business ownership**, and data inside the HTTP exchange.
2. Access `AuthorizationContext.getExchange()`, `getVariables()`, and useful request properties.
3. Write a `ReactiveAuthorizationManager<AuthorizationContext>` that combines roles, resource owner, HTTP method, query parameters, and headers.
4. Identify which data is **client-controlled** and must never be treated as proof of identity or permission; know when to look up trusted data from the server/database.
5. Return **ALLOW/DENY** decisions per the `Mono<AuthorizationDecision>` contract, handling `Mono.empty()` and asynchronous errors without bypassing security.
6. Build a runnable example with **Java 17+ and Spring Boot 3.3.13 WebFlux**, testing 200/401/403 cases with `WebTestClient`.
7. Recognize cross-tenant/IDOR vulnerabilities, client header spoofing, query parameter pollution, and path variable extraction mistakes.
8. Know where to apply HTTP authorization and when to add service-layer protection using **reactive method security**.

**Scope:** Spring Security **reactive** uses `SecurityWebFilterChain` and `ServerHttpSecurity`. Do not mix with Servlet `HttpSecurity.authorizeHttpRequests(...)` or `RequestAuthorizationContext`: the API names and request contracts differ.

## 1. From Pure RBAC to Request-Aware Conditions

RBAC (role-based access control) is commonly expressed as:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated());
```

This is enough when the requirement is simply "which role can access which URL group." But suppose there is an endpoint:

```text
GET /api/reports/alice
GET /api/reports/bob
GET /api/reports/alice?view=full
```

All are HTTP GET requests to `/api/reports/**`, yet:

- Alice is allowed to view **alice**'s report in summary form.
- Alice is **not** allowed to view Bob's report even if she holds the report-reader role.
- An Auditor may view other users' data per policy.
- The `view=full` mode or `X-Report-Format: raw` header requires an additional `AUDITOR` role.
- Requests with unknown mode values, anomalous duplicate parameters, or missing required data must be denied in a controlled manner.

We need to decide simultaneously based on:

```text
ALLOW =
  authenticated principal
  AND matcher matches request group
  AND HTTP data is valid
  AND (
        (matching owner AND has ROLE_REPORT_READER)
        OR has ROLE_AUDITOR
      )
  AND (
        only normal representation requested
        OR has ROLE_AUDITOR
      )
```

This is an example of **combining RBAC with contextual conditions (contextual/ABAC)**. Crucially, roles and principals must come from an `Authentication` verified by the framework; paths/queries/headers only describe the request and **can be altered by the client**.

## 2. Path of an HTTP Authorization Decision

```text
HTTP client
   |
   v
Spring WebFlux WebFilter pipeline
   |
   v
Spring Security WebFilterChainProxy
   |
   +--> select first matching SecurityWebFilterChain
             |
             +--> Authentication WebFilters
             |       authenticate Basic/Bearer/Form per config
             |
             +--> AuthorizationWebFilter
                       |
                       +--> match HTTP method/path
                       +--> create AuthorizationContext
                       |      + ServerWebExchange
                       |      + URI variables extracted by matcher
                       |
                       +--> ReactiveAuthorizationManager.check(
                       |       Mono<Authentication>,
                       |       AuthorizationContext)
                       |       |
                       |       +--> Mono<AuthorizationDecision>(true/false)
                       |
                       +--> ALLOW: chain continues -> handler
                       +--> DENY: block handler, handle exception
                       +--> ERROR: propagate error through error pipeline
```

At the DSL layer:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/reports/{owner}")
        .access(customReportManager)
    .anyExchange().denyAll());
```

- `pathMatchers(...)` selects the **authorization rule** applied to the request within the chain.
- `.access(customReportManager)` asks the manager to decide based on **Authentication + AuthorizationContext**.
- `.anyExchange().denyAll()` ensures undefined URLs in the chain are not accidentally left open.
- `ServerHttpSecurity`'s `securityMatcher(...)`, if configured, decides **which chain** is selected at the earlier layer. Do not treat `pathMatchers` or `access` as a substitute for security chain selection.

If there are multiple `SecurityWebFilterChain`s, the proxy only applies the first chain matching the request; custom managers in other chains will **not** be invoked.

## 3. Key APIs

### 3.1. AuthorizationContext

`AuthorizationContext` is a class in `org.springframework.security.web.server.authorization`. It lets you read:

```java
ServerWebExchange exchange = context.getExchange();
Map<String, Object> variables = context.getVariables();
```

These two sources serve different needs:

| API | Data | Usage |
| --- | --- | --- |
| `context.getExchange()` | HTTP request, response, attributes, principal, and session APIs | Read method/path/headers/query; application data placed on the exchange if trusted |
| `context.getVariables()` | URI variables extracted by the **authorization matcher** | Read `owner` from matcher `/api/reports/{owner}` |
| `exchange.getRequest().getMethod()` | WebFlux HTTP method | Check GET/POST/PUT/DELETE if policy requires |
| `exchange.getRequest().getPath()` | WebFlux request path | Observe path; does not replace standard matcher |
| `exchange.getRequest().getQueryParams()` | `MultiValueMap` of query parameters | Inspect client-chosen mode/filter; reject unexpected duplicate values |
| `exchange.getRequest().getHeaders()` | HTTP headers | Read representation/client intent; never treat a custom header as a verified role |
| `exchange.getRequest().getCookies()` | Cookies sent by client | Input data, not proof of permission unless verified by an authentication mechanism |
| `exchange.getRequest().getRemoteAddress()` | Server-observed connection address | Not necessarily the end user's IP behind a proxy |
| `exchange.getAttributes()` | Attributes stored on exchange by WebFilters/handlers | Only trust data set and managed by a **trusted** component |
| `Authentication.getAuthorities()` | Permissions authenticated/mapped by the system | Trusted source of permissions for policies |

**Warning:** `context.getVariables()` comes from the **matcher in the authorization configuration**, which may not always match WebFlux controller attributes. Authorization runs **before** the route handler executes, so do not rely on `HandlerMapping.URI_TEMPLATE_VARIABLES_ATTRIBUTE` as the default source of URL variables at this stage. Use variables provided by `pathMatchers` when configuring the rule.

### 3.2. ReactiveAuthorizationManager and AuthorizationDecision

With Spring Security 6.x versions managed by Boot 3.3, the common pattern is:

```java
ReactiveAuthorizationManager<AuthorizationContext> manager =
        (authenticationMono, context) -> {
            // Read request from context.getExchange()
            // Read role/principal from authenticationMono
            return authenticationMono
                    .map(authentication ->
                            new AuthorizationDecision(
                                    /* allow condition */ true))
                    .defaultIfEmpty(new AuthorizationDecision(false));
        };
```

In Java, the two lambda parameters have types:

- `authenticationMono`: `Mono<Authentication>`, because the user may be unauthenticated and security context info is delivered reactively.
- `context`: `AuthorizationContext` containing the exchange and URI variables.

`AuthorizationDecision(true)` indicates permission granted; `AuthorizationDecision(false)` indicates permission denied. In practice, also distinguish errors during policy evaluation from denial decisions: **never treat infrastructure errors as an ALLOW signal**.

In newer API versions there is an `authorize(...)` method returning `AuthorizationResult`; the WebFlux 6.x version using `check(...)`/`AuthorizationDecision` in the DSL is the right contract for the Java 17+ example below. When upgrading major versions, re-check the Javadoc and migration guide.

### 3.3. When Authentication Is Missing

Be careful with code like:

```java
return authenticationMono.map(authentication ->
        new AuthorizationDecision(authentication.getName().equals(owner)));
```

If `authenticationMono` is empty, the publisher can complete **without emitting a decision**; Spring Security has abstain/empty handling paths depending on the mechanism. In a business policy where missing identity must be denied, write:

```java
return authenticationMono
        .map(authentication ->
                new AuthorizationDecision(
                        authentication.isAuthenticated()
                        && !(authentication instanceof AnonymousAuthenticationToken)
                        && authentication.getName().equals(owner)))
        .defaultIfEmpty(new AuthorizationDecision(false));
```

The code above is an **illustrative snippet**; it requires importing `AnonymousAuthenticationToken` and providing `owner`. Note that an anonymous token can have `isAuthenticated() == true` by object contract, so checking that flag alone is insufficient to treat the token as a real user principal. Having explicit authority policies also helps prevent anonymous tokens from being treated as valid users.

**Never call `block()` to extract `Authentication`** from a `Mono` in WebFlux. Compose using `map`/`flatMap` or built-in managers.

## 4. Which Data May Influence Authorization?

| Data | Who Controls It? | Safe Role in Policy |
| --- | --- | --- |
| `Authentication.getName()` | Identity verified by auth mechanism | Can serve as actor ID in demos; production prefers a stable user ID |
| `Authentication.getAuthorities()` | Encoded/mapped from identity provider or user store | Verified roles/scopes for authorization |
| `/reports/{owner}` | URL chosen by client | **Target resource to access**, does not prove ownership itself |
| Query `view=full` | Sent by client | Requests a sensitive representation; demands stronger permissions |
| Header `X-Report-Format: raw` | Sent by client | Requests a sensitive mode; demands stronger permissions |
| Header `X-Tenant-ID` | Sent by client, spoofable | Only a request to select a tenant; **never** trust as proof of tenant membership |
| Self-set cookie | Sent by client | Only carries authentication value after the framework verifies session/token |
| `X-Forwarded-For` | Spoofable if proxies do not strip/overwrite | Do not treat as trusted IP without verifying proxy chain and forwarded-header policy |
| Tenant/ownership read from DB | Server-verified by principal & resource | Stronger source for resource-level access decisions |
| Attributes from trusted security filter | Set by server in a verified filter after validating data | Usable if there is a clear contract and it cannot be easily overwritten |

**Insecure example:**

```java
// WRONG: Client self-sending X-User-Role: ADMIN grants admin access.
String requestedRole =
        context.getExchange().getRequest().getHeaders()
                .getFirst("X-User-Role");

boolean allow = "ADMIN".equals(requestedRole);
```

An attacker only needs to send the header. **Fix:** inspect `Authentication.getAuthorities()` issued by the authentication mechanism and, if necessary, verify organization/resource ownership from server-side sources. A header may *request a mode* that makes the policy stricter, never grant extra permissions itself.

### Distinguishing Authorization from Validation

- Validation verifies valid format/path/query, parameter counts, and data lengths.
- Authentication verifies identity/credentials.
- Authorization decides whether that principal is allowed to access the resource/mode.
- Business logic verifies actual resource state, tenant membership, ownership, workflow status, and deeper invariants.

You can reject invalid request values right inside the manager to **fail-closed**, though production APIs typically also have a separate validation layer returning 400 instead of folding all input errors into 403. Whether the response is 400 or 403, **never run the handler with elevated privileges** when input data has not been checked.

## 5. Designing a Sample Policy

The demo application provides the endpoint:

```text
GET /api/reports/{owner}?view=summary
GET /api/reports/{owner}?view=full
X-Report-Format: json | raw  (optional header)
```

Rules:

1. Request must be **GET**; other methods have no permitting rule and are denied at the fallback.
2. `owner` must be a valid name extracted by the matcher, non-empty; never use the path to self-assert ownership.
3. If `view` is absent, default is `summary`; if present, it must be **exactly one value**, either `summary` or `full`.
4. If `X-Report-Format` is absent, default is `json`; if present, it must be **exactly one value**, either `json` or `raw`.
5. An authenticated request may view summary/json if **owner matches the `Authentication` name and the caller has `ROLE_REPORT_READER`**, or if the caller has `ROLE_AUDITOR`.
6. If `view=full` or `X-Report-Format: raw`, then **`ROLE_AUDITOR` is mandatory**, even when the owner is reading their own report.
7. Missing `Authentication`, duplicate query/header values, unrecognized modes, or invalid path owner: **DENY**.
8. Response data in the demo is only a placeholder; the policy illustrates read permissions. In production, controllers/services must query resources properly by identity/resource to prevent IDOR.

### Decision Matrix

| Caller | Request | Result |
| --- | --- | --- |
| Alice, `ROLE_REPORT_READER` | `GET /api/reports/alice` | ALLOW |
| Alice | `GET /api/reports/bob` | DENY (different owner) |
| Bob, `ROLE_REPORT_READER` | `GET /api/reports/bob?view=summary` | ALLOW |
| Alice | `GET /api/reports/alice?view=full` | DENY (lacks AUDITOR) |
| Auditor, `ROLE_AUDITOR` | `GET /api/reports/bob?view=full` | ALLOW |
| Auditor | `GET /api/reports/bob` + `X-Report-Format: raw` | ALLOW |
| Alice | `GET /api/reports/alice` + `X-Report-Format: raw` | DENY |
| Alice | `GET /api/reports/alice?view=garbage` | DENY |
| Alice | `GET /api/reports/alice?view=summary&view=full` | DENY (duplicate param) |
| Not logged in | `GET /api/reports/alice` | DENY; with HTTP Basic may return 401 |
| Alice | `POST /api/reports/alice` | No permitting rule; CSRF may block first |

**Key distinction:** Headers or queries only *request a data mode*. Clients cannot send a value to gain more permissions. When a client requests a more sensitive representation, the policy demands the `AUDITOR` role.

## 6. Complete Runnable Example with Java 17+ and Spring Boot WebFlux

The application uses Spring Boot **3.3.13**, Java 17, WebFlux, Spring Security, and HTTP Basic. HTTP Basic makes testing each request with `curl` easy without setting up an OAuth Authorization Server. Users stored in memory and `{noop}` passwords are **for learning only**, unsuitable for production.

### 6.1. Project Structure

```text
exchange-authorization-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/ExchangeAuthorizationApplication.java
    test/
      java/example/ExchangeAuthorizationApplicationTests.java
```

Create `settings.gradle`:

```groovy
rootProject.name = 'exchange-authorization-demo'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Boot BOM manages compatible Spring Security, WebFlux, and Reactor versions. Do not add `spring-boot-starter-web` (Servlet MVC) to the demo and do not use Servlet's `HttpSecurity`/`SecurityFilterChain`.

### 6.2. Main Class, HTTP Endpoint, and Custom Authorization

Create `src/main/java/example/ExchangeAuthorizationApplication.java`:

```java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ExchangeAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExchangeAuthorizationApplication.class, args);
    }

    @GetMapping("/health")
    public String health() {
        return "OK";
    }

    @GetMapping("/api/reports/{owner}")
    public Mono<Map<String, String>> getReport(
            @PathVariable String owner,
            @RequestParam(name = "view", defaultValue = "summary")
                    String view,
            @RequestHeader(name = "X-Report-Format",
                    defaultValue = "json") String format) {

        // Only returns simulated data. Real apps must load
        // the actual resource and check permissions in the service.
        return Mono.just(Map.of(
                "owner", owner,
                "view", view,
                "format", format,
                "data", "demo-only"));
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/health").permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/reports/{owner}")
                        .access(reportAccess())
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Keep CSRF default: example only authorizes GET.
                .build();
    }

    private static ReactiveAuthorizationManager<AuthorizationContext>
            reportAccess() {

        return (authenticationMono, context) -> {
            ServerHttpRequest request =
                    context.getExchange().getRequest();

            Object ownerVariable =
                    context.getVariables().get("owner");

            String owner = ownerVariable instanceof String
                    ? (String) ownerVariable
                    : "";

            // The same variable must come from the authorization pathMatcher.
            boolean validOwner =
                    owner.matches("[A-Za-z0-9_-]{1,64}");

            // Do not treat duplicate ?view=... as a single valid value.
            List<String> views =
                    request.getQueryParams().get("view");

            boolean validView = views == null
                    || (views.size() == 1
                        && ("summary".equals(views.get(0))
                            || "full".equals(views.get(0))));

            String view = views == null
                    ? "summary"
                    : validView ? views.get(0) : "";

            // This header is chosen by the client to request a format,
            // never as proof of granted permission.
            List<String> formats =
                    request.getHeaders().get("X-Report-Format");

            boolean validFormat = formats == null
                    || (formats.size() == 1
                        && ("json".equals(formats.get(0))
                            || "raw".equals(formats.get(0))));

            String format = formats == null
                    ? "json"
                    : validFormat ? formats.get(0) : "";

            boolean isGet =
                    request.getMethod() == HttpMethod.GET;

            boolean sensitiveView = "full".equals(view)
                    || "raw".equals(format);

            boolean requestValid =
                    isGet && validOwner && validView && validFormat;

            return authenticationMono
                    .map(auth -> {
                        boolean loggedIn =
                                auth.isAuthenticated()
                                && !(auth instanceof
                                        AnonymousAuthenticationToken);

                        boolean isReader = hasAuthority(
                                auth, "ROLE_REPORT_READER");
                        boolean isAuditor = hasAuthority(
                                auth, "ROLE_AUDITOR");

                        boolean isOwner =
                                owner.equals(auth.getName());

                        boolean canRead = isAuditor
                                || (isReader && isOwner);

                        boolean canSeeRequestedView =
                                !sensitiveView || isAuditor;

                        boolean allow =
                                requestValid && loggedIn
                                && canRead && canSeeRequestedView;

                        return new AuthorizationDecision(allow);
                    })
                    .defaultIfEmpty(new AuthorizationDecision(false));
        };
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {

        for (GrantedAuthority granted : auth.getAuthorities()) {
            if (required.equals(granted.getAuthority())) {
                return true;
            }
        }
        return false;
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("REPORT_READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}read")
                .roles("REPORT_READER")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password("{noop}audit")
                .roles("AUDITOR")
                .build();

        return new MapReactiveUserDetailsService(
                alice, bob, auditor);
    }
}
```

### 6.3. Why Was Each Decision Written This Way?

**Path:** `pathMatchers(HttpMethod.GET, "/api/reports/{owner}")` matches the request and puts `owner` into `AuthorizationContext.getVariables()`. The owner value comes from the URL and **does not itself say the caller is the owner**. We compare it with `auth.getName()` obtained from the `Authentication` verified by HTTP Basic.

**Method:** `pathMatchers(HttpMethod.GET, ...)` already filters the method at the DSL layer. Checking `request.getMethod() == HttpMethod.GET` inside the custom manager illustrates reading `ServerWebExchange`; with this rule it is slightly redundant, though it makes the policy self-describing. Other methods reach the deny fallback. For POST requests, the CSRF filter may block before authorization, so do not attribute every 403 response to the custom manager.

**Query:** `view=summary` is the basic mode; `view=full` requires an auditor. If a user sends `view=full&view=summary`, using `getFirst` alone can create unpredictable behavior. The policy uses `List<String>` and rejects multi-value cases. It also rejects modes outside the allowlist.

**Header:** `X-Report-Format: raw` only requests a sensitive representation; **it does not grant permission**. Only the `AUDITOR` role allows `raw`. Headers are client-controlled so they can be spoofed and must be treated as untrusted input. Duplicate headers or values outside `json/raw` are denied.

**Role:** `User.withUsername(...).roles("REPORT_READER")` creates `ROLE_REPORT_READER`, and similarly `ROLE_AUDITOR`. Do not compare the literal username `"auditor"` to decide audit privileges; the actual role is the source of permission.

**Missing authentication:** the manager always returns `new AuthorizationDecision(false)` when the publisher is empty, preventing "no result" from being misinterpreted as permission. `AnonymousAuthenticationToken` is also excluded from real logged-in users.

**Reactive:** `authenticationMono.map(...)` combines identity asynchronously without `block()`. Since the policy in the example is an in-memory boolean computation, it does not need `Schedulers.boundedElastic()` or thread switching. If a DB lookup is needed, use a reactive repository and `flatMap`.

**Handler data:** the HTTP response only returns the string `demo-only`; a real application needs to load the resource by ID with proper tenant/user scoping and enforce service-layer authorization. Never treat HTTP rules as the sole defense for every way a service can be invoked.

**Passwords:** `{noop}` is only for a standalone demo; production requires a one-way password encoder with a suitable work factor and HTTPS. HTTP Basic sends credentials on every request, so transport security, rate limiting, and hashing resources are also critical.

## 7. Running the Example and Predicting Output

Requires JDK 17+ and Gradle compatible with Spring Boot 3.3.13. Run in the project directory:

```bash
gradle bootRun
```

If the project has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Open another terminal and try:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/reports/alice

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/bob"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice?view=full"

curl -i -u auditor:audit \
  "http://localhost:8080/api/reports/bob?view=full"

curl -i -u alice:learn -H "X-Report-Format: raw" \
  "http://localhost:8080/api/reports/alice"

curl -i -u auditor:audit -H "X-Report-Format: raw" \
  "http://localhost:8080/api/reports/bob"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice?view=summary&view=full"

curl -i -u alice:learn \
  "http://localhost:8080/api/reports/alice?view=unknown"
```

### Expected Results

| Request | Expected HTTP | Meaning |
| --- | --- | --- |
| `GET /health` | 200, `OK` | Public |
| `GET /api/reports/alice` no credentials | 401 Basic challenge | Unauthenticated |
| Alice → `/api/reports/alice` | 200 | Owner + reader |
| Alice → `/api/reports/bob` | 403 | Not owner, not auditor |
| Alice → `/api/reports/alice?view=full` | 403 | Full requires AUDITOR |
| Auditor → `/api/reports/bob?view=full` | 200 | AUDITOR has special permission |
| Alice + header `X-Report-Format: raw` | 403 | Client cannot self-request raw without AUDITOR |
| Auditor + `X-Report-Format: raw` | 200 | Has AUDITOR |
| Alice + two `view` values | 403 | Policy rejects ambiguous input |
| Alice + `view=unknown` | 403 | Invalid |
| POST to report GET endpoint | Blocked | CSRF or fallback deny; do not conclude from status alone |

When HTTP 200 is returned, the endpoint returns JSON with properties such as `owner`, `view`, `format`, and `data`. For example, when Alice views summary:

```json
{
  "owner": "alice",
  "view": "summary",
  "format": "json",
  "data": "demo-only"
}
```

This is the **expected content shape**, not a guarantee of identical field order or whitespace: the JSON serializer may order fields differently. What matters is the HTTP status and field values. For 403/401, the `getReport` handler is not invoked to produce the JSON above.

## 8. Testing with Spring Boot / WebTestClient

Create `src/test/java/example/ExchangeAuthorizationApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeAuthorizationApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicHealthIsAllowed() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void unauthenticatedRequestRequiresBasicAuth() {
        client.get().uri("/api/reports/alice")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanAccessOwnSummary() {
        client.get().uri("/api/reports/alice")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice")
                .jsonPath("$.view").isEqualTo("summary");
    }

    @Test
    void readerCannotAccessAnotherOwner() {
        client.get().uri("/api/reports/bob")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerCannotRequestFullView() {
        client.get().uri("/api/reports/alice?view=full")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void auditorCanRequestOtherUsersFullView() {
        client.get().uri("/api/reports/bob?view=full")
                .headers(h -> h.setBasicAuth("auditor", "audit"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("bob")
                .jsonPath("$.view").isEqualTo("full");
    }

    @Test
    void clientHeaderCannotGrantRawView() {
        client.get().uri("/api/reports/alice")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .header("X-Report-Format", "raw")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void auditorCanRequestRawView() {
        client.get().uri("/api/reports/bob")
                .headers(h -> h.setBasicAuth("auditor", "audit"))
                .header("X-Report-Format", "raw")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.format").isEqualTo("raw");
    }

    @Test
    void duplicateViewIsDenied() {
        client.get()
                .uri("/api/reports/alice?view=summary&view=full")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownViewIsDenied() {
        client.get().uri("/api/reports/alice?view=unknown")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

The tests verify **real rules in the security filter chain**, not merely controller logic. The goal of this lesson is to prove that **actor + resource owner + mode from exchange** produces the right decision. `WebTestClient` lets you send paths, queries, headers, and Basic credentials to make each condition explicit.

**Additional tests needed before going to production:** GET vs. HEAD/OPTIONS, encoded paths, routes not matching matchers, duplicate queries, duplicate headers, Unicode names/tenant IDs, expired tokens, authority mapping, locked users, and database failures. Never rely on a single HTTP 200 test to conclude a policy is secure.

## 9. When Permissions Depend on Database Data

In the demo, the owner is tied to the username in the URL purely for clarity. With real data, users can change usernames, reports have distinct resource IDs, and permissions may depend on **ACLs/tenant membership**. Never allow access based on a client claiming `owner=alice` without verifying who owns the report in the database.

Suppose the request is `GET /api/reports/{reportId}` where `reportId` is a report identifier. Authorization needs:

```text
Authentication (verified userId/tenantId)
   + URL reportId (resource client wants to view)
   + Server-side lookup: report.ownerId, report.tenantId,
                          report.state, sharing grants
   -> ALLOW/DENY decision
```

The following snippet illustrates the idea using a **reactive** repository (not a standalone application):

```java
ReactiveAuthorizationManager<AuthorizationContext> policy =
        (authenticationMono, context) -> {

            Object rawId = context.getVariables().get("reportId");

            if (!(rawId instanceof String reportId)
                    || reportId.isBlank()) {
                return Mono.just(new AuthorizationDecision(false));
            }

            return authenticationMono
                    .flatMap(authentication -> {
                        if (!authentication.isAuthenticated()
                                || authentication instanceof
                                        AnonymousAuthenticationToken) {
                            return Mono.just(
                                    new AuthorizationDecision(false));
                        }

                        return reportRepository.findById(reportId)
                                .map(report -> {
                                    boolean sameTenant =
                                            report.tenantId().equals(
                                                trustedTenantOf(authentication));

                                    boolean canRead =
                                            report.ownerId().equals(
                                                trustedUserIdOf(authentication))
                                            || hasReadGrant(
                                                authentication, report);

                                    return new AuthorizationDecision(
                                            sameTenant && canRead);
                                })
                                .defaultIfEmpty(
                                    new AuthorizationDecision(false));
                    })
                    .defaultIfEmpty(new AuthorizationDecision(false));
        };
```

**Limitations of this illustrative snippet:** `reportRepository`, `trustedTenantOf`, `trustedUserIdOf`, and `hasReadGrant` are abstractions the application must supply; `report` must have a corresponding record/domain model. This snippet does not compile standalone; the complete Gradle project is in Section 6.

**Principles when placing DB logic inside a manager:**

- `reportRepository.findById(...)` should be a **reactive** repository returning a publisher, never calling `block()` on the event loop.
- If the report is not found or the user lacks permission, `Mono.empty()` must become DENY (or be handled intentionally as 404 at the API layer); never auto-allow.
- If the DB encounters an error, let the error travel through infrastructure monitoring/error handling; **never** convert it into `AuthorizationDecision(true)` or swallow the error to continue to the handler.
- If permissions change rapidly, re-check at business execution time; avoid TOCTOU (time-of-check to time-of-use) races between authorization and data-modifying operations.
- Never use arbitrary user ID/tenant ID values from request headers instead of verified information from `Authentication`/DB.
- In multi-tenant systems, repositories should **scope queries to the principal's tenant** rather than loading all records globally and filtering afterwards if other paths could leak data.

### Service-Layer Authorization for Defense in Depth

HTTP managers protect routes exposed to the Internet. However, if the same service is called from a scheduler, message listener, RSocket, or internal job, there is no guarantee it passed through `AuthorizationWebFilter`. For sensitive business logic, add checks in the service—such as reactive method security `@EnableReactiveMethodSecurity` and `@PreAuthorize` when appropriate. Method security must be configured properly for the Reactor context and non-HTTP call paths.

**Do not duplicate logic inconsistently**: place business/ACL policies in a shared service, while the HTTP manager handles routing and preliminary permissions. Test both APIs and services in their respective contexts.

## 10. IP Info, Proxies, Headers, and Trust Sources

`ServerWebExchange` allows reading `getRemoteAddress()` and HTTP headers. Behind a reverse proxy/load balancer, however:

```text
Client -> CDN -> Ingress -> App WebFlux

request.getRemoteAddress() may be the ingress IP.
X-Forwarded-For may contain values forwarded by upstream.
```

**Never trust `X-Forwarded-For`, `Forwarded`, or `X-Real-IP` unconditionally**. If the app is directly exposed to the Internet, attackers can forge those headers themselves. To use IP addresses in policies:

1. Allow traffic to the app only from **trusted** reverse proxies.
2. Configure the edge/gateway to overwrite or strip client-supplied forwarded headers.
3. Configure forward-header handling in the application per actual deployment (e.g., `server.forward-headers-strategy` in Spring Boot).
4. Determine which address is the true end-client IP after the proxy chain, avoiding trusting the leftmost client-supplied entry.
5. Never rely on IP alone to grant sensitive permissions: combine authentication, roles, network policy, MFA, and device controls as appropriate.
6. Write integration tests simulating an attacker sending forged headers.

Distinguish **network access control** (which networks may connect) from **business authorization** (which reports may be viewed). Inspecting an HTTP header used by clients to pick a representation mode is valid when it only tightens the policy; using a header as a principal/role is wrong.

### Cookies and Query Parameters Are Not Inherently Trustworthy Either

A session cookie only carries meaning after Spring Security/Spring Session verifies it, locates the session, and loads a valid `Authentication`. Reading `Cookie: role=ADMIN` manually in a custom manager to grant `ADMIN` is a vulnerability.

A query `?tenant=abc` can serve as a request to select a tenant, but must be compared against **verified membership** in the token/database. Blindly trusting `tenant=abc` to mean the user belongs to tenant `abc` causes IDOR/cross-tenant data leaks.

## 11. Rule Priority, Ordering, and Fail-Closed

### 11.1. Rule Order Within One Chain

```java
// Wrong: overly broad first rule can swallow stricter rules below.
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll());
```

A request to `/api/admin/...` matches `/api/**` first, so the subsequent `ADMIN` rule is never applied. Place **specific rules before general rules**:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll());
```

Similarly, if a custom manager applies to `/api/reports/{owner}`, it must be placed before an overly broad `/api/**` rule. `anyExchange().denyAll()` should be the final fallback.

### 11.2. Order of SecurityWebFilterChains

If multiple `SecurityWebFilterChain` beans exist, each chain's `@Order` and `securityMatcher` select the chain **before** `authorizeExchange` is evaluated internally. `@Order` on global `WebFilter` beans and `SecurityWebFiltersOrder` inside a chain are two more ordering layers.

Never assume a custom manager will be called if the request falls into a different chain. Test overlapping URLs, the fallback chain, and the case where no chain matches. **No matching chain does not automatically mean DENY**; ensure full protective coverage.

### 11.3. Mono.empty, DENY, and ERROR

| Signal from Custom Manager | Important Interpretation | Handling |
| --- | --- | --- |
| `Mono.just(new AuthorizationDecision(true))` | Permitted by evaluated policy | Emit only with sufficient proof |
| `Mono.just(new AuthorizationDecision(false))` | Denied | Use when lacking permission or invalid input |
| `Mono.empty()` | No decision emitted | Avoid letting missing identity/lookup become an unintended abstain |
| `Mono.error(...)` | Evaluation error, not a role DENY | Propagate error or handle fail-closed with metrics; never convert to ALLOW |

For an explicit policy, use `defaultIfEmpty(new AuthorizationDecision(false))` so missing context does not become "allowed". If the permission/ACL backend fails, **never** write:

```java
// WRONG: database error allows the user through.
return policy.check(authentication, context)
        .onErrorReturn(new AuthorizationDecision(true));
```

Infrastructure errors should return 5xx, emit metrics/alerts, and prevent the API from executing business logic. Avoid `onErrorComplete()` swallowing the error and letting downstream continue with an ambiguous context.

### 11.4. HTTP 401 and 403

- **401 Unauthorized:** request lacks valid authentication; HTTP Basic/Bearer entry points may send a challenge.
- **403 Forbidden:** user is authenticated but lacks permission, or another filter such as CSRF rejected the request.
- **400 Bad Request:** validation catches invalid input when the pipeline reaches the validation layer; the manager may also deny early per policy.
- **5xx:** system error when loading permissions from DB, network, serializer, etc., per error handling.

Do not assume "403 definitely came from the custom `ReactiveAuthorizationManager`" when CSRF, CORS, matchers, or authentication filters are also present. Tests must identify the exact **rejecting layer**.

## 12. Performance and Observability

A custom manager can run on **every request** matching the rule. Therefore:

- Do not call blocking DB operations, blocking HTTP clients, or `Thread.sleep(...)` on the Netty event loop.
- Use `ReactiveCrudRepository`/`WebClient` and `flatMap` operators when I/O is needed; if synchronous libraries are unavoidable, offload with bounded concurrency by design and load-test.
- Avoid heavy duplicate data lookups within the same request; consider short-lived request-scoped caching or efficient combined queries.
- Cross-request caching of ALLOW decisions must have clear invalidation when roles/tenant membership/resource ownership change; sloppy caching leaves stale permissions active.
- Policies should be side-effect-free (do not deduct quotas or change order state) because the framework may re-evaluate or requests may be canceled.
- Never log passwords/tokens/cookies/session IDs, sensitive raw queries, or the entire `SecurityContext`.
- Measure authorization and backend entitlement/ACL latency, allow/deny/error rates, 401/403/5xx counts, and p95/p99 latency under high load.
- For sensitive tenant data, audit logs should record **actor ID, resource ID, policy version, and outcome** in an approved format, avoiding leaking private data.

### Incident Investigation Matrix

| Symptom | Possibilities | What to Check |
| --- | --- | --- |
| User has role but gets 403 | Owner/path mismatch or mode requires AUDITOR | `context.getVariables()`, actual authorities, query/headers |
| User from another tenant is allowed | Trusted header or path instead of DB/claims | Trusted tenant source and ownership lookup |
| Custom manager never called | Earlier rule/chain matched first | Order of `securityMatcher`, `@Order`, `pathMatchers` |
| Same URL sometimes 200, sometimes 403 | Different query/header, role changed, or cache | Request context, JWT/session, ACL data |
| 403 on POST despite having role | CSRF blocked first | CSRF token, cookies, and HTTP method |
| 401 despite sending Basic | Wrong/expired credentials or manager rejected | Authentication mechanism and actual headers |
| 5xx when Redis/DB fails | Policy dependency unavailable | Controlled error logs, timeouts, circuit breaking |
| Slow event loop | Blocking inside custom manager | Thread dumps/profiling, reactive driver, latency |
| Duplicate query causes strange permissions | Parameter pollution | Check value count, not just `getFirst` |

## 13. Secure Implementation Checklist

1. **Separate inputs:** take actor/authorities from `Authentication`, resource from URL and server-side data; never take roles from self-sent headers.
2. **Correct matchers:** `pathMatchers` covers the right HTTP methods, URLs, and capture variables; specific rules are evaluated first.
3. **Correct chains:** `securityMatcher` and `@Order` do not exclude requests from the intended chain; a safe fallback exists.
4. **Check ownership:** compare stable user/tenant IDs; never treat path variables as proof of permission.
5. **Validate queries/headers:** handle invalid modes, duplicate values, missing fields, and unsupported values.
6. **Fail-closed:** missing authentication or missing ACL -> DENY; infrastructure error -> never ALLOW.
7. **Non-blocking:** compose identity/entitlement via Reactor operators; never `block()` on the event loop.
8. **HTTP status:** distinguish missing auth, insufficient permissions, CSRF failure, and system errors.
9. **Defense in depth:** sensitive resources have additional authorization in the service/domain, not only at routes.
10. **Negative testing:** different owner, missing role, higher mode, spoofed header, duplicate query, and paths outside matchers.
11. **No leaks:** limit logging of headers/tokens; if using real IP, verify proxy trust.
12. **Production observability:** authorization latency, deny/error metrics, auditing, and testing after every policy change.

## 14. Self-Check Questions

**Question 1.** How does `AuthorizationContext.getExchange()` differ from `getVariables()`?  
**Answer:** `getExchange()` provides the `ServerWebExchange` with HTTP request/response/attributes; `getVariables()` provides URI variables extracted by the authorization matcher.

**Question 2.** Why should you not use `X-User-Role: ADMIN` to grant admin access?  
**Answer:** HTTP headers can be forged by clients. Roles must come from a verified `Authentication`/identity provider.

**Question 3.** Alice has `ROLE_REPORT_READER`; can she access `/api/reports/bob`?  
**Answer:** No under the sample policy, because the read role alone is insufficient: Alice is neither the owner nor an `AUDITOR`.

**Question 4.** Alice sends `X-Report-Format: raw`; does her permission automatically escalate?  
**Answer:** No. The header only requests the `raw` representation; the policy requires `ROLE_AUDITOR` for raw output.

**Question 5.** Where can `pathMatchers(HttpMethod.GET, "/api/reports/{owner}")` pass `owner` to a custom manager?  
**Answer:** `AuthorizationContext.getVariables().get("owner")`. There is no need to wait for the controller to run to read the path variable.

**Question 6.** Does `Mono.empty()` from a custom authorization manager guarantee a definite DENY?  
**Answer:** Do not rely on implicit empty semantics. For policies that must deny when data is missing, explicitly return `AuthorizationDecision(false)`, for example with `defaultIfEmpty(...)`.

**Question 7.** Should you call `block()` to read roles or ownership from a reactive database inside a manager?  
**Answer:** No. Use `flatMap`/`map` and a reactive repository; blocking can stall the event loop.

**Question 8.** Why might `POST /api/reports/alice` receive 403 even before reaching the report manager?  
**Answer:** The CSRF filter can block state-changing methods before authorization. Additionally, the report manager is attached to a GET matcher, so POST does not invoke that manager.

**Question 9.** If you add an `/api/**.authenticated()` rule before the report rule, will the custom manager run?  
**Answer:** Likely not. The first rule matches first and decides, so specific rules must be placed before broad rules.

**Question 10.** Once a request passes HTTP authorization, is the service necessarily safe when invoked by a message listener?  
**Answer:** No. A message listener may not go through `AuthorizationWebFilter`; business permissions should be protected at the service/domain layer when multiple entry points exist.

**Question 11.** Is an address from `X-Forwarded-For` always a trustworthy client IP?  
**Answer:** No. You must have trusted reverse proxies, filtering/overwriting of forwarded headers, and an appropriate network boundary.

**Question 12.** If the entitlement database fails, can you return ALLOW because you "aren't sure it's forbidden"?  
**Answer:** No. An infrastructure failure is not proof of permission; fail closed or return an appropriate error.

**Key Takeaway:** In Spring Security WebFlux, `ReactiveAuthorizationManager<AuthorizationContext>` lets you combine **verified `Authentication`/authorities** with **`ServerWebExchange` and URI variables** to build conditional HTTP authorization. Request conditions can make a policy stricter, but **they can never replace a trusted permission source**. Use specific matchers, emit clear ALLOW/DENY decisions, compose reactive I/O properly, and test denied cases too.

## References

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `access`, and wiring a custom `ReactiveAuthorizationManager`.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): reactive authorization and authentication DSL.
- [Spring Security — AuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html): `getExchange()` and `getVariables()`.
- [Spring Security — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): reactive check/verify contract.
- [Spring Security — AuthorizationDecision API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html): representing granted/denied decisions.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): protecting service methods in reactive pipelines.
- [Spring Framework — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request/response/attributes/session API.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): why POST requests can be denied before authorization.
