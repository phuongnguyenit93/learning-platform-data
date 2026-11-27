# Verifying the Subject Token, Token State, and Token Exchange Policy

> **Chapter: Token Exchange.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module: designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. The goal is to understand **why a valid subject token alone is not enough to perform an exchange**, how to verify token state and client/actor bindings, and how to enforce **audience, resource, scope, tenant, and delegation** policies before issuing a new token.

## 1. What Problem Does Token Exchange Solve?

OAuth 2.0 Token Exchange (RFC 8693) extends the token endpoint so an OAuth client can present an existing security token (**subject token**) and ask the Authorization Server, acting as a **Security Token Service (STS)**, to issue another token tailored to a new resource target or authorization context.

For example:

- **Authorization Server:** `https://login.example.vn`.
- **User:** `user-123` has logged in and holds an original access token to call `orders-api`.
- **Intermediary service:** `orders-service` is a **confidential OAuth client** that needs to call `reports-api` as part of the same business operation.
- **Target service:** `reports-api` only accepts tokens with audience `reports-api` and permission `reports.read`.
- **Exchanging client ID:** `orders-service`, authenticated at the token endpoint; **not** automatically the user inside the subject token.

If the original access token is forwarded directly to `reports-api`, the target resource should reject it because `aud` does not match. Token Exchange enables the AS to **evaluate policy** and issue a new access token, for example with `aud=reports-api` and a narrowed `reports.read` permission.

**Token Exchange is NOT:**

1. **Refresh Token grant:** renews credentials for the same authorization rather than transforming trust context/targets.
2. **Client Credentials grant:** issues permissions under the client's own identity without relying on a subject token representing another party.
3. **Forwarding the original access token unchanged:** risks *confused deputy* issues and tokens being accepted at the wrong audience.
4. **Automatic privilege escalation:** having broad scopes in the source token or an admin user role does not obligate the AS to grant elevated scopes.
5. **Default ID Token exchange:** an ID Token is used by an RP to verify login and must not be treated as an access token for API privilege exchange.

A secure system issues a new token only after **two independent steps**: (1) authenticating and verifying the input token; (2) determining whether the client, subject, and target **are permitted to exchange** under policy.

### 1.1. Parties and Trust Boundaries

| Component | Role | What must NOT be assumed |
|---|---|---|
| **Authenticated exchanging client** | Client sending the token request and authenticating itself, e.g., `orders-service` | Holding a valid client secret **does not grant permission** to act for every user |
| **Subject token** | Evidence of the subject being represented, e.g., `user-123` | A valid JWT signature **does not prove** the client is allowed to exchange the token |
| **Actor token** (if present) | Evidence of the entity acting on behalf of the subject | Having an actor token does not automatically grant delegation rights |
| **Authorization Server / STS** | Verifies tokens, evaluates policy, and issues new tokens | Never trust unverified claims, self-asserted target URIs, or roles copied from input |
| **Target Resource Server** | Accepts only tokens with matching audience/issuer/permissions and checks business rules | Never accept tokens meant for another service just because they share the same issuer |

### 1.2. Basic Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    participant User as User
    participant Orders as orders-service (OAuth client)
    participant AS as Authorization Server / STS
    participant Store as Authorization/token store
    participant Reports as reports-api

    User->>Orders: Request report generation, sending original access token S0
    Orders->>Orders: Validate API request, verify business operation is valid
    Orders->>AS: POST /oauth2/token, client auth<br/>grant_type=token-exchange, subject_token=S0,<br/>audience=reports-api, scope=reports.read
    AS->>AS: Authenticate orders-service, check registered grant
    AS->>Store: Look up S0 and authorization state
    Store-->>AS: Subject, issuer, scopes, expiry, revoked/active
    AS->>AS: Check token type, state, client/tenant,<br/>target, scope, delegation, and policy
    alt Valid and permitted to exchange
        AS-->>Orders: Access token T1 with aud=reports-api
        Orders->>Reports: Authorization: Bearer T1
        Reports->>Reports: Verify signature/iss/aud/exp/scope
        Reports-->>Orders: Report within permitted scope
    else Invalid token or denied by policy
        AS-->>Orders: OAuth2 error, do not issue T1
    end
