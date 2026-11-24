# Distinguishing 401 Unauthorized and 403 Forbidden in Spring Security Reactive

## 1. Goals and Common Pitfalls

When a REST API running on **Spring WebFlux + Spring Security** rejects a request, the client may receive **401 Unauthorized** or **403 Forbidden**. These two codes are easily misunderstood because the word Unauthorized in 401 sounds like "no permission". In modern HTTP semantics, the key difference is:

- **401 Unauthorized**: the request has not provided valid authentication proof for the target resource. The client may need to log in, send credentials, or refresh a token per the protocol.
- **403 Forbidden**: the server understood the request but refuses to authorize it. A typical case is **a successfully authenticated user lacking the required authority/role/permission**.

A good REST API does not merely return the right status code; it also preserves the authentication protocol (**WWW-Authenticate** when needed), safe error messages, consistent access rules, diagnosable logs, and clear tests.

After this lesson, you will:

1. Distinguish **authentication (identity verification)** and **authorization (permission checking)**, and explain why 401/403 are not synonyms.
2. Understand 401/403 according to **RFC 9110**, HTTP Basic, and Bearer tokens.
3. See the exception flow inside **SecurityWebFilterChain**: AuthenticationWebFilter, AuthorizationWebFilter, ExceptionTranslationWebFilter, and reactive error-handling components.
4. Use **ServerAuthenticationEntryPoint** and **ServerAccessDeniedHandler** in the right places.
5. Write Java 17+ Spring Boot WebFlux code returning consistent 401/403 JSON without leaking credentials and without changing the meaning of WWW-Authenticate.
6. Test requests with missing credentials, wrong credentials, regular user missing ROLE_ADMIN, admin with sufficient permissions, permitAll, and denyAll.
7. Handle easily confused edge cases: **403 caused by CSRF**, CORS preflight, form login redirect, expired bearer token, 404/405, 5xx errors, and resource-level permissions.

**Note:** 401 does not mean "authenticated but lacking permissions", and 403 does not automatically mean "wrong password". Still, the final status also depends on the authentication scheme, security chain, exception handlers, and endpoint security decisions.

## 2. Reading HTTP Semantics Correctly: RFC 9110

### 2.1. 401 Unauthorized

Per HTTP Semantics (RFC 9110), 401 indicates the request lacks valid authentication credentials for the target resource. When the server sends a **401** response, it **MUST** send at least one corresponding challenge in the **WWW-Authenticate** header.

HTTP Basic example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="lesson-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

Here:

- **Status 401**: no valid credentials yet.
- **WWW-Authenticate: Basic realm="lesson-api"**: the client is asked to use HTTP Basic in the corresponding protection space.
- **JSON body**: informational contract for the client application; does not replace the standard challenge.
- **no-store**: prevents caching security-related responses.
- **message**: does not disclose whether the username exists, raw passwords, tokens, or stack traces.

Common situations: an endpoint requires authenticated access without a header; a Basic header has wrong username/password; a bearer token is expired or invalid. However, each scheme has its own challenge; never use a Basic challenge on an endpoint that only supports Bearer.

### 2.2. 403 Forbidden

403 means the server understood the request but **refuses to fulfill it**. The caller may already be authenticated, or the server may have another reason to refuse; the RFC does not assert that every 403 must have a valid Authentication.

Example of a logged-in caller missing ROLE_ADMIN:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

A normal 403 **is not required** to include WWW-Authenticate. If you add a Basic challenge for a logged-in user lacking admin permissions, the client might mistakenly think resending the same password will fix the permissions.

**More precise distinction:** 401 relates to not yet meeting **authentication** requirements, whereas 403 is a **refusal** decision; in Spring Security, an authenticated user without the required authority normally receives 403. A system may intentionally return 404 instead of 403 to avoid disclosing a resource's existence, but the policy and tests must be designed consistently.

### 2.3. Quick Comparison Table

| Criterion | 401 Unauthorized | 403 Forbidden |
| --- | --- | --- |
| Primary meaning | Missing/wrong credentials for the scheme required by the endpoint | Server refuses the operation |
| Common caller state | Not logged in, invalid token, expired token | Logged in but lacking role/scope/record-level permission |
| WWW-Authenticate | Required to have a challenge per RFC 9110 when responding 401 | Usually not needed; some schemes include extra info |
| What client should do | May need to log in/provide valid credentials/refresh token | Do not retry infinitely; may request permissions or change operation |
| Is it another 4xx business error? | Do not use instead of 400/404/409 | Do not use instead of 400/404/409 if unrelated to permissions |
| Should body distinguish wrong username vs wrong password? | Should not | Not applicable |
| Should return 200 with {"error":...}? | No | No |

