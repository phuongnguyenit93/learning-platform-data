# AuthenticationEntryPoint and Requesting Client Proof of Identity

> **Module:** Spring Security – Authentication. **Group:** Authentication Responses. Documentation for Java 17+, Spring Boot 3.x, and Spring Security 6.x on the Servlet stack. Focuses on the role of `AuthenticationEntryPoint` when a client has not yet proven its identity, how HTTP 401/403/302 carry different meanings, `WWW-Authenticate` authentication challenges, and securely designing web form login alongside a REST API.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the `AuthenticationEntryPoint` interface and the purpose of the `commence(...)` method.
2. State when `ExceptionTranslationFilter` invokes EntryPoint and when `AccessDeniedHandler` handles the error; explain why authentication filters can also invoke EntryPoint directly.
3. Distinguish between **missing credentials**, **invalid credentials**, **authenticated but lacking permissions**, and **a failed login submission attempt**.
4. Read HTTP responses: `302 Location` redirect, `401 WWW-Authenticate: Basic` or `Bearer`, and `403 Forbidden`.
5. Choose `LoginUrlAuthenticationEntryPoint`, `BasicAuthenticationEntryPoint`, `BearerTokenAuthenticationEntryPoint`, `HttpStatusEntryPoint`, or `DelegatingAuthenticationEntryPoint` according to the protocol.
6. Configure Spring Security for browsers and APIs using `SecurityFilterChain`/`@Order` without causing REST clients to receive an HTML login page.
7. Customize JSON when needed without dropping challenge headers, leaking tokens, or causing redirect loops.
8. Write tests and run a Java 17 example demonstrating the right response selection.

## 2. Core Answer: What Does EntryPoint Do?

`AuthenticationEntryPoint` is the **starting point of authentication** at the HTTP boundary. When a resource requires appropriate Authentication that the request has not yet satisfied, Spring Security uses this component to **ask the client to provide proof of identity**.

Depending on the authentication mechanism, it may:

- Redirect the browser to the `/login` page so the user can enter a username/password.
- Emit `401` and `WWW-Authenticate: Basic realm="..."` so the client knows the server supports HTTP Basic.
- Emit `401` and `WWW-Authenticate: Bearer` so the client knows the resource requires an OAuth2 access token.
- Send another status or challenge according to the agreed protocol; enforcing the HTTP contract and application policy properly.

**EntryPoint does not verify passwords or JWTs**: that responsibility belongs to `AuthenticationManager`, `AuthenticationProvider`, `BasicAuthenticationFilter`, `BearerTokenAuthenticationFilter`, `JwtDecoder`, or the corresponding identity service. Neither does it grant roles or issue sessions/tokens itself. It is the **authentication guidance output**, not an authentication verifier.

Interface provided by Spring Security, Servlet signature (for explanation, do not recreate the interface file yourself):

```java
package org.springframework.security.web;

public interface AuthenticationEntryPoint {
    void commence(
        jakarta.servlet.http.HttpServletRequest request,
        jakarta.servlet.http.HttpServletResponse response,
        org.springframework.security.core.AuthenticationException authException)
        throws java.io.IOException, jakarta.servlet.ServletException;
}
```

| Parameter | Purpose | Security Requirement |
|---|---|---|
| `request` | The request that caused auth to be required | Do not treat client-supplied `Host`, `Authorization`, or query parameters as proof of authentication |
| `response` | Where HTTP status, `WWW-Authenticate`, `Location`, or body is written | Only write when the response is not yet committed; do not produce conflicting responses |
| `authException` | Error or reason authentication is required | Do not echo the full `getMessage()`, stack trace, JWT, or sensitive data |

EntryPoint only **invites the client to provide credentials**. For a subsequent request to succeed, the client must actually send proof to the appropriate authentication filter/provider and have it verified. **A `401` does not prove that a username or account exists.**

## 3. Relationship Between Authentication, Authorization, and ExceptionTranslationFilter

Conceptual flow of Spring Security Servlet:

```text
Client GET /private (no login/token)
               |
               v
          FilterChainProxy
     selects SecurityFilterChain
               |
               v
      SecurityContext / auth filters
               |
               v
       ExceptionTranslationFilter
               |
               v
         AuthorizationFilter
           |          |
        permit       deny
           |          |
           v          v
       Controller  AccessDeniedException
                      |
                      v
              ExceptionTranslationFilter
                      |
           +----------+-------------------+
           |                              |
   anonymous/missing auth          authenticated enough but
   or AuthenticationException      lacking permissions
           |                              |
           v                              v
   AuthenticationEntryPoint       AccessDeniedHandler
           |                              |
   302 login or 401 challenge      403 / custom deny
```

`ExceptionTranslationFilter` is the bridge from Java security exceptions to HTTP responses. It wraps downstream processing in the chain, detects `AuthenticationException` or `AccessDeniedException`, and selects the proper response mechanism.

