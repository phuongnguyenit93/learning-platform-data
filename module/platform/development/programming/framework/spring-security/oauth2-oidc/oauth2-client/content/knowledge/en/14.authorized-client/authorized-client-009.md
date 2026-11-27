# 14.9. Saving, Loading, Updating, and Removing an Authorized Client

## 1. Why Does an OAuth2 Client Need Authorized Client Storage?

In a **Spring Security OAuth 2.0 OIDC Client** application, a user successfully signing in via a provider does not mean the backend only uses the token once. The application may need to:

- Call UserInfo or a business API after the user has logged in.
- Load the received Access Token for subsequent API calls.
- Refresh the Access Token when it expires while a valid Refresh Token remains.
- Update token details when the Authorization Server issues a new token pair.
- Remove the provider connection when the user clicks "Disconnect".
- Persist across multiple HTTP requests, multiple instances, or application restarts, depending on design.

Spring Security represents an authorized client with **`OAuth2AuthorizedClient`**. This object combines *client registration*, *principal name*, and issued tokens.

For example, a user logs into a portal via OIDC and authorizes the portal to call a calendar API. The backend must remember the **Access Token of the calendar registration** for that principal, rather than forcing the user through an authorization code flow every time they open the "My Calendar" page.

**An authorized client is neither a user account record nor an HTTP session.** It is the authorization state of an OAuth2 client for a principal/actor within a registration's scope. This lesson focuses on how Spring Security Servlet **saves, loads, updates, and removes** that state safely.

## 2. Distinguishing ClientRegistration and OAuth2AuthorizedClient

First, separate **client configuration** from **authorization outcome**.

| Component | What Does It Hold? | Nature |
| --- | --- | --- |
| `ClientRegistration` | `registrationId`, client ID, grant type, redirect URI, scopes, authorization/token/JWKS/UserInfo endpoints | Shared OAuth2 client configuration across transactions |
| `OAuth2AuthorizedClient` | `ClientRegistration`, `principalName`, Access Token, and Refresh Token if present | Authorization result for one principal |
| `OAuth2AuthorizedClientService` | Save/load/remove mechanism by `registrationId + principalName` | Token storage abstraction independent of Servlet requests |
| `OAuth2AuthorizedClientRepository` | Save/load/remove mechanism with `HttpServletRequest`, `HttpServletResponse`, and `Authentication` context | Suitable when working inside Servlet flows |
| `OAuth2AuthorizedClientManager` | Finds or acquires a new authorized client; can refresh tokens per configured providers/grants | Orchestrates authorization lifecycle, not just CRUD |

One `ClientRegistration` named `calendar` can be used by many users:

~~~text
ClientRegistration:
  registrationId = "calendar"
  clientId = "portal-calendar"
  authorizationGrantType = "authorization_code"

OAuth2AuthorizedClient #1:
  registrationId = "calendar"
  principalName = "alice"
  accessToken = "TOKEN_FOR_ALICE"

OAuth2AuthorizedClient #2:
  registrationId = "calendar"
  principalName = "bob"
  accessToken = "TOKEN_FOR_BOB"
~~~

**Never store user-scoped tokens solely by `registrationId`.** Without a principal namespace, User A's Access Token can mistakenly be returned for User B.

### 2.1. Important Fields of OAuth2AuthorizedClient

Core API:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

OAuth2AuthorizedClient client = /* loaded or authorized by the framework */;

ClientRegistration registration = client.getClientRegistration();
String registrationId = registration.getRegistrationId();
String principalName = client.getPrincipalName();
OAuth2AccessToken accessToken = client.getAccessToken();
OAuth2RefreshToken refreshToken = client.getRefreshToken(); // may be null
~~~

| Value | Meaning |
| --- | --- |
| `client.getClientRegistration()` | Provider/client configuration used to acquire the token |
| `client.getPrincipalName()` | Identifier name the authorized client data is bound to |
| `client.getAccessToken()` | Current Access Token, including value, token type, issued/expiry, and scopes |
| `client.getRefreshToken()` | Refresh Token if issued by the provider and stored by the framework |

**This object does not contain `id_token` as a standard property.** With OIDC Login, the ID Token authenticates the user and normally resides in `OidcUser`/authentication context; the OAuth2 client's Access Token/Refresh Token reside in `OAuth2AuthorizedClient`.

### 2.2. Principal Name Is a Storage Key, Not an Arbitrary Email

Most services store authorized clients under the logical key:

~~~text
(clientRegistrationId, principalName)
~~~

With OAuth2 Login, the principal name usually comes from `Authentication.getName()`, depending on the principal type and user name attribute. For OIDC, the stable identity key is **`iss + sub`**; `sub` alone can collide across two issuers. Therefore, when designing for multiple providers and tenants, ensure registration and principal namespaces prevent collisions or user mix-ups.

Never arbitrarily use email as `principalName` to store tokens, because emails can change, may be unverified, and can be reassigned/reused.

## 3. Lifecycle of an Authorized Client

A typical cycle:

~~~mermaid
flowchart TD
    A["Application needs to call API with client registration"] --> B["OAuth2AuthorizedClientManager.authorize(...)"]
    B --> C{"Valid authorized client already exists?"}
    C -->|Yes, token still eligible| D["Return stored authorized client"]
    C -->|Not yet present| E["Appropriate grant: authorization_code / client_credentials / ..."]
    C -->|Token expired, refresh token present| F["refresh_token grant"]
    E --> G["Token Endpoint issues tokens"]
    F --> G
    G --> H["Save/update OAuth2AuthorizedClient"]
    D --> I["Use Access Token to call API with right audience/scope"]
    H --> I
    I --> J{"User disconnects or token no longer needed?"}
    J -->|Yes| K["removeAuthorizedClient(...) and revocation if provider supports"]
    J -->|No| A