## 3. Authentication, Authorization, and Resources

**Authentication** answers "who is the caller?" and must verify credentials via a trusted mechanism. **Authorization** answers "is this caller allowed to perform this action on this request/resource?".

Diagram:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    +--> AuthenticationWebFilter (Basic, Bearer, ...)
    |      |
    |      +--> Missing credentials: may not create Authentication
    |      +--> Wrong credentials: authentication failure
    |      +--> Valid credentials: trusted Authentication
    |
    +--> AuthorizationWebFilter / authorizeExchange rules
    |      |
    |      +--> permitAll endpoint: passes URL authorization step
    |      +--> authenticated endpoint: requires authenticated caller
    |      +--> hasRole/hasAuthority endpoint: requires specific permission
    |      +--> denyAll endpoint: denies everyone
    |
    +--> ExceptionTranslationWebFilter / error handlers
    |      |
    |      +--> Authentication required: ServerAuthenticationEntryPoint
    |      +--> Authenticated but lacking permission: ServerAccessDeniedHandler
    |
    v
Controller / RouterFunction / Service
    |
    v
Business authorization (owner, tenant, record policy)
    |
    v
Response
~~~

This is a conceptual diagram and does not guarantee the exact order of every WebFilter across versions/configurations. An authentication error may be handled directly by the authentication filter, while authorization errors typically go through exception translation. Therefore, sometimes you need to configure the entry point in both **httpBasic(...)** and **exceptionHandling(...)** to unify JSON responses.

### 3.1. SecurityContext and AnonymousAuthenticationToken

An Authentication can hold a principal, authorities, and an isAuthenticated flag. **AnonymousAuthenticationToken** is the representation for an unauthenticated user, not the result of password verification. In some configurations, an anonymous token reports isAuthenticated() as true due to token semantics, yet Spring Security's **authenticated()** rule still **does not treat anonymous as a real login**.

**Do not write manually:**

~~~java
// Wrong if used alone to decide whether the caller is logged in:
if (authentication != null && authentication.isAuthenticated()) {
    return secretData;
}
~~~

Instead, use the **.authenticated()**, **hasRole(...)**, **hasAuthority(...)** DSL or an appropriate AuthenticationTrustResolver; check owner/tenant in the service/repository. There is no need to create a privileged anonymous Authentication to handle requests missing credentials.

### 3.2. Being Authenticated Does Not Mean Having Enough Permissions

Alice has ROLE_USER:

- GET /api/me requires authenticated → allowed.
- GET /api/admin/report requires ROLE_ADMIN → rejected (usually 403).
- GET /api/orders/42 requires authenticated → passes URL rule, **but** the service must still ensure order 42 belongs to Alice or Alice is permitted to read it.

If an API only uses authenticated without record-level checks, that can be an **IDOR/BOLA** vulnerability. A correct status code cannot substitute for proper authorization design.

## 4. 401/403 Decision Matrix in a REST API

Use the following table to predict behavior before writing code:

| Situation | Authentication | Permission check | Typical outcome |
| --- | --- | --- | --- |
| GET public without credentials | Not required | permitAll | 200 |
| GET protected without credentials | No valid identity | authenticated | **401**, Basic/Bearer challenge depending on scheme |
| GET protected with wrong password | Failed | Not eligible for authorization | **401** |
| GET protected using expired bearer token | Invalid token | Not eligible for authorization | **401**, Bearer invalid_token per mechanism |
| GET protected with valid user | Succeeded | authenticated | 200 |
| GET admin with ROLE_USER user | Succeeded | hasRole ADMIN not met | **403** |
| GET admin with ROLE_ADMIN | Succeeded | hasRole ADMIN met | 200 |
| GET denyAll endpoint while logged in | Succeeded | denyAll | **403** in common Basic configs |
| GET denyAll endpoint while not logged in | Invalid/missing | denyAll | May be **401** when entry point is used |
| POST missing CSRF with CSRF enabled | May be logged in or not | **CSRF filter** rejects | Usually **403** — not necessarily a role error |
| OPTIONS preflight rejected | May not send credentials | **CORS** | Status set by CORS/security config, may be 403/401 |
| GET record belonging to someone else | May be logged in | owner check rejects | May be 403 or 404 per policy |
| Non-existent URL | Not itself an authentication error | Routing | 404, though security may block earlier |
| Request with wrong HTTP method | Not itself an authentication error | Routing | 405, though security may block earlier |
| Identity database failure | Cannot verify due to system error | No permissions granted | Appropriate 5xx/503, not default 401 |
| Client sends too many requests | Rate limiting issue | Not a role issue | 429 if rate limit policy applies |

