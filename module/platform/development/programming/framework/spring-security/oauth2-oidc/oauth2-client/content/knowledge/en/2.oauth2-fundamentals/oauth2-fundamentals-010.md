# 2.10. Bearer Token, Opaque Token, and JWT Access Token

## 1. Context: Where Does an Access Token Travel?

In OAuth 2.0, an **access token** is a credential issued by an **Authorization Server** to an **OAuth 2.0 Client** so the client can access protected resources at a **Resource Server** within a defined authorization scope. The Client may be a Spring Boot web application that logged a user in with OIDC, a mobile app, or a service calling another service.

Suppose a system has three components:

- **Company IdP / Authorization Server**: authenticates employees, handles authorization, and issues access tokens.
- **Employee Portal**: a Spring Boot application acting as an **OAuth 2.0 Client**; after an employee logs in, Portal needs to call Orders API for that employee.
- **Orders API**: a Spring Security application acting as a **Resource Server**; returns orders only when the access token is valid and the user has access rights.

In the example, Portal receives a token with the **orders.read** permission, then sends a request:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

There are two separate questions here:

1. What does **Bearer** mean, and why does the token string appear in the **Authorization** header?
2. Is the access token string itself formatted as **opaque** or **JWT**, and how does Orders API verify it?

That is why we must separate **how the token is used** from **the token's format**.

## 2. Distinguishing Three Commonly Confused Concepts

| Concept | Which Layer? | Meaning | Example |
|---|---|---|---|
| **Bearer token** | Credential presentation mechanism | Whoever possesses the token can send it to exercise the granted permissions; the token does not itself prove the sender is the legitimate owner | **Authorization: Bearer ...** header |
| **Opaque access token** | Access token representation | Token value has no public structure that the Resource Server is permitted to interpret; the Resource Server typically asks the Authorization Server whether the token is active and what permissions it carries | **f8H2tR7x...** |
| **JWT access token** | Access token representation | Access token encoded as a JSON Web Token, typically as a signed **JWS**; the Resource Server can verify the signature and claims locally | **header.payload.signature** |

**Bearer is not the opposite of opaque or JWT.** An access token used via the Bearer mechanism can be an **opaque token** or a **JWT**. Conversely, JWT is a **format** usable for multiple kinds of tokens, not automatically an OAuth access token.

Classification tree:

~~~text
OAuth 2.0 Access Token
    |
    +-- How it is presented to the API
    |       +-- Bearer (Authorization: Bearer ...)
    |       +-- Other mechanisms if supported by the system, e.g., sender-constrained tokens
    |
    +-- Format decided by the Authorization Server
            +-- Opaque / reference token
            +-- JWT access token
            +-- Other representations per system contract
~~~

Concrete example: Portal can send **Authorization: Bearer f8H2tR7x...** if the access token is opaque. Portal can also send **Authorization: Bearer eyJ...** if it is a JWT. The outer HTTP syntax is identical, while the verification method at Orders API differs.

> Within the scope of this lesson, **Bearer** is the most common mechanism. **Sender-constrained token** mechanisms such as mTLS or DPoP have additional binding properties and cannot be equated with ordinary Bearer tokens.

## 3. Bearer Token: Whoever Holds the Token Can Present It

### 3.1. Meaning of Bearer

The word **bearer** refers to the party carrying or holding the token. When a Resource Server receives a valid bearer access token, it can accept the request within the scope of permissions the token represents. A bearer token itself **does not require the sender to prove possession of a separate cryptographic key**. Therefore, anyone who steals a bearer token risks replaying it until it expires, is invalidated, or is blocked by another defense.

A bearer token is like a **transferable admission ticket**, yet the ticket still has conditions: expiration, allowed areas, target audience, scope of permissions, and Resource Server enforcement policies. Never interpret "has a token" as "allowed to do everything."

### 3.2. Where the Token Is Sent in HTTP

The standard and common way is the **Authorization header** per OAuth 2.0 Bearer Token Usage:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Characteristics:

- **Bearer** is the authentication scheme name, followed by a space and the access token value.
- HTTPS/TLS must be used in real environments to protect the token in transit.
- Do not arbitrarily put tokens in query strings like **?access_token=...**: URLs commonly appear in logs, browser history, reverse proxies, analytics, and shared links.
- Do not send a bearer token to an API that is not the intended recipient (**audience**).
- Do not return tokens to the frontend if the application model only needs the browser to send a session cookie to a backend, such as the **Backend for Frontend (BFF)** pattern.