~~~

This is a logical model. **`OAuth2AuthorizedClientRepository` and `OAuth2AuthorizedClientService` themselves do not send HTTP requests to refresh tokens.** Acquiring/refreshing tokens is coordinated by `OAuth2AuthorizedClientManager` with appropriate `OAuth2AuthorizedClientProvider` instances.

Specifically, when Authorization Code Login succeeds, Spring Security can automatically save the authorized client into the repository during login processing. The application is **not required** to manually call `saveAuthorizedClient` immediately after every standard login.

## 4. Two Storage Abstractions: Repository and Service

Spring Security provides two closely related APIs with different scopes.

### 4.1. OAuth2AuthorizedClientRepository — With Servlet Context

Interface:

~~~java
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
~~~

Methods:

~~~java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);

void removeAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

These are illustrative signatures; `Authentication` is `org.springframework.security.core.Authentication`, and HTTP types on the modern Servlet stack use `jakarta.servlet.http.*`.

These three methods allow implementations to use **HTTP session, cookies, or server-side storage with user context**. The actual storage structure does not necessarily live inside the request.

Example: a controller needs to inspect a logged-in user's authorized client, or a user clicks a disconnect button in the web app.

### 4.2. OAuth2AuthorizedClientService — No Servlet Request Needed

Interface:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
~~~

Methods:

~~~java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    String principalName
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

The service does not take `HttpServletRequest`/`HttpServletResponse`. Therefore, it fits when tokens are stored in memory, JDBC, or retrieved from a service running **outside an HTTP request**, provided the application has authorization to look up that data.

| Characteristic | Repository | Service |
| --- | --- | --- |
| API requires HTTP request/response | Yes | No |
| API requires Authentication | Yes | No, uses `principalName` |
| Can store in session | Yes, with matching implementation | Not a required characteristic |
| Can store in database | Can delegate | Yes, e.g., JDBC |
| Automatically refreshes Access Token | No | No |
| Suitable for Servlet controllers | Yes | Yes, if principal name is safely determined |
| Suitable for scheduled jobs without Servlet request | Typically not directly | Yes |

### 4.3. Do Not Confuse with AuthorizationRequestRepository

| Repository | What Does It Store? | Phase |
| --- | --- | --- |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `state`, redirect URI, PKCE, and pending authorization request | **Before callback**, when browser is sent to IdP |
| `OAuth2AuthorizedClientRepository` | Issued Access Token/Refresh Token | **After authorization succeeds** |

If the callback reports `authorization_request_not_found`, the problem lies in correlation/session of the **initial authorization request**, not necessarily a lost `OAuth2AuthorizedClient`. Conversely, login succeeding while the API has no stored token is an authorized client lifecycle issue.

## 5. Common Implementations

### 5.1. HttpSessionOAuth2AuthorizedClientRepository

`HttpSessionOAuth2AuthorizedClientRepository` stores authorized client data using the **HTTP session**. It suits simple Servlet flows or unauthenticated contexts handled by session in the framework.

~~~text
Browser
  Cookie JSESSIONID -> session S1
                         |
                         v
                 HTTP Session S1
                   authorized clients:
                     calendar -> Access Token / Refresh Token
~~~

Pros: simple, aligned with the browser session. Limitations: data is normally lost when the session expires or is cleared; if kept only in single-node memory, it does not survive restarts or share across nodes.

### 5.2. InMemoryOAuth2AuthorizedClientService

`InMemoryOAuth2AuthorizedClientService` holds authorized clients **in the application process's memory**, keyed by registration and principal.

~~~java
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

OAuth2AuthorizedClientService service =
    new InMemoryOAuth2AuthorizedClientService(clientRegistrationRepository);
~~~

In this example, `clientRegistrationRepository` is assumed to be provided by Spring Boot/Spring Security. In-memory storage fits demos or environments that do not require tokens to survive restarts; it **does not automatically share data across instances**.

### 5.3. JdbcOAuth2AuthorizedClientService

`JdbcOAuth2AuthorizedClientService` uses a database via Spring JDBC to store Access Tokens and Refresh Tokens. This is a common choice when data must persist across multiple HTTP sessions or multiple instances.

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

OAuth2AuthorizedClientService jdbcService(
        DataSource dataSource,
        ClientRegistrationRepository registrations) {
    return new JdbcOAuth2AuthorizedClientService(
        new JdbcTemplate(dataSource), registrations);
}
~~~

This snippet demonstrates constructing the object, not a complete database/schema/migration setup. When using the JDBC service, you must **create the table/schema matching your Spring Security version** and protect token columns because they are sensitive credentials. Never apply a schema from another version without checking the library's contract.

