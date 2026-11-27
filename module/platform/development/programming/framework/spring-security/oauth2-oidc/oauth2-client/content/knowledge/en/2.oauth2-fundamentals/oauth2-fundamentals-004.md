# 2.4. Authorization Grant, Authorization Code, Access Token, and Refresh Token

## 1. The Big Picture

OAuth 2.0 is a mechanism for **delegated authorization**: an application (client) is granted permission to call another system's API without receiving the user's password. In OpenID Connect (OIDC), OAuth 2.0 also serves as the foundation for **user authentication**, though plain OAuth 2.0 does not itself define login or identity.

Suppose a Spring Boot application wants to display a user's orders:

| Role | Responsibility | In the Example |
| --- | --- | --- |
| Resource owner | Entity that decides access permissions, usually a user | The owner of the orders |
| Client | Application requesting access permissions | Spring Boot web app |
| Authorization server | Processes authorization and issues tokens | OAuth 2.0 / OIDC provider |
| Resource server | Protects APIs and validates tokens | Orders API |

The terms in the lesson title belong to different layers:

| Term | What Is It? | Primary Purpose |
| --- | --- | --- |
| **Authorization grant** | Method or workflow giving the client a basis to request tokens | Selecting the appropriate authorization flow for the context |
| **Authorization code** | Short-lived, single-use code received via redirect in the Authorization Code flow | Exchanged for tokens at the token endpoint |
| **Access token** | Credential granting access to resources within a defined scope | Sent to the resource server to call APIs |
| **Refresh token** | Credential allowing a client to request a new access token without repeating the full user authorization flow | Sent to the token endpoint, if issued |
| **ID token** (OIDC) | Proof of user authentication issued to an OIDC client | Confirms login identity; does not replace an access token for calling APIs |

**A grant is not a token.** An authorization code is not an access token. A refresh token is not an API access permission. In particular, an ID token and an access token may both be JWTs, yet their purposes, audiences, and validation rules are different.

## 2. Authorization Grants You Need to Know

`grant_type` is the parameter at the **token endpoint** indicating which grant type the client is using.

| Grant | Who Is Authorized? | When to Use? | Has Authorization Code? |
| --- | --- | --- | --- |
| **Authorization Code** (`authorization_code`) with PKCE | The user through the client | Web apps, SPAs, mobile apps with interactive login | Yes |
| **Client Credentials** (`client_credentials`) | The client/service itself | Service-to-service communication without an interactive user | No |
| **Refresh Token** (`refresh_token`) | Previously granted permissions | Requesting a new access token when holding a valid refresh token | No |
| **Device Authorization** (`urn:ietf:params:oauth:grant-type:device_code`) | User authenticating on another device | Smart TVs, CLIs, input-constrained devices | Does not use the Authorization Code flow's authorization code |
| **Implicit** (`response_type=token`) | The user | Legacy browser client design; not recommended for new applications | No |
| **Resource Owner Password Credentials** (`password`) | The user, but the client directly collects the password | Legacy design; not recommended | No |

OAuth 2.0 supports extensible grants. When choosing a grant, ask: is the application acting **on behalf of a user** or **in the name of the service itself**? With **Spring Security OAuth 2.0 OIDC Client**, the primary flow for web login is typically **Authorization Code + PKCE**. Client Credentials is used when tokens are needed for a backend task with no user.

## 3. Authorization Code Flow End-to-End

Example system components:

- Client: `https://app.example.com` (Spring Boot).
- Authorization server / OIDC provider: `https://id.example.com`.
- Resource server: `https://api.example.com`.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User's Browser
    participant C as Spring Security OAuth2 Client
    participant A as Authorization Server / OIDC Provider
    participant R as Resource Server
    U->>C: Visits page requiring login
    C-->>U: Redirect to authorization endpoint (state, PKCE)
    U->>A: Authenticates and consents when needed
    A-->>U: Redirect back to client with code and state
    U->>C: GET redirect_uri?code=...&state=...
    C->>A: POST token endpoint (code, code_verifier, client authentication)
    A-->>C: access_token (+ refresh_token, id_token)
    C-->>U: Creates login session / returns page
    C->>R: Calls API with Bearer access_token
    R-->>C: API response
    C-->>U: Displays data
~~~

### Step 1: Redirect to the Authorization Endpoint

The Client initiates a request with `response_type=code`, `client_id`, `redirect_uri`, and requested scopes:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo
    &scope=openid%20profile%20orders.read
    &state=RANDOM_STATE
    &code_challenge=BASE64URL_SHA256_VERIFIER
    &code_challenge_method=S256
    &nonce=RANDOM_NONCE
Host: id.example.com
~~~