A common mistake is confusing the **Authorization: Bearer ...** header with a login cookie. In a web app using OIDC login:

| Communication Channel | Typically Sent Info | Verifying Party |
|---|---|---|
| Browser → Portal | Portal's session cookie | Portal validates session |
| Portal → Orders API | OAuth access token in Bearer header | Orders API validates token |
| Portal → Authorization Server | Authorization code or refresh token in a valid request | Authorization Server processes grant/token exchange |

Where tokens are kept depends on architecture. With MVC/BFF applications, the access token can reside inside **OAuth2AuthorizedClient** server-side; browser JavaScript does not need to read it.

### 3.3. What Does Bearer Not Guarantee on Its Own?

A bearer token **does not by itself provide**:

- Replay protection if stolen.
- Sender identity verification at the device or private-key level.
- Immediate revocation across all token types.
- Access to every endpoint or every data record.

Accordingly, the API must verify **token validity**, **intended target API**, **scope/authority**, and then enforce **business permissions** on each resource object.

## 4. How Access Tokens Are Issued and Used in the OAuth 2.0 Flow

With a Portal application logging users in via the **OIDC Authorization Code Flow**, a typical flow is:

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant C as Portal (OAuth2 Client)
    participant AS as Authorization Server / OIDC Provider
    participant RS as Orders API (Resource Server)

    U->>B: Opens orders page
    B->>C: Accesses Portal
    C-->>B: Redirects to authorization endpoint
    B->>AS: Authorization request (openid, orders.read, state, ...)
    AS->>U: Logs in and grants consent if needed
    AS-->>B: Redirects back to callback with authorization code
    B->>C: Callback with code and state
    C->>AS: Exchanges code at token endpoint
    AS-->>C: ID token + access token (+ refresh token if issued)
    C->>C: Creates login session, stores OAuth2AuthorizedClient
    B->>C: GET /bff/orders with session cookie
    C->>RS: GET /api/orders, Authorization: Bearer access_token
    alt Access token is JWT
        RS->>RS: Validates signature, issuer, audience, expiration
    else Access token is opaque
        RS->>AS: Calls introspection endpoint
        AS-->>RS: Active status and token attributes
    end
    RS->>RS: Checks orders.read and data permissions
    RS-->>C: Authorized result
    C-->>B: Orders page or data
~~~

Both token formats can travel through the same OAuth 2.0 flow. **The OAuth2 Client normally does not need to decode the access token to call an API**: it simply retrieves the issued token value and presents it to the Resource Server. Rules for processing the token format belong to the Resource Server and Authorization Server.

## 5. What Is an Opaque Access Token?

### 5.1. "Opaque" Means No Structure for the Recipient to Interpret Directly

An opaque token is a value from whose string form the client—and typically the Resource Server—**cannot directly derive a standardized set of claims**. For example:

~~~text
q9Lz1D8vT4K7Wb3X0mR5yF2a...
~~~

The Authorization Server may manage the token as a **reference** pointing to a server-side authorization record. However, **opaque** is a property of the token-consumption interface; it is not a promise that the token must be a random string, have a fixed length, or be stored in a specific database structure.

Looking at the token string, Portal should not try to infer the user, scopes, expiry, or target API itself. To validate an opaque token, the Resource Server commonly uses **OAuth 2.0 Token Introspection** (RFC 7662) provided by the Authorization Server.

### 5.2. The Introspection Mechanism

When Orders API receives an opaque token:

1. The API extracts the token from the Bearer header.
2. The API calls the Authorization Server's **introspection endpoint** over a protected channel; normally the API must authenticate using the Resource Server's own registered credentials.
3. The Authorization Server checks the token, expiration, revocation status, and applicable policies.
4. The Authorization Server returns **active: true/false** along with attributes the API is permitted to see.
5. The API enforces scope, audience, and per-order permissions before returning data.

**Illustrative** introspection response example; not every IdP returns all of the following fields:

~~~json
{
  "active": true,
  "iss": "https://id.example.test/realms/company",
  "client_id": "portal-web",
  "sub": "employee-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "token_type": "Bearer",
  "exp": 1893456000
}
~~~

