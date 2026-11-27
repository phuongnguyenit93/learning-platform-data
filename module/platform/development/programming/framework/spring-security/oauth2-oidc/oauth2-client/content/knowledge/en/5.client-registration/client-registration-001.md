# 5.1. ClientRegistration and Client Registration Information

## Lesson Objectives

In Spring Security OAuth 2.0 Client, **`ClientRegistration` is the object that describes a client registered with an Authorization Server or OpenID Provider**. This object answers the following questions: which `client_id` identifies the application, what grant type it uses, where users must be redirected, which scopes it can request, and which endpoint it calls to obtain tokens.

After this lesson, you will be able to:

- Explain the role of `ClientRegistration` in an OAuth 2.0 Client and an OpenID Connect Relying Party (RP).
- Distinguish between **client registration** information, **provider** information, **granted authorization** data, and user identity.
- Identify the meaning of key fields: `registrationId`, `clientId`, `clientSecret`, `clientAuthenticationMethod`, `authorizationGrantType`, `redirectUri`, `scopes`, `clientName`, and `providerDetails`.
- Configure one or more client registrations using `application.yml` in Spring Boot.
- Read and create a `ClientRegistration` in Java, look it up via `ClientRegistrationRepository`, and relate it to the OIDC login or API calling process.
- Avoid common configuration mistakes regarding callbacks, scopes, issuers, secrets, and deployment environments.

## 1. Why Does an Application Need Client Registration Information?

Suppose there is a web application **Order Portal** written in Spring Boot. The portal wants to:

1. Allow employees to sign in through the enterprise OpenID Provider (OP).
2. After signing in, use an access token to call an order management API.
3. Possibly run another background job that only needs a token via `client_credentials` to call a reporting API.

For the Authorization Server to know which application is requesting permissions, an administrator must **register the client on the Authorization Server/OP side**. Registration typically provides or confirms:

- A `client_id`, and possibly a `client_secret` or another client authentication method.
- Accepted redirect URIs.
- Allowed grant types and client types.
- Scopes that the client is permitted to request.
- Token issuance policies, consent, PKCE, or provider-specific settings.

On the Spring Boot side, the corresponding configuration information must be stored so Spring Security knows **how to participate in the protocol**. Spring represents this configuration using **`ClientRegistration`**.

> Distinguish between two things: **registering a client at the OP/Authorization Server** is an administrative action or provisioning workflow on the provider side; **declaring `ClientRegistration` in Spring** is the local description of that client so the application can execute OAuth 2.0/OIDC flows. Declaring it in Spring does not automatically create the client at the OP.

For example, if the provider issues `client_id=order-portal-web` and accepts the callback `https://orders.example.com/login/oauth2/code/corporate`, the Spring configuration must reflect those exact values.

## 2. What Is `ClientRegistration`?

`ClientRegistration` is a Spring Security data type:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistration
~~~

It contains the information required for **a specific OAuth 2.0 Client configuration** to interact with an Authorization Server/OP.

An application can have:

- **A single registration**: only signing in with the enterprise identity system.
- **Multiple registrations for different providers**: for example, an enterprise OP and an external provider.
- **Multiple registrations for the same provider**: for example, one client ID for employee login and another client ID for calling service APIs.
- **A registration for a grant without a user**: such as `client_credentials`.

### 2.1. `ClientRegistration` Is Not a Token or a Login Session

In Spring Security, there are closely related types with different responsibilities:

| Component | What does it hold or do? | Example |
|---|---|---|
| **`ClientRegistration`** | Client configuration and provider details needed to initiate an OAuth 2.0/OIDC flow | Client ID, grant type, redirect URI, token endpoint |
| **`ClientRegistrationRepository`** | Stores and looks up registrations by `registrationId` | Look up the `corporate` registration |
| **`OAuth2AuthorizedClient`** | A registration that has been authorized in a principal/client context; holds the access token and possibly a refresh token | Access token issued for employee A |
| **`OAuth2AuthorizedClientService` / `OAuth2AuthorizedClientRepository`** | Stores and retrieves authorized client/token state | Account A's token for the `corporate` registration |
| **`OAuth2AuthorizedClientManager`** | Coordinates requesting, reusing, or re-authorizing tokens according to the configured grant/provider | Request an access token for a background job |
| **`Authentication` / `OidcUser`** | Principal information and login result within the application | User A has signed in via OIDC |

Key point: **`ClientRegistration` does not hold a user's access token**. Nor does it prove that someone has signed in. Tokens and principal information are created in later steps, once the authorization or authentication flow completes.

