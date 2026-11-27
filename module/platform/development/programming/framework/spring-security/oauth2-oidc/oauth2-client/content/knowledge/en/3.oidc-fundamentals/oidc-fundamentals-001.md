# 3.1. OpenID Connect Adds an Authentication Layer to OAuth 2.0

**OpenID Connect (OIDC)** is an identity protocol built on top of OAuth 2.0. OAuth 2.0 solves **delegated authorization to access resources**; OIDC adds a standardized way for an application to **authenticate who the logged-in user is** through an identity provider.

In the Spring Security ecosystem, this distinction is very clear: `oauth2Login()` can use OIDC to log a user in with an `OidcUser`; `oauth2Client()` manages access tokens for the application to call APIs; `oauth2ResourceServer()` verifies the access token that an API receives. These roles are related but not interchangeable.

## 1. The Problem: OAuth 2.0 Does Not Define a Login Protocol on Its Own

Suppose a document management application wants users to log in with an account from an Identity Provider (IdP).

OAuth 2.0 can help the application obtain an access token to call an API of the IdP. However, merely knowing "the application received an access token" does not give the application a standard, consistent way to conclude:

- Who is the authenticated end-user?
- Who made the assertion about that identity?
- **Which application** was that assertion issued for?
- When did the user log in, and is re-authentication required?
- How must the application verify the login proof?

An **access token** is a credential for accessing resources, issued for use at a **Resource Server**. OAuth 2.0 does not require an access token to be in JWT format, does not prescribe a standard set of claims about the end-user's identity, and does not guarantee that the client can decode the token's contents.

If an application obtains an access token and infers "login succeeded" using provider-specific rules, it is implementing a custom, ad-hoc login protocol. OIDC standardizes the missing part by defining the **ID Token**, identity scopes/claims, how to retrieve user information, and token validation rules.

> **Core distinction:** OAuth 2.0 answers "What is the application allowed to do with the resource?". OIDC also answers "Which subject did the identity provider authenticate for this application?".

OIDC still uses the components and authorization flows of OAuth 2.0, while adding identity constraints. An OAuth 2.0 Authorization Server is **not necessarily** an OpenID Provider; it must support the corresponding OIDC capabilities.

## 2. Roles in the OIDC Model

| Component | Role in OIDC | Relation to OAuth 2.0 |
|---|---|---|
| **End-User** | The user being authenticated | Usually the Resource Owner in a login scenario, though the two concepts are not always identical |
| **Relying Party (RP)** | The application relying on the authentication result issued by the OP | A type of OAuth 2.0 Client |
| **OpenID Provider (OP)** | Authenticates the user, issues the ID Token, and may provide UserInfo | An Authorization Server with OIDC support |
| **Resource Server** | Provides data/APIs protected by an access token | Does not need to be an OP or RP |

In a Spring Boot web application:

```text
Browser / End-User
         |
         | opens a page requiring login
         v
Spring Boot Web App (Relying Party / OAuth2 Client)
         |
         | redirects to OpenID Provider
         v
OpenID Provider (Authorization Server + identity service)
         |
         | authenticates user, returns authorization code
         v
Spring Boot exchanges code for tokens, validates ID Token
         |
         | establishes application session
         v
Browser receives session cookie
```

Spring Boot can then continue using the issued **access token** to call a separate Resource Server. The same OP may issue both an ID token and an access token, but **the two tokens have different intended recipients and purposes**.

## 3. What Does OIDC Add on Top of OAuth 2.0?

### 3.1. The `openid` Scope Marks an OIDC Request

In the authorization request, the application requests the `openid` scope to use OIDC:

```text
scope=openid profile email
```

The scopes have different meanings:

| Scope | Meaning |
|---|---|
| `openid` | Triggers an OIDC authentication request and receives an ID Token according to the supported flow |
| `profile` | Requests access to standard profile claims, if permitted by the OP |
| `email` | Requests the `email` and `email_verified` claims, if provided |
| `address` | Requests address information per the OIDC specification |
| `phone` | Requests phone number information per the OIDC specification |
| Custom API scope, e.g. `orders.read` | Requests permission to access a Resource Server; name/meaning is defined by the API system |

