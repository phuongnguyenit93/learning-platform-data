# AuthenticationWebFilter and Selecting Requests Requiring Authentication

## 1. Learning Objectives and the Problem to Solve

In Spring Security reactive (Spring WebFlux), **not every HTTP request needs a new authentication attempt**. A request may fall outside the scope of the authentication mechanism under consideration, carry no credentials, carry invalid credentials, or already be authenticated and need to proceed to authorization.

`AuthenticationWebFilter` is a Spring Security `WebFilter` responsible for **attempting to authenticate a specific request** when that request meets the activation condition. It coordinates with `ServerWebExchangeMatcher`, `ServerAuthenticationConverter`, and `ReactiveAuthenticationManager`, then transitions to the success or failure branch.

The most important point: **whether authentication is attempted on a request is different from whether it is allowed to access a resource**. Those decisions live at different layers.

After this lesson, you should be able to:
- Explain the sequence `requiresAuthenticationMatcher` → `ServerAuthenticationConverter` → `ReactiveAuthenticationManager` → success/failure handler.
- Distinguish `Mono.empty()` meaning *do not attempt authentication* in the converter from `Mono.error(AuthenticationException)` meaning *attempted authentication but failed*.
- Distinguish the `SecurityWebFilterChain` matcher, the `AuthenticationWebFilter` matcher, and `authorizeExchange` rules.
- Know how to configure a filter for a specific set of URLs so requests without credentials continue while invalid credentials are rejected.
- Understand SecurityContext, Reactor Context, sessions/cookies, and stateless setups.
- Build and test a runnable Java 17+ example with Spring Boot WebFlux.

## 2. Where `AuthenticationWebFilter` Sits in Spring Security WebFlux

Diagram for a request entering the application:

~~~text
HTTP request
    │
    ▼
WebFlux / Spring Security WebFilterChainProxy
    │
    │ Selects matching SecurityWebFilterChain (if there are multiple chains)
    ▼
Selected SecurityWebFilterChain
    │
    ├─ other security filters: context, CSRF, ...
    │
    ▼
AuthenticationWebFilter
    │
    ├─ requiresAuthenticationMatcher matches?
    │   ├─ No → skip authentication in this filter, continue chain
    │   └─ Yes
    │       ▼
    │   ServerAuthenticationConverter.convert(exchange)
    │       ├─ Mono.empty() → no authentication request, continue chain
    │       └─ emits unauthenticated Authentication
    │           ▼
    │       ReactiveAuthenticationManager.authenticate(authentication)
    │           ├─ succeeded → SecurityContext + success handler
    │           ├─ AuthenticationException error → failure handler
    │           └─ undecided / empty → must understand manager contract clearly
    ▼
AuthorizationWebFilter / authorizeExchange
    │
    ├─ permitAll / authenticated / hasRole / hasAuthority / denyAll
    ▼
Handler / RouterFunction / Controller (if allowed)
~~~

`AuthenticationWebFilter` does not magically verify passwords, API keys, or JWTs on its own. The filter **orchestrates**, while the converter reads request data and the manager verifies that data. Authorization then decides access permissions later.

Several built-in Spring Security WebFlux mechanisms (HTTP Basic, form login, OAuth2 Resource Server) already register appropriate authentication components through `ServerHttpSecurity` configuration. **You do not need to create `AuthenticationWebFilter` manually for every application.** A custom filter is typically suitable when implementing a custom credential method with a clear contract.

## 3. Four Independent Decisions Never to Confuse

| Decision level | Typical API | Question answered | Does NOT mean |
| --- | --- | --- | --- |
| Chain selection | `ServerHttpSecurity.securityMatcher(...)` | Which SecurityWebFilterChain applies to the request? | The request is already allowed access |
| Selecting requests to attempt auth | `AuthenticationWebFilter.setRequiresAuthenticationMatcher(...)` | Should this specific authentication filter inspect the request? | Credentials are valid |
| Credential detection | `ServerAuthenticationConverter.convert(...)` | Is there login data to send to the manager? | The user is authenticated |
| Authorization | `authorizeExchange(...).pathMatchers(...).authenticated()/permitAll()/hasRole(...)` | What is the request allowed to do with the current identity? | Replacing credential verification |

Example:
- A general chain matches **all** URLs.
- A dedicated API-key `AuthenticationWebFilter` only inspects `/api/**`.
- The converter only creates an authentication if an `X-API-Key` header is present.
- `/api/public` can be `permitAll`, while `/api/me` requires `authenticated()` and `/api/admin` requires `ROLE_ADMIN`.

