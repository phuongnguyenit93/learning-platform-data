# 1.1. Roles of OAuth 2.0 Client and OpenID Connect Relying Party

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between an **OAuth 2.0 Client** (an application requesting resource access permissions) and an **OpenID Connect Relying Party — RP** (an application relying on identity authentication results).
- Identify the roles of the user, Authorization Server, OpenID Provider, and Resource Server in a login and API-calling system.
- Explain why `access token`, `ID token`, and `refresh token` cannot be used interchangeably.
- Recognize the Spring Security components corresponding to each role, from `oauth2Login()` to `oauth2Client()`.
- Read a Spring Boot OIDC Client configuration and describe the login flow using Authorization Code.

## 1. Real-World Scenario: One Application, Two Needs

Suppose an order management application is built with Spring Boot. The enterprise uses a centralized identity system such as Keycloak, Microsoft Entra ID, or an OpenID Connect-compliant provider.

The application needs to solve two different problems:

1. **Who is currently opening the application?** When accessing the orders page, the user is redirected to the identity system to log in. After logging in successfully, the application needs to know the user's identity and create its own login session.
2. **What is the application allowed to do at another API?** When it needs to fetch order history from a separate service, the application must have permission to call that API, typically represented by an access token.

In this situation, the same Spring Boot application can simultaneously take on two roles:

- **OpenID Connect Relying Party (RP):** receives and validates authentication information issued by the identity provider, thereby logging the user in.
- **OAuth 2.0 Client:** requests and uses an access token to call protected APIs.

The two roles are closely related but address two different questions: **"Who has logged in?"** and **"Which resources is the client granted access to?"**.

## 2. What Is an OAuth 2.0 Client?

OAuth 2.0 is an **authorization** framework. It allows an application, called a *client*, to receive limited access to protected resources without needing to collect the user's password to call APIs directly.

For example: an order management application requests permission to read an employee's order list at another system. The user is sent to the Authorization Server to log in and grant consent, if required by the provider. The client receives an **access token** and uses that token to call the API.

### 2.1. Roles in OAuth 2.0

| Role | Responsibility | Example |
|---|---|---|
| **Resource Owner** | Entity that has rights over the resource; in interactive flows, usually the user | An employee with permission to view orders |
| **Client** | Application requesting access and using tokens | The Spring Boot order management application |
| **Authorization Server (AS)** | Processes authorization requests and issues access tokens | The enterprise authorization server |
| **Resource Server (RS)** | Stores/provides resources, validates the access token before serving APIs | The REST service managing orders |

**Client is not synonymous with browser.** In a server-side web application, the Spring Boot backend itself is the OAuth 2.0 Client; the browser only participates in redirecting the user. A mobile application or SPA can also be an OAuth 2.0 Client, with security requirements appropriate for that client type.

### 2.2. What Does an OAuth 2.0 Client Do?

Depending on the grant type and architecture, a client:

1. Is registered at the Authorization Server with a `client_id`, redirect URI, permission scopes (`scope`), and client authentication mechanism if applicable.
2. Initiates the corresponding authorization flow, such as Authorization Code with PKCE for interactive login.
3. Receives an authorization code and exchanges the code for tokens at the token endpoint, or directly requests a token in an appropriate grant such as `client_credentials`.
4. Stores and manages access tokens according to the user/client context; uses a refresh token when available and permitted.
5. Sends the access token to the Resource Server, typically via an HTTP header:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access_token>
~~~

The Resource Server validates the token and access permission requirements before processing the request. The client **must not send an ID token in place of an access token** when calling an API.

### 2.3. Confidential Clients and Public Clients

- **Confidential client** is capable of protecting its own credentials, such as a Spring Boot backend keeping the client secret on the server side.
- **Public client** cannot reliably keep a client secret confidential, such as an application running entirely in a browser or a mobile application installed on a user's device.

`client_id` is an identifier for the application, **not a password**. For public clients, do not embed a client secret in JavaScript or mobile apps. **PKCE** helps protect the Authorization Code from being intercepted and misused; being a confidential client is no reason to skip appropriate attack-prevention measures.

### 2.4. OAuth 2.0 Does Not Define an Identity Authentication Mechanism for Applications

When a user logs into an Authorization Server to grant consent, that login action serves the authorization process at the authorization server. The OAuth 2.0 specification **does not define a standard ID token for the client to authenticate the end user**.

An application can integrate login based on user data from an OAuth provider in a custom way, but it should not infer identity solely from the presence of an access token or from a token structure that the application guesses on its own. The identity authentication problem has its own protocol layer: **OpenID Connect**.