`openid` is **not** a business permission to read or modify data. Nor do `profile` and `email` guarantee that all claims will be present: the result depends on OP configuration, user consent, and data protection policies.

Merely including `openid` does not automatically turn an access token into an ID token; the application must handle each token type appropriately.

### 3.2. ID Token: Authentication Proof for the Relying Party

An **ID Token** is a security token in JWT format containing claims about the authentication event and the subject. The OP typically signs the JWT with its private key so the RP can verify its integrity and issuer.

Important claims:

| Claim | Meaning | Notes |
|---|---|---|
| `iss` | Issuer: identifier of the OP that issued the ID token | Must match the issuer trusted by the RP |
| `sub` | Subject: user identifier at the OP | Combined with `iss` to form a stable identity key |
| `aud` | Audience: client ID of the RP receiving the ID token | The RP must be included in the audience |
| `exp` | Expiration time of the ID token | The RP rejects expired tokens |
| `iat` | Time at which the token was issued | Used for protocol time-based checks |
| `nonce` | Value bound to the authentication request | If the RP sent a nonce, it must verify it in the ID token |
| `auth_time` | Time when the user was actually authenticated | Important when the RP requires `max_age` or recent authentication |
| `acr` | Authentication Context Class Reference | Exact meaning depends on agreement with the OP |
| `amr` | Authentication Methods References used | E.g. password, MFA; not guaranteed to be present by default |
| `azp` | Authorized party | Must be verified per OIDC rules, especially with multiple audiences |

An **illustrative JWT payload** (not a real usable token):

```json
{
  "iss": "https://login.example.org",
  "sub": "user-8c6e4d",
  "aud": "document-web-client",
  "exp": 1924999999,
  "iat": 1924996399,
  "auth_time": 1924996200,
  "nonce": "n-0S6_WzA2Mj"
}
```

The three common parts of a JWS-signed JWT are `header.payload.signature`. The JSON data in the payload is normally only **Base64URL-encoded, not encrypted**. Do not put passwords, secrets, or unnecessary sensitive data into a token simply because it is signed. If the OP/RP requires an encrypted ID token (JWE), that is a separate capability that both sides must support and configure.

From the example, we can infer: OP `https://login.example.org` asserts that it authenticated subject `user-8c6e4d`, and that result is intended for the RP with client ID `document-web-client`. The application **must only trust this assertion after performing full ID token validation**, not after Base64URL decoding.

### 3.3. UserInfo Endpoint: Retrieving User Claims

OIDC defines the **UserInfo Endpoint** for the RP to retrieve permitted claims about the End-User. The RP sends the **access token** in `Authorization: Bearer ...` to the UserInfo Endpoint, typically over HTTPS:

```http
GET /userinfo HTTP/1.1
Host: login.example.org
Authorization: Bearer <access-token>
```

Illustrative response:

```json
{
  "sub": "user-8c6e4d",
  "name": "Nguyen An",
  "email": "an@example.org",
  "email_verified": true,
  "picture": "https://images.example.org/avatars/8c6e4d.png"
}
```

**Important:** `sub` in the UserInfo response **must match** `sub` in the ID token that the RP verified. The RP must never mix up information from another user if the two subjects do not match.

Not every RP is required to call UserInfo. The ID token may already contain enough claims for the application to create a session, or the OP may provide additional claims via UserInfo depending on scopes/policies. Claims such as `email`, `picture`, or `name` may be missing or change over time; they are not immutable account identifiers.

### 3.4. Discovery and Public Signing Keys

OIDC Discovery allows a client to look up metadata from the issuer, for example:

```text
GET https://login.example.org/.well-known/openid-configuration
```

Illustrative metadata:

```json
{
  "issuer": "https://login.example.org",
  "authorization_endpoint": "https://login.example.org/oauth2/authorize",
  "token_endpoint": "https://login.example.org/oauth2/token",
  "userinfo_endpoint": "https://login.example.org/userinfo",
  "jwks_uri": "https://login.example.org/.well-known/jwks.json",
  "response_types_supported": ["code"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

The RP uses `jwks_uri` to fetch the JSON Web Key Set (JWKS), select the appropriate public key, and verify the ID token signature. When the OP rotates keys, the OIDC library can reload the JWKS according to its configuration. **The application must configure the trusted issuer beforehand**, then verify `issuer` in the metadata and ID token; never take an arbitrary issuer URL from an unverified token and automatically trust it.

OIDC Discovery reduces manual configuration of individual endpoint URLs and improves key management. If a provider does not support discovery metadata, the endpoints and keys must be configured in a compatible manner that the application can verify.

## 4. OIDC Authorization Code + PKCE Login Flow

In modern applications, the standard approach is the **OIDC Authorization Code Flow**, combined with **PKCE** to mitigate the risk of an authorization code being stolen and exchanged for tokens.

### 4.1. Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser / User
    participant RP as Spring Boot RP
    participant OP as OpenID Provider
    participant API as Resource Server

    U->>RP: GET /account
    RP-->>U: Redirect to authorization endpoint
    U->>OP: /authorize?scope=openid...&state=...&nonce=...&code_challenge=...
    OP->>U: Authenticate user, ask consent if needed
    OP-->>U: Redirect callback?code=...&state=...
    U->>RP: GET /login/oauth2/code/company?code=...&state=...
    RP->>RP: Verify state from initial request
    RP->>OP: POST /token (code + code_verifier + client auth if any)
    OP-->>RP: ID token + access token (+ refresh token if issued)
    RP->>RP: Validate ID token: issuer, signature, audience, time, nonce...
    opt Additional claims needed
        RP->>OP: GET /userinfo (Bearer access token)
        OP-->>RP: Claims, including sub matching ID token
    end
    RP-->>U: Create login session; send session cookie
    U->>RP: GET /account (session cookie)
    opt Call API on behalf of user
        RP->>API: Bearer access token
        API-->>RP: Data authorized by API
    end
    RP-->>U: Account page
```

### 4.2. Key Steps

1. **RP initiates the request:** generates a random `state`; may generate a `nonce`; when using PKCE, generates a `code_verifier` and derives `code_challenge` using `S256`. Required values are bound to the pending session/request.
2. **Redirect to the OP:** sends `client_id`, `redirect_uri`, `response_type=code`, `scope=openid ...`, `state`, `nonce` (if used), and `code_challenge`.
3. **OP authenticates:** the OP decides how to authenticate the user (password, MFA, passkey, federated IdP, etc.), handles consent, and redirects to the registered URI.
4. **RP receives the code:** validates `state`; rejects the code if the callback does not correspond to a valid pending request.
5. **Exchange code for tokens:** sends `code_verifier` along with the code to the token endpoint; a confidential client also authenticates with its registered credentials. The Authorization Server verifies PKCE, the client, and the redirect URI.
6. **Verify the OIDC result:** the RP validates the ID token, checks the nonce if present, optionally fetches UserInfo, and verifies `sub`.
7. **Create application session:** the RP maps `(iss, sub)` to an internal account and determines access policies within the application.

An illustrative authorization request (`state`, `nonce`, and challenge values are placeholders only):

```http
GET /oauth2/authorize?response_type=code
    &client_id=document-web-client
    &redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany
    &scope=openid%20profile%20email
    &state=<cryptographically-random-state>
    &nonce=<cryptographically-random-nonce>
    &code_challenge=<base64url-sha256-verifier>
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.org
```

The token endpoint may return a response structured as follows (tokens are illustrative placeholders with no real value):

```json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "id_token": "<signed-oidc-id-token>",
  "scope": "openid profile email"
}
```

A **refresh token** may be issued depending on OP policy, application type, scopes, and consent; OIDC does not guarantee that every login receives a refresh token. The API access lifetime, ID token lifetime, and web session lifetime are also **not required to be equal**.

### 4.3. State, Nonce, and PKCE Address Different Risks

