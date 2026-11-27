# Configuring Audience for an API Instead of Relying Only on the Frontend Application's client_id

When connecting a **Spring Security OAuth 2.0/OIDC Resource Server** to an **Authorization Server/Identity Provider (IdP)**, a very common design mistake is taking the frontend application's `client_id` and treating it as the **valid audience for every access token sent to the API**. Yet the frontend application and the API play **two distinct roles** in OAuth 2.0:

- The frontend application (SPA, mobile app, server-rendered web app, or BFF) is typically an **OAuth client**, registered with a `client_id` to request tokens.
- The backend Orders API, Payments API, or Reports API is a **Resource Server**. Each API must check whether an access token was issued **for that specific resource/API**, usually via the `aud` (audience) claim or an equivalent resource-binding mechanism guaranteed by the issuer.

An access token with a valid signature, correct `iss`, unexpired lifetime, and `scope=orders.read` **is not necessarily** allowed to call the Orders API. If the token's `aud` indicates it was meant for another application, the Resource Server should not accept it merely because a scope looks familiar.

> **Core principle:** Define the audience of the **API/resource being protected**, then require access tokens to contain that audience. **Do not default to using the frontend's `client_id` as the API's audience.** In some systems, the registration ID of **the API itself** is used as the audience; that is completely different from taking the frontend application's `client_id`.

This lesson belongs to the **Issuer Integration** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. Examples cover Java/Spring Security Servlet and WebFlux, OAuth/OIDC flows, issuer-side configuration, scope authorization, testing, and common pitfalls across different identity providers. URIs, app names, and identifiers are **illustrative data**.

## 1. Start with the Right Three Roles

Suppose a sales platform has:

| Component | Role | Illustrative Identifier |
|---|---|---|
| Shop Web SPA | **OAuth client** / frontend | `shop-spa-client` |
| Orders API | **Resource Server** | `https://api.example.test/orders` |
| Payments API | **Resource Server** | `https://api.example.test/payments` |
| Login Service | **Authorization Server / OIDC Provider** | `https://login.example.test/realms/shop` |

The frontend sends the user to sign in and executes OAuth 2.0 Authorization Code + PKCE per the issuer contract. After obtaining an access token, the frontend sends it to the Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

The Orders API must verify that **the token is intended for the Orders API**, not merely that a token was issued during Shop Web's login session.

~~~mermaid
flowchart LR
    U["User"] --> F["Shop Web SPA"]
    F -->|"Authorization Code + PKCE, client_id=shop-spa-client"| AS["Authorization Server / OIDC Provider"]
    AS -->|"Access token for Orders API"| F
    F -->|"Bearer access token"| API["Orders API / Resource Server"]
    API -->|"Verify signature, iss, aud, time, scopes"| API
~~~

In practice, a BFF may keep tokens on the backend instead of the browser, or a mobile app may interact differently, yet the **OAuth client** and the **token-receiving resource** remain two separate concepts.

### 1.1. What Question Does `client_id` Answer?

`client_id` is the identifier of an OAuth client registered at the Authorization Server. It is typically used in authorization or token requests to identify **the application requesting a token**.

Illustrative login parameters:

~~~text
GET https://login.example.test/authorize
    ?response_type=code
    &client_id=shop-spa-client
    &redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback
    &scope=openid%20profile%20orders.read
    &state=<RANDOM_STATE>
    &code_challenge=<PKCE_CHALLENGE>
    &code_challenge_method=S256
~~~

Real requests must be properly URL-encoded and use random/secure `state` and PKCE. `client_id` is usually a **public identifier**, not a secret authenticating the client. For an SPA public client, never embed a client secret and treat it as confidential.

### 1.2. What Question Does `aud` Answer?

The JWT `aud` claim identifies the **intended recipient of the token**. For OAuth access tokens following an appropriate JWT profile, the audience typically identifies the **Resource Server/API**.

A valid access token for the Orders API might carry:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["https://api.example.test/orders"],
  "client_id": "shop-spa-client",
  "scope": "orders.read",
  "iat": 1924988400,
  "exp": 1924992000
}
~~~

The fields above are **illustrative payload data**, not a signed token; `exp` and `iat` in the example must not be used as real lifetimes. Issuers may use `azp`, `client_id`, `appid`, or other metadata to describe the client that was issued the token; that is **distinct information** from audience.

Reading it in business terms:

~~~text
iss       → Who issued the token?
sub       → Which subject is described in the token?
aud       → Which resource/API is the token intended for?
client_id → Which client requested/was issued the token?
scope     → Which permission scopes were granted?
exp/nbf   → Is the token currently within its valid time window?
~~~

Not every token contains all fields under the same names; **the token profile contract with the issuer determines what is required**. For the Resource Server, clarify what the audience/resource binding is and how it is enforced.

### 1.3. `aud` Is Neither `scope` Nor `iss`

| Question | Typical Field | Example |
|---|---|---|
| Who is the trusted issuer? | `iss` | `https://login.example.test/realms/shop` |
| Which API is the token for? | `aud` | `https://api.example.test/orders` |
| Which client received the token? | `client_id` or provider-equivalent metadata | `shop-spa-client` |
| What actions can the token perform? | `scope` / `scp` | `orders.read orders.create` |
| Which subject does the token belong to? | `sub` | `user-123` |

A valid JWS signature **does not prove the audience matches**. A valid issuer **does not mean every token issued by that issuer can be used at every API**. A matching scope **does not fix a wrong audience**.

## 2. Two JWTs Frequently Conflated: ID Token vs. Access Token

OIDC introduces the **ID token**, which is also typically a JWT. An ID token is issued to the **OIDC client** to attest user authentication details—not as a general-purpose access token for calling any Resource Server API.

### 2.1. An ID Token Having `aud=client_id` Is Normal

Example ID token payload for Shop Web:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": "shop-spa-client",
  "exp": 1924992000,
  "iat": 1924988400
}
~~~

Per OIDC Core, an ID token's audience identifies the **client expected to receive the ID token**. Having `aud=shop-spa-client` here can be **completely right** for an **ID token**.

### 2.2. An Access Token for the Orders API Must Differ in Purpose

Example access token:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": "https://api.example.test/orders",
  "client_id": "shop-spa-client",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

| Field | ID Token | Access Token for Orders API |
|---|---|---|
| Purpose | Attest identity to the OIDC client | Authorize the client to call the resource within granted scopes |
| Typical audience | `shop-spa-client` | `https://api.example.test/orders` |
| Intended recipient | OIDC client | Orders API |
| Use as `Authorization: Bearer` for the API? | **Not allowed by default** | Proper credential type per API contract |

If the Orders API accepts an ID token merely because it also carries a signature from a trusted issuer and `aud=shop-spa-client`, the system risks **token substitution/confused-deputy attacks**: a token issued for one purpose gets accepted at a resource it was not intended for.

### 2.3. Do Not "Fix" an ID Token Error by Setting API Audience to Frontend Client ID

~~~text
API returns 401 because the ID token's aud is shop-spa-client
    ↓
Developer configures API audience = shop-spa-client
    ↓
The ID token can now pass the audience check
~~~

The proper solution is for **the client to obtain a proper access token for the Orders API** and for the Resource Server to validate the resource's audience. Never weaken resource policy to accept ID tokens as Bearer access tokens.

To guard against token-type confusion, you may also need **token type/profile validation** (such as `typ=at+jwt` per the RFC 9068 JWT access token profile when supported by the issuer), issuer/client bindings, and required claims. **Audience is necessary, though not the sole defense** against token misuse.

## 3. Tokens Issued by the Same Issuer Can Still Target Different Resources

Suppose Shop Web calls both the Orders and Payments APIs. Two access tokens can share the same `iss`, `sub`, and `client_id=shop-spa-client` while having different audiences:

~~~text
Token O:
  aud   = https://api.example.test/orders
  scope = orders.read

Token P:
  aud   = https://api.example.test/payments
  scope = payments.read
~~~

The Orders API must accept Token O and reject Token P. The Payments API must accept Token P and reject Token O, even though both share the same issuer, subject, and frontend client.

### 3.1. Why Checking Scope Alone Is Not Enough

Scope conveys **granted permissions**, not always which resource is targeted. Some systems use generic scopes like `read`, `api.read`, or `profile`. If API A and API B only check for the `read` scope, a token meant for A could be used at B if audience checks are skipped.

~~~text
Bad:
  signature valid AND issuer trusted AND scope=read
  → lets the token into every API using the read scope

Better:
  signature valid AND issuer trusted
  AND audience contains THIS_API
  AND scope matches THIS_ENDPOINT
  → allows operations on the right resource
~~~

### 3.2. Audience and Scope Work Together as Two Layers

