# Boundaries Between JWT Validation, Token Issuance, and Authorization Protocol Implementation

## 1. Three Distinct Responsibilities in a Bearer Token System

A Spring Security API that accepts `Authorization: Bearer <access-token>` and successfully validates a JWT **is not yet** a token-issuing system, nor has it become an OAuth 2.0/OpenID Connect (OIDC) server.

Three responsibilities must be kept distinct:

1. **JWT validation at the Resource Server:** receives an access token, verifies the signature and constraints such as issuer, audience, expiration, and token type; builds an `Authentication` and enforces access permissions.
2. **Token issuance:** selects identity and claims, decides lifetimes/scopes, signs tokens with the issuer's key or issues opaque tokens; manages keys, refresh, revocation, and lifecycle.
3. **Authorization protocol implementation:** the Authorization Server handles standard OAuth 2.0 flows, client registration, authorize/token endpoints, grants, redirect URIs, PKCE, consent, scopes, client authentication, refresh/revocation, and metadata. If supporting OIDC, it also handles ID Tokens, nonces, UserInfo, and identity authentication requirements.

They may live in separate processes or on the same platform, yet **you must not infer the second or third responsibility merely because an API has a `JwtDecoder`**.

Lesson goal: correctly identify Spring Security components, understand access token verification steps, recognize the limits of a JWT signing function, evaluate when an Authorization Server/OIDC Provider is needed, configure a Java 17+ Spring Boot Resource Server, and test issuer–audience–scope boundaries.

## 2. How Do JWT, Bearer, OAuth 2.0, and OIDC Differ?

| Concept | Meaning | Does Not Guarantee by Itself |
| --- | --- | --- |
| **JWT** | Token format holding JSON claims, typically protected by JWS (digital signature) or JWE (encryption) | OAuth authorization, login flows, refresh/revoke |
| **Bearer token** | Credential that any holder can present for access within its accepted scope | Proof that the HTTP caller itself holds a separate private key |
| **Access token** | Proof of granted authorization for an API/Resource Server | Full user profile details |
| **Refresh token** | Credential for a client to request new access tokens at the Authorization Server | Direct access to resource APIs |
| **OIDC ID Token** | Proof of identity authentication intended for an OIDC client (Relying Party) | Drop-in replacement for an access token to call arbitrary APIs |
| **OAuth 2.0** | Authorization framework issuing access tokens per grants/policies | Requiring access tokens to be JWTs |
| **OIDC** | Identity layer on top of OAuth 2.0 defining ID Tokens and related login flows | Arbitrary permissions across every API |
| **Resource Server** | API consuming/validating access tokens and enforcing permissions | OAuth token issuance endpoints |
| **Authorization Server** | Issues and manages permissions/tokens per protocol | Configuring authorization logic inside every API |
| **OAuth2 Client** | Application requesting tokens, optionally logging users in via an IdP | Issuing tokens to third parties itself |

**JWT does not equal access token.** OIDC ID Tokens are also typically JWTs. An OAuth access token can be an **opaque token**, meaning the Resource Server does not parse claims from the string itself and instead uses introspection against the Authorization Server.

**Bearer does not equal JWT.** The `Authorization: Bearer ...` header describes how a token is presented. The token string may be a signed JWT or an opaque reference token.

## 3. Architecture Diagram and Trust Boundaries

Suppose a website needs to call a reporting API:

~~~text
                         Browser / User
                              |
                     (1) Open web app
                              |
                              v
                          OAuth2 Client
                              |
                     (2) Authorization Code
                         + PKCE + state
                              |
                              v
                      Authorization Server
                     (AS / OIDC Provider)
                     - authenticate user/client
                     - check grant, scope/consent
                     - issue access token
                     - manage JWK/refresh/revoke
                              |
                 (3) JWT/opaque access token
                              |
                              v
                          OAuth2 Client
                              |
              (4) Authorization: Bearer <access-token>
                              |
                              v
                         Resource Server
                         Spring Security
                     - verify token validity
                     - check iss/aud/exp/nbf
                     - map scope/authorities
                     - check resource permissions
                              |
                              v
                            API data
