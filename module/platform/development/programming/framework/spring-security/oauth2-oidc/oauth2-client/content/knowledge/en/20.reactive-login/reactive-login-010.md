# 20.10. ServerAuthenticationSuccessHandler and ServerAuthenticationFailureHandler

## 1. What Do These Two Extension Points Decide After Reactive OAuth2/OIDC Login?

In a **Spring Security OAuth 2.0 OIDC Client** application built on **Spring WebFlux**, users typically initiate login by being redirected to an OpenID Provider (OP), then return to the application with an authorization code. Spring Security handles the transaction, exchanges the code at the Token Endpoint, verifies the ID Token per OpenID Connect, and builds an `Authentication` for the user.

At the end of this process, the application must decide:

- **If authentication succeeds:** send the user back to the page they requested before login, navigate to a dashboard, record an audit event, or run a valid post-login task.
- **If authentication fails:** direct the user to a safe error page, emit a categorized metric, and avoid leaking tokens, authorization codes, or Identity Provider error details.

On the **Reactive Security / WebFlux stack**, the two direct extension points are:

1. **`ServerAuthenticationSuccessHandler`** — handles a **successful authentication**.
2. **`ServerAuthenticationFailureHandler`** — handles a **failed authentication**.

Both can be configured on `ServerHttpSecurity.oauth2Login(...)`. Both return **`Mono<Void>`** instead of calling Servlet APIs directly to manipulate `HttpServletResponse`.

Example desired portal behavior:

~~~text
User accesses /reports/me (login required)
    -> Spring Security sends to OIDC Provider
    -> Callback /login/oauth2/code/company

If login succeeds:
    -> return to saved /reports/me
    -> or /dashboard if no saved request

If login fails:
    -> /auth/failed
    -> neutral notice page, do not display raw OAuth2 error
~~~

**The goal of this lesson** is to understand their interfaces, position in the OIDC flow, default behavior, how to replace or augment handlers, how to handle reactive chains properly, and how to preserve security context, saved requests, session policies, and security boundaries.

> **Scope:** Focused on a **Reactive WebFlux server** with `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchange`. Do not use Servlet's `HttpSecurity`, `SecurityFilterChain`, `AuthenticationSuccessHandler`, or `HttpServletRequest` in place of the reactive APIs in this lesson.

## 2. Distinguishing Reactive Login and Servlet Login

Spring Security supports both models. The names look similar, yet **they are not the same interfaces**:

| Concept | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Security configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP request/response | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| Authentication filter unit | Servlet filters, e.g. `OAuth2LoginAuthenticationFilter` | WebFilters, e.g. reactive authentication filters |
| Success handler | `AuthenticationSuccessHandler` | **`ServerAuthenticationSuccessHandler`** |
| Failure handler | `AuthenticationFailureHandler` | **`ServerAuthenticationFailureHandler`** |
| Return value | Mutates response via Servlet API | **`Mono<Void>`** representing asynchronous completion |
| Reactive security context | Not Servlet's primary mechanism | `ReactiveSecurityContextHolder` and matching repository |
| Redirect abstraction | `RedirectStrategy` / Servlet response | `ServerRedirectStrategy` / `ServerWebExchange` |

Example of **Servlet code incompatible** with Reactive WebFlux:

~~~java
// Wrong context: Servlet's AuthenticationSuccessHandler.
// Cannot be attached directly to ServerHttpSecurity's oauth2Login.
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
~~~

APIs required in WebFlux:

~~~java
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
~~~

A WebFlux application may use asynchronous HTTP clients, yet the focus here is **inbound authentication on the Reactive server**, not `WebClient`'s OAuth2 filter for outbound APIs.

## 3. Handler Position in the Authorization Code + OIDC Flow

### 3.1. Successful Login Flow

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant App as WebFlux OAuth2/OIDC Client
    participant OP as OpenID Provider
    participant Ctx as Reactive Security Context
    participant H as ServerAuthenticationSuccessHandler
    Browser->>App: GET /reports/me without Authentication
    App-->>Browser: Redirect to /oauth2/authorization/company
    Browser->>OP: Authorization request (state, PKCE, nonce if used)
    OP-->>Browser: Callback code + state
    Browser->>App: GET /login/oauth2/code/company?code=...
    App->>OP: Token Endpoint, exchange authorization code
    OP-->>App: Token response (ID Token, Access Token...)
    App->>App: Verify OIDC and build Authentication
    App->>Ctx: Save/set Authentication per configuration
    App->>H: onAuthenticationSuccess(exchange, authentication)
    H-->>Browser: Redirect to saved request or destination
    Browser->>App: Next request with matching session/cookie
    App-->>Browser: Authorized content
~~~

Exact filter wiring and when the security context is written can vary across versions/configurations, yet **the handler receives success only after Spring Security has constructed a valid `Authentication`**. Never use the handler to replace ID Token verification or `state` correlation.

### 3.2. Failed Login Flow

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant App as WebFlux OAuth2/OIDC Client
    participant OP as OpenID Provider
    participant H as ServerAuthenticationFailureHandler
    Browser->>App: Start OAuth2 Login
    App-->>Browser: Redirect to OP
    OP-->>Browser: Callback with error or invalid code
    Browser->>App: OAuth2 callback
    App->>App: Authentication fails / raises AuthenticationException
    App->>H: onAuthenticationFailure(exchange, exception)
    H-->>Browser: Redirect /auth/failed or controlled response
    Browser->>App: GET /auth/failed
    App-->>Browser: Generic message, containing no credentials
~~~

**Not every HTTP error or abnormal callback necessarily reaches this same handler.** For instance, network errors outside authentication processing, CSRF failures, access denied when already logged in, or exceptions thrown before/after the authentication filter may be handled by other components.

## 4. Contract of ServerAuthenticationSuccessHandler

The interface lives in package:

~~~java
org.springframework.security.web.server.authentication
    .ServerAuthenticationSuccessHandler
~~~

Primary method:

~~~java
Mono<Void> onAuthenticationSuccess(
    WebFilterExchange webFilterExchange,
    Authentication authentication
);
~~~

Related types:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
~~~

### 4.1. What Does webFilterExchange Contain?

`WebFilterExchange` wraps the WebFlux context for the authentication filter, including:

~~~java
ServerWebExchange exchange = webFilterExchange.getExchange();
~~~

From `ServerWebExchange`, you can access the request, response, reactive session, attributes, and HTTP metadata. It is **not an `HttpServletRequest`**.

### 4.2. What Is authentication?

`Authentication` represents the authenticated user. After OIDC Login, it may be an `OAuth2AuthenticationToken` whose principal is an `OidcUser`:

~~~java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

if (authentication instanceof OAuth2AuthenticationToken login) {
    String registrationId = login.getAuthorizedClientRegistrationId();

    if (login.getPrincipal() instanceof OidcUser oidcUser) {
        String subject = oidcUser.getSubject();
        // Use subject per policy; never log full principal/claims.
    }
}
~~~

