# Customizing HTTP Basic Error Responses for REST APIs in Spring Security Reactive

## 1. Goal and scenario

A REST API using **HTTP Basic Authentication** usually needs a stable, structured response so frontends, mobile apps, or integrating systems can handle errors programmatically. If a request lacks a username/password, sends wrong credentials, or is logged in without sufficient permissions, returning an empty HTTP status, an HTML page, or internal error text makes it hard for clients to tell causes apart and risks leaking sensitive details.

This lesson explains how to **customize HTTP Basic errors in Spring Security WebFlux (reactive)** while protecting data and honoring HTTP semantics:

1. Distinguish **401 Unauthorized** and **403 Forbidden** in the authentication/authorization flow.
2. Understand the role of **WWW-Authenticate: Basic realm="..."** in 401 responses.
3. Distinguish **ServerAuthenticationEntryPoint**, **ServerAccessDeniedHandler**, **ServerAuthenticationFailureHandler**, and controller exception handlers.
4. Configure a stable JSON error body, proper Content-Type, cache-prevention policy, and safe messages.
5. Handle both **missing credentials** and **wrong credentials**, avoiding customizing only half the flow.
6. Build a Java 17+ demo with Spring Boot 3.3.5, WebFlux, BCrypt, and HTTP Basic; observe with curl and WebTestClient.
7. Recognize common mistakes: using Servlet APIs instead of reactive APIs, returning 403 for wrong credentials, forgetting the challenge header, or returning stack traces/leaking passwords in JSON.

**End goal:** clients receive clear structured errors without gaining extra privileges or seeing sensitive information just because error presentation changed.

## 2. How do 401 and 403 differ?

| Scenario | Authentication | Authorization | Expected HTTP |
| --- | --- | --- | --- |
| No Authorization header on login-required endpoint | No valid authenticated identity yet | Endpoint requires authenticated | **401** |
| Authorization Basic with wrong username/password | Authentication failed | No valid identity to proceed | **401** |
| Authenticated user lacking ROLE_ADMIN | Succeeded | Permission denied | **403** |
| Authenticated user with sufficient permissions | Succeeded | Allowed | **200** or another business status |
| Backend identity provider/database unavailable | Cannot verify due to technical outage | Must not grant permissions | Appropriate **5xx**, do not default to 401 |
| Non-existent URL after passing security policy | May be authenticated | Application-defined policy | **404**, do not turn every 404 into a login error |

The HTTP name **401 Unauthorized** can be misleading: in practice it means **missing or lacking valid authentication proof**. **403 Forbidden** means the caller is not permitted to perform the action, typically an authenticated caller lacking sufficient authority.

A simple JSON contract:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="reactive-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

For a logged-in user lacking permissions:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

**Note:** 403 **does not need** a Basic challenge in standard handling. Sending a challenge on every 403 misleads clients into thinking changing passwords can grant permissions the policy has not assigned.

JSON should carry a stable **machine-readable error code** (`code`), while `message` is a safe human explanation. System-controlled fields like `requestId`, `timestamp`, or `details` can be added, but never arbitrarily echo the `Authorization` header or exception text.

## 3. Why does 401 require WWW-Authenticate?

HTTP Basic works via a challenge-response mechanism. When the server requires authentication, **401 must include at least one challenge in WWW-Authenticate** per HTTP Semantics. For the Basic scheme, the challenge carries a **realm** per RFC 7617. Example:

~~~text
WWW-Authenticate: Basic realm="reactive-api"
~~~

- **Basic** tells the client this uses the Basic username/password scheme.
- **realm** identifies the protection space for which the server requests credentials.
- Realm should be a static, system-controlled string; never derive it from client-supplied URL parameters or headers.
- **Authorization: Basic ...** from the client contains Base64 of `username:password`, **not security encryption**. HTTPS/TLS is required.

