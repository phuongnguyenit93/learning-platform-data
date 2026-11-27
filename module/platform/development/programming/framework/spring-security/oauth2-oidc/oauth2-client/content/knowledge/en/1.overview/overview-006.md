# 1.6. Core Components and Lifecycle of an Authorized Client

In **Spring Security OAuth 2.0 OIDC Client**, the Spring Boot application acts as an **OAuth 2.0 Client**: on behalf of a user or the application itself, it requests an access token from an Authorization Server and uses that token to access protected resources. When OpenID Connect (OIDC) login is required, the application also uses identity information from the Identity Provider to authenticate the user.

The central concept of this lesson is **`OAuth2AuthorizedClient`**. This object represents **an authorized client registration**, bound to a specific principal and the received tokens. Understanding this object along with the components that create, store, load, and renew it will help you trace Spring Security's processing flow accurately.

## 1. The Big Picture: Who Does What?

A system typically has four roles:

| Role | Responsibility | Example |
| --- | --- | --- |
| **Resource Owner** | Entity with rights over the data, usually the user | User logging into the application |
| **Client** | Application requesting access permissions on behalf of the user or itself | Spring Boot application |
| **Authorization Server (AS)** | Authenticates, obtains consent when needed, and issues tokens | Keycloak, Okta, Spring Authorization Server |
| **Resource Server (RS)** | Protects APIs and validates access tokens | Profile, invoice, or document APIs |

When the Authorization Server supports OIDC, it also acts as an **OpenID Provider (OP)** and issues **ID tokens** for the client to authenticate the user's identity.

```
flowchart LR
    U["User / browser"] --> C["Spring Boot<br/>OAuth2 / OIDC Client"]
    C <-->|"Authorization Code, token"| AS["Authorization Server<br/>/ OpenID Provider"]
    C -->|"Access token"| RS["Resource Server / API"]
    RS -.->|"Validate token per configuration"| AS
```

**Distinguish three easily confused concepts:**

- **`ClientRegistration`** is the *static configuration* of a client registered with the Authorization Server: client ID, grant type, scopes, endpoints, redirect URI, etc.
- **`OAuth2AuthorizedClient`** is the *runtime authorized state*: a registration plus a principal and an access token (possibly accompanied by a refresh token).
- **`Authentication` / `OidcUser`** describes the logged-in user in Spring Security. This is authentication information; it does not replace the object storing API access tokens.

One application can have **multiple client registrations** (such as `web-oidc` and `billing-service`), and at the same time have **multiple authorized clients** corresponding to different users or principals.

## 2. Core Components in Spring Security

### 2.1. `ClientRegistration` and `ClientRegistrationRepository`

**`ClientRegistration`** describes *how* the application talks to the Authorization Server. Common properties:

| Property | Meaning |
| --- | --- |
| `registrationId` | Internal identifier name, e.g., `web-oidc`; used to look up the configuration |
| `clientId`, `clientSecret` | Client identity and credentials (if a confidential client) |
| `authorizationGrantType` | How tokens are obtained, e.g., `authorization_code` or `client_credentials` |
| `redirectUri` | Callback URL when using Authorization Code |
| `scopes` | Permissions requested by the client, e.g., `openid`, `profile`, `email` |
| `authorizationUri`, `tokenUri` | Endpoints for redirecting to request authorization and exchanging codes for tokens |
| `issuerUri`, `jwkSetUri` | Issuer and key information used to validate tokens/ID tokens per configuration |

**`ClientRegistrationRepository`** allows looking up a `ClientRegistration` by `registrationId`. In Spring Boot, `spring.security.oauth2.client.registration.*` properties are usually mapped into registrations; a common implementation is `InMemoryClientRegistrationRepository`.

This repository stores **client configurations**, not per-user access tokens.

### 2.2. `OAuth2AuthorizedClient`: Data After Authorization

An `OAuth2AuthorizedClient` essentially holds:

```
OAuth2AuthorizedClient
├── clientRegistration : ClientRegistration
├── principalName       : String
├── accessToken         : OAuth2AccessToken
└── refreshToken        : OAuth2RefreshToken?  (may be null)
```

- **`principalName`** identifies the subject for which the token was issued in the application's context. For login, this is usually the user; for `client_credentials`, the application can use a fixed technical principal name.
- **Access token** is sent to the Resource Server; it has a token type (usually Bearer), value, scopes, issued-at timestamp, and expiration timestamp.
- **Refresh token** exists only if issued by the Authorization Server. Never assume every grant provides a refresh token.
- **The OIDC ID token is not a direct property of `OAuth2AuthorizedClient`**. ID token data usually resides in `OidcUser` or the OIDC authentication context.

