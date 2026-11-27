# 10.9. Analyzing `access_token`, `token_type`, `expires_in`, `scope`, and `refresh_token`

In a **Spring Security OAuth 2.0/OIDC Client**, after the user finishes authenticating at the Authorization Server, the Client application typically receives an **authorization code** via the Redirect URI. The Client sends that code to the **Token Endpoint** to exchange it for tokens. A successful result is a **token response** containing attributes that determine how the Client can call APIs, how long the token remains valid, and whether it can obtain new tokens without forcing the user to sign in again.

The five core fields of an OAuth 2.0 token response are **`access_token`**, **`token_type`**, **`expires_in`**, **`scope`**, and **`refresh_token`**. They are related, yet not interchangeable:

- `access_token` is the credential for the Client to access protected resources.
- `token_type` indicates **how** to present the access token; the most common is `Bearer`.
- `expires_in` indicates the **lifetime** of the access token, usually in seconds.
- `scope` describes the **granted permission scope** for the access token.
- `refresh_token`, if present, is used in a separate request to obtain a new access token.

In an OIDC flow, the token response also includes **`id_token`** for the Client to verify the user's identity. This lesson focuses on the five OAuth 2.0 fields listed above while explaining how they work alongside the ID Token in Spring Security.

## 1. The Token Endpoint and Where the Token Response Fits

### 1.1. From Authorization Code to Token

In the **Authorization Code Flow**, the browser passes through the Authorization Endpoint and returns to the Spring application at a Redirect URI such as:

```text
https://app.example.test/login/oauth2/code/company?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Spring Security validates `state` and the preceding authorization request, then calls the Token Endpoint server-side over HTTPS. Simplified example request:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=ORIGINAL_PKCE_VERIFIER
```

Parameters are wrapped onto separate lines purely for illustration; an actual HTTP form body is encoded properly as `application/x-www-form-urlencoded`. This example uses `client_secret_basic` for a confidential web client. For a public client or another Client authentication method, the request varies according to the registration at the Authorization Server. `code_verifier` is sent when the flow uses PKCE.

A successful token response might look like:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "id_token": "EXAMPLE_ID_TOKEN"
}
```

**This is illustrative data**, not a real token or value usable for authentication. In OAuth 2.0, `access_token` and `token_type` are the required core fields of a successful token response. `expires_in` is recommended, while `scope` may be omitted when the granted scope matches what the Client requested. `refresh_token` is optional and depends on grant type, policy, and Client registration.

In a **successful OIDC Authorization Code Flow**, the Token Endpoint response includes `id_token` per OIDC rules. In plain OAuth 2.0 or a Client Credentials Grant without OIDC login, the response normally **does not** contain an ID Token.

### 1.2. Why Must the Response Be Protected?

Access tokens and refresh tokens are usually **bearer credentials usable directly**. The token response must travel over a **TLS/HTTPS back-channel connection** to the Client, never through URLs in the browser address bar.

Headers such as `Cache-Control: no-store` and `Pragma: no-cache` prevent storing sensitive responses in HTTP caches. Even so, the application must still avoid writing tokens to logs, exception messages, monitoring systems, inappropriate cookies, or redirect URLs.

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant Client as Spring Security Client
    participant AS as Authorization Server
    participant API as Resource Server

    Browser->>Client: GET /oauth2/authorization/company
    Client-->>Browser: 302 to Authorization Endpoint
    Browser->>AS: User authenticates and grants consent
    AS-->>Browser: 302 to callback?code=...&state=...
    Browser->>Client: GET /login/oauth2/code/company?code=...&state=...
    Client->>AS: POST Token Endpoint (authorization_code)
    AS-->>Client: access_token, token_type, expires_in, scope, refresh_token?
    Client->>Client: Save OAuth2AuthorizedClient and establish session
    Client->>API: Authorization: Bearer access_token
    API-->>Client: Data per token permissions
    opt Access token expires and refresh is allowed
        Client->>AS: POST Token Endpoint (refresh_token)
        AS-->>Client: New access token, new refresh token if rotated
    end
```

Note: The **Resource Server** verifies the access token presented by the Client on API calls. The **Spring OAuth2 Client** is responsible for receiving and managing tokens. The same application can play both roles, yet their logic and configurations are distinct.

## 2. Quick Reference Table of the Five Fields

| JSON Field | Typical Data Type | OAuth 2.0 Requirement | Meaning |
|---|---|---|---|
| `access_token` | String | **Required** in a successful token response | Credential used to access resources |
| `token_type` | String | **Required** | Mechanism for using the token, commonly `Bearer` |
| `expires_in` | Number, seconds | **Recommended**, not strictly mandatory | Remaining lifetime described at token issuance |
| `scope` | String, space-delimited scope names | **Required if different** from what the Client requested; may be omitted if identical | Actual granted permissions or scopes |
| `refresh_token` | String | **Optional** | Credential to request a new access token at the Token Endpoint |