~~~mermaid
flowchart TD
    A["Bearer access token"] --> B{"Signature / issuer / time valid?"}
    B -->|No| X["401 / authentication rejected"]
    B -->|Yes| C{"aud contains Orders API?"}
    C -->|No| X
    C -->|Yes| D["Build Authentication and authorities"]
    D --> E{"Has SCOPE_orders.read for GET?"}
    E -->|No| Y["403 / authorization denied"]
    E -->|Yes| F["Check order owner / tenant"]
    F --> G["Return data if authorized"]
~~~

This flow shows audience validation belongs to **token validation** before authorization. A token valid for the Orders API yet missing a scope is still an authenticated token; it is blocked by permission rules at the HTTP/method layer.

### 3.3. Resource-Level Audience Does Not Replace Object-Level Authorization

A token with `aud=orders-api` and `scope=orders.read` does not necessarily allow viewing **every** order. The service must still check `sub`, tenant, order owner, partner permissions, and business policies. Audience answers "is the token for this API?", **not "is access to every record permitted?"**

## 4. Choosing the Actual Audience of the API

Audience is **not** an arbitrary string picked by the Resource Server without the issuer knowing. It is part of the **contract among issuer, OAuth client, and resource**:

1. Identify **which Resource Server** will receive the access token.
2. Register/declare a **resource identifier** or API registration at the issuer.
3. Have the issuer issue access tokens **for that resource identifier** using a supported mechanism.
4. Inspect the issued access token in a test environment and confirm its `aud` matches the contract.
5. Configure the Resource Server to require **the exact issued audience**, alongside issuer, signature, time, and permission checks.

Example design specification:

~~~yaml
oauth-resource-contract:
  authorization-server-issuer: https://login.example.test/realms/shop
  oauth-client-id: shop-spa-client
  resource-name: orders-api
  resource-audience: https://api.example.test/orders
  accepted-scope-for-reading: orders.read
~~~

This is an **illustrative contract document**, **not** Spring Boot YAML properties understood automatically by the framework. In a project, only properties bound into Spring Security configuration/beans take effect.

### 4.1. Must the Audience Be an Actual Reachable URL?

No. The audience can be a resource URI, an application identifier, or another value **explicitly agreed upon** by the issuer and API per the token profile. Examples:

~~~text
https://api.example.test/orders
api://orders-api
orders-api
<API_APPLICATION_ID>
~~~

A URL used as an identifier **does not have to be an HTTP endpoint that responds to GET**. However, the identifier should be stable, clearly scoped to the resource, consistent across environments, and free from collisions with other clients.

### 4.2. Never Derive the Audience from the Request's `Host` Header

Suppose the API is exposed publicly at:

~~~text
https://api.example.test/orders
~~~

while traffic is routed by a gateway to:

~~~text
http://orders-service.cluster.local
~~~

Never read `Host`, `X-Forwarded-Host`, or the inbound path to dynamically compute the expected audience per request. Those headers can be influenced by reverse proxies or unintended requests. The audience must come from **trusted server-side configuration**, or an explicitly managed resource/route mapping table.

### 4.3. Can the API's Own `client_id` Serve as the Audience?

**Yes**, if the issuer uses the **API application registration identifier** as the access token's audience. The key is distinguishing:

~~~text
SPA application / OAuth client:
    client_id = shop-spa-client

Orders API application/resource:
    application id = orders-api-registration

Access token:
    aud = orders-api-registration  // may be right per issuer contract
~~~

This is **completely different** from setting `aud=shop-spa-client` just because the frontend uses that client ID. IdP console labels can be confusing: a resource/API is sometimes registered as an "application" with a client/application ID, yet **its token-receiving role is still a resource**.

### 4.4. Separating Dev, Staging, and Production

Environments can have distinct resource registrations:

| Environment | Illustrative Audience |
|---|---|
| Development | `https://api.dev.example.test/orders` |
| Staging | `https://api.staging.example.test/orders` |
| Production | `https://api.example.test/orders` |

Never let the production API unconditionally accept dev/staging audiences for testing convenience. If a system intentionally shares a resource identifier across environments, it must enforce strict separation of issuers, keys, tenants, networks, and policies; a test token must never become a valid production credential due to overly broad trust settings.

## 5. How Should the Issuer Issue Access Tokens for a Resource?

Changing **Resource Server** configuration only controls which tokens the API **accepts**; it **does not cause the Authorization Server to emit a new `aud`**.

~~~mermaid
flowchart TD
    A["API defines expected audience"] --> B["AS registers resource/API and scopes"]
    B --> C["OAuth client requests permission to call resource"]
    C --> D["AS issues access token with right aud"]
    D --> E["Client sends Bearer token to API"]
    E --> F["API verifies signature, iss, aud, time"]
    F --> G["API authorizes scope and resource permissions"]
~~~

If the API requires `aud=https://api.example.test/orders` while the issuer still emits `aud=shop-spa-client`, all corresponding Bearer requests will be rejected **properly under the new policy**. Fix the **token-issuance path/issuer contract**, never disable the audience validator to avoid 401s.

### 5.1. OAuth 2.0 Resource Indicators — RFC 8707

RFC 8707 defines the `resource` parameter for a client to specify the target resource when requesting authorization or tokens. Standard authorization request example, **if supported by the Authorization Server**:

~~~text
GET /authorize
  ?response_type=code
  &client_id=shop-spa-client
  &redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback
  &scope=openid%20orders.read
  &resource=https%3A%2F%2Fapi.example.test%2Forders
  &code_challenge=<PKCE_CHALLENGE>
  &code_challenge_method=S256
  &state=<RANDOM_STATE>
~~~

After exchanging the code for a token (with PKCE), the Authorization Server **may** issue an access token targeting the specified resource. Support for the `resource` parameter, how `aud` is populated, multiple resources, and unauthorized cases depend on the AS profile/policy.

Never assume "adding `resource` to any OAuth URL works with every IdP"; verify the provider contract. An `audience` parameter in some providers is also a **provider-specific extension**, not a universal standard name across every AS.

### 5.2. Scope Alone Does Not Guarantee the Right Audience

~~~text
Requested scopes: orders.read
~~~

Unless the IdP explicitly binds scopes to an API/resource, requesting `orders.read` alone does not guarantee an access token with `aud=orders-api`. Some issuers determine audience from resource identifiers or API permissions; others from client scope mappers; others from issuer-specific parameters.

So during integration, verify three things together:

~~~text
Client request:
    resource / API permission / provider-specific audience

Issued access token:
    aud = expected API resource

Resource Server:
    expected audience validator = exact same value
~~~

### 5.3. Never Modify a JWT by Editing the Payload on the Frontend

Signed JWS JWTs have signed claims. If the frontend alters `aud` in the payload and reassembles the token, the signature **becomes invalid**. If a client mints its own JWT with the desired audience using an untrusted private key, the Resource Server must also reject it.

~~~text
Wrong:
    Frontend decodes JWT → edits aud → re-encodes → sends to API

Right:
    Client asks AS to issue an access token for Orders API
    AS signs/issues token
    API verifies key/issuer/audience/token policy
~~~

### 5.4. What Permissions Are Needed to Call the API?

Audience confirms the token **is targeted at the resource**. For specific actions, the API also checks scopes/authorities. Example:

| API | Audience | Operation | Required Authority |
|---|---|---|---|
| Orders API | `https://api.example.test/orders` | GET orders | `SCOPE_orders.read` |
| Orders API | `https://api.example.test/orders` | POST order | `SCOPE_orders.create` |
| Payments API | `https://api.example.test/payments` | GET payments | `SCOPE_payments.read` |

Two tokens with the same Orders API audience can carry different scopes. Never treat "right audience" as permission for every endpoint, nor "right scope" as compensating for a wrong audience.

## 6. Sequence for Integrating an Issuer and Resource Server

Follow an ordered engineering sequence:

**Step 1 — Lock down the trusted issuer.** For example, `https://login.example.test/realms/shop`, distinguishing realm/tenant/environment. Fetch metadata/JWKS from a trusted source and enforce allowed JOSE algorithms.

**Step 2 — Define the API resource identifier.** For example, `https://api.example.test/orders`. The API must have an **expected audience** independent of the frontend's ID.

**Step 3 — Register the API and scopes.** At the issuer, register the Orders API resource, `orders.read`/`orders.create`, and grants/consent/permissions for the frontend per policy.

**Step 4 — Configure frontend/BFF to fetch the right access token.** Use Authorization Code + PKCE for browser/public clients; pass resource/API permissions or provider-specific `audience` in authorization/token requests if supported by the IdP.

**Step 5 — Configure the API to verify signature/issuer/time/audience.** Audience must be checked against the **resource identifier**, not `shop-spa-client`.

**Step 6 — Wire HTTP/method authorization.** Map `scope`/`scp` to `SCOPE_*` and protect each method/route; enforce object/tenant checks in the business layer.

**Step 7 — Test positive and negative cases.** Include a valid API token, a token for another API, a frontend ID token, an expired JWT, and a valid token missing scopes.

