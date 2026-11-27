# 5.6. `ClientRegistrationRepository` in Servlet Applications

## 1. Role of `ClientRegistrationRepository`

In a **Spring Boot application using Spring MVC/Servlet**, Spring Security can act as an **OAuth 2.0 Client** to authenticate users through an Authorization Server or OpenID Provider (OIDC), and then use access tokens to call APIs on the user's behalf. Before starting the login flow, the application must know **which clients are registered**, **which provider serves each client**, **the redirect address**, and **the scopes to request**.

Spring Security represents an OAuth 2.0 Client configuration with a **`ClientRegistration`** object. The component that stores and looks up these objects is **`ClientRegistrationRepository`**.

Picture an application that allows login via enterprise SSO and another identity provider:

~~~text
                    Spring Boot Application (Servlet)
                                  |
                                  v
                     ClientRegistrationRepository
                           /               \
                          v                 v
               registrationId=corp    registrationId=partner
                      |                      |
                      v                      v
                  Corporate IdP          Partner IdP
                  (OIDC Provider)        (OIDC Provider)
~~~

Each registration holds the corresponding client and provider metadata; the repository identifies a registration by a **`registrationId`** recognized by Spring Security.

Three key points to grasp immediately:

- **`ClientRegistration`** describes *one OAuth2/OIDC Client configuration*.
- **`ClientRegistrationRepository`** provides lookup of configurations by `registrationId`.
- **`InMemoryClientRegistrationRepository`** is a built-in implementation, usually sufficient for applications with a fixed set of clients.

This repository is **not** a user account database, **does not store login sessions**, and **is not a store for access tokens/refresh tokens**. Those data are managed by other components.

## 2. What Does `ClientRegistration` Contain?

`ClientRegistration` is a configuration object provided by Spring Security in package:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistration
~~~

A typical registration contains the following information:

| Property | Role |
|---|---|
| `registrationId` | Unique internal identifier in the repository; e.g., `corp` or `google`. |
| `clientId` | Application ID registered at the Authorization Server. |
| `clientSecret` | Secret for confidential clients if issued and required by the provider. |
| `clientAuthenticationMethod` | How the client authenticates with the token endpoint, e.g., `client_secret_basic` or `client_secret_post`. |
| `authorizationGrantType` | Grant type; for user login, typically `authorization_code`. |
| `redirectUri` | Callback URI template so the Authorization Server returns the browser to the client. |
| `scopes` | Set of scopes to request, e.g., `openid`, `profile`, `email`, or API scopes. |
| `authorizationUri` | Provider's authorization endpoint. |
| `tokenUri` | Token endpoint for exchanging an authorization code for tokens. |
| `jwkSetUri` | Location publishing the JWK Set, typically used to verify JWT/ID Token signatures. |
| `issuerUri` | Issuer identifier of the OIDC Provider, used to bind the issuing source. |
| `userInfoUri` | OIDC UserInfo endpoint when supported by the provider. |
| `userNameAttributeName` | Claim/attribute used as the principal identifier name in the corresponding context. |
| `clientName` | Display name of the registration; typically used for login selection links. |

Not every provider supports every endpoint or scope. Configuration must reflect the provider's **actual** metadata and client registration conditions. With OIDC, the `openid` scope marks the request as an OIDC login and makes the ID Token part of the authentication result.

### 2.1. Distinguishing `registrationId`, `clientId`, and Issuer

Three easily confused identifiers:

~~~text
registrationId : corp
clientId       : web-portal-production
issuerUri      : https://identity.example.com/realms/employees
~~~

- `registrationId = corp` is chosen by the **Spring Security application** to reference the configuration. It appears in the application's default URLs such as `/oauth2/authorization/corp`.
- `clientId = web-portal-production` is issued by the **Authorization Server** during OAuth2 Client registration. It is sent in authorization requests and participates in client authentication steps.
- `issuerUri` identifies the trusted **OpenID Provider**; the ID Token's issuer must match the corresponding configuration.

They may happen to share the same string in a specific case, yet fundamentally serve three distinct roles. Changing `registrationId` in Spring without updating login and callback paths can prevent the login flow from locating the right client registration.

### 2.2. One Provider Can Have Multiple Client Registrations

For example, an application has two different clients on the same OIDC Provider:

| registrationId | clientId | Scope | Purpose |
|---|---|---|---|
| `employee-login` | `employee-web` | `openid profile email` | Employee login. |
| `admin-login` | `admin-web` | `openid profile email` | Login via a client dedicated to administrators. |

Both may share the same issuer and endpoints while differing in client ID, redirect URI, policy, or scope. Therefore **the repository stores client registrations**, not merely a list of provider names.

Conversely, multiple distinct providers can be declared in the same repository, each corresponding to one or more registrations.

## 3. Contract of `ClientRegistrationRepository`

The `ClientRegistrationRepository` interface belongs to package:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistrationRepository
~~~

Core contract:

~~~java
public interface ClientRegistrationRepository {
    ClientRegistration findByRegistrationId(String registrationId);
}
~~~

When Spring Security needs the configuration for registration `corp`, it calls:

~~~java
ClientRegistration registration =
    clientRegistrationRepository.findByRegistrationId("corp");
~~~

