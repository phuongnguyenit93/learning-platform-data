# 14.1. OAuth2AuthorizedClient and Linking Registration, Principal, and Token

## 1. Why Is OAuth2AuthorizedClient Needed?

In Spring Security OAuth 2.0/OIDC Client, knowing **which Authorization Server the application is registered with** is not enough to call a protected API. The application also needs to know **who granted authorization**, **which token was issued**, and which OAuth2 Client configuration that token belongs to.

For example, an enterprise portal has two users, An and Binh:

- The application has a ClientRegistration named <code>company</code> configured to sign in via an OpenID Provider.
- An signs in and receives an access token for An.
- Binh signs in via the same provider and receives an access token for Binh.
- An may also authorize another provider, such as <code>partner</code>.

If the application only kept a single global variable holding the "latest access token", An's request could accidentally use Binh's token. If it only stored tokens by provider name, users sharing the same provider could overwrite each other's tokens.

**<code>OAuth2AuthorizedClient</code>** is the object Spring Security uses to represent the association:

> **One ClientRegistration + one principalName + one access token + one optional refresh token.**

In the Authorization Code Flow, this object is typically created when the Client has successfully exchanged an authorization code for tokens. In the Client Credentials Flow, an authorized client can also be created even without an interactive End-User.

### Learning Objectives

After this lesson, learners can clearly explain:

1. How <code>ClientRegistration</code> and <code>OAuth2AuthorizedClient</code> differ.
2. How <code>principalName</code> is used when binding a token to a user or service.
3. Why access tokens/refresh tokens are different data from an ID Token.
4. How Spring Security stores, looks up, and refreshes an authorized client.
5. How to use an authorized client safely with Servlet OAuth2 Login and server-side jobs.
6. Common mistakes when multiple users, providers, or tenants share one application.

## 2. Data Model of OAuth2AuthorizedClient

~~~mermaid
flowchart TD
    R["ClientRegistration: company"] --> AC["OAuth2AuthorizedClient"]
    P["principalName: user-123"] --> AC
    AC --> AT["OAuth2AccessToken"]
    AC --> RT["OAuth2RefreshToken if issued"]
    AT --> ATD["tokenValue, tokenType, issuedAt, expiresAt, scopes"]
    RT --> RTD["tokenValue, issuedAt, expiresAt if present"]
    S["OAuth2AuthorizedClientService / Repository"] --> AC
~~~

Key accessor methods:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

OAuth2AuthorizedClient client = /* provided by Spring Security */;

ClientRegistration registration = client.getClientRegistration();
String principalName = client.getPrincipalName();
OAuth2AccessToken accessToken = client.getAccessToken();
OAuth2RefreshToken refreshToken = client.getRefreshToken(); // may be null
~~~

| Component | Meaning | What Not to Confuse It With |
|---|---|---|
| <code>clientRegistration</code> | Client configuration registered with the provider, grant type, endpoints, scopes | Not a user's token |
| <code>principalName</code> | Identifier name used to bind the authorized client to a principal | Not always an email or ID Token subject |
| <code>accessToken</code> | Credential used to call an API within the granted scope | Not to be used as an ID Token |
| <code>refreshToken</code> | Credential to request a new token if the provider/flow supports it | May be absent |

The <code>OAuth2AuthorizedClient</code> class resides in the <code>org.springframework.security.oauth2.client</code> package. It is a **model object**, not a repository or manager. Constructing this object yourself does not grant actual access at the Authorization Server.

### 2.1. ClientRegistration Represents the Application

<code>ClientRegistration</code> describes an OAuth 2.0 Client:

~~~text
registrationId: company
clientId:       rental-web
grantType:      authorization_code
issuer:         https://idp.example.org/realms/company
redirectUri:    {baseUrl}/login/oauth2/code/{registrationId}
scope:          openid, profile, api.read
~~~

The values in this example are placeholders; a real provider must supply the appropriate Client ID, endpoints, credentials, and policies.

ClientRegistration details can be shared across many users of the same application. **Access tokens must not be shared that way** when the token represents an individual user's authorization.

<code>registrationId</code> is an internal name chosen by the application; <code>clientId</code> is issued by the Authorization Server. The two values do not necessarily match.

### 2.2. principalName Represents the Context of the Authorized Client

With OAuth2 Login on Servlet, <code>principalName</code> is typically taken from <code>Authentication.getName()</code>. With the default OIDC User, it is usually based on the <code>sub</code> claim, though it can change if the application customizes the principal name.