This table is based on the token response model in [RFC 6749, Section 5.1](https://www.rfc-editor.org/rfc/rfc6749#section-5.1). Specific rules may be extended by other specs or a given Authorization Server's contract.

Do not invent rules like "missing `expires_in` means the token never expires" or "missing `refresh_token` means the Server is misimplemented." Both conclusions are incorrect.

## 3. `access_token` — The Token to Access Resources

### 3.1. What Question Does an Access Token Answer?

An access token is the credential the Client presents to a **Resource Server/API** to request a resource under granted permissions. For example, after a user signs in via OIDC, Spring might call a profile API:

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

The Resource Server validates the token according to its policy, such as:

- Whether the token was issued by a trusted Authorization Server.
- Whether the token is still valid or has expired/been revoked.
- Whether the token is intended for **the right API** (audience or equivalent claim).
- Whether the token carries the required scopes/permissions for the endpoint.
- Whether business rules and subject permissions allow access.

An access token **does not replace all authorization checks**. Holding a valid token does not mean access to every API or operation.

### 3.2. Must an Access Token Be a JWT?

**No.** OAuth 2.0 does not require access tokens to be JWTs. Two common formats exist:

| Format | Example | Characteristics |
|---|---|---|
| **Opaque token** | `a1b2c3...` | String without public structure; Resource Server may need introspection or a proprietary validation mechanism |
| **JWT access token** | `eyJhbGciOi...` | String containing header, payload, and signature; may include claims such as `iss`, `aud`, `exp`, `scope` |

Illustrative JWT payload:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-782",
  "aud": "https://api.example.test",
  "iat": 1780000000,
  "exp": 1780003600,
  "scope": "reports.read profile.read"
}
```

This is hypothetical **decoded** content; it is not a signed JWT. Actual claims and how scopes are represented can vary by token profile and provider.

**The Client must not infer trusted permissions or identity merely by Base64-decoding a token.** A JWT payload can be read without a key, yet authenticity must be verified. An OAuth2 Client usually does not need to decode an access token to log a user in: Spring Security OIDC Login uses the verified ID Token for identity, while the Resource Server is responsible for validating access tokens when APIs are called.

### 3.3. Access Token vs. ID Token

| Criterion | Access Token | ID Token |
|---|---|---|
| Primary purpose | Accessing resources/APIs | Confirming the authentication event and user identity in OIDC |
| Primary recipient | Resource Server | OIDC Relying Party/Client |
| Audience | Typically targets an API | Contains Client ID in `aud` per OIDC |
| Format | JWT or opaque | JWT per OIDC |
| Used as `Authorization: Bearer` to APIs? | Yes, when matching token type and API | **Never use in place of** an access token |
| Alone grants admin rights? | No | No |

If the Token Endpoint returns both, **never swap the ID Token into the access token's place** when calling an API. An API may reject an ID Token due to wrong audience or because the token is not meant for that resource.

### 3.4. Is an Exposed Access Token Dangerous?

With a **Bearer** token, anyone holding the token can generally use it within its granted scope until it expires or is revoked. Therefore:

- Never put tokens in URL query strings or fragments.
- Never log raw tokens in exceptions, analytics, access logs, or debug responses.
- Never store tokens in the frontend if the app relies on backend sessions and has no clear reason to do so.
- Only send tokens to trusted target APIs over HTTPS.
- Choose appropriate scopes, audiences, and lifetimes.
- Protect token stores and the credentials used to obtain new tokens.

A **signed-only** JWT still has a readable payload. Never place application secrets or unnecessary personal data into a token and treat the signature as encryption.

## 4. `token_type` — How the Client Presents the Access Token

### 4.1. What Does `Bearer` Mean?

Most OAuth 2.0 token responses use:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer"
}
```

`Bearer` is the token type defined in [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750). When a Resource Server accepts a Bearer token over HTTP, the standard and recommended header is:

```http
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

`Bearer` is the **authentication scheme** in the header, and `EXAMPLE_ACCESS_TOKEN` is the **token value**. Never store `"Bearer EXAMPLE_ACCESS_TOKEN"` as the `access_token` value itself and end up prepending a second `Bearer`.

Compare:

```text
Correct:
Authorization: Bearer EXAMPLE_ACCESS_TOKEN

Wrong:
Authorization: Bearer Bearer EXAMPLE_ACCESS_TOKEN

Inappropriate:
Authorization: Basic EXAMPLE_ACCESS_TOKEN
```

`Basic` is used for certain Client authentication methods at the Token Endpoint, not as the standard way to present a Bearer access token to a Resource Server.

### 4.2. Can the Value Differ from `Bearer`?

Yes. The `token_type` field specifies the token type the Client must understand to use it properly. Some OAuth extensions use proof-of-possession/token-binding mechanisms and other token types, such as `DPoP` in DPoP-enabled setups.

**Never assume every token type is equivalent to Bearer.** If a Client receives a token type not yet supported by the library and Resource Server, use the matching mechanism or report a configuration error. Seeing that an access token looks like a JWT is not enough to conclude it is a Bearer token.

### 4.3. How Is Token Type Represented in Spring Security?

Spring stores it on `OAuth2AccessToken`:

```java
import org.springframework.security.oauth2.core.OAuth2AccessToken;

