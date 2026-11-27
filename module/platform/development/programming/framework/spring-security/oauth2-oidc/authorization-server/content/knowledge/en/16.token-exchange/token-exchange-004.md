# Evaluating Support for `actor_token`, `resource`, and `audience` by Version

## 1. Why "Having Token Exchange" Does Not Mean "Supporting Every Parameter"

In an Authorization Server built with **Spring Boot, Spring Security, and Spring Authorization Server (SAS)**, an `orders-api` service might receive an access token representing user Alice and then need to call `inventory-api` to fetch stock levels. Forwarding the original access token intended for `orders-api` as-is to `inventory-api` is a dangerous design: the token may have the wrong `aud`, carry overly broad privileges, or prevent the target service from knowing who is acting on the user's behalf.

OAuth 2.0 **Token Exchange** (RFC 8693) defines how a client presents an input token and requests a new token scoped to **subject**, **actor**, **target**, and **scope** context. Notable parameters include:

- `subject_token`: token representing the subject on whose behalf the request is made; a **required** input.
- `actor_token`: optional token representing the party actually performing the action; useful for delegation.
- `resource`: URI of the resource/service the new token is intended to access.
- `audience`: logical name of the service or recipient receiving the new token.

However, four levels of support must be distinguished: **(1) defined by the spec; (2) converter parses the parameter; (3) provider validates it and enforces policy; (4) output token carries the right claims and the Resource Server verifies them**. Having getters like `getActorToken()` or `getAudiences()` in a version only proves the ability to **represent inputs**, not that the entire flow is secure.

This lesson belongs to the **Token Exchange** chapter and helps learners evaluate each capability for their running Spring version, design delegation and target checks, define token contracts, write interoperability tests, and operate safely rather than trusting class/API names alone.

## 2. How Token Exchange Differs from Authorization Code and Refresh Token

| Flow | Basis for requesting a token | Core meaning |
| --- | --- | --- |
| **Authorization Code + PKCE** | Code obtained after user authorization | Client obtains permissions via user login/consent interaction |
| **Refresh Token** | Refresh token previously issued to the client | Requests a fresh token under an existing authorization |
| **Client Credentials** | Client authentication and grant policy | Client/service receives permissions for itself, not necessarily involving a user |
| **Token Exchange** | Subject token, optional actor token, client authentication, and policy | Transforms token context: target, scope, actor/delegation, or token type |

RFC 8693 grant type:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

A token exchange typically **does not revoke** the input subject token/actor token; likewise, the output token is not automatically revoked if the input token later expires or is revoked. If cascading revocation is required, the system must explicitly design relationships, TTLs, and state-checking mechanisms.

### 2.1. Business Example

```mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant OA as orders-api
    participant AS as Authorization Server
    participant IA as inventory-api
    U->>OA: Call orders-api with token A (aud=orders-api)
    OA->>AS: Exchange token A, target inventory-api
    AS->>AS: Authenticate client, subject/actor, and target policy
    AS-->>OA: Token B (aud=inventory-api, appropriate scope)
    OA->>IA: Call API with token B
    IA->>IA: Verify iss, aud, exp, scope, and permissions
    IA-->>OA: Allow or deny
```

This is the **target flow**. Actor and target checks must be verified to actually exist in your running version and configuration; do not assume SAS handles every organizational policy out of the box.

## 3. RFC 8693 Parameters and Conditions

| Parameter | RFC requirement | Meaning | Key checks |
| --- | --- | --- | --- |
| `grant_type` | Required | Selects the Token Exchange Grant | Client is permitted to use the grant |
| `subject_token` | Required | Token representing the party on whose behalf the action is taken | Token type, issuer, signature/state, expiry, permissions |
| `subject_token_type` | Required | URI identifying the subject token type | Token type is actually supported |
| `actor_token` | Optional | Token identifying the acting party | Independent validation and delegation authorization check |
| `actor_token_type` | **Required when `actor_token` is present; must not be sent when absent** | URI of the actor token type | Both parameters must be consistent |
| `resource` | Optional, repeatable | URI of the target service/resource | Absolute URI, no fragment; target allowlist |
| `audience` | Optional, repeatable | Logical name of the target | Unambiguous, explicit mapping |
| `scope` | Optional | Desired scope on the target | Aligned with client/subject/actor/target permissions |
| `requested_token_type` | Optional | Desired security token type to receive | Provider can actually issue that type |