| Component | What Is Bound or Checked | Practical Role |
|---|---|---|
| `state` | Redirect result belongs to the exact request initiated by the RP | Protects against login CSRF / mismatched callbacks and correlates the response |
| `nonce` | ID token is bound to the initial authentication request | Helps detect replay or mismatched ID tokens; verified when sent |
| `code_verifier` / PKCE | The party exchanging the authorization code possesses the verifier from the initial request | Reduces the risk of an intercepted code being exchanged by an attacker |
| Client authentication | Client proves its registered credentials, if it is a confidential client | Protects the token endpoint against client impersonation |
| ID token validation | OP, signature, recipient, expiration, and authentication conditions | Verifies the login assertion before creating a session |

**Not interchangeable:** having PKCE does not mean you can skip ID token validation; having a client secret does not make `state` useless; having `nonce` does not replace audience or signature verification.

## 5. The Three Common Token Types and Their Meaning

| Token | Intended Recipient / Primary Function | Valid Usage | What to Avoid |
|---|---|---|---|
| **ID Token** | RP; proves the End-User authentication event | RP validates it and extracts subject and authentication info | Sending as a bearer token to an API |
| **Access Token** | Resource Server / API or UserInfo | Attached in `Authorization: Bearer ...` to access authorized resources | Using as proof of login to an RP without an appropriate authentication protocol |
| **Refresh Token** | OAuth client; requests a new access token when permitted | Kept in protected storage, used at the token endpoint | Putting in URLs, logs, or storing without proper controls |

An ID token is a JWT, but **not every JWT is an ID token**. An access token may be a JWT or an opaque token; if the access token is a JWT, its `aud` claim usually indicates the target API, whereas the `aud` of an ID token must include the **RP's OAuth client ID**.

For example, if a token has `aud=orders-api` and is sent to `https://api.example.org`, the Spring API should treat it as an access token intended for the API. Do not accept that token as login proof equivalent to an ID token with `aud=document-web-client`.

Similarly, **successful authentication** does not mean **permission to access all resources**. After trusting an ID token, the RP must still determine whether the user has a valid account, belongs to the right organization, holds the required roles/permissions, and is allowed to access a specific resource.

## 6. Validating an ID Token Properly

An RP cannot simply decode a JWT and trust `email` or `sub`. Validation involves multiple layers, typically handled by a well-maintained OIDC library:

1. **Trusted issuer:** `iss` in the token must equal the configured OP issuer; discovery metadata must be consistent with the issuer.
2. **Signature and algorithm:** verify the signature using the matching key from the OP's JWKS, with an algorithm permitted by client registration/policy; never accept an untrusted algorithm or key solely because the token declares it.
3. **Audience:** `aud` must contain the RP's `client_id`. If `aud` has multiple entries, check `azp` per OIDC requirements; if `azp` is present, verify that it corresponds to the client receiving the token.
4. **Time:** reject expired tokens via `exp`, and evaluate `iat`, allowed clock skew, and `auth_time` when recent authentication is required.
5. **Nonce:** if the authentication request sent `nonce`, match the value in the ID token against the nonce bound to that request.
6. **Flow-specific conditions:** verify hash claims such as `at_hash`/`c_hash` when required by the protocol/flow and parameters; do not mechanically apply hybrid flow rules to a pure authorization code flow.
7. **UserInfo subject:** if UserInfo is called, `sub` in the response must exactly equal `sub` in the validated ID token.
8. **Application context:** map `(iss, sub)` to an account; check active status, tenant, roles, and access policies.

Spring Security libraries typically handle the core OIDC checks of the login flow when issuer/registration are properly configured. However, **business rules**—such as allowing only corporate emails, requiring MFA for sensitive actions, or permitting only approved accounts—remain the application's responsibility.

### 6.1. Why Is `sub` More Important Than `email`?

OIDC defines `sub` as the subject identifier of a user at an issuer. Email addresses and display names can change, collide, or be unverified.

A linked account key should be based on the pair:

```text
(identity_issuer, identity_subject)
=
("https://login.example.org", "user-8c6e4d")
```

`sub` only needs to be stable **within the scope of the issuer and relevant identity policy**; with **pairwise subject identifiers**, the same user may have different subjects across different RPs/sectors. Never assume two ID tokens from different issuers with the same `sub` represent the same person.

