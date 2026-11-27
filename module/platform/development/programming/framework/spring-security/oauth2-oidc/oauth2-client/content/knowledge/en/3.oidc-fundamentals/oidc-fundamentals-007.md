# 3.7. OIDC Authorization Code Flow and Session Establishment

In a Spring Boot application using **Spring Security OAuth 2.0/OIDC Client**, clicking the **Log in** button typically starts a sequence of redirects between the browser, the application, and the identity provider. After the identity provider authenticates the user, the application receives the OIDC result, creates an `Authentication`, and establishes a **local login session** for subsequent HTTP requests to use.

With the **OIDC Authorization Code Flow**, the browser only receives an *authorization code* via redirect. The application's backend uses that code to exchange for an ID Token and an Access Token over a direct connection to the OpenID Provider (OP). Only after the ID Token is verified does the application create a login state and manage its own session. This is an important boundary between **logging in at the OP** and **logging into the Spring Boot application**.

This lesson walks step-by-step through the protocol flow, what data Spring Security stores across requests, how `SecurityContext` is formed, the role of session cookies, protective mechanisms, and common pitfalls.

## 1. Participants and Two Types of Login Sessions

Suppose an order management system runs at `https://app.example.org` and uses an OpenID Provider with issuer `https://id.example.org`.

| Component | Role in the Flow |
|---|---|
| **End User** | The person who needs to log in to use order features. |
| **Browser (User Agent)** | Visits the application, follows redirects, and sends cookies to the matching domain. |
| **Spring Boot OIDC Client / Relying Party (RP)** | Initiates the authorization request, handles the callback, exchanges the code for tokens, validates the ID Token, and creates the application session. |
| **OpenID Provider (OP)** | Authenticates the user, optionally prompts for MFA/consent, and issues authorization codes and tokens. |
| **Spring Security Servlet Filter Chain** | Processes login-related requests and protects web resources. |
| **Resource Server / API** (if any) | Validates the Access Token and data access permissions when the client calls APIs. |

During this process, two distinct sessions exist:

- **OP SSO session:** usually maintained by the OP via a cookie on the OP's domain. This session lets the OP recognize that the user is already logged in when another application redirects there.
- **Spring Boot application session:** usually maintained by the application via an HTTP session and a cookie carrying a session ID on the application's domain. This session lets Spring Security recognize the user on subsequent requests.

A user logged in at the OP does not necessarily have a session at the application yet. Conversely, while the local session remains valid, the application can continue recognizing the user without repeatedly querying the OP.

### 1.1. Four Non-Interchangeable Values

| Value | Where Used? | Meaning |
|---|---|---|
| **Authorization Code** | Returned by the OP to the callback; used by backend at the token endpoint. | Short-lived value, typically single-use, to exchange for tokens. |
| **ID Token** | Returned by the OP to the OIDC Client at the token endpoint. | JWT carrying authentication and identity claims that the client must validate. |
| **Access Token** | Used by the Client when calling authorized APIs / Resource Servers. | Token granting resource access; never used as an ID Token. |
| **Session cookie** | Sent by the browser to the application after login. | Associates the browser with the local session holding the application's login state. |

OIDC uses OAuth 2.0's Authorization Code Grant while adding identity requirements through the `openid` scope and ID Token. Therefore, an authorization request with only `response_type=code` and no OIDC request is not automatically an OpenID Connect login.

## 2. Preparation Before the Flow Starts

The application must be registered as a client at the OP. A typical server-side confidential client configuration includes:

| Property | Meaning |
|---|---|
| `client_id` | Application identifier at the OP; not a secret. |
| `client_secret` or another client authentication method | Used by the backend to prove its identity at the token endpoint when applicable. |
| `redirect_uri` | Callback URL to which the OP is permitted to redirect the browser. |
| `scope` | Requires `openid` to request OIDC; may include `profile`, `email`. |
| `issuer-uri` | Trusted OP identifier, used in configuration and token validation. |
| Authorization endpoint | OP endpoint receiving browser-based authentication/code requests. |
| Token endpoint | OP endpoint receiving the code from the backend and issuing tokens. |
| JWKS / signing key metadata | Information needed to verify the ID Token signature. |

OIDC Discovery lets a client discover an issuer's metadata, for instance from `.well-known/openid-configuration` per issuer path rules. Never take an issuer or endpoint from an arbitrary parameter in a user-supplied URL. The actual Redirect URI generated by the application must match the URL registered at the OP, including scheme, host, path, and other constraints per OP policy.

