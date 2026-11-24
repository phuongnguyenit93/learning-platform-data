# Bearer Token Mechanism and JWT Authentication Flow in WebFlux

## 1. Problem: How Does a Reactive API Receive a Bearer Token?

A Spring WebFlux application exposes `GET /api/catalog` and `POST /api/orders` APIs. A client has signed in with an Authorization Server and holds an **access token** issued for this API. The client sends:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Spring Security Reactive needs to answer **two independent questions**:

1. **Authentication:** Is the Bearer token present, valid, unexpired, and matching the expected issuer, signature, and audience? If so, who or which client is being identified?
2. **Authorization:** Does that Authentication hold a specific authority such as `SCOPE_catalog.read` or `SCOPE_orders.write` to perform the request?

If the token is missing or invalid, it usually returns **401 Unauthorized** along with `WWW-Authenticate: Bearer`. If the token is valid but lacks permission, it usually returns **403 Forbidden**. Errors regarding payload/orders/inventory occurring after security checks are separate business errors.

In Spring Security Reactive, the framework provides a pipeline to:
- Extract the Bearer credential from the HTTP request.
- Pass the token to a `ReactiveAuthenticationManager`.
- Decode and **verify** the JWT using `ReactiveJwtDecoder`.
- Convert the verified JWT into a `JwtAuthenticationToken`.
- Provide the authentication in the reactive security context.
- Enforce `authorizeExchange` rules or method/object authorization before allowing the controller to handle the request.

**Key point:** A Resource Server only **verifies access tokens**, not issues them. A JWT is **a signed token format**, not an encrypted password or proof that a token is always safe under all circumstances.

### What You Will Learn

- Understand Bearer Authentication per RFC 6750, the meaning of Bearer, and replay risk.
- Name the exact Reactive classes: `ServerBearerTokenAuthenticationConverter`, `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, `JwtAuthenticationToken`.
- Analyze JWT header/payload/signature, issuer/audience/expiry/not-before/scopes.
- Configure Spring Boot 3.5 + Spring Security WebFlux with `issuer-uri`, `jwk-set-uri`, `audiences`, and a default-deny security chain.
- Understand 401/403, challenge headers, CSRF, and stateless API trade-offs.
- Write a Java 17+ WebFlux application, test the real HTTP Bearer chain with a mock decoder, and test authorization separately with `mockJwt()`.
- Recognize which tests do **not** prove real signature/issuer/audience validation and which IdP/JWKS integration tests are needed.
- Debug token errors, key rotation, CORS, logging, multi-tenancy, and clock skew.

This lesson belongs to the **Resource Server JWT** group of the Spring Security - reactive module. Hostnames and tokens in the examples are simulated data, not live credentials or pre-deployed endpoints.

## 2. What Is a Bearer Token?

“Bearer” means **whoever holds a valid token can present that token to access resources**, within the limits of the token's permissions and lifetime. The resource server usually does not require a separate signature from the presenter on each request like a proof-of-possession scheme.

Common standard:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

According to RFC 6750:
- `Authorization` is the standard HTTP request header.
- `Bearer` is the authentication scheme.
- The remainder is the access token string received from the authorization server.
- The resource server verifies the token and applies the authorization policy.

### 2.1. Consequences of the Bearer Mechanism

If an attacker obtains a valid Bearer access token, the attacker can **replay** the token to call the API within the granted scope, unless the system has additional controls such as token binding, proof-of-possession (DPoP/mTLS), token revocation, or endpoint policies.

Therefore:
- Require TLS/HTTPS in real environments.
- Do not send tokens in URL query parameters: URLs can end up in logs, browser history, referrers, analytics, and reverse proxies.
- Do not log `Authorization`, raw JWTs, or refresh tokens.
- Do not return tokens in error responses, exception text, or telemetry.
- Use short-lived access tokens; consider refresh-token rotation/revocation at the Authorization Server.
- Consider DPoP/mTLS-bound tokens when the threat model requires stronger replay protection.

**A JWT signature only guarantees integrity and issuer authenticity according to the keys and trust policy; it does not by itself prevent a stolen token from being used.**

### 2.2. A Bearer Token Is Not Necessarily a JWT

There are two common types:

| Access token | Characteristics | What does the resource server do? |
| --- | --- | --- |
| Signed JWT | Header/payload/JOSE signature, claims such as iss/aud/exp/scope | Verifies signature, key, algorithm, and claims; usually does not need to call the IdP on every request |
| Opaque token | A string that cannot be meaningfully decoded as a JWT at the API | Uses token introspection or another trusted mechanism |

Spring Security supports both `oauth2ResourceServer(...jwt(...))` and `oauth2ResourceServer(...opaqueToken(...))`, but this lesson focuses only on **Bearer JWT**.

Do not choose JWT mode and then try to parse an arbitrary opaque token. Conversely, do not force JWTs to be introspected on every request if the architecture uses offline signature validation without such a requirement.

## 3. OAuth2 Client, Authorization Server, and Resource Server

A typical architecture:

~~~text
[Browser/Mobile/Service Client]
             |
             | Authorization Code + PKCE, Client Credentials,
             | or an appropriate grant depending on the client
             v
[Authorization Server / Identity Provider]
             |
             | Issues access token for a specific audience/resource
             v
[Client holds access token securely]
             |
             | HTTPS
             | Authorization: Bearer <access-token>
             v
[Spring WebFlux OAuth2 Resource Server]
             |
             | Decode + verify JWT, check scopes/roles/ownership
             v
[Controller -> Service -> Data]
~~~

Roles:
- **Authorization Server:** authenticates the client/user according to the flow and issues access tokens.
- **Resource Server:** trusts one or a few specific issuers, verifies tokens issued by them, and protects the API.
- **OAuth2 Client:** an application performing the authorization flow to obtain access tokens.
- **Resource Owner:** the entity that owns or has the authority to grant authorization to resources under the OAuth model.

An application can be both an OAuth2 Client and a Resource Server simultaneously, but each security chain/route must be clearly configured. Simply adding the resource-server starter **does not create JWT-issuing endpoints** or OAuth2 Login.

### 3.1. Access Tokens Differ from ID Tokens

In OIDC Login:
- **ID token** has the OIDC client as its audience; it is used by the client to confirm the end-user's authentication result.
- **Access token** is intended for the resource server/API; it has appropriate scopes/permissions, audience/resource, and lifetime.

Do not use `OidcUser.getIdToken().getTokenValue()` as a Bearer token to a business API. A JWT with a valid issuer and signature whose `aud` is the web client may still **not be a token intended for the API**.

### 3.2. Refresh Tokens Are Not Sent to the Resource Server

A refresh token is used with the Authorization Server/token endpoint according to the grant policy; it is not a credential for calling `/api/catalog`. The Resource Server does not automatically issue a refresh token just because an access token has expired.

## 4. Bearer JWT Authentication Flow Inside WebFlux

This is a conceptual pipeline matching Spring Security Reactive 6.x:

~~~text
HTTP request
  Authorization: Bearer <jwt>
          |
          v
SecurityWebFilterChain / WebFilter
          |
          v
AuthenticationWebFilter for Resource Server
          |
          v
ServerBearerTokenAuthenticationConverter
          |
          | No Bearer token?
          |   -> Mono.empty() (no authentication attempt from token)
          |
          | Token present / malformed string?
          |   -> candidate BearerTokenAuthenticationToken
          |      or extraction error depending on the situation
          v
ReactiveAuthenticationManager
  (typically JwtReactiveAuthenticationManager)
          |
          v
ReactiveJwtDecoder
  (typically NimbusReactiveJwtDecoder via Boot/JWKS)
          |
          +-- Invalid signature/issuer/audience/time
          |         -> Authentication failure -> typically 401
          |
          +-- Valid JWT
                    |
                    v
JWT -> GrantedAuthority mapping
  scope/scp -> SCOPE_catalog.read, ...
                    |
                    v
JwtAuthenticationToken
  principal = Jwt
  authentication.name usually from sub
                    |
                    v
Reactive SecurityContext / Reactor Context
                    |
                    v
AuthorizationWebFilter + authorizeExchange
                    |
          +---------+--------------+
          |                        |
     Missing authority        Has route permission
          |                        |
          v                        v
         403                 DispatcherHandler
                                Controller
                                Service + object policy
~~~

**This is a learning model, not an absolute execution trace of every WebFilter.** A request may be handled earlier by CORS, CSRF, matchers, a gateway, or another security chain. For an anonymous request to a protected route, authorization usually triggers the Bearer authentication entry point -> 401.

### 4.1. ServerBearerTokenAuthenticationConverter

Reactive package:

~~~java
org.springframework.security.oauth2.server.resource.web.server.authentication
    .ServerBearerTokenAuthenticationConverter
~~~

It implements `ServerAuthenticationConverter` and reads the Bearer token from `ServerWebExchange`, defaulting to the `Authorization` header.

- No matching Bearer: the converter can return `Mono.empty()`, meaning no token-based authentication attempt.
- Syntactically valid Bearer present: creates a `BearerTokenAuthenticationToken` containing the **unverified** token string.
- Malformed header/multiple tokens/invalid format: may emit an OAuth Bearer error; the exact status depends on the error type.

**Do not confuse the converter with the JWT decoder.** The converter should not parse JWT claims, decide permissions, or trust the token value.

### 4.2. JwtReactiveAuthenticationManager

`JwtReactiveAuthenticationManager` implements `ReactiveAuthenticationManager`. It receives an Authentication carrying the Bearer token, delegates to `ReactiveJwtDecoder` to verify the JWT, and transforms the result into an authenticated Authentication.

- Decode/validation fails: emits an authentication error without creating a principal.
- Decode succeeds: runs the JWT-to-Authentication converter.
- Controllers do not need to call `decode` manually on every request; Security Resource Server orchestrates this.

### 4.3. ReactiveJwtDecoder

Interface:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
~~~

Conceptual contract:

~~~java
// Illustrative signature, not a standalone Java file.
Mono<Jwt> decode(String token);
~~~

Its job is **not just Base64URL decoding**, but also verifying the signature with trusted keys, checking claims against validators, and emitting an error if the JWT fails policy. The typical implementation is `NimbusReactiveJwtDecoder`.

### 4.4. JwtAuthenticationToken

A valid JWT request typically has:
- `Authentication` of type `JwtAuthenticationToken`.
- `Authentication.getPrincipal()` is `Jwt`.
- `Authentication.getName()` defaults to `sub`.
- `Authentication.getAuthorities()` is mapped from `scope`/`scp` or a custom converter.

In a controller:

~~~java
@GetMapping("/api/whoami")
public Mono<Map<String, Object>> whoAmI(
        @AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of("subject", jwt.getSubject()));
}
~~~

This is a controller snippet; if the route does not require auth or `sub` is absent, an appropriate contract is needed. **Do not serialize the entire Jwt or raw token value** back to the client for “debugging”.

### 4.5. SecurityContext in Reactor Is Not a Servlet ThreadLocal

Spring Security Reactive propagates authentication down the pipeline via the **Reactor Context** and corresponding WebFilters. Do not use `SecurityContextHolder.getContext()` assuming a ThreadLocal always follows the request on the event loop; when needed, use `ReactiveSecurityContextHolder.getContext()` or argument injection.

Do not call `block()` or manual `subscribe()` inside filters/controllers to retrieve Authentication, as doing so can block the event loop or break the subscription context.

## 5. A JWT Has Three Parts, Not Encrypted Data

A JWS-signed JWT typically looks like:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Illustrative header example:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-11",
  "typ": "at+jwt"
}
~~~

Illustrative payload:

~~~json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-42",
  "aud": ["catalog-api"],
  "scope": "catalog.read orders.write",
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790003600,
  "jti": "opaque-token-id"
}
~~~

This is only **illustrative JSON**, not a usable signed JWT. The `typ=at+jwt` header is an example of the JWT access token profile; not every provider uses the same value, and token type validation rules depend on the issuer/resource server's token contract.

### 5.1. Header, Claims, and Signature

- **Header:** signing algorithm `alg`, key identifier `kid`, sometimes token type `typ`.
- **Payload:** claims; `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `scope/scp` have specific semantics.
- **Signature:** protects integrity and proves the token was issued by the party holding a valid signing key per the trust policy.

