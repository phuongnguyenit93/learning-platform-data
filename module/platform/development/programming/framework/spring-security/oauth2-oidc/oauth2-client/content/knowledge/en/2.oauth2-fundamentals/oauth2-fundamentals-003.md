# 2.3. Authorization Endpoint, Token Endpoint, and Redirect URI

In an application using **Spring Security OAuth 2.0/OIDC Client**, logging in via an Identity Provider (IdP) is typically based on the **Authorization Code Flow**. Three addresses appear repeatedly throughout this flow: the **Authorization Endpoint**, **Token Endpoint**, and **Redirect URI**. Understanding which party owns each address, what data is passed through each, and where Spring Security handles each step helps configure login properly while avoiding errors such as `redirect_uri_mismatch`, `invalid_grant`, or lost `state`.

## 1. Distinguish the Three Addresses Up Front

| Component | Where Does It Live? | Who Calls It? | Primary Role |
|---|---|---|---|
| **Authorization Endpoint** | Authorization Server/IdP | Browser redirected by the Client | Initiates the authorization request, authenticates the user, requests consent if needed, and returns an **authorization code** |
| **Token Endpoint** | Authorization Server/IdP | Client application calling directly from its server | Exchanges a valid authorization code for tokens; may also handle other grants |
| **Redirect URI** (callback URL) | Client application | Browser returning after the IdP processes the request | Receives `code` and `state` (or error details) so the Client can continue completing login |

Example in a hypothetical system:

- Authorization Endpoint: `https://id.example.test/oauth2/authorize`.
- Token Endpoint: `https://id.example.test/oauth2/token`.
- Redirect URI: `https://app.example.test/login/oauth2/code/company`.

The first two endpoints belong to the **IdP**; the Redirect URI belongs to the **Spring application**. The actual paths are decided by each provider, so never assume every IdP uses `/authorize` or `/token`.

There is one more URL easily confused with all three: `/oauth2/authorization/company`. This is **the login initiation path on the Spring Security Client side**, where `company` is the `registrationId`. It is neither the IdP's Authorization Endpoint nor the callback that receives the authorization code.

### How Do OAuth 2.0 and OpenID Connect (OIDC) Relate?

OAuth 2.0 describes the mechanism by which a Client obtains access to resources via an access token. **OIDC adds an identity authentication layer on top of OAuth 2.0**. When the Client requests the `openid` scope and the IdP supports OIDC, the login result of the Authorization Code Flow typically includes an **ID Token** for the Client to verify the user's identity.

- **Authorization code:** temporary, single-use value used to exchange for tokens; not a token for calling APIs.
- **Access token:** proof of permission to access an API or protected resource; should not be treated as an identity artifact in place of an ID Token.
- **ID Token:** OIDC token containing claims about the authentication event and identity; the Client must verify its signature and critical claims.
- **Refresh token:** may be issued depending on configuration, policy, and grant; not present in every login.

## 2. The Complete Authorization Code Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Spring Security Client
    participant A as Authorization Server / OIDC Provider

    U->>B: Opens page requiring login
    B->>C: GET /oauth2/authorization/company
    C->>C: Generates and stores state, PKCE verifier
    C-->>B: 302 to Authorization Endpoint
    B->>A: GET /authorize?response_type=code&...
    A->>U: Authenticates and requests consent if needed
    A-->>B: 302 to Redirect URI with code, state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Validates state and stored request
    C->>A: POST /token (code, redirect_uri, code_verifier, Client auth)
    A-->>C: access_token, id_token (OIDC), ...
    C->>C: Validates tokens and creates Authentication
    C-->>B: Establishes login session, redirects to target page