If the token does not exist, has expired, or is no longer valid, the response may simply be:

~~~json
{
  "active": false
}
~~~

**active: true is only one step of the access decision.** The API must still verify the right audience, sufficient scopes, and permissions to access the specific resource. The attributes returned by an introspection endpoint depend on the Authorization Server, policies, and registration protocol; never assume **sub**, **aud**, or **scope** are always present in the same data type.

### 5.3. Advantages and Limitations

Opaque tokens fit well when the Authorization Server wants centralized control over token state. Because the API receives fresh information from the latest introspection, revocation can be reflected promptly **if** every request introspects and the Authorization Server updates state accordingly.

In return:

- The API depends on the introspection endpoint over the network, requiring handling of latency, timeouts, connection failures, and rate limits.
- If introspection results are cached, revoked permissions may still be accepted during the cache window; you must balance performance against freshness of access decisions.
- The introspection credential is a privileged secret that must be protected; never use a browser client secret or expose this credential to the frontend.
- Opaque tokens are not immune to bearer token theft. If an attacker obtains an active token, replay risk remains.

## 6. What Is a JWT Access Token?

**JSON Web Token (JWT)** is a standard format for representing claims. When the Authorization Server issues a **JWT access token**, the Resource Server can validate the token using its digital signature and required claims, usually without calling introspection on every request.

A JWT signed in **JWS Compact Serialization** typically has three dot-separated parts:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Conceptual example:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0.eyJzdWIiOiJlbXBsb3llZS00MiJ9.<illustrative-signature>
~~~

This is only a structural example, **not a token with a valid signature**. JWTs can also exist as encrypted JWEs; in many systems, the most commonly used JWT access token is a signed JWS.

### 6.1. Header, Payload, Signature

**Header** describes how to process the signature, for example:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "signing-key-2026"
}
~~~

- **typ** can help indicate this is an access token per JWT Profile for OAuth 2.0 Access Tokens (RFC 9068). Many providers use their own formats and do not necessarily set this value; the Resource Server must follow the actual token contract.
- **alg** indicates the signing algorithm, e.g., RS256. The verifier must restrict trusted algorithms rather than blindly accepting whatever value the token declares.
- **kid** is a hint for selecting a key from the public key set. It **does not itself verify** which key is trusted; the key source must be pre-configured/trusted.

**Payload** contains claims. An example JWT access token:

~~~json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "employee-42",
  "aud": ["orders-api"],
  "client_id": "portal-web",
  "scope": "orders.read",
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

These values are illustrative only; real tokens must have lifetimes matching their issuance time.

| Claim | Purpose | What to Watch |
|---|---|---|
| **iss** | Who issued the token? | Must match the issuer trusted by the API |
| **sub** | Subject the token refers to | Can be a user or client, depending on grant type and provider |
| **aud** | Which resource/API is the token for? | Orders API only accepts matching audiences |
| **exp** | Expiration time (Unix epoch seconds) | Expired tokens must be rejected |
| **nbf** (if present) | Not valid before this time | Must be checked when the claim exists |
| **iat** | Issued-at time | Useful for token-age policies |
| **scope** or **scp** | Granted access permissions | Representation depends on the Authorization Server |
| **client_id**, **azp**, **jti** (if present) | Receiving client, authorized party, or token ID | Rely on them only when clearly defined in the token contract |

**Signature** verifies that the token has not been tampered with and was signed by a key belonging to a trusted issuer. With asymmetric signing, the Authorization Server holds the **private key**, while the Resource Server fetches the **public key** from a trusted **JWKS** source to verify. A valid signature does not mean the token is permitted to call every API: issuer, audience, expiration, and permissions still must be checked.

### 6.2. A Signed JWT Does Not Mean an Encrypted JWT

With ordinary JWS-format JWTs, the header and payload are merely **Base64URL-encoded**, not encrypted for confidentiality. Anyone holding the token string can read the claims by Base64URL-decoding without needing the signing key.

Therefore:

- **Do not put passwords, secrets, or unnecessary personal data** inside a JWT payload.
- **Do not treat decoding the payload as validation**. A forged string can still decode into plausible-looking JSON.
- **Do not read scopes or roles while skipping signature verification**.
- If token contents truly need confidentiality, use an appropriate design such as **JWE** or limit claims—do not assume "signed" protects confidentiality.