// accessToken retrieved from a valid OAuth2AuthorizedClient.
OAuth2AccessToken.TokenType type = accessToken.getTokenType();
String scheme = type.getValue();  // Typically "Bearer"
```

This illustrative snippet assumes `accessToken` has already been retrieved from an authorized client. Spring Security's standard OAuth2 Client APIs support Bearer tokens and integrate cleanly with HTTP clients; when a specialized token type is needed, verify whether your version/framework supports it.

## 5. `expires_in` — Access Token Lifetime

### 5.1. Units and Interpretation

Token response:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

`expires_in: 3600` means a **lifetime of roughly 3,600 seconds (1 hour)** for the access token when the response is issued. It is **not** a Unix timestamp and does not mean the token expires at 03:600 or on Jan 1, 1970 plus 3,600 seconds.

Approximate calculation on the Client:

```text
receivedAt ≈ time when token response was received
expiresAt ≈ receivedAt + expires_in seconds

Example:
receivedAt = 2026-11-16T09:00:00+07:00
expires_in = 3600
expiresAt ≈ 2026-11-16T10:00:00+07:00
```

This illustrates the calculation; the actual issuance time can be slightly earlier than when the Client receives the response. Token management libraries may use the receipt timestamp and a **clock skew** buffer to avoid using a token too close to expiration.

### 5.2. Are `expires_in` and the `exp` Claim the Same?

No.

| Attribute | Where Is It? | Type / Unit | Meaning |
|---|---|---|---|
| `expires_in` | Top-level token response JSON | Relative number of seconds | Access token lifetime at issuance |
| `exp` | Claim inside a JWT when the token is a JWT | Absolute time as NumericDate (seconds since Unix epoch) | Expiration deadline checked by JWT verifiers |

With opaque access tokens, the Client cannot read `exp` from a JWT payload because the token is not a public JWT. Even when the token is a JWT, the Spring OAuth2 Client should rely on the **expiration metadata** managed by the framework rather than decoding the access token itself just for timestamps.

When the Resource Server verifies a JWT, it must enforce token expiration using its own verification logic. The Client estimating that a token has not expired does not guarantee the Resource Server will accept it: the token could be revoked, carry the wrong audience, or encounter clock skew between systems.

### 5.3. What If `expires_in` Is Absent?

RFC 6749 recommends including `expires_in`, without making it strictly mandatory in every response. An Authorization Server might communicate lifetime through another mechanism or documentation.

Never conclude:

```text
expires_in absent => token never expires
```

The Client must follow the provider's contract and parser/framework behavior. When no reliable expiration is known, handle API errors or re-authenticate per policy; never hardcode an excessively long TTL and treat it as a granted lifetime.

### 5.4. Refreshing Early to Reduce Errors

Suppose a token expires at 10:00, yet an API call starts at 09:59:59, crosses the network, and reaches the Resource Server at 10:00:01. The token may be rejected even though the Client thought a few seconds remained.

That is why client libraries commonly apply **clock skew** or a **refresh buffer** before expiration. Conceptual example:

```text
Token expiresAt = 10:00
Safety skew = 60 seconds
Client treats token as needing refresh starting at 09:59
```

This is an example, **not** a rule that every Spring Security version uses the same buffer or 60 seconds. Expiration and refresh handling should be delegated to `OAuth2AuthorizedClientManager` and its providers where appropriate.

### 5.5. Access Token Expiration Differs from Login Session Expiration

In OIDC Login with a backend session, the user may still have a valid `SecurityContext`/HTTP session even after the access token used to call APIs has expired.

- **HTTP session:** login state with the application.
- **Access token:** validity window for calling a specific Resource Server.
- **Refresh token:** ability to obtain new tokens if issued by the provider.
- **ID Token:** evidence of an OIDC authentication event, with its own `exp` and claims.

Do not equate "access token expired" with "HTTP session immediately expires." Conversely, session expiration does not guarantee the server-side refresh token was revoked; design logout and token management explicitly.

## 6. `scope` — The Scope Granted by the Authorization Server

### 6.1. Format of the `scope` Field

In an OAuth 2.0 token response, `scope` is normally **a single string of space-separated scope names**, not a JSON array:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "scope": "openid profile email"
}
```

The authorization request can also ask for scopes, such as:

```text
scope=openid%20profile%20email%20reports.read
```

The **requested** scopes and **granted** scopes can differ due to provider policies or user consent.

### 6.2. Requested Scope vs. Granted Scope

Suppose the Client sends:

```text
openid profile email reports.read reports.write
```

The Authorization Server approves only:

```text
openid profile email reports.read
```

The token response might contain:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email reports.read"
}
```

The application cannot treat `reports.write` as granted. If an action requires report-writing permission, the Client must handle the missing scope via an appropriate UI/re-consent flow or deny the action. The Resource Server is responsible for enforcing actual token scopes.

### 6.3. What If the Token Response Omits `scope`?

Under RFC 6749, when the granted scope **matches** what the Client requested, the `scope` field may be omitted. When it differs, the Server must return `scope` so the Client knows what was granted.

Thus, these two cases are not equivalent:

```text
A. Client requests openid profile email
   Token response omits scope field.
   => Per OAuth2 rules, granted scope can be understood as matching requested scope.