If a matching registration exists, the repository returns the `ClientRegistration` object. If not, the method may return `null`; calling code must handle the not-found case. The interface does not mandate add/update/delete operations for registrations, nor does it require configurations to live in a database.

### 3.1. Why Only Look Up by `registrationId`?

In a typical authorization code flow:

1. The user visits `/oauth2/authorization/corp`.
2. Spring Security extracts `corp` as the `registrationId`.
3. The system calls `ClientRegistrationRepository.findByRegistrationId("corp")`.
4. The registration supplies `clientId`, authorization endpoint, scopes, callback template, and required fields.
5. Spring Security builds the authorization request and redirects the browser to the provider.
6. When the callback returns, the flow continues using data from that same registration to exchange the code.

In practice, Spring Security also saves the authorization request and validates `state`, PKCE, and related protocol conditions. `ClientRegistrationRepository` is responsible solely for **the client configuration part** of the overall process.

### 3.2. The Repository Exists at the Application Level, Not Per User

Registrations such as `corp` or `partner` are normally declared at application startup and shared across different login requests. User A and User B can both sign in via the same registration while still having **separate login sessions and tokens**. The repository does not create a `ClientRegistration` copy per user.

## 4. `InMemoryClientRegistrationRepository`

Spring Security includes a basic implementation:

~~~java
org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository
~~~

`InMemoryClientRegistrationRepository` keeps `ClientRegistration` instances in the application process's memory and looks them up by `registrationId`. It is a suitable choice when:

- The application has one or a few known OAuth2/OIDC providers.
- The registration list changes mainly through configuration and deployments.
- Dynamic registration administration while the application is running is not required.
- Client secrets can be protected via environment variables and a secret management system.

Example initialization from two constructed registrations:

~~~java
ClientRegistrationRepository repository =
    new InMemoryClientRegistrationRepository(corpRegistration, partnerRegistration);
~~~

An in-memory repository **does not mean access tokens are stored in this same map**. Clearly distinguish client registration configuration from tokens issued to users.

### 4.1. `InMemoryClientRegistrationRepository` and `Iterable`

Besides implementing `ClientRegistrationRepository`, `InMemoryClientRegistrationRepository` also implements `Iterable<ClientRegistration>`. This enables iterating over the registrations held by the repository:

~~~java
for (ClientRegistration registration : inMemoryRepository) {
    System.out.println(registration.getRegistrationId());
}
~~~

For the default login page generated by Spring Security when using `oauth2Login()`, an iterable repository (`Iterable<ClientRegistration>`) lets the framework discover login options. If using a custom repository that only implements `findByRegistrationId`, automatic login links on the default page may not appear as expected.

Supporting `Iterable` does not mean the `ClientRegistrationRepository` interface requires implementing it. Distinguish:

~~~text
ClientRegistrationRepository
    └─ findByRegistrationId(registrationId)

InMemoryClientRegistrationRepository
    ├─ findByRegistrationId(registrationId)
    └─ Iterable<ClientRegistration>
~~~

Do not use registration iteration to accidentally expose sensitive information, especially `clientSecret`, in public endpoints or logs.

## 5. How Spring Boot Builds the Repository from `application.yml`

For a Spring Boot Servlet application, the most common approach is **declaring registrations in Boot configuration**. When auto-configuration conditions match and no custom `ClientRegistrationRepository` bean is provided by the application, Spring Boot can create an `InMemoryClientRegistrationRepository` from `spring.security.oauth2.client.registration.*` and related provider settings.

Suppose the application supports login through OIDC provider `https://identity.example.com/realms/employees`.

### 5.1. Add Dependencies for a Servlet Web Application

Maven example — Spring Boot 3.x:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
~~~

Gradle example — Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

**Version note:** In Spring Boot 4.x, the MVC and OAuth2 Client starter names were reorganized. The recommended corresponding artifacts are `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`. The Java configuration examples in this lesson still illustrate a Servlet application; the project should use the BOM/plugin of the same Boot line to manage library versions consistently.

### 5.2. Declaring an OIDC Registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: Corporate SSO
        provider:
          corporate-idp:
            issuer-uri: https://identity.example.com/realms/employees
~~~

Explanation of how Spring Boot interprets the configuration:

| Configuration | Result in `ClientRegistration` |
|---|---|
| `registration.corp` | Creates a registration with `registrationId = "corp"`. |
| `provider: corporate-idp` | Links the registration to the provider details keyed `corporate-idp`. |
| `client-id` | Sets the client ID issued by the IdP. |
| `client-secret` | Sets the secret for a confidential client; example reads from an environment variable. |
| `authorization-grant-type` | Specifies the authorization code grant. |
| `redirect-uri` | Callback template; `{registrationId}` is replaced with `corp`. |
| `scope` | Requests OIDC and user information scopes. |
| `provider.corporate-idp.issuer-uri` | Uses the issuer to discover OIDC metadata when supported by the provider. |

The `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` variables must be supplied per application environment. Never place real client secrets in Git or training examples.

With public domain `https://app.example.com`, the default callback of the registration above is:

~~~text
https://app.example.com/login/oauth2/code/corp
~~~

Register that URI at the provider. When running locally, the callback can use `http://localhost:8080/login/oauth2/code/corp` if the provider permits HTTP redirects on localhost.

### 5.3. What Does Spring Boot Create?