```

## 2. RFC 8693 Contract: Request, Response, and Token Types

Token Exchange uses the existing token endpoint, typically `POST /oauth2/token` over TLS, with an `application/x-www-form-urlencoded` body and an **authenticated OAuth client** per AS policy.

### 2.1. HTTP Request Example

```http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Authorization: Basic REDACTED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&subject_token=SUBJECT_ACCESS_TOKEN_REDACTED&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&audience=reports-api&scope=reports.read
```

Uppercase strings are **placeholders**, not real credentials. `Authorization: Basic` is only an example of a confidential client using `client_secret_basic`; clients registered with `private_key_jwt` or another method must authenticate accordingly. **Never** put subject tokens in query URLs or request logs.

| RFC 8693 parameter | Required? | Role |
|---|---|---|
| `grant_type` | Yes | Exactly `urn:ietf:params:oauth:grant-type:token-exchange` |
| `subject_token` | Yes | Token representing the subject on whose behalf the request asks for a token |
| `subject_token_type` | Yes | Source security token type, e.g., `urn:ietf:params:oauth:token-type:access_token` |
| `requested_token_type` | Optional | Desired output token type; if omitted, the AS chooses per policy |
| `resource` | Optional per spec | Absolute URI of the target resource; repeatable if profile allows |
| `audience` | Optional per spec | Logical name of the target service, e.g., `reports-api`; repeatable per spec |
| `scope` | Optional | Desired scopes **in the target context**, not automatically inherited from source |
| `actor_token` | Optional | Token representing the party acting on behalf of the subject |
| `actor_token_type` | Required **when `actor_token` is present** | Indicates the actor token type; must not be sent without `actor_token` |

An organization can enforce a policy **requiring exactly one approved audience/resource** even though the RFC permits multiple. That avoids minting tokens usable across too many services. If multiple targets must be supported, the AS should evaluate permissions for **each `(scope, target)` pair**, not blindly merge audiences.

### 2.2. Token Type URNs Differ from Token Format

- `urn:ietf:params:oauth:token-type:access_token` means **an OAuth access token**; it does not assert the content is a JWT.
- `urn:ietf:params:oauth:token-type:jwt` indicates JWT form; a syntactically valid JWT must still satisfy **semantics and policy**.
- `urn:ietf:params:oauth:token-type:id_token` must not be used as an API access token just because it is also a JWT.
- `urn:ietf:params:oauth:token-type:refresh_token` has a different lifecycle and usage; never treat it as a subject access token unless explicitly defined.
- An opaque access token may require `OAuth2AuthorizationService` lookup or introspection; do not try to parse it as a JWT.

**Never let the caller-supplied `subject_token_type` select an untrusted validation path.** It is a declared claim that must match the **verified token type**. Wrong or disallowed types must be rejected, never falling back to weaker checks.

### 2.3. Successful Response

```json
{
  "access_token": "ISSUED_ACCESS_TOKEN_REDACTED",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
```

`issued_token_type` describes the token **issued in the response**, not the input subject token type. `token_type` such as `Bearer` specifies how to present the token to a resource, not whether it is JWT or opaque. `refresh_token` **does not appear by default** in Token Exchange; RFC 8693 allows it under explicit policies, though short-lived access tokens are normally preferred.

## 3. Verifying the Subject Token: More Than Decoding a JWT

A JWT having three base64url segments or decoding into claims only proves **format**, not that it came from a trusted source, is unexpired, unrevoked, or eligible for exchange.

### 3.1. Eight Verification Groups Before Considering Issuance

| Check group | Condition to satisfy | If skipped |
|---|---|---|
| **1. Token type** | `subject_token_type` is within the AS's supported profile; actual token matches that type | Confuses ID Token / refresh token / client assertion with an access token |
| **2. Trust source** | `iss` is on an explicit allowlist/trust anchor; never dynamically add input issuers to the trust store | Trusts tokens signed by an attacker's key |
| **3. Cryptography/lookup** | JWT signature, `alg`, `kid`, and trusted JWK match policy; opaque tokens checked via trusted store/introspection | Accepts forged or unissued tokens |
| **4. Time validity** | `exp` not expired; `nbf` valid; `iat`/TTL/clock skew within policy | Exchanges expired or not-yet-valid tokens |
| **5. Status** | Not revoked, not invalidated, authorization still active; active status read from authoritative source | "Launders" revoked tokens into fresh tokens |
| **6. Audience & scope** | Original `aud`/resource context matches an acceptable source, subject scopes were granted, subject may request target transition | Exchanges tokens from unrelated APIs and escalates privileges |
| **7. Client/tenant binding** | Exchanging client is permitted to use the subject under relationship, tenant, and sender-binding rules | Client A exchanges tokens of user/tenant/client B |
| **8. Target policy** | Target is permitted, scopes narrowed, roles/consent/actor satisfy policy | Issues tokens for unapproved targets |

**Note on source audience:** Not every token exchange preserves the subject token's `aud` in the output; changing audience is often the primary goal. However, **the source token must be intended to be presentable to that STS/service chain** or explicitly approved by policy. A token issued solely for one Resource Server should not automatically be accepted at every STS just because they share an issuer.

### 3.2. Example JWT Subject Token

An original access token may carry claims such as:

```json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "portal-web",
  "scope": "orders.read reports.read",
  "iat": 1794790000,
  "exp": 1794790300,
  "jti": "source-token-identifier",
  "tenant_id": "tenant-a"
}
```

This is only an **illustrative JSON payload**, not a signed JWT. Before using any claim in policy decisions:

1. Verify signature, issuer, algorithm, and key against a trusted source.
2. Verify token type and timestamps together with runtime status.
3. Evaluate policy for `orders-service` representing `user-123` in `tenant-a`.
4. Verify that target `reports-api` permits `reports.read` for this business scenario.
5. If approved, mint a **new JWT signed by the AS** with `aud=reports-api` and appropriate permissions—never merely edit the old payload and re-serialize it.

**A valid signature does not mean the token is still active.** A self-contained JWT can still pass signature verification even after privileges were revoked or the user was disabled in the backend. You need a status-checking strategy matched to your risk level.

### 3.3. Self-Contained JWTs, Opaque Tokens, and External Tokens

| Input form | Appropriate verification | Limitations to watch |
|---|---|---|
| JWT issued by **the AS itself**, with stored authorization | Verify metadata, query `OAuth2AuthorizationService`, check `token.isActive()`, claims, and policy | Decoding the JWT alone does not replace state lookup if your architecture promises revocation |
| Opaque access token issued by the AS | Exact lookup in the authorization store or trusted introspection | No JWT header/claims to parse locally |
| JWT from an **external issuer** | Requires federation/trust registry checking issuer/signature/audience/claims and status per profile; may use introspection or dedicated trust linkage | **Do not** assume Spring's default provider accepts arbitrary external JWTs |
| SAML assertion / other token types | Requires a profile-specific validator/token translator | Never change the type URN expecting the framework to support it automatically |

For external JWTs, a `JwtDecoder` for an arbitrary issuer is **not** enough for an STS: you must define **which issuers are trusted, which audiences are eligible for exchange, which clients may present them, and what authorization relationships apply**. Fetching JWKS must also be hardened against SSRF and key substitution.

## 4. Token States: Active, Expired, Revoked, Invalidated, Unknown

An OAuth2 token can be structurally intact yet **no longer valid for use**. The AS must distinguish at least:

| State | Meaning | Exchange decision |
|---|---|---|
| **Active** | Token exists, is unexpired, and has not been invalidated in a trusted store | May proceed to **policy evaluation**; does not automatically grant issuance |
| **Expired** | `now ≥ exp` or expired per token store | Reject |
| **Revoked/invalidated** | Owner, client, or admin revoked it; token metadata marked invalid | Reject; issue no new token |
| **Unknown** | Token not found, wrong issuer/store, or introspection failed | **Fail closed**; never pass solely on JWT signature if policy requires lookup |
| **Not yet valid** | `nbf` in the future beyond clock skew | Reject |
| **Actor invalid** | Subject may be active, yet actor token is revoked/expired | Reject delegation request involving that actor |
| **Session/consent changed** | Session, permissions, user, or tenant are no longer valid | Reject or downgrade per policy; never rely indefinitely on stale snapshots |

In Spring Authorization Server, `OAuth2Authorization.Token.isActive()` checks token state at the authorization metadata layer. However, **active does not automatically cover** external policies such as locked user accounts, suspended tenants, expired high-assurance sessions, recently revoked consent, or target audience rules. Evaluate those separately if required.

### 4.1. Token Exchange Does Not Automatically Consume the Subject Token

RFC 8693 states that unless a token type has single-use semantics, **exchanging a token does not invalidate the `subject_token` or `actor_token`**. After exchanging `S0 → T1`, subject token `S0` generally remains valid for its original purpose.

Moreover, RFC 8693 **does not create an automatic tight state linkage** between input and output. If `S0` is revoked later, `T1` does not automatically become invalid across all implementations; you must design **revocation propagation**, introspection, short TTLs, or explicit token lineage when required.

### 4.2. Preventing Races with Logout/Revocation

```mermaid
sequenceDiagram
    autonumber
    participant Client as Exchanging client
    participant AS as Authorization Server
    participant Store as Shared authorization store
    participant Admin as Revoke / Logout service

    Client->>AS: Exchange subject S0
    AS->>Store: Read S0 active
    Admin->>Store: Revoke S0/authorization
    AS->>AS: Evaluating policy from stale snapshot
    Note over AS,Store: Requires proper commit ordering and re-check<br/>before issuing target token
    alt Revocation wins per policy
        AS-->>Client: Reject exchange; issue no new token
    else Valid exchange commits before revocation
        AS-->>Client: Issue T1, persist lineage/audit
        Admin->>Store: Propagate revocation to T1 if policy requires
    end