**Do not infer from status alone:** 403 can come from CSRF, CORS, URL rules, method security, or object permissions. 401 can come from missing credentials, wrong password, expired token, or an authentication filter not supporting the scheme chosen by the client. Diagnosis must rely on request flow, sanitized logs, and tests.

## 5. 401/403 Depend on the Authentication Mechanism

### 5.1. HTTP Basic

The client sends the header:

~~~http
Authorization: Basic <base64(username:password)>
~~~

Base64 is **not secure encryption**; only send HTTP Basic over **HTTPS** in real environments.

- Missing header on a protected endpoint → usually 401 with Basic challenge.
- Header containing wrong username/password → 401.
- Valid header but lacking ROLE_ADMIN → 403.
- Valid header and sufficient permissions → 2xx per business logic.

If you want custom JSON while still complying with Basic, keep:

~~~http
WWW-Authenticate: Basic realm="lesson-api"
~~~

HTTP clients know they must send credentials using Basic. Browsers may display a login prompt upon seeing the challenge; that is client behavior, not a reason to break the HTTP standard.

### 5.2. Form Login Using Cookie/Session

In a **formLogin()** application for browsers, an unauthenticated caller accessing a protected URL is usually **HTTP 302 redirected** to the login page instead of receiving JSON 401. Wrong login credentials may also redirect to /login?error. A logged-in user lacking permissions may receive **403**.

Therefore, do not write a test asserting "every unauthenticated request is always 401" for an app with browser form login. For REST APIs needing JSON statuses, choose a clear mechanism or entry point, and separate security chains between API/browser if needed.

**Note:** 302 is the entry point's UX strategy in form login configuration; it does not alter the original meaning of HTTP 401. Tests must follow the actual configuration.

### 5.3. OAuth2 Resource Server with Bearer Token

Bearer has a different challenge from Basic:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

For invalid/expired tokens, RFC 6750 describes **error="invalid_token"** accompanying 401 when appropriate. When the token is valid but lacks the required scope, **403 Forbidden** and **insufficient_scope** information may be returned per the OAuth2 specification.

Illustrative examples per Bearer semantics:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

In Bearer, **403 sometimes also includes WWW-Authenticate** with insufficient_scope info; do not rigidly apply a rule that "only 401 has WWW-Authenticate". Conversely, when no token is present, a Resource Server may simply return WWW-Authenticate: Bearer without revealing error details.

**Prohibition:** do not hard-code a Basic challenge for an API that only accepts Bearer tokens. With Spring Security Resource Server, use Bearer entry points/denied handlers, preserving issuer, signature, expiry, audience, and scope mapping semantics.

### 5.4. Multiple SecurityWebFilterChains

