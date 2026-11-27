# 2.1. Resource Owner, Client, Authorization Server, and Resource Server

## Lesson Objectives

After this lesson, you will be able to:

- Accurately identify the four core roles of OAuth 2.0 in a system with login and API calls.
- Explain who owns the resource, who requests access, who issues tokens, and who validates tokens before returning data.
- Trace an Authorization Code flow with PKCE from the browser to the Authorization Server and Resource Server.
- Distinguish OAuth 2.0 (delegated authorization) from OpenID Connect (OIDC, the identity and authentication layer).
- Determine whether a Spring Security application acts as an OAuth2 Client, Resource Server, or Authorization Server, even when the same system holds multiple roles.

## 1. The Big Picture: Four Roles as Four Responsibilities

Suppose a school has:

- **Lan** wants to view her course list.
- **Study Portal** is the web application Lan uses, integrated with the school's login.
- **Campus Identity** is the centralized login system that issues tokens.
- **Course API** stores course data and provides endpoints that require access permissions.

In this interaction, Lan is the *Resource Owner*, Study Portal is the *Client*, Campus Identity is the *Authorization Server*, and Course API is the *Resource Server*. These names describe **roles in an OAuth transaction**, not necessarily separate servers or products.

| Role | Question the Role Answers | In the Example | Primary Responsibility |
| --- | --- | --- | --- |
| **Resource Owner** | Who has authority to grant access to the resource? | Lan | Decides or is the authoritative entity for delegated access permissions |
| **Client** | Which application wants to access the resource? | Study Portal | Initiates the authorization request, receives tokens via a valid flow, and uses the access token to call APIs |
| **Authorization Server** | Who authenticates and issues permissions/tokens? | Campus Identity | Authenticates the subject when needed, processes authorization requests, and issues tokens to the client |
| **Resource Server** | Who holds the protected resource? | Course API | Receives the access token, validates its validity and permissions, and decides whether to return data |

Overview diagram:

~~~mermaid
flowchart LR
    RO["Resource Owner<br/>Lan"]
    C["Client<br/>Study Portal"]
    AS["Authorization Server<br/>Campus Identity"]
    RS["Resource Server<br/>Course API"]

    RO -->|"Uses application"| C
    C -->|"Redirects authorization request"| AS
    RO -->|"Authenticates / consents when needed"| AS
    AS -->|"Authorization code, then tokens"| C
    C -->|"Calls API with access token"| RS
    RS -->|"Authorized data"| C
    C -->|"Displays result"| RO
~~~

**Key takeaway:** The Client does not need to know the Resource Owner's password to call an authorized API. The Authorization Server issues proof of authorization in the form of an access token; the Resource Server verifies that proof within the scope of the resources it protects.

## 2. Resource Owner: The Entity with Authority Over the Resource

In the OAuth 2.0 model, the *Resource Owner* is an entity capable of granting access to a protected resource. When this entity is a person, it is commonly referred to as the *end user*.

In the example, Lan's course list is the protected resource. Lan can allow Study Portal to access data in accordance with the school's policy. However, avoid assuming that:

- The Resource Owner is always the person directly clicking the login button. Some systems have delegated or organization-managed authority.
- User consent alone is enough for the client to view any data. The Resource Server still has to enforce business rules, actual permissions, and data boundaries.
- Every OAuth flow involves a human Resource Owner at token issuance time. With the **Client Credentials** flow, the client requests permissions based on its own identity, without representing an interactive user.

**The Resource Owner is distinct from the subject of every token.** In a user-facing flow, the access token typically represents an access context on behalf of a user; in a machine-to-machine flow, there is not necessarily a user. You should inspect the grant type, claims, and Authorization Server policy rather than guessing.

In OIDC, the term **End-User** refers to the human authenticated by the OpenID Provider. In typical login scenarios, Lan is both the End-User in OIDC and the Resource Owner in the OAuth example, but these are two concepts belonging to two different protocol layers.