```

For sensitive operations, define whether **"revoke wins"** or an explicit commit ordering applies. Use transactions/snapshot versions or re-check state close to token issuance. If an external status service is unavailable and policy mandates live status checks, **never** fall back to a stale "looks active" cache entry to mint stronger credentials.

### 4.3. State Caching and Consistency

- Self-contained tokens + offline Resource Server verification: fast, but revocation is not immediate.
- Opaque tokens + introspection: easier centralized state checks, at the cost of network and cache dependencies.
- `OAuth2AuthorizationService` lookup: suited to tokens issued and persisted by the AS; across multiple pods, the store must be durable and consistent.
- TTL-based status caching: if used, quantify the window during which revoked tokens remain accepted; exchanges targeting sensitive services typically need fresher checks.
- For *replay protection* or single-use tokens, maintain consumed state with atomic updates; **standard Token Exchange does not turn every subject token into a one-time token**.

## 5. Exchange Policy: Preventing Privilege Escalation and Confused Deputy

The safe default for production systems is **deny-by-default**, permitting exchange only along explicitly defined relationships: which client, which input token type, which issuer, which subject/tenant, which target, which scopes, what TTL, and what business context.

### 5.1. Illustrative Policy Matrix

| Exchanging client | Subject token | Allowed target | Max output scope | Additional rules |
|---|---|---|---|---|
| `orders-service` | Valid user access token, corporate issuer, `tenant-a` | `reports-api` | `reports.read` | User/tenant active; valid report request; source token carries appropriate authority |
| `billing-service` | Application token of `billing-job` | `invoices-api` | `invoices.read` | Only registered service identity; never exchange into a user token |
| `portal-web` | User access token at RP | **Disallowed** from arbitrary exchange to `admin-api` | N/A | Block escalation even if `portal-web` authenticates cleanly |
| Any client | JWT from untrusted external issuer | Any | N/A | Reject; never bootstrap trust from a URL inside the token |
| `orders-service` | Access token for `tenant-b` user | `reports-api` for `tenant-a` | N/A | Block cross-tenant access |

**Policy cannot simply be `requestedScopes ⊆ registeredClient.getScopes()`.** A client registered with `reports.write` still cannot grant itself that scope if the subject/source authorization and target policy forbid it. Conversely, target scopes may have different names from source scopes; mapping them requires **explicit, reviewed rules**, not naive string matching.

### 5.2. Combining Permission Sets and Context

Let:

- **C:** scopes the exchanging client is permitted to request by registration/policy.
- **S:** permissions from the **verified subject token**, plus live effective permissions/consent.
- **T:** permissions allowed at the target audience for the client→target relationship.
- **R:** scopes requested by the client in the exchange.
- **G:** scopes actually granted in the output token.

When source and target share **the same scope semantics and names**, the core rule is:

```text
R ⊆ C
R ⊆ S
R ⊆ T
G ⊆ R ∩ C ∩ S ∩ T
```

If `S` and `T` use different scope vocabularies (e.g., `orders.read` ↔ `reports.read`), use a **governed mapping** `f(S, resource, actor, businessContext)`. You cannot rely purely on string intersection in all cases—and you must certainly never default to `G = R` just because the client asked.

The output must also establish:
- `iss` of the AS issuing the new token;
- `sub` matching the subject per approved impersonation/delegation;
- `aud` restricted to approved target(s), avoiding unnecessary multi-audience tokens;
- filtered `scope`/roles;
- policy-governed `exp`/TTL, typically short, never extending subject trust past permitted limits;
- actor/delegation details preserved when required by policy so the target API can distinguish the user from the acting service.

### 5.3. Example Java Policy Helper

This is an **illustrative business-policy helper** invoked **after verifying the subject token, client authentication, actor, and active state**. It **does not replace** Spring's `AuthenticationProvider`, JWT decoder, or token endpoint.

```java
import java.util.Set;

record VerifiedExchangeContext(
        String clientId,
        String subjectId,
        String tenantId,
        boolean subjectActive,
        boolean actorAuthorized,
        Set<String> sourceScopes,
        Set<String> requestedScopes,
        Set<String> requestedAudiences) {}

record TargetPolicy(
        String audience,
        String tenantId,
        Set<String> allowedClientIds,
        Set<String> allowedScopes) {}

record ExchangeDecision(String audience, Set<String> grantedScopes) {}

