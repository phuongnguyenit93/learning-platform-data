# 15.10. Distinguishing Initial Authorization, Token Reuse, and Token Reissuance

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, an application often calls `OAuth2AuthorizedClientManager.authorize(...)` before sending a request to an API. The method name is easily misunderstood: **calling `authorize` does not automatically mean requesting a new access token**, nor does it mean forcing the user to log in again.

Depending on the authorized client's state and the configured `OAuth2AuthorizedClientProvider` instances, the manager can take one of three paths:

1. **Initial authorization:** no authorized client exists yet for the registration/principal; the client must be authorized and obtain tokens via the appropriate grant.
2. **Token reuse:** an authorized client already exists and does not need reauthorization; the manager can return the existing object without calling the token endpoint.
3. **Token reissuance:** the old access token is no longer usable or is about to expire; the manager attempts a supported reauthorization mechanism, such as refresh token or client credentials.

These three possibilities look identical at the application's call site, yet differ in **preconditions**, **grant**, **user interaction**, **storage**, and **error handling**.

After this lesson, you will be able to:

- Explain how `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientProvider`, and `OAuth2AuthorizedClientManager` collaborate.
- Distinguish initial authorization via `authorization_code` vs. `client_credentials`.
- Understand why calling `authorize(...)` can reuse an already-saved access token.
- Describe the refresh token grant and requesting a new token via client credentials.
- Distinguish refreshing/reissuing an access token from **OIDC Login**, reauthentication, and step-up authentication.
- Configure managers for Servlet applications and for work without an HTTP request.
- Interpret `authorize()` results, handling `null`, exceptions, `invalid_grant`, and API errors.
- Recognize risks around token rotation, concurrent requests, wrong principals, wrong audiences, and inconsistent stores.

## 1. One Problem, Three Processing Branches

Suppose **Employee Portal** is a Spring Boot application allowing employees to log in via OIDC through the company's OpenID Provider (OP). After login, the Portal uses an access token to call the **Orders API**.

At some point, the Portal needs a token for a request:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ACCESS_TOKEN>
~~~

To obtain the token, the application calls the manager with the client registration and current principal.

| Illustrative Time | State in Authorized Client Store | Expected Outcome |
|---|---|---|
| 09:00 | No token yet for Alice | Initial Authorization Code flow and save token |
| 09:02 | Access token A1 is still usable | Reuse A1 |
| 09:05 | A1 is still valid | Continue using A1 |
| 09:10 | A1 expired/near expiry; refresh token R1 exists | Request A2 via refresh token |
| 09:12 | A2 has been saved | Reuse A2 |
| 10:00 | Refresh token has been revoked | Cannot refresh; handle error or initiate a new flow |

The times above are illustrative only, not default token TTLs.

**The exact same `authorize()` call can lead to different behaviors at different times.** Without understanding this, applications easily fall into token-request loops or misunderstand why no fresh OIDC login occurred.

## 2. High-Level Diagram

~~~mermaid
flowchart TD
    A["Application needs token"] --> B["OAuth2AuthorizedClientManager.authorize"]
    B --> C["Load authorized client state"]
    C --> D{"Authorized client already exists?"}
    D -->|No| E["Provider matches initial grant?"]
    E -->|client_credentials| F["Request access token from AS"]
    E -->|authorization_code| G["Interactive authorization flow required"]
    E -->|Cannot| H["No authorized client"]
    D -->|Yes| I{"Does provider need and support reauthorization?"}
    I -->|No| J["Reuse saved authorized client"]
    I -->|refresh_token| K["Refresh access token at AS"]
    I -->|client_credentials| L["Request new token via client credentials"]
    K --> M{"AS accepts?"}
    L --> M
    M -->|Yes| N["Save updated authorized client"]
    M -->|No| O["Failure handling per policy"]
    F --> P["Save initial authorized client"]
    G --> P
    P --> Q["Use access token for target API"]
    J --> Q
    N --> Q
~~~

The diagram depicts conceptual branches. **Authorization Code browser redirects/callbacks do not occur wholly inside a synchronous manager call.** Interactive steps are supported by Spring Security web filters and the authorization request repository.

## 3. From Configuration to Authorized State

### 3.1. `ClientRegistration`

`ClientRegistration` describes a client registered with the Authorization Server (AS):