Think of a registration as *a service registration card*; an authorized client is *that card after it has received access permissions for a specific principal*.

### 2.3. Where Authorized Clients Are Stored and Loaded

Spring Security distinguishes two abstractions:

| Component | Typical API | Suitable For |
| --- | --- | --- |
| **`OAuth2AuthorizedClientService`** | `loadAuthorizedClient(registrationId, principalName)`; `saveAuthorizedClient(...)`; `removeAuthorizedClient(...)` | Accessing authorized client data by principal, independent of HTTP requests |
| **`OAuth2AuthorizedClientRepository`** | `loadAuthorizedClient(..., Authentication, HttpServletRequest)`; `saveAuthorizedClient(..., Authentication, HttpServletRequest, HttpServletResponse)` | Servlet/Web flows that have request, response, and session |

Example implementations:

- `InMemoryOAuth2AuthorizedClientService`: stores in memory; suitable for demos or simple cases.
- `JdbcOAuth2AuthorizedClientService`: can persist to a database via JDBC.
- `HttpSessionOAuth2AuthorizedClientRepository`: stores in the HTTP session.
- `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`: delegates to a service for authenticated principals and handles storage appropriately for unauthenticated principals.

**Key takeaway:** `ClientRegistrationRepository` answers *how is the client configured?*; `OAuth2AuthorizedClientService/Repository` answers *which token does this principal already have for this registration?*

Depending on how storage is configured, an authorized client may disappear when the session expires or the application restarts, or it may be shared across instances when an appropriate store is used. Never assume tokens are automatically synchronized across servers.

### 2.4. `OAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientProvider`

**`OAuth2AuthorizedClientManager`** is the central coordinator when the application needs a usable authorized client: finding existing state, authorizing for the first time, or re-authorizing when necessary.

A manager uses **`OAuth2AuthorizedClientProvider`** instances to handle each grant and token state. Providers are commonly assembled with `OAuth2AuthorizedClientProviderBuilder`:

| Provider | When Needed |
| --- | --- |
| `authorizationCode()` | Authorization Code flow with user interaction via browser |
| `refreshToken()` | A valid refresh token exists and a new access token is needed |
| `clientCredentials()` | Client requests an access token on its own to call APIs, with no direct user |

Two common manager implementations in **Servlet applications**:

- **`DefaultOAuth2AuthorizedClientManager`**: used with `OAuth2AuthorizedClientRepository`, suitable when `HttpServletRequest` / `HttpServletResponse` are present.
- **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**: used with `OAuth2AuthorizedClientService`, suitable for background tasks or services without an HTTP request.

When calling `manager.authorize(OAuth2AuthorizeRequest)`, the result may be an existing authorized client, a refreshed authorized client, or `null` if the provider does not support/cannot complete authorization in that context. Authorization failures can also appear as `OAuth2AuthorizationException`. Therefore, the application should not assume every `authorize()` call is guaranteed to return a new token.

### 2.5. Components Supporting Browser Flows and OIDC

In a Servlet configuration with `oauth2Login()`, the following components participate in the login process:

- **`OAuth2AuthorizationRequestRedirectFilter`**: starts the redirect flow to the Authorization Server, typically beginning at `/oauth2/authorization/{registrationId}` by default.
- **`OAuth2AuthorizationRequestResolver`**: builds the authorization request with client ID, redirect URI, scopes, `state`, and appropriate extra parameters; customizable.
- **`OAuth2LoginAuthenticationFilter`**: handles the callback containing the authorization code, by default at `/login/oauth2/code/{registrationId}`, and processes login.
- **`OidcUserService`** and OIDC authentication components: construct user details from the ID token and UserInfo when applicable.
- **`SecurityContext`**: holds the logged-in user's `Authentication`; persisted via the configured security context/session mechanism.

`oauth2Login()` handles **user login**; `oauth2Client()` and the authorized client infrastructure handle **managing permissions/tokens to call resources**. A web application can use both.

## 3. Lifecycle of an Authorized Client with Authorization Code + OIDC

Suppose a user opens a page requiring login in a Spring Boot application using the `web-oidc` registration, and the application subsequently calls another API.