The snippet assumes `authentication` is the handler's parameter. `OidcUser` holds an ID Token and optionally UserInfo; never obtain an Access Token by treating `getIdToken()` as an Access Token.

### 4.3. Mono<Void> Represents Work to Complete

Example:

~~~java
ServerAuthenticationSuccessHandler handler =
    (webFilterExchange, authentication) ->
        Mono.fromRunnable(() -> {
            // Very lightweight and non-blocking operation, for illustration only.
        });
~~~

In reactive APIs, the handler must **return a `Publisher` representing the entire operation**. Never call `subscribe()` yourself and return `Mono.empty()`, because the framework may treat the handler as finished before auditing or redirecting actually completes.

I/O operations such as calling an R2DBC database or sending an event via a reactive client should be composed with `flatMap`, `then`, or matching operators—never `block()` on the event-loop.

## 5. Contract of ServerAuthenticationFailureHandler

Interface:

~~~java
org.springframework.security.web.server.authentication
    .ServerAuthenticationFailureHandler
~~~

Primary method:

~~~java
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception
);
~~~

Imports:

~~~java
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;
~~~

### 5.1. AuthenticationException Is Not an HTTP Error Response

`AuthenticationException` represents a failure within the authentication pipeline. For OAuth2/OIDC Login, failures can arise from:

- Callback carrying an OAuth2 error returned by the provider.
- Correlation failure against `state` or the saved authorization request.
- Error exchanging the authorization code or invalid token response.
- ID Token verification rejection: signature, issuer, audience, timestamps, or flow-specific nonce.
- User service or authentication policy intentionally rejecting the principal.

**Accurate diagnosis relies on the error type, redacted security logs, and the provider contract.** Never assume every `AuthenticationException` means "wrong user password," because in OIDC Login the app normally neither receives nor checks passwords.

### 5.2. Do Not Expose exception.getMessage() to the Browser

Anti-pattern:

~~~java
// DO NOT USE:
String target = "/login?error=" + exception.getMessage();
~~~

Exception messages can disclose URLs, provider internals, policy names, validation details, or untrusted input. Putting them raw into query strings risks information disclosure, injection, or unwieldy URLs.

Instead, send users to a **fixed error page** such as `/auth/failed`. When error codes are needed for troubleshooting, log categorized metadata internally with a non-sensitive correlation ID.

## 6. OAuth2 Login Defaults on the Reactive Stack

With configuration:

~~~java
.oauth2Login(Customizer.withDefaults())
~~~

Spring Security provides default handlers for OAuth2 Login.

| Scenario | Default Handler | Typical Behavior |
| --- | --- | --- |
| Authentication succeeds | **`RedirectServerAuthenticationSuccessHandler`** | Redirects to saved request if present, otherwise default location `/` |
| Authentication fails | **`RedirectServerAuthenticationFailureHandler`** | Redirects to `/login?error` |

This is the default OAuth2 Login behavior for the matching Spring Security API; applications may customize login pages, request caches, session strategies, or handlers.

### 6.1. RedirectServerAuthenticationSuccessHandler

~~~java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
~~~

Two familiar constructors:

~~~java
new RedirectServerAuthenticationSuccessHandler();
new RedirectServerAuthenticationSuccessHandler("/dashboard");
~~~

**Common pitfall:** `new RedirectServerAuthenticationSuccessHandler("/dashboard")` **does not mean** every user always lands on `/dashboard`. The default handler prioritizes a **saved request** from `ServerRequestCache`, falling back to `/dashboard` only when none exists.

Example:

~~~text
User opens /reports/42 before login
  -> request is saved
  -> login succeeds
  -> redirect to /reports/42

User clicks Login button directly on home page
  -> no saved request
  -> login succeeds
  -> redirect to /dashboard (configured fallback)
~~~

### 6.2. RedirectServerAuthenticationFailureHandler

~~~java
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;

ServerAuthenticationFailureHandler failure =
    new RedirectServerAuthenticationFailureHandler("/auth/failed");
~~~

This handler issues a **redirect** to the configured location. That path must have a matching controller/page or static resource, and must be accessible **while unauthenticated**.

If the error page itself requires authentication, it can trigger a **redirect loop**:

~~~text
OAuth2 Login fails -> /auth/failed
  -> /auth/failed requires authentication
  -> /oauth2/authorization/company
  -> callback error -> /auth/failed -> ...
~~~

## 7. Basic Configuration with ServerHttpSecurity

### 7.1. Spring Boot WebFlux Dependencies

For **Spring Boot 3.x / Spring Security 6.x**, Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

In Spring Boot 4.x, starter/security module splits changed; select WebFlux and OAuth2 Client starters matching the **BOM and docs for your active Boot version**. Never arbitrarily mix Spring Security 6.x and 7.x.

### 7.2. application.yml for OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

URLs and registrations are illustrative. A real OP must publish valid discovery metadata, allow the registered redirect URI, and supply claims/scopes per contract.

`openid` indicates OIDC Login; `profile`/`email` request additional claims without **automatically** guaranteeing the OP returns all of them. Secrets must never be hardcoded in source control.

### 7.3. SecurityWebFilterChain with Post-Login Redirect

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/auth/failed", "/error")
                    .permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(
                    new RedirectServerAuthenticationSuccessHandler(
                        "/dashboard"))
                .authenticationFailureHandler(
                    new RedirectServerAuthenticationFailureHandler(
                        "/auth/failed")))
            .build();
    }
}
~~~

**What happens:**

1. OAuth2/OIDC Login handles the callback via reactive security filters.
2. When authentication succeeds, the success handler redirects to the **saved request** if present, or `/dashboard`.
3. When authentication fails and the filter routes the error to the failure handler, the browser redirects to `/auth/failed`.
4. `/auth/failed` is permitted for unauthenticated access.

This is a **complete `SecurityWebFilterChain` alternative** to other examples in this lesson. If the application has multiple chains, ensure the chain declaring `oauth2Login` actually matches the OAuth2 callback and related requests.

### 7.4. Minimal Public Error Page

~~~java
package com.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AuthenticationErrorController {

    @GetMapping("/auth/failed")
    public Mono<String> failed() {
        return Mono.just(
            "Unable to complete login. Please try again or contact support.");
    }
}
~~~

This page never puts raw OAuth2 exceptions, authorization codes, ID Tokens, Access Tokens, `state`, or session IDs in the response. In a real UI, use an HTML template with appropriate support guidance.

## 8. Configuring Beans Instead of Inline Handler Instantiation