Even if the filter **is allowed to inspect** `/api/public`, a request without an API key can still pass through `permitAll`. Yet a request **actively sending an invalid API key** can be rejected by the filter before reaching authorization. The word "public" only speaks to access permissions; it does not promise that any invalid credentials sent to that URL will be ignored.

## 4. `setRequiresAuthenticationMatcher`: Filtering Requests Before Reading Credentials

Declaring on `AuthenticationWebFilter`:

~~~java
AuthenticationWebFilter filter = new AuthenticationWebFilter(manager);

filter.setRequiresAuthenticationMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

`setRequiresAuthenticationMatcher(ServerWebExchangeMatcher)` defines **the condition that must be met before the filter attempts to convert the request into an Authentication**.

With the matcher above:
- GET `/api/me`: matches; converter is evaluated.
- GET `/api/admin`: matches; converter is evaluated.
- GET `/api/public`: also matches; whether login is required is a separate authorization rule.
- GET `/public`: does not match; the custom filter passes through without trying to read credentials.

When you **do not configure a matcher**, the default for `AuthenticationWebFilter` is to match all requests. This does **not** mean every request runs the manager, because the converter can still return `Mono.empty()` when no credentials are seen.

`PathPatternParserServerWebExchangeMatcher` is WebFlux's matcher accepting path patterns. You can configure matchers by HTTP method or combine multiple conditions, but every matcher must have a clear target: URL, HTTP method, request type, etc. Never match solely on an uncontrolled header if the presence of that header could bypass an intended protection step.

### 4.1. How Does a Chain's `securityMatcher` Differ from `requiresAuthenticationMatcher`?

In a multi-chain application:

~~~java
@Bean
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .build();
}
~~~

`securityMatcher` decides whether **the entire chain** is selected. A filter inside an unselected chain will not run, regardless of the filter's own matcher. Once a chain is selected, `requiresAuthenticationMatcher` decides solely whether **a specific AuthenticationWebFilter inside that chain** attempts to convert credentials.

You can also use a single global chain and restrict the custom filter via `requiresAuthenticationMatcher`, as in the complete example below. That way `/public` stays inside the security chain yet does not trigger API-key authentication.

## 5. `ServerAuthenticationConverter`: Credentials Present or Not?

`org.springframework.security.web.server.authentication.ServerAuthenticationConverter` is a strategy:

~~~java
Mono<Authentication> convert(ServerWebExchange exchange);
~~~

It reads `ServerWebExchange` (request, headers, cookies, parameters...) and creates an **Authentication requesting verification** or emits empty.

Example converter accepting only an API key in a header:

~~~java
ServerAuthenticationConverter converter = exchange ->
    Mono.justOrEmpty(
            exchange.getRequest().getHeaders().getFirst("X-API-Key"))
        .map(key -> (Authentication)
            UsernamePasswordAuthenticationToken.unauthenticated(
                "api-key", key));
~~~

In the snippet above, `"api-key"` is just a demo label. The raw value from the header is kept as `credentials` for **the manager to check**. The token is created with `unauthenticated(...)` because nothing has been verified yet; never call the `authenticated(...)` factory directly on client-supplied data.

The converter has three distinct cases:

1. **No header** → `Mono.empty()`. The filter interprets this as **no authentication request** to try and continues the chain. Authorization later can allow `/api/public` or reject `/api/me`.
2. **Header present** → emits an unauthenticated `Authentication`. The manager must verify the key. Even an empty or wrong string can be forwarded to the manager to emit an explicit error.
3. **Syntactically invalid data** → depending on the protocol, the converter may emit an `AuthenticationException` (e.g., `BadCredentialsException`) to signal an invalid authentication attempt; do not use `Mono.empty()` as a way to hide login errors that should be rejected.

Distinguishing `Mono.empty()` from `Mono.error(...)` is central to reactive authentication handling:

| Signal from converter | Filter interprets as | Example |
| --- | --- | --- |
| `Mono.empty()` | Do not attempt authentication via this mechanism | No `X-API-Key` |
| `Mono.just(unauthenticatedToken)` | Credentials present, send to manager | `X-API-Key` header present |
| `Mono.error(AuthenticationException)` | Authentication error to handle | Token/header malformed per converter contract |

**Note:** `AuthenticationWebFilter`'s default converter, if you do not replace it, is `ServerHttpBasicAuthenticationConverter`. Therefore, for a custom API-key mechanism, you must configure `setServerAuthenticationConverter(...)`; otherwise the filter will parse HTTP Basic instead of your API-key header.

