# Resource Owner, Client, Authorization Server, and Resource Server

> **Chapter:** Protocol and Terminology  
> **Scope:** OAuth 2.0/OpenID Connect (OIDC) Authorization Server with Spring Security, Spring Authorization Server, and Spring Boot.

## Learning Objectives

After completing this lesson, you will be able to:

1. Accurately distinguish the four **logical roles** defined in OAuth 2.0: Resource Owner, Client, Authorization Server, and Resource Server.
2. Explain who authenticates the user, who issues tokens, who uses tokens, and who enforces resource access permissions.
3. Describe an Authorization Code flow with PKCE; distinguish between an access token, an ID token, and a refresh token.
4. Map each role to Spring Security/Spring Authorization Server components; identify common design mistakes.
5. Identify trust boundaries and verification points when deploying a real-world application.

## 1. Why Separate the Four Roles?

Suppose a booking system has a web application, a booking management service, and a centralized login system. Users want to view their bookings without providing their password to every API. OAuth 2.0 separates **resource control**, **the application requesting access**, **the authorization-issuing service**, and **the resource-hosting service** into four distinct roles.

**OAuth 2.0 is primarily an authorization framework**: a client is granted limited access to protected resources. OIDC builds an **authentication** layer on top of OAuth 2.0 so that the client can verify that a user has logged in.

The four roles are **protocol responsibilities**, not necessarily four servers, four microservices, or four codebases. A single application can play multiple deployment roles, yet it must still separate the responsibilities and security checks of each role.

| Role | Question this role answers | Core responsibility | Example |
| --- | --- | --- | --- |
| **Resource Owner** | Who has authority to grant access to the resource? | Controls or has the authority to permit access to protected resources | The user who owns the booking data |
| **Client** | Which application is requesting and using access? | Initiates authorization requests, receives tokens, and calls APIs on behalf of the user or for itself | Booking web app, mobile app, integration backend |
| **Authorization Server (AS)** | Who authenticates and issues tokens? | Authenticates according to policy, processes authorization requests, registers clients, and issues/manages tokens | Login service using Spring Authorization Server |
| **Resource Server (RS)** | Which API protects the data? | Receives access tokens, validates tokens, and checks permissions before returning data | Booking API using Spring Security Resource Server |

### 1.1. Resource Owner: The Authority Over the Resource

The Resource Owner is typically the **end user** in interactive login scenarios. For example, Lan has permission to view her booking data and can allow the web application to use the `booking.read` scope. The Resource Owner can be another entity depending on the business model; the protocol definition does not require every resource to be tied to an individual person.

Key points to remember:

- **The Resource Owner is not the Client.** Lan uses the web application, but the web application is the Client; Lan is the person with authority over the data.
- **The Resource Owner is not the Authorization Server.** The login page may be rendered by the AS, but authentication policies and consent approval are enforced by the AS on behalf of the system.
- **Logging in does not automatically mean consenting to every permission.** The AS may require per-scope consent or have a policy that skips the consent screen in appropriate cases.
- **Identity and object-level permissions are different.** Knowing the user's `sub` is not enough to conclude they are allowed to view all bookings. The RS must still verify ownership, tenant, and business rules.

### 1.2. Client: The Application Requesting Access

The Client is the application that interacts with the AS to obtain access and uses the access token when calling the RS. In OAuth, the word "client" **does not exclusively mean a browser**: a Spring Boot backend can also be a client.

Two common client types:

| Client type | Characteristics | Design implications |
| --- | --- | --- |
| **Confidential client** | Capable of securely keeping client credentials on the server side | For example, backend/BFF; can authenticate using a client secret or another suitable mechanism |
| **Public client** | Cannot keep long-lived secrets confidential, such as a pure SPA or a mobile app distributed to users | Do not embed a client secret as a secret; use Authorization Code + PKCE and platform-appropriate safeguards |

Each client is identified by the AS via `client_id` and registers parameters such as redirect URIs, client authentication method, grant types, and allowed scopes. **`client_id` is an identifier, not a password.**

A client can act as a **Relying Party (RP)** when using OIDC for login. Similarly, a service can be both an RS when receiving API calls and a Client when it subsequently calls another API; both behaviors must be configured according to their respective responsibilities.

### 1.3. Authorization Server: The Issuer of Authorization and Tokens

The AS handles **protocol-level authorization**:

1. Receives the client's authorization request and validates the client, redirect URI, grant type, and scopes.
2. Authenticates the Resource Owner when the flow requires user interaction; collects or applies consent decisions according to policy.
3. Issues authorization codes and/or tokens according to valid grant types.
4. Manages authorization state, token lifecycle, and related policies such as expiration, revocation, signing keys, and consent.
5. With OIDC, acts as the **OpenID Provider (OP)** and issues ID tokens when protocol requirements are met.

**The AS does not necessarily store business data.** It may know who the user is and which scopes a client was granted without owning the bookings table. Being able to issue an access token does not replace the RS's per-record permission checks.

In the Spring ecosystem, **Spring Authorization Server** provides the endpoints and mechanisms to build an AS, while the deploying application is responsible for configuring user authentication, client registration, keys, storage, policies, and operations.

### 1.4. Resource Server: The API Protecting Resources

The RS is the server receiving requests for protected resources, such as `GET /api/bookings/123`. Its responsibilities are:

- Accept access tokens only through the mechanism configured by the system.
- Validate the token: signature or introspection, expiration, issuer, audience, and related constraints.
- Enforce scopes/authorities and business permissions for the requested data.
- Return `401 Unauthorized` when valid authentication credentials are missing or invalid; return `403 Forbidden` when authenticated but lacking sufficient permissions in the appropriate situation.

An RS **does not issue access tokens** merely because it exposes API endpoints. For JWTs, the RS can verify signatures locally using the AS's public key and cache the keys; it does not need to call the AS on every request. For opaque tokens, the RS typically calls the configured **token introspection** endpoint to determine whether the token is active and retrieve its attributes.

## 2. Visualizing the Boundaries Between Roles

~~~mermaid
flowchart LR
    U["Resource Owner<br/>User Lan"]
    C["Client<br/>Booking Web / BFF"]
    AS["Authorization Server<br/>Login and token issuance"]
    RS["Resource Server<br/>Booking API"]

    U -->|"Uses application"| C
    U <-->|"Login / consent<br/>via browser"| AS
    C <-->|"Authorization request<br/>exchange code for token"| AS
    C -->|"Access token + API request"| RS
    RS -->|"Permitted data returned"| C
    RS -.->|"Fetch public keys / introspection<br/>when needed"| AS
~~~

In a BFF deployment, the browser typically maintains a session with the backend; the backend acts as the Client, stores tokens server-side, and sends the access token to the RS. For a public client, token storage location and protection mechanisms differ, but the protocol responsibilities remain similar.

The table below helps prevent confusing "who talks to whom":

| Interaction | Meaning |
| --- | --- |
| Resource Owner ↔ AS | Authentication and consent decision when the flow requires interaction |
| Client ↔ AS | Requesting authorization, exchanging the authorization code for tokens, refreshing tokens if supported |
| Client → RS | Calling APIs with an **access token** |
| RS ↔ AS | Retrieving public keys, metadata, or performing introspection depending on token type; not necessarily a call on every request |
| Resource Owner ↔ Client | User interacting with the application; this is product behavior, not proof that the RS has authorized access |

## 3. End-to-End Example: Viewing Bookings with Authorization Code + PKCE

Assume the system has the following components:

- **Resource Owner:** Lan, who wants to view her data.
- **Client:** `booking-web`, a Spring Boot BFF registered with the AS.
- **AS:** `https://auth.example.test`.
- **RS:** `https://api.example.test`, providing the Booking API.
- **Scope:** `booking.read`, describing the API scope requested by the client.
- **OIDC scope:** `openid` if the application also needs OIDC login.

> The `.example.test` domain and application names below are for illustration only and are not live endpoints.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner (Lan)
    participant C as Client (Booking Web/BFF)
    participant AS as Authorization Server
    participant RS as Resource Server (Booking API)

    U->>C: Open My Bookings page
    C-->>U: Redirect to AS with state, PKCE challenge, scope
    U->>AS: Open /oauth2/authorize request
    AS->>U: Authenticate and request consent if required by policy
    U->>AS: Authenticate / approve
    AS-->>U: Redirect back to client with code and state
    U->>C: Access redirect URI carrying code and state
    C->>C: Verify state
    C->>AS: POST /oauth2/token with code and code_verifier
    AS-->>C: Access token (and ID token if OIDC)
    C->>RS: GET /api/bookings with Bearer access token
    RS->>RS: Validate token, scope, and data permissions
    RS-->>C: Only permitted bookings
    C-->>U: Display results
~~~

### 3.1. Step-by-Step Breakdown

**Stage A — Client requests authorization.** When Lan opens a page requiring API access, the Client redirects the browser to the AS authorization endpoint. The request typically includes `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`, `code_challenge`, and `code_challenge_method=S256`. The Client generates `code_verifier` and retains it for the code exchange; only the challenge is sent in this step. If using OIDC, `scope` must contain `openid`.