Things to note:

- Do not assume <code>principalName</code> is an email address.
- Do not use a user's display name as a token key if it can collide or change.
- Do not let the browser send an arbitrary <code>principalName</code> for the backend to look up another user's token.
- When designing multi-tenant systems, avoid principal name collisions between two issuers/tenants.
- With client credentials, the principal name can be a string representing a **service**, rather than an End-User.

For example, an OIDC system may use the pair <code>(iss, sub)</code> as the external identity. If only <code>sub</code> is turned into the principal name and different issuers have the same subject, collision risks can arise in shared storage. Design internal identifiers consistently with the system's trust boundaries.

### 2.3. What Does an Access Token Contain?

<code>OAuth2AccessToken</code> contains the following information:

~~~java
OAuth2AccessToken token = client.getAccessToken();
OAuth2AccessToken.TokenType type = token.getTokenType();
String tokenValue = token.getTokenValue(); // sensitive
Instant issuedAt = token.getIssuedAt();
Instant expiresAt = token.getExpiresAt();
Set<String> scopes = token.getScopes();
~~~

An access token may be a JWT or an opaque string. **Do not assume it is always a JWT** or can always be decoded to read claims. The Resource Server is responsible for validating the token using the appropriate mechanism (JWT validation or introspection), along with audience, scope, expiry, and business authorization.

Do not log <code>getTokenValue()</code> or return it to the browser just for debugging.

### 2.4. Refresh Token Is Optional

<code>OAuth2RefreshToken</code> can contain the token value, issued timestamp, and expiration timestamp if provided:

~~~java
OAuth2RefreshToken refresh = client.getRefreshToken();

if (refresh != null) {
    // Only use through the appropriate OAuth2 Client component.
}
~~~

Not every Authorization Server issues a refresh token for every grant. For example, client credentials typically obtain a new access token using the grant itself without needing a refresh token.

Do not assume <code>getRefreshToken()</code> is always non-null, or that a token remaining in storage can definitely be refreshed.

## 3. The Key Pair (registrationId, principalName)

A very useful mental model is that authorized clients are managed in a two-dimensional context:

~~~text
(clientRegistrationId, principalName)
~~~

Illustrative table:

| registrationId | principalName | Access token | Refresh token |
|---|---|---|---|
| <code>company</code> | <code>an</code> | <code>AT-COMPANY-AN</code> | <code>RT-COMPANY-AN</code> |
| <code>company</code> | <code>binh</code> | <code>AT-COMPANY-BINH</code> | None |
| <code>partner</code> | <code>an</code> | <code>AT-PARTNER-AN</code> | <code>RT-PARTNER-AN</code> |

The token strings in the table are illustrative labels only, not real credentials.

**Same registration, different principal:** An and Binh use separate tokens.

**Same principal, different registration:** An can have separate tokens for each Client/provider.

**An authorized client does not by itself prove current permission:** The Resource Server still decides whether the token has sufficient audience, scope, and entitlement. A user may have internal permissions revoked while the token has not yet expired.

### 3.1. Why Not Store Tokens by Registration Only?

Dangerous pattern:

~~~java
Map<String, String> accessTokenByProvider = new HashMap<>();
accessTokenByProvider.put("company", tokenValue);
~~~

If a singleton or static map is shared across all sessions, Binh's token can overwrite An's token. Afterwards, a request from An risks calling the API on Binh's behalf.

Spring Security provides authorized-client storage to address most needs for binding tokens to principals. The application must use it properly and ensure principal keys do not collide.

### 3.2. One User Can Have Multiple Authorized Clients

For example, An is allowed to use two providers:

~~~text
An + company = OAuth2AuthorizedClient A
An + partner = OAuth2AuthorizedClient B
~~~

The two authorized clients may have different endpoints, client IDs, issuers, scopes, audiences, and token lifetimes. Do not send provider A's token to provider B's API just because they share the same <code>principalName</code>.

### 3.3. principalName Is Not Necessarily a Globally Unique Internet Identity

<code>OAuth2AuthorizedClient.principalName</code> is a value used to store/access the authorized client within the application. It is not an automatic replacement for the OIDC <code>(iss, sub)</code> rule.

When users come from multiple issuers, the application should use a normalized, collision-free principal name with clear identity binding. The same name <code>user123</code> across two tenants does not implicitly mean the same person.