Base64URL is only **encoding**. Anyone holding the JWT can usually decode the header/payload; do not put passwords, access secrets, or overly sensitive data into claims just because the JWT is signed. When claim confidentiality is required, opaque tokens, minimal data, or JWE may be needed by design; a JWS signature alone does not keep the payload confidential.

### 5.2. Do Not Trust Claims Before Verifying

Do not do this:

~~~java
// WRONG: parsing payload and trusting "role" before verifying signature.
String role = parseBase64Payload(untrustedJwt).get("role");
if ("ADMIN".equals(role)) {
    grantAdminAccess();
}
~~~

This is pseudocode illustrating a bug. An attacker can modify the payload if the server does not verify the signature. If multi-tenancy requires reading an untrusted `iss` to select a decoder, use it only to **look up a fixed allowlist** and then verify the token completely with the corresponding decoder; do not accept arbitrary issuer/JWKS URLs from the token.

## 6. Claims to Validate

| Claim | Meaning | Security notes |
| --- | --- | --- |
| `iss` | Issuer/authorization server | Trust only configured issuers |
| `sub` | Subject, usually user/client ID | Do not automatically treat as email/role/tenant |
| `aud` | Audience/resource the token is intended for | **Must include your API** per contract |
| `exp` | Expiration | Reject expired JWTs; allow only limited clock skew |
| `nbf` | Not before | Reject tokens before their valid start time |
| `iat` | Issued at | Use for age/time policies when appropriate |
| `jti` | Token identifier | Can support revocation/replay detection if stateful |
| `scope` | Space-delimited scopes | Usually mapped to `SCOPE_...` |
| `scp` | List of scopes in some providers | Spring supports appropriate mapping |
| `client_id` / `azp` | Client/authorized party per profile | Does not imply permissions on data |
| `tenant` / `org` | Provider-specific claim | Needs validation alongside issuer/audience/ownership |
| `typ` (header) | Token type hint/profile | Evaluate if provider uses access-token profile |

