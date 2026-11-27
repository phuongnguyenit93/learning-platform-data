# 11.13. Restricting ID Token Reuse in API Calling Flows

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, after a user successfully logs in, the application may receive both an **ID token** and an **access token**. Both tokens may look like JWT strings and both contain `iss`, `sub`, and `exp` claims, yet they have **different purposes, audiences, and validation rules**.

**An ID token is issued by the OpenID Provider (OP) for the Relying Party (RP) to consume the End-User authentication result.** When the application needs to call a protected API, it normally must use an **access token intended for the Resource Server**. Sending an ID token as a bearer token to an API creates design flaws around audience validation, authorization, and token substitution.

After this lesson, you will be able to:

- Distinguish the roles of ID tokens, access tokens, refresh tokens, and application session cookies.
- Explain why **an ID token valid at the RP is not automatically valid at an API**.
- Analyze `aud`, `azp`, `iss`, `nonce`, `exp`, and why signature verification alone is insufficient.
- Recognize risks of **token substitution**, confused deputy, personal claim leakage, and bearer credential reuse.
- Use `OAuth2AuthorizedClient` in Spring Security to obtain the **access token** when calling APIs.
- Configure a JWT Resource Server to validate issuer, audience, and scopes/authorities of **access tokens**.
- Understand when token exchange or service-to-service delegation is needed rather than turning an ID token into an access token.
- Identify the limits of replay protection, sessions, and logout mechanisms.

## 1. Real-World Problem: After Login, Which Token Goes to the API?

Suppose a system has three components:

- **Employee Portal**: Spring Boot web application acting as OAuth 2.0 Client and OIDC Relying Party.
- **Corporate Identity Provider**: OpenID Provider / Authorization Server where employees log in.
- **Orders API**: Resource Server exposing order lists and order management operations.

Portal uses the OIDC Authorization Code flow. After a successful callback, the OP may return:

~~~text
ID token:       eyJhbGciOi... (illustrative only)
Access token:   eyJhbGciOi... or an opaque string
Refresh token:  may or may not be present, depending on grant and policy
~~~

Portal has two distinct tasks:

1. **Identify the logged-in user at Portal**: Spring Security processes and verifies the ID token, constructing `OidcUser` and `Authentication`.
2. **Fetch orders via Orders API**: Portal sends the **access token issued for the API** in the `Authorization: Bearer ...` header.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Employee
    participant B as Browser
    participant P as Employee Portal / RP
    participant OP as OpenID Provider
    participant API as Orders API / Resource Server
    U->>B: Open Portal
    B->>P: Request protected page
    P-->>B: Redirect OIDC Authorization Code
    B->>OP: Authentication Request
    OP->>U: Authenticate / consent if needed
    OP-->>B: Redirect with authorization code
    B->>P: Callback with code and state
    P->>OP: Exchange code for tokens
    OP-->>P: ID token + access token
    Note over P: Verify ID token and create OidcUser
    P->>API: Authorization: Bearer ACCESS_TOKEN
    Note over API: Verify access token and API permissions
    API-->>P: Order data
    P-->>B: Render result
~~~

What to avoid is replacing the API call in the diagram with:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ID_TOKEN>
~~~

In the standard OAuth/OIDC model, that is **misusing the ID token**. An ID token issued for `Employee Portal` is not a license to call every enterprise API.

## 2. What Does an ID Token Prove?

### 2.1. An ID Token Is an Authentication Result for the RP

In OpenID Connect, an ID token is typically a signed JWT issued by the OP. Example payload:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-1288",
  "aud": "employee-portal",
  "iat": 1800000000,
  "exp": 1800003600,
  "auth_time": 1799999900,
  "nonce": "nonce-of-authorization-request",
  "email": "alice@example.com"
}
~~~

This is illustrative data, **not a real token**, and timestamps are not for running applications.

These claims state:

| Claim | Meaning in OIDC | Notes |
|---|---|---|
| `iss` | OP that issued the token | RP must trust and verify the issuer |
| `sub` | End-User identifier within the issuer's scope | When linking users, usually use the `iss` + `sub` pair |
| `aud` | Audience receiving the ID token; must include RP's client ID | Do not infer as an API audience |
| `iat` | Time when the token was issued | Not synonymous with when the user authenticated |
| `exp` | Time when the token expires | Time limit does not replace authorization |
| `auth_time` | Time when the user authenticated, if present | Used for freshness policy |
| `nonce` | Binds ID token to Authentication Request when used | Not a one-time mechanism for API calls |
| `email` | Profile attribute that may be provided | Not an immutable identity key or business permission |

The RP verifies the signature or token protection per flow, issuer, audience, validity timestamps, and OIDC conditions such as nonce when applicable.

**The value of an ID token lies in giving the RP grounds to authenticate the user**, not because it is a JWT decodable by every service.

