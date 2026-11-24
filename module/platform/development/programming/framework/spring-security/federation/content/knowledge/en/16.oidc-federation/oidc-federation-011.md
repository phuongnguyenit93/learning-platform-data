# Boundaries with Authorization Server Configuration and Protecting APIs with Access Tokens

## 1. Goal and Real-World Scenario

A Java/Spring Boot application that has already implemented **SAML 2.0 federation** or **OpenID Connect (OIDC) login** can authenticate users successfully via an external IdP. When the same system also exposes REST APIs, a new question arises: **should the API trust the web application's SSO login session, or must it verify an OAuth 2.0 access token?** And if an access token is required, **who issues that token**?

Four roles must be distinguished:

- **SAML SP / OIDC Relying Party (RP)**: web application authenticating users via `SAMLResponse` or OIDC ID Token/authorization code, typically establishing its own `SecurityContext` and HTTP session.
- **OAuth 2.0 Client**: component requesting authorization grants and receiving access tokens from an Authorization Server, calling APIs on a user's behalf or via client credentials.
- **Authorization Server (AS)**: component managing registered clients, grants, consent, token endpoints, and signing keys, issuing access tokens/refresh tokens and, when OIDC is enabled, ID Tokens.
- **Resource Server (RS)**: API accepting Bearer access tokens, validating tokens and permissions before allowing reads/writes on resources.

**Enabling `oauth2Login` or `saml2Login` does not automatically turn an application into an Authorization Server. Enabling `oauth2ResourceServer` does not make an application sign or issue access tokens itself.** These features govern opposite sides of a trust boundary.

This lesson belongs to the **OIDC and Brokering** group: it explains the boundary when a broker verifies upstream identity and then issues or delegates permissions for downstream APIs. Examples target **Spring Boot 3.x / Spring Security 6.x / Java 17+**; Spring Security 7.x and Spring Authorization Server 1.x APIs have differences requiring pinned versions. `example.test` hostnames are illustrative data.

Learning objectives: distinguish ID Token/access token/session, recognize proper client/AS/RS configurations, configure a JWT Resource Server with `iss`/`aud`/signature/time/scope, understand opaque token introspection, design allowlisted multi-issuer APIs, separate web sessions from stateless Bearer APIs, test token substitution/mismatches, and avoid granting tenant access from unverified tokens.

## 2. Overall Model: Upstream Federation, Downstream OAuth 2.0

```mermaid
flowchart LR
    B["Browser"] -->|"SSO login"| W["Web App: SAML SP / OIDC Client"]
    W <-->|"SAMLRequest / SAMLResponse or OIDC Authorization Code"| U["Upstream IdP / OP"]
    W -->|"App session + cookie"| B
    AS["Downstream Authorization Server"] -->|"Issues access token"| C["OAuth2 Client / BFF"]
    C -->|"Authorization: Bearer access token"| API["Orders API: Resource Server"]
    API -.->|"Configured JWKS or introspection"| AS
    W -.->|"May itself be the client/BFF"| C
```

This diagram illustrates **roles**, not necessarily separate physical servers. Two common variants:

1. **OP is the AS**: the web app performs OIDC login with an OP, receives an access token issued by that OP/AS, and calls the API provided **the token was issued for the API's exact audience**.
2. **Identity broker**: the broker acts as SAML SP/OIDC RP upstream; if it also embeds a downstream Authorization Server, the broker **mints new tokens** using its own issuer and keys after verifying and linking the upstream identity. The API trusts the broker AS rather than necessarily trusting the SAML IdP directly.

**There is no default "SAMLResponse → JWT access token" step inside `saml2Login`.** Obtaining downstream tokens requires an Authorization Server, an approved grant/token-exchange profile, and an explicit authorization policy.

## 3. Responsibility Boundaries in Spring Security