**Stage B — AS authenticates and issues an authorization code.** The AS validates the client, redirect URI, and requested scopes; authenticates Lan if needed; and applies consent rules. If successful, it redirects back to a valid redirect URI with a **short-lived, single-use authorization code** and `state`. The code is an intermediate artifact for exchanging tokens; **the code is not an access token**.

**Stage C — Client exchanges the code.** The Client verifies `state` to match the request it initiated, then calls the token endpoint with the authorization code, matching redirect URI, and `code_verifier`. A confidential client must also authenticate with the AS using its registered authentication method, if required by configuration. The AS validates PKCE and token issuance conditions, then returns an access token; it may also return a refresh token and, in OIDC, an ID token.

**Stage D — Client calls the API.** The Client sends the access token in the HTTP header:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

**Stage E — RS validates and decides.** The RS verifies that the token was issued by a trusted AS, is intended for this API, has not expired, and has the appropriate scope, then proceeds to verify that the booking record belongs to Lan. Only when all conditions are satisfied does the RS return the resource.

The key takeaway: **the AS decides whether to issue a token**, whereas **the RS decides whether a specific API request is permitted**. A valid access token can still be rejected by the RS due to insufficient permissions.

## 4. What Are Tokens and Which Token Does Each Role Use?

| Artifact | Who issues it? | Who receives/uses it? | Purpose |
| --- | --- | --- | --- |
| **Authorization code** | AS | Client exchanges it at the token endpoint | Proves the client completed the authorization stage and exchanges it for tokens under binding constraints |
| **Access token** | AS | Client sends to RS; RS validates | Grants access to resources within specific scopes, audience, and lifetime |
| **ID token** (OIDC) | OP/AS | OIDC Client/RP validates | Conveys information about the authentication event and user identity to the client |
| **Refresh token** (if issued) | AS | Client sends to AS | Requests a new access token according to policy; not used to call APIs |
| **Client secret** (if any) | Configured during client registration | Confidential client uses to authenticate with AS | Client credential; **not a user token** |

Three concepts must be distinguished:

- **An access token is not the same as an ID token.** APIs must process **access tokens** intended for the right audience; do not treat an ID token as a Bearer token for API calls.
- **JWT is just a token format.** An access token can be either a JWT or opaque. The RS must follow the format and verification mechanism agreed upon with the AS.
- **Scope does not replace full authorization.** `booking.read` indicates that the token has permission to read the Booking API; it does not specify which booking IDs the client is allowed to read.

Example claims that may appear in a JWT access token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["booking-api"],
  "exp": 1893456000,
  "scope": "booking.read"
}
~~~

This is an **illustrative** payload, not a valid token, and it contains no signature. `sub` typically identifies the user in user-involved flows, though in some grants such as client credentials it may identify the client. `aud` is the intended recipient of the token and must be designed/issued by the AS to match the RS; it is not automatically inferred from `scope`.

## 5. How Do OAuth 2.0 and OIDC Change Responsibilities?

With **plain OAuth 2.0**, the Client primarily cares about whether it has obtained a valid access token to call the RS. OAuth 2.0 itself does not define a standardized user authentication mechanism whereby the Client can inspect an access token and reliably conclude "who the logged-in user is."

With **OpenID Connect**, the Client requests the `openid` scope and becomes a **Relying Party (RP)**. An AS supporting OIDC is called an **OpenID Provider (OP)**. The OP issues an **ID token** containing OIDC-defined claims (e.g., `iss`, `sub`, `aud`, `exp`, `iat`). The Client must validate the ID token per OIDC requirements, such as signature, issuer, audience, expiration, and nonce if a nonce was sent. The OP may also expose a UserInfo endpoint to return additional claims according to scopes and policy.

For example, `booking-web` has two separate purposes:

1. Use the **ID token** (alongside the application's login session mechanism) to know that the user has been authenticated by the OP.
2. Use the **access token** to call `booking-api`.

The RS does not need the ID token to prove "who Lan is"; it needs the access token and performs appropriate access-control checks.

## 6. Mapping to Spring Security and Spring Authorization Server

In a Spring Boot application, library names reflect primary responsibilities; a single system may use multiple configuration groups.

| Protocol role | Common Spring components | Function |
| --- | --- | --- |
| Resource Owner | Users/accounts, login mechanisms such as `UserDetailsService` or connected identity providers | Represents the principal authenticated according to policy; there is no dedicated "ResourceOwner" annotation |
| Client | `spring-security-oauth2-client`, `ClientRegistration`, OAuth2 Login/Authorized Client | Registers providers and clients, supports OIDC login, stores/manages authorized clients, and calls APIs |
| Authorization Server | **Spring Authorization Server**, `RegisteredClientRepository`, `OAuth2AuthorizationService`, endpoint/signing-key configuration | Handles the authorization protocol, issues tokens, registers clients, and persists authorization state |
| Resource Server | `spring-security-oauth2-resource-server`, `JwtDecoder` or opaque-token introspector, `SecurityFilterChain` | Validates access tokens and protects APIs |

### 6.1. Resource Server Configuration Example

A Booking API using JWTs issued by the AS can be configured as follows:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

And enforce the required scope when reading bookings:

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/bookings/**")
                .hasAuthority("SCOPE_booking.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

In Spring Security's JWT Resource Server configuration, scope values are typically mapped to authorities prefixed with `SCOPE_`, so `booking.read` becomes `SCOPE_booking.read`. The code above enforces **endpoint-level access control**; checking whether the booking belongs to the corresponding user/tenant still needs to be implemented in the business layer or data access policy.

**Note on audience:** `issuer-uri` identifies the trusted metadata/key source and corresponding default JWT checks. In multi-API systems, configure/register an additional `aud` validator matching the audience issued by the AS. Do not assume that a valid issuer alone means a token is intended for every RS.

### 6.2. OAuth2/OIDC Client Configuration Example

A Spring Boot backend/BFF that needs to log in with the AS can register the client via configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          booking-web:
            provider: booking-idp
            client-id: booking-web
            client-secret: ${BOOKING_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - booking.read
        provider:
          booking-idp:
            issuer-uri: https://auth.example.test
~~~

This is an example for a **confidential client with a backend holding the client secret**. The AS side must register the exact `client_id`, redirect URI, authentication method, grant type, and allowed scopes. The secret in this example is supplied via an environment variable; never commit real secrets to the repository. PKCE must be enabled/configured consistently with the client type and the AS.

### 6.3. Authorization Server Responsibilities Example

On the Spring Authorization Server side, common concepts include:

- **`RegisteredClientRepository`:** stores client identities and policies; for example, `booking-web` is permitted to use Authorization Code, which redirect URIs, and which scopes.
- **`OAuth2AuthorizationService`:** stores authorization and token records to support the authorization lifecycle.
- **`OAuth2AuthorizationConsentService`:** stores permission consent when the application requires consent.
- **`AuthorizationServerSettings`:** configures the issuer, endpoints, and AS settings.
- **`JWKSource` / signing keys:** provides keys to sign tokens and publishes the appropriate public keys so the RS can verify JWTs.
- **OIDC configuration:** enables the required OIDC endpoints/features alongside OAuth 2.0 endpoints.

Creating an AS does not automatically turn every API in the same application into an RS. To protect APIs, you must configure the corresponding RS setup and access controls. In production deployments, use durable persistence for clients/authorizations/consents as appropriate, protect signing keys, plan key rotation, and define a stable HTTPS issuer.

## 7. Commonly Confused Scenarios

### Scenario A — An Application Calls an API Without a User

A reporting service calls the Booking API using **Client Credentials**. The client is the reporting service, the AS authenticates the client and issues an access token, and the RS validates the token. **There is no user login or consent step in this request.** The Resource Owner does not necessarily appear as an interactive actor at runtime, because the grant is based on client permissions already authorized by the system. Service permissions must be scoped separately; do not assume the token represents a specific user.

### Scenario B — One Service Plays Two Roles

The Booking API receives an access token from the Web App (**RS**) and then needs to call the Payment API (**Client** toward the Payment API). The Booking API must authenticate incoming requests as an RS, while also having a mechanism to obtain/propagate access appropriately as a Client. Never blindly reuse an incoming access token for the Payment API if that token does not have the appropriate audience/permissions.

### Scenario C — An Authenticated User Views Someone Else's Data

Lan has an access token containing `booking.read`. Lan calls `GET /api/bookings/999`, but booking 999 belongs to Minh. Having an access token with a valid scope **does not grant permission to read booking 999**. The RS must deny the request per business policy. This is a classic example of object-level authorization.

### Scenario D — An ID Token Is Used Instead of an Access Token

The Web App received an ID token via OIDC and sends it to the Booking API with `Authorization: Bearer ...`. That is a misuse of purpose: the ID token is intended for the Client/RP, whereas the RS must require an access token intended for the API. The fact that both may be JWTs does not make them interchangeable.

## 8. Security Pitfalls and Mitigations

| Design mistake | Why it is dangerous | Mitigation |
| --- | --- | --- |
| Placing the client secret in JavaScript shipped to the browser | Users or third parties can inspect the secret | Use a public client with PKCE, or a BFF/confidential client keeping the secret server-side |
| Omitting `state` or not binding PKCE | Weakens protection for redirect and code-exchange flows | Use `state`, Authorization Code + PKCE (`S256`), and validate callback and redirect URIs |
| API accepts a token just because its JSON decodes | Payload could be forged or the token could be intended for another party | Verify signature/introspection, issuer, expiration, audience, and permissions |
| API checks only `scope` and skips record ownership | Allows reading other users' data (BOLA/IDOR) | Enforce owner/tenant/permission checks on each resource object |
| Using an ID token to call an API | Wrong intended recipient and token purpose | Client validates the ID token; RS validates the access token |
| Logging tokens, authorization codes, or client secrets | Secrets may leak through logs and monitoring | Mask/redact sensitive values and minimize logging of authentication artifacts |
| Lacking key rotation or revocation procedures | Compromised keys/tokens are hard to contain; verification breaks | Manage key lifecycle, token lifetimes, refresh tokens, and revocation strategies |

In addition, use HTTPS for real endpoints, configure exact redirect URIs, and separate development and production environments. Bearer tokens allow whoever possesses the token to use it within its limits, so token storage and transmission mechanisms are an integral part of secure design.

## 9. Testing According to Each Role's Responsibilities

A minimal integration test suite can follow the flow from Client to RS:

| Test case | Expected outcome | Primary responsibility |
| --- | --- | --- |
| Client sends an unregistered redirect URI | AS rejects the request | AS |
| Client exchanges code with an incorrect `code_verifier` | Token endpoint rejects | AS |
| User does not complete login or denies consent when required | No valid authorization granted to client | Resource Owner / AS |
| API request missing Bearer token | Returns `401` for resources requiring authentication | RS |
| API receives expired token, invalid signature, wrong issuer, or wrong audience | Access denied | RS |
| API receives token with valid audience but missing `booking.read` | Denies reading the Booking API | RS |
| API receives token with `booking.read` but requests another user's booking | Denied by business authorization | RS |
| Client sends an ID token instead of an access token | API does not treat it as valid access | Client / RS |
| Client Credentials calls a user-only endpoint | Denied if missing user identity/permissions per policy | RS |

In Spring Security, controller/service-level tests with mock authentication objects can verify scope rules and business authorization. Real integration tests should add evidence that the AS issues tokens as configured and the RS properly validates signatures, issuer, audience, and validity window.

## 10. Knowledge Self-Check

**Question 1.** A user logs in successfully, yet the Web App cannot read API data because the token lacks a scope. Does the error lie in "authentication" or "authorization"?  
**Hint:** Logging in proves identity; scope is a condition for granting access permissions.

**Question 2.** If a Resource Server verifies JWTs using the AS's public key, why doesn't it need to query the AS on every request?  
**Hint:** Signatures and claims can be verified locally using a trusted public key; immediate revocation policies require appropriate supplementary mechanisms.

**Question 3.** Can a client also act as a Resource Server?  
**Answer:** Yes, if the application both protects its own endpoints and calls another API. Roles are determined per interaction.

**Question 4.** Is having `scope=booking.read` sufficient to access all bookings?  
**Answer:** No. The RS must also enforce object-level, tenant, and business rule permissions.

**Question 5.** In OIDC, which token tells the Client the user authentication result, and which token is used to call APIs?  
**Answer:** The Client validates the ID token to process OIDC login; the Client uses the access token to call the RS.

## 11. System Design Takeaways

- **Resource Owner** is the entity with authority over the resource; typically the user.
- **Client** is the application requesting and using access; it can be a browser, mobile app, BFF, or backend.
- **Authorization Server** manages protocol-level authentication/authorization and issues tokens.
- **Resource Server** protects APIs, validates access tokens, and enforces actual access permissions.
- **OAuth 2.0** defines authorization; **OIDC** adds user authentication for the Client via ID tokens and related rules.
- **A valid access token does not guarantee sufficient permission**; checking audience, scope, and resource-level permissions is an indispensable responsibility of the RS.

Clearly distinguishing these four roles is the foundation for configuring Spring Authorization Server, Spring Security OAuth2 Client, and Resource Server without confusing where tokens are issued with where data is protected.