~~~text
registrationId: corporate
clientId: employee-portal
authorizationGrantType: authorization_code
redirectUri: https://portal.example.com/login/oauth2/code/corporate
scope: openid profile orders.read
provider: company-oidc
~~~

It knows the grant, endpoints, and client metadata. **It does not hold Alice's access token.**

### 3.2. `OAuth2AuthorizedClient`

After successful authorization, Spring Security can store:

~~~text
OAuth2AuthorizedClient
├── clientRegistration: corporate
├── principalName: Alice
├── accessToken: A1
│   ├── issuedAt: ...
│   └── expiresAt: ...
└── refreshToken: R1 (if issued)
~~~

The authorized client is located by the storage model matching the registration/principal or session. One registration can have many authorized clients for different principals.

### 3.3. `OAuth2AuthorizedClientRepository` and `Service`

Both abstractions manage authorized clients, yet differ in context:

| Abstraction | Access Context | Example |
|---|---|---|
| `OAuth2AuthorizedClientRepository` | HTTP Servlet request/response and `Authentication` | `HttpSessionOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientService` | Registration ID and principal name, without needing a Servlet request | `InMemoryOAuth2AuthorizedClientService` or a database-backed service |

The repository storing pending Authorization Requests awaiting callback is a **different abstraction**:

~~~text
OAuth2AuthorizationRequestRepository
    -> state / nonce / PKCE / callback correlation

OAuth2AuthorizedClientRepository
    -> access token / refresh token after authorization
~~~

Do not swap the two stores just because the class names look similar.

### 3.4. `OAuth2AuthorizedClientProvider`

Providers know how to execute grants when preconditions are met. Spring Security provides builder configuration:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();
~~~

A `DelegatingOAuth2AuthorizedClientProvider` can try providers in order. **Each provider performs only the work appropriate for the current registration and authorization context.**

### 3.5. `OAuth2AuthorizedClientManager`

The manager is responsible for coordinating:

1. Identifying registration and principal.
2. Looking up a saved authorized client.
3. Building `OAuth2AuthorizationContext`.
4. Letting the provider chain attempt authorization/reauthorization.
5. Using success/failure handlers to save/remove as needed.
6. Returning the corresponding authorized client, or no result if authorization cannot proceed.

That is why `authorize()` does not simply mean “call the token endpoint”.

## 4. Scenario A: Initial Authorization

### 4.1. Input State

~~~text
Client registration: corporate
Principal: Alice
Authorized client: none yet
~~~

The manager must determine which provider can create the initial authorization. The **grant type** dictates the approach.

### 4.2. Initial Authorization with Authorization Code and OIDC Login

A typical `authorization_code` flow includes:

1. Browser accesses a Portal page requiring authentication.
2. Spring Security creates an Authorization Request, `state`, and PKCE/nonce data where applicable.
3. Browser is redirected to the OP.
4. OP authenticates/obtains consent per policy.
5. Browser returns to callback with `code` and `state`.
6. Client verifies correlation and exchanges `code` for tokens.
7. Spring Security validates the ID token if it is an OIDC Login.
8. `OAuth2AuthorizedClient` is created and persisted for subsequent use.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant RP as Spring Security Portal
    participant OP as OpenID Provider
    participant Repo as Authorized Client Repository
    U->>B: Open /orders
    B->>RP: Unauthenticated request
    RP-->>B: Redirect to OP
    B->>OP: Authorization Request
    OP->>U: Login/consent if needed
    OP-->>B: Redirect code and state
    B->>RP: Callback
    RP->>OP: Token request
    OP-->>RP: ID token + access token
    Note over RP: Create Authentication/OidcUser
    RP->>Repo: Save OAuth2AuthorizedClient
    RP-->>B: Redirect back to app
~~~

**Key point:** never expect a background job calling `manager.authorize(...)` to open a browser and execute the entire redirect/callback flow. Authorization Code is an interactive flow requiring the corresponding web components.

### 4.3. “Initial Authorization” Is Not Necessarily “First OP Login”

Alice might already have a Single Sign-On session at the OP. When the Portal requests authorization for the first time, the OP may return a code without asking Alice to re-enter her password.

Distinguish:

- Portal has never had an authorized client for Alice.
- Browser already has an SSO session at the OP.
- Portal creates a new `Authentication`/session.
- OP requires re-authentication due to policy.