`email_verified=true` can be helpful within a carefully designed account-linking policy, but it does not automatically grant ownership of every account using that email in the application.

### 6.2. Fresh Authentication or Reusing an SSO Session?

The OP may already have an active login session and not prompt the user to re-enter a password. When the RP requires recent authentication, it can use OIDC parameters such as:

- `max_age`: limits the elapsed time since the last authentication; if requested, the RP must check `auth_time` in the ID token.
- `prompt=login`: asks the OP to re-authenticate according to the OP's semantics.
- `prompt=none`: asks the OP not to display any UI; the OP may return `login_required` or `interaction_required` if it cannot satisfy the request silently.
- `acr_values` and the `acr` claim: can help request a specific authentication level/context when the OP and RP agree on their meanings.

A valid ID token **does not by itself guarantee that MFA occurred**. Only conclude that when the OP publishes trustworthy information (such as `acr`/`amr` under an integration contract) and the RP has explicit validation logic for it.

## 7. Integrating OIDC Login in Spring Security

### 7.1. Spring Boot Web Application Acting as a Relying Party

Consider a Spring MVC application rendering server-side UI and using an OP that supports discovery.

Declare dependencies with Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Configure `application.yml`:

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

At the OP, register a confidential client with the exact `client_id`, authentication method, and redirect URI, for example:

```text
https://app.example.org/login/oauth2/code/company
```

The `OIDC_ISSUER_URI` value is the trusted issuer published by the OP, e.g., `https://login.example.org`; when discovery is compatible, Spring Security fetches metadata and verification keys from this issuer. Keep `client-secret` on the backend (in a secret manager or runtime environment), never in the frontend or committed to source control.

**Why does the `openid` scope matter?** When a registration requests `openid`, Spring Security recognizes this as an OIDC login and handles the principal as OIDC (typically `OidcUser`). If the client only requests plain OAuth scopes without `openid`, you cannot assume the RP receives an OIDC ID token.

Page protection configuration:

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
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

By default, a page requiring authentication triggers the appropriate login flow; you can also explicitly visit:

```text
GET /oauth2/authorization/company
```

After a successful callback, Spring Security validates the ID token and stores the OIDC principal in the `SecurityContext`, typically backed by an HTTP session for web apps. The browser receives a **session cookie**; the ID token does not need to be exposed to JavaScript.

**About PKCE:** Authorization Code + PKCE is a good security practice even when client authentication is present. For a confidential client, enabling PKCE explicitly may require an `OAuth2AuthorizationRequestResolver` configured with the `OAuth2AuthorizationRequestCustomizers.withPkce()` customizer depending on the Spring Security version; do not assume every configuration and version enables PKCE identically. The OP must support `S256` accordingly.

### 7.2. Retrieving Logged-in User Info via `OidcUser`

Example endpoint returning only the subject and a few claims for display, **without returning tokens to the browser**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    public record CurrentUser(
        String issuer,
        String subject,
        String displayName,
        String email
    ) {}

    @GetMapping("/me")
    public CurrentUser me(@AuthenticationPrincipal OidcUser user) {
        return new CurrentUser(
            user.getIdToken().getIssuer().toString(),
            user.getSubject(),
            user.getFullName(),
            user.getEmail()
        );
    }
}
```

`OidcUser` provides accessors such as `getIdToken()`, `getUserInfo()`, and claim helpers; UserInfo data is only present when provided by the OP and retrieved by Spring Security. Values like `name` and `email` may be `null`, so the UI must tolerate missing claims. `getSubject()` is an identifier from the OP, **not an auto-generated ID from your internal users table**.

For the application to have its own roles/permissions, map the OIDC principal to an internal account and grant authorization based on application policy. Do not blindly treat `openid`, `profile`, or `email` scopes as administrative privileges.

### 7.3. OIDC Login and Calling Downstream APIs Are Two Separate Steps

After login, the Spring application may hold an access token in the authorized client record; use `OAuth2AuthorizedClient` or `OAuth2AuthorizedClientManager` to manage tokens when calling APIs.

```text
Spring Boot RP:
  1. ID token -> authenticates the user for the login session
  2. Access token -> sent in Authorization: Bearer ... when calling APIs
  3. Session cookie -> maintains the browser session with the RP