### 6.1. iss: Trust Boundary

An API should only accept tokens issued by permitted issuers. If an API serves multiple tenants/providers, each issuer must have clear validation, key, and audience policies. Never accept an arbitrary `iss` and automatically fetch `.well-known` from an attacker-chosen URL; that introduces SSRF/issuer confusion risks.

### 6.2. aud: Easily Overlooked

A web client's ID token may have `aud=web-ui`, whereas an API access token has `aud=catalog-api`. **A valid signature and issuer are not enough**; `aud` must also match the resource server.

In Spring Boot 3.5, you can configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          audiences:
            - catalog-api
~~~

Combined with issuer/JWKS config, Boot applies audience validation to the token. If the access token lacks the contracted audience, do not arbitrarily disable validation just to get a 200 response; work with the authorization server to issue tokens targeted for the right resource.

### 6.3. exp, nbf, and Clock Skew

Spring Security uses JWT timestamp validators, which include a default clock skew in standard configuration to tolerate small clock differences. Do not increase clock skew to hours to “fix expired tokens”: doing so extends the window in which tokens that should be rejected are still accepted.

Ensure NTP/time synchronization on servers; check expired tokens, `nbf` in the future, issuer, timezone, and issuance time. An unexpired token that has been revoked will still be accepted by the JWT validator if the system **only performs offline signature/claim checks** without an additional revocation mechanism.

### 6.4. sub Is Not Automatically Permission

`sub` can be a user ID or a machine client ID. `sub=user-42` does not mean this user owns every record. Controllers/services must still check ownership/tenant and permissions for the specific resource. Do not use a token-asserted email/name as the primary identifier key if the provider does not guarantee stability rules.

## 7. JWT Signatures, JWKS, Algorithms, and Key Rotation

The Authorization Server signs JWTs with an appropriate private key. The Resource Server typically fetches public keys via a **JWK Set URI**, using `kid` and allowed algorithms to select the key and verify the JWS signature.

~~~text
Authorization Server
    private signing key
       |
       v
Signed JWT (alg, kid, claims, signature)
       |
       v
Spring Resource Server
    trusted JWK Set URI
       |
       +--> public keys / permitted JWS algorithms
       +--> verify signature
       +--> issuer/audience/timestamps validators
       v
Authenticated Jwt
~~~

### 7.1. jwk-set-uri and issuer-uri

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - catalog-api
~~~

This is a **demo configuration with non-existent endpoints**. In real usage, issuer/JWKS must come from a trusted Authorization Server. Providing both `issuer-uri` and `jwk-set-uri` gives the application the JWKS directly while retaining issuer information for validation; it avoids depending on discovery to find the JWKS endpoint at startup.

If only `issuer-uri` is configured, Spring Security can discover metadata/JWKS when needed; in modern Spring Security 6.5, this discovery may be deferred until the first Bearer request. Do not assume app startup always calls the IdP immediately.

### 7.2. Algorithm Allowlist and alg=none

Per the Spring Security 6.5 Reference, `NimbusReactiveJwtDecoder` defaults to trusting/verifying `RS256` in standard setups and can be configured with other trusted algorithms as required by the provider. Never accept `alg=none` and never let an untrusted JWT header freely dictate the key or algorithm.

A configuration if the real provider uses RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/jwks
          audiences:
            - catalog-api
          jws-algorithms:
            - RS512
~~~

Only change the algorithm after verifying the provider signs with it. If the provider uses RS256, forcing RS512 will cause tokens to be rejected; that is the intended behavior.

### 7.3. Key Rotation

When the Authorization Server rotates signing keys:
- JWKS may publish both old and new keys concurrently during the transition period.
- The JWT `kid` header helps the decoder choose the matching public key.
- The Resource Server may cache JWKS and refresh it according to library mechanics.
- Tokens signed with the old key may need to remain verifiable until they expire per policy.
- If JWKS lacks the new key, tokens valid per the IdP may be temporarily rejected.

Do not copy/paste public keys into code and forget key rotation if the infrastructure uses JWKS. Never disable signature validation to “bypass” a JWKS error: check cache, key id, trusted endpoint, TLS, and clock.

### 7.4. Untrusted JWKS from Token Input

A JWT header can contain `jku` or `x5u` in some profiles. Never allow the token itself to dictate a URL from an arbitrary host to fetch public keys. Keys and issuers must be bound to trusted configuration/allowlists. This is a commonly overlooked issue in custom decoders.

## 8. How Are SCOPE_* Authorities Created?

Spring Security Resource Server typically converts scopes from the `scope` claim (space-delimited string) or `scp` into GrantedAuthorities prefixed with `SCOPE_`.

Example valid token:

~~~json
{
  "sub": "reader-42",
  "aud": ["catalog-api"],
  "scope": "catalog.read orders.write"
}
~~~

Authorities may be:

~~~text
SCOPE_catalog.read
SCOPE_orders.write
~~~

Security rules:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/catalog")
            .hasAuthority("SCOPE_catalog.read")
        .pathMatchers(HttpMethod.POST, "/api/orders")
            .hasAuthority("SCOPE_orders.write")
        .anyExchange().denyAll())
~~~

**Notes:**
- `hasAuthority("SCOPE_catalog.read")` checks the exact string.
- `hasRole("ADMIN")` normally checks `ROLE_ADMIN`, **not** `SCOPE_admin`.
- A token having the right scope does not by itself prove object ownership; domain access checks are needed.
- If the provider stores scopes in a different claim, an intentional custom JWT authorities converter is needed.

### 8.1. Custom Authorities Converter in Reactive

Spring Security 6.5 provides `ReactiveJwtAuthenticationConverter` and `ReactiveJwtAuthenticationConverterAdapter`. With a synchronous `JwtAuthenticationConverter`:

~~~java
// Configuration snippet; include full imports in the corresponding project.
JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
scopes.setAuthoritiesClaimName("permissions");
scopes.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopes);

var reactiveConverter =
        new ReactiveJwtAuthenticationConverterAdapter(converter);

http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(reactiveConverter)));
~~~

Use this only when the provider actually issues the `permissions` claim in a known format and that claim is **signed/verified**. Never read JSON request bodies, user-controlled cookies, or untrusted headers to grant GrantedAuthorities.

### 8.2. Do Not Let the Issuer Grant Unchecked Internal Privileges

Even a valid token with `scope=orders.write` must still check:
- The token audience matches the API.
- The user/client has permission on the specific tenant/resource.
- Whether a machine-to-machine client is permitted to perform this operation.
- Organization least-privilege and revocation/entitlement policies.

Do not blindly map every scope to `ROLE_ADMIN`. Role and tenant mapping must be reviewed as a system security policy.

## 9. Authentication vs Authorization: 401 and 403