### 2.2. Where `ClientRegistration` Fits in the OIDC Flow

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["ClientRegistrationRepository"]
    B --> C["ClientRegistration: corporate"]
    C --> D["Client info: ID, secret, grant, scope, redirect"]
    C --> E["Provider info: issuer, authorize, token, JWK, UserInfo"]
    D --> F["Create OIDC Authorization Request"]
    E --> F
    F --> G["OpenID Provider authenticates and handles consent"]
    G --> H["Callback + authorization code"]
    H --> I["Exchange code for tokens"]
    I --> J["OidcUser / Authentication"]
    I --> K["OAuth2AuthorizedClient"]
    K --> L["Use access token to call Resource Server"]
~~~

The diagram shows that the registration is **the input configuration to the flow**, whereas the principal and authorized client are **the outcomes dependent on the login/authorization process**.

## 3. Key Properties of `ClientRegistration`

### 3.1. Client Identification Group

| Field / getter | Meaning | Example |
|---|---|---|
| `registrationId` / `getRegistrationId()` | Unique internal key used by Spring to look up the registration | `corporate` |
| `clientId` / `getClientId()` | Client identifier issued by the AS/OP | `order-portal-web` |
| `clientSecret` / `getClientSecret()` | Client authentication secret when the chosen method requires a secret | Value from a secret manager |
| `clientName` / `getClientName()` | Human-readable name for display or distinguishing registrations | `Corporate SSO` |
| `clientAuthenticationMethod` | Mechanism the client uses to authenticate with the token endpoint when required | `client_secret_basic` |

#### `registrationId` Is Different from `clientId`

Example:

~~~text
registrationId = corporate
clientId       = order-portal-web
clientName     = Corporate SSO
~~~

These three values serve different roles:

- `registrationId` is **the key within the Spring application**. You use it when selecting a provider/registration, for example `/oauth2/authorization/corporate`.
- `clientId` is **the identifier known to the provider**; this value appears in the OAuth 2.0/OIDC protocol, for example `client_id=order-portal-web`.
- `clientName` is **a human-readable label**; do not use it in place of `client_id`.

You should not assume `registrationId` must equal `clientId`. The two values can differ; that is a common way to keep internal names stable even if the ID issued by the provider changes.

Within the same `ClientRegistrationRepository`, each `registrationId` must uniquely identify a registration. If an application has multiple OPs or multiple tenants, plan clear names such as `employee-sso`, `partner-sso`, `reporting-service`.

#### Is `clientSecret` Always Required?

No. Some clients can protect their credentials and use a client secret; some public client types cannot reliably keep a secret.

- **Confidential web client**: a Spring Boot backend can store the secret on the server side.
- **Public client**: an SPA or mobile app cannot treat a secret embedded in the application as a safe secret.
- **Other methods**: providers may support authenticating clients with keys or corresponding mechanisms instead of a shared secret.

`client_id` is always a public identifier for the client; **`client_id` is not a password**. If configuring a client with a secret, you must manage the secret as sensitive data.

### 3.2. `clientAuthenticationMethod`: Authenticating the Client at the Token Endpoint

This field specifies how the client proves its identity to the Authorization Server when making requests that require client authentication, typically token requests.

Common methods include:

| Configuration value | Meaning |
|---|---|
| `client_secret_basic` | Sends client ID and secret via HTTP Basic authentication at the token endpoint |
| `client_secret_post` | Sends client credentials in the body of the token request |
| `none` | Does not use secret-based client authentication, suitable for certain public clients |
| `private_key_jwt` | Uses a JWT assertion signed with the client's private key, when the provider and client are configured accordingly |

In Java, standard values are represented by `ClientAuthenticationMethod`.

~~~java
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientAuthenticationMethod method =
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC;
~~~

**Choose the method according to the actual registration at the provider**. You should not arbitrarily switch from `client_secret_basic` to `client_secret_post` "just to make it work" without checking policy, and never expose a client secret to the browser to build token requests from JavaScript.

### 3.3. `authorizationGrantType`: Which Flow Does the Client Use to Obtain Authorization?

The grant type determines **the process for obtaining an access token**.

| Grant type | Typical scenario | Interactive user? |
|---|---|---|
| `authorization_code` | OIDC login or requesting delegated permissions on behalf of a user via an authorization code | Usually yes, unless the OP reuses an SSO session |
| `client_credentials` | Backend or background job requesting a token using the client's own identity | No end user required |
| `refresh_token` | Using an issued refresh token to request a new token | Usually non-interactive at refresh time |

