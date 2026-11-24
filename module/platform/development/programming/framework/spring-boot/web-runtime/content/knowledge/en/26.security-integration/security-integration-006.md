# Security Error Handling Before the Controller and the Limits of ControllerAdvice

## 1. The Problem: Why Do 401/403 Responses Still Lack Expected JSON Despite RestControllerAdvice?

You are building a Spring Boot API and write a `@RestControllerAdvice` to standardize error bodies. When a controller throws `IllegalArgumentException`, the response may return uniform JSON. However, calling a login-protected endpoint without credentials still returns 401 with `WWW-Authenticate`; an authenticated user missing a role receives 403; a POST missing a CSRF token gets blocked before any breakpoint inside the controller runs.

This is normal in **Security Integration**: Spring Security operates at the **Servlet Filter** or **WebFlux WebFilter** layer, before Spring MVC/WebFlux invokes controllers. **Not every HTTP exception goes through `@ControllerAdvice`.**

Distinguish between:
- **Authentication failure / challenge**: who is calling? Are credentials valid? Typically belongs to `AuthenticationEntryPoint`.
- **Authorization denial**: is the authenticated caller permitted to do this? Typically belongs to `AccessDeniedHandler`.
- **Controller/application exception**: invalid input, missing resource, business conflict. Typically belongs to `@ExceptionHandler`/`@RestControllerAdvice` or framework exception resolvers.
- **Errors from other layers**: CSRF/CORS filters, specific authentication mechanisms, reverse proxies, TLS handshakes, containers, gateways. Pinpoint the exact origin of the response.

**Lesson objectives:** explain the exact boundary between Security filters and MVC Advice; show how to return 401/403 with accurate semantics and schemas; provide a runnable Java 17+ demo with Spring Boot/Spring Security; cover exceptions such as method security, CSRF, Bearer tokens, WebFlux, and automated testing.

> **Practice versions:** Java 17+, Spring Boot **3.5.x**, Boot 3.5-managed Spring Security, and Spring MVC. Dependencies use `spring-boot-starter-web` and `spring-boot-starter-security`. For Spring Boot 4.x, the MVC starter is named `spring-boot-starter-webmvc`; cross-check APIs against Spring Security 7.x. Examples use HTTP Basic and GET routes for easy observation; production requires HTTPS and appropriate auth/CSRF policies.

## 2. Servlet Processing Flow: Filters Before DispatcherServlet

Conceptual diagram:

~~~text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty)
    |
    v
Servlet Filter chain
    |
    +-- DelegatingFilterProxy
    |      |
    |      v
    |   FilterChainProxy (Spring Security)
    |      |
    |      +-- SecurityFilterChain matching request
    |           +-- CORS/CSRF/authentication/... filters
    |           +-- ExceptionTranslationFilter
    |           +-- AuthorizationFilter
    |                      |
    +----------------------+-------------------------+
                                                   |
                                                   v
                                            DispatcherServlet
                                                   |
                                             HandlerMapping
                                                   |
                                           Controller / Service
                                                   |
                                           HandlerExceptionResolver
                                                   |
                                           @ExceptionHandler
                                           @ControllerAdvice
                                                   |
                                                   v
                                               HTTP response
~~~

This is **not** a fixed filter list: exact filter presence and order depend on Spring Security version and DSL configuration. What to remember is that `FilterChainProxy` can **short-circuit the request before `DispatcherServlet` is invoked**.

A Spring MVC `@RestControllerAdvice` is used by `ExceptionHandlerExceptionResolver` and MVC exception resolution when an exception occurs during dispatcher handling and matches an `@ExceptionHandler`. It does not automatically become a servlet filter catching everything.

### Case 1: Security Blocks at the Filter Layer

~~~text
GET /api/admin
   |
   v
SecurityFilterChain
   |
   +-- Authenticated user lacks ROLE_ADMIN
   |
   +-- AccessDeniedException / access denied handling
   |
   +-- HTTP 403
   |
   X  Does not call @GetMapping("/api/admin")
   X  Does not call @RestControllerAdvice because no MVC exception occurred
~~~

### Case 2: Request Passes Security, Fails in Controller

~~~text
GET /api/orders/123  (auth succeeds)
   |
   v
SecurityFilterChain allows through
   |
   v
DispatcherServlet -> OrderController
   |
   +-- throws ResourceNotFoundException
   |
   v
HandlerExceptionResolver -> @RestControllerAdvice
   |
   v
HTTP 404 + ProblemDetail
~~~

**Do not infer** from a JSON error body that the request reached a controller. Security handlers can also write JSON directly inside filters.

## 3. Comparing 401, 403, and Commonly Confused Errors

