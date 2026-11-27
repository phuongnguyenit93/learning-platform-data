# 8.12. Controlling Post-Login Redirect URLs and Open Redirect Risks

In a **Spring Security OAuth 2.0/OIDC Client** application, users rarely visit the login page just to log in. They want to perform a specific task: view an order, open their profile, access a report, or follow a link from an email. Once authentication finishes, the application must decide **where to send the browser**.

This navigation is easily confused with OAuth 2.0's `redirect_uri`, yet they are two distinct concepts:

- **OAuth redirect URI (callback URI):** the address on the application to which the Authorization Server/OpenID Provider (OP) returns the **authorization code** and `state` after the user authenticates.
- **Post-login redirect (success destination):** the address the application sends the user to **after receiving the callback, verifying the login result, and establishing the session**.

An application may have a fixed callback `/login/oauth2/code/company` while sending users after login to `/dashboard`, `/orders`, or the page previously requested.

**Open redirect risk** arises when an application lets user-controlled or third-party-controlled data determine the redirect target without proper validation policy. Attackers can exploit the application's trusted domain to send users to a spoofed page, and in certain flawed architectures, risk leaking authorization codes, tokens, or sensitive information.

This lesson focuses on controlling redirect targets in **Authorization Requests and OAuth2 Login on Spring Security Servlet**, using built-in mechanisms when appropriate and customizing only for clear business needs.

## 1. Understanding the Three Navigation Steps in OAuth 2.0/OIDC Login

### 1.1. Basic Flow

Suppose a Spring Boot application has:

- Web application (Relying Party): `https://portal.example.org`.
- OpenID Provider: `https://login.example.org`.
- Local Registration ID: `company`.
- Business page the user wants to view: `/orders`.

A valid flow:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as Spring Boot RP
    participant OP as OpenID Provider

    B->>RP: GET /orders
    RP->>RP: User not logged in; save requested URL
    RP-->>B: Redirect /login
    B->>RP: GET /login
    RP-->>B: Page with link /oauth2/authorization/company
    B->>RP: GET /oauth2/authorization/company
    RP->>RP: Create authorization request, state, and PKCE
    RP-->>B: Redirect OP /authorize
    B->>OP: GET /authorize (client_id, redirect_uri, state, ...)
    OP->>B: Authenticate and consent if needed
    OP-->>B: Redirect callback?code=...&state=...
    B->>RP: GET /login/oauth2/code/company?code=...&state=...
    RP->>OP: Exchange code for tokens (after verifying state)
    OP-->>RP: Token response (with ID token for OIDC)
    RP->>RP: Verify result, create Authentication and session
    RP-->>B: Redirect /orders (success destination)
    B->>RP: GET /orders with session cookie
    RP-->>B: Orders page
```

Here there are **three URL transitions to distinguish**:

| Step | Example Address | Who Decides | Purpose |
|---|---|---|---|
| Start OAuth Login | `/oauth2/authorization/company` | Spring filter config and `registrationId` | Initiates the authorization request |
| OP returns result | `/login/oauth2/code/company` | `ClientRegistration.redirectUri` and OP configuration | Receives code, `state`, and completes OAuth/OIDC |
| After login succeeds | `/orders` | Success handler / request cache / app policy | Sends the user to their intended destination |

**Never put an arbitrary browser-supplied URL into OAuth `redirect_uri` just to pick a post-login page.** The callback must be a registered, strictly controlled endpoint; the post-login destination is managed separately at the RP.

### 1.2. Why Does This Boundary Matter?

The OAuth Authorization Server must verify `redirect_uri` against the registered client configuration. If an application reads an arbitrary target from a query parameter and turns it into the callback, it can break redirect URI validation and cause **authorization code leakage** if the AS or app mishandles it.

Conversely, even when the OAuth callback is completely secure, a success handler like:

```java
response.sendRedirect(request.getParameter("next"));
```

can still turn the RP into an **open redirect** if `next` comes from an untrusted source.

Both problems involve HTTP redirects, yet they must be addressed at **two separate security boundaries**.

## 2. What Is an Open Redirect?

An **open redirect** occurs when a website lets a caller supply a target URL and automatically redirects to that target regardless of whether it falls within an allowed scope.

For instance, an application has an endpoint:

```text
GET https://portal.example.org/redirect?next=https://evil.example/phishing
```

If the application responds:

```http
HTTP/1.1 302 Found
Location: https://evil.example/phishing
```

then a URL on `portal.example.org` was used to send users to an unintended external website. An initial link on a trusted domain can be abused in emails, QR codes, messages, or phishing campaigns.

### 2.1. What Can an Attacker Do?

Depending on how the application is built, an open redirect can enable:

1. **Phishing:** sending a link that appears to start on an enterprise portal, then forwarding users to a fake login page.
2. **Trusted-domain abuse:** using the RP's domain as an intermediary hop to bypass basic link filters.
3. **Workflow hijacking:** after authentication, sending users to a page outside the application's control.
4. **Data leakage in flawed implementations:** if the app puts codes, tokens, or secrets into URLs and redirects externally, those values can leak via URLs, logs, or browser behavior.
5. **OAuth attack chaining:** an open redirect endpoint within URIs trusted by the Authorization Server can undermine or bypass callback boundaries, especially alongside loose redirect URI matching.

Not every open redirect automatically leaks tokens. Impact depends on redirect placement, cookies, browser policies, and how the app/AS handle OAuth. Even so, it remains a flaw to eliminate because the external target **is not reliably approved by the user and application**.

### 2.2. Common Risky Patterns in Code

Patterns prone to risk:

```java
// Intentionally insecure example: do not use in real applications
@GetMapping("/go")
public void go(@RequestParam String target,
               HttpServletResponse response) throws IOException {
    response.sendRedirect(target);
}
```

```java
// Intentionally insecure example: unchecked success handler customization
.oauth2Login(oauth2 -> oauth2
    .successHandler((request, response, authentication) -> {
        String next = request.getParameter("next");
        response.sendRedirect(next);
    }))
