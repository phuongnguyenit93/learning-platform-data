# Distinguishing OAuth2 Client, Resource Server, and Authorization Server

> **Topic:** Spring Security – reactive  
> **Knowledge Group:** OAuth2/OIDC Login  
> **Focus:** Properly identify **OAuth2 Client**, **OAuth2 Resource Server**, and **OAuth2 Authorization Server** in a WebFlux system; distinguish OIDC login from Bearer access token authentication, understand the endpoints and Spring Security configuration, and know how to test each role without mixing security responsibilities.

## 1. One System, Three Completely Different Roles

In OAuth 2.0, the word “OAuth” does not by itself refer to a login product. It describes how a **client** requests access to a **resource server** coordinated by an **authorization server**. If user identity verification is needed to establish a login session, **OpenID Connect (OIDC)** adds an identity layer on top of OAuth2. An application may perform one role, multiple roles, or simply interact with systems performing those roles.

Consider an e-commerce website example:

- **Website/BFF at `https://shop.example.test`**: users visit and click “Sign in”; this application is the **OAuth2 Client**. After OIDC login, the website manages its own session and can use an access token to call APIs.
- **Orders API at `https://orders.example.test`**: receives `Authorization: Bearer ...` and validates tokens/permissions before returning orders; this is the **Resource Server**.
- **Identity system at `https://id.example.test`**: authenticates users, displays consent when needed, issues authorization codes, access tokens, ID tokens, and publishes metadata/JWKS; this is the **Authorization Server**, and also acts as the **OpenID Provider** if it implements OIDC.

```text
                           +------------------------+
                           | Browser / End User     |
                           +-----------+------------+
                                       |
                              open website / login
                                       |
                                       v
                       +---------------+----------------+
                       | OAuth2 Client (WebFlux/BFF)     |
                       | shop.example.test               |
                       | oauth2Login / oauth2Client      |
                       +-------+------------------+------+
                               |                  |
              redirect (authorization code)       | API call:
                               |                  | Authorization: Bearer ACCESS_TOKEN
                               v                  v
                    +----------+--------+    +----+--------------------+
                    | Authorization      |    | Resource Server        |
                    | Server / OIDC OP   |    | orders.example.test    |
                    | id.example.test    |    | oauth2ResourceServer   |
                    | /authorize,/token  |    | JWT/opaque validation  |
                    +----------+--------+    +----+--------------------+
                               |                  |
                               +-- issuer/JWKS -->+
                               (metadata, key validation;
                                opaque token may use introspection)
```

Do not assume the three roles are necessarily **three processes or three physical machines**: they are **protocol roles**. A BFF can be a Client of API A while being a Resource Server for API B; an API can also use client credentials to call another API. However, each request must know its **corresponding role and token type** to avoid misconfiguration.

### Learning Outcomes

After this lesson you will be able to:

1. Identify each role and label it accurately in a system diagram.
2. Describe the Authorization Code + PKCE flow, token requests, API calls, token refresh, and browser sessions.
3. Distinguish access tokens, ID tokens, refresh tokens, authorization codes, and session cookies.
4. Know when to use `.oauth2Login()`, `.oauth2Client()`, `.oauth2ResourceServer().jwt()`, or opaque tokens.
5. Understand why WebFlux reactive client/resource server and Spring Authorization Server are configurations on **different stacks/capabilities**.
6. Write Spring Boot Java 17+ examples for a **WebFlux client** and a **resource server API**, with tests for present/missing tokens, matching/mismatching scopes, and login redirects.
7. Recognize common security mistakes: using an ID token to call APIs, omitting audience checks, confusing scopes with roles, trusting a JWT just because it decodes, and embedding client secrets in SPAs.

## 2. Quick Comparison Table: Who Does What?

| Criterion | OAuth2 Client | Resource Server | Authorization Server |
| --- | --- | --- | --- |
| Purpose | **Requests and uses** access permissions | **Protects** resources/APIs | **Issues and manages** access permissions/tokens |
| Example | WebFlux website, BFF, backend calling APIs | Orders/reports REST API | IdP/Authorization Service |
| Incoming request | Browser login/callback or business request | HTTP Bearer token calling an API | Authorization request, token request, introspection |
| Token handled | Receives/stores access/refresh/ID tokens (per flow) | Validates **access tokens** | Issues access/refresh tokens; OIDC includes ID tokens |
| Spring dependency | `spring-boot-starter-oauth2-client` | `spring-boot-starter-oauth2-resource-server` | Spring Authorization Server or external IdP |
| WebFlux DSL | `oauth2Login`, `oauth2Client` | `oauth2ResourceServer` | **Not** simply enabling a similar WebFlux DSL |
| Authentication handling | Redirects user to IdP, code/token exchange; or client credentials | Reads bearer, verifies JWT or introspects opaque token | Authenticates clients, users/consent, and issuance policy |
| Checks | `state`, PKCE, OIDC nonce/ID token, issuer/provider | `iss`, `exp`, signature, audience, scope, tenant | Client registration, redirect URIs, grant policy, signing keys, token TTL |
| Common errors | `invalid_client`, `invalid_grant`, callback mismatch | HTTP 401 invalid token, 403 insufficient scope | `invalid_client`, `invalid_scope`, `unauthorized_client` |

**Crucially:** `oauth2Login` **does not create an Authorization Server**. It configures an **OAuth2 Client** to receive login callbacks. Likewise, `oauth2ResourceServer().jwt()` **does not mean the application issues JWTs**; it primarily enables the API to **verify JWTs**.

## 3. Four Entities in the RFC: Don't Forget the Resource Owner

OAuth 2.0 defines four classic roles:

1. **Resource Owner:** the owner/grantor of access permissions, typically the end user.
2. **Client:** the software seeking to access resources on behalf of the resource owner or on its own behalf.
3. **Authorization Server:** the system that grants authorization, authenticates, and issues tokens.
4. **Resource Server:** the system holding resources and validating access tokens.

Resource Owner **is not synonymous with** Authorization Server: the user owns the data; the Authorization Server handles login/consent/token issuance. When `client_credentials` is used for machine-to-machine communication, no user participates per request; the client represents itself.

### 3.1. “Spring Boot Application” Does Not Define the Role

Repo names, ports, domains, or the use of WebFlux do not determine whether an app is a Client, Resource Server, or Authorization Server. Ask:

- Does this app **redirect to /authorize and exchange codes**? → OAuth2 Client side.
- Does this app **receive Bearer tokens and validate them to return JSON**? → Resource Server side.
- Does this app **operate /authorize, /token, metadata/JWKS, and manage clients/consent**? → Authorization Server side.
- Does the app both accept inbound Bearer tokens and obtain tokens for outbound calls? → Both **Resource Server + Client**, and security paths and token audiences should be clearly separated.

One server can play multiple roles, but policies and endpoint sets must have clear boundaries. Do not assume a Bearer token calling an API proves the user completed OIDC login at a separate BFF app.

## 4. How Do OAuth2 and OpenID Connect Differ?

**OAuth2 is primarily about resource access delegation (authorization)**: a client obtains an access token to call a resource server. OAuth2 **does not standardize a complete mechanism for proving an end-user logged in** to an application.

