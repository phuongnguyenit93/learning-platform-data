# Test Matrix for Token Types, Trust Sources, Endpoints, and Expected Outcomes

## 1. Purpose of the Matrix

A **Spring Security OAuth 2.0/OIDC Resource Server** may support multiple authentication methods in the same system: locally verified JWT access tokens, opaque tokens checked via introspection, tokens issued by multiple issuers, and even other mechanisms such as mTLS or sessions for dedicated endpoint zones. In that environment, a single test like "valid Bearer returns 200" does not sufficiently protect the system.

Security bugs usually hide at **the intersections**:

- A JWT has a valid signature yet **was issued for a different API**.
- A token from issuer A is sent to an endpoint that only trusts issuer B.
- An opaque token is active at the Authorization Server yet **is not intended for the current Resource Server**.
- An OIDC **ID token** is mistakenly used as an OAuth **access token**.
- A JWT with an invalid signature is retried with another authentication manager and unexpectedly accepted.
- A business endpoint is accidentally placed in a `SecurityFilterChain` using the wrong mechanism.
- Authentication succeeds with the right scope, yet accesses **another tenant's/owner's data**.
- Tests use mock principals and pass green while real JWKS loading or introspection is broken.

A **test matrix** puts all those dimensions side by side:

```text
Credential type
   × issuer / key source / introspection trust
   × endpoint / SecurityFilterChain / resource audience
   × token state / claims / scopes / data
   → expected outcome (HTTP + security impact + evidence)
```

Example concrete requirement:

> "A JWT access token signed by issuer A, `aud=orders-api`, with `orders:read`, sent to `GET /api/v2/orders` must succeed; the same token sent to `/api/legacy/orders` accepting only opaque tokens must be rejected unless the introspection contract permits it. A JWT signed by issuer B asserting `iss=A` must not pass decoder A."

This is a **verifiable security contract**, not just a list of HTTP status codes.

## 2. Boundaries to Separate: Authentication, Authorization, and Trust Sources

A 2xx result is safe only when **all three questions** are answered properly:

| Step | Question | Example mechanisms |
| --- | --- | --- |
| **Authentication** | Is the credential valid under a trust source accepted by the API? | JWT signature/JWKS/`iss`/`aud`/`exp`, opaque introspection `active`. |
| **Functional authorization** | Does the principal have permission to perform the operation? | `hasAuthority("SCOPE_orders:read")`, role or permission contract. |
| **Object/tenant authorization** | Does the principal have access to the specific record/tenant requested? | Query `WHERE tenant_id = ... AND owner_id = ...`, policy bean, RLS. |

A **trust source** is not wherever the client wants the token verified. It is **configuration approved by the Resource Server**, such as:

- An exact issuer paired with its JWKS URL or matching public key.
- A fixed OAuth 2.0 introspection endpoint with client authentication issued to the Resource Server.
- A trusted CA/SAN certificate set for mTLS.
- A session store and security configuration dedicated to the browser application.

Conversely, values such as `iss`, `kid`, `jku`, `x5u`, or `X-Token-Type` read from an **unverified** token/header must never dynamically add new trust sources.

## 3. Sample System for Building the Matrix

Suppose an **Orders Platform** has the following endpoint zones. Issuers, resources, and tokens in this article are **illustrative dummy data for learning**.

| Endpoint group | Expected mechanism | Trust source | Audience / resource | Permissions |
| --- | --- | --- | --- | --- |
| `GET /api/v2/orders/**` | JWT Bearer | Issuer A `https://login-a.example.test/realms/shop` | `orders-api` | `SCOPE_orders:read` |
| `POST /api/v2/orders/**` | JWT Bearer | Issuer A | `orders-api` | `SCOPE_orders:write` |
| `GET /api/legacy/orders/**` | Opaque Bearer | AS B introspection `https://login-b.example.test/oauth2/introspect` | `orders-legacy-api` per contract | `SCOPE_legacy:read` |
| `POST /api/legacy/orders/**` | Opaque Bearer | AS B introspection | `orders-legacy-api` | `SCOPE_legacy:write` |
| `GET /api/internal/reports/**` | Machine-to-machine JWT | Issuer C `https://workload-idp.example.test/issuer` | `reports-api` | `SCOPE_reports:read` + workload policy |
| `GET /public/status` | Public | No access token required | Not applicable | Public, exposes no internals |
| Remaining `/api/**` | Undeclared | Accepts no mechanism automatically | Not applicable | Deny by default |

In this example:

1. **JWT A** is a signed access token from issuer A, used for API v2.
2. **Opaque B** is a string that cannot be verified locally; the legacy API checks it via AS B using introspection client credentials.
3. **JWT C** is for services/workloads and reports endpoints, and **must not implicitly** act as a user on the Orders API.
4. API zones may use separate `SecurityFilterChain` beans in Servlet or `SecurityWebFilterChain` beans in WebFlux.
5. A resource path outside all groups must still have an explicit **deny policy**.

**Do not copy this matrix verbatim into production:** actual paths, token sources, and scopes must come from your real OAuth/API contracts. A system may accept JWT and opaque **on the same endpoint**, provided a dedicated selection mechanism is designed rather than relying on trial and error.

### 3.1. Processing Route Diagram

```mermaid
flowchart TD
    REQ["HTTP request"] --> MATCH{"Which zone does endpoint belong to?"}
    MATCH -->|"v2/orders"| JA["JWT A authentication"]
    MATCH -->|"legacy/orders"| OB["Opaque B introspection"]
    MATCH -->|"internal/reports"| JC["JWT C authentication"]
    MATCH -->|"public"| PUB["Public policy"]
    MATCH -->|"Outside routes"| DENY["Default deny / 404 per API"]
    JA --> JVALID["Verify JWS + trusted issuer A + aud=orders-api"]
    JC --> CVALID["Verify JWS + trusted issuer C + aud=reports-api"]
    OB --> OVALID["AS B active=true + resource contract"]
    JVALID --> AUTHZ["Functional + tenant/object authorization"]
    CVALID --> AUTHZ
    OVALID --> AUTHZ
    AUTHZ --> RESULT["2xx / 403 / policy 404"]
    PUB --> RESULT
```

What must be tested is that **the route chooses the right mechanism before authentication**, and then each mechanism trusts only its designated source and resource contract.

## 4. Creating a Catalog of Token Fixtures with Clear Identities

Do not create only two variables `validToken` and `invalidToken`. Fixture names should tell the reader how each differs from a standard token.

| Fixture | Content or state | Used to test |
| --- | --- | --- |
| `J_A_READ` | JWT JWS signed by A; `iss=A`, `aud=orders-api`, has `orders:read`, unexpired. | Positive GET v2. |
| `J_A_WRITE` | Same as above, but with `orders:write`. | Positive POST v2. |
| `J_A_NO_SCOPE` | Valid JWT A, right `aud`, missing required scope. | 403, not 401. |
| `J_A_EXPIRED` | Validly signed JWS A, but `exp` in the past beyond clock skew. | Timestamp validation. |
| `J_A_FUTURE_NBF` | Validly signed JWS A, but `nbf` in the future beyond clock skew. | Not-before validation. |
| `J_A_BAD_AUD` | Validly signed JWS A, but `aud=payments-api`. | Resource binding. |
| `J_A_MISSING_AUD` | Validly signed JWS A, missing `aud` required by contract. | Fail-closed claim policy. |
| `J_A_WRONG_TYP` | Validly signed token, but not the access-token profile accepted by the API. | JWT type/token confusion. |
| `J_B_ISS_A` | JWT payload claims `iss=A` yet is signed by key B. | Never trust unverified `iss`. |
| `J_UNKNOWN_ISS` | JWS issued by unregistered issuer D. | Trusted issuer allowlist. |
| `J_A_TAMPERED` | Payload/signature of `J_A_READ` modified without re-signing. | Signature validation. |
| `J_C_REPORTS` | Valid JWT C, `aud=reports-api`, scope `reports:read`, service actor. | Positive reports endpoint. |
| `J_C_ORDERS_LOOKALIKE` | Valid JWT C carrying claims/scopes resembling an Orders token. | Cross-issuer/resource denial. |
| `O_B_READ` | Opaque token where AS B returns `active=true`, right resource, scope `legacy:read`. | Positive GET legacy. |
| `O_B_WRITE` | Active opaque token B with `legacy:write`. | Positive POST legacy. |
| `O_B_NO_SCOPE` | Active opaque B missing required scope. | 403 legacy. |
| `O_B_INACTIVE` | AS B returns `{"active":false}`. | 401 inactive. |
| `O_B_BAD_AUD` | AS B returns `active=true` yet token audience belongs to another resource. | Resource binding. |
| `O_B_UNKNOWN` | Arbitrary opaque string unrecognized by AS B. | 401 `invalid_token`. |
| `OIDC_ID_A` | OIDC ID token from A, `aud` is the OAuth client ID. | Reject ID token as access token. |
| `REFRESH_A` | OAuth client refresh token; not an access token. | Reject at protected resource. |
| `CLIENT_ASSERTION` | JWT used for confidential client auth with AS. | Reject as API access token. |
| `EMPTY` | Missing `Authorization`. | 401 on protected endpoint. |
| `MALFORMED` | Malformed Bearer header or token format. | 400/401 per resolver and RFC 6750. |

