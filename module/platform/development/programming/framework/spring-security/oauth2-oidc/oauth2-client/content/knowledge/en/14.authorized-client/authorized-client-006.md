# 14.6. HttpSessionOAuth2AuthorizedClientRepository and Session-Scoped Data

## Learning Objectives

In **Spring Security OAuth 2.0 Client**, the `OAuth2AuthorizedClient` object represents an authorized client containing an **access token** and optionally a **refresh token**. The application needs to store that state to use tokens on subsequent requests after the user completes OAuth 2.0 or OpenID Connect (OIDC) Login.

`HttpSessionOAuth2AuthorizedClientRepository` is an `OAuth2AuthorizedClientRepository` implementation that stores authorized clients in the **Servlet application's `HttpSession`**. This storage ties tokens to the browser session, though it does not automatically guarantee all tokens remain isolated per principal if a session is reused to switch accounts.

After this lesson, you will be able to:

- Explain the role of `HttpSessionOAuth2AuthorizedClientRepository` and the `loadAuthorizedClient`, `saveAuthorizedClient`, and `removeAuthorizedClient` contracts.
- Distinguish where `OAuth2AuthorizedClient`, `SecurityContext`, and pending-callback `OAuth2AuthorizationRequest` are stored.
- Understand the difference between **session-scoped** storage and **principal-scoped** storage, as well as the role of `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`.
- Configure Spring Security OAuth2 Login/Client and read authorized clients in a controller.
- Distinguish **access tokens**, **refresh tokens**, and **ID tokens** within an OIDC session.
- Identify risks from account switching, multiple tabs, session expiration, multiple instances, and concurrent token refreshes.
- Design appropriate cleanup, logout, token refresh, and session store protections.

## 1. Context: After OIDC Login, Where Is the Access Token?

Suppose we have a **Customer Portal** built with Spring Boot. The portal lets customers sign in with an enterprise OpenID Provider (OP) and calls the **Orders API** to fetch orders.

General flow:

1. Browser visits `/orders` without being signed in.
2. Spring Security initiates the OIDC Authorization Code flow.
3. The OP authenticates the user and redirects the browser back to the callback.
4. Portal exchanges the authorization code for tokens.
5. Portal verifies the ID token and builds `OidcUser` and `Authentication`.
6. Portal saves the login result and authorized client state per the configured repository/service.
7. The subsequent request to `/orders` can use the issued access token to call the Orders API.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant P as Spring Boot Portal
    participant OP as OpenID Provider
    participant API as Orders API
    U->>B: Open /orders
    B->>P: HTTP request
    P-->>B: Redirect to OP
    B->>OP: OIDC Authorization Request
    OP->>U: Authenticate/consent as needed
    OP-->>B: Redirect authorization code
    B->>P: Callback code and state
    P->>OP: Exchange code for tokens
    OP-->>P: ID token + access token
    Note over P: Verify OIDC, save Authentication and authorized client
    P-->>B: Session cookie / redirect
    B->>P: Subsequent /orders request
    Note over P: Load Authentication and authorized client
    P->>API: Bearer ACCESS_TOKEN
    API-->>P: Authorized orders
    P-->>B: Page content
~~~

Login produces **two distinct kinds of state**:

- **Authentication/SecurityContext**: who is currently logged into Portal?
- **OAuth2AuthorizedClient**: which tokens were issued to the client to call APIs?

Both may involve the session, yet they are not the same object.

## 2. Key Components

| Component | Role | What Does It Hold? |
|---|---|---|
| `ClientRegistration` | Client and provider configuration | Client ID, grant type, redirect URI, scopes, token endpoint |
| `OAuth2AuthorizedClient` | Result of an authorized client | Registration, principal name, access token, refresh token if present |
| `OAuth2AuthorizedClientRepository` | Saves/loads/removes authorized clients in a Servlet request context | Depends on implementation |
| `OAuth2AuthorizedClientService` | Saves/loads/removes authorized clients by registration ID and principal name | Memory store, database, or custom |
| `OAuth2AuthorizedClientManager` | Coordinates authorize/reauthorize, token reuse/refresh | Coordinates registration, authorized client, providers |
| `SecurityContextRepository` | Saves/restores Authentication | `SecurityContext` and principal |
| `OAuth2AuthorizationRequestRepository` | Stores pending-callback authorization request data | `state`, redirect URI, nonce/PKCE when used |

### 2.1. `ClientRegistration` Does Not Hold User Tokens

Example registration:

~~~text
registrationId: corporate
clientId: portal-web
authorizationGrantType: authorization_code
scope: openid profile orders.read
provider: company-oidc
~~~

This object exists before Alice or Bob logs in. It only describes the client.

An authorized client issued for Alice has the conceptual structure:

~~~text
OAuth2AuthorizedClient
├── clientRegistration: corporate
├── principalName: Alice
├── accessToken: ...
└── refreshToken: ... (if issued by OP)
~~~

The same registration can be used by many principals, each with their own tokens/authorizations. Storage must preserve that isolation properly.

### 2.2. `OAuth2AuthorizedClient` Is Not `OidcUser`

`OidcUser` is the principal after OIDC Login, typically holding the ID token, UserInfo, and claims. `OAuth2AuthorizedClient` holds the access token for APIs and optionally a refresh token.

**Never use `OidcUser.getIdToken().getTokenValue()` as a bearer token to call a Resource Server.** The API needs an access token issued for the appropriate audience/scope.

### 2.3. What Does the Principal Name Mean?

`OAuth2AuthorizedClient.getPrincipalName()` describes the principal associated with the authorization.

However, having a principal name field on the object **does not mean every repository uses it as the storage key**. Session-based repositories and principal-based services locate entries differently, as explained in the sections below.

## 3. What Is `HttpSessionOAuth2AuthorizedClientRepository`?

The class resides in package:

~~~java
org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository
~~~

It implements:

~~~java
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
~~~

Its job is to keep `OAuth2AuthorizedClient` instances inside the Servlet web request's `HttpSession`.

### 3.1. The Browser Does Not Hold the Full Authorized Client

In the Servlet session-based model:

~~~text
Browser
  Cookie: JSESSIONID=SESSION_A
                  |
                  v
          Portal's session store
          HttpSession SESSION_A
          ├── SecurityContext if present
          ├── Pending Authorization Request if any
          └── Authorized clients if using session repository
              ├── corporate -> OAuth2AuthorizedClient
              └── partner   -> OAuth2AuthorizedClient
~~~

This is a conceptual diagram, not exact Spring Security attribute names.

Normally the browser only holds a **session identifier** in a cookie. Access tokens/refresh tokens remain server-side when the repository uses `HttpSession`. Even so, **the session cookie is still a sensitive credential**: if hijacked, an attacker can attempt to hijack the session and exercise privileges attached to it.

### 3.2. Session Scope Differs from Principal Scope

`HttpSessionOAuth2AuthorizedClientRepository` centers on **HttpSession-scoped data**. In typical implementations, authorized clients are stored/looked up by **registration ID within the session**, not in a global token store keyed strictly by issuer + subject.

Consequences:

- Two browsers with two independent sessions can hold different authorized clients.
- Two tabs in the same browser usually share the session and authorized clients.
- The same session can hold tokens for multiple registration IDs.
- If user A and user B log in sequentially within **the same session without proper cleanup**, old tokens may be mistakenly reused.

**Do not treat session scope as an absolute guarantee of principal ownership.** When switching accounts or handling multiple tenants, the application still needs to enforce identity binding and clear stale state.

### 3.3. Never Read Internal Session Attributes Directly

Avoid this pattern:

~~~java
Object tokenStore = session.getAttribute("SPRING_SOME_INTERNAL_KEY");
~~~

Attribute names and storage structures can change across versions/implementations. Use `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService`, or Spring Security's provided integrations rather than depending on session internals.

## 4. The `OAuth2AuthorizedClientRepository` Contract

The interface has three main operations:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

// Core methods in OAuth2AuthorizedClientRepository:

<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        HttpServletRequest request);

void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        HttpServletRequest request,
        HttpServletResponse response);

void removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

*This is a set of signatures to explain the API; it is not a complete Java class.*

### 4.1. `loadAuthorizedClient`

Example:

~~~java
OAuth2AuthorizedClient authorizedClient =
        repository.loadAuthorizedClient(
                "corporate",
                authentication,
                request);
~~~

If no matching authorized client exists, the result may be `null`.

Reasons:

- Authorization has not been completed for that registration.
- The session does not exist or expired.
- The repository used for reading differs from the repository that saved it.
- Different registration IDs used between login and API call.
- The client was removed per policy.
- A principal-aware service could not find a record for the current principal.

Never fall back to using an ID token as a substitute token when the repository returns `null`.

### 4.2. `saveAuthorizedClient`

Example:

~~~java
repository.saveAuthorizedClient(
        authorizedClient,
        authentication,
        request,
        response);
~~~

