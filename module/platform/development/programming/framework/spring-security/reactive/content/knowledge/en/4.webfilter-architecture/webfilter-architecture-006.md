# AuthenticationWebFilter: Converting Input Credentials and Invoking the Authenticator in Spring Security Reactive

## 1. Purpose and Position in the WebFilter Architecture

**AuthenticationWebFilter** is the WebFilter responsible for performing an **authentication** attempt on selected requests in Spring Security WebFlux. Its core responsibilities are:

1. Determine whether the request falls within the scope where authentication should be attempted.
2. Read authentication data from **ServerWebExchange** via **ServerAuthenticationConverter**.
3. Convert the input data into an **unauthenticated Authentication**, then pass it to **ReactiveAuthenticationManager**.
4. If authentication succeeds, place the resulting Authentication into **Reactive SecurityContext** and run the success handler; if authentication fails, run the failure handler.
5. Let downstream WebFilters, especially the authorization checker, use the authenticated identity.

This lesson focuses on the flow **convert input → invoke authenticator → handle result**. AuthenticationWebFilter does not itself know whether a password is correct, whether a token is valid, which orders a user may view, or whether a request exceeds rate limits: those decisions belong to the manager, token processors, authorization layer, and other protective mechanisms.

| Component | Responsibility | Must NOT Do |
| --- | --- | --- |
| **SecurityWebFilterChain** | Groups security WebFilters under a request matching rule | Mix Servlet `HttpSecurity` configuration with WebFlux `ServerHttpSecurity` |
| **ServerWebExchangeMatcher** | Selects requests that enter the authentication-attempt branch | Treat "not matched" as access granted |
| **ServerAuthenticationConverter** | Extracts credentials from the request and builds an input Authentication | Self-assign `ROLE_ADMIN` or self-mark as authenticated |
| **ReactiveAuthenticationManager** | Verifies credentials and builds a trusted Authentication | Trust client-asserted principals/authorities |
| **ReactiveAuthenticationManagerResolver** | Selects a manager per exchange in multi-source setups | Trust issuer/tenant from unverified input without validation |
| **ServerAuthenticationSuccessHandler** | Handles post-success flow after manager authentication | Release secret data before passing authorization |
| **ServerAuthenticationFailureHandler** | Returns response / handles authentication failure | Leak passwords, API keys, or bearer tokens |
| **ServerSecurityContextRepository** | Defines how SecurityContext is saved/restored across requests | Use sessions by default for stateless APIs unintentionally |
| **AuthorizationWebFilter / method security** | Checks the principal's permissions against resources | Assume "authenticated" means "sufficiently authorized" |

A mnemonic: **the converter understands the input protocol**, **the manager proves identity**, and **authorization decides what may be done**.

## 2. Request Processing Flow Diagram

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- matcher does NOT match ------------> chain.filter(exchange)
    |
    +-- matcher matches
             |
             v
    ServerAuthenticationConverter.convert(exchange)
             |
             +-- Mono.empty() -------------> chain.filter(exchange)
             |
             +-- Mono.error(...) ----------> handle authentication error if it is
             |                                AuthenticationException
             |
             +-- Mono<unauthenticated Authentication>
                          |
                          v
                  ReactiveAuthenticationManager.authenticate(...)
                          |
                          +-- success -> authenticated Authentication
                          |                   |
                          |                   v
                          |           SecurityContext / success handler
                          |                   |
                          |                   v
                          |               chain continues
                          |
                          +-- AuthenticationException -> failure handler
                          |
                          +-- system error -> handle error appropriately,
                                             do not grant access by default
~~~

This is a conceptual diagram for a properly configured filter, not a guarantee that exceptions of every class turn into 401. In Spring Security, the exception type, WebFilter position, and configured handlers determine the actual HTTP response.

**Important distinction:** a request that fails to produce an Authentication in the converter will **not attempt authentication at this filter**. The request still proceeds to downstream layers. If the endpoint requires login, the authorization step will deny the anonymous caller per configuration. **Skipping an authentication attempt does not mean access is granted.**