| Scenario | Layer Usually Deciding | Typical Outcome |
|---|---|---|
| No credentials on auth-required route | Security entry point | **401 Unauthorized**, with appropriate challenge |
| Wrong HTTP Basic password | Basic authentication filter/entry point | **401** |
| Invalid/expired OAuth2 Bearer token | Bearer authentication filter/entry point | **401**, appropriate `WWW-Authenticate: Bearer ...` |
| Authenticated user lacks role/scope | Authorization/Security AccessDeniedHandler | **403 Forbidden** |
| Missing/invalid CSRF token on protected request | CsrfFilter / corresponding handler | Usually **403**, before controller |
| Disallowed origin/preflight | CORS layer (filter/gateway/framework) | May be **403** or browser blocks reading response |
| Invalid JSON request after passing Security | MVC request conversion/validation | Usually **400**, can reach Advice |
| Business conflict | Controller/service | `409` if API defines it so |
| No matching handler | MVC/router/security/gateway per config | **404** or blocked earlier by security |
| Reverse proxy cannot reach upstream | Reverse proxy | `502/503`, Spring Advice is not involved |

Do not equate 401 with “missing role”: `401 Unauthorized` fundamentally means **authentication is required** (the historical name is misleading). `403 Forbidden` is for requests that are forbidden **even when identity is known**. For an anonymous user hitting an endpoint requiring `ROLE_ADMIN`, the same authorization rule can lead to 401 rather than 403.

### 401 Must Preserve the HTTP Authentication Challenge

HTTP Basic example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/problem+json

{"type":"about:blank","title":"Unauthorized","status":401}
~~~

If the server uses OAuth2 Bearer, `WWW-Authenticate` should be **Bearer** per RFC 6750, optionally including `realm`, `error`, or `scope` where appropriate. Never replace every entry point with a servlet JSON writer unaware of the authentication scheme; doing so can prevent API clients from properly handling tokens/challenges per standard.

## 4. ExceptionTranslationFilter: Very Specific Boundaries

In Spring Security Servlet, `ExceptionTranslationFilter` is a component inside `FilterChainProxy` that translates `AuthenticationException` and `AccessDeniedException` thrown downstream under its watch into HTTP actions.

Pseudo-flow:

~~~text
ExceptionTranslationFilter
  |
  +-- filterChain.doFilter(request, response)
        |
        +-- downstream authentication / authorization / app
  |
  +-- catch(AuthenticationException)
        -> AuthenticationEntryPoint
  |
  +-- catch(AccessDeniedException)
        |
        +-- anonymous/unauthenticated
        |      -> AuthenticationEntryPoint
        |
        +-- authenticated yet lacking permission
               -> AccessDeniedHandler
~~~

This is **illustrative logic**, not verbatim implementation code. `ExceptionTranslationFilter` does not catch every `Exception`. A regular business `IllegalArgumentException` is handled by MVC resolvers or propagates to general error handling—it is not mapped to 401/403 by this filter by default.

### Not Every Error Passes Through ExceptionTranslationFilter

Key points to master:
- `BasicAuthenticationFilter` may invoke its own entry point directly when credentials are invalid.
- `BearerTokenAuthenticationFilter` may have its own Resource Server entry point/handler.
- `CsrfFilter` may use its own access denied handler to terminate the request.
- Custom filters positioned **before** `ExceptionTranslationFilter` can write responses directly or throw exceptions outside its translation scope.
- Requests rejected by a CDN/gateway never even enter the application's `FilterChainProxy`.

Therefore `http.exceptionHandling(...authenticationEntryPoint(...).accessDeniedHandler(...))` is useful central configuration, yet **it does not guarantee every auth/CSRF error from every filter uses it automatically**. If all 401/403 responses must share a schema, identify each **actual error-producing component** and wire the shared error writer to them.

## 5. AuthenticationEntryPoint, AccessDeniedHandler, and ControllerAdvice

| Component | Package/stack | When Appropriate |
|---|---|---|
| `AuthenticationEntryPoint` | `org.springframework.security.web`, Servlet | Initiating/challenging authentication |
| `AccessDeniedHandler` | `org.springframework.security.web.access`, Servlet | Security authorization denial |
| `ExceptionTranslationFilter` | Servlet Security | Choosing entry point or denied handler for eligible downstream exceptions |
| `BasicAuthenticationFilter` | Servlet Security | Parsing/authenticating HTTP Basic credentials |
| `CsrfFilter` | Servlet Security | Enforcing CSRF on protected requests |
| `AuthorizationFilter` | Servlet Security | Request-level authorization |
| `@RestControllerAdvice` | Spring MVC (and annotated WebFlux has its own) | Errors thrown once controller/handler is dispatched |
| `HandlerExceptionResolver` | Spring MVC | Routing exceptions during MVC handling |
| `ServerAuthenticationEntryPoint` | WebFlux Security | Reactive equivalent of entry point |
| `ServerAccessDeniedHandler` | WebFlux Security | Reactive equivalent of denied handler |

Distinguish two duties:
- **Authentication**: are the identity/credentials valid?
- **Authorization**: is the identified caller allowed to call this endpoint/operation?

An API may share the **same body format** across 401, 403, and 400, yet must retain **semantically accurate status codes and headers**. Never turn all errors into 200 + `{"success":false}` or 500 just for frontend convenience.

## 6. The Exact Limits of @ControllerAdvice