In Spring Security, `ClientRegistration.authorizationGrantType` describes **the primary grant of the registration**. Refreshing an access token, when a refresh token is present, is a related authorized-client management step; you should not assume that refreshing requires creating a separate login registration with `authorization-grant-type: refresh_token`.

For web applications signing in with OIDC, the common choice is:

~~~yaml
authorization-grant-type: authorization_code
~~~

For service-to-service jobs:

~~~yaml
authorization-grant-type: client_credentials
~~~

**`client_credentials` is not synonymous with OIDC Login**: no end user is authenticated with an ID token in this flow. Do not add `openid` just to turn a service token into a login token.

### 3.4. `redirectUri`: Where the OP/AS Returns the Authorization Result

In Authorization Code, after the user authenticates and completes authorization, the browser is sent back to the registered redirect URI.

Spring configuration commonly uses the template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Suppose the application runs at `https://orders.example.com` and the registration ID is `corporate`; the corresponding callback is:

~~~text
https://orders.example.com/login/oauth2/code/corporate
~~~

Two important placeholders:

- `{baseUrl}`: the base URL Spring determines for the current request, which may depend on proxy configuration.
- `{registrationId}`: the selected registration ID.

The URI template must match the callback declared on the provider side. **Declaring the callback only in Spring is not enough**: the provider must accept that URI. A mismatched scheme, host, port, path, or reverse proxy configuration can cause a `redirect_uri_mismatch` or equivalent error.

`redirectUri` is primarily meaningful for browser-redirect flows such as Authorization Code. With `client_credentials`, the application communicates directly with the token endpoint, so there is no user callback.

### 3.5. `scopes`: The Scope of Permissions Requested by the Client

`ClientRegistration` stores the set of scopes requested during the OAuth 2.0/OIDC flow.

Example for OIDC login:

~~~yaml
scope:
  - openid
  - profile
  - email
~~~

Meaning:

- `openid`: requests OpenID Connect functionality; required for the transaction to be processed as an OIDC authentication request.
- `profile`: requests the corresponding profile claims per OP policy.
- `email`: requests the corresponding email information if granted by the OP.

Example for an API:

~~~yaml
scope:
  - orders.read
  - orders.write
~~~

API scopes such as `orders.read` depend on your system's Authorization Server and Resource Server. **A client requesting a scope does not guarantee the scope will be granted**: the provider may restrict, deny, or require consent; the Resource Server must still verify actual access permissions.

In OIDC, the ID token authenticates the user at the RP; when calling business APIs, the client uses **an access token appropriate for the API**, not the ID token instead.

### 3.6. `providerDetails`: Authorization Server / OpenID Provider Details

`ClientRegistration.ProviderDetails` groups the provider endpoints and technical details Spring needs.

| Provider property | Purpose |
|---|---|
| `issuerUri` | The OP/AS issuer identifier; important for verifying identity claims and discovery |
| `authorizationUri` | Endpoint where users are redirected to start Authorization Code |
| `tokenUri` | Endpoint where the client exchanges a code or requests a token per grant |
| `jwkSetUri` | Address for fetching the provider's public keys/JWK for signature verification when applicable |
| `userInfoEndpoint.uri` | The UserInfo Endpoint in OIDC, when available and used |
| `userInfoEndpoint.userNameAttributeName` | Attribute name identifying the principal in the corresponding case |
| `configurationMetadata` | Provider/discovery metadata recorded by Spring when creating a registration from metadata |

For example, an OP might provide:

~~~text
issuer:
https://id.example.com/realms/company

authorization endpoint:
https://id.example.com/realms/company/protocol/openid-connect/auth

token endpoint:
https://id.example.com/realms/company/protocol/openid-connect/token

JWKS endpoint:
https://id.example.com/realms/company/protocol/openid-connect/certs

UserInfo endpoint:
https://id.example.com/realms/company/protocol/openid-connect/userinfo
~~~

*These are illustrative URLs; actual endpoints are published by the provider.*

Fields in `providerDetails` **do not belong to the signed-in user**; they describe the shared provider for the registration.

## 4. Distinguishing Registration and Provider

Spring Boot can declare **registration** and **provider** in two separate configuration groups:

~~~text
spring.security.oauth2.client.registration.<registrationId>
spring.security.oauth2.client.provider.<providerId>
~~~

- **Registration** states which client this application is: `client-id`, `client-secret`, grant, scope, redirect, display name.
- **Provider** states which server to communicate with: issuer, authorization endpoint, token endpoint, verification keys, UserInfo.