`J_*` fixtures testing cryptographic trust must be signed with **test private keys** and verified against **trusted test public keys**. `O_*` should use a mock introspection endpoint with a clear state table. Never use production keys, production secrets, or real user tokens in tests.

### 4.1. Sample JWT Data

```json
{
  "iss": "https://login-a.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1893452400,
  "exp": 1893456000
}
```

This is purely an **illustrative payload**. Static timestamps can expire or not yet be valid when tests run. In automated tests, generate `iat`, `nbf`, and `exp` from a **fixed Clock** or from test execution time with a safe margin; negative fixtures must deliberately pick timestamps outside clock skew.

### 4.2. Sample Introspection Data

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "sub": "legacy-user-123",
  "aud": ["orders-legacy-api"],
  "scope": "legacy:read",
  "client_id": "legacy-web-client"
}
```

And an inactive token:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
```

**HTTP 200 from an introspection endpoint does not mean the token is active.** Evaluate `active` and metadata per contract. If AS B omits `aud` yet enforces resource binding via introspection client identity, tests must verify **that guarantee**, never filling in audience inside the application.

## 5. Conventions for Evaluating Outcomes: More Than Just HTTP Status

A test case should contain at minimum:

```text
CASE_ID
METHOD + ENDPOINT
TOKEN_FIXTURE / AUTHORIZATION TRANSPORT
EXPECTED_SECURITY_CHAIN
EXPECTED_AUTHENTICATION_SOURCE
EXPECTED_HTTP_STATUS
EXPECTED_BEARER_ERROR (if applicable)
EXPECTED_AUTHORITIES / DATA_SCOPE
EXPECTED_SIDE_EFFECTS
EXPECTED_UPSTREAM_CALLS
```

Example:

```yaml
id: V2-READ-001
request:
  method: GET
  path: /api/v2/orders
  authorization: Bearer J_A_READ
expected:
  chain: jwt-a
  trustSource: issuer-a-jwks
  status: 200
  authorities:
    contains: [SCOPE_orders:read]
  introspectionCalls: 0
  resultTenant: tenant-a-only
```

`J_A_READ` is a **test fixture reference**, not a raw Bearer value. When sending real HTTP requests, the test substitutes the signed test JWT string.

### 5.1. Statuses 400, 401, 403, 404, and 5xx

| Result | Meaning under common contracts | Notes |
| --- | --- | --- |
| **200/201/204** | Authentication and authorization passed; business operation completed. | Depends on endpoint/method; do not assume every positive case is 200. |
| **400 Bad Request** | Malformed Bearer request; `invalid_request` in applicable RFC 6750 scenarios. | Spring resolver and transport policy govern details. |
| **401 Unauthorized** | Missing or rejected credential. | Usually includes `WWW-Authenticate: Bearer`; `invalid_token` for rejected tokens. |
| **403 Forbidden** | Authentication succeeded, but scope/permissions are insufficient. | May include `insufficient_scope`; not every 403 is a missing OAuth scope. |
| **404 Not Found** | Resource does not exist or policy intentionally hides existence. | Needs a consistent contract, revealing nothing about other owners/tenants. |
| **429 Too Many Requests** | Rate-limit from gateway/API or AS if intentionally mapped. | Never turns into "valid token" on retry. |
| **5xx / 503** | Dependency failure such as JWKS/introspection or server error. | Must **fail closed**; exact status depends on handler—never label caller token invalid. |

With a Bearer challenge per **RFC 6750**:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

With a valid token lacking scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

These are typical responses rather than a literal default header across all versions/custom handlers. When no credential is present, a `Bearer realm="orders-api"` challenge **does not need `error="invalid_token"`**.

## 6. Main Matrix: Token Type × Endpoint

Convention: `2xx` denotes success per the endpoint's contract; `401`/`403` follow the authentication and authorization flows in the sample system.

| Token / credential | GET `/api/v2/orders` (JWT A, read) | GET `/api/legacy/orders` (opaque B, read) | GET `/api/internal/reports` (JWT C, read) | Conclusion to verify |
| --- | --- | --- | --- | --- |
| `J_A_READ` | **2xx** | **401** per opaque-B-only contract | **401** | Token A does not open legacy or reports zones. |
| `J_A_WRITE` missing read | **403** | **401** | **401** | Write scope does not imply read unless policy specifies. |
| `J_A_NO_SCOPE` | **403** | **401** | **401** | Valid token, missing functional privilege at v2. |
| `J_A_EXPIRED` | **401** | **401** | **401** | Expired token gets no fallback. |
| `J_A_BAD_AUD` | **401** | **401** | **401** | Same issuer yet wrong resource still rejected. |
| `J_B_ISS_A` | **401** | **401** | **401** | Issuer claim does not prove signature. |
| `J_C_REPORTS` | **401** | **401** | **2xx** | Workload token works only on reports. |
| `J_C_ORDERS_LOOKALIKE` | **401** | **401** | **401/403** per reports token contract | Claims resembling Orders scopes are insufficient. |
| `O_B_READ` | **401** | **2xx** | **401** | Opaque token verified by AS B, never takes JWT path. |
| `O_B_NO_SCOPE` | **401** | **403** | **401** | Active opaque missing functional scope. |
| `O_B_INACTIVE` | **401** | **401** | **401** | `active=false` must be rejected. |
| `O_B_BAD_AUD` | **401** | **401** per resource-binding policy | **401** | Active token does not grant access to every API. |
| `OIDC_ID_A` | **401** | **401** | **401** | ID token is not an API access token. |
| `REFRESH_A` | **401** | **401** | **401** | Refresh token is not used at a Resource Server. |
| `CLIENT_ASSERTION` | **401** | **401** | **401** | Client assertion is not an access token. |
| No Bearer | **401** | **401** | **401** | Protected endpoints require authentication. |

**Conditions of the table:** AS B in this example **does not recognize** JWT A/JWT C/ID tokens/refresh tokens and the legacy policy accepts only opaque B; JWT A decoder and JWT C decoder have separate issuer/audience validators. If a real AS supports introspecting JWT A as active for the legacy endpoint, **define a different contract and update expectations**; Spring does not choose status codes by inspecting format.

### 6.1. Why Can a Validly Signed JWT Return 403 on One Route and 401 on Another?

`J_A_NO_SCOPE` on `GET /api/v2/orders` is signed by issuer A, has the right audience, and is unexpired. It **passes authentication** yet lacks `SCOPE_orders:read`, so it typically returns **403**. The same token on `/api/internal/reports` fails **issuer C / audience reports-api**, so it is rejected **before authorization**: **401**.

Thus, tests must understand **which step failed**, not just compare HTTP status numbers.

### 6.2. Why Doesn't `J_A_WRITE` Automatically Include Read?

OAuth scopes are strings given meaning by **resource policies**, with no automatic hierarchy. `orders:write` does not automatically imply `orders:read`. If an API wants a "write also allows read" rule, write an explicit authorization policy and test it with a dedicated case instead of assuming from scope names.

## 7. Deep Matrix: Trust Source × JWT Token Profile

A JWT is considered valid by the Resource Server when **both signature and claims** conform to the trust profile. The following tests are needed for the JWT A endpoint:

| Case | JWS key source | `iss` in payload | `aud` | Lifetime / profile | Expectation |
| --- | --- | --- | --- | --- | --- |
| JWT-T01 | Test private key A; trusted public key A | A | `orders-api` | Valid | **2xx** if sufficient scope. |
| JWT-T02 | Test private key B | A | `orders-api` | Valid | **401**: never accept key B signature under trust A. |
| JWT-T03 | Test private key A | B | `orders-api` | Valid | **401**: issuer claim mismatch. |
| JWT-T04 | Test private key A | A | `payments-api` | Valid | **401**: wrong audience. |
| JWT-T05 | Test private key A | A | Missing `aud` | Valid | **401** if audience is required. |
| JWT-T06 | Test private key A | A | `orders-api-admin` | Valid | **401**: no substring-matching audience. |
| JWT-T07 | Test private key A | A | `["payments-api", "orders-api"]` | Valid | Per contract: membership may accept; exact-single may reject. |
| JWT-T08 | Test private key A | A | `orders-api` | `exp` in past beyond clock skew | **401**. |
| JWT-T09 | Test private key A | A | `orders-api` | `nbf` in future beyond clock skew | **401**. |
| JWT-T10 | Test private key A | A | `orders-api` | Missing mandatory `exp` | **401** if token profile mandates `exp`. |
| JWT-T11 | JWS payload altered without re-signing | A | `orders-api` | Looks valid | **401**: invalid signature. |
| JWT-T12 | `alg=none` or disallowed algorithm | A | `orders-api` | Looks valid | **401**. |
| JWT-T13 | Validly signed, but `typ`/token profile is ID token | A | Usually OAuth client ID | May be unexpired | **401**. |
| JWT-T14 | Unknown `kid`, not found in trusted keys | A | `orders-api` | Valid | Never create principal when unverifiable. |
| JWT-T15 | `jku`/`x5u` pointing to attacker host | A or forged | `orders-api` | Looks valid | Never fetch/trust arbitrary key sources. |
| JWT-T16 | JWS right issuer A, duplicate/wrong-type claims | A | Per input | Per input | Reject per parser/token-profile contract. |