## 3. Client: The Application Requesting and Using Access

A *Client* is an application making protected resource requests on behalf of the Resource Owner or under its own authority. A Client can be a server-side web application, a single-page application (SPA), a mobile app, a CLI, or a backend service.

### 3.1. What Must a Client Have?

The Authorization Server typically manages a **client registration** with the following properties:

| Property | Meaning |
| --- | --- |
| Client ID | Public identifier of the registered application |
| Client authentication | How the client proves its identity to the Authorization Server, when the client type is capable of doing so |
| Redirect URI | Address that receives the response after the authorization step; must be registered and strictly matched |
| Grant type | Allowed flows, such as Authorization Code or Client Credentials |
| Scope | Set of permissions the client is allowed to request |
| Provider / issuer | The Authorization Server trusted by the client, including its associated endpoints |

**A Client ID is not a password.** For a confidential client, the client secret or another strong authentication method is kept securely on the backend. Never put a client secret into browser-executed JavaScript, public source code, or mobile apps distributed to users.

### 3.2. Confidential Client vs. Public Client

- **Confidential Client** can maintain the confidentiality of its credentials, typically a web backend. It usually performs the authorization code exchange on the server.
- **Public Client** cannot guarantee the confidentiality of a client secret, such as a pure browser-based SPA or a mobile app. These clients must use compatible mechanisms, especially **Authorization Code with PKCE**.

PKCE is also recommended for confidential clients when using Authorization Code. PKCE binds the authorization request to the code exchange using a temporary secret *code verifier* and a *code challenge* derived from it.

**The browser and the Client are not always the same thing.** When Study Portal is a server-side application, the browser redirects through the Authorization Server, but the Study Portal backend component is the registered OAuth2 Client that holds the tokens. If an SPA executes the protocol directly, the SPA itself is the public client. This distinction determines where tokens are stored and how they are protected.

### 3.3. A Client Does Not Grant Permissions to Itself

The Client only **requests** the scopes it needs, such as `courses.read`. The Authorization Server decides which scopes are actually granted. The Resource Server is the component that performs the final check for a specific API. A client declaring a scope or rendering a "View Courses" button does not create access rights.

## 4. Authorization Server: Authenticating, Processing Authorization, and Issuing Tokens

The *Authorization Server* is the system that issues tokens after processing an authorization request according to policy. For user-facing flows, it typically authenticates the user and may request *consent*. For service-to-service flows, it can authenticate the client without showing a login screen.

Common responsibilities:

1. Managing registered clients, redirect URIs, allowed grant types, and scopes.
2. Receiving requests at the **authorization endpoint**, handling user authentication, consent, and policies.
3. Issuing the **authorization code** in the Authorization Code flow.
4. At the **token endpoint**, validating the code, PKCE, and client authentication when applicable, then issuing tokens.
5. Publishing metadata, public keys (JWKS), or an introspection endpoint so other components can validate tokens according to the configured model.
6. Managing token lifecycle, expiration, revocation, and refresh tokens according to policy.

The Authorization Server **is not by default the store of business data**. Campus Identity may issue an access token for `courses.read`, while Course API is what actually stores and returns the course list.

One Authorization Server can issue tokens for multiple Resource Servers. Issuing a token does not mean a token is valid for every API; a token may be constrained by **audience**, scope, and other conditions.

### The Authorization Endpoint and Token Endpoint Have Different Roles

- **Authorization endpoint:** typically accessed through the browser (front channel), receives the authorization request, and returns a redirect result. In the Authorization Code flow, the successful result is an *authorization code*.
- **Token endpoint:** the client exchanges the code over a direct connection with the Authorization Server (back channel) to obtain tokens. Tokens do not need to pass through redirect URLs in the user's browser.

An authorization code is short-lived, single-use, and bound to the client/redirect URI per server rules. It is **not** an access token and must not be sent directly to call Course API.