These four states do not necessarily coincide.

### 4.4. Initial Authorization with Client Credentials

A service using `client_credentials` needs no End-User:

~~~text
Client: reporting-service
Technical principal: reporting-job
Authorized client: none yet

Manager -> clientCredentials provider
Provider -> token endpoint
AS -> access token S1
Manager -> save authorized client S1
~~~

This grant authenticates the **client/service**, not an OIDC-logged-in human user.

### 4.5. Manager Lacks a Matching Grant Provider

For instance, registration `corporate` uses `authorization_code` while the manager only configures:

~~~java
OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();
~~~

Do not expect this provider to obtain a token for `corporate`. Likewise, a chain with only `refreshToken()` cannot create an initial token when no refresh token exists yet.

**Grant type and provider must match; you cannot get a token by “trying any grant”.**

## 5. Scenario B: Reusing an Existing Token

### 5.1. Authorized Client Exists

Example:

~~~text
corporate / Alice:
  access token A1
  expiresAt 10:30
  refresh token R1
~~~

At 10:05, another request wants to call the Orders API. The provider chain sees **no need to reauthorize**, and the manager returns the existing authorized client.

~~~text
manager.authorize(request)
  -> repository.loadAuthorizedClient(...)
  -> finds A1/R1
  -> provider executes no new grant
  -> returns existing authorized client
~~~

No token endpoint call and no new OIDC callback occur.

### 5.2. Benefits of Reuse

- Fewer requests to the AS.
- Lower API call latency.
- Avoids repeatedly redirecting the browser.
- Fewer access tokens issued.
- Minimizes unnecessary consent or login prompts.

### 5.3. Reuse Does Not Guarantee the API Will Accept the Token

An access token still valid per `expiresAt` can still be:

- Revoked by the AS/RS.
- Issued with an audience for a different API.
- Missing required scopes.
- Tied to the wrong tenant/user.
- Issued with an issuer or token profile rejected by the API.

**The manager primarily manages client authorization state.** The Resource Server must still validate the access token and business permissions.

### 5.4. Clock Skew

Token-refreshing providers normally evaluate `expiresAt` with an allowed clock skew window. A token close to expiry may be treated as needing renewal ahead of its literal `exp` timestamp so it does not expire mid-API processing.

Do not assume refresh happens only at the exact expiration second. The skew window and conditions depend on implementation/configuration.

### 5.5. What If the API Returns 401 Even Though the Token Has Not Expired?

The manager does not automatically observe every API HTTP response. An API 401 may stem from a wrong audience or a revoked token, not necessarily expiration.

Integrate an HTTP client and authorization failure handling appropriately, distinguishing reauthorizable errors from configuration/policy errors. **Never infinitely retry the exact same token that the API just rejected.**

## 6. Scenario C: Reissuing a Token

“Reissuing” can involve multiple mechanisms. There is no single OAuth grant generically named “reauthorize”.

| Mechanism | Precondition | Needs Browser? |
|---|---|---|
| `refresh_token` | Refresh token accepted by the AS | Usually no |
| Requesting a new token via `client_credentials` | Client permitted to use the grant | No |
| New Authorization Code flow | Fresh authorization required, client supports interaction | Has redirect/callback |
| Token exchange / delegation | Supported by AS and client allowed to exchange | Depends on mechanism |

### 6.1. Refresh Token Grant

If access token A1 is expired/expiring and refresh token R1 exists:

~~~text
Authorized client:
  accessToken = A1 (expired)
  refreshToken = R1 (still valid)
~~~

the `refreshToken()` provider can send a token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R1
~~~

This is an illustrative request and does not show actual client authentication. A confidential client may have to use `client_secret_basic`, `private_key_jwt`, mTLS, or another method per its registration. Never print real tokens in logs.

The AS may return:

~~~json
{
  "access_token": "ACCESS_TOKEN_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_TOKEN_R2"
}
~~~

The new tokens are placeholder values. The AS may issue a new refresh token under rotation or keep the old refresh token per policy.

Upon success, the manager/success handler saves the updated authorized client so subsequent requests use A2.

### 6.2. Refresh Is Not an OIDC Re-Login

The refresh token grant **does not prove the user just re-authenticated**. Issuing access token A2 just now does not mean Alice just entered her password or completed MFA.