### 6.3. Validating a JWT Access Token Properly

The Resource Server typically needs to verify:

1. **Syntax and signature:** the token is in a supported format, the algorithm is on the trusted allowlist, and the signature is valid against the issuer's key.
2. **Issuer:** **iss** matches the exact Authorization Server configured for the API.
3. **Timestamps:** **exp**, **nbf**, and other time constraints comply with policy; allowed clock skew should be small and intentional.
4. **Audience:** **aud** contains Orders API's identifier, avoiding accepting tokens issued for Portal or another API.
5. **Token type if required by contract:** do not confuse an **ID Token** with an **access token**. With a JWT access token profile, **typ**/claim requirements must be checked per standard and provider.
6. **Scope/authority:** the token has **orders.read** for the order-reading API; missing scope must not proceed.
7. **Data object permissions:** for user An, the API only retrieves orders An is allowed to view, even when the token carries **orders.read**.

Never trust an arbitrary **alg** taken from the token, never fetch keys from an untrusted URL inside the header, and never disable signature verification just to "make it run in dev." Spring Security's Resource Server libraries provide JWT validators; configuration must properly restrict issuer/keys, audience, and application policies.

### 6.4. Operational Characteristics

JWTs are advantageous when an API wants **local verification** without depending on an introspection call on every request. The API may still need access to metadata or JWKS to load/refresh keys on startup and during signing key rotation.

Conversely, an issued JWT typically remains accepted until **exp** when relying solely on local signature/claim checks. Logging out of Portal **does not automatically** revoke all JWT access tokens immediately. If the system needs rapid revocation, consider short-lived access tokens, blocklists/revocation lists, supplemental introspection, key management, and strategies suited to your IdP's capabilities.

## 7. Distinguishing a JWT Access Token from an OIDC ID Token

In **OpenID Connect**, the Authorization Server can return an **ID Token** alongside the access token. Both can take the shape of a JWT, yet **their purposes and intended recipients differ**:

| Property | OIDC ID Token | OAuth 2.0 Access Token |
|---|---|---|
| Purpose | Proves the user authentication event to the **OIDC Client** | Allows the client to access a **Resource Server** |
| Intended recipient | Portal / OIDC Relying Party | Orders API |
| Typical audience | Portal's **client_id** | API/resource identifier per contract with the Authorization Server |
| Contents | Authentication claims, potentially **nonce**, **auth_time**, **acr**, **amr** | Access permissions, issuer, subject, audience, lifetime, and specific claims |
| Where used | Portal validates during OIDC login | Portal sends via Bearer header; API validates |

**Dangerous mistake:** Portal logs in successfully and sends the **ID Token** in the **Authorization: Bearer ...** header when calling Orders API. Because an ID Token is often a valid JWT signed by the same IdP, a loosely configured API might mistakenly accept it. The API must validate access tokens per the proper contract and audience, not accept a token merely because its signature is valid.

Additionally, a **refresh token** is used by the OAuth Client to request new access tokens at the token endpoint per Authorization Server policy. **Never send a refresh token to Orders API**; it typically has a longer lifetime and must be strictly protected.

## 8. How Spring Security OAuth 2.0 Client Handles Access Tokens

### 8.1. `OAuth2AuthorizedClient` Holds Authorization State

In a Spring Boot web application using **spring-boot-starter-oauth2-client**, Spring Security can store an **OAuth2AuthorizedClient** associated with:

- **ClientRegistration**: configuration of the OAuth client, e.g., registration ID **company**.
- **Principal**: the currently logged-in user.
- **OAuth2AccessToken**: token value, token type, issued/expiration timestamps, and scopes stored per the client model.
- **OAuth2RefreshToken** if issued by the Authorization Server and supported by storage.

**OAuth2AccessToken.getTokenValue()** returns the token string for API calls. The Client does not need to parse the JWT payload or introspect the token before sending it. This is a clean separation of responsibilities: **the OAuth Client uses the token**; **the Resource Server validates and authorizes the token**.

### 8.2. Example Configuration for Portal

Example with Spring Boot 3 / Spring Security 6, where Portal is a confidential web client using Authorization Code and OIDC login. The configuration below is illustrative only; replace issuer, client ID, and scopes with values from your actual IdP.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
# Portal's application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
~~~