## 6. `ReactiveAuthenticationManager`: Where Credentials Are Judged Valid or Not

`ReactiveAuthenticationManager` receives `Authentication` from the converter and returns `Mono<Authentication>`. Per the framework contract:
- Emits an authenticated `Authentication`: success.
- Emits an `AuthenticationException` error: credentials were processed but invalid.
- Emits empty: the manager **cannot decide** for that request type (usually because it does not support the token form), not equivalent to success.

Illustrative logic:

~~~java
ReactiveAuthenticationManager manager = incoming -> {
    if (!(incoming instanceof UsernamePasswordAuthenticationToken)) {
        return Mono.empty(); // Manager does not handle this type.
    }

    if (!"expected-key".equals(incoming.getCredentials())) {
        return Mono.error(new BadCredentialsException("Invalid API key"));
    }

    Authentication trusted = UsernamePasswordAuthenticationToken.authenticated(
        "reader",
        null,
        List.of(new SimpleGrantedAuthority("ROLE_READER"))
    );
    return Mono.just(trusted);
};
~~~

This is an **illustrative snippet**, not a standalone Java program. Only after the manager verifies the key does it build a token with `authenticated(...)` and assign authorities. The resulting token's credentials can be `null` to avoid retaining secrets.

A manager must not:
- Call `block()` inside the pipeline to query a database when a reactive repository/client is available.
- Assign `ROLE_ADMIN` from an unverified client-sent role field.
- Turn an invalid key into `Mono.empty()` just to avoid returning an error; emit `AuthenticationException` per the contract.
- Log raw passwords/API keys/JWTs. External error content should remain generic to avoid leaking credential details.

With true async I/O, the manager can return a `Mono` from a reactive repository, inspect the result using `flatMap` or appropriate operators, and emit an authenticated authentication. Do not assume wrapping blocking code in `Mono.defer` automatically makes it non-blocking.

## 7. Success, Failure, and `SecurityContext` Lifecycle

`AuthenticationWebFilter` exposes these hooks:

~~~java
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
filter.setSecurityContextRepository(securityContextRepository);
~~~

**On authentication success**, the filter takes the verified `Authentication`, builds the appropriate `SecurityContext`, saves it through the configured `ServerSecurityContextRepository`, and attaches the security context to the Reactor Context of the downstream branch. The success handler decides what happens next: for example continuing the filter chain for an API, or redirecting after form login.

- The default success handler is `WebFilterChainServerAuthenticationSuccessHandler`: continues the processing chain.
- The default context repository on `AuthenticationWebFilter` is `NoOpServerSecurityContextRepository`: does not actively save the security context across requests.
- If using session login, the corresponding configuration/repository mechanism can save and load the SecurityContext via the session for subsequent requests. Repository choice must align with the authentication model.

**On authentication failure**, for example when the manager emits `BadCredentialsException`, the failure handler is invoked. The default filter prompts for HTTP Basic authentication; for custom APIs, set a failure handler returning an appropriate status without leaking credentials. Technical errors such as data-store timeouts should not be silently "ignored to let login pass".

**When the converter returns empty**, the filter **does not construct a successful Authentication**: the request moves on; authorization remains responsible for blocking areas requiring login.

### 7.1. `ReactiveSecurityContextHolder` and Reactor Operators

In Spring WebFlux, the security context is bound to the reactive chain via the Reactor Context; it can be accessed with:

~~~java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

`ReactiveSecurityContextHolder.getContext()` returns a publisher, not a synchronous `SecurityContext` directly. Do not read `SecurityContextHolder` assuming Servlet `ThreadLocal` inside WebFlux handlers, and never manually `block()`/`subscribe()` in a handler to read the username.

### 7.2. Never Confuse Authentication with Authorization

Even when the manager authenticates successfully, a request can still be rejected with 403 due to missing permissions in `authorizeExchange`. For instance, `reader`'s valid API key only has `ROLE_READER`; `/api/admin` needs `ROLE_ADMIN`. Conversely, a `permitAll` endpoint can return 200 without ever creating an `Authentication` for the client.

In a custom filter, *failed authentication* typically returns 401 per API policy, while *authorization denying an already logged-in user* typically returns 403. Actual HTTP responses also depend on the configured authentication entry point, failure handler, and access-denied handler.

## 8. Runnable Example: API Key Handled Only on `/api/**`