**Special rule for actor:** if `actor_token` is sent, `actor_token_type` **must** also be sent; if no actor token is sent, `actor_token_type` **must not be present**. An actor token with a valid signature **does not yet** prove the actor is permitted to act on behalf of the subject.

### 3.1. `resource` Is a URI, Not a Scope

Example:

```text
resource=https://inventory.example.com/api
```

Per RFC 8693, `resource` must be an **absolute URI**, may include a query component, and **must not include a fragment**. A server may accept multiple resources, though products should consider capping target counts. Syntactic URI validity is not enough for authorization: `https://unknown.example/collect` must be rejected if it is outside the trust/target policy.

Never treat `resource` as a URL from which the server dynamically fetches metadata. Custom designs that dereference caller-supplied URLs risk SSRF; only use a controlled, onboarded target registry.

### 3.2. `audience` Is a Logical Identifier

Example:

```text
audience=inventory-api
```

`audience` may be a logical name, another identifier meaningful to the AS, or the name of a service. Within an Authorization Server, every audience must have a **unique, unambiguous** meaning.

Distinguish clearly:

- **Request `audience`:** what the client *requests*.
- **JWT claim `aud`:** what the Authorization Server *actually issues* after approval.
- **`RegisteredClient.clientId`:** identifier of the OAuth client *calling* the token endpoint, not automatically the audience of the new token.
- **`ID token aud` in OIDC:** audience per the OIDC client contract, never to be substituted for API access token validation.

### 3.3. Relationship Between `resource`, `audience`, and `scope`

The RFC permits multiple `resource`, multiple `audience`, and `scope` values in the same request. When requesting a token for multiple targets, the requested scopes apply across **all listed targets**, not just one matching target.

For example, a client is allowed:

```text
inventory-api: inventory.read
reports-api: reports.read
```

Yet the request:

```text
audience=inventory-api
audience=reports-api
scope=inventory.read reports.read
```

cannot be approved merely via `clientScopes.containsAll(requestedScopes)`. It is requesting a single token usable at both APIs with both scopes. Safe policies commonly choose **one target per exchange**, or validate every **target–scope** pair explicitly. The RFC defines `invalid_target` when a requested target is invalid, disallowed, or overly broad.

## 4. Standard Request and Response Examples

Illustrative request for client `orders-service`, with both subject and actor:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=SUBJECT_ACCESS_TOKEN
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&actor_token=ACTOR_ACCESS_TOKEN
&actor_token_type=urn:ietf:params:oauth:token-type:access_token
&resource=https%3A%2F%2Finventory.example.com%2Fapi
&audience=inventory-api
&scope=inventory.read
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

Uppercase strings are placeholders, **not real tokens or secrets**. The body is line-wrapped for readability; in practice, send a valid URL-encoded form body over TLS with client authentication matching the registration.

Successful response per supported capability/profile:

```json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
```

`issued_token_type` specifies the **security token type issued**, while `token_type` specifies how the token is presented. Not every server can issue every `requested_token_type` from the RFC, and normal token exchanges do not automatically generate long-lived refresh tokens.

A request **without an actor token** is also syntactically valid when `actor_token_type` is omitted. However, "no actor" does not mean a client can impersonate any user freely; impersonation requires strict policy too.

## 5. Support Matrix by Spring Version