```
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Spring Boot Client
    participant AS as Authorization Server / OP
    participant API as Resource Server

    U->>B: Open a page requiring authentication
    B->>C: GET /private
    C-->>B: Redirect to authorization endpoint
    B->>AS: Authorize request (scope, state, ...)
    AS->>U: Authenticate / request consent if needed
    AS-->>B: Redirect with code and state
    B->>C: GET /login/oauth2/code/web-oidc?code=...&state=...
    C->>C: Validate state / saved request
    C->>AS: Exchange authorization code for tokens
    AS-->>C: Access token, ID token, possibly refresh token
    C->>C: Validate OIDC; create Authentication
    C->>C: Save OAuth2AuthorizedClient
    C-->>B: Establish login session / return page
    C->>API: Call API with Bearer access token
    API-->>C: Authorized data
```

### Phase A — Registration Is Ready, No Authorization Yet

Once client configuration is loaded, Spring Security knows the endpoints, client ID, grant type, and scopes. However, **an authorized client does not exist merely because a registration exists**; the system does not yet have an access token bound to the user.

### Phase B — Redirecting to Request Authorization

When the login flow starts, the application builds an authorization request and redirects the browser to the Authorization Server. This typically includes:

- `client_id`, `response_type=code`, `redirect_uri`, and `scope`;
- `state` to bind the callback to the original request and prevent request forgery;
- `nonce` in OIDC to bind the ID token to the authentication session;
- **PKCE** (such as `code_challenge` / `code_verifier`) when applied to protect authorization code exchange.

The user logs in at the Authorization Server and grants consent if required by policy. The client does not directly collect the user's password in this redirect flow.

### Phase C — Callback, Code Exchange, and OIDC Validation

The Authorization Server redirects the browser back to the redirect URI with an **authorization code** and `state`. The application verifies that the callback matches a pending request, and then the **backend** calls the token endpoint to exchange the code for tokens.

If the scope includes `openid` and this is OIDC, the result typically contains an **ID token**. Spring Security validates the required ID token conditions, such as signature, issuer, audience, time validity, and nonce per context. UserInfo may be queried depending on scopes and provider configuration.

Upon success:

1. Spring Security creates an `Authentication` (in OIDC login, usually an `OAuth2AuthenticationToken` with an `OidcUser` principal).
2. It saves **`OAuth2AuthorizedClient`** containing the registration, `principalName`, access token, and refresh token if issued.
3. Authentication context and authorized client are stored via **two related but distinct mechanisms**: the security context for login state; the authorized-client repository/service for access tokens.

**Do not send an authorization code or ID token to a Resource Server as if it were an access token.** An authorization code is single-use to exchange for tokens; an ID token proves identity to the client; an access token is the authorization credential for the intended API.

### Phase D — Reloading and Using the Access Token

When the user performs an action that needs to call an API, the application looks up the authorized client by **`registrationId` and principal** in the corresponding context. Its access token is usually attached to a header:

```
GET /api/profile HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
```

The Resource Server must independently validate the token, audience/scopes, and API authorization policies. Having the Spring Boot client logged in via OIDC **does not automatically make every API accept that token**; the token must be issued for the appropriate resource.

### Phase E — Expiration, Renewal, and Re-Authorization

An access token has a limited lifetime. When a component invokes an **authorized-client manager** configured with suitable providers, the lifecycle may proceed as follows:

```
flowchart TD
    A["Need to call API"] --> B["Find saved authorized client"]
    B --> C{"Client exists and access token<br/>is still usable?"}
    C -->|Yes| D["Use current access token"]
    C -->|No| E{"Has refresh token<br/>and refresh provider?"}
    E -->|Yes| F["Request new access token"]
    F --> G["Save updated authorized client"]
    G --> D
    E -->|No| H{"Does grant / context<br/>allow requesting new token?"}
    H -->|Yes| I["Run appropriate authorization mechanism"]
    I --> G
    H -->|No| J["Require re-login / re-authorization or report error"]
```

- **Refresh token**: if issued and the `refreshToken()` provider is configured, the manager can exchange the refresh token for a new access token without redirecting the user. Rotated tokens/refresh tokens must be saved back.
- **Authorization Code**: if refreshing is impossible, the application may need the user to go through the authorization flow again in the browser; the manager cannot generate a code on its own without an interactive context.
- **Client Credentials**: the application usually requests a new access token using client credentials when the old token expires. This is not refresh-token flow behavior.
- **Revocation / logout / authorization failure**: authorized client data can be removed or become unusable. Whether logout deletes tokens, revokes tokens remotely, or ends the session at the OP depends on specific configuration; do not assume every logout does all three.