This URL is line-wrapped for readability, not a verbatim valid HTTP request. In a real system, the query string must be properly encoded.

`scope=orders.read` requests permission to read orders; `openid` indicates an OIDC request. `state` is a random string tied to the authorization transaction so the client can correlate the callback. `code_challenge` is derived from `code_verifier` for PKCE. `nonce` in OIDC binds the ID token to the authentication transaction and must be validated when used.

### Step 2: User Logs In and Grants Permission

The user authenticates **at the authorization server**, without entering their password into the OAuth client. The authorization server may prompt the user to approve scopes or apply an existing consent policy. Successful authentication does not mean every scope is automatically approved.

### Step 3: Authorization Server Returns the Authorization Code

When authorization succeeds, the browser is redirected:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=SHORT_LIVED_CODE&state=RANDOM_STATE
~~~

The authorization code is short-lived, bound to the client and redirect URI, and **single-use only**. A code cannot be used to call a resource server. If the code expires, was already used, has a mismatched redirect URI, or fails PKCE validation, the token endpoint must reject it.

### Step 4: Client Exchanges the Code for Tokens via Back Channel

After verifying `state`, the backend contacts the token endpoint **directly**. Example for a *confidential client* capable of holding a client secret:

~~~bash
curl -X POST "https://id.example.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "web-client:REPLACE_WITH_CLIENT_SECRET" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=SHORT_LIVED_CODE" \
  --data-urlencode "redirect_uri=https://app.example.com/login/oauth2/code/demo" \
  --data-urlencode "code_verifier=ORIGINAL_RANDOM_VERIFIER"
~~~

The token endpoint verifies the code, client, redirect URI, and PKCE. For a *public client* such as a browser app or mobile app, **never embed a client secret** into code distributed to users; authentication at the token endpoint must match the client/provider type.

A response might look like:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile orders.read",
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "id_token": "ID_TOKEN_VALUE"
}
~~~

`expires_in` is the number of seconds the token remains valid at issuance time. The authorization server is **not required** to issue a refresh token; this depends on the grant, scopes, client type, and policy. `id_token` pertains only to OIDC, not plain OAuth 2.0.

### Step 5: Client Sends the Access Token to the API

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The resource server decides whether to accept the token and its permissions. An access token is **not necessarily a JWT**: it may be an opaque token or another format supported by the authorization server. A JWT access token typically requires validating the signature, `iss` (issuer), `aud` (audience), `exp`, and permissions; an opaque token can be validated via introspection or an appropriate resource server mechanism.

## 4. How Do PKCE, `state`, and `nonce` Differ?

| Mechanism | Threat Mitigated | What Must the Client Do? |
| --- | --- | --- |
| **PKCE** | Attacker intercepts the authorization code and exchanges it for tokens | Generate an unpredictable `code_verifier`; send `code_challenge` in the authorization request; send the original verifier when exchanging the code |
| **state** | Callback attached to the wrong session or forged request (authorization/login CSRF) | Generate `state` per transaction, store it bound to the session, and match it on callback |
| **OIDC nonce** | ID token replayed or not belonging to the expected authentication request | Send `nonce` and verify the `nonce` value in the ID token when applicable |

PKCE with the **S256** method computes:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

`code_verifier` must be generated randomly from a cryptographic source and retained for the current transaction; never put the verifier in the authorization request. Even if the code leaks, others cannot exchange it for tokens without the matching verifier when the server enforces PKCE properly. **PKCE does not replace `state`, `nonce`, redirect URI validation, or client authentication.**

Authorization Code + PKCE is the preferred choice for new applications, even for web backends with a client secret. In Spring Security, let the framework manage `state`, callbacks, and code exchange rather than building custom servlets for these security steps.

## 5. Access Token: Scoped and Time-Bounded Access

An access token represents granted permissions for a client in a specific context. Understand these properties:

| Property | Meaning |
| --- | --- |
| **Issuer** | Server that issued the token; the resource server only trusts valid issuers |
| **Audience/resource** | Target API allowed to accept the token, preventing tokens for one API from being accepted by another |
| **Scope/authority** | Granted permissions, e.g., `orders.read` differs from `orders.write` |
| **Expiry** | Token lifetime; clients should not use it after expiration |
| **Subject/client** | Token may represent a user or a service, depending on the grant |

Access tokens are **bearer** tokens: anyone holding the token can use it unless additional constraints apply. Therefore, use HTTPS, proper storage, short lifetimes, tight scopes/audiences, and avoid placing tokens in URLs, logs, analytics, or exceptions. Where supported, sender-constrained tokens (such as DPoP or mTLS) reduce misuse risk if a bearer token is stolen.