When handlers need to be reused, mocked, or tested separately, declare them as beans:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveLoginHandlerConfig {

    @Bean
    ServerAuthenticationSuccessHandler loginSuccessHandler() {
        return new RedirectServerAuthenticationSuccessHandler("/dashboard");
    }

    @Bean
    ServerAuthenticationFailureHandler loginFailureHandler() {
        return new RedirectServerAuthenticationFailureHandler("/auth/failed");
    }

    @Bean
    SecurityWebFilterChain appWebFilterChain(
            ServerHttpSecurity http,
            ServerAuthenticationSuccessHandler loginSuccessHandler,
            ServerAuthenticationFailureHandler loginFailureHandler) {

        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/", "/login", "/auth/failed").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(loginSuccessHandler)
                .authenticationFailureHandler(loginFailureHandler))
            .build();
    }
}
~~~

This is an **alternative** to `ReactiveSecurityConfig` in Section 7; do not copy both configurations if they match all requests.

Extracting beans helps when testing redirect logic or injecting an audit dependency. However, merely declaring a bean **does not guarantee the framework uses it automatically for every authentication mechanism**; explicitly wire it into `oauth2Login(...)` or the corresponding filter configuration.

## 9. Writing a Custom Success Handler: Audit Then Redirect

Scenario: after OIDC login succeeds, the application wants to record an audit event and then follow Spring Security's redirect rules.

Principles:

- **Never block** the event-loop with JDBC or blocking HTTP calls.
- **Never subscribe manually**; return the `Mono<Void>` chain so the framework manages completion.
- **Never log the full `Authentication`/principal**, tokens, or sensitive claims.
- **Keep default redirect/saved-request behavior** if the product still expects it.
- If auditing fails, enforce an explicit policy: is auditing mandatory or best-effort telemetry?

### 9.1. Illustrative Audit Interface

~~~java
package com.example.security;

import reactor.core.publisher.Mono;

public interface LoginAuditRecorder {

    // Never pass tokens, client secrets, or raw error descriptions.
    Mono<Void> loginSucceeded(String registrationId);

    Mono<Void> loginFailed(String errorCategory);
}
~~~

This is an **application-defined interface**, not a built-in Spring Security class. Implementations can write audit entries using a reactive database driver or event publisher, managing throughput, availability, and retention.

### 9.2. Success Handler Preserving Default Redirect Logic

~~~java
package com.example.security;

import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import reactor.core.publisher.Mono;

public final class ReactiveLoginHandlers {

    private ReactiveLoginHandlers() {
    }

    public static ServerAuthenticationSuccessHandler success(
            LoginAuditRecorder audit) {

        RedirectServerAuthenticationSuccessHandler redirect =
            new RedirectServerAuthenticationSuccessHandler("/dashboard");

        return (webFilterExchange, authentication) -> {
            String registrationId = "unknown";

            if (authentication instanceof OAuth2AuthenticationToken oauth2) {
                registrationId =
                    oauth2.getAuthorizedClientRegistrationId();
            }

            return audit.loginSucceeded(registrationId)
                .onErrorResume(auditError -> Mono.empty())
                .then(redirect.onAuthenticationSuccess(
                    webFilterExchange, authentication));
        };
    }
}
~~~

**How to read this:**

1. Extracts `registrationId` from `OAuth2AuthenticationToken` when present.
2. Invokes the audit recorder via `Mono<Void>` without exposing tokens.
3. In this example, an audit error is ignored so login proceeds; that reflects a **best-effort audit policy**, which may not fit every organization.
4. Once auditing completes or is skipped, `then(...)` runs the redirect handler.
5. The redirect handler still prioritizes any saved request.

If your organization requires **mandatory auditing before completing a login session**, never silently swallow failures with `onErrorResume(... -> Mono.empty())`; design resilient failure handling and consistency rules, including when authentication succeeded yet auditing failed.

### 9.3. Wiring into oauth2Login

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        LoginAuditRecorder audit) {

    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/", "/auth/failed").permitAll()
            .anyExchange().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .authenticationSuccessHandler(
                ReactiveLoginHandlers.success(audit))
            .authenticationFailureHandler(
                new RedirectServerAuthenticationFailureHandler(
                    "/auth/failed")))
        .build();
}
~~~

This is an **alternative configuration method**, placed inside a `@Configuration` class with the imports from earlier sections; do not add it alongside another chain matching all requests.

## 10. Writing a Custom Failure Handler: Safe Error Categorization

On login failure, the app wants to record metrics like:

~~~text
event=oidc_login_failed
registration=company
category=provider_rejected_or_validation_failed
correlation_id=internal-a83f
~~~

Never log raw authorization codes, token responses, client secrets, or raw `exception.getMessage()`.

### 10.1. Categorizing Using Approved Labels

`OAuth2AuthenticationException` may carry an `OAuth2Error` with an `errorCode`. However, **error codes from external systems may fall outside the set your application expects**.

A safe categorization helper:

~~~java
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

public static String safeCategory(AuthenticationException exception) {
    if (!(exception instanceof OAuth2AuthenticationException oauth2)) {
        return "authentication_failed";
    }

    String code = oauth2.getError().getErrorCode();

    return switch (code) {
        case "access_denied" -> "provider_access_denied";
        case "invalid_client" -> "client_configuration";
        case "invalid_grant" -> "code_or_token_grant_rejected";
        case "invalid_request" -> "invalid_request";
        default -> "oidc_authentication_failed";
    };
}
~~~

This is an **illustrative helper** for a utility class (Java 17+). Handle `null` if your integration allows missing error codes rather than assuming every error matches the spec.

Codes such as `invalid_client` or `invalid_grant` do not always surface verbatim in `OAuth2AuthenticationException` across every provider/filter; some errors are wrapped or translated into other exception types. This is purely a **classification** step—never a substitute for investigation, and not guaranteed error names across all versions.

### 10.2. Failure Handler Redirecting Without Leaking Details

~~~java
package com.example.security;

import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

public final class ReactiveLoginFailures {

    private ReactiveLoginFailures() {
    }

    public static ServerAuthenticationFailureHandler failure(
            LoginAuditRecorder audit) {

        RedirectServerAuthenticationFailureHandler redirect =
            new RedirectServerAuthenticationFailureHandler("/auth/failed");

        return (webFilterExchange, exception) -> {
            String category = categoryOf(exception);

            return audit.loginFailed(category)
                .onErrorResume(auditError -> Mono.empty())
                .then(redirect.onAuthenticationFailure(
                    webFilterExchange, exception));
        };
    }

    private static String categoryOf(AuthenticationException exception) {
        if (exception instanceof OAuth2AuthenticationException oauth2) {
            String code = oauth2.getError().getErrorCode();
            if ("access_denied".equals(code)) {
                return "provider_access_denied";
            }
            if ("invalid_client".equals(code)) {
                return "client_configuration";
            }
            if ("invalid_grant".equals(code)) {
                return "grant_rejected";
            }
        }
        return "authentication_failed";
    }
}
~~~

`ReactiveLoginFailures.failure(audit)` can be wired via:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authenticationFailureHandler(
        ReactiveLoginFailures.failure(audit)))
~~~

Here, audit errors do not block the redirect. **Do not put the category into the URL** unless the product intentionally defines controlled public error codes. The error page can always show a generic message while internal logs carry a correlation ID.