Many HTTP clients rely on the challenge to decide whether to resend credentials. Some browsers may display an HTTP Basic dialog upon seeing `WWW-Authenticate`. Dropping the header just to suppress popups trades away compatibility with HTTP Basic/HTTP 401. If you want custom UI login without relying on Basic challenges, consider an **appropriate authentication mechanism** instead of silently breaking the Basic contract.

In the demo, the 401 response **keeps the challenge** and changes the body to JSON. This is friendly to API clients while staying compliant with standards. Differences in browser dialog behavior are client characteristics, not a bug in JSON formatting.

## 4. WebFlux security flow and extension points

In Spring Security **Reactive**, requests pass through **SecurityWebFilterChain**. Conceptual model:

~~~text
Request GET /api/me
        |
        v
WebFlux SecurityWebFilterChain
        |
        +-- HTTP Basic AuthenticationWebFilter
        |       |
        |       +-- Valid Basic header?
        |       |       |
        |       |       +-- yes: ReactiveAuthenticationManager verifies
        |       |       |       |
        |       |       |       +-- invalid -> authentication failure
        |       |       |       +-- valid -> SecurityContext / chain continues
        |       |       |
        |       |       +-- no Basic -> skip attempt in this filter
        |       |
        v
AuthorizationWebFilter / exception translation
        |
        +-- Unauthenticated yet endpoint needs login -> entry point (401)
        |
        +-- Authenticated yet missing permission -> access denied handler (403)
        |
        +-- Permitted -> controller/service
~~~

The diagram simplifies internal ordering and does not guarantee all errors are handled by a single handler. For customization, understand these contracts:

| Reactive extension point | Interface/class | When used |
| --- | --- | --- |
| Start authentication request / missing valid credentials | **ServerAuthenticationEntryPoint** | Writes status 401, WWW-Authenticate, and JSON |
| User authenticated but insufficient permissions | **ServerAccessDeniedHandler** | Writes status 403 and JSON |
| A specific authentication attempt failed | **ServerAuthenticationFailureHandler** | Handles failures inside AuthenticationWebFilter; often delegates to entry point |
| Configure authorization error handling | **ServerHttpSecurity.exceptionHandling(...)** | Registers entry point / denied handler |
| Configure HTTP Basic error handling | **ServerHttpSecurity.httpBasic(...)** | Sets entry point / failure handler for Basic |
| Business code in controllers | **@RestControllerAdvice** / WebFlux exception handlers | Handles business errors post-routing; does not replace all security filter errors |

**Why configure in two places?** When credentials are missing, authorization checks can delegate to **exceptionHandling**'s entry point. When wrong Basic credentials are sent, the authentication filter itself can handle failure via **httpBasic**'s entry point/failure handler. Customizing only one of the two can produce inconsistent JSON results.

This lesson uses **the same ServerAuthenticationEntryPoint** for both flows, and **a separate ServerAccessDeniedHandler** for 403.

### 4.1. Which APIs are servlet, and which are reactive?

| Do not use directly for WebFlux | Correct reactive type |
| --- | --- |
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| AuthenticationEntryPoint with HttpServletRequest/HttpServletResponse | ServerAuthenticationEntryPoint with ServerWebExchange |
| Servlet AccessDeniedHandler | ServerAccessDeniedHandler |
| OncePerRequestFilter | WebFilter / AuthenticationWebFilter |

Examples using **jakarta.servlet.http.HttpServletResponse** belong to the Servlet stack and will not plug directly into an app using only `spring-boot-starter-webflux`. When searching online guides, always verify package names and method signatures.

## 5. Designing a JSON error contract for the API

The example chooses a minimal structure:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Authentication required"
}
~~~

and:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Access denied"
}
~~~

Quality requirements:

- **Status must be accurate**: 401 for authentication, 403 for authorization, 5xx for internal errors unable to verify due to infrastructure failure.
- **Content-Type**: `application/json`; body bytes encoded in UTF-8.
- **Challenge header**: include `WWW-Authenticate` with Basic realm on all corresponding 401 branches.
- **No caching**: `Cache-Control: no-store` to limit storing responses tied to authentication state.
- **No leaks**: never put username existence, raw passwords, Basic headers, tokens, stack traces, error class names, or DB query contents into JSON.
- **Stable contract**: clients inspect `code` rather than parsing localized/changing `message` text.
- **Proper enforcement**: returning an error must never allow the pipeline to continue serving the protected resource.