**OpenID Connect 1.0** is an identity layer on top of OAuth2, adding the **ID token**, authentication requests, provider metadata, nonce, userinfo, and rules for verifying end-user identity. With OIDC, a client can use a **properly verified ID token** to identify the user and establish a website login session.

| Question | OAuth2 | OIDC |
| --- | --- | --- |
| Primary concern | Which resources can the client access? | Who just logged in, and under which issuer? |
| Typical tokens | Access token, optional refresh token per grant | Access token **and ID token**, optional refresh token |
| Scopes | `orders.read`, `profile.read`… | Includes `openid`, often with `profile`, `email` |
| Recipient | Resource Server receives access token | OIDC Client verifies ID token |
| Outcome | API access authorization | User authentication result for the client |

Some social-login providers support OAuth2 profile retrieval without full OIDC support; Spring Security can perform OAuth2 Login based on the corresponding user info. However, **never invent your own login protocol by reading an access token as if it were an ID token**.

### 4.1. Never Use an ID Token to Call APIs

- **Authorization code:** short-lived, typically single-use code delivered to the client callback and exchanged for tokens. It **is not** an access token.
- **Access token:** proof granted to a client to access a resource server; must match the API's audience/scope/rules.
- **ID token:** a token **intended for the OIDC Client**, containing identity claims about end-user authentication; `aud` is typically `client_id`. **Never** treat an ID token as an access token for API authorization.
- **Refresh token:** credential for the client to request a new access token; do not send it in an API's `Authorization: Bearer` header.
- **Session cookie:** used by the browser to maintain a session at the website/BFF; not an OAuth2 access token issued for a resource server (even though some architectures forward session-backed requests downstream).

```text
Authorization code  -> sent to OAuth2 Client callback
ID token            -> OIDC Client verifies user identity
Access token        -> Resource Server verifies and accepts when valid
Refresh token       -> OAuth2 Client stores securely, uses at Token Endpoint
Session cookie      -> Browser <-> website/BFF (application manages its own session)
```

A JWT with three dot-separated segments **does not by itself tell you whether it is an ID token or an access token**. You must rely on intended use, issuer, audience, and claims/protocol. An access token can also be an **opaque string**, not necessarily a JWT.

## 5. Authorization Code + PKCE Flow: Who Receives Which Request?

This is the standard flow for users logging in via OIDC in a browser. The steps below are illustrated for a WebFlux OAuth2 Client:

```text
Browser                    OAuth2 Client             Authorization Server        Resource API
   |                            |                             |                        |
   | GET /private               |                             |                        |
   |--------------------------->|                             |                        |
   |                            | 302 to /authorize           |                        |
   |<---------------------------|                             |                        |
   | GET /authorize?client_id=&response_type=code             |                        |
   |--------------------------------------------------------->|                        |
   |                            |                             | login/consent          |
   |                            |                             | issue short-lived code |
   | 302 redirect_uri?code=...&state=...                       |                        |
   |<---------------------------------------------------------|                        |
   | GET /login/oauth2/code/demo?code=...&state=...            |                        |
   |--------------------------->|                             |                        |
   |                            | POST /token + code, verifier |                        |
   |                            |---------------------------->|                        |
   |                            | access_token (+ id_token)    |                        |
   |                            |<----------------------------|                        |
   |                            | validate token/claims       |                        |
   | session cookie / redirect  |                             |                        |
   |<---------------------------|                             |                        |
   | GET /orders                |                             |                        |
   |--------------------------->|                             |                        |
   |                            | GET /api/orders              |                        |
   |                            | Authorization: Bearer ACCESS_TOKEN                      |
   |                            |------------------------------------------------------->|
   |                            |                                  validate token        |
   |                            | 200 order JSON                                       |
   |                            |<-------------------------------------------------------|
   | 200 HTML/JSON              |                             |                        |
   |<---------------------------|                             |                        |
```

This is a conceptual diagram. Token exchange steps, `state`, PKCE, nonce, OIDC validation, authorized client persistence, and session creation may vary by framework/IdP, but **fundamental responsibilities do not change**.

### 5.1. Authorization Request Is the Client's Request to the AS

The client sends the browser to the AS's Authorization Endpoint with common parameters:

```http
GET /oauth2/authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fshop.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile%20orders.read&state=RANDOM_STATE&code_challenge=HASHED_VERIFIER&code_challenge_method=S256 HTTP/1.1
Host: id.example.test
```

This is an **illustrative request**, not a reusable token/callback URL; real `state` and code verifier/challenge values must be sufficiently random, generated, and verified by the security library.

- `client_id` identifies the client registration at the Authorization Server.
- `redirect_uri` must match the registration policy; the AS must not redirect the code to an attacker's URI.
- `scope` describes the permissions requested by the client; `openid` activates OIDC.
- `state` binds the callback to the pending authorization request, defending against CSRF/callback injection.
- `code_challenge`/`code_challenge_method=S256` relate to PKCE, making a stolen code hard to exchange for tokens without knowing `code_verifier`.
- `nonce` is used in OIDC to bind the ID token to the authentication request where applicable.

### 5.2. Callback Goes to the Client, Not to the API

The AS typically redirects the browser back to:

```text
https://shop.example.test/login/oauth2/code/demo?code=...&state=...
```

This is the **Client's callback**, not a Resource Server endpoint. Spring Security WebFlux `oauth2Login` handles callbacks by default at `/login/oauth2/code/{registrationId}`. The client must match `state`, use the authorization code once, exchange it for tokens at the Token Endpoint, process the OIDC ID token, and complete authentication. Never write a controller to “just Base64-decode the code” — an authorization code is an opaque credential that must be exchanged with the AS.

### 5.3. Token Endpoint Is an AS Endpoint