B. Client requests openid profile email reports.write
   Token response scope = "openid profile email".
   => reports.write was not granted.
```

This interpretation assumes an OAuth2-compliant provider. When integrating with non-standard custom systems, verify actual behavior and Client mapping configuration.

### 6.4. Scopes Are Not Application Roles

A crucial distinction when programming with Spring Security:

- The `openid` scope initiates OIDC authentication.
- `profile` and `email` request user profile claim sets.
- `reports.read` can be a provider-defined API scope.
- `ROLE_ADMIN` is an example of a **`GrantedAuthority`** for internal authorization in Spring.

There is no universal rule turning `scope=profile email` into `ROLE_USER` or `ROLE_ADMIN`. Mapping scopes, roles, groups, and business permissions must be designed explicitly from verified sources.

### 6.5. Scope and Audience Both Govern Access

A token with `scope=reports.read` cannot necessarily call every API with a `/reports` endpoint. It must also **target the right Resource Server** and satisfy the API's audience and policy.

Example:

```text
Access token A:
aud = https://api-a.example.test
scope = reports.read

Access token B:
aud = https://api-b.example.test
scope = reports.read
```

API B can reject token A even though its scope looks identical to token B. Never take an access token issued for the UserInfo Endpoint or one API and treat it as automatically valid for every resource.

## 7. `refresh_token` — Obtaining a New Access Token When Permitted

### 7.1. What Is a Refresh Token Used For?

Access tokens are typically short-lived to limit exposure if leaked. A refresh token, if issued by the Authorization Server, lets the Client call the **Token Endpoint** with the `refresh_token` grant to request a new access token without immediately redirecting the user through a login screen again.

Example initial token response:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN_1",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_1",
  "id_token": "EXAMPLE_ID_TOKEN"
}
```

When renewal is needed:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=EXAMPLE_REFRESH_TOKEN_1
```

This is a **direct POST from the Client to the Token Endpoint** using the registered Client authentication method. Never place refresh tokens into browser URLs.

A successful refresh token response might look like:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN_2",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_2"
}
```

The `refresh_token` field in the refresh response may be a **new token** under **refresh token rotation**. If the Authorization Server does not issue a new refresh token on refresh, continuing to use the old token must follow provider policy and rules. Never assume an old token remains valid once the provider has announced revocation or replacement.

### 7.2. Is a Refresh Token Always Issued?

No. Whether one is issued depends on:

- Client type: confidential server-side, public native/SPA, etc.
- Authorization grant: authorization code, client credentials, or another grant.
- Approved scopes and consent.
- Authorization Server lifetime and refresh token policies.
- Client trust level and refresh token protection mechanisms.
- Offline access settings when the user is no longer present.

For the **Client Credentials Grant**, RFC 6749 notes that a refresh token **should not** normally be included in the token response because the Client can authenticate directly to request a new token. For **OIDC Login**, the `offline_access` scope can request offline access capability, yet **does not guarantee** every provider or Client will receive a refresh token. Check the provider's policy and consent rules.

### 7.3. Refresh Tokens Can Expire or Be Revoked

A refresh token is not permanent access. Situations that cause refresh to fail:

- The refresh token expired or is no longer valid.
- The user revoked consent.
- The Client was disabled or its secret/credentials changed.
- The Authorization Server revoked the session or token family.
- An old refresh token was replaced after rotation.
- Security policy requires fresh user interaction.