```

The most important boundary:

**Front channel (via the browser)** consists of redirecting to the Authorization Endpoint and redirecting back to the Redirect URI. **Back channel (direct server-to-server connection)** consists of the call from the Spring Client to the Token Endpoint. Client secrets and token responses must be handled on the appropriate server channel, never placed in browser URLs.

## 3. Authorization Endpoint: Where the Authorization Request Starts

### 3.1. What Does This Endpoint Do?

The Authorization Endpoint receives an **authorization request** from the Client. The Authorization Server may prompt the user to log in, enforce MFA, check an existing login session, display a consent screen, and then make a decision. In the Authorization Code Flow, the successful outcome is an **authorization code** returned to the Redirect URI.

The Client typically redirects the browser with an HTTP `302 Location` to the Authorization Endpoint; HTTP `GET` is the common method. The actual URL must be obtained from provider configuration or OIDC metadata, not guessed from the provider's name.

Shortened illustrative URL example:

```http
GET /oauth2/authorize?response_type=code&client_id=spring-web&
    redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
    scope=openid%20profile%20email&
    state=RANDOM_STATE&
    code_challenge=BASE64URL_SHA256_VERIFIER&
    code_challenge_method=S256&
    nonce=RANDOM_NONCE HTTP/1.1
Host: id.example.test
```

In an actual request, the parameters are joined into a single valid URL and properly URL-encoded; the example is line-wrapped for readability.

| Parameter | Meaning |
|---|---|
| `response_type=code` | Requests the Authorization Code Flow |
| `client_id` | Client identifier registered at the IdP; this is not a secret |
| `redirect_uri` | Callback address to which the Authorization Server is permitted to redirect the browser |
| `scope` | Access permissions requested by the Client; `openid` indicates an OIDC request |
| `state` | Random value linking the response to the original request, helping prevent CSRF and session confusion |
| `code_challenge` | Value derived from `code_verifier` per PKCE |
| `code_challenge_method=S256` | Declares the PKCE method using SHA-256 |
| `nonce` | OIDC random value binding the ID Token to the authentication request, reducing replay risk |

Not every OAuth 2.0 request includes `nonce`: this parameter belongs to OIDC. Similarly, `scope=openid` is what distinguishes an OIDC request from plain OAuth 2.0.

### 3.2. What Does the Authorization Server Return?

After the user is authenticated and approves the request (if needed), the Authorization Server redirects the browser back to the callback:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/company?code=ONE_TIME_CODE&state=RANDOM_STATE
```

The application receives the **code**, which it must then exchange at the Token Endpoint. The code has a short lifetime, is typically single-use, and is bound to the original request. A code cannot be used directly like an access token to call an API.

If the user denies access or authorization fails, the response may be:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/company?error=access_denied&state=RANDOM_STATE
```

When the `redirect_uri` parameter is invalid, the Authorization Server **should not automatically redirect** to an untrusted address. Therefore, some configuration errors appear directly on the IdP instead of returning to the application.

### 3.3. `state`, `nonce`, and PKCE Solve Different Problems

These three mechanisms often appear together, yet none can replace another:

| Mechanism | What Does It Bind? | Primary Goal |
|---|---|---|
| **`state`** | The authorization response to the Client-created request | Detects callbacks not belonging to the original session/request, preventing login CSRF |
| **`nonce`** (OIDC) | The ID Token to the OIDC authentication request | Prevents replay or mix-up of ID Tokens in relevant attack scenarios |
| **PKCE** | The authorization code to the Client that started the flow | Prevents an attacker who steals the code from exchanging it for tokens without `code_verifier` |

With PKCE, the Client generates a random `code_verifier`, keeps this value secret throughout the flow, and sends:

```text
code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_method = S256
```

Only `code_challenge` is sent to the Authorization Endpoint; `code_verifier` is sent later to the Token Endpoint. Prefer `S256`, especially for public clients. For confidential web clients, using PKCE remains a valuable hardening measure; it can be enabled explicitly in Spring Security when needed.

`state` and `nonce` must be randomly generated for each request and verified upon receiving the corresponding response. Never use a fixed string across all login sessions.

## 4. Token Endpoint: Where the Code Is Exchanged for Tokens

### 4.1. Why Must the Token Endpoint Be Called on the Back Channel?

Once the callback is received by Spring Security and `state` has been matched, the Client sends the authorization code directly to the Token Endpoint over HTTPS. The browser **does not** need to know the client secret, refresh token, or the full token response payload.

The request is typically an HTTP `POST` with an `application/x-www-form-urlencoded` body:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=ORIGINAL_RANDOM_VERIFIER
```