**Step 8 — Monitor rollout.** Watch `invalid_token` spikes grouped by issuer/audience without logging raw tokens or personal claims. When 401s occur from wrong audiences, fix token issuance or align the resource identifier—never loosen the allowlist arbitrarily.

## 7. Spring Security Servlet: Configuring JWT Audience for Orders API

Spring Security OAuth 2.0 Resource Server uses `JwtDecoder` to verify Bearer JWTs. For signed JWTs, the decoder typically runs **signature validation** with trusted keys, then applies an `OAuth2TokenValidator<Jwt>` chain for issuer, timestamps, and required claims.

### 7.1. Dependencies

Spring Boot Servlet/Spring MVC example:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

In real applications, JWT/JOSE dependencies must match the running Spring Security version. Modern Spring Boot starters bring in compatible Resource Server/JOSE artifacts via dependency management.

### 7.2. Using Spring Boot Supported Audience Configuration

In Spring Boot versions supporting audience configuration for JWT Resource Servers, an application can use:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - https://api.example.test/orders
~~~

Purpose:

- `issuer-uri`: configures trust toward the issuer and validates the `iss` claim.
- `audiences`: requires access tokens to contain an accepted audience via the version's auto-configuration mechanism.

**Version note:** verify Spring Boot configuration docs for **your exact project version** and confirm `spring.security.oauth2.resourceserver.jwt.audiences` is actually bound and enforced. Older versions that do not support this property may ignore it or fail binding; **never assume an unrecognized YAML line means an audience validator is active**.

When an application defines its own `JwtDecoder` bean or overrides the Resource Server decoder in `SecurityFilterChain`, some Spring Boot auto-configuration **no longer applies**; you must explicitly wire the audience validator into the active decoder.

### 7.3. Explicit Approach: Configuring a Custom `JwtDecoder`

To control the contract explicitly, declare:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/shop
      jwks-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
      audience: https://api.example.test/orders
~~~

`app.security.jwt.*` are **application-defined custom properties** that have no effect unless bound by a Java bean. The JWKS path is an illustrative URI; real issuers may publish JWK Sets at another URL.

