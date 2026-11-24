# Never Leak Passwords, Tokens, Stack Traces, or Account Details in Error Responses

## 1. Context and Goals

In a **Spring Security reactive / Spring WebFlux** application, errors are not only about returning HTTP `401`, `403`, or `500`. Every response also has a **body, headers, message, status code, response timing, and related metadata**. If responses are constructed carelessly, the application may accidentally disclose:

- User-submitted **passwords** or password hashes stored in `UserDetails`.
- **Access tokens, refresh tokens, JWTs, API keys, session IDs**, `Authorization` or `Cookie` values.
- **Stack traces**, Java class names, packages, file paths, SQL queries, server addresses, configuration details, and infrastructure errors.
- **Account details**: whether a username/email exists, whether an account is locked, disabled, or expired, which roles it holds, last login time, or MFA mechanism type.
- Information inferred from differing **statuses, body lengths, redirects, response headers, or processing times**.

A seemingly "user-helpful" response such as `User alice@example.test exists but password is incorrect` helps attackers enumerate accounts. A 500 response containing `IllegalStateException: JWT secret=...` can turn an application bug into a credential-leak incident.

Lesson goals:

1. Design a **safe error response contract** for 401, 403, 400/404, and 500 without losing essential HTTP semantics.
2. Understand the exact boundary between **authentication failure**, **authorization denied**, and **application exception** in the reactive chain.
3. Configure WebFlux `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` to return JSON without exception messages.
4. Distinguish `@RestControllerAdvice` and `ErrorWebExceptionHandler`; know why a single handler does not cover all errors.
5. Configure Spring Boot `server.error.*` properties to disable internal error details.
6. Write a **Java 17+, Spring Boot 3.3.5, WebFlux** demo with sample users and standardized 401/403/500 responses.
7. Test wrong usernames, wrong passwords, disabled accounts, and errors with **fake canaries** to verify zero leakage.
8. Keep enough information for operations **in controlled log channels**, while preventing logs/traces themselves from becoming storage for passwords or tokens.

This lesson focuses on **error responses** in Spring Security reactive; it does not build a full user management system, OAuth2 setup, or production monitoring stack. All secrets in examples are **fake localhost values**, not real credentials.

## 2. Principle: Client Responses and Diagnostics Are Two Separate Channels

The contract should return to the client just enough information to take the next step, without returning internal data meant only for debugging.

Example response for an unauthenticated user:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store
WWW-Authenticate: Basic realm="api"

{"code":"AUTHENTICATION_FAILED","message":"Authentication failed"}
```

For an authenticated user lacking permissions:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
```

For an unexpected server error:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store

{"code":"INTERNAL_ERROR","message":"An unexpected error occurred"}
```

The responses above are **application schema examples**, not strings mandated by Spring Security for every API. A product may use `ProblemDetail` / `application/problem+json` (RFC 9457), yet must still use **curated codes/messages** rather than copying raw exception details or credentials into `detail`/`instance`.

### What Must Never Be Returned

```json
{
  "username": "alice@example.test",
  "password": "FAKE_PASSWORD_CANARY",
  "accessToken": "FAKE_TOKEN_CANARY",
  "status": "LOCKED",
  "roles": ["ROLE_ADMIN"],
  "exception": "org.example.security.TokenValidationException",
  "message": "Account alice@example.test is locked",
  "stackTrace": "at org.example...:123",
  "database": "postgres://internal-host/..."
}
```

This is an **anti-pattern containing fake illustrative data**. Also prevent responses from leaking by putting these values into `error`, `details`, `debugInfo`, `causes`, `validationErrors`, or HTTP response headers.

### Distinguishing Proper HTTP Statuses

| Status | Typical meaning | Info client should receive | Should NOT leak |
| --- | --- | --- | --- |
| `400 Bad Request` | Invalid syntax/input | Input error code + generic guidance or **allowlisted** fields | Submitted password/token values; raw binding results |
| `401 Unauthorized` | Missing or invalid authentication info | Generic message `Authentication failed`; Basic challenge when needed | Whether username exists, wrong password, locked/disabled account |
| `403 Forbidden` | Authenticated but lacking permission; or blocked by another security rule | Generic message `Access denied` | Exact missing permission if unnecessary, other groups/accounts |
| `404 Not Found` | Resource does not exist or policy hides resource | `Not found` | Confirming a sensitive ID exists but belongs to someone else |
| `429 Too Many Requests` | Rate limiting/login throttling | `Too many requests`, optionally appropriate `Retry-After` | Per-username brute-force state |
| `500 Internal Server Error` | Server-side processing error | `An unexpected error occurred`, safe support ID if any | Java stack traces, class names, file paths, SQL, config, tokens |

**Do not collapse every error into 200 OK** just to make responses look uniform: doing so breaks HTTP contracts, alerts, and client handling. For **login failures within the same mechanism**, keep status, message, structure, and handling consistent to reduce account enumeration. Distinguishing 401 and 403 remains necessary for authentication/authorization semantics.

## 3. Threat Model: Information Leakage Through "Side Channels"

### 3.1. Bodies Containing Exception Messages

Wrong:

```java
// Anti-pattern: ex may contain raw tokens, DB addresses, usernames.
return Mono.just(Map.of("error", ex.getMessage()));
```

This is a fragment inside an error handler assuming an `ex` variable. Never use `ex.getMessage()`, `ex.toString()`, or `ExceptionUtils.getStackTrace(ex)` as API response content. Even `BadCredentialsException` can sometimes carry authentication request info or causes; never return it to clients.

### 3.2. Account Details Causing Enumeration

The following three scenarios must **not disclose distinct causes** when a client attempts to log in:

1. User `ghost` does not exist.
2. User `reader` exists but password is wrong.
3. User `disabled` exists but is disabled.

If responses say `No such user`, `Wrong password`, and `Account disabled`, attackers can probe valid usernames. OWASP recommends **generic** authentication responses, including for locked or disabled accounts.

However, **an identical body is not necessarily enough**: differing status codes, redirect `Location`, `WWW-Authenticate`, response lengths, or latencies can still leak. Apply the same policy at every login check point and add rate limiting, credential stuffing detection, and appropriate lockout/MFA controls.

### 3.3. Tokens, Claims, and Signatures

Unsafe examples:

```text
Invalid JWT "eyJhbGciOi..." signed with key id=prod-key-04
Token expired for alice@example.test at internal-host
Refresh token FAKE_TOKEN_CANARY rejected
```

Tokens can carry bearer privileges or contain claims/PII. Never return full JWTs, raw tokens, refresh tokens, JWK private keys, client secrets, session IDs, or sensitive claims. With bearer tokens, OAuth2-compliant challenges/headers may carry `error`/`error_description` per standard; choose minimal descriptions and **never put raw tokens** in them.

### 3.4. Debug/Stack Traces and Internal Paths

A stack trace can reveal:
- Spring Security/Spring Framework versions, package names, class names.
- Module names, paths, file names, line numbers.
- Database/driver type, SQL, network topology, or internal service addresses.
- Exception causes holding tokens/passwords/query params and user data.

Do not rely on "the frontend will hide it" because attackers read raw HTTP responses directly. Spring Boot's `server.error.*` properties restrict default error attributes, yet you must still audit **custom handlers, gateways, WebFilters, and tracing**.

### 3.5. Headers, URLs, and Caches Can Leak Too

- `Location`/redirect queries can carry usernames, emails, reasons, or tokens.
- `WWW-Authenticate` should hold standard challenges; never put passwords/tokens into `realm`.
- `Set-Cookie` must never contain raw passwords and should not be echoed in errors in a way that exposes session IDs.
- Queries/paths in `instance`, `path`, or raw URLs may contain sensitive identifiers. Never echo full URLs in error payloads if the system ever allowed secrets in queries.
- For authentication errors, use `Cache-Control: no-store` to avoid unintended storage of sensitive responses; system-wide cache/proxy settings also depend on resource type.
- Debug headers such as `X-Exception-Class`, `X-Stacktrace`, and `X-Sql` are completely inappropriate for public APIs.

## 4. Three Error-Handling Layers in Spring Security WebFlux

```text
Client request
     |
     v