| Version | Default Token Exchange components | Actor/resource/audience | How to interpret |
| --- | --- | --- | --- |
| **SAS prior to 1.3** | Do not assume built-in RFC 8693 converter/provider | May require a custom grant | Check classpath and upgrade or build an extension |
| **SAS 1.3.x** | Token Exchange converter/provider introduced in 1.3 | API supports RFC parameter model | Test actual token types, issuer trust, and claims |
| **SAS 1.5.x** | Protocol Endpoints docs list `OAuth2TokenExchangeAuthenticationConverter` and `OAuth2TokenExchangeAuthenticationProvider` | `OAuth2TokenExchangeAuthenticationToken` exposes actor, resources, audiences getters | **Reading input fields does not guarantee every delegation/target policy** |
| **Spring Security 7.x** | Integrated Authorization Server infrastructure also lists Token Exchange converter/provider | Javadoc continues to expose actor/resource/audience data | Configuration/semantics may differ; test specifically on 7.x |
| **Custom provider/vendor** | Product-dependent | Profile- and policy-dependent | Never infer from parameter names or generic RFC claims |

Spring Authorization Server **1.5.8** documentation confirms Token Exchange as a Token Endpoint grant; the provider Javadoc notes **Since: 1.3**. In Spring Security **7.1.x**, the documentation likewise lists the corresponding converter/provider.

**Do not conclude:** "because `OAuth2ParameterNames.ACTOR_TOKEN` exists, every actor JWT is accepted" or "because `getAudiences()` is non-empty, the output JWT certainly has the right `aud`." Verify every layer.

### 5.1. Record the Exact Deployed Versions

When starting an evaluation, collect (never guess from the Spring Boot name alone):

```text
Spring Boot version:          <resolved>
Spring Security version:      <resolved>
SAS version (if using 1.x):   <resolved>
Authorization Server issuer:  <issuer>
Token type:                   JWT or opaque
Resource Server version:      <resolved>
Client SDK:                   <resolved>
```

Bracketed values are placeholders to fill in. Seeing a class in newer Javadoc **does not prove** your project runs that version. When verifying special token types or external issuers, read the exact documentation/changelog for your version and write integration tests.

## 6. Token Exchange Processing Flow in SAS

```mermaid
flowchart TD
    A[POST /oauth2/token] --> B[OAuth2ClientAuthenticationFilter]
    B --> C{Valid client?}
    C -->|No| X[invalid_client]
    C -->|Yes| D[OAuth2TokenEndpointFilter]
    D --> E[OAuth2TokenExchangeAuthenticationConverter]
    E --> F[OAuth2TokenExchangeAuthenticationToken]
    F --> G[OAuth2TokenExchangeAuthenticationProvider]
    G --> H[Validate subject and actor tokens]
    H --> I[Client, actor, resource, audience, and scope policy]
    I -->|Deny| J[OAuth2 error]
    I -->|Allow| K[OAuth2TokenGenerator and claims policy]
    K --> L[Access token + appropriate aud/act/scope]
    L --> M[Resource Server validates aud, iss, scope]
```

This diagram shows the **target security architecture to achieve**, not a promise that the default provider already implements every policy step in every version.

| Component | Responsibility |
| --- | --- |
| `OAuth2ClientAuthenticationFilter` | Authenticates the OAuth client calling the token endpoint; distinct from subject/actor tokens |
| `OAuth2TokenEndpointFilter` | Receives grant requests, invokes the manager, and returns tokens/errors |
| `OAuth2TokenExchangeAuthenticationConverter` | Parses the request into a Spring `Authentication` object |
| `OAuth2TokenExchangeAuthenticationToken` | Holds input subject, actor, resources, audiences, scopes |
| `OAuth2TokenExchangeAuthenticationProvider` | Processes the grant within the version's default capabilities |
| `RegisteredClientRepository` | Looks up the client, validates auth method and permitted grants |
| `OAuth2AuthorizationService` | Retrieves token/authorization state within the AS domain |
| `OAuth2TokenGenerator` | Issues the new token; customizers can adjust claims |
| **Resource Server** | Verifies issuer, signature/state, audience, expiry, scope, and API permissions |

### 6.1. SAS 1.5.x Getters Confirmed by Javadoc