**How to read this:** `kid` only helps pick a candidate key inside **trusted JWKS**; it never creates trust. An attacker can sign a token with their own key and set `kid` to match key A, yet signature verification against trusted key A must still fail.

### 7.1. Signature Tests Differ from Validator Tests

Both kinds of negative tests must coexist:

```text
INVALID JWS signature + plausible claims -> rejected at JOSE layer.

VALID JWS signature + INVALID exp/iss/aud -> rejected at claim validators.
```

If you test only invalid JWS signatures, a refactor that accidentally drops `JwtTimestampValidator` or the issuer validator could go unnoticed.

### 7.2. Preserving Default Validators

When adding an audience validator to `NimbusJwtDecoder`:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER_A);

OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Access token is not for this resource",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults, audience));
```

`setJwtValidator(...)` replaces the current validator—it **does not automatically append** to the defaults. If you attach only the audience validator, validly signed tokens that are expired or from the wrong issuer may skip essential checks depending on decoder/version.

### 7.3. Issuer and Public-Key Source Must Be Bound Together

A token asserting `iss=A` must never cause the server to invoke:

```java
ReactiveJwtDecoders.fromIssuerLocation(unverifiedIssuer);
```

for arbitrary token-supplied URLs. With multiple issuers, use `JwtIssuerAuthenticationManagerResolver` (Servlet) or `JwtIssuerReactiveAuthenticationManagerResolver` (WebFlux) with a trusted issuer allowlist; the decoder **still must verify issuer and JWS** after routing.

## 8. Deep Matrix: Opaque Tokens and AS Introspection

RFC 7662 requires the Resource Server to be able to query token state via an endpoint. Add tests for **upstream HTTP status**, **`active`**, **resource-binding**, and **HTTP client credentials**.

| Case | AS B returns | Meaning | Expected at `/api/legacy/orders` |
| --- | --- | --- | --- |
| OPAQUE-T01 | HTTP 200, `active=true`, scope `legacy:read`, right resource | Valid token, sufficient scope | **2xx**. |
| OPAQUE-T02 | HTTP 200, `active=true`, missing `legacy:read` | Authenticated, missing scope | **403**. |
| OPAQUE-T03 | HTTP 200, `active=false` | Inactive | **401 `invalid_token`**. |
| OPAQUE-T04 | HTTP 200, `active=true`, `aud=payments-api` | Token meant for another resource | **401** if API checks audience in introspector. |
| OPAQUE-T05 | HTTP 200 missing `active` or wrong type | Out-of-contract response | Fail closed, never create principal. |
| OPAQUE-T06 | HTTP 200, malformed JSON | Protocol error | Fail closed. |
| OPAQUE-T07 | HTTP 401/403 from introspection endpoint | **Resource Server client credentials/permissions** wrong | Fail closed; classify as dependency/config issue. |
| OPAQUE-T08 | HTTP 429/503 from AS | Throttling/unavailable | Fail closed; handle dependency properly. |
| OPAQUE-T09 | Connection timeout/TLS failure | Cannot verify | Fail closed; never create principal. |
| OPAQUE-T10 | `active=true` with wrong-type `scope` claim | Contract violation | Policy rejects; never grant privileges from odd data. |
| OPAQUE-T11 | Token revoked right before request | AS returns `active=false` | **401**, except within cache-policy staleness window. |
| OPAQUE-T12 | HTTP Basic client secret rotated while API still on v1 | AS rejects client auth | Do not treat all user tokens as invalid; alert ops error. |

### 8.1. Do Not Confuse Two HTTP 401s

```text
Client  ───Bearer token──▶  Resource Server
Resource Server ──Basic credentials + token──▶ AS introspection
```

- **API returns 401 to caller**: the caller's credential was rejected by the API.
- **AS returns 401 to Resource Server**: likely invalid **introspection client ID/secret/mTLS/private_key_jwt**.

These are two distinct HTTP hops. An AS returning 401 to an introspection request **does not prove the caller's token expired**. In both cases, never fail open, yet telemetry and runbooks must distinguish the root causes.

### 8.2. Testing Introspection Client Authentication

HTTP tests against a mock AS should assert:

1. Request uses **POST** to the configured trusted URI.
2. `Content-Type: application/x-www-form-urlencoded` and proper `token` field.
3. HTTP Basic/mTLS/client assertion configured per client registration.
4. Client ID/secret containing special characters are not double-encoded.
5. Access tokens or introspection secrets are never sent to arbitrary hosts.
6. Authorization Basic headers and `token` form bodies are never logged.

In Spring Security 6.5+, `SpringOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` is an appropriate Servlet configuration when the AS uses a client secret; WebFlux needs `ReactiveOpaqueTokenIntrospector` and a reactive implementation. APIs can vary by version; check your actual dependencies.

### 8.3. Introspection of JWTs Can Also Be Valid by Contract

An Authorization Server may require introspecting **JWT access tokens** to check revocation. In that case, "opaque token authentication" refers to **the verification method**, not necessarily the token's string format.

Therefore, the matrix must not state "a JWT sent to an opaque chain is always 401 in every system". In our sample system, **AS B does not recognize JWT A**, so 401 is expected. In production, define the contract explicitly:

```text
Token issuer A → JWT decoder A
Token issuer B → AS B introspection
Never auto-route tokens rejected at A over to B
```

If both mechanisms are allowed on the same route, you need a **trusted** discriminator and negative tests against token confusion.

## 9. Bearer Transport and Malformed Request Matrix

The Resource Server does not only check token payloads; it must handle **how the credential is transported over HTTP**.

| Case | Request | Expected policy |
| --- | --- | --- |
| HTTP-T01 | No `Authorization` on protected endpoint | 401 + Bearer challenge, usually without `error`. |
| HTTP-T02 | `Authorization: Bearer <valid>` | Passes exact token string to route's manager. |
| HTTP-T03 | `Authorization: Basic ...` to Bearer-only API | Does not treat Basic as Bearer; typically 401 if Basic unsupported. |
| HTTP-T04 | `Authorization: Bearer` with no token | Invalid Bearer request/credential per resolver, typically 400 or 401. |
| HTTP-T05 | `Authorization: Bearer token-with-invalid-chars` | Reject per Bearer grammar. |
| HTTP-T06 | Multiple differing `Authorization` headers | Reject or handle per explicit policy; never pick arbitrarily. |
| HTTP-T07 | Both Bearer header and `access_token` query present | Typically reject ambiguous request if both transports exist. |
| HTTP-T08 | `GET /api/orders?access_token=...` | Reject query tokens when policy supports headers only. |
| HTTP-T09 | Token in form body | Allow only if intentionally enabled per RFC/contract. |
| HTTP-T10 | Extremely long header or oversized token | Enforce size/request limits without memory exhaustion. |
| HTTP-T11 | Two Bearer credentials concatenated in one value | Never "take the first token" and ignore the rest. |
| HTTP-T12 | Header with CRLF/control characters | Reject at gateway/container/parser; never reflect in logs/challenges. |

Spring Security provides `DefaultBearerTokenResolver` in Servlet and the corresponding converter/resolver in WebFlux. **Never normalize headers yourself to accept arbitrary formats**, especially when a reverse proxy and Resource Server might interpret them differently.

### 9.1. Query-String Tokens Increase Credential Exposure

`access_token` in a URL can be recorded in:

- Proxy/access logs and WAFs.
- Browser history, referrers, and analytics.
- Cache keys, traces, and error report URLs.

Prefer `Authorization: Bearer`. Tests should assert **the server did not accidentally enable query-parameter token support** when policy forbids it.

### 9.2. Invalid Bearer Sent to a `permitAll` Endpoint

A `permitAll()` endpoint may still pass through the authentication filter. If a client **actively** sends an invalid Bearer token, the filter may return 401 before reaching the `permitAll` authorization rule. Therefore:

```text
GET /public/status, no Authorization   → public success
GET /public/status, invalid Bearer     → must be tested against real chain/resolver
```

Never assume `permitAll` means "all invalid credentials are ignored". If public endpoints should bypass the Bearer filter completely, design a separate chain matcher and test the security boundary.

## 10. HTTP Method, Scope, and Object Ownership Matrix

Even when a token is valid, permissions must match the **HTTP method and data**:

| Case | Request | Token | Expected outcome |
| --- | --- | --- | --- |
| AUTHZ-T01 | `GET /api/v2/orders` | `J_A_READ` | 2xx, list **belonging only to valid actor/tenant**. |
| AUTHZ-T02 | `POST /api/v2/orders` | `J_A_READ` | **403** if missing `orders:write`. |
| AUTHZ-T03 | `POST /api/v2/orders` | `J_A_WRITE` | **201/2xx** if request valid and domain policy passes. |
| AUTHZ-T04 | `GET /api/v2/orders` | `J_A_WRITE` | **403** unless policy specifies write includes read. |
| AUTHZ-T05 | `GET /api/v2/orders/{idA}` | `J_A_READ`, owner tenant A | 2xx, exact record. |
| AUTHZ-T06 | `GET /api/v2/orders/{idB}` | `J_A_READ`, tenant B record | **403/404**, zero data leak. |
| AUTHZ-T07 | `GET /api/v2/orders/{unknown}` | `J_A_READ` | 404 (or other domain contract), revealing nothing about other tenants. |
| AUTHZ-T08 | `POST /api/v2/orders` | `J_A_WRITE`, body sets `tenant_id=B` | **Reject or ignore spoofed tenant**; never create tenant B record. |
| AUTHZ-T09 | `DELETE /api/v2/orders/{idA}` | `J_A_READ` | **403/405** per route/method policy; no deletion. |
| AUTHZ-T10 | `GET /api/internal/reports` | `J_C_REPORTS` | 2xx if service identity permitted by policy. |
| AUTHZ-T11 | `GET /api/v2/orders` | `J_C_REPORTS` | **401** by issuer/resource boundary, regardless of role claims. |

**Important:** 403 vs. 404 for cross-tenant record access is an intentional choice. If the API hides resource existence with 404, tests should verify **there is no obvious response difference** between an existing unauthorized object and a nonexistent object.

### 10.1. Cross-Tenant Test Data

Minimum fixture:

```text
Tenant Alpha:
  issuer A, sub=user-123
  internal user id=1111...
  order A-001 owner=1111..., tenant=Alpha