A single provider can serve **multiple registrations**. For example, the same OP issues two client IDs: one for web login and one for an API-calling service.

### 4.1. Three Names Not to Confuse

~~~text
registrationId: corporate
providerId:     company-oidc
clientId:       order-portal-web
~~~

| Name | Who uses it? | Must they be the same? |
|---|---|---|
| `corporate` | Spring Security looks up the registration, builds the authorization endpoint and callback | No |
| `company-oidc` | Spring Boot maps the registration to the provider configuration | No |
| `order-portal-web` | Authorization Server/OP identifies the client | No |

A registration setting `provider: company-oidc` references the settings under `spring.security.oauth2.client.provider.company-oidc`. There is no rule requiring the registration ID to equal the provider ID.

### 4.2. Discovery via `issuer-uri`

With OpenID Connect, the OP usually exposes a metadata document so RPs can discover the required endpoints. Configuring:

~~~yaml
provider:
  company-oidc:
    issuer-uri: https://id.example.com/realms/company
~~~

allows Spring Boot/Spring Security to resolve provider details via **discovery** when the provider is compatible.

Key benefits:

- Reduces duplicating multiple endpoints in configuration.
- Uses the chosen issuer to obtain the endpoint values and public key information published by the OP.
- Reduces errors from misconfiguring individual component URLs.

However, keep in mind:

- `issuer-uri` must be accurate and point to a trusted issuer, not an arbitrary URL a user could supply.
- The OP must publish metadata at a location and format supported by the library; the application must be able to reach the metadata during configuration initialization.
- If the provider does not support compatible discovery, the required endpoints must be configured manually.
- Discovery **does not replace client registration** at the OP: Spring still needs the client ID and appropriate credentials.

## 5. Configuring `ClientRegistration` in Spring Boot

### 5.1. Dependency

With Maven and Spring Boot, add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

The starter provides Spring Security OAuth 2.0 Client integration and the required components for the Spring Boot version in use.

### 5.2. Complete Example: OIDC Login Registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${CORP_OIDC_CLIENT_ID}
            client-secret: ${CORP_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: Corporate SSO
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Reading the configuration layer by layer:

1. `corporate` is the **registration ID** Spring uses to look up the configuration when starting login.
2. `company-oidc` is the **provider ID**, where the issuer is declared.
3. `client-id` and `client-secret` are the credentials issued at the OP.
4. `client_secret_basic` specifies how the confidential client authenticates at the token endpoint.
5. `authorization_code` selects the interactive flow with callback.
6. `redirect-uri` declares Spring Security's callback; it must match the registration at the OP.
7. `scope` includes `openid`, since this is an OIDC login.
8. `client-name` is a descriptive label and does not replace `client_id` in the protocol.

In real systems, environment variables or a secret manager supply `CORP_OIDC_CLIENT_ID` and `CORP_OIDC_CLIENT_SECRET`. Never commit real client secrets to a repository.

### 5.3. Enabling OIDC Login in Spring Security

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

        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated()
                )
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

When Spring Boot builds the repository from `application.yml` and the application configures `oauth2Login()`, a typical flow can start at:

~~~text
GET /oauth2/authorization/corporate
~~~

After authentication at the OP, the typical callback is:

~~~text
GET /login/oauth2/code/corporate?code=...&state=...
~~~

Spring Security uses the matching registration to complete the authorization code exchange and handle login. For OIDC requests with `openid` and a compatible OP, Spring processes the ID token to build the OIDC principal.

The paths above are Spring Security's default paths in this illustrative configuration. If the application customizes the base URI for authorization or redirection, the endpoints and redirect URI must be adjusted consistently.

### 5.4. Another Example: Backend Using `client_credentials`

A service might only need to call an API without sending users to an OP. In that case, the client registration has a different configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: internal-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          internal-auth:
            token-uri: https://auth.example.com/oauth2/token
~~~

Here:

- `reporting-service` is an OAuth 2.0 Client registration for **client-to-server** exchange.
- Only the token endpoint is needed for this grant in the example configuration.
- There is no `scope=openid` or ID token authenticating an end user.
- There is no redirect URI or user login screen.
- Having a `ClientRegistration` **does not automatically acquire tokens**; application code must use the appropriate authorized client mechanism to request and manage tokens.

If the application has both `corporate` and `reporting-service`, they are two independent registrations with separate grants and policies. You should not use a `client_credentials` token to represent the identity of a specific user.

