# Consistent Error Responses Without Leaking Credentials, Tokens, or Internal Data

> **Scope:** Spring Security on the **Servlet stack** (Spring Boot 3.x, Spring Security 6.x, Java 17+). This lesson focuses on HTTP error responses when authentication or authorization fails, standardizing the JSON contract, and protecting sensitive information.

## 1. Goals and Principles

A secure API must answer three questions: **what category did the request fail under, how should the caller handle it, and how can operators trace the event**. Public responses do not need to contain detailed technical causes, login credentials, or token contents.

Practical rules:

1. **Preserve accurate HTTP statuses.** `401 Unauthorized` for unauthenticated or invalidly authenticated requests; `403 Forbidden` for authenticated users lacking permission. Never return `200` with a `success: false` flag for security errors.
2. **Keep the response contract stable.** For example, every API access error uses three fields: `code` (machine-readable code), `message` (safe message), and `requestId` (lookup ID). `message` may be localized, while `code` must stay stable.
3. **Use generic messages.** Never put `exception.getMessage()`, stack traces, internal user IDs, SQL queries, passwords, API keys, access/refresh tokens, session cookies, or full `Authorization` headers into responses.
4. **Separate public signals from internal diagnostics.** Responses provide only essential info; logs/traces record event codes, statuses, `requestId`, and redacted attributes. Internal error details, when needed, belong strictly in access-controlled observability channels.
5. **Never weaken security to standardize JSON.** Keep your authorization policies, CSRF, CORS, caching headers, and authentication standards intact.

Example JSON contract for an unauthenticated request:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Authentication is required to access this resource.",
  "requestId": "d13d7fb3-32be-4ee8-b9c4-5b4808ebbd7a"
}
```

`requestId` is an illustrative value; each response in the example below generates a fresh UUID. This ID does **not** substitute for a user ID and must never be used as proof of authentication.

## 2. Distinguish Errors Properly to Avoid Information Disclosure

| Scenario | HTTP | Public `code` | Safe message |
|---|---:|---|---|
| No credentials sent to a login-required API | 401 | `AUTHENTICATION_REQUIRED` | Authentication is required to access this resource. |
| Wrong password or invalid credentials | 401 | `AUTHENTICATION_REQUIRED` | Authentication is required to access this resource. |
| Logged in yet lacking permission for the operation | 403 | `ACCESS_DENIED` | You do not have permission to perform this action. |
| Request rejected due to CSRF check | 403 | `ACCESS_DENIED` | You do not have permission to perform this action. |
| Malformed input syntax or constraint violation | 400 | `BAD_REQUEST` | Invalid request. |
| Unexpected application error | 500 | `INTERNAL_ERROR` | Unable to process the request at this time. |

The sample code in Section 4 directly implements **the two security error types 401/403**. Codes 400/500 require corresponding MVC error-handling mechanisms and do not arise from those two handlers automatically. Returning 404 instead of 403 to conceal resource existence is appropriate only when business policies are designed consistently; never use messages like "You do not own account X" that inadvertently confirm account X exists.

Specifically for login APIs, use **the exact same failure message** whether the account does not exist, the password is wrong, or the account status cannot be disclosed publicly. Never return "Email is registered but password is wrong", "User is locked", or "Account 123 token expired" if doing so reveals data to unauthorized callers. Rate limiting, brute-force protection, and logging controls remain essential; generic messages alone do not stop those attacks.

## 3. Handling Mechanism in Spring Security Servlet

High-level flow:

```text
HTTP request
  -> Servlet Filter Chain
  -> Spring Security FilterChainProxy
     -> authentication filters / AuthorizationFilter
     -> ExceptionTranslationFilter (translates certain security exceptions into HTTP responses)
        -> AuthenticationEntryPoint (401 path, authentication required)
        -> AccessDeniedHandler (403 path, authenticated yet denied)
  -> HTTP response