A decoder bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwks-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String apiAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(apiAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Access token audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

#### Why Are Both Default Validators and Audience Validators Needed?

`NimbusJwtDecoder.setJwtValidator(...)` **replaces** the decoder's validator set. If you only attach:

~~~java
decoder.setJwtValidator(expectedAudience);
~~~

then default issuer/timestamp checks can be lost. In the right pattern, `JwtValidators.createDefaultWithIssuer(issuer)` provides the default issuer and timestamp validators for your Spring Security version, and `DelegatingOAuth2TokenValidator` combines them with audience validation. If your token profile requires **`exp` to be mandatory**, token type, tenant, or other constraints, add the corresponding validators.

**Audience checking compares claims on an already decoded/verified token.** `jwt.getAudience()` returns the audience list as represented by Spring Security. Never read `aud` from an unverified payload to construct a principal; rely on a trusted decoder/JWS validation.

#### Algorithms and Keys Must Be Allowlisted

`jwsAlgorithm(SignatureAlgorithm.RS256)` illustrates an issuer signing with RS256. **Not every issuer uses RS256.** Confirm the exact algorithm supported by the issuer and allowlist it alongside a trusted JWKS source; never trust `alg` or `jku` supplied in a Bearer token to fetch keys from arbitrary URLs.

If you already have `issuer-uri` and need an explicit JWKS URI, providing both the contract issuer and JWK Set can reduce startup dependency on metadata discovery, though the Resource Server must still protect public key fetching/refreshing.

### 7.4. Wiring HTTP Authorization into the API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersHttpSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

There are **two boundaries** here:

1. `JwtDecoder` requires **the Orders API audience** plus matching issuer/signature/timestamps.
2. `authorizeHttpRequests` requires **specific scopes per HTTP method**.

If a token has `aud=payments-api`, it is rejected during **authentication** before `hasAuthority("SCOPE_orders.read")` is ever evaluated. If a token has the right audience yet lacks the scope, it may authenticate and then be denied during **authorization**.

This illustrates security rules rather than a complete runnable app: you still need controllers/services, dependency management, real properties, audience registration at the issuer, appropriate CSRF/CORS/session policies, and object-level authorization when serving data.

### 7.5. Do Not Configure Using the Frontend Client ID

Anti-pattern:

~~~yaml
app:
  security:
    jwt:
      audience: shop-spa-client  # WRONG if this is only the frontend's OAuth client
~~~

Replace with the proper resource identifier:

~~~yaml
app:
  security:
    jwt:
      audience: https://api.example.test/orders
~~~

If a provider uses an **API application/client registration ID** as the audience, configure the exact **API registration** ID per contract—never substitute the SPA's ID. String formats may vary, yet **role and intended token recipient** determine correctness.

## 8. WebFlux Resource Server: Audience Validator on `ReactiveJwtDecoder`

With WebFlux, the corresponding types are `ReactiveJwtDecoder` and `SecurityWebFilterChain`. Security rules remain the same with an asynchronous execution pipeline.

### 8.1. Reactive Dependencies

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 8.2. Real Decoder Bean with API-Specific Audience

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
class OrdersReactiveJwtConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwks-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String apiAudience) {

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(apiAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT is not intended for Orders API",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

`setJwtValidator(...)` also **replaces** existing validators on the reactive decoder. Combine default issuer/time validators with audience validation so no check is accidentally dropped during customization.

### 8.3. Reactive HTTP Security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersReactiveHttpSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

In the reactive stack, `ReactiveJwtDecoder.decode(...)` returns `Mono<Jwt>`. A JWT with the wrong audience emits an authentication error and creates no valid principal; never write `onErrorResume(...)` returning a dummy `Jwt`/`Authentication` when verification fails.

### 8.4. Servlet vs. WebFlux Differences

| Responsibility | Servlet | WebFlux |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Nimbus implementation | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| URL authorization config | `authorizeHttpRequests` | `authorizeExchange` |
| Scope authority | `SCOPE_orders.read` | `SCOPE_orders.read` |
| Audience validation | `OAuth2TokenValidator<Jwt>` | `OAuth2TokenValidator<Jwt>` attached to reactive decoder |

Do not define a Servlet `SecurityFilterChain` expecting it to protect a pure reactive WebFlux application. Ensure the chain and decoder match **the exact runtime** your application runs.

## 9. Differences Across Issuers: Do Not Copy Configuration Blindly

Different identity providers register APIs and populate audiences in access tokens differently. **Spring Resource Server should only accept values the issuer actually emits per contract**, not property names lifted from another provider's example.

### 9.1. Providers Supporting "API Identifier" Registration

Some issuers, such as Auth0's API model, let you declare an API with an **identifier** and request access tokens for that API using a **provider-specific `audience` parameter**.

Conceptual flow:

~~~text
Application:
    Client ID = shop-spa-client

API Registration:
    Identifier = https://api.example.test/orders

SDK-supported authorization request:
    audience = https://api.example.test/orders
    scope    = orders.read

Access token:
    aud      = https://api.example.test/orders
~~~

Illustrative parameters:

~~~text
GET /authorize
  ?response_type=code
  &client_id=shop-spa-client
  &audience=https%3A%2F%2Fapi.example.test%2Forders
  &scope=openid%20orders.read
  &redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback
  &code_challenge=<PKCE_CHALLENGE>
  &code_challenge_method=S256
  &state=<RANDOM_STATE>
~~~

**Important:** `audience` in this authorization request is a **provider-supported mechanism**, not a standard OAuth 2.0 parameter every Authorization Server must accept. If your SDK/IdP lacks it, use that issuer's proper resource/API permission mechanism.

### 9.2. Keycloak: Audience Mapper and Client Scopes

In Keycloak-based systems, one option is configuring **client scopes** and an **Audience mapper** to include the API resource client's identifier in `aud` inside access tokens.

Conceptual example:

~~~text
Realm: shop

Frontend client:
    shop-spa-client

Resource/API client:
    orders-api

Mapper on client scope:
    included client audience = orders-api
    add to access token = true

Result (illustrative):
    aud = ["orders-api", ...]
~~~

Depending on the Keycloak version/config, an API resource may use its client ID as audience or a mapper may add a **custom audience**. Whether a scope is assigned as default/optional, scope request permissions, and role mapping policies affect which tokens receive `aud`.

Things to verify on test tokens:

1. Tokens for the Orders API actually contain `aud=orders-api` or the agreed custom audience.
2. Frontend tokens meant for another resource **do not automatically carry** the Orders audience merely from logging into the same realm.
3. The audience mapper applies to **access tokens**, not confused with ID tokens.
4. Scopes/roles used for authorization at Orders API are mapped reliably.
5. If a mapper accidentally adds every API audience to every token, re-evaluate resource isolation.

Do not change Orders API to `expectedAudience="account"` just because tokens currently carry a default `account` audience; first verify whether that is actually the resource ID provisioned for the Orders API.

### 9.3. Microsoft Entra ID: Distinguishing SPA ID from API Registration ID

An Entra ID architecture often has **two app registrations**:

~~~text
App registration 1: Shop SPA
    client/application ID = SPA_CLIENT_ID

App registration 2: Orders API
    client/application ID = ORDERS_API_APP_ID
    exposed delegated scope = orders.read
    application ID URI = api://ORDERS_API_APP_ID
~~~

The frontend requests the scope exposed by the **Orders API app registration**:

~~~text
scope=api://ORDERS_API_APP_ID/orders.read
~~~

Access tokens issued for the API may use the **API application/client ID** or **resource URI** as `aud`, depending on token version and resource/issuer configuration. The expected value must follow the **Entra contract for that exact token version and API registration**, never an arbitrary guess.

Key distinction:

~~~text
SPA_CLIENT_ID:
    client requesting the token (not the Orders API audience)

ORDERS_API_APP_ID:
    the API's application registration
    may be the access token's aud value per provider contract
~~~

Beyond audience, Entra tokens may use claims such as `scp` for delegated permissions, `roles` for application permissions, and `azp` or `appid` for the calling client depending on version/profile. The Resource Server still needs issuer/tenant validation and proper permission mapping; never replace audience checks with `azp`/`appid`.

### 9.4. Mental Model Comparison Table, Not Shared Configuration

| Issuer Model | Client Request Identifier | API Audience Typically Based On |
|---|---|---|
| AS supporting RFC 8707 | `resource=<resource URI>` | Resource identifier per contract |
| Provider supporting custom `audience` param | `audience=<API identifier>` | Registered API identifier |
| Keycloak with audience mapper | Appropriate client scope/mapping | API client ID or custom audience |
| Microsoft Entra ID | API exposed scopes/permissions | **API registration** ID or URI per token version |

**There is no universal rule that "`aud` must always be a URL" or "`aud` must always be a GUID."** The real rule is: **whichever resource identifier the issuer issues tokens for, the Resource Server must require that exact resource.**

## 10. When the Frontend Receives a Wrong-Audience Token: Where to Start?

A real-world scenario:

~~~text
Client configuration:
    client_id = shop-spa-client

Observed access token:
    aud = shop-spa-client

Orders API configuration:
    expected audience = https://api.example.test/orders

Result:
    HTTP 401 invalid_token
~~~

Do not immediately conclude "the Resource Server is broken." Possible causes include:

- The frontend sent an **ID token** instead of an access token.
- The client is requesting a token for another default resource.
- The AS has not registered the Orders API or has not granted the client permission to call it.
- The frontend/SDK did not pass `resource` or provider-specific `audience`.
- A token was cached before changing the resource/scope.
- The API and AS are pointing to **different environments/tenants**.
- The API configured the wrong audience identifier relative to its actual resource registration.

### 10.1. Diagnostic Steps

**One:** determine whether the Bearer header carries an **access token** or an ID token. Never dump raw tokens into logs during investigation.

**Two:** confirm `iss` and the signature against the trusted issuer using a verifier/decoder library. Only after verification, inspect `aud`, `scope`/`scp`, and `client_id`/`azp` claims for diagnostics in a secure environment.

**Three:** compare `aud` against the **API identifier** registered at the issuer, not against the frontend client ID.

**Four:** verify that the authorization/token request genuinely requests the right resource/API permission, and that the AS permits the frontend client to obtain that token.

**Five:** update the client request or issuer configuration to issue tokens with the right audience. Then accept only that exact audience in Spring Resource Server.

**Six:** run negative tests with a token issued for Payments API, a frontend ID token, and a wrong-issuer token.

### 10.2. Client-Side Token Caches Can Mislead

Many OAuth client libraries cache tokens by account, resource/scope, or internal keys. If the frontend changes how it requests tokens yet keeps reusing an old cached access token, the API still sees the wrong `aud`.

The fix is using the library's API to request **a token for the proper resource/scope** while respecting cache key semantics, token lifecycles, and consent. Never hand-edit JWT payloads or disable audience validation. Avoid telling users to manually clear storage when the library provides proper resource/scope acquisition APIs.

### 10.3. BFF and Server-Rendered Web Apps

With a BFF, the browser may only hold a session cookie to the BFF, while the BFF acts as the OAuth client holding access tokens server-side. When the BFF calls the Orders API, the **access token the BFF obtains from the issuer** must also have an audience for the Orders API.

Being a confidential backend client never exempts it from audience checks. The BFF's `client_id` identifies the calling client, while the token-receiving resource is still the Orders API.

### 10.4. Mobile/Public Clients

Mobile clients can use Authorization Code + PKCE much like SPAs. The mobile app's `client_id` and the Orders API audience must remain separate. Because mobile apps cannot securely hold a client secret, proper resource token issuance and server-side validation are even more critical and can never be replaced by trusting a client-sent ID.

## 11. When an API Is Registered as an "OAuth Client" at the Issuer

This is a very common source of confusion. An IdP may label every registration a "client" or "app," including both frontends and backend APIs. Then there are two IDs:

~~~text
frontendOauthClientId = shop-spa-client
ordersApiAppClientId  = orders-api
~~~

If the issuer emits an access token:

~~~json
{
  "aud": "orders-api",
  "client_id": "shop-spa-client",
  "scope": "orders.read"
}
~~~

then `aud=orders-api` is **right** under that provider's model. Do not misread "audience is not the frontend `client_id`" as "audience can never be a client ID." It **can be the API's client/application ID** when that is the resource identifier used by the issuer.

### 11.1. Name Configuration Properties Clearly to Avoid Ambiguity

Instead of:

~~~yaml
app:
  security:
    client-id: shop-spa-client
~~~

and using `client-id` to validate `aud`, distinguish them clearly:

~~~yaml
app:
  oauth:
    frontend-client-id: shop-spa-client
  security:
    jwt:
      expected-resource-audience: orders-api
~~~

These are **custom-defined properties** that must be bound in Java config when used. Clear naming prevents developers from accidentally changing a frontend login variable and relaxing or breaking Resource Server policy.

### 11.2. `azp` or `client_id` Can Still Be Checked Separately

Sometimes an API only allows a specific set of OAuth clients to call it, even among tokens with the right audience. In that case, add a **client allowlist**:

~~~text
Token accepted =
    trusted issuer/signature/time
    AND aud = Orders API
    AND client_id/azp in allowed client list (if required)
    AND HTTP scope sufficient for endpoint
~~~

This is an **additional policy layer**, not a replacement for audience validation. Also verify the exact claim for the token profile: do not blindly equate `azp`, `appid`, and `client_id` across providers.

## 12. Does the `aud` Claim Hold One Value or Multiple Values?

Per JWT, `aud` can be a string or an array of audience identifiers depending on the token profile. Both payloads represent a single audience:

~~~json
{
  "aud": "https://api.example.test/orders"
}
~~~

~~~json
{
  "aud": ["https://api.example.test/orders"]
}
~~~

In Spring Security, `Jwt.getAudience()` typically returns a normalized `List<String>` from the JWT claim. Thus, the validator:

~~~java
jwt.getAudience().contains(expectedAudience)
~~~

expresses **the token contains at least the expected resource audience**.

### 12.1. Multi-Audience Tokens

An access token may contain:

~~~json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/payments"
  ],
  "scope": "orders.read payments.read"
}
~~~

The Orders API checks that `aud` contains the Orders identifier; the Payments API checks that `aud` contains the Payments identifier. If the issuer **explicitly supports and permits** multi-resource tokens, both APIs may accept the token under that contract. Still, this should not be assumed as the best default.

**Security trade-off:** a leaked Bearer token can be used across more resources if it carries multiple audiences. Scope each API distinctly, limit issuance, shorten lifetimes, and apply token binding per risk policy. Many organizations prefer **resource-specific** access tokens to narrow blast radius.

### 12.2. When Should Only a Single Audience Be Accepted?

If the API/issuer requires tokens to target solely the Orders API, enforce a stricter rule:

~~~java
OAuth2TokenValidator<Jwt> singleAudience = jwt -> {
    boolean valid = jwt.getAudience().size() == 1
        && jwt.getAudience().contains("https://api.example.test/orders");
    return valid
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Unexpected audiences", null));
};
~~~

This differs from `contains(...)`: a token carrying both Orders and Payments audiences will be **rejected**. Use this only when the issuer profile guarantees a single-audience policy; if a valid issuer emits multi-audience tokens, the stricter rule will cause compatibility failures.

### 12.3. Identifier Migration Windows

When migrating audience from `orders-api-v1` to `https://api.example.test/orders`, a short window accepting both values may be needed to avoid breaking unexpired tokens:

~~~java
import java.util.Set;

Set<String> allowedApiAudiences = Set.of(
    "orders-api-v1",
    "https://api.example.test/orders"
);

OAuth2TokenValidator<Jwt> audienceDuringMigration = jwt -> {
    boolean matches = jwt.getAudience().stream()
        .anyMatch(allowedApiAudiences::contains);
    return matches
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong resource", null));
};
~~~

This is an **illustrative migration policy**. It allows **any** audience in the allowlist without requiring a single audience. Enable it only when both identifiers genuinely represent the **same resource/trust boundary**. If unrelated extra audiences must be rejected, add a corresponding check.

Never add `shop-spa-client` to the allowlist just to let ID tokens or frontend tokens pass validation. Set a firm migration end date, monitor issuer token adoption, and remove the legacy identifier once old tokens expire.

### 12.4. Avoid "Substring Contains" Comparisons

Anti-pattern:

~~~java
// WRONG: can accept lookalike or unrelated identifiers.
boolean accepted = jwt.getAudience().stream()
    .anyMatch(aud -> aud.contains("orders"));
~~~

Values like:

~~~text
https://api.example.test/orders
https://evil.example.test/orders-mock
https://api.example.test/orders-admin
orders-test
~~~

all contain "orders" yet represent completely different resources. **Perform exact comparisons against approved identifiers**, never substring matches, overly broad regexes, or arbitrary prefixes as an audience policy.

## 13. Multiple Issuers or Tenants: Audience Must Bind to Trust Context

A Resource Server may accept tokens from multiple Authorization Servers (multiple realms, tenants, or partners). In that case, you cannot maintain a single global `expectedAudience` while ignoring its relationship to the issuer.

Example:

| Trusted Issuer | Corresponding Resource Audience |
|---|---|
| `https://login.partner-a.example.test/realm/orders` | `orders-api-partner-a` |
| `https://login.partner-b.example.test/realm/orders` | `https://api.example.test/orders` |

Each issuer may have its own:

- Set of public keys.
- Allowed signing algorithms.
- Resource identifiers and token profiles.
- Scopes/roles/client identity encodings.
- Time, tenant, and token type policies.

### 13.1. Never Pick a JWKS URI from an Unverified `iss` Claim Without an Allowlist

An unverified JWT can carry:

~~~json
{
  "iss": "https://attacker.example.test",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read"
}
~~~

If the Resource Server reads `iss` and **automatically fetches JWKS from any arbitrary issuer**, an attacker can stand up their own issuer, sign tokens with their own keys, and trick the system into trusting them.

With multiple issuers, maintain an **approved issuer registry** and select the matching `JwtDecoder`/`ReactiveJwtDecoder` per policy. The `iss` claim at decoder-selection time may only serve as a **routing hint into the allowlist**, and **only after signature/claims validation** can it be treated as trustworthy.

### 13.2. Issuer–Audience Pair Policy

A contract structure:

~~~text
Issuer A:
    trusted keys A
    expected aud A = orders-api-partner-a

Issuer B:
    trusted keys B
    expected aud B = https://api.example.test/orders