When business logic requires a fresh authentication event, you may need a new OIDC Authorization Request with `max_age`, `prompt=login`, or `acr_values`, and then verify `auth_time`/`acr` in the ID token per policy.

**Never use access token issuance time to infer the freshness of user authentication.**

### 6.3. Refresh Does Not Automatically Escalate Permissions

Suppose the prior token only carried scope `orders.read`. A refresh does not automatically let the Portal upgrade to `orders.approve`.

Gaining new permissions may require the client to be granted the scope, fresh consent/authorization, or token exchange supported by the AS. Never manually alter scope claims or authorities to escalate privileges.

### 6.4. Client Credentials Issuing a New Access Token

For a background service:

~~~text
Access token S1 expired
Refresh token: typically not issued
Grant: client_credentials

Manager -> clientCredentials provider
AS -> access token S2
Manager -> saves S2
~~~

This is a fresh `client_credentials` token request, **not a refresh token grant**. It does not involve an OIDC user.

### 6.5. No Refresh Token and Unable to Reissue Automatically

An Authorization Code client may not receive a refresh token. When the access token expires:

- The refresh provider cannot be used without a refresh token.
- A new Authorization Code flow may have to be started.
- The OP may leverage an active SSO session to finish quickly without prompting for a password.
- If running in a background job, you cannot open a browser on the user's behalf.

Without a valid reauthorization mechanism, the manager cannot “invent an access token”. Never substitute an ID token as an API bearer token.

## 7. Return Results from `authorize()`

### 7.1. New Authorized Client

The provider issued an initial token or reauthorized and produced a new/updated object. The manager can use the success handler to persist state.

### 7.2. Already-Saved Authorized Client

The provider executed no new grant and the manager returned the existing object. This is normal token reuse, not an error.

### 7.3. No Result (`null`)

The manager may return `null` when no authorized client exists and no provider can handle the context. The application must determine whether interactive authorization, another grant, or error handling is needed.

Never proceed to call an API with an empty token or a substitute ID token.

### 7.4. Exception When Token Endpoint Fails

Typical errors:

| Error | Possible Cause | Handling |
|---|---|---|
| `invalid_grant` | Refresh token expired, revoked, reused, or invalid | Stop old retries, cleanup / fresh authorization |
| `invalid_client` | Wrong secret / client authentication | Check client registration |
| Timeout | Network or AS returned no response | Controlled retry, evaluate idempotency |
| No matching provider | Grant not supported by the chain | Fix configuration |
| API 401 | RS rejects token | Check audience, issuer, revocation, expiry |
| API 403 | Insufficient scope/authority or permission | Do not treat as a default refresh trigger |

Token endpoint errors differ from Resource Server HTTP errors. Diagnose at the exact right layer.

## 8. Spring Boot Configuration: OIDC Web and Service Client

### 8.1. Maven Dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 8.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

Here:

- `corporate` is the registration for user OIDC Login.
- `reporting-service` is a client using `client_credentials` for background tasks.
- Scopes `orders.read` and `reports.read` are illustrative examples and must be supported by the AS and APIs.
- Client secrets are loaded from environment/secret manager, never committed to source code.

## 9. Manager for Servlet Requests

### 9.1. `DefaultOAuth2AuthorizedClientManager`

Class:

~~~java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
~~~

It uses `ClientRegistrationRepository` and `OAuth2AuthorizedClientRepository`. It suits Servlet requests because the repository may need `HttpServletRequest` and `HttpServletResponse`.

Example configuration:

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
public class ServletAuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The provider chain covers capabilities matching the grants, yet **does not turn authorization code into a browserless flow**.

### 9.2. Security Filter Chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
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

`oauth2Login()` provides browser login/callback; `oauth2Client()` supports client authorization during requests needing tokens.

If the application defines custom repository/manager beans, ensure where **tokens are saved at login** matches where **tokens are read when calling APIs**.

### 9.3. Calling the Manager in a Servlet Controller

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class TokenStatusController {

    private final OAuth2AuthorizedClientManager manager;

    TokenStatusController(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/token-status")
    String status(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        OAuth2AuthorizeRequest authorizeRequest =
                OAuth2AuthorizeRequest.withClientRegistrationId("corporate")
                        .principal(authentication)
                        .attribute(HttpServletRequest.class.getName(), request)
                        .attribute(HttpServletResponse.class.getName(), response)
                        .build();

        OAuth2AuthorizedClient client =
                manager.authorize(authorizeRequest);

        if (client == null || client.getAccessToken() == null) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "No authorized client available");
        }

        return "registrationId="
                + client.getClientRegistration().getRegistrationId();
    }
}
~~~