static ExchangeDecision evaluate(
        VerifiedExchangeContext request,
        TargetPolicy target,
        Set<String> registeredClientScopes) {

    if (!request.subjectActive() || !request.actorAuthorized()) {
        throw new SecurityException("Exchange not permitted");
    }
    if (!target.tenantId().equals(request.tenantId())
            || !target.allowedClientIds().contains(request.clientId())) {
        throw new SecurityException("Client or tenant not permitted");
    }

    // Example policy: allow only one registered named target.
    if (!request.requestedAudiences().equals(Set.of(target.audience()))) {
        throw new SecurityException("Invalid target");
    }

    Set<String> requested = request.requestedScopes();
    if (requested.isEmpty()
            || !registeredClientScopes.containsAll(requested)
            || !request.sourceScopes().containsAll(requested)
            || !target.allowedScopes().containsAll(requested)) {
        throw new SecurityException("Scope escalation denied");
    }

    return new ExchangeDecision(target.audience(), Set.copyOf(requested));
}
```

**Code boundaries:**

1. Every field in `VerifiedExchangeContext` must come from an **authenticated client, verified tokens, and trusted policy sources**, never directly from the request body.
2. `actorAuthorized` must be computed from real delegation/impersonation policy (or `true` only when no actor is needed and that exchange mode is approved)—never read as a boolean from client JSON.
3. This helper is **intentionally strict**: source and target permissions must share **the exact same scope names**. To translate across differing scope names, replace that check with a governed mapping tested against privilege escalation.
4. `SecurityException` is only an internal signal for readability; the token endpoint adapter must translate denials into an **appropriate `OAuth2Error`**, never returning stack traces, tenant internals, or tokens to the client.
5. This method **does not yet check source audience, subject/client relationship, account status, TTL, or sender-constraining**. Those conditions must be enforced before calling the helper.

Never run this helper inside a token customizer **after** token issuance has already been approved; policy must block disallowed requests **before generating, persisting, or returning the token**.

## 6. Delegation, Impersonation, and Actor Tokens

RFC 8693 describes two modes:

- **Impersonation:** the output token lets the bearer act as the represented subject. A separate actor does not necessarily appear in the token, creating a high identity-confusion risk without strict policy.
- **Delegation:** an actor acts **on behalf of** the subject. The output may include the `act` claim identifying who is performing the action; target services must distinguish subject and actor in audit and authorization.

Example delegation JWT output (illustrative payload):

```json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["reports-api"],
  "scope": "reports.read",
  "client_id": "orders-service",
  "act": {
    "sub": "orders-service"
  },
  "exp": 1794790300
}
```

- `sub=user-123`: the subject on whose behalf the action occurs.
- `act.sub=orders-service`: the service performing the action.
- `client_id=orders-service`: client identifier per AS issuance profile/claims; check its exact meaning at the Resource Server.
- `aud=reports-api`: target resource audience.
- `scope=reports.read`: permission after downscoping policy.

### 6.1. Validating the Actor Token

If the request includes `actor_token`, RFC 8693 requires `actor_token_type`. The AS must:

1. Verify the actor token's own **type, issuer, signature/lookup, timestamps, and status**.
2. Verify that the current actor is permitted to represent the subject, with matching tenant, ownership, and target relationships.
3. When `may_act` is present in the subject token, treat it as an **authorization signal from a trusted subject-token issuer**, while still checking the actor and policy. Never read `may_act` from an unverified token.
4. Never treat having two "active" tokens as proof of delegation. There must be an explicit **binding** between the two principals.
5. When issuing a delegation output, preserve the necessary actor chain / enforce chain depth limits per policy so audit trails are never lost when required.

### 6.2. What If There Is No Actor Token?

Not every Token Exchange request includes `actor_token`. Some deployments allow **impersonation** based on client identity and an accepted subject token; others require an explicitly authenticated actor. Define policy **per client and use case**; never default to `actor absent ⇒ allow`.

**Do not confuse the authenticated client with the actor token:** client authentication proves who sent the request; the actor token (if present) describes the acting party in delegation. The two identities may match or differ depending on your profile, but should never be conflated blindly.

## 7. Spring Authorization Server: Which Components Verify Tokens?

In Spring Authorization Server 1.5.x, the Token Exchange grant is supported via `OAuth2TokenExchangeAuthenticationConverter` and `OAuth2TokenExchangeAuthenticationProvider` at the token endpoint. The provider uses `OAuth2AuthorizationService` and `OAuth2TokenGenerator`. Other versions—especially Spring Security 7.x with integrated Authorization Server support—must be checked against their respective APIs.

### 7.1. A `RegisteredClient` Permitted for Token Exchange

```java
import java.time.Duration;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

static RegisteredClient exchangingClient(String encodedSecret) {
    return RegisteredClient.withId("registration-orders-service")
            .clientId("orders-service")
            .clientName("Orders Service")
            .clientSecret(encodedSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.TOKEN_EXCHANGE)
            .scope("reports.read")
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .build())
            .build();
}
```

This is a **factory method**; it must be saved into a `RegisteredClientRepository` before use. `encodedSecret` is the **hashed** secret of the confidential client; plaintext is provided only to the legitimate client via a secret manager and TLS. Never use `{noop}secret` in production.

**Important note:** configuring `authorizationGrantType(TOKEN_EXCHANGE)` only permits the grant type; adding `scope("reports.read")` only sets a scope bound **on the registration**. Those two lines **do not automatically define** the `orders-service → reports-api` relationship, tenant policy, or delegation rights. You need a dedicated policy layer as in Section 5.

### 7.2. Token Endpoint Filter Chain

Skeleton configuration for an Authorization Server (Spring Security 6.x / Spring Authorization Server 1.5.x):

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, Customizer.withDefaults())
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
```

Typical imports come from `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer`, and `org.springframework.security.config.Customizer`; `@Order` is from Spring Core.

Beyond the filter chain, the AS needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, a token generator, `AuthorizationServerSettings`, signing keys/`JWKSource` if issuing JWTs, and client authentication infrastructure. Never build a competing `@PostMapping("/oauth2/token")` controller alongside the standard token endpoint filter.