The statement “`@ControllerAdvice` does not catch security exceptions” is often used as a reminder of the filter/controller boundary, yet needs precise phrasing:

**True:** `@RestControllerAdvice` does not automatically catch errors already handled and written by filters **before `DispatcherServlet`**. For example, request-level `AuthorizationFilter` blocks `/api/admin` before the controller.

**Also true:** if a security exception **arises inside a controller/service** after `DispatcherServlet` dispatches (such as method security `@PreAuthorize` on a service), it can pass through MVC `HandlerExceptionResolver`. In that case, an `@ExceptionHandler(AccessDeniedException.class)` can catch it **if resolved by MVC**.

**Cannot be inferred:** that all `AccessDeniedException` instances belong to Advice or all belong to `ExceptionTranslationFilter`. Where the exception originates, where it gets caught, and whether the response is already committed determine what handles it.

Example fragment:

~~~java
@RestControllerAdvice
class ApiAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> badInput(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid input");
    }
}
~~~

The snippet above targets controller/business errors. It is not a standalone runnable class; it requires imports, a Spring MVC app, and a controller throwing the exception.

### Why Should You Not “Catch Every Exception” in Advice?

Anti-example:

~~~java
// Anti-example, DO NOT copy into production:
@ExceptionHandler(Exception.class)
ResponseEntity<String> everything(Exception ex) {
    return ResponseEntity.status(500).body(ex.getMessage());
}
~~~

Harms:
1. Valid 400/404/409 statuses can accidentally be turned into 500.
2. Raw exception messages can leak tokens, table names, SQL, paths, or internal structures.
3. If a method-security `AccessDeniedException` reaches Advice, a broad handler can interfere with Security's status and semantics.
4. Filter errors still remain uncovered, since filters complete responses before MVC.

In real projects, group exceptions by ownership: MVC validation/business vs authentication/authorization vs network/proxy/container.

## 7. Runnable Java 17 Example: One API Returning 401, 403, and 400 from the Right Layers

Create a project via **Spring Initializr**: Java 17+, Gradle, **Spring Boot 3.5.x**, dependencies **Spring Web** and **Spring Security**, with no Redis/JWT needed. In a project with Boot Gradle plugin/dependency management configured, Gradle fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This is a **dependency fragment**, not the full build script. Initializr projects include the Gradle wrapper. Create a single Java file `src/main/java/demo/security/SecurityBoundaryApplication.java`:

~~~java
package demo.security;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class SecurityBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityBoundaryApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    AuthenticationEntryPoint jsonAuthenticationEntryPoint() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType("application/problem+json");
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""
            );
            response.getWriter().write(
                "{\"type\":\"about:blank\","
                + "\"title\":\"Unauthorized\",\"status\":401}"
            );
        };
    }

    @Bean
    AccessDeniedHandler jsonAccessDeniedHandler() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType("application/problem+json");
            response.getWriter().write(
                "{\"type\":\"about:blank\","
                + "\"title\":\"Forbidden\",\"status\":403}"
            );
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint entryPoint,
            AccessDeniedHandler deniedHandler) throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .requestMatchers("/api/admin").hasRole("ADMIN")
            .requestMatchers("/api/me", "/api/fail").authenticated()
            .anyRequest().denyAll()
        );

        // Explicit entry point: covers invalid Basic credentials too.
        http.httpBasic(basic -> basic.authenticationEntryPoint(entryPoint));

        // Authorization/challenge branch via ExceptionTranslationFilter.
        http.exceptionHandling(ex -> ex
            .authenticationEntryPoint(entryPoint)
            .accessDeniedHandler(deniedHandler)
        );

        http.sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

        http.formLogin(form -> form.disable());

        // Keep default CSRF: demo uses GET only.
        return http.build();
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("area", "admin");
    }

    @GetMapping("/api/fail")
    Map<String, String> fail() {
        throw new IllegalArgumentException("sensitive internal detail");
    }
}

@RestControllerAdvice
class ApiControllerAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> badInput(IllegalArgumentException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, "Request is not valid"
        );
        pd.setTitle("Invalid request");
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(pd);
    }
}
~~~

This is **one complete Java source file** in a project with the proper dependencies. Java allows multiple top-level classes when only one `public` class matches the filename; the package-private `@Configuration`, `@RestController`, and `@RestControllerAdvice` classes are still picked up by component scanning in the same package.

### Deliberate Choices in the Code

- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` provides proper password hashing for the demo instead of `{noop}`.
- The two sample usernames/passwords **are in source for local testing only**; never ship them to production. Production should connect to an identity provider/user store and secrets management.
- `AuthenticationEntryPoint` returns **401** with `WWW-Authenticate: Basic realm="demo-api"` since this uses HTTP Basic.
- `AccessDeniedHandler` returns **403** without exposing the specific role policy.
- `@RestControllerAdvice` catches only `IllegalArgumentException` from the controller and uses `ProblemDetail` for 400.
- `SessionCreationPolicy.STATELESS` avoids using `HttpSession` to store the demo's SecurityContext. This **does not automatically eliminate CSRF risk** with a browser sending credentials automatically.
- `formLogin(form -> form.disable())` avoids turning the API into a login-page redirect flow.
- `anyRequest().denyAll()` prevents unlisted URLs from passing Security without a policy.
- Because the demo uses GET endpoints, we **do not disable CSRF globally** just to simplify testing.

### Running the Project

To pin the port, create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

From the project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the app starts, send requests from another terminal. HTTP Basic over `http://localhost` here **is strictly for local learning**; production must use HTTPS because Basic headers are trivially decoded if intercepted in transit.

## 8. Verifying HTTP Status, Headers, and Bodies

### 8.1. Public Endpoint — Controller Returns 200

~~~bash
curl -sS -i http://localhost:8080/api/public
~~~

Status `200 OK`, JSON body:

~~~json
{"message":"public"}
~~~

### 8.2. No Credentials — Security Returns 401

~~~bash
curl -sS -i http://localhost:8080/api/me
~~~

Status `401 Unauthorized`, key headers:

~~~http
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/problem+json
~~~

JSON body **written explicitly by the example's entry point**:

~~~json
{"type":"about:blank","title":"Unauthorized","status":401}
~~~

`DemoController.me()` never runs because the filter blocked it.

### 8.3. Invalid HTTP Basic Credentials — Still 401

~~~bash
curl -sS -i -u alice:wrong-password \
  http://localhost:8080/api/me
~~~

Status 401 and similar `Unauthorized` JSON body. In this configuration, Basic authentication failures also use the JSON entry point thanks to:

~~~java
http.httpBasic(basic -> basic.authenticationEntryPoint(entryPoint));
~~~

If you **only** configure `exceptionHandling.authenticationEntryPoint` and forget the authentication mechanism's entry point, the body for a wrong Basic password may differ from the body for missing credentials depending on your Security configuration.

### 8.4. Logged-In User Lacking Permission — 403

~~~bash
curl -sS -i -u alice:alice-pass \
  http://localhost:8080/api/admin
~~~

`alice` has `ROLE_USER`, not `ROLE_ADMIN`. Status `403 Forbidden`. Body from `AccessDeniedHandler`:

~~~json
{"type":"about:blank","title":"Forbidden","status":403}
~~~

Controller `admin()` **does not run**. Advice never gets a chance to run because the error occurred at the request authorization filter.

### 8.5. Authorized Admin — 200

~~~bash
curl -sS -i -u admin:admin-pass \
  http://localhost:8080/api/admin
~~~

Status `200 OK`, body:

~~~json
{"area":"admin"}
~~~

### 8.6. Error Inside Controller — Advice Returns 400

~~~bash
curl -sS -i -u alice:alice-pass \
  http://localhost:8080/api/fail
~~~

After Security authenticates successfully, `fail()` throws `IllegalArgumentException`. `@RestControllerAdvice` catches it and returns `400 Bad Request` with `ProblemDetail`:

~~~json
{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request is not valid"
}
~~~

Spring may include an `instance` field, and JSON field ordering depends on the converter; do not compare verbatim response bytes—assert the relevant fields instead. **The original exception message “sensitive internal detail” is never leaked to the client**.

### 8.7. Flow Summary

| Request | Who decides? | HTTP status | Reaches Controller? |
|---|---|---|---|
| `GET /api/public` | Security permitAll → controller | 200 | Yes |
| `GET /api/me` without credentials | Entry point | 401 | No |
| `GET /api/me` wrong password | BasicAuthenticationFilter/entry point | 401 | No |
| `GET /api/admin` as alice | AuthorizationFilter/AccessDeniedHandler | 403 | No |
| `GET /api/admin` as admin | Controller | 200 | Yes |
| `GET /api/fail` as alice | Controller throws → Advice | 400 | Yes |

This table shows that identical status or JSON formatting does not imply the same layer produced the response.

## 9. Common Confusion: Same Exception Type, Different Origin

Suppose a service method is protected by Spring method security:

~~~java
// Illustrative fragment: requires @EnableMethodSecurity, a @Service class,
// and an appropriate reportRepository in a real project.
@PreAuthorize("hasRole('ADMIN')")
public Report loadReport() {
    return reportRepository.load();
}
~~~

`Report` and `reportRepository` here are illustrative business placeholders, **not a standalone program**.

If the controller was already invoked and the service proxy throws `AccessDeniedException` due to `@PreAuthorize`, the exception can pass through Spring MVC handler exception resolution. If the project defines `@ExceptionHandler(AccessDeniedException.class)`, it **can** be invoked and produce the response; if not resolved by MVC, the exception can propagate outward to `ExceptionTranslationFilter`.

**Exact takeaway:** never claim “Advice can absolutely never catch `AccessDeniedException`”. At the same time, do not rely on Advice as the **primary source** of error semantics when request-level Security filters exist. Test both request-level authorization and method-level authorization, and avoid catch-all advice that produces inconsistent behavior.

