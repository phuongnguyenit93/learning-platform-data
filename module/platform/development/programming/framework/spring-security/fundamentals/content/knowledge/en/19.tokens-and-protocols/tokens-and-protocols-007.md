# OAuth2: Resource Owner, Client, Authorization Server, and Resource Server

> **Context:** Spring Security – Fundamentals / **Tokens and Protocols**. This lesson explains the **four standard roles of OAuth 2.0**, trust boundaries, two common authorization flows, tokens, and how those roles map to Spring Security components. Hands-on examples use Java 17, Spring Boot 3.5.0, and Spring Security 6.x. OAuth 2.0 primarily addresses **authorization / delegated access**; when user identity authentication and ID tokens are needed, also explore **OpenID Connect (OIDC)**.

## 1. Why Are Four Separate Roles Needed?

Imagine Alice is using the **Report Dashboard** application and wants it to read part of her profile stored at **Profile API**. Alice does not want to give her Profile API password to Report Dashboard. The system has a separate authorization server, such as `https://login.example.test`.

In this scenario:

- **Resource owner:** Alice, the entity capable of granting access to protected data.
- **Client:** Report Dashboard, the application wanting to call the API with granted permissions.
- **Authorization server:** Server `login.example.test` that authenticates, confirms granted permissions, and issues tokens.
- **Resource server:** Profile API, the server holding the data and verifying access tokens on incoming requests.

```mermaid
flowchart LR
    RO["Resource owner<br/>Alice"] -->|"signs in / consents to grant access"| AS["Authorization server<br/>login.example.test"]
    C["Client<br/>Report Dashboard"] -->|"authorization request"| AS
    AS -->|"authorization code / access token"| C
    C -->|"Bearer access token"| RS["Resource server<br/>Profile API"]
    RS -->|"data per policy"| C
    C -->|"displays result"| RO
```

**Core value:** the client application receives **scoped permissions** without needing to know the resource owner's password. The resource server must not trust the client merely because the client claims "Alice agreed"; it must verify the token and its own resource server policies.

RFC 6749 defines these four roles at a **logical** level. They do not necessarily correspond to four separate processes: the authorization server and resource server may live in the same system or separate infrastructure; one piece of software can act as an OAuth client when calling external APIs and as a resource server for its own API.

## 2. The Four Roles According to RFC 6749

### 2.1. Resource Owner — Entity Capable of Granting Access

The **Resource owner** is an entity capable of granting access to a protected resource. When that entity is a person, the RFC calls them an *end-user*. In the example, Alice may consent to Report Dashboard reading her profile while refusing to let it edit or delete the profile.

Key points:

1. The resource owner is **not** the server storing the data; the entity managing/authorized to grant permission is the resource owner.
2. The resource owner is **not always a person sitting at a browser**. In machine-to-machine systems, not every grant involves an interactive user.
3. Alice may not hold absolute rights over all data: an enterprise API is also subject to tenant rules, organizational permissions, legal policies, and sharing permissions.
4. Authentication (who Alice is) and authorization (what Alice allows the client to do) are two related yet distinct decisions.

Example: A user clicking "Allow application to read name and email" is delegating permission to the client, not giving their password to the client. The authorization server may require login, MFA, or additional policies before consenting.

### 2.2. Client — Application Requesting Access to Resources

The **Client** is an application making protected resource requests, using the resource owner's authorization or the client's own permissions under an appropriate grant.

A client can be:

- A server-side web application with its own backend;
- A single-page application (SPA) running in a browser;
- A mobile/desktop app;
- A backend job or service-to-service integration.

**A client is not necessarily a browser.** In the authorization code flow, the browser is the *user-agent* helping the resource owner interact with the authorization server; the OAuth client may be the application's backend.

Important distinction:

| Client | Keeps Secret Safely? | Characteristics |
| --- | --- | --- |
| Confidential client, e.g., managed backend | Yes, if secrets/keys are managed securely | Can authenticate at the token endpoint via registered mechanism |
| Public client, e.g., SPA or mobile app distributed to users | Cannot guarantee keeping a client secret | Requires Authorization Code + PKCE and appropriate safeguards; **never embed secrets in the frontend** |

`client_id` is typically a **public identifier**, not proof of client authentication. `client_secret` (if issued) must be protected as a credential and never embedded in JavaScript, APKs, or public repositories. Public clients still require client registration and other checks such as redirect URIs and PKCE.

### 2.3. Authorization Server — Issues Tokens After Evaluating Grants