| Role | Common Spring Security / Boot Setup | Outcome | Does Not Do |
| --- | --- | --- | --- |
| OIDC web client | `spring-boot-starter-oauth2-client`, `oauth2Login`, `ClientRegistrationRepository` | OIDC authentication, browser session, authorized client when applicable | Does not mint API tokens itself |
| SAML SP | `spring-security-saml2-service-provider`, `saml2Login`, `RelyingPartyRegistrationRepository` | Validates SAML Assertion, browser principal/session | Does not act as an OAuth2 AS |
| OAuth2 client calling APIs | `OAuth2AuthorizedClientManager` / authorized-client repository | Obtains/manages AS-issued access tokens | Does not replace API token verification |
| Authorization Server | `spring-boot-starter-oauth2-authorization-server` in Boot 3.x, Spring Authorization Server 1.x | Authorization code/token/introspection/JWKS, keys, registered clients | Does not automatically protect business APIs in other services |
| JWT Resource Server | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer().jwt()`, `JwtDecoder` | Verifies JWT access tokens, produces `JwtAuthenticationToken` | Does not issue JWTs |
| Opaque Resource Server | `oauth2ResourceServer().opaqueToken()`, `OpaqueTokenIntrospector` | Introspects tokens and maps scopes | Does not issue refresh tokens |
| Broker | Upstream client + downstream AS **if both sides are deployed** | Brokers identity, mints new tokens per downstream policy | Does not merely rename upstream tokens |

Spring Boot configures clients, resource servers, and authorization servers in **distinct property namespaces**. Copying `oauth2.resourceserver.jwt.issuer-uri` into a login app **does not create a `/oauth2/token` endpoint**.

## 4. Distinguishing SAMLResponse, ID Token, Access Token, and Cookie

| Artifact | Issued By | Valid Recipient | Purpose |
| --- | --- | --- | --- |
| SAML Response/Assertion | SAML IdP | SP ACS | Authenticates identity via SAML federation |
| OIDC ID Token | OIDC Provider | **OIDC client/RP** | Asserts authentication event, `iss`, `sub`, client `aud` |
| OAuth access token | OAuth Authorization Server | **Designated Resource Server** | Authorizes a client to access an API within granted scopes |
| Refresh token | AS | Authorized OAuth2 Client | Requests new access tokens; never sent to Orders API |
| Authorization code | AS | OAuth2 Client via redirect | Exchanged for tokens at token endpoint per PKCE/client auth |
| `JSESSIONID` / `SESSION` | SP/web app or Spring Session | Browser → exact web app | Maintains app session; not an API access token |
| Opaque token | AS | Used by client, introspected by RS | Reference access token without self-contained claims for API decoding |

**An ID Token is not an access token.** OIDC Core mandates that an ID Token's `aud` contain the **RP's client ID**. A JWT access token for Orders API must target **Orders API's** audience. An RS must never accept every JWT signed by the same OP as an API access token.

**A user logged into the web app does not mean the browser holds Bearer rights to backend APIs.** The web app may use server-side `OAuth2AuthorizedClientManager` to fetch access tokens and call APIs via a BFF while the browser holds only a BFF cookie. Alternatively, a public client/mobile app obtains tokens via Authorization Code + PKCE under separate configuration. These models differ in token storage and XSS/CSRF exposure.

## 5. Illustrative JWTs: Client Audience vs. API Audience

OIDC ID Token for client `portal-client`:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-1001",
  "aud": "portal-client",
  "iat": 1799999000,
  "exp": 1800000000,
  "nonce": "nonce-from-authorization-request"
}
```

JWT access token for Orders API:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-1001",
  "aud": ["orders-api"],
  "client_id": "portal-client",
  "scope": "orders.read orders.write",
  "iat": 1799999000,
  "exp": 1800000000,
  "jti": "example-access-token-id"
}
```

Both JSON blocks **describe claims only**—they are not complete JWTs, carry no signatures, and cannot log in or call APIs. Timestamps are sample numbers with no guarantee of validity at reading time.

If a system uses the **RFC 9068 JWT access token profile**, the header also includes `typ=at+jwt` or `application/at+jwt` alongside a valid JWS algorithm and signature. ASs not using RFC 9068 may follow a custom profile; the API must validate the exact profile/token type committed by the AS, rather than just checking three Base64URL JWT segments.

**Never assume `sub` is always an internal user ID**: subjects are issuer-scoped, and `client_credentials` tokens may represent an application rather than a human user.

## 6. Where Is the Authorization Server Configured?

If an organization needs to **issue its own OAuth tokens**, build a dedicated Authorization Server application or an explicitly configured AS role. In Spring Boot 3.x / Spring Authorization Server 1.x, the core dependency is:

```groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-oauth2-authorization-server"
}
```

This is a **Gradle fragment** assuming the project already configures Java/Spring Boot plugins, BOM, repositories, and Java 17+. The AS also requires:

- `RegisteredClientRepository`: client IDs, client authentication methods, redirect URIs, grant types, scopes, consent, and PKCE policies.
- `OAuth2AuthorizationService`: persists authorizations/refresh tokens and their states.
- `AuthorizationServerSettings`: issuer and protocol endpoint paths.
- `OAuth2TokenGenerator` / `OAuth2TokenCustomizer`: token issuance and claim/format customization.
- `JWKSource`, key management, and rotation for signed JWTs.
- User authentication mechanism for grants requiring a resource owner; OIDC support when the AS also acts as OP.
- CSRF, consent, sessions, rate limiting, and auditing tailored to protocol endpoints and infrastructure.

Spring Security 7.x now houses Authorization Server documentation directly inside Spring Security. **Choose class/package APIs matching your exact release**, never mixing Spring Authorization Server 1.x and Spring Security 7.x snippets.

### Typical AS Endpoints

| Endpoint | Purpose |
| --- | --- |
| `/oauth2/authorize` | Authorization endpoint |
| `/oauth2/token` | Token endpoint |
| `/oauth2/jwks` | Public JWK Set for verification |
| `/oauth2/introspect` | Token introspection |
| `/oauth2/revoke` | Token revocation |
| `/.well-known/oauth-authorization-server` | AS metadata |
| `/.well-known/openid-configuration` | OIDC OP discovery when enabled |
| `/userinfo` | OIDC UserInfo if supported |

These are **AS endpoints**, not controllers inside Orders API. Never slap `@PostMapping("/oauth2/token")` onto an API and call it a secure AS.

## 7. AS Settings and Responsibility for Issuing the Right Audience

Inside the **Authorization Server** app, `issuer` is the token-issuing identity. Spring Authorization Server 1.x Java fragment:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .build();
}
```

This is **not a standalone class**: declare it inside an AS `@Configuration` with matching library imports. Token `iss` will match this issuer, while APIs configure the **approved value** as their expected issuer.