### 2.1. What Is ServerWebExchange?

ServerWebExchange represents an HTTP exchange in WebFlux, containing the request, response, and related attributes. Converters typically inspect:

- Request headers: Authorization, X-API-Key, certificate details from a trusted proxy, etc.
- Cookies/sessions if the authentication mechanism actually uses them.
- Path, method, and information needed to choose an authentication mechanism.

Do not arbitrarily read the body inside a converter: WebFlux's body is a single-consumption stream, incurs memory cost, and affects downstream body reading. If authentication is based on JSON/form login, use framework-aligned body reading/caching mechanisms with size limits.

### 2.2. Processing Order Inside SecurityWebFilterChain

Spring Security Reactive uses positions in **SecurityWebFiltersOrder**, where **AUTHENTICATION** is designated for authentication filters, and authorization is handled at a later stage. When adding a custom filter, insert it via **ServerHttpSecurity.addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)** inside the proper SecurityWebFilterChain.

Distinguish:

- **WebFilter** and **ServerHttpSecurity** belong to WebFlux/reactive.
- **jakarta.servlet.Filter**, **OncePerRequestFilter**, and **HttpSecurity** belong to the servlet stack; they do not directly replace AuthenticationWebFilter.
- Do not declare a Spring WebFilter bean and simultaneously pass the same instance to `addFilterAt` without control, as this can cause unintended filter registration/execution. In the demo, the filter is instantiated locally inside `@Bean SecurityWebFilterChain`.

## 3. Step 1 — Selecting Requests with ServerWebExchangeMatcher

AuthenticationWebFilter has **setRequiresAuthenticationMatcher(ServerWebExchangeMatcher)**. If the matcher returns a non-match, the filter forwards the request and **does not invoke the converter or manager**.

Example:

~~~java
filter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"));
~~~

Only requests whose path matches `/api/**` enter this filter's converter. Matchers can combine HTTP method/path conditions when the application requires it; avoid overly broad matchers that cause one mechanism to try processing login callbacks, CORS preflights, or endpoints belonging to another scheme.

**Default per Javadoc:** `requiresAuthenticationMatcher` matches every request. When building a custom filter, explicitly define its scope to avoid colliding with other authentication methods.

A matcher **does not** make the final allow/deny decision. An unmatched request can still be denied by a subsequent matcher or authorization rule.

## 4. Step 2 — ServerAuthenticationConverter Turns the Request into an Authentication

**ServerAuthenticationConverter** is a reactive contract:

~~~java
Mono<Authentication> convert(ServerWebExchange exchange);
~~~

The converter's job is to recognize credentials in the request and construct an **authentication attempt**; it does not itself trust that those credentials are valid.

Minimal example for the `X-API-Key` header:

~~~java
ServerAuthenticationConverter converter = exchange -> {
    String rawKey = exchange.getRequest()
            .getHeaders()
            .getFirst("X-API-Key");

    if (rawKey == null) {
        return Mono.empty();
    }

    Authentication attempt =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "api-client", rawKey);

    return Mono.just(attempt);
};

filter.setServerAuthenticationConverter(converter);
~~~

Required imports for this illustrative snippet: **ServerAuthenticationConverter**, **Authentication**, **UsernamePasswordAuthenticationToken**, and **Mono**. This code belongs inside a filter configuration method, not as a standalone runnable Java class.

Meaning:

- Missing header → **Mono.empty()** → filter does not attempt authentication.
- Header present → **Mono<Authentication>** holding the raw credential, but the token is in the **unauthenticated** state.
- Only the manager may verify the value and return an authenticated token with authorities determined by a trusted system.

Converter signal table:

| Converter Result | Filter Interpretation | Impact on Request |
| --- | --- | --- |
| **Mono.empty()** | No matching credential found / no authentication attempt | Forwards request; remaining policies decide afterward |
| **Mono.just(unauthenticated)** | An authentication attempt exists | Invokes ReactiveAuthenticationManager |
| **Mono.error(BadCredentialsException)** | Credential recognized but malformed/unusable | Follows authentication failure handling |
| **Mono.error(non-AuthenticationException error)** | Unexpected technical failure | Must be handled by the proper error pipeline; never assume it is always 401 |

If the header is present but blank or malformed, it should generally be treated as an **invalid authentication attempt** emitting an AuthenticationException; do not always return `Mono.empty()`, because that conflates "no credential supplied" with "invalid credential supplied". For bearer tokens, validate the `Bearer` scheme properly, reject ambiguous headers or multiple credentials violating policy, and enforce size limits.

**Preferred API:** `setServerAuthenticationConverter(...)`. The older method **setAuthenticationConverter(Function<ServerWebExchange, Mono<Authentication>>)** has been deprecated since Spring Security 5.1. AuthenticationWebFilter's default converter is **ServerHttpBasicAuthenticationConverter**; therefore, if you want a custom header, you must set a new converter rather than expecting the filter to understand `X-API-Key` automatically.

## 5. Step 3 — ReactiveAuthenticationManager Verifies Credentials

Primary contract:

~~~java
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

A manager can:

1. Check the Authentication type it supports.
2. Extract the credential from the unauthenticated token.
3. Perform trusted verification: password hash, API key in a secret store, JWT signature/claims verification, introspection, etc., depending on the mechanism.
4. When valid, return an **authenticated Authentication** containing the principal and GrantedAuthority decided by the system.
5. When credentials are wrong, return **Mono.error(AuthenticationException)** (e.g., BadCredentialsException).
6. When the token type is unsupported, depending on the contract it may return **Mono.empty()** so a manager dispatcher can try another manager. In a dedicated manager, explicitly design which token types are supported and how unsupported ones are handled; never treat empty as approval.

**Never** accept a role list, user ID, or `authenticated` boolean taken verbatim by a converter from client headers/bodies and pass it straight into a success token. Clients can forge those fields. Authorities must originate from trusted policies/identity stores or verified tokens.

### 5.1. Mono Is an Asynchronous Processing Promise

The manager returns **Mono<Authentication>**, allowing WebFlux to compose I/O and processing with Reactor. Never call `block()` inside `authenticate` or a converter, as the event loop can stall. For unavoidable blocking I/O clients, isolate the work on an appropriate scheduler or better yet use reactive drivers/clients; still enforce timeouts and concurrency limits.

Never call `subscribe()` manually inside a converter or manager: return the Publisher so the framework owns its lifecycle, propagates context, and receives errors. Never write credentials into debug logs, exception messages, or unnecessary Reactor Context entries.

### 5.2. Why Unauthenticated and Authenticated Must Differ

A **UsernamePasswordAuthenticationToken.unauthenticated(principal, credentials)** carries data awaiting verification. Only after successful verification in the manager should it return:

~~~java
Authentication success =
        UsernamePasswordAuthenticationToken.authenticated(
                "api-client",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_READER")));
~~~

The credential in the result can be `null` to limit its lifetime in memory. `ROLE_READER` is assigned by the server; it is not taken from the request. **isAuthenticated()** represents the Authentication's state; in Spring Security it must be paired with proper token creation/verification mechanisms, never client-asserted state.

## 6. Step 4 — Success, Failure, and SecurityContext

### 6.1. Authentication Success

After the manager emits a successful Authentication, AuthenticationWebFilter:

- Creates/sets SecurityContext information and establishes the reactive context for downstream processing.
- Invokes **ServerAuthenticationSuccessHandler**.
- May save the SecurityContext through **ServerSecurityContextRepository** if a stateful repository is configured.

**Default per Javadoc:** the success handler is **WebFilterChainServerAuthenticationSuccessHandler** — continuing the pipeline. The default SecurityContextRepository on AuthenticationWebFilter itself is **NoOpServerSecurityContextRepository**, meaning no state is persisted across requests. This is the filter class's own default; SecurityWebFilterChain configurations, form/session login, or other mechanisms may choose a different repository.

After success, Authentication can be read with **ReactiveSecurityContextHolder.getContext()** in the reactive pipeline. Do not rely on Servlet's ThreadLocal **SecurityContextHolder** when accessing it in WebFlux handlers.

**Success does not automatically mean permission to view data:** the `authorizeExchange` stage or method security checks `hasRole`/`hasAuthority`/ownership.

### 6.2. Authentication Failure

A **BadCredentialsException** from the manager indicates rejected credentials. AuthenticationWebFilter calls the configured **ServerAuthenticationFailureHandler**; it can return HTTP 401, redirect to login, or respond otherwise according to configuration.

The filter class's default failure handler uses an HTTP Basic challenge; when implementing an `X-API-Key` scheme, you typically need to configure a failure handler returning 401 **without misleading the client into sending Basic auth**.

Example:

~~~java
filter.setAuthenticationFailureHandler((filterExchange, exception) -> {
    var response = filterExchange.getExchange().getResponse();
    response.setStatusCode(HttpStatus.UNAUTHORIZED);
    return response.setComplete();
});
~~~

**Distinguish:** 

- **401 Unauthorized**: no valid authentication proof yet or authentication attempt failed (depending on entry point).
- **403 Forbidden**: trusted identity exists, but denied by authorization.
- **500/503**: technical failures in the identity store or auth service may need mapping to system errors, never granting access and never exposing secrets.

Response codes depend on configuration and response commit timing; do not claim every AuthenticationException or internal error automatically turns into one exact HTTP status code.

### 6.3. SecurityContext Is Subscription-Scoped Context

In Reactor, request execution can switch threads and traverse asynchronous operators. Spring Security Reactive uses **Reactor Context** to propagate SecurityContext. **ReactiveSecurityContextHolder** is the proper API; creating detached subscriptions, calling `block()`, using ThreadLocal carelessly, or splitting off a fire-and-forget pipeline all risk losing context or obscuring errors.

**NoOpServerSecurityContextRepository** keeps the filter from maintaining login via sessions. Being stateless does not exempt an API from security concerns: TLS protection, secret protection, CORS/CSRF configuration if browsers automatically send credentials, and rate limiting remain separate responsibilities.

## 7. Java 17+ Demo: Creating an AuthenticationWebFilter for X-API-Key

This demo uses **Spring Boot 3.3.5**, **Java 17+**, WebFlux, and Spring Security. We configure an AuthenticationWebFilter manually to illustrate three steps: reading `X-API-Key`, verifying via the manager, and placing the identity into Reactor Context. Only GET endpoints are included; the hardcoded **demo-only-key** is test data, not a production secret-storage method.

Structure:

~~~text
auth-webfilter-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/security/ApiKeyDemoApplication.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'auth-webfilter-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}
~~~

**src/main/java/example/security/ApiKeyDemoApplication.java**

~~~java
package example.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
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
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ApiKeyDemoApplication {

    private static final byte[] EXPECTED_KEY =
            "demo-only-key".getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/api/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }

    @Bean
    ReactiveAuthenticationManager apiKeyManager() {
        return candidate -> Mono.defer(() -> {
            Object credential = candidate.getCredentials();

            if (!(credential instanceof String submittedKey)) {
                return Mono.error(
                        new BadCredentialsException("Unsupported credential"));
            }

            byte[] actual = submittedKey.getBytes(StandardCharsets.UTF_8);

            if (!MessageDigest.isEqual(EXPECTED_KEY, actual)) {
                return Mono.error(
                        new BadCredentialsException("Invalid API key"));
            }

            Authentication verified =
                    UsernamePasswordAuthenticationToken.authenticated(
                            "demo-client",
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_READER")));

            return Mono.just(verified);
        });
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager apiKeyManager) {

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(apiKeyManager);

        // Filter only attempts authentication on /api/** requests.
        apiKeyFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        // Convert header into an UNAUTHENTICATED Authentication.
        ServerAuthenticationConverter converter = exchange -> {
            String rawKey = exchange.getRequest()
                    .getHeaders()
                    .getFirst("X-API-Key");

            if (rawKey == null) {
                return Mono.empty();
            }

            Authentication attempt =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "api-client", rawKey);
            return Mono.just(attempt);
        };
        apiKeyFilter.setServerAuthenticationConverter(converter);

        // Each request carries its own credential; filter does not save a session.
        apiKeyFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());

        // Do not advertise an HTTP Basic challenge for the API key scheme.
        apiKeyFilter.setAuthenticationFailureHandler((filterExchange, ex) -> {
            var response = filterExchange.getExchange().getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        });

        return http
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((exchange, ex) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.UNAUTHORIZED);
                            return exchange.getResponse().setComplete();
                        })
                        .accessDeniedHandler((exchange, ex) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.FORBIDDEN);
                            return exchange.getResponse().setComplete();
                        }))
                .addFilterAt(
                        apiKeyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

**Part-by-part explanation:**

1. **setRequiresAuthenticationMatcher** only attempts this mechanism on `/api/**`.
2. **converter**: no `X-API-Key` → `Mono.empty`; header present → unauthenticated `Authentication`.
3. **apiKeyManager**: compares the test value; mismatch → `BadCredentialsException`; match → new `Authentication` with principal `demo-client` and `ROLE_READER`.
4. **success**: default handler lets the request proceed; identity is placed in Reactor Context, usable in `/api/me`.
5. **failure**: custom failure handler sets 401 for an invalid key. When no key is sent, `/api/**`'s authorization requires `authenticated` and the entry point returns 401.
6. **authorization**: `/api/admin/**` requires `ROLE_ADMIN`, whereas the demo token only has `ROLE_READER`; thus even after successful authentication it receives 403.
7. **NoOpServerSecurityContextRepository**: does not persist identity to subsequent requests. Reusing a valid key on the next request must authenticate again.
8. The configuration does not alter default CSRF; the demo only uses GET. If adding write methods or browser clients, design CSRF/CORS properly according to cookie, token, and origin usage.

**Run the demo:** install JDK 17+ and a compatible Gradle 8.x. Inside the `auth-webfilter-demo` directory:

~~~bash
gradle bootRun
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-API-Key: wrong-key' http://localhost:8080/api/me
# 401

curl -s -H 'X-API-Key: demo-only-key' \
  http://localhost:8080/api/me
# hello demo-client

curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-API-Key: demo-only-key' \
  http://localhost:8080/api/admin/report
# 403
~~~

**Command note:** multi-line commands use backslashes for Bash/macOS/Linux-style shells. On Windows PowerShell, run each command on a single line with **curl.exe**, because the `curl` alias may point to `Invoke-WebRequest` and line-continuation rules differ from Bash.

### 7.1. Expected Results Table

| Request | Converter | Manager | Authorization | Result |
| --- | --- | --- | --- | --- |
| GET /public/ping without key | Filter does not match | Not called | permitAll | **200**, pong |
| GET /api/me without key | Mono.empty | Not called | authenticated requires identity | **401** |
| GET /api/me wrong key | Builds unauthenticated token | BadCredentialsException | Does not reach allow step | **401** |
| GET /api/me valid key | Builds unauthenticated token | Returns ROLE_READER | authenticated | **200**, hello demo-client |
| GET /api/admin/report valid key | Builds unauthenticated token | Returns ROLE_READER | Lacks ROLE_ADMIN | **403** |

Thus you observe the difference between **no authentication attempt**, **failed authentication**, and **successful authentication with insufficient permissions**. The code uses an in-memory key to learn the API; in production, move secrets to a secure configuration store, support key rotation/revocation, manage scopes, and monitor usage.

## 8. When to Use AuthenticationWebFilter Directly?

Most applications should use the built-in configurations:

- **http.httpBasic(...)** for HTTP Basic when appropriate.
- **http.formLogin(...)** when actually using form/session login.
- **http.oauth2ResourceServer(...)** for bearer token/JWT/opaque token APIs, with issuer, audience, signature, expiry, and authority mapping validation.
- **http.oauth2Login(...)** for OAuth2/OIDC login flows in web applications.

A custom AuthenticationWebFilter is useful when you need a custom authentication protocol or integration with a specialized identity system. Do not write your own JWT/token verifier just to replace a few configuration lines: standard mechanisms already handle signature rules, key rotation, clock skew, and exception handling.

When an application has multiple mechanisms:

- Use **matchers** for the proper APIs/paths instead of letting filters compete over the same credential.
- You can use **ReactiveAuthenticationManagerResolver<ServerWebExchange>** to choose a manager per request; however, data from the request used to pick a manager is **untrusted** until verified. With multiple issuers/tenants, verify the issuer and keys against a trusted source; never use an arbitrary issuer string to grant access.
- If using multiple **SecurityWebFilterChain** beans, verify chain selection policies and ordering. A request is typically protected by the first matching chain, so do not assume all chains accumulate.
- Test missing/malformed/invalid credential errors separately, especially alongside CORS preflight and anonymous mechanisms.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Converter returns a token with **authenticated=true** | Bypasses/spoofs identity verification | Return an unauthenticated token; let the manager issue the trusted token |
| Taking roles from the **X-Role: ADMIN** header | Client self-escalates privileges | Authorities must be issued by a trusted verification source |
| Treating **Mono.empty()** from converter as "valid password" | Confuses skipping auth with succeeding | Endpoints must have appropriate `authenticated`/role policies |
| Converter returns empty for malformed credentials | Hard to distinguish missing key from invalid key | Emit `AuthenticationException` for recognized yet invalid credentials |
| Manager uses **onErrorReturn(authenticatedToken)** | Identity service outage still logs users in | Fail closed; let errors flow through proper handling and monitoring |
| Calling **block()** to query the user | Stalls event loop and degrades throughput | Use reactive APIs, timeouts, and resource limits |
| Calling **subscribe()** manually inside a filter | Loses lifecycle, context, and makes error handling hard | Return `Mono`/`Flux` so the framework subscribes |
| Logging API keys/tokens | Exposes secrets in centralized logs | Mask/omit credentials and protect logs |
| Confusing 401 and 403 | Clients and incident responders misdiagnose state | Clearly define failure handler, entry point, and access denied handler |
| Using only **authenticated()** for all resources | User A reads User B's data | Enforce role/authority and owner/tenant checks |
| Using the default HTTP Basic failure handler for another scheme | Client misinterprets `WWW-Authenticate` or login method | Configure an appropriate failure handler |
| Registering the same custom WebFilter multiple times | Duplicate authentication or unpredictable behavior | Register strictly in the intended chain |

A common scenario: a developer writes a converter like this:

~~~java
// Insecure: client self-asserts ADMIN privileges.
Authentication spoofed =
        UsernamePasswordAuthenticationToken.authenticated(
                requestUser, null,
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
return Mono.just(spoofed);
~~~

This is not true "input conversion"; it **grants privileges** before identity verification. A converter should only return an unauthenticated value, and the manager should verify and create a trusted identity.

## 10. How to Test AuthenticationWebFilter

Test at both **unit** and **integration** levels along proper API boundaries.

**Unit tests for the converter:**

1. Missing header → `Mono.empty`.
2. Well-formed header → unauthenticated `Authentication`, credentials extracted accurately, no self-asserted authorities.
3. Empty, oversized, multi-valued, or wrong-scheme header → outcome matches an explicit contract (typically `AuthenticationException`).
4. Does not consume the request body unintentionally.

**Unit tests for the manager:**

1. Valid credential → authenticated `Authentication`, server-determined principal and authorities.
2. Wrong credential → `AuthenticationException`; no success result emitted.
3. Credential/policy store unavailable → no fallback granting access.
4. Does not log keys, passwords, or tokens; does not retain raw credentials in the result unnecessarily.
5. Identity-source query is reactive, with timeouts and load bounds.

**Integration tests with WebTestClient:**

- Missing key: requests to login-required APIs return 401; public endpoints still work.
- Wrong key: failure handler emits 401.
- Valid key: `/api/me` sees the right `Authentication` in Reactor Context.
- Valid key lacking `ROLE_ADMIN`: `/api/admin/report` emits 403.
- Unauthorized for a specific record: service/data layer blocks even when authentication succeeds.
- Concurrent requests using different credentials do not bleed `SecurityContext` across each other.
- If sessions/CORS/multiple chains exist, test independently to catch another filter consuming credentials or preflights being blocked.

With **StepVerifier**, verify that the converter/manager emits a value, empty, or error. With **WebTestClient**, verify the full behavior of `SecurityWebFilterChain`. Separating these makes it easy to pinpoint whether a bug is in credential parsing, credential verification, or permission evaluation.

## 11. Real-World Scenario: Bearer-Token API

Suppose a request arrives:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

In an OAuth2 Resource Server configuration, an appropriate converter recognizes the bearer credential; the manager/token authenticator validates signature or introspection and trust conditions; SecurityContext receives the identity; authorization checks scope/role and then ownership of order 42.

**Do not assume a decodable token is valid.** Only after verifying the signature and application-specific conditions for issuer, audience, `exp`, `nbf`, and scope should you trust the principal/authorities. Likewise, do not assume an order-reading scope permits viewing all orders: owner/tenant checks are still required in the business layer.

For standard bearer tokens, configure the official Resource Server; building a demo-style custom AuthenticationWebFilter is just for understanding the architecture mechanics.

## 12. Self-Check Questions

1. How does AuthenticationWebFilter use a matcher and a converter for two distinct tasks?
2. The converter returns `Mono.empty` when `X-API-Key` is absent. Why does `/api/me` still return 401?
3. Why does the converter create `UsernamePasswordAuthenticationToken` in the unauthenticated state?
4. After the manager returns an authenticated `Authentication`, what are the roles of the success handler and `ReactiveSecurityContextHolder`?
5. Why do a wrong API key and being logged in without `ROLE_ADMIN` produce two different failure types?
6. Why should you never take `ROLE_ADMIN` directly from a client-sent `X-Role` header?
7. What are AuthenticationWebFilter's defaults for converter, matcher, success handler, and context repository?
8. When should you use OAuth2 Resource Server instead of a custom filter?
9. When multiple authentication mechanisms coexist, how do matchers and `SecurityWebFilterChain` prevent confusion?
10. Why do `block()` / manual `subscribe()` in reactive authentication complicate Context and error handling?

**Suggested answers:** (1) the matcher selects requests, while the converter extracts credentials and creates an attempt; (2) skipping auth does not grant access, so authorization blocks anonymous requests; (3) avoids self-accepting unverified credentials; (4) continues the flow per handler and carries identity via Reactor Context; (5) 401 indicates missing/invalid proof, while 403 indicates insufficient permissions; (6) clients can tamper with headers; (7) Basic converter, any-request matcher, chain-continuing success handler, NoOp repository; (8) when handling standard bearer/JWT/opaque tokens; (9) selects the right chain/filter and credentials, avoiding duplicate/misrouted handling; (10) causes blocking, detaches subscriptions, and loses context.

## 13. Reference Documentation

- Spring Security Javadoc — AuthenticationWebFilter: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — OAuth2 Resource Server Reactive JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html

**Conclusion:** AuthenticationWebFilter bridges the **HTTP request** to a **trusted Authentication** in WebFlux. Know the exact difference between **matcher non-match**, **converter returning empty**, **manager returning authenticated**, and **manager signaling AuthenticationException**. Only the manager verifies credentials; success places the result into the reactive context; authorization proceeds to check permissions. Keeping these steps cleanly separated yields correct, secure, and testable filters.