Spring Boot API:
  1. Receives Bearer access token
  2. Validates token using Resource Server
  3. Checks audience and scope/permissions before returning data
```

A REST API validating JWT access tokens uses `spring-boot-starter-oauth2-resource-server` and `oauth2ResourceServer().jwt()` with the proper issuer/audience. An API does **not** use `oauth2Login()` solely to validate bearer tokens, and does **not** accept an ID token in place of an access token.

If a SPA calls the API directly, the SPA is typically a **public client** performing OIDC Authorization Code + PKCE; the Spring API acts only as a Resource Server. If the SPA communicates through a BFF backend, the backend can be a confidential RP and keep tokens server-side.

### 7.4. When Should You Customize the OIDC User Service?

Spring Security provides classes like `OidcUserService` and authentication success hooks. Customization may be needed to:

- Link `(iss, sub)` to a user in the application database.
- Require the user to have been invited or activated.
- Load business roles/permissions from internal sources.
- Enforce specific conditions such as organization, tenant, authentication level, and access rights.

Keep two responsibilities strictly separate:

- **Protocol validation:** validating the ID token, issuer, signature, audience, nonce, etc., handled by the OIDC components.
- **Business authorization:** determining which groups, tenants, admin pages, or specific data the principal can access.

Never take an arbitrary unverified claim and treat it as `ROLE_ADMIN`. Likewise, do not link accounts by email by default without a proper identification and proof-of-ownership policy.

## 8. OIDC Sessions, Logout, and Token Lifetimes

There can be **multiple distinct sessions**:

1. **Application session at the RP**: the session cookie created by Spring Boot to maintain login state.
2. **SSO session at the OP**: the user may already be logged in at the IdP and reuse that session across other RPs.
3. **Token lifecycles**: ID token, access token, and refresh token each have their own lifetimes/policies.

When a user clicks **Logout** at the RP, clearing the Spring session **does not necessarily** clear the SSO session at the OP. If the OP supports **RP-Initiated Logout**, the application can coordinate redirecting to the OP's logout endpoint, using a compatible mechanism such as `OidcClientInitiatedLogoutSuccessHandler` in Spring Security and configuring the exact `post_logout_redirect_uri`.

Do not assume "global logout" happens automatically just because one side clears a cookie. Front-channel/back-channel logout mechanisms, refresh token revocation capabilities, and session policies supported by the integrated system must be evaluated separately.

An expired access token also does not mean the application session must expire immediately; how long the session lasts is the RP's decision. Conversely, an active session does not guarantee the previously issued access token is still accepted by the Resource Server. Application design must coordinate these lifecycles, especially when refresh tokens are involved.

## 9. OIDC Security in Real-World Applications

### 9.1. Trust Boundaries

| Trust Boundary | What Must Be Protected |
|---|---|
| Browser ↔ RP | HTTPS, `Secure`/`HttpOnly` session cookies, appropriate `SameSite`, and CSRF protection |
| RP ↔ OP | Trusted issuer/metadata, TLS, exact redirect URI, client authentication when applicable |
| Authorization callback | `state` and request binding, nonce if sent, code + PKCE |
| OP → RP via ID token | Signature, algorithm, issuer, audience, timestamps, nonce |
| RP ↔ UserInfo | Appropriate access token, HTTPS, `sub` matching the ID token |
| RP ↔ API | Access token with right audience/scopes, resource-level authorization at the API |

For SPAs, avoid exposing access/refresh tokens in URLs, logs, analytics, or anywhere third-party JavaScript could read them. With a BFF, keeping tokens on the backend reduces the chance of JavaScript directly reading tokens, though it does not eliminate the impact of XSS or CSRF on the browser session.

### 9.2. Common Pitfalls

| Mistake | Consequence | Proper Approach |
|---|---|---|
| "OAuth 2.0 already gives an access token, so it's enough for login" | No standardized user authentication contract | Use OIDC, request `openid`, and validate the ID token |
| "Being able to decode the JWT means the token is valid" | May accept forged tokens, wrong issuer, or wrong audience | Use a library to verify signature and all required claims |
| Sending an ID token to call a REST API | Wrong recipient/purpose and risk of token confusion | APIs accept access tokens intended for the API |
| Using `email` as the sole identifier key | Email can change, be unverified, or be recycled | Store `(iss, sub)` key; link emails under a dedicated policy |
| Equating "logged in" with "has admin privileges" | Risk of over-privileged access | Separate authentication from business authorization |
| Skipping `state`/`nonce` validation in custom implementations | Vulnerable to cross-context callbacks/tokens or replay | Use a trusted OIDC library and enforce request binding |
| Assuming the OP performed MFA | Authentication assurance may be lower than business requirements | Agree on `acr`/`amr`/`max_age` and validate explicitly |
| Expecting RP logout to automatically clear the OP session | Users may still silently SSO back in | Design OP-integrated logout if required |
| Putting a server `client_secret` into a SPA | Secret is exposed to end-users | SPA public client + PKCE or BFF confidential client |
| Trusting an arbitrary `roles` claim from an unverified token | Privilege escalation risk | Verify issuer/token and map permissions under controlled rules |

## 10. End-to-End Example: Logging into a Document Management System

Suppose a system has three components:

- `https://app.example.org`: Spring Boot MVC acting as the OIDC RP.
- `https://login.example.org`: OpenID Provider managed by the enterprise.
- `https://api.example.org`: Document API acting as the OAuth Resource Server.