## 4. Creating an Illustrative OAuth2AuthorizedClient in Java

The constructor takes the Client configuration, principal name, and access token; a refresh token is provided if present.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

ClientRegistration registration = /* configuration created elsewhere */;

Instant now = Instant.now();
OAuth2AccessToken access = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "demo-access-token",
    now,
    now.plus(30, ChronoUnit.MINUTES),
    Set.of("profile.read"));

OAuth2RefreshToken refresh = new OAuth2RefreshToken(
    "demo-refresh-token",
    now);

OAuth2AuthorizedClient authorizedClient = new OAuth2AuthorizedClient(
    registration,
    "user-123",
    access,
    refresh);
~~~

This code snippet illustrates **object structure**, not instructions for minting fake tokens for production use. In practice, tokens come from the Token Endpoint after a valid grant and must be handled by OAuth2 Client components. Hardcoded token strings like the ones above have no validity to an Authorization Server.

If there is no refresh token, the application can still create an authorized client with a null refresh token or use the appropriate constructor for the API version. Only put real token data into protected storage.

### 4.1. Access Tokens Change Upon Refresh

A stored authorized client may hold an expired access token. When the manager refreshes successfully, the new token needs to be saved as an updated authorized client.

Do not hold an <code>OAuth2AuthorizedClient</code> reference in a singleton for hours and expect the old object to update its token automatically when another instance refreshes. Re-query the appropriate state or use <code>OAuth2AuthorizedClientManager</code>.

## 5. Lifecycle When Signing In with OIDC Authorization Code

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant C as Spring Security Client
    participant OP as OpenID Provider
    participant S as Authorized Client Storage
    participant API as Resource Server
    U->>C: GET /oauth2/authorization/company
    C-->>U: 302 to OP with state and PKCE where applicable
    U->>OP: User signs in
    OP-->>U: Callback with authorization code and state
    U->>C: GET /login/oauth2/code/company
    C->>C: Look up authorization request and verify state
    C->>OP: POST /token
    OP-->>C: Access token, refresh token if any, ID Token if OIDC
    C->>C: Verify ID Token and build Authentication
    C->>S: Save OAuth2AuthorizedClient
    C-->>U: Login success / session
    U->>C: GET /my/data
    C->>S: Look up matching registration and principal
    S-->>C: OAuth2AuthorizedClient
    C->>API: Bearer access token with proper audience and scope
    API-->>C: Resource response
    C-->>U: Application result
~~~

Three points in time to distinguish:

**Before callback:** Spring Security holds an <code>OAuth2AuthorizationRequest</code> containing state, redirect URI, and PKCE data. It is usually stored by <code>HttpSessionOAuth2AuthorizationRequestRepository</code>. This is **not yet** an authorized client.

**When token exchange succeeds:** The Client has received an access token and possibly a refresh token. Spring Security creates an <code>OAuth2AuthorizedClient</code> binding the registration to the principal.

**In subsequent requests:** Spring Security retrieves the authorized client and uses the current access token (or refreshes according to configuration) to call the API.

### 5.1. OAuth2AuthorizedClient Differs from OidcUser

After OIDC Login:

~~~text
Authentication / SecurityContext
  └── principal: OidcUser
        ├── Verified ID Token
        ├── UserInfo if present
        └── GrantedAuthorities

OAuth2AuthorizedClient
  ├── ClientRegistration
  ├── principalName
  ├── OAuth2AccessToken
  └── OAuth2RefreshToken if present
~~~

<code>OidcUser</code> tells the application **who the authenticated user is**. <code>OAuth2AuthorizedClient</code> tells the Client **which tokens were issued in that principal's context**.

Do not look for the ID Token via <code>OAuth2AuthorizedClient.getAccessToken()</code>. ID Tokens and access tokens serve different purposes.

### 5.2. Comparison Table of Token Types

| Token | Purpose | Where Is It Used? |
|---|---|---|
| ID Token | Proves authentication to the OIDC Client | Spring Security verifies the ID Token and builds <code>OidcUser</code> |
| Access token | Grants access to a Resource Server within the granted scopes | Client sends it to the target API |
| Refresh token | Requests a new access token if the Authorization Server supports it | Client sends it to the Token Endpoint |

Do not turn an ID Token into a bearer token for arbitrary APIs; likewise, do not send a refresh token in API requests.