~~~

Two independent operational paths:

- **Token issuance:** the Client asks the Authorization Server for a token per grant and policy.
- **Token consumption:** the Client presents the access token to the Resource Server; the Resource Server verifies and authorizes access.

With asymmetrically signed JWTs, the Resource Server can verify signatures using the issuer's public key/JWK without asking the Authorization Server on every request. With opaque tokens or JWTs requiring immediate status checks, the API can call **introspection**.

In the `client_credentials` grant there is no end user: the backend client authenticates itself to the Authorization Server and requests a token for the client itself. Never assume the `sub` claim of every access token represents a logged-in human user.

## 4. What Does a JWT Contain?

A JWS compact JWT typically consists of:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Illustrative header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-01"
}
~~~

Illustrative claims:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["reports-api"],
  "iat": 1793900000,
  "nbf": 1793900000,
  "exp": 1793903600,
  "client_id": "web-portal",
  "scope": "reports.read reports.export"
}
~~~

This is **not a signed token**. Values and timestamps only illustrate the structure.

| Claim/Header | Meaning | What to Consider When Verifying |
| --- | --- | --- |
| `alg` | Signature algorithm | Accept only allowlisted algorithms; never trust arbitrary algs |
| `kid` | Key ID | Look up keys only in the trusted issuer's JWK Set |
| `typ` | Profile-defined token type | Avoid using an ID Token as an access token |
| `iss` | Issuer | Must match the exact issuer trusted by the API |
| `aud` | Intended token recipient | Must include the identifier of the API being called |
| `exp` | Expiration timestamp | Reject expired tokens |
| `nbf` | Must not be used before this time | Reject not-yet-valid tokens |
| `iat` | Token issuance time | Enforce token age checks when required by policy |
| `sub` | Subject | Do not assume subject is always a user; scope by issuer/tenant |
| `scope`/`scp` | Granted scopes | Map to authorities and validate accurately |
| `client_id` | Client receiving the token in profiles using this claim | Validate client where required by the resource |
| `jti` | Token ID in profiles defining it | Does not prevent replay alone without state |

**Simply parsing a JWT is not authentication.** Base64URL decoding lets you read the payload without confirming who issued it. If an app decodes manually and trusts `sub="admin"`, a client can edit the JSON to impersonate anyone.

**Verifying the signature is still not enough.** A token validly signed by a trusted issuer yet having `aud="billing-api"` must not be accepted at `reports-api`. A token with `scope="reports.read"` does not allow exporting reports if the endpoint requires `reports.export`.

**JWS does not encrypt the payload:** digitally signed tokens are normally readable by anyone holding the string. Never place passwords, secrets, or unnecessary sensitive data in a JWT. Encrypting contents requires a separate mechanism such as JWE, in addition to TLS.

**Token type:** JWT access tokens per RFC 9068 use `typ=at+jwt` or `application/at+jwt`, along with profile claims and validation rules. Do not rigidly enforce RFC 9068 on every JWT/issuer if the token contract differs; however, you must ensure ID Tokens and access tokens cannot be confused.

## 5. First Boundary: Resource Server Validating Bearer JWTs

In Spring Security Servlet, the typical path is:

1. `BearerTokenAuthenticationFilter` extracts the access token from the request per Bearer rules.
2. `AuthenticationManager` delegates to `JwtAuthenticationProvider`.
3. `JwtDecoder` verifies signature/alg, token claims, and configured validators.
4. `JwtAuthenticationConverter` converts a valid JWT into a `JwtAuthenticationToken` with `GrantedAuthority` instances.
5. Spring Security evaluates `authenticated()`, `hasAuthority(...)`, or method/object policies.
6. The API returns data if authorized.

The Resource Server **does not need the issuer's private signing key** when tokens are asymmetrically signed. It typically needs a trusted public key/JWK Set. Never extract `jku` or a JWK URL from a caller-sent token and connect to arbitrary URLs: the key source must be operator-managed.