The **Authorization server (AS)** processes authorization requests and issues access tokens to the client once conditions are met. For user-interactive flows, the AS typically orchestrates login, consent, code issuance, and token exchange. For the client credentials grant, the AS authenticates the client and issues tokens for operations the client is permitted to perform.

Example endpoints commonly provided by an AS:

| Endpoint | Responsibility | Notes |
| --- | --- | --- |
| `/oauth2/authorize` | Receives authorization requests, handles login/consent, returns code on success | Accessed via browser redirect |
| `/oauth2/token` | Exchanges an authorization code or credentials/grant for tokens | Communicates over HTTPS, validates grant and client |
| `/oauth2/jwks` | Publishes public keys for JWT verification when using a compatible mechanism | Never publishes private keys |
| `/oauth2/introspect` | Lets resource servers check opaque token status or per chosen architecture | Must authenticate authorized callers |
| `/oauth2/revoke` | Revokes tokens per RFC 7009 when supported by the AS | Does not guarantee every JWT access token is rejected immediately if the RS does not check state |
| Metadata/discovery | Publishes endpoints, issuer, and supported capabilities | E.g., RFC 8414 / OIDC discovery |

The URLs above are only **common examples**, not a mandate that every provider uses those exact paths. With Spring Authorization Server, some default paths may look similar; read actual metadata and configuration rather than hardcoding from this lesson.

An AS may be paired with an Identity Provider to authenticate users, yet **logging in to an Identity Provider and a resource server accepting an access token are two distinct steps**.

### 2.4. Resource Server — API Server Receiving and Validating Tokens

The **Resource server (RS)** hosts/serves protected resources. When a client sends a Bearer access token, the RS must validate it and decide whether the request is permitted for the specific resource.

With JWTs, the RS typically must verify:

- Valid signature, trusted algorithm/key, expiration (`exp`), and not-before (`nbf`) if present;
- Issuer (`iss`) matching the configured AS;
- Audience (`aud`) or resource indicator matching **this API**, if the token profile/AS uses audience;
- Scopes/authorities, HTTP action, and resource role/tenant/ownership rules;
- Key status or revocation if the system requires and implements additional checks.

With opaque tokens, the RS can use token introspection at the AS to ask whether the token is still **active** and falls within appropriate scopes. Do not decode an opaque token as though it were a JWT.

**Do not delegate all authorization to the authorization server:** the AS can report that a token has `scope=profile.read`, yet Profile API must still check whether Alice is permitted to read **the requested profile record**. Scope is only part of the decision.

## 3. Summary of Roles and Responsibility Boundaries

| Question | Primary Responsible Component |
| --- | --- |
| Who is authorized to consent to reading the profile? | Resource owner |
| Who wants to call the API? | Client |
| Who authenticates the user account, approves the grant, and issues the access token? | Authorization server |
| Who holds the profile and rejects tokens lacking sufficient permissions? | Resource server |
| Who stores `client_id` and performs the redirect to the AS? | Client |
| Who must verify the registered `redirect_uri`? | Authorization server |
| Who must verify the token has the API's right `aud`? | Resource server |
| Who must keep the client secret confidential? | Confidential client and authorization server |
| Who can re-issue an access token via a refresh token? | Authorization server, if the grant/client qualifies |
| Who must block IDOR/BOLA when user A requests user B's data? | Resource server and business/data layer |
| Who decides which scopes a client may consent to? | AS policy and resource owner when user interaction occurs |

**Trust model:** Clients must not grant themselves permissions by altering requests or claims. The RS must not trust every Bearer token just because it has JWT structure; tokens must be verified for origin, intended recipient, lifetime, and permissions. The AS must not trust a client-supplied `redirect_uri` without matching it against registered values per policy.

## 4. Authorization Code + PKCE: Flow with an Interactive Resource Owner

The **Authorization Code Grant** is a common way for a client to request permissions on behalf of a user. Security BCP RFC 9700 requires **public clients to use PKCE**; confidential clients are also recommended to use PKCE.

### 4.1. High-Level Sequence

```mermaid
sequenceDiagram
    participant O as Alice / Browser
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    O->>C: Clicks "Connect Profile API"
    C->>C: Generates state + code_verifier
    C->>C: Computes S256 code_challenge
    C-->>O: Redirects to authorization endpoint
    O->>AS: GET /authorize?client_id=...&scope=...&state=...&code_challenge=...
    AS->>O: Login + consent (if needed)
    O->>AS: Grants appropriate permissions
    AS-->>O: Redirects back to client with code + state
    O->>C: Callback with code + state
    C->>C: Verifies state
    C->>AS: POST /token code + code_verifier + client auth if applicable
    AS->>AS: Verifies code, client, redirect_uri, and PKCE
    AS-->>C: access_token (+ refresh_token if issued)
    C->>RS: GET /api/profile with Authorization: Bearer access_token
    RS->>RS: Validates token + scope + policy
    RS-->>C: Returns authorized profile
    C-->>O: Displays result
```

