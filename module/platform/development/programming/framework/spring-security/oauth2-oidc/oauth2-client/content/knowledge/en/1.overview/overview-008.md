# 1.8. Foundational Prerequisites: HTTP, TLS, Sessions, JWT, and Spring Security

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** application, clicking "Sign in with identity provider" is actually a coordination of multiple mechanisms: HTTP redirecting the browser, TLS protecting the transport channel, sessions maintaining user state in the application, tokens carrying identity and access permissions, and Spring Security orchestrating authentication steps and endpoint protection.

This lesson builds the foundation to read and understand `oauth2Login()` configuration, trace the OIDC login process, and distinguish components that are frequently confused. Examples use **Spring Boot 3.x, Spring Security 6.x, and a Servlet application (Spring MVC)**; implementation details may vary by version or identity provider.

## 1. The Big Picture: Who Talks to Whom?

The main roles:

| Component | Role in the Login Flow |
| --- | --- |
| **Browser (user agent)** | Sends HTTP requests, follows redirects, holds cookies for the application and the identity provider. |
| **Spring application (OAuth 2.0 Client / Relying Party)** | Initiates login requests, receives authorization codes, exchanges codes for tokens, validates OIDC information, and creates an application login session. |
| **Authorization Server / OpenID Provider (OP)** | Authenticates users, prompts/accepts consent when needed, and issues authorization codes and tokens. |
| **Resource Server / API** | Accepts access tokens to protect resources; may be a separate service from the Spring application. |

`OAuth 2.0` provides an **authorization** mechanism: a client can obtain an access token to call an API. `OIDC` extends OAuth 2.0 with an **identity authentication** layer, specifically the `ID Token` and the rules for validating it.

A common flow is the **Authorization Code Flow**, often combined with **PKCE (Proof Key for Code Exchange)**:

```mermaid
sequenceDiagram
    autonumber
    actor U as User / Browser
    participant C as Spring OAuth2 Client
    participant P as OpenID Provider
    participant A as API / Resource Server
    U->>C: GET /account
    C-->>U: 302 to login page / OAuth2 entry point
    U->>C: GET /oauth2/authorization/demo
    C-->>U: 302 to authorization endpoint (state, nonce, PKCE)
    U->>P: GET /authorize?... over HTTPS
    P->>U: Login / consent (if needed)
    P-->>U: 302 to callback with code and state
    U->>C: GET /login/oauth2/code/demo?code=...&state=...
    C->>P: POST /token (code, redirect_uri, PKCE, client auth)
    P-->>C: ID token, access token, and related info
    C->>C: Validate state, ID token; create Authentication
    C-->>U: Set-Cookie: JSESSIONID=...; 302 to original page
    U->>C: GET /account + Cookie: JSESSIONID=...
    C-->>U: 200 content for authenticated user
    opt Application calls API on behalf of user
        C->>A: Authorization: Bearer <access_token>
        A-->>C: Protected resource
    end
```

The diagram shows that the **authorization code**, **tokens**, and **session cookie** appear at different stages. They cannot be used interchangeably.

## 2. HTTP: Requests, Responses, Headers, Cookies, and Redirects

### 2.1. HTTP Is a Request–Response Protocol

The browser sends a request; the server returns a response. Each request carries a method, path, headers, and optionally a body. HTTP does not inherently remember "who the previous request belonged to"; continuity must be created via cookies, sessions, or credentials attached to each request.

Common methods in an OIDC client:

| Method | Example | Meaning |
| --- | --- | --- |
| `GET` | `GET /oauth2/authorization/demo` | Initiates login and redirects the browser. |
| `GET` | `GET /login/oauth2/code/demo?code=...&state=...` | Receives the callback with the authorization code when using response mode `query`. |
| `POST` | `POST /oauth2/token` or the OP's token endpoint | Client exchanges the authorization code for tokens via back-channel communication. |
| `POST` | `POST /logout` | Performs application-side logout in Spring Security configurations typically protected with CSRF. |
| `GET` / `POST` | Calling a protected API | Sends the access token via the `Authorization` header when using a Bearer token. |