### 10.3. Why Not Send Exception Details in Query Strings?

Anti-pattern:

~~~text
/auth/failed?message=invalid_nonce_for_user_xxx
~~~

Query URLs can appear in:

- Browser history.
- Reverse proxy access logs.
- Observability/tracing systems.
- Screenshots or user-shared links.
- Certain referrer headers if misconfigured.

**Never put credentials or detailed authentication internals into URLs for debugging convenience.** Write safe audit records and show a separate support reference ID if needed.

## 11. Customizing Redirects and Saved Requests

### 11.1. RedirectServerAuthenticationSuccessHandler Prioritizes Saved Requests

~~~java
new RedirectServerAuthenticationSuccessHandler("/dashboard")
~~~

fits when you want:

~~~text
Saved request exists -> return to the URL the user wanted to access
No saved request     -> /dashboard
~~~

`RedirectServerAuthenticationSuccessHandler` uses `WebSessionServerRequestCache` by default and lets you swap `ServerRequestCache` via `setRequestCache(...)`.

If the app spans multiple domains, reverse proxies, or URL rewrites, verify the saved request target stays within the **proper origin/trust boundary**.

### 11.2. When You Always Want a Fixed Destination Page

Do not assume passing `"/dashboard"` to the constructor ignores saved requests. If business logic genuinely wants to **bypass the saved request**, use `ServerRedirectStrategy`:

~~~java
import java.net.URI;
import org.springframework.security.web.server.DefaultServerRedirectStrategy;
import org.springframework.security.web.server.ServerRedirectStrategy;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

ServerRedirectStrategy redirect = new DefaultServerRedirectStrategy();

ServerAuthenticationSuccessHandler dashboardOnly =
    (webFilterExchange, authentication) ->
        redirect.sendRedirect(
            webFilterExchange.getExchange(),
            URI.create("/dashboard"));
~~~

This performs an **unconditional redirect**. If users expect to return to their original saved destination, keep the default `RedirectServerAuthenticationSuccessHandler` instead of discarding it.

### 11.3. Open Redirect When Reading returnUrl from the Browser

Dangerous design:

~~~java
// ANTI-PATTERN: never let unvalidated input dictate the redirect.
String returnUrl = exchange.getRequest().getQueryParams()
    .getFirst("returnUrl");
return redirect.sendRedirect(exchange, URI.create(returnUrl));
~~~

If an attacker crafts `returnUrl=https://evil.example/collect`, a newly logged-in user gets redirected to an untrusted external site. Other bypasses include protocol-relative paths like `//external-host` or tricky encodings.

To implement custom post-login redirects safely:

1. Accept only **application-relative paths** after normalization and validation.
2. Use a **route allowlist** such as `/dashboard`, `/profile`, `/reports`.
3. Never redirect freely to URIs taken from query strings.
4. Never append tokens or authorization codes to redirect URLs.
5. When carrying a return-to value, persist it server-side tied to the transaction/session with TTL and validation.

## 12. Custom Success Handlers Can Affect Concurrent Session Control

One version-dependent detail to keep in mind: Spring Security Reactive supports **concurrent sessions control** for authentication mechanisms including Form Login and OAuth2 Login. Some session management handlers are registered in the **list of success handlers**.

Replacing the success handler with:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(myHandler))
~~~

can **replace the prior handler list** depending on API semantics. That can prevent concurrent-session management handlers from running as expected.

### 12.1. Handler Lists in Spring Security 6.3+

Spring Security versions supporting the overload:

~~~java
authenticationSuccessHandler(
    Consumer<List<ServerAuthenticationSuccessHandler>> handlersConsumer)
~~~

allow **appending/customizing** handlers without wiping out existing configuration.

Formal example:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(handlers ->
        handlers.add(myAdditionalSuccessHandler)))
~~~

This assumes `myAdditionalSuccessHandler` is an already-constructed `ServerAuthenticationSuccessHandler`. Use the API matching your **active Spring Security version**; this overload was introduced in the 6.3 line.

**Mind the order:** with multiple handlers, know which ones manage sessions and which one redirects/commits the response. Avoid adding a second handler that also writes or redirects when a redirect handler is already in the list.

### 12.2. When to Wrap vs. Use the Handler List?

| Need | Approach to Evaluate |
| --- | --- |
| Only change post-login fallback URL | `RedirectServerAuthenticationSuccessHandler` |
| Log an audit event then redirect | Wrapper returning `audit.then(redirect.onAuthenticationSuccess(...))` |
| Preserve all framework-configured handlers | Append to the list per 6.3+ API and control ordering |
| Concurrent session control enabled | Verify the custom handler does not drop session-control/registration hooks |
| Need JSON response instead of redirect | Different handler matching the authentication mechanism/API contract |

Never assume "login succeeded" implies "concurrent session limits were enforced" if you replaced the handler without checking session management configuration.

## 13. When Should You Return JSON Instead of Redirecting?

OAuth2/OIDC Authorization Code Login is a **browser redirect flow**. Consequently, redirecting on success/failure fits session-based web applications far better.

Still, some apps need controlled API responses. You can write a `ServerAuthenticationFailureHandler` returning JSON rather than redirecting:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import reactor.core.publisher.Mono;

ServerAuthenticationFailureHandler jsonFailure =
    (webFilterExchange, exception) -> {
        ServerHttpResponse response =
            webFilterExchange.getExchange().getResponse();

        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] payload =
            "{\"error\":\"authentication_failed\"}"
                .getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(payload)));
    };
~~~

Key points:

- The body returns a **fixed error code**, never `exception.getMessage()`.
- `writeWith(...)` returns `Mono<Void>`, obeying the reactive contract.
- Never call `subscribe()` manually or `setComplete()` before the body finishes writing.
- Only **one** handler should set status/body/redirect for a given response.
- Once the response is committed, you cannot switch to a redirect afterward.

**Do not replace browser OAuth2 login defaults with JSON 401 just because the frontend uses AJAX.** Authorization Code Login still requires OP redirects, callbacks, and cookies/sessions; for pure SPAs or mobile apps, choose an explicit OAuth2 Client/BFF architecture.

### 13.1. Distinguishing 401, 403, and 302 in WebFlux Security

| HTTP Response | Typical Context | Component Involved |
| --- | --- | --- |
| `302` to OP/login page | Unauthenticated, needs to start authentication | Authentication entry point / authorization redirect |
| `302` to saved request/dashboard | Authentication succeeded | `ServerAuthenticationSuccessHandler` |
| `302` to `/login?error` | Authentication failed | `ServerAuthenticationFailureHandler` |
| `401` JSON | API authentication policy or custom failure handler | Entry point or failure handler depending on source |
| `403` | Authenticated, lacks permissions | `AccessDeniedHandler` / authorization pipeline |