The Token Endpoint may return an error such as:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or expired"
}
```

Never retry endlessly with a rejected refresh token. A sensible strategy is removing the invalid authorized client when appropriate, guiding the user through a fresh authentication/consent flow, and reporting an understandable status to the UI.

### 7.4. Refresh Token Rotation and Race Condition Risk

Some providers issue a **new refresh token on every use** and invalidate the previous one. Example:

```text
T0: Client holds RT-1
T1: Client sends RT-1 to Token Endpoint
T2: Server issues AT-2 and RT-2, potentially invalidating RT-1
T3: Client must save RT-2 and stop using RT-1
```

If two concurrent requests both use `RT-1`, one may succeed while the other fails. Therefore, refreshing tokens across multi-request/multi-instance apps requires consistent coordination rather than independent refresh calls from individual controllers.

OAuth2 Client libraries help manage authorized clients and refreshes, yet the application must still choose **storage and synchronization mechanisms** suited to its instance count, session model, and provider rotation policy.

### 7.5. Why Must Refresh Tokens Be Strictly Protected?

Refresh tokens grant ongoing ability to mint new access tokens. If leaked, damage can last far longer than leaking a short-lived access token. Principles:

1. Store them only in controlled locations; for confidential web apps, typically server-side.
2. Never log, display, or return refresh tokens in JSON to the frontend.
3. Protect stored data and transport, enforcing strict access controls.
4. Support rotation and persist new tokens promptly.
5. Handle revocation on logout or security incidents if supported by the provider and required by design.
6. Never share one refresh token across Clients/tenants belonging to different registrations.

**Server-side stored tokens still require protection.** Keeping tokens invisible in the browser does not automatically make databases, caches, backups, or operational logs safe.

## 8. Comparing the Three Key Tokens in an OIDC Client

During an OIDC Authorization Code Flow, you may encounter an **access token**, an **ID Token**, and a **refresh token**:

| Token | Consumer | Purpose | Sent to APIs? | Used to Refresh? |
|---|---|---|---|---|
| Access token | OAuth2 Client and Resource Server | Authorizes resource access | **Yes**, when type/audience/scope match | Not used as a refresh credential |
| ID Token | OIDC Client/Relying Party | Verifies user authentication/identity | **Never** substitute for an access token | Not used as a refresh token |
| Refresh token | OAuth2 Client and Authorization Server | Requests new tokens | **Never** send as a Bearer token to business APIs | **Yes**, at the Token Endpoint |

Additionally, there is the **authorization code**: a temporary, single-use code received by the Client via callback to exchange for tokens. An authorization code is distinct from all three tokens above.

Example Spring Security OIDC Login lifecycle:

1. Receive `code` via browser redirect.
2. Exchange the code at the Token Endpoint.
3. Verify the ID Token to establish `OidcUser`/`Authentication`.
4. Use the authorized access token to call the UserInfo Endpoint or downstream APIs.
5. When the access token needs renewal and a refresh token exists, use the refresh token over the back channel.
6. When refresh is no longer valid, re-trigger authentication/authorization per policy.

Do not assume an expired `access_token` means `OidcUser` must be discarded immediately. Session state and token refresh lifecycles should be managed distinctly.

## 9. How Is a Token Response Represented in Spring Security?

Spring Security provides abstractions so applications do not manually parse JSON or pass loose token strings around.

### 9.1. From HTTP JSON to `OAuth2AccessTokenResponse`

During token exchange, Spring Security parses the Token Endpoint response and models OAuth2 data using:

```text
OAuth2AccessTokenResponse
 ├── OAuth2AccessToken accessToken
 │    ├── TokenType (usually BEARER)
 │    ├── tokenValue
 │    ├── issuedAt
 │    ├── expiresAt
 │    └── scopes
 ├── OAuth2RefreshToken refreshToken? 
 └── additionalParameters
      └── may hold extension fields (OIDC id_token, ...)
```

This is a conceptual diagram, not a JSON serialization of the classes.

Related classes:

| Class | Package | Data / Purpose |
|---|---|---|
| `OAuth2AccessTokenResponse` | `org.springframework.security.oauth2.core.endpoint` | Parsed token response |
| `OAuth2AccessToken` | `org.springframework.security.oauth2.core` | Access token, token type, issued/expires timestamps, scopes |
| `OAuth2RefreshToken` | `org.springframework.security.oauth2.core` | Refresh token |
| `OAuth2AuthorizedClient` | `org.springframework.security.oauth2.client` | `ClientRegistration` + principal name + issued access/refresh tokens |
| `OAuth2AuthorizedClientRepository` | `org.springframework.security.oauth2.client.web` | Saves/loads authorized clients in a web request context |
| `OAuth2AuthorizedClientService` | `org.springframework.security.oauth2.client` | Manages authorized clients by client registration and principal |

Notably, `OAuth2AuthorizedClient` is the object an application typically works with **after login** or once client authorization succeeds. You rarely need to craft raw HTTP requests to the Token Endpoint when using Spring Security OAuth2 Client.

### 9.2. Mapping Table from Response JSON to Spring

| Token Endpoint JSON | Spring Security | Notes |
|---|---|---|
| `access_token` | `OAuth2AccessToken#getTokenValue()` | Sensitive value; never log |
| `token_type` | `OAuth2AccessToken#getTokenType()` | Usually `TokenType.BEARER` |
| `expires_in` | `issuedAt` / `expiresAt` on `OAuth2AccessToken` | Spring models expiration as an instant rather than a raw JSON number |
| `scope` | `OAuth2AccessToken#getScopes()` | `Set<String>` after Spring parses scopes |
| `refresh_token` | `OAuth2AuthorizedClient#getRefreshToken()` | May be `null` |

Having `OAuth2AccessToken#getExpiresAt()` as an `Instant` (or null when absent) makes time comparisons clean in Java and avoids mistaking `expires_in` for an epoch timestamp.

### 9.3. `ClientRegistration` and OAuth2 Login Configuration

Example `application.yml`:

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
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

Spring Security Servlet:

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
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

This configuration illustrates a web application using OIDC login and OAuth2 Client. To run in a real environment, you need the Spring Security OAuth2 Client dependency matching your Spring Boot version, a valid IdP, and a Redirect URI registered at the provider.

`client-id` and `client-secret` must be supplied via environment variables or a secret manager. The `example.test` URLs are placeholders only.

### 9.4. Safely Reading Token Metadata with `OAuth2AuthorizedClient`