The client secret must be loaded from a secure configuration source, never placed directly in the repository. **openid** requests OIDC; **orders.read** is an illustrative scope that must be configured on the Authorization Server for the API. The access token format (opaque/JWT) is decided by the Authorization Server, not chosen merely by renaming a property in Portal's configuration.

Basic SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PortalSecurityConfig {
    @Bean
    SecurityFilterChain portalChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Example server-side controller using the current user's token:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class OrdersProxyController {
    private final RestClient ordersApi =
        RestClient.create("https://orders.example.test");

    @GetMapping("/bff/orders")
    String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String token = authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
~~~

In this code, **headers.setBearerAuth(token)** works identically for opaque tokens and JWT access tokens. **@RegisteredOAuth2AuthorizedClient("company")** requests the authorized client bound to the **company** registration and the current principal; never share a fixed bearer token across all users.

In real applications, handle expired tokens, refresh if issued, API 401/403 errors, timeouts, and authorized-client storage across multiple instances. You can use **OAuth2AuthorizedClientManager** and corresponding HTTP client integrations to manage tokens consistently instead of building an unsafe manual refresh mechanism.

## 9. Spring Security Resource Server Validating JWT Access Tokens

Orders API acts as the Resource Server. For JWT access tokens, Spring Security can validate the signature, issuer, and timestamps using Authorization Server metadata. The API must add audience validation and business authorization.

### 9.1. Dependencies and Configuration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
# Orders API application.yml, JWT case
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/company

app:
  security:
    expected-audience: orders-api
~~~

**issuer-uri** is the URI identifying the issuer; the framework can use discovery/JWKS according to the IdP's capabilities. Declaring only the issuer is **not enough** to enforce Orders API's audience. A dedicated validator configuration helps the API reject tokens issued for other services.

### 9.2. FilterChain Checking Scopes

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersJwtSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

In standard configuration, Spring Security converts a **scope** value **orders.read** into the authority **SCOPE_orders.read**. For tokens with **scp**, roles, or custom claim structures, you may need a **JwtAuthenticationConverter** to map accurately—do not assume every IdP uses the same schema.

The **csrf.disable()** call fits this example of a **stateless API that only authenticates via bearer headers and does not use cookies for authentication**. Do not blindly apply this to Portal using session cookies, where CSRF protection must still be considered.

### 9.3. Adding Audience Validation for JWTs

Example of a **JwtDecoder** that validates issuer/timestamps using default validators and checks the **orders-api** audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
        String issuer,
        @Value("${app.security.expected-audience}")
        String expectedAudience
    ) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Unexpected access token audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator));

        return decoder;
    }
}
~~~

Here **audienceValidator** does not replace signature or issuer validation; it adds a check that the token was actually issued for **orders-api**. If the API must also adhere to a JWT access token profile, token type, or IdP-specific claims, those conditions must be checked separately per the published contract.

**A Resource Server verifying identity does not mean permission to read every object.** After the filter layer, the application must still verify whether the order belongs to the right subject/tenant. Subject (**sub**) is only meaningful when the token was issued by a trusted issuer and validated.

## 10. Spring Security Resource Server Validating Opaque Access Tokens

If the Authorization Server issues opaque access tokens, Orders API uses **opaque-token introspection**. The **spring-boot-starter-oauth2-resource-server** dependency remains the same; the Resource Server configuration changes.

### 10.1. Introspection Configuration

~~~yaml
# Orders API application.yml, opaque token case
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

The introspection path is an **example**; the actual URL depends on the IdP. The **orders-api-introspector** credentials allow Orders API to authenticate when introspecting, distinct from the client credentials used for OIDC login in Portal. Never expose the introspection client secret.

### 10.2. FilterChain Using Opaque Tokens

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersOpaqueSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

The two configurations in Section 9 and Section 10 are **two mutually exclusive alternatives for the same Orders API**. Do not register both **SecurityFilterChain** beans with identical request matchers in the same application expecting Spring to auto-select based on token shape.

After successful introspection, Spring Security can map scopes to authorities prefixed with **SCOPE_**. If the IdP returns data or audience policies in a custom format, the application must configure an appropriate **OpaqueTokenIntrospector**/authorization logic to verify that the token was issued for Orders API. Never treat **active: true** as enough to skip audience and business permission checks.