## 6. How Does Spring Boot Build `ClientRegistration`?

At a high level:

~~~mermaid
flowchart LR
    A["application.yml / properties"] --> B["Spring Boot configuration binding"]
    B --> C["ClientRegistration"]
    C --> D["ClientRegistrationRepository"]
    D --> E["oauth2Login / oauth2Client"]
    E --> F["Authorization request / Token request"]
~~~

Spring Boot reads the `spring.security.oauth2.client.*` properties group, combines registration and provider information, and configures the corresponding client beans when auto-configuration conditions are met.

You do not need to declare `@Bean ClientRegistrationRepository` yourself if properties configuration is sufficient. Conversely, if you provide your own repository bean, understand that the application is actively managing the set of registrations; do not expect Boot's auto-configuration to also create a second repository.

### 6.1. Looking Up via `ClientRegistrationRepository`

Basic interface:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

ClientRegistration registration =
        clientRegistrationRepository.findByRegistrationId("corporate");
~~~

`findByRegistrationId(...)` returns the matching registration or `null` if not found, per the interface contract.

Example used inside a component to **safely read metadata**, without printing secrets:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class ClientRegistrationInspector {

    private final ClientRegistrationRepository registrations;

    public ClientRegistrationInspector(
            ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String describe(String registrationId) {
        ClientRegistration registration =
                registrations.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown registration: " + registrationId);
        }

        return "registrationId=" + registration.getRegistrationId()
                + ", clientId=" + registration.getClientId()
                + ", grantType="
                + registration.getAuthorizationGrantType().getValue()
                + ", scopes=" + registration.getScopes();
    }
}
~~~

This example is for internal observation of configuration only. Even without printing secrets, exposing the list of client IDs and security configuration may still be inappropriate. Do not turn this component into a public endpoint without a need and proper access control.

### 6.2. `InMemoryClientRegistrationRepository`

Spring Security provides a simple repository that stores registrations in memory:

~~~java
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
~~~

It is suitable when the registration list is a relatively static configuration determined at application startup. If the application has many tenants, frequently adds/removes clients, or manages metadata dynamically, a custom `ClientRegistrationRepository` implementation and appropriate secret/configuration management model may be needed.

**The repository is not where access tokens are stored**. Using `InMemoryClientRegistrationRepository` does not mean storing tokens in memory; that is the responsibility of other authorized-client components.

## 7. Creating `ClientRegistration` Directly in Java

Alongside `application.yml`, Spring Security provides a builder to create `ClientRegistration` in code. This is useful when configuration comes from another system or needs manual initialization.

### 7.1. Using Discovery from an Issuer

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
public class ManualClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${CORP_OIDC_CLIENT_ID}") String clientId,
            @Value("${CORP_OIDC_CLIENT_SECRET}") String clientSecret) {

        ClientRegistration corporate = ClientRegistrations
                .fromIssuerLocation(
                        "https://id.example.com/realms/company")
                .registrationId("corporate")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .clientName("Corporate SSO")
                .build();

        return new InMemoryClientRegistrationRepository(corporate);
    }
}
~~~

What the code snippet demonstrates:

- `ClientRegistrations.fromIssuerLocation(...)` fetches metadata from a compatible issuer to initialize the builder with provider details.
- `registrationId("corporate")` sets the key used in Spring.
- `clientId(...)`, `clientSecret(...)`, and `clientAuthenticationMethod(...)` configure the client identity and authentication method.
- `authorizationGrantType(...)`, `redirectUri(...)`, and `scope(...)` describe the login flow.
- `InMemoryClientRegistrationRepository` supplies the registration to Spring Security components that need to look it up.

Prerequisite: the issuer must actually support the discovery mechanism used by the library, and the application must be able to reach the metadata endpoint in the deployment environment. If the provider does not support it, specify endpoints explicitly according to their documentation.

**Note:** this bean registration example is **an alternative to configuring the repository via properties**, not meant to be placed alongside the earlier auto-configuration approach.

### 7.2. Building from Manually Declared Endpoints

When discovery cannot be used, the corresponding metadata can be declared using the builder:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration registration = ClientRegistration
        .withRegistrationId("corporate")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .issuerUri("https://id.example.com/realms/company")
        .authorizationUri(
                "https://id.example.com/realms/company/protocol/openid-connect/auth")
        .tokenUri(
                "https://id.example.com/realms/company/protocol/openid-connect/token")
        .jwkSetUri(
                "https://id.example.com/realms/company/protocol/openid-connect/certs")
        .userInfoUri(
                "https://id.example.com/realms/company/protocol/openid-connect/userinfo")
        .clientName("Corporate SSO")
        .build();