SecurityWebFilterChain
     |
     +-- AuthenticationWebFilter / HTTP Basic
     |        |
     |        +-- failure -> ServerAuthenticationEntryPoint
     |
     +-- Authorization / ExceptionTranslationWebFilter
     |        |
     |        +-- authentication needed -> ServerAuthenticationEntryPoint -> 401
     |        +-- lacking permission    -> ServerAccessDeniedHandler      -> 403
     |
     v
WebFlux Handler / Controller / Service
     |
     +-- Controller exception -> @ExceptionHandler / @RestControllerAdvice
     |
     +-- Unresolved error     -> ErrorWebExceptionHandler /
                                 Spring Boot reactive error handling
     |
     v
HTTP response
```

The diagram aims to distinguish **handling paths** and does not promise the order of every WebFilter across versions. In reality, exceptions may arise in decoders, CORS, CSRF, resource servers, gateways, or custom WebFilters; never assume one `@RestControllerAdvice` catches everything.

### 4.1. `ServerAuthenticationEntryPoint`

Import: `org.springframework.security.web.server.ServerAuthenticationEntryPoint`.

Conceptual contract:

```java
Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception);
```

When the client must be asked to authenticate or invalid credentials are handled, the entry point decides the appropriate response (usually 401). With HTTP Basic, include `WWW-Authenticate: Basic realm="api"` so clients know how to authenticate; **never copy the exception message** into the body.

### 4.2. `ServerAccessDeniedHandler`

Import: `org.springframework.security.web.server.authorization.ServerAccessDeniedHandler`.

Conceptual contract:

```java
Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied);
```

When the user is authenticated yet lacks sufficient role/authority, the handler returns a generic 403. Never return role lists, internal policies, or the account name owning the resource.

### 4.3. `@RestControllerAdvice`

Advice catches exceptions from corresponding controllers/handler mappings, not errors across all WebFilters or before controller invocation. It is useful for standardizing 400/404/500 inside controllers, yet **does not replace Spring Security's `exceptionHandling(...)`**.

With `@PreAuthorize` method security or reactive errors from services, test the actual ordering and execution path. A sloppy `@ExceptionHandler(Exception.class)` can swallow `AccessDeniedException` and turn a 403 into 500, or worse, 200. Handle only clearly scoped exceptions without breaking security semantics.

### 4.4. `ErrorWebExceptionHandler` and Boot Error Attributes

Spring Boot WebFlux handles out-of-controller errors. Properties `server.error.include-message`, `include-stacktrace`, `include-exception`, `include-binding-errors`, and `include-path` control fields in the default error response. Never enable "always" options in production just for convenient debugging.

If an application wants all errors to follow one custom JSON schema, you can implement/customize `ErrorWebExceptionHandler` / `ErrorAttributes`, while preserving accurate statuses and guarding against error loops. That is an extension after verifying basic 401/403/500 paths.

## 5. Designing a Low-Leakage Error Contract

Use **stable server-controlled error codes** instead of echoing raw exceptions:

| Application code | HTTP status | Client message |
| --- | --- | --- |
| `AUTHENTICATION_FAILED` | 401 | `Authentication failed` |
| `ACCESS_DENIED` | 403 | `Access denied` |
| `BAD_REQUEST` | 400 | `Invalid request` |
| `NOT_FOUND` | 404 | `Not found` |
| `RATE_LIMITED` | 429 | `Too many requests` |
| `INTERNAL_ERROR` | 500 | `An unexpected error occurred` |

If localization is needed, return a **stable code** and let the frontend use a translation table. Never use raw `ex.getLocalizedMessage()` as a public translation.

### Correlation ID: Helpful Yet Must Be Safe

`requestId` can help support look up logs if:
- Generated by a trusted server/gateway, such as a UUID or bounded-length random ID.
- Never equal to a username, session ID, JWT, email, API key, database key, or sensitive fingerprint.
- If accepted from a client, validated/normalized and never used as identity proof.
- Logs have controlled access and redacted data.

Example:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred",
  "requestId": "req-7f39a21e"
}
```