When an employee accesses the documents page:

1. The RP redirects the browser to the OP with `scope=openid profile email` and request-binding parameters.
2. The user authenticates at the OP. The OP returns an authorization code, and the RP exchanges it for an ID token and an access token.
3. The RP validates that the ID token has `iss=https://login.example.org`, `aud=document-web-client`, valid signature/timestamps, and matching nonce if sent.
4. The RP maps `(iss, sub)` to an internal employee record, checks that the account is active, and creates a session.
5. When loading the document list, the RP sends the **access token** to the API. The API validates the token for the exact audience and required scopes, then checks permissions on each document.
6. When the user logs out, the RP clears its session and considers calling the OP logout endpoint if the corresponding SSO session should also end.

If the RP receives an ID token with a valid `sub` whose internal account has been disabled, **the RP still denies access to the application** per policy. This illustrates that **OIDC proves identity; the application decides system access rights**.

## 11. How to Remember the Boundary Between OAuth 2.0 and OIDC

| Question | Responsible Component |
|---|---|
| Who was authenticated by the IdP, and for which application was the authentication proof issued? | **OIDC ID token** after RP validation |
| Which APIs can the application call and with what scopes? | **OAuth 2.0 access token** and Resource Server policies |
| Where do the user's name, email, and picture come from? | **OIDC claims** in the ID token / UserInfo, if provided by the OP |
| Is the user allowed to view documents from another department? | **Business authorization** enforced by the application/API |
| Why does Spring MVC remember the logged-in user across requests? | **Spring Security session/cookie**, with a lifetime independent of tokens |
| How does the RP know the OP is trusted and the ID token is valid? | **Issuer, discovery, JWKS, and OIDC token validation** |

**Conclusion:** OpenID Connect turns OAuth 2.0 into an interoperable login foundation by adding the **ID token**, standardized identity claims, UserInfo, discovery, and validation rules. When applying it with Spring Security, let **OIDC Login** establish the user principal and session, let **OAuth2 Client** manage tokens for API calls, and let **Resource Server** validate access tokens and enforce resource access permissions.

## 12. Standards and Implementation References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): defines RP, OP, ID Token, UserInfo, flows, and token validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata discovery, issuer, and key information.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): the authorization framework upon which OIDC is built.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE for Authorization Code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): modern security recommendations for OAuth/OIDC.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): logging in with OAuth 2.0/OIDC in Servlet applications.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients and tokens for downstream calls.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): protecting APIs based on access tokens.