The controller illustrates attaching `Authentication` and Servlet request/response to the authorize request. It only returns the registration ID, **never the access token string**.

The example assumes the user has completed OIDC Login. If no authorized client exists for `corporate`, an interactive flow must run, e.g., starting at:

~~~text
/oauth2/authorization/corporate
~~~

Never treat an arbitrary manager call as a substitute for the entire redirect/callback flow.

## 10. Manager for Background Jobs

### 10.1. `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Background jobs or scheduled tasks normally have no Servlet request/session.

For that, Spring Security provides:

~~~java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

It uses `ClientRegistrationRepository` and `OAuth2AuthorizedClientService`, suited to saving/reading tokens by service principal.

### 10.2. Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundTokenConfig {

    @Bean("backgroundClientManager")
    OAuth2AuthorizedClientManager backgroundClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, service);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### 10.3. Using the Manager to Obtain a Token

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class ReportingTokenService {

    private final OAuth2AuthorizedClientManager manager;

    ReportingTokenService(
            @Qualifier("backgroundClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String accessToken() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("reporting-service")
                        .principal("reporting-job")
                        .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException(
                    "Could not authorize reporting-service");
        }

        return client.getAccessToken().getTokenValue();
    }
}
~~~

`reporting-job` is a **technical principal name** for managing the service's token, not an OIDC-logged-in End-User.

In real applications, never log access tokens or return tokens via frontend endpoints; use an HTTP client properly configured for the target domain and scopes.

## 11. Selecting the Right Manager for the Environment

| Criterion | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
|---|---|---|
| Primary context | Servlet request | Background/service outside Servlet requests |
| Store | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| May need HTTP request/response | Yes | No |
| Principal | `Authentication` in request context | Supplied principal name |
| Typically used with browser OIDC Login | Yes | Does not handle browser login itself |
| Typically used with client credentials jobs | Can be used inside requests | Better fit |
| Refresh token | Depends on provider/authorized client | Depends on provider/authorized client |
| Opens browser automatically in background | No | No |

With **Reactive WebFlux**, Spring Security uses corresponding reactive abstractions such as `ReactiveOAuth2AuthorizedClientManager`; do not confuse Servlet managers with reactive services.

## 12. Token Expiration and Clock Skew

### 12.1. Key Timestamps

An access token can have:

~~~java
client.getAccessToken().getIssuedAt();
client.getAccessToken().getExpiresAt();
~~~

A token with `expiresAt=10:30` may be rejected if the API receives the request at 10:30:01. Thus providers can factor in a clock skew window and treat a token **nearing expiration** as requiring refresh/reissuance.

Do not hardcode a rule like “only refresh when `now >= exp`” and bypass the provider's policy.

### 12.2. A Non-Expired Token Can Still Be Unusable

Beyond time, the API also checks:

- Trusted issuer.
- Matching audience/resource.
- Accepted token type/profile.
- Scopes/authorities.
- Permissions on the specific resource.
- Token status if revocation/introspection mechanisms exist.

`authorize()` returning an authorized client does not mean the API will accept every request.

### 12.3. `HttpSession` and Tokens Have Different Lifecycles

Example:

~~~text
Portal HttpSession idle timeout: 30 minutes
Access token TTL:              10 minutes
Refresh token lifetime:        governed by AS
OP SSO session lifetime:       governed by OP
~~~

An active session does not guarantee the token is still valid. A valid token does not guarantee the user still has a Portal session. The OP SSO session may remain alive even after Portal logout.

## 13. Refresh Token Rotation and Concurrent Requests

### 13.1. Two Requests Refreshing Together

Suppose the authorized client currently holds A1/R1, and R1 is rotated upon use.

~~~text
Request A loads A1/R1
Request B loads A1/R1
Request A refreshes R1 -> receives A2/R2
Request B refreshes R1 -> invalid_grant or reuse detection
~~~

Depending on the AS, reusing R1 may simply be rejected or may trigger broader revocation policies.

Do not assume `OAuth2AuthorizedClientManager` and the repository always guarantee atomic refresh across threads/instances.