The AS must also issue **access tokens targeted at the exact API**, never assuming every issued token grants access to all resources. With Spring Authorization Server, an `OAuth2TokenCustomizer<JwtEncodingContext>` can attach `aud` to **access tokens** per client/scope/resource policy:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> ordersAudience() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && context.getAuthorizedScopes().contains("orders.read")) {
            context.getClaims().audience(java.util.List.of("orders-api"));
        }
    };
}
```

This is an **illustrative AS code fragment**, not part of the Resource Server. In production, determine `aud` from **registered client, resource indicators (RFC 8707 when supported), granted scopes, and AS policy**, not merely a shared scope. Never change an ID Token's `aud` to an API audience.

Never grant `orders.write` merely because a client requested that scope; the AS must verify client eligibility, resource owner, and consent/policy. The API must still verify object-level rights even when the token carries a granted scope.

## 8. Spring Boot Properties: Client, AS, and Resource Server Are Completely Distinct

| Prefix | Where It Belongs |
| --- | --- |
| `spring.security.oauth2.client.registration.*` | OIDC/OAuth2 Client (client ID/secret, scopes, redirect) |
| `spring.security.oauth2.client.provider.*` | Client: issuer and authorization/token/JWKS endpoints provided by OP/AS |
| `spring.security.saml2.relyingparty.registration.*` | SAML SP: IdP metadata, SP Entity ID, ACS, keys |
| `spring.security.oauth2.authorizationserver.*` | Authorization Server: registered clients / AS settings |
| `spring.security.oauth2.resourceserver.jwt.*` | Resource Server: issuer/JWKS/audience/algorithms to **verify** JWTs |
| `spring.security.oauth2.resourceserver.opaquetoken.*` | Resource Server: introspection endpoint and credentials |
| `server.servlet.session.cookie.*` | Web app session cookie, not an OAuth token verifier |

Client and Resource Server issuer settings may be **identical** when talking to the same AS/OP, yet their purposes differ: the client uses the issuer to validate **OIDC login/authorized clients**, whereas the RS uses it to verify **Bearer access tokens**.

### A Common Real-World Mistake

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
```

This snippet **does not create an Authorization Server** and does not mint access tokens. It tells the API which issuer to trust when verifying JWTs.

## 9. Protecting APIs with JWTs: Signature, Issuer, Audience, and Expiry

An OAuth Bearer request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_REDACTED
```

The API must:

1. Read the token from the `Authorization` header per Bearer policy, never from SSO cookies or query parameters.
2. Verify the JWS signature against **trusted JWKS/public keys** belonging to the provisioned AS; `kid` only selects among already-trusted keys.
3. Verify `iss` matches the expected AS issuer.
4. Verify `exp`/`nbf` with bounded clock skew.
5. Verify `aud` contains **Orders API's** resource identifier.
6. Verify token type/profile: reject ID Tokens sent instead of access tokens.
7. Map `scope`/`scp` to authorities using an approved mapper.
8. Enforce HTTP method, scope, tenant, owner/ACL, and record state.
9. Fail closed if any check fails.

**A valid signature does not mean the token belongs at this API.** A token with `aud=billing-api` may be signed by the **same AS** yet must be rejected by Orders API. Nor does a token with `orders.read` grant access to every order across every tenant.

## 10. Spring Boot 3.5+ / Security 6.5 JWT Resource Server

In the **API project**, dependencies can be:

```groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
}
```

This is a build snippet for a project already configured with Java 17+ and Spring Boot plugins/BOM.

Example `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          jwk-set-uri: "https://auth.example.test/oauth2/jwks"
          audiences: "orders-api"