With Spring Security Servlet and a registration named `company`, two key default paths are:

- `/oauth2/authorization/company`: initiates login with this registration.
- `/login/oauth2/code/company`: callback handling the authorization code or error from the OP.

The first path belongs to the client, even though it redirects the user to the login page next. The callback path also belongs to the **application**, not to the OP's token endpoint.

## 3. Full OIDC Authorization Code Flow

The following diagram illustrates a web application using a Spring Boot backend to manage sessions:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Security OIDC Client
    participant I as OpenID Provider

    B->>C: GET /orders (no Authentication yet)
    C->>C: Save original request if needed
    C-->>B: Redirect to login / oauth2 authorization
    B->>C: GET /oauth2/authorization/company
    C->>C: Generate state, nonce, PKCE verifier if used
    C->>C: Save authorization request for correlation
    C-->>B: 302 to OP authorization endpoint
    B->>I: GET /authorize?response_type=code&scope=openid...
    I->>I: Authenticate, MFA/consent per policy
    I-->>B: 302 redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Verify state; retrieve original request
    C->>I: POST token endpoint with code and required bindings
    I->>I: Verify code/client/PKCE
    I-->>C: ID Token, Access Token, and optional tokens
    C->>C: Validate ID Token; create OidcUser/Authentication
    C->>C: Populate and save SecurityContext in session
    C-->>B: Set-Cookie session (if needed), redirect /orders
    B->>C: GET /orders with session cookie
    C->>C: Restore Authentication, check authorization
    C-->>B: Authorized content
```

This flow has three distinct communication legs: **browser ↔ application**, **browser ↔ OP**, and **application backend ↔ OP token endpoint**. Token exchange occurs in the final leg; ID Tokens and Access Tokens are never placed in browser redirect URLs in a properly implemented server-side flow.

## 4. Step 1: User Visits a Resource Requiring Authentication

The user opens `GET /orders` while unauthenticated. Spring Security sees the request lacks a valid `Authentication` and initiates the configured authentication mechanism.

With default `oauth2Login()`, the application may route the user to a login page listing links for registered OAuth2 Clients, or use a dedicated login button pointing directly to `/oauth2/authorization/company`. When using `RequestCache`, Spring Security can save the URL the user intended to visit to return after login.

Common point of confusion: **an HTTP session may be created before authentication succeeds**. The client needs somewhere to store the original request and protocol state so it can verify the callback later. Having a session cookie at this point does not mean the user is authenticated.

### 4.1. Spring Builds the Authorization Request

Upon receiving `GET /oauth2/authorization/company`, Spring Security uses `ClientRegistration` to build the authorization request and redirect to the OP's authorization endpoint.

Illustrative URL representation (sample values abbreviated):

```text
https://id.example.org/authorize
  ?response_type=code
  &client_id=order-web
  &redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany
  &scope=openid%20profile%20email
  &state=s_7c9...
  &nonce=n_4e2...
  &code_challenge=Kq_...
  &code_challenge_method=S256