**Note:** simply reading `authorizedClient.getAccessToken()` from an already-loaded object does not guarantee the token is refreshed. Renewal logic resides in the **manager/provider or configured HTTP client integration**; if you retrieve tokens and send requests manually, you must account for when to request a fresh token.

## 4. A Different Lifecycle: `client_credentials` for Machine-to-Machine Communication

A batch job needs to call a billing API without a user opening a browser. In that case:

1. The application looks up the registration using the `client_credentials` grant.
2. It invokes `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a technical principal, e.g., `invoice-batch`.
3. The provider sends client credentials to the token endpoint.
4. The Authorization Server returns an access token; the manager stores `OAuth2AuthorizedClient` under the `(registrationId, principalName)` pair.
5. Subsequent calls can reuse the still-valid token. When the token expires, the provider can request a new token.

There are no browser redirects, user logins, or OIDC ID tokens in a normal `client_credentials` flow. The principal name here helps Spring Security key the stored token state; it **does not mean a real human user has logged in**.

| Criterion | Authorization Code + OIDC | Client Credentials |
| --- | --- | --- |
| Actual subject | Logged-in user | The application itself |
| Browser interaction | Yes, during authorization | No |
| Required components | Login/filters, OIDC, authorized client storage | Manager + provider + service |
| Typical tokens | Access token, ID token; possibly refresh token | Access token; usually no refresh token |
| Upon expiration | Can refresh or require re-authorization | Request a new access token with client credentials |
| Principal used as storage key | Authenticated user | Stable technical name chosen by the application |

## 5. Configuration and Usage Example in Spring Boot (Servlet)

The example below uses Spring Boot 3.x / Spring Security 6.x with modern DSL syntax. Endpoint names and refresh-token issuance depend on the actual Authorization Server.

### 5.1. Declaring Two Registrations

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web-oidc:
            provider: corporate
            client-id: ${WEB_OIDC_CLIENT_ID}
            client-secret: ${WEB_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email

          billing-service:
            provider: corporate
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: billing.read

        provider:
          corporate:
            issuer-uri: https://id.example.org/realms/demo
```

`issuer-uri` enables Spring Security/Boot to discover OIDC provider metadata when the provider supports discovery. For providers without suitable metadata, explicitly configure the necessary endpoints. Environment values must be supplied at runtime and **secrets must never be committed to source code**.

### 5.2. Enabling OIDC Login and OAuth2 Client Support

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

When accessing a page requiring authentication, the user can be directed to the OAuth2/OIDC login page. To initiate login directly with the `web-oidc` registration, the application can send the browser to `/oauth2/authorization/web-oidc`.

### 5.3. Retrieving the User's Authorized Client in a Controller

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/account/connection")
    String connection(
            @AuthenticationPrincipal OidcUser user,
            @RegisteredOAuth2AuthorizedClient("web-oidc")
                    OAuth2AuthorizedClient authorizedClient) {

        return "subject=" + user.getSubject()
                + ", registration="
                + authorizedClient.getClientRegistration().getRegistrationId()
                + ", accessTokenExpiresAt="
                + authorizedClient.getAccessToken().getExpiresAt();
    }
}
```

`@AuthenticationPrincipal` retrieves user information from `SecurityContext`. `@RegisteredOAuth2AuthorizedClient` retrieves the authorized client bound to the registration/principal. The snippet only displays safe metadata for illustration and **never prints token values**.

### 5.4. Manager for Background Jobs

For jobs without an HTTP request, use the service-based manager:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.*;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class ServiceClientConfig {

    @Bean("serviceClientManager")
    OAuth2AuthorizedClientManager serviceClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

The application requests a token through the manager whenever it needs to make a call; the manager has the opportunity to reuse or request a new token depending on state:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
class BillingTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    BillingTokenProvider(
            @Qualifier("serviceClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String currentAccessToken() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
            .withClientRegistrationId("billing-service")
            .principal("invoice-batch")
            .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException(
                "Cannot authorize billing-service");
        }
        return client.getAccessToken().getTokenValue();
    }
}
```

In a real application, attach the manager to `RestClient` or `WebClient` via appropriate OAuth2 integration to manage Bearer headers and token lifecycles consistently. If writing manual HTTP requests, API-calling code must handle 401/403 errors properly; **do not assume every HTTP 401 means refresh and retry infinitely**.