### 13.2. Synchronization Decisions Required

Under high load, you may need:

- Synchronization keyed by registration and principal/service.
- Single-flight or appropriate locking during refresh.
- Conditional token updates to avoid overwriting the new record with stale data.
- An authorized client store properly shared across instances.
- Appropriate failure handling when tokens are rotated/revoked.
- Error monitoring without logging raw refresh tokens.

This is token lifecycle design, not just toggling a flag.

### 13.3. Same Principal Across Multiple Scheduled Jobs

Two jobs using `principal("reporting-job")` and the same registration can share a token in the service store. That can be an intentional design choice.

However, if each job needs a different audience/scope, do not reuse the same registration/token across every API. Create separate registrations/policies when needed.

## 14. Authorization Success/Failure Handlers

### 14.1. Saving After Token Issuance

When a provider returns a new/updated authorized client, the manager can call the success handler to save the result in the repository/service.

If customizing the manager, ensure the save location is **consistent** with where controllers/HTTP clients read. Otherwise, the new token may exist only in the current request while the next request reads the old token.

### 14.2. `invalid_grant` During Refresh

A refresh token may expire, be revoked, or already be rotated. When the AS returns `invalid_grant`, the application must not keep retrying the same stale refresh token endlessly.

Common Spring Security managers/handlers include logic to delete the authorized client on applicable OAuth errors such as `invalid_grant`; exact behavior depends on how the manager and handlers are configured.

From a design standpoint, handle:

1. Stopping use of the rejected refresh token.
2. Deleting/updating the local authorized client for the exact principal/registration.
3. Initiating a fresh authorization for the user or returning an error for the service if needed.
4. Preventing infinite refresh loops.

Deleting the local authorized client **does not revoke the token at the AS**.

### 14.3. Network Errors Differ from Grant Rejections

If the token endpoint times out, you cannot automatically conclude the credentials are invalid. Handle retries/backoff according to grant semantics, avoiding infinite loops or inconsistent state.

If the client secret is wrong, retrying with the same secret will not fix it. Fix client authentication configuration.

### 14.4. API 401/403 Does Not Automatically Mean Token Refresh

An API can return:

| HTTP | Common Situation | Handling Meaning |
|---|---|---|
| 401 | Invalid token, wrong issuer/audience, expired, revoked | Investigate authentication/token validity |
| 403 | Valid token yet insufficient permissions | Investigate scopes/authorities/ownership |

Never assume “on every 401/403, immediately refresh”. A 403 due to insufficient permissions cannot be fixed by requesting an access token with the exact same scopes.

## 15. OAuth2-Aware HTTP Clients and API Errors

Spring Security provides OAuth2 integrations for HTTP clients like `RestClient` and `WebClient` in supported versions. Typically, an integration can:

- Look up authorized clients by registration and principal.
- Use the manager to authorize/reauthorize when needed.
- Attach the access token to the Bearer header.
- Pair with a failure handler to process certain authorization errors.

You do not necessarily need to call `authorize()` manually in every controller. For large systems, centralize token management at the HTTP client/service layer.

When the HTTP client receives 401, determine whether the token can legitimately be reissued. If the root cause is a wrong audience or the API rejecting the issuer, requesting a new token with the same broken configuration will not fix it.

Specifically avoid retrying business requests with side effects, such as `POST /payments`, without an appropriate idempotency mechanism.

## 16. Reauthorization Differs from Reauthentication and Step-Up

### 16.1. A New Access Token Does Not Prove Recent User Authentication

The refresh token grant can issue A2 after A1, yet does not make the OP re-authenticate Alice. Distinguish:

~~~text
Issuing a new access token
    !=
Re-authenticating the End-User
    !=
Higher authentication assurance
~~~

### 16.2. When Business Logic Requires a Fresher Login

OIDC provides parameters:

- `prompt=login`: asks the OP to re-authenticate.
- `max_age`: caps authentication age, requiring evaluation of `auth_time` in the ID token per OIDC rules.
- `acr_values`: specifies the desired authentication context class per OP policy.

These belong to the **Authentication Request**. They are not added to a refresh token grant to turn a refresh into an MFA event.

### 16.3. Step-Up Authentication

If an employee may view the Orders API yet must strongly authenticate when approving large amounts:

1. Backend checks current `Authentication` and assurance policy.
2. If insufficient, initiates a new OIDC Authentication Request.
3. OP authenticates per policy and returns results.
4. RP validates ID token, `acr`, and `auth_time` as required by policy.
5. Backend verifies exact user and transaction permissions.
6. Only then executes the approval.

Never use the issuance timestamp of a refreshed access token as evidence that the user just completed MFA.

## 17. Which Principal Does the Token Belong To?

### 17.1. Never Store Tokens Globally by Registration ID

One registration `corporate` can be used by both Alice and Bob. If a token is stored in a static variable keyed only by registration:

~~~java
public static String lastAccessToken;
~~~

Bob could accidentally use Alice's token.

Use a repository/service bound to the exact principal/session and registration. When switching accounts within the same `HttpSession`, clean up the previous user's tokens if storing per session.

### 17.2. Multiple Issuers and Tenants

OIDC `sub` is meaningful only within an issuer's scope. If two OPs both issue `sub=12345`, do not assume they are the same person.

When constructing identity keys for token stores, tie them to **`iss` + `sub`** or a properly mapped and managed internal user ID.

### 17.3. Registration ID Is Not the API Audience

`registrationId=corporate` is a Spring Security internal key, and does not guarantee the received token has `aud=orders-api`. The API must validate the proper audience and permissions.

If an access token is used for the wrong Resource Server, the manager cannot fix the audience itself. Scopes/resource indicators or an AS-supported token exchange mechanism may be needed.

## 18. Reuse After Logout and Token Revocation

### 18.1. Portal Logout

Local logout normally clears `SecurityContext` and may invalidate `HttpSession`. If the authorized client lives in the session, local tokens disappear with the session.

However, authorized clients stored in `OAuth2AuthorizedClientService` can outlive the session without dedicated cleanup.

### 18.2. Token Revocation

Deleting a token from the repository **differs from** revoking the token at the AS. An already-issued access token may still be accepted by the Resource Server until it expires or is revoked via AS/RS mechanisms.

### 18.3. OP SSO Session

Portal logout does not necessarily terminate the SSO session at the OP. When the user reopens the Portal, a fresh OIDC Authorization Code flow may complete quickly thanks to SSO, yet it is still a **new authorization flow**, not reusing an old code.

## 19. Multi-Instance Environments

Suppose two Portal instances share an authorized client service or session store:

~~~text
Browser / Jobs
      |
Load balancer
  |------- Portal A
  |------- Portal B
~~~

If A and B hold separate in-memory token stores, a request hitting B will not see the authorized client saved by A. This easily causes repeated token requests or unauthorized errors.

Decide explicitly:

- Are tokens stored by `HttpSession` or service principal?
- Is the store shared across instances?
- How is refresh token rotation coordinated?
- Are authorized clients lost on redeployment?
- Are tokens cleaned up properly when switching accounts/tenants?
- Is there a notification or cleanup mechanism when tokens are revoked?

Never move tokens into a static global cache just so “multiple nodes can reach them easily”.

## 20. Mental Checklist When Reading an `authorize()` Call

When encountering:

~~~java
OAuth2AuthorizedClient client = manager.authorize(request);
~~~

answer in order:

1. **What is the Registration ID?**
2. **What is the Grant type?** `authorization_code` or `client_credentials`?
3. **Who is the Principal?** OIDC user or service principal?
4. **Does the Manager belong to Servlet or service/background?**
5. **Which Repository/service stores it?**
6. **Is there an already-saved authorized client?**
7. **Is the access token expired or nearing expiry per the provider?**
8. **Is there a valid refresh token?**
9. **Does the provider chain support the matching grant?**
10. **If the provider does not issue a new token, what will the manager return?**
11. **If the token endpoint rejects, how does the failure handler respond?**
12. **Does the target API accept the issuer, audience, scopes, and permissions?**

This sequence distinguishes **initial authorization**, **reuse**, and **token reissuance** without guessing from the method name.

## 21. Illustrative Scenarios

### Scenario A — First-Time Login

Alice has no session or authorized client at the Portal yet. The browser starts the OIDC Authorization Code flow. After a valid callback, Spring Security creates `Authentication` and saves the authorized client. Subsequent requests can use the issued token.

### Scenario B — Opening the Orders Page Consecutively

Alice already has a non-expired A1. Two visits to `/orders` can reuse the same A1. The manager does not necessarily call the token endpoint.