This is an illustrative schema, not a requirement to expose every request ID publicly. Without a trustworthy correlation ID system, omitting this field is better than stuffing raw request URLs or tokens into it.

## 6. Runnable Example: Java 17+, Spring Boot 3.3.5, WebFlux

The project uses HTTP Basic on localhost to easily observe 401/403 and includes an endpoint emitting an **intentional** server error to test non-disclosure. In real deployments, **HTTP Basic must run over HTTPS/TLS with certificate verification**.

Structure:

```text
safe-reactive-errors/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/safeerrors/
    │   │   ├── SafeErrorsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── SafeApiErrorWriter.java
    │   │   ├── DemoController.java
    │   │   └── SafeControllerAdvice.java
    │   └── resources/application.properties
    └── test/java/dev/example/safeerrors/
        └── SafeErrorResponsesTests.java
```

### 6.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'safe-reactive-errors'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
```

Do not add `spring-boot-starter-web` to the demo if you want Spring Boot to select reactive WebFlux. Boot manages Spring Security versions via dependency management; do not pin security dependencies individually to avoid version mismatches.

### 6.2. Spring Boot Properties: Never Expose Traces to Clients

`src/main/resources/application.properties`:

```properties
server.port=8080

server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false
server.error.include-path=never

logging.level.org.springframework.security=INFO
```

These values fit Spring Boot 3.3.x. `include-path=never` further reduces the risk of reflecting raw URLs/paths containing non-public data. Some properties have safe defaults, yet declaring them explicitly prevents another profile configuration from accidentally turning traces on.

**Limitation:** `server.error.*` controls **default Boot error attributes**; it does not scrub JSON returned by custom controllers, stop proxy/APM logs, or override a handler that explicitly returns `ex.getMessage()`. That is why we still need the two handler layers below.

### 6.3. Main Application

`src/main/java/dev/example/safeerrors/SafeErrorsApplication.java`:

```java
package dev.example.safeerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorsApplication.class, args);
    }
}
```

### 6.4. Dedicated Error JSON Writer for Security

`src/main/java/dev/example/safeerrors/SafeApiErrorWriter.java`:

```java
package dev.example.safeerrors;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class SafeApiErrorWriter {

    public static final String AUTHENTICATION_JSON =
            "{\"code\":\"AUTHENTICATION_FAILED\",\"message\":\"Authentication failed\"}";

    public static final String ACCESS_DENIED_JSON =
            "{\"code\":\"ACCESS_DENIED\",\"message\":\"Access denied\"}";

    private SafeApiErrorWriter() {
    }

    public static Mono<Void> authenticationFailure(ServerWebExchange exchange) {
        return write(exchange, HttpStatus.UNAUTHORIZED,
                AUTHENTICATION_JSON, true);
    }

    public static Mono<Void> accessDenied(ServerWebExchange exchange) {
        return write(exchange, HttpStatus.FORBIDDEN,
                ACCESS_DENIED_JSON, false);
    }

    private static Mono<Void> write(
            ServerWebExchange exchange,
            HttpStatus status,
            String safeJson,
            boolean basicChallenge) {

        ServerHttpResponse response = exchange.getResponse();

        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().set("X-Content-Type-Options", "nosniff");

        if (basicChallenge) {
            response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"api\"");
        }

        byte[] bytes = safeJson.getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
```

Key points:
- Response JSON is a **server-defined constant**, containing no exceptions, usernames, tokens, or passwords.
- The two methods select status 401 and 403 respectively. Never return `AccessDeniedException.getMessage()` or `AuthenticationException.getMessage()`.
- The `WWW-Authenticate` header only contains realm `api`, with no user identifier or credentials. This satisfies HTTP Basic interaction requirements.
- `Cache-Control: no-store` prevents storing error responses unexpectedly; system-wide cache/proxy evaluation is still necessary.
- `DataBuffer`/`Mono<Void>` is returned to WebFlux; never call `block()`/`subscribe()`.
- `MediaType.APPLICATION_JSON` specifies JSON; no separate framework is needed when wanting a simple, fixed schema.

Because the JSON strings are constants, there is no risk of JSON injection from exception messages. When moving to dynamic values like request IDs, use a JSON serializer, validate inputs, and **allow only explicitly defined fields**; never manually concatenate raw exceptions into JSON.

### 6.5. Wiring Entry Point and Access-Denied Handler to Spring Security

`src/main/java/dev/example/safeerrors/SecurityConfig.java`:

```java
package dev.example.safeerrors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode("disabled-pass"))
                .roles("USER")
                .disabled(true)
                .build();

        return new MapReactiveUserDetailsService(
                reader, admin, disabled);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {

        ServerAuthenticationEntryPoint entryPoint =
                (exchange, exception) ->
                        SafeApiErrorWriter.authenticationFailure(exchange);

        ServerAccessDeniedHandler deniedHandler =
                (exchange, denied) ->
                        SafeApiErrorWriter.accessDenied(exchange);

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(entryPoint)
                        .authenticationFailureHandler(
                                new ServerAuthenticationEntryPointFailureHandler(
                                        entryPoint)))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler))
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Explanation:
1. `MapReactiveUserDetailsService` holds three **test** accounts. `reader` and `admin` are enabled; `disabled` has `isEnabled() == false`. Passwords are BCrypt-encoded; never store cleartext passwords in real storage.
2. `ServerAuthenticationEntryPoint` accepts `AuthenticationException`, yet the lambda **intentionally does not read `exception`**. Instead, it returns `AUTHENTICATION_FAILED`.
3. `ServerAccessDeniedHandler` accepts `AccessDeniedException`, yet **intentionally does not reflect `denied.getMessage()`**.
4. `HttpBasicSpec.authenticationEntryPoint(...)` sets the shared entry point for the Basic mechanism. `authenticationFailureHandler(...)` with `ServerAuthenticationEntryPointFailureHandler` defines the response when Basic authentication emits a credential error.
5. `ExceptionHandlingSpec.authenticationEntryPoint(...)` and `accessDeniedHandler(...)` handle cases where authentication is requested or authorization is denied.
6. `formLogin(form -> form.disable())` disables form login so clients get JSON errors instead of an HTML redirect to `/login`.
7. `/public` requires no login; `/admin` requires `ROLE_ADMIN`; remaining endpoints require an authenticated user.