| Situation | Error layer | Typical HTTP | How to handle |
| --- | --- | --- | --- |
| Protected GET without Bearer | Unauthenticated | **401** | Supply an access token |
| Bearer with invalid signature | Authentication failed | **401** | Obtain a valid token; do not disable verification |
| Expired Bearer | Authentication failed | **401** | Refresh/re-authorize at OAuth client |
| Bearer with wrong issuer or audience | Authentication failed | **401** | Fix issuer/resource target; do not drop validation |
| Malformed Bearer header or multiple credentials | Syntax/protocol | **400 or 401**, depending on error handler | Fix how the header is sent; check RFC 6750 |
| Valid JWT without `catalog.read` | Authorization | **403** | Grant scope/permission per policy |
| Valid JWT, sufficient scope, but object belongs to another tenant | Domain authorization | **403** or intentional 404 | Protect object-level access |
| Valid JWT, sufficient permission, invalid order payload | Request/business | **400/409/422** per contract | Fix request or handle conflict |
| JWKS/IdP unreachable when key fetch is needed | Dependency/security infrastructure | May be auth failure/5xx depending on stage | Check network/cache; do not weaken verification |

### 9.1. WWW-Authenticate: Bearer

A response missing credentials per RFC 6750 typically includes:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

An invalid token can result in:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

An authenticated user lacking a scope may receive:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

These are **protocol examples**; actual headers may include additional realm, error_description, or vary by Spring Security configuration. Do not unnecessarily test exact strings or accidentally strip `WWW-Authenticate` when writing custom error handlers.

### 9.2. Why Doesn't @RestControllerAdvice Catch All 401s?

Because the Resource Server WebFilter can reject the request **before DispatcherHandler/controller**. `@RestControllerAdvice` primarily handles exceptions thrown along the handler/controller path, not security filters' entry points or failure handlers.

If a JSON body is needed for JWT errors:
- Configure `ServerAuthenticationEntryPoint` / failure handler / `ServerAccessDeniedHandler` appropriately at the security layer.
- Preserve HTTP 401/403 and the Bearer challenge.
- Do not let the response body leak raw tokens, signing keys, or stack traces.
- Test missing token, invalid token, expired token, and insufficient scope.

## 10. What Does a “Stateless” JWT Resource Server Mean?

An API that only uses Bearer tokens **explicitly** placed by the client in `Authorization` usually does not need a server-side login session. On each request:
1. The client sends the token.
2. The Resource Server verifies the token.
3. Authentication is created in the request/reactive context.
4. The controller/service processes the request.
5. The request finishes without needing to store authentication in `WebSession`.

You can configure:

~~~java
.securityContextRepository(
        NoOpServerSecurityContextRepository.getInstance())
~~~

This tells Spring Security not to persist `SecurityContext` across sessions in that chain. It does **not** mean the whole WebFlux app cannot have a `WebSession` if another controller/filter calls `getSession()`, nor does it automatically mean tokens cannot be replayed.

### 10.1. When Is Disabling CSRF Valid in a Bearer-Only API?

For an API that genuinely only accepts Bearer tokens placed manually in the `Authorization` header, browsers do not automatically send this credential the way they send session cookies/form logins, so traditional CSRF risk can be lower. When the threat model confirms **no ambient credentials are used**, many Bearer-only APIs configure:

~~~java
.csrf(ServerHttpSecurity.CsrfSpec::disable)
~~~

This is **not advice to disable CSRF by default for every WebFlux app**. If the same app uses cookie login, browser-cached HTTP Basic, OAuth2 Login sessions, or endpoints relying on ambient credentials, CSRF must be evaluated separately, potentially using **multiple SecurityWebFilterChains** with route-specific matchers.

In the demo below, we disable CSRF because we are **only simulating a Bearer-only API**, with no form login or cookie authentication. If browser session authentication is added to the same chain, this decision must be revisited.

### 10.2. CORS Does Not Replace CSRF and Does Not Grant Permissions

A frontend at `http://localhost:5173` calling an API at `http://localhost:8080` with an `Authorization` header may require a CORS preflight. CORS only controls whether browsers are allowed to communicate cross-origin; it does not validate JWTs or grant scopes.

Do not do `permitAll OPTIONS/**` and assume CORS is fully configured. Use proper WebFlux CORS config/filters, verify preflight runs before authentication, and test actual requests. Conversely, disabling CORS does not block `curl` or non-browser clients.

## 11. Runnable Project: Java 17 + Spring Boot WebFlux Resource Server JWT

Illustrative project:
- `GET /public/ping`: public.
- `GET /api/catalog`: requires `SCOPE_catalog.read`.
- `POST /api/orders`: requires `SCOPE_orders.write`.
- `GET /api/whoami`: authenticated JWT, returns **safe metadata** (no raw token).
- `anyExchange().denyAll()`: default deny.
- JWT issuer/JWKS/audience policy configured explicitly.
- HTTP Bearer tests via a **mock ReactiveJwtDecoder**, focusing on the filter/authz flow without needing a live IdP over the network.
- Authorization-only tests via `mockJwt()`, used when testing the JWT decoder is not required.

Uses **Java 17, Spring Boot 3.5.7, Spring Security Reactive 6.5.x** with Gradle. These specific versions are a reference setup for the lesson; production requires patched and organization-supported releases. The sample IdP address is a **documentation placeholder** and cannot verify real tokens until replaced with an active trusted issuer/JWKS.

### 11.1. Structure

~~~text
reactive-jwt-resource-server/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── BearerJwtWebFluxTest.java
        └── JwtAuthorizationMockTest.java
~~~

### 11.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-jwt-resource-server'
~~~

### 11.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-resource-server` pulls in Resource Server and JOSE/JWT support via dependency management. You **do not need** `spring-boot-starter-oauth2-client` for an API that only receives JWTs from clients; the OAuth2 Client starter is for when the application itself performs authorization flows or calls downstream services with authorized clients.

### 11.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: reactive-jwt-resource-server
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/jwks
          audiences:
            - catalog-api
~~~

This describes:
- `issuer-uri`: the issuer the decoder must accept.
- `jwk-set-uri`: the endpoint to fetch public signing keys; set explicitly to avoid needing metadata discovery.
- `audiences`: the JWT access token must contain an `aud` matching `catalog-api`.

**There is no IdP at the example hostname.** The app can start for local/mock tests, but accepting real JWTs requires connecting to a valid issuer/JWKS. Do not “quickly craft” an `alg=none` token and configure the API to accept it just to avoid configuring an IdP.

### 11.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Bearer-only demo ONLY: no cookie/form/Basic login.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/catalog")
                                .hasAuthority("SCOPE_catalog.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders")
                                .hasAuthority("SCOPE_orders.write")
                        .pathMatchers(HttpMethod.GET, "/api/whoami")
                                .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Analysis:**
1. No session authentication: `NoOpServerSecurityContextRepository`.
2. CSRF is disabled **only because of the Bearer-only simulation conditions**; do not apply mechanically to cookie/browser apps.
3. Basic/form login are disabled so authentication responses use Bearer instead of HTML redirects or Basic challenges.
4. `/api/catalog` and `/api/orders` check authorities mapped from scopes.
5. `/api/whoami` only requires a verified JWT, without a specific scope.
6. `denyAll()` catches undeclared requests, including other HTTP methods.
7. `oauth2ResourceServer(...jwt(...))` enables the Reactive JWT decoder auto-configured by Boot from `application.yml`.
8. Do not declare an unnecessary custom decoder, avoiding accidentally losing Boot's issuer/audience validators.
9. Object-level authorization is not yet present in the demo, so production must add tenant/ownership policies in the service layer.

