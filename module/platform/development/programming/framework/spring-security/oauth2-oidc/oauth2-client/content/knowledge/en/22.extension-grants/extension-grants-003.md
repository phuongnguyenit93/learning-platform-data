# 22.3. Token Exchange and Provider Compatibility Requirements

## 1. Problem Statement: Why Is Token Exchange Needed?

In a **Spring Security OAuth 2.0/OIDC Client** architecture, an application may receive a valid access token from a user and then need to call an API in a different trust domain or audience. You cannot assume that an access token issued for Service A is also valid at Service B.

Example:

```text
Browser / Mobile App
   |
   | Access Token A
   | aud = gateway-api
   v
Service A / Gateway
   |
   | Needs to call Orders API, which requires aud = orders-api
   v
Authorization Server / Security Token Service (STS)
   |
   | RFC 8693 Token Exchange:
   | subject_token = Token A
   | audience = orders-api
   | scope = orders.read
   |
   v
Access Token B
   |
   | aud = orders-api, scope = orders.read
   v
Orders API
```

If Service A sends Token A directly to the Orders API, a Resource Server validating audience properly must reject it. If Service A alters the JWT payload itself and signs it with a key not trusted by the Orders API, that is not valid Token Exchange.

**OAuth 2.0 Token Exchange (RFC 8693)** defines an extension grant allowing an OAuth2 client to ask an STS to issue a new security token based on an existing token, subject to authentication and authorization policies. This is not a mandatory feature of every OAuth2 Authorization Server or OpenID Provider.

### After this lesson, you will be able to

1. Explain how Token Exchange differs from Authorization Code, Refresh Token, and Client Credentials.
2. Understand RFC 8693 format requirements: subject token, actor token, token types, audience, resource, and scope.
3. Distinguish impersonation from delegation, and understand `act` and `may_act` claims.
4. Read responses and distinguish `issued_token_type` from `token_type`.
5. Know exactly what the provider must support for Token Exchange to succeed.
6. Assess compatibility between RFC 8693 and provider-specific On-Behalf-Of (OBO) flows.
7. Configure `TokenExchangeOAuth2AuthorizedClientProvider` in Spring Security Servlet.
8. Use `RestClientTokenExchangeTokenResponseClient` to customize `audience` or `resource`.
9. Select subject tokens and actor tokens via appropriate resolvers.
10. Identify the corresponding integration for WebFlux/reactive.
11. Design token caching, lifecycle, error handling, testing, and security within proper trust boundaries.

The URLs, tokens, issuers, scopes, audiences, and client IDs in this lesson are **illustrative only**. With a real provider, always check documentation and policies for **the exact version, tenant/realm, and client registration**.

---

## 2. Microservices Context and Token Exchange Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant A as Service A - Resource Server & OAuth2 Client
    participant STS as Authorization Server - STS
    participant B as Service B - Resource Server

    U->>A: GET /my-orders, Bearer Token A
    Note over A: Validate Token A: issuer, signature, aud, exp
    A->>STS: POST /token, Token Exchange, subject_token=A
    Note over STS: Authenticate client and subject token
    Note over STS: Check target, scope, delegation policy
    STS-->>A: Token B for orders-api
    A->>B: GET /orders, Bearer Token B
    Note over B: Validate Token B and authorization
    B-->>A: Orders data
    A-->>U: Response
```

**Three security boundaries to keep distinct:**

- **Inbound Resource Server (Service A):** validates tokens sent directly to A. A valid token from any issuer is not enough; A must verify its own audience and policy.
- **STS:** determines whether the requesting client is permitted to use the subject token to obtain a token for target B. This is where Token Exchange policy is enforced.
- **Target Resource Server (Service B):** validates Token B, checking issuer, audience, expiry, scopes, actor/delegation claims if present, and business authorization.

Token Exchange does not replace B's authorization. An HTTP 200 from the STS does not prove the user is authorized to view all orders.

## 3. How Token Exchange Differs from Other Grants

| Grant / Mechanism | Primary Input | Purpose |
|---|---|---|
| Authorization Code + PKCE | Authorization code from browser login | Obtain tokens per user authorization |
| Client Credentials | Client authentication itself | Token representing the client/service |
| Refresh Token | Refresh token issued by the AS | Obtain a new access token for existing authorization |
| **Token Exchange** | **Subject token**, optionally an actor token | Ask STS to issue a new token for a policy-permitted target/context |
| JWT Bearer Grant | JWT assertion per profile | Authorization based on an assertion trusted by the AS |

Common misconceptions:

- Token Exchange is **not** how you refresh an old access token using `refresh_token`.
- A Client Credentials token cannot on its own substitute for a user's token.
- OIDC Login authenticates the End-User to the client; it does not automatically grant exchange rights to every downstream API.
- Token Exchange can swap an access token for an access token, though the RFC also describes other token types when supported by participants.

### 3.1. When Is Token Exchange Unnecessary?

If API B is designed to accept Token A, and Token A genuinely carries the right audience, scope, issuer, and authorization policy, Service A may not need an exchange. Adding an STS round-trip brings no benefit if no security boundary changes.

Conversely, having many APIs accept a single overly broad-audience token increases blast radius if that token leaks. Issuing target-specific tokens generally helps narrow privileges.

## 4. RFC 8693 Is an OAuth2 Extension Grant

Exact grant identifier:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Token Exchange is sent to the Token Endpoint over HTTP POST with a form body:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.net
Authorization: Basic BASE64_CLIENT_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SUBJECT_TOKEN_A
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=orders-api
&scope=orders.read
```

Body lines are split here for readability; real requests must be properly form-encoded.

### 4.1. RFC 8693 Parameters

| Parameter | RFC Requirement | Meaning |
|---|---|---|
| `grant_type` | **Required** | Exact Token Exchange URN value |
| `subject_token` | **Required** | Token representing the subject the client wants to exchange |
| `subject_token_type` | **Required** | URI identifying the input token type |
| `requested_token_type` | Optional | Desired output token type |
| `resource` | Optional | Absolute URI of the target resource |
| `audience` | Optional | Logical name of the target service |
| `scope` | Optional | Permissions requested at the target |
| `actor_token` | Optional | Token representing the actor acting on behalf of the subject |
| `actor_token_type` | Required **if `actor_token` is present**; must not be sent without an actor token | Type of the actor token |

**Optional in the RFC does not mean optional for every provider.** An AS may require `audience`, `resource`, scope, actor token, or other documented parameters per deployment policy.

### 4.2. Client Authentication Differs from Subject Token