If you want to use **application/problem+json (RFC 9457)**, follow the full Problem Details structure (`type`, `title`, `status`, `detail`, `instance`) and matching content type rather than just swapping the header on a custom schema. This demo uses `application/json` to keep focus on HTTP Basic security.

Never return errors with status 200 and body `{"success":false}`. That hides HTTP outcomes from clients, proxies, metrics, and retry policies.

## 6. Two 401 errors: missing credentials and invalid credentials

**Missing Authorization header:** HTTP Basic's `AuthenticationWebFilter` cannot build an authentication proposal from a Basic header. When the request reaches an endpoint requiring `authenticated`, authorization requests authentication via the entry point.

**Wrong username/password:** the converter reads the Basic credentials and the manager fails verification. The authentication filter routes the error to its failure handling, using the configured entry point.

On the client side, both can receive the exact same JSON:

~~~json
{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

Do not publicly disclose "valid username, wrong password" versus "account does not exist". Any detailed breakdown needed belongs in sanitized server logs/metrics, paired with anti-enumeration and rate limiting.

**Do not blindly catch every AuthenticationException and return 401**: some subtypes indicate authentication service outages, such as `AuthenticationServiceException`. In Spring Security, default handlers can propagate technical errors instead of turning them into a Basic challenge; when writing a custom failure handler, preserve this distinction and map to an appropriate 5xx. The demo does not simulate identity system outages.

## 7. Complete Java 17+ demo: Spring Boot WebFlux returning 401/403 JSON

The example uses **Spring Boot 3.3.5**, **Java 17+**, Gradle 8.x, **spring-boot-starter-webflux**, and **spring-boot-starter-security**. Two test users:

| User | Demo password | Authority |
| --- | --- | --- |
| reader | reader-pass | ROLE_USER |
| admin | admin-pass | ROLE_USER, ROLE_ADMIN |

API:

- GET **/public/ping**: public.
- GET **/api/me**: requires login.
- GET **/api/admin/report**: requires ROLE_ADMIN.

File structure:

~~~text
basic-json-errors/
├── settings.gradle
├── build.gradle
├── src/main/java/example/basic/BasicJsonErrorsApplication.java
├── src/main/java/example/basic/SecurityConfig.java
├── src/main/java/example/basic/ApiController.java
└── src/test/java/example/basic/BasicErrorResponseTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'basic-json-errors'
~~~

### 7.2. build.gradle

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.3. BasicJsonErrorsApplication.java

~~~java
package example.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicJsonErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicJsonErrorsApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — core of the lesson

~~~java
package example.basic;

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
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    private static final String BASIC_CHALLENGE =
            "Basic realm=\"reactive-api\"";

    private static final String UNAUTHORIZED_JSON =
            "{\"code\":\"AUTHENTICATION_REQUIRED\","
                    + "\"message\":\"Authentication required\"}";

    private static final String FORBIDDEN_JSON =
            "{\"code\":\"ACCESS_DENIED\","
                    + "\"message\":\"Access denied\"}";

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

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ServerAuthenticationEntryPoint restAuthenticationEntryPoint() {
        return (exchange, authError) ->
                writeJsonError(exchange,
                        HttpStatus.UNAUTHORIZED,
                        UNAUTHORIZED_JSON,
                        true);
    }

    @Bean
    ServerAccessDeniedHandler restAccessDeniedHandler() {
        return (exchange, deniedError) ->
                writeJsonError(exchange,
                        HttpStatus.FORBIDDEN,
                        FORBIDDEN_JSON,
                        false);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerAuthenticationEntryPoint restAuthenticationEntryPoint,
            ServerAccessDeniedHandler restAccessDeniedHandler) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(basic ->
                        basic.authenticationEntryPoint(
                                restAuthenticationEntryPoint))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                restAuthenticationEntryPoint)
                        .accessDeniedHandler(
                                restAccessDeniedHandler))
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    private static Mono<Void> writeJsonError(
            ServerWebExchange exchange,
            HttpStatus status,
            String json,
            boolean includeBasicChallenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);

        HttpHeaders headers = response.getHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (includeBasicChallenge) {
            headers.set(
                    HttpHeaders.WWW_AUTHENTICATE,
                    BASIC_CHALLENGE);
        }

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        headers.setContentLength(bytes.length);
        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