### 5.4. AuthenticatedPrincipalOAuth2AuthorizedClientRepository

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` is an important adapter:

- For **authenticated principals**, it delegates save/load/remove through `OAuth2AuthorizedClientService`.
- For **unauthenticated/anonymous principals**, it can use another repository, usually `HttpSessionOAuth2AuthorizedClientRepository`.

~~~mermaid
flowchart TD
    A["OAuth2AuthorizedClientRepository"] --> B{"Is principal authenticated?"}
    B -->|Yes| C["OAuth2AuthorizedClientService"]
    B -->|No/anonymous| D["Anonymous fallback repository"]
    C --> E["InMemory / JDBC / custom store"]
    D --> F["HttpSessionOAuth2AuthorizedClientRepository"]
~~~

This explains why **registering a JDBC service** and **HTTP sessions** are not always mutually exclusive: one repository can use the service for logged-in users and a session fallback for unauthenticated cases.

**Do not assume that seeing an HTTP session cookie means tokens are definitely inside the session.** Check which repository/service implementation the application actually uses.

## 6. Configuring a Spring Boot Servlet Application

### 6.1. Dependencies

Example with Spring Boot 3.x and Servlet MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // When using the JDBC authorized client service:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

With Spring Boot 4.x, starters are modularized and may be named `spring-boot-starter-webmvc`, `spring-boot-starter-security-oauth2-client`. Pick the exact dependency set matching your project's BOM; never mix Spring Security versions just to get a JDBC class.

### 6.2. OAuth2/OIDC Registration

Example `application.yml` for an OIDC provider with discovery:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

These URLs and IDs are examples; replace them with your real provider's details. `company` is the **registration ID**; `company-provider` is the ID of the provider configuration block.

### 6.3. SecurityFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
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

`oauth2Login()` handles browser login; `oauth2Client()` enables OAuth2 Client configuration when calling APIs and managing authorized clients. **Successful OIDC login does not automatically prove the Access Token has scopes suitable for every API**; you must request the right permissions and target the right resource server.

## 7. Saving an Authorized Client

### 7.1. Saving with OAuth2AuthorizedClientService

When the application **already has a valid `OAuth2AuthorizedClient` from a trusted OAuth2 flow**, it can call:

~~~java
void save(
        OAuth2AuthorizedClientService service,
        OAuth2AuthorizedClient authorizedClient,
        String principalName) {
    service.saveAuthorizedClient(authorizedClient, principalName);
}
~~~

Save behavior: the logical key combines `authorizedClient.getClientRegistration().getRegistrationId()` with the supplied `principalName`. Never take `principalName` from an unconstrained browser query string to save tokens into another user's account.

### 7.2. Saving with OAuth2AuthorizedClientRepository

Inside a Servlet request:

~~~java
void saveForCurrentRequest(
        OAuth2AuthorizedClientRepository repository,
        OAuth2AuthorizedClient authorizedClient,
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response) {

    repository.saveAuthorizedClient(
        authorizedClient,
        authentication,
        request,
        response);
}
~~~

Imports:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
~~~

**Never construct an `OAuth2AuthorizedClient` from a browser-submitted Access Token**, or take an arbitrary token and attach it to another principal. Tokens must originate from a valid authorization flow for the right registration and authorized subject.

### 7.3. Must You Call Save Manually After OAuth2 Login?

Normally **no**. `OAuth2LoginAuthenticationFilter` and related OAuth2 Login components already integrate with the authorized client repository to save authorization results upon successful login.

Calling save redundantly after login can cause:

- Duplicate token writes.
- Saving under a different `principalName` than the framework selected.
- Accidentally saving one registration's token under another user if code maps names manually.
- Desynchronization when session/authentication changes.

Only call save explicitly when genuinely managing a custom flow or an authorized client created/updated outside the automatic mechanism.

## 8. Loading an Authorized Client

### 8.1. Loading from Service

~~~java
OAuth2AuthorizedClient authorizedClient =
    authorizedClientService.loadAuthorizedClient(
        "company",
        authentication.getName());
~~~

If no matching record exists, the method typically returns `null`. Application code must handle the unauthorized case rather than immediately calling `getAccessToken()` on `null`.

Example:

~~~java
OAuth2AuthorizedClient client =
    service.loadAuthorizedClient("company", currentPrincipalName);

if (client == null) {
    // User has not authorized this registration yet,
    // or the record was deleted / does not exist.
    return;
}

OAuth2AccessToken accessToken = client.getAccessToken();
// Never log or return the token to the browser.
~~~

This snippet assumes `service` and `currentPrincipalName` come from a valid server-side authentication mechanism.

### 8.2. Loading from Repository in a Controller

Example endpoint reporting only **whether an authorized client is stored**, without exposing tokens:

~~~java
package com.example.web;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConnectionStatusController {

    private final OAuth2AuthorizedClientRepository repository;

    public ConnectionStatusController(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/integrations/company/status")
    public Map<String, Object> status(
            Authentication authentication,
            HttpServletRequest request) {

        OAuth2AuthorizedClient client =
            repository.loadAuthorizedClient(
                "company", authentication, request);

        return Map.of(
            "registrationId", "company",
            "stored", client != null,
            "accessTokenPresent", client != null
        );
    }
}
~~~

This endpoint is protected by `anyRequest().authenticated()` in the `SecurityFilterChain` above. The result only reflects **storage status**, not whether the token is still valid or usable against an API.

In real products, `stored` alone may suffice; avoid sending detailed scopes, token expiry, or principal names if the UI does not need them.

### 8.3. @RegisteredOAuth2AuthorizedClient

Spring Security Servlet provides the annotation:

~~~java
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
~~~

Examples on specific Spring Security versions use a controller parameter like:

~~~java
@GetMapping("/calendar")
String calendar(
    @RegisteredOAuth2AuthorizedClient("calendar")
    OAuth2AuthorizedClient authorizedClient) {

    // Use authorizedClient.getAccessToken() server-side.
    return "calendar";
}
~~~

**Note:** the annotation/resolver does not merely "fetch the raw record" in every case; it can collaborate with `OAuth2AuthorizedClientManager` to find or authorize/re-authorize per configuration. If you need to **inspect storage state without triggering an authorization flow**, call `loadAuthorizedClient(...)` directly with explicit principal and registration.

Never put `authorizedClient.getAccessToken().getTokenValue()` into a model/template, URL, or HTTP response simply because the controller received the object.

## 9. Updating an Authorized Client: Re-Save or Refresh?

The word "update" has at least two meanings:

1. **Replace the stored record**: write a new `OAuth2AuthorizedClient` under the same `(registrationId, principalName)` key.
2. **Obtain a new token**: execute an OAuth2 grant—typically the Refresh Token grant—and save the new result.

**Repositories/services only perform storage.** They do not understand full refresh conditions and do not call the token endpoint themselves. Issuing/refreshing tokens must be handled by `OAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientProvider` or a deliberately designed flow.

### 9.1. When the Access Token Has Expired

An `OAuth2AccessToken` has timestamps:

~~~java
OAuth2AccessToken token = authorizedClient.getAccessToken();

Instant issuedAt = token.getIssuedAt();
Instant expiresAt = token.getExpiresAt();
~~~

`expiresAt` describes the expiration timestamp if present. Never use logic like "whenever `OAuth2AuthorizedClient` is non-null, the Access Token is always valid".

When a token is found to be no longer eligible:

- If a valid Refresh Token exists and provider/grant permit, the token manager can refresh it.
- If there is no Refresh Token or refresh is rejected, restarting the Authorization Code flow or prompting the user to re-authorize may be required.
- With Client Credentials, the token manager can request a new token using client credentials; there is no interactive user.
- Providers can revoke tokens before expiration; client-side expiry checks do not replace handling 401/403 responses from the API.

### 9.2. Token Rotation and Re-Saving

A refresh response may return:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "calendar.read"
}
~~~

If Refresh Tokens are rotated, the `OAuth2AuthorizedClient` record must reflect the new token. Never hold onto the old Refresh Token and keep retrying after the token endpoint has invalidated it.

Depending on the provider, a refresh response **might not include a new Refresh Token**. Framework or client logic must apply the right keep/replace Refresh Token rule per grant and provider contract; never assume "missing field means delete the entire connection".

### 9.3. Never Update Tokens via String Manipulation

`OAuth2AuthorizedClient` is not an object whose token the application should "patch" via string operations:

~~~java
// ANTI-PATTERN: never take a token string from the browser and overwrite.
String token = request.getParameter("access_token");
// repository.save... with an unverified token is broken design.
~~~

Access Tokens must be issued by a trusted Authorization Server under the proper grant. When new state must be saved, obtain the result from the OAuth2 client/provider and build/save the object per Spring Security's contract.

## 10. OAuth2AuthorizedClientManager: Entry Point for Acquisition and Refresh

Two common managers in the Servlet ecosystem:

| Manager | Context | Associated Store |
| --- | --- | --- |
| `DefaultOAuth2AuthorizedClientManager` | Inside an `HttpServletRequest` of a Servlet web app | `OAuth2AuthorizedClientRepository` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Outside Servlet requests, e.g., jobs/backend services | `OAuth2AuthorizedClientService` |

The manager coordinates providers for grants such as `authorization_code`, `refresh_token`, and `client_credentials` depending on configuration. Each grant has its own conditions; a manager cannot refresh a token if the provider did not issue a Refresh Token or the client is not authorized for that grant.

### 10.1. Example Manager Configuration for Servlet Requests

~~~java
package com.example.security;

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

**This example illustrates the configuration point**, not a requirement for every app to enable all grants. For a portal with only Authorization Code login, do not enable Client Credentials if business logic does not use it. Conversely, a worker service without a user/browser typically uses Client Credentials and `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