### 11.7. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record CreateOrderRequest(String sku, int quantity) {
    }

    public record OrderReceipt(String status, String sku, int quantity) {
    }

    @GetMapping(path = "/public/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(path = "/api/catalog",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<String>> catalog() {
        return Mono.just(List.of("BOOK", "PEN", "NOTE"));
    }

    @GetMapping("/api/whoami")
    public Mono<Map<String, Object>> whoAmI(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "audience", jwt.getAudience()));
    }

    @PostMapping(path = "/api/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<OrderReceipt> createOrder(
            @RequestBody Mono<CreateOrderRequest> request) {
        return request.map(value -> {
            if (value.quantity() < 1 || value.sku() == null
                    || value.sku().isBlank()) {
                throw new IllegalArgumentException(
                        "sku and quantity must be valid");
            }
            return new OrderReceipt(
                    "ACCEPTED", value.sku(), value.quantity());
        });
    }
}
~~~

In a real application, use `@Validated` and dedicated 4xx exception mapping for invalid requests; in the demo, tests only send valid payloads. `IllegalArgumentException` does not default to 400 across all WebFlux handlers, so do **not** treat it as proof of a production error contract.

`OrderReceipt` is merely an illustrative result, **not saved to a database** or creating a real transaction. HTTP 201 shows the demo API's intent; when implementing real business logic, you need transactions, idempotency keys, object-level authorization, and stock/tenant checks.

`whoAmI` intentionally does not return `jwt.getTokenValue()`, the `Authorization` header, or all claims. Even subject/audience are metadata that should be protected by policy; this endpoint already requires authentication.

## 12. Testing Real HTTP Bearer with a Mock Decoder

Two test styles are easily confused:
1. **Sending an HTTP `Authorization: Bearer ...` header** into Spring Security WebFilters and mocking `ReactiveJwtDecoder` to test the converter, AuthenticationWebFilter, manager, authorities, and authorization.
2. Using `mockJwt()` to inject authentication directly, bypassing JWT decoding. Suitable for authorization/controller unit/integration tests.

This section uses approach **(1)**. It genuinely sends the Bearer header via `WebTestClient`, but **the decoder is mocked**, so it does **not** prove signature/issuer/audience/exp validation.

### 12.1. BearerJwtWebFluxTest.java