```

Meaning:

- `issuer-uri` is the **API-approved issuer** used to validate `iss`.
- `jwk-set-uri` points to the configured trusted JWKS endpoint. When both issuer and JWKS are specified, the RS does not necessarily call discovery at startup while still validating `iss`.
- `audiences` in Boot 3.5+ sets expected audiences to enforce `aud`.
- This is **verification config**, not a token-issuing endpoint.

For other Boot/Security versions, verify property support for your release; if `audiences` is unsupported, add an `OAuth2TokenValidator<Jwt>` per your API version rather than skipping audience validation.

If the AS is purely a SAML IdP lacking OAuth token/JWKS endpoints, **never use the SAML metadata URL as `jwk-set-uri`**. SAML XML signing certificates and OAuth JWT verification keys belong to different systems and trust contracts.

## 11. Configuring an App with Separate Web Login and Bearer API

Deploying **two separate applications** isolates security boundaries more cleanly. When web and API live in the same Spring Boot application, define **two `SecurityFilterChain` beans**:

- `/api/**` uses stateless Bearer auth, independent of session cookies.
- `/web/**` uses OIDC/SAML browser login and HTTP sessions with default CSRF protection.

The combined example below illustrates both side-by-side, yet **contains no Authorization Server in the app**.

### 11.1. Dependencies

In `build.gradle` of a Spring Boot project with plugins and dependency management:

```groovy
repositories {
    mavenCentral()
    // When Spring Security's OpenSAML requires an additional repository:
    maven { url "https://build.shibboleth.net/maven/releases/" }
}

dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-client"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
    implementation "org.springframework.security:spring-security-saml2-service-provider"
}
```

### 11.2. application.yml

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
        provider:
          corp:
            issuer-uri: "https://auth.example.test"
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          jwk-set-uri: "https://auth.example.test/oauth2/jwks"
          audiences: "orders-api"
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              metadata-uri: "${SAML_IDP_METADATA_URI}"
```

OIDC client, SAML SP, and RS use **three separate responsibility configs**. `${...}` placeholders load from environment variables or a secret manager; **never** put real credentials in documentation or source control. `example.test` is a placeholder public hostname.

### 11.3. Complete Java Class

Save `src/main/java/demo/boundary/TokenBoundaryApplication.java`:

```java
package demo.boundary;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class TokenBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenBoundaryApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .saml2Login(Customizer.withDefaults())
                .build();
    }

    @GetMapping("/")
    public String home() {
        return "Use /web/me or /api/orders/42 with an access token";
    }

    @GetMapping("/web/me")
    public String me() {
        return "Authenticated browser session";
    }

    @GetMapping("/api/orders/{id}")
    public Map<String, Object> read(@PathVariable long id) {
        // Demo does not fetch real data. Production also checks
        // the order's owner, tenant, role, and ACL.
        return Map.of("orderId", id, "status", "visible");
    }

    @PostMapping("/api/orders/{id}")
    public Map<String, Object> update(@PathVariable long id) {
        // Simulation only; production requires transactions and domain policy.
        return Map.of("orderId", id, "status", "updated-demo");
    }
}
```

**Explanation of boundaries in the code:**

1. `@Order(1)` with `securityMatcher("/api/**")` routes API traffic to the Bearer resource server first.
2. `oauth2ResourceServer().jwt()` uses the Boot auto-configured `JwtDecoder` from YAML issuer/JWKS/audience. There is no JWT-signing code here.
3. `SessionCreationPolicy.STATELESS` prevents API Bearer requests from creating authenticated browser sessions.
4. `csrf.disable()` applies **only to the API chain**. That is safe only because the API relies strictly on `Authorization: Bearer` headers and never accepts ambient browser session cookies. Cookie-authenticated APIs must retain CSRF protection.
5. `GET /api/orders/**` requires `SCOPE_orders.read`; `POST` requires `SCOPE_orders.write`; all other methods hit the `denyAll()` fallback.
6. The `@Order(2)` web chain retains browser login, HTTP sessions, and CSRF protection.
7. `/login/oauth2/code/corp` and `/login/saml2/sso/partner` belong to web authentication protocols, **not** `/api/**`.
8. There are no `AuthorizationServerSettings`/`RegisteredClientRepository`/`JWKSource` beans because this project **does not issue tokens**.

Scopes in the example protect routes only; never use this code for real orders without owner/tenant/object-level authorization.

### Running and Output

The project requires real OIDC and SAML providers plus a configured AS JWT issuing/JWKS endpoint. After replacing placeholders with valid sandbox values, run:

```bash
OIDC_CLIENT_ID=portal-client \
OIDC_CLIENT_SECRET=from-secret-store \
SAML_IDP_METADATA_URI=https://saml.example.test/metadata \
./gradlew bootRun
```

There is no fixed login/token stdout; output depends on the AS/IdP and credentials. When calling the API with an **access token matching issuer, audience, and scope**, `GET /api/orders/42` returns JSON:

```json
{"orderId":42,"status":"visible"}
```

When the token has an invalid signature, is expired, or has the wrong `aud`, the RS rejects authentication. When the token is valid yet lacks the required scope, HTTP authorization denies the call. That is expected behavior, not an SSO session bug.

## 12. Calling the API with a Token and Distinguishing 401 vs. 403 Responses

Client call:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.test/api/orders/42
```

`ACCESS_TOKEN` must be obtained via a **valid OAuth grant** intended for Orders API. Never substitute an OIDC ID Token, refresh token, `SAMLResponse`, or session cookie. `api.example.test` is an illustrative host; locally, use your running app's URL and port.

| Scenario | Typical Outcome |
| --- | --- |
| API request missing `Authorization: Bearer` | **401 Unauthorized** |
| Bearer has invalid signature, issuer, audience, or expired | **401 Unauthorized** |
| ID Token rejected due to audience/token type | **401 Unauthorized** |
| Valid token lacking `orders.read` on GET | **403 Forbidden** |
| Token has `orders.read` yet user cannot read order 42 | **403**, or existence-hiding response per policy |
| Web `/web/me` without session | Typically **302 redirect** to login/IdP |
| Logged into web app yet calling API without Bearer | **401** on stateless API chain |

Bearer handling may add `WWW-Authenticate` per RFC 6750. An API HTTP 401 **does not mean** web app IdP SSO failed; the token may simply lack or mismatch the API audience.

## 13. JWT Authentication and Scope Authorities

Once Spring Security Resource Server validates a JWT, `Authentication` is typically `JwtAuthenticationToken` with a `Jwt` principal. By default, Spring Security uses `JwtGrantedAuthoritiesConverter` to map `scope` or `scp` claims into **`SCOPE_`**-prefixed authorities.

For example, `scope="orders.read orders.write"` maps to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

With `authorizeHttpRequests` or `@PreAuthorize`:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public void updateOrder(long id) {
    // Insufficient without owner/tenant/domain policy.
}
```

This is an **illustrative Java fragment** requiring `@EnableMethodSecurity` and a Spring-managed service; it is not a standalone class. `hasAuthority("SCOPE_orders.write")` checks the mapped authority and **differs** from `hasRole("ADMIN")` (which looks for `ROLE_ADMIN` by default).

If the AS uses custom claims, configure `JwtAuthenticationConverter` per issuer contract. Never convert arbitrary `groups=["admins"]` straight into `ROLE_ADMIN` because a less-trusted AS or tenant may use identical group names. Domain authorization requires local permissions and resource ACLs.

## 14. Audience Validation and Custom JwtDecoder

Spring Boot 3.5+ supports `spring.security.oauth2.resourceserver.jwt.audiences`. If a project needs a custom validator, never replace default issuer/timestamp checks with a lambda that checks only audience.

Example **Bean fragment** for an API inside a `@Configuration` having `app.jwt.issuer` and `app.jwt.jwks-uri`:

```java
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.jwt.issuer}") String issuer,
        @Value("${app.jwt.jwks-uri}") String jwksUri) {

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience() != null
                    && jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Audience orders-api required",
                                    null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, audience));
    return decoder;
}
```

Imports belong to `org.springframework.security.oauth2.jwt.*`, `org.springframework.security.oauth2.core.*`, `org.springframework.security.oauth2.core.validator.*`, `org.springframework.beans.factory.annotation.Value`, and `org.springframework.context.annotation.Bean`. This is **not a standalone Java class**; use it as a **replacement** for the auto-configured decoder only when genuinely needed.

**Warning:** declaring your own `JwtDecoder` `@Bean` overrides Boot's default decoder. Retain every required validator: issuer, timestamps, audience, token type/profile, and allowed algorithms. Do not expect the `audiences` property to attach automatically to a manually constructed bean.

For RFC 9068, use a type-aware validator matching your Spring Security version—such as `JwtValidators.createAtJwtValidator()`—and ensure the decoder accepts/validates `typ=at+jwt` properly. Check Javadoc for your exact version; `createDefaultWithIssuer` **does not by itself enforce** every RFC 9068 rule.

## 15. JWT Access Token Profile Differs from Arbitrary Valid JWTs

RFC 9068 defines a profile for **OAuth2 JWT access tokens**. Key requirements include:

- Access tokens must be signed; reject `alg=none`.
- Header `typ` indicates `at+jwt` (or full media type `application/at+jwt`).
- Clear semantics for `iss`, `exp`, and `aud`; `aud` targets the right resource server.
- RS validates signature with trusted keys, issuer, timestamps, and token type.
- Authorization claims are evaluated alongside object/resource policies.

If an API accepts only tokens conforming to that profile, an **ID Token** with `typ=JWT` or `aud=portal-client` must be rejected even if both share the OP's signing key. Even when an AS uses another JWT access token profile, you still need a way to distinguish ID Tokens from access tokens by agreed issuer, audience, token type, and policy—never solely because a string "looks like a JWT".

Never read `kid`/`jku`/`x5u` from a JWT header to fetch arbitrary keys from the internet. `kid` only selects among **already-trusted keys**. Dynamic key fetching from unverified input enables SSRF and self-signed trust attacks.

## 16. Opaque Token Introspection vs. Local JWT Validation

An AS may issue **reference/opaque access tokens** instead of JWTs. The API cannot validate them by parsing claims. Instead, the Resource Server calls the **OAuth2 Token Introspection Endpoint** (RFC 7662).

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant API as Orders Resource Server
    participant AS as Authorization Server
    Client->>API: Authorization: Bearer opaque-token
    API->>AS: Introspection request + RS client credentials
    AS-->>API: active, scope, exp, sub, aud ... per policy
    API->>API: Check active, resource audience, scope, local ACL
    API-->>Client: 200 or 401/403
```

An **API project** using opaque tokens can configure:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "https://auth.example.test/oauth2/introspect"
          client-id: "${INTROSPECTION_CLIENT_ID}"
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

And switch the DSL from JWT to:

```java
.oauth2ResourceServer(oauth -> oauth
        .opaqueToken(Customizer.withDefaults()))
```

These two setups are **alternatives**; JWT and opaque are not usually both enabled together. Introspection returning `active=true` **is not sufficient authorization**: the RS must still enforce audience/resource, scope, tenant/ACL, and policy rules.

### Trade-Offs

| Criterion | Self-Verified JWT via JWKS | Opaque Introspection |
| --- | --- | --- |
| Network call to AS per request | Usually none when keys are cached | Usually yes, unless cached |
| Immediate revocation | Harder while JWT is unexpired without a denylist | Can reflect revocation faster depending on cache |
| Latency | Typically lower | Adds network round-trip latency |
| Resilience during brief AS outage | Can continue using trusted cached keys | Usually unable to verify; must fail closed |
| Metadata inside token | JWT payload is typically readable (not encrypted by default) | Opaque string hides claims from clients |
| Object-level authorization | Still required | Still required |

If caching introspection results, accept the **revocation delay window** and protect cached token state. Credentials for calling introspection belong to the **Resource Server**, never the browser or JavaScript.

## 17. Scope Differs from Per-Record Permissions

Scope `orders.read` states that the token is authorized to invoke order-reading capabilities **per AS/RS policy**. It **does not** prove the user/client may read `orderId=42`. A token with the right scope may still be denied because:

- The order belongs to another tenant.
- The local user is unlinked or disabled.
- The user is not among the order's owners/readers.
- The order entered a state disallowing edits.
- The token belongs to a machine client while the API requires user delegation.
- The transaction requires extra MFA/freshness beyond scope.

Decision model:

```text
allow = tokenVerified
    AND expectedIssuer
    AND expectedAudience
    AND tokenWithinValidityWindow
    AND requiredScope
    AND localIdentityOrClientAllowed
    AND tenantMatchesResource
    AND resourcePolicyAllowsAction
    AND optionalAssuranceFreshnessSatisfied
```

This is pseudocode, not runnable SpEL. Enforce **authorization at service/domain/repository layers** alongside `authorizeHttpRequests` to defeat IDOR/BOLA, and avoid TOCTOU with transactions/atomic updates on state-changing operations.

With `client_credentials`, tokens may represent no human user; APIs should distinguish **service identities** from **end-user identities**. Never treat `sub` as an internal user ID if the AS profile sets `sub` to the client.

## 18. Identity Broker: Upstream Login and Downstream Issuance

A broker can be an **OIDC Client/SAML SP** toward an external IdP while simultaneously acting as an **Authorization Server** for internal apps/APIs. These are two trust domains:

1. The broker receives the upstream `SAMLResponse`/ID Token and validates issuer, signature, audience, timestamps, and correlation.
2. The broker maps the external subject to a **local user** per policy, never auto-linking on matching email.
3. The broker evaluates whether the downstream client may receive tokens, scopes, resources/audiences, and authentication freshness.
4. When the broker includes an AS module, it mints **new access tokens** with the broker's issuer and signing keys, the API's audience, and granted scopes.
5. The API validates the downstream token against the **trusted broker issuer/JWKS**, never accepting an upstream SAML assertion as a Bearer token.

**There is no implicit "SAMLResponse → JWT" conversion when enabling `saml2Login`.** If a broker acts solely as a login proxy, it does not necessarily expose `/oauth2/token` or issue Bearer tokens. Token issuance requires deploying an actual AS and protocol flows.

When propagating identity from service A → B, consider OAuth2 Token Exchange (RFC 8693) if supported by the AS, or an agreed service-to-service/BFF grant. Never forward an access token with `aud=api-a` straight to `api-b` and drop audience validation just to "avoid issuing a new token".

## 19. Multi-Issuer Resource Server: Unverified iss Only Selects the Verifier

If Orders API trusts multiple ASs (e.g., North and South), Spring Security supports:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://north-auth.example.test",
                "https://south-auth.example.test");

http.oauth2ResourceServer(oauth -> oauth
        .authenticationManagerResolver(resolver));
```

This is a **`SecurityFilterChain` fragment**, not standalone Java SE. It shows selecting a verifier from pre-configured **trusted issuers**. The unverified `iss` claim only picks a verifier, which then validates signature and issuer.

Never do this:

```text
issuer = unverifiedJwt.getClaim("iss")
decoder = JwtDecoders.fromIssuerLocation(issuer)
acceptJwtIfDecoderSucceeds()
```

That is **dynamic trust**. An attacker can stand up their own issuer/JWKS and sign tokens. Issuers must come from an admin-managed allowlist or repository updated through an approved workflow. Each issuer also requires its own audience/type/scope and tenant authorization checks; a valid JWT from South never automatically grants North access.

## 20. Session Cookies, CSRF, and Bearer APIs Are Two Different Contexts

Web federation uses `JSESSIONID` or `SESSION` cookies. Browsers attach cookies automatically, so web apps require CSRF protection on state-changing forms/methods even when using SAML or OIDC login.

An API accepting only `Authorization` header tokens typically **does not rely on ambient cookies**. If it is genuinely Bearer-only, stateless, and free of cookie authentication, you may configure `csrf.disable()` **strictly on the API `SecurityFilterChain`**. Never disable CSRF on the web login/action chain just to "make SAML callbacks work".

Principles:

- SAML ACS `/login/saml2/sso/...` accepts protocol form POSTs and must be handled by Spring Security's SAML filter with signature/issuer/audience/recipient/correlation checks.
- OIDC callback `/login/oauth2/code/...` belongs to OAuth2 login and must check `state`/nonce/issuer per protocol.
- `/api/**` accepts Bearer tokens and returns 401 when missing rather than redirecting to an IdP.
- CORS governs browser cross-origin JS requests; it **does not grant API authorization** or replace issuer/audience validation.
- If an API also accepts cookies/sessions, **never copy a Bearer-only API's CSRF disablement**.
- A BFF may store access tokens server-side while the browser holds a BFF session cookie; that BFF still requires CSRF, XSS, and session protections.

## 21. Bearer Tokens and Secret Protection

Access tokens and refresh tokens are **sensitive credentials**. Practices:

- Use HTTPS everywhere; never pass tokens in URL queries like `?access_token=...`.
- Send access tokens in the `Authorization: Bearer` header, never stuffed into SAML `RelayState`.
- Never log raw tokens, `Authorization` headers, ID Tokens, `SAMLResponse`, cookies, or client secrets.
- Keep refresh tokens at the authorized OAuth2 Client; **never send them to business APIs**.
- Bound access token TTLs; consider refresh-token rotation and revocation/introspection per AS policy.
- Manage JWKS rotation and bounded public-key caching; never fetch keys from `jku`/`x5u`.
- Public clients (SPA/mobile) cannot safeguard a client secret like confidential server clients; use Authorization Code + PKCE per policy.
- In a BFF, keep tokens server-side without unnecessary exposure to browser JS.
- If immediate privilege revocation is required, evaluate self-contained JWTs vs. introspection/denylists.

**HTTPS/TLS does not replace JWT signature verification**; they protect different boundaries. Nor does signature verification replace audience, scope, or ACL checks.

## 22. Standalone Java 17: Modeling Policy After Access Token Verification

The program below **does not decode or verify JWTs**. It simulates authorization decisions **after** the Resource Server library has verified the token. The `verified` flag is a test input only—**never take it from an HTTP header or self-asserted client token**.

Save file `VerifiedApiPolicyDemo.java`:

```java
import java.util.Set;

public final class VerifiedApiPolicyDemo {

    record VerifiedToken(
            boolean verified,
            String issuer,
            Set<String> audiences,
            Set<String> scopes,
            String tenant) {
    }

    static boolean canRead(VerifiedToken token, String resourceTenant) {
        return token != null
                && token.verified()
                && "https://auth.example.test".equals(token.issuer())
                && token.audiences().contains("orders-api")
                && token.scopes().contains("orders.read")
                && token.tenant().equals(resourceTenant);
    }

    public static void main(String[] args) {
        VerifiedToken valid = new VerifiedToken(
                true, "https://auth.example.test",
                Set.of("orders-api"),
                Set.of("orders.read"), "north");

        VerifiedToken otherApi = new VerifiedToken(
                true, "https://auth.example.test",
                Set.of("billing-api"),
                Set.of("orders.read"), "north");

        VerifiedToken noScope = new VerifiedToken(
                true, "https://auth.example.test",
                Set.of("orders-api"),
                Set.of("profile"), "north");

        VerifiedToken unverified = new VerifiedToken(
                false, "https://auth.example.test",
                Set.of("orders-api"),
                Set.of("orders.read"), "north");

        System.out.println("allowed=" + canRead(valid, "north"));
        System.out.println("wrongAudience=" + canRead(otherApi, "north"));
        System.out.println("missingScope=" + canRead(noScope, "north"));
        System.out.println("wrongTenant=" + canRead(valid, "south"));
        System.out.println("unverified=" + canRead(unverified, "north"));
    }
}
```

Run with Java 17+:

```bash
javac VerifiedApiPolicyDemo.java
java VerifiedApiPolicyDemo
```

Exact stdout:

```text
allowed=true
wrongAudience=false
missingScope=false
wrongTenant=false
unverified=false
```

In production, if `tenant` comes from a JWT issued by an AS not authorized to assert tenant claims, never trust it for access decisions. Map the authenticated issuer/subject to a local user and tenant membership per app policy. The demo simply shows that **a failure in any condition must deny access**.

## 23. Minimum Test Matrix

| Test | Token / Login | Expected Outcome |
| --- | --- | --- |
| A. Valid OIDC browser login | Verified ID Token, web session | `/web/me` works |
| B. Valid SAML login | Signed `SAMLResponse` and valid ACS | Web session created |
| C. Web session cookie sent to Bearer-only API | No access token | API 401 |
| D. API call without Bearer | Missing `Authorization` header | 401 |
| E. JWT with wrong signature | Key outside trusted JWKS | 401 |
| F. JWT from unapproved issuer | Unknown `iss` | 401 |
| G. Expired JWT | `exp` in the past | 401 |
| H. Not-yet-valid JWT | `nbf` in the future | 401 |
| I. JWT with wrong audience | `aud=billing-api` | 401 |
| J. ID Token sent as Bearer | `aud=portal-client` / wrong type | 401 |
| K. GET access token with sufficient scope | `orders.read` + right audience | 200 if ACL permits |
| L. POST access token lacking write scope | Only `orders.read` | 403 |
| M. Valid scope yet order belongs to another tenant | Cross-tenant | Denied per resource ACL |
| N. Opaque `active=false` | Introspection inactive | 401 |
| O. Introspection endpoint outage | Unable to verify token | Fail closed |
| P. Multi-issuer unknown `iss` | Unknown issuer | No dynamic trust |
| Q. JWT header has attacker `jku` | Untrusted key URL | Never fetches arbitrarily |
| R. Valid AS signing key rotation | Updated JWKS, right issuer | New tokens verify cleanly |
| S. Machine `client_credentials` token | No human principal | Service permissions only |
| T. Unauthorized admin scope/group mapping | Unknown `groups=admin` claim | Grants no internal role |
| U. Same-site browser POST missing CSRF | Session/cookie authentication | Web CSRF filter denies |
| V. Unexpired token yet local user disabled | Business revocation state | Domain policy denies |

Using Spring Security Test's `jwt()` mock helper to test HTTP authorization/mapping **does not prove** real signature validation. Write integration tests exercising `JwtDecoder` with sandbox keys, issuer/audience mismatches, and a real AS to test the full pipeline.

Never put production tokens, refresh tokens, or raw `SAMLResponse` XML in public test fixtures or tickets; redact secrets when tracing.

## 24. Common Error Diagnosis

| Symptom | Cause | Resolution |
| --- | --- | --- |
| 401 at API while web SSO works | Web cookie ≠ Bearer access token | Have client acquire token via right grant/resource |
| 401 invalid issuer | AS issuer differs from expected `issuer-uri` | Check approved issuer; never drop issuer validator |
| 401 invalid audience | Token meant for another API or AS omitted `aud` | Update AS token policy and RS expected audience |
| 401 invalid signature | JWKS/cert mismatch or rotation | Check keys from trusted AS; never read keys from token headers |
| 401 OP ID Token rejected | Wrong token type/audience | Use an access token from the AS |
| 403 missing `SCOPE_orders.write` | Token was not granted write scope | Check client registration/consent/scopes; never grant blindly |
| 403 despite valid scope | Tenant/ACL/domain policy | Check ownership and record-level permissions |
| Resource Server fails startup | Cannot reach issuer discovery/JWKS | Use trusted `jwk-set-uri` when appropriate and check TLS |
| Introspection timeout | AS down, network, or wrong credentials | Set timeouts and fail closed; monitor endpoint |
| JWT still works after user logout | Self-contained JWT within `exp` | Short TTLs, denylist, or introspection per policy |
| OAuth2 client callback error | Wrong client ID/secret, `redirectUri`, or `state`/nonce | Fix client registration; do not touch API `JwtDecoder` |
| SAML ACS error | Metadata/Issuer/Signature/Recipient/session | Debug SAML SP separately; not a JWT API error |
| JWT accepted cross-tenant | Signature-only check lacking audience/tenant | Add audience and local tenant policies |
| API redirects to IdP | Web chain intercepted API due to matcher order | Use `@Order`, `securityMatcher`, and test each path |

**Never fix these by disabling signature validation, dropping audience checks, accepting arbitrary issuers, or setting `permitAll("/api/**")`.** Those destroy the core security boundaries of a Resource Server.

## 25. Pre-Production Checklist

- [ ] Every service has an explicit role: Client/SP, Authorization Server, Resource Server, or broker.
- [ ] AS enforces registered clients, consent/PKCE/grants, key custody/rotation, issuer, token TTLs, and auditing.
- [ ] ID Tokens, SAML Assertions, access tokens, and refresh tokens are never conflated.
- [ ] Bearer-only APIs are protected with `oauth2ResourceServer`, not another web app's SSO cookies.
- [ ] JWTs are validated for signature, expected issuer, audience, `exp`/`nbf`, token profile/type, and algorithms.
- [ ] `jwk-set-uri` comes only from trusted ASs, never dynamically from JWT headers or unverified `iss`.
- [ ] JWT scopes map consistently to `SCOPE_*` and combine with owner/tenant/ACL checks.
- [ ] Multi-issuer APIs use an allowlist; unknown issuers fail closed.
- [ ] `client_credentials` tokens are never mistaken for human users.
- [ ] When using opaque tokens, introspection credentials, timeouts, caching, and revocation are governed.
- [ ] When using a broker, upstream auth is verified before the downstream AS mints tokens with new issuer/`aud`/scopes.
- [ ] Tokens issued for API A are never forwarded to API B without a matching `aud`.
- [ ] Stateless API chains are isolated from session-based web chains; CSRF stays enabled on web chains.
- [ ] Browsers/BFFs protect session cookies and access/refresh tokens without storing unnecessary secrets.
- [ ] Tested 401/403, issuer/`aud`/signature/time, ID Token confusion, tenant ACLs, introspection outages, and key rotation.
- [ ] Never log raw tokens, `SAMLResponse`, `JSESSIONID`, private keys, or client secrets.
- [ ] Pinned Spring Boot/Security/Authorization Server versions and re-tested after upgrades.

## 26. Self-Check Questions

**1. Does `oauth2Login` issue access tokens?**  
No. The client performs login/authorization code flow; the AS issues tokens per grant and policy.

**2. Does `oauth2ResourceServer().jwt()` make an API an Authorization Server?**  
No. It configures the API to verify JWT Bearer access tokens.

**3. Should a valid ID Token call Orders API?**  
No. ID Tokens target the OIDC RP; APIs require access tokens with the right audience, token type, and scopes.

**4. Why can a token with a valid signature still get 401 at an API?**  
Wrong issuer, wrong audience, expired, not yet valid, or wrong token profile.

**5. Does `SCOPE_orders.read` automatically allow reading any order?**  
No. Tenant, owner, and object-level authorization are still required.

**6. Why not read `iss` from an unverified JWT and run discovery to trust that issuer?**  
That creates dynamic self-established trust and SSRF risks; use a trusted issuer allowlist.

**7. Does successful SAML login automatically create a downstream JWT access token?**  
No. You need a downstream AS and an approved token-issuance flow.

**8. When should opaque token introspection be used?**  
When the AS issues opaque/reference tokens or you need live active-status checks via the AS, balancing availability/latency/caching trade-offs.

**9. Can an API accepting only Bearer tokens disable CSRF?**  
Yes, strictly on a truly stateless API chain with no cookie authentication. Session-based web chains must keep CSRF protection.

**10. How do 401 and 403 differ?**  
401 normally indicates unauthenticated or invalid token; 403 indicates authenticated yet lacking required scope or permission.

## 27. References

- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `oauth2Login`, OIDC client registration.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/): `OAuth2AuthorizedClientManager` and token lifecycle.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, JWKS, audiences, JWT validation, and scope mapping.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, active status, and configuration.
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers`.
- [Spring Authorization Server 1.x — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): starter, registered clients, keys, AS setup.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer`, protocol endpoints, and issuer.
- [Spring Security — Authorization Server Core Components](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/core-model-components.html): token generator/customizer, JWT/opaque formats.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation/audience, issuer, and subject.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `typ=at+jwt`, `aud`, `iss`, token verification.
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): active status and introspection API.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer Authorization header and error responses.
- [RFC 8707 — OAuth2 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707.html): specifying resource/audience in access-token requests.
- [RFC 8693 — OAuth2 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): delegated token exchange when supported by the AS.
- [RFC 9700 — OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): AS mix-up defenses and OAuth2 client protection.
- [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): owner/tenant/object authorization.