In the illustrative request:

```text
Authorization: Basic ...
```

proves the identity of the **OAuth2 client** calling the STS.

Meanwhile:

```text
subject_token=Token A
```

conveys information/authorization related to the **subject**.

Both must be enforced:

- Valid client credentials do not mean the client may exchange any subject token.
- A valid subject token does not mean anyone holding it may call the STS to mint another token.
- The STS may use `client_secret_basic`, mTLS, `private_key_jwt`, or another registered mechanism.
- The STS must verify issuer/trust, token type, and client permissions for the target.

A provider that lets stolen tokens be exchanged without constraining client identity and policy opens the door to token laundering.

---

## 5. `subject_token` and Accepted Token Types

The input token can be an OAuth2 access token, JWT assertion, OIDC ID Token, or another security token, **only if the STS genuinely supports that token type**.

Common token type URIs in RFC 8693:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
urn:ietf:params:oauth:token-type:saml2
```

### 5.1. `access_token` Does Not Always Mean `jwt`

- `access_token` describes an **OAuth2 purpose**.
- `jwt` describes a **syntactic representation**.
- An OAuth2 access token may be encoded as a JWT, yet the provider still requires `subject_token_type=access_token`.
- A JWT from another issuer might require `subject_token_type=jwt`.

Never guess the token type merely because the token string has three dot-separated parts.

### 5.2. Opaque Subject Tokens

An opaque access token can still be exchanged if the STS can validate it via storage or token introspection and policy permits it.

If the STS only trusts signed JWTs from an issuer allowlist, an opaque token—even if valid at Resource Server A—will be rejected.

### 5.3. Can an ID Token Be Used as a Subject Token?

The RFC defines a token type URI for ID Tokens, yet an OIDC ID Token exists for the client to verify End-User Authentication, not as an API access token.

Do not take `OidcUser.getIdToken()` and drop it into `subject_token` unless the provider explicitly documents support for **ID Token exchange** with an accompanying trust policy. When the STS requires a subject **access token**, retrieve the managed access token for the user/client.

### 5.4. The Input Token Must Still Be Valid

The STS may check:

- Signature/MAC or introspection status.
- Issuer.
- Audience or resource for which the token was issued.
- Expiration / not-before.
- Token type.
- Subject identity and tenant.
- Proof-of-possession / sender constraint if applicable.
- Client permissions and delegation policy.

A client cannot bypass STS-side validation merely by placing a token into a syntactically valid form body.

## 6. `resource`, `audience`, and `scope`

### 6.1. `resource`

Example:

```text
resource=https://orders.example.net
```

Per the RFC, `resource` is an absolute URI identifying the target resource/service. It must not contain a fragment. Providers may accept multiple `resource` parameters, though they are not obligated to issue tokens for every requested target.

### 6.2. `audience`

Example:

```text
audience=orders-api
```

This is the logical name of the target service understood by both the STS and client.

Some providers require a URL, others an API identifier or client ID. There is no universal rule that `audience` always equals the REST API URL.

### 6.3. `scope`

Example:

```text
scope=orders.read orders.export
```

Scope is a space-delimited OAuth2 string, while **permission semantics** are defined by the target API and AS policy.

### 6.4. Do Not Request Overly Broad Targets

Example:

```text
audience=orders-api
audience=finance-api
scope=orders.read finance.write
```

Requesting multiple audiences combined with multiple scopes can force the STS to mint an overly broad token; RFC 8693 defines the `invalid_target` error to signal target problems.

**Principle:** request minimal scopes and generally obtain separate tokens per Resource Server. Having a `resource` parameter in Token Exchange also does not imply the provider supports all of RFC 8707 Resource Indicators.

## 7. Impersonation and Delegation

Both concepts can arise in Token Exchange, with distinct meanings.

### 7.1. Impersonation

Service A requests a token for the Orders API with subject Alice:

```text
Subject: Alice
Output token: permissions representing Alice at the target API
```

The Resource Server sees actions as performed by Alice within the scope of the issued token. This is valid only if the STS authorizes client A to impersonate Alice.

### 7.2. Delegation

Service A acts on behalf of Alice **with a distinct actor identity**:

```text
Subject = Alice
Actor = Service A
Target = Orders API
```

The STS may issue a JWT containing an actor claim:

```json
{
  "iss": "https://id.example.net",
  "sub": "alice-901",
  "aud": "orders-api",
  "scope": "orders.read",
  "act": {
    "sub": "service-a"
  }
}
```

Where:

- `sub` represents the subject.
- `act` represents the actor.
- The Resource Server can enforce policies and auditing based on both subject and actor.

Not every provider emits `act` when given an actor token; exact format and policy belong to the STS implementation and documentation.

### 7.3. `may_act`

`may_act` is a claim an STS may use to determine whether a given actor is permitted to act on behalf of a subject.

Never infer:

```text
Input JWT contains may_act
    => any actor may exchange
```

The STS must still validate signatures, trust, permissions, and targets. Nor may a client add `may_act` to a JWT not signed by a trusted issuer to claim rights.

### 7.4. When Should `actor_token` Be Sent?

Only when the provider supports the actor token type and corresponding delegation semantics.

Never pass a raw string such as a client ID or client secret in place of an actor security token; if you send `actor_token_type=jwt`, the actor token must actually be a JWT accepted by the STS.

---

## 8. Token Exchange Response

Example success response when the STS issues a **Bearer access token**:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
```

```json
{
  "access_token": "TOKEN_FOR_ORDERS_API",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

| Field | RFC | Meaning |
|---|---|---|
| `access_token` | Required | Issued token; field name comes from OAuth2 history |
| `issued_token_type` | **Required** | Type of security token issued |
| `token_type` | **Required** | How the token is used, e.g., Bearer |
| `expires_in` | Recommended | Lifetime in seconds |
| `scope` | Optional if matching requested scope; required if different | Actually granted permissions |
| `refresh_token` | Optional | Not issued by default |

### 8.1. `issued_token_type` and `token_type` Are Different

Example:

```text
issued_token_type = urn:ietf:params:oauth:token-type:access_token
token_type        = Bearer
```

The first field states **what kind of token was issued in terms of security token representation/purpose**. The second states **how to use the token**.

An access token using the JWT wire format can still be reported with `issued_token_type=access_token`.

### 8.2. Not Every Output Token Is an API Bearer Token

The RFC allows some exchanges to issue security tokens other than OAuth access tokens. In those cases `token_type` may be `N_A`.

Therefore, do not blindly attach a WebClient Bearer filter to every token response. Verify that the output is actually an OAuth access token suitable for calling the Resource Server.

### 8.3. Refresh Token Is Optional

An STS typically issues short-lived access tokens for the target and does not necessarily return a refresh token. An output token with `expires_in=600` cannot automatically be refreshed with `grant_type=refresh_token`.

Without a refresh token, the application may need to perform Token Exchange again with a still-valid subject token or obtain fresh subject authorization. This is a provider-specific lifecycle decision.

## 9. Does Token Exchange Invalidate the Input Token?

**Not by default.** Under RFC 8693, unless the token type and provider enforce one-time-use semantics, performing an exchange does not automatically revoke the subject token or actor token.

Example:

```text
Token A valid for 30 minutes
    |
    +-- exchange -> Token B1
    +-- exchange -> Token B2