**An API returning 403 is not an OAuth2 Login authentication failure.** Never tweak `ServerAuthenticationFailureHandler` to fix a `@PreAuthorize` or `authorizeExchange(...).hasRole(...)` denial.

## 14. Authentication Success Differs from Authorized-Client Authorization Success

A reactive app using both OAuth2 Login **and** OAuth2 Client for downstream API calls has two distinct sets of hooks:

| Hook | Layer | Purpose |
| --- | --- | --- |
| **`ServerAuthenticationSuccessHandler`** | Inbound WebFlux authentication | Handles newly logged-in user: redirect/audit/session |
| **`ServerAuthenticationFailureHandler`** | Inbound WebFlux authentication | Handles rejected login attempts |
| `ReactiveOAuth2AuthorizationSuccessHandler` | **`ReactiveOAuth2AuthorizedClientManager`** | Saves/updates `OAuth2AuthorizedClient` after obtaining or refreshing an Access Token |
| `ReactiveOAuth2AuthorizationFailureHandler` | Reactive authorized client manager | Handles token issuance/refresh failures per policy |

Example:

~~~text
User completes OIDC login:
  -> ServerAuthenticationSuccessHandler -> redirect /dashboard

Later, portal calls Reports API via WebClient:
  -> ReactiveOAuth2AuthorizedClientManager.authorize(...)
  -> Token needs refresh
  -> ReactiveOAuth2AuthorizationSuccessHandler -> store new token
~~~

**Never use `ServerAuthenticationSuccessHandler` to refresh Access Tokens** before API calls. A user logs in once, while `WebClient` may refresh tokens multiple times during a session.

### 14.1. Two Types of Principals and Tokens

In OAuth2/OIDC Login:

- The user's `Authentication` confirms **identity** per OIDC/OAuth2 Login.
- `OAuth2AuthorizedClient` holds the Access Token/Refresh Token for a client registration and principal.
- The ID Token authenticates the user to the client; Resource Servers normally expect an **Access Token**.

Never read the ID Token from `OidcUser` and use it as an Access Token simply because the login success handler has access to the principal.

### 14.2. Never Persist Tokens Manually Inside the Login Handler Without Good Reason

Spring Security already provides authorized-client persistence abstractions. If a custom success handler writes:

~~~java
// CONCEPTUAL ANTI-PATTERN: never store tokens in an arbitrary session attribute yourself.
exchange.getSession().map(session -> {
    session.getAttributes().put("userAccessToken", tokenValue);
    return session;
});
~~~

that creates a second token store out of sync with the authorized client manager, risking leaks or stale tokens. Prefer `ServerOAuth2AuthorizedClientRepository` or `ReactiveOAuth2AuthorizedClientService` per your architecture.

## 15. State, Nonce, PKCE, and Handler Boundaries

In the OIDC Authorization Code flow, several checks happen **before success**:

| Mechanism | Function | Can the Handler Replace It? |
| --- | --- | --- |
| `state` | Binds authorization response to initial request; prevents login CSRF / correlation failures | No |
| PKCE `code_verifier` | Binds code exchange to the client that created the challenge | No |
| OIDC `nonce` | Binds ID Token to the authentication request in applicable flows | No |
| ID Token signature/`iss`/`aud`/`exp` | Verifies token came from the right issuer for the right client | No |
| UserInfo `sub` | Matches profile claims against the ID Token identity | No |

### 15.1. Login Handlers Do Not Verify ID Tokens

A success handler runs only after the framework confirms authentication succeeded; it **must never** bypass validation just to redirect faster.

A failure handler decides only how to respond to failure. It **cannot make an invalid-signature ID Token valid** by issuing a 302 instead of raising an error.

### 15.2. Never Turn Failure into Success

Dangerous design:

~~~text
Provider returns invalid_grant or invalid ID Token
  -> custom failure handler catches error
  -> fabricates Authentication with ROLE_USER
  -> redirects to protected page
~~~

This breaks the authentication boundary. Whenever identity cannot be verified, **keep the user unauthenticated** or terminate the flow per valid policy.

### 15.3. OAuth2 Errors Can Come from the Callback

The OP may return:

~~~text
/login/oauth2/code/company?error=access_denied&state=...
~~~

`access_denied` during authorization can simply mean the user declined consent or the OP denied access. Do not assume it means bad credentials/password, and never expose raw `error_description` to the browser.

## 16. SecurityContext, WebSession, and Request Cache

### 16.1. SecurityContext Is Not Saved by Redirect URLs

In WebFlux, the security context is managed via reactive security components, `ReactiveSecurityContextHolder`, and `ServerSecurityContextRepository` per configuration.

~~~text
OIDC Authentication succeeds
  -> Authentication has valid principal
  -> SecurityContext is saved/managed per repository and policy
  -> Success handler redirects
  -> Next browser request carries matching session/cookie
~~~

Writing a handler that only sends 302 must not replace the framework's `SecurityContext` storage configuration. Conversely, if a system is intentionally configured as **stateless**, browser login sessions and subsequent requests must be designed accordingly; the handler does not handle `WebSession` persistence on its own.

### 16.2. What Is the Saved Request For?

Suppose a user visits a protected page:

~~~text
GET /reports/quarterly
  -> unauthenticated
  -> saved in ServerRequestCache
  -> browser performs OIDC Login
  -> success redirects back to /reports/quarterly
~~~

The default `RedirectServerAuthenticationSuccessHandler` uses `WebSessionServerRequestCache`. If a custom handler always redirects to `/dashboard` and ignores the request cache, the "return to where the user left off" UX is lost.

### 16.3. Multiple Tabs and Saved Requests

Within the same browser session, a user might open several tabs and start different authorization requests. Depending on the repository/cache mechanics, the saved request can be overwritten or bounded.

Do not rely on one global `returnUrl` in a cookie or local storage for all transactions. If the product requires preserving exact destinations per flow, design correlation with TTLs and origin checks instead of trusting arbitrary query strings.

### 16.4. Session Management and Login Success

A successful login session may also be subject to policies for:

- Session timeout.
- Concurrent sessions control.
- Session fixation protection.
- Logout and OIDC logout when configured.
- Session invalidation when a user is locked or permissions change.

**The success handler does not replace these mechanisms.** Specifically, if you replace the success handler list wholesale, verify whether Spring Security's concurrent-session/registration hooks were displaced.

## 17. Multiple SecurityWebFilterChains and Multiple Authentication Mechanisms

An application may have:

- One chain for OAuth2/OIDC browser login.
- One chain for APIs using Bearer Tokens (Resource Server).
- Public/health endpoints.

If the OAuth2 Login success handler is configured on a chain that does not match the callback, the handler will never run.

### 17.1. Distinguishing Success Handlers for formLogin and oauth2Login

~~~java
.formLogin(form -> form
    .authenticationSuccessHandler(formSuccess))

.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(oidcSuccess))
~~~

These two handlers serve **two different authentication mechanisms**. Configuring `formLogin` alone does not make OIDC Login use that same success handler.