```

| Parameter | Purpose |
|---|---|
| `response_type=code` | Selects the Authorization Code Flow. |
| `client_id` | Tells the OP which client is making the request. |
| `redirect_uri` | Specifies the permitted callback URL. |
| `scope` | `openid` activates OIDC semantics; other scopes request additional info/permissions. |
| `state` | Binds the authorization response to the client-initiated request to prevent forged callbacks and session mix-ups. |
| `nonce` | Binds the ID Token to the OIDC request when a nonce is sent. |
| `code_challenge` and `code_challenge_method` | Public part of PKCE to protect the code-exchange step. |

`nonce` and `code_challenge` appear when the client uses/configures those mechanisms; do not assume they are always present for every client type. If you need to verify the system uses PKCE, inspect the actual authorization request and how the token request sends the verifier.

### 4.2. Why Must the Original Request Be Saved?

The browser leaves the application, visits the OP, and returns on **a different HTTP request**. The client must remember at least the data required to confirm the callback belongs to the exact request initiated earlier.

In Spring Security Servlet, `OAuth2AuthorizationRequestRedirectFilter` handles initiating/redirecting, while `AuthorizationRequestRepository` stores the authorization request. In standard configurations, `HttpSessionOAuth2AuthorizationRequestRepository` uses the HTTP session to store this request.

The correlated information includes `state` and, where applicable, `nonce` and `code_verifier`. Hence, losing the cookie/session between redirects often causes a `state` error or missing PKCE state error. Never fix that error by disabling `state` verification.

### 4.3. How Does PKCE Bind the Authorization Code?

PKCE (*Proof Key for Code Exchange*) works in three steps:

1. The client generates a sufficiently strong random `code_verifier` and keeps it private for that login attempt.
2. The client derives `code_challenge`, typically via `BASE64URL(SHA256(ASCII(code_verifier)))` under method `S256`, and sends the challenge when requesting the authorization code.
3. When exchanging the code, the backend sends back `code_verifier`. The OP compares the verifier against the challenge bound to that code.

An attacker who intercepts only the authorization code without the verifier cannot easily exchange it for tokens. PKCE is especially essential for public clients, and also beneficial for confidential clients when supported by both OP and application. PKCE does not replace `state` checking or ID Token validation.

## 5. Step 2: The OP Authenticates and Redirects the Browser Back

The browser opens the authorization endpoint on the OP's domain. There, the OP may:

- Authenticate immediately if an existing SSO session meets policy.
- Prompt for password, passkey, MFA, or another authentication method.
- Display a consent screen if required by policy.
- Deny login when the user or client fails requirements.

When approving the request, the OP issues a short-lived authorization code bound to the client and the authorization request's constraints. The browser typically receives a redirect:

```http
HTTP/1.1 302 Found
Location: https://app.example.org/login/oauth2/code/company?code=abc...&state=s_7c9...
```

An authorization code is **not** a logged-in session, nor is it an ID Token. The code has a short lifetime, is normally single-use, and must be exchanged at the token endpoint under the OP's constraints.

If the request is denied, the OP may return parameters such as `error=access_denied` and `state` via the callback. The client must handle the failure path and never construct a successful `Authentication`.

Never place codes, tokens, or full callback URLs containing codes into logs, support tickets, analytics URLs, or public error messages.

## 6. Step 3: Spring Security Processes the Callback

At the default endpoint, `OAuth2LoginAuthenticationFilter` handles `/login/oauth2/code/{registrationId}`. The OAuth/OIDC authentication logic retrieves the original request and checks `state` before accepting the callback result.

If the callback is valid, the backend sends a POST to the OP's token endpoint. An illustrative request:

```http
POST /token HTTP/1.1
Host: id.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication-value>