## 6. State Milestones and Storage

To troubleshoot a "token not found" issue, trace this table:

| Milestone | Registration Config | Authorized Client | SecurityContext |
| --- | --- | --- | --- |
| Application just started | Present if config is valid | Not necessarily present | No user login yet |
| User starts authorization | Present | May not exist yet | Currently in authentication step |
| Authorization Code + OIDC succeeds | Unchanged | Created/saved | Has user's `Authentication` |
| Next request from same principal | Unchanged | Can be reloaded | Restored via session mechanism |
| Access token expires | Unchanged | May exist but token is expired | User may still be logged in |
| Refresh or new token request succeeds | Unchanged | Updated with new token | May remain unchanged |
| Remove authorized client / clear session | Unchanged | May no longer be loadable | Depends on logout/session action |

Remember two operational rules:

1. **The authorized client lookup key includes the principal context.** The same `registrationId` with different principals can be two independent token records. For background jobs, choose a consistent technical principal to avoid creating unnecessary multiple records.
2. **Sessions and tokens have separate lifecycles.** A login session can remain active while the access token has expired. Conversely, a token stored in a persistent service can still exist even after the browser session ends; revocation and cleanup must follow application policy.

## 7. Common Pitfalls and How to Diagnose Them

| Symptom | What to Check |
| --- | --- |
| `ClientRegistration` exists but cannot retrieve authorized client | Has the user/client completed authorization? Are the `registrationId` and principal used for lookup correct? |
| Callback returns error after login | Does `redirect_uri` match the registration at the Authorization Server? Are `state`, saved request session, PKCE, and authorization code valid? |
| OIDC login fails when validating ID token | Are `issuer-uri`, signature/JWKS, audience/client ID, time validity, and clock skew correct? |
| First API call succeeds, subsequent call returns 401 | Did the access token expire/get revoked? Does the manager have the right provider? Did the client send the new token? Does the token have the right audience? |
| No refresh token present | Does the server/grant/scope/policy issue refresh tokens? The client cannot generate refresh tokens itself. |
| Batch job reports missing request/response | Are you using a Servlet-request-bound manager outside a request? Consider `AuthorizedClientServiceOAuth2AuthorizedClientManager`. |
| Running multiple instances, token intermittently disappears | Is authorized-client storage shared across instances? Are session routing/persistence consistent? |
| API returns 403 | Does the token have the right scope/authority and resource permissions? 403 differs from unauthenticated 401. |

### Security Principles to Maintain

- Use HTTPS for redirects, token endpoints, and API calls; register exact redirect URIs.
- Protect client secrets and refresh tokens with a secret manager/appropriate store; never write them to logs or responses.
- Request only necessary scopes. Across different APIs, verify tokens have the proper audience and permissions; do not reuse tokens indiscriminately.
- Keep `state` checks, OIDC nonce, and PKCE when applicable; never bypass ID token validation.
- When storing tokens long-term, consider encryption, retention period, revocation capability, application access controls, and cleanup mechanisms.
- Never send an ID token instead of an access token; never treat a merely decoded JWT as already validated.

## 8. Self-Check Understanding

**Scenario 1.** An application has a `web-oidc` registration and a user has never logged in. Does an `OAuth2AuthorizedClient` for that user exist yet?

> Cannot assume it exists. A registration is only configuration; an authorized client is only formed once an authorized state/token has been obtained.

**Scenario 2.** A user has logged in with OIDC, but an API call using the access token fails with 401 due to token expiration. Must the user log in again?

> Not necessarily. If a valid refresh token exists and the manager/provider is configured to refresh, the application can obtain a new token. If refreshing is not possible, re-running the authorization flow may be necessary.

**Scenario 3.** A sessionless job needs to call an API using `client_credentials`. Which manager should be chosen?

> `AuthorizedClientServiceOAuth2AuthorizedClientManager` with the `clientCredentials()` provider and a stable technical principal.

**Scenario 4.** Why not use an ID token to call an API?

> An ID token is for the client to verify user identity; a Resource Server normally requires an access token issued with the appropriate permissions and target audience.

---

**Remember the main flow:** `ClientRegistration` describes the configuration → authorization/token endpoints issue tokens → `OAuth2AuthorizedClient` holds token state per principal → repository/service stores and loads → manager/provider coordinates reuse, renewal, or requesting new tokens → HTTP client sends the access token to the API.