**HTTP status codes** are critical when debugging:

- `200 OK`: request processed successfully; by itself it does not prove the user has been authenticated.
- `302 Found` or `303 See Other`: response requesting a redirect; the browser reads the `Location` header and sends a new request.
- `400 Bad Request`: missing/invalid parameter or invalid OAuth request.
- `401 Unauthorized`: request lacks credentials or has invalid credentials, commonly seen on APIs using Bearer tokens.
- `403 Forbidden`: request was recognized/authenticated but lacks permissions; can also result from a failed CSRF check.
- `5xx`: server-side or infrastructure processing error.

For an HTML endpoint requiring login, Spring Security typically starts login with a **redirect**. For an API configured for Bearer tokens, the response is usually `401`. Exact behavior depends on the `SecurityFilterChain` and `AuthenticationEntryPoint`.

### 2.2. Redirects Are Separate HTTP Requests

Simplified example (values and URLs are illustrative only):

```http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.com

HTTP/1.1 302 Found
Location: https://idp.example.com/authorize?response_type=code&client_id=demo-client&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile&state=RANDOM_STATE&code_challenge=CHALLENGE&code_challenge_method=S256
```

After the user logs in at the OP:

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=ONE_TIME_CODE&state=RANDOM_STATE
```

It is the browser that visits the URL in `Location`. Meanwhile, exchanging `code` for tokens is usually an **HTTP POST from the Spring backend to the OP**, not passing through browser JavaScript for server-side web applications.

A typical code-exchange request uses `Content-Type: application/x-www-form-urlencoded` and parameters `grant_type=authorization_code`, `code`, `redirect_uri`, and `code_verifier` (if using PKCE). A confidential client must also authenticate to the token endpoint using a method supported by the OP, such as `client_secret_basic`. Never place `client_secret` in URLs or public JavaScript code.

### 2.3. Headers, Query Strings, and Cookies Serve Different Roles

- **Query string** holds authorization request/callback parameters such as `code` and `state`. URLs can be stored in browser history, access logs, or monitoring systems; avoid placing access tokens or client secrets in URLs.
- **`Authorization: Bearer ...`** typically carries the access token when the application calls an API. Bearer tokens operate on the principle that whoever possesses a valid token can use it within the granted scope.
- **`Cookie`** carries the session identifier of the *target application*. A cookie from `idp.example.com` does not automatically become a cookie for `app.example.com` because browsers enforce domain, path, and cookie policies.
- **`Set-Cookie`** is a response header used by the server to instruct the browser to store/update a cookie.
- **`Cache-Control: no-store`** is appropriate for responses containing sensitive data such as tokens and many pages with personal data. Exact headers also depend on endpoint type and caching policy.

**`redirect_uri` must be registered and match the OP configuration** according to the provider's rules. Differences in scheme (`http`/`https`), hostname, port, path, or trailing `/` can cause the request to be rejected. In Spring Security, the default OAuth 2.0 login callback path is `/login/oauth2/code/{registrationId}`.

## 3. TLS/HTTPS: Protecting Transport and Server Identity

HTTPS is HTTP running over **TLS (Transport Layer Security)**. When a browser connects to `https://app.example.com` or the backend connects to the token endpoint over HTTPS, TLS serves three main purposes:

1. **Confidentiality in transit**: passive eavesdroppers cannot read cookies, codes, tokens, or request/response bodies.
2. **Transport integrity**: reduces the risk of content tampering in transit.
3. **Server authentication**: the client verifies the certificate and hostname to know it is connecting to the trusted server.

TLS **does not replace** `ID Token` validation, API authorization checks, protecting data at rest on the server, or session management. An improperly signed JWT remains untrustworthy even when delivered over HTTPS.

### 3.1. Certificates, Trust Chain, and Hostname Verification

TLS clients check certificate validity periods, the certificate chain up to a trusted CA, and the hostname. Errors such as expired certificates, domain mismatches, untrusted CAs, or misconfigured TLS interception can halt OAuth login before tokens are even received.