grant_type=authorization_code&
code=abc...&
redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=<original-verifier-if-PKCE-was-used>
```

Client authentication at the token endpoint may use HTTP Basic, POST body, private key JWT, mTLS, or another method per registration; the example shows only one option. Public clients do not rely on a secret embedded in the app to protect the token exchange. When PKCE is used, `code_verifier` must be the value generated for the initial authorization request.

The OP checks that the code is valid, unused, unexpired, issued to the right client, with a matching redirect URI, and a matching verifier if PKCE was used. Then the OP returns tokens:

```json
{
  "access_token": "eyJ...or-opaque-value",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email",
  "id_token": "eyJ..."
}
```

A `refresh_token` may also be issued depending on OP conditions; do not assume every flow receives a refresh token. The Access Token may be a JWT or an opaque token. The token endpoint may return an error such as `invalid_grant` if the code was already used or failed constraints; in that case, the client has no basis to establish a successful login session.

### Callback vs. Token Endpoint

| Endpoint | System | Caller | Primary Data |
|---|---|---|---|
| `/login/oauth2/code/company` | Application | Browser after redirect | `code`, `state`, or error. |
| `/token` (per OP metadata) | OpenID Provider | Application backend | Authorization code, redirect URI, client authentication, PKCE verifier if any. |
| `/orders` | Application | Browser after login | Local session cookie. |

In a server-side OIDC Authorization Code Flow, the ID Token is received by the backend at the token endpoint, not carried back by the browser in the callback URL.

## 7. Step 4: Validating the ID Token Before Creating Authentication

The ID Token is a JWT issued by the OP for the OIDC Client. Example payload:

```json
{
  "iss": "https://id.example.org",
  "sub": "user-94831",
  "aud": "order-web",
  "exp": 1760000300,
  "iat": 1760000000,
  "nonce": "n_4e2..."
}
```

These timestamps merely illustrate claim structure, not a currently unexpired token at the time of reading.

The application **must never merely decode the JWT and trust its contents**. Required checks under OIDC include:

| Condition | What the Client Must Verify |
|---|---|
| Signature / key / algorithm | ID Token is valid under the signing mechanism and key published by the trusted OP, using an allowed algorithm. |
| `iss` | Matches the trusted issuer of the client registration. |
| `aud` | Contains the receiving `client_id`; handle `azp` when OIDC rules require it. |
| `exp` and time | Token is unexpired and satisfies time constraints; check `iat` and related claims as needed. |
| `nonce` | Matches the initial nonce if the client included a nonce in the authorization request. |
| `auth_time`, `acr`, `amr` if applicable | Satisfies timing or authentication assurance policies, such as when re-authentication was requested. |

In an `oauth2Login()` flow with scope `openid`, Spring Security's OIDC components validate the token, construct the `OidcUser` principal, and return an `Authentication` upon successful verification. The application must configure the right issuer, registration, and policies, and never bypass validation steps when customizing.

The OP may also provide a **UserInfo endpoint**. If the client queries UserInfo, the result must be bound to the exact same `sub` as the ID Token per OIDC; never merge attributes from two different users.

### 7.1. Identity Is Not Automatically Authorization

`iss` and `sub` are usually a solid foundation for linking identity to an internal profile. The **`(issuer, subject)`** pair is far more reliable than email as a long-term key because emails can change or be recycled.

Even when the ID Token is valid, the application must still check permissions to read, create, edit, or approve data. `Authentication` holds the principal and authorities for access control, yet business authorization may require mapping groups from the OP, checking internal roles, or enforcing resource-level rules.

**The ID Token is for the OIDC Client; the Access Token is for the Resource Server.** Never forward an ID Token to an API as a bearer token, and never assume an Access Token contains claims sufficient to authenticate an OIDC login for the client.

## 8. Step 5: Creating SecurityContext and the Spring Security Session

After the OIDC authentication provider succeeds, Spring Security holds an `Authentication` describing the logged-in user. The security layer sets `SecurityContext` for the current request and persists the context via the configured `SecurityContextRepository` so subsequent requests can restore it.

This is the **application session establishment step**. It takes place after the backend exchanges the code and validates the OIDC result; receiving the callback alone does not make a session an authenticated session.

### 8.1. Related Spring Security Components

| Component | Role |
|---|---|
| `OAuth2AuthorizationRequestRedirectFilter` | Builds/redirects the authorization request to the OP. |
| `AuthorizationRequestRepository` | Stores the authorization request for correlation at the callback; commonly `HttpSessionOAuth2AuthorizationRequestRepository`. |
| `OAuth2LoginAuthenticationFilter` | Receives the authorization code callback and triggers the login authentication flow. |
| OAuth/OIDC authentication providers | Exchange the code for tokens, validate the result, and create the appropriate principal/authentication. |
| `SecurityContextHolder` | Holds `SecurityContext` for the scope of the current request. |
| `SecurityContextRepository` | Saves/restores `SecurityContext` across requests; may use the HTTP session. |
| `RequestCache` and authentication success handler | Remembers the originally requested URL and redirects the user after login. |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Manages OAuth 2.0 authorized clients and tokens used for downstream API calls; a separate storage responsibility from `SecurityContext`. |

A typical sequence after ID Token validation succeeds:

1. Spring Security builds `OidcUser` (ID Token and optionally UserInfo) along with authorities.
2. The authentication provider returns the authenticated `Authentication`.
3. Spring Security persists `SecurityContext` using the configured repository so future HTTP requests restore user state.
4. Session handling applies session fixation protection and configured session limits.
5. The success handler redirects to the URL saved in the request cache or the default landing page.
6. The browser sends the application session cookie on subsequent requests; requests are authorized based on the restored authentication.

An HTTP session may already have been created **before** login finished in order to store the authorization request or target URL. Upon successful login, **session fixation** protection may rotate the session ID. Therefore, distinguish merely having an HTTP session from that session holding an authenticated `SecurityContext`.

### 8.2. Session Cookie and Subsequent Requests

The response after login might look like:

```http
HTTP/1.1 302 Found
Location: /orders
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

These are illustrative headers; actual cookie attributes depend on the servlet container, proxy, and session configuration. `JSESSIONID` is only a session identifier, not an OIDC ID Token or Access Token. Applications may choose a different cookie name.

Subsequent request:

```http
GET /orders HTTP/1.1
Host: app.example.org
Cookie: JSESSIONID=<opaque-session-id>
```

Spring Security retrieves the corresponding `SecurityContext` from storage, resolves the principal/authorities, and evaluates access rules before the request reaches the controller. If the session has expired or lacks authentication state, the user must go through the appropriate login flow again.