**Production note:** `ServerAuthenticationEntryPointFailureHandler` has a policy for forwarding `AuthenticationServiceException` (service failures) per its implementation; do not force every database/identity provider error into "bad password" just so the API always returns 401. Infrastructure failures must be handled and monitored as system incidents, while public responses stay sanitized.

**CSRF note:** The demo uses GET only, so default CSRF needs no change. Never add `csrf(csrf -> csrf.disable())` just to make a POST test pass; whether CSRF is needed depends on clients, browsers, and authentication mechanisms.

### 6.6. Controller: One Public Route, Two Protected Routes, and One Fake Error

`src/main/java/dev/example/safeerrors/DemoController.java`:

```java
package dev.example.safeerrors;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(Principal principal) {
        return Mono.just(Map.of("user", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @GetMapping("/explode")
    public Mono<String> simulatedFailure() {
        // Fake data solely to test non-disclosure in 500 responses.
        return Mono.error(new IllegalStateException(
                "FAKE_SECRET_CANARY_042 in internal stack trace"));
    }
}
```

`/explode` is for local demos only. Never ship an intentionally failing endpoint to production. In reality, errors come from databases, HTTP clients, parsers, services, or external APIs; do not deliberately put secrets into exceptions to test production.

For `/me`, return only the username **to the authenticated principal itself**; never return `UserDetails.getPassword()` or authorities unnecessarily. If an API has endpoints querying other users, separate DTOs/profiles and enforce ownership-based authorization.

### 6.7. Controller Advice: Never Echo 500 Errors

`src/main/java/dev/example/safeerrors/SafeControllerAdvice.java`:

```java
package dev.example.safeerrors;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeControllerAdvice {

    public record SafeError(String code, String message) {
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<SafeError> handleDemoInternalFailure(
            IllegalStateException ignored) {

        SafeError safe = new SafeError(
                "INTERNAL_ERROR", "An unexpected error occurred");

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .cacheControl(CacheControl.noStore())
                .body(safe);
    }
}
```

Here `ignored` is handled **without ever being returned verbatim**. The code returns a safe DTO, status 500, and Cache-Control no-store. Even though the exception message contains the fake string `FAKE_SECRET_CANARY_042`, the response only contains `INTERNAL_ERROR`.

**Scope to understand:** Advice catches `IllegalStateException` from the demo controller. It is **not** a blanket catch-all for every WebFilter/Netty-layer error, and does not guarantee turning every infrastructure exception into one schema. Spring Boot `server.error.*` provides default protection for remaining errors. To standardize the entire system, also design `ErrorWebExceptionHandler`/`ErrorAttributes`, and test security filters, CORS, CSRF, rate limiters, and gateways.

Never carelessly add `@ExceptionHandler(Exception.class)` returning 200 or 500 for `AccessDeniedException`: doing so can mask Spring Security's 401/403 statuses. If a catch-all is needed, ensure security exceptions are handled separately, HTTP semantics are kept, and every error path is audited.

## 7. Running the Application and Observing Response Groups

From the `safe-reactive-errors` directory:

```bash
gradle bootRun
```

If using Gradle Wrapper, run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). On localhost, curl can test over HTTP; **never use HTTP Basic on public networks without HTTPS/TLS**.

Illustrative commands:

```bash
# Public endpoint:
curl -i http://localhost:8080/public

# Protected endpoint, missing credentials:
curl -i http://localhost:8080/me

# Wrong username:
curl -i -u ghost:guess http://localhost:8080/me

# Wrong password:
curl -i -u reader:wrong http://localhost:8080/me

# Existing account that is disabled:
curl -i -u disabled:disabled-pass http://localhost:8080/me

# Valid credentials with USER role:
curl -i -u reader:reader-pass http://localhost:8080/me

# Reader lacking ADMIN role:
curl -i -u reader:reader-pass http://localhost:8080/admin

# Admin with ADMIN role:
curl -i -u admin:admin-pass http://localhost:8080/admin

# Demo 500 error with message containing fake canary:
curl -i -u reader:reader-pass http://localhost:8080/explode
```