Never "fix" this by disabling certificate verification or configuring the HTTP client to accept all hostnames. If an internal environment uses a private CA, configure the trust store properly.

### 3.2. HTTPS at Reverse Proxy / Load Balancer

A Spring application may run plain HTTP internally behind a reverse proxy terminating TLS. In that setup, ensure:

- Browsers still use HTTPS on the public domain; the proxy forwards headers and scheme consistently.
- The application derives the correct **external base URL** when generating `redirect_uri`. Headers such as `Forwarded` or `X-Forwarded-Proto` must only be trusted when arriving from a controlled proxy.
- The session cookie has the `Secure` flag so the browser never sends it over public plain HTTP connections.
- OIDC callbacks, paths, and public hostnames match the configuration at the OP.

You can use Spring Boot's `server.forward-headers-strategy` according to your proxy deployment, while configuring trusted proxies appropriately. Production normally uses HTTPS across all public access paths; loopback HTTP exceptions for development must be controlled separately.

## 4. Sessions and Cookies: Maintaining Login After Callback

### 4.1. Sessions Solve HTTP Statelessness

After successful OIDC authentication, Spring Security can place `Authentication` into `SecurityContext` and persist it across requests using an **HTTP session**. The browser receives a **session ID**, typically as a `JSESSIONID` cookie when using the default servlet container.

```http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Location: /account
```

On the next request:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=RANDOM_SESSION_ID
```

The server uses the session ID to look up the session associated with the user. **The cookie normally contains only the session ID**, not the ID Token or access token. `SecurityContext` data and, depending on the storage mechanism, OAuth authorized client info remain on the server side.

The application session, the login session at the OP, and the access token lifetime are **three independent lifecycles**. Application session expiration does not mean the user logged out of the OP; access token expiration does not necessarily expire the application session.

### 4.2. Cookie Attributes to Understand

| Attribute | Purpose | Notes |
| --- | --- | --- |
| `Secure` | Only send cookie over HTTPS connections (loopback exceptions depend on browser). | Should be enabled in HTTPS deployments. |
| `HttpOnly` | Browser JavaScript cannot read the cookie directly. | Reduces cookie theft risk via certain XSS vectors, does not eliminate XSS. |
| `SameSite=Lax` | Restricts sending cookies in cross-site contexts. | Usually suitable for top-level GET OIDC callbacks; `form_post` callbacks require evaluation. |
| `SameSite=Strict` | Stronger cross-site restriction. | Can cause login redirects/callbacks to miss cookies. |
| `SameSite=None` | Allows cookies in supported cross-site contexts. | Must be paired with `Secure`; consider CSRF and browser policies. |
| `Path` / `Domain` | Limits URLs/hosts receiving the cookie. | Use the narrowest scope needed; avoid sharing cookies across unrelated subdomains. |
| `Max-Age` / `Expires` | Defines cookie lifetime in the browser. | Not synonymous with server-side session timeout. |

Spring Boot can configure session cookies for an HTTPS application:

```yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

This is an illustrative setting; the final configuration must consider proxy topology, callback method, and cookie policies in the runtime environment.

### 4.3. Session Fixation, CSRF, and Multi-Server Session Storage

- **Session fixation**: an attacker tries to force a victim to use a known session ID. Spring Security provides session fixation protection during login, typically changing the session ID after authentication.
- **CSRF (Cross-Site Request Forgery)**: browsers automatically send session cookies when calling the application, so state-changing requests (POST/PUT/PATCH/DELETE) require proper CSRF protection. `SameSite` helps but does not completely replace CSRF tokens. Never disable `csrf` merely to resolve a `403` error without finding the root cause.
- **Logout**: application logout typically clears `SecurityContext`/session and associated cookies; synchronized logout with the OP is a separate flow that may require OIDC RP-Initiated Logout.
- **Multiple instances**: if sessions live in a single JVM's memory, requests routed to another instance may lose the session. Consider sticky sessions or a shared session store such as Spring Session + Redis.
- **Session timeout**: the application should enforce appropriate timeouts and manage authorized credentials, including access/refresh tokens stored on the backend.