The **application** session cookie is sent to `app.example.org`; the **OP** SSO cookie is sent to the OP's domain per its own cookie attributes. Never treat the OP cookie as the application's session ID.

### 8.3. Token Lifecycle Differs from Session Lifecycle

Suppose the OP issues an ID Token expiring after 5 minutes, while the application HTTP session expires after 30 minutes.

The ID Token must be valid when the client uses it to verify login. Once the application session is established, normal requests can use the valid `SecurityContext` per session policy without re-validating the ID Token or bouncing through the OP every 5 minutes.

Meanwhile, if the backend needs to call an API with an Access Token, that token must still be valid according to the API and may require refreshing. The Refresh Token, if present, is managed per OP policy and `OAuth2AuthorizedClient` storage. Do not assume every Access Token lives inside `SecurityContext` or that tokens are stored directly in browser cookies.

Application session, SSO session, ID Token, Access Token, and Refresh Token lifetimes are **independent lifetimes**. For sensitive operations, the application may require re-authentication or check authentication recency under its own policy.

## 9. Spring Boot Implementation with `oauth2Login()`

### 9.1. Dependencies

Gradle example in a Spring Boot project:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
```

You do not need Resource Server if the requirement is only web login; an API accepting bearer tokens is a separate role and requires `oauth2ResourceServer()` when needed.

### 9.2. Client Registration and Session Timeout

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
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://id.example.org

server:
  servlet:
    session:
      timeout: 30m
```