## 3. What Is an OpenID Connect Relying Party?

**OpenID Connect (OIDC)** is an identity layer built on top of OAuth 2.0. It standardizes how a client requests user authentication, receives authentication results, and retrieves standardized user information.

In OIDC:

| Component | Meaning |
|---|---|
| **End-User** | The user who needs to be authenticated |
| **OpenID Provider (OP)** | The system that authenticates users and issues ID tokens; also provides the related OAuth 2.0 endpoints |
| **Relying Party (RP)** | The application that trusts valid authentication results issued by the OP, after performing the required validation steps itself |
| **ID Token** | A token containing claims describing the authentication event and user identity for the RP to consume |
| **UserInfo Endpoint** | An OIDC endpoint that can return additional user information when called with an appropriate access token |

At the protocol level, an RP is also an OAuth 2.0 Client registered with the OP. However, **not every OAuth 2.0 Client is an RP**. For example, a background job requesting a token via `client_credentials` to call an API: it is an OAuth client, but it does not perform end-user login via OIDC.

### 3.1. When Does a Client Become an OIDC Relying Party?

In an OIDC request, the client requests the **`openid`** scope. This is the key signal for the OP to handle the request according to OpenID Connect and issue an ID token following the appropriate flow.

Example scopes:

~~~text
scope=openid profile email
~~~

- `openid`: requests OIDC functionality and user identification.
- `profile`: requests a standard set of profile claims, depending on the OP's capabilities and claim-issuing policy.
- `email`: requests email claims such as `email` and `email_verified` if provided.

You should not assume that requesting a scope guarantees all corresponding claims will always be present in the ID token. The OP may provide some claims through the UserInfo Endpoint or omit them according to policy.

### 3.2. The ID Token Is Proof for the RP to Authenticate the User

An ID token is a JWT in OIDC format, typically signed by the OP. An illustrative payload might look like this:

~~~json
{
  "iss": "https://idp.example.com/realms/acme",
  "sub": "8f61c2b4-3b72-4b26-b22c-93f165b2c9a0",
  "aud": "orders-web",
  "iat": 1760000000,
  "exp": 1760003600,
  "nonce": "random-request-binding"
}
~~~

*The values above are illustrative data, not a real token.*

Important claims:

| Claim | Meaning | What the RP Needs to Check |
|---|---|---|
| `iss` | Issuer that issued the token | Must match the OP configured by the RP |
| `sub` | User identifier at the issuer | Should combine `iss` + `sub` as a durable identity key |
| `aud` | Intended audience of the token, including the RP's client ID | The RP must be a valid audience |
| `exp`, `iat` | Expiration and issuance timestamps | Validate time validity according to OIDC rules |
| `nonce` | Value binding the token to the authentication request | Validate when nonce is used in the request |
| `auth_time` | Time when the user was authenticated | Useful when re-authentication is required and OIDC policies apply |

The RP must verify the signature or corresponding token protection mechanism, issuer, audience, time validity, and other conditions according to the standard and the flow used. Merely decoding a JWT into JSON and trusting its contents **is not ID token validation**.

Email or display name are only profile attributes and can change. **`sub` scoped by `iss` is a much more appropriate basis for linking internal accounts**. Some OPs use *pairwise subject identifiers*, so `sub` may differ across clients.

### 3.3. What Does the RP "Rely" On?

The word *relying* does not mean trusting any data sent by the browser. It means that after completing protocol verification, the RP relies on the authentication assertion of a **pre-configured and trusted OP**.

The RP does not directly verify the user's password at the OP. After successful authentication, the RP can create an `Authentication` and a login session in its own application. **Business authorization** still belongs to the application: successful login does not automatically mean the user is allowed to approve every order.

## 4. Distinguishing Authorization Code, Access Token, ID Token, and Refresh Token

| Value | Issued by / Received by | Primary Purpose | Used to Call Business APIs? |
|---|---|---|---|
| **Authorization code** | Returned by AS/OP to client's redirect URI | Short-lived, single-use value exchanged for tokens | No |
| **Access token** | Issued by AS to client; received by RS | Carries resource access permissions, per scope/audience/policy | Yes, if the API accepts the token |
| **ID token** | Issued by OP to RP | Authenticates and conveys user identity/login event | Never use instead of access token |
| **Refresh token** | May be issued by AS/OP to client | Requests new access tokens per server policy | No |

Common points of confusion:

- An ID token has an audience targeting the **RP/client**; an access token is intended for the **API/Resource Server** and has its own representation. An access token may be a JWT or an opaque string: do not assume it can always be decoded.
- An access token proves permission to call an API within granted scopes; it does not mean it is a user login credential intended for the client.
- An ID token helps the RP authenticate the user; it does not authorize reading or writing resources at an API.
- A refresh token may not be issued, even after a successful login, and must be stored with extreme care.
- The same OIDC Authorization Code request can return both an ID token and an access token: both tokens appear together, but they have **different consumers and validation responsibilities**.

## 5. Authorization Code Flow When Spring Boot Plays Both Roles

For a server-side Spring Boot web application, the common flow is **OIDC Authorization Code**. The OP both authenticates the user and acts as the Authorization Server issuing access tokens.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant S as Spring Boot (Client and RP)
    participant OP as OpenID Provider / Authorization Server
    participant API as Resource Server
    U->>B: Open a page requiring login
    B->>S: GET /orders
    S-->>B: Redirect to OP
    B->>OP: Authorization request (openid, state, nonce, PKCE if used)
    OP->>U: Authenticate and request consent if needed
    OP-->>B: Redirect with code and state
    B->>S: GET /login/oauth2/code/corp?code=...&state=...
    S->>OP: Exchange code for tokens at token endpoint
    OP-->>S: ID token, access token (refresh token if issued)
    Note over S: Validate ID token and create Authentication / session
    S->>API: Call API with access token
    API-->>S: Authorized data
    S-->>B: User page or data
~~~

Steps to understand:

1. **Protect resources:** Spring Security detects a request requiring authentication and redirects the browser to start login.
2. **Create authorization request:** The client puts `client_id`, `redirect_uri`, scope containing `openid`, and request-protection data into the authorization URL. `state` binds the response to the request and prevents CSRF in the flow; `nonce` binds the ID token to the OIDC request; PKCE, if applied, uses `code_challenge`.
3. **Authenticate at OP:** The user logs in at the OP. The client never needs to receive their password.
4. **Receive authorization code:** The browser is redirected back to the registered redirect URI with `code` and `state`. The code is not yet an access token.
5. **Back-channel exchange:** The Spring backend sends the code to the token endpoint, along with client credentials and/or `code_verifier` as configured.
6. **Validate OIDC result:** Spring Security processes and validates the ID token and builds an OIDC principal. The application may retrieve additional claims from the UserInfo Endpoint when appropriate.
7. **Establish application state:** The user is authenticated in `SecurityContext`; servlet applications typically maintain login via an HTTP session/cookie.
8. **Call APIs:** When needed, the OAuth client uses a valid access token for the corresponding registration and user to call the Resource Server. The API independently validates the token and access permissions.

**Note:** Logging in at the OP and logging in at the application are two related sessions/states, but they are not identical. Expiring a Spring Boot session does not necessarily log the user out of the OP; logging out on the OP side also does not automatically invalidate every application session unless an appropriate logout mechanism is integrated.

## 6. How Does Spring Security Represent These Roles?

Spring Security provides distinct abstractions to handle client configuration, OAuth state, and authenticated identity.

| Component / API | Role |
|---|---|
| `ClientRegistration` | Client registration details: `clientId`, scopes, grant type, redirect URI, endpoints, and provider |
| `ClientRegistrationRepository` | Looks up registrations by `registrationId`, e.g., `corp` |
| `oauth2Login()` | Enables login based on OAuth 2.0 Authorization Code; when the provider supports OIDC and `openid` is requested, handles OIDC login |
| `OidcUser` / `OidcIdToken` | OIDC principal and ID token processed by Spring Security after login |
| `SecurityContext` / `Authentication` | Represents the authenticated user state in the application |
| `OAuth2AuthorizedClient` | Associates a `ClientRegistration` with the access token and refresh token (if any) issued for a principal/client |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Stores and retrieves authorized clients/tokens in the appropriate context |
| `oauth2Client()` | Enables OAuth 2.0 client support for authorizing and using tokens for outbound calls |
| `OAuth2AuthorizedClientManager` | Coordinates authorize/reauthorize, e.g., obtaining and refreshing tokens per supported grant |
| `oauth2ResourceServer()` | Configures a **different role**: the application accepts bearer tokens to protect its own APIs |

An application can simultaneously be an RP, an OAuth 2.0 Client, and a Resource Server. However, configuring `oauth2Login()` **does not automatically turn the application's API into a Resource Server**; accepting and verifying bearer tokens requires separate configuration.

### 6.1. Example OIDC Client Configuration in Spring Boot