**Distinguish two cases:**

1. The request has no credentials, yet `AuthorizationFilter` requires `authenticated()`. An `AccessDeniedException` occurs; because the subject is actually anonymous, `ExceptionTranslationFilter` triggers EntryPoint.
2. The user is already fully authenticated but lacks `ROLE_ADMIN` or the appropriate scope/ownership. `AccessDeniedHandler` handles it, typically returning `403`, instead of asking to log in again.

The framework's `AuthenticationTrustResolver` can help evaluate anonymous/remember-me and cases requiring stronger authentication; **do not merely check `Authentication != null` and conclude the user has logged in**. An `AnonymousAuthenticationToken` may be present in the SecurityContext, and certain flags like `isAuthenticated()` still do not mean the user actually passed login.

### 3.1. EntryPoint Is Also Called Directly by Authentication Filters

Not every 401 has to originate from `ExceptionTranslationFilter`:

- If a Bearer token is missing, the filter may skip; `AuthorizationFilter` later blocks anonymous access and calls EntryPoint via translation.
- If the client sends an expired/invalid-signature JWT, `BearerTokenAuthenticationFilter` receives the credential, authentication fails, and it can **invoke EntryPoint through its own failure handling**.
- HTTP Basic with wrong username/password is usually handled as a failure by `BasicAuthenticationFilter`, which then calls EntryPoint.
- Form login POST with wrong credentials is usually handled by `UsernamePasswordAuthenticationFilter` via `AuthenticationFailureHandler`, redirecting to `/login?error` or as configured. That is **not** the "anonymous user just opened a page requiring login" scenario.

Therefore, when customizing, you need to test **missing credentials** and **present-but-invalid credentials** separately, not just a single 401 case.

### 3.2. RequestCache / SavedRequest

In browser applications, `HttpSessionRequestCache` can hold the path the user wanted to open before login. EntryPoint redirects to the login page; upon successful login, a success handler such as `SavedRequestAwareAuthenticationSuccessHandler` can redirect back to the original request.

For stateless APIs using Basic/Bearer, the client usually resends the request with fresh credentials; `NullRequestCache` is more suitable than creating an HTTP session. Do not turn a JWT API into a session-based one just because of an unauthenticated request. Saved destinations must be controlled so they do not create open redirects, replay sensitive data, or put tokens into `Location`.

## 4. Three Very Easily Confused Responses: 401, 403, 302

**401 Unauthorized** in HTTP authentication means **the request lacks or has not presented valid authentication proof**. According to RFC 9110, when sending 401 in HTTP authentication, the response needs a `WWW-Authenticate` challenge applicable to that resource.

**403 Forbidden** usually means the request was understood, but the caller lacks permission. For example, the token is valid but lacks a scope, or the logged-in user lacks a role or data-level permission. Forcing re-login does not automatically grant extra permissions.

**302 Found** is used by browser form login to navigate to a credential entry page. It should not be the default response for a REST endpoint that only accepts bearer tokens.

| Scenario | Usually Correct Response | Component |
|---|---|---|
| Browser GET `/profile` without a login session | `302 Location: /login` | `LoginUrlAuthenticationEntryPoint` |
| HTTP Basic API without credentials sent | `401 WWW-Authenticate: Basic` | `BasicAuthenticationEntryPoint` |
| OAuth2 API missing bearer token | `401 WWW-Authenticate: Bearer` | `BearerTokenAuthenticationEntryPoint` |
| OAuth2 API expired/bad-signature/revoked bearer | `401`, possibly `error="invalid_token"` | Bearer entry point |
| Valid token without required scope | `403`, possibly `error="insufficient_scope"` | `AccessDeniedHandler` |
| Logged in but missing `ROLE_ADMIN` | `403` | `AccessDeniedHandler` |
| Form login POST with wrong username/password | Failure response/redirect per UI | `AuthenticationFailureHandler` |
| Browser POST missing valid CSRF | Usually 403 | CSRF protection/denial |
| Malformed Bearer request per RFC 6750 | Possibly 400 `invalid_request` | Bearer error policy |
| Public permitted endpoint | Request proceeds | EntryPoint not needed |

Note: API endpoints may deny data access with 404 so as not to disclose the existence of a resource, depending on policy. Do not assume that **all** 403 errors are necessarily emitted by `AccessDeniedHandler` or that every 401 is emitted along the same filter path.

### 4.1. HTTP WWW-Authenticate Is a Challenge

Illustrative response for Basic:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="internal-api"
Cache-Control: no-store
```

Illustrative response for missing Bearer token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
```

Illustrative response for invalid Bearer token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
```

Illustrative response for valid bearer with insufficient scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
Cache-Control: no-store
```

