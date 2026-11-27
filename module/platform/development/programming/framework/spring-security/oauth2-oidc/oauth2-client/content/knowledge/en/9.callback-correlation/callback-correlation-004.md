# 9.4. Correlating the Redirect URI and redirectionEndpoint Base URI

## 1. Scenario: Login Succeeds at the IdP, but Cannot Return to the Portal

Employee Portal is a Spring Boot application using **Spring Security OAuth 2.0 Client** so employees can log in via **OpenID Connect (OIDC)**. A user opens:

~~~text
https://portal.example.test/oauth2/authorization/company
~~~

Spring Security redirects the browser to the company's Authorization Server. The user authenticates successfully, yet afterward receives one of these errors:

- The IdP reports **invalid_redirect_uri / redirect_uri_mismatch**.
- The browser returns to the Portal but receives **404**, is sent back to the login page again, or enters a redirect loop.
- The error page shows **authorization_request_not_found**, **invalid_state**, or an OAuth2 Login failure message.
- Local works, while staging/production fails because the generated callback uses **http://** or an internal hostname instead of **https://** and the public hostname.

These symptoms usually appear when the following three places **disagree**:

1. The **Redirect URI** that the OAuth Client sends to the IdP when starting the Authorization Code Flow.
2. The **redirectionEndpoint base URI** that Spring Security Servlet uses to **receive and handle the callback**.
3. The **Allowed/registered redirect URI** at the IdP, which is the callback list permitted by the Authorization Server.

In the context of the **Callback and Correlation** chapter, you also need to understand how **state** and the **saved authorization request** are used to link the callback to the initial login request. A callback with the right path can still fail if the session or state is gone.

The goal of this lesson is to consistently configure **Redirect URI ↔ callback matcher ↔ IdP**, understand each component's role, and know how to pinpoint which step is failing.

> Examples use **Java 17+, Spring Boot 3 / Spring Security 6, Servlet stack (Spring MVC)**, and registration ID **company**. All domains, client IDs, and secrets are illustrative. The model corresponds to an OAuth2/OIDC web client using **Authorization Code Flow**; it is not a Resource Server validating bearer tokens.

## 2. Distinguishing Four URIs in One Login

These URIs are easily confused because they contain "authorization", "redirect", or "callback":

| Component | Example | Where does it live? | Purpose |
|---|---|---|---|
| **Authorization request base URI** | `/oauth2/authorization` | **Portal** | URL the user clicks to ask Spring to start login |
| **Provider's Authorization URI** | `https://login.example.test/oauth2/authorize` | **IdP** | Endpoint that receives the authorization request |
| **OAuth2 Client redirect URI** | `https://portal.example.test/login/oauth2/code/company` | **Portal**, sent as the `redirect_uri` parameter to the IdP | Address the IdP sends the browser back to after completing the authorization step |
| **redirectionEndpoint base URI** | `/login/oauth2/code/*` | **Spring Security Servlet** | Pattern for the filter to intercept callbacks arriving at the Portal |

**Authorization request base URI** and **redirectionEndpoint base URI** sit at opposite ends of the flow. The first triggers the **outbound trip to the IdP**; the second receives the **return trip from the IdP**.

Example:

~~~text
Browser                                 Employee Portal
  │
  ├─ GET /oauth2/authorization/company ──────► Start authorization
  │                                                  │
  ◄──────────── 302 to IdP (Location) ───────────────┤
  │
  ├─ GET https://login.example.test/oauth2/authorize?... ──► IdP
  │
  ◄──────────── 302 redirect_uri?code=...&state=... ─────── IdP
  │
  └─ GET /login/oauth2/code/company?code=...&state=... ──► Callback filter
~~~

**The Client redirect URI is a complete URL**, including scheme, host, port (if any), path, and any other valid URL components per the IdP contract. **The redirectionEndpoint base URI is a request-handling path pattern**, often containing a wildcard to match multiple registration IDs. They do not have to be identical strings, but **the redirect URI's path must match Spring Security's callback pattern** after proxy/context path processing.

## 3. Spring Security Servlet Defaults

Spring Security provides defaults so OAuth2/OIDC login works without writing a custom callback controller:

| Setting / constant | Typical value |
|---|---|
| `OAuth2AuthorizationRequestRedirectFilter.DEFAULT_AUTHORIZATION_REQUEST_BASE_URI` | `/oauth2/authorization` |
| Initiation URL per registration ID | `/oauth2/authorization/{registrationId}` |
| `OAuth2LoginAuthenticationFilter.DEFAULT_FILTER_PROCESSES_URI` | `/login/oauth2/code/*` |
| Common client registration redirect URI template | `{baseUrl}/login/oauth2/code/{registrationId}` |