To keep the example accessible, the flow depicts a typical browser redirect. Real client components may use BFF, SPA, or mobile; how tokens are stored and where code exchange occurs depend on client classification.

### 4.2. Authorization Request — Parameters to Understand

**Illustrative** example; values are placeholders only:

```http
GET /oauth2/authorize?
    response_type=code&
    client_id=report-dashboard&
    redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&
    scope=profile.read&
    state=opaque-random-state&
    code_challenge=BASE64URL_SHA256_VERIFIER&
    code_challenge_method=S256
Host: login.example.test
```

| Parameter | Meaning |
| --- | --- |
| `response_type=code` | Requests the Authorization Code Flow |
| `client_id` | Client identifier registered at the AS |
| `redirect_uri` | Callback address strictly validated by the AS |
| `scope` | Permissions requested by the client; AS may grant fewer per policy |
| `state` | Binds callback to pending request, helping prevent CSRF and response injection |
| `code_challenge` | Value derived from the one-time secret `code_verifier` |
| `code_challenge_method=S256` | Instructs the AS to use SHA-256 hashing per PKCE |

`state`, `code_verifier`, and `nonce` (if using OIDC) must be generated with strong randomness, bound to the transaction/client, verified strictly on callback, and never reused indefinitely. Never put a literal like `opaque-random-state` into a real system.

**OAuth vs. OIDC note:** If this is a login request via OIDC, it typically includes `scope=openid` and validates an **ID token** along with `nonce`/issuer per OIDC. A plain OAuth access token is neither proof of login nor an ID token for the client.

### 4.3. What Do Code and PKCE Protect?

An **authorization code** is a short-lived credential for the client to exchange for tokens; the code must be time-limited, bound to the client and redirect URI, and single-use. If an attacker intercepts the code in the callback, PKCE makes exchanging the code harder because the attacker lacks the `code_verifier` generated by the client holding the legitimate transaction.

Calculation for PKCE `S256`:

```text
code_verifier: high-entropy random string per authorization request
digest: SHA-256(ASCII(code_verifier))
code_challenge: BASE64URL(digest) without padding
```

Never put `code_verifier` in the authorization request (send only `code_challenge`), never reuse a static secret across multiple login transactions, and never treat PKCE as replacing other checks such as redirect URI, mix-up/issuer, and transaction binding.

### 4.4. Token Request — Only the Client Exchanges the Code

Code exchange example (conceptual; do not use fake values against a real provider):

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=ONE_TIME_AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&
client_id=report-dashboard&
code_verifier=ORIGINAL_HIGH_ENTROPY_VERIFIER
```

Confidential clients also typically authenticate themselves to the AS, such as via `client_secret_basic` or private-key JWT per AS policy. A public client **cannot** turn itself into a confidential one by attaching a client secret embedded in frontend code.

Illustrative result:

```json
{
  "access_token": "ACCESS_TOKEN_FROM_AS",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "profile.read",
  "refresh_token": "REFRESH_TOKEN_IF_ISSUED"
}
```

Not every grant issues a refresh token. Token responses and formats depend on the provider. **Never log tokens**, and never put real tokens into READMEs, bug reports, or query strings.

### 4.5. Client Calling the Resource Server

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_FROM_AS
```

At the RS: valid token lacking profile-read scope → **403** commonly accompanied by Bearer error `insufficient_scope`; missing or invalid/expired token → **401** typically with `WWW-Authenticate`. HTTP error handlers can be customized, so tests must verify against contracts without leaking data or inferring solely from status codes.

## 5. Client Credentials: Flow Without an Interactive User

OAuth 2.0 also serves **backend-to-backend** communication. For example, a batch service needs to read internal metrics granted to the application itself.

```mermaid
sequenceDiagram
    participant C as Backend Client
    participant AS as Authorization Server
    participant RS as Metrics Resource Server
    C->>AS: POST /token, grant_type=client_credentials + client authentication
    AS->>AS: Authenticates client and checks client permissions
    AS-->>C: Access token scoped to metrics.read
    C->>RS: GET /metrics with Bearer token
    RS->>RS: Checks issuer, audience, scope, and policy
    RS-->>C: Authorized metrics
```