This configuration is for a server-side confidential client supported by the OP. `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are loaded from environment variables / secret manager at runtime; never hardcode secrets in source code or frontend builds.

- `registration.company` corresponds to `/oauth2/authorization/company`.
- `redirect-uri` points to the callback handled by Spring Security; the actual URL must match the URI allowed by the OP.
- `scope: openid` makes the request OIDC; `profile` and `email` are optional depending on the IdP.
- `issuer-uri` lets Spring Security obtain issuer metadata and corresponding validation details.

If the application sits behind a load balancer or reverse proxy, ensure public URLs are generated with the right scheme, host, and path; trust forwarded headers only from controlled proxies. Wrong public URLs commonly cause `redirect_uri_mismatch` or redirect loops.

### 9.3. HTTP Security Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

With this setup, `/orders` requires a logged-in user while `/public/**` permits public access. The `/oauth2/authorization/company` entry point and callback are handled by Spring Security's OAuth2 Login components.

Do not configure the entire web application with `SessionCreationPolicy.STATELESS` and expect default `oauth2Login()` to continue storing authorization requests and login sessions. A stateless design requires explicitly building suitable protection and state-persistence mechanisms.

### 9.4. Reading the Authenticated Principal

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
```

After OIDC login, `@AuthenticationPrincipal` retrieves the principal of the request managed by Spring Security. In real systems, `(issuer, subject)` can be used to look up the application profile and evaluate business permissions.

Do not write a custom controller at `/login/oauth2/code/company` to read the authorization code and manually decode JWTs while the default filters handle the flow. If you need to customize the login page, success handler, authorization request resolver, or authorized client storage, use Spring Security's extension points and preserve all required validation steps.

## 10. Different Protective Mechanisms in a Single Flow

| Mechanism | What It Protects | What It Cannot Replace |
|---|---|---|
| `state` | Links the authorization response to the client-initiated login request. | ID Token validation, PKCE, or CSRF protection on business forms. |
| `nonce` | Binds the ID Token to the OIDC authorization request when a nonce is sent. | `state`, PKCE, or authorization. |
| PKCE | Protects the authorization code exchange using a per-request secret verifier. | Issuer/audience checks and session cookie protection. |
| Client authentication | Authenticates a confidential client at the token endpoint. | PKCE for public clients or ID Token validation. |
| ID Token validation | Verifies provenance and validity of OIDC authentication assertions. | Resource-level business authorization checks. |
| Session fixation protection | Mitigates session hijacking when a session ID was pre-assigned. | CSRF/XSS protection. |
| CSRF protection | Protects state-changing requests using session cookies. | OIDC callback `state`. |
| HTTPS and cookie settings | Protects transport and limits exposure of session cookies. | Token validation or access control. |

Cookies typically need `Secure`, `HttpOnly`, and `SameSite` compatible with how the callback operates. For instance, an OIDC GET redirect usually works with `SameSite=Lax`, whereas other response modes or complex domain topologies require separate evaluation. Never disable CSRF globally just to make an OIDC callback work.

Never log raw authorization codes, Access Tokens, ID Tokens, Refresh Tokens, client secrets, `code_verifier`, or session cookies. When troubleshooting, log error codes, safe correlation IDs, flow start/end points, and appropriate validation outcomes.

## 11. Failure Scenarios and Where to Check

### 11.1. Callback Has Missing or Mismatched `state`

Common causes include the authorization request no longer being in the session, blocked cookies, expired session, wrong cookie domain/path, host mismatch behind a proxy, or the user starting multiple parallel login flows. First check whether the **OIDC Client side** can restore the authorization request matching the callback.

Never disable `state` validation to make the error disappear.

### 11.2. Password Entered at OP, Yet Token Endpoint Returns `invalid_grant`

The code may be expired, already consumed, mismatched on redirect URI, or missing a matching PKCE verifier. This is a failure at the **backend code-exchange stage**, even though the user authenticated successfully at the OP. Check token endpoint policies and metadata without printing the code/verifier into logs.

### 11.3. Tokens Received, Yet OIDC Login Fails

The ID Token may fail `iss`, `aud`, signature, `exp`, `nonce`, or another validation check. Even if the token contains readable `name` or `email` fields, the client must refuse to create an `Authentication` if validation fails.

### 11.4. Login Completes, Then Redirects Back to Login Repeatedly

Often tied to session cookies, lost `SecurityContext`, repository configuration, or multi-instance infrastructure not sharing sessions properly. Distinguish the **session holding the authorization request** from the **post-authentication session**; trace both stages.

If the application runs across multiple nodes, session and authorization request storage must be consistent across nodes via shared sessions or proper routing. Storage for `OAuth2AuthorizedClient` must also be designed accordingly if the application uses Access Tokens to call APIs.

### 11.5. Browser Logged In, Yet Endpoint Returns 403

Having an `Authentication` does not mean the user is allowed to do everything. Check authority mapping, application roles, and data-level permissions. This is the difference between authentication and authorization.

### 11.6. UI Logged In, Yet External API Returns 401

The web session uses a session cookie, whereas APIs accept an Access Token. The client must send a valid Access Token intended for that exact API; the Resource Server validates signature/introspection, audience, scopes, and its access policy. Sending an ID Token instead of an Access Token is not a valid fix.

### 11.7. Logged Out, Yet Logging Back In Requires No Password

The application may have cleared its local session while the SSO session at the OP remains active. When the browser navigates to the OP, the OP authenticates using the existing SSO session. If synchronized logout is desired, design OIDC logout around OP capabilities and application-specific rules.

### 11.8. Multi-Tab Login, Browser Rejecting Cookies, or Callback from Another Environment

Each authorization response must correlate to a still-valid authorization request. Design state storage to support concurrent logins and test cookies in realistic environments. Never assume the same `state` or `nonce` can be reused across multiple logins.

## 12. How to Observe and Understand a Login Attempt

Using browser Network tools alongside server logs in development, you can trace in order:

1. The user visits a protected resource; the application routes to the login/authorization entry point.
2. The client sends the browser to the OP with `response_type=code`, scope `openid`, and appropriate protective parameters.
3. The user authenticates or is recognized by the OP via an SSO session.
4. The OP redirects back to the callback with code and state, or returns an error.
5. The backend exchanges the code at the token endpoint and receives the ID Token / Access Token.
6. The client validates the ID Token and creates `OidcUser` and `Authentication`.
7. Spring Security saves `SecurityContext` in the configured session mechanism, then redirects to the originally requested URL.
8. The browser sends the session cookie on the next request; the application restores identity and evaluates authorization.

Never capture or share callback URLs containing codes, `Authorization` headers, or real session cookies. For Spring Security logs, enable only the level needed for diagnosis and restrict sensitive logging in production.

### Authoritative References for Further Reading

- [OpenID Connect Core 1.0 — Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth)
- [OAuth 2.0 RFC 6749 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1)
- [OAuth 2.0 PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)

The Authorization Code merely bridges the OP user-authentication stage with the backend token-retrieval step. **The application's login session** is formed when the OIDC Client validates the result, creates `Authentication`, saves `SecurityContext`, and maintains the session cookie for future requests. Keeping these steps distinct helps build a secure OIDC flow and properly troubleshoot issues involving state, tokens, sessions, and SSO.