```java
// Snippet inside logic that has already received the Authentication request;
// not a standalone runnable provider implementation.
if (authentication instanceof OAuth2TokenExchangeAuthenticationToken exchange) {
    String subjectToken = exchange.getSubjectToken();
    String subjectType = exchange.getSubjectTokenType();
    String actorToken = exchange.getActorToken();        // May be null
    String actorType = exchange.getActorTokenType();    // May be null
    Set<String> resources = exchange.getResources();
    Set<String> audiences = exchange.getAudiences();
    Set<String> scopes = exchange.getScopes();

    // The variables above are INPUTS, not proof of approval.
    // Never log subjectToken or actorToken.
}
```

The Javadoc also notes that `actorToken`, `actorTokenType`, `resources`, and `audiences` may be empty/nullable. **Being able to represent input data in a parser does not mean the data has been verified and authorized.**

### 6.2. Registering the Grant on `RegisteredClient`

```java
RegisteredClient ordersService = RegisteredClient.withId(stableInternalId)
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode(secretFromSecureSource))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)
        .scope("inventory.read")
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
```

`AuthorizationGrantType.TOKEN_EXCHANGE` has existed since Spring Security 6.3. `stableInternalId` and `secretFromSecureSource` are illustrative variables; this code does not yet configure the repository, JWT keys, provider policies, or security filter chains.

**Having the grant registered does not mean the client can exchange any subject token or request any target.** Specific permissions must be enforced for `orders-service`, subject, actor, and audience.

## 7. `actor_token`: Identifying the Actor Is Not Delegation Authorization

In a single request, three distinct identities may exist:

```text
subject:           Alice (subject_token)
actor:             orders-service (actor_token)
requesting client: OAuth client authenticating at /oauth2/token
```

Never assume `actor_token` belongs to the requesting client or that the client is authorized to act for Alice merely because two name strings match.

### 7.1. Required Checks

1. **Subject token:** trusted issuer, supported type, valid signature/introspection/state, unexpired, profile-compliant audience/binding.
2. **Actor token:** validated **independently**; never trust a credential just because it accompanies a valid subject token.
3. **Subject–actor relationship:** is the actor allowed to perform delegation/impersonation? Requires explicit policy, sometimes drawing on `may_act` in the subject token plus internal rules.
4. **Client binding:** is the OAuth client calling exchange authorized to present that subject and actor?
5. **Target:** at which audience/resource and with which scopes is delegation permitted?
6. **Output:** new token carries the subject identity and appropriate actor info; never copy caller-asserted claims into the JWT without verification.

### 7.2. `act` and `may_act` Claims per RFC 8693

- **`act`:** identifies the party acting in a delegated token. In JWTs, this is a JSON object identifying the actor, such as `sub`, optionally paired with `iss` to avoid ambiguity. Values like `exp` or `aud` inside `act` **are not** the expiration/audience verification mechanism of the outer token.
- **`may_act`:** expresses that a party is permitted to become the actor under applicable circumstances; it can be a policy signal, but **does not replace** full AS authorization checks.

**Illustrative, simplified** output token:

```json
{
  "iss": "https://auth.example.com",
  "sub": "alice-sub-17",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "act": {"sub": "orders-service"}
}
```

This is not a complete JWT: a real token requires a signature, expiration, and profile-specific claims. Never take `act` content from an untrusted form field and issue it as a verified identity.

### 7.3. Actor/Subject Tokens from External Issuers

Token Exchange **is not automatically cross-domain federation**. It has been reported in the Spring project that the default provider queries `OAuth2AuthorizationService` to verify subject/actor tokens, so it does not automatically validate tokens issued by arbitrary external issuers. This is a **historical capability checkpoint** that must be re-verified against your exact version.

If exchanging tokens from another IdP is required, you need issuer onboarding, trust stores/JWKs, allowed algorithms, audience checks, expiry, key rotation, token types, subject mapping, delegation policy, and revocation handling. Never pull an arbitrary JWKS URL directly from a claim/token submitted by the caller to validate that same token.