**There is no user resource owner participating in a login/consent step** in this request. The grant relies on the permissions of the client itself registered at the AS. The resource server **must not infer that Alice is logged in** merely because the token is valid. In JWT access token profiles, the `sub` claim can represent the client rather than an end user. If a system accepts both user tokens and client tokens, it must distinguish identity type/scope/audience/actor so a client cannot impersonate a user.

Illustrative request from a confidential client:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=metrics.read
```

Base64 in HTTP Basic **is not secret encryption**; HTTPS and secure secret/key management are required. For stronger client authentication, mTLS or private-key JWT may be used if supported by the AS.

Do not use **Resource Owner Password Credentials** for new integrations: RFC 9700 explicitly states this grant must not be used because it forces clients to handle the resource owner's password and expands the attack surface. Also do not choose the implicit flow for new designs when Authorization Code + PKCE meets requirements.

## 6. Which Token Goes to Which Component?

### 6.1. Access Token

An **access token** is the credential the client sends to the RS to access resources. Its format can be:

- **JWT (self-contained):** RS verifies signature, claims, and rules; does not necessarily call the AS on every request. Immediate revocation requires additional state/denylist/version/introspection by design.
- **Opaque token:** The token itself provides no claims to the client; RS typically introspects with the AS or an appropriate verification layer to learn active status and authorities.

There is no rule that **every OAuth 2.0 access token is a JWT**. A bearer token is a credential: anyone holding it can try to use it within its valid scope and lifetime. Always protect it with HTTPS, and never record it in URLs, logs, or analytics.

### 6.2. Refresh Token

A refresh token (if issued) lets the client obtain a new access token without having the resource owner repeat every interactive step. It is **sent to the AS token endpoint**, never sent as a Bearer credential to read APIs at the RS. AS policy may enforce **refresh token rotation**, sender-constraining, and revocation upon replay detection or logout.

**Do not confuse:** revoking a refresh token stops the client from getting new tokens, yet an existing unexpired JWT access token may still be accepted by the RS if no additional revocation/status check exists.

### 6.3. Authorization Code

An authorization code is a short-lived, single-use credential to complete the token exchange; it must **never** be used as a Bearer token to call the RS.

### 6.4. ID Token — Belongs to OpenID Connect, Not Core OAuth 2.0

An ID token is typically a JWT issued by an OIDC provider to the **client** containing authentication event info, subject, and client audience. It is **not synonymous** with an access token and is usually **not an appropriate credential for calling APIs**. The RS must accept and validate access tokens intended for the RS.

Simplified overview:

| Type | Who Issues | Who Receives/Verifies | Purpose |
| --- | --- | --- | --- |
| Authorization code | AS | AS token endpoint via client | One-time token exchange |
| Access token | AS | Resource server | Call protected APIs |
| Refresh token | AS | AS token endpoint | Request new access tokens |
| OIDC ID token | OIDC Provider | OAuth/OIDC client | Attest login result to the client |

### 6.5. Scope Does Not Replace Object-Level Authorization

Suppose an access token has `scope=invoice.read`. That **does not** prove the user may read **every invoice**. Invoice APIs must check owner, tenant, ACL, transaction status, and specific business rules.

```java
// Service-level check sample, not a standalone program:
Mono<Invoice> loadInvoice(String invoiceId, String accountId) {
    return repository.findByIdAndAccountId(invoiceId, accountId)
        .switchIfEmpty(Mono.error(new NotFoundException()));
}
```

This is **illustrative code** for a reactive repository with undefined interfaces/domain; with Spring MVC/JPA, a synchronous repository can be used. The core point is **scope + object-level policy**; never trust a user-supplied `accountId` without tying it to a verified principal/claim.

## 7. JWT: Signature Verification Is Necessary but Insufficient

When an RS accepts JWT access tokens, distinguish:

1. **Decode**: reading a Base64URL payload does not prove the token is trustworthy.
2. **Verify signature**: confirms the signature with an allowed key/algorithm, preventing tampered contents.
3. **Validate claims**: checks `iss`, `aud`, `exp`, `nbf` (if present), profile, and matching token type.
4. **Authorize action**: checks scopes/authorities, tenant, roles, and resource-level permissions.

**Illustrative** claims sample, not a signed token:

```json
{
  "iss": "https://login.example.test",
  "sub": "alice-user-id",
  "aud": ["profile-api"],
  "scope": "profile.read",
  "iat": 1760000000,
  "exp": 1760000900
}
```

The Profile API RS must reject a token meant only for `payments-api` even if its signature is valid and its scope looks reasonable. Never use a client-targeted ID token as an API access token. Watch out for **algorithm confusion**, select keys from trusted issuers, validate key rotation, and never let a token dictate an arbitrary key-fetching URL.

Some providers pass authorities via claims other than `scope` or `scp`; configure converters to match the exact contract, rather than assuming all roles always reside in a `roles` claim.

## 8. Where Does Spring Security Represent the Four Roles?

Spring Security is a toolkit; it does not turn one project into all four roles via a single annotation.

| OAuth 2.0 Role | In a Spring Application |
| --- | --- |
| Resource owner | User or entity controlling permissions; not a required Java bean |
| OAuth2 client | `spring-boot-starter-oauth2-client`, `oauth2Login()`, `oauth2Client()`, `OAuth2AuthorizedClientManager` |
| Authorization server | **Spring Authorization Server** or an independent IdP product/service; not `oauth2ResourceServer()` |
| Resource server | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer().jwt(...)` or `opaqueToken(...)` |