Tenant Bravo:
  issuer B or different tenant mapping per contract
  internal user id=2222...
  order B-001 owner=2222..., tenant=Bravo
```

Tests must send Alpha's token to read B-001 and assert **access is denied**, even when Alpha's token holds `orders:read`.

### 10.2. Colliding Subject/Email Across Issuers

If issuer A and issuer B both issue:

```json
{"sub": "user-42", "email": "same@example.test"}
```

that is **not proof** both tokens represent the same identity. External identity should use `(verified iss, verified sub)` or a verified account-linking contract. Tests must prove:

- User A cannot read User B's data just because `sub` collides.
- Email/display name never automatically merges accounts.
- Tenant membership is checked from a trusted source.

## 11. Multiple Authentication Mechanisms: Do Not Let a Weaker Mechanism Open a Stronger Endpoint

An API may simultaneously use Bearer JWTs, opaque introspection, HTTP Basic, API keys, browser sessions, or mTLS. Having **multiple mechanisms** does not mean one endpoint should accept all of them.

### 11.1. Endpoint Routing vs. Token Routing

**Routing by endpoint defined in the API contract**:

```text
/api/v2/**          -> JWT issuer A
/api/legacy/**      -> opaque introspection AS B
/api/internal/**    -> JWT issuer C + network/workload policy
/web/**             -> browser session (if present)
```

This is explicit and easy to tabulate and test.

**Routing by a client-sent header**:

```http
X-Token-Type: opaque
Authorization: Bearer ...
```

That header is caller-controlled data and creates zero trust. A dedicated protocol/design is required if an endpoint genuinely must accept multiple credential types.

### 11.2. Anti-Pattern: Exception-Based Fallback

```java
// WRONG: jwtManager rejects -> tries opaqueManager regardless of reason.
return jwtManager.authenticate(authentication)
        .onErrorResume(error ->
                opaqueManager.authenticate(authentication));
```

A JWT with the wrong issuer/audience or signature could be checked through a channel with a different policy. Tests must prove **no fallback occurs when a token is rejected**, especially when:

- Valid JWT A is not meant for the legacy resource.
- JWT A has an invalid signature.
- JWT A has a forged `iss`.
- Active opaque B is meant for the payments API.
- Introspection AS is unavailable.

### 11.3. Account for Authentication Precedence and Path Matchers

A request may match multiple route patterns, yet `FilterChainProxy` in Servlet picks **the single first matching `SecurityFilterChain`** in order. In WebFlux, `WebFilterChainProxy`/`SecurityWebFilterChain` similarly selects by matcher and order.

Risky example:

```text
@Order(1)  matcher("/api/**")          -> Basic authentication
@Order(2)  matcher("/api/v2/**")       -> JWT
```

The broad chain placed earlier can **shadow** the JWT chain. A passing JWT test against a mocked controller **does not prove** real HTTP requests hit the right chain.

A sound configuration puts specific chains before general chains and defines an explicit **unmatched-route policy**.

## 12. Example Configuring Two SecurityFilterChains in Servlet

The code below illustrates separating JWT A and opaque B by **endpoint path**. It does not prove complete security without the corresponding decoder/introspector beans and domain authorization.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleResourceServerChains {

    @Bean
    @Order(1)
    SecurityFilterChain v2JwtApi(
            HttpSecurity http,
            JwtDecoder issuerAJwtDecoder) throws Exception {

        return http
                .securityMatcher("/api/v2/**")
                .sessionManagement(sm ->
                        sm.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .requestMatchers(HttpMethod.POST,
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(jwt ->
                                jwt.decoder(issuerAJwtDecoder)))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain legacyOpaqueApi(
            HttpSecurity http,
            OpaqueTokenIntrospector asBIntrospector) throws Exception {

        return http
                .securityMatcher("/api/legacy/**")
                .sessionManagement(sm ->
                        sm.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/legacy/orders/**")
                            .hasAuthority("SCOPE_legacy:read")
                        .requestMatchers(HttpMethod.POST,
                                "/api/legacy/orders/**")
                            .hasAuthority("SCOPE_legacy:write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(opaque ->
                                opaque.introspector(asBIntrospector)))
                .build();
    }
}
```

This is a **partial configuration**; the sample system still needs the reports chain, public endpoint, and default-deny policy, or a comprehensive security architecture meeting those requirements. Never copy this snippet assuming uncovered paths deny automatically.

**CSRF:** For REST APIs genuinely accepting only Bearer tokens in `Authorization` without relying on cookies/sessions, you may consider disabling CSRF in those chains. The snippet above **has not disabled CSRF**, so POST tests may get 403 for missing CSRF tokens even with `orders:write`. Define CSRF policies per credential transport, configure explicitly, and test accordingly. Never disable CSRF for a browser-session app just to make a POST test return 2xx.

### 12.1. JWT A Decoder with Issuer and Audience

Example decoder creation logic:

```java
String issuerA = "https://login-a.example.test/realms/shop";
String jwksA = "https://login-a.example.test/realms/shop/certs";

NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwksA)
        .build();

OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuerA);

OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Wrong resource audience",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults, audience));
```

Move these variables into `@Bean`/trusted configuration for use in the chain rather than hardcoding production URLs across multiple places. `withJwkSetUri` does not enforce `iss` on its own; keep issuer validation. Token types, profiles, and allowed algorithms must also follow the contract.

### 12.2. Opaque B Introspector

On Spring Security versions supporting the builder:

```java
OpaqueTokenIntrospector rawB =
        SpringOpaqueTokenIntrospector
                .withIntrospectionUri(
                        "https://login-b.example.test/oauth2/introspect")
                .clientId(introspectionClientId)
                .clientSecret(introspectionClientSecret)
                .build();
```

In Spring Security 6.5+, the Spring implementation builder is available; older versions have different APIs. Use a secret manager, HTTPS, timeouts, and a resource-binding policy. If AS B returns `aud`, add a decorator verifying `orders-legacy-api`; if the AS binds resources via introspection client registration, test that guarantee.

### 12.3. Do Not Attach `JwtDecoder` A to Every Chain

If a broad-matcher `SecurityFilterChain` uses decoder A and shadows legacy/reports, the matrix must catch:

- Was `J_A_READ` wrongly accepted at legacy?
- Did `O_B_READ` return 401 at legacy due to hitting the JWT chain?
- Was `J_C_REPORTS` rejected by decoder A on reports?
- Which endpoints matched no chain and were left unprotected?

That is why you need **HTTP integration tests running the entire filter chain**, not just decoder unit tests.

## 13. WebFlux: Equivalent Matrix with `SecurityWebFilterChain`

In WebFlux, configuration uses `ServerHttpSecurity` and `SecurityWebFilterChain`:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveApiChains {

    @Bean
    @Order(1)
    SecurityWebFilterChain jwtOrders(
            ServerHttpSecurity http,
            ReactiveJwtDecoder issuerADecoder) {

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/v2/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(jwt ->
                                jwt.jwtDecoder(issuerADecoder)))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain opaqueLegacy(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspectorB) {

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/legacy/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/legacy/orders/**")
                            .hasAuthority("SCOPE_legacy:read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(opaque ->
                                opaque.introspector(introspectorB)))
                .build();
    }
}
```

The illustrative code requires imports for `@Configuration`, `@Bean`, `@Order`, `@EnableWebFluxSecurity`, `PathPatternParserServerWebExchangeMatcher`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and the matching reactive decoder/introspector. It configures only GET in the two zones; POST is not permitted yet, and reports/public/default-deny must be designed outside this snippet.

**Never wire a blocking Servlet `AuthenticationManager` or `JwtDecoder` into WebFlux and call `.block()` on the Netty event loop.** A reactive Resource Server needs `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector`, and `ReactiveAuthenticationManager`; tests use `WebTestClient`.

### 13.1. Multiple JWT Issuers in WebFlux

If the JWT API accepts two trusted issuers:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(ISSUER_A, ISSUER_C);
```

Wire the resolver:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver))
```

**Note:** `fromTrustedIssuers` focuses on trusted issuer selection. Per-issuer audience and scope/tenant policies must be added properly via a custom manager/decoder registry when needed. Reading `iss` from an unverified JWT only picks a candidate; the selected decoder still must verify JWS and issuer.

## 14. Organizing Tests in Three Layers to Avoid "False-Green Tests"

| Layer | Tools | What does it prove? | What does it NOT prove? |
| --- | --- | --- | --- |
| **Unit policy** | JUnit, custom validators, `JwtGrantedAuthoritiesConverter`, policy beans | Issuer/audience/claim mapping logic and object decisions with mocked dependencies. | JWS signatures, actual HTTP chains, TLS/JWKS/introspection. |
| **Component/protocol** | Signed test JWS + `NimbusJwtDecoder`, WireMock/MockWebServer introspection, `StepVerifier` if reactive | Signatures/claims with real decoder; HTTP introspection requests/responses. | Full route ordering and domain layer unless app runs. |
| **HTTP integration** | `MockMvc` + Spring Security filters, `WebTestClient` + WebFlux Security | Route → right chain → right manager → 401/403/2xx → right data/side effects. | That production has real IAM/TLS/AS configured identically to tests. |

A strong strategy combines all three:

```text
Unit tests  -> policy logic is sound
Protocol    -> trust sources are verified properly
HTTP        -> requests enter the right security mechanism and data is protected
```

### 14.1. The Trap of `jwt()` in MockMvc

```java
mockMvc.perform(get("/api/v2/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

`spring-security-test`'s `jwt()` creates a mock authentication. This test suits **authorization** checks yet can **bypass `JwtDecoder`, signature, issuer, audience, and expiry**.

Thus it **does not prove** `J_B_ISS_A` is rejected, does not prove JWT A hitting legacy is rejected, and does not prove JWKS rotation works.

### 14.2. The Trap of `mockJwt()` in WebFlux

```java
webTestClient.mutateWith(
        mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get()
        .uri("/api/v2/orders")
        .exchange()
        .expectStatus().isOk();
```

`mockJwt()` also constructs a fake principal. Never use that result to claim `ReactiveJwtDecoder` verified signatures or that the issuer resolver chose the right manager. Full trust-path tests require **a Bearer header with a real test-signed JWS**.

## 15. Building Real Signed JWT Fixtures

A strong test suite uses **two distinct test keypairs**, not just a decoder lambda that always returns a JWT.

```text
Test issuer A:
  private key A (test-only)
  public JWK A, kid=a-key-1

Test issuer B:
  private key B (test-only)
  public JWK B, kid=b-key-1
```

To build `J_B_ISS_A`:

1. Construct a payload declaring `iss=A`, `aud=orders-api`, valid `exp`.
2. **Sign the payload with private key B**.
3. Send the token to the JWT A endpoint.
4. Decoder A trusts only public keys A, so **signature verification must fail**.
5. Assert HTTP 401 and zero domain side effects.

To build a validly signed JWT with the wrong audience:

1. Use private key A.
2. Valid `iss=A` and `exp`.
3. `aud=payments-api`.
4. Decoder A must reject at the **audience validator**, not at signature verification.

To build a validly signed expired JWT:

1. Sign payload with private key A.
2. `exp` far enough in the past beyond clock skew.
3. Assert the token is rejected even when `aud` and scopes are right.

**Never use production private keys** to build fixtures. For integration tests, serve public JWKs via a mock server or build decoders from test public keys; ensure issuer/audience config mirrors production guarantees.

### 15.1. Testing JWKS Rotation

A trusted issuer may publish new keys:

```text
Step 1: JWKS A contains a-key-1.
Step 2: JWKS A contains a-key-1 + a-key-2.
Step 3: JWKS A drops a-key-1 after the overlap window.
```

Test:

- JWT signed with a currently published key is accepted after the decoder refreshes/updates cache properly.
- JWT signed with an untrusted key is rejected.
- An unknown `kid` never makes the decoder fetch an attacker's `jku`.
- Key rotation on A never turns public key B into a valid key for A.
- When the JWKS endpoint temporarily errors and the key is uncached, the API **fails closed**.

You do not need long sleeps to test every cache timing detail; use mock key sources, controlled clocks/cache configs, and assert behavior.

## 16. Designing a Purpose-Built Mock Introspection Server

A mock HTTP server should map token fixtures to responses:

```text
O_B_READ       -> 200 {"active":true, "scope":"legacy:read", ...}
O_B_WRITE      -> 200 {"active":true, "scope":"legacy:write", ...}
O_B_NO_SCOPE   -> 200 {"active":true, "scope":"profile:read", ...}
O_B_INACTIVE   -> 200 {"active":false}
O_B_BAD_AUD    -> 200 {"active":true, "aud":["payments-api"], ...}
O_B_UNKNOWN    -> 200 {"active":false}
```

The mock server must verify **requests actually hit the introspection endpoint**:

```http
POST /oauth2/introspect HTTP/1.1
Authorization: Basic <test-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=O_B_READ
```

Here `O_B_READ` is an illustrative fixture name; tests can use random strings. Never log Basic headers or real tokens into logs or snapshots.

### 16.1. Asserting Call Counts on the Right Trust Source

For `GET /api/v2/orders` with `J_A_READ`:

```text
JWT decoder A: invoked
Introspection AS B: 0 calls
JWT decoder C: not invoked
```

For `GET /api/legacy/orders` with `O_B_READ`:

```text
Introspection AS B: receives 1 request when uncached
JWT decoder A: not invoked
JWT decoder C: not invoked
```

**If the application uses caching**, call counts will differ. When testing the authentication path, isolate or disable caching in tests, or use fresh fixtures to force a **cache miss**. Never equate a 200 from cache with working remote introspection credentials.

### 16.2. Testing AS Errors Without Failing Open

Mock server returns HTTP 503/timeout:

```text
Expected authentication: NONE
Expected resource data: NONE
Expected writes: NONE
Expected telemetry: introspection_dependency_error
Expected HTTP: safe failure per API error contract
```

Do not assume every Spring Security version always returns 503. Some exception mappings may return 401/5xx; the **invariant** to test is **zero authenticated principals and zero business execution**.

## 17. Parameterized Tests: Representing the Matrix as Data

One way to organize JUnit 5 is a record describing each case with `@ParameterizedTest`. The snippet below is an **integration skeleton**; `TestTokens` must be backed by a real JWS test encoder and fixtures/mock AS as described above.

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MultiMechanismHttpMatrixTest {

    @Autowired MockMvc mvc;
    @Autowired TestTokens tokens; // Project-provided test fixture service.

    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of("J_A_READ",
                        "/api/v2/orders", 200, null),
                Arguments.of("J_A_NO_SCOPE",
                        "/api/v2/orders", 403, "insufficient_scope"),
                Arguments.of("J_A_EXPIRED",
                        "/api/v2/orders", 401, "invalid_token"),
                Arguments.of("J_A_BAD_AUD",
                        "/api/v2/orders", 401, "invalid_token"),
                Arguments.of("O_B_READ",
                        "/api/legacy/orders", 200, null),
                Arguments.of("O_B_INACTIVE",
                        "/api/legacy/orders", 401, "invalid_token"),
                Arguments.of("J_A_READ",
                        "/api/legacy/orders", 401, "invalid_token"),
                Arguments.of("J_C_REPORTS",
                        "/api/v2/orders", 401, "invalid_token")
        );
    }

    @ParameterizedTest(name = "{0} -> {1}, expected {2}")
    @MethodSource("cases")
    void securityMatrix(String fixture, String path,
                        int expectedStatus, String bearerError)
            throws Exception {

        String signedOrOpaqueTestToken = tokens.resolve(fixture);

        var result = mvc.perform(get(path)
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + signedOrOpaqueTestToken))
                .andExpect(status().is(expectedStatus));

        if (bearerError != null) {
            result.andExpect(
                    header().string(
                            HttpHeaders.WWW_AUTHENTICATE,
                            containsString(
                                    "error=\"" + bearerError + "\"")));
        }
    }
}
```

**Conditions for this example to be meaningful:**

- `TestTokens` is a dedicated test component generating/returning **real token values for requests** (signed JWS or opaque strings), never injecting mock Authentication.
- Mock AS/keys/decoders are wired into the test context.
- Controllers for `GET /api/v2/orders` and `GET /api/legacy/orders` return 200 for authorized actors; business dependencies are safely stubbed.
- Bearer entry point and access denied handler actually emit error codes like `invalid_token`/`insufficient_scope`. Depending on failure and custom handlers, header assertions should match your defined protocol.
- Apps may add authentication factor authorities in newer versions; never assert total authority count against a constant when policy only checks scope.

### 17.1. Encoding Trust-Source Expectations in Code

HTTP status alone is not enough. With mocks/spies, add:

```java
// Assertion idea; test doubles provided by the application.
verify(jwtADecoder).decode(jARead);
verifyNoInteractions(introspectionClientB);
verifyNoInteractions(jwtCDecoder);
```

In real code, depending on Spring version/configuration, you can verify on decoder mocks, HTTP mock servers, or manager instrumentation. When using real decoders, mock the HTTP JWKS server and verify **outbound requests** rather than needing Mockito spies on every class.

Never use a `@MockBean JwtDecoder` that always returns a valid `Jwt` to "test JWS signatures"; that is a **test double** bypassing cryptography.

### 17.2. Testing POST and Side Effects

Do not merely swap `GET` for `POST` and assert status. For write endpoints, verify:

1. Invalid/unauthorized tokens → zero new rows, events, or external side effects.
2. Valid POST → creates a record in the right tenant.
3. Tenant A token with a body declaring tenant B → cannot write into B.
4. Test CSRF policy per credential transport; for browser/cookie APIs, CSRF must genuinely be enforced.
5. Test idempotency, validation, and domain constraints independently of authentication.

If an API intentionally returns 404 for unauthorized object access, tests should assert **no obvious timing/response differences leaking data** within practical control.

## 18. WebTestClient: Data-Driven Tests for WebFlux

In WebFlux, the test is equivalent using `WebTestClient`:

```java
record ReactiveCase(
        String fixture,
        String path,
        int expectedStatus) {
}

List<ReactiveCase> matrix = List.of(
        new ReactiveCase("J_A_READ", "/api/v2/orders", 200),
        new ReactiveCase("J_A_EXPIRED", "/api/v2/orders", 401),
        new ReactiveCase("O_B_READ", "/api/legacy/orders", 200),
        new ReactiveCase("O_B_INACTIVE", "/api/legacy/orders", 401)
);

for (ReactiveCase testCase : matrix) {
    webTestClient.get()
            .uri(testCase.path())
            .headers(h -> h.setBearerAuth(
                    testTokens.resolve(testCase.fixture())))
            .exchange()
            .expectStatus()
            .isEqualTo(testCase.expectedStatus());
}
```

This is a **test-body template**, not a standalone JUnit class. `webTestClient`, `testTokens`, and mock AS/JWKS must be configured in test setup; endpoints must return 200 as assumed.

**Important:** use `headers(...setBearerAuth(...))` with **real test JWT/opaque values**. Using `mutateWith(mockJwt())` tests authorization with a fake principal and does not prove `ReactiveJwtDecoder` or `JwtIssuerReactiveAuthenticationManagerResolver` executed.

### 18.1. Testing Reactor Signals When Needed

A reactive manager has the contract:

```java
Mono<Authentication> authenticate(Authentication input);
```

With `StepVerifier`:

```java
StepVerifier.create(
        jwtManager.authenticate(
                new BearerTokenAuthenticationToken(signedTestJwt)))
        .expectNextMatches(Authentication::isAuthenticated)
        .verifyComplete();
```

Testing this manager **does not prove** requests route to the right `SecurityWebFilterChain` or that HTTP 401/403 responses are built properly. A `WebTestClient` integration test is still needed.

## 19. Using a Contract Matrix to Test Authentication Manager Resolvers

When an endpoint accepts JWTs from multiple issuers, a manager resolver can pick by trusted issuer. A dedicated matrix:

| `iss` hint in JWS | Signed with key | Trusted registry | Expected decoder | Result |
| --- | --- | --- | --- | --- |
| A | A | A, C | A | Verify + claims pass if right resource. |
| C | C | A, C | C | Verify + claims pass if right resource. |
| Unknown D | D | A, C | None | Reject; no discovery to D. |
| A | C | A, C | A | Signature rejected; **never try C**. |
| C | A | A, C | C | Signature rejected; **never try A**. |
| A | A yet `aud=payments-api` | A, C | A | Reject wrong audience. |

In WebFlux:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(ISSUER_A, ISSUER_C);
```

In Servlet:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver
                .fromTrustedIssuers(ISSUER_A, ISSUER_C);
```

`fromTrustedIssuers` has version requirements (added in Spring Security 6.2 for the related APIs); on older dependencies, use the version-appropriate constructor/API. **Never create decoders from arbitrary `iss` values.**

### 19.1. Audience per Issuer

`fromTrustedIssuers(A, C)` does not automatically enforce **every custom audience/policy**. If A is for `orders-api` and C is for `reports-api`, build decoders/managers with separate expected audiences or a trusted resolver registry, and test cross-audience negative cases.

### 19.2. Changes That Must Preserve Test Coverage

When onboarding a legitimate issuer D:

1. Onboard D in the control plane (issuer URI, JWKS, algorithms, audience, token profile, tenant mapping).
2. Update the trusted registry.
3. Add positive JWT D tests on allowed resources.
4. Add negative D tests on other resources.
5. Add D-key signature spoofing and wrong-audience tests.
6. Test that offboarding D rejects subsequent requests.

Never auto-generate a trust registry from arbitrary JWT issuer strings seen in logs.

## 20. Checking Public, Health, and Admin Endpoints

Endpoints that do not accept Bearer tokens or serve monitoring are often left out of the matrix.

| Endpoint | Credential | Expectation | Risk if wrong |
| --- | --- | --- | --- |
| `GET /public/status` | No Bearer | Minimal 2xx. | Leaks config/infrastructure if overly detailed. |
| `GET /public/status` | Malformed Bearer | Depends on security chain; must have real test. | False assumption that `permitAll` skips all filters. |
| `GET /actuator/health` | Unauthenticated or auth per deployment policy | Controlled response. | Leaks unnecessary readiness/dependency details. |
| `GET /actuator/env` | Anonymous | **Must not be publicly accessible**. | Leaks secret references/configuration. |
| `GET /api/internal/reports` | JWT C + right scope | 2xx when workload permitted. | Admin/workload endpoint opened to user JWTs. |
| `GET /api/internal/reports` | JWT A + same-named scope | **401** per issuer/resource contract. | Cross-mechanism privilege escalation. |
| Undeclared route | Any token | Deny/404 per contract. | Missing chain or `permitAll` fallback. |

**Security matchers and method matchers differ:** securing `GET /api/v2/orders` does not prove `POST /api/v2/orders` is safe. Every dangerous method needs positive/negative cases, especially when CSRF and browser credentials are present.

## 21. Another Dimension: Tenant and Actor Type

If the API supports end-user JWTs, machine JWTs, opaque tokens, and multi-tenancy, also test:

| Actor/token | Resource | Expectation |
| --- | --- | --- |
| User A with `orders:read` | Order A | Allow if right owner/membership. |
| User A with `orders:read` | Order B of another tenant | Deny/404. |
| User A with `orders:admin` only in tenant A | Admin action in tenant B | Deny. |
| Machine client C with `reports:read` | Granted reports endpoint | Allow. |
| Machine client C with `reports:read` | User-owned order endpoint | Deny per profile/issuer policy. |
| User from issuer A, `sub=user-1` | Issuer B user also `sub=user-1` | Never auto-merge accounts. |
| User A sharing email with User B | User B data | Deny unless a verified account-linking contract exists. |
| Valid token A with `tenant_id` overridden by client header | Tenant B data | Deny. |

**Token type and actor type are not identical.** A JWT can represent an end user or a workload depending on grant/token profile. Never infer a human user merely because a token is a JWT or has an email claim.

### 21.1. Query-Level Tenant Isolation

Data queries should be constrained at the database:

```sql
SELECT id, tenant_id, owner_user_id, total_amount
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantId
  AND owner_user_id = :verifiedUserId;
```

`verifiedTenantId` and `verifiedUserId` must come from a **verified internal actor context**, never caller-supplied queries or headers. If policy lets a tenant admin read all orders in that tenant, adjust the owner condition accordingly while keeping the tenant condition intact.

## 22. "Denied" Must Mean Zero Side Effects

For data-mutating operations, tests should assert multiple invariants:

```text
Expected HTTP: 401 or 403
Expected authentication: failed / denied
Expected domain service invocation: 0 (if security blocks before controller)
Expected DB writes: 0
Expected external events: 0
Expected outbound payment/email requests: 0
Expected audit: safe security denial event
```

A buggy handler might write to the DB before returning 403. In that case, a test checking only HTTP status **misses the real damage**.

If method security runs inside a service already invoked by the controller, domain service invocations will not be 0, yet **zero unauthorized effects must occur**. Tailor assertions to the actual boundary.

### 22.1. Atomicity and Side Effects

In reactive or async flows, returning 403 does not guarantee a previously launched background `subscribe()` stopped. Never fire-and-forget sensitive business work before authorization passes.

Tests must verify:

- No queue messages published.
- No database transactions committed.
- No downstream API side effects.
- No files/exports generated for another tenant.

## 23. Testing Infrastructure Errors and Rotation

Tests using only valid/invalid claims miss operational failures such as:

- JWKS endpoint unreachable.
- Issuer publishes a new key not yet picked up by cache.
- Introspection AS times out.
- Introspection client secret rotated while Resource Server still uses the old one.
- Mismatched issuer URL / JWKS metadata.
- Expired TLS certificate or wrong trust store.

### 23.1. Dependency Matrix

| Case | Trust source | Situation | Expectation |
| --- | --- | --- | --- |
| DEP-T01 | JWKS A | Cache holds trusted old key A; token uses that key | May verify per cache/policy. |
| DEP-T02 | JWKS A | New key A; JWKS unreachable | Never accept unverified token. |
| DEP-T03 | JWKS A | New key published properly | Decoder updates via cache/key-rotation mechanism and verifies. |
| DEP-T04 | JWKS A | Untrusted TLS certificate | Reject; never disable TLS verification. |
| DEP-T05 | AS B introspection | Timeout | Fail closed; no authenticated principal. |
| DEP-T06 | AS B introspection | Old `client_secret` inactive | Fail closed; surface credential config error. |
| DEP-T07 | AS B introspection | AS returns malformed JSON | Fail closed; never use partial claims. |
| DEP-T08 | AS B introspection | Cache hit active, yet AS just revoked | Per approved TTL/revocation policy; test stale window. |
| DEP-T09 | Issuer registry | Tenant/issuer offboarded | New requests from untrusted issuer must be rejected. |
| DEP-T10 | Config rollout | One pod still uses old issuer/secret | Canary/cluster tests catch inconsistency. |

### 23.2. Fail-Closed Tests Need Not Assert Every Failure Is 401

When AS/JWKS is unavailable, the minimum right outcome is:

- Never create a verified authentication without sufficient proof.
- Zero data access or side effects.
- Zero leakage of raw tokens, keys, or introspection client secrets.
- Telemetry **distinguishing dependency unavailability from invalid tokens**.
- HTTP responses tested per API contract and Spring exception handling—possibly 5xx/503 rather than always 401.

Never "fix" tests by turning infrastructure errors into login success or adding `onErrorResume` returning a mock principal.

## 24. Preventing Test and Production Data Leakage

Authentication tests risk printing tokens/keys into output on failure:

```java
// WRONG: failure logs the entire access token.
log.error("JWT decode failed: token={}, error={}", token, exception);
```

Log instead:

```java
log.warn(
        "Authentication denied: requestId={}, routeGroup={}, category={}",
        safeRequestId, "orders-v2", "invalid-token");
```

For test fixtures:

1. Use only **test-dedicated** private keys and client secrets.
2. Never put production access/refresh tokens into test failure messages.
3. Mock introspection servers must not log `Authorization: Basic ...` or raw `token` bodies in CI artifacts.
4. Test that `WWW-Authenticate`/JSON responses omit tokens, private keys, internal JWKS URLs, and stack traces.
5. Avoid using raw unverified `iss`, `kid`, or `sub` as high-cardinality metric labels.
6. Test request identifiers/correlation IDs contain no PII or credentials.

If grouping failures by token, prefer correlation IDs; never log long token prefixes/suffixes for "easy identification".

## 25. Reducing Combinations Without Dropping Dangerous Intersections

If you have:

```text
4 token types
× 3 trust sources
× 8 endpoints
× 6 claim states
× 4 scopes
× 3 tenant states
 = 6,912 combinations
```

You do not need to run all of them as HTTP integration tests. Tier them:

**Tier A — Mandatory for every security boundary:**

- Right mechanism + right issuer + right audience + sufficient scope.
- Right mechanism, **wrong issuer**.
- Right issuer, **wrong audience**.
- Invalid signature / `active=false`.
- Valid authentication, **missing scope**.
- Right scope, **different tenant/owner**.
- **Wrong token type** on endpoint (JWT A → opaque B, opaque B → JWT A, ID/refresh → API).
- Undeclared route.
- Dependency unavailable → fail closed.

**Tier B — Claim/transport/operational edge cases:**

- `exp`, `nbf`, `typ`, algorithms, `kid`, unknown issuer.
- Bad HTTP Bearer syntax, duplicate credentials, query tokens.
- Key/secret rotation, caches, request concurrency.
- mTLS, session/API-key mixing if used by the system.

**Tier C — High-volume fuzz/property tests:**

- Malformed JWT/JSON, unicode/control characters.
- Unusual JWT headers `kid`/`alg`/`jku`.
- Token length, concurrency, denial-of-service resistance.
- Scope/claim permutations per token profile.

**Pairwise testing** can trim low-interaction dimensions, yet negative cases for **cross-trust**, **cross-audience**, **cross-tenant**, and **fallback confusion** must stay explicit. Those intersections carry the highest privilege-escalation risk.

### 25.1. Assigning Stable IDs to Every Case

An internal JSON/YAML schema (not a summary of this article):

```yaml
caseId: MM-JWT-AUDIENCE-003
category: token-contract
tokenFixture: J_A_BAD_AUD
method: GET
path: /api/v2/orders
expected:
  trustedSource: issuer-a-jwks
  authentication: rejected
  httpStatus: 401
  bearerError: invalid_token
  domainWrites: 0
  introspectionCalls: 0
```

When policy changes intentionally, update the case alongside the review decision. Never silently change expected statuses to match broken output without understanding the trust-boundary shift.

## 26. Integrating the Matrix into CI/CD

### 26.1. On Pull Requests

1. Run unit tests for JWT claim validators, authority converters, and domain policies.
2. Run protocol tests with signed test JWS and mock AS introspection.
3. Run the HTTP integration matrix for **every security chain/route**.
4. Assert status codes, Bearer challenges, route managers, and side effects.
5. Verify negative cross-issuer/cross-audience/cross-tenant cases.

### 26.2. Pre-Deployment

1. Verify issuer/JWKS/introspection URLs come from trusted configuration.
2. Verify secret manager entries and client B credentials match the right version.
3. Verify `SecurityFilterChain` matchers/ordering do not shadow one another.
4. Verify CSRF policy if browser cookies/sessions exist.
5. Verify default-deny or 404 on undeclared routes.
6. Confirm logs/traces redact tokens, secrets, and key material.

### 26.3. Post-Deployment / Canary

1. Verify issuer A JWT succeeds on v2 and is rejected in other zones.
2. Verify opaque B introspects using the canary's own credentials.
3. Verify workload C works only on reports.
4. Monitor 401/403/5xx by **trusted route group** instead of raw tokens.
5. Verify cross-tenant domain queries using authorized test accounts.
6. Monitor key/secret rotation, JWKS/introspection latency, and caches.

Never send production tokens to unauthorized monitoring services. Use minimal test identities/scopes and audit canary actions.

## 27. Anti-Patterns in Security Test Matrices

### 27.1. Having Only One Valid Token and One Invalid Token

Two fixtures cannot prove issuer, audience, token type, scope, tenant, key rotation, or route isolation. Explicit intersection cases are required.

### 27.2. Asserting Only HTTP Status

A 403 returned **after writing to the DB** is still a security bug. Assert side effects and verify no data/tenant leakage.

### 27.3. Using Mock JWTs to Test Trust

`mockJwt()`/`jwt()` can bypass decoders and issuer resolvers. Use real signed JWS tokens to prove signature, `iss`, `aud`, `exp`, `typ`, and JWKS selection.

### 27.4. Retrying Bad-Signature Tokens with Opaque Introspection

Exception-based fallbacks can break trust boundaries. The matrix must assert **no other mechanism is tried** when a token is rejected by the initial policy.

### 27.5. Treating Introspection HTTP 200 as `active=true`

`{"active":false}` is still an invalid token. Tests must inspect `active` in the response body.

### 27.6. Skipping Unknown Issuer Tests

An unverified `iss` must never cause the API to fetch JWKS from arbitrary hosts. Tests must confirm zero outbound discovery to unknown issuers.

### 27.7. Treating JWT A and B with the Same `sub`/Email as the Same User

External identities need an issuer namespace. Cross-tenant account linking must be verified rather than matched by email string.

### 27.8. Ignoring Other HTTP Methods

Securing GET does not guarantee POST, PUT, PATCH, and DELETE are safe. CSRF, side effects, and method matchers differ.

### 27.9. Ignoring Routes Outside Matchers

A URL missing the intended security chain may fall into an unconfigured default chain. Test default-deny and matcher ordering.

### 27.10. Using Status 401 for Every Error

An active token missing privileges is typically 403; syntax errors may be 400; dependency failures need distinct classification. Labeling everything invalid token harms operations and breaks client handling.

### 27.11. Treating a Test Double's Response as Cryptographic Proof

A Mockito mock `JwtDecoder` can return a valid `Jwt` for **any string**, proving nothing about JWS verification.

### 27.12. Treating a Cache Hit as Proof of AS Credentials

A cached active opaque token can return 200 even after the introspection client secret broke. Testing rotation requires a **cache miss or a live introspection probe**.

### 27.13. Testing Public Endpoints by Sending Invalid Bearer and Demanding 200

`permitAll` does not necessarily skip the Bearer filter. Determine whether public routes use a dedicated chain or still run authentication processing.

### 27.14. Changing Expected Results to Match Buggy Implementations

When token B unexpectedly accesses API A, do not flip the expected status from 401 to 200 to make the test green. First determine whether trust policy **intentionally** changed or the system is permitting cross-mechanism access.

## 28. Comprehensive Practice Exercise

Suppose the development team adds an endpoint:

```http
POST /api/v2/orders/6a5c.../approve
```

New policy:

- JWT issuer A only, `aud=orders-api`.
- Token must be unexpired and match the JWT access-token profile.
- Must have `SCOPE_orders:approve`.
- Actor must be an approver for the tenant owning the order.
- Must not self-approve an order created by oneself if prohibited by business policy.

Minimum matrix:

| Case | Token | Order / actor | Expected |
| --- | --- | --- | --- |
| APPROVE-01 | Valid JWT A, `orders:approve` | Tenant A approver, not creator | 2xx; single approval event. |
| APPROVE-02 | Valid JWT A, `orders:read` | Tenant A approver | 403; zero approval events. |
| APPROVE-03 | Expired JWT A, `orders:approve` | Tenant A approver | 401; zero events. |
| APPROVE-04 | Valid JWT C, same scope name | Order A | 401 by issuer/resource boundary. |
| APPROVE-05 | Active opaque B with similar-named permission | Order A | 401 by JWT-A-only route. |
| APPROVE-06 | OIDC ID token A | Order A | 401. |
| APPROVE-07 | Valid JWT A, `aud=payments-api` | Order A | 401. |
| APPROVE-08 | Valid JWT A, `orders:approve` | Tenant B approver | 403/404; zero events. |
| APPROVE-09 | Valid JWT A, `orders:approve` | Creator self-approving | 403 per domain policy. |
| APPROVE-10 | Valid JWT A, `orders:approve` | Nonexistent order | 404; zero events. |
| APPROVE-11 | Tampered JWT A | Tenant A approver | 401. |
| APPROVE-12 | No credential | Order A | 401 + Bearer challenge. |
| APPROVE-13 | Valid JWT A, `orders:approve` | Body `tenant=B` attempting write to B | Deny/no side effects. |
| APPROVE-14 | JWKS A unavailable, token key uncached | Order A | Fail closed. |

This exercise illustrates a vital point: **a new endpoint does not create just one positive test**. It must also enumerate every credential, trust source, resource, and actor **forbidden** from passing through.

## 29. Self-Check Questions

**1. Why is a multi-dimensional matrix needed?** Because many bugs occur when **a token valid in one context** is used in **another context**, such as wrong issuer, audience, chain, or tenant.

**2. Is a JWT with a valid signature enough to call an API?** No. Issuer, audience, lifetime, token profile, and permissions are also required.

**3. Is `iss` inside a JWT trustworthy before verification?** No. It may only act as a routing hint to a **trusted issuer**; the decoder must still verify signature and issuer.

**4. Will JWT A sent to an opaque B endpoint always return 401 in every system?** No. It depends on whether AS B recognizes that token per contract. In the sample system, AS B **does not recognize it**, so 401 is expected.

**5. Is HTTP 200 from opaque introspection enough to authenticate?** No. You must check `active` and the resource/claims contract.

**6. When a token is valid yet lacks scope, what HTTP status is typical?** Typically **403 Forbidden**, distinct from 401 when a credential is rejected at authentication.

**7. Why test a validly signed token with the wrong audience?** To catch a missing audience validator; signature validation alone cannot block tokens intended for another API.

**8. Can an OIDC ID token be used as an OAuth access token?** Not by default. The Resource Server must accept only the right access-token profile and audience.

**9. Why not fall back from a failed JWT manager to an opaque manager?** It can break the trust boundary and cause token confusion.

**10. Do `MockMvc.jwt()` or `WebTestClient.mockJwt()` verify real signatures?** No; they mainly construct a fake principal to test authorization.

**11. Why must the matrix include the expected trust source?** To catch requests passing through **the wrong `SecurityFilterChain` or decoder/introspector** even when the HTTP status happens to look right.

**12. Why assert domain side effects?** A 401/403 returned after writing data is still a security vulnerability.

**13. Does `SCOPE_orders:write` automatically grant read access?** No; only when policy explicitly specifies it.

**14. Does an AS introspection error from a wrong client secret prove the user's access token is inactive?** No. That can be a Resource Server–AS client authentication failure; still fail closed.

**15. When the JWKS endpoint loses connectivity, may signature validation be skipped?** No.

**16. Should email be used as the identity key when switching issuers?** No, not without an account-linking contract; typically use `(verified iss, verified sub)`.

**17. Why must tests include undeclared routes?** To catch endpoints slipping past matchers into unprotected chains.

**18. Why separate CSRF from OAuth scopes?** Because POST requests can return 403 from CSRF policy before scope authorization; test credential transport and chains independently.

**19. Should resource audience be tested for opaque tokens?** Yes if the contract requires it. The AS may return `aud` or enforce resource binding via introspection client permissions; test that guarantee.

**20. When tenant A and tenant B share the same scope, is data isolated?** No. You must verify internal identity, membership, owner, and tenant-scoped data access.

## 30. References and Standards

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** token transport and `invalid_request`, `invalid_token`, `insufficient_scope` errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `nbf`. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JSON Web Token Best Current Practices:** preventing algorithm/token confusion, controlling issuer/audience and key trust. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** token profile/access-token type and profile-required claims. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active` and introspection metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6749 — OAuth 2.0 Authorization Framework:** access/refresh tokens and client authentication. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 9110 — HTTP Semantics:** HTTP 401/403/404 and authentication challenges. https://www.rfc-editor.org/rfc/rfc9110
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Servlet Security Architecture:** https://docs.spring.io/spring-security/reference/servlet/architecture.html
- **Spring Security Reference — Reactive JWT Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive Opaque Token Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Reactive Multi-tenancy:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security Reference — Servlet Testing:** https://docs.spring.io/spring-security/reference/servlet/test/index.html
- **Spring Security Reference — Reactive Testing:** https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **Spring Security API — `JwtIssuerAuthenticationManagerResolver`, `JwtIssuerReactiveAuthenticationManagerResolver`, `JwtValidators`, `NimbusJwtDecoder`, `NimbusReactiveJwtDecoder`:** consult the Javadoc matching your project's dependency version.

## 31. Conclusion

When a Resource Server supports **multiple authentication mechanisms**, tests must clearly answer **which token type is used, which issuer/key source or introspection server is trusted, which endpoint is targeted, and which exact outcomes are allowed**. A matrix with only "valid → 200, invalid → 401" misses most **cross-issuer, cross-resource, and cross-tenant** vulnerabilities.

The minimum set should always include:

```text
Positive: right type + right issuer/trust + right audience + right route
          + right scope + right owner/tenant  → succeed

Negative: wrong type or trust source          → 401
Negative: right issuer, wrong audience        → 401
Negative: invalid signature / inactive        → 401
Negative: valid token, missing permission     → 403
Negative: right scope, wrong tenant           → 403/404 per policy
Negative: AS/JWKS unavailable                 → fail closed, zero side effects
Negative: undeclared route                    → default deny / 404
```

Finally, run **signed JWT tests and HTTP introspection mocks** to prove trust sources; use **`MockMvc`/`WebTestClient` through the filter chains** to prove routing and HTTP behavior; and inspect **data and side effects** to prove business authorization. The central question of the matrix is not merely **"does the request return 200?"**, but **"is a credential accepted strictly within the right trust boundary, on the right resource, with the right privileges, and unable to cross into another tenant or mechanism?"**.