## 5. Resource Server: Protecting APIs and Enforcing Access Control

The *Resource Server* is the system that hosts or provides protected resources. Course API may receive a request such as:

~~~http
GET /api/me/courses HTTP/1.1
Host: courses.example.org
Authorization: Bearer <access-token>
~~~

The Resource Server must perform both **token validation** and **authorization checks**:

- Is the token well-formed and from a trusted issuer?
- For a JWT, are the signature and timestamps such as `exp` and `nbf` valid? For an opaque token, is introspection from the Authorization Server required?
- Was the token issued **for this API** (appropriate audience / resource) and does it contain the required scopes?
- Is the principal allowed to view the exact requested resource, such as only their own courses?
- Are there additional restrictions by tenant, organization, account status, or business rules?

The final steps cannot be replaced by merely checking "does the JWT have a valid signature?". A valid access token with scope `courses.read` does not necessarily allow reading someone else's courses.

**A Resource Server must not accept an ID token as an access token.** An ID token is meant for the OIDC Client to verify login information; it is not an authorization credential for calling Course API.

HTTP responses typically mean:

- **401 Unauthorized:** missing or invalid authentication credentials; the Resource Server may return a Bearer challenge.
- **403 Forbidden:** an authentication context is present, but required permissions are missing, such as lacking the appropriate scope.

The exact details of 401/403 depend on configuration and error nature, but this is a useful distinction when reading logs and troubleshooting.

## 6. Tracing an Authorization Code + PKCE Transaction

Below is a typical flow when Lan logs into Study Portal and views her courses. Because the module includes OIDC, the example requests both the `openid` scope for login and `courses.read` for calling the API.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Lan (Resource Owner)
    participant B as Browser
    participant C as Study Portal (Client)
    participant AS as Campus Identity (Authorization Server / OP)
    participant RS as Course API (Resource Server)

    U->>B: Opens courses page
    B->>C: GET /my-courses
    C-->>B: Redirect to authorization endpoint
    B->>AS: client_id, redirect_uri, scope, state, code_challenge, nonce
    AS->>U: Login, consent if needed
    U-->>AS: Completes authentication/authorization step
    AS-->>B: Redirect back to Client with code and state
    B->>C: GET /login/oauth2/code/campus?code=...&state=...
    C->>C: Validates state
    C->>AS: Exchanges code + code_verifier (and client authentication if needed)
    AS-->>C: access_token, id_token, possibly refresh_token
    C->>C: Validates ID token; establishes login session
    C->>RS: GET /api/me/courses + Bearer access_token
    RS->>RS: Validates token + checks resource permissions
    RS-->>C: Authorized course list
    C-->>B: Data page
~~~

Steps to understand clearly:

1. **The Client initiates the authorization request.** It sends `response_type=code`, `client_id`, `redirect_uri`, scope, and protection values such as `state` and PKCE `code_challenge`. An OIDC Client may also send `nonce` to bind the ID token to the request.
2. **The Resource Owner interacts with the Authorization Server.** Lan enters her credentials into the trusted interface of Campus Identity. If policy requires it, Lan reviews and approves the shared scope.
3. **The Authorization Server returns the code via redirect.** The browser returns to the registered redirect URI. The Client checks `state` to correlate the callback with the initiated transaction.
4. **The Client exchanges the code for tokens.** The request to the token endpoint includes `code_verifier`; a confidential client also authenticates itself as configured. The Authorization Server verifies these constraints and issues tokens.
5. **The Client handles OIDC login.** If `openid` is present, the client validates the ID token according to OIDC rules—including signature, issuer, audience, expiration, and nonce when used—then establishes the application's login session.
6. **The Client calls the Resource Server.** It passes the access token in the Bearer Authorization header. The API validates the token and actual permissions before returning data.
7. **Subsequent lifecycle.** When an access token expires, a new authorization or a refresh token may be used if the client was issued one and policy allows it. Logging out of the Portal does not automatically guarantee that all issued access tokens are immediately revoked.