## 8. `resource` and `audience`: Dedicated Policy and Output Claims Are Required

A system might maintain a mapping such as:

| Registered Resource URI | Logical audience | Allowed scopes per policy |
| --- | --- | --- |
| `https://inventory.example.com/api` | `inventory-api` | `inventory.read`, `inventory.write` |
| `https://reports.example.com/api` | `reports-api` | `reports.read` |
| `https://admin.example.com/api` | `admin-api` | Dedicated admin rights, client-restricted |

This is an **application-managed** registry, not a built-in SAS mapping.

### 8.1. Three Pieces of Evidence Required

1. The converter parses `resource`/`audience`, including repeated values per the RFC.
2. The provider/policy validates client, subject, actor, and target; rejects unknown targets and over-broad multi-targets.
3. The actual access token carries the **approved** `aud`, and the Resource Server enforces audience validation before returning data.

If only item 1 is true, Token Exchange **has not achieved audience isolation**.

### 8.2. `resource` and `audience` in the Same Request

Policy can:
- Allow both **only when they refer to the same registered target**.
- Allow multiple targets with granular rules per target–scope pair.
- Adopt a conservative policy: **at most one target per request**, rejecting any other combination with `invalid_target`.

Do not claim RFC 8693 forbids multi-target requests; that is an **implementation constraint chosen by the product**.

### 8.3. Scope Mapping Must Be Grounded in Source Authority

If the source token has `orders.read` and the target token needs `inventory.stock.read`, differing scope names do not mean exchange must be rejected; the organization can allow an **approved mapping**. However, never take the requested scope from the request and issue it directly. Rules must consider subject, actor, target, and source authority.

```text
Client: orders-service
Input:  subject token has orders.read
Target: inventory-api
Policy: allows mapping to inventory.stock.read when actor is valid
Output: token has only aud=inventory-api, scope=inventory.stock.read
```

**Preventing confused deputy:** a service called on behalf of a user must never turn a narrow user permission into administrative rights on another service.

## 9. Customizing SAS Without Breaking the Default Provider

Spring Authorization Server 1.x exposes `tokenEndpoint().authenticationProviders(...)` to access the provider list. When extra rules must run before issuing a token, you can wrap the default provider with a reviewed target policy.

### 9.1. Example Wrapper Allowing Only One Target

```java
final class SingleTargetExchangeProvider implements AuthenticationProvider {
    private final AuthenticationProvider delegate;

    SingleTargetExchangeProvider(AuthenticationProvider delegate) {
        this.delegate = delegate;
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return OAuth2TokenExchangeAuthenticationToken.class
                .isAssignableFrom(authentication);
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {
        if (!(authentication instanceof OAuth2TokenExchangeAuthenticationToken request)) {
            return null;
        }

        int count = request.getResources().size()
                  + request.getAudiences().size();
        if (count != 1) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_target"));
        }

        // Still invoke the standard provider: do not skip grant and token checks.
        return delegate.authenticate(authentication);
    }
}
```

**Important limitation:** this snippet only **caps the target count**; it does not yet check whether the target is on an allowlist or whether subject/actor may target it. A single `audience=admin-api` would still pass `count == 1`. In production, enforce full trusted policy **before** delegating and ensure the output audience matches.

### 9.2. Registering the Wrapper at the Right Point

```java
OAuth2AuthorizationServerConfigurer as =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(as.getEndpointsMatcher())
    .with(as, server -> server.tokenEndpoint(tokenEndpoint ->
        tokenEndpoint.authenticationProviders(providers -> {
            providers.replaceAll(provider ->
                provider instanceof OAuth2TokenExchangeAuthenticationProvider
                    ? new SingleTargetExchangeProvider(provider)
                    : provider);
        })))
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
```

This snippet illustrates only the **SAS 1.x configuration hook**, not a complete `SecurityFilterChain`. Appending a new provider after the default provider may mean the new provider **never executes**; always verify ordering and all execution paths. On Spring Security 7.x, use the corresponding 7.x Authorization Server configuration API instead of mixing syntaxes.