This example uses **Spring Boot 3.3.13, Java 17+, and Gradle 8.x**. It is a **simulated API-key mechanism for learning**; hard-coded keys in source code are not suitable for production. Real systems need secret stores, rotation/revocation workflows, TLS, log controls, and secure key-checking practices. For JWT/OAuth2, prefer Spring Security OAuth2 Resource Server instead of writing a custom filter.

Things to observe:
- `/public` is outside `/api/**`: the custom authentication filter skips it.
- `/api/public` is within filter scope, yet authorization does not require login; without a header it still gets 200.
- `/api/me` requires authentication: no header → 401; valid key → 200.
- `/api/admin` requires ADMIN role: reader key → 403, admin key → 200.
- An **invalid** API-key header on `/api/public` can still trigger a failed authentication attempt → 401, even though the endpoint rule is `permitAll`.

### 8.1. Project Setup

Structure:

~~~text
reactive-auth-filter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── ReactiveAuthFilterApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── AuthenticationFilterTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-auth-filter-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

Spring Boot manages compatible Spring Security and Reactor versions via dependency management; do not pin child library versions arbitrarily. In other projects, use a supported Boot version already tested by your project.

### 8.2. Startup Class

`src/main/java/demo/ReactiveAuthFilterApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthFilterApplication.class, args);
    }
}
~~~

### 8.3. Configuring `AuthenticationWebFilter` with a Clear Scope

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    ReactiveAuthenticationManager apiKeyManager() {
        return incoming -> {
            if (!(incoming instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty(); // Does not recognize other token types.
            }

            if (!(incoming.getCredentials() instanceof String key)) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            if ("reader-demo-key".equals(key)) {
                return Mono.just(trusted("reader", "ROLE_READER"));
            }

            if ("admin-demo-key".equals(key)) {
                return Mono.just(trusted("admin", "ROLE_ADMIN"));
            }

            return Mono.error(
                new BadCredentialsException("Invalid API key"));
        };
    }

    private static Authentication trusted(String name, String authority) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http,
                                   ReactiveAuthenticationManager apiKeyManager) {

        AuthenticationWebFilter apiKeyFilter =
            new AuthenticationWebFilter(apiKeyManager);

        // Only /api/** requests trigger the filter's converter.
        apiKeyFilter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        );

        // No header => Mono.empty() => do not attempt authentication.
        // Header present => UNAUTHENTICATED Authentication for manager to verify.
        ServerAuthenticationConverter converter = exchange ->
            Mono.justOrEmpty(
                    exchange.getRequest().getHeaders()
                        .getFirst("X-API-Key"))
                .map(key -> (Authentication)
                    UsernamePasswordAuthenticationToken.unauthenticated(
                        "api-key", key));

        apiKeyFilter.setServerAuthenticationConverter(converter);

        // Each request provides its own key; do not save SecurityContext
        // across sessions or requests in the custom filter.
        apiKeyFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        // Authentication failure: return 401, do not expose the API key.
        apiKeyFilter.setAuthenticationFailureHandler((web, exception) -> {
            var response = web.getExchange().getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        });

        // Use default success handler: continue WebFilterChain.
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public", "/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            // Do not use Basic / form login in the API key example.
            .httpBasic(spec -> spec.disable())
            .formLogin(spec -> spec.disable())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint((exchange, cause) -> {
                    var response = exchange.getResponse();
                    response.setStatusCode(HttpStatus.UNAUTHORIZED);
                    return response.setComplete();
                })
            )
            .addFilterAt(apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }
}
~~~

**Key points to understand in the code:**

1. `@EnableWebFluxSecurity` and `SecurityWebFilterChain` configure web security infrastructure/rules. Spring Boot with the security starter also provides corresponding auto-configuration; the annotation is placed here to make configuration explicit.
2. We only create **one default chain matching every request**. `setRequiresAuthenticationMatcher("/api/**")` limits **only the API-key authentication filter**, not the protection scope of the chain.
3. `converter` returns `Mono.empty()` when `X-API-Key` is absent. This is the **no authentication attempt** case, distinct from a header with a wrong value. A wrong key makes `apiKeyManager` emit `BadCredentialsException`.
4. `UsernamePasswordAuthenticationToken.unauthenticated` acts as a *temporary credential carrier* because the example avoids creating a new token class. In complex systems, you can use a dedicated custom `Authentication` so the manager can clearly identify the credential type.
5. `apiKeyManager` checks the key and builds an authenticated Authentication with `credentials = null` and server-determined authorities. Never use client-sent roles. Hard-coded string key comparisons are only for learning, not to be copied verbatim to production.
6. `NoOpServerSecurityContextRepository` keeps the API-key mechanism stateless: clients must supply the key on every request requiring authentication. The context still exists within the **current subscription** after success so controllers/authorization can read it.
7. The failure handler handles filter authentication errors and returns 401. `exceptionHandling.authenticationEntryPoint` handles requests to resources requiring authentication when no valid authentication exists, also returning 401.
8. `SecurityWebFiltersOrder.AUTHENTICATION` is the position for placing custom filters in the security chain. It guarantees authentication runs before authorization evaluates declared rules.
9. `/api/admin` requires `ROLE_ADMIN` because `hasRole("ADMIN")` applies the prefix by convention. The reader key only has `ROLE_READER`.
10. CSRF is not disabled: the example uses **HTTP GET only**. When implementing POST/PUT/DELETE, understand CSRF and credential sources before configuring a custom policy.

### 8.4. Endpoints to Observe Behavior

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    public record Identity(String name, List<String> authorities) {}

    @GetMapping("/public")
    Mono<String> rootPublic() {
        return Mono.just("root-public");
    }

    @GetMapping("/api/public")
    Mono<String> apiPublic() {
        return Mono.just("api-public");
    }

    @GetMapping("/api/me")
    Mono<Identity> me() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(this::toIdentity);
    }

    @GetMapping("/api/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin-area");
    }

    private Identity toIdentity(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList();
        return new Identity(auth.getName(), authorities);
    }
}
~~~

`ReactiveSecurityContextHolder` reads the verified authentication from the Reactor Context. The `/api/me` endpoint displays only the name and authorities; it never displays `getCredentials()` or the raw `X-API-Key`. If unauthenticated, the `authenticated()` rule blocks the request in the security chain before this handler returns content.

The project does not have controllers for other routes, yet `anyExchange().denyAll()` ensures the policy never implicitly allows unnamed URLs. A real application should explicitly configure health checks, static resources, or other required endpoints.

## 9. Request Outcomes: Matcher, Converter, Manager, and Rules

| HTTP request | `requiresAuthenticationMatcher` | Converter | Manager | Authorization | Expected |
| --- | --- | --- | --- | --- | --- |
| GET `/public`, no key | No match | Does not run | Does not run | `permitAll` | 200 |
| GET `/api/public`, no key | Matches | `Mono.empty()` | Does not run | `permitAll` | 200 |
| GET `/api/me`, no key | Matches | `Mono.empty()` | Does not run | `authenticated()` | 401 |
| GET `/api/me`, `reader-demo-key` | Matches | Creates unauthenticated token | Returns `ROLE_READER` | `authenticated()` | 200 |
| GET `/api/me`, wrong key | Matches | Creates unauthenticated token | `BadCredentialsException` | Never reaches handler | 401 |
| GET `/api/admin`, `reader-demo-key` | Matches | Creates unauthenticated token | Returns `ROLE_READER` | `hasRole("ADMIN")` denies | 403 |
| GET `/api/admin`, `admin-demo-key` | Matches | Creates unauthenticated token | Returns `ROLE_ADMIN` | `hasRole("ADMIN")` allows | 200 |
| GET `/api/public`, wrong key | Matches | Creates unauthenticated token | `BadCredentialsException` | Request failed before authorization | 401 |

The last row is critical: **`permitAll` does not mean "bypass AuthenticationWebFilter"**. Because the filter runs before authorization, an invalid credential that is present can still trigger the failure handler. If the product requirement is that all requests to `/api/public` skip the filter, you must **explicitly exclude that URL from `requiresAuthenticationMatcher`** rather than hoping the `permitAll` rule replaces the filter's match condition.

## 10. Running with curl

Start the server from the `reactive-auth-filter-demo` directory:

~~~bash
gradle bootRun
~~~

If Gradle Wrapper is present, use `./gradlew bootRun` on Unix/macOS or `gradlew.bat bootRun` on Windows. By default the application listens on `http://localhost:8080` unless the port is changed.