With matching configuration, Spring Boot reads the properties group and creates a repository bean containing the corresponding `ClientRegistration`s. The application can inject the interface without manually calling the `InMemoryClientRegistrationRepository` constructor:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Service
public class OAuthProviderInfoService {

    private final ClientRegistrationRepository registrations;

    public OAuthProviderInfoService(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String getProviderDisplayName(String registrationId) {
        ClientRegistration registration =
            registrations.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                "Unknown registrationId: " + registrationId);
        }

        return registration.getClientName();
    }
}
~~~

The service reads only the registration's **display name**, without exposing the client secret. The example illustrates the lookup, without implying that provider name is a safe authorization decision.

### 5.4. Multiple Registrations from `application.yml`

One repository can contain multiple client registrations:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: company-oidc
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            scope:
              - openid
              - profile
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope:
              - openid
              - email
        provider:
          company-oidc:
            issuer-uri: https://login.corp.example.com
          partner-oidc:
            issuer-uri: https://login.partner.example.com
~~~

In the configuration above, Spring Boot recognizes **two** `registrationId`s: `corp` and `partner`. The corresponding default login URIs are:

~~~text
/oauth2/authorization/corp
/oauth2/authorization/partner
~~~

The registrations share the same repository while keeping separate client IDs, issuers, and scopes. If a provider requires a specific callback, set `redirect-uri` per registration and register that exact URI.

## 6. Integrating the Repository with a Servlet Application's `SecurityFilterChain`

Servlet applications use `HttpSecurity` and `SecurityFilterChain`. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

With the configuration above:

- `oauth2Login()` lets users sign in via a provider and establishes the application's authentication context.
- `oauth2Client()` provides integration supporting authorized clients when needing to call APIs using access tokens.
- When a flow requires `registrationId = corp`, OAuth2 Client components query `ClientRegistrationRepository` to obtain the needed metadata.

These two configuration methods are related but do not replace each other. An application that only signs users in can focus on `oauth2Login()`; if it also needs to call external APIs, `oauth2Client()` and authorized client management mechanisms are usually necessary additions.

### 6.1. Repository Lookup Flow Diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant S as Spring Security Servlet
    participant R as ClientRegistrationRepository
    participant OP as Authorization Server / OIDC Provider

    B->>S: GET /oauth2/authorization/corp
    S->>R: findByRegistrationId("corp")
    R-->>S: ClientRegistration(corp)
    Note over S: Build authorization request from metadata
    S-->>B: 302 to authorization endpoint
    B->>OP: Authorization request
    OP->>B: Authentication / consent
    OP-->>B: 302 callback?code=...&state=...
    B->>S: GET /login/oauth2/code/corp
    Note over S: Match saved authorization request/state
    S->>OP: POST token endpoint (authorization code)
    OP-->>S: Access token + ID Token if OIDC
    Note over S: Verify token, create Authentication and session
    S-->>B: Redirect to requested page
~~~

`ClientRegistrationRepository` participates in resolving the client configuration. It **does not verify `state` itself**, does not perform the authorization code exchange itself, and does not create sessions. Spring Security's filters and authentication providers use it as a configuration dependency.

### 6.2. Spring Security Endpoints Tied to `registrationId`

By default when using `oauth2Login()`:

| Path | Function |
|---|---|
| `/oauth2/authorization/{registrationId}` | Application entry point to start an authorization request. |
| `/login/oauth2/code/{registrationId}` | Callback receiving the authorization response. |

For example, `registrationId = corp`:

~~~text
GET /oauth2/authorization/corp
GET /login/oauth2/code/corp?code=...&state=...
~~~

These paths can be customized. If customizing the authorization base URI or callback URI, configure Spring Security, `redirectUri`, and the callback registered at the provider consistently. Do not assume you can simply rename a URL without affecting lookup and routing.

## 7. Declaring `ClientRegistrationRepository` Manually

When you want direct control over how client registrations are constructed, you can define a `ClientRegistrationRepository` bean directly instead of declaring everything via Spring Boot properties.

This is suitable when:

- Configuration is supplied by an existing internal layer.
- Multiple verified and trusted configuration sources must be aggregated.
- Registrations must be constructed via a builder or advanced setup logic.
- The project does not use Spring Boot's default property binding.

### 7.1. Creating from OIDC Discovery

If the OpenID Provider supports discovery at a trusted issuer URI, use `ClientRegistrations.fromIssuerLocation(...)` to fetch provider metadata, then attach the application's client details:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class ClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.oidc.issuer}") String issuer,
            @Value("${app.oidc.client-id}") String clientId,
            @Value("${app.oidc.client-secret}") String clientSecret) {

        ClientRegistration corp = ClientRegistrations
            .fromIssuerLocation(issuer)
            .registrationId("corp")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .clientName("Corporate SSO")
            .build();

        return new InMemoryClientRegistrationRepository(corp);
    }
}
~~~

Corresponding properties can be declared as:

~~~yaml
app:
  oidc:
    issuer: https://identity.example.com/realms/employees
    client-id: ${OIDC_CLIENT_ID}
    client-secret: ${OIDC_CLIENT_SECRET}
~~~

Key points to understand:

- `fromIssuerLocation(issuer)` uses the corresponding discovery endpoint to build metadata; the issuer must be configured from a trusted source, never taken arbitrarily from a user request.
- `registrationId("corp")` sets the internal lookup key.
- `clientId` and `clientSecret` come from the client registration at the provider.
- `clientAuthenticationMethod` must match the method registered/allowed at the provider.
- `redirectUri` must match a URI permitted at the provider.
- `InMemoryClientRegistrationRepository(corp)` stores the registration for Spring Security lookup.

This is an **alternative** to letting Spring Boot auto-create the repository from `spring.security.oauth2.client.registration.*`. Within one application, choose clear bean ownership; if you provide your own `ClientRegistrationRepository` bean, Boot normally backs off from creating another default repository from properties.

Discovery may issue HTTP requests to fetch metadata when the bean is created. Therefore the issuer must be available and trusted; network, certificate, or metadata errors can cause startup to fail. Do not treat discovery as arbitrarily probing issuers from user-submitted data.

### 7.2. Building with `ClientRegistration.Builder` Without Discovery

If the provider has fixed metadata or does not expose compatible discovery, endpoints can be declared explicitly.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class ExplicitClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.oidc.client-id}") String clientId,
            @Value("${app.oidc.client-secret}") String clientSecret) {

        ClientRegistration corp = ClientRegistration
            .withRegistrationId("corp")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .authorizationUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/auth")
            .tokenUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/token")
            .jwkSetUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/certs")
            .issuerUri("https://identity.example.com/realms/employees")
            .userInfoUri(
                "https://identity.example.com/realms/employees/protocol/openid-connect/userinfo")
            .userNameAttributeName("sub")
            .clientName("Corporate SSO")
            .build();

        return new InMemoryClientRegistrationRepository(corp);
    }
}
~~~

The endpoints above **only illustrate a common URL pattern**, not the exact URLs for every OIDC Provider. Before using them, verify against discovery metadata or the real provider's documentation. If the provider requires a different client authentication method, update accordingly; do not use `client_secret_basic` by default when the actual registration disallows it.

Both examples in sections 7.1 and 7.2 define a bean named `clientRegistrationRepository`; **do not put both classes into the same application**. Choose one initialization approach for the repository.

### 7.3. Manually Registering Multiple Clients

Once you have multiple `ClientRegistration`s:

~~~java
@Bean
ClientRegistrationRepository clientRegistrationRepository(
        ClientRegistration corp,
        ClientRegistration partner) {

    return new InMemoryClientRegistrationRepository(corp, partner);
}
~~~

This snippet only shows combining two objects created from valid configuration sources; `corp` and `partner` must have distinct `registrationId`s. Do not confuse the `ClientRegistration` type with a String provider name.

An explicit variant when assembling inside the same method:

~~~java
ClientRegistrationRepository repository =
    new InMemoryClientRegistrationRepository(
        corpRegistration,
        partnerRegistration
    );
~~~

Spring Security looks up registrations independently by ID while still allowing iteration when the repository supports `Iterable`.

## 8. Which Repository Stores What in Spring Security OAuth2 Client?

This is the most easily confused area when learning `ClientRegistrationRepository`. Spring Security has several other repositories/services, each solving a different problem.

| Component | What is stored/looked up | Typical key/input | Scope |
|---|---|---|---|
| **`ClientRegistrationRepository`** | OAuth2/OIDC Client configuration metadata | `registrationId` | Shared application-level configuration. |
| **`AuthorizationRequestRepository<OAuth2AuthorizationRequest>`** | In-flight authorization request, including `state` and correlation data | Request/response and HTTP session | Temporary during redirect/callback. |
| **`OAuth2AuthorizedClientRepository`** | Authorized client tied to a principal and request | `registrationId` + principal + request/response | Servlet/web and user context. |
| **`OAuth2AuthorizedClientService`** | Authorized client already granted tokens | `clientRegistrationId` + principal name | Service layer storing authorized clients; can use in-memory or other persistence. |
| **`HttpSession` / `SecurityContextRepository`** | Application authentication/session context | Session/cookie and security context | User's logged-in application session. |

### 8.1. `ClientRegistration` Is Not `OAuth2AuthorizedClient`

`ClientRegistration` is a static configuration record:

~~~text
registrationId: corp
clientId: web-portal
tokenUri: https://identity.example.com/.../token
scope: openid profile email
~~~

`OAuth2AuthorizedClient`, by contrast, represents an authorization granted to a principal, linked to a registration and tokens:

~~~text
clientRegistration: corp
principalName: alice
accessToken: ...
refreshToken: ... (if present)
~~~

Two users both signing in with `corp` share **the same `ClientRegistration` configuration** yet each may have **a separate `OAuth2AuthorizedClient`** holding different tokens. Therefore, never put access tokens into registration configuration and never use the configuration repository as token storage.

### 8.2. `AuthorizationRequestRepository` Is Not `ClientRegistrationRepository`

When Spring Security redirects the browser to the IdP, the framework usually saves the generated authorization request so that on callback it can verify `state` and related details. In Servlet applications, a common implementation is `HttpSessionOAuth2AuthorizationRequestRepository`.

This repository stores **the in-flight login transaction**, not long-lived client metadata. If the HTTP session or authorization request data is lost between redirect and callback, the user can hit a state/missing authorization request error even though `ClientRegistrationRepository` still holds complete client information.