```

`ExceptionTranslationFilter` receives `AuthenticationException` or `AccessDeniedException` from downstream parts of the chain. When the caller is not sufficiently authenticated, an `AccessDeniedException` can also route to `AuthenticationEntryPoint` to initiate authentication. When authenticated yet lacking permissions, `AccessDeniedHandler` handles 403.

Some authentication mechanisms report errors **directly inside the authentication filter**; for instance, HTTP Basic requires configuring the entry point in both `httpBasic` and `exceptionHandling` for a consistent 401 contract. Form login has its own `AuthenticationFailureHandler`. Spring MVC's `@RestControllerAdvice` normally **cannot** catch errors raised in the security filter chain before the request reaches a controller: configuring only a global MVC exception handler is not enough.

For OAuth2 Resource Server/Bearer tokens, the `WWW-Authenticate` header and standard error codes carry protocol meaning (RFC 6750). Preserve the challenge conventions clients depend on—for example, using Spring Security's Bearer handlers—while limiting descriptions and never echoing raw tokens. The **HTTP Basic demo** below must not have its Basic header copied verbatim onto a Bearer API.

## 4. Complete Example on Spring Boot 3.x / Java 17+

Assume the project already includes `spring-boot-starter-web` and `spring-boot-starter-security`; Jackson comes with the Web starter. The example has two files in package `demo.security`. Use only dummy accounts with passwords loaded from an environment variable for local machine testing. In real applications, keep your existing `UserDetailsService`/identity provider and integrate the two handlers into your security configuration.

**File `src/main/java/demo/security/SecurityErrorConfig.java`:**

```java
package demo.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
public class SecurityErrorConfig {
    private static final Logger LOG =
            LoggerFactory.getLogger(SecurityErrorConfig.class);

    public record ErrorBody(String code, String message, String requestId) {}

    private static void writeError(HttpServletResponse response,
                                   ObjectMapper mapper,
                                   int status,
                                   String code,
                                   String publicMessage) throws IOException {
        if (response.isCommitted()) {
            LOG.warn("Cannot write security error: response already committed");
            return;
        }

        String requestId = UUID.randomUUID().toString();
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Request-Id", requestId);
        mapper.writeValue(response.getOutputStream(),
                new ErrorBody(code, publicMessage, requestId));

        // Log error category and lookup ID; never log exceptions or credentials.
        LOG.info("security_rejection code={} status={} requestId={}",
                code, status, requestId);
    }