With `HttpSessionOAuth2AuthorizedClientRepository`, authorized client state is stored in `HttpSession`.

Tokens can contain long-lived secrets such as refresh tokens, so:

- Only store authorized clients validly established by the framework/AS.
- Never accept a browser-submitted token object as a valid authorized client.
- Never dump entire authorized clients into logs.
- Be aware the repository may create a session when needed and know what data resides in it.
- Protect the session store as a credential repository.

### 4.3. `removeAuthorizedClient`

Example:

~~~java
repository.removeAuthorizedClient(
        "corporate",
        authentication,
        request,
        response);
~~~

This deletes the authorized client **from the local store** according to the implementation in use.

It is **not equivalent to**:

- Revoking the token at the Authorization Server.
- Clearing `SecurityContext` or logging out of Portal.
- Ending the OP's SSO session.
- Invalidating an already-issued access token currently accepted by a Resource Server.

These are separate responsibilities with separate mechanisms.

## 5. Three Repositories That Can All Involve HttpSession

Similar class names easily cause confusion:

| Class/Abstraction | Data | Timing |
|---|---|---|
| `HttpSessionOAuth2AuthorizationRequestRepository` | Original Authorization Request, `state`, nonce/PKCE when used | **Before** callback |
| `HttpSessionSecurityContextRepository` | `SecurityContext`, `Authentication` | **After** authentication or when restoring session |
| `HttpSessionOAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClient` containing access/refresh tokens | **After** authorization is granted |

### 5.1. An Authorization Request Is Not Yet an Authorized Client

When the browser starts login, Spring Security creates an Authorization Request. That data helps correlate the callback:

~~~text
Pending Authorization Request:
  state=STATE_A
  clientRegistration=corporate
  redirectUri=...
  nonce=... (when used)
  code_verifier=... (when using PKCE)
~~~

At this point no token has been issued yet. Only after the callback and token exchange succeed can `OAuth2AuthorizedClient` be saved.

Two classes easily confused:

~~~text
HttpSessionOAuth2AuthorizationRequestRepository
HttpSessionOAuth2AuthorizedClientRepository
~~~

The first has **AuthorizationRequest**; the second has **AuthorizedClient**. They do not replace one another.

### 5.2. SecurityContext Shows Who Logged In

After OIDC Login:

~~~text
SecurityContext
└── OAuth2AuthenticationToken
    ├── principal: OidcUser
    ├── authorities: [...]
    └── authenticated: true
~~~

This is Portal's authentication info. It does not necessarily carry the access token for the Orders API in the same object.

### 5.3. Having a Session Does Not Prove Having a Token

A snippet like:

~~~java
HttpSession session = request.getSession(false);
boolean hasSession = session != null;
~~~

only indicates that a session exists. The session may have been created before login to hold `state`, a request cache, or a CSRF token.

Do not infer:

~~~text
HttpSession exists
  => User is logged in
  => OAuth2AuthorizedClient exists
  => Access token is unexpired
  => API permits all operations
~~~

Each condition requires its own verification mechanism.

## 6. Role of `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`

Another very important class is:

~~~java
org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository
~~~

It enables combining:

1. For **principals considered authenticated**, use `OAuth2AuthorizedClientService`.
2. For **anonymous/unauthenticated** contexts, delegate to a secondary `OAuth2AuthorizedClientRepository`, typically defaulting to `HttpSessionOAuth2AuthorizedClientRepository`.

~~~mermaid
flowchart TD
    A["Authorized client load/save/remove"] --> B{"Principal authenticated?"}
    B -->|Yes| C["OAuth2AuthorizedClientService"]
    C --> D["registrationId + principalName"]
    B -->|No| E["Anonymous authorized client repository"]
    E --> F["Typically HttpSessionOAuth2AuthorizedClientRepository"]
~~~

This explains why a session repository can appear as part of default or composite configurations even when the application does not directly declare a session repository bean.

### 6.1. Why Use a Principal-Based Service?

`OAuth2AuthorizedClientService` uses the key registration ID + principal name.

This helps when:

- Tokens must be managed per authenticated user.
- The application wants to retrieve authorized clients without depending entirely on a single browser session.
- Tokens must be stored in memory or a database with an independent lifecycle.
- Multiple requests/instances need access under an established identity.

However, **the principal name must be designed properly**. With multiple OIDC issuers, do not use only email or only `sub` as a global key if collisions are possible. Define binding using issuer + subject or a trustworthy internal user ID.

### 6.2. Why Can Anonymous Requests Use a Session?