### 8.1. OAuth2 Client / OAuth2 Login

If an application needs **login via an OIDC provider**, configure client registration and `oauth2Login`. If the application needs to obtain tokens to call external APIs, `oauth2Client`/authorized client management handles those responsibilities. Both use cases can coexist, yet are **not synonymous**.

```java
// Illustrative SecurityFilterChain bean of an OAuth2 Client with registered IdP:
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/").permitAll()
        .anyRequest().authenticated())
    .oauth2Login(org.springframework.security.config.Customizer.withDefaults())
    .oauth2Client(org.springframework.security.config.Customizer.withDefaults());
```

This snippet is **not a standalone runnable file**: it requires an OAuth2 Client project, a `ClientRegistration` with exact issuer/client-id/redirect URI, secret/PKCE configuration, and matching dependencies. Do not drop it into the Section 9 resource server demo and assume you have built an AS.

Spring Security supports callback templates such as `/login/oauth2/code/{registrationId}` for OAuth2 Login in common setups. The redirect URI must match the value registered at the AS. Behind a reverse proxy, strictly control forwarded headers from trusted proxies and enforce HTTPS to avoid redirects to arbitrary hosts.

### 8.2. Authorization Server

To operate your own token-issuing server, use **Spring Authorization Server** or a supported AS/IdP. It must manage registered clients, grants, user authentication/consent, token signing keys, authorization persistence, token issuance/revocation, and endpoints.

```text
spring-boot-starter-oauth2-client
    -> App REQUESTS grants/tokens to call APIs

spring-boot-starter-oauth2-resource-server
    -> API RECEIVES Bearer access tokens and validates them

Spring Authorization Server
    -> System ISSUES tokens/grants
```

A Resource Server **does not automatically issue access tokens** merely by having a `JwtDecoder` bean. An OAuth Client **does not automatically become a resource server** merely by having a `ClientRegistration`. Separating roles clearly makes security configuration and deployment easier to audit.

### 8.3. Resource Server Using JWT

A common configuration for **JWTs issued by a real AS**:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.test
```

```java
// Inside SecurityFilterChain of a Resource Server backed by a real IdP/AS:
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin.read")
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(org.springframework.security.config.Customizer.withDefaults()));
```

**Integration illustration code**—it does not run on its own without an issuer, metadata/JWKS, real tokens, and matching policies. Spring Security typically creates a `JwtDecoder` from issuer/metadata to validate JWTs; production still needs **audience** checks, custom claims, scope mapping, and action/object-level authorization tailored to your API.

### 8.4. Resource Server Using Opaque Tokens

With opaque tokens and an AS introspection endpoint:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://login.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=profile-api-introspector
# Use a secret manager / environment variable; never hardcode secrets in the repo.
```

The Resource Server can use `OpaqueTokenIntrospector`; the provider returns `active` status along with scope/principal info. Introspection client secrets and TLS must be configured per provider docs; the property snippet above omits full credentials for production.

## 9. Runnable Example: A Resource Server Accepting Bearer Tokens and Checking Scopes

This lesson focuses on clarifying **who receives the token** and **who checks permissions**. So the example can run **without registering a real OAuth provider**, we simulate **introspection results** using an `OpaqueTokenIntrospector` bean *for local demo only*. It accepts two test strings and turns them into principal + scope; all other strings are rejected.

**STRICT BOUNDARY:** This demo **does not implement an Authorization Server**, **does not issue valid OAuth tokens**, **does not execute Authorization Code + PKCE**, and **must never be deployed as production security configuration**. Its sole goal is to verify the Resource Server layer and token-based authorization in Spring Security. For production, replace the fake introspector with real AS introspection or a trusted JWT decoder/AS.

### 9.1. Project Structure