### 8.3. `ClientRegistrationRepository` Does Not Determine User Permissions

A registration supplies OAuth2 configuration and requested scopes, yet does not replace determining who the authenticated user is, what roles they hold in the application, or whether an access token is authorized to call a specific API.

For instance, `scope: openid profile email` does not grant administrator privileges to a user. The application must still map authorities and enforce authorization policies based on trusted data.

## 9. Collaborating with `OAuth2AuthorizedClientService` and `OAuth2AuthorizedClientManager`

When a Servlet backend calls an API using an access token, it can obtain an authorized client via `OAuth2AuthorizedClientService` or `OAuth2AuthorizedClientManager`. Those components depend directly or indirectly on `ClientRegistrationRepository` to know which clients are configured.

Conceptual flow:

~~~text
                    ClientRegistrationRepository
                               |
                               | ClientRegistration
                               v
               OAuth2AuthorizedClientManager
                     /                  \
                    v                    v
        OAuth2AuthorizedClient     Provider Token
          (access/refresh token)      endpoint
                    |
                    v
           HTTP client calls API
~~~

In Servlet applications, the manager interface used is:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager
~~~

For WebFlux applications, the corresponding API family carries reactive prefixes, such as `ReactiveClientRegistrationRepository` and `ReactiveOAuth2AuthorizedClientManager`. Do not import them into a Servlet configuration expecting Spring to convert them automatically.

### 9.1. Does Having the Repository Alone Automatically Acquire Access Tokens?

No. The repository returns metadata such as client ID, endpoints, and scopes. To obtain an access token for a user, the application must complete a valid **grant flow**, such as Authorization Code Grant with user login/consent. If token refresh is needed, the authorized client mechanism requires a refresh token and provider support.

One way to picture it:

~~~text
ClientRegistrationRepository:
    "How is the corp application registered?"

OAuth2AuthorizedClientRepository/Service:
    "Has Alice authorized the corp client yet, and what tokens are saved?"

OAuth2AuthorizedClientManager:
    "When the application needs an authorized client, how should it be obtained?"
~~~

Never assign the responsibilities of a token manager or token storage to `ClientRegistrationRepository`.

## 10. Accessing `ClientRegistration` in Java Code

A valid use case is retrieving the display name, declared scopes, or endpoint of a registration to support UI rendering or internal administration.

~~~java
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Service
public class RegistrationCatalog {

    private final ClientRegistrationRepository repository;