```

```java
// Example that can be dangerous if the value is user-controlled
successHandler.setTargetUrlParameter("redirectTo");
successHandler.setUseReferer(true);
```

The `setTargetUrlParameter(...)` and `setUseReferer(true)` APIs do not by themselves verify whether an external address is permitted as an application destination. Whenever enabling input-driven target selection, design a strict destination policy.

## 3. Sources for Post-Login Redirect Destinations

After Spring Security authenticates a user, the application can choose the URL from several sources:

| Source | Example | Characteristics |
|---|---|---|
| **Application default path** | `/dashboard` | Server-configured; simple and easy to control |
| **Saved request** | User requested `/orders/42` before login | Spring `RequestCache`/`SavedRequest` restores original intent |
| **Restricted business selection** | `go=orders`, `go=profile` | Server maps selection code to a fixed path |
| **Query parameter holding free-form URL** | `?next=https://...` | Untrusted without strict validation policy |
| **HTTP Referer** | Previous page in browser | Easily missing, partially controlled, or not an allowed target |
| **Data tied to OAuth `state`** | Intent to return to `/orders` after login | Safe only when bound to the request, integrity-checked, and target-restricted; `state` does not validate URLs |
| **Host/protocol from reverse proxy headers** | `Forwarded`, `X-Forwarded-Host` | Trusted only when proxy and trust boundaries are properly configured |

Prefer **server-defined internal URLs** or **SavedRequest managed by Spring Security**, depending on UX. If business rules genuinely require user-selected targets, accept an **allowlisted destination code**, never an arbitrary URL.

## 4. How Does Spring Security Choose the Post-Login Page?

### 4.1. Default Success Handling

In Servlet OAuth2 Login applications, Spring Security runs an `AuthenticationSuccessHandler` after successful authentication. A commonly used component is **`SavedRequestAwareAuthenticationSuccessHandler`**.

How it works:

1. When an unauthenticated user visits a protected page, the request may be saved by `RequestCache`.
2. The user proceeds through the login page and OAuth/OIDC flow.
3. After authentication succeeds, the success handler can restore the target from the saved request.
4. If no saved request exists, the application falls back to a default destination.

Example: visiting `/orders` before login typically returns to `/orders` afterward; visiting `/oauth2/authorization/company` directly with no saved request uses the fallback path.

**`RequestCache` is not an arbitrary URL bin to trust blindly.** Keep framework behavior, do not overwrite the request cache with raw query-string values, and control incoming requests, hosts, and headers per deployment policy.

### 4.2. `defaultSuccessUrl`

A common configuration:

```java
http.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard"));
```

With the single-argument variant, `/dashboard` is the default URL when no matching saved request exists. If the user visited a protected page before login, the saved request mechanism can still take precedence.

If the application wants to **always** send everyone to the dashboard:

```java
http.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard", true));
```

The `true` argument means **always use the default success page**, even if a prior request was saved. This is a UX decision: suitable for single-entry portals, unsuitable if users need deep-link navigation after login.

### 4.3. Explicitly Declaring `SavedRequestAwareAuthenticationSuccessHandler`