```

Multiple tokens can remain valid concurrently if policy permits.

Conversely, Token B is not automatically revoked when Token A is revoked. An STS may implement revocation propagation, yet that is an implementation feature rather than a universal guarantee.

Lifecycle questions to confirm:

- How long can Token B live at most?
- Is B's expiry capped by A's expiry?
- Do logout and disconnect revoke B?
- Can B be introspected or revoked?
- Must the STS be called again when the source token or actor changes?
- Is B bound to a session or sender-constrained key?

---

## 10. What Must the Provider Support?

A provider that supports OIDC Login, OAuth2 Authorization Code, JWTs, or Resource Servers **does not necessarily** support RFC 8693.

For Spring OAuth2 Client to succeed with Token Exchange, the STS needs:

1. A **Token Endpoint** that genuinely accepts the extension grant URN.
2. A **Client registration** enabled for that grant.
3. **Client authentication** matching the registered method.
4. Acceptance of the **Subject token type**.
5. Valid **Source issuer/trust relationships**.
6. **Input token validation** matching the token format.
7. **Audience/resource** within the target allowlist.
8. **Scope mapping** granting appropriate permissions for the Resource Server.
9. Defined **Delegation/impersonation policy**.
10. **Actor token handling** if the flow uses an actor.
11. **RFC-compliant responses** containing required fields.
12. **Output token issuer/audience** trusted by the target Resource Server.
13. Clear **Refresh/revocation/expiry policies**.
14. Properly enabled **Tenant/realm-specific permissions**.
15. Proper **TLS, key/certificate trust**, and network transport.

### 10.1. Compatibility Checklist Table

| Question | Where to Verify | Symptom When Missing |
|---|---|---|
| Does the AS support the `token-exchange` URN? | Provider docs / token endpoint | `unsupported_grant_type` |
| Is the client allowed to use the grant? | Client permissions / AS policy | `unauthorized_client` |
| Does the client auth method match? | Registration / provider config | `invalid_client` |
| Is the subject token type accepted? | STS trust / token-type docs | `invalid_request` |
| Is the subject issuer trusted? | Token exchange trust / federation | Token rejected |
| Is audience/resource valid? | Allowed target identifiers | `invalid_target` |
| Are scopes valid for the target? | Scope mapping | `invalid_scope` or 403 |
| Is actor token supported? | Delegation policy | `invalid_request` |
| Are required response fields present? | STS implementation | Parse error |
| Does the target trust B's issuer? | API JWT / introspection config | API 401 |
| Is revocation propagated? | Provider lifecycle docs | Token B outlives revocation |
| Is Token B sender-constrained? | STS / API docs | API rejects proof |
| Is the tenant/realm enabled? | Tenant settings | Grant fails despite product support |

### 10.2. Metadata and `grant_types_supported`

Authorization Server Metadata / OIDC Discovery may publish `grant_types_supported`. Seeing the Token Exchange URN there is a helpful signal, yet **does not prove** a specific client has permission to exchange tokens for every target.

If metadata omits the URN, consult deployment docs and the provider's actual Token Endpoint; never conclude solely from the product name.

**Conclusion:** you must verify **server capability**, **client permission**, **token trust**, and **target authorization**.

## 11. How Does RFC 8693 Differ from Proprietary On-Behalf-Of?

Some Identity Providers call similar capabilities:

- On-Behalf-Of (OBO).
- Audience exchange.
- Token swap.
- Delegation or impersonation.
- Downstream access token issuance.

However, feature names **do not guarantee RFC 8693 compliance**.

RFC 8693 request example:

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=...
subject_token_type=urn:ietf:params:oauth:token-type:access_token
audience=orders-api
```

A vendor-specific OBO flow might use:

```text
grant_type=<vendor-grant>
assertion=<source-token>
requested_token_use=<vendor-value>
scope=<vendor-scope>
```

Differences can appear in grant URNs, parameters, client authentication, audience models, consent, response formats, and error semantics.

**Do not just swap the grant name in YAML and expect the built-in Token Exchange provider to handle any proprietary OBO flow.** If the provider lacks an RFC 8693 endpoint, use the vendor's SDK or write an extension matching the vendor contract.

### 11.1. Providers Supporting the RFC Still Differ on Policy

Even under RFC 8693, two STSs can differ in:

- Whether `subject_token_type` is `access_token` or `jwt`.
- Whether `audience` or `resource` is mandatory.
- Whether opaque tokens are accepted via introspection.
- Whether an actor token is required.
- Whether an output `act` claim is emitted.
- Whether cross-issuer/cross-tenant exchange is supported.
- Whether refresh tokens are issued.
- How scope mapping and revocation propagation behave.

The RFC provides common syntax; **provider compatibility** must still be evaluated per deployment.

---

## 12. Which Spring Security Version Introduced Token Exchange Support?

Spring Security includes:

```java
org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider
```

This class appeared in **Spring Security 6.3**.

In the Servlet stack, the `RestClient`-based HTTP token response client:

```java
org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient
```

appeared in **Spring Security 6.4**.

For WebFlux/reactive:

```java
org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider
org.springframework.security.oauth2.client.endpoint.WebClientReactiveTokenExchangeTokenResponseClient
```

Auto-detection of configuration beans and customization APIs depend on the Spring Security/Boot version. Do not mix dependencies across version lines or apply 7.x examples to a 6.2 project without checking the APIs.

### 12.1. Declaring the Grant Type Alone Is Not Enough

Configuring:

```yaml
authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
```

declares the registration's grant type, yet does not guarantee the default manager has `TokenExchangeOAuth2AuthorizedClientProvider` wired.

Enable the provider or configure the corresponding authorized client manager depending on your version and application auto-configuration.