    public RegistrationCatalog(ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public String providerName(String registrationId) {
        ClientRegistration client =
            repository.findByRegistrationId(registrationId);

        if (client == null) {
            throw new IllegalArgumentException(
                "Unknown OAuth2 registration: " + registrationId);
        }

        return client.getClientName();
    }

    public Set<String> declaredScopes(String registrationId) {
        ClientRegistration client =
            repository.findByRegistrationId(registrationId);

        if (client == null) {
            throw new IllegalArgumentException(
                "Unknown OAuth2 registration: " + registrationId);
        }

        return client.getScopes();
    }
}
~~~

`getScopes()` returns **the scopes the client is configured to request**, not necessarily the actual access token scopes granted to each user. The Authorization Server can narrow the scope. To inspect scopes on an issued token, read the corresponding authorized client/access token.

### 10.1. Never Return `ClientRegistration` Directly from a Public API

The object may contain `clientSecret` and sensitive metadata. Avoid doing this:

~~~java
// AVOID: risks exposing secrets in the HTTP response.
@GetMapping("/debug/registration/{id}")
ClientRegistration debug(@PathVariable String id) {
    return repository.findByRegistrationId(id);
}
~~~

If an API is needed to list login options, create a DTO containing only genuinely required public fields, such as `registrationId` and `clientName`. Consider carefully whether provider details should be exposed publicly in the application.

### 10.2. Never Blindly Trust a Client-Supplied `registrationId`

`registrationId` in a URL is a **selector**, not proof of authorization or permission to access arbitrary providers. If the system supports multiple IdPs, restrict the list of permitted registrations per application, tenant, or user policy.

If building a dynamic repository, never treat a request-supplied issuer value or URL as a trusted address for automatic discovery without validation. Doing so can open SSRF, issuer mix-up, or unauthorized IdP login risks.

## 11. Configuration via Properties vs. Manual Bean: When to Choose Which?

| Criterion | Spring Boot properties | Manual `InMemoryClientRegistrationRepository` bean |
|---|---|---|
| Configuring a few fixed providers | Very suitable | Suitable, though more verbose. |
| Changing client ID/secret per environment | Use environment/property placeholders | Use `@Value` or config injection mechanisms. |
| Using OIDC Discovery | Declare `issuer-uri` | `ClientRegistrations.fromIssuerLocation(...)`. |
| Applying custom registration construction logic | Limited by property structure | Flexible via builder. |
| Simplicity of maintaining basic config values | High | Requires maintaining additional Java config. |
| Updating registrations at runtime | Does not update automatically just from property file edits | Also not automatic with a fixed in-memory bean. |
| Integrating `oauth2Login()` | Yes | Yes, when the bean and metadata are valid. |

For most Spring Boot Servlet applications, **properties + auto-configuration** is the clear starting choice. A manual bean makes sense when there are specific requirements around how registrations are built or supplied.

### 11.1. When Multi-Tenancy or Dynamic Configuration Is Required

An application serving multiple organizations may need to construct registrations per tenant or load configuration from an internal data store. In that case, you can implement a custom `ClientRegistrationRepository`, ensuring:

- Each `registrationId` maps consistently to managed client IDs, issuers, and endpoints.
- Configuration sources are authenticated; requests cannot arbitrarily specify issuers/secrets.
- The callback flow can still look up the exact registration used during initiation.
- Secrets are stored securely with an appropriate rotation mechanism.
- When changing configuration, account for in-flight authorization flows to avoid modifying a registration so that callbacks can no longer be verified.
- If relying on Spring Security's auto-generated login page, consider the `Iterable<ClientRegistration>` requirement; or build a custom login page listing permitted choices.
- Caching, updates, and synchronization layers must be designed carefully, especially across multiple instances.

Switching `ClientRegistrationRepository` to a database-backed repository only solves **the client configuration source**. It does not turn `OAuth2AuthorizedClientService` or HTTP sessions into persistent storage automatically. Token storage and session management needs must be designed separately.

## 12. Which Spring Security Components Use the Repository?

In the Servlet OAuth2/OIDC Client flow, key components include:

| Component | How it relates to `ClientRegistrationRepository` |
|---|---|
| `OAuth2AuthorizationRequestRedirectFilter` | Uses the repository indirectly via a resolver to build the authorization request from a registration ID. |
| `DefaultOAuth2AuthorizationRequestResolver` | Queries `ClientRegistrationRepository` by ID to fetch metadata and construct the OAuth2 authorization request. |
| `OAuth2LoginAuthenticationFilter` | Receives the authorization response/callback and triggers authentication via the authentication manager/provider. |
| `OAuth2LoginAuthenticationProvider` and `OidcAuthorizationCodeAuthenticationProvider` | Handle authorization code exchange and token response per OAuth2/OIDC login type. |
| `OAuth2AuthorizedClientRepository` | Stores the authorized client for a principal after tokens are issued; holds different data from the registration repository. |
| `OAuth2AuthorizedClientService` | Retrieves authorized clients with issued tokens when using the service layer. |

These class names help explain the architecture; they do not mean the application must define beans for every single class. Spring Security's `oauth2Login()` configuration normally builds the default filter chain and providers from required dependencies and beans.

### 12.1. Changing the Authorization Base URI Must Preserve Registration Lookup

For example, an application wants to initiate login from `/login/sso/corp` instead of `/oauth2/authorization/corp`. You can configure an authorization request resolver or base URI supported by your Spring Security version.

Even when the URL changes, **`registrationId` must still be extracted properly** so the resolver calls `findByRegistrationId("corp")`. If misconfigured, the request may return 404, fail to redirect, or report registration not found.

Do not change the callback path independently of the redirect URI registered at the provider; the Authorization Server can reject an invalid callback right at the authorization step.

## 13. Role of the Repository in OIDC vs. Plain OAuth2

`ClientRegistrationRepository` is a **shared** structure for OAuth2 Client. It does not exist solely in OIDC applications.

| Case | What does `ClientRegistration` hold? | Principal / intended use |
|---|---|---|
| OAuth2 Login without `openid` | Client ID, grant type, API scopes, endpoints, user info if used | OAuth2 principal per provider integration. |
| OIDC Login with `openid` | Adds issuer/JWK metadata suitable for processing ID Tokens | `OidcUser` and ID Token processed per OIDC. |
| OAuth2 Client calling APIs with authorization code | Client registration, with access token stored separately in authorized client | Calling resource servers on behalf of a user. |
| Service-to-service using `client_credentials` | Client registration for the client credentials grant | Client/service token, not representing a user OIDC login. |

The same `ClientRegistrationRepository` interface can hold registrations for multiple grant types, yet not every registration produces a browser login URL. For instance, `client_credentials` is not an OAuth2 Login flow and should not be rendered as a user-facing "Sign In" button.

With OIDC, Spring Security uses metadata in the registration—especially issuer/JWK Set, client ID, scopes, and endpoints—to perform code exchange and validate the ID Token per protocol requirements. The application must still enforce appropriate authorization policies after authentication succeeds.

## 14. Common Errors When Using `ClientRegistrationRepository`

### 14.1. `registrationId` Not Found

**Symptom:** visiting `/oauth2/authorization/corp` fails to initiate login in Spring Security.

**Common cause:** configuration only declares `registration.partner`, the ID has mismatched casing, or a custom bean omits `corp`.

**Resolution:** check the actual `registrationId` of `ClientRegistration`s in the repository; ensure login links use an existing ID.

### 14.2. Using `clientId` Instead of `registrationId` in URLs

**Symptom:** using `/oauth2/authorization/web-portal-production` while configuration only defines `registration.corp`.

**Cause:** confusing the provider-issued client ID with the application-chosen registration ID.

**Resolution:** default initiation endpoints rely on **registration ID**, e.g., `/oauth2/authorization/corp`; client ID is placed into the authorization request via metadata.

### 14.3. Properties Declared, Yet Custom Bean Overrides Auto-Configuration

**Symptom:** configuration in `application.yml` does not appear in the repository; only manually constructed registrations work.

**Cause:** the application defines its own `ClientRegistrationRepository` bean, causing auto-configuration to back off.

**Resolution:** establish clear **repository ownership**. If combining multiple sources is required, create an intentional composite repository and guard against duplicate IDs rather than assuming Boot will merge them automatically.

### 14.4. Repository Has the Registration, Yet OIDC Metadata Is Wrong

**Symptom:** authorization redirect occurs, but token exchange or ID Token validation fails.

**Cause:** wrong issuer, wrong token endpoint, unsuitable JWK Set URI, wrong client secret/auth method, or rejected scopes.

**Resolution:** verify against the provider's official metadata, issued client registration, and registered redirect URI. The repository does not guarantee that author-supplied metadata is accurate.

### 14.5. Default Login Page Does Not Display Login Links

**Symptom:** a custom repository can look up registrations by ID, yet the auto-generated login page does not list clients.

**Possible cause:** the repository does not implement `Iterable<ClientRegistration>` or the registration is ineligible for OAuth2 login display.

**Resolution:** use `InMemoryClientRegistrationRepository` when appropriate, or build a custom login page containing approved `/oauth2/authorization/{registrationId}` links.

### 14.6. Confusing the Registration Repository with Token Storage

**Symptom:** developers expect `InMemoryClientRegistrationRepository` to hold refresh tokens, or worry that user B signing in will use user A's token.

**Cause:** confusing `ClientRegistrationRepository` with `OAuth2AuthorizedClientRepository` or `OAuth2AuthorizedClientService`.

**Resolution:** design token storage per principal and client, while keeping registration configuration separate from granted authorization data.

### 14.7. Declaring a Servlet `ClientRegistrationRepository` for WebFlux

**Symptom:** using `SecurityWebFilterChain` in a reactive app while only defining a Servlet `ClientRegistrationRepository` bean; the framework searches for `ReactiveClientRegistrationRepository` and fails to find it.

**Cause:** wrong web stack selected.

**Resolution:** this lesson applies to **Servlet**. If the application uses WebFlux, switch to `ReactiveClientRegistrationRepository` and the corresponding reactive configuration types.

### 14.8. Callback Differs from `redirectUri`

**Symptom:** provider rejects the redirect URI, or the callback arrives without matching a Spring Security endpoint.

**Cause:** the URI configured on the IdP differs from what the client sends; or callback configuration in Spring changed without updating the registration.

**Resolution:** synchronize `redirectUri`, callback login processing URL, and the redirect URI allowlist at the provider.

### 14.9. Logging an Entire `ClientRegistration`

**Symptom:** client secrets or internal metadata appear in logs/monitoring.

**Cause:** logging the raw object or serializing it to JSON for debugging.

**Resolution:** log only necessary fields, such as ID and provider name, after filtering sensitive data. Client secrets must follow an appropriate handling policy.

### 14.10. Allowing Request-Supplied Provider URLs as Issuers

**Symptom/risk:** the client could perform discovery and send data to endpoints specified by an untrusted user.

**Cause:** a dynamic repository lacks an allowlist and fails to bind issuers to trusted tenants/clients.

**Resolution:** manage tenant-to-trusted-provider mappings, restrict metadata sources, and bind callbacks to the selected registration.

## 15. Complete Example: Corporate Login in Servlet

Suppose a system has the requirement: **users open an internal portal and sign in with the Corporate OIDC Provider**.

### 15.1. Components

- Spring Boot Servlet application at `https://portal.example.com`.
- Internal client registration ID is `corp`.
- Client ID issued by the IdP is `portal-web`.
- Issuer is `https://identity.example.com/realms/employees`.
- Registered Redirect URI is `https://portal.example.com/login/oauth2/code/corp`.
- Login scopes are `openid profile email`.

### 15.2. Repository Configuration

The application declares in `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-idp
            client-id: portal-web
            client-secret: ${CORP_OIDC_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corp-idp:
            issuer-uri: https://identity.example.com/realms/employees
~~~

Spring Boot binds the registration and builds the repository via auto-configuration when conditions match. Spring Security uses that bean inside `oauth2Login()`.

### 15.3. Runtime Steps

1. A user accesses a route requiring authentication or clicks the corporate login button.
2. The browser is directed to `/oauth2/authorization/corp`.
3. Spring Security queries the repository for `corp` and builds an authorization request from its metadata.
4. The browser goes to the Authorization Server, where the user authenticates and grants consent if needed.
5. The provider returns the callback `/login/oauth2/code/corp?code=...&state=...`.
6. Spring Security correlates the authorization transaction and performs code exchange using the matching client configuration.
7. For OIDC, the ID Token is verified; Spring Security builds the authenticated principal and stores the session per application strategy.
8. If the application needs to call APIs, the authorized client/token is retrieved from the corresponding authorized client store; **the registration repository does not hold user tokens**.

In step 3, the repository has a very specific role: "for `corp`, supply all of the client's metadata". The remaining authentication and token exchange steps belong to other Spring Security components.

### 15.4. Why No Manual Bean Is Needed in This Case?

All client registration values are declared cleanly in Boot configuration, the issuer supports discovery, and there is no requirement for dynamic client creation. Therefore `application.yml` and `oauth2Login()` suffice for registration configuration. Defining an extra manual bean only adds maintenance overhead without a specific need.

## 16. Practical Scenarios

### Scenario A: Two Registrations Sharing an Issuer

The application has:

~~~text
registrationId=corp-user,  clientId=portal-user
registrationId=corp-admin, clientId=portal-admin
issuer=https://identity.example.com
~~~

**Correct understanding:** the repository has two entries with distinct IDs. Sharing an issuer does not mean only one `ClientRegistration` can be stored, because client ID, scopes, secret, and callback may differ.

### Scenario B: One User Signs In Twice

User Alice signs in from browser A and browser B using the same `registrationId=corp`.

**Correct understanding:** both flows use the same client registration metadata in the repository while having their own `state`, sessions, and authorized clients. The repository is not used to store per-session `state` or tokens.

### Scenario C: Custom Repository and Options Missing from the Login Page

A developer writes a custom implementation implementing only `findByRegistrationId(...)`. Direct URL `/oauth2/authorization/corp` still works, yet the default login page does not automatically list providers.

**Correct understanding:** examine the repository's `Iterable` capability or build a custom login page. Do not invent a `findAll()` method on the interface expecting Spring Security to call it.

### Scenario D: API Receiving Bearer Tokens

Another application calls `GET /api/orders` on the current server with a Bearer token. Someone suggests using `ClientRegistrationRepository` to validate the token.

**Correct understanding:** `ClientRegistrationRepository` is not a JWT decoder/token introspector. If the application **receives and validates** Bearer tokens, that is a **Resource Server** responsibility, requiring appropriate configuration and dependencies.

### Scenario E: Needing to Rotate a Client Secret

Per security policy, the secret for registration `corp` must be rotated.

**Correct understanding:** the secret is data inside `ClientRegistration`; with an in-memory repository created at startup, the application typically needs a reload/restart mechanism or controlled configuration refresh to pick up the new value. Changing the secret does not wipe user accounts; however, in-flight code exchanges may be affected if client credentials change mid-flow.

## 17. Self-Check Questions

**Q1.** What core method does the `ClientRegistrationRepository` interface provide?

**Answer:** `findByRegistrationId(registrationId)`, retrieving the registered OAuth2/OIDC Client configuration metadata.

**Q2.** Is `registrationId` the same as `clientId`?

**Answer:** No. `registrationId` is the internal key Spring Security uses to look up the repository; `clientId` is the identifier issued to the client by the Authorization Server.

**Q3.** If an application declares `spring.security.oauth2.client.registration.corp` in `application.yml`, must it manually create an `InMemoryClientRegistrationRepository`?

**Answer:** Usually not when Spring Boot auto-configuration already creates the corresponding bean and the application requires no repository customization.

**Q4.** Which repository stores the authorization request and `state` during redirect/callback?

**Answer:** `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`, typically backed by the HTTP session in Servlet; not `ClientRegistrationRepository`.

**Q5.** Which repository relates to authorized clients and tokens issued to users?

**Answer:** `OAuth2AuthorizedClientRepository` and/or `OAuth2AuthorizedClientService`, depending on storage configuration; not `ClientRegistrationRepository`.

**Q6.** Why might an auto-generated login page require a repository supporting `Iterable<ClientRegistration>`?

**Answer:** Because the framework needs to iterate over registrations to build the list of login choices. `InMemoryClientRegistrationRepository` implements `Iterable`, whereas the base interface only requires lookup by ID.

**Q7.** Do Servlet and WebFlux share the same repository interface?

**Answer:** No. Servlet applications use `ClientRegistrationRepository`, whereas WebFlux uses `ReactiveClientRegistrationRepository` with reactive return types.

**Q8.** Can an OAuth2 Client repository be used to issue access tokens itself like an Authorization Server?

**Answer:** No. The repository stores client metadata for an application acting as an OAuth2 Client; issuing tokens is the Authorization Server's responsibility.

## 18. Key Takeaways

| Term | How to remember it |
|---|---|
| **`ClientRegistration`** | A metadata set describing an OAuth2/OIDC Client and provider. |
| **`ClientRegistrationRepository`** | Looks up metadata by `registrationId`. |
| **`InMemoryClientRegistrationRepository`** | Built-in implementation holding configuration in memory, supporting `Iterable`. |
| **`spring.security.oauth2.client.registration.*`** | How Spring Boot reads configuration and creates the repository via auto-configuration. |
| **`/oauth2/authorization/{registrationId}`** | Login initiation point based on registration ID. |
| **`/login/oauth2/code/{registrationId}`** | Default callback for authorization responses in Servlet OAuth2 Login. |
| **`AuthorizationRequestRepository`** | Stores temporary authorization requests, including correlation data. |
| **`OAuth2AuthorizedClientRepository/Service`** | Stores granted tokens/authorizations per principal, separate from registrations. |
| **`ReactiveClientRegistrationRepository`** | Corresponding API for WebFlux, not used directly in Servlet. |

In a **Spring Security OAuth 2.0 OIDC Client application on Servlet**, `ClientRegistrationRepository` is **the lookup point for client information** needed by components like the authorization request resolver to know which provider to send users to and which client ID, scopes, redirect URI, and token endpoint to use. The practical starting point is declaring registrations in Spring Boot properties and letting the framework create `InMemoryClientRegistrationRepository`. Only write a custom repository when you genuinely need custom configuration sources, multi-tenancy, or advanced client management.