### 2.2. An ID Token May Contain Profile Data, but It Is Optional

OIDC defines scopes such as `openid`, `profile`, and `email`. Depending on the OP, profile claims may appear in the ID token, be returned via the UserInfo Endpoint, or be omitted per policy.

Do not rely on `email` inside the ID token to:

- Grant full permission to view orders.
- Determine which tenant a user belongs to without checking policy.
- Authorize payments, approvals, or customer data access.
- Link two accounts from two issuers just because their emails match.

An ID token carries **authentication assertions and identity claims**, not a standardized API permission set.

### 2.3. Can an ID Token Be Reused Internally Within the RP?

The RP can use verified ID token information to:

- Identify the OIDC principal after login.
- Link an internal account via `iss` + `sub`.
- Read processed claims if required by business logic.
- Inspect `auth_time`, `acr`, or `amr` to evaluate authentication policy when present.
- Execute other parts of the OIDC protocol with specific rules, such as `id_token_hint` in an OP-supported logout flow.

**Re-reading verified details inside the RP** differs from **sending the raw ID token to an API as a bearer credential**.

An ID token is not a "universal access pass." When an application splits into multiple backends/services, each service needs its own trust model and token issued for that recipient.

## 3. Comparing ID Token, Access Token, Refresh Token, and Session

| Artifact | Primary Consumer | Purpose | Used as Bearer Credential for Business APIs? |
|---|---|---|---|
| **ID token** | OIDC Relying Party | Conveys End-User authentication result | **No under the standard OAuth Resource Server model** |
| **Access token** | Resource Server | Authorizes resource access per granted permissions | **Yes**, when token fits the API |
| **Refresh token** | OAuth client at token endpoint | Obtains new access tokens per AS policy | No |
| **Portal session cookie** | Browser and Portal | Maintains web application session | Never replaces access token for external APIs |
| **Authorization code** | Client and token endpoint | Redeemed once for tokens in the flow | No |

**Never judge a token by its format alone.** An OIDC ID token is a JWT, whereas an access token can be a JWT or an opaque string depending on the AS. Two JWTs can both be validly signed by the same OP yet have different purposes and audiences.

### 3.1. Access Token Intended for a Resource Server

A JWT access token, when an AS/RS uses that format, might have an illustrative payload like:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-1288",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1800000000,
  "exp": 1800001800
}
~~~

In this example:

- `iss` identifies the AS that issued the token.
- `aud` identifies the target Resource Server.
- `scope` describes granted access rights as agreed between AS and RS.
- `exp` bounds the usage lifetime.
- `sub` may reflect the user, though semantics depend on the grant and token profile.

**This is still only an illustrative payload.** The API must verify real tokens using the mechanism established by the AS and Resource Server, never merely decoding JSON.

### 3.2. An Access Token Does Not Automatically Grant All Permissions Either

An access token with a valid signature and unexpired timestamp can still be rejected by an API because:

- Its audience does not match the receiving API.
- It lacks `orders.read` or required business permissions.
- It belongs to an untrusted issuer/tenant.
- It is scoped for another resource type.
- The user lacks permission to view a specific order.

A well-designed API separates **token validation** from **action authorization**.

### 3.3. Refresh Tokens Do Not Replace ID Tokens or Access Tokens

A refresh token exists solely to renew access per the Authorization Server's policy. Never put a refresh token in the `Authorization` header when calling a business API.

Spring Security manages access/refresh token state through `OAuth2AuthorizedClient` and token-management components, never by using the ID token as a fallback token.

## 4. Audience: The Primary Reason Not to Misuse an ID Token

### 4.1. `aud` Answers "Who Was This Token Issued For?"

Suppose the same OP issues two tokens:

~~~text
ID token:
  aud = employee-portal

Access token:
  aud = orders-api
  scope = orders.read
~~~

When Portal consumes the ID token, client ID `employee-portal` is the right OIDC audience. When Orders API receives an access token, it must check the audience meant for itself, such as `orders-api`.

If Orders API accepts an ID token with `aud=employee-portal` simply because its signature is valid, the API has **bypassed token recipient boundaries**.

### 4.2. A Valid Signature Is Insufficient

Suppose an API only checks:

~~~text
1. Does the JWT have a valid signature? Yes.
2. Is the JWT unexpired? Yes.
3. Allow request.
~~~

This check misses critical questions:

- Was the token issued by an issuer trusted by the API?
- **Is the audience intended for the API?**
- Does the token have the type and semantics of an **access token** accepted by the API?
- Do scopes, authorities, and business permissions match?
- Has the token been revoked or violated an AS/RS policy?

Sharing an OP's JWK Set **does not make all JWTs signed by that OP interchangeable**.

### 4.3. `azp` Does Not Grant API Access

In some multi-audience ID tokens, the OP may emit an `azp` (*authorized party*) claim indicating the authorized party. `azp` has its own OIDC validation rules.