## 10. CSRF: Pre-Controller 403s May Not Use the Shared Authorization Handler

In apps using session cookies or browser credentials, Spring Security enables CSRF protection by default for many state-changing HTTP methods such as POST/PUT/PATCH/DELETE. If a request requires a CSRF token and it is missing or invalid, `CsrfFilter` can return `403` before the controller.

~~~http
POST /api/orders HTTP/1.1
Cookie: JSESSIONID=...
Content-Type: application/json

{"sku":"A"}
~~~

**Never disable CSRF unconditionally** just to make status/body formatting easier:

~~~java
// ANTI-EXAMPLE: DO NOT use to "fix all CSRF errors" in production.
http.csrf(csrf -> csrf.disable());
~~~

If an API uses only tokens explicitly attached by JavaScript/clients without relying on auto-sent browser credentials, the CSRF threat model differs. However, base this on actual evaluation rather than assuming “API returns JSON” implies CSRF can be skipped. With session cookies, a CSRF token or approved equivalent is normally required.

### CSRF Can Have Its Own AccessDeniedHandler

Security filters do not necessarily route every denial through `ExceptionTranslationFilter`. `CsrfFilter` may invoke its own denial handler directly. Thus merely configuring:

~~~java
http.exceptionHandling(ex -> ex.accessDeniedHandler(myHandler));
~~~

does not prove every CSRF error will carry the body written by `myHandler`. If your product requires a unified schema, inspect CSRF and `exceptionHandling` behavior for your **exact Security version**, identify the handler actually writing the response, and test POSTs with and without tokens. Never weaken security policy just to unify JSON.

## 11. CORS and Requests Blocked Before DispatcherServlet

When a browser wants to send a cross-origin JSON POST, it may send a preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,authorization
~~~

Preflight requests do not carry the same credentials as actual requests; if Security attempts to authenticate the preflight before the CORS handler runs, it can return 401/403. The browser never sends the actual POST, and the console often reports only a generic “CORS error”.

In Servlet Spring Security, integrate CORS via:

~~~java
// Fragment in Servlet SecurityFilterChain with an existing CORS policy.
http.cors(org.springframework.security.config.Customizer.withDefaults());
~~~

CORS configuration can be supplied via `WebMvcConfigurer.addCorsMappings` or `CorsConfigurationSource` per architecture. Never fix this with `permitAll("/**")` or `allowedOrigins("*")` alongside credentials. In Spring WebFlux, use `ServerHttpSecurity.cors(...)` and `CorsWebFilter`.

**An easily overlooked detail:** a 401 response from a gateway/filter may lack `Access-Control-Allow-Origin`, preventing browser JavaScript from **reading the 401 body/status**, even though `curl -i` clearly shows 401. When debugging, compare headers of actual responses through the proxy instead of looking solely at the console.

## 12. OAuth2 Resource Server / Bearer JWT: Preserve the Right Challenge

The main example uses HTTP Basic for ease of practice, while production apps often use JWT Bearer tokens.

When a Bearer token is missing or invalid:
- Spring Security Resource Server has dedicated logic in `BearerTokenAuthenticationFilter` and `BearerTokenAuthenticationEntryPoint`.
- The `WWW-Authenticate: Bearer ...` header may contain `error="invalid_token"`, `realm`, or other attributes per RFC 6750.
- When a valid token lacks an OAuth2 scope, the appropriate handler may be `BearerTokenAccessDeniedHandler`, including `insufficient_scope` in the challenge per standard.

Never reuse the Basic demo's `AuthenticationEntryPoint` for Bearer responses; emitting `WWW-Authenticate: Basic` on a Bearer endpoint uses the **wrong security scheme**. When standardizing JSON bodies:
1. Identify the actual authentication mechanism and its handlers.
2. Preserve status/challenge headers per OAuth2/RFC 6750.
3. Write JSON/`ProblemDetail` using a shared schema **without breaking protocol semantics**.
4. Test missing, malformed, expired, invalid-signature, and insufficient-scope tokens.

For traditional browser form login, the entry point may redirect `302` to a login page rather than returning JSON 401. APIs and UIs with differing experiences may need **two security chains or distinct entry-point matchers**.

## 13. When You Need a Single Unified JSON Error Contract

A clean design:

~~~text
                      Shared error contract
                  (status, type, code, detail)
                             |
           +-----------------+--------------------+
           |                                      |
   Spring Security handlers               MVC RestControllerAdvice
   AuthenticationEntryPoint               HandlerExceptionResolver
   AccessDeniedHandler                    @ExceptionHandler
           |                                      |
           +-----------------+--------------------+
                             |
                             v
                          HTTP response
~~~

You can extract a shared `ErrorResponseFactory` or serializer to share the JSON structure. Yet ownership stays distinct:
- 401, `WWW-Authenticate`, login redirects: belong to the authentication scheme.
- 403: belongs to security policy/denial handlers.
- 400, 404, 409 domain errors: belong to MVC/business mappings.
- Gateway error responses: belong to the gateway.