To access identity, opaque-token handling code can use **OAuth2AuthenticatedPrincipal** and attributes returned by introspection. With JWTs, the principal is typically **Jwt**. Therefore, if a controller is tightly coupled to **@AuthenticationPrincipal Jwt**, that controller cannot automatically work with opaque tokens without changing the principal type or authentication mapping.

## 11. Choosing Opaque vs. JWT Access Tokens Based on System Requirements

| Criterion | Opaque Access Token | JWT Access Token |
|---|---|---|
| How does the API learn token info? | Typically via introspection endpoint | Typically via local signature/claim verification |
| Per-request network dependency | Yes, if introspected every time; reducible with caching | Usually no, once verification keys/JWKS are cached |
| Token verification latency | Incurs extra network hop | Usually lower since verified at the API |
| Token/permission revocation | Can be reflected promptly on re-introspection | Usually remains valid until expiry if checked locally only |
| Are claims visible to token holder? | Typically unreadable directly from the string | JWS payload can be decoded; signing does not encrypt |
| Claim flexibility | Authorization Server decides what introspection returns | Claims are baked in at issuance time |
| Notable operational risks | Timeouts, IdP dependency, introspection credentials and caching | Signing key management, JWKS rotation, lifetime and revocation |
| Mandatory security conditions | TLS, **active** check, audience, scope, resource permissions | TLS, signature, issuer, audience, lifetime, scope, resource permissions |

Neither format is **always better** in every case. Some organizations prefer opaque tokens for centralized state control; distributed systems may use JWTs to reduce introspection load and improve latency. The final choice also depends on IdP policies, token lifetime, permission sensitivity, revocation needs, and operational architecture.

Invariants regardless of format:

- Access tokens must only be used with the right **audience** and **scope**.
- Bearer tokens must be kept confidential in transit, storage, and logging.
- Data operation permissions still must be enforced at the Resource Server.
- Clients should not depend on the internal structure of an access token to implement UI behavior.

## 12. Expired, Revoked, or Stolen Access Tokens

### 12.1. Expiration and Refresh

Access tokens typically have a bounded lifetime. Once expired, the Resource Server must reject requests using the old token. The OAuth2 Client can use a **refresh token** to request a new access token if the Authorization Server issued one, the grant permits it, and the client is configured to handle refresh. If refreshing is not possible, the client must restart the authorization flow or handle the login failure appropriately.

A refresh token is more sensitive than an access token because it can obtain subsequent tokens; it must be stored and protected appropriately, never sent in a Bearer header to a Resource Server.

### 12.2. Revocation and Logout

**Logging out of Portal** usually terminates Portal's HTTP session, yet **does not automatically** revoke issued access tokens. Revocation depends on the Authorization Server, token revocation endpoint/policies, session state, token lifetime, and the API's verification mechanism.

With opaque tokens, introspection after revocation can return **active: false**. With JWT access tokens verified only locally, the API normally does not notice revocation events unless an additional strategy is in place. Shortening token lifetimes narrows the exposure window while increasing token re-issuance demand.

### 12.3. Mitigating Bearer Token Theft Risks

Fundamental safeguards include HTTPS, keeping tokens out of URLs/logs, granting minimal scopes, issuing appropriately short-lived tokens, protecting tokens on the client, and enforcing explicit audiences. When stronger replay protection is needed, consider **sender-constrained access tokens** such as mTLS-bound access tokens or DPoP if supported by your ecosystem; that changes the sender-proof mechanism, rather than simply switching between opaque and JWT.

## 13. 401, 403, and Common Testing Scenarios

Example client call to Orders API:

~~~bash
curl -i "https://orders.example.test/api/orders" \
  -H "Authorization: Bearer ACCESS_TOKEN_VALUE"
~~~

In practice, use a validly issued token from a test environment and avoid leaving real tokens in shell history or logs. Never use illustrative token strings from this lesson as credentials.