Example authorization request parameters (illustrative values; must be URL-encoded when building a real URL):

~~~text
GET https://login.example.org/oauth2/authorize
  ?response_type=code
  &client_id=study-portal
  &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcampus
  &scope=openid%20profile%20courses.read
  &state=<random-state>
  &code_challenge=<S256-derived-challenge>
  &code_challenge_method=S256
  &nonce=<random-nonce>
~~~

`state`, `nonce`, and `code_verifier` must be freshly generated, sufficiently random, and properly managed per transaction. Do not copy illustrative strings into fixed values.

### Channels and Trust Boundaries

- **Front channel:** the browser passes through the authorization endpoint and redirect URI. Because URLs can leak via browser history or logs, the Authorization Code flow only passes a temporary code through this channel.
- **Back channel:** the client backend exchanges the code with the token endpoint and calls the Resource Server over HTTPS; this is where access tokens must be protected.
- **Trust boundary:** the Client trusts the configured Authorization Server; the Resource Server only trusts tokens issued, signed, or introspected by an accepted source for the corresponding resource.
- **Decision points:** the Authorization Server decides whether to grant authorization/tokens; the Resource Server decides whether to allow access to the endpoint and data objects.

## 7. Access Token, ID Token, Refresh Token, and Scope

The four roles are easy to confuse if all tokens are lumped into a single type.

| Concept | Who Receives / Uses It? | Purpose | Sent to Course API? |
| --- | --- | --- | --- |
| **Authorization code** | Client receives via redirect and sends to token endpoint | One-time exchange for tokens | No |
| **Access token** | Client holds and sends to Resource Server | Proves granted access permissions for an API | **Yes** |
| **ID token** (OIDC) | OIDC Client / Relying Party | Contains information about the authentication event and End-User identity | **No** |
| **Refresh token** | Client sends to token endpoint when eligible | Requests a new access token according to policy | No |

An access token can be a **JWT** (the API verifies the signature and claims) or an **opaque token** (the API typically queries an introspection endpoint). There is no OAuth 2.0 rule requiring every access token to be a JWT.

**Scope** describes the permission boundary the client requests and is granted, such as `courses.read`. It differs from:

- **Role:** the user's business role in the application, such as `TEACHER` or `STUDENT`.
- **Audience (`aud`):** the system or target recipient the token is issued for.
- **Subject (`sub`):** identifier of the subject within the token context; must be interpreted according to token type and issuer.
- **Consent:** the step expressing the user's approval when applicable; it does not replace scope checks or API policies.

For example, a token with `courses.read` whose audience is meant for a different API must be rejected by Course API. Even when the audience and scope match, the question "Is Lan allowed to read course 123?" still requires checking business data.

## 8. How OIDC Extends the OAuth Model

**OAuth 2.0** solves the problem of authorizing applications to access resources. **OpenID Connect (OIDC)** is a protocol layer built on top of OAuth 2.0 that adds standardized user authentication and identity information for the client.

The same Campus Identity system can play both roles simultaneously:

- **Authorization Server (OAuth 2.0):** processes authorization requests and issues access tokens.
- **OpenID Provider, abbreviated OP (OIDC):** authenticates the End-User and issues ID tokens containing OIDC-standard claims.

Similarly, Study Portal is an **OAuth2 Client** when calling Course API, and a **Relying Party (RP)** when using the ID token to know who logged in.

| Problem to Solve | Appropriate Mechanism | Receiving Component |
| --- | --- | --- |
| "Which APIs is the application allowed to call?" | OAuth 2.0 + access token / scope / audience | Resource Server |
| "Who just logged in?" | OIDC + validated ID token | Relying Party (Client) |
| "Retrieve profile information consented for sharing?" | OIDC UserInfo endpoint or claims issued per OP rules | OIDC Client |
| "Is this user allowed to edit course 123?" | Business authorization rules, possibly combined with token claims | Course API |