~~~

In the example above, `clientId` and `clientSecret` are variables supplied securely; all URLs are illustrative only.

Ensure all URLs/issuers are taken from trusted OP configuration. In particular, **never construct the token endpoint or JWK Set URI from arbitrary user request parameters**, as doing so can lead to contacting the wrong server and leaking credentials or tokens.

### 7.3. When to Use Properties vs. Java?

| Configuration approach | Suitable when | Things to watch out for |
|---|---|---|
| `application.yml` / environment variables | Fixed set of clients, easy per-environment deployment | Managing secrets and URLs per environment |
| Java builder | Configuration supplied by code or a trusted configuration service | Responsible for initializing all required fields accurately |
| Custom `ClientRegistrationRepository` | Many tenants/clients with a dynamic lifecycle | Designing caching, updates, synchronization, tenant isolation, and secret protection |

Do not turn the Java builder option into a dynamic client registration mechanism at the OP unless the OP actually supports that protocol or provisioning workflow.

## 8. Relationship Between `ClientRegistration` and `OAuth2AuthorizedClient`

This is one of the most important distinctions when developing OAuth 2.0 applications.

Suppose there is a registration:

~~~text
registrationId = corporate
clientId       = order-portal-web
scope          = openid profile email orders.read
~~~

Two users, Alice and Bob, can both sign in via the `corporate` registration, yet each has **their own tokens and authorized client state**.

~~~mermaid
flowchart TD
    R["ClientRegistration: corporate"] --> A["Alice's OAuth2AuthorizedClient"]
    R --> B["Bob's OAuth2AuthorizedClient"]
    A --> AT["Alice's access token / refresh token"]
    B --> BT["Bob's access token / refresh token"]
~~~

The registration is **the shared description of the client**; the authorized client is **the granted state within the corresponding principal context**.

In Spring Security, an `OAuth2AuthorizedClient` typically links:

- `ClientRegistration`;
- the authorized principal name;
- the current access token;
- the refresh token, if issued.

An authorized client storage and management mechanism can use the registration to perform token requests according to the selected grant type. Having a registration does not guarantee a token will be issued; tokens still depend on the protocol, client authentication, permissions, consent, and Authorization Server response.

### 8.1. Example: Reading the Authorized Client After OIDC Login

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientInfoController {

    @GetMapping("/client-status")
    public String clientStatus(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        return "registrationId="
                + authorizedClient.getClientRegistration().getRegistrationId()
                + ", accessTokenAvailable="
                + (authorizedClient.getAccessToken() != null);
    }
}
~~~

The example returns a simple status **without exposing token values**. In a real application, the token is attached to calls to **the appropriate Resource Server** via an HTTP client/authorized-client helper, while the API itself validates the token, issuer/audience/scope, and access permissions.

### 8.2. When One Registration Has Multiple Users

Never take Alice's token and use it for Bob just because both share `registrationId=corporate`. If the application stores tokens manually, the storage key must properly reflect both the client registration and the authorized principal/context.

Similarly, when supporting **OIDC account switching**, the application must ensure old token state is not reused for the new account.

## 9. An Application with Multiple `ClientRegistration`s

For example, the Portal supports two login systems: **Corporate OP** and **Partner OP**. Each provider issues a different client ID.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, email]
        provider:
          corporate-oidc:
            issuer-uri: https://id.company.example/realms/staff
          partner-oidc:
            issuer-uri: https://id.partner.example/realms/external
~~~

The application can select either flow:

~~~text
GET /oauth2/authorization/corporate
GET /oauth2/authorization/partner
~~~

After login, keep in mind:

- Two OPs may issue **identical `sub` strings belonging to two different people**. In OIDC, identity must generally be identified by the **`iss` + `sub`** pair.
- Emails may match across two issuers; do not automatically merge internal accounts solely because emails match.
- Scopes, client authentication methods, and consent mechanisms may differ by provider.
- If the UI lets users choose how to sign in, the choices must map to registrations permitted by the system, avoiding turning user input into an arbitrary issuer/token endpoint address.
- `clientSecret` and callback configurations must be accurate for each registration.

### 9.1. One Provider, Multiple Client IDs

Conversely, a single Authorization Server can also issue two separate client IDs for the same application across different flows:

~~~text
Registration 1: corporate-login
Provider:       internal-op
Grant:          authorization_code
Scope:          openid profile email