**Tooling note:** The passwords above are **fake** localhost strings. With real secrets, never put passwords after `-u user:password` in shell history/process arguments. Use `curl --user reader` so curl prompts interactively, and always use HTTPS with certificate validation.

### Expected Result Matrix

| Request | Status | Main response |
| --- | --- | --- |
| `GET /public`, not logged in | 200 | `public` |
| `GET /me`, missing Basic | 401 | `AUTHENTICATION_FAILED` |
| `GET /me`, non-existent username | 401 | `AUTHENTICATION_FAILED`, same message as other cases |
| `GET /me`, reader wrong password | 401 | `AUTHENTICATION_FAILED`, same message as other cases |
| `GET /me`, disabled valid password | 401 | `AUTHENTICATION_FAILED`, does not leak account state |
| `GET /me`, reader valid password | 200 | JSON with `user=reader`, no password/hash |
| `GET /admin`, reader valid password | 403 | `ACCESS_DENIED` |
| `GET /admin`, admin valid password | 200 | `admin-ok` |
| `GET /explode`, reader valid password | 500 | `INTERNAL_ERROR`, no `FAKE_SECRET_CANARY_042` |

These are **expected results from the example**, not a claim that Gradle was run on your machine. Statuses/bodies of some paths (especially outside controllers) may change if you use different filters/error handlers. Rely on actual tests to verify when upgrading Spring Security versions.

### Why Does 401 Use a Challenge While 403 Does Not?

HTTP Basic clients need to know the authentication mechanism, so 401 includes `WWW-Authenticate: Basic realm="api"`. Authenticated users lacking permissions at `/admin` normally receive 403. 403 should not disclose "You lack ROLE_SUPER_ADMIN in tenant 42" if that is internal information.

## 8. Automated Testing with WebTestClient

Tests do not just check status codes; they must verify **zero sensitive data in the body**, and that different login failures return consistent messages.

`src/test/java/dev/example/safeerrors/SafeErrorResponsesTests.java`:

```java
package dev.example.safeerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SafeErrorResponsesTests {

    @Autowired
    WebTestClient client;

    private static void assertNoLeak(String body) {
        assertNotNull(body);
        assertFalse(body.contains("FAKE_SECRET_CANARY_042"));
        assertFalse(body.contains("reader-pass"));
        assertFalse(body.contains("disabled-pass"));
        assertFalse(body.contains("TokenValidationException"));
        assertFalse(body.contains("IllegalStateException"));
        assertFalse(body.contains("stackTrace"));
        assertFalse(body.contains("org.springframework."));
        assertFalse(body.contains("at dev.example."));
    }

    private String unauthorizedBody(String username, String password) {
        String body = client.get().uri("/me")
                .headers(h -> h.setBasicAuth(username, password))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertNoLeak(body);
        return body;
    }

    @Test
    void publicEndpointIsAvailable() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturnSanitized401() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueMatches(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"api\"")
                .expectBody()
                .jsonPath("$.code").isEqualTo("AUTHENTICATION_FAILED")
                .jsonPath("$.message").isEqualTo("Authentication failed");
    }

    @Test
    void wrongUserWrongPasswordAndDisabledHaveSamePublicError() {
        String missingUser = unauthorizedBody("ghost", "guess");
        String wrongPassword = unauthorizedBody("reader", "wrong");
        String disabled = unauthorizedBody("disabled", "disabled-pass");

        assertEquals(SafeApiErrorWriter.AUTHENTICATION_JSON, missingUser);
        assertEquals(missingUser, wrongPassword);
        assertEquals(missingUser, disabled);
    }

    @Test
    void successfulLoginReturnsIdentityOnly() {
        String body = client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertNotNull(body);
        assertTrue(body.contains("reader"));
        assertFalse(body.contains("reader-pass"));
        assertFalse(body.contains("password"));
        assertFalse(body.contains("ROLE_ADMIN"));
    }

    @Test
    void readerCannotAccessAdminAndReceivesGeneric403() {
        String body = client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertEquals(SafeApiErrorWriter.ACCESS_DENIED_JSON, body);
        assertNoLeak(body);
    }

    @Test
    void adminIsAuthorized() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void unexpectedControllerExceptionDoesNotLeakCanary() {
        String body = client.get().uri("/explode")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().is5xxServerError()
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody(String.class)
                .returnResult().getResponseBody();

        assertNotNull(body);
        assertTrue(body.contains("INTERNAL_ERROR"));
        assertNoLeak(body);
    }

    @Test
    void invalidPasswordDoesNotReflectInput() {
        String canaryPassword = "FAKE_SECRET_CANARY_042";
        String body = unauthorizedBody("reader", canaryPassword);
        assertFalse(body.contains(canaryPassword));
    }
}
```

Run tests:

```bash
gradle test
```

**Expected:** 8 tests succeed when using the exact project and dependencies above. This is expected from the code; **no claim is made that Gradle was executed** in your repository.

### What Do the Tests Guarantee?

1. Public route still works.
2. Missing Basic → safe 401 JSON with Basic challenge.
3. Non-existent username, wrong password, and disabled account have **the same status/body**; prevents revealing causes through response content.
4. Valid login does not return passwords/hashes.
5. User lacking role receives **generic 403**, never protected permissions or exception classes.
6. Admin with sufficient role can still access valid endpoints.
7. Fake controller error has a canary in the exception yet the 500 body **contains no canary/stack trace**.
8. Client-submitted fake password is not reflected in the response.

**Limitation to remember:** Testing body equality does not completely prove immunity to account enumeration. Attackers can still analyze **processing time, response size, differing headers, rate-limit behavior, and login/password-reset channels**. Add controlled timing measurements if needed, and never claim "constant time" merely because response bodies match.