### 10.2. Calling authorize() to Obtain a Usable Client

When `Authentication` is present inside a Servlet request:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest.withClientRegistrationId("calendar")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient client =
    authorizedClientManager.authorize(authorizeRequest);

if (client == null) {
    // Manager could not authorize/restore client in current context.
    // Do not call the API without a token.
}
~~~

In this example, `authentication` and `authorizedClientManager` are injected/supplied by the server. With `DefaultOAuth2AuthorizedClientManager`, the call needs an appropriate **Servlet request/response context** or configured attributes so the manager can interact with the repository.

When the provider succeeds, the manager normally uses an appropriate success handler to save the newly issued or refreshed authorized client into the store. Therefore, **you do not need an extra manual `saveAuthorizedClient` call when the manager already handles saving**.

### 10.3. Service Manager for Work Outside HTTP Requests

~~~java
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientService);

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build());
~~~

The snippet assumes both dependencies are configured. With Client Credentials, there is no OIDC end-user login: the Access Token represents a **client/service principal**, with no ID Token authenticating a user.

In background jobs, pick a consistent `principalName` for storing service-level tokens (e.g., `system-calendar-sync`). Never pick an arbitrary end-user's name to hold system-wide Client Credentials tokens.

### 10.4. Difference Between load() and authorize()

| Call | Possible Effect |
| --- | --- |
| `service.loadAuthorizedClient(registrationId, principalName)` | Only reads the stored record |
| `repository.loadAuthorizedClient(registrationId, auth, request)` | Only reads the record via repository context |
| `manager.authorize(authorizeRequest)` | Reads state, may acquire/refresh token, may update/remove per policy and handlers |

When simply displaying connection status, distinguish **"a record exists"** from **"a usable Access Token currently exists"**. Those two states are not equivalent.

## 11. Removing an Authorized Client

A user may choose "Disconnect Calendar", or an administrator may request removing stored application access. In Spring Security, removing an authorized client is the operation of **deleting the token record held by the client**.

### 11.1. Removing from OAuth2AuthorizedClientService

~~~java
service.removeAuthorizedClient(
    "calendar",
    currentPrincipalName
);
~~~