### 7.3. Reading Subject Token State via the Repository

Illustrative Java snippet verifying a **subject access token issued by the AS itself and still stored in the authorization service**:

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2Token;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;

record ActiveSubject(
        OAuth2Authorization authorization,
        OAuth2Authorization.Token<OAuth2Token> token) {}

static ActiveSubject requireActiveSubject(
        OAuth2AuthorizationService service, String rawSubjectToken) {

    OAuth2Authorization authorization = service.findByToken(
            rawSubjectToken, OAuth2TokenType.ACCESS_TOKEN);

    if (authorization == null) {
        throw new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_GRANT));
    }

    OAuth2Authorization.Token<OAuth2Token> token =
            authorization.getToken(rawSubjectToken);

    if (token == null || !token.isActive()) {
        throw new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_GRANT));
    }
    return new ActiveSubject(authorization, token);
}
```

This method is one **step in a pipeline** and must be invoked **inside a trusted server-side provider/validator**. It does not yet verify `subject_token_type`, issuer, source audience, subject/client relationship, tenant, actor, target, scope, or external revocation. Never expose it as a public endpoint that accepts any token and returns authorization metadata.

**Relation to Spring's default behavior:** In Spring's Token Exchange handling, the provider typically queries `OAuth2AuthorizationService.findByToken(..., ACCESS_TOKEN)` and checks `token.isActive()` along with certain type/principal, grant, and scope conditions. This **does not** mean the default provider enforces your organization's full **custom business policy** on audience/resource, client/subject/tenant relationships, token lineage, or trust federation.

### 7.4. Extending Validation Without Disabling Default Checks

`OAuth2TokenEndpointConfigurer` supports `authenticationProviders(...)` to control the `AuthenticationProvider` list handling token grants. In the Spring Authorization Server 1.5.x line, `OAuth2TokenExchangeAuthenticationProvider` is `final`, so do not write `extends OAuth2TokenExchangeAuthenticationProvider` assuming it will compile.

A sound strategy is:

1. Keep Spring's protocol/token handlers or wrap/replace the provider through the official extension point.
2. After client authentication and **before generating and returning a token**, run additional validation from your policy service.
3. The provider/adapter reads the subject authorization via `OAuth2AuthorizationService`, plus actor if present, and evaluates live token state alongside target/scope/client/tenant policy.
4. When policy denies, throw `OAuth2AuthenticationException` with an appropriate OAuth error. **Never** rely solely on checks inside `OAuth2TokenCustomizer` after issuance has begun, as that is not a substitute for an authorization decision.
5. If replacing `OAuth2TokenExchangeAuthenticationProvider`, preserve all required default checks (client auth, grant, token type, active state, actor rules, issuance) and audit every replacement carefully. Simply appending an `AuthenticationProvider` **after** the default provider may leave it unexecuted if the default provider handles the request first.

**There is no generic Spring Boot setting** like `app.token-exchange.allow-any-audience=true` that the framework guarantees safe. Target policy is application logic; it must be deliberately implemented and tested.

### 7.5. Binding Target `aud` to the Issued Token

Token Exchange can transform the source audience into a target audience per policy. When issuing a JWT, ensure `aud` on the **new JWT** comes from the **verified policy decision**, not directly from caller-supplied `audience`/`resource` strings. The Resource Server receiving the new JWT must enforce that specific audience.

In Spring Authorization Server, `OAuth2TokenCustomizer<JwtEncodingContext>` can customize claims in a JWT access token, but **a customizer is not the sole place to authorize exchanges**. Policy must validate the target first; only then should the customizer write the approved audience/scope/actor into the token.

**Pseudocode** illustrating the order of operations:

```text
validateClientAuthentication()
validateGrantTypeIsRegistered(TOKEN_EXCHANGE)
subject = verifySubjectTokenAndLiveStatus()
actor   = verifyActorTokenIfPresent()
decision = exchangePolicy.authorize(
    authenticatedClient, subject, actor,
    requestedAudience, requestedResource, requestedScopes)
# If denied: OAuth2 error and NEVER invoke token generator.
accessToken = tokenGenerator.issue(
    sub=decision.subject,
    aud=decision.target,
    scopes=decision.scopes,
    actor=decision.actor,
    expiresAt=decision.expiry)