## 5. JWT: Structure, Signature, and Trust Conditions

**JWT (JSON Web Token)** is a token format containing a set of **claims** (information such as subject, issuer, audience, expiration). JWT is not the name of a login protocol: OAuth 2.0 and OIDC define **what tokens are issued/used for**; JWT describes **one way to represent a token**.

A signed JWT in compact JWS form usually has three dot-separated parts:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Example header and payload **after decoding**, illustrative only:

```json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "JWT"
}
```

```json
{
  "iss": "https://idp.example.com",
  "sub": "user-123",
  "aud": "demo-client",
  "iat": 1794816000,
  "exp": 1794819600,
  "nonce": "random-nonce-from-login"
}
```

Here `iss` is issuer, `sub` is subject identifier at the issuer, `aud` is intended recipient, `iat` is issued-at timestamp, and `exp` is expiration timestamp. `nonce` binds the ID Token to the OIDC authentication request when the client sent a nonce. Timestamp values are illustrative only, not a real usable token.

**Base64URL is representation encoding, not secret encryption.** Anyone holding a JWS-signed JWT can usually read its header and payload; only the signature guarantees integrity and origin when properly verified. JWE-format JWTs can be encrypted, with a compact structure typically containing five parts; never assume all JWTs are encrypted.

### 5.1. Mandatory Context-Specific Checks

When a component receives a JWT, **decoding the string** is not enough to trust its contents. Checks include:

1. **Signature and algorithm**: verify the signature using a trusted key and permitted algorithm; never accept `alg: none` or let the token dictate algorithm policy.
2. **Issuer (`iss`)**: the token must be issued by the exact configured provider.
3. **Audience (`aud`)**: the token must be intended for the exact client (ID Token) or API (access token) receiving it.
4. **Timestamps (`exp`, `nbf`, `iat`)**: verify the token is still valid and satisfies time constraints; use a small, controlled clock skew.
5. **Purpose-specific claims**: for OIDC ID Tokens this can include `nonce`, `azp`, and other authentication requirements; for access tokens evaluate scope/authority and API policy.

For asymmetrically signed tokens, the OP usually publishes a **JWKS (JSON Web Key Set)** at an endpoint declared in metadata. The `kid` header helps select the matching key from the trusted key set. Keys can rotate; the application needs to handle key updates, yet **must not** arbitrarily fetch keys from URLs dictated by an unverified token itself.

### 5.2. Access Token, ID Token, Refresh Token, and Session Cookie

| Data | Who Issues / Manages It? | What Is It Used For? | Where Is It Typically Presented? |
| --- | --- | --- | --- |
| **Authorization code** | Authorization Server | Exchanged once for tokens at the token endpoint. | Callback to the client, usually via query string. |
| **Access token** | Authorization Server | Grants access to resources within granted scopes. | `Authorization: Bearer ...` header when calling APIs. |
| **ID Token** | OpenID Provider | Asserts authentication event and user identity to the OIDC Client. | Received by the client via token endpoint and validated at login. |
| **Refresh token** | Authorization Server (if issued) | Requests new access tokens per OP policy. | Client back-channel; must be stored securely. |
| **Session ID** | Web application / session store | Looks up the application's login session. | Cookie sent by the browser back to the application. |

Key takeaways:

- **Access tokens do not have to be JWTs**; some providers use opaque tokens. APIs can validate JWTs locally or call an introspection endpoint depending on token type and configuration.
- **ID Tokens are usually JWTs** but **are not access tokens**: an API should never accept an ID Token merely because its signature is valid.
- **Refresh tokens** are highly sensitive; never assume they are JWTs and never expose them to the browser without a proper design reason.
- **Session cookies** may suffice for a browser accessing a logged-in website, but a cookie itself is not a bearer access token for calling another OAuth2 API.

## 6. `state`, `nonce`, and PKCE: Three Values with Distinct Jobs

Three mechanisms often appear together in an authorization request:

| Value | When Created / Sent? | Validation / Function |
| --- | --- | --- |
| **`state`** | Created by client when starting login, sent to authorization endpoint. | Callback must return the exact `state`; binds response to initiated request and prevents login CSRF. |
| **`nonce`** | Sent by OIDC Client in authorization request when nonce is used. | OP embeds nonce in ID Token; client checks exact sent value to prevent replay and bind token to authentication session. |
| **`code_verifier` / `code_challenge` (PKCE)** | Client generates random secret, sends challenge in authorization request; keeps verifier for token request. | OP checks transformation of verifier matches challenge; makes intercepted authorization codes difficult to exchange by another party. |

With `code_challenge_method=S256`:

```text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
```

`state` does **not** replace PKCE; `nonce` does **not** replace `state`. In Servlet Spring Security applications, the authorization request and `state` are typically held temporarily in the HTTP session via `AuthorizationRequestRepository`; if the session cookie disappears before callback, callback verification can fail.

Spring Security supports PKCE in OAuth 2.0 Client; exact activation rules depend on client type and configuration. For modern Authorization Code Flows, use PKCE even for confidential clients when supported by the OP.

## 7. How Does Spring Security Connect These Layers?

### 7.1. Security Filter Chain in a Servlet Application

In Spring MVC, requests pass through **Servlet Filters** before reaching controllers. Spring Security uses `FilterChainProxy` and one or more `SecurityFilterChain`s to determine which requests require authentication and which mechanisms apply.

```text
Browser / HTTP request
    |
    v
Servlet container
    |
    v
springSecurityFilterChain (FilterChainProxy)
    |-- load appropriate SecurityContext
    |-- read cookie / receive OAuth2 callback / verify credentials
    |-- handle CSRF and other security checks
    |-- check URL access permissions
    v
DispatcherServlet -> Controller
    |
    v
HTTP response (redirect / 200 / 401 / 403 ...)
```

Concepts to distinguish:

- **`SecurityFilterChain`**: set of security rules for requests, declared as a bean.
- **`Authentication`**: object describing principal, authorities, and authentication state.
- **`SecurityContext` / `SecurityContextHolder`**: where Spring Security holds `Authentication` while processing a request; repository mechanisms save/restore context across requests.
- **`AuthenticationManager` / `AuthenticationProvider`**: coordinates or executes authentication per mechanism.
- **`AuthenticationEntryPoint`**: decides how to initiate authentication for unauthenticated requests, such as redirecting to a login page or returning `401`.
- **`Authorization`**: step deciding whether the current principal may access a resource. Authentication (verifying "who") differs from Authorization (checking "what they may do").

Do not think that every request calls the OP to re-authenticate. After a successful login callback, web applications typically restore `SecurityContext` from the session.

### 7.2. Distinguishing Spring Security's Three OAuth2 Feature Groups

| Spring Security Configuration | Use Case | Focus Requests / Tokens |
| --- | --- | --- |
| `oauth2Login()` | User logs into website via an OP. | Browser redirect, code callback, ID Token; application creates a login session. |
| `oauth2Client()` | Application calls APIs on behalf of a user or with client credentials. | Managing authorized clients, acquiring and using access tokens for outbound requests. |
| `oauth2ResourceServer()` | Application's API accepts Bearer tokens from callers. | Validating inbound request tokens, enforcing scopes/authorities and API policies. |

One application can play multiple roles, but **never assume** enabling `oauth2Login()` automatically makes API endpoints validate Bearer tokens. That is a separate resource server mechanism.

### 7.3. Default Endpoints of `oauth2Login()`

In the default configuration, with client registration ID `demo`:

| URL | Related Filter | Role |
| --- | --- | --- |
| `/oauth2/authorization/demo` | `OAuth2AuthorizationRequestRedirectFilter` | Builds authorization request and redirects browser to the OP. |
| `/login/oauth2/code/demo` | `OAuth2LoginAuthenticationFilter` | Receives callback, validates login request, and performs code exchange. |
| `/login` | Spring Security login page mechanism | Can serve a default login page with links to OAuth2 providers, depending on configuration. |