The client calls:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=...&redirect_uri=...&code_verifier=...
```

This is a simplified sample; confidential clients also include **client authentication** per the registered method (e.g., Basic, private-key JWT, mTLS), with actual fields handled by Spring Security/provider. The token response is usually JSON containing `access_token`, `token_type`, `expires_in`, and potentially `refresh_token` and `id_token` for OIDC. Never log this raw payload.

### 5.4. Resource Server Does Not Participate in Login Redirects

After obtaining an access token, the Client calls the API:

```http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer ACCESS_TOKEN
```

A Resource Server normally **does not redirect browsers to a login page** on a Bearer API; when a token is missing or invalid, it returns **401** with an appropriate `WWW-Authenticate: Bearer` header. When the token is valid but lacks the required scope, it returns **403** (optionally with `insufficient_scope` details per RFC/policy). An OAuth2 Resource Server **protects resources**; it does not “perform login” merely because a request has an Authorization header.

## 6. OAuth2 Client: Not Just a Sign-In Button

Spring Security reactive OAuth2 Client covers two use cases:

1. **Login via OAuth2/OIDC**: `ServerHttpSecurity.oauth2Login(...)`, redirecting to the AS, callback handling, OIDC authentication, and establishing a web session.
2. **Obtaining and using access tokens to call APIs**: `ServerHttpSecurity.oauth2Client(...)`, `ReactiveOAuth2AuthorizedClientManager`, `OAuth2AuthorizedClient`, and `WebClient`.

**OAuth2 Client does not equal OAuth2 Login.** A background service using `client_credentials` to call APIs is an OAuth2 Client with **no logged-in user**. A website can combine both when it both logs users in and calls APIs on their behalf.

### 6.1. Key Components in WebFlux

| Component | Role |
| --- | --- |
| `ClientRegistration` | Client registration metadata: client ID, secret/method, redirect URI, scopes, provider endpoints |
| `ReactiveClientRegistrationRepository` | Store of `ClientRegistration` instances, usually auto-created by Boot from `application.yml` |
| `OAuth2AuthorizedClient` | Association between a client registration, a principal, and issued tokens |
| `ServerOAuth2AuthorizedClientRepository` | Saves/reads authorized clients in the context of a web request |
| `ReactiveOAuth2AuthorizedClientManager` | Manages authorizing, re-authorizing, and refreshing per provider/grant |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Attaches an authorized client's Bearer token to outbound `WebClient` requests |
| `oauth2Login` | Handles browser login redirects/callbacks |
| `oauth2Client` | Supports client authorization/token management without automatically creating login UX |

The following two calls are **not equivalent**:

```java
// OAuth2/OIDC browser login:
http.oauth2Login(Customizer.withDefaults());

// Supports OAuth2 Client fetching/sending tokens to downstream APIs:
http.oauth2Client(Customizer.withDefaults());
```

These are DSL snippets inside a `ServerHttpSecurity` configuration method, not standalone Java files. When you want both login and downstream API calls, you can enable **both** and configure an authorized `WebClient`.

### 6.2. Attaching Tokens Properly with WebClient

WebFlux bean example:

```java
@Bean
WebClient downstreamClient(
        ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {
    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager);
    return WebClient.builder().filter(oauth2).build();
}
```

Import classes from `org.springframework.security.oauth2.client`, `org.springframework.security.oauth2.client.web.reactive.function.client`, and `org.springframework.web.reactive.function.client`. On an outbound request, explicitly choose the appropriate `clientRegistrationId` or authorized client, for example:

```java
// Snippet inside a service with downstreamClient injected.
return downstreamClient.get()
    .uri("https://orders.example.test/api/orders")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("demo"))
    .retrieve()
    .bodyToMono(String.class);
```

**Warning:** `clientRegistrationId("demo")` only selects the registration; an actual token must be successfully issued according to the authorization grant and appropriate principal. With `authorization_code`, the flow may require a logged-in/authorized user; with `client_credentials`, the token represents the client itself rather than a user. Never use `setDefaultOAuth2AuthorizedClient(true)` indiscriminately across all HTTP calls because it can inadvertently send access tokens to untrusted endpoints.

### 6.3. How Does Client Credentials Differ from Authorization Code?

| Attribute | Authorization Code (+ PKCE) | Client Credentials |
| --- | --- | --- |
| User login/consent in flow? | Usually yes | No |
| Access token represents | Client permissions granted per user and policy | Permissions of the client/service itself |
| Primary requests | Browser redirect, callback, token exchange | Backend calls token endpoint directly |
| Best suited for | Websites/BFFs, browser-based login/OIDC | Machine-to-machine, service jobs |
| OIDC ID token? | Possible when scope includes `openid` | Normally no end-user ID token |
| Secret/public client | Depends on client type and registration; PKCE is important | Confidential client auth must be kept secret |

**Never** place a client secret in JavaScript/browser SPA source code: public clients cannot keep secrets the way a backend can. For SPAs, authorization code + PKCE and BFF/tokens/cookies architectures must be designed according to the threat model and IdP policy.

## 7. Resource Server: Validates Access Tokens, Does Not Issue Them

A Spring WebFlux API acts as a Resource Server when it receives:

```http
Authorization: Bearer ACCESS_TOKEN
```

The API's responsibilities are:

1. Extract the bearer token cleanly from the request.
2. **Verify** the token according to its type and configured mechanism.
3. Build `Authentication`/authorities from verified data.
4. Apply URL/method/object authorization.
5. Return the resource only if both authentication and permissions succeed.

Spring Security reactive supports two main approaches.

### 7.1. JWT Access Token

A JWT is a token whose signature can be verified by the resource server using public keys/JWKS published by a trusted issuer, **without contacting the AS on every request** once keys/metadata are available/cached. Common configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test
```

Spring Security uses `ReactiveJwtDecoder` to decode and **validate** the token, not merely Base64-parse it. When using issuer discovery, metadata dependency at startup vs. request time depends on configuration, caching, and version. You can also specify `jwk-set-uri` explicitly so the decoder knows where to fetch keys without depending on discovery at startup:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test
          jwk-set-uri: https://id.example.test/oauth2/jwks
```

You must still ensure the **right issuer**, allowed signature algorithms, `exp`/`nbf`, the API's `aud`, tenant, scope, and key rotation. **Do not assume all business audience validation is enabled automatically by the framework**: applications often must configure an `OAuth2TokenValidator<Jwt>` or custom issuer/audience policy to ensure they only accept access tokens issued for that specific API.

### 7.2. Opaque Access Token

An opaque token is a string without a publicly decodable JWT structure; the API can use the AS's **token introspection endpoint**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: SERVER_SIDE_SECRET
```

The client ID/secret here are the **Resource Server's credentials to call introspection** as defined by the AS, **not** the OAuth2 Client website's secret. Real values must live in a secrets manager/environment, never committed to the repo. An opaque token itself is not a JWT; do not try `Base64.decode` to authenticate it yourself.

Introspection increases network/latency dependence on the AS or controlled caching, but can reflect active/revocation status faster than a signed JWT that has not yet expired. Choosing JWT vs. opaque depends on threat model, operations, revocation needs, latency, and policy.

### 7.3. HTTP 401 vs. HTTP 403

| Bearer API Scenario | Typical HTTP Status | Meaning |
| --- | --- | --- |
| No access token on protected endpoint | **401** | Unauthenticated |
| Invalid, expired, bad issuer/signature Bearer token | **401** | Authentication failed |
| Valid access token but missing `orders.read` | **403** | Authenticated, insufficient authorization |
| Valid access token and sufficient scope but does not own the order | **403** or policy-appropriate response | Object-level/tenant authorization |
| Authorization Code or ID token sent instead of access token | Rejected | Wrong credential type for Resource Server |

Responses may include `WWW-Authenticate: Bearer`. Never use error bodies to leak tokens, private keys, sensitive claims, or internal authorization policies. CORS and CSRF are separate layers and do not replace OAuth2 token validity decisions.

## 8. Authorization Server: Who Manages /authorize and /token?

The Authorization Server is where OAuth2 tokens are **issued** and authorization lifecycles are managed. It may be your organization's identity service, a third-party IdP product, or a custom application built with Spring Authorization Server. It typically includes:

- **Client registration:** client ID, secret/public client, redirect URI allowlist, grant types, scopes, client authentication methods.
- **User authentication** and consent (when a user is involved), determining which permissions are granted.
- **Authorization Endpoint:** receives `response_type=code` and returns a code via redirect.
- **Token Endpoint:** exchanges code/refresh/client credentials for tokens after validating the grant and client.
- **JWK Set/metadata:** publishes keys/issuer/endpoints so clients and resource servers can establish trust.
- **Introspection/Revocation:** enabled as needed; do not assume every AS exposes every endpoint at the same paths.
- **OIDC endpoints and ID tokens:** only when the AS is also an OpenID Provider, with OIDC issuer/userinfo/discovery per configuration.

### 8.1. Distinguishing the Endpoints

| Illustrative Path at the AS | Usually Called By | Purpose |
| --- | --- | --- |
| `/oauth2/authorize` | Browser via redirect initiated by Client | Authentication/consent and issuing an authorization code |
| `/oauth2/token` | Client backend or eligible public client | Exchanges a grant for access/refresh/ID tokens |
| `/oauth2/jwks` | Resource Server, Client/OIDC verifier | Retrieves public keys/JWK Set |
| `/oauth2/introspect` | Authorized Resource Server | Checks whether an opaque token is active and its scopes |
| `/oauth2/revoke` | Authorized Client | Revokes tokens per policy |
| `/.well-known/openid-configuration` | OIDC Client/Resource Server | OIDC provider metadata |
| `/userinfo` | OIDC Client, after obtaining a suitable access token | Claims about the end-user |

**These paths are examples from one configuration family**, not fixed requirements for every AS/IdP. External providers may use different URLs. Use trusted metadata/discovery or IdP documentation instead of hardcoding guessed paths.

### 8.2. Spring Security Reactive Does Not Provide a Complete Authorization Server Out of the Box

Spring Security WebFlux documentation covers two main areas: **OAuth2 Client** and **OAuth2 Resource Server**. The **Authorization Server** role is handled by Spring Authorization Server (a separate project in the Spring Security ecosystem); Authorization Server docs use **Servlet `HttpSecurity`/`SecurityFilterChain`** configuration. Do not take those examples, rename the class to `ServerHttpSecurity`, and assume you now have a full reactive Authorization Server with all endpoints.

The dependency typically used when you actually **build a dedicated Authorization Server**:

```xml
<!-- Dependency belonging to a separate Authorization Server application. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
```

Running a production Authorization Server also requires designing registered clients, user authentication, key management/JWK, issuer configuration, authorization storage, consent, token generators/TTL, revocation, rotation, auditing, and HA. **Merely adding the dependency does not make a complete IdP.** This lesson deliberately **does not pretend to build a runnable Authorization Server in a few lines of WebFlux**, because that is a separate application and security architecture.

### 8.3. Spring Authorization Server and Newer Spring Security Versions

In recent Spring Security branches, Authorization Server capabilities have deeper package/documentation integration into the Spring Security ecosystem. When checking current versions, consult the documentation for the exact **Spring Boot/Spring Security** version you run; do not assume an `HttpSecurity` snippet from a 7.x branch is drop-in compatible with Spring Authorization Server 1.5.x or WebFlux `ServerHttpSecurity`. **What never changes** is that the “token issuance” role is distinct from “client login” and “API token verification”.

## 9. Log-Reading Exercise: Infer the Role from the Transaction, Not the Service Name

| Log/request | Handling Role | Interpretation |
| --- | --- | --- |
| `GET /oauth2/authorization/demo` on website | OAuth2 Client | Initiates authorization request/redirect |
| Browser redirected to IdP `/oauth2/authorize` | Authorization Server | Authenticates/consents, issues code |
| `GET /login/oauth2/code/demo?code=...` on website | OAuth2 Client | Callback receiving code/state |
| `POST /oauth2/token` on IdP | Authorization Server | Validates grant, issues tokens |
| `POST /oauth2/token` called by backend worker | Client calling AS | Could be client_credentials/refresh grant |
| `GET /api/orders` + `Authorization: Bearer` | Resource Server | Validates access token/authorization |
| `GET /.well-known/openid-configuration` on IdP | Authorization Server/OpenID Provider | Publishes metadata |
| `GET /oauth2/jwks` on IdP | AS publishing public keys | Typically consumed by resource servers/clients |
| `POST /oauth2/introspect` on IdP | Authorization Server | Checks whether opaque token is active |
| `GET /api/userinfo` on IdP | OIDC UserInfo protected resource | Component of the OIDC provider |

The same IdP product can simultaneously be an AS and expose **resource endpoints** like UserInfo. A piece of software is not limited to a single role.

## 10. Plain Java 17: Reinforcing Roles with Exact Output

This example **neither issues nor parses tokens**; it is just a plain Java program to check whether you distinguish responsibilities accurately. It requires no Spring Boot, Maven, or internet access.

File `OAuthRolesDemo.java`:

```java
public final class OAuthRolesDemo {

    enum Role { CLIENT, RESOURCE_SERVER, AUTHORIZATION_SERVER }

    static String duty(Role role) {
        return switch (role) {
            case CLIENT -> "request and use access tokens";
            case RESOURCE_SERVER -> "validate access tokens and protect APIs";
            case AUTHORIZATION_SERVER -> "issue and manage access tokens";
        };
    }

    public static void main(String[] args) {
        System.out.println("CLIENT: " + duty(Role.CLIENT));
        System.out.println("RESOURCE_SERVER: " + duty(Role.RESOURCE_SERVER));
        System.out.println("AUTHORIZATION_SERVER: "
            + duty(Role.AUTHORIZATION_SERVER));
    }
}
```

Run with Java 17+:

```bash
javac OAuthRolesDemo.java
java OAuthRolesDemo
```

**Exact stdout**:

```text
CLIENT: request and use access tokens
RESOURCE_SERVER: validate access tokens and protect APIs
AUTHORIZATION_SERVER: issue and manage access tokens
```

In real systems, an OAuth2 Client sometimes only uses the ID token for OIDC Login without needing to call an API; the program above describes **typical responsibilities**, not the entirety of each role's capabilities.

## 11. Project A: WebFlux Java 17+ OAuth2/OIDC Client

Project A is a **Client website**. It does **not** issue JWTs and does **not** protect a separate Bearer API. Because there is no real IdP yet, the project reaches the step where the browser **redirects** to a demo Authorization Server; end-to-end login requires configuring a corresponding real IdP. The code and tests below **make no network calls to an IdP** when testing public endpoints or redirect initiation.

### 11.1. Project Structure

```text
oidc-client-webflux/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/client/
    │   │   ├── Application.java
    │   │   ├── ClientSecurityConfiguration.java
    │   │   └── PageController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/demo/client/OidcClientTests.java
```

### 11.2. pom.xml (OAuth2 Client Application)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oidc-client-webflux</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The goal is **Client/OIDC Login**, so `spring-boot-starter-oauth2-client` is used. There is no need to add `spring-boot-starter-oauth2-resource-server` if the website only handles login and outbound calls without exposing a Bearer-authenticated API. If both roles are required, separate resource server paths/filters must be configured.

### 11.3. src/main/resources/application.yml