### Scenario C — Access Token Expired, Refresh Token Available

A1 expired while R1 remains valid. The `refreshToken()` provider can use R1 to obtain A2 and save the updated authorized client. No browser redirect is needed if refresh succeeds.

### Scenario D — No Refresh Token

A1 expired, the registration uses `authorization_code`, yet the AS issued no refresh token. A new Authorization Code flow may need to start. The OP may leverage SSO, though the manager cannot turn a background job into a browser.

### Scenario E — Service Token Expired

`reporting-service` uses `client_credentials`; S1 expired. The appropriate manager requests S2 via a new grant, with no End-User or ID token involved.

### Scenario F — Refresh Token Rejected

R1 was rotated/revoked and the token endpoint returns `invalid_grant`. The application must not retry R1 infinitely, and must handle cleanup/fresh authorization.

### Scenario G — API Returns 403

The token is still valid yet lacks `orders.approve`. Do not refresh hoping the permission magically appears; permissions must be granted by the AS/RS/application per policy.

### Scenario H — Two Requests Refreshing Simultaneously

Two requests both see A1/R1 expired. One receives A2/R2 while the other hits reuse. Review concurrency and refresh token rotation rather than blaming the Authorization Code flow.

## 22. Self-Check Questions

**Question 1.** Does every call to `authorize()` necessarily create a new access token?

**Answer:** No. The manager can return the saved authorized client when the provider does not need/cannot reauthorize.

**Question 2.** Can `refreshToken()` be used to obtain an initial token when no refresh token exists yet?

**Answer:** No. The refresh token grant requires a refresh token already issued by a prior authorization.

**Question 3.** Can `authorization_code` complete entirely in a background job without a browser?

**Answer:** Not in the standard interactive web flow. It requires an Authorization Request, redirect/callback, and matching protocol mechanisms.

**Question 4.** When `client_credentials` requests a new token after expiry, is that a refresh token grant?

**Answer:** No. The client executes a fresh `client_credentials` grant under the client's own identity.

**Question 5.** Does a freshly refreshed access token prove the user just completed MFA?

**Answer:** No. Authentication freshness/assurance must be evaluated via an OIDC Authentication Request and matching claims.

**Question 6.** The API returns 401 yet the access token is not expired; does the manager fix it automatically?

**Answer:** Not by default. Investigate the cause and configure HTTP client / failure handling if appropriate reauthorization is desired.

**Question 7.** The API returns 403 due to missing scope; does refreshing automatically expand scopes?

**Answer:** No. Authorization and permissions must be granted per AS/RS policy, never escalated via refresh.

**Question 8.** Which manager should be used for a scheduled job?

**Answer:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` is usually better suited because it does not depend on an HTTP Servlet request.

**Question 9.** Why must authorized clients be bound to a principal?

**Answer:** To avoid using Alice's token for Bob or mixing tokens across issuers/tenants.

**Question 10.** How should `invalid_grant` during refresh be handled?

**Answer:** Do not retry the old refresh token infinitely; evaluate cleanup and a fresh authorization flow per policy.

**Question 11.** Does the manager returning a token prove the token has the right audience for the Orders API?

**Answer:** No. The API must validate the token's audience, scopes, issuer, and permissions.

**Question 12.** Does deleting an authorized client in the local store revoke the token at the AS?

**Answer:** No. Local cleanup and token revocation are two separate mechanisms.

## Summary

- **`OAuth2AuthorizedClientManager.authorize(...)` is an orchestration API**, not a command to “always request a new access token”.
- **Initial authorization** depends on the grant: `authorization_code` needs an interactive flow; `client_credentials` can run on the backend.
- **Token reuse** typically makes no call to the AS; the token comes from the configured repository/service.
- **Token reissuance** can occur via refresh token, a new client credentials request, or a new Authorization Code flow. These mechanisms are not interchangeable.
- **A new access token does not mean the user was re-authenticated.** For step-up or freshness, an OIDC flow and claim checks are required.
- **Provider chain, manager, and repository/service must align** on grant, registration, principal, and execution context.
- **Refresh rotation, concurrent requests, API 401/403 responses, and account switching** need explicit policies; never retry infinitely or borrow another principal's token.
- **The Resource Server must verify tokens and permissions**, even if the client-side manager found an authorized client.