In an MVC application, Spring Security offers `@RegisteredOAuth2AuthorizedClient` to inject an authorized client by registration. Example endpoint returning **non-secret metadata**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TokenMetadataController {

    @GetMapping("/account/token-metadata")
    public Map<String, Object> metadata(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        OAuth2AccessToken accessToken = authorizedClient.getAccessToken();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put(
            "registrationId",
            authorizedClient.getClientRegistration().getRegistrationId()
        );
        result.put("tokenType", accessToken.getTokenType().getValue());
        result.put("scopes", accessToken.getScopes());
        result.put(
            "expiresAt",
            accessToken.getExpiresAt() == null
                ? null
                : accessToken.getExpiresAt().toString()
        );
        result.put(
            "refreshTokenAvailable",
            authorizedClient.getRefreshToken() != null
        );
        return result;
    }
}
```

Example response:

```json
{
  "registrationId": "company",
  "tokenType": "Bearer",
  "scopes": ["openid", "profile", "email"],
  "expiresAt": "2026-11-16T03:00:00Z",
  "refreshTokenAvailable": true
}
```

This example demonstrates reading token properties in Spring. Protect the endpoint with appropriate security rules; in production, expose metadata only when genuinely needed by functionality. **Never add**:

```java
// DO NOT return to the frontend in a backend-session web login.
result.put("accessToken", accessToken.getTokenValue());
result.put("refreshToken", authorizedClient.getRefreshToken().getTokenValue());
```

Returning tokens in JSON needlessly widens the token-leakage attack surface.

### 9.5. When `getRefreshToken()` Returns `null`

This can be completely normal. The application should:

- Check whether the provider issues refresh tokens in this flow.
- Review scopes, consent, and Client registration if refreshing is genuinely required.
- Be ready to ask the user to sign in again when the access token expires without a valid refresh path.
- Never substitute dummy strings or copy the access token into the refresh token field.

Features relying purely on the login session can continue working even without a refresh token. Only features that need a valid access token for downstream APIs must manage that token lifecycle.

## 10. Refreshing Tokens with `OAuth2AuthorizedClientManager`

### 10.1. Why Not Write `POST /token` Manually in a Controller?

Spring Security provides `OAuth2AuthorizedClientManager` along with providers implementing authorization flows, including refresh tokens. Using this infrastructure handles:

- Looking up the authorized client by `ClientRegistration` and principal.
- Checking whether the token is expired or nearing expiration per provider mechanics.
- Using the refresh token when present and permitted.
- Persisting the updated authorized client.
- Integrating with error handling such as `invalid_grant` per configuration.

Not every `authorize(...)` call is guaranteed to have a refresh token or fetch a new token. If the access token is still valid, the manager returns the existing authorized client. If renewal fails, the application must handle the error or transition into re-authentication.

### 10.2. Example Manager Configuration for Servlet Requests

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

In this example, `DefaultOAuth2AuthorizedClientManager` operates in an `HttpServletRequest`/`HttpServletResponse` context. For jobs running outside HTTP requests (scheduled jobs/background processes), Spring Security offers an `OAuth2AuthorizedClientService`-backed option, typically `AuthorizedClientServiceOAuth2AuthorizedClientManager`. Choose the manager type matching your execution environment.

### 10.3. Asking the Manager for a Valid Authorized Client

Inside a controller or service with the right request context and principal:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

// manager and authentication are supplied via DI / Spring Security.
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("company")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);

if (client == null) {
    // No matching authorized client; initiate or restore login flow.
}

String tokenType = client.getAccessToken().getTokenType().getValue();
```

This snippet demonstrates API usage, not a standalone copy-paste method. In a real application, handle the `client == null` branch and provider failures appropriately. With OAuth2 Login, the principal must map to its own authorized client; never grab one user's token to call APIs on behalf of another user.

When the Client needs to call APIs, use Spring Security OAuth2 Client's `RestClient`/`WebClient` integration backed by the appropriate `OAuth2AuthorizedClientManager`, rather than building headers and refresh logic manually in every controller. Exact HTTP client integration details depend on your Spring Security version.

### 10.4. How to Handle Failed Refreshes

Common strategies:

| Situation | Appropriate Behavior |
|---|---|
| Access token still valid | Reuse the current token for matching APIs |
| Access token nearing expiration, valid refresh token exists | Manager/provider can renew before the API call |
| No refresh token | Require re-login/re-authorization when a new access token is needed |
| Refresh returns `invalid_grant` | Discard invalid refresh state, avoid infinite retries; trigger re-authorization |
| API returns `401 invalid_token` | Inspect actual token, audience, expiry, revocation; may require refresh or re-login |
| API returns `403 insufficient_scope` | Insufficient permissions; refreshing with the same scope usually will not help |
| Concurrent requests trigger refresh together | Coordinate persistence/synchronization of authorized clients and rotation |

Never send a refresh token as `Authorization: Bearer` to a downstream API. Refresh tokens belong strictly to the Token Endpoint (or provider-designated token management endpoints) and must be safeguarded as high-value credentials.

## 11. Storing Authorized Clients in Multi-Instance Applications

In a single-machine development setup, authorized clients may live in memory or the HTTP session per Spring Security defaults. In multi-instance production apps, account for:

- **Session affinity or shared session store:** OAuth2 Login must preserve user session continuity across redirects.
- **`OAuth2AuthorizedClient` store:** the app must reliably retrieve the right access/refresh tokens per user and registration.
- **Refresh token rotation:** new tokens must be persisted atomically; prevent other instances from reusing stale tokens.
- **Data protection:** encryption at rest, access controls, log redaction, backup, and deletion policies.
- **Logout and revocation:** logging out of the app does not automatically revoke tokens at the Authorization Server; design lifecycle handling explicitly.
- **Access isolation:** an access token for API A must never leak into calls to API B or another Client.

Architecture overview:

```text
Browser ──> Spring MVC + OAuth2 Login
                     |
                     v
               SecurityContext
                     |
                     v
         OAuth2AuthorizedClientRepository
                     |
          Access token + Refresh token
                     |
                     v
       OAuth2AuthorizedClientManager
                     |
          (refresh if needed and allowed)
                     |
                     v
          API request with access token
```

If each instance stores tokens locally in memory and user traffic moves across nodes, the app may fail to find the authorized client or hold stale tokens. Choose an appropriate storage mechanism and test scale-out behavior.

## 12. Common Real-World Token Responses

### 12.1. OIDC Login with Refresh Token

```json
{
  "access_token": "AT-1",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "refresh_token": "RT-1",
  "id_token": "IDT-1"
}
```

Reading it: a Bearer access token with a roughly one-hour lifetime; three granted scopes; a refresh token for the Client; and an ID Token for OIDC identity verification.

### 12.2. OIDC Login Without Refresh Token

```json
{
  "access_token": "AT-2",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "openid profile",
  "id_token": "IDT-2"
}
```

This is still a valid OIDC Code Flow response. Once the access token expires, the Client cannot refresh solely from this response; it needs a re-authorization flow or another provider-supported mechanism.

### 12.3. OAuth2 Client Credentials

```json
{
  "access_token": "SERVICE-AT",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "invoices.read"
}
```

No OIDC ID Token or logged-in user details. The Client can request a fresh token via the Client Credentials Grant whenever needed and permitted by the Server. Refresh tokens are normally not issued here.

### 12.4. Token Response After Refresh with Rotation

```json
{
  "access_token": "AT-NEW",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "openid profile email",
  "refresh_token": "RT-NEW"
}
```

The Client must persist `RT-NEW` per rotation policy and stop assuming `RT-OLD` works. A refresh response might also omit a new `refresh_token`; in that case, follow the provider's contract and OAuth2 Client library behavior.

### 12.5. Server Omits `scope` Because It Matches the Request

Authorization request:

```text
scope=openid%20profile%20email
```

Token response:

```json
{
  "access_token": "AT-3",
  "token_type": "Bearer",
  "expires_in": 3600,
  "id_token": "IDT-3"
}
```

Per OAuth2 rules, omitting `scope` in this response is valid if the granted scope matches what was requested. Do not conclude "the token has no permissions."

## 13. Common Errors When Analyzing Token Responses

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `access_token` rejected when calling API | Wrong audience, scope, resource, or token revoked/expired | Check target API, granted permissions, and Resource Server validation |
| `Authorization` header rejected | Prepended `Bearer` twice, wrong token type, or sent ID Token | Inspect `token_type`, send only the valid access token |
| `expires_in=3600` yet token expires early | Clock skew, token revoked, or TTL counted from earlier issuance | Check clock skew, response/API errors, and provider policies |
| `expires_in` misread as Unix timestamp | Confused relative duration with JWT `exp` | Use `Instant`/expiresAt managed by Spring |
| Access token is not a JWT | Provider returns an opaque token | Do not decode manually; let Resource Server introspect/validate per contract |
| `openid` requested yet email missing from ID Token | Requesting a scope doesn't guarantee every claim; email may live at UserInfo | Check OIDC provider, actual claims, consent, and scopes |
| Token response omits `scope` | Granted scope likely matches requested scope | Apply RFC 6749; verify provider behavior |
| Only `read` granted even though `write` was requested | Provider restricted granted permissions | Never assume `write` was granted; handle permission limits cleanly |
| No `refresh_token` | Provider does not issue one for this Client/flow | Check policies, consent, grant, and related scopes |
| Refresh returns `invalid_grant` | Token expired, revoked, rotated, or belongs to another Client | Clear stale state, avoid infinite retries, re-authorize |
| Concurrent refreshes fail | Rotation + race condition updating tokens | Coordinate refresh and authorized client persistence |
| Old token still calls APIs after logout | Session logout does not automatically revoke tokens | Design revocation/token lifecycle per provider |
| Login session active yet API returns 401 | Access token no longer accepted | Distinguish login session from API token; refresh or re-authorize |
| API returns 403 even though token is unexpired | Missing scope/role/business authorization | Check permissions and audience, not just token expiration |
| Logs contain full token responses | HTTP logging/debug captured sensitive payloads | Redact at source, lower verbosity, purge leaked logs per procedure |

### 13.1. Reading Resource Server HTTP Errors Properly

When the Client calls an API with a Bearer token, errors may appear in `WWW-Authenticate`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

or:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