`src/test/java/demo/BearerJwtWebFluxTest.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BearerJwtWebFluxTest {

    @Autowired
    ApplicationContext context;

    // Spring Framework 6.2+; replaces real decoder with mock for tests.
    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        when(jwtDecoder.decode("reader-token"))
                .thenReturn(Mono.just(jwt(
                        "reader-token", "reader-42", "catalog.read")));
        when(jwtDecoder.decode("writer-token"))
                .thenReturn(Mono.just(jwt(
                        "writer-token", "writer-99",
                        "catalog.read orders.write")));
        when(jwtDecoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("invalid JWT for test")));
    }

    private Jwt jwt(String value, String subject, String scopes) {
        Instant now = Instant.now();

        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", "https://idp.example.test/realms/demo")
                .claim("sub", subject)
                .claim("aud", List.of("catalog-api"))
                .claim("scope", scopes)
                .issuedAt(now.minusSeconds(30))
                .expiresAt(now.plusSeconds(600))
                .build();
    }

    @Test
    void publicRouteNeedsNoBearer() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingBearerIs401WithChallenge() {
        client.get().uri("/api/catalog")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                .valueMatches("WWW-Authenticate", "Bearer.*");
    }

    @Test
    void malformedOrInvalidJwtIs401() {
        client.get().uri("/api/catalog")
                .headers(h -> h.setBearerAuth("bad-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validReaderScopeCanReadCatalog() {
        client.get().uri("/api/catalog")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0]").isEqualTo("BOOK");
    }

    @Test
    void authenticatedReaderWithoutWriteScopeGets403() {
        client.post().uri("/api/orders")
                .headers(h -> h.setBearerAuth("reader-token"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CreateOrderRequest(
                        "BOOK", 1))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void writerWithWriteScopeCanCreate() {
        client.post().uri("/api/orders")
                .headers(h -> h.setBearerAuth("writer-token"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CreateOrderRequest(
                        "BOOK", 2))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ACCEPTED")
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.quantity").isEqualTo(2);
    }

    @Test
    void validJwtShowsSafePrincipalDetails() {
        client.get().uri("/api/whoami")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("reader-42")
                .jsonPath("$.audience[0]").isEqualTo("catalog-api")
                .jsonPath("$.tokenValue").doesNotExist();
    }

    @Test
    void writerCannotUseUnlistedRoute() {
        client.get().uri("/api/unlisted")
                .headers(h -> h.setBearerAuth("writer-token"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

### 12.2. Why Is This a Filter Integration Test Rather Than Signature Validation?

- WebTestClient creates a real HTTP request inside the mock WebFlux application context.
- `ServerBearerTokenAuthenticationConverter` sees the Bearer header.
- `JwtReactiveAuthenticationManager` invokes the `ReactiveJwtDecoder` bean.
- `@MockitoBean` makes the decoder return a pre-built `Jwt`, **without verifying any signature**.
- JwtAuthenticationConverter maps `scope` to `SCOPE_...`.
- AuthorizationWebFilter decides 200/201/401/403 based on rules.
- The controller runs only if the request passes the appropriate security checks.

**Very important:** The fake JWT `reader-token` is not a real token and does not have three JWS parts. It “works” in the test because the decoder is mocked. Sending this string to a running app with a real `NimbusReactiveJwtDecoder` will be rejected with 401.

### 12.3. Role of @MockitoBean

`@MockitoBean` belongs to Spring Framework Test 6.2+, available in Spring Boot 3.5.x. It replaces/registers a mock for the decoder in the test `ApplicationContext`; this differs from production configuration. Never keep a mock decoder in `src/main` or an active production-profile bean, as doing so could allow forged tokens past the system.

In older projects, you may see Spring Boot's `@MockBean`, but newer versions provide the `@MockitoBean` API. In this lesson, use compatible Spring Boot 3.5.7 / Spring Framework 6.2 dependencies.

### 12.4. Running Tests

In the project directory:

~~~bash
gradle test
~~~

If using the Wrapper: `./gradlew test` or `gradlew.bat test`. **8 tests** are expected in this class to verify the corresponding flows; that expectation comes from reading the code, **not a report of an actual Gradle run**.

If a 401 HTTP test fails, check which security chain is active, whether the mock decoder receives the expected token string, whether a proxy/other filter modified the Bearer header, and whether `springSecurity()` was properly applied to `WebTestClient`.

## 13. Testing Authorization Separately with mockJwt()

When you only want to test controllers/access policies, Spring Security Test provides `SecurityMockServerConfigurers.mockJwt()`. It creates a simulated authentication, **without calling `ReactiveJwtDecoder` and without verifying signature/issuer/audience**.

### 13.1. JwtAuthorizationMockTest.java

`src/test/java/demo/JwtAuthorizationMockTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class JwtAuthorizationMockTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void scopeCanBeSuppliedViaMockJwt() {
        client.mutateWith(mockJwt()
                    .jwt(jwt -> jwt
                            .claim("sub", "mock-user")
                            .claim("scope", "catalog.read")))
                .get().uri("/api/catalog")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void missingScopeIsForbiddenEvenWhenJwtIsMocked() {
        client.mutateWith(mockJwt()
                    .jwt(jwt -> jwt
                            .claim("sub", "mock-user")
                            .claim("scope", "profile")))
                .get().uri("/api/catalog")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Here `mockJwt()` bypasses token parsing/validation and supplies a principal to the authorization layer. These are **2 additional tests**, requiring no real IdP. If a test uses a custom authorities converter, you can specify `.authorities(...)` explicitly or apply the matching converter to avoid confusing “scope in claim” with “present GrantedAuthorities”.

### 13.2. Two Test Types Answer Two Different Questions

| Test type | Sends Authorization header through filter? | Real decode? | What it proves |
| --- | --- | --- | --- |
| `mockJwt()` | Not required | No | Route/permission/controller behavior once authenticated |
| HTTP Bearer + mocked ReactiveJwtDecoder | **Yes** | No | Token extraction, error path, JWT-to-authorities, authorization |
| HTTP Bearer + Nimbus decoder + signed fixture/JWKS test server | **Yes** | **Yes** | Signature, algorithm, issuer, audience, timestamps, and integration |
| Browser/IdP staging | Depends on client | **Yes** | Complete deployment, key rotation, discovery, gateway, TLS, token lifecycle |

Therefore, **no** `mockJwt()` test proves that an `alg=none` token will be rejected in production. To prove that, you must test the real decoder/JWS validation using negative fixtures.

## 14. Testing Real JWT Validation: Test Plan with JWKS and RSA

In test/staging environments, you should have an Authorization Server/JWKS test fixture or an embedded test HTTP server serving JWKS public keys. Test one **validly signed** JWT and invalid variants as follows:

| Case | Setup | Expected result |
| --- | --- | --- |
| Happy path | Valid signature, expected issuer/audience, valid exp/nbf | Authentication succeeds |
| Wrong signature | Token signed by private key not matching trusted JWKS | 401 |
| Unknown kid | Header kid absent from trusted JWKS | 401 |
| Unsupported alg | Header alg not in allowlist | 401 |
| alg=none | Unsigned JWT under disallowed profile | 401 |
| Wrong issuer | Valid signature but `iss` is not a trusted issuer | 401 |
| Wrong audience | `aud` does not contain catalog-api | 401 |
| Expired token | exp is earlier than current time beyond clock skew | 401 |
| nbf in the future | Token is not yet valid | 401 |
| Missing scope | Valid JWT, lacks catalog.read | 403 on /api/catalog |
| Correct scope, wrong tenant | Has scope but does not own tenant/object | 403 or intentional 404 |
| Key rotation | JWKS publishes new key and decoder refreshes per policy | Valid token accepted |
| JWKS unavailable | Key cached or uncached; outcome depends on config | Must not bypass signature to return 200 |

**Do not build negative fixtures by altering a payload and making a mock decoder return that payload**, as that bypasses signature validation. Each test must exercise the exact layer it intends to prove.

### 14.1. What Once a Token Is Revoked?

Offline JWT validation does not automatically know that an access token was just revoked at the IdP. A token with a valid `exp` and valid signature can still be accepted until expiry if no additional mechanism exists.

System-dependent options:
- Short access token TTL.
- Introspection instead of offline JWT for certain APIs/flows.
- Revocation store/deny-list by `jti` for specific scenarios.
- Emergency key rotation, understanding its impact on all tokens sharing that key.
- DPoP/mTLS-bound access tokens.
- Gateway policy/continuous access evaluation when supported by the platform.

Do not claim “JWT is stateless so it has instant logout/revocation” — that is a design decision, not a guarantee of the token format.

## 15. curl Commands: Distinguishing Local Demo from a Real IdP

Start the app:

~~~bash
gradle bootRun
~~~

Public endpoint:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expect `200 OK`, body `pong`.

Protected endpoint without token:

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Expect **401 Unauthorized** and `WWW-Authenticate: Bearer` because it is unauthenticated.

Token with invalid format/signature:

~~~bash
curl -i http://localhost:8080/api/catalog \
  -H 'Authorization: Bearer not-a-real-jwt'
~~~

Expect **401 Unauthorized**, because the real Nimbus Reactive JWT decoder cannot verify a fake string.

**You cannot** use `reader-token` / `writer-token` from the unit tests against the running app. Those strings are only accepted by the test mock `ReactiveJwtDecoder`. If you want to test the happy path with curl, use **a real access token issued by a trusted Authorization Server for catalog-api**, over TLS in an appropriate environment:

~~~bash
# Do not commit tokens; obtain one through your test environment's flow.
curl -i https://your-api.example.test/api/catalog \
  -H "Authorization: Bearer <valid-access-token-for-catalog-api>"
~~~

This is a sample command: the bracketed string must be replaced with a real access token; it is not a pre-provisioned credential. Avoid typing production tokens in shared terminals or storing them in history/logs. Temporary environment variables with proper secret-handling policies can be used instead.

With a valid JWT having `catalog.read`: expect 200 and the catalog list. With a valid JWT having `orders.write` and a valid JSON body:

~~~bash
curl -i -X POST https://your-api.example.test/api/orders \
  -H "Authorization: Bearer <valid-access-token-for-catalog-api>" \
  -H 'Content-Type: application/json' \
  --data '{"sku":"BOOK","quantity":2}'
~~~

Expect **201 Created** in the demo if the real token has the required scope. If the scope is insufficient, 403. If issuer/audience is wrong or the token is expired, 401.

## 16. Multi-Tenancy, Multiple Issuers, and Token Confusion

An API may serve multiple tenants or multiple Authorization Servers. A common risk is trusting `iss`/`aud`/tenant claims too broadly.

### 16.1. Do Not Build a Decoder from a Client-Supplied Issuer

Incorrect pseudocode:

~~~java
// WRONG, not a production implementation:
String issuer = unverifiedJwtPayload.get("iss");
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(issuer);
return decoder.decode(token);
~~~

If the issuer is chosen by an attacker, the server could call malicious URLs (SSRF), fetch attacker keys, or break trust boundaries. Replace with a configured issuer allowlist:

~~~text
trusted issuer A -> verifier/key set A -> tenant policy A
trusted issuer B -> verifier/key set B -> tenant policy B
unrecognized issuer -> reject
~~~

Spring Security provides `JwtIssuerReactiveAuthenticationManagerResolver` for multi-tenant trusted issuer resolution. It is an architectural tool and does not exempt you from checking the trusted-issuer allowlist, audience, and resource ownership.

### 16.2. A Token with a Scope Does Not Automatically Have Access to Every Tenant

Even with `SCOPE_orders.write`, the API must restrict which tenant a user/client can write orders into. Bind the tenant to the principal and entity ID in the service layer, not just to a client-chosen URL parameter.

Do not authorize solely via a `tenant_id` claim if it is not issued by a trusted issuer under contract and verified; even a valid claim must still be checked against the resource's tenant/current entitlements.

### 16.3. Different Token Profiles

An issuer may issue:
- ID tokens for frontends.
- JWT access tokens for APIs.
- Opaque tokens for introspection clients.
- Tokens for multiple audiences and scopes.

Do not accept a token of the wrong profile just because it shares the same issuer and signature. When the Authorization Server supports the RFC 9068 JWT Access Token Profile, also check the token type/header and profile claims. Protect against token substitution and cross-resource token confusion.

## 17. Bearer Token Propagation via WebClient: When Is It Needed?

Resource Server A may need to call API B. Depending on the contract, you can:
- Forward the caller's token **if** the token is also issued for API B and policy allows it.
- Perform token exchange to obtain a token with API B as the audience.
- Use the backend's own client credentials if it is a service-level action.
- Avoid forwarding the user token when the downstream service does not need it.

Spring Security Reactive provides `ServerBearerExchangeFilterFunction`:

~~~java
// @Bean snippet; requires WebClient and Spring Security imports.
@Bean
WebClient downstreamWebClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
~~~

This filter can extract the Bearer token from the current Authentication and attach it to the `Authorization` header of outbound requests. It does **not** automatically refresh expired tokens like an OAuth2 Client authorized-client manager.

**Security:** do not attach this filter to a `WebClient` used to reach arbitrary user-supplied URLs; otherwise, the token could be sent to an attacker's host. Restrict trusted downstream hosts, audience/resource binding, retries, and logging. If B requires its own audience, forwarding A's token as-is may yield 401 — that indicates the token was designed for a different API, so do not disable audience validation.

### 17.1. API Gateway and Header Preservation

When running behind a gateway:
- HTTPS from client to edge and on internal hops per policy.
- The `Authorization` header is not stripped or mistakenly altered by the gateway.
- Gateway-level authentication alone does not automatically replace API authorization.
- If the gateway forwards a trusted identity header, use mTLS/proxy trust and strip untrusted incoming headers; never unconditionally trust a client-supplied `X-User-ID` instead of Bearer validation.
- Do not log the `Authorization` header in access logs, WAF, CDN, or distributed tracing.

## 18. Common Pitfalls and How to Fix Them

| Anti-pattern | Consequence | Resolution |
| --- | --- | --- |
| Assuming a three-part JWT is valid | Header/payload can be forged | Use ReactiveJwtDecoder/JWS verification |
| Verifying signature only, skipping issuer/audience | Accepts tokens meant for other clients/resources | Issuer + audience + exp/nbf validators |
| Accepting `alg=none` | Bypasses signing | Algorithm allowlist and safe JOSE decoder |
| Fetching JWKS from arbitrary `jku` | SSRF / attacker-controlled keys | Trusted JWK Set URI / issuer allowlist |
| Sending an ID token as an API Bearer | Wrong audience, token substitution | Use an access token intended for the API |
| Using a refresh token to call APIs | Exposes credential for wrong purpose | Refresh at Authorization Server |
| Defaulting every scope to ROLE_ADMIN | Privilege escalation | Map permissions from trusted sources |
| Skipping object/tenant authorization | Users read other users' objects | Ownership/ABAC/RBAC in service layer |
| Enabling `setDefaultOAuth2AuthorizedClient` or propagating to any URL | Outbound token leak | Scope WebClient to trusted hosts |
| Disabling CSRF app-wide because Bearer exists | Browser cookie flows exposed to CSRF | Per-chain threat model |
| Thinking disabling CSRF also disables CORS | Two independent mechanisms | CORS before authentication, CSRF per client |
| Calling `block()` inside WebFlux | Blocks event loop | Mono/map/flatMap |
| Using Servlet `BearerTokenAuthenticationFilter` | Wrong stack | Reactive AuthenticationWebFilter |
| Reading ThreadLocal `SecurityContextHolder` as in Servlet | Authentication unreliable across reactive hops | Reactor Context / ReactiveSecurityContextHolder |
| Confusing `JwtAuthenticationToken` with `OidcUser` | Wrong principal type | Separate Resource Server and OAuth2 Login |
| Testing with `mockJwt` and concluding signature validation PASSES | Mock bypasses decoder | Test JWKS/real JWT separately |
| Sending `reader-token` from tests to production | Unsigned token, 401 | Use real tokens in controlled environments |
| Disabling verification to “fix 401” | Authentication bypass | Fix issuer/JWKS/alg/aud |
| Treating every 403 as a bad token | Could be missing scope/CSRF/tenant | Check which layer emitted the error |
| Logging tokens for debugging | Credential leak | Redact Authorization and raw JWTs |
| Assuming instant JWT revocation | Offline tokens remain valid until exp | Short TTL / revocation strategy |

## 19. Step-by-Step Debugging

### Protected GET Returns 401

1. Is the header genuinely `Authorization: Bearer <token>`?
2. Did a gateway/proxy strip the header?
3. Is the token an access token rather than an ID token?
4. Does the string have valid JWS structure and signature?
5. Does issuer `iss` match the configured issuer?
6. Does audience `aud` contain the appropriate resource ID?
7. `exp`/`nbf` and clock skew?
8. Is the algorithm permitted by the decoder?
9. Is `kid` present in the trusted JWKS? Are key rotation and caches updated?
10. Are TLS and the JWKS endpoint reachable?
11. What error is returned in `WWW-Authenticate` (without logging the token)?
12. Did the request enter the right security chain?

**Never disable audience or signature validation to fix a 401.** If a token has a different audience, request a token issued for the right resource server.

### GET Returns 200, POST Returns 403

1. Is the JWT valid with `catalog.read` scope while missing `orders.write`?
2. Does the API have a method-specific rule for POST?
3. Are object/tenant-level checks denying it?
4. If the application mixes in cookie login, is the CSRF filter blocking POST?
5. Does browser CORS preflight allow `Authorization` and `Content-Type`?
6. Are there multiple security chains with different matchers or ordering?
7. Did the request pass converter/decoder and get blocked by `AuthorizationWebFilter`?
8. Is a custom authority converter mapping claims with the wrong prefix?

### JWT from Issuer A Works, Issuer B Fails

- Does the system actually allow multiple issuers?
- Does Issuer B have its own trust/key set?
- Is B's audience targeting the right API?
- Is there an issuer allowlist for multi-tenancy?
- Key rotation/truststore/clock?
- Do not dynamically accept issuers from requests.

### Mock Tests PASS, Production Returns 401

- Mock JWTs can skip signature/issuer/audience/expiry checks.
- Production config only accepts policy-approved signing algorithms.
- Real tokens have different `aud`/scopes than mocks.
- JWKS and IdP endpoints are absent in local tests.
- The Resource Server is receiving an ID token instead of an access token.

This is why **at least two test layers** are required: authorization mocks and JWT validation integration tests.

## 20. Pre-Production Security Checklist

### HTTP and Token Handling

- [ ] HTTPS/TLS for client-to-API and trusted internal hops.
- [ ] `Authorization: Bearer` header is the default channel; never put tokens in query strings.
- [ ] No secrets/token values in logs, error bodies, or telemetry.
- [ ] JWTs do not carry unnecessary sensitive data because payloads are generally readable.
- [ ] Short-lived access tokens and appropriate revocation/refresh policies.
- [ ] Do not return the Jwt object/raw token in DTOs.

### JWT Validation

- [ ] Only trusted issuers and trusted JWKS endpoints.
- [ ] Signature verified with approved keys/algorithms.
- [ ] `aud` matches the resource server; reject web client ID tokens.
- [ ] `exp`/`nbf`/`iat` and clock skew evaluated.
- [ ] Header `alg`/`kid`/`typ` profiles handled safely.
- [ ] Key rotation, JWKS caching, and outage behavior tested.
- [ ] Never accept `jku`/`x5u` outside an allowlist.
- [ ] Opaque access tokens are not routed through a JWT decoder.

### Authorization

- [ ] Scopes/authorities mapped correctly to `SCOPE_` or via a reviewed claim converter.
- [ ] `hasAuthority` and `hasRole` are not mixed up.
- [ ] Default-deny HTTP method/route matchers.
- [ ] Object ownership and tenant boundaries enforced.
- [ ] Machine client tokens do not automatically gain user privileges.
- [ ] Multi-issuer resolution restricted to trusted issuers.

### Reactive, Browser, and Operations

- [ ] Proper Spring Security Reactive classes: `ServerHttpSecurity` / `SecurityWebFilterChain`.
- [ ] No blocking or manual `subscribe()` inside the authentication chain.
- [ ] SecurityContext repository/stateless policy explicitly chosen.
- [ ] CSRF not disabled if browser ambient credentials exist.
- [ ] CORS preflight works when an SPA needs the `Authorization` header.
- [ ] Entry point 401 and access-denied 403 preserve Bearer semantics.
- [ ] WebClient does not propagate tokens to untrusted hosts.
- [ ] Monitoring includes request ID, route, and auth result, without raw tokens.

### Tests

- [ ] Missing token -> 401 + Bearer challenge.
- [ ] Invalid token -> 401.
- [ ] Valid token + correct scope -> 200/201.
- [ ] Valid token + insufficient scope -> 403.
- [ ] Safe Jwt principal DTO does not expose token.
- [ ] Different issuer/audience/key/expiry negatives tested via real decoder.
- [ ] Key rotation JWKS fixture.
- [ ] Ownership/tenant authorization negatives.
- [ ] Mock tests are not treated as signature-validation tests.
- [ ] Gateway/header forwarding, TLS, CORS/CSRF, and session behavior verified on staging.

## 21. Self-Check Questions

**1. What does a Bearer token mean?**

> Whoever holds a valid credential can present it to call the API within its permissions and lifetime; if stolen, it can be replayed.

**2. Is the Bearer converter a JWT decoder?**

> No. `ServerBearerTokenAuthenticationConverter` extracts the Bearer string from the request; `ReactiveJwtDecoder` verifies the JWS and claims.

**3. Which authentication manager does Spring Security Reactive use for JWTs?**

> Typically `JwtReactiveAuthenticationManager`, implementing `ReactiveAuthenticationManager`.

**4. Which principal does a controller receive after a JWT Resource Server?**

> Typically `Jwt` inside `JwtAuthenticationToken`, not `OidcUser` from OAuth2 Login.

**5. Is a valid signature enough for the API to accept a JWT?**

> No. Appropriate issuer, audience, `exp`/`nbf`, algorithm, and policy checks are also required.

**6. Why does `scope=catalog.read` become `SCOPE_catalog.read`?**

> Spring Security's default JWT authorities converter prepends the `SCOPE_` prefix.

**7. How do missing token and insufficient scope differ in HTTP status?**

> Typically 401 for missing/invalid credentials, and 403 for an authenticated user lacking permission.

**8. Can an ID token be used as `Authorization: Bearer` to `orders-api`?**

> No. An ID token is for the OIDC client; the API expects an access token intended for its own resource.

**9. Does `NoOpServerSecurityContextRepository` prevent the API from using authentication?**

> No. Authentication is still created per request; it just is not saved as a server session security context.

**10. When is disabling CSRF reasonable?**

> When the API genuinely only uses client-sent Bearer tokens and has no browser ambient credentials; a clear threat model is required.

**11. Can `mockJwt()` test signature verification?**

> No. It bypasses the decoder and only tests security decisions after authentication is simulated.

**12. How should a wrong audience be fixed?**

> Request an access token for the right resource and configure the expected audience, rather than removing validation.

**13. Does an expired JWT automatically expire the refresh token?**

> No. Token lifetimes and refresh policies have separate lifecycles.

**14. If the JWKS key rotates, what must be done?**

> Ensure the trusted JWKS updates/decoder refreshes keys and test the transition period; do not disable verification.

**15. If a JWT is revoked at the IdP, does an offline Resource Server know immediately?**

> No. Short TTL policies, revocation/introspection/deny-list checks, or additional mechanisms are required.

## 22. Summary

The Bearer JWT mechanism in Spring Security WebFlux is a **Reactive** pipeline:

~~~text
Authorization: Bearer <JWT>
       -> ServerBearerTokenAuthenticationConverter
       -> JwtReactiveAuthenticationManager
       -> ReactiveJwtDecoder (signature + issuer/audience/time validation)
       -> JwtAuthenticationToken (principal=Jwt, authorities=SCOPE_...)
       -> Reactor SecurityContext
       -> authorizeExchange / method and object authorization
       -> Controller / Service
~~~

Maintain these three boundaries:
1. **A Bearer token is a replayable credential**, so require TLS, protect tokens, do not log them, and limit lifetimes.
2. **JWT authentication is not just payload decoding**: you must verify signature, issuer, audience, timestamps, and token profile per trust policy.
3. **Authentication is not automatically authorization**: scopes, roles, tenant, and object ownership must be enforced separately.

Use `spring-boot-starter-oauth2-resource-server`, `ServerHttpSecurity.oauth2ResourceServer(...jwt(...))`, and `issuer-uri/jwk-set-uri/audiences` to protect your API. Testing JWT authorization with mocks is useful, but must be complemented by real JWT/JWKS validation tests before production.

### Official References

- Spring Security 6.5 — OAuth 2.0 Resource Server JWT (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Bearer Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html
- Spring Security 6.5 — Testing Reactive OAuth2/JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot 3.5 — Spring Security Resource Server properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Security 6.5 Javadoc — JwtReactiveAuthenticationManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- Spring Security 6.5 Javadoc — ServerBearerTokenAuthenticationConverter: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html
- Spring Security 6.5 Javadoc — ReactiveJwtDecoder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html
- Spring Security — Reactive multi-tenancy: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700