Never reason:

> The token has `azp=employee-portal`, so Orders API can trust that token to grant access.

`azp` is not an API scope and does not turn an ID token into an access token. The API still requires a token of the right audience/type with granted permissions.

### 4.4. What If Client ID and API Audience Coincidentally Collide?

A system might be loosely configured so that an API and an RP share the same audience string. In that case, checking `aud` alone **may not distinguish** a login token from an API token.

Design clearly:

- Distinct Resource Server audience.
- Token profile or token-type marker published by the AS and enforced by the API.
- API permission scopes and authority mapping.
- Distinct issuer, client, tenant, and resource rules.
- Policy rejecting tokens lacking access-token semantics.

With the **JWT Access Token for OAuth 2.0** profile per RFC 9068, tokens carry dedicated format/validation rules including type markers. However, **not every provider emits RFC 9068 JWT access tokens**, so never hardcode `typ=at+jwt` across all AS implementations without confirming the actual profile.

## 5. Risks of Using an ID Token as an API Bearer Token

### 5.1. Token Substitution / Token Confusion

**Token substitution** occurs when a component accepts a token intended for a different purpose as if it were a valid access token.

Example:

1. An OIDC client receives an ID token intended for itself.
2. The client sends that ID token to an API.
3. The API accepts it because it checks only issuer and signature.
4. The API grants access even though the AS never issued an access token for that API and never evaluated API scopes.

This is a trust-boundary failure. A trusted signature **is not enough to determine token purpose**.

### 5.2. Confused Deputy

An API acts as a trusted deputy processing data. If the API accepts a credential intended for another party without checking intended audience, it can be tricked into acting beyond what the caller was authorized to do.

For example, an ID token used to log into Portal must never be treated by Orders API as permission to read all orders. Order-reading rights must be represented through authorization mechanisms designed by the AS/RS and application.

### 5.3. Missing Scopes or Resource Permissions

ID tokens focus on claims such as `sub`, `nonce`, `auth_time`, `acr`, and `email`. They do not share an access token's contract for API scopes and audiences.

Even if an ID token contains a claim named `roles`, the API must not automatically infer that the claim grants business privileges. Determine:

- Under what semantics was the claim issued?
- Does it describe the user, client, or OP?
- Is the API permitted to use that claim for authorization?
- Are there tenant, resource-type, and specific action boundaries?

### 5.4. Unnecessary Leakage of Personal Data

An ID token may contain email, name, authentication metadata, or user attributes the API does not need.

Sending the ID token to multiple services increases:

- The number of components able to see those claims.
- The number of places the token may be logged or stored.
- The risk of disclosing PII in tracing and debugging.
- The chance the token is reused outside its original purpose.

An API access token also needs protection, yet can be tailored by the AS with claims and permissions **appropriate for the Resource Server**.

### 5.5. Reuse of a Bearer Credential

If an API accepts an ID token as a bearer token, anyone obtaining that string can replay it throughout the token's validity window.

OIDC `nonce` does not turn an ID token into a single-use API token. `exp` limits lifetime, yet does not stop replay within that window.

Details on replay protection follow in a later section.

## 6. Purpose of the ID Token in Spring Security OIDC Login

### 6.1. Spring Security Builds `OidcUser` After Login

In a Servlet application, a successful OIDC Login typically produces:

~~~text
SecurityContext
└── OAuth2AuthenticationToken
    ├── principal: OidcUser
    │   ├── idToken: OidcIdToken
    │   ├── userInfo: OidcUserInfo (if any)
    │   └── claims / attributes
    ├── authorities
    └── registrationId
~~~

The ID token's purpose here is to help the RP **authenticate the user and construct the principal**. Spring Security uses this result to authenticate the application session.

### 6.2. Example of Reading OIDC Identity

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    Profile me(@AuthenticationPrincipal OidcUser user) {
        return new Profile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName());
    }

    record Profile(String issuer, String subject, String displayName) {}
}
~~~

This example assumes the endpoint is reached only after OIDC Login. If the application supports multiple authentication types, handle the principal according to actual types.

`displayName` may be absent. When linking internal users, normally use **`iss` + `sub`**, avoiding email or name as unique keys.

**Never return raw `user.getIdToken().getTokenValue()` to the frontend** just to display a name or forward it to an API. Controllers may return only genuinely needed profile fields.

### 6.3. `SecurityContext` Is Not an Access Token Store for APIs

Spring Security separates concepts:

| Component | Role |
|---|---|
| `OidcUser` / `OidcIdToken` | Principal and OIDC authentication result details |
| `SecurityContext` / `Authentication` | Authentication state of the request / application session |
| `ClientRegistration` | OAuth client and provider configuration |
| `OAuth2AuthorizedClient` | Associates registration/principal with access token and refresh token if any |
| `OAuth2AuthorizedClientManager` | Coordinates requesting, using, or refreshing tokens per configured mechanism |