Registration 2: reporting-job
Provider:       internal-op
Grant:          client_credentials
Scope:          reports.read
~~~

Two registrations can reference the same provider while having different client IDs, secrets, grants, scopes, and token lifecycles. This separates permissions by function to reduce the blast radius of credentials.

## 10. Consequences of Misconfiguring Each Field

| Misconfiguration | Common symptom | What to check |
|---|---|---|
| Wrong `registrationId` in URL | Spring cannot find the client registration or fails to initiate login properly | Does the name after `/oauth2/authorization/` match? |
| Wrong `clientId` | OP rejects the request or token exchange | Does the Client ID match the right tenant/realm/provider? |
| Wrong or expired `clientSecret` | Token endpoint rejects client authentication | Are the secret, rotation mechanism, and method correct? |
| Wrong `clientAuthenticationMethod` | Token endpoint returns a client authentication error | Is the method allowed by the OP? |
| Wrong `redirectUri` | OP rejects the redirect URI or callback fails | Scheme, domain, port, path, proxy headers, and configuration at the OP |
| Wrong `authorizationGrantType` | Application starts an unsupported flow | Is the grant registered and permitted by the OP? |
| Missing `openid` in an intended OIDC flow | Does not exhibit expected OIDC login/ID token behavior | Does the registration request the OIDC scope? |
| Wrong `issuer-uri` or unreachable metadata | Client/discovery initialization or token verification fails | Issuer, network connectivity, certificates, and metadata |
| Wrong `token-uri` / `authorization-uri` | Redirect or token request fails | Are you using the exact endpoints of the same issuer/tenant? |
| Scope not granted | Consent or API request fails | Do the OP/client/Resource Server support that scope? |

The table only lists root-cause categories to guide diagnosis. **Exact error codes depend on the Spring Security version, provider, and protocol stage**.

### 10.1. Reverse Proxy Case

A Spring Boot application may run internally at:

~~~text
http://localhost:8080
~~~

but be accessed externally via:

~~~text
https://orders.example.com
~~~

If `{baseUrl}` is resolved from the internal address instead of the public address, the redirect URI is built as `http://localhost:8080/login/oauth2/code/corporate` and does not match the registration at the OP.

You must configure the reverse proxy and the mechanism for trusting forwarded headers reliably, or use an explicit redirect URI matching the deployment architecture. Do not accept headers from untrusted sources as the basis for constructing redirect URIs.

### 10.2. Secret Rotation Case

When a client secret is rotated at the OP while the application still uses the old value, the Spring-side registration **does not automatically learn the new secret**. You must update the secret source, ensure the application picks up the new configuration per your deployment mechanism, and confirm that the client auth method remains valid.

Never print the entire `ClientRegistration`, the entire environment, or token requests into logs for debugging; these data may contain secrets.

### 10.3. Environment Switching Case

Development, staging, and production typically have:

- Separate client IDs/secrets.
- Separate redirect URI domains.
- Separate issuers/realms/tenants or different policies.
- Different scopes and provider details.

Spring Boot profiles and environment variables can be used to manage differences. Never use production client secrets on developer machines or point a production callback to localhost.

## 11. Process for Setting Up a Registration in a Real Project

### Step 1: Identify the Application's Exact Role

Does the application need to:

- **Sign in users with OIDC** → usually Authorization Code with scope `openid`.
- **Call APIs on behalf of users** → choose grants and scopes permitted by the AS, and manage the authorized client after authorization.
- **Call APIs using a service identity** → usually `client_credentials`, with no user login.

An application can support multiple scenarios, using separate registrations if needed.

### Step 2: Register the Client at the Provider

Align with the administrator on:

- Client ID and client authentication method.
- Valid redirect URIs for Authorization Code.
- Enabled grant types.
- Scopes to request and consent policies.
- Issuer or endpoints to use.
- PKCE requirements, client authentication, and other security policies.

### Step 3: Declare `ClientRegistration`

Choose a clear `registrationId`. Declare `client-id`, `client-secret` (if needed), `authorization-grant-type`, `client-authentication-method`, `redirect-uri`, `scope`, and provider details via `issuer-uri` or manual endpoints.

### Step 4: Connect to Spring Security

- Use `oauth2Login()` for web login.
- Use `oauth2Client()` and/or `OAuth2AuthorizedClientManager` components for acquiring/using tokens to call APIs.
- If the application **receives bearer tokens to protect its own APIs**, that is also the **Resource Server** role, requiring different configuration (e.g., `oauth2ResourceServer()`). Having `ClientRegistration` alone does not make an API automatically validate bearer tokens.