When processing OIDC, Spring Security validates the ID Token and creates a principal such as `OidcUser`. Without the `openid` scope, standard OAuth 2.0 login may use `OAuth2User` instead of an OIDC principal.

## 8. Example Configuration of a Basic OIDC Client

Suppose a Spring Boot application serves a website with an `/account` endpoint and the OP publishes OIDC discovery metadata. The application runs at `https://app.example.com`; `demo` is the registration name we chose.

### 8.1. Dependency

With Maven using Spring Boot's dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

This starter integrates components for OAuth 2.0 Client and OAuth 2.0 Login. If the application uses Thymeleaf, Spring MVC, or another template engine, add the corresponding dependencies for the UI layer.

### 8.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          demo-provider:
            issuer-uri: https://idp.example.com

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Where:

- `registration.demo` is the client registration; `demo-provider` points to the OP configuration.
- `issuer-uri` must be the real issuer published by the OP. Spring uses discovery metadata when supported by the OP; `https://idp.example.com` here is an example domain only.
- The `openid` scope enables OIDC login. The `profile` and `email` scopes request additional claims per OP policy; not every provider returns every claim.
- `{baseUrl}` and `{registrationId}` are placeholders processed by Spring Security in the redirect URI, not environment variables.
- `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are loaded from the environment or a secret store. **Never commit client secrets to Git.**
- `redirect-uri` must be registered correspondingly at the OP and resolve to the correct external URL behind a proxy.

### 8.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

This configuration permits public resources, requires login for the rest, and enables OIDC/OAuth2 Client mechanisms. **Do not disable CSRF** in a session-based website example. Spring Security handles many details such as authorization requests, callbacks, and `SecurityContext` through the configured components.

A controller can read the principal after the user logs in:

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/account")
    public Map<String, String> account(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "subject", user.getSubject(),
            "displayName", user.getFullName() != null
                ? user.getFullName() : "(not provided)"
        );
    }
}
```

This example is only for an **OIDC** login session having an `OidcUser`. Never return raw ID Tokens, access tokens, refresh tokens, or all claims in a response just to verify login. In practice, return only the data the UI needs and the user is authorized to view.

When the client needs to call an external API, **`OAuth2AuthorizedClient`** associates the client registration, principal, and issued access token. The application can integrate with `OAuth2AuthorizedClientManager` or corresponding support mechanisms. Calling an API with an access token does not turn a session cookie into an access token.

## 9. Tracing a Request from Unauthenticated to Logged In

Suppose a user opens `https://app.example.com/account`:

1. **Browser → Spring:** sends `GET /account` without a valid login session. Spring Security determines the URL requires authentication and directs the user to login.
2. **Browser → Spring:** opens `/oauth2/authorization/demo`. Spring creates the authorization request, stores correlation data (such as `state` and PKCE), and sends `302` to the OP over HTTPS.
3. **Browser → OP:** user logs in at the OP; the Spring client never receives the OP password. The OP decides whether to prompt for consent.
4. **OP → Browser → Spring:** OP redirects the browser back to the callback with `code` and `state`. Spring uses the data saved at initiation to verify the matching callback.
5. **Spring → OP:** backend calls the token endpoint over HTTPS, authenticates the client when required, and sends `code_verifier` if using PKCE. The OP returns tokens after verification.
6. **Spring:** validates the ID Token per OIDC (e.g., signature, issuer, audience, expiration, and appropriate nonce), creates `Authentication`, applies login session handling, and redirects the user back to the requested page.
7. **Browser → Spring:** sends the session cookie on the follow-up request. Spring restores login info and allows access to `/account`.
8. **If an API call is needed:** Spring retrieves the appropriate authorized client/access token and calls the API over HTTPS. The API independently validates the access token and its permissions.

Step 4 checks `state`, step 5 uses PKCE, and step 6 validates the ID Token. These are three protective layers addressing different threats.

## 10. Common Errors and How to Pinpoint the Right Layer