When calling an API, use the **authorized client / access token** rather than pulling the ID token from `OidcUser`.

## 7. Spring Boot: Configuring an OIDC Client to Call an API

### 7.1. Client Dependency

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 7.2. Client Registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/company
~~~

In this example:

- `corporate` is Spring Security's internal registration ID.
- Scope `openid` requests OIDC Login.
- `orders.read` is a **hypothetical** API scope that works only if the AS and Orders API actually support it.
- Client secret comes from a secure environment, never hardcoded in source.
- Redirect URI must match the callback registered at the OP.

**Requesting `orders.read` does not guarantee the AS will issue a token with that scope**; client and user may still be subject to consent, audience, and policy constraints.

### 7.3. Enabling OIDC Login and OAuth Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

Here:

- `oauth2Login()` handles user login.
- `oauth2Client()` provides OAuth client support for using tokens on outbound requests.
- `authorizeHttpRequests(...)` protects Portal URLs.

Enabling `oauth2Client()` **does not automatically make every API accept the token**, nor does it guarantee an issued access token has the audience expected by Orders API.

## 8. Calling an API with the Access Token from `OAuth2AuthorizedClient`

### 8.1. Example in a Servlet Controller

After OIDC Login, Spring Security can look up the authorized client matching the registration and principal. Example:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersProxyController {

    private final RestClient ordersApi =
            RestClient.create("https://orders-api.example.com");

    @GetMapping("/orders/proxy")
    String orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        String accessToken =
                authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
    }
}
~~~

This Spring Framework 6.1+ example clearly shows the outbound token sent is:

~~~java
authorizedClient.getAccessToken().getTokenValue()
~~~

**Not:**

~~~java
oidcUser.getIdToken().getTokenValue()
~~~

Real API calls must ensure the access token is unexpired, carries the right audience/scope, and is managed by `OAuth2AuthorizedClientManager` or an appropriate HTTP client integration when automatic refresh/reauthorization is needed. The manual example above focuses on **picking the right token type**; it is not a complete production pattern for token errors, retries, or refreshes.

### 8.2. When Logged In Without a Usable API Access Token

This can happen when:

- The client was granted only basic OIDC scopes.
- The access token was issued for UserInfo or another API, not Orders API.
- The AS denied the `orders.read` scope.
- The token expired or was revoked.
- The access token is opaque while the API tries to validate it as a JWT.
- The API requires a token with a different resource/audience.

Never pull out the ID token as a "temporary substitute." Adjust client config, scopes, audience/resource indicators, or token issuance flows per AS-supported protocols.

### 8.3. Using Client Manager or HTTP Integration

In larger applications, use Spring Security components such as:

- `OAuth2AuthorizedClientManager` to coordinate authorize/reauthorize.
- `OAuth2AuthorizedClientService` or `OAuth2AuthorizedClientRepository` to manage token state per registration and principal.
- OAuth 2.0 integration with `RestClient` or `WebClient` appropriate to your Spring Security version to attach access tokens to outbound requests.

This centralizes token management and reduces manually assembling headers in every controller. Whichever mechanism you pick, verify **the token is genuinely intended for the target API**.

## 9. What Must the Resource Server Validate?

### 9.1. Receiving a Bearer Access Token

Orders API expects requests like:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

The API must enforce an explicit trust policy:

1. Validate the token via JWT signature or introspection depending on token type.
2. Validate the trusted issuer.
3. Validate expiration and time constraints.
4. Validate the **audience/resource** intended for Orders API.
5. Validate token type/profile when the system provides a distinguishing mechanism.
6. Validate scopes/authorities and business authorization.
7. Handle invalid tokens per API contract; never redirect to web OIDC login.

### 9.2. JWT Resource Server Dependency

With Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Example issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/company
~~~

**`spring.security.oauth2.resourceserver.jwt.issuer-uri` differs from `spring.security.oauth2.client.provider.*.issuer-uri`.** The former serves an API receiving tokens; the latter serves an OAuth client / OIDC RP.

If the access token is an opaque string, the Resource Server needs proper introspection instead of trying to decode it as a JWT.

### 9.3. API `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This example assumes the AS emits JWT access tokens and Spring Security maps scope `orders.read` to authority `SCOPE_orders.read`. Actual mapping depends on `scope`/`scp` claims or a custom converter if the provider uses another format.

**The configuration above does not yet show audience validation.** In Spring Security, configure audience validation appropriately; checking only issuer, signature, and timestamps is usually **not enough** to prevent accepting tokens with a different audience.

### 9.4. Adding Audience Validation

Example Resource Server requiring JWT access tokens with audience `orders-api`:

~~~java
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
public class OrdersTokenValidationConfig {