This deletes the record for that exact `registrationId` and `principalName`. If the user had multiple authorized clients for different registrations, this operation does not delete all of them automatically.

### 11.2. Removing from OAuth2AuthorizedClientRepository

~~~java
repository.removeAuthorizedClient(
    "calendar",
    authentication,
    request,
    response
);
~~~

In a Servlet app, request, response, and Authentication determine the context to remove. With a repository delegating to a service, this may delete a database row; with a session-based repository, it may remove a session attribute.

### 11.3. POST Controller for Disconnecting

Illustrative endpoint:

~~~java
package com.example.web;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DisconnectController {

    private final OAuth2AuthorizedClientRepository repository;

    public DisconnectController(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    @PostMapping("/integrations/calendar/disconnect")
    public Map<String, String> disconnect(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        repository.removeAuthorizedClient(
            "calendar", authentication, request, response);

        return Map.of("status", "local_record_removed");
    }
}
~~~

This example assumes the URL is protected by `anyRequest().authenticated()` and Spring Security CSRF protection is enabled for POST requests. HTML forms must include the corresponding CSRF token; SPAs must configure CSRF/session per architecture rather than disabling CSRF globally.

**The `local_record_removed` response only confirms deletion of data stored by the application.** It **does not guarantee** that the Access Token was revoked by the Authorization Server, that the user was logged out of the IdP, or that all grants were canceled at the provider.

### 11.4. Removing a Record Differs from Revoking a Token

| Action | What Does It Actually Do? |
| --- | --- |
| `removeAuthorizedClient(...)` | Deletes the token record in the OAuth2 client's store |
| OAuth2 Token Revocation (if provider supports) | Asks the Authorization Server to revoke the token per standard/extension mechanism |
| Local logout | Ends SecurityContext/HTTP session per logout policy |
| OIDC RP-Initiated Logout | Can ask the OP to end the IdP login session if configured and supported |
| Deleting business account link | Modifies application integration data; may require its own workflow |

For complete disconnection, some products need to call the **revocation endpoint** (RFC 7009) before removing stored tokens, if supported by the provider. Handle the response per the provider's contract without logging raw tokens. Deleting only the local record leaves old tokens valid at the Resource Server until expiration or revocation.

Do not require calling a revocation endpoint if the provider lacks one; in that case, communicate the exact scope of the action accurately and manage token lifetime risks.

## 12. Storing in a Database: From Demo to Multiple Instances

### 12.1. When Is JDBC Needed?

If running one instance without needing authorized clients to survive restarts, an in-memory service may suffice for learning examples. However, if the application:

- Runs multiple pods/instances behind a load balancer.
- Needs Access Tokens to execute tasks after the user closes the browser.
- Wants users to connect once and reuse across multiple HTTP sessions.
- Needs long-lived token/Refresh Token lifecycle management per policy.

then a shared, persistent store such as JDBC may be more appropriate.

~~~text
Browser A ------> App Instance 1 ---+
                                    |
Browser B ------> App Instance 2 ---+---> Shared database
                                    |     oauth2_authorized_client
Background job --> Worker Instance -+     (encrypted/restricted tokens)
~~~

### 12.2. JDBC Service Bean Example

~~~java
package com.example.security;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            DataSource dataSource,
            ClientRegistrationRepository registrations) {
        return new JdbcOAuth2AuthorizedClientService(
            new JdbcTemplate(dataSource),
            registrations);
    }
}
~~~

For the authenticated-user repository to actually delegate to this service, use/declare `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` appropriately. Explicit configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientRepositoryConfig {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            service);
    }
}
~~~

In applications with Spring Boot auto-configuration, service/repository beans may already exist. Never register duplicate beans or alter the active store without inspecting your current configuration. The snippets above illustrate **the components that work together**, not a requirement for every real project to copy every bean.

### 12.3. Schema and Secret Data

Spring Security provides a reference schema for the JDBC authorized client service. The table name is typically:

~~~text
oauth2_authorized_client
  client_registration_id
  principal_name
  access_token_type
  access_token_value
  access_token_issued_at
  access_token_expires_at
  access_token_scopes
  refresh_token_value
  refresh_token_issued_at
~~~

This is an **illustrative column list** for understanding the model, not a replacement for the official DDL of your Spring Security version. In production, use migrations matching your database/schema/column lengths, with an index/unique key on `client_registration_id + principal_name`, and consistent byte/token encoding.

The `access_token_value` and `refresh_token_value` columns hold **credentials**. You must:

- Restrict database privileges per least privilege.
- Encrypt sensitive data at rest when policy requires; manage keys separately and define a rotation lifecycle.
- Protect backups and replication.
- Never include tokens in SQL logs, tracing, or support dumps.
- Define clear retention/cleanup on disconnect or account deletion.
- Evaluate refresh token rotation protocols and concurrent writes from multiple instances.

**Never use database persistence as an excuse to skip revocation or audience/scope checks when calling APIs.**

## 13. Concurrency Issues When Refreshing and Updating Tokens

### 13.1. Two Requests Refreshing One Authorized Client Concurrently

Suppose an Access Token expires and two API requests arrive simultaneously:

~~~mermaid
sequenceDiagram
    autonumber
    participant R1 as Request A
    participant R2 as Request B
    participant DB as Authorized Client Store
    participant OP as Token Endpoint
    R1->>DB: Load old access/refresh token
    R2->>DB: Load same old token
    R1->>OP: Refresh with old refresh token
    R2->>OP: Refresh with old refresh token
    OP-->>R1: New access + rotated refresh token
    OP-->>R2: invalid_grant or other outcome per policy
    R1->>DB: Save new authorized client
~~~