Minimal dependency for client features when using Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: \${OIDC_CLIENT_ID}
            client-secret: \${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://idp.example.com/realms/acme
~~~

In this example:

- `corp` is the **registrationId** used to select the client configuration, not a mandatory OIDC standard name.
- `client-id` identifies the application at the OP; `client-secret` is the backend confidential client's secret. Sensitive values are provided via environment variables/a secret manager.
- `issuer-uri` points to the OIDC issuer trusted by the application. Spring Security can use provider metadata discovery to obtain the authorization endpoint, token endpoint, JWK Set URI, and related information, depending on the provider.
- The default redirect URI in the example sends the user back to `/login/oauth2/code/corp`. The actual URI must be registered to match at the OP.
- `openid` makes this an OIDC login request, while `profile` and `email` request appropriate additional claims.

This configuration assumes the OP supports OIDC discovery and Authorization Code, and that the client has been registered at the OP. The domain `idp.example.com` is an example address only.

### 6.2. Enabling Login and OAuth 2.0 Client Support

~~~java
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
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Meaning:

- `oauth2Login()` serves the **user login** step; when a valid ID token is received, Spring creates an OIDC principal for the request.
- `oauth2Client()` supports the **application using API access permissions** step, including retrieving authorized clients and integrating with token management mechanisms.
- The `authorizeHttpRequests(...)` section specifies which application resources require login. Permissions for specific business actions must enforce separate policies; do not infer them merely from the user having an ID token.

Depending on the version, Spring Boot may auto-configure part of these features if there is only one client configuration; the example above explicitly configures both features to clearly distinguish their roles.

### 6.3. Reading OIDC Identity After Login

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public UserView currentUser(@AuthenticationPrincipal OidcUser user) {
        return new UserView(
            user.getIdToken().getIssuer().toString(),
            user.getIdToken().getSubject(),
            user.getFullName()
        );
    }

    record UserView(String issuer, String subject, String fullName) {}
}
~~~

Here `OidcUser` allows the application to retrieve the identity processed by the OIDC login system. `fullName` may be absent if the OP does not return the corresponding claim. Choosing `issuer` + `subject` as the identifier is more appropriate than using email or display name.

The controller above is for an endpoint requiring OIDC login. If the same application also supports another login mechanism, the principal will not necessarily always be of type `OidcUser`; application code must properly handle all allowed authentication types.

### 6.4. Obtaining an Access Token to Call an API

In a servlet application, you can retrieve the authorized client granted for the registration and user:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/orders/access-status")
    public String accessStatus(
            @RegisteredOAuth2AuthorizedClient("corp")
            OAuth2AuthorizedClient authorizedClient) {

        return authorizedClient.getAccessToken() != null
                ? "Access token is available for an API request"
                : "No access token is available";
    }
}
~~~

This is an illustrative example of receiving `OAuth2AuthorizedClient`, **not returning tokens in an HTTP response**. In real business logic, the application sends the token via the `Authorization: Bearer ...` header to the right Resource Server, typically using an HTTP client integrated with `OAuth2AuthorizedClientManager` to manage obtaining/refreshing tokens.

Having a token **does not guarantee** that the token works for every API. The Resource Server also checks issuer, audience, scope, expiration, authorization policies, and the token format it supports. If you need to call another API with a different scope/audience, you may need to register or request appropriate permissions.

## 7. Deployment Scenarios: When Is It a Client, When Is It an RP?

| Scenario | OAuth 2.0 Client? | OIDC RP? | Explanation |
|---|---|---|---|
| Web app logging in with OIDC via an OP | Yes | Yes | Requests tokens via OAuth, validates ID token to log in |
| Web app using the user's access token to call an API | Yes | Possibly | It is a Client; it is an RP if it also uses OIDC to authenticate the user |
| Backend running background jobs with `client_credentials` | Yes | No | Permissions granted to the client/service, no end user to authenticate with an ID token |
| REST API only receiving/validating bearer tokens | Not necessarily | Not necessarily | Primarily a Resource Server; only a Client/RP if it also has the corresponding capabilities |
| Application only receiving OIDC callback and creating a session, not calling a separate API yet | Yes | Yes | An RP is still an OAuth/OIDC Client even if the access token is not used to call business APIs |

**Comparison example:** "Application A allows employees to log in via Keycloak, then uses the access token to read `/employees` from Service B." A is an RP **and** an OAuth 2.0 Client. Keycloak is the OP/Authorization Server. Service B is the Resource Server. The user is the End-User and, in the appropriate authorization flow, the Resource Owner.