    private static final String ISSUER =
            "https://idp.example.com/realms/company";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = token ->
                token.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token audience is not orders-api",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime,
                        audience));

        return decoder;
    }
}
~~~

This snippet shows the **API enforcing issuer/time and audience checks**; the decoder also verifies the JWT signature using keys fetched per configured issuer/metadata. This is an illustrative example that should be combined with scope policy, token type/profile checks, and real system business permissions.

**If an ID token has `aud=employee-portal`**, it fails `aud=orders-api` and is rejected. If a system has overlapping audiences between ID tokens and access tokens, add checks for **access-token-specific** properties per the provider's profile rather than trusting an overlapping audience.

### 9.5. Distinguishing 401 and 403

An API may respond with:

| Situation | Usually Appropriate Response |
|---|---|
| Missing token or invalid token, wrong issuer/audience, expired | **401 Unauthorized** |
| Token validly authenticated yet lacks permission for the action | **403 Forbidden** |

For instance, a client authenticated with an access token lacking `orders.read` is normally denied at authorization. Exact HTTP status codes depend on authentication entry point and access denied handler config, yet the principle is **never grant access solely because a JWT has a valid signature**.

## 10. Preventing Token Substitution When One Issuer Signs Multiple JWT Types

### 10.1. Sharing a JWKS Does Not Mean All Tokens Serve the Same Purpose

One OP may sign:

- ID tokens for clients.
- JWT access tokens for one or more Resource Servers.
- Other JWTs or assertions for separate protocols.

Resource Servers may fetch verification keys from the same `jwks_uri`. Yet a signing key only proves the token was issued by that issuer and not altered — **it does not prove the token is meant for the receiving Resource Server**.

Beyond signature, the API must enforce **issuer, audience, token type, scopes, and permissions**.

### 10.2. Token Type and Profile

If an AS emits JWT access tokens per **RFC 9068**, they carry distinctive markers and verification rules for OAuth access tokens. For example, the profile may use the `typ` header to identify access tokens.

However:

- Not every access token is a JWT.
- Not every JWT access token follows RFC 9068.
- Some providers use custom claims or metadata to classify tokens.
- ID tokens and access tokens may share common claims like `iss` and `sub`.

Therefore, confirm **which token profile the Resource Server is allowed to accept**. Never invent token-type rules based solely on claim names without agreeing with the AS.

### 10.3. Do Not Use `authenticated()` as the Entire API Policy

If an API is configured to accept any valid JWT from the same issuer without checking audience, token type, and scopes, and only declares:

~~~java
.anyRequest().authenticated()
~~~

then a validly signed JWT meant for a completely different purpose could be treated as sufficient to access endpoints.

Instead, specify the API's audience, validate token profile, and enforce appropriate permissions per endpoint. Rules like `hasAuthority("SCOPE_...")` are helpful, yet **do not replace audience validation**.

## 11. Replay: ID Tokens Can Be Reused as Bearer Tokens If an API Accepts Them Wrongly

### 11.1. OIDC Nonce Is Not a One-Time API Counter

`nonce` is created by the RP in the Authentication Request and verified in the ID token per OIDC rules. It binds the token to the authentication request.

Suppose an ID token contains:

~~~json
{
  "nonce": "NONCE_A",
  "aud": "employee-portal",
  "exp": 1800003600
}
~~~

If an API accepts this ID token as a bearer token, the fact that `nonce` once matched an Authentication Request **does not make subsequent API calls one-time-use**.

The API lacks the RP's original Authorization Request state to verify `nonce` in context. Trying to use `nonce` as an API idempotency key is a broken mental model.

### 11.2. `exp` Limits Lifetime, Not Replay Within the Valid Window

A token can be replayed repeatedly before expiration. `exp` only states when the token ceases to be valid under verification policy.

Similarly:

- `iat` states issuance time, not a counter.
- `auth_time` states the authentication event, not a "used" flag.
- `jti` if present can serve as an identifier in specialized replay-detection schemes, yet **an ID token carrying `jti` does not automatically make it single-use**.

Preventing API replay requires proper API authentication and authorization design, not relying on OIDC claims.

### 11.3. Single-Use Authorization Codes Differ from ID Tokens

In the Authorization Code flow, the **authorization code** is restricted to a single exchange at the AS. The ID token is an authentication assertion consumed by the RP in its protocol context; it has no built-in consume-once enforcement per claim read.

Never infer from single-use codes that an ID token cannot be copied and replayed if a misdesigned API accepts it.

### 11.4. Bearer Access Tokens Also Carry Replay Risk

Switching from an ID token to a purpose-built access token **does not eliminate all replay risks**.

A leaked bearer access token can be replayed while still valid. Mitigations include:

- Minimizing scopes and restricting audience.
- Using reasonable TTLs and storing tokens securely.
- Protecting transport with HTTPS and never logging tokens.
- Applying AS revocation and refresh policies.
- Using sender-constrained access tokens such as **mTLS** or **DPoP** when supported by AS/RS/client.
- Enforcing resource-level authorization and idempotency at the API.

DPoP and mTLS have strict protocol requirements; never assume merely renaming a header binds a token to its sender.

## 12. What If Another Backend Needs to Confirm the User Logged In?

### 12.1. Do Not Pass the ID Token Across Services as "Universal Proof"

Suppose Portal calls Service A, and A calls Service B. A weak design:

~~~text
Browser -> Portal (OIDC login)
Portal -> Service A (sends Portal's ID token)
Service A -> Service B (forwards same ID token)
Service B -> Database
~~~

Both A and B are accepting an ID token whose audience is Portal, blurring trust boundaries and privileges.

A better model:

~~~text
Browser -> Portal: Portal session cookie
Portal -> Service A: access token intended for Service A
Service A -> Service B: token intended for B via delegation/exchange if needed
~~~

If Service B needs user identity, the token intended for B must convey it under a model trusted by the AS and B. Never turn an email or `sub` copied into an HTTP header into a new authentication credential.

### 12.2. Token Exchange When Audience Must Change

Some systems support **OAuth 2.0 Token Exchange** (RFC 8693) or provider-specific on-behalf-of mechanisms so a client or service can obtain a new token intended for a downstream API.

The flow may look like:

~~~mermaid
flowchart LR
    A["Portal holds valid token for current context"] --> B["Authorization Server: token exchange / delegation"]
    B --> C["New access token with audience Service B"]
    C --> D["Service B verifies token and permissions"]
~~~

Conditions:

- The AS must **support** token exchange or the corresponding delegation mechanism.
- The client/service must be authorized to perform the exchange.
- Source token, audience, scopes, and identity must satisfy AS policy.
- The new token must be validated by the target Resource Server for type and permissions.

**RFC 8693 defines subject token types that can include an ID token in certain cases**, yet that **never permits sending an ID token directly to an API as a bearer access token**. If an AS and deployment profile genuinely accept an ID token as an input assertion for token exchange, the ID token is sent to the **AS's token endpoint per the exchange contract**, and the AS decides whether to issue an access token for the Resource Server.

Never assume every OP supports token exchange or that every ID token can be exchanged.

### 12.3. Service-to-Service Calls Without a User

If a background service calls an API using its own application identity, it can use the `client_credentials` grant when permitted by the AS.

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://idp.example.com/oauth2/token
~~~

The `client_credentials` grant issues tokens for a client/service per policy; **it does not prove an End-User logged in via OIDC**. Never borrow an arbitrary employee's ID token as a credential for background jobs.

## 13. Browser, SPA, BFF, and Sessions

### 13.1. Server-Side / Backend for Frontend (BFF)

In the **Backend for Frontend (BFF)** pattern:

1. The browser logs in via OIDC Authorization Code.
2. The Spring Security backend receives tokens over the back channel.
3. The backend verifies the ID token and maintains `SecurityContext`/session.
4. The browser sends its session cookie to the BFF for application requests.
5. The BFF uses the **API access token** to call the Resource Server.

~~~text
Browser
  |
  | Session cookie (appropriate HttpOnly, Secure, SameSite)
  v
Spring Boot BFF
  | OAuth access token with right audience/scope
  v
Resource Server
~~~

This model avoids returning raw ID tokens to the browser and asking frontend code to call APIs with ID tokens.

The BFF still needs proper session, cookie, HTTPS, and CSRF protections; a session cookie is also a credential requiring protection.

### 13.2. SPAs Calling APIs Directly

In an SPA calling APIs directly, the OAuth client typically needs an **API access token**, using Authorization Code + PKCE and appropriate token policies.

Never grab the ID token from login results and attach it to every `fetch` request simply because the frontend OIDC library happens to expose it.

Example to avoid:

~~~javascript
const idToken = oidcUser.id_token;

fetch("https://orders-api.example.com/api/orders", {
  headers: { Authorization: "Bearer " + idToken }
});
~~~

A sounder flow obtains an API token via the authorized-client mechanism supported by the library/provider, then sends an access token with matching audience/scopes. Browser token storage and refresh handling depend on the SPA's security architecture.

### 13.3. Portal Session and API Tokens Have Two Separate Lifecycles

All of these can happen simultaneously:

- Portal session is still valid.
- Initial login's ID token has expired.
- API access token has expired and needs refresh.
- OP still holds an SSO session for the browser.
- API has revoked the `orders.read` permission.

Therefore, **an active session does not guarantee the API access token is valid**, and **a valid access token does not mean the user is authorized for every action**. Enforce policies at each layer independently.

## 14. Exceptions and Specialized Integrations to Understand Properly

### 14.1. APIs Authenticating via ID Token Under a Provider-Specific Profile

Certain platforms or products support accepting an **ID token issued specifically with the service URL as its audience** as an identity assertion to call a specific endpoint. This is a **platform/provider-specific authentication contract**, not the default rule for OAuth 2.0 Resource Servers.

In that case, the system must explicitly define:

- Which issuer is trusted.
- Which audience corresponds to that exact service.
- Which token type and token source are accepted.
- Where access decisions come from.
- Lifetimes, TLS, logging, and replay risks.
- How the backend validates tokens and authorizes resources.

Never extrapolate from that exception that **an OIDC ID token issued for an arbitrary web client** can be sent to every API.

### 14.2. Backend Accepting an ID Token to Establish Its Own Session

Some architectures allow a backend to **receive an identity assertion** from a defined source to establish an application session, such as a custom sign-in flow.

If an ID token is used in such a protocol, the backend must:

- Have an explicit contract on allowed client/audience/issuer.
- Verify signature, timestamps, claims, and appropriate replay conditions.
- Never treat the token merely as a generic bearer access token across all endpoints.
- Separate **user authentication** from **API access authorization**.

This is a specialized architectural choice. With standard Spring Security OIDC Login, the framework already handles authentication via callback; there is no need to replay the ID token to an arbitrary API for "extra verification."

### 14.3. `id_token_hint` in OIDC Is Not an Access Token

An application may use `id_token_hint` at certain OIDC endpoints such as RP-Initiated Logout when supported by the provider. Its purpose is to hint at the related session/identity per the logout protocol.

That **does not make the ID token a credential for Orders API**. Each endpoint has its own contract and must be used only for its intended purpose.

## 15. Practice Analyzing 401 and 403 Errors

### 15.1. ID Token Rejected by API Due to Audience

Suppose a client accidentally sends:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <ID_TOKEN_AUD_EMPLOYEE_PORTAL>
~~~

Orders API checks for audience `orders-api` and sees the ID token has audience `employee-portal`.

**Expected outcome:** token fails the API's authentication requirements; rejected, typically with 401.

Fix: send an **access token intended for Orders API**; never delete the audience validator.

### 15.2. Valid Access Token Yet Missing Scope

The client sends an access token with `aud=orders-api`, yet only scope `orders.list` while the endpoint requires `orders.read`.

**Expected outcome:** API authenticates the token and then denies authorization; typically 403 when the token is valid yet lacks the required authority.

Fix: check scopes granted by the AS and API policy. Never switch to the ID token or add fake authorities on the Resource Server to bypass the error.

### 15.3. Using a Validly Signed ID Token from the Wrong Tenant

Suppose a company has:

~~~text
Employee issuer:
https://idp.example.com/realms/employees

Partner issuer:
https://idp.example.com/realms/partners
~~~

A validly signed JWT from the partner issuer is not automatically accepted by the employee API. The API must configure trusted issuers and appropriate tenant separation.

Even if the email in the token belongs to the same domain, that does not prove the account holds the corresponding privileges.

### 15.4. API Uses `authenticated()` Without Audience Validation

If an API accepts JWTs from a shared OP, validates only signature/issuer/timestamps, and declares:

~~~java
.anyRequest().authenticated()
~~~

it is missing a critical policy layer. Add audience/token-profile checks and resource permissions.

Never "fix" integration friction by allowing every OIDC client token to be accepted.

## 16. Secure Design Workflow for API Calling Flows

### Step 1. Define Each Service's Role

Clarify:

- Which **RP/OIDC Client** authenticates users?
- Which **Authorization Server** issues access tokens?
- Which **Resource Server** receives tokens?
- Does the API require user delegation or service identity?

Never lump tokens with different purposes together under one label "JWT."

### Step 2. Register Required Audiences and Scopes

Agree between AS and RS on:

- API identifier or audience/resource URI.
- Scopes/authorities required by endpoints.
- Access token type: JWT or opaque.
- Token profile and verification mechanism.
- How permissions are requested on behalf of users or clients.
- Consent, refresh, and revocation policies.

### Step 3. Spring Security Client Manages Access Tokens

Use `ClientRegistration`, `OAuth2AuthorizedClient`, and appropriate integrations to obtain tokens and call APIs.

Never drop `OidcIdToken.getTokenValue()` into an API's bearer header out of habit.

### Step 4. Resource Server Validates Tokens Purposefully

Verify:

- Signature / introspection.
- Issuer.
- Expiration and time constraints.
- **Audience**.
- Token type/profile when applicable.
- Scopes/authorities.
- Business permissions per user/tenant/resource.

### Step 5. Protect Tokens and Session Data

Protect secrets/tokens on the server, never log them, enforce HTTPS, and keep session lifecycles separate from access tokens. When stronger bearer replay protection is required, evaluate sender-constrained tokens and matching AS/RS policies.

### Step 6. When Calling Downstream Services, Design Delegation

If Service A must call Service B on behalf of a user, obtain a token with audience B through an AS-supported delegation or token-exchange mechanism. Never forward the RP's original ID token.

## 17. Common Misconceptions

**"Both ID tokens and access tokens are JWTs, so they can be swapped?"**

No. JWT is merely a representation format. Audience, purpose, privileges, and validation rules differ.

**"The API shares the same OP as Portal, so it can trust Portal's ID token?"**

Not merely because they share an OP. The API needs an access token or an identity assertion under an explicit contract with matching audience, token type, and policy.

**"Spring Security already verified the ID token, so can we forward it to other services?"**

The RP verified the token for RP login purposes. Other services need their own authentication/authorization mechanisms; RP verification does not expand a token's audience.

**"The ID token has `email_verified=true`, so that's enough to read data?"**

No. Email verification is not resource access authorization. The API must enforce designed authorization checks.

**"With a nonce, an ID token cannot be replayed?"**

No. Nonce binds an ID token to an OIDC Authentication Request; it does not create a one-time API counter.

**"A JWT access token with a valid signature means the API is secure?"**

Not enough. The API must also check issuer, audience, timestamps, token profile, scopes, and business permissions.

**"When the ID token expires, the Portal `HttpSession` expires immediately?"**

Not by default. ID token lifetime and Spring Security session lifecycle can differ. Application session policy must be designed independently.

**"Can an ID token be sent to a token exchange endpoint?"**

Some AS implementations/profiles allow an ID token as an input assertion under OAuth Token Exchange, provided the AS supports it and the client is authorized. **A token exchange endpoint is not a Resource Server API.**

**"Having `issuer-uri` on the Resource Server automatically blocks ID tokens?"**

Do not assume that. Issuer and signature checks do not replace audience and token-type validation. API config must reflect the accepted token contract.

## 18. Self-Check Scenarios

### Scenario A: Portal Receives Two Tokens

After login, the client holds:

~~~text
ID token:
  aud = portal-web
  sub = alice

Access token:
  aud = orders-api
  scope = orders.read
~~~

**Question:** Which token should be used to call Orders API?

**Answer:** The access token with audience `orders-api` and appropriate scopes. The ID token is for Portal to process the authentication result.

### Scenario B: API Receives a Validly Signed ID Token

Orders API receives a JWT with a valid issuer and signature, yet `aud=portal-web`.

**Question:** May it grant access solely because the signature is valid?

**Answer:** No. Audience targets the wrong recipient; this is not an access token issued for the API. The API must reject it per policy.

### Scenario C: Access Token Present Yet Returns 403

The token has `aud=orders-api`, yet lacks `orders.read`.

**Question:** Should we try sending the ID token instead?

**Answer:** No. Check granted permissions, scopes, and API policy. An ID token does not replace an access token lacking privileges.

### Scenario D: ID Token Has a Valid Nonce

A valid ID token has a `nonce` matching the Authentication Request; a client sends this token repeatedly to Orders API.

**Question:** Does `nonce` make each request single-use?

**Answer:** No. Nonce belongs to OIDC validation at the RP. The API needs a purpose-built access token and dedicated replay protections where needed.

### Scenario E: Backend Needs to Call Service B

Portal holds an access token for Service A; A needs to call Service B.

**Question:** Should A grab Portal's original ID token and forward it to B?

**Answer:** Not under the standard model. Obtain a token intended for B via an AS-supported delegation or token-exchange mechanism, or use client identity for userless background tasks.

### Scenario F: Provider Has a Specialized API Accepting ID Tokens

A platform states its service authenticates callers using an ID token issued by a specific issuer with the service URL as audience.

**Question:** Does that permit using any OIDC ID token to call any API?

**Answer:** No. That is a specialized authentication contract. Use only tokens matching the exact issuer/audience/type and policy specified by that service; never generalize it to other OAuth Resource Servers.

## Key Takeaways

- **An ID token is for the OIDC Relying Party to authenticate the user.** It is not a default access token for calling Resource Servers.
- **An API access token** must be validated by the API for issuer, audience, expiration, token profile, scopes, and business permissions per its contract with the AS.
- **A valid JWT signature is insufficient to accept a token**: a token can have the right issuer yet the wrong audience or purpose.
- **Nonce, `exp`, and single-use codes** do not turn an ID token into a non-replayable bearer credential at an API.
- In **Spring Security**, use `OidcUser`/`OidcIdToken` to handle post-login identity; use `OAuth2AuthorizedClient.getAccessToken()` and authorized client manager mechanisms when calling APIs.
- Token exchange and provider-specific identity assertions are distinct contracts. Use them only when supported by the AS/service with clearly defined trust boundaries.
- In multi-service architectures, **never forward the RP's original ID token across APIs** as a universal permission credential; issue or obtain the proper token for each Resource Server.