### Extending Tests with Canaries

In test environments **with no real secrets**, you can send distinctive values such as `FAKE_SECRET_CANARY_042` in passwords/headers and throw intentional errors with the same canary, then verify:
- HTTP response bodies/headers contain no canary.
- Error logs, proxy logs, and APM spans contain no raw canary in forbidden fields.
- No class names, SQL, password hashes, token payloads, or raw Authorization appear in responses.
- API gateways do not return stack traces when upstream returns 500.
- Test 401/403/500 from WebFilters and out-of-controller error handlers if customized.

When testing logs, never use production tokens/passwords. Use a **fake credential or revocable test account**, verify log policies, and delete afterward.

## 9. How to Diagnose Errors Without Disclosing Them?

### 9.1. Log Allowlisted Fields

An operational log can contain:
- `event=AUTH_FAILURE` / `event=ACCESS_DENIED` / `event=SERVER_ERROR`.
- Timestamp, server-issued route tag, status, latency, service, non-sensitive trace ID.
- Policy-minimized account identifier if required for auditing with proper access controls.
- Cause category in controlled monitoring systems, **never made public to clients**.

Conceptual example:

```java
// Fragment inside a component with a safe logger and context.
log.warn("event={} route={} outcome={}",
        "AUTH_FAILURE", "api-login", "DENIED");
```

Conversely, **do NOT log**:

```java
// ANTI-PATTERN: DO NOT USE.
log.error("Authentication failed: {}", exception.getMessage());
log.debug("Headers: {}", exchange.getRequest().getHeaders());
log.info("Credentials: {}", authentication.getCredentials());
```

These are **anti-patterns**; variables `exception`, `exchange`, and `authentication` are illustrative Spring Security objects. They can contain raw passwords/tokens; even `toString()` is sometimes unsafe if you do not control the implementation.

### 9.2. What If Internal Stack Traces Are Needed?

Some organizations permit writing stack traces into **access-controlled log channels** for forensics. However, stack traces can contain sensitive exception messages or request data. Policies should:
- Restrict loggers/packages, sampling, access permissions, and retention.
- Redact/avoid logging raw messages from untrusted exceptions.
- Never send raw `Authorization`, `Cookie`, or bearer tokens to log aggregators.
- Never print bodies containing passwords, OTPs, or refresh tokens.
- Never attach stack traces to API responses on 500 errors.
- Check APM/tracing configs because they may automatically capture exception attributes outside the application logger.

**Important:** "No stack trace in HTTP" does not equal "no secrets in logs". Both attack surfaces require independent review.

### 9.3. Redaction Must Happen at the Source