saveAuthorizationAndAudit(accessToken, subject, policyDecision)
respond(accessToken)
```

## 8. Never Confuse "Active" with "Permitted to Exchange"

Split the workflow into two explicit layers:

### Layer A — **Validation** (Is the token genuine and still usable?)

- Valid token type, trusted source, algorithm, and signature or lookup.
- Unexpired, unrevoked, and not invalidated.
- Claims `iss`, `aud`/context, `sub`, `jti`, and metadata verified for the token type.
- Token exists in the required authorization store or passes introspection.
- Satisfies sender binding (DPoP/mTLS) or one-time semantics where applicable.
- Actor token independently validated if present.

### Layer B — **Authorization Policy** (What is it permitted to exchange into?)

- Exchanging client is registered for Token Exchange and authenticated properly.
- Client is authorized to represent **that subject**, in that tenant, for that business action.
- Target resource/audience is registered and trusted.
- Output scopes/roles comply with policy; cross-context mappings are explicit.
- Actor is permitted to act for the subject; `act` is recorded when needed for audit.
- TTL and revocation propagation satisfy security goals.
- Result is persisted properly for auditing and revocation.

An **active subject token** belonging to a user with `orders.read`, where `orders-service` requests `aud=payroll-api` with `salary.write`, must be **rejected**. That is not a signature or expiry error; it is a **policy violation**.

## 9. External Tokens, Cross-Tenant Access, and Sender-Constrained Tokens

### 9.1. When the Subject Token Is Issued by Another AS

A request with `subject_token=EXTERNAL_JWT` is not automatically handled by Spring Authorization Server the same way as a token it issued itself. In a standard `OAuth2AuthorizationService` store, an external JWT will **have no matching local authorization record**.

If federation/token translation is required, design it explicitly:

1. A trust registry mapping `issuer → JWKS/introspection URL → allowed audiences/clients/tenants`.
2. Accept only onboarded issuers, hardening metadata and public JWKS fetches against SSRF with redirect/DNS/egress controls.
3. Verify signature and token type per profile; perform controlled user/account mapping.
4. Check status/revocation via that issuer's actual mechanism (if required); define failure modes when the issuer is unreachable.
5. Map subject, tenant, actor, scopes, audience, and TTL according to **governed policy**—never treating raw external claims directly as internal privileges.
6. Record provenance/audit data distinguishing internally issued tokens from externally translated ones.

A `JwtDecoder` successfully decoding an external token **does not** replace these policy decisions.

### 9.2. Cross-Tenant Isolation

- Never merge two users sharing the same `sub` across two issuers or tenants into one internal identity without verified mapping.
- Key subject identities by `issuer + sub + tenant` in identity mappings.
- An exchanging client authorized for `tenant-a` must never exchange a `tenant-b` token for a `tenant-a` audience.
- Partition authorization, policy, and introspection caches by issuer/client/tenant; never cache an "active" result by `jti` alone unless `jti` is globally unique.
- Never log raw emails or tokens to debug tenant errors; use correlation IDs and access-controlled audit logs.

### 9.3. DPoP- or mTLS-Bound Subject Tokens

A sender-constrained subject token carrying a `cnf`/binding key or certificate must be verified under the corresponding **proof-of-possession** rules. Never validate only the bearer JWT signature and exchange it into an unbound target token, which accidentally **strips sender protection**.

Safe options depending on profile:

- Require the client to present valid proof for the subject token (when mandated by protocol and token source).
- Permit exchange only if policy allows and the target token is also sender-constrained to the new target/actor.
- Reject downgrading a sender-bound token into a broader bearer token without an explicitly approved use case.
- Verify DPoP/mTLS support in **your exact Spring version and extension pipeline**; never assume every binding variant is handled automatically.

## 10. Error Handling: Protocol Errors vs. Policy Errors

RFC 8693 defines OAuth2 token endpoint errors and adds `invalid_target`. Distinguish **RFC requirements** from the **exact error codes returned by a specific framework version**.

| Scenario | Standard meaning | Desired outcome |
|---|---|---|
| Missing `subject_token` or `subject_token_type` | Malformed request | Return `invalid_request`; never leak tokens |
| Invalid or policy-rejected subject/actor token | Under RFC 8693 §2.2.2, the AS **MUST** return `invalid_request`; other codes may appear per profile | **Fail closed**; test exact framework/profile behavior |
| Unsupported target `audience/resource` | Unable or unwilling to issue for target | `invalid_target` is **SHOULD** per RFC 8693 |
| Client authentication fails | Cannot prove exchanging client's identity | `invalid_client` per OAuth2 |
| Client not registered for Token Exchange grant | Grant not permitted for client | `unauthorized_client` |
| Invalid requested scope | Exceeds allowed scopes/permissions | `invalid_scope` or profile error; never grant excess permissions |
| Token not found / expired / revoked in Spring provider | No longer a valid authorization | Some Spring versions return `invalid_grant`; **do not conflate this with RFC 8693's general rule** |
| Policy or external dependency failure | Cannot safely verify required conditions | Fail closed, low-detail valid error, internal alert |

**Example error response**:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_target"
}
```

Never return messages like "token for user-123 in tenant-b exists but was locked at 10:30" to the caller. Use a concise `error_description` that reveals neither user existence/identity nor token contents; detailed diagnostics belong in internal audit logs.

## 11. Special Scenarios Requiring Explicit Design

### 11.1. Exchanging the Same Subject Token Multiple Times

RFC 8693 does not treat subject tokens as single-use by default. If a client submits the same subject token to obtain multiple target tokens, the AS may allow it by policy, provided it enforces:

- rate limiting, quotas, and token fan-out caps;
- auditing by subject/client/actor/target;
- tight TTLs on output tokens;
- revocation/consent checks as required;
- preventing the same source token from spawning unbounded tokens for unapproved targets.

If your business requires one-time exchange, you need **atomic token consumption** and dedicated replay tracking; never assume `Token Exchange` includes this automatically.

### 11.2. Multi-Hop Token Exchange Chains

For example `S0 → T1 → T2`. Each hop may add an actor, change audience, and translate scopes. Constrain:

- maximum delegation/impersonation chain depth and permitted forwarding targets;
- authorized actors at each hop;
- zero "scope inflation" across multi-hop mappings;
- TTL bounded by the source and absolute lifetime policy;
- provenance/actor-chain metadata for auditing;
- downstream token revocation when the source is revoked, if required.

Never trust `T1` as sufficient authority for every target merely because it was signed by the internal AS.

### 11.3. User, Consent, or Tenant Changes Mid-Exchange

If a user is disabled or a tenant suspended after the original token was issued, `isActive()` may only reflect persisted token state. Policy must specify live identity/consent checks at exchange time. When revocation occurs concurrently, enforce transaction/state versioning, commit ordering, and concurrency tests.

### 11.4. New Token Returned, Yet Rejected by the Resource Server

If the output token has the wrong `aud`, policy-violating scopes, or is signed with an unpublished key, the bug **is not necessarily in the subject token**. Check:

- issuer metadata and JWKS of the AS issuing the new token;
- actual token claims emitted after generators/customizers;
- whether `audience/resource` passed policy and mapped accurately;
- Resource Server verification of `iss/aud/exp/signature/scope`;
- token type, `act` delegation claim, and target API policy.

Never "fix" the Resource Server by disabling audience checks just to make Token Exchange succeed.

## 12. Testing: Both Token State and Exchange Policy

Integration tests should create **test clients and subject tokens** in the AS store, call `/oauth2/token` for real, and verify the output token against a test Resource Server. Never use production tokens. For signed JWTs, test with proper keys and issuer metadata; for opaque tokens, use a store/stub matching the contract.