## 6. OAuth2AuthorizedClientService: Storing by Registration and Principal

The <code>OAuth2AuthorizedClientService</code> interface has the following core APIs:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName);
~~~

The service is suited for use cases that do not necessarily require an <code>HttpServletRequest</code> to read token data.

Example of looking up a token for an authenticated user:

~~~java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedClientLookup {

    private final OAuth2AuthorizedClientService service;

    public AuthorizedClientLookup(OAuth2AuthorizedClientService service) {
        this.service = service;
    }

    public OAuth2AuthorizedClient findForCurrentUser(
            Authentication authentication) {

        if (authentication == null || !authentication.isAuthenticated()) {
            throw new IllegalArgumentException("Authentication required");
        }

        return service.loadAuthorizedClient(
            "company",
            authentication.getName());
    }
}
~~~

When no matching authorized client exists, <code>loadAuthorizedClient</code> can return <code>null</code>. Do not fabricate an access token or fall back to another user's token as a "workaround".

**Important:** Do not let the browser choose an arbitrary <code>principalName</code> via a query parameter to call a load API. For End-User-bound tokens, obtain the principal from a trusted <code>Authentication</code> and enforce authorization.

### 6.1. InMemoryOAuth2AuthorizedClientService

Spring Security provides an in-memory implementation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {
    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
~~~

This bean snippet only illustrates explicit configuration. If Spring Boot already provides the service via auto-configuration, do not arbitrarily declare an extra duplicate bean.

Characteristics:

- Easy to use for prototypes or single-instance applications.
- Token data in memory is lost after a restart.
- Other instances do not automatically see tokens stored by the current instance.
- Does not itself guarantee refresh token or session lifetime.

**<code>InMemoryOAuth2AuthorizedClientService</code> differs from <code>InMemoryClientRegistrationRepository</code>**. One stores issued tokens; the other only holds Client registration configuration.

### 6.2. Storage with JDBC

Spring Security also supports <code>JdbcOAuth2AuthorizedClientService</code> for cases requiring persistent storage. In production, you must consider:

1. Protecting access/refresh tokens with database permissions, encryption-at-rest, and/or application-level encryption depending on the threat model.
2. Restricting who can read token data and avoiding overly broad database privileges.
3. Having a cleanup policy when a user logs out, unlinks a provider, is locked, or no longer needs authorization.
4. Handling refresh concurrency when multiple nodes might update the same authorized client.
5. Preventing token values from leaking into logs, unprotected backups, or support systems.

Switching to JDBC preserves data across restarts, but does not automatically make it more secure or guarantee tokens remain valid.

## 7. OAuth2AuthorizedClientRepository: Storing in Servlet Context

For Servlet web requests, Spring Security provides the interface:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
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

The <code>HttpServletRequest</code>/<code>HttpServletResponse</code> classes belong to <code>jakarta.servlet.http</code> in Spring Boot 3/Spring Security 6.

The repository receives request/response and Authentication so it can choose a storage mechanism appropriate for the session or user.

Spring Security includes implementations such as:

- <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code>: can use a service to store authorized clients for an authenticated principal.
- <code>HttpSessionOAuth2AuthorizedClientRepository</code>: stores authorized clients in the HTTP session.

The specific choice depends on configuration and Spring Security/Spring Boot version; you should not assume all tokens are only stored in HttpSession.

### 7.1. Comparing Service and Repository

| Characteristic | OAuth2AuthorizedClientService | OAuth2AuthorizedClientRepository |
|---|---|---|
| Lookup by | registration ID + principalName | registration ID + Authentication + HTTP request |
| Depends on Servlet request | No | Yes |
| Typical usage | Service layer, background process, storage | OAuth2 Login, Servlet request |
| Example implementations | InMemory, JDBC | HTTP session or delegate to service |
| Automatically refreshes tokens? | No | No |

**Storage is not a token manager.** Both interfaces primarily handle saving/reading/removing authorized clients; refresh or re-authorization logic belongs to the appropriate providers/managers.

### 7.2. Do Not Confuse the Three Repositories

| Component | What Does It Hold? | Phase |
|---|---|---|
| <code>ClientRegistrationRepository</code> | Client ID, grant type, endpoints, scopes, issuer | Configuration before/between flows |
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | Pending authorization request awaiting callback, state, PKCE attributes | Before and during callback |
| <code>OAuth2AuthorizedClientRepository</code> | Authorized client containing access/refresh tokens | After token exchange |

In particular, **AuthorizationRequestRepository does not store refresh tokens after login**; it holds data to correlate the authorization response.

## 8. Configuring OIDC Login and Accessing the Authorized Client

Example with Spring Boot 3/Spring Security 6 Servlet.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 8.2. Registering the Client

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: rental-web
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Values here are examples only. <code>api.read</code> must be a scope actually accepted and issued by the Authorization Server for the API; the client secret should come from environment/secret manager, never committed to source control.

### 8.3. Enabling Login/Client

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

<code>oauth2Login()</code> supports Servlet sign-in; <code>oauth2Client()</code> provides supporting components when the application acts as an OAuth2 Client and needs tokens to call APIs. If the application only performs login, both are not always required.

### 8.4. Receiving the Authorized Client in a Controller

The <code>@RegisteredOAuth2AuthorizedClient</code> annotation allows a controller to request the authorized client for the right registration in the current user's context:

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientInfoController {

    @GetMapping("/my/authorized-client")
    public Map<String, Object> info(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient) {

        return Map.of(
            "registrationId",
            authorizedClient.getClientRegistration().getRegistrationId(),
            "hasRefreshToken",
            authorizedClient.getRefreshToken() != null,
            "hasKnownExpiry",
            authorizedClient.getAccessToken().getExpiresAt() != null
        );
    }
}
~~~

The controller only returns **metadata**, not token values or refresh tokens. If there is no authorized client and the resolver cannot authorize according to configuration, the request may fail; the application should handle this appropriately instead of assuming every registration has a token.

The annotation does not mean the server will grab an arbitrary user's token for the same registration: resolution is based on the authenticated principal/request context.

### 8.5. Using the Access Token to Call an API

Suppose the API <code>https://api.example.org/v1/me</code> is configured to **accept access tokens with matching audience/scope** from the provider:

~~~java
package example.web;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class DownstreamProfileController {

    private final RestClient api;

    public DownstreamProfileController(RestClient.Builder builder) {
        this.api = builder.baseUrl("https://api.example.org").build();
    }

    @GetMapping("/my/remote-profile")
    public String remoteProfile(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient) {

        String token = authorizedClient.getAccessToken().getTokenValue();

        return api.get()
            .uri("/v1/me")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
~~~

This snippet uses <code>RestClient</code> (Spring Framework 6.1+/Spring Boot 3.2+) and only demonstrates a backend calling an API. In production, DTOs, timeouts, error handling, response size limits, and appropriate data policies are required.

If an access token is only meant for the UserInfo Endpoint, **do not send it to another business API**. Having an access token does not mean it has the right audience/scope for every Resource Server.

## 9. OAuth2AuthorizedClientManager and Token Lifecycle

<code>OAuth2AuthorizedClientManager</code> is a higher-level abstraction that coordinates registration, storage, and providers to **authorize** or **refresh** when allowed by the configured grant.

~~~java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizeRequest authorizeRequest);
~~~

Responsibilities:

1. Find the ClientRegistration by registration ID.
2. Find the current authorized client in the principal's context.
3. Select the appropriate <code>OAuth2AuthorizedClientProvider</code>.
4. Issue a token or refresh if conditions allow.
5. Save the new authorized client state on success.
6. Handle errors according to the manager/handler's policy.

Common providers include authorization code, refresh token, and client credentials; not every grant is enabled by default in every manager.

### 9.1. Web Manager vs. Service Manager

| Class | Context |
|---|---|
| <code>DefaultOAuth2AuthorizedClientManager</code> | Servlet HTTP request, uses OAuth2AuthorizedClientRepository |
| <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> | Service/background, does not require Servlet request, uses OAuth2AuthorizedClientService |

Do not use a manager that depends on HTTP requests in a background job without a request/response. For periodic client credentials jobs, use the service manager.

### 9.2. Client Credentials Example Without an End-User

Registration configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          billing-service:
            provider: company
            client-id: billing-worker
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [billing.read]
        provider:
          company:
            token-uri: https://idp.example.org/oauth2/token
~~~

Manager bean:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class WorkerClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager workerAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        var provider = OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Code to obtain the token:

~~~java
package example.jobs;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class BillingAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public BillingAccessTokenProvider(
            OAuth2AuthorizedClientManager workerAuthorizedClientManager) {
        this.manager = workerAuthorizedClientManager;
    }

    public String accessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest.withClientRegistrationId("billing-service")
                .principal("billing-worker-runtime")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException("Client cannot be authorized");
        }
        return client.getAccessToken().getTokenValue();
    }
}
~~~