When the provider **rotates single-use Refresh Tokens**, the second request may hit `invalid_grant`. Depending on failure-handler logic, an old refresh failure could even delete the record freshly updated by Request A if the system does not handle contention properly.

### 13.2. Handling Strategies

Approaches to evaluate based on scale:

1. **Let the default manager handle it** and observe actual behavior under concurrent load/refresh before building complex mechanisms.
2. If concurrency causes real failures, use a **single-flight/lock keyed by (registrationId, principalName)** during refresh, with a TTL and release mechanism if a node crashes.
3. With a database, consider optimistic locking/versioning or compare-and-swap to prevent a stale response from overwriting a new token.
4. When refresh fails with `invalid_grant`, check whether a newer record/token was already saved by another thread before deciding to delete or force reauthorization.
5. Never retry an old Refresh Token indefinitely.

**Never place a global lock across all users**, as that serializes every refresh operation. Any synchronization lock must be scoped appropriately to the authorized client while preserving isolation.

## 14. Storage Keys and Multi-Tenant Boundaries

### 14.1. Logical Key Pair

With the Service:

~~~text
registrationId + principalName -> OAuth2AuthorizedClient
~~~

Examples:

| registrationId | principalName | Meaning |
| --- | --- | --- |
| `company` | `employee-123` | User with company OIDC registration |
| `partner` | `employee-123` | User with partner registration, **not the same connection** |
| `calendar` | `employee-123` | Separate authorization to call calendar API |
| `service-reports` | `system-reports-job` | Service Client Credentials, not end-user login |

Two providers can issue the same `sub` to two different people. With OIDC, logical identity must consider **`issuer + subject`**, and registration IDs must have clear boundaries. In multi-tenant systems, an insufficiently namespaced principal name can lead to wrong token associations.

### 14.2. When principalName Changes

If the application switches how `Authentication.getName()` is derived from `sub` to email, the service may fail to find authorized clients stored under the old name.

Never "fix" this by broadly querying tokens by email or bypassing principal checks. Use a controlled migration strategy bound to verified identity.

### 14.3. Never Trust Arbitrarily Browser-Selected registrationId

If an endpoint accepts `registrationId` from a query/path parameter, validate:

- Is the user allowed to use this registration?
- Does the registration belong to the current tenant/feature?
- Is the token stored under the authenticated principal or another legitimately authorized account?
- Could guessing registration IDs leak token/tenant status?

A safe disconnect endpoint should use an allowlist of registrations or map from a business integration rather than blindly deleting any client ID supplied by the browser.

## 15. Logout, Disconnect, User Deletion: Separate Lifecycles

A user may:

- Log out of the application's HTTP session.
- Disconnect an OAuth2 integration.
- Have their account locked at the IdP.
- Delete their internal account.
- Request Refresh Token revocation.

These events **are not automatically synonymous**.

| Event | Impact the Application Must Decide |
| --- | --- |
| HTTP logout | SecurityContext/session ends, yet JDBC authorized client may still be stored |
| Disconnect an integration | Deletes that registration's authorized client; may revoke tokens |
| Delete internal user | Deletes all related authorized clients per data policy and locks internal user |
| IdP logout/SSO logout | May affect OP session; does not guarantee application authorized client records vanish |
| Refresh Token revoked | Subsequent refreshes will fail; handle reauthorization/cleanup |
| Access Token rejected by API | May be due to audience, scope, or expiration; does not automatically clear the entire user session |

For a pure OIDC login portal, whether to delete the authorized client on logout or keep it for other tasks is a **product and security decision**. If tokens permit API calls after logout, explicitly verify whether that is legitimate and expected by users.

**Never assume `logout()` automatically deletes all records in `JdbcOAuth2AuthorizedClientService`.** Deleting them requires an explicit policy and delete/revoke action.

## 16. Error Handling: Missing Token on Load, Refresh Failure, Store Unavailable

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `loadAuthorizedClient(...)` returns null after login | Wrong registration/principal name, different repository, or flow didn't save | Check store/Authentication/registration; do not assume token exists |
| Login works on one instance, request on another loses token | In-memory or local session only | Shared JDBC/session, or appropriate routing |
| Restart loses authorized clients | Store is in-memory | Use persistence if business requires surviving restarts |
| `getRefreshToken() == null` | Provider did not issue one or grant does not support it | Depending on flow, re-request authorization or acquire a new token |
| Access Token expired | Refresh/re-authorization has not run | Use `OAuth2AuthorizedClientManager` with right providers |
| Token endpoint returns `invalid_grant` | Refresh Token expired/revoked/rotated, or code/PKCE issue | Identify grant, handle per policy; never retry indefinitely |
| 401 from API though token appears unexpired client-side | Token revoked, wrong audience/issuer | Check API resource policy; may need refresh/re-auth |
| 403 from API | Missing scope/role/policy | Request right permissions and check Resource Server; do not edit token |
| Token stored in JDBC cannot be read | Schema/serialization/permissions/DB connection error | Check migrations, datasource, DB privileges, and data format |
| Refresh succeeds yet new token is not saved | Different manager success handler/repository | Check manager and active store; avoid overwriting with stale token |
| One refresh overwrites/deletes a new token written by another request | Concurrent refresh/rotation | Consider per-client synchronization or optimistic concurrency |
| Token remains in DB after logout | Logout does not automatically remove persistent authorized clients | Define disconnect/cleanup/revocation per policy |
| User A sees User B's API data | Wrong principal namespace or store query lacks full key | Enforce isolation by registration/principal/tenant; review security boundaries |

### 16.1. Debug Layer by Layer Without Skipping Steps