The example above uses the `client_secret_basic` client authentication method, appropriate when the Client is a server-side web application capable of protecting a secret. The Authorization Server may support other mechanisms, such as `private_key_jwt` or a public client with `client_authentication_method=none`; configure according to the registered Client type. **Never embed a client secret in the Authorization Endpoint URL or in browser-executed JavaScript.**

Key fields:

- `grant_type=authorization_code`: indicates an authorization code exchange.
- `code`: the exact code received from the current callback.
- `redirect_uri`: the same URI sent in the authorization request when one was provided; the Authorization Server enforces this binding.
- `code_verifier`: the original value matching the initial request's challenge if PKCE is used.
- Client authentication: performed per the registered method; no client secret is used for a public client.

### 4.2. Token Response

A successful response may look like:

```json
{
  "access_token": "eyJ...access-token-example",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "eyJ...id-token-example",
  "refresh_token": "optional-refresh-token"
}
```

This data is illustrative only, not real tokens. `id_token` appears in the OIDC Authorization Code Flow; `refresh_token` may be absent. Access tokens are sometimes JWTs and sometimes opaque strings: the Client should not assume the access token format on its own.

For OIDC login, Spring Security must verify the ID Token, checking items such as signature, issuer (`iss`), audience (`aud`), expiration (`exp`), and `nonce` if sent in the request. After successful validation, Spring creates an `Authentication` object in the security context. The access token is used when the Client needs to call protected resources; the ID Token serves to confirm the user's identity.

### 4.3. What Errors Does the Token Endpoint Return?

The Token Endpoint typically returns an HTTP error and JSON, for example:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code is invalid or expired"
}
```

`invalid_grant` can occur when the code has expired, was already used, belongs to another Client, the callback URI does not match, or the PKCE verifier is incorrect. `invalid_client` indicates failed Client authentication. You must distinguish errors **on the callback/front channel** from errors **during the token exchange/back channel** to pinpoint the true cause.

The Token Endpoint is not solely for authorization codes: depending on the Authorization Server and allowed grants, it can also process refresh tokens or client credentials. This lesson focuses on the authorization code flow in Spring Security OAuth2 Login.

## 5. Redirect URI: The Client's Callback Endpoint

### 5.1. The Redirect URI Does Not Belong to the Authorization Server

The Redirect URI is a URL **hosted by the Client application**. The Authorization Server only uses it as the target to redirect the browser after authentication/authorization. The callback must be pre-declared in the Client registration at the IdP.

By default with Spring Security OAuth2 Login:

```text
https://app.example.test/login/oauth2/code/company
                         └──────┬──────┘
                       registrationId = company
```

The `/login/oauth2/code/{registrationId}` path is typically handled by Spring Security's login filter; there is no need to write a custom `@GetMapping` to receive the code. Spring reads the query parameters, looks up the original authorization request, verifies `state`, performs the token exchange, and establishes login.

### 5.2. Why Must the URI Be Registered Exactly?

The Authorization Server needs to ensure the code is only sent to a callback authorized by the Client. Proper configuration must be consistent in three places:

1. The Redirect URI registered in the IdP admin console.
2. The `redirect_uri` sent in the authorization request generated by Spring.
3. The `redirect_uri` sent when exchanging the code at the Token Endpoint (if sent in the authorization request).

For instance, if the IdP has registered:

```text
https://app.example.test/login/oauth2/code/company
```

then the following URLs are normally **not equivalent**:

```text
http://app.example.test/login/oauth2/code/company
https://app.example.test:8443/login/oauth2/code/company
https://app.example.test/login/oauth2/code/other
https://app.example.test/login/oauth2/code/company/
```

Scheme, host, port, path, and trailing slash can all create mismatches. Each Authorization Server applies specific matching rules; some support standardized exceptions for loopback addresses in native apps. Do not rely on wildcard redirect URIs or uncontrolled dynamic URLs in production.

### 5.3. Why Is the Redirect URI Security-Sensitive?

If arbitrary callbacks are allowed, an attacker can attempt to capture the code via a domain they control. Therefore:

- Register a specific allowlist of callbacks, preferring HTTPS for real deployments.
- Avoid open redirects, where the callback forwards the user to an unvalidated external URL.
- Never put access tokens, refresh tokens, or client secrets into query strings, browser history, or access logs.
- Never log full `code`, `state`, or token values in operational logs.
- Ensure the callback returns to the exact browser session that initiated login so Spring can match `state`.

The URI `http://localhost:8080/login/oauth2/code/company` may be used in local development if the IdP allows registering that callback; that does not make plain HTTP over the public Internet a safe choice.