Requesting the `openid` scope signals that the client is performing OIDC. Scopes like `profile` and `email` can request additional information subject to policy; they do not automatically guarantee every claim appears in the ID token. A stable `sub` value within the scope of an issuer/subject type is more suitable as an identity key than an email address, since emails can change or remain unverified.

**Do not equate "logged in via OIDC" with "allowed to access every API."** An application may authenticate Lan successfully yet still lack an access token permitted to call Course API.

## 9. Mapping to Spring Security

Spring Security provides different mechanisms depending on the role **the current Spring application** plays. Two applications both using Spring do not necessarily share the same configuration.

| Responsibility of the Spring Application | Typical Capability / Configuration | What Role Does It Play? |
| --- | --- | --- |
| Let users log in with an OpenID Provider | `oauth2Login()`, `ClientRegistration` | OIDC Client / Relying Party |
| Call external APIs with an access token | `oauth2Client()`, `OAuth2AuthorizedClient` | OAuth2 Client |
| Accept Bearer tokens on its own APIs | `oauth2ResourceServer().jwt()` or opaque token | Resource Server |
| Provide authorization/token endpoints itself | A dedicated Authorization Server implementation, e.g., Spring Authorization Server | Authorization Server |

Note: adding `oauth2Login()` configuration **does not turn Study Portal into an Authorization Server**. It only enables the Portal to log users in via an external identity provider. Likewise, `oauth2ResourceServer()` only protects API endpoints accepting tokens; it does not issue tokens itself.

### 9.1. Study Portal: Configuring an OIDC Client

