# 9.11. Cookies, SameSite, Sessions, and Reverse Proxies in the Callback Step

## 1. Context: Right Callback URL, Yet Login Still Fails

Suppose an **Employee Portal** is built with **Spring Boot**, **Spring Security OAuth 2.0 Client**, and **OpenID Connect (OIDC)**. A user clicks **Sign in with Company Account**. Portal redirects the browser to the Identity Provider (IdP), the user enters credentials, the IdP authenticates them successfully, and redirects the browser back to:

~~~text
https://portal.example.test/login/oauth2/code/company?code=...&state=...
~~~

Even though the callback URL looks right, Portal throws an error such as:

- Initial authorization request not found.
- `state` value does not match the initiated request.
- After callback, the user is sent back to the login page or caught in a login loop.
- Login works normally locally, yet fails behind ingress/reverse proxy in staging or production.
- Cookie appears in the response on login start, yet is absent from the callback request.

These scenarios tie closely to **HTTP sessions**, **session cookies**, browser **SameSite** policies, **reverse proxy** configuration, and the **correlation** mechanism in the OAuth 2.0 Authorization Code Flow.

This lesson focuses on the conditions needed for a callback to **route to the right filter**, **locate the saved authorization request**, **correlate the transaction**, and **complete OIDC login**. Examples use Java 17+, Spring Boot 3, and Spring Security 6 on the **Servlet stack (Spring MVC)**. Hostnames and secrets are illustrative only.

## 2. Components Participating in the Callback

| Component | Responsibility |
|---|---|
| **Browser** | Holds Portal's cookie, navigates to the IdP, and returns to the callback via redirect or form POST |
| **Employee Portal** | OAuth 2.0 Client/OIDC Relying Party; stores authorization state in session, verifies callback, creates login session |
| **Authorization Server / OpenID Provider** | Authenticates user, returns authorization code and state, issues tokens when Portal exchanges code |
| **Reverse proxy / ingress** | Receives HTTPS from browser, forwards requests to app, controls forwarded host/scheme/prefix info |
| **Session store** | Holds session data Portal needs to match the authorization response |
| **Orders API** | Resource Server called by Portal after login using an access token; does not participate directly in Portal's callback |

Distinguish four artifacts often loosely called "tokens/login state":

1. **Portal's session cookie**, such as `JSESSIONID`, is the session identifier value sent by the browser to Portal.
2. **Pending authorization request** holds `state`, redirect URI, client registration, and PKCE/OIDC data needed for the next step. This data is typically stored **server-side**, bound to the session.
3. **Authorization code** is returned by the IdP on the callback; Portal exchanges the code for tokens at the token endpoint.
4. **ID Token, access token, and refresh token** (if issued) are results of code exchange and authentication; they are not Portal's session cookie.

**A session cookie is not an OAuth access token.** In a server-side web/BFF model, the browser does not need to hold access tokens for Portal to log in and call APIs on the user's behalf.

## 3. Overview of the Authorization and Callback Flow on Servlet

Spring Security typically uses:

- `OAuth2AuthorizationRequestRedirectFilter` to initiate the authorization request.
- `OAuth2AuthorizationRequestResolver` to construct the request sent to the IdP.
- `HttpSessionOAuth2AuthorizationRequestRepository` to save the authorization request before redirecting.
- `OAuth2LoginAuthenticationFilter` to receive the callback and coordinate authorization response checks.
- `SecurityContext` and session to maintain authenticated state.

Illustrative diagram:

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant P as Reverse proxy
    participant A as Spring Boot Portal
    participant S as HTTP Session Store
    participant I as OIDC Provider

    U->>B: Click Company Login
    B->>P: GET /oauth2/authorization/company
    P->>A: Forward request
    A->>A: Generate state, nonce/PKCE as applicable
    A->>S: Save OAuth2AuthorizationRequest in session
    A-->>P: 302 to IdP, Set-Cookie if creating new session
    P-->>B: Location and Portal session cookie
    B->>I: Follow redirect, authenticate at IdP
    I-->>B: Redirect with code and state
    Note over B: Browser decides whether to send Portal cookie per SameSite/Secure/Path/Domain
    B->>P: GET callback?code=...&state=... + Cookie (if permitted)
    P->>A: Forward callback
    A->>S: Look up session's authorization request
    S-->>A: Original request if session still valid
    A->>A: Verify state and transaction details
    A->>I: Exchange code for tokens via token endpoint
    I-->>A: Token response
    A->>S: Save SecurityContext and matching authorized client
    A-->>B: Redirect to application page