In some client authorization flows, the application may not yet have an authenticated principal in the web model. A session helps associate authorized client state with the browser/request context without an explicit principal key.

However, that does not mean every OAuth flow needs an `HttpSession`.

For example, **`client_credentials` for a background job** has no browser/`HttpServletRequest` and should normally use a manager/service and a configured principal representing the client/service, rather than relying on an arbitrary user's session.

### 6.3. Do Not Assume One Repository Across All Versions/Configurations

In Spring Boot/Spring Security, auto-configuration can create repositories and services when bean conditions match. If the application supplies its own beans or custom config, the actual choice can change.

Therefore, when inspecting a project, what matters is **which repository is actually used during login/save and API lookup**, not merely whether a class exists on the classpath.

## 7. Configuring an OIDC Client for a Servlet Application

### 7.1. Dependency

With Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 7.2. Client Registration

Example `application.yml`:

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
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Here:

- `corporate` is Spring's registration ID.
- `client-id` and secret are credentials issued by the OP.
- `authorization_code` uses browser redirects and callbacks.
- `openid` requests OIDC Login.
- `orders.read` is an illustrative API scope only; the AS and Orders API must support it.
- `issuer-uri` is the trusted issuer for provider metadata.

Secret values come from environment variables/secret manager; never commit real secrets.

### 7.3. Security Filter Chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

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

`oauth2Login()` handles OAuth2/OIDC Login, while `oauth2Client()` enables support for using authorized clients in outbound requests per configuration.

Normally you do not need to declare `HttpSessionOAuth2AuthorizedClientRepository` manually if Spring Security's default wiring already satisfies your needs.

## 8. Explicitly Configuring a Session-Based Repository

If the application wants all authorized clients in Servlet flows to use a session repository, you can declare the bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class SessionAuthorizedClientConfiguration {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }
}
~~~

When you need to explicitly pass this repository into security configuration extension points:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ExplicitRepositorySecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizedClientRepository repository)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .authorizedClientRepository(repository))
                .oauth2Client(client -> client
                        .authorizedClientRepository(repository))
                .build();
    }
}
~~~

Both examples are combined in an illustrative project; you do not need two separate `SecurityFilterChain` beans.

**Caution:** this binds tokens to `HttpSession`. If the same session is used to switch from Alice to Bob, ensure old tokens are removed, principals are bound properly, or select a principal-based repository. Do not pick the session repository solely because the class name contains `HttpSession`.

## 9. Configuring a Combined Authenticated Principal + Anonymous Repository