```yaml
server:
  port: 8082

spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: local-learning-web
            client-secret: local-learning-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          demo-provider:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            jwk-set-uri: https://idp.example.test/oauth2/jwks
            user-info-uri: https://idp.example.test/userinfo
            user-name-attribute: sub
```

**Demo config warning:** `idp.example.test` and the client credentials here are **public dummy values**. They let the project boot and test redirects without metadata discovery. For full login, replace them with provider endpoints, `client_id`, secret/PKCE policy, and redirect URI **actually registered at the IdP**. Keep real client secrets in environment variables/a secret manager, never committed in YAML or frontend JS.

- `registration.demo` creates a `ClientRegistration` with registration ID **demo**.
- `provider.demo-provider` holds the Authorization Server/OIDC Provider endpoints; it does **not** make the client an AS.
- `scope: openid` indicates **OIDC** login, triggering the requirement for a valid ID token.
- `redirect-uri` is the callback on the **Client** at `/login/oauth2/code/demo`; the AS must allow that URI.
- For IdPs with issuer metadata, in production you can use `provider.*.issuer-uri` instead of manually listing endpoints when supported; ensure the issuer URL is valid and never run discovery against a user-supplied URL.

### 11.4. src/main/java/demo/client/Application.java

```java
package demo.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 11.5. src/main/java/demo/client/ClientSecurityConfiguration.java

```java
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ClientSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(withDefaults())
            .oauth2Client(withDefaults())
            .build();
    }
}
```

`oauth2Login` handles browser login and callbacks; `oauth2Client` provides OAuth2 Client components when the client needs to obtain/attach outbound access tokens. If only login is needed, the additional `oauth2Client` part may not be required for a simple flow; both are kept in the demo to emphasize that **both features belong to the Client role**, not AS/RS.

This sample uses the default login page and callback provided by Spring Security; `GET /login` and `GET /oauth2/authorization/demo` are handled by security filters, not the controller below. **Do not** arbitrarily create `@GetMapping("/login/oauth2/code/demo")` without understanding the callback filter.

### 11.6. src/main/java/demo/client/PageController.java

```java
package demo.client;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("client public OK");
    }

    @GetMapping("/private")
    public Mono<String> privateInfo() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "signed-in:" + auth.getName());
    }
}
```

`/private` simply returns the signed-in principal name via the reactive security context, without needing any client-issued access token. In real products, never return raw ID tokens/access tokens to the browser just to prove login; the browser typically uses the BFF's session cookie, while the BFF retains the authorized client/tokens appropriately.

### 11.7. src/test/java/demo/client/OidcClientTests.java

```java
package demo.client;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OidcClientTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAvailableWithoutLogin() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("client public OK");
    }

    @Test
    void browserNavigationToPrivatePageStartsLogin() {
        client.get().uri("/private")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void loginInitiationRedirectsToAuthorizationServer() {
        client.get().uri("/oauth2/authorization/demo")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION, location -> {
                assertTrue(location.startsWith(
                    "https://idp.example.test/oauth2/authorize?"));
                assertTrue(location.contains("response_type=code"));
                assertTrue(location.contains("client_id=local-learning-web"));
                assertTrue(location.contains("state="));
            });
    }

    @Test
    void mockedOidcLoginCanAccessProtectedPage() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/private")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(value -> assertTrue(value.startsWith("signed-in:")));
    }
}
```

There are **4 tests** focused on distinguishing the Client role:

- Unauthenticated users can still view the public endpoint.
- Browser navigation to a private page is directed to login.
- `/oauth2/authorization/demo` produces a redirect **to the Authorization Server** with `response_type=code`, `client_id`, and `state` — it does not issue a local token.
- `mockOidcLogin()` verifies authorization once a mocked OIDC Authentication is present.

**Crucially:** `mockOidcLogin()` **skips** a live IdP, signatures, ID token validation, state/nonce exchange, and real callbacks. This test **does not prove end-to-end SSO**. To prove real behavior, use a test IdP with real redirects/callbacks/cookies, registered client settings, and verify the actual token flow.

### 11.8. Running Project A

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

The tests are expected to let you observe the **4 tests** in `OidcClientTests`. This is an **expectation from the code**, not a claim that the tests have been executed in this environment.

Open:

```text
http://localhost:8082/public
http://localhost:8082/private
http://localhost:8082/oauth2/authorization/demo
```

`/private` leads to login; `/oauth2/authorization/demo` will redirect to the dummy hostname so it **cannot complete login** until replaced with a real IdP. A host-not-found error here **does not mean the OAuth2 Client configuration logic is wrong**; it marks the boundary between a redirect demo and a live SSO environment.

## 12. Project B: WebFlux Java 17+ OAuth2 Resource Server

Project B is an **API receiving Bearer access tokens**. It has no OAuth2 login page and does not manage authorization codes/callbacks. Spring Security **verifies JWTs via `ReactiveJwtDecoder`** against issuer/JWKS when running with real tokens; the tests here use `mockJwt()` to check scopes and HTTP authorization without **depending on an IdP**.

### 12.1. Project Structure

```text
oauth2-resource-api/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/resource/
    │   │   ├── Application.java
    │   │   ├── ResourceSecurityConfiguration.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/demo/resource/ResourceServerTests.java
```

### 12.2. pom.xml (Resource Server Application)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oauth2-resource-api</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The project only includes the resource-server starter; no client starter is needed to **receive** Bearer JWTs. Only if the API also needs to call a downstream service with client credentials would you add OAuth2 Client separately and manage outbound tokens under control.

### 12.3. src/main/resources/application.yml

```yaml
server:
  port: 8083

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test
          jwk-set-uri: https://idp.example.test/oauth2/jwks
```

These two URLs **are dummy issuer/JWK endpoints for a no-IdP demo**. Declaring both `issuer-uri` and `jwk-set-uri` tells the resource server where keys live without needing issuer discovery right at startup; **real JWTs cannot be verified** until configured with a real IdP issuing JWTs with matching issuer/signatures. Tests using `mockJwt` make no JWKS network calls and **do not check signatures**; this lesson states so explicitly.

In production, use a real trust policy: expected `iss`, key rotation, signing algorithms, `exp`/`nbf`, appropriate audience, token type, and tenant/scope; if the AS issues opaque tokens, configure `opaqueToken`/introspection instead of `jwt`. Never configure `jwk-set-uri` to point to a server chosen by client requests (SSRF/trust bypass).

### 12.4. src/main/java/demo/resource/Application.java

```java
package demo.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 12.5. src/main/java/demo/resource/ResourceSecurityConfiguration.java