| Symptom | Layer to Check | First Thing to Verify |
| --- | --- | --- |
| OP reports `redirect_uri_mismatch` / `invalid_redirect_uri` | HTTP redirect, client registration, proxy | Compare exact scheme, host, port, path, trailing slash, and registered callback URL. |
| Callback reports `invalid_state` or authorization request not found | Session/cookie, callback, load balancer | Check whether session cookie is sent back, SameSite, domain/path, timeout, and session sharing across instances. |
| Backend reports SSL handshake / certificate error | TLS and trust store | Check CA, hostname, certificate validity, OP URL, and proxy configuration. |
| `401` when calling API with Bearer token | Resource server / token | Verify issuer, audience, signature, expiration, and how the `Authorization` header is sent. |
| `403` when submitting a form POST | Authorization or CSRF | Check permission denial logs and CSRF token before changing security config. |
| Login succeeds but next request appears logged out | Cookie/session | Check `Secure`, domain/path, browser cookie transmission, session store, and session timeout. |
| ID Token rejected | OIDC/JWT | Check issuer, client ID/audience, JWKS/key rotation, nonce, and system clock. |
| Login works but API call is rejected | OAuth2 access token | Check that the access token is sent to the right API, scopes/roles, and audience; never substitute ID Token. |
| Login loops behind HTTPS proxy | External URL / forwarded headers | Check whether the app properly detects `https` and the public callback URL. |

**Logging note:** you can log request ID, registration ID, status, processing duration, and sanitized error details. Avoid logging full callback URLs containing codes, `Authorization` headers, tokens, session IDs, client secrets, or sensitive user data.

## 11. Self-Check Understanding

**Scenario A:** Browser successfully logs into the website and receives a `JSESSIONID` cookie. Later, another service calls an API using only that cookie value.

- Will the API automatically accept the cookie? **Cannot assume that.** An API configured as an OAuth2 Resource Server typically requires a Bearer access token with valid issuer/audience/permissions. A session cookie only has meaning for the system owning the session and an explicitly designed session-sharing mechanism.

**Scenario B:** An ID Token has a readable payload stating `"role": "admin"`.

- Can that role be trusted immediately? **No.** You must verify the signature and mandatory claims, and determine whether that claim is permitted by the identity source and application policy for authorization. An ID Token does not automatically grant API-calling privileges.

**Scenario C:** OIDC callback runs over HTTPS yet Spring reports `invalid_state`.

- Is TLS broken? **Not necessarily.** HTTPS can be completely valid while the session holding the authorization request cannot be found due to cookies, load balancers, timeouts, or browser policies.

**Scenario D:** Access token is issued for 10 minutes; website session lives for 30 minutes.

- Must the user be automatically logged out after 10 minutes? **Not necessarily.** The login session and access token have different lifecycles. When needing to call an API after the access token expires, the application needs an appropriate mechanism to obtain a new token or require re-login per policy.

## 12. Remembering the Trust Boundaries

- **HTTP** defines how browser, client, OP, and API exchange requests, redirects, headers, and cookies.
- **TLS** protects data in transit and helps verify the communicating endpoint.
- **Sessions** help the Spring application recognize a logged-in user across multiple requests.
- **JWT** represents claims that can be signed; tokens must be verified according to their **intended purpose**.
- **Spring Security** connects these mechanisms via filter chains, authentication, authorization, and OAuth2/OIDC integration.
- **OAuth2 access tokens** are for accessing resources, **OIDC ID Tokens** are for client authentication info, and **session cookies** are for login state in web applications.

When reading an error or designing a new endpoint, first identify: **who sends the request, who receives the request, which credential is being used, and which component must verify that credential**. This is a useful approach before diving into the steps of building a real Spring Security OIDC Client.

### Standards References for Further Lookup

- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
- [TLS 1.3 — RFC 8446](https://www.rfc-editor.org/rfc/rfc8446)
- [HTTP State Management Mechanism (Cookies) — RFC 6265](https://www.rfc-editor.org/rfc/rfc6265)
- [JSON Web Token — RFC 7519](https://www.rfc-editor.org/rfc/rfc7519)
- [Proof Key for Code Exchange — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security Reference: OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