### 9.3. Do Not Subclass `final` Classes or Discard Validation

`OAuth2TokenExchangeAuthenticationProvider` may be declared `final` per Javadoc; if subclassing is disallowed, use a wrapper/delegate or implement a thoroughly reviewed provider. Never write a provider that merely checks `subject_token != null` and issues a token, as that skips issuer, audience, scope, client binding, token status, and actor authorization.

## 10. Issuing the `aud` Claim on the Access Token

Once a target is approved by a **trusted policy**, the token generator can emit that target into the JWT access token. The `JwtEncodingContext` API provides `getAuthorizationGrant()`, `getClaims()`, and `getTokenType()`.

Illustrative example:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> exchangeAudienceCustomizer(
        ExchangeTargetPolicy policy) {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }
        if (!(context.getAuthorizationGrant()
                instanceof OAuth2TokenExchangeAuthenticationToken request)) {
            return;
        }

        // approvedAudiences() must return the VERIFIED DECISION;
        // never return raw getAudiences() from an unverified request.
        List<String> audiences = policy.approvedAudiences(
                context.getRegisteredClient(), request);
        context.getClaims().audience(audiences);
    };
}
```

`ExchangeTargetPolicy` is a **custom-designed** abstraction, not a built-in SAS class. Ensure the authorization step and the token customizer use the exact same decision to avoid cache/race drift. If other customizers exist, **compose the logic** instead of creating mutually exclusive bean overrides. For opaque tokens, audience can be conveyed via introspection/metadata rather than a direct JWT claim.

**Do not confuse:** setting `aud` on the JWT is the *claim emission* step; it does not prove the request was authorized for that target. Target authorization must happen **before** issuing the token.

### 10.1. Resource Server Must Enforce Audience Validation

Simplified JWT access token for inventory:

```json
{
  "iss": "https://auth.example.com",
  "sub": "alice-sub-17",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "act": {"sub": "orders-service"}
}
```

`inventory-api` verifies signature/issuer, `exp`/`nbf`, `aud=inventory-api`, scope, and resource permissions. `reports-api` **must reject** this token even though it was signed by the same issuer. If APIs check only signature and issuer, a token with the wrong audience can still be misused across services.

## 11. Error Table and Cases That Must Be Rejected

| Scenario | Appropriate error/check | Notes |
| --- | --- | --- |
| Missing `subject_token` or `subject_token_type` | `invalid_request` | Converter/request validation |
| Actor present without `actor_token_type` | `invalid_request` | Pair constraint violated |
| `actor_token_type` present without actor | `invalid_request` | Do not silently ignore the field |
| Relative `resource` or includes fragment | `invalid_request` / corresponding validator error | Format check |
| `resource` or `audience` outside permissions | `invalid_target` | RFC 8693 target error |
| Requesting too many targets | `invalid_target` | Do not issue broad multi-audience grants |
| Disallowed scope | `invalid_scope` | Check against target and policy |
| Client not allowed to use Token Exchange | `unauthorized_client` | `RegisteredClient.authorizationGrantTypes` |
| Invalid client credentials | `invalid_client` | Client authentication |
| Input token invalid signature/expired/untrusted | Grant/token error per version | Do not leak internal reasons |
| Token type unsupported by provider | Error per profile/implementation | Do not assume SAS must issue whatever the RFC mentions |

Exact error codes per token type and issuer depend on your version and provider and must be empirically tested. **Never** replace errors with HTTP 200 and dummy tokens, and never expose raw JWTs or internal policy structures to callers.

## 12. Capability Test Matrix by Version

| Case | Primary input | Expected |
| --- | --- | --- |
| Basic exchange | Client has grant, valid subject | Issues token per profile or defined error |
| Client lacks grant | `authorizationGrantTypes` omits exchange | Rejected |
| Missing subject token | No `subject_token` | Rejected |
| Actor with matching type | Verified and delegated actor | Succeeds **only if** policy supports it |
| Actor missing type | Actor present, no `actor_token_type` | Rejected |
| Extra actor type | No actor, type present | Rejected |
| Actor signed with unknown key | Forged actor token | Rejected |
| Actor from external issuer | Unboarded issuer | Rejected |
| Subject from external issuer | Source token outside trust | Rejected |
| Input wrong audience | Subject token ineligible for exchange context | Rejected |
| No target passed | Missing `resource`/`audience` | Policy-defined default or rejected |
| Valid `resource` | Registered target URI | If supported: proper output audience |
| Invalid `resource` URI | Relative URI or fragment | Rejected |
| Unknown `resource` | URL outside allowlist | Rejected |
| Valid `audience` | `inventory-api` | Output `aud` is the approved target |
| Unknown `audience` | Unauthorized `admin-api` | `invalid_target` / appropriate error |
| Matching `resource` + `audience` | Registered mapping | Accepted only if policy permits |
| Conflicting `resource` + `audience` | Two targets not allowed together | Rejected |
| Multi-audience | Multiple targets, combined scopes | No privilege escalation; rejected under single-target policy |
| Scope escalation | Requests unapproved scope | Rejected |
| Other subject token type | Unsupported ID token / SAML token | Rejected |
| Other requested token type | Requests unissuable type | Rejected |
| JWT output token | Approved audience/actor/scope | Claims match profile |
| Cross-audience Resource Server | Inventory token sent to reports | Reports rejects |
| Input revoked after exchange | Input token revoked after output issued | Output behavior matches documented TTL/revocation rules |
| Logging | Run tests with logging/telemetry enabled | No leakage of raw subject/actor/output tokens |

### 12.1. Recording Results Instead of a Single YES/NO Label

| Capability | Parser | Provider/policy | Output claims | Resource Server | Conclusion |
| --- | --- | --- | --- | --- | --- |
| Same-issuer actor | PASS/FAIL | PASS/FAIL | `act` valid/invalid | Actor check | Supported/Partial/No |
| Cross-issuer actor | PASS/FAIL | PASS/FAIL | Claims valid/invalid | Trust valid/invalid | Supported/Partial/No |
| Single resource | PASS/FAIL | PASS/FAIL | `aud` valid/invalid | Audience check | Supported/Partial/No |
| Logical audience | PASS/FAIL | PASS/FAIL | `aud` valid/invalid | Audience check | Supported/Partial/No |
| Multi-target | PASS/FAIL | PASS/FAIL | No scope escalation | Audience check | Supported/Partial/No |
| Scope mapping | PASS/FAIL | PASS/FAIL | Appropriate scopes | API policy | Supported/Partial/No |

Mark **Supported** only when all relevant layers pass together. If the parser accepts `actor_token` but the provider rejects external-issuer tokens or the output token lacks `act` per contract, record **Partial** or **No**, not full compatibility.

## 13. Common Architectural Mistakes

**Mistake 1 — treating a getter as an end-to-end guarantee.** Having `getAudiences()` does not mean the JWT carries `aud` or that the API validates `aud`.

**Mistake 2 — trusting an actor token because its signature is valid.** A signature only verifies key integrity and origin; it does not prove the actor is authorized by the user/subject.

**Mistake 3 — trusting every external issuer.** Never fetch a JWKS URL from an untrusted token to validate that token; explicit trust onboarding is required.

**Mistake 4 — copying request `audience` into the JWT.** Emit audiences only after policy approval.

**Mistake 5 — checking scopes only in `RegisteredClient`.** Exchange also depends on the source token, actor, target, and scope mapping.

**Mistake 6 — appending a provider at the end and assuming policy runs.** The default provider may handle the request before your new provider is reached. Wrap/replace the right provider and test for bypasses.

**Mistake 7 — forgetting multi-target semantics.** Each target being individually valid does not mean the combined targets and scopes are valid together.

**Mistake 8 — assuming revoking input revokes output.** The RFC does not guarantee tight lifecycle coupling; design it explicitly if needed.

## 14. Scenario Exercise

An AS at `https://auth.example.com` has client `orders-service` and two APIs: `inventory-api` and `reports-api`. An input token representing Alice has `aud=orders-api` and `scope=orders.read`. The client sends:

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=ALICE_TOKEN
subject_token_type=urn:ietf:params:oauth:token-type:access_token
actor_token=ORDERS_SERVICE_TOKEN
actor_token_type=urn:ietf:params:oauth:token-type:access_token
audience=inventory-api
audience=reports-api
scope=inventory.read reports.export
```

The product team wants the service to read inventory on Alice's behalf, and **never** export financial reports.

Answer the following:

1. Which parameters are required, conditional, or optional under RFC 8693?
2. Why can the request above escalate privileges even though every parameter parses cleanly?
3. What must the AS verify across `client_id`, subject token, actor token, and audience?
4. Propose a mapping `orders.read → inventory.read` for the inventory target while rejecting reports.
5. If the actor token is issued by another IdP, what trust prerequisites are mandatory before accepting it?
6. What happens if the output token carries both audiences and the reports API fails to check target or scope?
7. Write six negative test cases covering forged actor, disallowed audience, invalid `resource` URI, scope escalation, and cross-audience replay.

**Hint:** enforce one target per exchange, verify subject/actor and delegation policy, and issue only `aud=inventory-api` with `inventory.read` when approved; never issue report scopes. Resource Servers must validate audience and business permissions. If multi-target is supported, enforce dedicated policies for every target–scope combination.

## 15. Production Readiness Checklist for Token Exchange

1. **Version:** pin Spring Boot/Security/SAS dependencies and verify active converters, providers, and configurer APIs.
2. **Input tokens:** validate `subject_token`, `subject_token_type`, conditional actor/type pairs, issuer, signature/state, expiry, audience, and bindings.
3. **Client:** authenticate via the registered method, require the Token Exchange grant, and verify delegation rights.
4. **Target:** maintain a `resource → audience` registry, reject unknown URIs and unauthorized multi-targets, and prevent SSRF.
5. **Scopes:** prevent privilege escalation; enforce client–subject–actor–target–scope mappings.
6. **Claims:** ensure `aud`, `act`, `iss`, `exp`, and token types match the contract; do not issue long-lived refresh tokens without justification.
7. **Resource Server:** enforce issuer, signature, expiry, audience, and business authorization.
8. **Revocation:** document whether input and output are linked and state revocation SLAs.
9. **Tests:** contract tests across parser, provider, output, and APIs, including negative cases and external issuers.
10. **Operations:** controlled auditing of client/target and correlation IDs; never log raw subject, actor, or issued tokens.

## 16. Official Reference Documentation

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): semantics of actor, resource, audience, scope, `act`, `may_act`, and `invalid_target`.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint and default converters/providers.
- [SAS 1.5.x — `OAuth2TokenExchangeAuthenticationToken` Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html): getters for actor token, resource, audience, and scopes.
- [SAS 1.5.x — `OAuth2TokenExchangeAuthenticationProvider` Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationProvider.html): provider and `Since 1.3` baseline.
- [Spring Security 7.x — Authorization Server Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): token endpoint APIs for the integrated generation.
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): client-side Token Exchange and subject/actor resolvers.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation and audience configuration.
- [Spring Authorization Server issue #1867](https://github.com/spring-projects/spring-authorization-server/issues/1867): historical discussion on external issuers, **not representative of all future versions**.
- [Spring Authorization Server issue #1880](https://github.com/spring-projects/spring-authorization-server/issues/1880): historical discussion on `id_token` in token exchange; always re-verify against your deployed version.

**Key takeaway:** RFC 8693 supports `actor_token`, `resource`, and `audience`, and Spring Authorization Server has included Token Exchange infrastructure since 1.3. However, **parsing parameters does not mean delegation has been verified or that tokens are audience-bound**. Conclude "supported" only after verifying **your exact version, your policy, the emitted output claims, and Resource Server enforcement**.