```text
oauth2-resource-roles-demo/
├── pom.xml
└── src/
    ├── main/java/demo/oauth/
    │   ├── OAuth2RolesApplication.java
    │   ├── SecurityConfig.java
    │   └── ProfileController.java
    └── test/java/demo/oauth/
        └── ResourceServerTest.java
```

Requires **JDK 17+**, Maven 3.9+, and port 8080 free if running the server. Spring Boot 3.5.0 is pinned for reproducibility; real applications need currently supported patch/minor versions.

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oauth2-resource-roles-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 9.3. Startup

`src/main/java/demo/oauth/OAuth2RolesApplication.java`:

```java
package demo.oauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OAuth2RolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuth2RolesApplication.class, args);
    }
}
```

### 9.4. Resource Server SecurityFilterChain and Demo Introspector

`src/main/java/demo/oauth/SecurityConfig.java`:

```java
package demo.oauth;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }

    /**
     * Local demo only: simulates AS introspection results.
     * DO NOT use these hardcoded string tokens in production.
     */
    @Bean
    OpaqueTokenIntrospector demoOpaqueTokenIntrospector() {
        return token -> {
            if ("demo-alice".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                    "alice",
                    Map.of("sub", "alice", "scope", "profile.read"),
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_profile.read"))
                );
            }
            if ("demo-bob".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                    "bob",
                    Map.of("sub", "bob", "scope", "tasks.read"),
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_tasks.read"))
                );
            }
            throw new BadOpaqueTokenException("Token not active");
        };
    }
}
```

Explanation:

1. `STATELESS`: does not rely on login sessions to authenticate API requests; a Bearer token accompanies every request.
2. `oauth2ResourceServer(...opaqueToken(...))`: enables the Resource Server mechanism for Bearer opaque tokens.
3. `OpaqueTokenIntrospector` is where the Resource Server receives validated token info. In the demo, **only** two test tokens are treated as active; there is no connection to a real Authorization Server.
4. Case `demo-alice` is built with authority `SCOPE_profile.read`; `demo-bob` has only `SCOPE_tasks.read`.
5. `hasAuthority("SCOPE_profile.read")` requires the matching scope; even though Bob's token is recognized, Bob still cannot access `/api/profile`.
6. `anyRequest().denyAll()` rejects unlisted endpoints even with a valid token.
7. The demo only has read-only GETs and **does not disable CSRF**. With cookie-based browser flows or POST/PUT/PATCH/DELETE, analyze CSRF separately; `STATELESS` does not prove an app is immune to CSRF if browsers still automatically send credentials.

**Why is the demo introspector a trust boundary that must be clearly flagged?** In production, the Authorization Server itself must issue tokens and the RS must verify status via real introspection or a standard decoder. A hardcoded token lookup table in source code is *not* an acceptable token-issuance model and can expose the API if deployed outside local testing.

### 9.5. Controller Only Receives Verified Principal

`src/main/java/demo/oauth/ProfileController.java`:

```java
package demo.oauth;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("subject", principal.getName());
    }
}
```

The controller **does not manually read the `Authorization` header** and does not trust client-supplied usernames. Spring Security has already turned a valid Bearer token into an `Authentication` and principal; requests missing the required authority are blocked before reaching the controller. Real systems need **object-level policies** if returning data across multiple users/tenants.

### 9.6. Integration Tests with MockMvc

`src/test/java/demo/oauth/ResourceServerTest.java`:

```java
package demo.oauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteNeedsNoToken() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void privateRouteWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBearerTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void recognizedTokenWithoutScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-bob"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedTokenGetsOnlyItsOwnProfileView() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-alice"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void unapprovedPathIsForbiddenEvenWithToken() throws Exception {
        mvc.perform(get("/api/internal/secrets")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-alice"))
            .andExpect(status().isForbidden());
    }
}
```

**These are integration tests for the demo Resource Server**, not tests executing an Authorization Code Flow. Six tests clearly isolate: public route, missing token, inactive token, token with wrong scope, token with sufficient scope, and disallowed route. Spring Security Test provides the testing infrastructure; requests in the tests deliberately send `Authorization: Bearer ...` to exercise the real filter rather than pre-mocking `Authentication`.

### 9.7. Running the Application and Testing with curl

```bash
mvn test
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/profile
curl -i -H 'Authorization: Bearer invalid' \
  http://localhost:8080/api/profile
curl -i -H 'Authorization: Bearer demo-bob' \
  http://localhost:8080/api/profile
curl -i -H 'Authorization: Bearer demo-alice' \
  http://localhost:8080/api/profile
```