These are **protocol patterns**, not byte-for-byte mandatory output for every configuration. `realm`, `scope`, `error_description`, and parameter ordering are determined by the implementation/policy. RFC 6750 recommends that when a request **contains no authentication information at all**, the server should not add an error code describing a nonexistent token. For `invalid_request` caused by a malformed request, the response may be 400 rather than 401.

### 4.2. What Should the Client Do After a Challenge?

- **HTTP Basic:** obtain the authorized username/password and send them over HTTPS using the `Authorization: Basic ...` header; Base64 is only encoding, not encryption.
- **Bearer:** obtain an access token from the Authorization Server via the appropriate OAuth flow and retry using `Authorization: Bearer ...`. If the token is expired, a bounded refresh may be attempted; if the token is revoked or the refresh grant is invalid, re-authentication is required per policy.
- **403 insufficient_scope:** do not retry indefinitely or self-grant scopes; the user/client needs real permissions and consent if policy supports it. If object-level or tenant permissions are missing, requesting a new token must not bypass authorization either.
- **Browser 302:** display a secure login form; upon success, return to a valid path. Never append bearer tokens or passwords to `next`, `redirect`, or `Location`.

## 5. Common AuthenticationEntryPoint Implementations

| Class | Protocol/Scenario | Notes |
|---|---|---|
| `LoginUrlAuthenticationEntryPoint` | HTML form login | Redirects to login URL; the login route must be permitted |
| `BasicAuthenticationEntryPoint` | HTTP Basic | 401 and Basic challenge with realm |
| `BearerTokenAuthenticationEntryPoint` | Spring Security OAuth2 Resource Server | Uses `BearerTokenError` to pick status and Bearer challenge |
| `HttpStatusEntryPoint` | API/custom scheme wanting a simple status | Does **not** automatically add Basic/Bearer challenges |
| `DelegatingAuthenticationEntryPoint` | Multiple schemes sharing one chain | Selects entry point by `RequestMatcher` |
| `Http403ForbiddenEntryPoint` | Some pre-auth architectures | Do not use as a default substitute for a bearer API missing a token |
| `NoOpAuthenticationEntryPoint` | Self-handled flow in special designs | Produces no response; error-prone if misused |

**Key rule:** choose the entry point based on the **authentication scheme and client contract**, not simply because you "want status 401". Customizing Basic/Bearer responses must not strip `WWW-Authenticate`. `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` returns a plain 401 but does not automatically provide the challenge header for HTTP authentication.

### 5.1. Form Login