Another approach is using `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class PrincipalAwareClientConfig {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {

        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
                service);
    }
}
~~~

For authenticated principals, this repository uses `OAuth2AuthorizedClientService`. For anonymous principals, it uses a secondary repository via its default mechanism.

This combination provides a clearer principal-scoped token storage model for signed-in users. However, it carries implications to consider:

- Tokens can outlive a single `HttpSession` if the service persists independently.
- Local logout does not automatically delete every record in the service.
- Per-principal revocation and cleanup must be designed when disconnecting a provider.
- If the principal key does not sufficiently distinguish issuer/tenant, accounts risk mixing.

Do not declare this bean unnecessarily if your project is already auto-configured as desired, since overriding beans can alter storage behavior.

## 10. Reading the Authorized Client in a Controller

### 10.1. Using `@RegisteredOAuth2AuthorizedClient`

Spring Security provides the annotation:

~~~java
org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient
~~~

Example:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientStatusController {

    @GetMapping("/client-status")
    ClientStatus status(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        if (client == null) {
            return new ClientStatus("corporate", false, null);
        }

        return new ClientStatus(
                client.getClientRegistration().getRegistrationId(),
                client.getAccessToken() != null,
                client.getAccessToken() != null
                        ? client.getAccessToken().getExpiresAt()
                        : null);
    }

    record ClientStatus(
            String registrationId,
            boolean accessTokenPresent,
            Instant accessTokenExpiry) {}
}
~~~

The code returns simple metadata only; **never return raw tokens**.

In real systems, verify the authorized client was issued for the right registration/principal and use a manager/provider when refresh is needed. Whether the annotation returns a client depends on the project's authorized client resolution setup.

### 10.2. Using the Repository Directly

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedClientLookup {

    private final OAuth2AuthorizedClientRepository repository;

    public AuthorizedClientLookup(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    public OAuth2AuthorizedClient find(
            String registrationId,
            Authentication authentication,
            HttpServletRequest request) {

        return repository.loadAuthorizedClient(
                registrationId,
                authentication,
                request);
    }
}
~~~

This approach queries the repository inside a specific HTTP request.

Never serialize the entire `OAuth2AuthorizedClient` into a JSON response or log, because it contains the access token and potentially the refresh token.

## 11. Calling a Resource Server with the Access Token

After OIDC Login:

- `OidcUser.getIdToken()` provides the ID token intended for the RP.
- `OAuth2AuthorizedClient.getAccessToken()` provides the access token intended for APIs per granted permissions.

Example using Spring Framework 6.1+ `RestClient`:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {

    private final RestClient ordersApi =
            RestClient.create("https://orders-api.example.com");

    @GetMapping("/orders")
    String orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException("No access token available");
        }

        String token = client.getAccessToken().getTokenValue();

        return ordersApi.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(token))
                .retrieve()
                .body(String.class);
    }
}
~~~

The purpose of this example is to show **tokens must be taken from the authorized client**, not from the ID token.

This is not yet a complete production template: you must check token validity, scope/audience, reauthorization/refresh, retry policies, and API errors.

In practice, consider OAuth2 integration with an HTTP client or `OAuth2AuthorizedClientManager` to centralize token management. The Resource Server must validate the token and permissions itself.

### 11.1. Having a Token in the Session Does Not Guarantee API Acceptance

An access token sitting in the session may:

- Have expired.
- Have been revoked.
- Have an audience meant for a different API.
- Lack the `orders.read` scope.
- Belong to a different tenant.
- No longer match the current account after switching users.

Never send a token merely because the registration ID matches; enforce authentication and authorization policies on both the client and Resource Server.

## 12. Session Timeout, Access Token, and Refresh Token

### 12.1. Three Different Lifecycles

Example:

~~~text
HttpSession idle timeout:    30 minutes
Access token expires in:    10 minutes
Refresh token expires in:   2 hours, if issued
OP SSO session:              per OP policy
~~~

These durations are illustrative only.

Accurate conclusions:

- **Session still alive** does not mean the access token is unexpired.
- **Access token still alive** does not mean the Portal session still exists.
- **ID token expired** does not automatically clear `HttpSession` in all configurations.
- **OP SSO still alive** does not mean Portal still has a local `Authentication`.
- **Refresh token present** does not guarantee refreshing will always succeed.

### 12.2. The Repository Does Not Refresh Tokens Automatically

`HttpSessionOAuth2AuthorizedClientRepository` only handles **save/load/remove**.

Requesting new tokens belongs to mechanisms like `OAuth2AuthorizedClientManager` coordinating `OAuth2AuthorizedClientProvider` instances.

~~~mermaid
flowchart TD
    A["Application needs to call API"] --> B["AuthorizedClientManager"]
    B --> C["Look up authorized client in repository"]
    C --> D{"Token eligible for use?"}
    D -->|Yes| E["Call API with access token"]
    D -->|No| F{"Can reauthorize/refresh?"}
    F -->|Yes| G["Request new token from AS"]
    G --> H["Save updated authorized client"]
    H --> E
    F -->|No| I["Trigger new flow or report error"]
~~~

This diagram illustrates conceptual roles; actual refresh behavior also depends on grants, token policies, and manager configuration.

### 12.3. Refresh Tokens Are Especially Sensitive Data

If an authorized client holds a refresh token, storing the object in `HttpSession` means the session store holds a credential capable of obtaining additional access tokens.

You must protect:

- The session store and its backups.
- Connections between the application and the session store.
- Operational access privileges.
- Appropriate TTL, cleanup, and encryption.
- Logs/tracing/debug dumps to avoid leaking tokens.

Do not assume server-side tokens are automatically safe if the session store allows unrelated services or operators to read raw data unnecessarily.

### 12.4. Concurrent Refresh Tokens

When two HTTP requests both see an access token nearing expiration, both may attempt to refresh. If the AS uses refresh token rotation, a race can occur:

~~~text
Request A sees refresh token R1
Request B sees refresh token R1
A uses R1 -> receives R2
B uses R1 -> rejected or triggers reuse policy
~~~

The session repository does not by itself provide safe refresh token coordination across all nodes.

If the application requires high concurrency, design refresh coordination/update policies across the manager, token store, and Authorization Server rules.

## 13. Switching Accounts in the Same Session: A Situation Requiring Care

### 13.1. Example of Token Mix-Up

Suppose Portal provides a "Switch Account" button without creating a new session or clearing tokens.

~~~text
Before:
HttpSession S
  SecurityContext -> Alice
  corporate authorized client -> Alice's access token

After Bob logs into the same session S:
HttpSession S
  SecurityContext -> Bob
  corporate authorized client -> Alice's token still remains
~~~

If the application uses `HttpSessionOAuth2AuthorizedClientRepository` and retrieves the authorized client solely by registration ID `corporate`, Bob's request risks calling the API with Alice's token.

This is a key consequence of **session scope not automatically equating to principal scope**.

### 13.2. How to Avoid It

When switching accounts, you must:

1. Identify the new user by issuer + subject in the verified ID token.
2. Ensure the session/authentication is replaced consistently.
3. Remove authorized clients that do not belong to the new principal.
4. Discard cached business DTOs remaining from the previous user.
5. If using a service, ensure principal keys are truly unique and distinguish tenant/issuer.
6. Enforce authorization at the API per account and specific resource.

Never treat `login_hint` or a browser-submitted email as proof of a new user.

### 13.3. Never Fix This Using a Global Latest Token

A variable like:

~~~java
public static String lastAccessToken;
~~~

is broken for multi-user applications: every request could use whichever user updated it last.

Use an appropriately designed repository/service, and never store user credentials in mutable singleton fields.

## 14. Multiple Registrations and Multiple Tabs

### 14.1. Multiple Registrations in One Session

An application may have:

~~~text
corporate: enterprise OIDC login
partner: calling partner APIs
billing: using a different provider
~~~

An `HttpSession` repository can hold the corresponding authorized clients by registration ID within the session.

A user having a token for `corporate` does not mean that token is valid for `billing` or `partner`. Each token has its own issuer/audience/scope.

### 14.2. Two Tabs Sharing One Session

Two tabs in the same browser profile normally send the same session cookie. Therefore, they can share the authorized client stored in `HttpSession`.

If Tab A refreshes the token, Tab B may be holding an older object in-flight during processing. This is a concurrency/lifecycle issue, not each tab having its own token store.

When multiple OAuth logins run in parallel, you must also distinguish **pending Authorization Requests** from already-issued authorized clients. Pending state/callbacks belong to `HttpSessionOAuth2AuthorizationRequestRepository`, not the authorized client store.

### 14.3. Tab A Uses Alice While Tab B Switches to Bob

If the product allows switching accounts in one tab, the other tab may continue displaying stale data in its UI while the browser shares the same server session.

Never rely solely on UI state displayed in a tab to determine the current user. Every sensitive request must be authenticated and authorized against the current backend principal/session.

## 15. Logout and Token Data Cleanup

### 15.1. Portal Logout Does Not Mean Token Revocation

During logout in a Servlet application, Spring Security normally invalidates the local session and clears `Authentication`/`SecurityContext` per configuration.

If authorized clients reside inside the invalidated `HttpSession`, local token data disappears with the session.

However:

- Issued access tokens may still be accepted by the AS/Resource Server until expiration or revocation.
- Refresh tokens may remain valid at the AS if not revoked.
- The OP may still keep the SSO session active.
- If tokens are stored in an `OAuth2AuthorizedClientService` outside the session, records may continue to exist.

### 15.2. `removeAuthorizedClient` Does Not Automatically Call Revocation

Deleting tokens from the local repository only modifies Portal's store.

Revoking access/refresh tokens at the AS requires using a provider-supported token revocation mechanism with proper authentication and policy. Design this workflow separately.

### 15.3. Events Requiring Authorized Client Cleanup

Depending on business rules, cleanup may be needed when:

- User logs out.
- User switches accounts or tenants.
- Client is unlinked from a provider.
- Token refresh is rejected.
- Account is locked or downgraded.
- Registration/client secret changes.
- Session expires.
- User requests permission revocation.

**Ensure cleanup targets the store actually in use.** Deleting a session attribute does not affect records stored in a service/database, and vice versa.

## 16. Security of a Session Containing Tokens

### 16.1. Cookie and Timeout Configuration

Example:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Explanation:

- `timeout` is the session inactivity limit, not the access token TTL.
- `HttpOnly` restricts ordinary JavaScript from reading the session cookie.
- `Secure` requires HTTPS.
- `SameSite` helps control cookie transmission in cross-site contexts; evaluate against your specific OIDC redirect flow.

In local HTTP environments, `Secure` cookies may not be sent as expected. Configure per environment without weakening production requirements.

### 16.2. Session Fixation

After successful authentication, the application should rotate the session identifier or apply appropriate session fixation protection. Spring Security Servlet provides session fixation protection.

This protects the session ID, though it does not replace clearing tokens when an existing session is reused to switch principals.

### 16.3. CSRF

Because browsers automatically send session cookies, state-changing requests can be vulnerable to CSRF if unprotected.

`state` in the OAuth Authorization Request protects callback correlation, not arbitrary endpoints like `POST /orders` or `POST /account`.

Never disable CSRF globally just because the application uses OAuth2/OIDC Login.

### 16.4. Distributed Session Stores Are Credential Stores

With Spring Session or distributed session stores, serialized session data can contain authorized clients along with refresh tokens.

Controls to consider:

- Access permissions and network isolation of the session store.
- TLS/encryption in transit and encryption at rest where appropriate.
- TTL, backups/replication, rotation, and data deletion.
- Reviewing whether sessions appear in logs/metrics/backups.
- Restricting other services from reading raw session objects.
- Monitoring serialization compatibility across deployed versions.

**Never dump the entire `HttpSession`** as a diagnostic technique in production.

## 17. Multiple Instances and Load Balancers

Diagram:

~~~text
Browser
  |
Load Balancer
  |---- Portal A
  |---- Portal B
~~~

If Portal A stores the authorized client in local in-memory session storage and the next request hits Portal B, B may not see the saved token.

The resulting symptom is "login succeeded, yet API calls cannot find the authorized client".

Solutions include:

1. **Session affinity** so the same browser usually hits the same node, while understanding limits during node failures/scaling.
2. **Shared session store** via Spring Session or a distributed session manager.
3. **Principal-based authorized client service** with an appropriate backing store if persistence outside the session is desired.

Whichever option you choose, you must still design token isolation, concurrent refresh, and cleanup. Shared sessions do not automatically guarantee atomic updates in every case.

### 17.1. Reading from Another Instance and Cookie Inconsistencies

Also verify:

- Cookie domain/path.
- HTTPS and `Secure` flag.
- Session ID rotation after login.
- Forwarded headers from reverse proxies.
- Session store timeouts.
- Session loss during deployments.

Never bypass authentication checks or move tokens into global variables just to make multi-node setups work.

## 18. When Should You Choose Which Repository?

| Requirement | Session Repository | Principal-Aware Repository/Service |
|---|---|---|
| Tokens only needed for one browser session | Good fit | May need explicit session binding |
| Anonymous flow needs browser context | Can fit | Usually needs fallback repository |
| User wants tokens across multiple browser sessions | Does not meet on its own | Can fit if policy permits |
| Background job without Servlet request | Not convenient | Service/manager with service principal is cleaner |
| Logout must remove tokens with session | Can follow session invalidation | Requires explicit cleanup outside session |
| Account switching within same session | Must guard and clear old tokens | Has principal key, still needs accurate identity |
| Multiple nodes without shared sessions | Easy to lose state | Service-backed store can help |
| Concurrent token refresh | Still needs separate handling | Still needs separate handling |

In a typical Servlet OIDC web application, **understand existing beans and repositories before overriding**. Choose the repository based on token ownership model, sessions, logout, and operability—not solely on the class name.

## 19. Common Issues

| Symptom | Possible Cause | What to Check |
|---|---|---|
| No authorized client after login | Different repository/service used on save vs. load; session/cookie lost | Repository wiring, registration, session |
| `loadAuthorizedClient` returns null | Token not issued yet, removed, or wrong registration | Flow, principal, repository |
| Session active yet API returns 401 | Token expired, wrong audience/scope, or revoked | Token manager and Resource Server |
| Token still works after logout | Local logout does not automatically revoke tokens | AS/RS token policy |
| Bob accidentally uses Alice's token | Session reused or keys do not isolate principals | Account switching/cleanup |
| Tabs A and B see different token states | Concurrent requests, refresh/repository update | Concurrency and token lifecycle |
| Token intermittently missing across nodes | Unshared session store or unstable routing | Spring Session, load balancer |
| Refresh token rejected | Token rotation, expiration, or concurrency | AS policy, refresh coordination |
| Background job lacks token | No Servlet request/session | Service principal/manager |
| Reading token via internal session attribute breaks | Relies on implementation details | Use repository API |
| API receives ID token and returns 401 | Wrong token type/audience | Send access token for the target resource |

### 19.1. Safe Diagnostics

Safe to observe:

- Registration ID.
- Authentication type and authenticated status.
- Whether a session exists (do not log its ID).
- Which repository is wired.
- Whether an authorized client was found.
- Token expiry time if permitted.
- Generic error codes from the token endpoint.
- Instance and request correlation ID.

Never log:

~~~text
access token
refresh token
ID token
authorization code
code_verifier
client secret
JSESSIONID / session cookie
serialized HttpSession
~~~

## 20. Comprehensive Design Example

A Customer Portal requires:

- OIDC Login via `corporate`.
- Using the access token to call the Orders API.
- Never mixing Alice's and Bob's tokens.
- Multiple server instances.
- Supporting logout and disconnecting the provider.

Design decisions needed:

1. Should authorized clients be scoped per browser session or per principal?
2. If signing in from multiple devices, should they share one token?
3. When switching accounts in the same browser, which session/tokens must be cleared?
4. When a token expires, which component refreshes it?
5. Does concurrent refresh rotation need handling?
6. Does the token live in `HttpSession` or in which service/database?
7. On logout, are local tokens deleted and must tokens be revoked at the AS?
8. How does the API verify audience, scope, issuer, and order permissions?

A solid design does not just "save the token for the next request"—it defines **who may use the token, how long it is kept, and when it is deleted**.

## 21. Self-Check Questions

**Question 1.** What is `HttpSessionOAuth2AuthorizedClientRepository` used to store?

**Answer:** `OAuth2AuthorizedClient` objects with access tokens and optionally refresh tokens within the `HttpSession` context of a Servlet application.

**Question 2.** Does it store authorization requests awaiting callback?

**Answer:** That is not its job. Authorization Requests and state are managed by `OAuth2AuthorizationRequestRepository`, which typically has a corresponding session implementation.

**Question 3.** Does having an HttpSession mean the user is logged in and has a token?

**Answer:** No. A session can exist prior to login. `SecurityContext`/`Authentication` and authorized clients must be checked separately.

**Question 4.** How does `OAuth2AuthorizedClientRepository` differ from `OAuth2AuthorizedClientService`?

**Answer:** The repository takes Servlet request/response along with `Authentication`; the service stores/looks up by registration ID and principal name without needing a Servlet request.

**Question 5.** For an authenticated principal, which store does `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` normally use?

**Answer:** `OAuth2AuthorizedClientService`. For anonymous principals, it uses a fallback repository, typically defaulting to a session repository.

**Question 6.** What is the risk when switching from Alice to Bob in the same HttpSession?

**Answer:** Without clearing old tokens and binding principals properly, Alice's token could be picked up for Bob's requests.

**Question 7.** The session has 20 minutes remaining, yet the access token expired; does the repository refresh it automatically?

**Answer:** No. The repository only saves/loads/removes; the manager/provider and AS policies coordinate reauthorization/refresh.

**Question 8.** Does logging out of Portal immediately invalidate issued access tokens at the Orders API?

**Answer:** Not by default. Local session cleanup differs from token revocation at the AS.

**Question 9.** Why can multiple nodes lose authorized clients?

**Answer:** If sessions are stored locally in memory on Node A, Node B cannot read them. A shared session store or appropriate principal-based storage is required.

**Question 10.** Can `OidcUser`'s ID token be used instead of an access token when calling an API?

**Answer:** No, under the standard OAuth Resource Server model. An access token intended for the API's audience/scope is required.

**Question 11.** Does using a session repository guarantee each browser tab stores separate tokens?

**Answer:** No. Tabs in the same browser usually share the session cookie and therefore can share the authorized client.

**Question 12.** What should an application use for a background job without an `HttpServletRequest`?

**Answer:** Consider an authorized client manager/service with a principal representing the service or an appropriate mechanism, rather than relying on a browser's `HttpSession`.

## Key Takeaways

- **`HttpSessionOAuth2AuthorizedClientRepository` stores authorized client/token state in the Servlet session**.
- **`ClientRegistration` is configuration only**, whereas `OAuth2AuthorizedClient` holds the access token and optional refresh token.
- **Authorization Request**, **SecurityContext**, and **Authorized Client** are managed by distinct abstractions, even when all involve `HttpSession`.
- **Session scope does not automatically equal principal scope**: guard carefully against account switching and multi-tenancy issues.
- **`AuthenticatedPrincipalOAuth2AuthorizedClientRepository`** can use a service for authenticated principals and a session repository for anonymous ones.
- **The repository does not automatically refresh or revoke tokens**. Use an authorized client manager and proper cleanup/logout/revocation mechanisms.
- **A session store holding tokens is a sensitive credential store**; protect cookies, HTTPS, CSRF, session fixation, TTL, concurrency, and distributed deployments.
- **When calling APIs, use an access token with the right audience/scope, never an ID token as a substitute.**