`invalid_token` can indicate expiration, revocation, or other token validation failures. `insufficient_scope` explicitly indicates missing permissions; refreshing a token with the same scopes usually will not solve it. Applications must distinguish the two before deciding whether to renew the token or request broader permissions.

## 14. Practice Exercises: Reading and Deciding How to Use Tokens

### Exercise 1: Identify Required and Optional Fields

Given the response:

```json
{
  "access_token": "TOKEN_A",
  "token_type": "Bearer",
  "expires_in": 1200,
  "scope": "reports.read"
}
```

Answer:

1. Which scheme is used to send the token to an API?
2. Is `expires_in` a Unix timestamp?
3. Which field in this response enables automatic refresh?
4. Can this token be used to write reports?

**Suggested answers:** `Bearer` scheme; `expires_in` is a relative duration in seconds; there is no `refresh_token`, so refresh capability cannot be assumed; `reports.read` does not grant `reports.write`.

### Exercise 2: ID Token vs. Access Token

A Client receives `id_token` and `access_token` after OIDC login. A developer puts `id_token` into `Authorization: Bearer` when calling an invoices API.

**Suggested answer:** Wrong purpose. The ID Token verifies user identity at the OIDC Client; the API requires an access token issued for the right Resource Server with matching permissions.

### Exercise 3: Clock Skew

A token response has `expires_in=600`. The Client computes `expiresAt≈10:00`, yet an API call at `09:59:59` is rejected as expired.

**Suggested answer:** Account for clock skew, network latency, or revocation; use `OAuth2AuthorizedClientManager` and refresh tokens early where available rather than waiting until the exact final second.

### Exercise 4: Refresh Token Rotation

Two concurrent requests read `RT-1`. The first refreshes successfully and receives `RT-2`; the second retries `RT-1` and gets rejected.

**Suggested answer:** Update persisted state with the latest refresh token and coordinate concurrency. Never retry infinitely with the old RT; inspect authorized client storage and refresh locking across instances.

### Exercise 5: Reading Metadata with Spring

After a successful OAuth2 Login, write an endpoint that returns only:

```json
{
  "tokenType": "Bearer",
  "scopes": ["openid", "profile", "email"],
  "refreshTokenAvailable": false
}
```

**Hint:** use `OAuth2AuthorizedClient#getAccessToken()` and `getRefreshToken()`; never return `getTokenValue()`. If the endpoint serves end users, evaluate whether exposing even this metadata is truly needed.

## 15. Operational and Security Principles to Remember

- **`access_token`** is the credential for accessing a Resource Server; it may be opaque or a JWT and must match the target audience and scopes.
- **`token_type`** specifies how to present the token; for `Bearer`, the standard format is `Authorization: Bearer ...`.
- **`expires_in`** is a relative lifetime in seconds; distinct from a JWT's `exp` claim and distinct from the HTTP session timeout.
- **`scope`** describes granted permissions; if narrowed, the application must respect the actual limits. Scopes do not automatically become internal roles.
- **`refresh_token`** is an optional credential for obtaining new tokens; highly sensitive and subject to rotation, expiration, or revocation.
- **OIDC ID Token** verifies identity at the Client, never substituting for an API access token.
- **Token responses are sensitive backend data.** Never push full token responses to the browser, logs, or URLs.
- **Spring Security OAuth2 Client** stores tokens via `OAuth2AuthorizedClient` and coordinates acquisition/renewal via `OAuth2AuthorizedClientManager`.
- **API token expiration and login session expiration are separate concerns.** Design logout, refresh, re-authorization, and API permissions per product needs.
- **Do not manually parse or refresh tokens when the library already provides the right mechanics.** Extend behavior only when a provider explicitly requires it and compatibility limits are understood.

## 16. References

1. [RFC 6749, Section 5.1 — Successful Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): `access_token`, `token_type`, `expires_in`, `scope`, and `refresh_token`.
2. [RFC 6749, Section 6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): refresh token grant, server responses, and refresh token rotation.
3. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): HTTP `Authorization: Bearer`, `invalid_token`, and `insufficient_scope`.
4. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Token Endpoint, ID Token, refresh tokens, and the meaning of `openid`.
5. [Spring Security Reference — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth2 Client and authorized client configuration.
6. [Spring Security Reference — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): authorization code, refresh token, and client credentials.
7. [Spring Security API — OAuth2AccessTokenResponse](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/endpoint/OAuth2AccessTokenResponse.html): token response model object.
8. [Spring Security API — OAuth2AccessToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AccessToken.html): `getTokenType()`, `getScopes()`, `getIssuedAt()`, and `getExpiresAt()`.
9. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): access/refresh tokens and `ClientRegistration`.
10. [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): managing, authorizing, and refreshing authorized clients.

When analyzing a Token Endpoint result, read **what the token is used for (`access_token`, `token_type`), how long it stays valid (`expires_in`), what it is permitted to do (`scope`), and whether a renewal mechanism exists (`refresh_token`)**. Spring Security stores and manages this data under the `OAuth2AuthorizedClient` model; the application's remaining job is sending tokens only to the right APIs, enforcing permissions, and protecting the entire token lifecycle.