`LoginUrlAuthenticationEntryPoint` is usually created through the DSL:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll());
```

This is a **snippet** inside a `SecurityFilterChain`. When specifying a custom login page, the application must provide `GET /login` to render the template and a POST login form with a CSRF token. If using `formLogin(Customizer.withDefaults())`, Spring Security can provide a generated login page depending on configuration.

Do not make `/login` also require `authenticated()`: the browser may fall into a `/login` → `/login` redirect loop. If the browser is already logged in but lacks permissions, redirecting back to the login page only causes confusion.

### 5.2. Basic Login

`BasicAuthenticationEntryPoint` tells the HTTP client that it needs to send Basic credentials:

```java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
```

This is also a snippet within a chain and requires importing `org.springframework.security.config.Customizer`. With an explicitly declared SecurityFilterChain, configure the Basic mechanism explicitly rather than relying on defaults from another Spring Boot application.

Some browsers show a password dialog when receiving a Basic challenge; some `XMLHttpRequest` mechanisms handle it differently to avoid the dialog. Do not treat an easily spoofable client header as proof of being authenticated.

### 5.3. Bearer Resource Server

`BearerTokenAuthenticationEntryPoint` is built into Spring Security for OAuth2 Resource Server, preserving error responses according to Bearer semantics (RFC 6750). Invalid/expired tokens can return `invalid_token`, while valid tokens with insufficient scope are usually handled by `BearerTokenAccessDeniedHandler`. Do not pass `authException.getMessage()` verbatim into `error_description` or JSON: it can expose the issuer, signature errors, internal URLs, user details, and configuration information.

### 5.4. DelegatingAuthenticationEntryPoint

`DelegatingAuthenticationEntryPoint` can select the response endpoint via `RequestMatcher` (for example, APIs receive 401, browsers receive a redirect). For systems with clear route boundaries, **two separate SecurityFilterChains** are usually easier to operate: an API chain matching `/api/**` and a browser chain as fallback. Using `Accept: application/json` or `X-Requested-With` to guess the authentication scheme should not be the sole trusted mechanism for dispatching.

## 6. Spring Boot 3 / Spring Security 6: Separating REST API and Browser UI Configuration

Combined example:

- `/api/**` is an API using JWT bearer in the `Authorization` header, stateless.
- Other routes are web browser session + form login.

The two mechanisms use **two `SecurityFilterChain` beans** with explicit ordering. As a result, the API does not return 302 HTML when the client expects a Bearer challenge.

### 6.1. Gradle Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

For real password login, you must add an appropriate `UserDetailsService` / user repository / `PasswordEncoder`. A JWT resource server needs a trusted issuer/JWK to validate tokens.

### 6.2. application.yml for JWT

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: https://api.example.org
```

Verify **signature, issuer, audience, exp/nbf**, and authorities/scopes according to policy. Do not accept an ID Token intended for a client as an API access token just because it is a JWT. Source the issuer/JWK and expected audience from trusted configuration; do not disable validation just to make 401s go away.

### 6.3. Complete Configuration-Level SecurityFilterChain

File `src/main/java/com/example/security/MixedSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().authenticated())
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            // Only when the API does NOT use cookie/session authentication.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // CSRF remains enabled for browser forms.
        return http.build();
    }
}
```

**How it works and limitations:**

1. Spring picks **the first matching chain**. `@Order(1)` with `securityMatcher("/api/**")` separates the API from the browser chain.
2. API requests without a token to protected routes receive a Bearer challenge instead of a form redirect. If an invalid token is sent to a `permitAll` endpoint, the authentication filter may still reject it before authorization; `permitAll` does not disable all filters.
3. `SCOPE_admin` here is an authority derived from JWT scopes under the default mapping; if the token lacks the scope, a 403 is returned rather than issuing new credentials.
4. `STATELESS` means Security does not use a session to retrieve Authentication for the API. Disabling CSRF in that chain is **only appropriate for pure Bearer-header APIs that do not rely on cookies/automatic credentials**. If an API uses browser sessions/cookies, CSRF must be kept/designed.
5. The browser uses form login with SecurityContext/session and CSRF as configured.
6. Requires `@SpringBootApplication`, endpoints, a JWT decoder/issuer, a user store/login provider, and a real HTTP server. The configuration file cannot run standalone with `javac`.
7. When adding `/api` without a trailing slash or multiple Servlet mappings, verify matchers so requests do not fall through to the browser chain. Do not assume every `/**` is equivalent to an exact path.

**Illustrative HTTP responses** for the configuration above:

```http
GET /api/orders HTTP/1.1
Host: app.example.org

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

```http
GET /profile HTTP/1.1
Host: app.example.org

HTTP/1.1 302 Found
Location: /login
```

The examples combine request and response to highlight the difference, rather than representing a complete wire-format HTTP exchange. A real `Location` may be an absolute URL and depends on proxy/context path settings.

## 7. HTTP Basic: Enabling Explicitly Only When Truly Needed

For internal APIs using Basic, the appropriate mechanism differs from Bearer. Example configuring an independent chain for `/internal-basic/**`:

```java
@Bean
@Order(1)
SecurityFilterChain basicChain(HttpSecurity http)
        throws Exception {

    http
        .securityMatcher("/internal-basic/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

The above is a **snippet** inside a `@Configuration` class that already has imports and dependencies, and needs ordering coordinated if other chains exist. A corresponding `AuthenticationProvider` / `UserDetailsService` is required for password login.

Flow:

```text
1. Client GET /internal-basic/report (no credentials)
2. Server: 401 + WWW-Authenticate: Basic realm="..."
3. Client sends Authorization: Basic <base64(username:password)>
4. BasicAuthenticationFilter verifies via AuthenticationManager
5. Authentication succeeds with sufficient permissions: request continues
```

Base64 is encoding, not secret protection. TLS, Authorization redaction, rate-limiting, strong password policies, and appropriate client secrets are mandatory. Basic can be a simple internal solution, but it is not a default replacement for OAuth Bearer across all APIs.

## 8. EntryPoint, FailureHandler, and AccessDeniedHandler Are Not the Same

| Component | Responsibility | Typical Call Site |
|---|---|---|
| `AuthenticationEntryPoint` | Requests or initiates authentication | Anonymous access to protected resource, invalid Basic/Bearer |
| `AuthenticationFailureHandler` | Handles **a login attempt** that was submitted and failed | Form POST login with wrong password |
| `AuthenticationSuccessHandler` | Redirects or processes post-successful login | Saved request redirect, login audit |
| `AccessDeniedHandler` | Handles permission denied for an authenticated principal | 403 missing role/scope/ownership |
| `AuthenticationProvider` | Verifies credentials and builds Authentication | PasswordEncoder, JwtDecoder/introspection |
| `RequestCache` | Saves the web destination the user wanted before login | HttpSessionRequestCache for forms, NullRequestCache for APIs |

Seeing `/admin` return 403 **does not mean EntryPoint is misconfigured**. Authentication may have succeeded, yet an authority is missing. Check `authorizeHttpRequests`, method security, domain tenant/ownership checks, and `AccessDeniedHandler`. Conversely, an API missing a token returning 302 HTML login may mean it matched the wrong web chain or form entry point.

### 8.1. Why Does @ControllerAdvice Usually Not Control 401?

Many 401/403 responses occur in Servlet security filters **before DispatcherServlet invokes a controller**. MVC's `@ControllerAdvice` / `@ExceptionHandler` does not automatically catch security exceptions already handled by filters. Place authentication response policy in `exceptionHandling(...)`, `httpBasic(...)`, or `oauth2ResourceServer(...)` on the proper security chain.

### 8.2. Custom Filters and Exception-Catching Scope

A custom filter placed **before** `ExceptionTranslationFilter` can throw an error before the exception translation filter wraps the call. If you write a custom authentication filter, use proper failure handling/entry points rather than throwing `RuntimeException("bad token")` and assuming the framework will return 401 on its own. Check filter order and response commit state to avoid writing a response twice.

## 9. Customizing JSON 401 While Preserving the Bearer Challenge

APIs sometimes want a consistently formatted JSON body; however, the following snippet is **wrong** if used alone to replace the Bearer EntryPoint:

```java
// WRONG: loses WWW-Authenticate Bearer information.
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
```

Safer approach: **delegate status/headers to Spring Security** and only add a secret-free body. Example `JsonBearerEntryPoint` class in Spring Security 6.x (requires the OAuth2 Resource Server starter):

```java
package com.example.security;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;

public final class JsonBearerEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException error)
            throws IOException, ServletException {

        // Preserves exact WWW-Authenticate and status per BearerTokenError.
        delegate.commence(request, response, error);

        if (response.isCommitted()) {
            return;
        }

        int status = response.getStatus();
        String title = (status == 400)
            ? "Bad Request" : "Unauthorized";

        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");
        response.getWriter().write(
            "{\"type\":\"about:blank\",\"title\":\""
            + title + "\",\"status\":" + status + "}");
    }
}
```

This is a **Spring integration snippet**, not a standalone app runnable with `javac`. The class intentionally **does not** echo `error.getMessage()` to the client. The delegate has already decided the status based on `BearerTokenError` if present; the client still receives the challenge.

Attach it to `oauth2ResourceServer` on the API chain:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationEntryPoint(new JsonBearerEntryPoint())
    .jwt(Customizer.withDefaults()))
```

If you want the `ExceptionTranslationFilter` branch to also use the JSON EntryPoint, configure `exceptionHandling(ex -> ex.authenticationEntryPoint(...))` accordingly on the **API chain**. Verify both the **missing token** path and the **invalid token** path with integration tests, as errors may flow through different handlers.

For **403** on a Bearer API, `BearerTokenAccessDeniedHandler` can provide `WWW-Authenticate` with `insufficient_scope` when appropriate. Do not overwrite it with a JSON 401 merely because the codebase wants uniform bodies. If adding a custom 403 body, delegate to AccessDeniedHandler and preserve the headers/status it sets.

### 9.1. HttpStatusEntryPoint Is Not a Default Bearer EntryPoint

`HttpStatusEntryPoint` can produce a fixed status such as 401:

```java
.exceptionHandling(ex -> ex.authenticationEntryPoint(
    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
```

Imports in the project:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
```

This snippet is suitable in certain **custom protocols**, but it is **not sufficient** to produce `WWW-Authenticate` for Basic/Bearer. HTTP authentication under RFC 9110 requires a challenge on 401; Bearer RFC 6750 also includes `invalid_token`, `insufficient_scope`, and other states. Prefer the scheme-appropriate entry point or implement the full contract yourself.

## 10. Designing Clear API Errors for Clients

**Do not collapse every case into a single "Unauthorized" message.** Clients need to distinguish missing credentials, expired tokens, insufficient permissions, CSRF failures, and application errors:

- `401 Bearer`: missing/invalid token. The frontend may prompt for login or perform one controlled refresh under the OAuth grant.
- `403`: token is verified but permissions are insufficient. Do not infinitely auto-refresh or "retry" with another account just to bypass policy.
- `400 invalid_request`: malformed Bearer usage must be fixed on the client.
- `302 /login`: intended for browser form flows; do not force REST/mobile clients to follow HTML login just to get a 200.
- `429 Too Many Requests`: rate limiting for login/token brute-force; do not pretend it is 401 forever.
- `503` or operational status per policy: the authentication system/IdP dependency is experiencing an outage; do not fail open, and do not claim credentials are wrong simply because an introspection service timed out.

When using Problem Details JSON, keep the actual status consistent across body and header, do not reflect raw exceptions or secrets, and ensure an appropriate `Cache-Control`.

### 10.1. Login URLs and Redirects Must Be Safe

A login entry point may redirect based on the configured `/login`. Do not use a raw `next` parameter or `Host`/`X-Forwarded-Host` as the login origin without a trust boundary; attackers can craft spoofed URLs to harvest credentials. Behind proxies, manage a canonical HTTPS origin and accept forwarded headers only from trusted proxies. Saved request redirects after login should only target verified paths/domains.

Never place raw Bearer access tokens, Basic passwords, refresh tokens, or cookie values in `Location`, query strings, or logs; URLs can be recorded by browser history, referrers, and proxies.

### 10.2. CORS Preflight and CSRF

Browser CORS preflight `OPTIONS` requests typically do not send bearer credentials. If API security blocks with 401 before CORS runs, the frontend sees a CORS error instead of the auth policy. Configure CORS with explicit allowed origins/methods/headers in Spring Security; do not open `permitAll("/api/**")` or disable security app-wide to fix it.

CSRF and CORS are different: browser session/cookie authentication requires a CSRF policy. For APIs that **only** use `Authorization: Bearer` manually attached by the client with no automatically sent cookies, different CSRF handling may be chosen; base this on your threat model, rather than mechanically disabling CSRF across every chain.

## 11. Standalone Java 17: Simulating Response Selection

The following program runs on Java 17 and **does not use Spring**. It assumes a verifier has already classified the credential as `MISSING`/`INVALID`/`VALID_BUT_DENIED`/`VALID_ALLOWED`, simulating only how the response/challenge is chosen. It **does not actually verify JWTs, passwords, sessions, or roles**.

Save file `AuthenticationEntryPointDemo.java`:

```java
public class AuthenticationEntryPointDemo {

    enum Scheme { FORM, BASIC, BEARER }
    enum State { MISSING, INVALID, VALID_BUT_DENIED, VALID_ALLOWED }

    record Response(int status, String detail) {
        @Override
        public String toString() {
            return status + " " + detail;
        }
    }

    static Response respond(Scheme scheme, State state) {
        if (state == State.VALID_ALLOWED) {
            return new Response(200, "OK");
        }

        if (state == State.VALID_BUT_DENIED) {
            return scheme == Scheme.BEARER
                ? new Response(403,
                    "WWW-Authenticate=Bearer error=\"insufficient_scope\"")
                : new Response(403, "Forbidden");
        }

        return switch (scheme) {
            case FORM -> new Response(302, "Location=/login");
            case BASIC -> new Response(401,
                "WWW-Authenticate=Basic realm=\"study\"");
            case BEARER -> state == State.MISSING
                ? new Response(401, "WWW-Authenticate=Bearer")
                : new Response(401,
                    "WWW-Authenticate=Bearer error=\"invalid_token\"");
        };
    }

    public static void main(String[] args) {
        System.out.println("FORM missing: " +
            respond(Scheme.FORM, State.MISSING));
        System.out.println("BASIC missing: " +
            respond(Scheme.BASIC, State.MISSING));
        System.out.println("BEARER missing: " +
            respond(Scheme.BEARER, State.MISSING));
        System.out.println("BEARER invalid: " +
            respond(Scheme.BEARER, State.INVALID));
        System.out.println("BEARER denied: " +
            respond(Scheme.BEARER, State.VALID_BUT_DENIED));
        System.out.println("FORM denied: " +
            respond(Scheme.FORM, State.VALID_BUT_DENIED));
        System.out.println("BASIC allowed: " +
            respond(Scheme.BASIC, State.VALID_ALLOWED));
    }
}
```

Commands:

```bash
javac AuthenticationEntryPointDemo.java
java AuthenticationEntryPointDemo
```

Exact stdout:

```text
FORM missing: 302 Location=/login
BASIC missing: 401 WWW-Authenticate=Basic realm="study"
BEARER missing: 401 WWW-Authenticate=Bearer
BEARER invalid: 401 WWW-Authenticate=Bearer error="invalid_token"
BEARER denied: 403 WWW-Authenticate=Bearer error="insufficient_scope"
FORM denied: 403 Forbidden
BASIC allowed: 200 OK
```

**Explanation:** Unauthenticated FORM is redirected; Basic/Bearer return challenges; bad tokens receive `invalid_token`; callers with valid credentials lacking scope receive 403; form users lacking permission also receive 403. The 200 line simulates **the normal controller continuing**, not EntryPoint returning 200.

**Limitations:** the demo does not simulate `ExceptionTranslationFilter`/RequestCache/anonymous/remember-me, Basic filters, JWT signatures, CORS, CSRF, or real Spring Security. In production, rely on the framework and proper validators instead of copying this `switch` pattern into a filter.

## 12. Testing the Flow Properly with curl

Use HTTPS and a real IdP in test environments. These are reference commands; do not send real credentials to example domains:

```bash
# No token: expect 401 + WWW-Authenticate Bearer.
curl -i https://api.example.org/api/orders

# Invalid token: expect 401 + Bearer invalid_token.
curl -i -H 'Authorization: Bearer not-a-real-token' \
  https://api.example.org/api/orders

# Valid token, missing scope: expect 403.
curl -i -H 'Authorization: Bearer TEST_READ_ONLY_TOKEN' \
  https://api.example.org/api/admin/reports

# Browser without session: may receive 302 Location /login.
curl -i https://app.example.org/profile
```

A real deployed API, endpoint, issuer/JWKS, and valid token are needed for the third case. If you use `curl -L`, the client automatically follows redirects, causing you to see the `200` of the final login page and miss the initial `302`. When testing an entry point, first use `curl -i` **without** enabling redirect following.

## 13. Testing Spring Security and Failure Paths

You can use Spring Security Test/MockMvc in Spring Boot:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
```

Snippet inside a test class that has `MockMvc mvc`, endpoints, and a test application context:

```java
mvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "WWW-Authenticate",
        org.hamcrest.Matchers.startsWith("Bearer")));

mvc.perform(get("/profile"))
    .andExpect(status().is3xxRedirection());
```

Optional test imports:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

To simulate an authenticated bearer lacking a scope with `spring-security-test`:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_read"))))
    .andExpect(status().isForbidden());
```

Additional imports:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

These are **test snippets**, not standalone Java files. `jwt()` is a testing postprocessor, not a generator of IdP-signed JWTs. The test application context may still need a `JwtDecoder` test bean or appropriate issuer config to start up. Beyond mock tests, integration-test real JWTs (signature/`iss`/`aud`/`exp`) against a test IdP/JWK.

### 13.1. Mandatory Test Case Matrix

| Test | Expected Result |
|---|---|
| Anonymous browser calling protected page | 302 to proper login page, no Bearer JSON |
| Authenticated browser lacking role | 403, no login redirect loop |
| Basic client missing credentials | 401 + `WWW-Authenticate: Basic` |
| Basic client wrong password | 401 challenge, no account enumeration |
| Bearer API missing token | 401 + `WWW-Authenticate: Bearer` |
| Bearer API expired token | 401 invalid_token |
| Bearer API forged/wrong issuer/wrong audience JWT | Unauthenticated, typically 401 |
| Bearer API valid token lacking scope | 403; possibly insufficient_scope header |
| Bearer API sufficient scope | Passes filter; business authorization still applies |
| GET /api/public without token | Allowed through even though `/api/**` has a security chain |
| GET /api/public with invalid Bearer | May be rejected by authentication filter; test explicitly |
| Form login POST wrong password | FailureHandler handles it, not confused with EntryPoint |
| Missing CSRF on form POST | Blocked according to CSRF policy |
| Valid API CORS preflight | CORS handled, no erroneous auth challenge |
| Customized JSON Bearer entrypoint | Challenge status/header intact, neutral body |
| Two security chains in reversed order | Test detects API receiving form redirect |
| Login page protecting itself | Test detects 302 loop |
| Saved request redirect to spoofed external URL | Does not redirect to arbitrary external domains |
| Authorization header/cookie in logs | No secrets appear |
| Custom filter throwing exception too early | Clear response and no double write |
| Multiple nodes/proxies | Consistent 401/403/302, no internal host leakage |

### 13.2. Testing the Two Separate 401 Paths

**Path A:** no `Authorization`, `AuthorizationFilter` requires authentication → `ExceptionTranslationFilter` selects EntryPoint.

**Path B:** client sends a Bearer JWT with a bad signature, authentication filter fails immediately → Resource Server's handler/EntryPoint.

If you only test A, custom configuration might still leave B returning an HTML error page, different JSON, or missing `WWW-Authenticate`. Add the **valid token with missing role/scope** case to ensure 403 still goes through AccessDeniedHandler and is not turned into 401.

## 14. Mistakes to Avoid

| Mistake | Consequence | Solution |
|---|---|---|
| Bearer API returns 302 to HTML login | REST client cannot understand it, retry/redirect fails | Separate API chain, Bearer EntryPoint |
| Returning 401 JSON without `WWW-Authenticate` | Violates HTTP challenge semantics | Delegate to Basic/Bearer EntryPoint |
| Authenticated user lacking role gets 401 | Client retries login endlessly | Proper 403/AccessDeniedHandler and policy |
| Anonymous API call gets 403 without challenge | Client does not know how to authenticate | 401 EntryPoint + scheme |
| Form POST wrong password handled by wrong handler | Incorrect UX/security flow | AuthenticationFailureHandler |
| Customizing in `@ControllerAdvice` | Filter errors occur before MVC, has no effect | Configure handlers in SecurityFilterChain |
| Sending raw `authException.getMessage()` to client | Leaks issuer/token/internal config | Neutral error codes in body, redacted audit logs |
| Using `HttpStatusEntryPoint` instead of Bearer delegate | Loses challenge and error semantics | `BearerTokenAuthenticationEntryPoint` |
| `/login` requires authenticated | Redirect loop | PermitAll login and assets |
| Relying on Accept header to pick scheme | Altered by client/proxy, violates contract | Pin to API path/chain |
| Using `permitAll` to "skip all filters" | Invalid bearer on public route still 401s | Understand filter order, test intentional behavior |
| Disabling CSRF globally to make API work | Web cookie endpoints vulnerable to CSRF | Split chains, disable only per threat model |
| Skipping JWT audience verification | Tokens issued for other APIs get accepted | Validate issuer, audience, signature, time |
| Writing tokens into URLs/logs/redirects | Leaks bearer credentials | Authorization header over TLS, redaction |
| Missing per-resource permission checks | Valid token still allows BOLA/IDOR | Domain/tenant/ownership authorization |

## 15. Production Deployment Checklist

1. Clearly determine whether clients use form, Basic, OAuth Bearer, or a custom challenge.
2. Pick the EntryPoint matching the scheme; preserve `WWW-Authenticate` on 401 responses.
3. Define 401 for missing/invalid authentication, 403 for permission denied, and 302 for form redirect.
4. Understand how `ExceptionTranslationFilter` differs from authentication filters/FailureHandler.
5. Configure `SecurityFilterChain` and `@Order` so APIs are not accidentally caught by browser fallback.
6. Keep CSRF on web sessions, consider stateless APIs separately; handle CORS preflight properly.
7. Configure JWT decoder issuer/audience/signature/time; never use EntryPoint to "fix" bad tokens.
8. Control `/login`, request cache, and saved redirects; prevent open redirects and login loops.
9. Never log Authorization/JWT/passwords, and never expose exception details externally.
10. Test 401 missing token **and** 401 invalid token, plus 403 missing scope/role on every release.
11. Use `curl -i` without following redirects when debugging, inspecting both `WWW-Authenticate` and `Location`.
12. Maintain integration tests with actual IdP/keys and security filters, not just mocked unit tests.
13. Monitor 401/403 metrics by API route and secret-scrubbed error reason.
14. When upgrading Spring Security, check version-specific defaults and keep running protocol tests.

## 16. Self-Check Questions

**1.** Does `AuthenticationEntryPoint` verify passwords or JWT signatures?  
**Answer:** No, it produces the HTTP response requesting credentials. AuthenticationProvider/filters/decoders perform verification.

**2.** An unauthenticated browser calls `GET /private`; what is a reasonable response?  
**Answer:** With form login, `302 Location: /login`.

**3.** A REST bearer API request is missing Authorization; what is a reasonable response?  
**Answer:** `401 WWW-Authenticate: Bearer`.

**4.** A token is valid but lacks a scope; should EntryPoint be called to re-authenticate?  
**Answer:** No; normally AccessDeniedHandler returns 403 and may include `insufficient_scope`.

**5.** Why does `Authentication != null` not prove a user actually logged in?  
**Answer:** `AnonymousAuthenticationToken` and remember-me/partial auth mechanisms can be represented in the security context; you must rely on appropriate policy/AuthenticationTrustResolver.

**6.** Does submitting a wrong password on form login always go through `ExceptionTranslationFilter`?  
**Answer:** No. `UsernamePasswordAuthenticationFilter` normally uses `AuthenticationFailureHandler`.

**7.** Why can a syntactically valid JSON 401 still be protocol-incorrect?  
**Answer:** If it is HTTP Basic/Bearer without `WWW-Authenticate`, the client lacks the authentication challenge required by HTTP.

**8.** How can `curl -L` mislead you about a 302 status?  
**Answer:** It follows the redirect to the login page and shows only the final response, which may be 200; use `curl -i` to inspect the original status.

**9.** Does `permitAll("/api/public")` always bypass bearer validation?  
**Answer:** No, the auth filter may process a proactively sent token and reject a malformed/invalid token before authorization.

**10.** When needing different behavior for JSON APIs and browsers, should you check `Accept: application/json` to decide who is authenticated?  
**Answer:** No. Separate security chains cleanly and verify via authentication proof; Accept only describes representation format.

## References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationEntryPoint`, `AuthenticationManager`, and authentication filters.
- [Spring Security — Servlet Architecture/ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html): security exception translation, `RequestCache`, `AccessDeniedHandler`.
- [Spring Security 6.5 — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html): `commence` and HTTP response contract.
- [Spring Security 6.5 — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): `BasicAuthenticationEntryPoint` and filter failure.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `LoginUrlAuthenticationEntryPoint`, login failures, and success.
- [Spring Security — OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): bearer challenge/error responses.
- [Spring Security 6.5 — DelegatingAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationEntryPoint.html): selecting entry points with `RequestMatcher`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): `401`, `WWW-Authenticate`, and `403`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): `invalid_request`, `invalid_token`, `insufficient_scope`.