| Scenario | Typical API Response | Explanation |
|---|---|---|
| No Bearer token | **401 Unauthorized** | No authentication credentials provided to the Resource Server |
| Invalid signature, wrong issuer, expired, or **active: false** | **401 Unauthorized** | Token is not accepted |
| Valid JWT but audience lacks **orders-api** | **401 Unauthorized** | This token is not intended for this API |
| Valid token but missing **orders.read** | **403 Forbidden** | Authenticated, but insufficient authority |
| Has **orders.read** but requests another user's order | **403 Forbidden** or **404 Not Found**, per resource-hiding policy | Business layer denies access to the resource |
| Valid token, sufficient scope and record permission | **200 OK** | API returns authorized data |
| Introspection server temporarily unavailable | Do not grant access by guessing; return an error aligned with implementation | Upstream failures and timeouts must be handled safely |

When returning authentication errors, the Resource Server may use the **WWW-Authenticate: Bearer** header with protocol error details such as **invalid_token** or **insufficient_scope**. Never write real access tokens into error responses.

An example of a 401 error:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

An example of a 403 error when a scope is missing:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Exact headers may vary depending on the application's exception handling and `AccessDeniedHandler` configuration.

## 14. Common Misconceptions

**"A Bearer token is a JWT."** False. Bearer describes how a token is presented and its usage semantics; the token inside may be opaque or JWT.

**"Opaque tokens are always safer because their payload cannot be read."** Not necessarily. An opaque string is still a credential; if leaked, anyone else can present it. Security depends on verification, lifetime, transport/storage protection, and authorization policies.

**"If a JWT is signed, the data inside is encrypted."** False for standard JWS JWTs. The Base64URL payload is readable; the signature verifies integrity and issuer origin.

**"Successfully decoding a JWT means the token is valid."** False. Decoding merely reads data; you must verify the signature and claims—especially **iss**, **aud**, **exp**, time constraints, and token type where applicable.

**"If the same IdP signed the token, it can be used at any API."** False. Each API must reject tokens with a different audience and enforce its own scopes/policies.

**"Having the `orders.read` scope means reading any order is allowed."** False. Scope defines capability at the API level; the API must still check permissions per resource, tenant, or subject.

**"An ID Token is also a JWT, so it can be used as a Bearer access token."** False. An OIDC ID Token is for the client to verify login; APIs require an access token issued for the API and validated against the access token contract.

**"JWTs never require connecting to the IdP."** False. APIs may need metadata/JWKS at startup or during key rotation; some architectures also require supplemental permission/revocation checks.

**"Opaque tokens must be introspected on every single request."** Not conceptually mandatory: it is the standard mechanism. Systems may cache results or use another internal verification method per contract, though caching introduces staleness in permission updates.

## 15. Practice Exercises

Suppose Portal receives an access token and needs to call two APIs:

- **Orders API** requires audience **orders-api** and scope **orders.read**.
- **Payroll API** requires audience **payroll-api** and scope **payroll.read**.

Evaluate each case:

1. The access token is a JWT with **aud=["orders-api"]**, **scope="orders.read"**, valid signature, and not expired. Can it be sent to Payroll API?
2. The access token is opaque; introspection returns **active=true**, **aud=["orders-api"]**, **scope="orders.read"**. Can Orders API conclude the user may read every employee's orders?
3. A browser steals the Bearer header from a Portal → Orders API request. Does JWT or opaque automatically stop an attacker from reusing the token?
4. Portal just logged out. Will a previously issued JWT access token with 10 minutes remaining be automatically rejected by Orders API?

**Comparison hints:** (1) No, the token is intended for Orders API, not Payroll API. (2) No, per-order permissions still must be checked. (3) No, ordinary bearer tokens carry replay risk regardless of format; prevent leaks or use appropriate sender-constraining mechanisms. (4) Not automatically; it depends on token revocation and verification mechanisms.

## 16. Takeaways When Designing Spring Security OAuth 2.0/OIDC

A helpful mental model is **three consecutive layers**:

1. **Bearer** describes **how the client presents the token** in HTTP calls to the API.
2. **Opaque or JWT** describes **which representation the Authorization Server issues** and **which mechanism the Resource Server uses to validate it**: introspection or signature/claim validation.
3. **API Authorization** decides **whether that valid token is allowed to perform the operation on the specific resource**.

Spring Security OAuth 2.0 Client helps the application acquire, hold, and send access tokens; Spring Security Resource Server helps the API validate tokens, establish principals, and map authorities. Whether tokens are opaque or JWT, validating audience, scope, lifetime, and data-object permissions remains mandatory for safely calling APIs on behalf of users.