With registration ID **company**, this set of values produces:

~~~text
Login initiation on Portal:
    /oauth2/authorization/company

Redirect URI sent to IdP:
    https://portal.example.test/login/oauth2/code/company

Callback pattern handled by Spring Security:
    /login/oauth2/code/*

Registered redirect URI at IdP:
    https://portal.example.test/login/oauth2/code/company
~~~

The callback filter constant uses `*` to accept registration-specific paths, while the actual redirect URI contains **company**. If the IdP enforces exact URI matching, register the **actual URL**, not Spring's Servlet pattern with `*`.

### 3.1. Important Point About registrationId

In Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal-prod
~~~

**company** is the internal **registration ID** Spring uses to select the `ClientRegistration`. **employee-portal-prod** is the **client ID** issued by the IdP. They do not have to be identical.

`{registrationId}` in the standard callback template expands to **company**, not **employee-portal-prod**.

## 4. Which Filter Processes the Callback?

The Servlet OAuth2 Login flow typically involves these components:

- **`OAuth2AuthorizationRequestRedirectFilter`**: initiates the authorization request and redirects the browser to the IdP.
- **`OAuth2AuthorizationRequestResolver`**: constructs the authorization request based on the client registration and HTTP request.
- **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`**: saves the authorization request before the browser leaves the Portal.
- **`OAuth2LoginAuthenticationFilter`**: matches the callback by URL, processes the authorization response, and delegates authentication/code exchange to the relevant components.
- **`OAuth2AuthorizedClientRepository/Service`**: saves the authorized client and tokens when authorization succeeds.
- **`SecurityContext`**: holds the user's Authentication after login.

Sequence diagram:

~~~mermaid
sequenceDiagram
    actor User as Employee
    participant Browser as Browser
    participant Portal as Portal (Spring Security)
    participant Repo as AuthorizationRequestRepository
    participant IdP as IdP / Authorization Server

    User->>Browser: Click Company Login
    Browser->>Portal: GET /oauth2/authorization/company
    Portal->>Portal: Resolver builds request, state, and redirect_uri
    Portal->>Repo: Save authorization request in session
    Portal-->>Browser: 302 to authorization endpoint
    Browser->>IdP: GET /authorize?client_id=...&redirect_uri=...&state=...
    IdP->>User: Authenticate and consent if needed
    IdP-->>Browser: 302 to redirect_uri?code=...&state=...
    Browser->>Portal: GET /login/oauth2/code/company?code=...&state=...
    Portal->>Portal: OAuth2LoginAuthenticationFilter matches callback path
    Portal->>Repo: Look up/consume initial request to verify state
    Portal->>IdP: Exchange authorization code for tokens
    IdP-->>Portal: ID Token, access token, and other issued tokens
    Portal->>Portal: Verify tokens, create Authentication, save authorized client
    Portal-->>Browser: Establish session and redirect to app page
~~~

**redirectionEndpoint base URI only decides which callbacks this filter intercepts.** It does not change the redirect URI in the request sent to the IdP, does not register the URL at the IdP, and does not replace **state** verification.

### 4.1. No Need to Write a `@GetMapping` for the Default Callback

When using standard `oauth2Login()`, the path:

~~~text
/login/oauth2/code/company
~~~

is handled by the **Security Filter Chain**. A controller like:

~~~java
@GetMapping("/login/oauth2/code/company")
String callback() {
    return "ok";
}
~~~

is not the standard way to complete OIDC login. The callback must process **state**, the authorization code, the token endpoint, and OIDC validation; Spring Security's filter handles these steps. Only build a custom callback flow when genuinely required and when you understand all associated security responsibilities.

## 5. Minimal Default Configuration in Spring Boot

Suppose Portal runs on `http://localhost:8080` in development.

### 5.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

**spring-boot-starter-web** selects Servlet/MVC; **spring-boot-starter-oauth2-client** provides OAuth2 Client and OIDC login. If the application uses WebFlux, the callback filter and configuration APIs differ from this example.

### 5.2. Client Registration

~~~yaml
# application.yml
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
~~~

Placeholder values must be supplied by the runtime environment. **client secret** is a secret for a confidential web client and must never be committed to Git or exposed in the frontend.

**issuer-uri** is the provider's identity; when the IdP supports metadata discovery, Spring Security can discover the required endpoints. **redirect-uri** is a client registration template expanded when initiating the authorization request.

### 5.3. SecurityFilterChain

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

In this configuration, you do not need to declare `redirectionEndpoint().baseUri(...)` because the default matcher already corresponds to the redirect URI template in YAML.

When the browser visits `http://localhost:8080/oauth2/authorization/company`, Portal generates an authorization request with redirect URI:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

That URI must be permitted on the IdP's client registration for local development. Do not use production client/secrets locally unless explicitly required and permitted by policy.

## 6. Changing the Callback Path: Update Three Places Together

Suppose the development team wants Portal's callback URL to be:

~~~text
https://portal.example.test/auth/callback/company
~~~

instead of:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

**Changing only one place is not enough.** You must update:

| Configuration place | New value | Why? |
|---|---|---|
| **ClientRegistration.redirectUri** | `{baseUrl}/auth/callback/{registrationId}` | Places the new value in the `redirect_uri` parameter sent to the IdP |
| **redirectionEndpoint.baseUri** | `/auth/callback/*` | Lets `OAuth2LoginAuthenticationFilter` accept callbacks at the new path |
| **Allowed redirect URI at IdP** | `https://portal.example.test/auth/callback/company` | Allows the Authorization Server to redirect the browser back to the Portal |

Specifically:

- The first two values are **application configuration**.
- The last value is **client configuration at the IdP**, typically updated via an admin console or client registration provisioning system.
- If there are multiple environments, each environment must have its corresponding registered redirect URI.

### 6.1. application.yml After Changing the Callback

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

### 6.2. SecurityFilterChain Accepting the New Callback

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .redirectionEndpoint(redirection -> redirection
                    .baseUri("/auth/callback/*")))
            .build();
    }
}
~~~

This is an **alternative configuration** to section 5; do not create a second duplicate `SecurityFilterChain`.

In this DSL, **`redirectionEndpoint(...).baseUri("/auth/callback/*")`** adjusts the callback filter's matcher. It is **not a full URL** and does not take an IdP URL as its value. The path must match the redirect path after accounting for the servlet context path.

### 6.3. Registering with the IdP

On the production IdP, register explicitly:

~~~text
https://portal.example.test/auth/callback/company
~~~

On the staging IdP, if Portal is exposed under a different hostname:

~~~text
https://portal.staging.example.test/auth/callback/company
~~~

For local:

~~~text
http://localhost:8080/auth/callback/company
~~~

These URIs belong to **their respective managed clients/environments**. Never register `/auth/callback/*` with the IdP assuming all providers allow wildcards. Many providers require exact URIs, and wildcards can increase risk if overly broad.

### 6.4. Changing the Callback Does Not Change the Login Initiation URL

After changing the callback to `/auth/callback/*`, the URL triggering the authorization request **can still be**:

~~~text
/oauth2/authorization/company
~~~

These are two opposite directions of the flow. If you want to change the login initiation URL, configure the **authorization endpoint/request resolver** separately, for example using the corresponding `authorizationRequestResolver`. Do not confuse the authorization request base URI configuration with `redirectionEndpoint` base URI.

## 7. What Does "Correlating the Redirect URI" Mean?

When talking about "correlating the Redirect URI", think in terms of **matching at three layers**:

1. **At the Authorization Server**: the URI in the authorization request's `redirect_uri` parameter must be accepted by the IdP according to the client registration and the IdP's matching rules.
2. **At the OAuth2 Client upon receiving callback**: the HTTP path of the returning request must match `OAuth2LoginAuthenticationFilter`'s matcher, governed by `redirectionEndpoint.baseUri`.
3. **In the correlation flow**: the callback must carry a `state` matching a saved authorization request; the code and parameters must be processed within the same transaction. The subsequent token request must adhere to Authorization Code Flow requirements, including `redirect_uri` when mandatory.

**This alignment does not mean Spring Security has a single mechanism that auto-synchronizes all three places.** An application can configure the callback matcher correctly yet have the IdP reject the URI; or the IdP can accept the URI while Spring Security fails to match the path.

### 7.1. At the Authorization Server: Matching the Registered URI

For example, the IdP registered:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

yet Portal sends:

~~~text
http://portal.example.test/login/oauth2/code/company
~~~

Due to the **scheme** difference, the URI can be rejected even though host and path look identical. Similarly, differences in **port, path, trailing slash**, or **public vs. internal hostname** can cause a mismatch.

Always configure the exact redirect URI and rely on the provider's strict matching rules. Never count on the IdP "guessing" or rewriting a URL to accept a callback.

### 7.2. At the Portal: Matching the Callback Path

Suppose the IdP is permitted to redirect to:

~~~text
https://portal.example.test/auth/callback/company?code=...&state=...
~~~

while Spring Security still only matches:

~~~text
/login/oauth2/code/*
~~~

Then a request to `/auth/callback/company` **is not handled by the callback filter under that configuration**. The request may fall through to another controller, security entry point, or error handler; whether it returns 404, 302, or another error depends on the application.

### 7.3. At Callback Correlation: State and the Initial Request

Even when the callback path matches, the request can still fail if:

- The browser lost the session cookie used when starting login.
- The saved authorization request no longer exists, expired, or was deleted.
- The callback carries a `state` different from the initial state.
- The callback is revisited after the authorization request was already consumed.
- A multi-instance deployment uses an unshared session store.

Therefore, **a matching callback path is a necessary condition for the filter to run, but not sufficient to complete OAuth2/OIDC login**.

## 8. AuthorizationRequestRepository and State: The "Correlation" Part of the Callback

In a typical Servlet flow:

1. `OAuth2AuthorizationRequestResolver` builds `OAuth2AuthorizationRequest`, containing `state`, redirect URI, and grant details.
2. `OAuth2AuthorizationRequestRedirectFilter` saves the request via `AuthorizationRequestRepository` and redirects the browser.
3. The IdP handles the authorization request and sends back a callback containing the authorization code and matching state (if successful).
4. `OAuth2LoginAuthenticationFilter` receives the callback and locates the matching authorization request.
5. Spring Security uses the saved request to validate the authorization response and correlate the transaction before exchanging the code for tokens.

Common implementation in session-backed Servlet apps:

~~~java
org.springframework.security.oauth2.client.web
    .HttpSessionOAuth2AuthorizationRequestRepository
~~~

This repository differs from **`OAuth2AuthorizedClientRepository`**:

| Store | Data | Stage |
|---|---|---|
| **AuthorizationRequestRepository** | Pending authorization request, including state and attributes needed for callback | From authorization start until callback |
| **OAuth2AuthorizedClientRepository/Service** | Access token/refresh token and authorized client info | After authorization succeeds |
| **SecurityContextRepository/session** | User's Authentication | After login succeeds |

**Never "fix a state error" by disabling state checks** or hard-coding `state` to a constant. `state` protects the binding between the authorization response and the initial request. With OIDC, separate `nonce` and ID Token validation rules also apply; never substitute `nonce` for `state`.

### 8.1. A Callback Does Not Strictly Need Registration ID in Its Path to Correlate

Examples commonly use `/login/oauth2/code/company` because the template contains `{registrationId}`. However, the essence of callback correlation is not "read the registration ID from the path and immediately trust it." Spring Security can rely on the **saved authorization request and state** to identify the matching registration/transaction.

When designing a custom callback, ensure the matcher, redirect URI, and repository agree. Never assume that having `company` in the path makes a callback automatically valid.

### 8.2. Controlling a Pending Login Session

Users should never manually invoke the callback URL with fabricated `code` or `state` values. Values must belong to a real Authorization Code transaction. Sensitive transaction data must never appear in logs or web analytics tools.

In applications with multiple tabs or concurrent login flows, carefully consider how the repository saves, looks up, and consumes authorization requests to prevent state loss. Custom implementations must support appropriate concurrency and correlation policies; never simply store the "latest state" in a variable shared across all users.

## 9. How Is the Redirect URI Built from `{baseUrl}`?

In client registration:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

**`{baseUrl}`** is a template variable expanded by Spring Security based on the URL the application perceives for the current request. It can include scheme, host, port, and external context path based on processed request metadata.

Example when accessed directly locally:

~~~text
http://localhost:8080 + /login/oauth2/code/company
    = http://localhost:8080/login/oauth2/code/company
~~~

When deployed behind a reverse proxy:

~~~text
Browser ──HTTPS──► https://portal.example.test
                     │
                     ▼
               Reverse Proxy
                     │  internal HTTP
                     ▼
               portal-service:8080
~~~

If the application **does not accurately recognize the external scheme and hostname**, `{baseUrl}` may resolve to:

~~~text
http://portal-service:8080
~~~

leading to:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

A production IdP configured for **https://portal.example.test** will normally reject that internal URI.

### 9.1. Forwarded Headers

Spring Boot Servlet can be configured with:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The reverse proxy or ingress forwards necessary details such as scheme/host/port/prefix via `Forwarded` or `X-Forwarded-*` depending on the setup.

**Security prerequisite:** only trust forwarded headers controlled by a trusted proxy. The proxy must strip or overwrite forged headers sent by Internet clients; otherwise, external users could manipulate URLs generated by the backend.

Once configured, inspect the `redirect_uri` value **actually appearing in the Location redirect to the IdP**, rather than looking at YAML properties alone and assuming Spring deduced the right URL.

### 9.2. Keeping a Fixed Redirect URI When Infrastructure Requires It

Another option is configuring the redirect URI via a runtime property:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: ${OIDC_REDIRECT_URI}
~~~

Example in production:

~~~text
OIDC_REDIRECT_URI=https://portal.example.test/login/oauth2/code/company
~~~

This reduces reliance on inferring the request's public host when the design has **a single fixed public callback URL**. However, the callback URL must still be routable to the Portal, match the filter pattern, and match the IdP registration list. Never share one fixed redirect URI across multiple domains/tenants if flows require distinct callbacks.

## 10. Context Path, Path Prefix, and Trailing Slash

Distinguish three kinds of paths:

1. **Public URL** seen by the browser/IdP.
2. **Servlet context path** where the application is mounted, if any.
3. **Filter process URI** after the servlet container and reverse proxy have processed the request.

### 10.1. When Spring Boot Has a Context Path

Suppose the config is:

~~~yaml
server:
  servlet:
    context-path: /portal
~~~

And the application is accessed directly at:

~~~text
https://example.test/portal
~~~

With the template `{baseUrl}/login/oauth2/code/{registrationId}`, the redirect URI can become:

~~~text
https://example.test/portal/login/oauth2/code/company
~~~

In that case, the filter matcher is still typically configured using the **path inside the Servlet context**:

~~~text
/login/oauth2/code/*
~~~

rather than blindly prepending `/portal` to `redirectionEndpoint.baseUri`. The public URL includes the context path, whereas the matcher applies to the request path received by the Servlet security filter after context resolution.

### 10.2. When a Proxy Adds or Strips a Prefix

Suppose the browser visits:

~~~text
https://apps.example.test/portal/login/oauth2/code/company
~~~

while the proxy forwards to the backend:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

The application may need public prefix headers (such as `X-Forwarded-Prefix`) and proper forwarded-header handling so `{baseUrl}` reflects `/portal`.

If the public URI looks right yet the filter fails to match, inspect the path the backend actually receives: whether the proxy **strips the prefix**, whether Spring Boot has a context path, and which path the matcher expects. **Never blindly tweak context path, proxy rules, and `redirectionEndpoint.baseUri` all at once.**

### 10.3. Common Discrepancies

| Discrepancy | Example | Consequence |
|---|---|---|
| Scheme | `http` vs. `https` | IdP may reject the redirect |
| Port | `:8080` vs. default public port | Redirect matching may fail |
| Host | `portal-service` vs. `portal.example.test` | IdP or browser does not receive the right callback |
| Context path | With `/portal` vs. without | Callback sent to wrong URL |
| Path | `/login/oauth2/code/company` vs. `/auth/callback/company` | Matcher does not handle it if misaligned |
| Trailing slash | `/company` vs. `/company/` | May fail to match registered URI or matcher |
| Case sensitivity | `/Callback/company` vs. `/callback/company` | Paths may be treated as distinct |

Preserve the principle of **exact redirect URI registration** and use **HTTPS** outside local environments.

## 11. Distinguishing `redirect_uri` from Other Post-Login URLs

Some "redirect" URLs are not OAuth redirect URIs at all.

| URL/redirect | When does it appear? | Is it an OIDC callback URI? |
|---|---|---|
| `redirect_uri` in authorization request | Before the IdP authenticates the user | **Yes** |
| `/login/oauth2/code/company` | When the IdP returns authorization code/state | **Yes**, default callback path |
| `/dashboard` after login | After Spring Security completes Authentication | **No** |
| Original URL saved by `RequestCache` | After successful login, to return the user to their requested page | **No** |
| `post_logout_redirect_uri` in OIDC RP-Initiated Logout | When ending the session at the IdP | **No**, that is a post-logout redirect |

Customizing `defaultSuccessUrl("/dashboard")` or `successHandler(...)` **does not change the OAuth redirect URI**. If IdP login fails with **redirect_uri_mismatch**, modifying the success handler will not fix the root cause.

Likewise, configuring a logout callback or post-logout redirect does not change `redirectionEndpoint.baseUri` for Authorization Code login.

## 12. Aligning Across Local, Staging, and Production Environments

A configuration matrix helps prevent misdeployments:

| Environment | Public base URL | Actual redirect URI to register at IdP | redirectionEndpoint matcher |
|---|---|---|---|
| Local | `http://localhost:8080` | `http://localhost:8080/login/oauth2/code/company` | `/login/oauth2/code/*` |
| Staging | `https://portal.staging.example.test` | `https://portal.staging.example.test/login/oauth2/code/company` | `/login/oauth2/code/*` |
| Production | `https://portal.example.test` | `https://portal.example.test/login/oauth2/code/company` | `/login/oauth2/code/*` |

If using a custom callback `/auth/callback/{registrationId}`, update **both the redirect URI and matcher columns** together, and register the corresponding public URL at the IdP.

Each environment should have its own **client registration/secret/allowed redirects** to prevent accidentally using production secrets or callbacks from local machines. Public configuration such as issuer/client ID can be managed via Spring Profiles; secrets should come from a secret manager or runtime environment.

### 12.1. Example YAML Profiles

~~~yaml
# application.yml: shared logic
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

~~~yaml
# application-prod.yml: HTTPS proxy infrastructure
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

At runtime, deployment provides:

~~~text
SPRING_PROFILES_ACTIVE=prod
OIDC_CLIENT_ID=employee-portal-prod
OIDC_CLIENT_SECRET=<secret-from-secret-store>
OIDC_ISSUER_URI=https://login.example.test/realms/company
~~~

Do not use `<secret-from-secret-store>` as a real credential; it only indicates where the secret comes from. Note that Spring Boot **does not automatically load `.env` files** merely because they exist; your launcher must pass variables into Java's environment.

## 13. Verifying Callback and Redirect URI Step by Step

To isolate errors quickly, observe **actual requests/responses** in a controlled test environment. Avoid logging raw codes/states/tokens or pasting them into public tickets.

### 13.1. Step 1: Generate the Authorization Request

~~~bash
curl -i "http://localhost:8080/oauth2/authorization/company"
~~~

With a valid registration, the response typically looks like:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=employee-portal&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin%2Foauth2%2Fcode%2Fcompany&state=<redacted>
~~~

This is an **illustrative response**, not live execution output. Actual cookie/session headers and encoding depend on framework configuration.

Inspect **Location**:

- Does the base URL point to the **right IdP**'s authorization endpoint?
- Does the URL-decoded `redirect_uri` parameter have the exact **scheme, host, port, and path**?
- Do `client_id` and `scope` match the registration?
- Are `state` and configured PKCE/OIDC parameters present?

In production, use browser developer tools or authorized tooling, keeping only **redacted values**. `state`, `nonce`, authorization codes, and tokens are session-sensitive data.

### 13.2. Step 2: Check the Allowed Redirect URI at the IdP

Take the **actual `redirect_uri` value**, not just the template. Compare it against the registration for the right client ID and environment at the IdP.

Example:

~~~text
request.redirect_uri:
    https://portal.example.test/login/oauth2/code/company

IdP registered redirect:
    https://portal.example.test/login/oauth2/code/company
~~~

If they differ, fix the root cause producing the wrong value or update the IdP registration per security policy. Do not open broad wildcards to mask infrastructure bugs.

### 13.3. Step 3: Check the Callback Request Arriving at the Portal

After IdP authentication, the browser typically requests:

~~~http
GET /login/oauth2/code/company?code=<redacted>&state=<redacted> HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=<redacted>
~~~

Determine:

- Did the browser hit the right hostname and callback path?
- Which Security Filter Chain received that request?
- Does `redirectionEndpoint.baseUri` match the path after proxy/context path processing?
- Did the browser send the session cookie along with the callback?

If the filter did not run, fix the matcher/path/proxy. If the filter ran but the authorization request was missing, inspect state/session/repository next.

### 13.4. Step 4: Check Correlation and Token Exchange

Once the path matches, Spring must find the original authorization request, verify `state`, and perform token exchange. If an error occurs at the token endpoint, possible causes include:

- Incorrect client secret or client authentication method.
- Expired or already-used authorization code.
- `redirect_uri` in token exchange inconsistent with the earlier request or IdP rules.
- PKCE code verifier does not match the code challenge.
- IdP denied scope/permission per policy.

Do not alter the callback matcher once you have identified the failure belongs to the **token endpoint**, **PKCE**, or **client authentication**.

## 14. The `response_mode=form_post` and Session Cookie Case

Most Authorization Code Flow examples use a **GET** callback with `code` and `state` in the query string. Some providers support or require **OIDC `response_mode=form_post`**, where the callback can be an HTTP **POST**.

When using `form_post`, additionally verify:

- Do the callback filter and Security Filter Chain config support the chosen HTTP method/form data?
- Does the application's **CSRF protection** block the POST callback before the OAuth2 Login filter handles it?
- Does the browser send the session cookie on a **cross-site POST**? `SameSite=Lax` generally does not guarantee cookies are sent on cross-site POSTs; `SameSite=None; Secure` may be needed for certain designs and must be evaluated against security policy.
- Can `AuthorizationRequestRepository` still locate the initial state/request?

**Never disable CSRF globally** merely because a POST callback was blocked. Design proper handling tailored to the endpoint, method, session state, and provider while preserving CSRF protection for cookie-authenticated business actions.

## 15. Multiple IdPs: Each Registration Has Its Own Redirect URI

Suppose Portal supports two providers:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${COMPANY_ISSUER_URI}
          partner:
            issuer-uri: ${PARTNER_ISSUER_URI}
~~~

**This is a replacement for the single-registration YAML example**, not a snippet to append into a file that already has a duplicate `spring.security.oauth2.client` key.

Corresponding public callbacks:

~~~text
https://portal.example.test/login/oauth2/code/company
https://portal.example.test/login/oauth2/code/partner
~~~

One matcher:

~~~text
/login/oauth2/code/*
~~~

can handle both paths. However, **each client at each IdP must register its own exact callback**. Never extract `issuer`/`client_id` from a query parameter to dynamically construct an arbitrary provider to process a callback.

If distinct callback paths are needed per provider, configure the matcher and `ClientRegistration` accordingly. Setups with dynamic/tenant configuration must verify issuer trustworthiness and bind `state` to the authorization request; never treat the `registrationId` value in the URL as a credential.

## 16. Common Errors and Troubleshooting Guide

| Symptom | Possible cause | How to check |
|---|---|---|
| IdP returns **redirect_uri_mismatch** before callback | URI sent to IdP is not in its allowlist | Decode `redirect_uri` and compare with client registration at IdP |
| IdP redirects to `http://internal-host` | `{baseUrl}` picked up internal scheme/host | Configure proxy and trusted forwarded headers |
| IdP redirects to right path, but Portal returns 404 | `redirectionEndpoint.baseUri` does not match the path | Check matcher and actual request path received by backend |
| Callback loops back to login page repeatedly | Callback not handled by filter, lost session, or exception handler redirects back | Inspect network redirect chain and handling filter |
| **authorization_request_not_found** | Authorization request store lacks the initiated request | Check session cookie, repository, and multiple replicas |
| **invalid_state** | State mismatches saved request or callback was reused | Check correlation; never disable state validation |
| Works locally, fails on staging | Public URL, profile, issuer, callback, or proxy differs | Compare actual generated URIs per environment |
| Callback gains or loses `/portal` | Context path / reverse proxy prefix stripping out of sync | Compare public URL, context path, forwarded prefix |
| Token endpoint returns **invalid_grant** | Code/redirect URI/PKCE may be inconsistent | Inspect saved transaction, code lifetime, and IdP config |
| Token endpoint returns **invalid_client** | Wrong secret or client authentication method | Verify confidential client registration/runtime secret |
| After login, fails to return to `/dashboard` | Success handler or `RequestCache` | Distinguish post-login redirect from OAuth callback redirect URI |

Do not draw conclusions from HTTP status alone: **401/403/404/302** all depend on filter chains, entry points, controllers, and error handlers. Determine whether the request was rejected **at the IdP**, **at the callback matcher**, or **after the callback filter began processing**.

## 17. Security Risks When Customizing the Redirect URI

### 17.1. Never Allow Clients to Supply an Arbitrary `redirect_uri`

Unsafe example:

~~~text
/oauth2/authorization/company?redirect_uri=https://attacker.example/callback
~~~

and then taking `redirect_uri` directly from the query parameter to modify the authorization request. This risks redirecting to untrusted destinations, leaking authorization codes, or creating open-redirect vulnerabilities if the IdP/client is misconfigured.

**Redirect URIs must come from trusted `ClientRegistration` config and the IdP's allowlist**, never freely controlled by the browser.

### 17.2. Never Turn a Wildcard Matcher into a Trust Decision

The pattern `/login/oauth2/code/*` enables the filter to accept callbacks by path; it **does not grant trust** to every IdP or every client ID. Trust still depends on client registration, `state`, code exchange, and OIDC/token validation.

### 17.3. Preserve State, Nonce, and PKCE

- `state` binds the authorization response to the initiated request.
- OIDC `nonce` binds the ID Token to the authentication transaction per OIDC rules.
- PKCE binds the authorization code to the `code_verifier` generated at transaction start.

If customizing the resolver or redirect URI, never delete, overwrite, or log these values carelessly. **Client secrets** also do not belong in the authorization request query string.

### 17.4. Avoid Leaking Authorization Codes on Callback

Authorization codes are short-lived and typically single-use, yet still sensitive. Callback URLs can end up in web server access logs, browser history, proxies, or observability systems. Avoid logging sensitive query strings; never send codes/states/ID Tokens/access tokens to analytics or public documentation.

### 17.5. HTTPS and Host Headers

Production requires HTTPS and a properly configured proxy. Never trust arbitrary `Host`/`Forwarded` headers from Internet clients; when using request-derived URL templates, strictly control which host/scheme sources the application accepts.

## 18. Applied Exercise

An application has the configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
~~~

And:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(endpoint ->
        endpoint.baseUri("/login/oauth2/code/*"))
);
~~~

IdP registers:

~~~text
https://portal.example.test/auth/callback/company
~~~

### Questions

1. If `{baseUrl}` is `https://portal.example.test`, what `redirect_uri` parameter is sent to the IdP?
2. Does the IdP have any reason to reject that redirect URI, assuming other settings are valid?
3. Will the callback be processed by `OAuth2LoginAuthenticationFilter` with the current matcher?
4. Which line in `SecurityFilterChain` must be changed for the callback to work?
5. After fixing the path, if `authorization_request_not_found` still occurs, what should be checked?

### Suggested Answers

1. `https://portal.example.test/auth/callback/company`.
2. The URI matches the registered redirect at the IdP, so **there is no mismatch solely from the redirect URI** under these assumptions. The IdP could still reject for other reasons.
3. **No.** The matcher `/login/oauth2/code/*` does not match `/auth/callback/company`.
4. Change to `baseUri("/auth/callback/*")` inside `redirectionEndpoint`.
5. Check the session cookie, `state`, `AuthorizationRequestRepository`, proxy handling, and session sharing across nodes. Do not disable state verification.

## 19. Short Alignment Checklist for Implementers

When rolling out a new callback, follow this sequence:

1. **Choose the final public URI**, e.g., `https://portal.example.test/auth/callback/company`.
2. **Set `ClientRegistration.redirectUri`** to a fixed URI or a template that expands to that exact URI.
3. **Set `redirectionEndpoint.baseUri`** to match the **path inside the Servlet** (e.g., `/auth/callback/*`).
4. **Register the final URI at the IdP** for the right client ID/environment.
5. **Inspect the URL generated when starting login**, specifically the `redirect_uri` and `state` parameters.
6. **Inspect the actual callback request**: path, method, cookie/session, and filter chain.
7. Once the callback is caught by the filter, **verify correlation** before investigating token endpoint and OIDC validation.

This sequence cleanly separates **registered URI errors**, **route/matcher errors**, and **state/session errors**. Inspecting the actual HTTP redirect is stronger evidence than guessing from a single YAML file in isolation.

## 20. Summary

In Spring Security OAuth 2.0/OIDC Client on Servlet, the **Redirect URI** is the full address placed in the authorization request so the Authorization Server knows where to return the browser. The **redirectionEndpoint base URI** is the pattern `OAuth2LoginAuthenticationFilter` uses to intercept callbacks in the application. The **Allowed redirect URI** at the IdP is the constraint enforced by the Authorization Server for the registered client.

These three places must **agree on URL and routing**, while serving distinct responsibilities. By default, the `{baseUrl}/login/oauth2/code/{registrationId}` template aligns with the `/login/oauth2/code/*` matcher. When changing the callback path, update **`ClientRegistration.redirectUri`**, **`redirectionEndpoint.baseUri`**, and the **IdP registration** together.

Finally, arriving at the right callback URL **is not enough to succeed at login**: Spring Security must still locate the saved authorization request and verify **`state`**, preserve PKCE/nonce as applicable, exchange a valid code, and verify OIDC tokens. Clearly understanding the distinction between **callback URL**, **filter matcher**, and **correlation** is the foundation for accurately diagnosing OAuth2 Login issues across local, staging, and production.