If one chain for /api/** uses Bearer and another chain for browsers uses form login, **the exact same unauthenticated state** can yield 401 on the API but 302 on the web. This is intentional if the matchers and ordering are configured properly.

When there are multiple chains, check securityMatcher, @Order, and the authentication/authorization mechanism of the **chain that actually selects the request**. Do not funnel all errors through a global Basic entry point when other protocols exist.

## 6. Error-Handling APIs in Spring Security Reactive

Relevant interfaces:

| Reactive API | When used | Result |
| --- | --- | --- |
| **ServerAuthenticationEntryPoint** | Client needs to be asked to authenticate | Mono<Void>, usually writes 401/challenge |
| **ServerAccessDeniedHandler** | Authenticated but fails authorization, or other denial cases | Mono<Void>, usually writes 403 |
| **ServerAuthenticationFailureHandler** | An authentication attempt fails in AuthenticationWebFilter | Mono<Void>, may delegate to entry point |
| **ServerHttpSecurity.exceptionHandling(...)** | Registers entry point/denied handler for exception translation | Applies to authorization errors |
| **ServerHttpSecurity.httpBasic(...)** | Configures Basic filter, entry point, failure handler | Applies to Basic credentials |
| **ReactiveAuthenticationManager** | Verifies input Authentication | Mono<Authentication> or error |
| **SecurityWebFilterChain** | Runs WebFilters and security rules | Protects both Controllers and RouterFunctions |

Correct WebFlux packages:

~~~java
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.web.server.ServerWebExchange;
~~~

Do not confuse with Servlet's AuthenticationEntryPoint, AccessDeniedHandler, HttpServletRequest, HttpServletResponse, or HttpSecurity. They have different signatures and lifecycles.

### 6.1. AuthenticationEntryPoint

Functional signature:

~~~java
Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception);
~~~

Responsibility: initiate an authentication challenge response, usually setting 401 and WWW-Authenticate matching the Basic/Bearer scheme. Do not fabricate a granted Authentication inside an error handler.

### 6.2. AccessDeniedHandler

Functional signature:

~~~java
Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied);
~~~

Responsibility: write an access-denied response when authorization fails. For an authenticated user lacking a role/authority, usually write 403. Do not convert it into 401 just to make the client open a login screen if credentials are already valid.

### 6.3. AuthenticationFailureHandler

In a specific authentication filter, the failure handler can handle bad credentials and delegate to the entry point. **ServerAuthenticationEntryPointFailureHandler** is the adapter for using an entry point in this flow. Note that an **AuthenticationServiceException** may indicate a system error and need different handling from a wrong password; do not catch all errors and automatically convert them to 401 if that hides identity store failures.

### 6.4. Why Is @RestControllerAdvice Not Enough?

HTTP security filters process requests **before the controller is invoked**, so exceptions handled by filters do not necessarily pass through `@ExceptionHandler` in `@RestControllerAdvice`. Authentication/authorization errors should be customized in **SecurityWebFilterChain** or appropriate handlers; controller advice handles business errors, validation, and exceptions emerging from controllers/services within the framework-supported scope.

Do not add `@ExceptionHandler(Exception.class)` returning 403 for every exception. Doing so turns NullPointerException, timeouts, and database errors into "access denied", hiding server outages and skewing metrics.

### 6.5. Designing the JSON Error Contract

A simple contract:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Authentication required"
}
~~~

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Access denied"
}
~~~

Criteria:

- Status remains genuine **401/403**, never return 200 with an error body.
- Content-Type is properly **application/json**, body UTF-8 encoded.
- For Basic 401, must include **WWW-Authenticate: Basic realm="..."**.
- Never return raw exception messages, passwords, Authorization headers, session cookies, hashes, JWT claims, or stack traces.
- Use stable error codes for clients; message wording may be localized while avoiding leaking account info.
- A server-generated/controlled requestId can be added if correlation/auditing is needed.
- Set Cache-Control: no-store to avoid caching security-related errors.
- If using application/problem+json, must comply with RFC 9457 Problem Details (appropriate type/title/status/detail/instance) and test the schema, not merely change the header.

**Never use status 403 instead of a required 401 response just to hide authentication failure**, nor tell untrusted clients specifically "username exists but password is wrong".

## 7. Java 17+ Demo: HTTP Basic API Distinguishing 401 and 403

The demo uses **Spring Boot 3.5.16**, Java 17+, and compatible Gradle 8.x. Version 3.5.16 is available on Maven Central, though it is the final OSS release of the 3.5.x branch per Spring Boot announcements; for new production deployments, choose an actively updated branch or appropriate commercial support. This lesson picks 3.5.16 so the sample code uses Spring Security 6.x and common WebFlux APIs.

Observed targets:

| Request | Condition | Result |
| --- | --- | --- |
| GET /public/ping | No login needed | 200 JSON |
| GET /api/me | Requires authenticated | 401 if missing/wrong credentials; 200 if valid |
| GET /api/admin/report | ROLE_ADMIN | 403 for ROLE_USER; 200 for ROLE_ADMIN |
| GET /closed/feature | denyAll | 403 for logged-in user |
| GET /unlisted | default denyAll | 403 for logged-in user |

Demo user data:

- alice / alice-pass: ROLE_USER.
- admin / admin-pass: ROLE_USER, ROLE_ADMIN.

**File structure:**

~~~text
reactive-401-403/
├── settings.gradle
├── build.gradle
├── src/main/java/example/errors/ErrorsApplication.java
├── src/main/java/example/errors/SecurityConfig.java
├── src/main/java/example/errors/ApiController.java
└── src/test/java/example/errors/HttpErrorsTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'reactive-401-403'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
~~~

Spring Boot manages Spring Framework/Security/Reactor versions via dependency management; do not manually pin incompatible Spring Security versions. For real projects, generate a Gradle Wrapper so team members use the same Gradle version.

### 7.3. ErrorsApplication.java

~~~java
package example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — Distinguishing Entry Point and Denied Handler

~~~java
package example.errors;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    private static final String CHALLENGE =
            "Basic realm=\"lesson-api\"";

    private static final String AUTHENTICATION_JSON =
            "{\"code\":\"AUTHENTICATION_REQUIRED\","
            + "\"message\":\"Authentication required\"}";

    private static final String AUTHORIZATION_JSON =
            "{\"code\":\"ACCESS_DENIED\","
            + "\"message\":\"Access denied\"}";

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ServerAuthenticationEntryPoint jsonAuthenticationEntryPoint() {
        return (exchange, error) ->
                writeError(exchange,
                        HttpStatus.UNAUTHORIZED,
                        AUTHENTICATION_JSON,
                        true);
    }

    @Bean
    ServerAccessDeniedHandler jsonAccessDeniedHandler() {
        return (exchange, error) ->
                writeError(exchange,
                        HttpStatus.FORBIDDEN,
                        AUTHORIZATION_JSON,
                        false);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerAuthenticationEntryPoint jsonAuthenticationEntryPoint,
            ServerAccessDeniedHandler jsonAccessDeniedHandler) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .pathMatchers("/closed/**").denyAll()
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(
                                jsonAuthenticationEntryPoint))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                jsonAuthenticationEntryPoint)
                        .accessDeniedHandler(
                                jsonAccessDeniedHandler))
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    private static Mono<Void> writeError(
            ServerWebExchange exchange,
            HttpStatus status,
            String json,
            boolean challenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);

        HttpHeaders headers = response.getHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (challenge) {
            headers.set(HttpHeaders.WWW_AUTHENTICATE, CHALLENGE);
        }

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        headers.setContentLength(bytes.length);

        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
~~~

**Technical notes:**

1. **jsonAuthenticationEntryPoint** returns 401, the Basic challenge, and safe JSON.
2. **jsonAccessDeniedHandler** returns 403 and different JSON; does not add a Basic challenge for users missing a role.
3. **httpBasic.authenticationEntryPoint(...)** handles the HTTP Basic flow needing an authentication challenge response.
4. **exceptionHandling.authenticationEntryPoint(...)** handles when authorization requires login but the caller has no valid identity yet.
5. **exceptionHandling.accessDeniedHandler(...)** handles missing permissions for a request that already has authentication.
6. **Specific rule /api/admin/** is placed before /api/**; reversing the order would let normal users match the broader rule.
7. **anyExchange().denyAll()** avoids accidentally exposing unlisted URLs.
8. **writeError** returns Mono<Void> and writes a data buffer via reactive ServerHttpResponse. Never call block() or subscribe() manually.
9. The JSON payload is static so dynamic escaping is unnecessary; when displaying requestId or input metadata, use a standard JSON serializer and sanitize data.
10. The demo only uses GET, keeping CSRF default. If adding POST, handle CSRF according to the client model; do not disable it just to make tests easier.

**Password security:** passwords in source are only learning fixtures; hash with BCrypt when creating UserDetails. Do not use hard-coded passwords, sensitive usernames, or non-TLS HTTP in production. Do not return raw Authentication/UserDetails to the client.

### 7.5. ApiController.java

~~~java
package example.errors;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }

    @GetMapping("/closed/feature")
    public Mono<Map<String, String>> disabled() {
        return Mono.just(Map.of("feature", "hidden"));
    }
}
~~~

The controller does not check passwords or permissions itself; URL rules already blocked invalid requests before the handler returns data. For real APIs with per-user data, the service still needs record-ownership checks.

### 7.6. Running the Application

In the `reactive-401-403` directory, JDK 17+ and compatible Gradle 8.x are required:

~~~bash
gradle bootRun
~~~

The application uses port 8080 per Spring Boot defaults unless overridden. On localhost you can test over HTTP; production must use HTTPS to protect Basic credentials.

## 8. Observing with curl

In another Bash terminal, try:

~~~bash
# 1. Public: no login needed.
curl -i http://localhost:8080/public/ping

# 2. Missing credentials, protected endpoint.
curl -i http://localhost:8080/api/me

# 3. Wrong Basic credentials.
curl -i -u alice:wrong-pass http://localhost:8080/api/me

# 4. Non-existent username.
curl -i -u unknown:some-pass http://localhost:8080/api/me

# 5. Valid login, allowed to access profile.
curl -i -u alice:alice-pass http://localhost:8080/api/me

# 6. Valid login but missing ROLE_ADMIN.
curl -i -u alice:alice-pass http://localhost:8080/api/admin/report

# 7. Has ROLE_ADMIN.
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report

# 8. DenyAll: even admin cannot access.
curl -i -u admin:admin-pass http://localhost:8080/closed/feature

# 9. Unlisted route: blocked by default deny.
curl -i -u admin:admin-pass http://localhost:8080/unlisted
~~~

**The representative HTTP responses below are expected demo results, not experimental logs from a running server.** Headers added by Netty/proxies may differ; JSON property order is not a contract.

**Missing credentials or wrong credentials:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="lesson-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

**Alice logs in correctly:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"username":"alice"}
~~~

**Alice lacks admin role:**

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

**Valid admin:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"report":"ok"}
~~~

**Admin accesses denyAll endpoint:**

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

If the same URL uses form login, the status may differ (especially 302 redirect). If placing the API behind a gateway or changing ExceptionHandlingSpec/HttpBasicSpec, update expectations to match the real contract rather than copying this table mechanically.

### 8.1. Result Matrix for the Demo

| Request | Authentication | Permission | Expected |
| --- | --- | --- | --- |
| /public/ping without header | Not required | permitAll | 200 |
| /api/me without header | Missing | authenticated | **401** + Basic challenge |
| /api/me wrong password | Failed | No valid identity | **401** + Basic challenge |
| /api/me non-existent username | Failed | No valid identity | **401**, does not leak username |
| /api/me with alice | Succeeded ROLE_USER | authenticated | 200 |
| /api/admin/report with alice | Succeeded ROLE_USER | Missing ROLE_ADMIN | **403** |
| /api/admin/report with admin | Succeeded ROLE_ADMIN | Has ROLE_ADMIN | 200 |
| /closed/feature with admin | Succeeded ROLE_ADMIN | denyAll | **403** |
| /unlisted with admin | Succeeded ROLE_ADMIN | default denyAll | **403** |

On Windows PowerShell, use **curl.exe** instead of the curl alias and enter commands on a single line. You can add `-v` or `-i` to view WWW-Authenticate; avoid copying real Authorization/cookie values from logs into public documents.

## 9. Integration Testing with WebTestClient

The most important tests send requests **actually through the WebFilter chain**, because unit tests calling a controller directly bypass authentication and authorization.

File **src/test/java/example/errors/HttpErrorsTest.java**:

~~~java
package example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HttpErrorsTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsAccessibleWithoutAuthentication() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingCredentialsProduces401ChallengeAndJson() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"lesson-api\"")
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED")
                .jsonPath("$.message")
                .isEqualTo("Authentication required");
    }

    @Test
    void invalidPasswordProduces401Not403() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"lesson-api\"")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void unknownUsernameDoesNotRevealAccountExistence() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("unknown", "some-pass"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void validCredentialsAllowProfile() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void loggedInUserWithoutAdminRoleGets403() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.WWW_AUTHENTICATE)
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
                .jsonPath("$.message").isEqualTo("Access denied");
    }

    @Test
    void adminCanReadReport() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }

    @Test
    void denyAllRejectsEvenAdmin() {
        client.get().uri("/closed/feature")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectBody()
                .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void unlistedRouteIsNotAutomaticallyPublic() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Run with:

~~~bash
gradle test
~~~

**Expected result:** 9 tests PASS, Gradle exits with **BUILD SUCCESSFUL** if the environment and dependencies are configured properly. Tests use RANDOM_PORT and WebTestClient auto-configured by Spring Boot, so there is no need to run the demo server manually on port 8080.

### 9.1. Three Most Important Assertions

1. **401 missing credentials** must carry WWW-Authenticate; do not test status alone.
2. **401 wrong credentials** must match the missing-credentials error in the public contract, without revealing whether the username exists.
3. **403 insufficient permissions** must happen when Authentication has already succeeded; do not replace it with 401 and do not return admin data.

Add tests for method security, CSRF, owner checks, gateway, and multi-chain if your real product has them; the demo only checks URL authorization.

### 9.2. Tests Must Not Bypass Auth Filters

Wrong way:

~~~java
// Conceptual illustration: calling the controller directly bypasses WebFilter.
ApiController controller = new ApiController();
controller.report().subscribe();
~~~

This snippet does not test the `/api/admin/report` policy, and manual `subscribe()` is unsuitable for unit-testing HTTP responses. If you need to test a Reactor publisher standalone, use **StepVerifier**; if you need to test 401/403, use **WebTestClient** through SecurityWebFilterChain.

### 9.3. Must Test Both Subjects and Different States

In a multi-role project, test at least unauthenticated user, wrong credentials, ROLE_USER, and ROLE_ADMIN. Testing an endpoint only with admin succeeding **does not prove** ROLE_USER will be blocked. Similarly, testing an endpoint only without cookies without testing a valid cookie lacking permissions may fail to distinguish 401 from 403.

## 10. Special Situations Easily Confused

### 10.1. 403 Caused by CSRF, Not Missing Role

In web apps using cookies/sessions, CSRF protection usually applies to unsafe methods such as POST, PUT, PATCH, DELETE. If POST /api/orders lacks a CSRF token, the WebFilter may reject with **403 even when Authentication and role are valid**.

Therefore, when debugging:

- Check the HTTP method and whether CSRF is enabled.
- Check whether the request has the right type of CSRF token (form field/header) and corresponding cookie/session.
- When testing roles on POST, satisfy CSRF as well or configure CSRF according to the appropriate architecture.
- Never disable CSRF system-wide just to make authorization tests pass.

Example matrix:

| Request | Credentials | CSRF | Role | Possible result |
| --- | --- | --- | --- | --- |
| POST /orders | Valid | Missing | Valid | 403 due to CSRF |
| POST /orders | Valid | Valid | Missing | 403 due to authorization |
| POST /orders | Valid | Valid | Valid | 2xx per business logic |
| POST /orders | Missing | Missing | Unknown | May be rejected by CSRF before authn |

Do not infer the cause from status alone; safe logs/metrics and single-variable tests help identify which filter returned the error.

### 10.2. CORS Preflight and Browsers

An OPTIONS preflight request may not carry credentials. If CORS configuration is missing or filter order is wrong, the request may be blocked with 401/403 and the frontend shows "CORS error". This is not necessarily a missing user role.

The solution is to configure CORS for trusted origins, methods, allowed headers, and appropriate credential policy; process preflight in the right order without exposing sensitive data publicly just to let OPTIONS pass. Compare `curl` with browser Network tab to separate CORS errors from authentication errors.

### 10.3. Form Login Redirect Differs from REST HTTP Status

Form login can return 302 to /login when the caller is unauthenticated, while HTTP Basic/Bearer APIs usually return 401. Do not use default REST tests to force 401 on browser web pages unless you change the entry point.

A hybrid application can separate SecurityWebFilterChains by matcher; test `/api/**` and `/web/**` behavior separately. Do not unintentionally attach a Basic challenge to an HTML form login flow.

### 10.4. 401 Does Not Always Mean Refresh the Token

A client should refresh an access token only when the authentication mechanism and error contract indicate an expired/refreshable token error. For a wrong Basic password, calling refresh infinitely is wrong. For Bearer insufficient_scope (403), refreshing with the same scope usually does not resolve insufficient permissions.

Limit retry attempts, avoid login/refresh loops, and distinguish 5xx system errors from 401 invalid credentials.

### 10.5. 404 and 405 Can Be Blocked Early by Security

A request to a URL with no handler but covered by `anyExchange().denyAll()` can receive 401/403 before DispatcherHandler even knows the URL does not exist. Thus status 403 does not prove the controller/service ran, and status 404 does not prove the URL has the right policy.

When testing security, use **endpoints that actually exist**, with multiple identities; testing an unknown path is a separate fail-closed test.

### 10.6. DenyAll and Unauthenticated Users

The **denyAll()** rule denies both unauthenticated users and admins. However, exception translation may return 401 to unauthenticated callers and 403 to logged-in users. Do not treat "denyAll always returns 403" as an invariant law.

### 10.7. Object-Level Permissions

For example, Alice requests GET /api/orders/42, but order 42 belongs to Bob. Depending on policy, the service may return **403** or **404 to hide existence**. Regardless of status, never return Bob's data to Alice.

Illustrative pattern:

~~~java
// Integration illustration; OrderDto/repository are provided by the application.
public Mono<OrderDto> getOrder(String orderId, String verifiedUserId) {
    return repository.findByIdAndOwnerId(orderId, verifiedUserId);
}
~~~

`verifiedUserId` must come from the verified Authentication/subject. Never read a username from a query parameter and trust that the client owns the resource.

### 10.8. Authentication Errors Caused by Infrastructure

If the identity database times out, the manager does not know whether the password is right or wrong because it cannot retrieve the account. Do not turn every internal error into 401; that makes clients retry passwords and hides operational incidents. Fail closed and return an appropriate 5xx/503 per contract while recording controlled internal metrics.

## 11. Checklist for Implementing a Real API

**Designing statuses and challenges:**

1. Write an endpoint matrix: public, authenticated, role/scope, owner/tenant.
2. Choose an explicit authentication mechanism: Basic, cookie form login, JWT/Bearer, mTLS, or another mechanism.
3. When returning 401, provide a scheme-appropriate **WWW-Authenticate** (RFC 9110).
4. With Basic, realm is a server-controlled static string; with Bearer, keep error semantics compliant with RFC 6750.
5. Return 403 for authenticated callers lacking permissions per policy.
6. Do not turn every exception into 401/403; let system errors and validation have appropriate statuses.
7. Do not cache security-related errors if the contract contains sensitive info.
8. Never output tokens/passwords/hashes/stack traces in JSON or logs.
9. Verify URL rules ordered specific before broad; end with deny-by-default where appropriate.
10. Keep method security and owner/tenant checks independent of URL-level statuses.
11. When using multiple chains, verify securityMatcher/@Order, entry point, and the corresponding authentication scheme.
12. With browsers/cookies, test CSRF and CORS; with stateless APIs, evaluate against a real threat model.
13. Test missing credentials, wrong credentials, valid credentials lacking permissions, sufficient permissions, and unlisted paths.
14. Test behavior through gateways/proxies if proxies have their own rewrites/auth/filters.

**Monitoring:**

- Record endpoint template, category such as AUTHN_FAILURE/AUTHZ_DENIED/CSRF_DENIED, status code, and correlation ID if present.
- Only log verified actor/subject when appropriate; never log raw Authorization headers or full principals.
- Rate-limit login/password attempts and monitor anomalies without returning differences useful for user enumeration.
- For 401/403 rate spikes, slice by client type, scheme, and URL before concluding users are mistyping passwords.

## 12. Practice Exercises

1. Which status does GET /api/me without Authorization Basic receive, and which header is required?
2. Is sending a wrong password to GET /api/me considered "logged in but lacking permissions"?
3. When Alice (ROLE_USER) calls GET /api/admin/report, is it 401 or 403 in the demo? Why?
4. Admin calls /closed/feature under denyAll; which status is expected in the demo?
5. If Admin's POST /api/orders returns 403 when CSRF is enabled, can you conclude Admin lacks ROLE_ORDER_WRITE?
6. With browser form login, why can an unauthenticated request return 302 instead of 401?
7. How do an expired Bearer token and a valid Bearer token lacking scope differ?
8. Is WWW-Authenticate required on 401 per RFC 9110? Should a Basic challenge be used for a Bearer API?
9. When only modifying ServerAccessDeniedHandler, why might the wrong-password branch still use the default error body?
10. Why doesn't @RestControllerAdvice always catch AuthenticationException inside SecurityWebFilterChain?
11. When a route does not exist under a denyAll policy, does 403 prove the handler ran?
12. What test should be added to detect a non-existent Basic username leaking in the message?
13. Why does returning 200 with {"error":true} not replace 401/403?
14. For a resource owned by Bob, can a logged-in Alice read it if the URL only has authenticated()?
15. Should an identity store timeout error return 401 by default?

**Suggested answers:** (1) 401 and WWW-Authenticate: Basic realm; (2) no, authentication is not yet valid; (3) 403 because logged in but lacking ROLE_ADMIN; (4) 403 since admin is authenticated; (5) no, CSRF may have blocked it first; (6) form login's entry point redirects; (7) invalid_token is usually 401, insufficient_scope is usually 403; (8) an appropriate challenge is required, do not use the wrong scheme; (9) wrong credentials are handled in the authentication filter/entry point rather than necessarily the denied handler; (10) security filters run before the controller; (11) no; (12) compare public code/message of unknown username vs wrong password; (13) breaks HTTP semantics, clients/proxies/observability; (14) not automatically, must check owner; (15) no, infrastructure errors need 5xx/503 handling and fail closed.

## 13. References

- RFC 9110 — HTTP Semantics, 401 Unauthorized and 403 Forbidden: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 7617 — The Basic HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- Spring Security Javadoc — ServerHttpSecurity.HttpBasicSpec: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security Javadoc — ServerHttpSecurity.ExceptionHandlingSpec: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security Javadoc — ServerAuthenticationEntryPoint: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- Spring Security Javadoc — ServerAccessDeniedHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Boot 3.5.16 Release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Conclusion:** In Spring Security Reactive, **401** usually occurs when a request lacks or has invalid credentials and needs a scheme-accurate **authentication challenge**; **403** usually occurs when the caller is authenticated but rejected by **authorization**. Do not judge solely by the names Unauthorized/Forbidden: inspect filters, authentication mechanisms, URL rules, roles/scopes, CSRF/CORS, and resource-level permissions. Use **ServerAuthenticationEntryPoint** for 401, **ServerAccessDeniedHandler** for 403, return safe JSON, and test both flows with WebTestClient.