~~~

**Key point:** the IdP may return `code` and `state` completely intact, yet if the browser **fails to send Portal's session cookie** when returning to the callback, the app cannot find the saved authorization request to correlate against.

## 4. At Which Points Is the Session Used?

### 4.1. When Initiating Login

The browser visits:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
~~~

Spring Security creates `OAuth2AuthorizationRequest`, containing critical details such as:

- Chosen **client registration**, e.g., `company`.
- Portal's **redirect URI**.
- **`state`** used to bind the response to the request.
- OIDC **`nonce`**, if applicable.
- **PKCE code verifier** retained for code exchange when PKCE is enabled.

With standard Servlet config, `HttpSessionOAuth2AuthorizationRequestRepository` saves the request object in the **HTTP session**. If no session exists yet, the app may create one and return a session-identifying cookie.

Illustrative response:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=...
Set-Cookie: JSESSIONID=<session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Not every redirect must include a `Set-Cookie` header: if a session already exists, the browser may already hold the cookie from an earlier request. The snippet above shows the case where the app creates and sends a new cookie.

### 4.2. When the Callback Returns

The IdP redirects the browser back to Portal:

~~~http
GET /login/oauth2/code/company?code=<authorization-code>&state=<state> HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=<session-id>
~~~

The server uses the cookie to look up the right HTTP session, locate the saved authorization request, and match it against the authorization response. If the session does not exist or the request was deleted/consumed, correlation fails even if the callback URI matches.

### 4.3. After Login Succeeds

Spring Security finishes OIDC authentication and creates `Authentication`. The authenticated state can be saved via `SecurityContextRepository` into the HTTP session, depending on security config.

Spring Security may also perform **session fixation protection**, such as rotating the session ID after login. Therefore, seeing the **session cookie change after successful login** is not by itself an error. Distinguish the cookie of the **pre-callback pending** session from the cookie of the authenticated session.

Sessions can expire from timeout, be cleared on logout, be rotated by app policy, or be absent on another node. Having a cookie in the browser **does not guarantee** session data still exists on the backend.

## 5. Cookie Attributes That Directly Impact Callbacks

| Attribute | Effect | OAuth2/OIDC consideration |
|---|---|---|
| **Name** | Cookie name, e.g., `JSESSIONID` | Multiple apps on the same host must avoid overwriting each other's cookies |
| **Value** | Session identifier | Must be unpredictable and protected; never log it |
| **Secure** | Send cookie only over HTTPS connections, with browser-specific local dev exceptions | Enable in production using HTTPS |
| **HttpOnly** | Prevents JavaScript from reading the cookie via `document.cookie` | Enable to reduce session theft risk via scripts |
| **SameSite** | Controls whether cookies are sent on cross-site navigations/requests | Especially critical when the browser returns from IdP to Portal |
| **Path** | Restricts which URL paths receive the cookie | Callback must fall within the cookie's path scope |
| **Domain** | Restricts which hosts/domains receive the cookie | Host-only default is usually safer than widening across an entire domain |
| **Max-Age / Expires** | Browser-side cookie lifetime if set | Distinct from server-side session timeout and validity |

For example, when a cookie has:

~~~http
Set-Cookie: JSESSIONID=abc...; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

The browser can send the cookie to `/portal/login/oauth2/code/company`, yet **will not send it to `/login/oauth2/code/company`** because that path falls outside `Path=/portal`. This is a frequent bug when apps change context paths or proxies rewrite URLs without updating the cookie path to match.

**Domain** matters too: a host-only cookie set by `portal.example.test` is not automatically sent to `login.example.test`. That is normal, since the IdP does not need Portal's session cookie. Portal's cookie needs to be sent **when the browser returns to Portal's own host**.

## 6. Understanding SameSite Accurately at the Callback Step

**SameSite** is a cookie attribute that lets browsers decide whether to send cookies in cross-**site** contexts. The **site** concept is not identical to **origin**: two different origins may count as same-site in certain cases; modern browsers also factor in scheme under the schemeful same-site model.

If Portal is `https://portal.example.test` and the IdP is `https://login.company-idp.test`, the browser returning from IdP to Portal is normally a **cross-site navigation**. If both actually count as same-site under browser rules, cookie behavior may differ; never deduce same-site status solely from differing hostnames.

Three main values:

| SameSite | Top-level **GET** navigation from cross-site IdP to Portal | Cross-site **POST** from IdP to Portal | Notes |
|---|---|---|---|
| **Strict** | Usually **withholds** cookie | **Withholds** | Easily loses session on cross-site callbacks |
| **Lax** | Usually **sends** cookie | Usually **withholds** cookie | Fits common GET-redirect Authorization Code callbacks |
| **None** | Permitted subject to remaining cookie rules | Permitted subject to remaining cookie rules | Requires `Secure`; still subject to other browser cookie-blocking policies |

Key conditions:

- **SameSite=Lax** applies to **top-level navigations using safe methods like GET**; do not confuse with cross-site `fetch`/XHR calls or iframes.
- **SameSite=Strict** can cause the browser to **withhold Portal's cookie when the IdP redirects from another site**, losing the authorization request.
- **SameSite=None** must be paired with **Secure** in modern browsers and only works if the cookie also satisfies Domain, Path, expiry, and other browser cookie-blocking rules.
- Omitting `SameSite` **is not** a reliable way to ensure POST callback support; many browsers default undeclared cookies to Lax-like behavior, with implementation quirks you should not depend on.

**SameSite does not replace CSRF protection**, nor does it replace OAuth2/OIDC `state`, `nonce`, or PKCE.

## 7. Default GET Callback: SameSite=Lax Usually Fits

With **Authorization Code Flow** using query-string callbacks, the IdP typically returns an HTTP redirect sending the browser back to Portal:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.test/login/oauth2/code/company?code=<code>&state=<state>
~~~

The browser performs a **top-level GET navigation** to Portal. When the cookie has `SameSite=Lax`, `Secure`, and matching Domain and Path, the browser normally sends Portal's session cookie.

As a result:

1. `OAuth2LoginAuthenticationFilter` receives the callback at the matching path.
2. `AuthorizationRequestRepository` locates the request saved in the session.
3. Spring Security checks correlation of `state` and other required data.
4. Portal exchanges the authorization code for tokens and completes OIDC login.

That is why **Lax is a common choice** for session cookies in web apps using OIDC Authorization Code Flow with GET callbacks.

However, Lax **does not guarantee login success across all configs**. With a wrong cookie `Path`, different host, missing HTTPS for a `Secure` cookie, lost backend session, or misrouted proxy, the callback can still fail.

## 8. `form_post` Callbacks: Evaluate `SameSite=None` and CSRF

Some OpenID Providers support **`response_mode=form_post`**, where the IdP returns an HTML page with a form and the browser **POSTs** directly to Portal's callback URL.

Example request shape:

~~~http
POST /login/oauth2/code/company HTTP/1.1
Host: portal.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-id>

code=<authorization-code>&state=<state>
~~~

Because this can be a **cross-site POST**, a cookie set to `SameSite=Lax` is normally **not sent**. Consequently, Portal lacks the session needed for correlation.

If the system genuinely requires `form_post`, evaluate all of the following together:

1. **Cookie policy:** Does the session used at callback require `SameSite=None; Secure`?
2. **TLS and browsers:** Is HTTPS deployed properly? Do browsers block the cookie in that specific context despite `SameSite=None`?
3. **Callback filter:** Do Spring Security and your library version handle the method/form parameters of the chosen response mode?
4. **CSRF protection:** Does the CSRF filter block the POST callback before the OAuth2 Login filter handles it?
5. **AuthorizationRequestRepository:** Are the session and initial `state` still accessible?
6. **IdP configuration:** Does the provider accept and actually emit callbacks using the requested response mode?

If a CSRF exemption is needed for a thoroughly analyzed, clearly scoped **OAuth POST callback**, restrict the exemption strictly to that callback while keeping `state`, PKCE, nonce, and OIDC validations intact. Never disable CSRF across the entire Portal because of a callback error.

**Important:** `SameSite=None` makes cookies available on more cross-site requests per browser rules, so cookie-authenticated state-changing endpoints must be guarded with CSRF tokens/policies. Some browsers also enforce anti-tracking, third-party cookie restrictions, iframe, or webview limits; `SameSite=None` is not guaranteed to bypass those restrictions.

For a typical Portal, choosing a **top-level GET** callback when appropriate reduces special session-cookie requirements. However, the response mode must align with the IdP and agreed security model.

## 9. Spring Boot Configuration for Session Cookies

For example in production, Portal serves HTTPS at its public endpoint:

~~~yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        name: JSESSIONID
        http-only: true
        secure: true
        same-site: lax
~~~

Meaning:

- `http-only: true` restricts JavaScript from reading the cookie.
- `secure: true` requires browsers to send the cookie only over HTTPS.
- `same-site: lax` is the standard setting for cross-site top-level GET callbacks.
- `timeout: 30m` configures the Servlet container's session timeout; it is not the access token lifetime or IdP session lifetime.
- `forward-headers-strategy: framework` helps Spring see public scheme/host details forwarded by a trusted proxy, when infrastructure is configured properly.

Locally over plain **HTTP**, a `Secure` cookie may not behave like HTTPS production; use a separate local config:

~~~yaml
# src/main/resources/application-local.yml
server:
  port: 8080
  servlet:
    session:
      cookie:
        http-only: true
        secure: false
        same-site: lax
~~~

The local example is strictly for loopback development. Staging/production environments must use HTTPS with proper secret and session configurations.

If using `form_post` and confirmed to require cross-site POST cookies, setting `same-site: none` in that environment must be paired with `secure: true`, TLS, and matching CSRF protection. Never switch every environment to `None` out of habit when GET callbacks with Lax already meet your needs.

### 9.1. Be Careful When Modifying Path and Domain

Spring Boot/Servlet containers may default the cookie path to the context path. Do not blindly set `Path=/` for every app if Portal is mounted at `/portal` alongside other apps on the same host.

When configuring path explicitly:

~~~yaml
server:
  servlet:
    session:
      cookie:
        path: /portal
~~~

only use this if **the public callback URL genuinely lives under `/portal`** and proxy forwarding matches consistently. Likewise, avoid widening `Domain=.example.test` merely to "fix a cookie bug" when the callback already uses Portal's exact host.

The broader a cookie's scope, the more carefully you must evaluate collision risks across apps on the same domain and exposure from sibling subdomains.

## 10. Minimal OIDC Client and SecurityFilterChain Configuration

To see the relationship between callback and session, consider a client registration with default paths:

~~~yaml
# src/main/resources/application.yml
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

`OIDC_CLIENT_SECRET` must be injected via environment variables or a secret manager. Never commit real secrets to Git, browsers, or frontend bundles.

Session-based security config for web login:

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
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

By default, Spring Security uses:

~~~text
Login initiation URL:
  /oauth2/authorization/company

Callback handled by OAuth2LoginAuthenticationFilter:
  /login/oauth2/code/company

Redirect URI template:
  {baseUrl}/login/oauth2/code/{registrationId}
~~~

In this setup, **you do not need a custom `@GetMapping("/login/oauth2/code/company")` controller**; the filter handles the callback.

Never set `SessionCreationPolicy.STATELESS` on an HTTP-session-backed OAuth2 Login filter chain without simultaneously redesigning authorization request storage, `SecurityContext`, and callback correlation end to end. For standard MVC/OIDC login apps, the default session mechanism serves best.

## 11. Reverse Proxies Create Two Views of the URL

When deploying Portal behind a reverse proxy/ingress:

~~~text
Browser
   |
   | HTTPS https://portal.example.test
   v
Reverse proxy / ingress (TLS termination)
   |
   | HTTP http://portal-service:8080
   v
Spring Boot Portal
~~~

The browser only knows the public address `https://portal.example.test`. Spring Boot may only see the internal request `http://portal-service:8080`.

If the application uses:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

and fails to recognize the public URL, Spring Security may generate:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

instead of:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

The IdP normally checks `redirect_uri` against registered callbacks. An internal address, HTTP scheme, or wrong port can trigger `redirect_uri_mismatch` before the IdP ever redirects to the callback.

### 11.1. Forwarded Headers for Scheme, Host, Port, and Prefix

The proxy can pass details such as:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.test
X-Forwarded-Port: 443
~~~

Or use the standard `Forwarded` header, and when a path prefix exists, `X-Forwarded-Prefix` depending on infrastructure.

On the Spring Boot side:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

lets the Servlet request see the public scheme/host supplied by a trusted proxy.

**Mandatory trust condition:** the proxy at the trust boundary must **strip/overwrite any forwarded headers sent by external clients**, and only forward valid hosts. Never trust arbitrary `X-Forwarded-*` headers from the Internet: attackers could make the app generate redirect URLs or security metadata using a host/scheme of their choice.

### 11.2. Secure Cookies When TLS Terminates at the Proxy