~~~text
API call fails
  |
  +-- Was the right client registration selected?
  |
  +-- Does Authentication/principalName match the current user?
  |
  +-- Does loadAuthorizedClient return a record or null?
  |
  +-- Is the Access Token expired / does it have the right scopes?
  |
  +-- Did AuthorizedClientManager refresh/re-authorize when needed?
  |
  +-- Was the new token saved to the same repository/service?
  |
  +-- Did the API return 401 or 403?
  |
  +-- Does the token match issuer, audience, and Resource Server policies?
~~~

**Never log `access_token` or `refresh_token` values** for "easier debugging". Use registration ID, error code, has-refresh-token boolean, rounded/categorized expiration time, and a credential-free correlation ID.

## 17. Security Issues to Resolve Before Production

### 17.1. Credential Protection

Access Tokens and especially Refresh Tokens are **secrets capable of granting access**. When storing authorized clients:

1. Protect the token store with least privilege; only required services may read it.
2. Encrypt tokens at rest when required or warranted by risk, and manage encryption keys separately.
3. Use TLS for the Token Endpoint, database network, and downstream APIs.
4. Never expose tokens in browser URLs, HTML, localStorage, or logs if using a confidential Servlet client architecture.
5. Never write raw `OAuth2AuthorizedClient` objects to application logs or serialize them into JSON responses.
6. Enforce retention periods, cleanup, and deletion when tokens are no longer needed.
7. Monitor token read/write/delete operations with safe audit metadata, without logging secrets.

### 17.2. Authorization to Delete and Retrieve Tokens

Endpoints viewing status or deleting an integration must verify **the currently signed-in user/tenant**. Never expose an API like:

~~~http
DELETE /authorized-clients?principalName=someone-else&registrationId=calendar
~~~

and delete tokens from input without authentication/authorization. If an admin feature must disconnect integrations on someone else's behalf, require controlled admin privileges and separate auditing.

### 17.3. Do Not Confuse ID Tokens with Access Tokens

With OIDC Login:

- **ID Token:** verifies identity at the OIDC client, with issuer/subject/audience and validation rules.
- **Access Token:** calls UserInfo or authorized Resource Servers.
- **Refresh Token:** obtains new tokens at the Token Endpoint; never sent to business APIs.

Never store an ID Token in place of an Access Token or use an ID Token as a Bearer token for an API merely because both may be JWTs. `OAuth2AuthorizedClient` is an object for storing **OAuth2 access/refresh tokens**, not a generic container for arbitrary JWTs.

### 17.4. A Valid Token Does Not Mean Blanket Permissions

Every Access Token carries a specific audience/scope/policy. When a client calls another API using a token issued for UserInfo, the API may return 401/403. Never try to work around this by granting roles at the portal or disabling Resource Server validation.

### 17.5. Never Trust Unverified Metadata

If the application stores an extra tenant or user ID alongside `OAuth2AuthorizedClient`, that data must derive from verified `Authentication` and issuer/subject, never directly from query parameters or unverified claims. A namespacing bug can be more severe than a token expiry bug because it causes cross-user data leakage.

## 18. Testing Save, Load, Update, and Remove Behavior

A test suite should separate **storage logic** from **token endpoint exchange**.

### 18.1. Unit Testing Service with the InMemory Implementation

Illustrative example creating an authorized client **using fake test tokens only**, never outside test environments:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

class AuthorizedClientStorageTest {

    @Test
    void saveLoadReplaceAndRemove() {
        ClientRegistration registration = ClientRegistration
            .withRegistrationId("calendar")
            .clientId("test-client")
            .clientSecret("test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://id.example.com/authorize")
            .tokenUri("https://id.example.com/token")
            .userInfoUri("https://id.example.com/userinfo")
            .userNameAttributeName("sub")
            .build();

        var registrations =
            new InMemoryClientRegistrationRepository(registration);
        var service =
            new InMemoryOAuth2AuthorizedClientService(registrations);

        Instant now = Instant.now();
        OAuth2AccessToken token1 = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "TEST_TOKEN_1",
            now,
            now.plusSeconds(300),
            Set.of("calendar.read"));

        OAuth2AuthorizedClient first =
            new OAuth2AuthorizedClient(registration, "user-1", token1);
        service.saveAuthorizedClient(first, "user-1");

        OAuth2AuthorizedClient loaded =
            service.loadAuthorizedClient("calendar", "user-1");
        assertNotNull(loaded);
        assertEquals("TEST_TOKEN_1", loaded.getAccessToken().getTokenValue());
        assertNull(service.loadAuthorizedClient("calendar", "user-2"));

        OAuth2AccessToken token2 = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "TEST_TOKEN_2",
            now,
            now.plusSeconds(600),
            Set.of("calendar.read"));
        OAuth2AuthorizedClient updated =
            new OAuth2AuthorizedClient(registration, "user-1", token2);
        service.saveAuthorizedClient(updated, "user-1");

        assertEquals(
            "TEST_TOKEN_2",
            service.loadAuthorizedClient("calendar", "user-1")
                .getAccessToken().getTokenValue());

        service.removeAuthorizedClient("calendar", "user-1");
        assertNull(service.loadAuthorizedClient("calendar", "user-1"));
    }
}
~~~

This test verifies the **in-memory storage contract**: save → load → replace record under the same key → remove. It **does not execute OAuth2 Authorization Code, does not verify OIDC tokens, and does not prove Token Endpoint refresh works**.

### 18.2. Integration-Level Tests