The **expected** HTTP statuses in order are **200, 401, 401, 403, 200**; the last command returns JSON containing `"subject":"alice"`. These are **expectations derived from the demo configuration and code**, not outputs from Maven/curl executed while authoring this lesson.

**Never use demo tokens or a fake introspector in production.** When moving to a real AS, replace with secured introspection client credentials or a standard JWT decoder, add audience/issuer validation, rate limiting, object-level authorization, and test real tokens issued by the AS.

## 10. With a Real Authorization Server: What Must Change?

In a real product:

1. **Client registration:** The AS needs the client ID, public/confidential type, redirect URIs, grant types, scopes, and proper client-authentication methods.
2. **Authorization flow design:** User-facing clients use Authorization Code + PKCE; machine-to-machine services use Client Credentials where appropriate.
3. **Access token contract definition:** Issuer, audience, scope, subject/actor, TTL, resource indicators, refresh strategy, and version.
4. **Connecting RS to AS:** JWT decoder/metadata/JWKS or introspection endpoint, TLS, caching, and timeouts.
5. **Mapping authorities:** Translate claims/scopes accurately to authorities (e.g., `SCOPE_profile.read`), adding owner/tenant checks.
6. **Token storage:** Clients avoid exposing tokens via URLs, unprotected browser storage, logs, or referrers; use BFF/secure cookies if appropriate for the architecture.
7. **Revocation:** Client logout, refresh token rotation, AS revocation, and RS validation SLAs must reflect one consistent policy.
8. **Testing in real environments:** Login/consent, callback, state/PKCE, refresh, expiry, revocation, key rotation, audience mismatch, invalid scope, and unauthorized objects.

Do not try to mint JWTs with a self-signing Java method inside the Resource Server application and claim you have an "OAuth2 Authorization Server": OAuth encompasses grant processing, client registration, token issuance, redirect rules, consent, key management, and security requirements far beyond creating a JWT string.

## 11. Common Role-Confusion Mistakes

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| "Resource owner is the resource server" | One grants permission, one serves data | Alice grants permission; Profile API stores data |
| "Client means JS frontend" | Clients can be backend, mobile, desktop, or SPA | Identify client boundary and ability to hold secrets |
| "Authorization server and resource server must be two physical machines" | The RFC defines logical roles | Can share a server, yet responsibilities differ |
| "OAuth2 is a standardized ID-token login protocol" | OAuth is primarily about authorization | Use OIDC when identity authentication with ID tokens is needed |
| "Having an access token lets you call any endpoint" | Tokens have scopes/audiences/lifetimes | RS checks token and action/resource authorization |
| "Successful JWT decode means valid" | Readable Base64URL does not prove signature | Verify signature, issuer, audience, lifetime, scope |
| "Use ID tokens as Bearer access tokens for APIs" | Audience and purpose differ | Resource server accepts access tokens meant for that API |
| "Embedding a client secret in an SPA is secure" | Users can inspect frontend code | Public client + Authorization Code + PKCE |
| "PKCE replaces redirect URI/state/issuer checks" | PKCE mitigates only specific threats | Enforce full transaction and redirect constraints |
| "Client Credentials also represents Alice" | No user login/consent occurs in that grant | Token represents client permissions, not an end user |
| "`scope=invoice.read` allows viewing every invoice" | Scope can be broad | RS checks tenant/owner/ACL per invoice |
| "Client logout revokes JWTs immediately at every RS" | Stateless unexpired JWTs may remain accepted | Choose TTL/denylist/introspection/version per SLA |
| "CORS replaces authorization" | Non-browser callers ignore CORS | OAuth bearer validation and API authorization |
| "Every access token must be a JWT" | OAuth mandates no such format | Both JWT and opaque tokens can be used |
| "Need password grant to build a custom login screen" | Client handles user passwords, violating BCP | Use Authorization Code + PKCE / SSO properly |

## 12. Security Checklist by Role

### 12.1. Resource Owner

- [ ] Understands which application is requesting permissions and which resource groups are shared.
- [ ] Does not enter AS passwords into forged third-party apps; prefers redirecting to a trusted AS.
- [ ] Can view/revoke granted permissions per AS and product policy.
- [ ] For high-risk operations, uses MFA/fresh authentication when required.

### 12.2. Client

- [ ] Registers accurate `client_id`, redirect URIs, and client type.
- [ ] Uses Authorization Code + PKCE `S256` for user authorization flows; avoids implicit/password grants for new designs.
- [ ] Validates `state` and transaction binding, plus OIDC `nonce` when applicable.
- [ ] For confidential clients, protects secrets/keys, rotates them, and uses HTTPS exclusively.
- [ ] Never stores access/refresh tokens in URLs, logs, or unprotected frontend locations.
- [ ] Safely handles expiry, refresh token rotation/replay, logout, and AS errors.