## 8. Security Boundaries to Keep Clear

### 8.1. Three Mechanisms That Do Not Replace Each Other

- **`state`** binds the authorization response to the initial request and helps prevent CSRF in redirect flows.
- **`nonce`** binds the ID token to the OIDC request session to prevent token replay or substitution attacks according to the OIDC mechanism.
- **PKCE** binds the authorization code to the party that initiated the request via `code_challenge` and `code_verifier`, reducing the risk of the code being intercepted and exchanged for tokens by another party.

These measures serve distinct purposes. Let a battle-tested OIDC/OAuth library execute the flow and standard validations; do not write a custom callback handler that skips verification just to simplify code.

### 8.2. Tokens Must Go to the Intended Recipient

- Do not use an **ID token** to call APIs in place of an access token.
- Do not use an **access token** received from the browser as sole proof for RP login while bypassing OIDC.
- Do not write access tokens, refresh tokens, authorization codes, or client secrets to logs or responses.
- Use HTTPS and strictly registered redirect URIs; avoid open redirects or handling callbacks at arbitrary URLs.
- Limit scopes to what is needed, protect token/secret storage, and establish appropriate expiration/revocation policies.

### 8.3. Authentication and Authorization Remain Distinct

OIDC tells you that the user has been authenticated by the OP in the context described by the ID token. To decide "is this employee allowed to approve order 123?", the application needs to check **business permissions**. You can map claims, groups, or roles from the OP into Spring Security authorities if policy requires, but do not assume every claim from the OP grants full permissions to the user.

If the application exposes APIs to other clients, Spring Security also needs a Resource Server configuration to accept and verify access tokens at those APIs. Evaluate **web login** and **API protection** separately.

### 8.4. Logging Out Across Multiple Places

Spring Security's application `logout()` typically handles local login state. If you want the user to log out at the OP as well, you must integrate the corresponding OIDC mechanism (e.g., RP-Initiated Logout when supported by the provider). Conversely, an active OP session may allow the next login to proceed without the user having to re-enter a password.

## 9. Common Misconceptions

**"Having an access token means you already know who the user is?"**  
No. An access token is for accessing resources and may represent the client, the user, or another context depending on the grant and policy. An RP needs an appropriate identity authentication mechanism, typically via an OIDC ID token.

**"Having the `openid` scope means all profile information will always be in the ID token?"**  
No. `openid` triggers an OIDC request; claims like name and email depend on scopes, OP capabilities, and policies. Some claims may come from the UserInfo Endpoint.

**"Do `oauth2Login()` and `oauth2Client()` have the same job?"**  
No. The first serves the login flow; the second serves authorization/token management for the client. They can share the same client registration and can both be enabled in one application.

**"Is an application that only calls APIs using `client_credentials` an RP?"**  
No. It is an OAuth 2.0 Client performing service-to-service authorization; it does not authenticate an End-User with OIDC.

**"Does a Spring Boot application with `spring-boot-starter-oauth2-client` automatically protect REST APIs with JWT?"**  
No. Protecting endpoints with bearer access tokens is the Resource Server role, typically using `spring-boot-starter-oauth2-resource-server` and appropriate token validation configuration.

**"If the ID token is a JWT, must the access token also be a JWT?"**  
No. OIDC specifies the ID token as a JWT, whereas the access token format is decided by the Authorization Server/Resource Server according to the protocol and products involved.

## 10. Self-Check Scenario

Identify the role of each component in the system:

> The **Portal** application running Spring Boot redirects users to **Identity Server** to log in. Portal receives an ID token and an access token. Portal then uses the access token to call **Inventory API** to view the inventory list.

- **Portal**: OAuth 2.0 Client when requesting and using the access token; OIDC RP when validating the login result using the ID token.
- **Identity Server**: OpenID Provider and Authorization Server.
- **Inventory API**: Resource Server, validating the access token and access permissions.
- **User**: End-User; may also be the Resource Owner in the authorization flow for their resources.

If Portal later exposes REST endpoints for a mobile app sending bearer tokens, Portal can also act as a **Resource Server**. Roles are determined by **behavior at each interaction**, not merely by name or the number of deployed applications.

## Key Takeaways

**OAuth 2.0 Client** enables an application to obtain and use resource access permissions via access tokens. **OpenID Connect RP** enables an application to authenticate users based on valid ID tokens issued by an OP. In Spring Security, these two responsibilities often appear together in a web application, but you must clearly distinguish the target consumer of each token, the handling components, and the security rules of each role.