<code>billing-worker-runtime</code> is a **synthetic principal** used to partition storage. A token issued via client credentials represents the **Client/service**, and does not mean it is acting on behalf of a signed-in End-User.

If the system has multiple tenants/workloads, do not default to sharing one synthetic principal and token across all of them when policy requires isolation; design namespaces by tenant, registration, and granted permissions.

## 10. Expired Access Tokens, Refresh, and Storage State

### 10.1. An Authorized Client Can Exist After Its Token Expires

Example:

~~~text
registrationId=company
principalName=an
accessToken.expiresAt=10:00
now=10:05
refreshToken=available
~~~

The authorized client may still reside in storage even though the access token has expired. If the manager has a refresh-token provider and the refresh token is accepted by the OP, the manager can obtain a new access token and save the updated authorized client.

If there is no refresh token, or it is expired/revoked, the user may need to sign in/re-authorize. Do not mint a new token from local data.

### 10.2. Refresh Tokens Are Not Always Issued

- With OAuth2 authorization code, whether a refresh token is issued depends on OP and registration policy.
- Some OPs require a scope like <code>offline_access</code> to grant offline access, though not all providers behave identically.
- With client credentials, a new token can normally be requested via the client credentials grant itself without needing a refresh token.

Code calling <code>getRefreshToken()</code> must accept a <code>null</code> value.