In bash/Git Bash:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
curl -s -H 'X-API-Key: reader-demo-key' http://localhost:8080/api/me
curl -s -H 'X-API-Key: wrong' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
curl -s -H 'X-API-Key: reader-demo-key' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -H 'X-API-Key: admin-demo-key' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -H 'X-API-Key: wrong' -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
~~~

The HTTP codes for commands 1, 2, 3, 5, 6, 7, and 8 in order:

~~~text
200
200
401
401
403
200
401
~~~

Command 4 returns JSON representing the verified identity, formatted like:

~~~json
{
  "name": "reader",
  "authorities": ["ROLE_READER"]
}
~~~

Whitespace/property order in JSON may differ, yet name and authority must match. No API key is echoed back in the body. In Windows PowerShell, use `curl.exe`; depending on your setup, `/dev/null` may need to be replaced with `NUL`. Sample API keys must never be used as real secrets or sent over plain HTTP outside local environments.

## 11. Practical Testing with `WebTestClient`

Create `src/test/java/demo/AuthenticationFilterTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationFilterTests {

    @Autowired
    WebTestClient client;

    @Test
    void outsideApiIsNotAnAuthenticationAttemptForCustomFilter() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("root-public");
    }

    @Test
    void anonymousPublicApiIsAllowedButProtectedApiIsNot() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api-public");

        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyProducesTrustedPrincipalInReactorContext() {
        client.get().uri("/api/me")
            .header("X-API-Key", "reader-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("reader")
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER");
    }

    @Test
    void incorrectKeyReturnsAuthenticationFailure() {
        client.get().uri("/api/me")
            .header("X-API-Key", "wrong")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authorizationHappensAfterSuccessfulAuthentication() {
        client.get().uri("/api/admin")
            .header("X-API-Key", "reader-demo-key")
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin")
            .header("X-API-Key", "admin-demo-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-area");
    }

    @Test
    void publicAuthorizationDoesNotIgnoreBadCredentials() {
        client.get().uri("/api/public")
            .header("X-API-Key", "wrong")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or use the wrapper if the project includes one. All six test methods should PASS to confirm the behavior of the sample configuration. Gradle exits with code 0 on success; exact log lines depend on the environment, so do not assert a fixed log string.

**Why is the final test important?** If a developer mistakes `permitAll` for skipping the filter, that test catches the bug. It is especially useful when adding public endpoints to an API that already has a custom authentication filter.

## 12. How Do You Skip Authentication on a Public Endpoint?

If the business requirement is that `/api/public` **never attempts API-key authentication**, even when a client accidentally sends a wrong key, you must replace the filter's matcher with a `ServerWebExchangeMatcher` matching only the paths that truly require authentication attempts.

Example selecting two groups of protected paths, shown as a replacement for the `/api/**` matcher in the full configuration:

~~~java
import org.springframework.security.web.server.util.matcher.OrServerWebExchangeMatcher;

// Only /api/me and /api/admin trigger the API key filter.
// Other endpoints, including /api/public, bypass this filter.
apiKeyFilter.setRequiresAuthenticationMatcher(
    new OrServerWebExchangeMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/me"),
        new PathPatternParserServerWebExchangeMatcher("/api/admin")
    )
);
~~~

This is an **illustrative edit, not standalone**: it belongs inside `SecurityConfig` in section 8 with the added import. In an API with many protected routes, listing every path can be hard to maintain. Choose a structure matching the product's model; if the filter must cover new endpoints, do not let forgetting to update the matcher leave an endpoint with authorization only and no authentication mechanism.

Do not try to fix it by putting `.pathMatchers("/api/public").permitAll()` and expecting the filter to skip it automatically: that remains an **authorization condition**, not a change to the filter's matcher.

## 13. Matchers by HTTP Method and Other Conditions

Not every endpoint needs the same mechanism. Some applications want to inspect credentials only for certain HTTP methods. `PathPatternParserServerWebExchangeMatcher` has an overload accepting both HTTP method and path. Illustrative example:

~~~java
new PathPatternParserServerWebExchangeMatcher(
    "/api/data/**",
    org.springframework.http.HttpMethod.POST
);
~~~

When using the overload, check the signature for your chosen Spring Security version; matcher APIs have overloads taking path/method that can differ across versions. With any method-specific rule, test GET, POST, PUT, DELETE, and OPTIONS to avoid accidentally leaving a sensitive method unauthenticated. Authorization must still be applied independently of filter scope.

Matchers can also be combined with `AndServerWebExchangeMatcher` / `OrServerWebExchangeMatcher` or a custom implementation. If an API lets a filter intercept requests based on a header, remember **headers can be controlled by the client**. Never treat "presence of an auth header" as the sole criterion deciding **whether a request must be protected**: a request lacking a header must still be blocked by authorization if the endpoint requires login.

**Technical note:** The snippet above expresses the intent of matching by HTTP method; before copying, check the `PathPatternParserServerWebExchangeMatcher` constructors in your exact version and verify compilation. If the API takes method first, use that signature; the learning goal is knowing to verify path + method for your version rather than guessing parameter order.

## 14. Common Misconceptions and Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing chain `securityMatcher` with filter `requiresAuthenticationMatcher` | Protection/login scope behaves unexpectedly | Distinguish chain selection from filters inside the chain |
| Thinking `permitAll` stops `AuthenticationWebFilter` from running | Sending a bad key to a public endpoint is still rejected | Design the matcher to exclude public routes if needed, and test separately |
| Converter returns `Mono.empty()` when key is present yet wrong | No clear authentication error; unpredictable outcomes | Return an unauthenticated token to the manager and emit `BadCredentialsException` |
| Converter creates `authenticated(...)` token itself | Bypasses credential verification, risks privilege escalation | Converter only creates unauthenticated tokens |
| Manager grants `ROLE_ADMIN` from client payload | Authorization vulnerability | Grant authorities only from verified sources |
| Calling `block()` to query database in manager | Blocks WebFlux event loop | Use reactive repository/client and compose with `flatMap` |
| Using Servlet `HttpSecurity`, `OncePerRequestFilter`, or `RequestMatcher` | Incompatible with WebFlux architecture | Use `ServerHttpSecurity`, `WebFilter`, and `ServerWebExchangeMatcher` |
| Calling `subscribe()` manually inside a filter | Request lifecycle/context and errors are no longer managed properly | Return `Mono<Void>` so the framework subscribes |
| Misunderstanding `NoOpServerSecurityContextRepository` | Thinking authentication is saved automatically for reuse | Send credentials per request or configure session persistence intentionally |
| Not configuring failure handler/entry point for an API | Unexpected 401/redirect/`WWW-Authenticate` behavior | Configure appropriate HTTP error handling and test |
| Placing filter at wrong `SecurityWebFiltersOrder` | Authorization may run before custom authentication | Choose `AUTHENTICATION` when it is an authentication step |
| Assuming default converter reads API keys | Default converter parses HTTP Basic | Set a dedicated `setServerAuthenticationConverter` |
| Testing only the valid-key case | Misses anonymous, bad key, public route, missing role | Use a request matrix and WebTestClient |
| Logging raw headers or tokens | Secret leakage | Log only error codes/trace IDs and sanitized info |
| Using hard-coded string keys as a production mechanism | Hard to rotate secrets, risk of source exposure | Vault/secret manager, TLS, hashing, rotation, revocation, rate limiting |

### 14.1. "Absent Credentials" vs "Invalid Credentials"

A common scenario on a public API: when the client omits `X-API-Key`, the converter returns empty and `permitAll` lets the request succeed. When the client sends `wrong`, the converter emits a token, the manager emits an error, and the failure handler returns 401. This is **not** a contradiction: a route not requiring an identity can still reject a request that **actively tries to authenticate with bad credentials**.

For protected APIs, both "missing header" and "wrong header" can surface as 401 via two different paths. Adding sanitized traces/metrics helps distinguish them:
- missing credentials: authorization/entry point;
- wrong credentials: authentication failure handler.
Never put key values into logs or metric labels.

### 14.2. HTTP 401, 403, and Technical Errors

- `401 Unauthorized`: no valid authentication or authentication failed under the current mechanism; returned by the entry point/failure handler.
- `403 Forbidden`: valid authentication yet insufficient permissions, or another security filter such as CSRF rejected the request.
- `5xx` may reflect system failures; never convert key-store timeouts into `Mono.empty()` or successful logins.

Exact responses depend on error-handling configuration, filter order, content negotiation, and reverse proxies. API tests should verify safe statuses and bodies according to your application contract.

### 14.3. What About JWT, HTTP Basic, and Form Login?

Spring Security offers supported DSLs:
- `http.httpBasic(...)`: filters requests carrying HTTP Basic and uses the appropriate authentication mechanism.
- `http.formLogin(...)`: handles form-based login requests.
- `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`: Resource Server mechanism verifying Bearer JWTs with built-in components.

Prefer built-in mechanisms when the problem fits standard protocols. A custom `AuthenticationWebFilter` fits custom credential formats better, in which case you must explicitly define matcher, converter, manager, success/failure handlers, and SecurityContext policy. Do not write your own JWT parser or signature verification.

## 15. Step-by-Step Diagnosis When Authentication Does Not Run

If a request carries `X-API-Key` yet the controller still sees anonymous or 401, check in order:

1. **Is the app running Spring WebFlux?** Check dependencies to avoid accidentally pulling in Servlet MVC.
2. **Which chain was selected?** With multiple `SecurityWebFilterChain`s, check `securityMatcher` and `@Order`.
3. **Was the filter added to the selected chain?** Check `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`.
4. **Did the filter's matcher match?** Inspect path, method, trailing slash, context path, and reverse proxy.
5. **Did the converter see the header?** Verify header name, HTTP case-insensitivity, and whether proxies forward the header. Never log the secret value.
6. **Did the converter return `Mono.empty()`?** If empty, the manager receives no token to process.
7. **What did the manager return?** Verified authentication, `AuthenticationException`, or an empty publisher because it was unsupported?
8. **After success, does authorization accept the authorities?** `hasRole("ADMIN")` typically requires `ROLE_ADMIN`.
9. **Do the failure handler and entry point return the expected status codes?** Test 401 and 403 separately.
10. **Is the SecurityContext in the same Reactor pipeline?** Do not detach the request with `subscribe()` or use Servlet ThreadLocal in WebFlux.

For debugging, you can enable appropriate Spring Security log levels in development while always redacting raw credentials, Authorization headers, and cookies. For deeper observability, add instrumentation for **match decisions and outcome categories** without collecting secrets.

## 16. Practice Exercises

**Exercise 1.** With the configuration in section 8, does GET `/api/public` without `X-API-Key` call the manager?  
**Answer:** No. The matcher matches, yet the converter returns `Mono.empty()`; `permitAll` authorization lets the request through.

**Exercise 2.** If `X-API-Key: wrong` is sent to `/api/public`, what happens?  
**Answer:** The converter creates an unauthenticated authentication, the manager emits `BadCredentialsException`, and the failure handler returns 401 even though the URL is `permitAll`.

**Exercise 3.** If the reader key is sent to `/api/admin`, does the filter succeed or fail?  
**Answer:** **Authentication succeeds** (the reader identity is established), yet **authorization fails** due to missing `ROLE_ADMIN`; expected 403.

**Exercise 4.** When using a catch-all chain and filter matcher `/api/**`, is `/public` still protected by the security chain?  
**Answer:** Yes, because the chain matches all requests; only the custom API-key filter skips attempting authentication on that URL. The `permitAll` rule marks it public.

**Exercise 5.** When the client omits the key on `/api/me`, should the converter create a default `ROLE_READER`?  
**Answer:** No. The converter returns empty; the `authenticated()` rule must reject unauthenticated requests.

**Exercise 6.** Why not use `Mono.empty()` for an invalid key?  
**Answer:** Because it is an authentication attempt with invalid credentials; it must be represented as an authentication error. Returning empty can mislead downstream logic into treating it as no attempt at all.

**Exercise 7.** To bypass the custom filter for `/api/public`, should you edit `authorizeExchange` or `setRequiresAuthenticationMatcher`?  
**Answer:** Edit **the filter's** matcher; `authorizeExchange` only decides permissions and does not disable an authentication filter.

**Exercise 8.** In a standard JWT app, should you build a custom `AuthenticationWebFilter` to parse tokens?  
**Answer:** Usually no. Use Spring Security's OAuth2 Resource Server for Bearer JWTs, configuring standard decoders and validators.

**Exercise 9.** The repository returns `Mono<Authentication>` inside the manager, yet you call `.block()` in the manager to fetch the user; is that appropriate in WebFlux?  
**Answer:** No. Keep the reactive publisher and use `flatMap`/`map` to decide authentication.

**Exercise 10.** When would a filter not be invoked even though its own matcher is "match all"?  
**Answer:** When the request is routed to a **different** `SecurityWebFilterChain` that does not include that filter, or no chain matches; a filter's condition only matters inside the active chain.

## 17. Official Documentation

- Spring Security API `AuthenticationWebFilter` (algorithm, matcher, converter, success/failure): https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security WebFlux configuration (multiple chains, matchers, `ServerHttpSecurity`): https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security reactive authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security reactive HTTP authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security API `ReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security API `ServerAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html

**Takeaway:** `AuthenticationWebFilter` decides **whether to attempt authenticating a request** via its matcher and converter; the manager verifies credentials; success/failure handlers decide the next branch; `authorizeExchange` decides **whether a request with that identity is permitted to access the resource**. Keeping the boundaries among these four responsibilities clear is the key to building secure reactive authentication.