## 6. Connecting to Spring Boot and Spring Security

### 6.1. Default Paths to Remember

| Path or Property | Owner | Meaning |
|---|---|---|
| `/oauth2/authorization/{registrationId}` | Spring Client | URL the user/browser calls to **initiate** login |
| `authorization-uri` | IdP | Authorization Endpoint URL, used in the redirect request |
| `token-uri` | IdP | Token Endpoint URL, used to exchange the authorization code |
| `/login/oauth2/code/{registrationId}` | Spring Client | Default callback receiving the response from the IdP |
| `redirect-uri` | Client config | Callback URL template that Spring sends to the IdP |
| `issuer-uri` (OIDC) | IdP Metadata | Issuer address used to discover the provider's endpoints and verification keys |

The `registrationId` name (e.g., `company`) is purely a Spring-side configuration key. It does not have to match the `client_id` issued by the IdP.

In the Servlet stack, two notable components are:

- `OAuth2AuthorizationRequestRedirectFilter` handles the OAuth2 initiation URL, builds the authorization request, saves correlation data (typically tied to the HTTP session), and redirects to the IdP.
- `OAuth2LoginAuthenticationFilter` handles the login flow callback and delegates authentication/code exchange to Spring Security OAuth2 Login infrastructure.

Supporting components such as `ClientRegistrationRepository`, `OAuth2AuthorizedClientService`, or `OAuth2AuthorizedClientRepository` store Client details and authorized clients/tokens according to the configured mechanism. Application developers usually do not need to manually build HTTP requests to the Token Endpoint.

### 6.2. Configuring an OIDC Provider with `issuer-uri`

A Spring Boot 3 and Spring Security 6 application can start with the `spring-boot-starter-oauth2-client` dependency and the following illustrative configuration:

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
            scope: openid, profile, email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

`OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are application environment variables, not real names/values. `issuer-uri` must point to the exact issuer published by the IdP, typically discoverable via a corresponding `.well-known/openid-configuration` URL.

Example returned metadata fields:

```json
{
  "issuer": "https://id.example.test/realms/company",
  "authorization_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://id.example.test/realms/company/protocol/openid-connect/certs"
}
```

When the provider supports discovery, Spring reads the endpoints from metadata and sets up the appropriate configuration. Thus the Authorization Endpoint and Token Endpoint **do not need to be manually configured** if discovery info is accurate. When a provider does not support discovery, you can specify `authorization-uri`, `token-uri`, `user-info-uri`, `jwk-set-uri`, and required properties depending on the OAuth2/OIDC provider.

You must register the exact callback, such as:

```text
http://localhost:8080/login/oauth2/code/company
```

for local development running on port 8080, and:

```text
https://app.example.test/login/oauth2/code/company
```

for production. Values registered at the IdP must match the actual URL Spring generates in each environment.

### 6.3. Enabling OAuth2 Login

Simple Servlet Security configuration:

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
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

When visiting `http://localhost:8080/oauth2/authorization/company`, Spring Security builds an authorization request using the `company` registration configuration and redirects the browser to the Authorization Endpoint. After the user logs in successfully and the IdP returns the browser to `/login/oauth2/code/company`, Spring continues the processing steps. The configuration above is for **session-based web login**; calling APIs as a Client (`oauth2Client`) or validating bearer tokens at an API (`oauth2ResourceServer`) are separate capabilities, even though they belong to the same Spring Security OAuth2 ecosystem.