### Step 5: Operate and Manage Configuration Lifecycle

Keep secrets in a secure store; control changes to issuers, callbacks, and scopes across environments. With multiple registrations, ensure the right client is chosen for each journey and do not mix authorized clients/tokens across principals.

## 12. Frequently Asked Questions

**Q1. Can `registrationId` be set to any string?**

It is an internal name chosen by the application, but it must be consistent and distinct among registrations in the repository. The name must be used consistently when configuring URLs or referencing the registration. Avoid changing it arbitrarily because this name can appear in callback paths and application configuration.

**Q2. If I only want OIDC login, do I need to configure `token-uri`?**

The Authorization Code flow needs the token endpoint to exchange the code for tokens. If the OP supports discovery via `issuer-uri`, Spring can obtain endpoints from metadata; when configuring manually, the required details must be provided.

**Q3. Having a client secret means the client is definitely an OIDC Relying Party?**

No. Having a secret only indicates that the client authentication mechanism can use a secret. A client using `client_credentials` may just be an OAuth 2.0 Client. OIDC Login requires requesting OIDC user authentication, typically including `openid` and processing an ID token.

**Q4. Does creating a `ClientRegistration` automatically request an access token?**

No. `ClientRegistration` only holds configuration. Only when an authorization flow or authorized client manager mechanism is triggered does the system make the corresponding token request.

**Q5. Can a single `ClientRegistration` be used for all users?**

Yes. The same registration typically represents the web application to the OP, while tokens and authorized client state are managed per principal and appropriate context. Never share one user's access token with another user.

**Q6. Why is `registrationId` `corporate` while the OP only knows `order-portal-web`?**

Because the OP uses `client_id`, whereas Spring uses `registrationId` to select internal configuration. The two names serve different roles and do not need to match.

**Q7. Is the `openid` scope needed for `client_credentials`?**

It is not a scope used for user login in service-to-service calls. For `client_credentials`, request API scopes supported by the Authorization Server; do not expect a user ID token just by adding `openid`.

**Q8. Can an `issuer-uri` from a user query parameter be used to add a new provider?**

It should not be. Issuers and endpoints used for authentication/token exchange must be managed from trusted configuration. If a system needs to support multi-tenant or dynamic providers, it must explicitly design an allowlist of accepted issuers, metadata validation, and tenant isolation rules.

## 13. Applied Exercise

An **Inventory Portal** application needs to let users sign in via an enterprise OP. The provider supplies the following details:

~~~text
Issuer:         https://login.example.com/realms/staff
Client ID:      inventory-web
Client secret:  retrieved from environment variable INVENTORY_CLIENT_SECRET
Grant type:     authorization_code
Redirect URI:   https://inventory.example.com/login/oauth2/code/staff
Requested scope: openid profile email
~~~

**Requirement:** design a Spring Boot registration using `registrationId=staff` and `providerId=staff-oidc`.

A suitable configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: staff-oidc
            client-id: inventory-web
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          staff-oidc:
            issuer-uri: https://login.example.com/realms/staff
~~~

In that configuration:

1. Spring looks up the registration using `staff`.
2. The Authorization Request uses `client_id=inventory-web`.
3. The browser is redirected to the OP's authorization endpoint provided by discovery.
4. The OP redirects back to `https://inventory.example.com/login/oauth2/code/staff` after completing the appropriate interactive steps.
5. Spring completes the token exchange and OIDC login according to the configuration.
6. The issued token, if stored, belongs to the `OAuth2AuthorizedClient` mechanism corresponding to the principal and registration.

If later there is a background job calling an API without an end user, consider **a separate registration using `client_credentials`** with functionally appropriate scopes, rather than reusing an employee's login token.

## Key Takeaways

**`ClientRegistration` is the configuration description of an OAuth 2.0 Client in Spring Security**. It brings together client identity, authentication method, grant type, redirect URI, scopes, display label, and provider metadata. `ClientRegistrationRepository` looks up these descriptions by `registrationId`; when an authorization flow takes place, `OAuth2AuthorizedClient` is what represents the granted token state.

When configuring OIDC, always distinguish between **`registrationId` in Spring**, **`clientId` at the OP**, **`issuerUri` of the provider**, **the user's identity**, and **the issued access token**. Making that distinction helps you configure login flows properly, call APIs with the right permissions, and safely manage registrations in systems with multiple clients or multiple providers.