```java
package demo.resource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ResourceSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/read")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers("/api/admin")
                    .hasAuthority("SCOPE_admin")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            // Bearer API only in demo, no browser session/login used.
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Why disable CSRF in Project B?** This demo assumes **the API only accepts `Authorization: Bearer` access tokens explicitly attached by the client**, with no cookies/automatic browser authentication and no state-changing endpoints called via a session. This assessment **does not hold for every resource server**: if the same app also supports cookie sessions, browser-cached Basic auth, or form login, CSRF must be designed per security chain/request matcher; never blindly copy `.csrf(...disable())` into production.

`hasAuthority("SCOPE_orders.read")` relies on the default mapping of the JWT scope claim to Spring authorities named `SCOPE_...`. If the issuer uses `roles`/custom scope claims or a custom converter, you must verify the authority mapping. **`SCOPE_orders.read` does not automatically equal `ROLE_ADMIN`.**

### 12.6. src/main/java/demo/resource/ApiController.java

```java
package demo.resource;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("resource public OK");
    }

    @GetMapping("/api/read")
    public Mono<String> read() {
        return Mono.just("orders read OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "subject=" + auth.getName());
    }
}
```

`/api/me` reads `Authentication` from **Reactor Context**, rather than taking a username from a client-supplied query/header. With default JWT handling, the authentication name is typically `sub`; if a converter changes the principal claim, it may differ. Use a trusted subject ID and tenant scope when checking resource ownership, rather than merely trusting a returned display name.

### 12.7. src/test/java/demo/resource/ResourceServerTests.java

```java
package demo.resource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ResourceServerTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec withScope(
            String uri, String authority) {
        return client.mutateWith(
                mockJwt().authorities(
                    new SimpleGrantedAuthority(authority)))
            .get().uri(uri)
            .exchange();
    }

    @Test
    void publicEndpointDoesNotRequireBearerToken() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("resource public OK");
    }

    @Test
    void protectedEndpointWithoutBearerIs401() {
        client.get().uri("/api/read")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void readEndpointWithCorrectScopeIs200() {
        withScope("/api/read", "SCOPE_orders.read")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("orders read OK");
    }

    @Test
    void readEndpointWithWrongScopeIs403() {
        withScope("/api/read", "SCOPE_orders.write")
            .expectStatus().isForbidden();
    }

    @Test
    void readEndpointWithUnprefixedAuthorityIs403() {
        withScope("/api/read", "orders.read")
            .expectStatus().isForbidden();
    }

    @Test
    void adminEndpointWithAdminScopeIs200() {
        withScope("/api/admin", "SCOPE_admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void adminEndpointWithOnlyReadScopeIs403() {
        withScope("/api/admin", "SCOPE_orders.read")
            .expectStatus().isForbidden();
    }

    @Test
    void getMeUsesAuthenticatedJwtSubject() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("subject=alice");
    }

    @Test
    void getMeWithoutTokenIs401() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void defaultDenyProtectsUnknownPath() {
        withScope("/api/not-configured", "SCOPE_admin")
            .expectStatus().isForbidden();
    }

    @Test
    void bothScopeAuthoritiesCanAccessBothEndpoints() {
        var both = mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"),
            new SimpleGrantedAuthority("SCOPE_admin"));

        client.mutateWith(both)
            .get().uri("/api/read")
            .exchange()
            .expectStatus().isOk();

        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"),
                new SimpleGrantedAuthority("SCOPE_admin")))
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validMockJwtDoesNotImplyEveryAuthority() {
        withScope("/api/admin", "SCOPE_profile")
            .expectStatus().isForbidden();
    }
}
```

The test suite has **12 `@Test` methods**, showing that the Resource Server API:

- Missing Bearer -> **401** (unauthenticated).
- Sufficient `SCOPE_orders.read` authority -> **200** at `/api/read`.
- Wrong/missing scope -> **403** even though the mocked principal is authenticated.
- Authority `orders.read` instead of `SCOPE_orders.read` -> **403** in the demo configuration.
- JWT subject appears via `Authentication.getName()` in Reactor Context.

**Test scope:** `mockJwt()` creates a valid mock Authentication for **authorization tests**, and intentionally **does not test signatures, issuers, audiences, expirations, the actual Bearer decoder, or remote JWKS**. To test JWT security end-to-end, add tests with genuinely signed JWTs from a test AS/JWKS (and JWTs with invalid signature/aud/iss/exp) in addition to the tests above.

### 12.8. Running Project B

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

The Resource Server test suite is expected to have **12 tests**. Do not claim they have actually been executed: this is the expected learning outcome from the source code.

Call the public endpoint:

```bash
curl -i http://localhost:8083/public
```

Call a protected endpoint without a Bearer token:

```bash
curl -i http://localhost:8083/api/read
```

Expected: **401** with a Bearer challenge. To call the protected API successfully at runtime, you need a **real JWT access token issued for the API by the configured issuer**, with the right audience/scope. Because the project uses a dummy IdP:

```text
GET /api/read without token -> 401
GET /api/read with an arbitrary hand-crafted Base64 JWT -> not accepted
GET /api/read with a valid access token from a real IdP -> can be 200 if scope matches
```

**Do not** substitute a browser's OIDC ID token into a Bearer request to the Resource Server. Never treat `mockJwt()` from tests as a token generator outside tests.

## 13. What If One WebFlux Application Acts as Both Client and Resource Server?

A BFF + API architecture sometimes uses **a single Spring process**: users log in with an OIDC session on `/ui/**`, while the server also accepts Bearer JWTs from another service on `/api/**`. These are **two authentication mechanisms** with separate boundaries.

The design approach is to have multiple `SecurityWebFilterChain` beans **with specific `securityMatcher` and `@Order`**, as a conceptual example:

```java
// Illustrative snippet, not a complete application.
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain uiChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults())
        .build();
}
```

Remember to import `@Order`, `PathPatternParserServerWebExchangeMatcher`, `Customizer`, and `SecurityWebFilterChain`. **This is only an architectural illustration**: production code also needs CSRF/cookies, public login/callback paths, unauthenticated entry points, CORS, JWT decoders, registration repositories, session repositories, and properly ordered security matchers. **Do not copy verbatim to expose sensitive APIs.**

Common mistakes:

- Letting a Bearer API return an HTML login redirect instead of 401.
- Letting a browser session cookie accidentally authenticate an API intended for service-to-service Bearer tokens.
- Using a token with `aud=web-client` to access an API expecting `aud=orders-api`.
- Opening `/api/**` broadly just because `/ui/**` needs public routes.
- Disabling CSRF for the entire session-based website just because the Bearer API doesn't use cookies.
- Wrong `@Order` causing the web chain to match the API or vice versa.
- Using user A's access token when outbound `WebClient` handles user B's request.

Principle: **the right role for the right request/route**, verify principals/authorities, and test negative cases.

## 14. Authentication, Authorization, and Scope/Role

An OAuth2 Access Token typically carries granted **scopes**. With Spring Security's JWT Resource Server, scopes from the `scope` or `scp` claim are converted by default into `SCOPE_...` authorities. For example, claim `scope="orders.read orders.write"` becomes:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Then:

```java
.pathMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
```

is not the same as `hasRole("ADMIN")`, which by default convention requires `ROLE_ADMIN`. **Roles and scopes are not two different token formats**; they are claims/authorization conventions mapped into authorities. A user with `ROLE_ADMIN` does not automatically possess the `orders.read` scope without a mapping policy.

### 14.1. JWT Claims Do Not Automatically Become Authorities

An illustrative JWT payload:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
```

Showing a payload **does not mean the token is valid**. Signature, issuer, audience, timestamps, and relevant policies must be verified. Do not take this JSON snippet, assemble a Base64 token by hand, and trust it. If the AS sends `roles`, `groups`, or permissions in custom claims, the resource server needs an explicit converter; Spring Security does not automatically turn every claim into `ROLE_...`.

### 14.2. User Authority and Client Authority Must Both Be Bounded

In the `authorization_code` grant, the access token typically reflects authorization involving both the user and the client; you must still verify which user/tenant owns the accessed resource. In `client_credentials`, the token typically represents the **client application**, not an end-user. Never take a service token's `sub` and treat it as the owner of a customer's order.

Concepts like `azp`, `client_id`, `aud`, `iss`, tenant ID, and resource ID may be needed. Exact policy depends on the IdP and token profile; never force a vendor-specific claim into a universal OAuth2 rule.

## 15. Why Merely Decoding a JWT Is a Serious Bug

JWT segments are Base64URL-encoded; anyone holding a token can decode its header/payload. **Decoding is not verifying.**

Suppose you see:

```json
{"sub":"admin","scope":"orders.read"}
```

This does not mean the caller was actually granted permissions. A malicious client can craft such a payload itself. The Resource Server must verify:

1. Is the **Signature** valid against a trusted JWKS/key?
2. Is the `alg` header among the allowed algorithms? Never accept `none` arbitrarily.
3. Does `iss` match the trusted Authorization Server?
4. Is `aud` intended specifically for this API/resource server?
5. Are `exp`/`nbf` and clock skew valid?
6. Are `scope`/permissions sufficient for the endpoint and resource object/tenant?
7. Does the token type/format match the access token profile?
8. Are revocation/session constraints or extra claim validations required?

An **ID token** may carry `aud=client-id`; if the API skips audience checking, it risks accepting a token meant for the Client for the wrong purpose. This is a **token substitution** issue. A Resource Server does not accept a JWT merely because it was signed by a trusted IdP; it must also check **who the token was issued for and what it is meant to do**.

### 15.1. JWT vs. Opaque and Revocation Capabilities

A signed, expiring JWT is self-contained; it can be verified locally, quickly, and with low per-request AS dependency, but immediate revocation is harder without an extra denylist/backchannel or short lifetimes. An opaque token can be introspected to check active status at the AS; in return, it introduces network/caching/failure-mode trade-offs. Neither option is automatically “more secure” in every environment.

When the AS rotates keys, the JWKS cache must refresh appropriately; during an AS outage, token validation must follow a clear failure policy. Never disable signature checking in a Resource Server just to preserve availability.

## 16. 401/403 and OAuth2 Errors by Role

| Where It Occurs | Error | Common Cause | How to Investigate |
| --- | --- | --- | --- |
| OAuth2 Client on redirect | `redirect_uri_mismatch` | Callback URI not registered at the AS | Exact scheme/host/port/path, proxy headers |
| OAuth2 Client on callback | `invalid_state` or login failure | Session/correlation state lost/mismatched | Cookies, WebSession, SameSite, reverse proxy |
| OAuth2 Client on token exchange | `invalid_grant` | Expired/reused code, wrong code_verifier, redirect URI mismatch | Redacted authorization code/PKCE/token endpoint logs |
| OAuth2 Client on token exchange | `invalid_client` | Invalid client authentication | Client ID, secret/mTLS/JWT assertion/registration |
| OAuth2 Client on ID token validation | Invalid issuer/audience/nonce | Failed OIDC security checks | Discovery, client_id, issuer, nonce, clock |
| Resource Server inbound | **401** | Missing/invalid/expired Bearer token | `WWW-Authenticate: Bearer`, issuer/JWKS/clock |
| Resource Server inbound | **403** | Valid token but missing scope/permission/tenant | Authentication authorities, policy |
| Authorization Server | `invalid_scope` | Client requested an unpermitted scope | RegisteredClient, consent policy |
| Authorization Server | `unauthorized_client` | Grant type or flow not allowed for this client | Registration/grant configuration |
| Authorization Server | Invalid redirect URI | AS refuses to redirect code | Client redirect URI allowlist |
| BFF browser UX | Login redirect loop | Wrong session/cookie/callback path | Cookie SameSite/Secure, base URL, proxy |
| WebFlux API CORS | Browser reports CORS despite HTTP 401/403 | Error response/preflight missing CORS headers | Network tab, CORS before security |

**OAuth2 protocol errors** like `invalid_grant` may appear in responses from the Token Endpoint and do not necessarily surface as HTTP 401/403 on a business API. When `/orders` returns 403, do not jump to assuming `invalid_grant`: it may simply be a missing authority.

### 16.1. When OIDC Login Fails

Debugging order:

1. Check `ClientRegistration` and provider metadata (authorization/token/JWKS/userinfo).
2. Confirm the browser is redirected from the **Client** to the **AS** with the right `client_id`, `scope`, `redirect_uri`, and `state`.
3. Confirm the callback returns to the exact `/login/oauth2/code/{registrationId}`, without proxy rewriting.
4. Check that state/session remain intact and cookies are sent back by the browser (SameSite/Secure).
5. Check that the code is fresh and unused; PKCE verifier and token exchange succeed.
6. Check OIDC ID token validation, issuer, audience, nonce, clock, and key rotation.
7. Check that the Spring Security session was saved if the app requires logged-in navigation.
8. Never log codes, access tokens, refresh tokens, ID tokens, or client secrets.

### 16.2. When Calling a Resource Server Fails with 401/403

Debugging order:

1. Confirm the Client actually sent an **`Authorization: Bearer` access token**, not an ID token.
2. If **401**: was the token sent, are `exp`/signature/issuer/audience valid, and are the JWKS/introspection endpoints reachable?
3. If **403**: check the authorities Spring derived from the token (`SCOPE_...`/roles) and `hasAuthority`/method security rules, plus tenant/resource ownership.
4. If the browser throws a CORS error before seeing 401/403: debug CORS/preflight/error responses **separately**, do not fix it by disabling Bearer validation.
5. If recently upgraded versions: review resource-server starter/Jose and reactive JWT converter setup.
6. Never treat passing `mockJwt()` tests as proof that real tokens have valid signatures or audiences.

## 17. Security Checklists by Role

### OAuth2 Client / OIDC Login

- [ ] Use Authorization Code + PKCE where appropriate; verify state, OIDC nonce, and checks supported by the provider/framework.
- [ ] Register exact redirect URIs; use HTTPS in real environments.
- [ ] Never place confidential client secrets in frontend code/public bundles.
- [ ] Store access/refresh tokens securely, never log them, and never attach them by default to every WebClient request.
- [ ] Validate ID token issuer/audience/signature/time and purpose; never use ID tokens instead of access tokens.
- [ ] Configure browser session cookies with appropriate HttpOnly/Secure/SameSite; protect CSRF on cookie-based endpoints.
- [ ] Prevent open redirects and callback injection; test logout/session rotation paths.
- [ ] Test login/callbacks with a real IdP or sandbox IdP, not only `mockOidcLogin`.

### Resource Server

- [ ] Accept only access tokens with the API's proper type/audience/issuer.
- [ ] Validate signatures, algorithms, timestamps, keys/JWKS, or introspection active status.
- [ ] Map scopes/roles/claims to authorities consistently; never trust arbitrary client claims.
- [ ] Enforce HTTP + method/object/tenant authorization, not just `authenticated()`.
- [ ] Return 401 for invalid/missing tokens and 403 for valid principals lacking permissions per policy.
- [ ] Set CSRF policy according to credential type; never disable it if endpoints use browser cookies.
- [ ] Test valid tokens as well as bad signature/issuer/audience/expired tokens in addition to `mockJwt` authorization tests.
- [ ] Never log raw Bearer headers, tokens, or JWKS private keys.

### Authorization Server

- [ ] Enforce strict policies for RegisteredClient, redirect URIs, client auth, and grant types.
- [ ] Enforce short-lived, single-use authorization codes, PKCE, CSRF/callback-injection protection, and proper consent.
- [ ] Align token claims/issuer/audience/TTL with resource servers and client registrations.
- [ ] Store private signing keys securely, with key rotation/JWKS and recovery runbooks.
- [ ] Monitor introspection/revocation when needed, as well as sessions/logout/end-user auth.
- [ ] Test metadata, trusted issuer, scopes, and OIDC provider behavior.
- [ ] Ensure clear multi-instance HA/DB storage, auditing, monitoring, and incident response.
- [ ] Choose the proper Authorization Server product/stack instead of mistaking `oauth2Login` for a token issuer.

## 18. Role Classification Exercises and Answers

**Q1.** A WebFlux app displays a “Login with OIDC” button, redirects users to an IdP, and receives a code. What is it?  
**Answer:** **OAuth2 Client** using OIDC/OAuth2 Login functionality. It is not an Authorization Server.

**Q2.** An API only configures `.oauth2ResourceServer(o -> o.jwt(...))`. Does it issue JWTs or log users in via the browser?  
**Answer:** No. It **validates access tokens** for the API; token issuance and interactive login belong to other roles.

**Q3.** Who checks `grant_type=authorization_code` and issues an access token after receiving the code?  
**Answer:** The **Authorization Server** at the Token Endpoint.

**Q4.** Who calls `GET /api/orders` with `Authorization: Bearer`?  
**Answer:** The **OAuth2 Client** (or a service acting as a Client) sends the request; the **Resource Server** receives and validates the token.

**Q5.** The browser receives an ID token during OIDC login. Should the ID token be used directly to call all APIs?  
**Answer:** No. The ID token is for the **OIDC Client**; APIs require an **access token** with the matching issuer/audience/scope.

**Q6.** A background job uses client credentials with no user login. Is the job an OAuth2 Client?  
**Answer:** Yes. An OAuth2 Client does not necessarily involve a user or browser.

**Q7.** Why does a resource server need to verify `aud` in addition to signature/issuer?  
**Answer:** A token signed by the same IdP could still be intended for a **different Client or API**. Checking the audience prevents token substitution/cross-service token replay.

**Q8.** Why does a passing `mockJwt()` test not prove the real AS/JWKS are configured correctly?  
**Answer:** The mock bypasses real JWT decoding/verification; it only tests Spring authorization rules against a supplied Authentication.

**Q9.** A user logs in successfully at the Client but gets 403 when calling an API. Where is the issue?  
**Answer:** The access token may be valid but lack the required scope/permission/tenant, or the Resource Server policy denies it. Successful OIDC login **does not promise** 200 on every API.

**Q10.** If a server issues self-signed tokens, is that system automatically a standards-compliant OAuth2 Authorization Server?  
**Answer:** No. “Generating a JWT” is just token generation; a real AS requires client registration, grants, consent, client authentication, token lifecycles, metadata/JWKS, and protocol security.

**Q11.** What does `scope=openid` mean?  
**Answer:** It activates an **OpenID Connect** request so the client can receive/validate an ID token to verify the end-user's identity.

**Q12.** How does a Resource Server process opaque tokens?  
**Answer:** It typically calls **introspection** on the AS via `ReactiveOpaqueTokenIntrospector` instead of decoding a JWT locally.

**Q13.** Can one Spring WebFlux app act as both Client and Resource Server?  
**Answer:** Yes; however, you must **separate matchers/security chains/credentials and token audiences**, ensuring web session logins do not inadvertently bleed into Bearer API endpoints.

**Q14.** Why is writing your own `POST /login/oauth2/code/demo` handler misaligned with the default flow?  
**Answer:** The default callback is typically a browser GET redirect carrying code/state to the client endpoint; Spring Security handles it and exchanges the code with the AS. Do not write an ad-hoc callback handler that skips validation.

**Q15.** Without a real client secret in Project A, can the project still test the redirect?  
**Answer:** For the confidential client in the demo, a dummy secret is already set; redirect initiation happens before token exchange. End-to-end login requires real client authentication/registration, not just a dummy secret.

**Q16.** Does a Resource Server need to contact the Authorization Server for every JWT?  
**Answer:** Not necessarily. Signed JWTs can be verified locally with trusted, cached keys/JWKS. Opaque token introspection generally depends on the AS/cache by design.

## 19. Summary and Official Documentation

**Final rule of thumb:**

```text
OAuth2 Client
    -> REQUESTS tokens / uses tokens / can log users in via OIDC.

OAuth2 Resource Server
    -> RECEIVES Bearer access token / validates / checks scope & API permissions.

OAuth2 Authorization Server
    -> ISSUES authorization code, access token, refresh token (and ID token if OIDC).

OAuth2 Login
    -> A FEATURE of OAuth2 Client, not a fourth role.

ID Token
    -> OIDC Client verifies identity; never use directly as an API access token.

Access Token
    -> Resource Server verifies, using proper audience/scope.

Spring Security WebFlux
    -> oauth2Login + oauth2Client + oauth2ResourceServer.
       Authorization Server is a separate product/configuration, not issued
       automatically by those two DSLs.
```

This lesson distinguished **roles, protocol messages, tokens, endpoints, Spring dependencies, DSLs, test strategies, and security boundaries**. When debugging, the first question is not “is OAuth enabled?” but rather: *which role is this request entering, which token is being used, and which component is responsible for verifying or granting it?*

**Official Sources and Reference Standards:**

- Spring Security 6.5 – OAuth2 WebFlux overview: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security – Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security – Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security – Reactive Authorized Client/WebClient: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Security – Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security – Reactive Resource Server opaque tokens: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- Spring Security – Reactive OAuth2 WebTestClient testing (mockJwt, mockOidcLogin): https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Authorization Server – Getting Started: https://docs.spring.io/spring-authorization-server/reference/getting-started.html
- IETF RFC 6749 – OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 6750 – OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- IETF RFC 7636 – Proof Key for Code Exchange (PKCE): https://www.rfc-editor.org/rfc/rfc7636
- IETF RFC 8414 – OAuth2 Authorization Server Metadata: https://www.rfc-editor.org/rfc/rfc8414
- OpenID Connect Core 1.0 – Identity layer and ID token: https://openid.net/specs/openid-connect-core-1_0.html
- OWASP OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