### 10.3. Refresh Token Rotation and Concurrent Races

Multiple requests may read the same nearly-expired authorized client and attempt to refresh concurrently. If the provider uses **refresh token rotation**, the first request may invalidate the old refresh token; the second request using the same refresh token may receive <code>invalid_grant</code>.

For multi-node deployments, an appropriate synchronization/locking/optimistic concurrency strategy or safe failure handling is needed. A lock within a single JVM does not protect the entire cluster.

Managers/handlers may remove the authorized client from storage upon certain refresh errors, such as <code>invalid_grant</code>. Therefore, do not assume the old record always remains after an error.

### 10.4. Expiry Does Not Guarantee API Permission

An unexpired access token is not guaranteed to be accepted by the Resource Server: the token may be revoked, have the wrong audience, lack scopes, or belong to a locked user. The application must handle 401/403 from the target API instead of blindly retrying with an unsuitable token.

## 11. Logout, Removing the Authorized Client, and Token Revocation

Logging out of an HTTP session, deleting a local authorized client, and revoking a token at the Authorization Server are three **separate** actions.

~~~text
09:00 User signs in → token saved in JDBC
09:20 User logs out → session ends
09:21 Token in JDBC may still remain without separate cleanup
~~~

Do not assume logout automatically deletes all persistent authorized clients or revokes all access/refresh tokens at the provider.

Example of deleting local data for the matching principal:

~~~java
authorizedClientService.removeAuthorizedClient(
    "company",
    authentication.getName());
~~~

This call **only deletes local storage** of the invoked service. Revoking tokens at the Authorization Server requires a dedicated revocation mechanism when supported by the provider (per RFC 7009 or provider documentation).

For locked users or revoked roles, session invalidation, authorized-client cleanup, token revocation, and entitlement checks at the Resource Server may all be needed. A remaining stored <code>OAuth2AuthorizedClient</code> does not mean the user is still permitted access.

## 12. Safety Across Multiple Users, Issuers, Providers, and Tenants

### 12.1. Do Not Store Tokens in Static Fields

Broken privilege partitioning:

~~~java
public class GlobalTokenHolder {
    public static String accessToken;
}
~~~

A later user's token will overwrite an earlier user's token. Use authorized-client storage bound to the proper registration and principal.

### 12.2. Do Not Forward Access Tokens to a Resource Server with the Wrong Audience

Having an authorized client with a token for API A does not mean that token can be used for API B. Each token must be issued for the appropriate Resource Server with the right scope and audience; the target API must validate the token itself.

### 12.3. Do Not Let the Browser Choose an Arbitrary Principal

Unsafe endpoint pattern:

~~~text
GET /internal/token?principal=another-user
~~~