An illustrative example for a Spring Boot application using Spring Security and an OIDC Provider publishing issuer metadata:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          campus:
            provider: campus
            client-id: ${CAMPUS_CLIENT_ID}
            client-secret: ${CAMPUS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - courses.read
        provider:
          campus:
            issuer-uri: https://login.example.org
~~~

The example above assumes a **confidential client** using a client secret. In a real environment, `CAMPUS_CLIENT_ID` and `CAMPUS_CLIENT_SECRET` are provided through secret configuration; the issuer and scopes must match the provider being integrated. The name `campus` is Spring's local `registrationId`.

Spring Security uses OIDC discovery from `issuer-uri` to look up the appropriate endpoints and validation keys when supported by the provider. The redirect URI must be registered identically at the Authorization Server. Spring's default template generates a callback such as:

~~~text
https://portal.example.org/login/oauth2/code/campus
~~~

Web page protection configuration:

~~~java
@Configuration
class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The snippet only shows the relevant parts; real source code requires the appropriate Spring Security imports and dependencies. When accessing a page requiring authentication, Spring triggers the login flow via the configured provider. Login can also be initiated proactively at:

~~~text
/oauth2/authorization/campus
~~~

After a successful OIDC login, a controller can access the identity authenticated by Spring:

~~~java
@GetMapping("/whoami")
Map<String, String> whoami(@AuthenticationPrincipal OidcUser user) {
    return Map.of(
        "subject", user.getSubject(),
        "issuer", user.getIssuer().toString()
    );
}
~~~

Here `OidcUser` represents user information from the OIDC process. It is **not** an access token to send to Course API.

### 9.2. Study Portal: Using the Access Token to Call the Resource Server

Spring stores token information associated with a client registration and an authorized context inside `OAuth2AuthorizedClient`. For example, a controller can retrieve that object:

~~~java
@GetMapping("/my-token-metadata")
Map<String, String> tokenMetadata(
        @RegisteredOAuth2AuthorizedClient("campus")
        OAuth2AuthorizedClient authorizedClient) {

    return Map.of(
        "registrationId", authorizedClient.getClientRegistration().getRegistrationId(),
        "expiresAt", authorizedClient.getAccessToken().getExpiresAt().toString()
    );
}
~~~

This is only an example for inspecting metadata; **never return the access token value in a response for debugging**. When implementing actual calls, the Client reads `authorizedClient.getAccessToken().getTokenValue()` and attaches it to the `Authorization: Bearer ...` header of an HTTPS request to Course API, or uses Spring Security's OAuth2-integrated HTTP client. Ensure that the mechanism for obtaining a new token upon expiration is compatible with the client type, authorized-client storage, and grant type.

### 9.3. Course API: Configuring a Resource Server

In a standalone Spring Boot application acting as a Resource Server, configuration for a **JWT access token** might start like this:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org
~~~

And endpoint access rules:

~~~java
@Configuration
class CourseApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/courses/**")
                .hasAuthority("SCOPE_courses.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

With JWT, Spring Security can verify the signature via the issuer's trusted keys, check supported token conditions, and convert scopes into `SCOPE_...` authorities by default. To protect the API properly, **you must configure expected audience validation** if that is a system constraint; do not assume validating `issuer-uri` is sufficient in every case. The API must also enforce per-object data permissions, such as which user a course belongs to.

The Java snippet above is an illustrative skeleton; a pure Bearer-token API system may additionally configure stateless sessions, credential-appropriate CSRF handling, and error policies. If the provider issues opaque access tokens instead of JWTs, the Resource Server must use an appropriate introspection mechanism and cannot default to parsing tokens as JWTs.

### 9.4. One Application Can Hold Multiple Roles

Roles are bound to **behavior at each communication boundary**:

- Portal receives an ID token to log the user in: OIDC Client / RP.
- Portal holds an access token to call Course API: OAuth2 Client.
- Course API validates an incoming Bearer token: Resource Server.
- If Course API calls another API using its own token or a delegated token, Course API is also an OAuth2 Client in that call.
- Campus Identity issues tokens: Authorization Server and possibly OpenID Provider.

Inbound/outbound token processing paths and session authentication models must be separated when a single Spring application both logs users in and accepts Bearer tokens. Merging everything into one `SecurityFilterChain` without distinguishing endpoints can cause API requests to redirect to a login screen or apply incorrect policies.

## 10. Scenarios to Identify Roles Correctly

### Scenario A — Logging in via Google or an Enterprise IdP

A user opens a Spring application, is redirected to the IdP to log in, and returns to the application. The IdP acts as the Authorization Server/OpenID Provider; the Spring application is the OAuth2/OIDC Client. If the application has no APIs protected by Bearer tokens, it **does not necessarily** act as a Resource Server.

### Scenario B — Backend Verifying the Caller's JWT

A mobile app calls `GET /api/orders` with an access token; the Spring backend validates the JWT and returns data. The backend is the Resource Server; the mobile app is the Client. The server that issued the JWT is the Authorization Server. The backend does not become an Authorization Server merely because it verifies JWT signatures.

### Scenario C — One Service Calling Another via Client Credentials

Billing Service requests an access token of its own and then calls Inventory API. Billing Service is the Client; Identity Service is the Authorization Server; Inventory API is the Resource Server. This flow has no user directly performing login or consent; avoid mislabeling a service account as a human Resource Owner.

### Scenario D — Frontend, Backend for Frontend (BFF), and API

The browser communicates with the BFF via cookie sessions; the BFF acts as a confidential OAuth2 Client, holds tokens server-side, and calls the Resource Server. The browser is the user agent in the login flow. This distinction matters when choosing where to store tokens and how to prevent CSRF.

## 11. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "An OAuth 2.0 token proves who is logged in." | An access token primarily serves API authorization; an OIDC ID token serves identity authentication for the Relying Party. |
| "Having a scope in the client request means permission is granted." | The scope in the request is only a proposal; the actually granted and enforced permissions may be narrower. |
| "The Resource Server is where access tokens are issued." | The Authorization Server issues tokens; the Resource Server validates and consumes tokens to protect resources. |
| "Every access token is a JWT." | OAuth allows other token formats, including opaque tokens. |
| "The ID token has user info, so it can be used to call APIs." | APIs must receive an access token intended for the API; an ID token has a different audience and purpose. |
| "The backend holds a JWT, so it is the OAuth2 Client." | Merely receiving/validating a token on an incoming request is Resource Server behavior; using a token to call an API is Client behavior. |
| "If a user is granted `courses.read`, they can read any course." | The API must still check permissions at the record, organization, and business-policy levels. |
| "Spring Security `oauth2Login` implements an Identity Provider itself." | `oauth2Login` integrates the application with an external provider; a separate Authorization Server is needed to issue tokens. |
| "Getting a code on the callback means login is complete." | The Client must validate `state` and exchange a valid code; with OIDC, it must validate the ID token before trusting the identity. |

## 12. Security Principles by Role

**Resource Owner / End-User**

- Only log in on a trusted Authorization Server/OP page.
- Read the requested permissions when consent is shown and understand what data the client will use.

**Client**

- Prefer Authorization Code + PKCE for user-facing flows; avoid Implicit flow and Resource Owner Password Credentials in new designs.
- Validate `state`, use exact registered redirect URIs, protect `nonce` when used, and validate ID tokens according to OIDC.
- Protect client secrets, access tokens, and refresh tokens appropriately for the client type; never put tokens in URLs or logs; use HTTPS.
- Request minimal scopes, retain tokens only as long as needed, and support token expiration/revocation strategies.

**Authorization Server / OP**

- Authenticate clients properly, validate redirect URIs, and enforce PKCE constraints.
- Issue tokens only according to permitted grant types, scopes, and policies; set appropriate token lifetimes.
- Publish accurate issuer/keys and metadata, and operate key rotation and token revocation according to system needs.

**Resource Server**

- Only accept access tokens from a trusted issuer, intended for the API, and still valid.
- Verify JWT signatures or properly use introspection for opaque tokens.
- Enforce scope/authority checks alongside resource, tenant, and business authorization.
- Never accept an ID token in place of an access token; avoid leaking token contents or sensitive data in error responses.

## 13. Self-Check Questions

**Question 1.** A user logs in successfully via OIDC, but Course API returns HTTP 403. Which role needs to check API access permissions?

> The Resource Server (Course API) checks scopes and access policies; the Client also needs to verify that it requested/received the right permissions. Successful login alone is not enough to guarantee API access.

**Question 2.** A Spring service only configures `oauth2ResourceServer().jwt()`. Does that service issue access tokens for other applications?

> No. It is receiving and validating access tokens as a Resource Server; issuing tokens belongs to the Authorization Server.

**Question 3.** In the Authorization Code flow, why does the callback deliver a code to the client instead of an access token?

> The client can exchange the code at the token endpoint over a direct channel, using PKCE and client authentication when needed. This reduces the risk of exposing access tokens in the browser or redirect URLs.

**Question 4.** Study Portal receives an ID token with `sub=lan123`. Can it send that ID token in the Bearer header to call Course API?

> No. An ID token is for the OIDC Client to verify login. The API requires a valid access token with the appropriate audience/scope and permissions.

**Question 5.** In a system using Client Credentials, which roles remain clearly present and which role does not have an interactive user?

> Client, Authorization Server, and Resource Server remain clearly present. The flow does not require a human Resource Owner interactively approving the request at token issuance time.

---

## Remember

Read every OAuth 2.0 diagram through four questions: **Who has authority over the resource?** (Resource Owner), **which application requests access?** (Client), **who issues the token?** (Authorization Server), and **who validates the token before granting data access?** (Resource Server). When OIDC is added, the client can also verify user identity based on the OpenID Provider's **ID token**. In Spring Security, `oauth2Login`, `oauth2Client`, and `oauth2ResourceServer` correspond to different responsibilities of those roles.