### 6.4. Explicitly Enabling PKCE for Authorization Requests

Depending on the Client type and specific Spring Security version, automatic PKCE behavior can vary. To require `S256` PKCE for OAuth2 Login, you can configure a resolver:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;

@Configuration
class OAuth2RequestConfig {

    @Bean
    DefaultOAuth2AuthorizationRequestResolver authorizationRequestResolver(
            ClientRegistrationRepository registrations) {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization"
        );
        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce()
        );
        return resolver;
    }
}
```

Then use this resolver in the `SecurityFilterChain` configuration:

```java
http.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(authorizationRequestResolver)
    )
);
```

In the second snippet, `authorizationRequestResolver` is the bean injected into the `SecurityFilterChain` builder method. When combining the two examples, replace `.oauth2Login(Customizer.withDefaults())` with the call containing the resolver; avoid duplicate OAuth2 Login configurations. Spring retains the `code_verifier` associated with the authorization request to use during the code exchange. The Authorization Server must also support PKCE.

### 6.5. Intentionally Changing the Callback URL

Suppose the application wants its callback at `/auth/callback/company`. Three parts must be updated in sync:

**Callback template in Client configuration:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

**Path Spring Security listens on:**

```java
http.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(endpoint -> endpoint
        .baseUri("/auth/callback/*")
    )
);
```

**Redirect URI registered at the IdP:**

```text
https://app.example.test/auth/callback/company
```

Changing only one side can cause `redirect_uri_mismatch` at the IdP or callbacks arriving at the application without matching the processing filter. When using a custom callback configuration, still ensure the login initiation URL and authorization request remain properly aligned.

### 6.6. Applications Running Behind a Reverse Proxy or Load Balancer

A common error: users access `https://app.example.test`, but Spring receives the internal connection as `http://service:8080`, causing `{baseUrl}` to expand into an internal callback or the wrong scheme/port.

The solution is to configure the proxy to forward accurate public host/protocol information and enable Spring Boot to process forwarded headers where appropriate, for example:

```yaml
server:
  forward-headers-strategy: framework
```

Only trust forwarded headers from controlled proxy infrastructure; never let external clients dictate host/scheme via spoofed headers. If needed, set an explicit `redirect-uri` matching the environment's public URL. Afterward, verify the redirect URI in the authorization request against the entry registered at the IdP.

## 7. End-to-End Walkthrough Scenario

Suppose the application runs at `https://portal.example.test`, the IdP is at `https://sso.example.test`, the registration is `staff`, and the IdP has registered the callback:

```text
https://portal.example.test/login/oauth2/code/staff
```

The process unfolds as follows:

1. The user opens `https://portal.example.test/reports` while not logged in.
2. Spring triggers the login flow; the user may be routed to `/oauth2/authorization/staff`.
3. Spring generates `state`, `nonce` (if applicable), and a PKCE challenge, and redirects the browser to the Authorization Endpoint published by the IdP.
4. The IdP authenticates the user, then returns the browser to `https://portal.example.test/login/oauth2/code/staff?code=...&state=...`.
5. Spring compares `state` with the stored request, then calls the Token Endpoint over HTTPS to exchange the code and `code_verifier` for tokens.
6. In OIDC, Spring validates the ID Token and creates a login session. The user is redirected back to `/reports` via the saved-request mechanism.

Here are the three types of data traveling along three different segments:

| Segment | Typical Data | Passes Through Browser Address Bar? |
|---|---|---|
| Spring → Authorization Endpoint via redirect | `client_id`, `redirect_uri`, `scope`, `state`, `code_challenge`, `nonce` | **Yes** |
| Authorization Server → Redirect URI via redirect | `code`, `state`, or `error` | **Yes** |
| Spring → Token Endpoint via direct POST | `code`, `code_verifier`, `redirect_uri`, Client authentication | **No** |