~~~

**Key points in the code:**

1. **restAuthenticationEntryPoint** returns 401 with fixed JSON and a Basic challenge. Never use raw exception messages as the body.
2. **restAccessDeniedHandler** returns 403 with different JSON; never add a challenge when the user is authenticated yet lacks permissions.
3. **httpBasic(basic -> basic.authenticationEntryPoint(...))** handles HTTP Basic branches, including authentication attempt failures.
4. **exceptionHandling(errors -> errors.authenticationEntryPoint(...))** handles authorization requiring login when a request lacks valid credentials.
5. **exceptionHandling(...accessDeniedHandler(...))** handles missing permissions (403).
6. **writeJsonError** uses reactive `ServerHttpResponse` and `Mono<Void>`, never calling `block()` or using `HttpServletResponse`.
7. **ROLE_ADMIN** is checked before the broad `/api/**` rule, preventing accidental access just because the caller logged in.
8. Responses set JSON and `no-store`, writing only predefined system byte payloads. When schemas are dynamic, use a safe serializer like Jackson to escape data rather than concatenating strings from input.

To keep the code easy to follow, both accounts and passwords are in source code. They are **for localhost/demo only**; production needs an identity store/IdP and secrets management, never committed real passwords.

### 7.5. ApiController.java

~~~java
package example.basic;

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
        return principal.map(user ->
                Map.of("username", user.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

The controller does not verify passwords itself. If permissions are insufficient, the request is blocked by a WebFilter before reaching the handler. **Mono<Principal>** provided by WebFlux reflects the identity resolved in the request's security chain.

### 7.6. Starting and testing with curl

From the **basic-json-errors** directory, using JDK 17+ and Gradle 8.x compatible with Spring Boot 3.3.5:

~~~bash
gradle bootRun
~~~

In another terminal:

~~~bash
# 1. Public URL: 200
curl -i http://localhost:8080/public/ping

# 2. Missing Basic credentials: 401 + JSON + WWW-Authenticate
curl -i http://localhost:8080/api/me

# 3. Wrong password: 401 + same JSON and challenge
curl -i -u reader:wrong-pass http://localhost:8080/api/me

# 4. Valid reader login: 200
curl -i -u reader:reader-pass http://localhost:8080/api/me

# 5. Reader missing ROLE_ADMIN: 403 + JSON, no challenge needed
curl -i -u reader:reader-pass http://localhost:8080/api/admin/report

# 6. Admin with sufficient permissions: 200
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report
~~~

**Key parts of expected outputs**, omitting container/server-added headers like `Date` or `Transfer-Encoding`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok"}
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="reactive-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"username":"reader"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"report":"ok"}
~~~

These are **expected values from the demo configuration**, not a capture from a live server. On PowerShell you can use **curl.exe**; commands in the lesson target Bash/curl and pass `-i` to display status/headers/body. Exact HTTP outcomes also depend on other deployed components like reverse proxies, CORS, error handlers, or other `SecurityWebFilterChain`s.

## 8. Automated testing with WebTestClient

You must test **both 401 branches** and the **403 branch**. If you only test wrong passwords and forget requests without an Authorization header, you might accidentally configure JSON for one branch and get a different response on the other.

### 8.1. BasicErrorResponseTest.java

~~~java
package example.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BasicErrorResponseTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequireLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingCredentialsProduceJson401AndBasicChallenge() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"reactive-api\"")
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
    void wrongPasswordUsesTheSameSafeJson401() {
        client.get().uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"reactive-api\"")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void validUserCanReadOwnIdentity() {
        client.get().uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void authenticatedUserWithoutRoleGetsJson403() {
        client.get().uri("/api/admin/report")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.WWW_AUTHENTICATE)
                .expectBody()
                .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
                .jsonPath("$.message").isEqualTo("Access denied");
    }

    @Test
    void adminCanReadReport() {
        client.get().uri("/api/admin/report")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** six tests PASS; Gradle finishes with BUILD SUCCESSFUL if the project is imported properly and dependencies resolve. The test boots a WebFlux application context and sends requests to a random port, without needing the demo server running separately on 8080.

### 8.2. A test matrix to have in real products

| Request | Expected |
| --- | --- |
| GET public without Authorization | 200, business response |
| GET protected without Authorization | 401, JSON code, Basic WWW-Authenticate |
| GET protected Basic wrong password | 401, same JSON shape, does not disclose whether user exists |
| GET protected Basic non-existent username | 401, public body has no useful difference for user enumeration |
| GET protected valid Basic | 200, data per permissions |
| GET admin with ROLE_USER | 403, ACCESS_DENIED JSON, no challenge |
| GET admin with ROLE_ADMIN | 200 |
| Malformed/invalid Basic header | Cannot access resource; error behavior verified per configured converter |
| Identity store outage/timeout | Does not return 200 or spoof login; mapped to appropriate infrastructure error |
| Requests with methods other than GET | Check 405/CSRF/authorization properly; do not lump all errors into 401 |

**Malformed header cases** can differ in detail depending on the converter and filters, so test actual requests rather than assuming any arbitrary Authorization string is treated as a wrong password. If multiple `SecurityWebFilterChain`s exist, verify which chain matches the tested endpoints.

## 9. Other customization paths and limits

### 9.1. Using a dedicated ServerAuthenticationFailureHandler

In WebFlux, **ServerAuthenticationFailureHandler** has the conceptual signature:

~~~java
Mono<Void> onAuthenticationFailure(
        WebFilterExchange filterExchange,
        AuthenticationException exception);
~~~

It handles failures of an **authentication attempt in AuthenticationWebFilter**. If you only want to change wrong-password handling for one authentication mechanism, this is the right extension point. However, endpoints without submitted credentials blocked by authorization may go through exception translation's entry point. Thus customizing the failure handler **does not completely replace** `ServerAuthenticationEntryPoint`.

**ServerAuthenticationEntryPointFailureHandler** is an adapter placing a `ServerAuthenticationEntryPoint` in the failure handler slot. The adapter can be configured to **rethrow AuthenticationServiceException** rather than treating infrastructure outages as invalid credentials. Do not arbitrarily replace this mechanism with a handler that always returns 401; it hides identity service failures and skews metrics.

### 9.2. Is @RestControllerAdvice enough?

**Not enough for all authentication/authorization.** Errors occurring in WebFilters generally happen before controllers are invoked, so `@ExceptionHandler` inside `@RestControllerAdvice` will likely not see errors already handled by entry points/failure handlers/denied handlers.

Assign responsibilities properly:

- **SecurityWebFilterChain**: authentication and URL authorization.
- **ServerAuthenticationEntryPoint**: response when authentication is required.
- **ServerAccessDeniedHandler**: response when access is denied.
- **@RestControllerAdvice**: business errors, validation, and domain exceptions in controllers/services.
- **Gateway/reverse proxy**: rate limits, TLS, and proxy-specific errors; do not assume every gateway error came from Spring Security.

An API can share the same JSON schema across these layers, yet each layer requires its own configuration/mapper.

### 9.3. Should WWW-Authenticate be replaced with JSON-only?

If still using Basic, the answer is usually **no**. Per HTTP semantics, 401 must carry a challenge; the Basic RFC requires `realm`. Removing the header may curb popups in some browsers but breaks compatibility with standard Basic clients. If the app is a browser SPA and you do not want the browser managing Basic credentials, consider session cookies with proper CSRF, OAuth2/OIDC, or bearer tokens over an API aligned with your architecture.

### 9.4. When an API has multiple authentication mechanisms

An API might use bearer tokens for `/api/**` and Basic for `/admin/**`, or have multiple `SecurityWebFilterChain`s. In that case:

- Define **securityMatcher** and chain ordering explicitly.
- Each chain needs entry points/challenges matching the scheme it supports.
- Never return a Basic challenge on an endpoint that only accepts Bearer.
- Never apply a JSON-returning handler to every chain if the app still has browser login pages needing redirects.
- Test public URLs, Basic URLs, and Bearer URLs independently.

Do not leave HTTP Basic enabled everywhere by inertia when security requires another scheme.

### 9.5. Warning about already-committed Responses

In HTTP streaming, if a controller has started emitting content bytes, status/headers may already be committed. An error occurring **after streaming begins** cannot always be rewritten into a clean 401/403 JSON response. Therefore, verify authentication/authorization **before emitting sensitive data**, and enforce per-object permissions for complex streams.

## 10. Security when handling HTTP Basic errors

| Risk | Safe action |
| --- | --- |
| Leaking username existence | Return identical public messages for non-existent user / wrong password |
| Leaking raw Authorization or passwords | Never log headers/credentials; mask in observability |
| Returning stack traces/causes in JSON | Use fixed code/message; filter internal logs |
| Returning 200 on authentication failure | Keep status 401 and WWW-Authenticate |
| Returning 403 for wrong password | Use 401 when valid authentication proof is absent |
| Returning 401 for users missing ROLE_ADMIN | Use 403 to reflect logged-in yet denied |
| Treating identity provider failures as allowed | Fail closed; return safe technical error and alert |
| Removing WWW-Authenticate just to stop browser popups | Consider switching authentication schemes if needed |
| Caching responses carrying security context | `Cache-Control: no-store` |
| Concatenating JSON strings from unescaped input | Use a standard JSON serializer |
| Basic credentials traversing non-TLS HTTP | HTTPS/TLS; restrict password logins over weak channels |
| Misconfigured password hashing | Use proper PasswordEncoder, BCrypt/DelegatingPasswordEncoder per policy |
| Brute-forcing Basic logins | Rate limiting, failure monitoring, appropriate lockouts/challenges |
| Trusting admin roles sent by client headers | Load GrantedAuthority from trusted server sources |
| Mechanically disabling CSRF | Evaluate browser credentials, cookies, and actual mutating methods |

**CSRF:** Basic is a scheme where browsers can automatically resend credentials in an authenticated context; for state-changing browser requests, you cannot assume CSRF is harmless. The demo only has GET endpoints, keeping the default security config. If implementing POST/PUT/PATCH/DELETE, design CSRF based on the real client model instead of blindly copying `disable()`.

**CORS:** CORS is a browser policy, not authentication. Preflight `OPTIONS` requests may omit credentials. If browser clients call the API cross-origin, configure CORS and WebFilter ordering properly so preflight isn't blocked for lacking Basic credentials, while restricting allowed origins/methods/headers as required.

**Logging:** you may log result category, endpoint template, correlation/request ID, and processing duration; avoid raw `Authorization`, passwords, `Cookie`, and exception details containing secrets. Do not return the same audit ID for every request; if a request ID is included in JSON, generate/sanitize it server-side.

## 11. Debugging when still getting HTML or empty bodies

If the code is customized yet clients still receive empty bodies or HTML, check:

1. **Right stack?** Are you using `ServerHttpSecurity` and `SecurityWebFilterChain`, not `HttpSecurity`/servlet?
2. **Right chain running?** With multiple chains, matchers/priorities might select another configuration.
3. **Configured both `httpBasic` and `exceptionHandling`?** Wrong-credential and missing-credential branches may use different handlers.
4. **Is `formLogin` enabled?** If form login remains active on that path, responses may redirect to a login page.
5. **Response already committed?** An earlier WebFilter/controller might have written bytes or status.
6. **Does the handler return `Mono<Void>` subscribed by the pipeline?** Never manually call `subscribe()` or `block()` to write responses.
7. **Do JSON payload and Content-Type match?** An `application/json` header with an HTML body is inconsistent.
8. **Is another exception handler/proxy overriding it?** Test directly against the app with `WebTestClient`, then compare through the gateway.
9. **How were credentials malformed?** A malformed Basic header can follow a different converter path than a wrong password.
10. **Is there an `AuthenticationServiceException` or user store connection error?** Avoid turning infrastructure failures into invalid credentials.
11. **Does `WWW-Authenticate` have the right scheme and realm?** Inspect response headers, not just the JSON body.
12. **Are CORS or CSRF policies affecting it?** Especially with browsers and mutating HTTP methods.

Use `curl -i` to observe full headers and bodies. Use `WebTestClient` to lock down behavior, since looking only at frontend messages can confuse frontend errors with security chain responses.

## 12. Practice exercises

1. Change the realm in `SecurityConfig` to another static string and verify `WWW-Authenticate` on both missing-credential and wrong-password requests.
2. Extend the 401 response body with a system-generated `requestId` field; ensure the `Authorization` header is never echoed.
3. Add a user with role `REVIEWER` and an `/api/reviews/**` endpoint requiring only `REVIEWER`. Distinguish 401/403 responses.
4. Write a `WebTestClient` test for a non-existent username and compare its public error code with a wrong-password error.
5. Temporarily remove `.httpBasic(basic -> basic.authenticationEntryPoint(...))`, observe which branch stops returning expected JSON, then restore it.
6. Temporarily remove `exceptionHandling().authenticationEntryPoint(...)`, observe a credential-less request, then restore it.
7. Replace the body with a Problem Details schema using `application/problem+json` and update tests accordingly.
8. Simulate a `ReactiveAuthenticationManager` reporting an infrastructure error; write a check ensuring the response cannot be 200 or grant access.
9. Explain why returning 200 with `{"error":"invalid"}` breaks clients, tracing, and monitoring.
10. Explain why `WWW-Authenticate` must be kept for Basic even though some browsers may show a dialog.

**Answer hints:**

- (1) Basic realm is a challenge parameter, not a username or password.
- (2) `requestId` belongs to server-controlled data and must be safely encoded.
- (3) 401 when lacking valid credentials; 403 when authenticated yet missing a role.
- (4) Use a generic message to mitigate user enumeration.
- (5) The failure branch in HTTP Basic may fall back to the default entry point.
- (6) The authorization branch detecting anonymous callers may fall back to a different entry point.
- (7) Both `Content-Type` and JSON contents must conform to the schema's RFC.
- (8) Technical errors must fail closed, logged and mapped to an appropriate 5xx.
- (9) Status 200 hides failures from HTTP semantics.
- (10) Basic uses a standardized challenge-response mechanism.

## 13. References

- Spring Security Javadoc — ServerHttpSecurity.HttpBasicSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security Javadoc — ServerHttpSecurity.ExceptionHandlingSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security Javadoc — ServerAuthenticationEntryPointFailureHandler: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- RFC 7617 — The Basic HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 9110 — HTTP Semantics (401/403 and WWW-Authenticate): https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html

**Conclusion:** To customize HTTP Basic errors for a WebFlux REST API, use **ServerAuthenticationEntryPoint** for 401 and **ServerAccessDeniedHandler** for 403, configure both **httpBasic** and **exceptionHandling** consistently, preserve **WWW-Authenticate: Basic realm="..."** on 401, and return JSON with a stable schema that never leaks secrets. Separately test missing credentials, wrong credentials, missing permissions, and technical failures; changing presentation must never alter authentication and authorization principles.