    @Bean
    AuthenticationEntryPoint apiEntryPoint(ObjectMapper mapper) {
        return (request, response, exception) -> {
            // HTTP Basic requires a challenge; contains no passwords or tokens.
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo\"");
            writeError(response, mapper, 401,
                    "AUTHENTICATION_REQUIRED",
                    "Authentication is required to access this resource.");
        };
    }

    @Bean
    AccessDeniedHandler apiDeniedHandler(ObjectMapper mapper) {
        return (request, response, exception) ->
                writeError(response, mapper, 403,
                        "ACCESS_DENIED",
                        "You do not have permission to perform this action.");
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUser(PasswordEncoder encoder) {
        String password = System.getenv("APP_DEMO_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "Set APP_DEMO_PASSWORD before starting the demo");
        }
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiEntryPoint,
            AccessDeniedHandler apiDeniedHandler) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/admin")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                    .authenticationEntryPoint(apiEntryPoint)
                    .accessDeniedHandler(apiDeniedHandler))
            .httpBasic(basic ->
                    basic.authenticationEntryPoint(apiEntryPoint))
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
```

**File `src/main/java/demo/security/DemoApplication.java`:**

```java
package demo.security;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicResource() {
        return Map.of("data", "public");
    }

    @GetMapping("/api/private")
    public Map<String, String> privateResource() {
        return Map.of("data", "private");
    }

    @GetMapping("/api/admin")
    public Map<String, String> adminResource() {
        return Map.of("data", "admin");
    }
}
```

Run from a Gradle-configured Spring Boot project; enter the demo password via terminal rather than hardcoding passwords in source code or `curl` commands:

```bash
read -rs APP_DEMO_PASSWORD
export APP_DEMO_PASSWORD
./gradlew bootRun
```

Open a second terminal:

```bash
curl -i http://localhost:8080/api/private
curl -i --user learner http://localhost:8080/api/admin
curl -i --user learner http://localhost:8080/api/private
```

With `--user learner`, `curl` will prompt for the password. Expected results: command 1 returns **401** with `AUTHENTICATION_REQUIRED`; command 2 returns **403** with `ACCESS_DENIED` because `learner` only has role `USER`; command 3 returns **200** with JSON `{"data":"private"}`. Both error responses include `Content-Type: application/json`, `Cache-Control: no-store`, and the same `requestId` in the body and `X-Request-Id` header. With Basic, 401 also includes `WWW-Authenticate: Basic realm="demo"`. UUIDs and timing may vary per run. When running outside localhost, HTTP Basic **must use HTTPS**; never use demo accounts in production.

**Why does this avoid leaking information?** Both handlers deliberately ignore `exception` contents in responses; messages are reviewed constants with uniform JSON built by one shared helper. Logging records only error code, status, and `requestId`. `Cache-Control: no-store` lowers the risk of caching access-related errors. `BCryptPasswordEncoder` serves only the demo account; real apps still need standard password/identity management.

## 5. Applying to Real-World Systems

### Keep Contracts Consistent Without Breaking Protocols

- Place `AuthenticationEntryPoint` and `AccessDeniedHandler` on **the exact `SecurityFilterChain`** protecting target routes. With multiple chains using `securityMatcher`, verify which chain matches the request, because configuration on another chain does not apply automatically.
- For HTTP Basic, 401 should include a valid `WWW-Authenticate` header. For OAuth2 Bearer, preserve `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` semantics; clients may require standard auth/scope status metadata. Never swap the challenge string for a Basic string or leak raw tokens in `error_description`.
- For form login, the default failure handler may redirect to the login page; if building a JSON login API, configure a matching `AuthenticationFailureHandler`. With Spring MVC, use `@RestControllerAdvice` for validation/business/500 errors to keep the same envelope without exposing exceptions; never expect it to replace security handlers.
- Do not arbitrarily disable CSRF just to get a JSON body. If the application uses cookies/sessions for state-changing requests, keep CSRF protection and test the 403 path of that branch.
- If the system already receives a trace ID from a request filter or tracing setup, **reuse the server-controlled ID** instead of always generating a new UUID in the writer. Client-supplied request ID headers must be validated for format, length, and trustworthiness before logging to prevent log injection.

### Data That Must Never Be Made Public

Inspect **body, headers, and logs** together. Never return or log verbatim: `Authorization`, `Cookie`, `Set-Cookie`, passwords, `client_secret`, OTPs, session IDs, access tokens, refresh tokens, private keys, connection strings, SQL statements, stack traces, filesystem paths, full request bodies, or private user data. A line like `LOG.error("Authentication failed", exception)` is occasionally needed for internal investigation, yet must pass through sensitive-data redaction and log access controls; the current example avoids logging exceptions directly.

Never automatically return `exception.getMessage()` even if the current exception looks harmless: messages from libraries, identity providers, or future configurations may contain sensitive details. Never produce overly distinct messages between valid/invalid accounts, existing/non-existent tokens, or permitted/denied resources; such differences create information-disclosure channels.

## 6. Testing Checklist and Common Mistakes

| Test case | Expected outcome |
|---|---|
| Anonymous GET to protected route | 401; stable `code`; no HTML redirect in API |
| Wrong HTTP Basic password | 401; same envelope, no echoed username/password |
| Regular user accessing admin route | 403; does not reveal internal roles or exact missing permissions |
| Authorized user accessing valid route | 200; error handlers do not interfere |
| CSRF error on state-changing endpoint | 403; does not expose CSRF token |
| Request with fake sensitive token/signature/header | No sensitive string appears in body, response headers, or logs |
| Consecutive errors | Each response has a valid `requestId`; body/headers match; server has matching lookup trace |
| Internal 500 error from controller | Generic message; no stack trace/SQL/server path exposed |
| Requests traversing different `SecurityFilterChain`s | Each chain uses its right handlers and authentication standards |

Common implementation mistakes:

1. Adding only `@RestControllerAdvice` and seeing 401/403 still return HTML or redirects: errors come from the **filter chain**, requiring entry points/denied handlers.
2. Configuring 403 properly while wrong HTTP Basic passwords still return another format: configure the same entry point on `httpBasic`.
3. Using `exception.getMessage()` as `message` or serializing `Exception` objects: risks exposing internal details.
4. Swallowing all errors into 401 or 500: clients misclassify missing login, missing permissions, bad input, and server failures; metrics become inaccurate too.
5. Omitting `WWW-Authenticate` challenges or using the wrong scheme: standard clients may fail to re-authenticate properly.
6. Logging request bodies, tokens, or full headers while debugging, or blindly trusting client-supplied request IDs: leaks secrets and pollutes logs.
7. Disabling CSRF/CORS or loosening access rules to "fix JSON error formatting": proper responses must never come at the expense of lost access control.

**Completion criteria:** for the same error category, clients receive a consistent status and `code`, a safe message, and a traceable `requestId`; 401/403 errors route through the proper Servlet Security handlers; and no response or log path exposes credentials, tokens, or internal data.