| # | Test case | Input/variation | Expected |
|---|---|---|---|
| 1 | Happy path | Valid client, active subject, valid target and scope | Issues new token, `aud` matches target, `sub` matches subject per policy |
| 2 | Client lacks grant | `RegisteredClient` omits `TOKEN_EXCHANGE` | Rejects with `unauthorized_client` |
| 3 | Wrong client secret | Token request fails client auth | Rejects with `invalid_client` |
| 4 | Missing subject | Missing `subject_token` or type | `invalid_request` |
| 5 | Unknown subject | Token absent from trusted store | No output issued |
| 6 | Expired subject | `exp` in the past | No output issued |
| 7 | Revoked subject | Token metadata invalidated/revoked | No output issued |
| 8 | Not-yet-valid subject | `nbf` in future beyond skew | No output issued |
| 9 | Wrong subject type | ID Token / refresh token sent as `access_token` | Rejected; never auto-coerced |
| 10 | Invalid JWT signature | Altered payload/`kid`/`alg` | No output issued |
| 11 | Untrusted external JWT issuer | Validly signed JWT from unlisted issuer | No output issued |
| 12 | Invalid actor token | Expired/revoked actor or wrong type | No output issued |
| 13 | Unauthorized actor | Active actor not authorized by subject/policy | No output issued |
| 14 | Missing required actor | `actor_token` omitted when policy requires it | No output issued |
| 15 | Disallowed target | `audience=payroll-api` | `invalid_target` / policy error |
| 16 | Overly broad multi-audience | Sends `audience` for two unapproved APIs | Rejected instead of minting broad multi-audience token |
| 17 | Scope escalation | Source has `reports.read`, requests `reports.write` | Higher scope denied |
| 18 | Client has scope, subject lacks it | `RegisteredClient` has `reports.write`, subject does not | Denied; registration scope alone is insufficient |
| 19 | Invalid scope translation | Differing source/target scope names with no mapping | No unauthorized escalation/conversion |
| 20 | Cross-tenant | User in tenant B, target in tenant A | No output issued |
| 21 | Subject state change | Revoke/logout between lookup and issuance | No issuance after revoke per policy; concurrency tested |
| 22 | Output token claims | Inspect output JWT | `iss/aud/sub/scope/exp/act` match policy |
| 23 | Input remains active | One successful exchange | Subject not auto-invalidated (unless custom policy) |
| 24 | Output revocation propagation | Revoke subject after exchange | Output behaves per design (do not assume auto-revoke) |
| 25 | Sender-constrained input | DPoP/mTLS-bound token missing valid proof | Prevent laundering into a broader bearer token |
| 26 | Opaque subject | Lookup/introspection of active token | Policy evaluated cleanly; not parsed as a fake JWT |
| 27 | Foreign JWT | Trust registry/validator enabled per allowed profile | Accepts only approved issuer/client/tenant/target |
| 28 | Multi-pod | AS nodes A and B share authorization state | Consistent policy and revocation state |
| 29 | Load/abuse | High volume of exchanges on same subject | Rate limit/alert/quota enforced without leaking tokens |
| 30 | Error leakage | Bad token/tenant/target | Response leaks no tokens/users/secrets in body or logs |

### 12.1. Pure-Java Policy Test Example

The following unit test illustrates **only** the scope, target, client, and tenant policy from Section 5.3:

```java
@Test
void deniesScopeEscalationEvenIfClientRegisteredForIt() {
    VerifiedExchangeContext ctx = new VerifiedExchangeContext(
            "orders-service",
            "user-123",
            "tenant-a",
            true,
            true,
            Set.of("reports.read"),  // Subject only has read permission.
            Set.of("reports.write"), // Client requests write permission.
            Set.of("reports-api"));

    TargetPolicy policy = new TargetPolicy(
            "reports-api",
            "tenant-a",
            Set.of("orders-service"),
            Set.of("reports.read", "reports.write"));

    assertThrows(SecurityException.class, () ->
            evaluate(ctx, policy,
                    Set.of("reports.read", "reports.write")));
}
```

Add JUnit 5 imports and place the helper/records in the appropriate test class or package. **This test does not yet verify JWT signatures, client authentication, the authorization service, or the token endpoint**; add integration tests for all of those. A single `assertThrows` on a helper is not enough to declare the system secure.

### 12.2. Verifying Output with a Test Client

After calling the token endpoint in tests, verify:

1. HTTP status and `issued_token_type`.
2. `scope` does not exceed policy.
3. The output JWT signature is verified before reading claims; `aud` contains only approved targets.
4. `sub` was not replaced by the service identity when delegating for a user, unless an explicit impersonation policy requires it.
5. The `act` claim is emitted and validated accurately when the profile requires delegation.
6. `exp`/TTL does not accidentally over-extend privileges.
7. The target Resource Server accepts the token, while a **non-target** Resource Server rejects a validly signed token with the wrong audience.

Use synthetic test user/subject tokens; never capture raw token values or `Authorization` headers in snapshots or logs.

## 13. Troubleshooting and Runbook

| Symptom | Cause to investigate | Remediation |
|---|---|---|
| `unauthorized_client` on exchange | `RegisteredClient` lacks `TOKEN_EXCHANGE` | Check client provisioning, grant types, least privilege |
| `invalid_client` | Confidential client authentication failure | Check client secret hash, method, `private_key_jwt`/mTLS; never log credentials |
| Signed JWT looks "valid" yet AS rejects it | Signature exists, but authorization record is missing or token type/policy fails | Distinguish local token lookup vs. external federation |
| Subject expired/revoked | `isActive() == false` or live status failed | Reject and require a fresh valid token via a supported grant |
| Actor rejected | Bad `actor_token`, `may_act` mismatch, or missing policy | Check delegation relationship, issuer, claims, and token state |
| `invalid_target` | Target outside allowlist or overly broad multi-audience request | Check target policy and resource/audience semantics |
| Output token has overly broad scopes | Relied solely on `RegisteredClient.getScopes()` without bounding by subject/target | Enforce policy before issuance and verify claims post-generator |
| Target API returns 401 | Wrong output `iss/aud/signature/exp` | Compare token claims, JWKS, issuer, and Resource Server config |
| Target API returns 403 | Insufficient scope or business authorization | Check target permissions, actor/subject, mappings, and API policy |
| Subject revoked yet output still calls API | No linkage/revocation propagation; offline JWT | Short TTLs, token lineage/revocation strategy, API status checks |
| Client A exchanges tenant B's token | Policy missing binding or tenant cache bleed | Partition caches, verify principal+issuer+tenant, audit logs |
| Token exchange intermittent after scale-out | Token store / revocation cache not shared across AS pods | Shared persistence and consistency; verify session/authorization store |
| External issuer JWKS fetch error | DNS/TLS/network/trust configuration | Fail closed; never relax trust to uncontrolled URLs |
| Actor missing downstream | Token generator/customizer dropped `act` | End-to-end tests for delegation policy and claim mapping |