If the backend passes this query directly into <code>loadAuthorizedClient(registrationId, principalName)</code>, it can expose another user's credentials. Queries for End-User-bound tokens must originate from a verified <code>Authentication</code> and internal authorization.

### 12.4. Principal Names Can Collide Across Issuers

If issuers A and B both use subject <code>12345</code>, using only principalName <code>12345</code> in shared storage can cause collisions when registration IDs are reused or mapping rules lack namespacing.

To prevent this:

- Verify both the issuer and subject of the OIDC identity.
- Use a stable, collision-free principal key scoped to tenant/issuer per your architecture.
- Do not automatically link two accounts based solely on email.
- Ensure service, repository, and manager agree on the principal key when saving/loading.

### 12.5. Do Not Confuse Login Authentication with Business Authorization

Access tokens, OIDC principals, and internal roles serve different purposes. A user with a valid OIDC Login may not have administrative rights. The Resource Server or domain service must enforce authorization, not merely check that an OAuth2AuthorizedClient exists.

## 13. Storing Tokens Safely in Production

An authorized client stores access tokens and possibly refresh tokens, so storage must be treated as a credential store.

| Risk | Appropriate Mitigation |
|---|---|
| Token leaked via logs | Never log <code>getTokenValue()</code>, raw token responses, or Authorization headers |
| Token read from database | Restrict privileges, encryption-at-rest, auditing, backup protection |
| Token sent to browser | Return only business results; keep tokens on backend if using a confidential server-side Client |
| Token used on wrong API | Enforce audience/scope, Resource Server validation |
| Token lives too long | Cleanup, TTL, revocation, and retention policies |
| Token mixed across users/tenants | Proper storage keys/namespaces and Authentication enforcement |
| Concurrent refresh | Concurrency design suited for refresh token rotation |

Safer telemetry might include:

~~~text
registrationId=company
authorizedClientFound=true
hasRefreshToken=true
accessTokenExpiresSoon=true
refreshResult=success
~~~

Never log client secrets, access tokens, refresh tokens, authorization codes, PKCE verifiers, callback queries containing code/state, or the entire authorized client object.

## 14. Common Issues

| Symptom | Common Cause | Resolution |
|---|---|---|
| <code>loadAuthorizedClient</code> returns null | Wrong registration/principal, not yet authorized, or token was removed | Verify key and lifecycle |
| Login succeeds but service cannot find token | Repository uses different storage or principal name mismatch | Check wiring and <code>Authentication.getName()</code> |
| User A's token used for user B | Cache keyed only by provider or self-declared principal | Use authenticated storage and principal |
| API returns 401 | Token expired, wrong issuer/audience, or revoked | Check token and Resource Server config |
| API returns 403 | Insufficient scope/permissions | Check authorization, not just token expiry |
| <code>getRefreshToken()</code> is null | Provider did not issue a refresh token | Design flow without relying on refresh |
| Refresh fails with <code>invalid_grant</code> | Refresh token expired, reused, or revoked | Clear bad state, re-authorize if appropriate |
| Tokens lost after restart | In-memory service | Use persistent service if required |
| Only one node can read token | Token lives in another node's memory | Use shared storage or proper session/routing design |
| Job outside web request fails | Using web manager without a Servlet request | Use service manager |
| Token remains in DB after logout | Missing cleanup/revocation policy | Remove authorized client and revoke token if needed |
| Same principal gets another tenant's token | Key does not distinguish issuer/tenant | Design proper namespaces and identity mapping |
| Code still uses old token after refresh | Holding reference too long | Fetch current token via manager/storage |

### 14.1. Diagnostic Workflow

~~~text
Does ClientRegistration exist?
  └── Is registrationId correct?
       └── Does principalName match Authentication?
            └── Which storage is Service/Repository using?
                 └── Does OAuth2AuthorizedClient exist?
                      └── Is the access token still valid?
                           ├── Yes → check audience/scope/Resource Server
                           └── No → is refresh/authorize supported?
                                         └── was storage updated?
~~~

Do not print token values during investigation. Use registration ID, error type, token presence flags, expiry, and safe correlation IDs.

## 15. Practice Exercises

### Exercise 1 — Determine the Number of Authorized Clients

The system has:

~~~text
(company, an)
(company, binh)
(partner, an)
~~~

**Question:** At least how many independent authorized client associations are needed?

**Explanation:** Three. Same provider with different principals requires separate tokens; same principal with different providers is also a separate authorized client.