Token from A with aud B:
    reject (unless A's contract is explicitly allowed to issue tokens for B)
~~~

Do not treat issuers as having equivalent permissions merely because they share an audience string or scope name. If issuer A and issuer B use `SCOPE_orders.read` with different meanings, separate mappings/authorization checks are required to prevent cross-issuer privilege escalation.

### 13.3. Tenant ID Does Not Replace Audience

Example token:

~~~json
{
  "iss": "https://login.example.test/tenant-a",
  "tid": "tenant-a",
  "aud": "billing-api",
  "scope": "orders.read"
}
~~~

Matching tenant is not enough: the audience is still Billing API. Conversely, a token with the right Orders API audience still does not authorize reading orders belonging to another tenant. Both checks serve different purposes:

~~~text
audience validation → token is intended for Orders API
tenant validation   → token belongs to an accepted tenant
domain permission   → order access is permitted for principal/tenant
~~~

### 13.4. Multiple Security Chains Do Not Automatically Ensure Each API Checks the Right Audience

An application has:

~~~text
/orders/**   → Orders endpoints
/payments/** → Payments endpoints
~~~

If both share **one `JwtDecoder` that only checks a single shared frontend audience**, URLs can still accept tokens meant for the wrong resource. You can define multiple `SecurityFilterChain`/`SecurityWebFilterChain` beans, each wired with its appropriate decoder/validator, or establish a consistent token policy across the API gateway and downstream resources.

In Spring Security, chain ordering usually picks the **first matching chain**. Verify that each chain actually uses its intended decoder/resource audience rather than assuming "an audience validator bean was declared somewhere."

## 14. Microservices, API Gateway, and Token Relay

Audience becomes especially important when requests traverse multiple services:

~~~mermaid
flowchart LR
    UI["Frontend"] -->|"Token aud=Orders API"| GW["Gateway"]
    GW -->|"Bearer token"| O["Orders API"]
    O -->|"Calls Payments API?"| P["Payments API"]
~~~

A frontend token with `aud=Orders API` **does not automatically become** a valid token for the Payments API. If the Orders API forwards that same Bearer token to the Payments API, a Payments API that properly checks audience will reject it—which is often the **intended security behavior**.

### 14.1. Patterns for Designing Downstream Calls

| Pattern | Conditions |
|---|---|
| **Token relay** | Appropriate only if downstream is permitted by the issuer to receive that exact token (matching audience/resource binding) and risk policy approves |
| **Client credentials** | Orders API obtains a fresh service token intended for Payments API using its service identity and permissions |
| **OAuth 2.0 Token Exchange (RFC 8693)** | If supported by AS, exchanges the token/delegation for a token targeting the downstream resource while preserving delegation bindings |
| **Gateway-issued internal identity** | Only within a deliberately designed internal trust model with strong service-to-service authentication and anti-spoofing controls |

Never solve downstream 401s by making the Payments API accept the frontend's `client_id` as its audience or turning off audience checks system-wide.

### 14.2. If the Gateway Verified the Token, Should Downstream Verify Again?

It depends on your trust boundary. If downstream can be reached independently or from multiple callers, it should validate access tokens and check its own audience. If the gateway is a **strictly enforced single point of control**, downstream may rely on an internally propagated identity/authorization mechanism with strong integrity protection, but that must be an explicit trust architecture—never "the gateway checked the issuer so every service skips audience."

### 14.3. A Single Token Shared Across Many APIs Can Increase Risk

A token with:

~~~json
{
  "aud": ["orders-api", "payments-api", "reports-api"],
  "scope": "orders.read payments.read reports.read"
}
~~~

is accepted at all three resources if each uses `contains(...)`. Weigh the **blast radius if the token leaks**, least privilege, and revocation capabilities. Resource-specific access tokens generally limit token replay across APIs.

## 15. When the Resource Server Uses Opaque Tokens/Introspection

Audience matters not only for signed JWTs. If a Resource Server uses `oauth2ResourceServer().opaqueToken(...)` and RFC 7662 introspection, the issuer may return:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-spa-client",
  "scope": "orders.read",
  "aud": "https://api.example.test/orders",
  "exp": 1924992000
}
~~~

The Resource Server must still ensure the access token is meant for the Orders API. `active=true` only indicates the token is active according to the AS, which **is not always enough to prove resource binding**.

### 15.1. RFC 7662 Does Not Guarantee Responses Always Include `aud`

An introspection response returns metadata per the contract and the introspection caller's permissions. If the Orders API requires an audience:

- Agree with the AS to return `aud` or equivalent resource metadata.
- Or require the AS to **enforce resource binding** when deciding `active` for the Orders API's introspection client.
- Or add another organization-managed, trustworthy resource verification mechanism.
- Without sufficient proof, **reject** rather than treating a missing `aud` as "accept all."

### 15.2. Example Custom `OpaqueTokenIntrospector` Checking Audience

Assume a delegate `OpaqueTokenIntrospector` already performs introspection against a trusted AS:

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean accepted =
            (aud instanceof String value
                && expectedAudience.equals(value))
            || (aud instanceof Collection<?> values
                && values.contains(expectedAudience));

        if (!accepted) {
            throw new BadOpaqueTokenException(
                "Token audience does not match this API");
        }

        return principal;
    }
}
~~~

This is an **illustrative decorator**, not a built-in Spring Security class. It must wrap the **actual introspector used by the Resource Server**. If the response lacks `aud` and the AS provides no other contract-backed binding proof, the decorator rejects the token.

Systems with different `aud` formats (such as introspection-specific structures) need a dedicated metadata adapter; never guess from the frontend `client_id` as a substitute.

### 15.3. AS Failures Must Never Turn into Skipping Audience Checks

If introspection times out, returns 5xx, or omits required fields, never synthesize an `OAuth2AuthenticatedPrincipal` with `aud=orders-api` to "keep the API up." Without a trustworthy verification result, grant no authentication. If introspection caching is used, rely only on verified results still valid under your freshness/revocation policy.

## 16. Testing the Audience Validator Independently

Audience should be tested at **two layers**:

1. **Validator unit tests**: prove the audience comparison policy passes/fails accurately, including string/list forms, multi-audience, and missing claims.
2. **Resource Server integration tests**: prove Bearer JWTs are verified by the **real decoder** for signature, issuer, audience, and timestamps before creating `Authentication`.

Doing only layer one risks writing a correct validator and forgetting to wire it into the live HTTP decoder. Doing only layer two with a JWT that is invalid in multiple ways at once means a 401 does not prove the audience validator actually ran.

### 16.1. Extracting the Validator into a Reusable Class

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class ApiAudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public ApiAudienceValidator(String expectedAudience) {
        if (expectedAudience == null || expectedAudience.isBlank()) {
            throw new IllegalArgumentException(
                "Expected API audience must be configured");
        }
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt token) {
        if (token.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Access token is not intended for this resource",
                null
            )
        );
    }
}
~~~

Characteristics:

- `expectedAudience` comes from **server configuration**, never from headers/request input.
- Uses exact `String.equals` matching via `contains(...)`.
- If the `aud` claim is absent or lacks the resource identifier, the validator fails.
- The error message **does not echo raw tokens or audiences** in public responses.
- This is solely a **claims validator**: signature and issuer must still be verified by the decoder and combined validator chain.

When wiring this class into the decoder:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new ApiAudienceValidator(apiAudience)
    )
);
~~~

### 16.2. Unit Testing Audience Policy with Synthetic `Jwt` Objects

Test dependencies:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Example:

~~~java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class ApiAudienceValidatorTest {

    private static final String ORDERS =
        "https://api.example.test/orders";
    private static final String PAYMENTS =
        "https://api.example.test/payments";

    private final ApiAudienceValidator validator =
        new ApiAudienceValidator(ORDERS);

    private Jwt jwtWithAudiences(List<String> audiences) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-only-placeholder")
            .header("alg", "RS256")
            .claim("iss", "https://login.example.test/realms/shop")
            .claim("aud", audiences)
            .issuedAt(now.minusSeconds(30))
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    @Test
    void acceptsOrdersAudience() {
        var result = validator.validate(
            jwtWithAudiences(List.of(ORDERS)));
        assertThat(result.getErrors()).isEmpty();
    }

    @Test
    void rejectsPaymentsAudience() {
        var result = validator.validate(
            jwtWithAudiences(List.of(PAYMENTS)));
        assertThat(result.getErrors()).isNotEmpty();
    }

    @Test
    void allowsMultipleAudiencesWhenOrdersIsIncluded() {
        var result = validator.validate(
            jwtWithAudiences(List.of(PAYMENTS, ORDERS)));
        assertThat(result.getErrors()).isEmpty();
    }

    @Test
    void rejectsEmptyAudience() {
        var result = validator.validate(
            jwtWithAudiences(List.of()));
        assertThat(result.getErrors()).isNotEmpty();
    }
}
~~~

**Scope of this test:** `Jwt.withTokenValue(...)` **does not create a signed JWT** and does not invoke `JwtDecoder`. It only builds a test `Jwt` object and calls the audience validator directly. It proves the **audience comparison** logic, not signature verification, issuer/time checks, or HTTP wiring.

### 16.3. Testing String vs. Array `aud`

If the issuer can emit `aud` as either a string or an array, also test:

~~~text
aud = "https://api.example.test/orders"
aud = ["https://api.example.test/orders"]
aud = ["https://api.example.test/payments",
       "https://api.example.test/orders"]
aud = []
aud = missing
~~~

To test **real claim conversion**, sign compact JWTs for each payload shape and decode them through the actual `JwtDecoder`. Building a `Jwt` object with a builder only tests **already-normalized input** and misses JWT JSON parsing/conversion.

## 17. HTTP Testing with Genuinely Signed Access Tokens

A secure audience configuration must be tested through the live security filter chain, not solely with unit tests.

### 17.1. Minimum Test Matrix

| Case | JWS Signature | Issuer | Audience | Scope | Expected |
|---|---|---|---|---|---|
| Valid token | Valid | Valid | Orders API | `orders.read` | HTTP 200 if controller allows |
| Wrong-audience token | **Valid** | Valid | Payments API | `orders.read` | **401** |
| Token with ID-token-like audience | Valid | Valid | Frontend client ID | No API scopes | **401** if audience/profile properly enforced |
| Wrong-issuer token | Valid | Wrong | Orders API | `orders.read` | **401** |
| Bad-signature token | Invalid | Valid | Orders API | `orders.read` | **401** |
| Expired token | Valid | Valid | Orders API | `orders.read` | **401** |
| Missing-scope token | Valid | Valid | Orders API | `orders.create` | **403** |
| No token | N/A | N/A | N/A | N/A | **401** on protected endpoints |

**The wrong-audience case must be signed with the same trusted key** as the valid token. If a wrong-audience token also has a bad signature, a 401 only proves JWS verification failed and **does not prove audience validation**.

### 17.2. Creating Test Access Tokens with Nimbus JOSE/JWT

A helper producing tokens with **real RS256 signatures**:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String signedAccessToken(
        RSAPrivateKey testPrivateKey,
        String audience,
        String scope) throws JOSEException {

    Instant now = Instant.now();
    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer("https://login.example.test/realms/shop")
        .subject("test-user")
        .audience(audience)
        .issueTime(Date.from(now.minusSeconds(30)))
        .notBeforeTime(Date.from(now.minusSeconds(30)))
        .expirationTime(Date.from(now.plusSeconds(300)))
        .claim("client_id", "shop-spa-client")
        .claim("scope", scope)
        .build();

    SignedJWT jwt = new SignedJWT(
        new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID("test-key")
            .build(),
        claims
    );
    jwt.sign(new RSASSASigner(testPrivateKey));
    return jwt.serialize();
}
~~~

To run integration tests, generate an RSA key pair in the **test runtime** and configure the real decoder to trust that **test public key**. In production, the decoder must use the real issuer's JWKS/keys; **never** let test private keys or trust in test keys leak into production configuration.

### 17.3. Servlet: Sending Real JWTs with `MockMvc`

Assume the test application wires a real `NimbusJwtDecoder` using the test public key, issuer/time/audience validators, and a `GET /api/orders/42` controller:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAudienceHttpTest {

    @Autowired
    MockMvc mockMvc;

    // Must be initialized by a test fixture holding the matching public key.
    RSAPrivateKey testPrivateKey;

    @Test
    void wrongResourceAudienceIsRejected() throws Exception {
        String token = signedAccessToken(
            testPrivateKey,
            "https://api.example.test/payments",
            "orders.read"
        );

        mockMvc.perform(get("/api/orders/42")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This is an **integration test pattern**: to run it, provide `testPrivateKey` via a fixture/bean with a clear lifecycle, configure the matching public key in the decoder, and define the route/controller and issuer properties as described. You cannot simply drop this class into a production project assuming key pairs/controllers exist automatically.

### 17.4. WebFlux: Sending Real JWTs via `WebTestClient`

With WebFlux and a real `NimbusReactiveJwtDecoder`:

~~~java
webTestClient
    .get()
    .uri("/api/orders/42")
    .headers(h -> h.setBearerAuth(
        signedAccessToken(
            testPrivateKey,
            "https://api.example.test/payments",
            "orders.read"
        )
    ))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Switching the token to `aud=https://api.example.test/orders` with the same key/issuer/time/scope must pass authentication; if the endpoint controller and business policy permit, it can return HTTP 200. With a right-audience token carrying `scope=orders.create`, a GET rule requiring `orders.read` will typically return 403.

### 17.5. Why Are `mockJwt()` and `jwt()` Test Helpers Not Enough?

Spring Security Test provides `mockJwt()` for WebFlux and `jwt()` for Servlet. They typically **inject a simulated authentication into the context** to test authorization, **without calling the real decoder**. Example:

~~~java
// Useful for testing HTTP authorization, DOES NOT prove aud verification.
mockMvc.perform(get("/api/orders/42")
    .with(jwt().jwt(token -> token
        .claim("aud", "https://api.example.test/payments"))));
~~~

This snippet requires appropriate static imports in real test code. A wrong `aud` inside `mockJwt()`/`jwt()` can **still be treated as an authenticated principal**, because the helper intentionally bypasses token verification to test permissions.

To prove **the decoder checks audience**, use **genuinely signed Bearer JWTs** and send requests through the real `JwtDecoder`/`ReactiveJwtDecoder`. Combine with validator unit tests to isolate causes.

### 17.6. Protecting CI and Test Fixtures

- Use only private keys generated specifically for tests, never real AS signing keys.
- Never commit real user raw access tokens into the repository.
- Never print JWTs in assertion errors, console logs, traces, or CI artifacts.
- Compute `exp` relative to test execution time so positive controls do not expire months later.
- Expired-JWT tests must set `exp` far enough in the past to exceed clock skew.
- Avoid real ID tokens as test fixtures unless permitted by data/environment rules; generate synthetic JWTs with ID-token-like audiences using test keys.
- If running a JWKS HTTP test server, serve only public keys on loopback and shut down the server after tests.

## 18. Troubleshooting Table for Common Audience Issues

| Symptom | Likely Cause | Safe Resolution |
|---|---|---|
| Access token has `aud=shop-spa-client` | ID token sent, or issuer issued token for frontend/default audience | Confirm token type; request **an access token for the API resource** |
| Access token has `aud=payments-api` when calling Orders API | Client requested wrong resource/scope or relayed wrong token | Request a token for Orders API; never widen audience allowlist |
| Valid issuer/signature yet 401 | Audience/time/profile validation rejected it | Check API registration without exposing raw JWTs |
| Right audience yet GET returns 403 | Missing `SCOPE_orders.read` or business permission | Check scope grants and HTTP/domain authorization |
| `aud` is an API application GUID instead of a URI | Provider uses the API registration ID for this token version | Configure the exact **API ID**, not the SPA ID |
| `aud` is missing | Token profile omits audience or wrong token type/resource | Clarify issuance contract; reject if audience is mandatory |
| Added `audiences` YAML yet wrong-resource token gets 200 | Property unbound or custom decoder overrode auto-configuration | Verify Spring Boot version and live decoder |
| Expired token accepted after adding audience validator | `setJwtValidator` overwrote default timestamp validators | Combine `JwtValidators.createDefaultWithIssuer(...)` with audience |
| Frontend keeps sending old-audience token | Client SDK cache/resource request not updated | Request token for right resource via SDK |
| Production accepts staging tokens | Environment issuer/audience allowlists mixed | Separate trust configs and test cross-env rejection |
| Token for another API still works | Resource Server only checks issuer/scope | Add resource audience validation |
| API derives audience from `Host` header | Expected audience influenced by request | Use trusted configuration |
| Wrong-audience JWT still passes `mockJwt()` | Test helper bypasses decoder/validators | Use genuinely signed JWTs via Bearer HTTP |
| Multi-audience token accepted | Validator uses `contains` | Decide whether multi-resource tokens are permitted |
| Downstream rejects incoming token | Token only targets upstream API | Use a downstream-targeted token or token exchange |
| Introspection `active=true` yet lacks `aud` | AS did not return resource metadata | Agree on AS resource binding; fail closed when proof is missing |

### 18.1. Do Not Conflate Every 401

~~~text
Token authentication errors:
    malformed token
    invalid JWS signature
    issuer not trusted
    audience mismatch
    expired / not-before
    token type/profile mismatch

Infrastructure errors:
    JWKS endpoint unavailable
    introspection timeout
    trusted key not currently available

Authorization errors:
    insufficient scope / role
    tenant/owner access denied
~~~

Authentication errors typically result in HTTP 401; authorization denials for an authenticated principal typically result in 403. Infrastructure errors may map to other statuses depending on exception handling. During diagnostics, identify **which layer failed** without leaking credentials or sensitive claims to clients.

### 18.2. Do Not Leak Raw JWTs During Error Handling

Never log:

~~~text
Authorization: Bearer eyJ...
client_secret=...
Full decoded claims from every request
~~~

Log bounded-cardinality failure categories instead:

~~~text
event=jwt_validation_failed reason=wrong_audience api=orders
event=jwt_validation_failed reason=invalid_issuer api=orders
event=jwt_validation_failed reason=expired api=orders
event=http_authorization_denied reason=insufficient_scope api=orders
~~~

For correlation, use a system-generated request/trace ID. Never use raw tokens, `sub`, or `jti` as metric labels. When inspecting staging tokens, inspect claims only in authorized environments with trusted tools—never paste real access tokens onto unapproved online debugging sites.

## 19. Anti-Patterns with Security Risks

### 19.1. Using the Frontend's `client_id` as the Default Audience

~~~java
// ANTI-PATTERN:
String expectedAudience = frontendClientId;
~~~

Unless the contract explicitly specifies **that exact value is the API's resource identifier** (very different from a plain frontend client ID), this risks accepting tokens intended for the client rather than the API.

### 19.2. Checking Only the Issuer

~~~java
// ANTI-PATTERN if the API needs audience yet adds no validator.
decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer)
);
~~~

This lacks resource binding; tokens from the same issuer meant for another API will be accepted if remaining checks pass.

### 19.3. Checking Only the Scope

~~~java
// ANTI-PATTERN if decoder does not validate resource audience.
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

`hasAuthority` checks permissions on an **already-authenticated** principal and does not ensure the token was issued for the Orders API. Audience validation must happen at the token layer.

### 19.4. Letting Missing `aud` Pass

~~~java
// ANTI-PATTERN:
boolean valid = jwt.getAudience().isEmpty()
    || jwt.getAudience().contains(expectedAudience);
~~~

If the access token contract requires an API audience, **a missing `aud` is an error**, not "accept any audience."

### 19.5. Using Substrings or Wildcards Without a Contract

~~~java
// ANTI-PATTERN:
boolean valid = jwt.getAudience().stream()
    .anyMatch(aud -> aud.startsWith("https://api.example.test/"));
~~~

A shared prefix can cover Orders, Payments, Admin, and future APIs. If an API must accept only Orders tokens, check the **exact resource identifier**.

### 19.6. Trusting Other Claims Based on an Unverified `aud`

~~~java
// ANTI-PATTERN:
Map<String, Object> claims = decodeBase64Payload(rawJwt);
if (claims.get("aud").equals(expectedAudience)) {
    return makeAuthenticationFromClaims(claims);
}
~~~

`aud` in an unverified JWT can be altered by an attacker. Only use claims as evidence after the decoder verifies signature, allowed algorithm, trusted key, and required validators.

### 19.7. Confusing API `aud` with Caller `azp`

`azp`/`client_id` may indicate the calling client, yet does not establish which resource receives the token. A token with `azp=shop-spa-client` could still target the Payments API. To restrict callers, add a client allowlist **in addition to** audience validation.

### 19.8. Configuring Audience from Client-Supplied Data

~~~java
// ANTI-PATTERN:
String expectedAudience = request.getHeader("X-Expected-Audience");
~~~

If the sender dictates the expected audience, policy becomes meaningless. API resource identifiers must come from **server-side trust configuration**.

### 19.9. Giving Every API the Same Frontend Audience

If Orders, Payments, and Admin APIs all accept `aud=shop-spa-client`, it becomes hard to tell which API a token was actually issued for, increasing cross-service replay risk. A shared audience makes sense only if there truly is **one unified resource/trust boundary** with compensating policies, not to avoid configuring the issuer per API.

### 19.10. Skipping Token Type Checks Because "Audience Is Checked"

Audience is crucial, yet may not prevent token substitution on its own. If an issuer emits multiple JWT token types, you may need to enforce **access token profile**, `typ`, or required claims. Do not hardcode `typ` if the issuer does not use that profile; align on the issuance contract.

## 20. Three-Phase Rollout Scenario

Suppose Shop Web initially only used OIDC login, and later added the Orders API.

### 20.1. Phase 1: OIDC Login Only

~~~text
Shop Web:
    client_id = shop-spa-client
    scope = openid profile

ID token:
    aud = shop-spa-client
~~~

At this stage, there is no reason for the Orders API to accept the frontend's ID token. The token was issued for the **client identity flow**, not for the Orders API.

### 20.2. Phase 2: Registering the Orders API Resource

~~~text
Issuer:
    API/resource identifier = https://api.example.test/orders
    scopes = orders.read, orders.create
    client permissions:
        shop-spa-client is permitted to request scopes

Frontend:
    requests an access token for the Orders API resource
~~~

Depending on the issuer, use RFC 8707 `resource`, provider-specific `audience`, or API-exposed scopes/mappers. Ensure the AS returns an access token with `aud` set to the resource and withholds tokens from unauthorized clients.

### 20.3. Phase 3: Protecting the Orders API

~~~text
Spring Resource Server:
    verify signature + trusted issuer
    require audience = https://api.example.test/orders
    require expiration/time validity

GET /api/orders/**:
    require SCOPE_orders.read

POST /api/orders:
    require SCOPE_orders.create

Service:
    require owner/tenant policy
~~~

Test with **old wrong-audience tokens**, new right-audience tokens, and valid tokens lacking scopes. Post-rollout, rejecting wrong-audience tokens with 401 is the intended security outcome; the client must fetch the proper token.

### 20.4. When an API Needs to Change Its Audience Identifier

Suppose the Orders API renames its resource ID from `orders-api-v1` to `https://api.example.test/orders`. A migration plan can be:

1. Register the new resource identifier at the issuer and configure the new issuance path.
2. Ensure the frontend/BFF can request tokens targeting the new resource.
3. During a short approved window, have the API accept **both identifiers for the same resource**, provided that does not widen the trust boundary.
4. Monitor issuer token issuance on the new identifier without logging raw tokens.
5. Wait until tokens carrying the old identifier expire naturally, then remove the legacy audience.
6. Re-run negative tests: tokens for Payments API and frontend ID tokens must still be rejected.

If new tokens receive 401 because the issuer is not configured yet, never add `shop-spa-client` to the allowlist as a shortcut. The issue to fix is **issuing tokens for the right resource**, not opening the API to client-centric tokens.

## 21. Self-Check Exercises

### Exercise 1 — Which Token Is for the Orders API?

Given:

~~~text
Frontend OAuth client ID = shop-spa-client
Orders API audience = orders-api

Token A:
    iss = trusted issuer
    aud = shop-spa-client
    scope = orders.read

Token B:
    iss = trusted issuer
    aud = orders-api
    scope = orders.read
~~~

**Question:** Which token should pass the Orders API's audience check?

**Answer:** Token B, assuming signature, timestamps, and token profile are valid. Token A is not intended for the Orders API despite having the same scope.

### Exercise 2 — Why Does an ID Token Have `aud=client_id`?

**Answer:** In OIDC, an ID token is issued to the **client** to attest login details, so its audience is typically the client ID. A Resource Server API must never use that as justification to accept ID tokens in place of access tokens.

### Exercise 3 — API Application ID vs. SPA Client ID

Given a system:

~~~text
SPA client ID = SPA-123
API app registration ID = API-456
Issuer issues access token aud = API-456
~~~

**Question:** Can `API-456` be used as the expected audience even though it is also an application/client registration ID?

**Answer:** Yes, **if the issuer uses the API registration ID as the resource audience**. Never replace it with `SPA-123` merely because the SPA is the OAuth client fetching tokens.

### Exercise 4 — Multi-Valued `aud`

Given:

~~~json
{
  "aud": ["orders-api", "payments-api"],
  "scope": "orders.read"
}
~~~

**Question:** Does `jwt.getAudience().contains("orders-api")` returning true mean the design is completely secure?

**Answer:** Not by itself. It satisfies an "at least one audience is Orders" policy, yet you must check whether the issuer permits multi-resource tokens, scope/resource binding, replay risks, and domain authorization. If policy allows only one audience, use a stricter validator.

### Exercise 5 — Frontend Changes Client ID

Suppose Shop Web changes `client_id` from `shop-spa-client-v1` to `shop-spa-client-v2` while still calling the same Orders API.

**Question:** Should the Orders API automatically change its expected audience to match the frontend client ID?

**Answer:** No. The Orders API's resource audience can stay unchanged. If the API restricts which OAuth clients may call it, update a **separate client allowlist/consent policy** rather than replacing the resource audience with a frontend ID.

### Exercise 6 — Valid Signature, Wrong Audience

A token is signed by the trusted issuer's key, `iss`/`exp` are valid, `scope=orders.read`, yet `aud=payments-api`. What must the Resource Server do?

**Answer:** Reject the token during **authentication/claims validation**, typically returning 401; never pass it on to HTTP authorization to grant access via `orders.read`.

### Exercise 7 — Right Audience, Missing Scope

A token has valid issuer/signature/time, `aud=orders-api`, only `scope=orders.create`, yet the client calls a GET requiring `orders.read`.

**Answer:** Authentication may succeed; authorization rejects due to missing `SCOPE_orders.read`, typically HTTP 403. This is not an audience error.

### Exercise 8 — Shared JWKS Across Multiple APIs

An issuer uses the same JWK Set to sign tokens for both Orders and Payments APIs. Can both simply check signature and issuer and accept the tokens?

**Answer:** No. Being signed by the same trusted issuer key does not make a Payments token valid for Orders. Each Resource Server must still check its resource audience or equivalent binding proof.

### Exercise 9 — Introspection Does Not Return `aud`

The AS returns `active=true` and `scope=orders.read` without an audience. Can we assume the token is intended for the Orders API?

**Answer:** No, unless another **trusted contract** guarantees the AS already enforced resource binding for the Orders API's introspection client. Without sufficient proof per policy, reject and renegotiate the AS contract.

### Exercise 10 — Gateway Relay to Payments

Shop Web receives an access token with `aud=orders-api`, the gateway sends it to the Orders API, and the Orders API forwards it to the Payments API. The Payments API rejects with 401; should Payments accept the Orders audience?

**Answer:** Never relax validation just to make relay work. Design dedicated tokens for the Payments API, client credentials, OAuth Token Exchange, or a relay model approved by issuer/architectural trust policy.

## 22. Checklist for Integrating Issuer with API Audience

### 22.1. Before Coding

- [ ] Have a diagram clearly identifying **OAuth client**, **Authorization Server**, and **Resource Server**.
- [ ] Understand that frontend/BFF `client_id` and **API resource identifier** are two distinct roles.
- [ ] Locked down issuer/realm/tenant and allowed signing algorithms.
- [ ] Locked down audience **exactly per the issuer's token profile**.
- [ ] Know whether the audience is a URI, API application/client ID, or another provider-specific identifier.
- [ ] Know the mechanism by which the frontend requests resource access tokens: `resource`, provider-specific `audience`, or API-exposed scopes/mappers.
- [ ] Distinguished ID tokens from access tokens.
- [ ] Have the list of scopes/permissions required by the API.

### 22.2. In Spring Security

- [ ] JWT signatures are verified with trusted keys/JWKS.
- [ ] `iss` claim is checked against the trusted issuer.
- [ ] `aud` is checked against the **expected API audience**, not a frontend client ID.
- [ ] `exp`/`nbf` and required profile claims are checked per contract.
- [ ] If using `setJwtValidator(...)`, default issuer/time validators remain combined.
- [ ] If using Spring Boot `jwt.audiences`, verified the property is supported by the framework version and enforced by the live decoder.
- [ ] HTTP methods/paths require appropriate scopes/authorities.
- [ ] Tenant/owner authorization is enforced in service/domain logic when required.
- [ ] If multi-issuer, each issuer has matching keys/audience/token profile.
- [ ] If opaque introspection, confirmed the AS provides or enforces resource binding.
- [ ] No wildcard/prefix audience matching enabled outside policy.

### 22.3. In Testing and Operations

- [ ] Positive test: right-issuer, right-audience, right-scope token accepted.
- [ ] Negative test: token for another API from the same issuer with similar scope rejected.
- [ ] Negative test: ID-token-like token meant for the frontend rejected.
- [ ] Negative test: bad-signature/wrong-issuer/expired JWT rejected.
- [ ] Positive authentication lacking scope yields an authorization error, not confused with audience errors.
- [ ] JWT audience tests use a **real decoder**, not solely `mockJwt()`/`jwt()`.
- [ ] Dev, staging, and production tokens/keys are never mixed.
- [ ] Raw access tokens/sensitive claims are never logged on 401/403 errors.
- [ ] Downstream token relay is permitted only per resource-binding/trust contract.
- [ ] Migration plan exists when changing audience identifiers, with a clear timeline to drop legacy values.

## 23. Summary

Remember the distinction between three strings:

~~~text
Frontend OAuth client:
    client_id = shop-spa-client

Authorization Server:
    iss = https://login.example.test/realms/shop

Orders Resource Server:
    expected aud = https://api.example.test/orders
~~~

An access token for the Orders API can carry both:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "client_id": "shop-spa-client",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read"
}
~~~

There is no contradiction: **`client_id` is who requested the token; `aud` is who receives the token.** The audience value may be an API URI or the ID of an **API application registration** per the issuer contract; what matters is never blindly substituting the **frontend's** client ID as the resource identifier.

With Spring Security Resource Server, a trustworthy setup combines:

~~~text
trusted JWS key / issuer
    AND signature / allowed alg
    AND issuer + time / token profile validation
    AND audience = THIS API
    AND scope / HTTP authorization
    AND domain / tenant ownership checks
~~~

**Audience errors usually must be fixed on both sides:** the Authorization Server must **issue access tokens for the right resource**, and the Resource Server must **validate the right resource audience**. Merely tweaking the frontend `client_id` or removing the validator may make things appear to work on the surface while breaking access-token boundaries across APIs.

## References

- [RFC 7519 — JSON Web Token (JWT), Audience Claim](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Boot — OAuth2 Resource Server Properties](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Keycloak Server Administration — Protocol Mappers / Client Scopes](https://www.keycloak.org/docs/latest/server_admin/)
- [Auth0 — API Authorization / Access Tokens](https://auth0.com/docs/secure/tokens/access-tokens)
- [Microsoft Identity Platform — Access Tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)