**RFC 9457 Problem Details** is a strong choice for JSON APIs. Common fields:
- `type`: URI identifying the error type or `about:blank`.
- `title`: short title for the error type.
- `status`: HTTP status.
- `detail`: description that leaks no sensitive data.
- `instance`: identifier for a specific occurrence when appropriate.
- Extensions such as `code` and `traceId` per contract.

Note: sharing a JSON structure **does not mean sharing the HTTP status**. Never return `200 OK` with `{"status":401}` on authentication failure. Ensure HTTP status, caching directives, challenge headers, and CORS policies remain accurate.

## 14. When Do ResponseEntityExceptionHandler or /error Participate?

Spring MVC provides `ResponseEntityExceptionHandler` to customize common MVC exceptions (such as validation errors, unsupported methods, or media types). Spring Boot also provides error dispatch via `/error` and `BasicErrorController` for certain unhandled errors.

These are **different handling paths**:
- `@RestControllerAdvice`: MVC error resolution during eligible handler processing.
- `ResponseEntityExceptionHandler`: base class for standardizing several built-in MVC errors.
- `BasicErrorController` / `ErrorAttributes`: errors routed through Boot's error dispatch/container in certain cases.
- `AuthenticationEntryPoint` / `AccessDeniedHandler`: security errors at the filter layer.
- Proxy/CDN: can generate 401/403/429/502 before reaching the backend.

Do not rely on `/error` to catch every filter exception reliably. A filter may call `sendError` or write directly to the body; whether the container performs an error dispatch depends on how it handles the response and whether it is already committed. Once a response is committed, you cannot arbitrarily change its status/headers and write a different body.

## 15. WebFlux: Same Concept, Different APIs

Spring WebFlux uses reactive security components:

| Servlet/MVC | Reactive/WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `FilterChainProxy` | `WebFilterChainProxy` |
| `ExceptionTranslationFilter` | `ExceptionTranslationWebFilter` |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| `HttpServletResponse` | `ServerHttpResponse` |
| `DispatcherServlet` | `DispatcherHandler` |

`@RestControllerAdvice` can also be used with **WebFlux annotated controllers**, yet it still does not catch errors inside `WebFilter` instances automatically. Writing responses in reactive code must return an appropriate publisher and avoid blocking the event loop.

### Illustrative WebFlux Fragment

This fragment goes inside `@Configuration` in a **separate WebFlux project** with Spring Security reactive dependencies; do not mix it into the Servlet project above:

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/public").permitAll()
            .pathMatchers("/api/admin").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(org.springframework.security.config.Customizer.withDefaults())
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(
                new HttpBasicServerAuthenticationEntryPoint())
            .accessDeniedHandler(
                new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN))
        )
        .build();
}
~~~

Key imports: `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint`, `org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler`, `org.springframework.http.HttpStatus`, and `org.springframework.context.annotation.Bean`.

That snippet only illustrates **status/challenge branches** in WebFlux and **does not build a JSON body**. To produce JSON errors at the reactive layer, implement `ServerAuthenticationEntryPoint` or `ServerAccessDeniedHandler` writing via `ServerWebExchange.getResponse()` and returning `Mono<Void>`, without calling `block()`. For invalid HTTP Basic credentials, verify the `httpBasic` entry point as well rather than assuming every error passes through `ExceptionTranslationWebFilter`.

## 16. Multiple SecurityFilterChains: Which Chain Handles the Error?

A Spring Boot app may have two endpoint groups:
- `/api/**` using Basic/Bearer and JSON errors.
- `/ui/**` using form login, redirects, and sessions.
- Management/Actuator endpoints with their own chain or management context.

Spring Security selects a chain by matchers and order, typically applying **the first matching chain**. Each chain has its own authentication mechanisms and error handlers. An entry point configured for `/api/**` does not automatically apply to `/ui/**`.

Illustrative **fragment**, not a complete production configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // Configure appropriate authentication/authorization for API.
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain ui(HttpSecurity http) throws Exception {
    http.securityMatcher("/ui/**");
    // Configure appropriate login for UI.
    return http.build();
}
~~~

**Warning:** with only the two chains above, requests **matching neither chain** may go unprotected by Spring Security. Always design an explicit fallback chain. Never copy incomplete fragments lacking authentication/authorization into production.

When an API returns HTML login instead of 401 JSON, do not immediately blame Advice; the request may have matched the form-login chain or been routed elsewhere by a proxy.

## 17. Automated Testing: Do Not Omit Spring Security Filters from MockMvc

A common testing flaw is testing controllers only with `MockMvcBuilders.standaloneSetup(controller)`. Without the Security filter chain attached, tests can return 200 even when production returns 401/403. To verify pre-controller security, use a Spring Boot integration test or properly register security configuration.