### 17.2. An API Chain Typically Does Not Need Browser Redirects

API token authentication normally expects HTTP 401/403 per contract, not browser redirects to `/login`. Under `ServerHttpSecurity.oauth2ResourceServer(...)`, Bearer Token verification and policies differ from `oauth2Login(...)`.

Do not reuse one failure redirect handler across every authentication mechanism without considering clients; API callers usually cannot handle HTML login pages.

### 17.3. Matchers and Ordering

When multiple chains are registered:

~~~text
/api/**                  -> API resource server policy
/login/oauth2/**         -> OAuth2 login callback chain
/oauth2/authorization/** -> OAuth2 login initiation chain
/**                      -> Web UI chain
~~~

This is a conceptual sketch, not a mandatory route layout. Inspect `securityMatcher(...)`, chain ordering, actual redirect URIs, and Spring Security endpoints so you never route the callback into a chain lacking OAuth2 Login.

## 18. Reactivity: Never Block, Never Manually Subscribe

### 18.1. Why Does Mono<Void> Matter?

A handler might call an audit repository/reactive client and then redirect:

~~~java
return audit.loginSucceeded(registrationId)
    .then(redirect.onAuthenticationSuccess(
        webFilterExchange, authentication));
~~~

If `audit` returns a **cold** publisher, it runs only when subscribed by the framework. Returning the composed chain lets Spring Security await completion.

### 18.2. Avoid Detached subscribe() Calls

Anti-pattern:

~~~java
// ANTI-PATTERN: detached side effect with no lifecycle guarantee.
audit.loginSucceeded(registrationId).subscribe();
return Mono.empty();
~~~

Risks:

- Audit records may be lost when the request ends or the app shuts down.
- Errors are not handled cleanly.
- Audit/redirect ordering is not guaranteed.
- Latency/correlation measurement and testing become difficult.

### 18.3. Avoid Blocking I/O

Anti-pattern:

~~~java
// ANTI-PATTERN on Reactor event-loop:
repository.saveToJdbcBlocking(authentication.getName());
Thread.sleep(500);
~~~

When legacy blocking I/O must be used, design a dedicated adapter/scheduler or switch to a reactive driver instead of dropping blocking code into handler lambdas. Keep side effects minimal; login callbacks should not stall on an unstable downstream service unless strictly required by security policy.

### 18.4. Do Not Retain ServerWebExchange Beyond the Request Lifecycle

`ServerWebExchange`, responses, and `WebSession` belong to the inbound HTTP request's lifecycle. Never push the whole exchange into a background queue to manipulate after sending a redirect; for auditing, extract only **permitted metadata** and process per contract.

## 19. Handling Errors When Redirect or Audit Fails

### 19.1. An Audit Failure Is Not Always an Authentication Failure

Suppose the ID Token is verified and `Authentication` is valid, yet the audit system is temporarily unavailable. Choices:

- Auditing is **best-effort**: safely log/emit a metric for the audit failure and continue redirecting.
- Auditing is **compliance-mandatory**: enforce an explicit policy and durable design such as an outbox or error-handling workflow; never ignore silently.

Do not confuse auxiliary post-authentication failures with user credential failures. Separate "identity validation failed" from "post-login side effect failed."

### 19.2. Wrong Redirect URL

If the handler points to `/dashboard` and that route does not exist, login itself still succeeded; the browser gets a 404 after the redirect. That error does not mean the OIDC token was invalid.

### 19.3. Redirect Loops

If `/auth/failed` is protected, or `/dashboard` redirects back to `/login` because `SecurityContext` was not saved properly, the browser loops.

Check:

1. Which URL is the OP's real callback?
2. Does any handler redirect to a URL that itself requires auth?
3. Does the browser send the session cookie back?
4. Do `SameSite`/`Secure`/proxy/HTTPS settings match the callback mode?
5. Are `SecurityWebFilterChain` and the context repository configured correctly?

### 19.4. Provider Callback Fails Yet the Failure Handler Does Not Run

Not every provider error triggers an authentication `WebFilter` `AuthenticationException`. Common reasons:

- Callback URL does not match the authentication matcher.
- Proxy path rewrite mismatch.
- Authorization request/session correlation failed before the filter.
- Technical exception outside the auth exception handler.
- Multiple filter chains prevented the callback from reaching the OAuth2 Login filter.

Therefore, do not start by rewriting the failure handler. Confirm **the request actually reached the OAuth2 Login filter** and the exception is of a type handled there.

## 20. Security: Handlers Should Do Little, and Do It Right

### 20.1. Never Log Credentials or Full Principals

Never log:

- Authorization codes on callback URLs.
- Access Tokens, Refresh Tokens, or ID Tokens.
- `client_secret`, client assertions, or private keys.
- PKCE `code_verifier`, OIDC `nonce`, or `state`.
- Entire `Authentication` objects or `OidcUser.getClaims()`.
- Raw `OAuth2AuthenticationException.getMessage()` or provider error descriptions.

A safe audit record might contain:

~~~text
event=oidc_login_completed
registration_id=company
outcome=success
timestamp=server_time
correlation_id=internal-9d83
~~~

This format is illustrative. When compliance requires `subject` or `tenant` in audit logs, enforce personal-data policies, access control, and retention limits.

### 20.2. Never Grant Roles Inside a Failure Handler

A failure handler handles failure—it is **never a fallback authentication provider**. Never mark a user as authenticated "to avoid interrupting the experience" when the ID Token is invalid or `state` mismatches.

### 20.3. Never Accept Arbitrary External Redirects

Redirect only to trusted routes or strictly validated URLs. Never use an unchecked `returnUrl` from query parameters or cookies as the destination.

### 20.4. Never Use Exceptions to Disclose Account Information

An error page letting attackers distinguish "email exists," "account locked," "wrong nonce," or "consent declined" adds an account enumeration channel. For standard browser UX, display a neutral message alongside a separate support reference code.

### 20.5. Control Post-Login Side Effects

After login, never automatically:

- Grant admin privileges just because a username claim contains `"admin"`.
- Link accounts based on an unverified email.
- Send tokens to external analytics endpoints.
- Store raw ID Tokens in custom cookies.
- Call sensitive APIs on the user's behalf before checking scopes/audience and authorization.

Use `issuer + subject` as the OIDC identity anchor and enforce internal policies for account linking and authorization.

## 21. Issues Commonly Mistaken for Handler Bugs

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| Login succeeds yet does not go to `/dashboard` | Saved request took priority | Check `RedirectServerAuthenticationSuccessHandler` and request cache |
| Login fails yet still lands on `/login?error` | Custom failure handler wired to wrong chain | Check `oauth2Login(...).authenticationFailureHandler(...)` |
| Redirect loop on error page | `/auth/failed` lacks `permitAll` | Permit error page publicly or change response policy |
| Dashboard returns 401 after redirect | Session/`SecurityContext` missing on next request | Check repository, cookies, proxy, and session |
| Success handler logs twice | Multiple auth attempts or multiple handlers/chains | Check matchers, handler list, event deduplication |
| Custom handler breaks session limits | Replaced the success handler list | Check additive handler overload and concurrent session control |
| Browser redirects before audit finishes | Handler called `subscribe()` and returned early | Return `Mono<Void>` chain via `then`/`flatMap` |
| Login hangs due to auditing | Blocking call on reactive thread or slow upstream audit | Use reactive I/O, timeouts, and policy |
| Failure handler doesn't run on 403 | 403 is authorization failure, not authentication failure | Check `ServerAccessDeniedHandler`/authorization rules |
| Failure handler doesn't run on API 401 | API entry point differs from OAuth2 Login callback | Check authentication entry point and API security chain |
| OAuth2 callback returns 404 | Wrong redirect URI/matcher/proxy | Check `/login/oauth2/code/{registrationId}` |
| ID Token verification fails | Issuer, audience, signature, `exp`, `nonce`... | Inspect OIDC config/metadata; never bypass validation |
| Login success handler runs yet API token is missing | Authorized client store differs or scope mismatch | Check reactive authorized client manager/repository |
| Browser sent to foreign domain | Open redirect via `returnUrl` | Enforce URL allowlists and validated saved requests |
| Error page exposes provider internals | `exception.getMessage()` placed in query/body | Log safe error codes and show neutral messages |
| Fails only across multiple pods | Sessions not shared, cookie key/route mismatch | Check session architecture, reverse proxy, distributed store |

### 21.1. Debugging Workflow When "Not Landing on Expected Page"

~~~text
User finishes OIDC Login
  |
  +-- Did callback hit the right SecurityWebFilterChain?
  |
  +-- Did ID Token validation and Authentication succeed?
  |
  +-- Is the success handler actually wired into oauth2Login?
  |
  +-- Was a saved request stored?
  |
  +-- Did the redirect strategy pick the saved request or fallback location?
  |
  +-- Does the target URL exist within a trusted origin?
  |
  +-- Did the browser send the session cookie on the next request?
  |
  +-- Does the target page's authorization allow this principal?
~~~

Never assume "the success handler is broken" merely because the destination page returns 403—that can be a post-authentication authorization check.

## 22. Testing Success and Failure Handlers

Categorize tests by objective:

| Test Type | Objective |
| --- | --- |
| Direct handler unit test | Verify `Mono<Void>` completes, redirect URL/status, or JSON body |
| Reactive Security integration test | Verify right `SecurityWebFilterChain`, OAuth2 Login config, and handlers |
| Fake OIDC Provider flow test | Authorization Code callback, ID Token validation, saved request, provider errors |
| Session/redirect test | `SecurityContext` and request cache work across browser redirects |
| Observability test | Audit logs omit tokens/secrets and classify errors safely |
| Multi-session test | Custom success handler does not break concurrent session policies |

### 22.1. Unit Testing Redirect Behavior

With Spring WebFlux test utilities, create a mock `ServerWebExchange` and `WebFilterExchange`, pass a test `Authentication` to the handler, and verify with `StepVerifier`:

~~~java
StepVerifier.create(
    successHandler.onAuthenticationSuccess(
        testWebFilterExchange,
        testAuthentication))
    .verifyComplete();
~~~

This is a **test skeleton** assuming `testWebFilterExchange`/`testAuthentication` exist. Afterward, assert HTTP status/`Location` or saved-request state as configured. You do not need a live provider to unit test a simple handler.

### 22.2. Failure Testing with a Simulated Exception

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import reactor.test.StepVerifier;

StepVerifier.create(
    failureHandler.onAuthenticationFailure(
        testWebFilterExchange,
        new BadCredentialsException("TEST_ONLY_FAILURE")))
    .verifyComplete();
~~~

Assert on the response:

- Redirects to `/auth/failed` or returns fixed JSON `401`.
- Neither `Location` nor body contains `TEST_ONLY_FAILURE` or exception messages.
- No valid `Authentication` is created after failure.
- No raw credentials appear in audit records.

`BadCredentialsException` is just a convenient test exception; **real OIDC Login failures can be other exception types**.

### 22.3. WebTestClient Does Not Prove the Full OIDC Flow by Itself

`WebTestClient` tests Spring WebFlux HTTP behavior and Spring Security. Tests using mock logins (e.g., mocking an OIDC principal) verify controller authorization, yet **do not prove real callbacks, token exchange, `state`, PKCE, or nonces**.

End-to-end tests need a mock OP/Authorization Server to initiate authorization requests, handle callbacks, and validate ID Tokens/token responses. Separate clearly:

~~~text
Handler unit test
  -> redirect/audit logic

SecurityWebFilterChain integration test
  -> matcher, context, request cache, response policy

OIDC protocol integration test
  -> discovery, authorization code, state, PKCE, ID Token, nonce
~~~

### 22.4. Scenarios to Cover

| Scenario | Expected Outcome |
| --- | --- |
| Login succeeds without saved request | Redirects to fallback `/dashboard` |
| Login succeeds with saved request | Redirects to saved page when policy allows |
| User actively denies consent | Generic error notice, safe audit category |
| Invalid ID Token | Success handler is never invoked as a valid login |
| State/correlation fails | No valid authenticated session created |
| `AuthenticationException` contains sensitive message | Message never appears in URL/response |
| Audit succeeds | Redirect runs after audit per chain design |
| Best-effort audit fails | Flow continues per policy without hanging login |
| Custom handler writes JSON body | Accurate HTTP status, `Content-Type`, and body |
| API authorization returns 403 | Not confused with OAuth2 Login failure |
| Two browser sessions | Sessions/identities remain isolated |
| Concurrent sessions control enabled | Custom success handler preserves required session handlers |
| Strange or absolute redirect target | Rejected by allowlist/policy |
| Callback URL hits wrong chain | Test catches misconfigured redirect/matcher |
| Browser omits cookie after callback | Test identifies session continuity bug |

## 23. Practical Scenarios

### Scenario A — Returning to the Requested Page After Login

User wants `/reports/2026` while unauthenticated. Spring Security saves the request and redirects to the OP.

**Solution:** use `RedirectServerAuthenticationSuccessHandler("/dashboard")`; the saved request takes priority. Do not override with an unconditional `/dashboard` redirect if you want to keep this UX.

### Scenario B — Always Sending Users to the Dashboard

The product intentionally drops returning to the prior page.

**Solution:** write a custom `ServerAuthenticationSuccessHandler` using `ServerRedirectStrategy.sendRedirect(exchange, URI.create("/dashboard"))`. Validate the redirect URL and accept the trade-off of ignoring saved requests.

### Scenario C — Recording Login Audits Without Slowing Down UX

The audit system occasionally stalls.

**Solution:** build a handler returning `audit.loginSucceeded(...).onErrorResume(...).then(redirect...)` when auditing is best-effort; bound latency and use durable auditing if required by policy. Never call `subscribe()` inside the handler and ignore errors.

### Scenario D — OAuth2 Provider Returns access_denied

The user declines to grant permissions to the client.

**Solution:** the failure handler redirects to a generic page and logs a safe audit category. Never fabricate an `Authentication` to bypass consent.

### Scenario E — Dashboard Redirect Succeeds Yet API Returns 403

The user is logged in, yet lacks `ROLE_REPORT_EDITOR` or tenant permission.

**Solution:** inspect authorization rules, role mapping, and API/resource policies. Do not modify the success handler because authentication already succeeded.

### Scenario F — Replacing Success Handler Bypasses Concurrent Session Limits

The app configured session management, yet replaced the single success handler on OAuth2 Login.

**Solution:** check your Spring Security version and how the success handler list works. Consider the additive handler overload (6.3+) to keep concurrent-session hooks without duplicating redirects.

### Scenario G — Error Page Causes a Login Loop

The failure handler redirects to `/auth/failed`, which is protected.

**Solution:** add `/auth/failed` to `permitAll` on the right chain and avoid automatically triggering OAuth2 Login on the error page.

### Scenario H — OP Callback Misses the Failure Handler

OP redirects to `/login/oauth2/callback/company`, while Spring Security listens by default on `/login/oauth2/code/{registrationId}`.

**Solution:** align the redirect URI registered at the OP, `ClientRegistration.redirectUri`, and the `authenticationMatcher` in Reactive OAuth2 Login. Never try to catch it in another controller.

### Scenario I — OIDC ID Token Rejected Yet App Shows the Main Page

A custom failure handler redirects to `/dashboard` despite login failing.

**Problem:** landing on a success URL misleads users; if `/dashboard` is unprotected it exposes data in the wrong state, and if protected it causes a login loop. **Solution:** redirect to a public error page and keep the user unauthenticated.

### Scenario J — Background Job Needs to Refresh a Token

A job without a browser session needs to call an API after a user previously logged in.

**Solution:** this belongs to **`ReactiveOAuth2AuthorizedClientManager`**, token storage, and user delegation—not `ServerAuthenticationSuccessHandler`. Design offline access permissions and token retention policies explicitly.

### Scenario K — Error Page Displays the OP's error_description

The provider returns a verbose description containing internal details. The app appends it to the query string to help support teams.

**Solution:** never expose raw descriptions in responses or browser-visible logs. Map internal error categories, log correlation IDs, and display a neutral message.

### Scenario L — Logging In from Two OIDC Providers

Both `company` and `partner` registrations have `preferred_username="admin"`.

**Solution:** during auditing, namespace by registration and the verified ID Token's **`issuer + subject`** where needed; never grant admin privileges from matching usernames inside a success handler.

## 24. Review Questions

**1. When is `ServerAuthenticationSuccessHandler` invoked?**

After the reactive authentication pipeline builds a valid `Authentication` and passes the result to the configured handler. It is not a hook for every HTTP request.

**2. Why does the handler return `Mono<Void>`?**

To represent response/redirect writing and asynchronous side effects inside the reactive chain; Spring Security manages subscription and completion.

**3. Does `RedirectServerAuthenticationSuccessHandler("/dashboard")` always redirect to `/dashboard`?**

No. Saved requests take priority; `/dashboard` is typically the fallback.

**4. Does the failure handler handle HTTP 403 for an already-logged-in user?**

Usually not. That is an authorization failure, handled by `ServerAccessDeniedHandler` or authorization rules.

**5. Should you log `exception.getMessage()` when OIDC fails?**

Never send it raw to the browser or unredacted logs. Categorize errors, redact sensitive fields, and use correlation IDs.

**6. What problem can a custom success handler cause for concurrent sessions?**

Replacing the handler list can drop session-management hooks; verify version semantics and use the additive handler configuration where appropriate.

**7. Should a login handler save Access Tokens in a custom `WebSession` attribute?**

No when an authorized client repository/service already exists; creating a separate token store causes security and synchronization bugs.

**8. For OIDC Login, what must be verified before considering a user authenticated?**

The OAuth2/OIDC transaction must pass correlation, token response checks, ID Token issuer/audience/signature/timestamps, flow-specific `nonce`, and remaining protocol constraints.

## 25. References

- Spring Security — Reactive OAuth2 Login Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
- Spring Security — Reactive OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
- Spring Security — `ServerHttpSecurity.OAuth2LoginSpec` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html
- Spring Security — `ServerAuthenticationSuccessHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationSuccessHandler.html
- Spring Security — `ServerAuthenticationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html
- Spring Security — `RedirectServerAuthenticationSuccessHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html
- Spring Security — `RedirectServerAuthenticationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html
- Spring Security — Reactive Concurrent Sessions Control: https://docs.spring.io/spring-security/reference/reactive/authentication/concurrent-sessions-control.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

## 26. Summary

~~~text
Reactive OAuth2/OIDC Login
  |
  +-- Start Authorization Code flow
  |     state / PKCE / OIDC nonce per flow
  |
  +-- OP callback
  |     exchange code -> validate ID Token -> create Authentication
  |
  +-- Authentication SUCCEEDS
  |     ServerAuthenticationSuccessHandler
  |       -> audit if needed (non-blocking)
  |       -> saved request if present
  |       -> or /dashboard
  |
  +-- Authentication FAILS
        ServerAuthenticationFailureHandler
          -> categorize error safely
          -> audit/metrics if needed
          -> redirect /auth/failed or generic response

Do not confuse:
  ServerAuthenticationSuccessHandler
    != client manager's ReactiveOAuth2AuthorizationSuccessHandler

  ServerAuthenticationFailureHandler
    != ServerAccessDeniedHandler for an authenticated request

  WebFlux ServerWebExchange/Mono<Void>
    != Servlet HttpServletRequest/HttpServletResponse
~~~

**Four points to remember:**

1. **`ServerAuthenticationSuccessHandler` handles successful authentication on Reactive WebFlux**, typically redirecting to a saved request or fallback route. `RedirectServerAuthenticationSuccessHandler` preserves consistent browser-login behavior.
2. **`ServerAuthenticationFailureHandler` handles failed authentication**, typically redirecting to a public error page. Never forward raw exceptions/error descriptions or credentials to the browser.
3. **Handlers must return a complete reactive chain**, without manual `subscribe()`, blocking on the event-loop, or writing multiple responses for the same request.
4. **Customizations must uphold security and lifecycle boundaries**: OIDC validation before handlers, `SecurityContext`/`WebSession`, saved requests, concurrent session control, open-redirect prevention, and separation from OAuth2 authorized-client/token refresh.

With a clear grasp of these two interfaces, a WebFlux application can customize post-login OIDC UX, auditing, and error reporting without inadvertently weakening authentication, breaking session management, or mixing OAuth2 Login with Access Token API calls.