### 5.1. Default and Additional Checks

With `issuer-uri` in Spring Boot 3.5.x and Spring Security 6.5.x, the standard decoder verifies signatures, `iss`, `exp`, and `nbf`; scopes are typically mapped with the `SCOPE_` prefix. Depending on the issuer/provider, also enforce access token type, client ID, tenants, allowed algorithms, custom claims, and token age policies.

**Check `aud` explicitly.** Checking `iss` alone does not stop a token minted for another API from reaching yours. Spring Boot provides `spring.security.oauth2.resourceserver.jwt.audiences` to validate the expected audience.

### 5.2. Distinguishing HTTP 401 and 403

- Missing required Bearer token, bad signature, expired, or invalid issuer/audience: authentication rejected, **typically 401**.
- Valid token, insufficient scope/authority: request is authenticated yet lacks permission, **typically 403**.
- Valid token and matching scope: still check object, tenant, owner, and resource state permissions; **never grant all access merely because `authenticated` is true**.

For example, if the issuer grants `scope="reports.read"`, Spring Security maps it by default to `SCOPE_reports.read`. `hasAuthority("SCOPE_reports.read")` checks that authority. It differs from `hasRole("reports.read")`, which normally checks the `ROLE_` prefix.

## 6. Complete Example: Java 17+ Spring Boot Resource Server

This example only **receives and validates JWTs**; it has no token-issuing endpoints. It uses Spring Boot 3.5.x / Spring Security 6.5.x / Java 17+, Maven, and Servlet/Spring MVC.

### 6.1. Dependencies

Create a Spring Initializr project with:

- Spring Web: `spring-boot-starter-web`.
- OAuth2 Resource Server: `spring-boot-starter-oauth2-resource-server`.

The starter brings in the required modules for JWT/JOSE. If declaring dependencies manually, include both `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose` at compatible versions; let the Spring Boot BOM manage versions.

### 6.2. Configuring Issuer and Audience