Sometimes the backend speaks HTTP with the proxy while the browser speaks HTTPS. What the browser checks is whether the cookie in the public response has:

~~~http
Set-Cookie: JSESSIONID=<value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

and whether the actual callback travels over HTTPS on the matching host/path.

To avoid depending entirely on backend auto-detection of HTTPS requests when TLS terminates at the proxy, production setups typically **explicitly configure `server.servlet.session.cookie.secure=true`**, alongside valid forwarded headers and client-facing HTTPS.

Never turn off `Secure` in production merely because Spring Boot receives internal HTTP. That is a sign to inspect TLS termination and forwarded headers, or set the `Secure` cookie flag explicitly.

### 11.3. Context Path and Path Prefix

Suppose public Portal sits under:

~~~text
https://apps.example.test/portal
~~~

Public callback is:

~~~text
https://apps.example.test/portal/login/oauth2/code/company
~~~

There are at least two deployment patterns:

**Option A — Servlet context path `/portal`:**

~~~yaml
server:
  servlet:
    context-path: /portal
~~~

Here the browser sends paths with `/portal`, while Spring Security's callback matcher is still written using the **path inside the Servlet context**:

~~~text
/login/oauth2/code/*
~~~

**Option B — Proxy receives `/portal` and strips the prefix before forwarding:**

~~~text
Browser:
  /portal/login/oauth2/code/company

Backend receives:
  /login/oauth2/code/company
~~~

The app must receive accurate public prefix info when expanding `{baseUrl}` and building redirects, and the cookie `Path` must align with the public URL.

Never configure **overlapping servlet context path and proxy strip/add prefix rules**. If you see callback 404s or redirects to `/portal/portal/login/oauth2/code/...`, trace the path sent by the browser, the path forwarded by the proxy, and the Servlet matcher before making edits.

## 12. Aligning Redirect URI, Callback Matcher, and Cookies

All three layers must align:

| Check | Standard example | If wrong |
|---|---|---|
| **Redirect URI on `ClientRegistration`** | `https://portal.example.test/login/oauth2/code/company` | IdP may reject callback |
| **Allowed redirect at IdP** | Same exact full URI | Authorization Server reports mismatch |
| **`redirectionEndpoint` matcher** | `/login/oauth2/code/*` | Spring Security ignores the callback |
| **Cookie Domain/Path** | Host `portal.example.test`, Path covering callback | Browser withholds session cookie |
| **Cookie SameSite** | `Lax` for cross-site top-level GET callbacks | Cookie may be blocked on return request |
| **Cookie Secure and TLS** | Public HTTPS + `Secure` | Cookie may be rejected/not sent by browser |
| **Session store** | Session still exists on the right node/store | Authorization request cannot be found |
| **State** | Callback value matches saved request | Correlation fails |

For example, when changing the callback path to:

~~~text
https://portal.example.test/auth/callback/company
~~~

update synchronously:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
~~~

and:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(redirection ->
        redirection.baseUri("/auth/callback/*"))
);
~~~

then register the exact public URL at the IdP. Also verify whether the cookie `Path` covers `/auth/callback/company`.

**Changing `redirectionEndpoint.baseUri` does not automatically update `ClientRegistration` or cookie `Path`**. These are three independent parts of the same callback flow.

## 13. Sessions Across Multiple Instances: Right Cookie Can Still Lose State

Suppose Portal runs two nodes:

~~~text
                           +--> Portal A (session A)
Browser -> Load Balancer --|
                           +--> Portal B (session B)
~~~

What happens:

1. Browser initiates login and routes to **Portal A**.
2. The authorization request is saved in session A.
3. Browser receives the cookie and navigates to the IdP.
4. The callback returns to the load balancer, which this time routes to **Portal B**.
5. If Portal B **cannot access the same session data**, the original request is missing even though the browser sent the right cookie.

Two common operational strategies exist:

| Approach | Description | Notes |
|---|---|---|
| **Session affinity / sticky session** | Tries to route the same session to the same instance | Can lose sessions when nodes are replaced, restarted, or scaled |
| **Shared session store** | All instances access a protected shared session store | Requires designing for availability, access control, TTLs, and sensitive-data protection |

**Spring Session** can be used for shared sessions, for example backed by Redis. Authorization request data and `SecurityContext` then become accessible across nodes, depending on repository/serialization config and session lifecycle.

Example Portal dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Add only when using Spring Session with Redis:
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Example runtime config for an environment with managed Redis:

~~~yaml
spring:
  data:
    redis:
      host: ${SESSION_REDIS_HOST}
      port: ${SESSION_REDIS_PORT:6379}
  session:
    redis:
      namespace: employee-portal:sessions
~~~

This example only shows connection and namespace settings. Real deployments must provide Redis authentication, TLS, network access controls, TTL policies, and platform-appropriate high availability. Never store Redis credentials directly in the repository.

**Redis or a shared store does not fix `SameSite`, `Secure`, or `Path` bugs.** If the browser does not send the cookie, the backend has no session ID to query the shared store, even when every node shares the same Redis.

## 14. Session Fixation, Session Timeout, and Multi-Tab Login

### 14.1. Session ID Changes After Login

Spring Security commonly applies **session fixation** protection upon successful authentication, such as changing the session ID. Looking at the Network panel, you may see the `JSESSIONID` cookie updated after the callback.

Verify that:

- The **pre-callback** session cookie is sent so the authorization request is found.
- The callback is verified successfully.
- After login, the browser receives and continues sending the authenticated session cookie.

Do not assume every session ID rotation is an error.

### 14.2. Session Expires While the User Authenticates Slowly

If the user stays on the IdP page too long, Portal's HTTP session may expire before the callback arrives. The browser may still hold the cookie, yet the backend no longer has the authorization request, causing a correlation failure.

Timeouts must balance the time users need for MFA/consent against session security policies. **Never raise timeouts indefinitely** to dodge callback errors; handle error messages and login restarts cleanly.

### 14.3. Multiple Tabs or Multiple Login Initiations

Users may open two tabs to start login simultaneously, or click login repeatedly. Depending on how `AuthorizationRequestRepository` stores pending requests, an earlier authorization request may be overwritten or the callback may fail to find its matching transaction.

Apps using custom repositories must define clearly how **multiple concurrent transactions** are stored, how `state` binds to the right request, and when completed requests are deleted. Never use a `static` field or a single shared `state` across all users.

If the same callback is resubmitted after the code was spent or the authorization request was consumed, login may fail. That is the expected behavior of anti-reuse protection.

## 15. SameSite, CSRF, CORS, and OIDC State Are Distinct Concerns

All of these terms appear in login flows, yet operate at different layers:

| Mechanism | What does it control? | Role in the callback |
|---|---|---|
| **Cookie `SameSite`** | Whether the browser sends cookies by site/method context | Determines whether Portal receives the session cookie on callback |
| **CSRF protection** | Prevents another site from making a browser execute cookie-authenticated state changes | Matters for business endpoints and POST callbacks if used |
| **OAuth2 `state`** | Binds the authorization response to the initiated authorization request | Prevents transaction mix-ups and login CSRF per OAuth design |
| **OIDC `nonce`** | Binds the ID Token to the authentication transaction per OIDC rules | Adds verification at the OIDC layer |
| **PKCE** | Binds the authorization code to the initiating client's code verifier | Protects code exchange |
| **CORS** | Controls whether browsers let JavaScript read cross-origin fetch/XHR responses | Does not govern top-level login redirects the way SameSite governs cookies |

**Never use wildcard CORS to "fix" a missing cookie on an OIDC callback.** A top-level redirect from the IdP does not behave like a cross-origin `fetch`/XHR. Changing CORS has zero effect on `SameSite` or lost sessions.

Similarly, **disabling CSRF globally** cannot make a browser send a cookie blocked by `SameSite`/`Path`/`Domain`. If a callback lacks a session cookie, fix the root cause in browser cookie policy or URL/session architecture.

## 16. IdP Cookies Differ from Portal Cookies

When a user logs in at the IdP, the IdP may set its own cookie, e.g.:

~~~text
Host: login.company-idp.test
Cookie: IDP_SESSION=...
~~~

Portal also has its own cookie:

~~~text
Host: portal.example.test
Cookie: JSESSIONID=...
~~~

The two cookies serve different functions:

- **The IdP cookie** maintains authentication or SSO state at the identity provider.
- **Portal's cookie** identifies the pre-callback pending session and the application login session.

When the browser navigates to the IdP, Portal's cookie is normally **not sent to the IdP**; that is not an error. When the browser returns to Portal, the IdP cookie is normally **not sent to Portal**; Portal only needs its own cookie and a valid authorization response.

Consequently, a user may remain signed into SSO at the IdP after losing Portal's session, or log out of Portal while the IdP session remains active. They have two separate session lifecycles.

## 17. Observing Actual Requests with Browser Developer Tools

You must pinpoint the exact boundary where the cookie or session is lost. In an authorized dev/test environment, open the **Network** tab, enable request recording before clicking login, and check step by step:

### 17.1. Authorization Initiation Request

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
~~~

On the redirect response to the IdP, check:

- Does `Location` point to the right authorization endpoint?
- Does the decoded `redirect_uri` inside `Location` match the exact public URL?
- If a session was created, does the response include `Set-Cookie`?
- Does the cookie have appropriate `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain`?
- Did the browser display any cookie-blocked or rejected warning?

### 17.2. Returning Callback Request

Find the request to `/login/oauth2/code/company` or your custom callback. Check:

- Did the request use **GET** or **POST**?
- Did the browser send **Portal's session cookie**? Only confirm presence—do not copy its value.
- Do host/scheme/path match the registered public callback?
- If using form POST, how are `SameSite` and CSRF interacting?
- Was the request routed to the right app/filter?

### 17.3. Server-Side Outcome

Using sanitized logs with sensitive data redacted, determine:

- Did Spring Security's callback filter process the request?
- Did `AuthorizationRequestRepository` find the prior request?
- Was there a state/correlation error or a code-exchange error at the token endpoint?
- In multi-node setups, which node received the callback and is session data shared?

**Never log or paste into public docs** values of `JSESSIONID`, authorization codes, state, nonce, PKCE verifiers, ID Tokens, access tokens, refresh tokens, or client secrets. Those values can be used to hijack sessions or correlate/compromise transactions.

### 17.4. Why Is `curl` Insufficient to Test SameSite?

You can check basic HTTP redirects:

~~~bash
curl -i "https://portal.example.test/oauth2/authorization/company"
~~~

Or manage cookies in a curl jar when probing an endpoint:

~~~bash
curl -i -c cookies.txt "https://portal.example.test/oauth2/authorization/company"
~~~

However, **`curl` does not enforce browser navigation-context `SameSite` policies like a real browser**. A curl test successfully sending a cookie does not prove a browser will send it after a cross-site POST/redirect. When suspecting `SameSite`, inspect a real browser and its cookie policies. Never upload a cookie jar holding real sessions to a ticket or repository.

## 18. Common Error Scenarios and Isolation Guide

| Symptom | Likely area | What to check |
|---|---|---|
| IdP reports `redirect_uri_mismatch` | Proxy broke scheme/host/prefix, or wrong client registration/IdP allowlist | Actual `redirect_uri` value sent to IdP |
| Browser hits right callback URL without sending `JSESSIONID` | `SameSite`, `Secure`, `Domain`, `Path`, or browser policy | Cookie attributes, request method, Network cookie warnings |
| Cross-site GET callback loses cookie under `SameSite=Strict` | `Strict` blocks cookies on cross-site navigations | `SameSite` policy; consider `Lax` if flow suits |
| POST `form_post` loses cookie under `SameSite=Lax` | Cookie withheld on cross-site POST | Response mode, `SameSite=None` + `Secure` if appropriate, CSRF |
| Cookie present on request, yet authorization request not found | Session expired, data absent on receiving node, inconsistent repository | Session TTL, session store, load balancer, repository |
| Callback goes to `http://internal-host` or wrong hostname | Wrong forwarded headers/redirect template | Trusted proxy, `{baseUrl}`, `Location` |
| Callback returns 404 | Rewritten prefix/path or `redirectionEndpoint` matcher mismatch | Public path, backend path, filter matcher |
| Works on one node, fails when scaling | Local session or unstable affinity | Shared session store/affinity |
| After login, still loops back to login page | New session cookie not saved/sent, `SecurityContext` not persisted | Post-login cookie, session fixation, session store |
| Callback gets CSRF 403 | POST callback blocked by CSRF filter | Response mode and endpoint-scoped CSRF policy |
| `invalid_state` error | Original session/request missing or state mismatch | Cookies, session, lifetime, multiple tabs, reused callback |
| Token endpoint returns `invalid_client` | Wrong client secret/auth method | Client registration and runtime secret, not `SameSite` |
| Token endpoint returns `invalid_grant` | Expired/spent code, PKCE or redirect URI inconsistency | Code exchange step and IdP config |

Never deduce causes from HTTP status codes like 302, 401, 403, or 404 alone. The same status code can originate from an entry point, CSRF filter, callback filter, controller, or reverse proxy.

## 19. Three Practical Scenarios

### Scenario A: GET Callback with SameSite=Lax

Setup:

~~~text
Portal:  https://portal.example.test
IdP:     https://login.company-idp.test
Cookie:  Secure; HttpOnly; SameSite=Lax; Path=/
Callback method: GET
~~~

When the IdP redirects back to Portal via **top-level GET**, the browser usually sends Portal's session cookie. If login still fails, focus next on **state**, session store, routing, and token exchange rather than switching the cookie to `None`.

### Scenario B: `form_post` Callback with SameSite=Lax

Setup:

~~~text
Portal:  https://portal.example.test
IdP:     https://login.company-idp.test
Cookie:  Secure; HttpOnly; SameSite=Lax; Path=/
Callback method: POST (cross-site form_post)
~~~

Browsers usually withhold cookies on cross-site POSTs. Spring Security may fail to find the original authorization request. The remedy is **confirming the required response mode**, evaluating `SameSite=None` + `Secure`, and scoping CSRF handling for the callback alongside appropriate security controls.

### Scenario C: Public HTTPS, Internal HTTP

Setup:

~~~text
Public callback:
  https://portal.example.test/login/oauth2/code/company

Backend URL:
  http://portal-service:8080

Wrong generated redirect_uri:
  http://portal-service:8080/login/oauth2/code/company
~~~

This is a **public URL/proxy** problem, not `SameSite`. Inspect forwarded headers, `server.forward-headers-strategy`, hostname allowlists, and exact redirect URI registration at the IdP. After fixing the URI, still verify the session cookie on callback.

## 20. Comprehension Check Exercises

**Exercise 1.** Portal sets a cookie:

~~~http
Set-Cookie: JSESSIONID=...; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Yet the IdP redirects the browser back to:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Question: Why does the cookie fail to arrive, even though `SameSite=Lax` supports top-level GET callbacks?

**Hint:** Cookie `Path=/portal` does not cover `/login/oauth2/code/company`. Align the public path and cookie path/context path properly rather than just changing `SameSite`.

**Exercise 2.** Portal uses GET callbacks and `SameSite=Strict` cookies. The IdP is on another site. Returning from login reports a missing authorization request.

**Hint:** `Strict` typically blocks cookies when browsers navigate cross-site back to Portal; `Lax` is better suited for standard top-level GET callbacks. Still verify `Domain`, `Path`, `Secure`, and session store.

**Exercise 3.** Production has two nodes; the authorization start request hits Node A, and the callback hits Node B. The browser sends the right `JSESSIONID`, yet the authorization request is not found.

**Hint:** Check shared session storage or session affinity. `SameSite` does not resolve session data living solely on Node A.

**Exercise 4.** The browser receives the right cookie on callback, yet the IdP reports `invalid_redirect_uri` right at initiation.

**Hint:** Inspect the `redirect_uri` generated by Portal, forwarded public scheme/host/prefix, and the registered URI at the IdP. The failure happens before the browser ever returns to the callback.

**Exercise 5.** The engineering team disables CSRF across the entire Portal to support `response_mode=form_post`, yet the browser still does not send `JSESSIONID`.

**Hint:** The CSRF filter does not control whether browsers send cookies. Check `SameSite`, `Secure`, HTTPS, `Domain`/`Path`, and browser policies; then design narrowly scoped CSRF handling.

## 21. Architectural Summary

In OAuth 2.0/OIDC callbacks on Spring Security Servlet, **having the right URI is only part of the requirement for success**. The browser must also send the **matching session cookie**, Portal must reach the **saved authorization request**, and Spring Security must correlate **`state`** before exchanging the authorization code for tokens.

For **top-level GET** callbacks, `SameSite=Lax` usually allows cookies to return from a cross-site IdP. For **cross-site POST** callbacks such as `form_post`, you may need `SameSite=None; Secure` combined with CSRF protection and attention to browser policies. In both cases, **`HttpOnly`, `Secure`, `Path`, `Domain`, session lifetime, and session storage** must all be properly understood.

When Portal sits behind a reverse proxy, the public URL, forwarded headers, cookies, and callback matcher must all describe one coherent path: the browser sees **public HTTPS and hostname**, the proxy forwards in a controlled way, and the backend handles the right path. Across multiple replicas, sessions must be routed or shared consistently. Mastering these boundaries lets you pinpoint callback bugs accurately and build reliable, secure correlated login flows across local, staging, and production.