### 13.1. Operational Observability Without Leaking Tokens

Useful metrics include:

- `token_exchange_requests_total{outcome,client_class,target_class}`;
- `token_exchange_rejected_total{reason}`, categorized as `invalid_subject`/`invalid_actor`/`invalid_target`/`scope_policy`/`tenant_policy`;
- `token_exchange_latency_seconds` and `token_exchange_subject_lookup_latency_seconds`;
- `token_exchange_external_introspection_failures_total` when federated;
- `token_exchange_revocation_conflict_total` and `token_exchange_output_revoked_total` when tracking lineage.

Never use raw `subject_token`, `actor_token`, client secrets, user IDs/emails, raw `jti`, or `Authorization` headers as **metric labels**. Logs should contain only correlation IDs, policy-safe client IDs, target categories, denial codes, timestamps, and protected audit data; enforce log retention and access controls.

### 13.2. Runbook When Exchange Denial Rate Spikes

1. Check recent deployments of policies, client registrations, or token-format changes; compare against the running Spring version.
2. Categorize errors: client auth, unknown/expired/revoked subject, invalid actor, target/scope/tenant policy, or dependency failure.
3. Verify `OAuth2AuthorizationService` holds records for the source token without cross-instance staleness. For external tokens, check the trust registry and introspection/JWKS.
4. Compare issuer, audience, scope, client identity, and delegated actor using **masked metadata**; never paste raw JWTs into tickets.
5. If a new policy caused the issue, fix the mapping/provisioning through an approved workflow; **never** enable "allow any audience" or bypass `isActive()`.
6. If replay/abuse is suspected, rate-limit, revoke affected tokens, evaluate already-issued output tokens, and audit.
7. Reproduce in staging with synthetic tokens, verifying both valid requests and negative cases before rolling out.

## 14. Production Checklist and Self-Check Questions

- [ ] Only authenticated clients with `TOKEN_EXCHANGE` in `RegisteredClient` enter the exchange flow.
- [ ] Exchanging client, subject, and actor identities are clearly separated; a valid client secret is never equated with permission to represent all users.
- [ ] `subject_token` and `subject_token_type` are present and allowlisted; ID Tokens/refresh tokens are never treated as access tokens.
- [ ] Subject and actor tokens (if any) are verified for issuer/key trust, type, timestamps, status, revocation, and sender binding.
- [ ] For AS-issued tokens, `OAuth2AuthorizationService` returns a trusted authorization and `token.isActive()`; external tokens use a dedicated trust registry/validator.
- [ ] Client→subject/tenant→target/audience→scope rules are explicitly defined and **deny by default**.
- [ ] `audience/resource` is evaluated prior to issuance, with target count caps and fan-out controls.
- [ ] Scopes never exceed permissions allowed by source, target, and client policies; cross-vocabulary scope mappings are reviewed.
- [ ] `act`/`may_act` and delegation chains have explicit rules, validation, and auditing.
- [ ] Output tokens carry policy-compliant `iss`, `aud`, `sub`, `scope`, `exp`, and `act`; Resource Servers enforce authorization independently.
- [ ] A strategy exists for post-exchange source revocation: short TTLs, lineage, introspection/propagation matched to risk.
- [ ] Sender-constraining is never stripped during exchange or downgraded into a broader bearer target.
- [ ] Raw tokens are never logged, and unverified token URLs/headers never drive JWKS or target lookups.
- [ ] Multi-node persistence/caching is consistent, and race conditions with revoke/logout are tested.
- [ ] Integration tests cover subject failures, actor failures, wrong issuers, cross-tenant attempts, scope escalation, invalid targets, and output JWT claims.
- [ ] Error responses leak no sensitive data, and observability includes auditing and rate limiting.

**Self-Check Questions**

1. Can a JWT with a valid signature still be used as a subject token if `OAuth2AuthorizationService` reports it has been revoked?
2. Why is successful client authentication different from permitting the client to act on behalf of a subject?
3. How do `subject_token_type=access_token` and `subject_token_type=jwt` differ?
4. Why might a source token with `aud=orders-api` be allowed to exchange into `aud=reports-api`, yet require extra policy?
5. When both `RegisteredClient` and the target allow `reports.write`, but the subject only holds `reports.read`, how should the AS handle a request for `reports.write`?
6. Which aspects of delegation do `act` and `may_act` represent?
7. If `subject_token` is revoked after a successful exchange, is the new token automatically revoked under RFC 8693?
8. Does Spring Authorization Server's default provider automatically federate arbitrary JWTs from external issuers?
9. Why must policy run **before** the token generator rather than simply injecting audience claims in a customizer?
10. What tests would you design to prevent cross-tenant exchange and token laundering of a DPoP-bound token?

## References

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): request/response, subject/actor validation, impersonation/delegation, audience/resource/scope, token lifecycle, and errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client authentication, scopes, and error responses.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token misuse, limiting privilege escalation, and security controls.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): verifying token state via introspection.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation and token lifecycle bounds.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims and format.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constraining with proof keys.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): certificate binding.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenEndpointConfigurer`, `OAuth2TokenExchangeAuthenticationConverter`, and default providers.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, and `OAuth2AuthorizationService`.
- [Spring Authorization Server — `OAuth2TokenExchangeAuthenticationProvider` API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationProvider.html): provider for the Token Exchange grant.
- [Spring Authorization Server — `OAuth2TokenExchangeAuthenticationToken` API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html): subject/actor, resource/audience/scope parameters.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Token Exchange OAuth2 Client provider and selecting subject/actor tokens when calling the grant.