File `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.test
spring.security.oauth2.resourceserver.jwt.audiences=reports-api
~~~

This is an **illustrative** issuer; for real authentication, replace it with a valid issuer exposing metadata and a JWK Set, minting JWTs with exact `iss` and `aud` containing `reports-api`.

If the issuer does not provide standard discovery yet exposes a verified JWK Set endpoint, you can also specify (path depends on issuer):

~~~properties
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://login.example.test/oauth2/jwks
~~~

Keeping `issuer-uri` preserves `iss` validation. Specifying only `jwk-set-uri` without configuring an issuer validator can skip issuer checking, depending on custom decoder configuration.

### 6.3. Complete Java Source

Create `src/main/java/demo/jwt/JwtResourceServerApplication.java`:

~~~java
package demo.jwt;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtResourceServerApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/me")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @RestController
    static class ReportApi {

        @GetMapping("/health")
        String health() {
            return "Resource Server ready";
        }

        @GetMapping("/api/reports/me")
        Map<String, Object> myToken(@AuthenticationPrincipal Jwt jwt) {
            return Map.of(
                "subject", jwt.getSubject(),
                "issuer", jwt.getIssuer().toString(),
                "audience", jwt.getAudience()
            );
        }
    }
}
~~~

Explanation:

- `oauth2ResourceServer(...jwt(...))` registers Bearer JWT authentication; it **does not** create `/oauth2/token` or sign tokens.
- `issuer-uri` and `audiences` enforce trust so the API does not accept tokens from other issuers or services.
- `hasAuthority("SCOPE_reports.read")` requires the token to carry the matching scope.
- `@AuthenticationPrincipal Jwt` is the JWT **already verified by Spring Security**; the controller never pulls raw tokens from the request to decode itself.
- `/health` allows unauthenticated calls; `denyAll()` blocks other URLs unless explicitly permitted.

The `GET /api/reports/me` example outputs a few claims for learning; in real applications, avoid exposing issuer/audience/subject details unnecessarily to callers who do not need them.

### 6.4. Running and Verifying

In a Maven project:

~~~bash
./mvnw spring-boot:run
~~~

Windows: `mvnw.cmd spring-boot:run`. Without the wrapper, use `mvn spring-boot:run`.

Test the public route:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

Expected body:

~~~text
Resource Server ready
~~~

Test the protected route:

~~~bash
curl -i http://127.0.0.1:8080/api/reports/me
~~~

Normally returns HTTP 401 without a Bearer token. Once you have **obtained a real access token** from a compatible issuer:

~~~bash
curl -i \
  -H "Authorization: Bearer VALID_ACCESS_TOKEN" \
  http://127.0.0.1:8080/api/reports/me
~~~

`VALID_ACCESS_TOKEN` is a placeholder, not a real token. On Windows PowerShell you can use `curl.exe` on a single line. Never save real tokens in shared shell history or logs.

If the JWT is valid with scope `reports.read`, example response:

~~~json
{
  "subject": "user-123",
  "issuer": "https://login.example.test",
  "audience": ["reports-api"]
}
~~~

If the token has the right issuer yet `aud=billing-api`, authentication must fail. If the audience is right yet `reports.read` is missing, the request typically returns 403. Exact responses depend on the IdP, actual token claims, and entry point configuration.

**Limitation:** this application has no login page, accepts no username/password, and has no grant flows, refresh tokens, client registration, or token issuance. Failing to reach the hypothetical hostname is not a Resource Server logic bug.

## 7. Second Boundary: A JWT Signing Function Is Only a Token-Issuing Primitive

A program can use `JwtEncoder` to create and sign a JWT:

~~~java
// Illustrative snippet; not a standalone class or program.
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer("https://issuer.example.test")
    .subject("user-123")
    .audience(java.util.List.of("reports-api"))
    .expiresAt(java.time.Instant.now().plusSeconds(900))
    .claim("scope", "reports.read")
    .build();

Jwt jwt = jwtEncoder.encode(
    org.springframework.security.oauth2.jwt.JwtEncoderParameters.from(claims)
);
~~~

This requires a key-configured `JwtEncoder` bean, algorithm selection, caller-authentication logic, and claim policies. The code above **is not** an operational AS; it merely describes signing an assembled payload.

### 7.1. Why Is a POST /login Endpoint Returning a JWT Not Yet OAuth 2.0?

Custom example:

~~~http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"..."}
~~~

Illustrative response:

~~~json
{
  "token": "eyJ..."
}
~~~

That can be an **application-specific custom token protocol**, if properly designed and secured. By itself, however, it lacks:

- OAuth client registration, client authentication, and public/confidential client types.
- Authorization Code + PKCE, Client Credentials, and Refresh Token flows with standard contracts.
- Authorization endpoint, token endpoint, redirect URI validation, state/correlation, and CSRF protection.
- Scope, resource/audience, and consent management; preventing granting scopes beyond policy.
- Client-credentials security, key rotation, JWKS, and metadata/discovery.
- Refresh token lifecycle, revocation/introspection, and authorization state storage.
- OIDC ID Tokens, nonces, UserInfo, and logout when federated login is needed.

Do not call a custom `/login` returning a JWT an "OAuth Server" if standard OAuth clients cannot complete the protocol. Using JWTs as access tokens **does not mandate** implementing OAuth, yet you should name the protocol accurately.

### 7.2. Which Responsibilities Belong to the Issuer?

1. Deciding **who** is requesting a token: which client, which user, and which credential/grant.
2. Checking client registration, allowed grant types, redirect URIs, and scopes.
3. Setting valid `iss`, `aud`, `sub`, claims, token type, and lifetimes.
4. Protecting signing private keys, publishing public JWKs, `kid` management, rotation, and compromise handling.
5. Persisting authorizations, refresh tokens, and consent/revocation state as needed.
6. Auditing, rate limiting, login abuse prevention, and securing token endpoints.
7. Enforcing policies for client secrets, PKCE, and MFA/SSO (where relevant).

A Resource Server generally **does not control token issuance**. It validates tokens per its contract with the issuer and enforces resource access permissions at the API.

## 8. Third Boundary: Authorization Server Implementing OAuth 2.0/OIDC

### 8.1. Protocol Roles

| Role | Responsibility |
| --- | --- |
| Resource Owner | Entity that owns the resource, typically a user |
| Client | Application wanting to access the resource |
| Authorization Server | Authenticates appropriately, executes grants, issues tokens |
| Resource Server | API accepting access tokens and protecting resources |

The AS may share a user database with the API, yet their contracts and permissions differ.

### 8.2. Authorization Code + PKCE

Typical browser/OIDC flow:

~~~text
Browser → Client → AS /oauth2/authorize
                (client_id, scope, redirect_uri,
                 state, code_challenge, method=S256)
                       |
                  login / consent
                       |
                 redirect code + state
                       |
Client → AS /oauth2/token
             (code, redirect_uri, code_verifier,
              client auth if applicable)
                       |
            access token (+ refresh token if permitted;
                           ID Token for OIDC login)
                       |
Client → API: Authorization: Bearer <access-token>
~~~

**PKCE** binds the authorization code to the client's `code_verifier`, reducing code-interception risk. `state` supports correlation/CSRF protection on the authorization response. OIDC adds requirements such as ID Token validation and `nonce` where applicable. Public clients like SPAs and mobile apps must never embed a hardcoded client secret in the frontend and call it a secret.

**Access token vs. ID Token:** ID Tokens target the OIDC client; Resource Servers generally require an access token with API-specific audience/claims and scopes. Being signed by the same issuer does not make them interchangeable.

### 8.3. Client Credentials

A backend calls the AS with `grant_type=client_credentials` and proper client authentication, receives an access token, and calls the Resource Server. There is no end user in this flow; permissions usually bind to the service/client. Never treat `sub` as a human user ID when the token has client semantics.

### 8.4. Refresh and Revoke

A client with a valid refresh token can send it to the **AS token endpoint** to obtain a new access token. The Resource Server is not where refresh tokens are sent. With offline-verified JWTs, revoking at the AS does not automatically notify every API immediately; choose short TTLs, introspection, denylists, revocation events, or complementary mechanisms based on revocation-latency requirements.

## 9. Which Spring Modules Do Resource Server, OAuth2 Client, and Authorization Server Use?

| Need | Spring Mechanism |
| --- | --- |
| API verifying IdP-issued JWT Access Tokens | `spring-boot-starter-oauth2-resource-server` with JWT decoder |
| API verifying opaque Bearer Tokens | Resource Server + introspection |
| Web app logging in via OIDC IdP | `spring-boot-starter-oauth2-client` + `oauth2Login()` |
| Backend fetching `client_credentials` tokens to call APIs | Appropriate OAuth2 Client token acquisition |
| Building a standard OAuth2 Authorization Server | `spring-boot-starter-oauth2-authorization-server` or dedicated IdP platform |
| Only signing/reading JWTs in Java | `JwtEncoder`/`JwtDecoder` are primitives, not a protocol |

**Example version baseline:** Spring Boot 3.5.x / Spring Security 6.5.x / compatible Authorization Server per Spring Boot BOM. From Boot 4 / Spring Security 7 onward, recheck module names, APIs, DSLs, and migration guides rather than copying old project configs verbatim.

### 9.1. Shape of an Authorization Server Configuration

A separate project acting as an AS can start with the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
~~~

YAML example describing **one client** for authorization code and refresh token (abbreviated configuration to show structure; not a complete production deployment):

~~~yaml
server:
  port: 9000

spring:
  security:
    oauth2:
      authorizationserver:
        client:
          web-client:
            registration:
              client-id: web-client
              client-secret: "${CLIENT_SECRET_ENCODED}"
              client-authentication-methods:
                - client_secret_basic
              authorization-grant-types:
                - authorization_code
                - refresh_token
              redirect-uris:
                - https://app.example.test/login/oauth2/code/web-client
              scopes:
                - openid
                - profile
                - reports.read
            require-authorization-consent: true
~~~

`CLIENT_SECRET_ENCODED` must come from a secrets store and be encoded per the configured `PasswordEncoder`; never commit plaintext passwords or client secrets to Git. Production AS operation requires configuring the issuer URI, HTTPS, keys, persistent storage for clients/authorizations/consents, user login, rotation/revocation, HA, and monitoring.

Common components:

- `RegisteredClientRepository` manages clients, grants, redirect URIs, and scopes.
- `OAuth2AuthorizationService` manages authorization state and token lifecycle.
- `OAuth2AuthorizationConsentService` manages consent when enabled.
- `JWKSource<SecurityContext>` supplies key material for JWT signing and JWK publication.
- `AuthorizationServerSettings` defines the issuer and endpoints.
- `SecurityFilterChain` beans for AS protocol endpoints and user login.
- Separate OIDC setup when the AS issues ID Tokens and serves OIDC metadata/UserInfo.

An in-memory configuration is fine for learning, yet lacks HA, key persistence, auditing, and production token lifecycle management.

## 10. JWT vs. Opaque Token and Status Checking

| Criterion | Self-Verified JWT | Opaque Token via Introspection |
| --- | --- | --- |
| Verification | JWS + claims/issuer/audience/time/policy | AS introspection returns `active` and claims per contract |
| Network call per API request | Usually none once JWKS is cached | Usually needed, unless caching is designed |
| Are token claims readable? | JWS payload is usually readable | Opaque value exposes no claims directly |
| Runtime AS dependency | Lower, still needs JWKS/rotation | Higher, needs introspection endpoint |
| Early permission revocation | Needs extra mechanisms if offline-only | AS can stop marking it active |
| Key/credential | Trusted public key/JWKS | Client secret or introspection auth |
| Authorization | API still enforces policy itself | API still enforces policy itself |

Spring Security supports `opaqueToken(...)` when a trusted introspection endpoint is available:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://login.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=reports-api
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

~~~java
// Configuration snippet inside SecurityFilterChain:
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

This is only a **configuration fragment** replacing `jwt(...)`, not a standalone application. Spring can introspect a JWT-shaped token if querying AS status is required; token format and verification strategy are separate choices. Protect secrets, TLS, timeouts, and fail closed.

## 11. Separating Token Authentication from Resource Authorization

A token can answer who/what is calling and which baseline permissions were granted; the API must still check specific resources.

Example:

- AS issues JWT: `sub=user-123`, `aud=reports-api`, `scope=reports.read`, `tenant_id=tenant-A`.
- API verifies the JWT and confirms matching scope.
- User calls `GET /api/tenants/tenant-B/reports/99`.

If the API checks only scope, a tenant A user can read tenant B data. The API must check tenant and ownership/object-level permissions. **A valid JWT does not equal valid access.**

Distinct concepts:

- User authentication at the IdP/AS verifies user credentials or session.
- Client authentication at the AS verifies the client.
- Token authentication at the API verifies the Bearer token.
- Authorization grant at the AS decides which scopes/resources were granted.
- Resource authorization at the API decides each action, object, tenant, and business policy.

A client **requesting** a scope in an authorization request does not force the issuer to grant it. Seeing a scope at the API also does not automatically imply internal roles. Role-based authorization and scope-based authorization can complement each other, yet are not the same thing.

## 12. Standalone Java 17: Illustrating Issuer/Audience/Time/Scope Checks

To practice checking claim rules without a server, the program below models the policy step **after claims have already been verified by a trusted JWT decoder**. It does not parse tokens, verify signatures, and **must never be used standalone to authenticate Bearer tokens**.

Create `TokenPolicyDemo.java`:

~~~java
import java.time.Instant;
import java.util.Set;

public class TokenPolicyDemo {

    record VerifiedClaims(
            String issuer,
            Set<String> audiences,
            Instant expiresAt,
            Set<String> scopes) {}

    static boolean mayRead(VerifiedClaims token, Instant now) {
        return "https://login.example.test".equals(token.issuer())
                && token.audiences().contains("reports-api")
                && now.isBefore(token.expiresAt())
                && token.scopes().contains("reports.read");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        Instant later = Instant.parse("2026-12-01T00:00:00Z");

        var valid = new VerifiedClaims(
                "https://login.example.test",
                Set.of("reports-api"),
                later,
                Set.of("reports.read"));

        var wrongAudience = new VerifiedClaims(
                "https://login.example.test",
                Set.of("billing-api"),
                later,
                Set.of("reports.read"));

        var wrongScope = new VerifiedClaims(
                "https://login.example.test",
                Set.of("reports-api"),
                later,
                Set.of("reports.export"));

        var expired = new VerifiedClaims(
                "https://login.example.test",
                Set.of("reports-api"),
                Instant.parse("2026-11-05T00:00:00Z"),
                Set.of("reports.read"));

        System.out.println(mayRead(valid, now));
        System.out.println(mayRead(wrongAudience, now));
        System.out.println(mayRead(wrongScope, now));
        System.out.println(mayRead(expired, now));
    }
}
~~~

Run:

~~~bash
javac --release 17 TokenPolicyDemo.java
java TokenPolicyDemo
~~~

**Exact** stdout:

~~~text
true
false
false
false
~~~

Line 1 meets all four conditions; subsequent lines fail due to wrong audience, missing scope, or expiration. Real systems also require signature verification, algorithm allowlists, issuer trust, `nbf`, token type, and business rules.

## 13. Common Mistakes and Fixes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Only Base64URL-decoding to read `sub` | Attacker-crafted claims can be trusted | Use `JwtDecoder` verification and validators |
| Checking signature only, skipping `aud` | Tokens from other APIs accepted | Validate resource audience |
| Checking `iss` only, skipping `exp` | Expired tokens accepted | Validate timestamps and reasonable clock skew |
| Trusting `alg`/`jku` headers | Algorithm/key confusion, malicious key sources | Allowlist algorithms and JWK URLs |
| Using ID Token instead of access token | Token meant for OAuth client accepted by API | Validate audience and token profile |
| Sharing one symmetric secret across all services | Any service knowing the secret can spoof the issuer | Separate signing/verification, prefer asymmetric keys |
| Writing `/login` returning a JWT and calling it OAuth | Missing protocol grants/PKCE/refresh/metadata | Use a standard AS/IdP when interoperability is needed |
| Embedding client secret in SPA/mobile | Secret can be extracted | Use public-client model with PKCE |
| Checking only `authenticated()` | Skips scope/tenant/object permissions | Enforce scope and data-level rules |
| Overly long JWT TTL | Stolen tokens remain usable longer | Short TTLs, refresh/revocation per policy |
| Assuming `jti` prevents replay on its own | Bearer tokens can still be replayed | Token binding, state/replay detection when required |
| Forgetting JWKS rotation | Valid tokens rejected or compromised keys still trusted | Key lifecycle, multiple active keys, cache refresh |
| Recording Bearer tokens in URLs/logs | Tokens leak via history, logs, monitoring | Headers, masking, HTTPS, client security |
| Calling every error 403 | Confuses invalid tokens with missing permissions | Distinguish 401/403 and verify with tests |
| Using `sub` globally across tenants | Subject collisions across issuers/tenants | Namespace identities by issuer + tenant + sub |

### Is a Bearer Token Proof-of-Possession?

No. With Bearer tokens, any party holding a valid token string can use it within permitted bounds. An RSA-signed JWT proves the token was signed by the issuer holding the private key, **not that the HTTP request was sent by a client holding its own private key**. If proof-of-possession is required, design sender-constrained tokens such as mTLS-bound tokens or DPoP properly.

### Browsers and Token Storage

Clients must defend against XSS, exfiltration, and log leakage. Tokens stored in JS-readable storage carry XSS risk; tokens sent automatically via cookies require CSRF, SameSite, and session policy analysis. CORS is not authentication and does not replace authorization. Use HTTPS on every channel carrying tokens and avoid query parameters.

### Revocation Is Not Automatic

A signed, unexpired JWT can continue being accepted by an offline API after user logout or role changes unless the Resource Server has a mechanism to detect updates. Decide on TTLs, introspection, revocation lists, key rotation, policy lookups, or revocation events. Never disable signature validation just to work around key/JWK issues.

## 14. Deployment Checklist

**Resource Server:**

- [ ] Accept only declared issuers; JWK Set from trusted sources.
- [ ] Verify signature, allowed algorithms, `iss`, `aud`, `exp`, `nbf`.
- [ ] Check token type/profile when the app encounters multiple JWT types.
- [ ] Validate API audience; never accept tokens intended for another service.
- [ ] Map scopes/roles and enforce object/tenant ownership.
- [ ] Distinguish 401 invalid token from 403 insufficient permission.
- [ ] Protect Bearer credentials, avoid logs/URLs, enforce HTTPS.
- [ ] Plan for JWKS caching/rotation, timeouts, and issuer outages.
- [ ] Design appropriate revocation and token lifetime policies.

**Authorization Server:**

- [ ] Register clients, authenticate clients, and constrain grants/scopes/redirect URIs.
- [ ] Use Authorization Code + PKCE for public applications where appropriate.
- [ ] Configure issuer, aud, claims, token lifetimes, and token types accurately.
- [ ] Protect private signing keys, JWKS, secret storage, and key rotation.
- [ ] Manage authorization consent/refresh/revocation/introspection as needed.
- [ ] OIDC ID Token/UserInfo/metadata if implementing identity login.
- [ ] Configure HTTPS, rate limits, MFA/login policies, auditing, and monitoring.
- [ ] Have a recovery plan for key compromise and token leakage.

## 15. Test Matrix

| Case | Expectation |
| --- | --- |
| No token sent to protected endpoint | 401 |
| Bearer token is a random string | 401 |
| Structurally valid JWT with bad signature | 401 |
| Token from untrusted issuer | 401 |
| Valid signature, wrong audience | 401 |
| Expired token or before `nbf` | 401 |
| Valid token missing `reports.read` | 403 |
| Valid token, matching scope, wrong tenant/object | Deny per policy, typically 403 |
| Valid issuer, aud, scope, and data permission | 200 or valid business response |
| ID Token presented instead of access token | Rejected per audience/token type policy |
| Refresh token presented to API | Rejected; refresh is only for the AS |
| Issuer key rotation | Resource Server updates JWKs per policy without disabling verification |
| AS temporarily unreachable, JWKS cached | Behavior per tested cache/timeout policy, never accept unverified tokens |
| Introspection endpoint fails | Fail closed, never assume token is `active` |

Statuses reflect standard Bearer API expectations; custom entry points or gateways may adjust final HTTP status codes, yet **must never grant unauthorized access**.

## 16. Self-Check Questions

1. Why does `oauth2ResourceServer().jwt()` not expose `/oauth2/token`?
2. What does a JWT signing function lack compared to a full OAuth2 protocol implementation?
3. How do an ID Token and an access token differ in audience and purpose?
4. Why is a valid JWT signature not enough for an API to grant access?
5. When does a Resource Server not need the private signing key?
6. Which Spring Security authority does `reports.read` usually become?
7. Does a `client_credentials` token necessarily represent a human user?
8. Does logging out at the AS immediately invalidate all signed JWTs everywhere?
9. When should 401 be returned vs. typically 403?
10. Why is `sub` insufficient as a global identity in multi-tenant systems?
11. Why does `jti` not automatically prevent Bearer replay?
12. When do you choose Resource Server, OAuth2 Client, Authorization Server, or OIDC Provider?

## 17. References

- [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Authorization Server 1.5 — Getting Started](https://docs.spring.io/spring-authorization-server/reference/1.5/getting-started.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