### 12.3. Authorization Server

- [ ] Validates client registration, redirect URIs, grant types, and authentication appropriately.
- [ ] Authenticates the resource owner, records consent when needed, and grants minimal scopes.
- [ ] Issues short-lived, single-use codes; verifies PKCE and client binding.
- [ ] Signs tokens and manages keys/`jwks` securely when using JWTs.
- [ ] Exposes metadata, token, and revocation/introspection endpoints as designed.
- [ ] Defines explicit issuer/audience, defending against mix-up and token substitution.
- [ ] Implements auditing, rate limiting, and abuse monitoring without logging raw tokens.

### 12.4. Resource Server

- [ ] Accepts tokens only from configured issuers/ASs.
- [ ] Verifies signature or introspection, expiration, audience, and appropriate token type.
- [ ] Maps scopes/authorities accurately, denying out-of-policy methods/paths.
- [ ] Enforces object-level ownership/tenant/ACL at business and query layers.
- [ ] Never grants permissions based solely on caller-supplied `client_id` or unverified JWT contents.
- [ ] Tests 401 for missing/invalid tokens, 403 for missing scope, and 2xx only when authorized.
- [ ] Defines handling for revoked tokens, AS outages, stale caches, and key rotation.
- [ ] Never leaks sensitive claims or Bearer tokens in logs/responses.

## 13. Self-Check Questions

**1. In OAuth2, who are the Resource Owner, Client, Authorization Server, and Resource Server?**  
The resource owner can grant permissions on protected resources; the client requests access; the AS issues tokens after a valid grant; the RS serves resources and validates access tokens.

**2. Alice enters her password into Report Dashboard so the app can call Profile API. Is this the preferred flow?**  
No. The preferred model redirects to the AS, letting Alice authenticate/consent at the AS and giving the client a code/token, avoiding having the client directly receive the resource owner's password.

**3. Can the Authorization Server and Resource Server share the same deployment?**  
Yes. They are two distinct logical roles; you must still keep token/grant endpoints separate from protected resource APIs.

**4. Can Client Credentials replace Authorization Code when acting on behalf of Alice?**  
Not by default. Client Credentials grants permissions to the client itself and does not represent Alice authorizing or being logged in.

**5. After receiving an authorization code, can the client use that code directly to call Profile API?**  
No. The client exchanges the code at the token endpoint for an access token; the resource server accepts the access token.

**6. Why use PKCE S256?**  
To bind the token exchange to the client that initiated the authorization request, reducing code interception/injection risk. PKCE does not waive redirect URI, state/mix-up, and other binding checks.

**7. Will a JWT with a valid signature yet `aud=payments-api` be accepted by Profile API?**  
No, if the API requires tokens intended for itself. The resource server must check audience and action scope.

**8. If an access token has scope `invoice.read`, can it read another user's invoice?**  
Not automatically. The resource server must check ownership/tenant/ACL for the specific invoice.

**9. Do OAuth access tokens and OIDC ID tokens serve the same role?**  
No. Access tokens target protected resources/APIs; ID tokens let clients verify login results in OIDC.

**10. Does an unexpired JWT automatically become invalid when the client deletes it locally?**  
Not necessarily. If the RS validates JWTs statelessly without revocation checks, a copy of the token can still be accepted until it expires.

**11. In the runnable example, is `demo-alice` a valid OAuth access token from a real Authorization Server?**  
No. It is a test string treated as active by the simulated introspector bean, solely for practicing Resource Server authorization.

**12. If Bob's token is confirmed by the introspector yet lacks `SCOPE_profile.read`, what is the API expected to return?**  
Typically **403 Forbidden** due to missing authority, distinct from **401 Unauthorized** for invalid or missing tokens.

## 14. References

- [RFC 6749 – The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), especially sections **1.1 Roles**, **1.2 Protocol Flow**, authorization code / client credentials.
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, preventing token/authorization code injection, client identity, and avoiding the password grant.
- [RFC 7636 – Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `S256`, `code_challenge`.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer header and error handling.
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` status and introspection.
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): how clients request token revocation.
- [Spring Security – OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClient` and client registration.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): login via AS/OIDC provider and callbacks.
- [Spring Security – OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): JWT, opaque tokens, Bearer validation, and authorities.
- [Spring Authorization Server](https://docs.spring.io/spring-authorization-server/reference/): token-issuing role, endpoints, and server configuration.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html): `openid` scope, ID tokens, and authentication.