Spring Security Servlet example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var success = new SavedRequestAwareAuthenticationSuccessHandler();
        success.setDefaultTargetUrl("/dashboard");
        success.setAlwaysUseDefaultTargetUrl(false);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/css/**")
                .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .successHandler(success));

        return http.build();
    }
}
```

Key points:

- `setDefaultTargetUrl("/dashboard")` sets a fixed server-controlled fallback.
- `setAlwaysUseDefaultTargetUrl(false)` lets saved-request logic be honored.
- Do not enable `targetUrlParameter` or `useReferer` to pull arbitrary URLs from the browser.
- `/login` and CSS assets must be accessible to unauthenticated users.

You do not need to declare this handler manually when defaults and `defaultSuccessUrl(...)` already suffice. The less custom URL-building logic you write, the smaller the attack surface.

## 5. Using `SavedRequest` to Return to the Pre-Login Page

### 5.1. Deep-Link Scenario

An internal email contains a link:

```text
https://portal.example.org/orders/742
```

The user is not logged in yet. The application needs to:

1. Require authentication before returning data.
2. Preserve the allowed request metadata via `RequestCache`/session.
3. Let the user complete OAuth2 Login.
4. Return to `/orders/742`.
5. **Check authorization to view order 742 after authentication**, rather than assuming any logged-in user can access that resource.

`SavedRequest` preserves the **navigation target**; it is not an authorization mechanism. Authorization checks at the controller/service/API remain mandatory.

### 5.2. What Is Typically Stored?

`HttpSessionRequestCache` can store initial request details in the HTTP session, such as URL and metadata needed for request matching/replay per framework mechanics. `SavedRequestAwareAuthenticationSuccessHandler` uses this data to choose the redirect.

Never turn `SavedRequest` into storage for unvalidated URLs. In multi-domain or proxied deployments, prevent host-header poisoning and enforce valid hosts/schemes at the ingress layer. If implementing a custom `RequestCache`, keep a strict boundary between external HTTP input and trusted redirect targets.

### 5.3. Behavior When Users Visit the Login Screen Directly

If a user visits:

```text
GET https://portal.example.org/login
```

and chooses to log in with the OP, there is typically no saved business request. Falling back to `/dashboard` or `/` is appropriate.

When users arrive from an email link, you do not need to invent `?next=...`; `RequestCache` already handles many deep-link scenarios in session-based applications.

### 5.4. Limitations to Consider

- Session/request cache can be lost due to session expiration or cookie policies.
- In multi-instance deployments, authorization request and saved request state may require a shared session store.
- Starting multiple login flows across tabs can introduce state/request race conditions that framework and architecture must handle.
- Initial requests containing sensitive data in query strings require care in logging and redirects.
- Endpoints such as `/logout`, OAuth callbacks, or API endpoints are not suitable post-login destinations; the app may need explicit target filtering.

## 6. Dangerous Example: Using a `next` Parameter to Decide Redirects

Suppose a login page supports:

```text
/login?next=/orders
```

A developer writes:

```java
String next = request.getParameter("next");
response.sendRedirect(next);
```

An attacker can alter the URL:

```text
/login?next=https://attacker.example/fake-login
```

If the application uses this input in its success handler, the browser leaves the portal right after login. Some payloads do not even contain `https://` directly:

```text
//attacker.example/path
\attacker.example\path
/%2F%2Fattacker.example/path
https://portal.example.org.attacker.example/
https://portal.example.org@attacker.example/path
https:%2f%2fattacker.example/path
```

These examples show confusing URL representations. **Not every payload works on every parser, container, or browser**; the point is illustrating why naive string checks fail across multiple decoding and normalization layers.

### 6.1. Why `startsWith` Is Not Enough

Example:

```java
// Intentionally insecure example
if (next.startsWith("https://portal.example.org")) {
    response.sendRedirect(next);
}
```

This condition can accept:

```text
https://portal.example.org.attacker.example/login
```

because the string starts with a trusted-looking prefix. Yet **the actual hostname is `portal.example.org.attacker.example`**, not `portal.example.org`.

Another common mistake:

```java
// Intentionally insecure example
if (next.startsWith("/")) {
    response.sendRedirect(next);
}
```

The string `//attacker.example/path` starts with `/`, yet in URL contexts it can be interpreted as a **network-path reference** to an external host.

Safe URL validation is far more than string prefix checking. Whenever external destinations are unnecessary, the best policy is **never letting the browser supply free-form URLs**.

### 6.2. Risks of Trusting HTTP `Referer`

`Referer` is not a reliable source of user intent. It may be stripped by privacy policies, reflect an external site, or in some cases be influenced by the caller.

Setting `setUseReferer(true)` for post-login redirects without destination validation can send users outside the application to an unwanted site. Use saved requests or a fixed fallback rather than treating `Referer` as a trusted destination list.

## 7. Safe Design: Using Destination Codes and a Server-Side Allowlist

If the UI genuinely needs to route users to different pages after login, pass **business intent** instead of a URL.

Instead of:

```text
/login?next=https://any-domain.example/path
```

use one of the accepted codes:

```text
/sign-in?go=orders
/sign-in?go=profile
/sign-in?go=dashboard
```

The backend maps these codes to **fixed server-defined paths**:

| `go` Code | Server-Decided Destination |
|---|---|
| `orders` | `/orders` |
| `profile` | `/profile` |
| `dashboard` | `/dashboard` |
| Other / missing | `/dashboard` |

This transforms the problem from "parse and trust an externally supplied URL" into "pick an entry from a server-published table."

### 7.1. Controller Recording Intent Before Starting OAuth

Spring MVC example:

```java
import java.util.Map;

import jakarta.servlet.http.HttpSession;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class SignInController {

    private static final String LOGIN_GO = "LOGIN_GO";

    private static final Map<String, String> ALLOWED_GO = Map.of(
        "orders", "/orders",
        "profile", "/profile",
        "dashboard", "/dashboard"
    );

    @GetMapping("/sign-in")
    public String signIn(
            @RequestParam(required = false) String go,
            HttpSession session) {

        String selected =
            go != null && ALLOWED_GO.containsKey(go) ? go : "dashboard";
        session.setAttribute(LOGIN_GO, selected);

        return "sign-in";
    }
}
```

The `go != null` check handles missing selection and avoids passing `null` to `Map.of().containsKey(...)`. For unauthenticated users, `/sign-in` must be `permitAll()`.

### 7.2. Login Page Contains Only Authentication Initiation Links

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In</title>
</head>
<body>
<main>
    <h1>System Sign In</h1>
    <a th:href="@{/oauth2/authorization/company}">
        Sign in via corporate account
    </a>
</main>
</body>
</html>
```

The HTML page holds no external URLs and does not alter `redirect_uri`. When the user clicks the link, Spring Security builds the authorization request normally and binds it to `state`/session.

### 7.3. Success Handler Mapping Destination Code to Fixed Path

```java
import java.io.IOException;
import java.util.Map;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.DefaultRedirectStrategy;
import org.springframework.security.web.RedirectStrategy;
import org.springframework.stereotype.Component;

@Component
public class SafeLoginSuccessHandler implements AuthenticationSuccessHandler {

    private static final String LOGIN_GO = "LOGIN_GO";

    private static final Map<String, String> ROUTES = Map.of(
        "orders", "/orders",
        "profile", "/profile",
        "dashboard", "/dashboard"
    );

    private final RedirectStrategy redirectStrategy = new DefaultRedirectStrategy();

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        HttpSession session = request.getSession(false);
        String selected = null;

        if (session != null) {
            Object value = session.getAttribute(LOGIN_GO);
            if (value instanceof String go) {
                selected = go;
            }
            session.removeAttribute(LOGIN_GO);
        }

        String destination = selected == null
            ? "/dashboard"
            : ROUTES.getOrDefault(selected, "/dashboard");

        redirectStrategy.sendRedirect(request, response, destination);
    }
}
```

This code never reads a URL from `request.getParameter("next")` after callback. It chooses **one of three routes declared in code**, then removes the consumed intent from the session so it does not affect future logins.

If the app needs to store `go` per authorization request or across concurrent login tabs, associate the intent with each `state` instead of using one shared session attribute that can be overwritten. This matters in multi-provider or parallel-flow architectures.

### 7.4. Wiring the Success Handler into OAuth2 Login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            SafeLoginSuccessHandler loginSuccessHandler) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/sign-in", "/error", "/assets/**"
                ).permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/sign-in")
                .successHandler(loginSuccessHandler));

        return http.build();
    }
}
```

With this handler, **the chosen `go` code takes precedence**, and the normal request cache is **not automatically used** the way `SavedRequestAwareAuthenticationSuccessHandler` uses it. If you want saved deep links to take precedence, implement explicit precedence and consult `RequestCache` appropriately. Do not replace the default handler if your only goal is returning users to the URL they visited before login.

Also consider how state survives when Spring Security rotates the session ID upon login to prevent session fixation; default session migration normally preserves session attributes. If customizing session management, ensure login intent data is retained and cleared at the right time.

### 7.5. Why Is the Destination-Code Pattern Safer Than Free-Form URLs?

- Attackers cannot pick an out-of-allowlist hostname simply by changing a query parameter.
- All target paths are visible and auditable in code review.
- Each code can be bound to roles or business conditions.
- No need to write complex custom URL parsers.
- Easy to test against a table of valid codes and a fixed fallback.

Note: redirecting to `/orders` **does not grant permission**. The `/orders` endpoint must still enforce authentication and authorization as usual. After login, if an account lacks access to that page, the application should return `403` or an appropriate access-denied page.

## 8. If Dynamic URLs Must Be Supported, How Should They Be Constrained?

Some products must preserve deep links parameterized by ID, such as `/orders/742?tab=history`. When a fixed route set is insufficient, the redirect policy must be stricter.

**Order of preference:**

1. **`SavedRequest`:** if the user genuinely hit a deep link on the same app before login, let `RequestCache` handle it.
2. **Separated destination code and parameter data:** e.g. `go=order&id=742`; the server validates the ID and builds `/orders/742` using the application's route builder.
3. **Parsed and validated internal path:** if accepting a path, allow only matching route patterns; reject schemes, authorities, backslashes, or out-of-scope paths.
4. **Strictly allowlisted external URLs:** only when business rules require routing to another application with known domains and configuration.

### 8.1. Constraining Same-Origin Targets

Accepting only relative paths served by the application reduces risk. Still, strings like `//host`, backslashes, encoded delimiters, control characters, or double-decoded URLs can behave inconsistently across Java, servlet containers, proxies, and browsers.

Therefore, never write a validator using only:

```java
next.startsWith("/")
```

and let every route pass. If dynamic paths must be supported, use a trustworthy URL parser/canonicalizer, validate **after canonicalization**, and match against concrete route patterns—or construct the path server-side from validated IDs.

An easier-to-control server-side pattern:

```text
Request: /sign-in?go=order&id=742
After authentication:
  go == order
  id matches allowed identifier format
  account is authorized to view order 742
  -> /orders/742
```

The application never accepts an arbitrary URL string, and the business service still checks authorization when the user accesses the resource.

### 8.2. When Redirecting to an External Website Is Required

Sometimes an RP acts as a central login portal that forwards users to a separate application. This requires an **exact server-side destination table** and a trusted inter-application protocol. Never permit a free-form `next` parameter merely because a hostname "looks corporate."

Static table example:

```java
private static final Map<String, String> EXTERNAL_DESTINATIONS = Map.of(
    "hr", "https://hr.example.org/",
    "docs", "https://docs.example.org/"
);
```

Pass only `destination=hr` or `destination=docs`, and let the server select the fixed URL from the map. Never accept arbitrary URLs post-login.

If you are forced to validate an externally provided URL, parse the URI and verify all attributes:

- `https` scheme (aside from tightly managed dev exceptions).
- Host matches an exact registered hostname after consistent canonicalization/IDNA handling.
- Port matches an allowed value, not an arbitrary port.
- No `userinfo` (`user@host`) that could spoof the host authority.
- Path and query match permitted patterns.
- No network-path references, backslashes, redirect chaining, or control characters.
- No further open redirect from the allowlisted destination to an untrusted domain, if that chain is under system control.

**Never match hostnames by string prefix or bare suffix without DNS label boundaries.** `example.org.attacker.test` is not part of `example.org`, and an `@` character can turn what looks like a domain into `userinfo` rather than the host.

### 8.3. Deep Links with Tokens or Custom Session Codes Need a Different Protocol

If an application must hand a user off to another domain after login, never pass ID tokens, access tokens, or refresh tokens in a `next` query parameter. Each RP application should perform OIDC login with its own registration, or use a dedicated handoff protocol with security bindings, short lifetimes, and explicit recipients.

Never treat an open redirect as an inter-app SSO mechanism. SSO is provided by the OP session and OIDC protocol, without RPs forwarding secret tokens in arbitrary URLs.

## 9. Connection to OAuth Authorization Request and `redirect_uri`

### 9.1. `redirect_uri` Is the Callback Registered with the AS

In Spring Boot:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Typically:

```text
Registration ID: company
Redirect callback: https://portal.example.org/login/oauth2/code/company
Post-login destination: /dashboard (or SavedRequest)
```

By default, `/oauth2/authorization/company` is **the authorization request initiation path** on the Spring application. It is not the callback.

The `redirect_uri` parameter the RP sends to the OP must match the URI registered under the OP's policy. Using wildcards or loose prefix matching at the AS increases the risk of authorization codes being delivered to the wrong destination.

### 9.2. Never Inject Browser-Supplied `next` into the Callback

A flawed pattern:

```java
// Intentionally insecure example
String next = request.getParameter("next");
authorizationRequest = OAuth2AuthorizationRequest
    .from(authorizationRequest)
    .redirectUri(next)
    .build();
```

If `next` is an external URL, the application has altered where the authorization code is sent. A compliant Authorization Server may reject the request, yet an application must never rely on the AS to fix broken routing design.

The right approach is keeping the configured callback fixed and trusted, then handling post-login intent **after the OAuth flow finishes**.

### 9.3. `state` Is Not a Trusted Place for Arbitrary URLs

The `state` parameter binds an authorization response to the request initiated by the client, helping prevent CSRF and callback mix-ups. It **does not verify whether a post-login URL is safe**.

Flawed conceptual example:

```text
state = "https://attacker.example/collect"
After callback: sendRedirect(state)
```

An unpredictable random `state` and a free-form `next` parameter are two different things. If an app needs to tie redirect intent to the flow, store a **random lookup key or allowlisted destination code** in server-side state bound to the authorization request; after callback, use it only once the request is verified and the target meets policy.

Never skip `state` checks or assume PKCE makes any redirect target safe. PKCE protects authorization code exchange, not URL filtering.

### 9.4. `nonce` and PKCE Solve Different Problems

| Mechanism | Function | Prevents Open Redirect? |
|---|---|---|
| `state` | Binds authorization response to initial request | Does not validate URLs |
| `nonce` in OIDC | Binds ID token to authentication request | No |
| PKCE | Binds authorization code exchange to verifier | No |
| `redirect_uri` matching | Prevents AS from sending code to invalid callbacks | Protects callback boundary, not success URL |
| Success redirect allowlist | Constrains post-login destination | **Yes, for post-login scope** |
| Business endpoint authorization | Governs resource access rights | Not a URL validator; still mandatory |

A secure system needs **both** full protocol validation and success URL controls.

## 10. Reverse Proxies, Forwarded Headers, and `Host` Header

### 10.1. Base URL May Come from the Request

In a typical deployment:

```text
Browser -> https://portal.example.org
             |
             v
      Reverse proxy / Load balancer
             |
             v
        http://spring:8080
```

Spring Boot can use request/forwarded headers to determine `{baseUrl}` and build callback URIs. If infrastructure trusts `Forwarded` or `X-Forwarded-Host` from untrusted sources, the app can generate URLs using a **caller-manipulated host**.

This is a trust-boundary risk: redirects or auto-generated URLs can point to the wrong domain, even when application code never reads a `next` parameter directly.

### 10.2. How to Design Safely

- Define valid public origins in infrastructure config and register matching redirect URIs at the OP.
- Accept forwarded headers only from trusted proxies/ingress; strip or overwrite headers supplied by Internet clients.
- Configure Spring Boot `server.forward-headers-strategy` per your architecture, without assuming setting that property alone is sufficient if the proxy leaks spoofed headers.
- Restrict valid `Host` headers at the ingress and control domains serving the RP.
- Prefer relative targets for internal navigation and never build absolute URLs from arbitrary `Host` headers.

Example property in a trusted reverse-proxy setup:

```yaml
server:
  forward-headers-strategy: framework
```

Use this only when header propagation is controlled. Different Spring Boot/container versions may process forwarded headers differently; verify host/scheme propagation against your actual deployment.

## 11. Multi-Provider and Multi-Tenant: Two Layers of Allowlists

A login page may display multiple providers:

```text
/oauth2/authorization/company
/oauth2/authorization/partner
```

`company`/`partner` is a **registration ID**, not a destination URL. If users can select a provider via parameters:

```text
/sign-in?provider=company&go=orders
```

the application must enforce **two separate checks**:

1. `provider` maps only to an existing, policy-permitted registration ID.
2. `go` maps only to a permitted post-login destination.

Never construct:

```text
/oauth2/authorization/{untrusted-provider}
/login/oauth2/code/{untrusted-return-host}
/success?next={arbitrary-url}
```

from free-form input assuming Spring or the OP will validate all business intent.

### 11.1. Tenant-Specific Destinations

For example, users of tenant A return to `/tenant/a/home`, while tenant B returns to `/tenant/b/home`. Never let the browser pick an arbitrary tenant and redirect anywhere.

Instead:

- Rely on verified tenant metadata after OIDC Login (issuer/claims/account mapping).
- Look up which tenant the user is permitted to access in internal data.
- Build the route with the verified tenant ID, or select from a server-managed route table.
- Keep authorization checks on every endpoint; redirecting does not grant access.

When multiple OPs are involved, determine trusted issuers/registrations per tenant, never reading issuers or token endpoints from user-supplied URLs.

## 12. Redirect Precedence in Real Applications

A product may have competing notions of "where to go next" at the same time:

- An initial deep link to `/orders/742`.
- A destination code from a homepage login button.
- A default dashboard page.
- A mandatory onboarding step after first login.

Choose a **clear precedence rule**.

Example:

1. If the account has not completed onboarding, redirect to a **fixed onboarding path**.
2. Else if a valid saved request exists within app scope and the user is allowed to access it, use the saved request.
3. Else if the user selected an allowlisted destination code in the current flow, map that code to its route.
4. Otherwise, redirect to `/dashboard`.

This order is an **example business policy**, not a mandatory Spring Security default. The app must validate before redirecting and still check permissions at the target page.

If you want the user-selected code to **override** the saved request, explicitly design and implement that precedence. Avoid letting multiple success handlers, target URL parameters, and saved requests compete unpredictably.

### 12.1. Onboarding Considerations

A user just completed OIDC login, yet must satisfy an application requirement before viewing resources. The app can send them to `/onboarding` right after login.

That **does not** strengthen OP authentication and does not grant permissions. Business endpoints must still check onboarding status or access permissions in security rules so users cannot jump directly to `/orders/742` and bypass the mandatory step.

### 12.2. Login Failure Handling

Do not confuse **failure URL** with **success destination**. When the OP rejects login or the callback is invalid, Spring may send the user to `/login?error`. Error handlers must never redirect to an arbitrary browser-supplied `next`.

Example:

```java
.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard")
    .failureUrl("/login?error"))
```

The error page should display an appropriate message without leaking authorization codes, ID tokens, access tokens, or internal exceptions in the query string.

## 13. Common Failure Scenarios

### Scenario A — User Arrives at an Internal Page from an Email

**Requirement:** A user opens `/documents/123` while logged out; after OIDC Login they want to return to that exact document.

**Right design:** Protect `/documents/123` with security rules; use `SavedRequestAwareAuthenticationSuccessHandler`/`RequestCache` to retain the original request. After login, the document endpoint still checks whether the user has permission to view document 123.

No need to build `?next=https://portal.example.org/documents/123` when saved requests already cover it.

### Scenario B — Users Can Pass External URLs into Login

**Initial requirement:** `/login?next=/orders`.

**Flaw:** The app redirects straight to `next` after login, so `next=https://attacker.example` also works.

**Right design:** Use a `go=orders` code mapped server-side, or allow only internal routes after parsing/canonicalization and policy validation. Never rely on naive host/path prefix checks.

### Scenario C — `Host` Header Altered at Proxy

**Symptom:** Redirect callbacks or absolute app links point to a hostname outside the product domain.

**Possible cause:** Reverse proxy forwards client-supplied `Host`/`X-Forwarded-Host`, or the app derives `{baseUrl}` from unvalidated headers.

**Right design:** Enforce a host allowlist at ingress, configure forwarded headers from trusted proxies only, and register exact callback URIs with the OP.

### Scenario D — Login Success Handler Always Goes to Dashboard

**Symptom:** Opening `/orders/742` and logging in still lands on `/dashboard`.

**Cause:** `defaultSuccessUrl("/dashboard", true)` was configured, or a custom success handler ignores `SavedRequest`.

**Right design:** To restore deep links, use a saved-request-aware handler or explicit precedence. If the product intentionally sends everyone to the dashboard, that is a valid UX choice and should be documented clearly.

### Scenario E — Modifying OAuth `redirect_uri` to Carry `next`

**Symptom:** OP reports `invalid_redirect_uri` or the Spring filter does not match the callback.

**Cause:** The app put `next`/business paths into `redirect_uri`, while the OP registered a fixed callback.

**Right design:** Keep `/login/oauth2/code/company` stable; store return intent in session/request cache or trusted flow state and handle it after login.

### Scenario F — Multiple Concurrent Login Tabs

**Symptom:** One tab picks `go=orders`, another picks `go=profile`; the first tab finishes login and lands on profile.

**Cause:** Redirect intent was stored in a single session attribute and overwritten by the second flow.

**Right design:** Bind redirect intent to **each authorization transaction** via state/request key or explicit multi-tab rules; avoid a single shared session slot if parallel flows must be supported.

### Scenario G — Bearer-Token API Receives Redirect to HTML Login

**Symptom:** A client calling `/api/orders` gets `302 /login` instead of HTTP `401`.

**Cause:** The web login filter chain handles stateless API routes, or entry points are not separated by request type.

**Right design:** Separate filter chains for the API Resource Server and the web RP. APIs should return appropriate `401`/`403` statuses rather than browser login redirects.

## 14. Security and Operations After Fixing Redirect Policy

### 14.1. Never Put Tokens or Authorization Codes in the Success URL

A server-side OIDC Login app should complete token exchange on the backend, verify the ID token, and establish a browser session. The success URL can be `/dashboard` or an internal deep link, but **never append**:

```text
/dashboard?access_token=<token>
/dashboard?id_token=<token>
/dashboard?code=<authorization-code>
```

Tokens/codes in query strings can be captured in access logs, browser history, analytics, proxies, or referrer headers under certain conditions. For browser sessions, keep tokens server-side and use properly secured session cookies when the architecture allows.

### 14.2. Never Treat Successful Authentication as Sufficient Access Permission

OIDC Login proves identity, not blanket access to every resource. A URL that is safe to redirect to can still be denied by application authorization.

Spring Security example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/", "/login", "/error").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
```

If a success handler redirects a user without role `ADMIN` to `/admin`, Spring Security still blocks access per the rule. Never weaken authorization just to make a post-OIDC redirect "succeed."

### 14.3. Cookies/Sessions and `SavedRequest`

When the browser goes to the OP and returns to the callback, the application must recover the saved authorization request and session data. Check:

- HTTPS, `Secure`, and `HttpOnly` cookies.
- `SameSite` matching the callback method (GET or POST) and browser policies.
- Session fixation protection, timeouts, and invalidation.
- Shared session store across multiple instances.
- Matching proxy scheme/host/path and cookie path.
- Session expiration mid-login-flow.

Never fix issues by disabling `state` checks or turning off CSRF globally. These protections serve different roles and must fit your real browser/session model.

### 14.4. Logging, Telemetry, and Troubleshooting

Log useful, secret-free events:

- Registration ID used by the application.
- `success`/`failure` outcome and normalized error code.
- A flow-specific request correlation ID (never use tokens as correlation keys).
- Allowlisted destination code, such as `orders` or `dashboard`.
- Validated internal URI path if allowed by logging policy.

Never log full OAuth callback query strings, `Authorization` headers, access tokens, refresh tokens, ID tokens, or client secrets. Never feed unverified `next` values into analytics dashboards where operators might click them.

## 15. A Security-Oriented Spring Boot Configuration

Example Spring MVC app using one OP that wants:

- `/login` page showing an SSO button.
- Default Spring callback.
- Fallback destination `/dashboard`.
- `SavedRequest` when users arrive via deep links.
- No browser-chosen external redirect URLs.

### 15.1. OIDC Client Registration Configuration

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
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
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

The client secret exists only on the backend. The OP must register the exact redirect URI matching the app's public origin.

### 15.2. `SecurityFilterChain` Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error",
                    "/css/**", "/js/**"
                ).permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard"));

        return http.build();
    }
}
```

No arbitrary target URL parameter is exposed. The success handler uses the prior request if saved, otherwise falling back to `/dashboard`.

### 15.3. Login Page

Controller:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }
}
```

Thymeleaf template:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In</title>
</head>
<body>
<main>
    <h1>Sign in with corporate account</h1>
    <a th:href="@{/oauth2/authorization/company}">
        Continue with SSO
    </a>
</main>
</body>
</html>
```

The link points only to Spring's initiation endpoint. Spring creates and manages `state`, callback, and token exchange; the template neither creates nor accepts free-form `next` parameters.

### 15.4. Typical Request Walkthrough

```text
GET /reports/2026
-> unauthenticated; Spring saves request and redirects to /login
-> click /oauth2/authorization/company
-> OP /authorize then returns to /login/oauth2/code/company
-> Spring authenticates; success handler checks SavedRequest
-> 302 Location: /reports/2026
-> GET /reports/2026 with authenticated session
-> application checks permission to view the report
```

If the user starts directly from the login page with no saved request, the `/dashboard` fallback is used.

## 16. Decision Table for Each Navigation Requirement

| Requirement | Recommended Approach | Risks to Control |
|---|---|---|
| Send everyone to one dashboard | `defaultSuccessUrl("/dashboard", true)` | Loses pre-login deep links if needed by product |
| Return to blocked pre-login page | `RequestCache` + saved-request-aware success handler | Session, Host/proxy trust boundary, post-login authorization |
| Pick among a few fixed pages | `go` code + server-side destination map | Session overwrites across tabs; route authorization |
| Deep link with ID parameter | `SavedRequest` or route builder from validated ID | Avoid arbitrary URLs; authorize access to ID |
| Forward user to another app | App code + fixed URI allowlist; SSO at destination | External domain redirects, token leakage, redirect chaining |
| Change OAuth callback | `redirect-uri`, callback matcher, and OP registration | Never turn callback into a post-login target |
| Multiple OPs/tenants | Map registrations and destinations from trusted config | Issuer mix-up, selecting disallowed providers |
| Separate web and API | Dedicated `SecurityFilterChain` per request type | APIs must not redirect to HTML login |
| Multi-tab concurrent logins | Bind redirect intent per authorization transaction | Overwriting shared session attributes |
| Post-onboarding/auth redirect | Success handler based on verified user state | Never use redirects as a substitute for endpoint authorization |

## 17. Practice Guidelines

When designing post-OAuth2/OIDC Login redirects, answer these questions in order:

1. **Which stage does this destination belong to?** OP authorization endpoint, `redirect_uri` callback, or RP success URL?
2. **Who controls the destination?** Server config, `SavedRequest`, allowlisted code, or browser-supplied query parameter?
3. **Can a fixed internal route be used?** If yes, avoid building URLs from user input.
4. **Is returning to a deep link required?** If yes, prefer `RequestCache`/`SavedRequest` to preserve original intent within the session model.
5. **If the user selects a destination, can you pass a selection code?** Use `go=orders` rather than `next=https://...`.
6. **If the URL is truly dynamic, did you validate the URI after canonicalization?** Check scheme, authority, host, port, path, redirect chaining, and encoding variants.
7. **Is the OAuth callback stable and accurately registered at the OP?** Never alter `redirect_uri` based on post-login destination.
8. **Are `state`, PKCE, `nonce`, and sessions preserved properly?** These protect the authentication flow independently of URL allowlists.
9. **Are permissions checked at the target page?** Successful authentication does not automatically grant resource access.
10. **Is fallback behavior clearly defined for missing targets or failed logins?** Use a fixed fallback, never redirecting to untrusted URLs.

**Key takeaway:** In Spring Security Servlet OAuth2/OIDC Client, **the OAuth callback is part of the protocol**, whereas **the post-login URL is an application navigation decision**. Keep callbacks fixed, leverage `SavedRequest` for deep links, use server-controlled paths or destination codes, and never let arbitrary URL parameters dictate HTTP redirects. These practices support great UX without introducing open redirects.

## 18. References

- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth2/OIDC Login mechanics on the Servlet stack.
- [Spring Security — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): authorization endpoint, callbacks, and login settings.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, success handlers, entry points.
- [Spring Security — RequestCache](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering in Servlet Security, including request caching and exception handling.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization requests, `redirect_uri`, and validation requirements.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE in the Authorization Code Flow.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): recommendations for securing redirect URIs, authorization codes, and OAuth components.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, `state`, `nonce`, and ID Token.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): open redirect risks, allowlists, and prevention examples.