An API response of `401 Unauthorized` can result from an expired token, wrong issuer/audience, invalid signature, or revoked token. `403 Forbidden` usually means the token was recognized but lacks permissions; refreshing a token with the same scopes will not fix a missing-permission error.

## 6. Refresh Token and the Access Renewal Lifecycle

When an access token expires, the client can request a new token using the **Refresh Token grant** if the authorization server issued a refresh token. The user does not need to repeat login/consent for each refresh.

~~~mermaid
flowchart TD
    A["Client needs to call API"] --> B{"Is access token still valid?"}
    B -->|Yes| C["Call API with access token"]
    B -->|No| D{"Is a valid refresh token available?"}
    D -->|Yes| E["POST /token with grant_type=refresh_token"]
    E --> F{"Refresh succeeded?"}
    F -->|Yes| G["Save new access token; replace refresh token if rotated"]
    G --> C
    F -->|No| H["Clear invalid token state; re-authorize / re-login"]
    D -->|No| H
~~~

Example request from a confidential client:

~~~bash
curl -X POST "https://id.example.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "web-client:REPLACE_WITH_CLIENT_SECRET" \
  --data-urlencode "grant_type=refresh_token" \
  --data-urlencode "refresh_token=REFRESH_TOKEN_VALUE"
~~~

The response may contain a new access token, a new expiration, and a new refresh token:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_REFRESH_TOKEN_IF_ROTATED",
  "scope": "openid profile orders.read"
}
~~~

Do not assume a refresh response always includes `refresh_token`. If the authorization server returns a **new** refresh token (*rotation*), the client must safely replace the old value; reusing an old token can trigger reuse detection and revoke the entire token family. Applications handling concurrent requests must avoid two threads using the same refresh token simultaneously under rotation.

Mandatory rules when handling refresh:

1. Only send the refresh token **to the token endpoint**; never put it in headers sent to resource servers or expose it unnecessarily to the frontend.
2. Protect tokens in storage, restrict access and lifetime, and never log them.
3. Refresh tokens can expire or be revoked; the client must handle `invalid_grant` and guide the user back to authorization when appropriate, avoiding infinite refresh loops.
4. Scopes of a refreshed token cannot arbitrarily expand beyond granted permissions. Requesting additional permissions generally requires a new authorization request.
5. Confidential clients must authenticate properly when refreshing; public clients need refresh token protections such as rotation or sender constraints.
6. The `offline_access` scope in some OIDC providers may relate to refresh token issuance, but **does not guarantee** the provider will always issue one; check the provider's specific policy.

Client Credentials typically simply requests a new access token upon expiration and does not need a refresh token because there is no interactive user authorization session.

## 7. An OIDC ID Token Differs from an Access Token

OIDC uses the ID token to confirm authentication results to the **client**. An ID token can contain `iss`, `sub`, `aud`, `exp`, `iat`, and `nonce` (when used). The client must validate required claims, signature, and correlation with the login transaction.

Example with the application displaying orders:

- **"Who just logged in?"** — use the validated OIDC principal/ID token.
- **"Can we call the orders API?"** — use an access token issued for that API and scope.
- **"Access token expired?"** — use the refresh token at the token endpoint if one was issued.
- **"Can we send the ID token in `Authorization: Bearer` instead of an access token?"** — no; the ID token has an audience and semantics meant for the OIDC client, and does not prove permission to call an API.

In Spring Security, `oauth2Login()` can authenticate the OIDC user; `OAuth2AuthorizedClient` holds the token state used to call resources. **The web app's login session and the API access token lifecycle are two separate concepts.**

## 8. Configuring and Using Spring Security OAuth 2.0 Client

### 8.1. Registering an OIDC Client in Spring Boot