## 13. Spring Boot Example: Service A as Both Resource Server and OAuth2 Client

Suppose:

```text
Service A:
    https://service-a.example.net
    receives JWT Token A, aud=service-a

STS:
    https://id.example.net/oauth2/token
    accepts Token Exchange from client service-a-exchange

Orders API:
    https://orders.example.net
    requires aud=orders-api, scope=orders.read
```

### 13.1. Dependencies for Spring Boot 3.x Servlet

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Spring Boot 4.x renames some starters; use a BOM compatible with your framework version. Do not drop security dependencies if Service A needs both inbound JWT validation and outbound token exchange.

### 13.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.net

      client:
        registration:
          orders-exchange:
            provider: enterprise-sts
            client-id: ${ORDERS_EXCHANGE_CLIENT_ID}
            client-secret: ${ORDERS_EXCHANGE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            scope:
              - orders.read

        provider:
          enterprise-sts:
            token-uri: https://id.example.net/oauth2/token
```

Explanation:

- Resource Server JWT configuration verifies the inbound issuer/token. The application must still validate Service A's **audience** and authorization.
- Registration `orders-exchange` is the outbound OAuth2 client using the Token Exchange Grant.
- `token-uri` is the STS Token Endpoint, not the Orders API URL.
- `scope=orders.read` is an example per target policy.
- `client-id` and `client-secret` are credentials of the **exchange client**, not End-User credentials.

If the provider requires `private_key_jwt`, mTLS, or another method instead of Basic secret auth, configure client authentication to match that contract.

### 13.3. A Token Exchange Registration Is Not OAuth2 Login

You can define separate registrations:

```text
corporate-login    -> authorization_code
orders-exchange    -> token-exchange
inventory-service  -> client_credentials
```

A Token Exchange registration does not provide browser redirects or OIDC UserInfo. It solely describes how to exchange tokens.

## 14. SecurityFilterChain Validating the Inbound Token

Service A receives a Bearer JWT from the caller:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

This is only a baseline configuration. Production needs validation of Service A's audience, claims/authorities, tenant, and business authorization. Never assume any JWT signed by a valid issuer grants the caller unrestricted permissions.

**Never construct a `JwtAuthenticationToken` from an unverified JWT** and treat it as a trusted principal.

---

## 15. TokenExchangeOAuth2AuthorizedClientProvider

The provider responsible for handling the Token Exchange grant inside `OAuth2AuthorizedClientManager`:

```java
org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider
```

Interface:

```java
OAuth2AuthorizedClientProvider
```

It can:

1. Receive `OAuth2AuthorizationContext`.
2. Check whether the client registration uses the Token Exchange grant.
3. Inspect any existing authorized client and its expiry.
4. Resolve the subject token and optional actor token.
5. Call the token response client against the STS.
6. Return an `OAuth2AuthorizedClient` containing the issued token.
7. Return `null` if unsupported or if reauthorization is not yet needed per contract.

Token Endpoint errors are typically translated into OAuth2 exceptions rather than triggering fallback to another grant.

### 15.1. Provider Bean

Example for Spring Security 6.4+:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient;

@Configuration
class ExchangeProviderConfiguration {

    @Bean
    TokenExchangeOAuth2AuthorizedClientProvider tokenExchangeProvider() {
        RestClientTokenExchangeTokenResponseClient responseClient =
            new RestClientTokenExchangeTokenResponseClient();

        TokenExchangeOAuth2AuthorizedClientProvider provider =
            new TokenExchangeOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(responseClient);
        return provider;
    }
}
```

This illustrates explicit wiring; you do not need to declare this bean if your version's auto-configuration already meets your needs. If an application has multiple providers/managers, select beans using qualifiers.

### 15.2. Creating a Servlet Manager

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
class ExchangeManagerConfiguration {

    @Bean("tokenExchangeManager")
    OAuth2AuthorizedClientManager tokenExchangeManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients,
            TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider) {

        OAuth2AuthorizedClientProvider providers =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .provider(exchangeProvider)
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
```

The manager above contains only the Token Exchange provider. If the app also needs Authorization Code, Refresh Token, or Client Credentials for other registrations, construct the corresponding provider chain per application policy rather than blindly enabling every grant.

**The Manager/Provider only executes the OAuth2 Client workflow; the STS remains the authority deciding token issuance.**

## 16. Default Subject Token in Spring Security

By default, `TokenExchangeOAuth2AuthorizedClientProvider` attempts to obtain the subject token from:

```java
OAuth2AuthorizationContext
    .getPrincipal()
    .getPrincipal()
```

when that principal object represents an appropriate `OAuth2Token`.

A Spring Resource Server validating a JWT typically creates:

```java
JwtAuthenticationToken
```

whose principal is:

```java
Jwt
```

Thus `JwtAuthenticationToken` fits the default resolver out of the box.

### 16.1. Calling the Manager from a Controller

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ExchangeController {

    private final OAuth2AuthorizedClientManager manager;

    ExchangeController(
            @Qualifier("tokenExchangeManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/api/exchange-status")
    ResponseEntity<String> exchange(JwtAuthenticationToken authentication) {

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("orders-exchange")
                .principal(authentication)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            return ResponseEntity.badRequest()
                .body("No authorized client available");
        }

        // Return harmless metadata only; never return the token value.
        return ResponseEntity.ok(
            "Authorized via " +
            client.getClientRegistration().getRegistrationId()
        );
    }
}
```

This controller only demonstrates passing an authenticated principal into the manager. In production, never expose an unrestricted exchange endpoint to callers; enforce business authorization before requesting target tokens. Handle OAuth2 failures via proper exception handling.

### 16.2. When the Principal Is OidcUser

An OAuth2 Login/OIDC Client application typically has:

```text
Authentication = OAuth2AuthenticationToken
Principal      = OidcUser
AuthorizedClient = registration + access token + refresh token (if any)
```

`OidcUser` is not itself a raw OAuth2 subject token that the default resolver can use directly.

When the STS requires an **OAuth access token** as input, retrieve the user's access token from their authorized client using the verified registration and principal.

Do not pick the ID Token just because `OidcUser.getIdToken()` is convenient to call.

### 16.3. `setSubjectTokenResolver(...)`

Spring Security supports:

```java
provider.setSubjectTokenResolver(context -> {
    // Return a trusted OAuth2Token or null.
    return null;
});
```

Example custom resolver accepting only a Resource Server JWT principal:

```java
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

TokenExchangeOAuth2AuthorizedClientProvider provider =
    new TokenExchangeOAuth2AuthorizedClientProvider();

provider.setSubjectTokenResolver(context -> {
    if (context.getPrincipal() instanceof JwtAuthenticationToken auth) {
        return auth.getToken();
    }
    return null;
});
```

This example restricts the subject token source; it is not a substitute for inbound JWT verification. If retrieving tokens from `OAuth2AuthorizedClientService`, verify ownership, tenant, and source registration.

### 16.4. Never Accept Subject Tokens from Query Parameters

An endpoint like:

```text
GET /exchange?subject_token=...&audience=...
```

is unsafe if the backend uses privileged client credentials to exchange tokens for arbitrary user-requested subjects or targets.

The subject token and target must come from a **controlled security/business context**, never from arbitrary caller-supplied input.

## 17. Actor Tokens Are Not Resolved by Default

`TokenExchangeOAuth2AuthorizedClientProvider` provides the hook:

```java
setActorTokenResolver(...)
```

However, **actor tokens are not resolved automatically by default**.

If the STS requires delegation with an actor:

1. Determine who the actor is per policy.
2. Obtain a valid actor security token from an issuer trusted by the STS.
3. Configure the resolver to supply that token to the grant.
4. Verify the actor token type and required target/scope.
5. Verify the output token contains actor claims when the STS issues a delegation token.

Never place a raw client ID string into `actor_token` and claim it is a JWT. Never manually inject `act` into a signed JWT.

### 17.1. Resolver Differs from Client Authentication

An actor token is not necessarily the client assertion used for client authentication. Under some policies client and actor are related, yet each token serves a **different protocol role**.

Never use `client_secret` as an actor token or treat an HTTP Basic header as actor authorization.

---

## 18. Customizing Audience with RestClientTokenExchangeTokenResponseClient

The STS may require:

```text
audience=orders-api
```

Spring Security 6.4+ lets you add parameters using a converter:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

@Configuration
class ExchangeHttpConfiguration {

    @Bean
    RestClientTokenExchangeTokenResponseClient exchangeResponseClient() {
        RestClientTokenExchangeTokenResponseClient responseClient =
            new RestClientTokenExchangeTokenResponseClient();

        responseClient.addParametersConverter(grantRequest -> {
            MultiValueMap<String, String> params =
                new LinkedMultiValueMap<>();

            if ("orders-exchange".equals(
                    grantRequest.getClientRegistration()
                        .getRegistrationId())) {
                params.add(
                    OAuth2ParameterNames.AUDIENCE,
                    "orders-api"
                );
            }

            return params;
        });

        return responseClient;
    }
}
```

Attach this response client to the provider:

```java
@Bean
TokenExchangeOAuth2AuthorizedClientProvider tokenExchangeProvider(
        RestClientTokenExchangeTokenResponseClient responseClient) {

    TokenExchangeOAuth2AuthorizedClientProvider provider =
        new TokenExchangeOAuth2AuthorizedClientProvider();

    provider.setAccessTokenResponseClient(responseClient);
    return provider;
}
```

**Note:** This `tokenExchangeProvider` bean **replaces** the identically named bean from the previous section; do not declare both simultaneously unintentionally.

### 18.1. When Does `addParametersConverter` Fit?

When you only need to **append** audience/resource or provider extensions per registration.

Common APIs:

| API | Meaning |
|---|---|
| `addParametersConverter(...)` | Appends parameters to the standard request |
| `setParametersConverter(...)` | Customizes/overrides parameters per contract |
| `setParametersCustomizer(...)` | Deeply customizes the final parameters, including potentially removing default params |

Avoid replacing the entire form body just to add an audience. Accidentally dropping `grant_type`, `subject_token`, or `subject_token_type` invalidates the request.

### 18.2. When the Provider Requires a Resource URI

Example:

```java
params.add("resource", "https://orders.example.net");
```

Use a **configured and allowlisted** resource, never an arbitrary URL supplied by the browser. Using a user-supplied URI to request a token and then sending the token to that URI can lead to SSRF and token leakage.

### 18.3. When the Provider Requires Multiple Audiences

The RFC permits multiple values, though issuing a token valid for multiple audiences depends on STS policy. Generally, issue separate tokens per API to avoid overly broad targets/scopes.

## 19. HTTP Transport and Token Endpoint Errors

Spring can use `RestClient` for Token Exchange requests. Aspects to configure:

- Connect/read/response timeouts.
- Proxy settings.
- TLS truststore.
- Client authentication.
- Form HTTP message converters.
- OAuth2 token response JSON converters.
- OAuth2 error response handling.

`RestClientTokenExchangeTokenResponseClient.setRestClient(...)` lets you supply a customized HTTP transport.

If you build a custom `RestClient`, retain the form and token response converters along with the proper error handler. Do not swap in a bare hand-rolled HTTP POST parser that ignores OAuth2 errors.

### 19.1. Never Disable TLS Validation

Token Exchange requests contain highly sensitive credentials:

```text
subject_token
actor_token
client_secret
client_assertion
Authorization header
```

If you encounter PKIX/TLS failures, fix the truststore/CA/hostname/proxy. Never use trust-all settings or disable hostname verification.

### 19.2. Retries Must Follow Semantics

A timeout does not prove the AS failed to process the request. Never retry infinitely, especially if the subject token has one-time-use semantics or the provider enforces replay detection.

Distinguish errors:

- `invalid_client`, `unauthorized_client`, `invalid_target`: usually cannot be fixed by retrying.
- HTTP 503/timeout: may be retried with bounded attempts/backoff per provider contract.
- `invalid_request`: inspect the subject token, type, and policy rather than changing HTTP clients.

---

## 20. Calling Orders API with Token B

After the manager returns:

```java
OAuth2AuthorizedClient authorized =
    manager.authorize(request);
```

the output token is accessed via:

```java
authorized.getAccessToken().getTokenValue()
```

Example call using `RestClient`:

```java
import org.springframework.web.client.RestClient;

public String fetchOrders(
        RestClient ordersRestClient,
        OAuth2AuthorizedClient authorized) {

    return ordersRestClient.get()
        .uri("/v1/orders")
        .headers(headers -> headers.setBearerAuth(
            authorized.getAccessToken().getTokenValue()
        ))
        .retrieve()
        .body(String.class);
}
```

Dedicate `ordersRestClient` to the Orders API with a fixed `baseUrl` and controlled redirects. Never send Token B to another API simply because it has not expired yet.

### 20.1. Resource Server B Must Validate the Token

Token B must satisfy:

- `iss`: trusted issuer.
- `aud`: matches Orders API.
- `exp`/`nbf`: within validity window.
- Signature/introspection.
- Relevant scopes and claims.
- Actor/delegation/tenant policies if applicable.

A successful token exchange does not automatically grant all business permissions.

## 21. AuthorizedClientManager and Token Exchange Caching

`OAuth2AuthorizedClientManager` can use an authorized client repository/service to store Token B after exchange.

The key is typically:

```text
(clientRegistrationId, principalName)
```

Example:

```text
("orders-exchange", "alice-901")
    -> Token B
```

### 21.1. The Cache Key May Be Insufficient

Token Exchange may additionally depend on:

- Which Token A was sent as `subject_token` (issuer, token ID, session).
- Actor token.
- Tenant.
- Target audience/resource.
- Per-request scopes.
- Authentication strength/consent.

If the cache key is only `(registrationId, principalName)`, an **unexpired** authorized client B could be reused for a request whose **subject token/actor/target has changed**.

Example:

```text
T0: Alice Token A1 -> exchange -> B1, stored under "orders-exchange", "alice"
T1: Alice logs in again and gets Token A2 with different claims/permissions
T2: Manager sees B1 is still unexpired and may reuse B1
```

If business logic requires Token B to always correspond to the **current request's** source token, that cache key violates policy.

### 21.2. Design Options

- Separate registrations per target audience/scope profile.
- Stable principals namespaced by issuer/tenant.
- Custom storage keys incorporating source authorization context when needed.
- Explicit re-authorization when the subject token changes.
- Cache Token B only within request/session scope when policy demands it.
- Never store Alice's Token B under a shared service principal.
- Design invalidation on logout/revoke/disconnect.

Do not treat the provider seeing an unexpired `OAuth2AuthorizedClient` as proof that Token A is still valid.

### 21.3. Token Lifecycles Are Not Synchronized by Default

The RFC does not guarantee that revoking Token A automatically revokes Token B. Consequently, on user disconnect, the STS/Resource Server or application may need explicit revocation/removal.

Questions to answer:

1. Does Token B survive user logout?
2. If subject token A is revoked, is B still usable?
3. Does Token B have a refresh token?
4. When B expires, can A be exchanged again?
5. When A expires, how must fresh authorization be obtained?
6. Across multiple nodes, what coordinates avoiding duplicate exchange requests?

## 22. WebFlux/Reactive Counterpart

In Spring WebFlux, use:

```java
TokenExchangeReactiveOAuth2AuthorizedClientProvider
WebClientReactiveTokenExchangeTokenResponseClient
```

Reactive contracts return `Mono<OAuth2AuthorizedClient>` rather than a synchronous `OAuth2AuthorizedClient`.

Provider example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.TokenExchangeReactiveOAuth2AuthorizedClientProvider;

@Configuration
class ReactiveExchangeConfiguration {

    @Bean
    TokenExchangeReactiveOAuth2AuthorizedClientProvider exchangeProvider() {
        return new TokenExchangeReactiveOAuth2AuthorizedClientProvider();
    }
}
```

Attach the provider to `ReactiveOAuth2AuthorizedClientManager` and matching reactive repositories/services. In a WebFlux server, the manager typically uses `ReactiveClientRegistrationRepository` and `ServerOAuth2AuthorizedClientRepository`.

### 22.1. Reactive Resolvers Return Mono

`setSubjectTokenResolver` and `setActorTokenResolver` on the reactive provider take functions returning `Mono<OAuth2Token>`, not a synchronous `OAuth2Token`.

Never call `.block()` on a Reactor event loop just to retrieve a token; compose reactive publishers instead.

### 22.2. SecurityContext Is Not Yet a Subject Token

`ReactiveSecurityContextHolder` carries authentication across the Reactor Context, yet does not automatically turn an `Authentication` into an `OAuth2Token` accepted by the STS. You must still select the proper source token, client registration, and target.

---

## 23. `invalid_request`, `invalid_target`, and Common Errors

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `unsupported_grant_type` | AS does not support/enable RFC 8693 | Check Token Endpoint, version, and tenant |
| `unauthorized_client` | Client is not permitted to use Token Exchange | Grant/client permissions |
| `invalid_client` | Wrong secret, mTLS, or JWT client assertion | Client authentication |
| `invalid_request` | Subject token/type missing, invalid, or rejected by policy | Request body, trust, issuer, expiry |
| `invalid_target` | Audience/resource unsupported or disallowed | Target identifiers and allowed audiences |
| `invalid_scope` | Scope invalid for client/target | Scope mapping |
| `subject_token` not found | Principal is not an `OAuth2Token` | Custom subject resolver pointing to the right source |
| Actor token not sent | Missing actor resolver | Delegation config and actor source |
| Response parse error | Missing `issued_token_type` or wrong `token_type` | RFC response contract |
| Token B missing expected audience | Provider ignores/overrides target | Request params and STS policy |
| Orders API 401 | Wrong `iss`/`aud`/signature/expiry | Resource Server validation |
| Orders API 403 | Missing scope/role/ownership | Scope mapping and business policy |
| STS timeout | Network/proxy/TLS/AS outage | HTTP transport and bounded retries |
| Another user's Token B reused | Wrong cache principal/tenant key | Storage key and authorization |
| `OAuth2AuthorizedClientManager` lacks matching provider | Token Exchange not enabled | Provider builder/bean wiring |
| Provider configured yet still fails | AS policy rejects client/source/target | Interoperability contract |

### 23.1. `invalid_request` Is Not Only Missing Fields

RFC 8693 allows `invalid_request` when a subject or actor token is invalid or unacceptable under policy. A form body containing all required parameters can still be rejected.

### 23.2. `invalid_target` Differs from `invalid_scope`

`invalid_target` concerns the target audience/resource. `invalid_scope` concerns the requested permission scope.

A scope valid for Orders API may be invalid at Billing API. When troubleshooting, inspect target + scope + client permissions together.

### 23.3. STS HTTP 200 Yet API 401

This can stem from a mismatch between the issuer/audience issued by the STS and what API B validates. Do not keep requesting new Token Bs indefinitely before checking Resource Server configuration.

## 24. Using cURL to Verify Compatibility

Before writing complex Spring logic, you can test the Token Endpoint in development with a test client:

```bash
curl --request POST "https://id.example.net/oauth2/token" \
  --user "$EXCHANGE_CLIENT_ID:$EXCHANGE_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
  --data-urlencode "subject_token=$SUBJECT_ACCESS_TOKEN" \
  --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:access_token" \
  --data-urlencode "requested_token_type=urn:ietf:params:oauth:token-type:access_token" \
  --data-urlencode "audience=orders-api" \
  --data-urlencode "scope=orders.read"
```

In practice, command-line arguments, terminal history, process listings, and CI logs can expose credentials. Only use dummy tokens/test secrets in examples, or pass secrets via mechanisms protected by your infrastructure.

### 24.1. Inspecting the Response

- HTTP status.
- `access_token`.
- Correct `issued_token_type`.
- Usable `token_type`.
- Reasonable `expires_in`.
- Actually granted scopes.
- Whether the target API accepts the token.
- Whether the token received overly broad scopes/audiences.

### 24.2. Important Negative Tests

1. Missing subject token.
2. Wrong subject token type.
3. Expired subject token.
4. Subject token from an untrusted issuer.
5. Client lacking Token Exchange permission.
6. Invalid client authentication.
7. Audience outside allowlist.
8. Disallowed scope.
9. Invalid actor token.
10. Disallowed cross-tenant token.
11. Output token carrying wrong audience.
12. Response missing required fields.
13. Revocation or logout behavior.
14. Consecutive token exchanges / one-time-use behavior.

This is actual compatibility evidence—far beyond merely observing that the Spring application starts cleanly.

## 25. Testing in Spring Security

### 25.1. Client Registration Test

Verify:

```text
registrationId = orders-exchange
authorizationGrantType = urn:ietf:params:oauth:grant-type:token-exchange
tokenUri = correct STS
clientAuthenticationMethod = expected method
```

Use `ClientRegistrationRepository` in unit tests without hitting the network for static configuration.

### 25.2. Subject Resolver Test

Create a test JWT or mock `SecurityContext` to confirm the resolver extracts the expected `OAuth2Token` from an authenticated principal. Never fake an unverified JWT in a test and claim the real Resource Server validated its signature.

### 25.3. Token HTTP Request Test

Mock the Token Endpoint and verify:

```text
grant_type
subject_token
subject_token_type
requested_token_type if needed
audience/resource
scope
client authentication
```

Do not log raw tokens; use dummy values.

### 25.4. Response Test

Mock:

```json
{
  "access_token": "fake-orders-token",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Verify the token is saved under the right registration/principal and used to call API B as expected.

### 25.5. Contract Test Against a Real Provider

Mocking `OAuth2AuthorizedClientManager` to always return a dummy token **does not prove** the provider supports RFC 8693 compatibility.

You need a test STS environment with real grant/client policies to verify:

- Source token trust.
- Target allowlist.
- Delegation/actor policy.
- Output issuer/audience.
- Token expiry/revocation.
- Vendor-specific requirements.

---

## 26. End-to-End Security

### 26.1. Preventing Confused Deputy

Service A holds privileged client credentials. If it accepts arbitrary audiences/tokens from users and exchanges them unchecked, Service A becomes a **confused deputy**.

Mitigations:

- Never expose an endpoint letting callers pick arbitrary audiences.
- Validate inbound authentication.
- Allow only targets defined by business policy.
- Restrict the OAuth2 client's permissions at the STS.
- Never bypass user/tenant authorization.
- Audit targets/registrations using safe identifiers.

### 26.2. Never Log Credentials

Avoid logging:

```text
subject_token
actor_token
access_token
refresh_token
client_secret
client_assertion
Authorization header
Raw ID Token value
```

Safe metadata to log:

```text
registrationId=orders-exchange
target=orders-api
event=token_exchange
result=success|invalid_target|invalid_request
latencyMs=...
```

If principal identifiers constitute personal data, apply pseudonymization and avoid high-cardinality metric labels.

### 26.3. Never Send Token B to Arbitrary Hosts

When using Token B with the Orders API, lock down base URLs, absolute URIs, redirects, and proxies. A Bearer token can be used by anyone who intercepts it unless sender-constrained.

### 26.4. Sender-Constrained Tokens

If the STS issues mTLS-bound or DPoP-bound access tokens, the client must present the corresponding proof. A plain `Authorization: Bearer ...` header does not satisfy proof-of-possession policies.

### 26.5. Caching and Lifecycle

Never store Token B indefinitely in a singleton field or a cache lacking tenant/source context. Token B can become invalid through expiry/revocation, and the source token or user session can change.

If the STS lacks revocation propagation, implement TTL, logout/disconnect, and invalidation rules matching your requirements.

---

## 27. Real-World Scenarios

### Scenario A: Service A Calls Orders API

A receives Token A with audience `service-a` and needs to call B with audience `orders-api`.

**Approach:** RFC 8693 Token Exchange with subject Token A, target Orders, and minimal scope, provided the STS/client has permission.

### Scenario B: Provider Returns `unsupported_grant_type`

**Likely cause:** the STS does not implement RFC 8693 or the grant is disabled in the realm/tenant.

**Approach:** check server documentation and configuration; this cannot be fixed in Java alone.

### Scenario C: Provider Requires Audience

The request body omits `audience`.

**Approach:** use `addParametersConverter` to send an allowlisted audience.

### Scenario D: Provider Only Supports Proprietary OBO

Documentation requires an `assertion` parameter or custom grant.

**Approach:** use the vendor SDK/extension; do not mix it into an RFC 8693 request.

### Scenario E: Subject Token Is Opaque

The STS cannot introspect it.

**Approach:** configure proper trust/introspection or pick a flow supported by the provider.

### Scenario F: OIDC Login Has OidcUser, Yet the Resolver Sees No Subject Token

**Approach:** retrieve the user's access token from the appropriate authorized client via a trusted resolver; never substitute the ID Token unconditionally.

### Scenario G: Actor Token Is Required

The STS expects an actor JWT from a trusted issuer.

**Approach:** supply an actor resolver and permission policy; never use `client-id` as the actor token.

### Scenario H: Token B Is Issued Successfully, Yet Orders API Returns 401

**Approach:** verify JWT B's issuer, audience, expiry, signature, and API trust config; do not loop Token Exchange infinitely.

### Scenario I: User Logs Out, Yet Token B Still Works

**Approach:** inspect revocation/removal/TTL policies; logout does not automatically revoke every token at the STS.

### Scenario J: Two Tenants Share the Same Subject String

**Risk:** cached Token B used across tenants.

**Approach:** namespace by issuer/tenant and stable principal, and enforce ownership checks.

### Scenario K: Service A Needs Application Permissions, Not User Permissions

**Approach:** consider Client Credentials instead of Token Exchange.

### Scenario L: Provider Issues `issued_token_type=jwt` and `token_type=N_A`

**Approach:** review the output token's purpose; do not assume it can be used as an OAuth Bearer access token.

### Scenario M: STS Refuses Cross-Issuer Token Exchange

**Approach:** configure governed trust/federation rules. Never strip validation or spoof issuers to bypass errors.

### Scenario N: Token B Remains Cached Even Though Token A Changed

**Approach:** tie cache keys/lifecycles to the source authorization policy, or proactively re-exchange when needed.

### Scenario O: Client Requests Overly Broad Scopes

**Approach:** apply scope downscoping per API; never omit business authorization at the Resource Server.

## 28. Self-Check Questions

**1. Which RFC standardizes Token Exchange?**  
RFC 8693.

**2. What is the Token Exchange Grant URN?**  
`urn:ietf:params:oauth:grant-type:token-exchange`.

**3. What are the required request parameters per the RFC?**  
`grant_type`, `subject_token`, and `subject_token_type`; plus client authentication per deployment requirements.

**4. Does optional `audience`/`resource` mean providers cannot require them?**  
No. They are optional in the RFC, yet may be mandatory under STS policy.

**5. When is `actor_token_type` required?**  
Only when `actor_token` is present; then it is required.

**6. Can an OIDC ID Token simply be treated as an access token?**  
No. They serve different purposes; token types must match the provider contract.

**7. Are `subject_token_type=jwt` and `access_token` always identical?**  
No. JWT describes syntax, while `access_token` describes OAuth2 purpose.

**8. How does `issued_token_type` differ from `token_type`?**  
The first states the type of token issued; the second states how the token is used.

**9. Does exchanging automatically revoke Token A?**  
Not by default.

**10. Does Token Exchange always return a refresh token?**  
No.

**11. Is a vendor's OBO always RFC 8693?**  
No; compare grants, parameters, and documentation.

**12. Since which version has Spring Security included built-in Token Exchange?**  
`TokenExchangeOAuth2AuthorizedClientProvider` since 6.3.

**13. Since which version has `RestClientTokenExchangeTokenResponseClient` existed?**  
Spring Security 6.4.

**14. Why does `JwtAuthenticationToken` fit the default subject token resolver?**  
Its principal is typically a `Jwt`, an `OAuth2Token` understood by the framework.

**15. Is `OidcUser` automatically a raw subject access token?**  
No. You may need a resolver fetching the right token from the authorized client.

**16. Which API adds `audience` to the token request?**  
`RestClientTokenExchangeTokenResponseClient.addParametersConverter(...)`.

**17. When does the STS return `invalid_target`?**  
When the target audience/resource is unsupported or disallowed by policy.

**18. Does an issued Token B prove business authorization?**  
No. API B must still check scopes, claims, and ownership.

**19. Can Alice's Token B be used for Bob under the same registration?**  
No. Enforce principal, tenant, and token ownership controls.

**20. When should Client Credentials be used instead?**  
When the backend needs a token representing the service itself rather than a delegated subject token.

---

## 29. Key Takeaways

| Concept | Memory Aid |
|---|---|
| RFC 8693 | Standard for Token Exchange via the OAuth2 Token Endpoint |
| `grant_type` | Extension grant URN, not `authorization_code` |
| `subject_token` | Input token representing the subject |
| `subject_token_type` | Input token type, required |
| `actor_token` | Optional token of the actor |
| `actor_token_type` | Required when an actor token is present |
| `requested_token_type` | Desired output token type |
| `resource` | Target absolute URI |
| `audience` | Target logical identifier |
| `scope` | Permissions requested at the target |
| `act` | Actor claim usable in delegation |
| `may_act` | Claim that can help the STS evaluate actor permissions |
| `issued_token_type` | Required in RFC 8693 responses |
| `token_type` | Token usage type (`Bearer`/`N_A`, etc.) |
| `invalid_target` | Target unsupported or disallowed |
| STS compatibility | Grant, client auth, subject trust, target, and response |
| `TokenExchangeOAuth2AuthorizedClientProvider` | Built into Spring Security since 6.3 |
| `RestClientTokenExchangeTokenResponseClient` | HTTP token client since 6.4 |
| `setSubjectTokenResolver` | Selects trusted input token |
| `setActorTokenResolver` | Selects actor token when allowed by STS |
| `addParametersConverter` | Appends audience/resource/extension parameters |
| `OAuth2AuthorizedClientManager` | Coordinates grant execution and token storage |
| Reactive counterpart | Reactive token-exchange provider + WebClient response client |
| Proprietary OBO | Not RFC 8693-compatible by default |
| Resource Server B | Independently validates Token B and authorization |
| Token lifecycle | Exchange does not sync revocation/expiry with input |

### Conclusion

Token Exchange enables an OAuth2 client to **exchange an input security token for a new token** at an STS, typically to call a downstream API with the **right audience and scope**. It is especially useful for API gateways, BFFs, and microservices spanning multiple Resource Servers.

However, **Spring Security configuration cannot create RFC 8693 support on the provider side**. Before implementing, verify grant permissions, client authentication, subject token type, issuer trust, actor/delegation policy, audience/resource/scope, and output token semantics.

In modern Spring Security, `TokenExchangeOAuth2AuthorizedClientProvider`, `RestClientTokenExchangeTokenResponseClient`, and `OAuth2AuthorizedClientManager` are the right starting point. Add custom resolvers/converters only as required by the provider contract; always protect tokens, principals, tenants, token lifecycles, and every API call.

**A Token Exchange returning HTTP 200 does not prove secure authorization**: the entire trust chain from caller → Service A → STS → Service B must be verified end-to-end.

## Official References

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html) — request/response, delegation, actor claims, and errors.
- [Spring Security — Authorization Grant Support (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html) — Token Exchange and client customization.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/) — authorized client manager and providers.
- [Spring Security API — TokenExchangeOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/TokenExchangeOAuth2AuthorizedClientProvider.html) — subject/actor resolvers and expiry.
- [Spring Security API — RestClientTokenExchangeTokenResponseClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/RestClientTokenExchangeTokenResponseClient.html) — Token Exchange HTTP request customization.
- [Spring Security API — TokenExchangeGrantRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/TokenExchangeGrantRequest.html) — grant request type.
- [Spring Security — Reactive Authorization Grants](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html) — Token Exchange on WebFlux.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html) — security practices for OAuth2.