In a Boot 3.5 project, declare test dependencies (Gradle fragment):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create `src/test/java/demo/security/SecurityBoundaryApplicationTests.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousGets401WithBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void wrongBasicPasswordGets401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void authenticatedWithoutRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.status").value(403));
    }

    @Test
    void administratorCanAccessEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.area").value("admin"));
    }

    @Test
    void controllerExceptionGoesToAdvice() throws Exception {
        mvc.perform(get("/api/fail")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.title").value("Invalid request"));
    }
}
~~~

This is a complete test class with **top-of-file imports** and annotations matching the Spring Boot MVC project. Commands:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

When the environment and dependencies are configured properly, Gradle reports `BUILD SUCCESSFUL` if all 5 tests pass. Exact console output may vary between Gradle versions. The tests verify 401 without credentials, 401 with bad Basic password, 403 missing role, 200 with role, and 400 routed via Advice.

### Additional Scenarios to Test in Real Environments

| Case | Expected |
|---|---|
| POST missing CSRF when using cookies | Denied per security policy, usually 403 |
| OPTIONS preflight with valid Origin | CORS before auth, not 401 for missing cookie |
| Missing/invalid Bearer token | 401 and appropriate `WWW-Authenticate: Bearer` |
| Valid Bearer token missing scope | 403/challenge per resource server |
| Method security denial in service | Response per policy, not turned into 500 by catch-all |
| API and UI security chains | Entry point/schema matches route |
| 401 from proxy instead of backend | Distinguish origin vs edge response |
| Error after response committed | Never writes two response bodies |
| Missing API route | Never leaks routes or turns 404 into 200 |
| Backend 403 passing through CDN | Headers/body intact per caching policy |

## 18. Debugging Security Errors by Layer

In local/test environments, you can enable:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Spring Security logs help identify which chain/filter handled a request. With many custom filters, finer-grained levels may help; **never leave sensitive debug/trace logging enabled long-term in production**. Avoid logging `Authorization`, cookies, session IDs, credentials, or tokens.

Debugging workflow:

1. **Check HTTP status:** 401, 403, 400, 404, or 500? Was there a 302 redirect?
2. **Check headers:** does 401 include the right `WWW-Authenticate` scheme? Does the response have appropriate `Content-Type` and CORS headers?
3. **Trace the path:** did the request reach the app or get stopped at the gateway/CDN?
4. **Identify the SecurityFilterChain:** do matchers and order select the intended API/UI chain?
5. **Identify the filter:** Basic/JWT/CSRF/Authorization/CORS/custom.
6. **Controlled breakpoints:** did the controller run? Did Advice run? Which security handler wrote the response?
7. **Inspect the exception:** `AuthenticationException`, `AccessDeniedException`, or business exception? Did another resolver handle it first?
8. **Check response commit state:** were headers/body already sent, or was there an `/error` dispatch?
9. **Test with MockMvc/WebTestClient and a real HTTP client** through the proxy, not just isolated controller tests.
10. **Fix at the right layer** and verify Security/CSRF have not been downgraded.

Useful metrics: 401/403 rates by route template, aggregated reason codes (never put usernames/tokens in metric labels), authentication/identity provider latency, CORS preflight rejections, CSRF denials, and gateway errors. A spike in 401s after deploy may come from key rotation, token issuer/audience changes, or cookie policies rather than Advice.

## 19. Common Errors Table

| Symptom | Why? | How to Fix |
|---|---|---|
| 401 returns HTML instead of Advice JSON | Entry point or form login ran before Controller | Choose entry point/API chain matching scheme |
| 403 skips `@ExceptionHandler` | `AuthorizationFilter` blocked the request | Configure `AccessDeniedHandler` |
| Wrong Basic password returns different body than “not logged in” | Basic filter has its own entry point | Configure `httpBasic(...authenticationEntryPoint(...))` and test |
| Invalid Bearer token returns Basic challenge | Wrongly used Basic handler on Resource Server | Use `BearerTokenAuthenticationEntryPoint` per RFC 6750 |
| 401 JSON lacks `WWW-Authenticate` | Custom writer omitted challenge header | Preserve scheme-appropriate challenge |
| POST with session cookie gets 403 | CSRF filter or policy active | Check CSRF token, never disable to bypass |
| Custom denial handler not used on CSRF 403 | `CsrfFilter` handles denials separately | Identify CSRF handler for your Security version |
| Browser reports CORS instead of 401 | Preflight hit auth or 401 lacked CORS response headers | Configure CORS before Security, check gateway |
| Controller 400 error returns 500 | Broad Advice or wrong status mapper | Catch exact exceptions / `ProblemDetail` |
| Advice sees `AccessDeniedException` from method security | Exception originated inside MVC handler processing | Check MVC resolver and Security propagation |
| API redirects 302 to login | Form-login entry point selected | Configure right authentication scheme and chain |
| Works locally, returns 403 behind gateway | Gateway IAM/WAF/route rules | Inspect edge logs rather than only changing Spring code |
| A group of paths goes unprotected | Missing fallback security chain/matcher | Add appropriate rule/chain and test routes |
| Controller test passes yet prod returns 403 | Standalone MockMvc lacks filters | Run integration tests with Spring Security |
| Error body written twice | Attempted write after response committed | Fix handlers/error dispatch, avoid duplicate writers |
| Logs leak JWT/Basic Authorization | Logging sensitive request headers | Redact and restrict DEBUG |

## 20. Secure API Design Checklist

- [ ] Documented **FilterChainProxy → DispatcherServlet → ControllerAdvice** flow for Spring MVC.
- [ ] 401/403 handled by Security components matching the credential type.
- [ ] HTTP Basic/Bearer preserve `WWW-Authenticate` where needed.
- [ ] `AuthenticationEntryPoint` handles both missing and invalid credentials for the active mechanism.
- [ ] `AccessDeniedHandler` returns 403 for authenticated-but-forbidden callers.
- [ ] No catch-all Advice unintentionally swallows `AccessDeniedException`.
- [ ] CSRF protection evaluated against browser credentials/sessions.
- [ ] CORS preflight and error responses handled properly before auth where needed.
- [ ] Multiple `SecurityFilterChain` beans have explicit matchers, `@Order`, and fallback.
- [ ] Consistent `ProblemDetail`/JSON contract without altering HTTP semantics.
- [ ] No raw exception messages, role policies, tokens, session IDs, or stack traces leaked.
- [ ] WebFlux uses `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`.
- [ ] Integration tests include the Security filter chain, not just controller unit tests.
- [ ] Responses tested via gateway/CDN across 401/403/400/500 paths.
- [ ] Security/CSRF never disabled and `permitAll` never widened just to “beautify” responses.

## 21. Review Questions

**1.** Why does a `@RestControllerAdvice` handling `IllegalArgumentException` never see the 401 error when an API is called without logging in?

**Answer:** Spring Security filters can block the request before `DispatcherServlet`; no MVC exception ever reaches Advice.

**2.** If a logged-in user lacks `ROLE_ADMIN`, what is the primary handler for a request-level denial?

**Answer:** Usually `AccessDeniedHandler` returning 403. For an anonymous request to the same endpoint, `AuthenticationEntryPoint`/401 may be used instead.

**3.** You configured `exceptionHandling.authenticationEntryPoint`, so why does entering a wrong Basic password still return a different body?

**Answer:** `BasicAuthenticationFilter` can use its own entry point. You must check and also configure `httpBasic(...authenticationEntryPoint(...))` as in the example.

**4.** Can `@ControllerAdvice` **ever** catch `AccessDeniedException`?

**Answer:** Yes, when the exception arises inside a controller/service after dispatch and the MVC exception resolver handles it. Do not infer from this that Advice catches errors already handled at pre-controller filters.

**5.** Is disabling `csrf()` so error JSON matches Advice acceptable?

**Answer:** No. CSRF is a security protection; design according to threat model and tokens/policies rather than lowering security just to unify response bodies.

**6.** When an OAuth2 Bearer token is invalid, should you return `WWW-Authenticate: Basic` just because another system already had a Basic JSON handler?

**Answer:** No. Use the proper Bearer challenge/handler per RFC 6750.

**7.** An HTTP POST from a browser reports “CORS error” while curl sees 401. Can that happen?

**Answer:** Yes. Preflight may get 401 from Security, or an actual 401 may lack CORS headers, causing the browser to deny frontend access to the response.

**8.** Should `@RestControllerAdvice` and Security errors be tested together using a single standalone MockMvc without filters?

**Answer:** That is insufficient. You need an integration setup with the Spring Security filter chain for 401/403.

**9.** If an API has multiple `SecurityFilterChain` beans, does a shared entry point automatically apply to every chain?

**Answer:** No. Chains are selected by matchers and order and may be configured differently; design and test each namespace.

**10.** Can you return `{"status":401}` with HTTP status 200 to make frontend code simpler?

**Answer:** You should not. HTTP status codes must remain accurate; the response body is supplementary. Preserve true 401/403 statuses and challenge headers where needed.

### Extension Exercise

Starting from the Section 7 example, add a `GET /api/report` route requiring `ROLE_ADMIN`, and verify `alice` gets 403 while `admin` gets 200. Next, add a CSRF-protected POST, test missing-token requests, and trace which handler returns 403. Then throw an exception from a `@PreAuthorize` service method to see whether MVC resolver or Security handles it under that configuration. Finally, inspect a response from a reverse proxy/gateway in front of the backend and explain why Advice never received it.

## 22. Official References

- [Spring Security — Servlet Architecture, Security Filter Chain, ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — In-Memory UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html)
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Framework — MVC @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework — RFC 9457 ProblemDetail in MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9110 — HTTP Semantics: 401/403 and Authentication](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)

**Remember:** Security filters can handle errors **before the Controller**, whereas `@RestControllerAdvice` is exception resolution **within MVC/WebFlux handler processing**. To unify JSON errors, use **`AuthenticationEntryPoint`/`AccessDeniedHandler`** or the corresponding Security mechanism's handlers for 401/403, and Advice for controller errors. Keep HTTP semantics intact, avoid weakening security, and always verify with tests running the real filter chain.