### Exercise 2 — Does OAuth2AuthorizedClient Contain the ID Token?

A controller needs to display the signed-in user's subject, issuer, and name. A service needs an access token to call an API.

**Explanation:** Obtain OIDC identity from the verified <code>OidcUser</code>/<code>OidcIdToken</code>; obtain the access token from the <code>OAuth2AuthorizedClient</code> matching the registration/principal. Do not use an access token as an ID Token.

### Exercise 3 — Null Refresh Token

An authorized client already has an access token, but <code>getRefreshToken() == null</code>. The access token is about to expire.

**Explanation:** This can be a valid state. Do not attempt to call <code>getRefreshToken().getTokenValue()</code>. Use a manager with a supported provider/grant or prompt the user to re-authorize depending on the flow.

### Exercise 4 — Background Job

A job uses client credentials to fetch a daily report; there is no user session or HttpServletRequest.

**Explanation:** <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> with the <code>clientCredentials()</code> provider and a stable synthetic principal is more appropriate than a web manager requiring an HTTP request. A synthetic principal does not turn a service token into a user token.

### Exercise 5 — Token Remains After Logout

Tokens are stored in JDBC. The user logs out from the web app.

**Explanation:** You cannot conclude the token was revoked at the OP or deleted from the database. Session logout, local cleanup, and token revocation are separate operations.

### Exercise 6 — Token with Wrong Audience

The Client takes an access token issued for API A and uses it to call API B.

**Explanation:** Avoid doing this. API B may reject it due to a different audience/scope/issuer. Obtain a token with valid permissions intended for API B and let the Resource Server validate it.

### Exercise 7 — Hands-On Lab

1. Create an OIDC ClientRegistration with a valid issuer, Client ID, secret, and scopes.
2. Enable <code>oauth2Login()</code> and sign in with a test user.
3. Inject <code>OAuth2AuthorizedClientService</code> or use <code>@RegisteredOAuth2AuthorizedClient</code> in a controller.
4. Observe the registration ID, principalName, access token expiration, and refresh token presence, **without printing token values**.
5. Sign in with another user; compare lookup results by principal.
6. Try restarting when using in-memory storage and compare with persistent storage policy if available.
7. Observe refresh/authorize behavior through the manager according to the configured grant.

## 16. Key Takeaways

- <code>OAuth2AuthorizedClient</code> binds a **ClientRegistration**, **principalName**, **OAuth2AccessToken**, and **optional OAuth2RefreshToken**.
- <code>ClientRegistration</code> stores **Client registration configuration**, not individual user tokens.
- The <code>(registrationId, principalName)</code> pair is the foundation for distinguishing authorized clients in default services. Principal keys must be consistent, never arbitrarily supplied by the browser, and collision-free across tenants.
- <code>OAuth2AuthorizedClientService</code> manages authorized clients by registration/principal; <code>OAuth2AuthorizedClientRepository</code> serves Servlet request contexts.
- <code>OAuth2AuthorizedClientManager</code> coordinates providers and storage to authorize or refresh when conditions/grants allow. Merely reading a token from the service does not automatically refresh it.
- The OIDC ID Token primarily belongs to <code>OidcUser</code>; the authorized client holds access/refresh tokens for calling Resource Servers with the proper audience/scope.
- In-memory storage does not persist across restarts or share across multiple instances; persistent storage requires credential protection and lifecycle management.
- Logout, local authorized client deletion, and token revocation are separate mechanisms. Never log token values or return them to the browser.

### References

- **Spring Security Reference — OAuth2 Client:** OAuth2AuthorizedClient, ClientRegistration, Authorized Client Service/Repository, and Authorized Client Manager.
- **Spring Security Reference — OAuth2 Login (Servlet):** Authorization Code Flow, callback, and authorized-client persistence.
- **Spring Security Java API:** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, <code>OAuth2AuthorizedClientManager</code>, <code>OAuth2AuthorizeRequest</code>.
- **Spring Security Java API:** <code>InMemoryOAuth2AuthorizedClientService</code>, <code>JdbcOAuth2AuthorizedClientService</code>, <code>DefaultOAuth2AuthorizedClientManager</code>, <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Client, Access Token, Refresh Token, Authorization Code, and Client Credentials Grants.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoking tokens at the Authorization Server.
- **OpenID Connect Core 1.0:** ID Token, Authorization Code Flow, and the relationship between OIDC and OAuth2 Token Responses.