| Scenario | Objective |
| --- | --- |
| OAuth2/OIDC login succeeds | Authorized client is saved via the configured repository/service |
| Users A and B share a registration | Never returns A's token to B |
| User has two registrations | Removing registration A does not delete B |
| Restart an instance using JDBC | Record persists as long as DB retains data |
| Two instances share JDBC | Saved client can be loaded from the other instance |
| Access Token expired, valid Refresh Token present | Manager refreshes and updates authorized client under the right key |
| Refresh Token revoked | Handles failure/re-authorization per policy without infinite retries |
| Concurrent refresh rotation | Prevents old token from overwriting new token |
| Disconnect integration | Local record removed and revocation handled per contract |
| Application logout | Verifies actual policy for keeping/deleting authorized clients |
| HTTP POST disconnect missing CSRF token | Request rejected per CSRF policy |
| User guesses unauthorized registration ID | Cannot manipulate authorized clients outside their permissions |

Never use a mocked `OAuth2AuthorizedClient` to conclude ID Token validation or grant refresh works; those belong to separate test layers.

## 19. Real-World Scenarios

### Scenario A — Calling an API After Login

A user signs into a portal via OIDC registration `company`. The application needs to call an authorized profile API.

**Approach:** let Spring Security save the authorized client after login; load via `OAuth2AuthorizedClientRepository` or use a manager to obtain a suitable token; use the Access Token only for allowed endpoints. Never read the ID Token and pass it as an Access Token.

### Scenario B — Token Missing After Page Reload

`loadAuthorizedClient("company", authentication, request)` returns `null` after a browser reload.

**How to investigate:** check whether the user/Authentication changed, whether registration ID matches, whether the repository/service matches login, and whether the session was lost. Never mint a new token from browser parameters.

### Scenario C — Token Exists in DB Yet API Calls Fail

The JDBC service finds the Access Token, yet the API returns 401.

**Approach:** check token expiry, revocation, audience/resource, and scopes. If refresh is needed, use the configured manager; never assume "stored" equals "valid".

### Scenario D — User Clicks "Disconnect"

The user previously authorized calendar access and now wants to stop syncing.

**Approach:** call the revocation endpoint if supported and appropriate, delete the authorized client matching `registrationId + principalName`, and mark the integration disconnected. Never treat deleting the local record as an IdP logout.

### Scenario E — A Scheduled Job Needs a Service-Level Token

A backend job calls a reporting API via Client Credentials, with no browser session.

**Approach:** use `AuthorizedClientServiceOAuth2AuthorizedClientManager` together with `OAuth2AuthorizedClientService`. Bind the token to a clearly namespaced service principal key, rather than a repository requiring a Servlet request.

### Scenario F — User Changes Email

The application previously stored tokens by email. When the user changes email, old records can no longer be retrieved.

**Approach:** design a stable principal key based on a trusted identity source—for OIDC, pay attention to `iss + sub`; if migration is needed, match real accounts rather than scanning tokens by similar emails.

### Scenario G — User Has API Permissions Revoked at the Provider

The Access Token still exists in JDBC, yet the provider/Resource Server revoked access, causing 403 or token rejection.

**Approach:** do not grant extra scopes/roles inside the app to bypass it; handle insufficient permissions, prompt re-authorization where appropriate, or remove the link per policy.

### Scenario H — Two Requests Refresh Simultaneously

The provider rotates Refresh Tokens. Request A refreshes successfully; Request B uses the old Refresh Token and hits `invalid_grant`.

**Approach:** prevent competing refreshes with a per-client-scoped mechanism where needed, guard writes of the new token, and ensure error handling does not accidentally delete the newer record.

### Scenario I — Portal Logout Leaves Integration Token Intact

The application stores authorized clients in JDBC and the user clicks logout. After logging back in, the integration still shows "Connected".

**Approach:** this can be intentional behavior for persistent connections or a privacy risk. The product must decide whether tokens survive logout, support disconnect/revoke, and communicate the behavior clearly.

## 20. References

- Spring Security — Servlet OAuth 2.0 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Core Interfaces and Classes, Authorized Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — OAuth2AuthorizedClient Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html
- Spring Security — OAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html
- Spring Security — OAuth2AuthorizedClientRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — JdbcOAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Revocation (RFC 7009): https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 21. Key Takeaway: CRUD and Token Management Are Two Different Layers

~~~text
OAuth2/OIDC Authorization succeeds
  -> OAuth2AuthorizedClient
       ClientRegistration
       principalName
       accessToken
       refreshToken (if any)
  |
  +-- SAVE
  |     OAuth2AuthorizedClientRepository.saveAuthorizedClient(...)
  |     OAuth2AuthorizedClientService.saveAuthorizedClient(...)
  |
  +-- LOAD
  |     repository.loadAuthorizedClient(registrationId, auth, request)
  |     service.loadAuthorizedClient(registrationId, principalName)
  |
  +-- UPDATE
  |     Manager uses appropriate grant to acquire/refresh token
  |     -> saves new authorized client under the right key
  |
  +-- REMOVE
        repository.removeAuthorizedClient(...)
        service.removeAuthorizedClient(...)
        -> token may still need separate revocation at provider

Storage != refreshing tokens
Deleting local record != revoking token at provider
Browser logout != automatically deleting all persistent authorized clients
Token in store != valid token for every Resource Server
~~~

**Four operations to master:** **save** preserves authorization results for the right principal, **load** retrieves tokens by registration/principal, **update** persists a new token pair after a valid grant, and **remove** deletes client data when disconnecting. Spring Security provides abstractions for each responsibility; pick **repository for Servlet contexts**, **service for persistent/non-HTTP-request stores**, and **authorized client manager for acquisition/refresh logic**. Always protect credentials, distinguish user identity from client identity, and clearly design revocation and token lifecycles.