Because the code appears in the callback URL, avoid logging, sharing, or forwarding callback URLs uncontrollably. PKCE, short lifetimes, and callback validation reduce the risk of code exposure, but do not replace session protection, HTTPS, and exact redirect URIs.

## 8. Common Errors and How to Isolate Them

| Symptom | Common Cause | Where to Check? |
|---|---|---|
| `redirect_uri_mismatch` | URL sent by Spring differs from URI registered at IdP; mismatched scheme, host, port, path, or trailing slash | Compare the URL-decoded `redirect_uri` from the authorization request with the callback list at the IdP |
| `invalid_client` at Token Endpoint | Wrong `client_id`/secret or client authentication method | Spring `registration` configuration and client authentication method at the IdP |
| `invalid_grant` when exchanging code | Code expired/already used, wrong `redirect_uri`, or mismatched PKCE verifier | Token request, code lifetime, and PKCE data of the current flow |
| Callback reports `state` error or original request not found | Lost session/cookie, callback landed on a different host, multiple tabs or stale flow overwritten, inconsistent session config | Session, cookies, proxy, `AuthorizationRequestRepository`, and redirect chain |
| Login succeeds at IdP but callback returns 404 | Callback path does not match Spring's filter/route | `redirect-uri`, `redirectionEndpoint().baseUri(...)`, and filter chain |
| Access token received but app does not treat it as OIDC login | Missing `openid` scope or incorrect IdP/OIDC metadata config | Requested scopes, `issuer-uri`, ID Token, and provider configuration |
| Callback URL has `http://` even though external access uses HTTPS | Reverse proxy not forwarding or app not handling public host/protocol | `Forwarded` / `X-Forwarded-*`, proxy config, and forwarded headers |
| Redirect loop or always returning to login | Authenticated session not saved/restored, cookies blocked, or misconfigured multiple filter chains | Session policy, cookies, security matchers, and saved requests |

When diagnosing an error, start with **which step failed**: cannot reach the IdP (initiation/Authorization Endpoint), cannot return to the Client (Redirect URI), returned to Client but cannot exchange tokens (Token Endpoint), or exchanged tokens successfully but cannot establish a login session (OIDC validation/session). You can temporarily raise Spring Security log levels in development, but always mask or avoid logging codes, session cookies, and tokens.

## 9. Implementation Principles to Remember

- **Separate responsibilities:** Authorization Endpoint and Token Endpoint are provided by the IdP; the Redirect URI is provided by the Client and registered with the IdP.
- **Use Authorization Code Flow with PKCE:** `state` and PKCE address different risks, so maintain both; with OIDC, use `nonce` and validate the ID Token per specification.
- **Keep secrets server-side:** Client secrets and token responses must not be sent through browser URLs or embedded in the frontend; use HTTPS and appropriate token storage.
- **Synchronize callbacks:** The URI in the IdP, authorization request, token request, and Spring callback filter must all align.
- **Leverage Spring Security mechanisms:** `oauth2Login` handles redirection, callback processing, code exchange, and authentication; applications do not need to write custom controllers to exchange codes in the default flow.
- **Distinguish tokens:** Authorization code, access token, ID Token, and refresh token have different purposes and lifecycles.
- **Read provider metadata:** With OIDC, `issuer-uri` and discovery retrieve the right Authorization Endpoint, Token Endpoint, and verification keys instead of guessing hardcoded paths.

## 10. Authoritative References for Deeper Study

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization request, redirect endpoint, token request, and error types.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge`, and the `S256` method.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, ID Token, `nonce`, and validation rules.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): configuring `oauth2Login` and Client registrations.

Once you grasp **the browser goes to the Authorization Endpoint**, **the browser returns to the Redirect URI**, and **Spring calls the Token Endpoint directly**, you have the right mental model to read requests, configure Client registrations, debug callback errors, and explain how Spring Security completes an OIDC login.