Masking a header in an APM dashboard after raw values have already been sent to the collector **does not prevent** exposure at the collector/export. Capture allowlisted fields from the start and drop:
- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie` when holding session tokens.
- `X-API-Key`, custom auth headers, bearer/refresh tokens.
- Passwords, password confirmations, OTPs, recovery codes in bodies/queries.
- Sensitive info encoded in URLs, metadata, or nested JSON.

Header names are case-insensitive; redaction mechanisms must recognize all case variants. When secrets can appear under custom field names, allowlisting is safer than relying on a denylist of a few common keys.

### 9.4. Protecting Investigation Support Data

Do not paste user emails, phone numbers, account states, roles, or tokens into public issues to "prove a bug". If a request ID exists, look up details through an internal RBAC/audited system and share only what is permitted.

### 9.5. Logs and Responses Require Separate Data Policies

Control access, encryption at rest, retention, exports, backups, log search, and incident response. If a secret leaked into logs, **rotate/revoke** the secret and inventory all copies; deleting one log line does not un-expose a leaked credential.

## 10. Preventing Account (User) Enumeration

OWASP emphasizes that "non-existent username", "wrong password", and "account disabled/locked" should have **generic** public responses in login contexts.

### 10.1. Why Is Fixing Messages Alone Not Enough?

Attackers can probe thousands of usernames and compare:
- 401 vs 403 vs 404.
- Body length, JSON fields, headers, redirect destinations.
- Average response times for existing vs non-existing users.
- Whether password-reset emails are sent and public response content.
- Attempt counts before rate limiters, captchas, or lockouts trigger.
- Timing and outcomes reflected by UI/JS.

To reduce risk:
- Keep status/body/headers consistent across login failures of the same class.
- Perform password verification through a trusted `PasswordEncoder`, never compare hashes manually with equals.
- When a username does not exist, design timing protection at the appropriate authentication layer; **do not write a manual fake BCrypt check and claim constant-time**.
- Apply rate limiting / throttling by IP, account, device, or combinations while accounting for anti-DoS.
- Use MFA, anomalous-login alerts, and credential-stuffing defenses where appropriate.
- Design password reset with messages like "If an account exists, we will send instructions", without confirming email existence.
- During registration, balance UX and enumeration resistance per the risk model; avoid unnecessary response differences.

### 10.2. Do Not Give Detailed Responses for Every 403

A business API sometimes needs to return field-level validation hints like "email format invalid" or "name too long". Those can be public **if the input is non-sensitive and design permits**. Never return:
- "Account 42 exists but belongs to user B".
- "User admin@example.test is disabled".
- "Your password matched, but you lack finance:approve in tenant secret".
- "JWT signature failed using private key ID ...".

When resource ownership must be hidden, 404 can be chosen instead of 403 in some cases; be consistent and test against resource enumeration. Never blindly change every 403 to 404 if that breaks API semantics and auditing.

## 11. Avoiding Leaks via Validation Errors and JSON Serialization

Errors from `@Valid`, binding, JSON decoding, and enum conversion can carry **input values** inside exceptions. Never return raw:
- `BindingResult.toString()`.
- `WebExchangeBindException.getMessage()`.
- `MethodArgumentNotValidException.getMessage()` per Servlet examples.
- Parsed request bodies/payloads if they contain passwords, tokens, or sensitive documents.

For safe validation, return only an **allowlisted** list of fields and server-defined codes:

```json
{
  "code": "BAD_REQUEST",
  "message": "Invalid request",
  "fields": [
    {"name":"displayName","code":"TOO_LONG"}
  ]
}
```

If `password` fails length requirements, you can display info about the **length rule** without returning the **submitted password value**. Never send `rejectedValue` or raw DTOs containing credentials.

When using `ProblemDetail`, do not mechanically assign `problem.setDetail(ex.getMessage())`. Pick only approved details; `instance` should not reflect raw paths/queries containing secrets.

## 12. WebFilter, CSRF, CORS, JWT, and Gateway Errors

### 12.1. `@RestControllerAdvice` Is Not the Chokepoint for All Errors

A custom `WebFilter` can emit `Mono.error(...)` **before the controller**. Likewise, CORS, CSRF, and resource-server authentication can return errors from different filters.

When aiming for a consistent error schema across the whole stack:
1. Inventory error sources at each layer.
2. Configure Spring Security entry points/denied handlers in the right places.
3. Configure error attributes or `ErrorWebExceptionHandler` for unexpected out-of-controller errors.
4. Configure gateway/reverse proxy error mapping for upstream outages, timeouts, or unsendable bodies.
5. Test actual HTTP responses, not just a controller with `throw new RuntimeException(...)`.

### 12.2. CSRF 403 Is Not Necessarily a Missing Role

A POST missing a CSRF token can receive 403 **before** controller logic executes. Never reflect expected/actual tokens or session IDs for debugging. The demo only uses GET, yet production state-changing endpoints must evaluate CSRF and test sanitized failure responses.

### 12.3. JWT and OAuth2 Resource Server

With bearer tokens, Spring Security can use OAuth2-specific entry points and `WWW-Authenticate: Bearer ...`. Never blindly apply `Basic realm="api"` to a bearer-only API; that violates client expectations. Keep protocol-accurate challenges while ensuring `error`/`error_description` contain no raw JWTs, refresh tokens, or sensitive claims.

### 12.4. Gateways Return Different Errors Than the Application

If a reverse proxy/Gateway emits 502/503/504 itself, WebFlux `@RestControllerAdvice` **never sees that request/exception**. You must configure gateway error pages/bodies, disable server banners/debug pages as appropriate, scrub headers, and test real upstream failures.

### 12.5. Committed Responses

In a reactive stack, if the server has already sent part of a response body and the publisher then emits an error, error handlers cannot always replace everything with a fresh 500 JSON. Never try to append stack traces/exceptions into a streaming response; design a streaming protocol, internal logging, and sensible partial-response policies. Test mid-stream errors with `Flux` or SSE if your product uses streaming.

## 13. Security QA Checklist for Error Responses

1. **401:** same message and structure for non-existent username, wrong password, and locked/disabled within the same flow; protocol-accurate Basic/Bearer challenges.
2. **403:** never return authority lists, resource ownership, or internal rule expressions unnecessarily.
3. **500:** no exception classes, stack traces, SQL, hostnames, internal file paths, versions, or secrets.
4. **400:** never reflect `rejectedValue` for passwords/tokens/OTPs.
5. **404:** never disclose resources belonging to other users/tenants via differing statuses/bodies.
6. **Headers:** no raw `Authorization`, `Cookie`, or secret-bearing `Set-Cookie` in support messages; verify `WWW-Authenticate`/`Location`.
7. **URL:** never echo raw query strings or secret-bearing request URIs.
8. **Cache:** apply appropriate caching policy; demo auth errors use `Cache-Control: no-store`.
9. **Error tiers:** test security filters, controller advice, Boot default handler, and gateways separately.
10. **Timing/enumeration:** do not compare bodies only; check status, headers, length, redirects, throughput/timing, and rate limits.
11. **Logging:** never print raw authentication objects, request bodies, headers, or exception messages that may hold credentials.
12. **Observability:** APM/tracing/exporters filter secrets at the source; do not mask only in dashboards.
13. **Security context:** never pretend an anonymous caller is authenticated; never turn `AccessDeniedException` into a 200 fallback.
14. **Tests:** use fake canaries, never real credentials; verify both HTTP responses and logs/traces in a controlled environment.
15. **Production flags:** audit `server.error.include-*` and profile-specific configs; never enable traces via query parameters.
16. **Incident:** if a credential leaked, rotate/revoke it and inventory all copies/logs/artifacts.

## 14. Anti-Patterns to Eliminate

| Anti-pattern | Consequence | Replace with |
| --- | --- | --- |
| `return ex.getMessage()` | Leaks username, token, stack, or SQL | Generic code/message |
| `return exception.toString()` | Exposes class/package and cause | Allowlisted response DTO |
| 401 "user not found", 403 "wrong password" | Account enumeration | One unified login-failure policy |
| 500 containing `stackTrace`/`exception` | Exposes runtime structure | `server.error.*=never/false` and safe handlers |
| `@ExceptionHandler(Exception.class)` always returning 200 | Masks security errors, breaks HTTP semantics | Properly scoped handlers; never swallow `AccessDeniedException` |
| Logging raw `HttpHeaders` | Leaks Authorization/Cookie | Safe allowlisted metadata |
| Logging raw `Authentication` | May leak credentials/details | Event code and minimized identity |
| `ProblemDetail.detail = ex.getMessage()` | Leaks via RFC problem details | Approved detail |
| `error.path` containing sensitive queries | Leaks resource identifiers/secrets | Never echo raw URLs; Boot flags |
| Trusting frontend to hide response | Attackers still inspect raw HTTP | Server/gateway sanitization |
| Checking only status 401 | Body/headers may still leak | Inspect full response and timing |
| Tests using production passwords | Tests create data incidents | Fake canaries and revocable test accounts |
| APM debug auto-capturing exceptions | Tokens in tracing platform | Scrub in instrumentation/at source |
| 403 response revealing missing role | Exposes internal policy/org structure | Generic `ACCESS_DENIED` |
| "Didn't log stacks" so no incident needed | Secrets may exist in other copies | Rotation, log inventory, RBAC |

## 15. Review Questions

**1. Why shouldn't `BadCredentialsException.getMessage()` be returned to clients?**  
Because the exception can contain diagnostic details, usernames, account details, or internal data; return server-defined safe codes/messages instead.

**2. How should responses look when a username does not exist vs when a password is wrong?**  
Within the same login flow, use consistent status/body/headers and avoid revealing separate causes.

**3. How does `401` differ from `403`?**  
401 means authentication is required or credentials are invalid; 403 usually means authenticated yet not permitted (or blocked by another rule such as CSRF).

**4. Which header should be considered on an HTTP Basic 401?**  
`WWW-Authenticate: Basic realm="api"`, without containing credentials, users, or secrets.

**5. Can `@RestControllerAdvice` catch every exception from WebFilters?**  
No. Handle at security entry points/denied handlers and Boot's reactive error pipeline where appropriate.

**6. Does `server.error.include-stacktrace=never` automatically stop custom controllers from returning stack traces?**  
No. It only governs default error attributes; custom code must still be fixed.

**7. Why aren't identical auth error bodies proof of complete enumeration protection?**  
Because statuses, headers, redirects, timing, or rate-limit behavior can still differ.

**8. Can the raw JWT be returned so the client can analyze the error itself?**  
Should not; tokens can carry bearer privileges/PII. Return only minimal protocol-compliant error codes/challenges.

**9. Should raw `Authorization` be logged to make support easier?**  
No. It can contain Basic passwords or bearer tokens; log event codes and curated metadata instead.

**10. How can non-leakage of secrets be tested safely?**  
Use **fake** canaries/credentials in tests and inspect response bodies/headers and logs/APM within an authorized test scope.

**11. If a 500 comes from a gateway rather than WebFlux, which app handler catches it?**  
No WebFlux handler can reliably catch gateway-generated errors; configure/test the gateway separately.

**12. Is setting `ProblemDetail.detail` to `ex.getMessage()` safe by default?**  
No; you need to allowlist content and avoid sensitive causes/instances/paths.

**13. Why shouldn't `onErrorResume(ex -> Mono.just(secret))` be used on authorization failure?**  
Because it can swallow `AccessDeniedException` and turn a rejected request into a successful response containing sensitive data.

**14. Why should error responses include `Cache-Control: no-store` in the demo?**  
To reduce the risk of caches storing authentication error info or sensitive metadata; full system configuration is still required.

### Practice Exercises

1. Run the project and compare 401 bodies for `ghost`, `reader` with wrong password, and `disabled`. Confirm they match **in response body**, then propose additional timing/header checks.
2. Add a test cookie/Authorization header containing `FAKE_TOKEN_CANARY` to a demo request; verify the response does not reflect this value.
3. Intentionally replace `SafeControllerAdvice` with `ex.getMessage()` in a learning environment, run the canary test to see it fail, then restore the safe version.
4. Add an ADMIN-protected `GET /admin/details` endpoint and test that `reader` receives a generic 403 with no role names or account info.
5. Set `server.error.include-stacktrace=always` in an isolated test environment to observe the risk; **never put that config in production**, then restore `never`.
6. Create a validation error for a body containing `password`, designing a `BAD_REQUEST` response with an allowlisted field name and no `rejectedValue`.
7. Design a random request ID included in responses and redacted logs to aid debugging without passing usernames/tokens.
8. Try a failing `WebFilter` and a failing controller to explain why `@RestControllerAdvice` does not replace Spring Security exception handling.
9. If using bearer tokens instead of HTTP Basic, update `WWW-Authenticate` to a protocol-compliant Bearer challenge; verify no raw tokens/claims appear in responses.
10. Write an API gateway checklist: 502/503/504 responses contain no upstream hostnames, stack traces, server banners, or raw headers.

## 16. Official References

- [Spring Security API — ServerHttpSecurity.HttpBasicSpec](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html): custom entry point and failure handler for Basic.
- [Spring Security API — ServerHttpSecurity.ExceptionHandlingSpec](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html): `authenticationEntryPoint` and `accessDeniedHandler`.
- [Spring Security API — ServerAuthenticationEntryPointFailureHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html): bridge from authentication failure to entry point.
- [Spring Framework — WebFlux Controller Advice](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-advice.html): scope of `@RestControllerAdvice` and `@ExceptionHandler`.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.error.include-*` and logging.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication responses, account enumeration.
- [OWASP — Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): public error info vs internal diagnostics.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): never log passwords, session IDs, access tokens, and sensitive data.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): JSON problem details standard when APIs choose to use it.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): security chain and authentication configuration.

**Key takeaway:** When handling errors in Spring Security reactive, **preserve accurate HTTP statuses**, return **intentional generic error codes/messages**, and never reflect `ex.getMessage()`, raw credentials, account states, tokens, or stack traces. Configure protections at the **HTTP Basic entry point, access-denied handler, controller advice, Boot error handler, and gateway**, while scrubbing logs/APM. Test with **fake canaries** and **varied account cases** to ensure error responses never become an attacker's data source.