Example for a server-side web app:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: ${OAUTH2_CLIENT_ID}
            client-secret: ${OAUTH2_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          demo:
            issuer-uri: https://id.example.com/realms/demo
~~~

`issuer-uri` is an illustrative address and must be replaced with the real issuer of a provider supporting discovery. Register the exact redirect URI, client ID, authentication method, and scopes at the authorization server. The client secret is a backend secret sourced from environment variables/secret store; never commit real values.

Example `SecurityFilterChain` for Spring Security Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

The path `/oauth2/authorization/demo` initiates the authorization flow for the `demo` registration. The corresponding default callback is `/login/oauth2/code/demo`. Spring Security generates, stores, and validates transaction state, sends the code to the token endpoint, performs OIDC validation when `openid` is present, and associates the authorized client with the principal. Paths, base URL, and proxy/HTTPS configuration must align with the provider.

### 8.2. `OAuth2AuthorizedClient` and Automatic Refresh

Commonly confused types:

| Spring Security Type | Function |
| --- | --- |
| `ClientRegistration` | Client configuration, provider, scopes, grant type, endpoints |
| `OAuth2AuthorizedClient` | A client registration that has been authorized for a principal; holds access token and refresh token if present |
| `OAuth2AuthorizedClientManager` | Performs/continues authorization using appropriate providers; can refresh tokens |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Loads/stores authorized client state depending on deployment |

An `OAuth2AuthorizedClientManager` for a Servlet request context:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientConfig {
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
            new DefaultOAuth2AuthorizedClientManager(registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

In a method with the user's `authentication` and injected manager, the client requests the authorized client as follows:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("demo")
    .principal(authentication)
    .build();

OAuth2AuthorizedClient client = authorizedClientManager.authorize(request);
if (client == null) {
    throw new IllegalStateException("OAuth2 client is not authorized");
}
String accessToken = client.getAccessToken().getTokenValue();
// Send accessToken over HTTPS to the appropriate downstream resource server.
~~~

The two types in the snippet are `org.springframework.security.oauth2.client.OAuth2AuthorizeRequest` and `OAuth2AuthorizedClient`. The manager can only refresh when the provider supports it, the refresh token is still valid, and storage/authorization configuration fits; not every registration receives a refresh token.

For background jobs without a Servlet request, consider `AuthorizedClientServiceOAuth2AuthorizedClientManager` and the `client_credentials` grant if the task is not tied to a user. Across multiple applications/instances, decide how to store tokens durably, protect secrets, and coordinate refresh token rotation; avoid storing all tokens in global variables or sending them to the browser without proper design.

### 8.3. A Web Session Is Not Equivalent to Token Lifetime

An application may still maintain a login session while the access token has expired and requires refreshing. Conversely, a revoked refresh token does not automatically mean the application's session cookie is deleted immediately. Logout behavior, session timeout, token revocation, and refresh-failure handling must match product and provider requirements.

## 9. Failure Scenarios and How to Distinguish Them

| Symptom | Likely Cause | How to Handle |
| --- | --- | --- |
| Callback returns `error=access_denied` | User/policy denied authorization | Show a message and do not assume permission was granted |
| Callback has code but login does not complete | Mismatched state, lost session cookie, wrong redirect URI | Check state/session, proxy, HTTPS, and callback URL |
| Token endpoint returns `invalid_grant` on code exchange | Code expired/used, wrong redirect URI, or PKCE mismatch | Restart the Authorization Code flow properly |
| Token endpoint returns `invalid_client` | Wrong Client ID, secret, or authentication method | Compare against client configuration registered at the provider |
| Token response has no refresh token | Provider does not issue one for this grant/client/scope | Redesign the authorization flow for when tokens expire |
| Refresh returns `invalid_grant` | Refresh token expired, revoked, or reused after rotation | Remove the old authorized client and require re-authorization |
| API returns `401` | Token expired or wrong issuer, audience, signature, or revoked | Check token and resource server; refresh properly if available |
| API returns `403` | Token accepted but lacks permissions/scopes | Check scopes and policies; refreshing with the same scopes usually won't help |
| OIDC login works but API fails | Sent ID token instead of access token or wrong audience | Send the proper access token for the target API |

Do not log full callback URLs, authorization codes, access tokens, refresh tokens, or client secrets. Log error codes, correlation IDs, and non-sensitive metadata instead.

## 10. Three Examples of Choosing the Right Grant

**User-facing web app:** users log in via OIDC using Authorization Code + PKCE. Spring Boot receives the authorization code at the callback, exchanges it for tokens, and uses the access token to read orders; refreshes when needed if a refresh token was issued. The ID token serves login.

**Nightly data sync:** one service calls another service's API using Client Credentials. There is no authorization code or user session; it typically requests a new access token upon expiration rather than expecting a refresh token.

**Login on a Smart TV:** the device displays a code for the user to log in on a phone/computer. Use the Device Authorization grant; the device code is not the authorization code of the Authorization Code flow.

~~~text
Authorization Code + PKCE
  User logs in / authorizes
      -> authorization code (short-lived, single-use)
      -> token endpoint (+ code_verifier)
      -> access token -> call resource server
      -> refresh token (if issued) -> token endpoint -> new access token

OIDC may additionally issue an ID token -> OIDC client verifies user identity.
~~~

The key rule to preserve when developing with Spring Security OAuth 2.0 OIDC Client is: **authorization codes are only for exchanging tokens, access tokens are only sent to the right API, refresh tokens are only sent to the token endpoint, ID tokens are for OIDC authentication, and the grant determines the authorization flow matching the application type.**
