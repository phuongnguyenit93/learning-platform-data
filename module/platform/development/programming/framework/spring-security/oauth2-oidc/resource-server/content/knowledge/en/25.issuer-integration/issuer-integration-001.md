# Reading Issuer Metadata and Access Token Contracts

In a **Spring Security OAuth 2.0/OIDC Resource Server** architecture, an API should not decide to trust an access token just because the token string has three JWT-like parts, contains a `sub` claim, or is sent by a familiar OAuth client. The Resource Server must know **which issuer is trusted**, which keys or introspection endpoint belong to that issuer, and **which access token contract** is accepted at the API itself.

An Authorization Server (AS) or OpenID Provider (OP) typically publishes metadata at endpoints under `.well-known`. Metadata may include `issuer`, `jwks_uri`, `authorization_endpoint`, `token_endpoint`, `introspection_endpoint`, and other capabilities. However, **metadata is not the entire access token contract**. The Resource Server still needs a separate agreement on audience, access-token profile, signing algorithms, scopes, custom claims, token lifetime, tenant boundaries, revocation, and error responses.

This lesson explains how to:

1. Properly read **OAuth 2.0 Authorization Server Metadata** (RFC 8414) and **OpenID Connect Discovery**.
2. Identify the issuer URI, metadata endpoints, and JWK Set from a trusted source.
3. Distinguish metadata about OAuth/OIDC endpoints from requirements that apply specifically to the **API's access token**.
4. Define JWT and opaque access token contracts: issuer, audience, signature, time, scopes, principal, client, tenant, token type.
5. Configure Spring Security Resource Server in Servlet/WebFlux, including `issuer-uri` and `jwk-set-uri`.
6. Avoid trusting arbitrary metadata, JWT headers containing key URLs, unverified `iss`, or ID tokens mistakenly sent as access tokens.
7. Test the contract with genuinely signed JWTs, fake JWKS/introspection servers, and negative scenarios.
8. Monitor metadata/JWKS operations, key rotation, clock synchronization, and issuer policy changes.

> **Core Principle:** Metadata helps the Resource Server **discover information about an already-trusted issuer**. The access token contract helps the Resource Server decide **whether a specific token is accepted at this API**. And HTTP/method/object authorization decides **what the caller is allowed to do** after the token is valid.

## 1. Three Roles in an OAuth 2.0 Flow

Suppose a sales system has:

```text
Authorization Server / OpenID Provider:
  https://login.example.test/realms/shop

OAuth Client:
  shop-web

Resource Server:
  Orders API: https://orders.example.test
  Payments API: https://payments.example.test
```

A user uses `shop-web` to sign in or perform an authorization flow. The AS issues an access token for the client to call the API. The Resource Server verifies the token before processing data.

```mermaid
sequenceDiagram
    participant U as User
    participant C as OAuth Client shop-web
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    U->>C: Access Orders feature
    C->>AS: OAuth/OIDC authorization flow
    AS-->>C: Access token for orders-api
    C->>RS: GET /api/orders + Bearer token
    Note over RS: Trusted issuer + key/introspection config
    RS->>RS: Token validation: iss, aud, time, alg, contract
    RS->>RS: Scope + tenant + object authorization
    RS-->>C: Data or appropriate 401/403/404 error
```

Four commonly confused identifiers:

| Value | Example | Role |
|---|---|---|
| **Issuer** | `https://login.example.test/realms/shop` | Identifies the AS that issued the token |
| **OAuth client ID** | `shop-web` | The application that received/was issued the token |
| **Resource/API audience** | `orders-api` | The target for which the token is authorized to be used |
| **Subject** | `user-123` | The principal within the issuer's identity namespace |

Do not substitute `client_id=shop-web` for `aud=orders-api`. An OAuth client can request access tokens for multiple APIs; the client ID does not tell which API the current token is intended for.

### 1.1. Are Authorization Server and OpenID Provider the Same?

**Authorization Server** is an OAuth 2.0 role that can issue access tokens without supporting OIDC.

**OpenID Provider** is an issuer that supports OpenID Connect and can provide ID tokens and OIDC Discovery in addition to OAuth functionality.

An AS that does not support OIDC can still publish **OAuth Authorization Server Metadata under RFC 8414**. Therefore, a Resource Server must not assume every issuer is required to have `/.well-known/openid-configuration`.

### 1.2. A Resource Server Usually Does Not Need to Perform Login

Spring Security Resource Server is responsible for validating bearer access tokens. It **does not need to act as an OAuth login client** just to verify JWTs.

In an application combining web login and an API, both OAuth Client and Resource Server dependencies may be present, but they are two separate functions. Do not take an ID token from OIDC login and allow the API to accept it in place of an access token.

## 2. What Is Metadata and What Problem Does It Solve?

A metadata document is typically JSON published by the AS so interacting parties know the endpoints and supported capabilities.

Minimal illustrative example:

```json
{
  "issuer": "https://login.example.test/realms/shop",
  "authorization_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.test/realms/shop/protocol/openid-connect/certs",
  "introspection_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/token/introspect",
  "revocation_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/revoke",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "private_key_jwt"],
  "scopes_supported": ["openid", "profile", "orders.read", "orders.write"]
}
```

Not every Authorization Server returns all of the fields above; the exact required fields depend on the metadata profile and issuer. This JSON example also **does not prove that the listed scopes are always granted** to every OAuth client.

Metadata helps answer:

- What identifier does the issuer advertise?
- Where is the JWK Set URI?
- Where are the token endpoint and introspection endpoint, if the issuer publishes them?
- Which OAuth/OIDC flows, authentication methods, or capabilities are advertised?
- How can a Resource Server configure discovery/JWKS from a known issuer?

**Metadata alone does not fully answer**:

- Which audience is valid for the Orders API?
- Is the access token a JWT, opaque, JWE, or a custom profile?
- What is the required `typ` for a JWT access token?
- Which signing algorithms does the AS use for **access tokens**?
- Is `scope` formatted as a string or an array?
- What does `tenant_id` mean, and is it a required claim?
- How quickly does revoking tenant membership take effect?
- Is `ROLE_ADMIN` a global or tenant-scoped role?
- Is the Orders API allowed to forward tokens to the Payments API?

Those require a separate **access token contract**.

## 3. Two Common Discovery Standards

### 3.1. RFC 8414: OAuth 2.0 Authorization Server Metadata

RFC 8414 defines how an AS publishes metadata, typically using the well-known suffix:

```text
/.well-known/oauth-authorization-server
```

For an issuer without a path:

```text
Issuer:
  https://login.example.test

OAuth AS Metadata:
  https://login.example.test/.well-known/oauth-authorization-server
```

For an issuer with a path:

```text
Issuer:
  https://login.example.test/realms/shop

OAuth AS Metadata per RFC 8414:
  https://login.example.test/.well-known/oauth-authorization-server/realms/shop
```

Common pitfall: With **RFC 8414**, the well-known path is inserted between the host and the issuer path per the standard rule. Do not blindly append `/.well-known/oauth-authorization-server` to the end of the path in every issuer configuration.

### 3.2. OpenID Connect Discovery

OIDC Discovery uses a well-known document usually named:

```text
/.well-known/openid-configuration
```

For an OIDC issuer with a path:

```text
Issuer:
  https://login.example.test/realms/shop

OIDC Discovery:
  https://login.example.test/realms/shop/.well-known/openid-configuration
```

This is the **appended-to-issuer-URL suffix** form of OIDC Discovery. An Authorization Server may support both RFC 8414 and OIDC Discovery, or only one of them.

### 3.3. Do Not Hardcode One Discovery URL for All Systems

For example, with issuer path `/realms/shop`, the two URLs have different shapes:

| Standard | Illustrative Metadata URL |
|---|---|
| OAuth AS Metadata (RFC 8414) | `https://login.example.test/.well-known/oauth-authorization-server/realms/shop` |
| OIDC Discovery | `https://login.example.test/realms/shop/.well-known/openid-configuration` |

When implementing Spring Security, the library's discovery factory may try compatible metadata location forms depending on the version. **Do not assume a fixed fallback order across all Spring Security versions.** Use the official discovery API and check the actual endpoint provided by the issuer.

### 3.4. Not Every OAuth Issuer Is Required to Have OIDC Metadata

If an AS only does OAuth 2.0, receiving a 404 from the OIDC endpoint does not mean the AS is invalid. The issuer may provide RFC 8414 metadata, an explicit JWK Set URI, or an opaque introspection contract.

**A pre-established integration contract** is the source of truth for deciding which endpoints to use.

## 4. Reading a Metadata Document Properly

Example command to inspect metadata, using an endpoint published by the organization:

```bash
curl --fail-with-body -sS \
  "https://login.example.test/realms/shop/.well-known/openid-configuration"
```

Use `--fail-with-body` if your curl version supports it; otherwise, use `curl -i` and inspect the HTTP status before parsing JSON.

Some important metadata fields:

| Field | Meaning | Required for Every Resource Server? |
|---|---|---|
| `issuer` | Issuer identifier advertised by metadata | Critical for trust and JWT issuer validation |
| `jwks_uri` | URL of the JWK Set published by the issuer | Needed when verifying JWTs with remote public keys |
| `authorization_endpoint` | Endpoint used in the OAuth authorization flow | Usually for OAuth clients rather than APIs |
| `token_endpoint` | Endpoint that issues access tokens | Needed by clients; API Resource Servers usually do not call it themselves to verify JWTs |
| `introspection_endpoint` | Endpoint to query token status/details | Needed if the API uses opaque introspection |
| `revocation_endpoint` | Endpoint to request token revocation | Does not mean the API is permitted to call it; usually part of the OAuth client/AS contract |
| `userinfo_endpoint` | OIDC UserInfo endpoint | Does not replace access-token validation at the API |
| `grant_types_supported` | Grant types advertised by the AS | Does not prove a specific client is allowed to use every grant |
| `response_types_supported` | Authorization response types | Does not prove an access token suits the API |
| `scopes_supported` | Set of scopes supported/advertised by the issuer | Does not mean every token contains them |
| `id_token_signing_alg_values_supported` | ID token signing algorithms per OIDC | Does not automatically define access token algorithms |
| `token_endpoint_auth_methods_supported` | Client authentication methods at the token endpoint | Does not imply introspection auth methods |

Do not conflate endpoint capabilities with the token contract. For example, if `scopes_supported` includes `orders.write` but a client receives a token with only `orders.read`, the API must still block POST requests requiring write permission.

## 5. A Source of Trust Must Exist Before Discovery

An insecure integration step:

```text
Receive bearer token from the Internet
  -> manually parse unverified JWT payload
  -> extract iss from payload
  -> connect to caller-supplied issuer URL
  -> download metadata/JWKS
  -> use newly downloaded keys to verify token
  -> accept if signature matches
```

An attacker can create their own issuer and keys, sign their own token, and make the Resource Server connect to that source. This is **trusting a key source designated by an unverified token**.

Proper design:

1. **Pre-configure** the trusted issuer URI or an allowlist of issuers.
2. The Resource Server only discovers metadata belonging to allowed issuers.
3. Metadata must be fetched over HTTPS with verified certificates and hostname, per the deployment contract.
4. The `issuer` field in the metadata must match the configured trusted issuer.
5. JWTs are verified using trusted keys and allowed algorithms.
6. `iss`, `aud`, time, token type, and custom claim rules must pass.
7. When multiple issuers exist, routing must be restricted to the allowlist rather than dynamically adding new issuers from input.

### 5.1. An Issuer URL Alone Does Not Mean Metadata Is Trusted

HTTPS provides transport protection and server identity via PKI, but the Resource Server still must know **which specific organization/issuer it trusts**. A completely valid metadata document from an attacker's domain gives the API no reason to accept the attacker's tokens.

### 5.2. Do Not Disable TLS Validation

To "fix discovery errors," you must never:

- Disable certificate validation.
- Skip hostname verification.
- Use unprotected HTTP in production when the contract requires HTTPS.
- Follow redirects to arbitrary/internal URLs without control.
- Accept metadata/JWKS from a fallback domain outside the trust policy.

If the environment uses a private CA or mTLS, configure the corresponding truststore/HTTP client rather than disabling certificate checks.

### 5.3. SSRF When Performing Dynamic Discovery

Metadata/JWKS endpoints are network URLs. If URLs are constructed from unvalidated input, the backend can be forced to access localhost, cloud metadata, or internal networks. Use an allowlist of issuers/endpoints, egress rules, and controlled redirect policies.

## 6. Issuer URI: An Identifier Value, Not Just a Hostname

Suppose metadata returns:

```json
{
  "issuer": "https://login.example.test/realms/shop",
  "jwks_uri": "https://login.example.test/realms/shop/protocol/openid-connect/certs"
}
```

A valid JWT access token from this issuer typically has:

```json
{
  "iss": "https://login.example.test/realms/shop"
}
```

The Resource Server must compare the issuer according to an exact policy.

### 6.1. Variants That Can Differ in Issuer

```text
https://login.example.test/realms/shop
https://login.example.test/realms/shop/
https://LOGIN.example.test/realms/shop
http://login.example.test/realms/shop
https://login.example.test/realms/other
```

Do not assume manual normalization or treat all variants as the same issuer; issuer comparison must follow the contract/specification supported by the library. In particular, **scheme, path, and trailing slash can be significant**. An issuer mismatch should never be "fixed" by disabling issuer validation altogether.

### 6.2. A Realm or Tenant Path Is Not Automatically a Data Tenant

For example, the `/realms/shop` issuer may issue tokens for multiple data tenants:

```text
shop-a
shop-b
shop-c
```

Do not take the `shop` path segment and assign it as the tenant for every request. Identity realm, OAuth issuer, and data tenant are distinct concepts. If the AS provides `tenant_id`, you must define what that claim means and whether a server-side membership check is required.

## 7. Reading the JWK Set from `jwks_uri`

In a JWT Resource Server, the AS usually signs access tokens with a private key. The Resource Server fetches public keys at `jwks_uri` to verify signatures.

Example:

```bash
curl --fail-with-body -sS \
  "https://login.example.test/realms/shop/protocol/openid-connect/certs"
```

Illustrative response:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-key-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA_MODULUS_BASE64URL>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "shop-key-02",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA_MODULUS_BASE64URL>",
      "e": "AQAB"
    }
  ]
}
```

This is illustrative public key material; placeholder values are not valid keys.

| JWK Property | Meaning |
|---|---|
| `kty` | Key type, such as RSA or EC |
| `kid` | Key identifier, used to select the matching key |
| `use` | Key purpose, such as `sig` when present |
| `key_ops` | Permitted key operations if published |
| `alg` | Algorithm suggested/declared by the JWK if present |
| `n`, `e` | RSA public key components |
| `crv`, `x`, `y` | EC key components for the corresponding curve |

The Resource Server needs to verify the JWS using the matching key, but `kid` **does not prove a key is trusted**. The key must come from the JWKS of an issuer allowed by the application.

### 7.1. A Public JWK Set Does Not Mean Skipping JWT Validation

Public keys are published so the Resource Server can verify signatures; that grants no permissions to anyone viewing the JWKS. Private keys remain protected by the AS. An attacker can view the public key, but cannot forge a valid signature without the private key.

### 7.2. Do Not Use `jku` or `x5u` from a JWT to Fetch Keys

A JWT header can contain parameters pointing to a key/certificate URL. Do not let an untrusted token dictate a new endpoint for the API to fetch. In a typical configuration, the JWKS URI must come from trusted metadata/configuration, not from a caller-controlled token header.

### 7.3. Failed JWKS Key Lookup Must Fail Closed

If a token has `kid=unknown-key` and no matching key exists in the trusted set, **do not skip signature verification**. Refreshing the JWKS depending on the decoder/cache may help, but if there is still no trusted key, the token must be rejected.

## 8. JWT Header: `alg`, `kid`, and `typ`

Example header:

```json
{
  "alg": "RS256",
  "kid": "shop-key-02",
  "typ": "at+jwt"
}
```

The three fields have different roles:

- `alg` is the JWS signing algorithm.
- `kid` helps select the corresponding public key from the trusted key set.
- `typ` can describe the JWT type/profile according to the contract.

**The JWT header is untrusted data prior to signature verification.** The decoder must check the algorithm against an allowlist, the key source against the trusted issuer, and the type profile against the application contract.

### 8.1. Do Not Accept Arbitrary Token-Chosen Algorithms

Wrong:

```text
if token.header.alg == anything:
    choose algorithm requested by token
    use any provided key
    accept if operation succeeds
```

Better:

```text
Issuer contract:
  accepted access token JWS algs = [RS256]

Decoder:
  only use trusted JWKS keys suitable for RS256
  reject none/unsupported/algorithm-confusion cases
```

If the issuer contract supports ES256 or PS256, the configuration can differ. Do not open up all algorithms just to "make a broken token work."

### 8.2. ID Token Alg Metadata Does Not Replace the Access-Token Alg Contract

OIDC metadata may publish `id_token_signing_alg_values_supported`. The field name explicitly says **ID token**. The Resource Server should not infer this is the algorithm list for JWT **access tokens** unless the AS documentation/contract confirms it.

### 8.3. `typ=at+jwt` and RFC 9068

RFC 9068 describes the JWT Profile for OAuth 2.0 Access Tokens, including the `at+jwt` header token type (or the corresponding media type form in the spec). However, **not every AS issuing JWT access tokens implements RFC 9068 in full**.

If the Resource Server requires this profile, you need to:

- Agree with the AS to issue tokens following the profile.
- Verify the exact `typ` and required claims per the standard/profile.
- Check the expected audience.
- Reject OIDC ID tokens or other JWTs even if they share the same key/issuer.

Do not assume Spring Security's default validator automatically enforces the full RFC 9068 profile; behavior depends on the version and decoder configuration.

## 9. What Is an Access Token Contract?

An **access-token contract** is an agreement among the AS, OAuth clients, and Resource Servers, expressed through architecture docs, test fixtures, issuer configuration, and deployment policies.

A contract for the Orders API might include:

```yaml
# Descriptive contract only, NOT Spring Boot configuration.
issuer:
  value: https://login.example.test/realms/shop
  discovery: oidc-or-oauth-metadata

resource:
  id: orders-api
  audience: orders-api

access_token:
  format: jwt
  profile: rfc9068
  signing_algorithms:
    - RS256
  public_keys: trusted-issuer-jwks
  expires_at_required: true
  accepted_clock_skew_seconds: 60

claims:
  required:
    - iss
    - sub
    - aud
    - exp
    - scope
  custom:
    tenant_id:
      required: true
      type: string
      semantics: active-data-tenant

authorization:
  scope_authorities_prefix: SCOPE_
  read: orders.read
  write: orders.write

revocation:
  strategy: short-lived-tokens-plus-server-side-policy
```

**Note:** This is a system-defined example. The OAuth 2.0 specification does not require every issuer to return `tenant_id` or issue scopes matching this exact list. If the AS does not implement RFC 9068, pick the actual profile instead of blindly enforcing this requirement.

### 9.1. Fields That Must Be Agreed Upon

| Category | Questions That Must Have Answers |
|---|---|
| Token format | Is the access token JWT, opaque, JWE, or another format? |
| Issuer | What is the exact `iss` value and what are the AS endpoints? |
| Trust | JWKS/introspection URL, TLS trust, client credentials, rotation policy? |
| Audience | Which Resource Server ID must the token contain? |
| Type/profile | Which token type/`typ` is accepted; is RFC 9068 used? |
| Crypto | Which signing algorithms and key types are allowed? |
| Lifetime | `exp`, `nbf`, `iat`, skew, maximum TTL? |
| Identity | `sub` namespace, how do service principals differ from end users? |
| Authorization | What do `scope`/`scp`/`roles` mean? How are they mapped? |
| Client | Should `client_id`/`azp` be restricted to an application allowlist? |
| Tenant | Which claim or membership determines the active tenant; are permissions tenant-scoped? |
| Revocation | Offline JWT, introspection, denylist, or short TTL? |
| Errors | How are 401 authentication and 403 authorization errors represented? |
| Compatibility | How are issuer/claims/keys changes rolled out? |

A contract is valuable when **verified by code and tests**, not just as a documentation table.

## 10. An Illustrative JWT Access Token

JWT payload:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "tenant_id": "shop-a",
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800,
  "jti": "jti-123"
}
```

Explanation:

| Claim | Meaning | Check at Orders API |
|---|---|---|
| `iss` | Which AS issued the token | Exact expected trusted issuer |
| `sub` | Subject per issuer | Present/correct type if contract requires |
| `aud` | APIs permitted to receive the token | Must contain `orders-api` |
| `client_id` | OAuth client recorded per token profile | Client allowlist if policy requires |
| `scope` | Set of granted scopes | Mapped and checked per endpoint |
| `tenant_id` | Tenant per custom contract | Check type/value and membership when needed |
| `iat` | Issued-at | Used if there is a max-token-age policy |
| `nbf` | Not-before | Do not use before valid time |
| `exp` | Expiration | Do not accept expired tokens |
| `jti` | Token identifier | Can support audit/denylist, does not grant permission by itself |

With Spring Security, a token is **only trusted after signature and validators pass**. Do not take a Base64URL payload string and place it directly into `SecurityContext`.

### 10.1. Claim Presence Differs from Claim Semantics

A token with `tenant_id="shop-a"` does not prove by itself that the caller is still a member of shop-a if membership can be revoked. A token with `scope="orders.read"` does not mean the user can view anyone's orders. A token with `client_id="shop-web"` cannot be used at the Payments API if the audience is only Orders API.

## 11. Audience Must Bind to the Resource Server, Not the Client ID

A client using multiple APIs:

```text
OAuth client:
  shop-web

Orders access token:
  aud = ["orders-api"]

Payments access token:
  aud = ["payments-api"]
```

Sometimes two tokens have the same `iss`, `sub`, and `client_id` but different audiences and scopes. The Orders API should only accept tokens whose `aud` contains the Orders API identifier.

### 11.1. Scope Does Not Replace Audience

Token:

```json
{
  "aud": ["payments-api"],
  "scope": "orders.read"
}
```

still does not match the Orders API per the audience contract. A string looking like an Orders scope does not prove the token was issued for the Orders Resource Server.

### 11.2. Audience Can Contain Multiple Resource Identifiers

JWT `aud` can be a string or an array per the JSON Web Token specification. Spring Security's `Jwt.getAudience()` provides the list of audiences for validation.

If the AS issues multi-audience access tokens, the Resource Server must still check that **its own identifier is present in the list**, and evaluate the necessity/risk of multi-audience tokens. Never assume "the token has at least one audience" is enough.

### 11.3. Resource Indicators RFC 8707

OAuth 2.0 Resource Indicators allow a client to specify a resource when requesting a token in flows supported by the AS:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
resource=https%3A%2F%2Forders.example.test&
scope=orders.read
```

This abbreviated example omits client authentication; the token endpoint must still be protected according to the client type and AS contract.

**Do not assume passing `resource` will always produce an `aud` equal to the exact resource string.** Check the mapping in the AS contract. The Resource Server must verify the token's actual audience.

## 12. Scope and Authority Mapping in Spring Security

Example claim:

```json
{
  "scope": "orders.read orders.write"
}
```

With standard configuration, Spring Security converts this to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

and the API uses:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.write")
```

### 12.1. `scopes_supported` in Metadata Are Not the Token's Scopes

Metadata has:

```json
{
  "scopes_supported": [
    "openid",
    "profile",
    "orders.read",
    "orders.write",
    "orders.export"
  ]
}
```

But the token only has:

```json
{"scope": "orders.read"}
```

The caller still does **not** have `SCOPE_orders.export`. The Resource Server must read authorities from the verified token or introspection response, never taking all `scopes_supported` as permissions for every caller.

### 12.2. `scope` and `scp` Do Not Always Share the Same Format

One AS uses:

```json
{"scope": "orders.read orders.write"}
```

Another AS may use:

```json
{"scp": ["orders.read", "orders.write"]}
```

This is part of the **issuer/token profile contract**. Do not automatically apply one AS's parser to another AS. Verify converter behavior for your Spring Security version and configure claim names/types explicitly when needed.

### 12.3. Are `roles` Converted to `ROLE_...`?

OIDC/OAuth metadata does not mandate that every AS issue roles in one identical standard claim. Claims such as:

```json
{
  "roles": ["ORDER_MANAGER"],
  "realm_access": {
    "roles": ["shop-user"]
  }
}
```

can be product- or deployment-specific structures. If you want to map them to `ROLE_ORDER_MANAGER`, use a converter based on a **trusted contract**, never granting roles from a caller-controllable field.

## 13. Translating Custom Claims into Domain Identity

A tenant-aware API may need:

```json
{
  "sub": "user-123",
  "tenant_id": "shop-a",
  "groups": ["shop-a/orders-editors"]
}
```

You need to determine:

1. Is the tenant claim a single tenant or a membership list?
2. Does the tenant ID have a global namespace or depend on the issuer?
3. Within which tenant are roles/groups valid?
4. When membership changes, can old tokens still be used?
5. Is `sub` a stable user ID or a service principal?
6. If the AS does not return `tenant_id`, from which server-side source does the API obtain it?

An authentication converter can build an `AuthenticatedActor`/domain principal from validated claims. However, it **must never populate the tenant from the URL** and treat it as AS-verified.

### 13.1. Multi-Issuer Contracts Must Prevent Identity Collisions

Two issuers can issue `sub="user-123"` for two different accounts. When querying order ownership, identity usually requires the **(iss, sub)** pair or a trusted internal mapping.

Do not use username/email alone as an ownership key in a multi-issuer system when the contract does not guarantee uniqueness and stability.

## 14. Time: `exp`, `nbf`, `iat`, and Clock Skew

JWT time claims typically use NumericDate: seconds since the Unix epoch.

```json
{
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

Meaning:

| Claim | Purpose |
|---|---|
| `iat` | Issued-at timestamp |
| `nbf` | Earliest time the token is valid |
| `exp` | Expiration timestamp |

The Resource Server must check timestamps according to the validator/contract, and may allow a small clock skew to handle clock drift. Do not use an overly large skew that extends token validity.

### 14.1. Metadata Does Not Prove a JWT Is Unexpired

AS metadata has the exact `issuer` and `jwks_uri`, yet an old JWT can still be expired. Every token must be checked at authentication time.

### 14.2. `iat` Does Not Replace Expiration

A token issued 5 minutes ago does not prove it is still valid. If the contract requires `exp`, check its presence and value; do not synthesize `exp=now+1h` when a token is missing the claim.

### 14.3. Revocation Is a Separate Problem from Expiration

Self-contained JWTs can be verified offline until they expire. If rapid permission/token revocation is needed, the system can use short TTLs, revocation/denylist, introspection, or a policy service depending on the architecture. Discovery metadata alone **does not tell whether a JWT has currently been revoked**.

## 15. Distinguishing JWT Access Tokens from OIDC ID Tokens

An OIDC ID token and an OAuth access token can both use the compact JWT format and share the same issuer, yet serve different purposes:

| Characteristic | OIDC ID token | OAuth access token |
|---|---|---|
| Primary recipient | OIDC client | Resource Server/API |
| Typical audience | OAuth client ID | API resource ID |
| Purpose | Convey authentication info to the client | Let the API check token and access permissions |
| `sub` | May be present | May be present depending on profile |
| API scopes | Not a default source of API permissions | Can carry scopes/permissions per contract |
| Use in `Authorization: Bearer` to Orders API | Should not be used unless it is an API-targeted access token | Proper role when issued by the AS |

Example ID token:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["shop-web"],
  "email": "user@example.test"
}
```

The ID token may be valid for shop-web, but **Orders API must reject it** if the audience contract requires `orders-api`. Do not drop audience validation just because both tokens share the same issuer and `sub`.

### 15.1. The UserInfo Endpoint Does Not Replace the Access-Token Contract

OIDC metadata may provide `userinfo_endpoint`. An API Resource Server usually does not need to call UserInfo to decide whether a bearer token has the right audience and scopes. UserInfo is an OIDC profile endpoint, not an automatic JWT signature verification tool for the API.

### 15.2. Avoiding Cross-JWT Confusion

An issuer may issue multiple kinds of JWTs: ID tokens, access tokens, refresh-related assertions, logout tokens, service assertions, or internal tokens. If they share the same key, **a valid signature alone does not guarantee the token is of the right type**.

When the contract requires a token type/profile, verify `typ` and appropriate claims, not just `iss`/`sub`.

## 16. What to Read When the Issuer Issues Opaque Access Tokens

Not all access tokens are JWTs. For an opaque token:

```text
Authorization: Bearer 8NqVx2pLmZ_some_opaque_value
```

The Resource Server cannot inspect the token string to extract claims. It needs the AS's **introspection endpoint** per RFC 7662 and authentication credentials for the Resource Server.

Metadata may publish:

```json
{
  "issuer": "https://login.example.test/realms/shop",
  "introspection_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/token/introspect"
}
```

However, that URI **does not automatically provide credentials**; the API must be granted access by the AS to call the introspection endpoint (e.g., Basic client authentication, private_key_jwt, or mTLS per contract).

### 16.1. Introspection Request

Illustrative example:

```http
POST /realms/shop/protocol/openid-connect/token/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
```

The server may return:

```json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "shop-web",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iss": "https://login.example.test/realms/shop",
  "tenant_id": "shop-a",
  "exp": 1900000000
}
```

This is an **illustrative response**. Aside from `active`, the remaining fields depend on the AS and contract. Do not assume RFC 7662 requires every issuer to return `iss`, `aud`, `tenant_id`, or `exp`.

### 16.2. `active=true` Is Not Enough for Every API

An active token might be intended for the Payments API:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "payments.read"
}
```

The Orders API needs to enforce `aud` or resource identity per contract; if the contract requires the `orders-api` audience and the AS provides the field, a wrapper `OpaqueTokenIntrospector` can reject tokens with the wrong audience.

### 16.3. Introspection Client ID Differs from Caller Client ID

- `client-id` in Resource Server introspection config: the API's own identifier used when calling the AS.
- `client_id` in the introspection response: the OAuth client recorded by the AS as the token's client.

They do not have to match. Never compare the two values as if they represent the same entity.

## 17. JWT Validation and Opaque Introspection Are Two Different Contracts

| Aspect | JWT Resource Server | Opaque Resource Server |
|---|---|---|
| Token format | Supported JWT/JWS | Opaque string issued by AS |
| Trust mechanism | Public-key signature + validators | AS introspection via trusted endpoint |
| Key endpoint | `jwks_uri`/configured key | `introspection_endpoint`/configured URI |
| Auth credentials to AS | Usually not needed for public JWKS | Usually requires credentials/authorization |
| Revocation | Depends on TTL/denylist/other introspection | AS can evaluate `active` online |
| Network dependency | Metadata/JWKS fetch/cache | Typically an introspection call per request/token |
| Resource audience | `aud` in JWT | Audience/resource info returned by AS introspect per contract |
| Scope mapping | Claims in JWT | Claims/authorities from introspection |
| Failure mode | Signature/issuer/audience/time/JWKS | inactive/AS HTTP timeout/credential errors/contract |
| Error principle | Fail closed | Fail closed |

Do not pick a mode just because a token "looks like it has dots." Choose JWT vs. opaque based on the AS token format contract and Resource Server architecture.

## 18. Spring Boot Servlet: Configuring the Issuer URI

A simple option for a JWT Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Spring Security/JWT auto-configuration can use issuer discovery to find the JWK Set URI and apply issuer validation depending on the version. This works well when the AS publishes standard metadata and the Resource Server trusts a single issuer.

### 18.1. HTTP Authorization Must Still Be Configured

```java
@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/catalog"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders"
                ).hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

`issuer-uri` helps establish the token source, while `hasAuthority(...)` evaluates HTTP operation permissions. A token with the right issuer but insufficient scope must still receive 403; a token with the wrong issuer or invalid signature typically receives 401.

### 18.2. Metadata Discovery Does Not Replace Audience Validation

An issuer can issue tokens for Orders API, Payments API, and Admin API. **Configuring only the issuer URI does not automatically know the Orders API's expected audience** in all Spring Boot/Spring Security versions. Configure `audiences` if your version supports it, or register a custom `OAuth2TokenValidator<Jwt>`.

## 19. Spring Boot: Explicitly Configuring JWK Set URI

If the organization knows the exact JWK Set URL:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
```

Meaning:

- `issuer-uri`: expected issuer used for token validation.
- `jwk-set-uri`: source of public keys for signature verification.

Some configurations can reduce startup dependency on discovery metadata by providing an explicit `jwk-set-uri`, though JWKS may still need an HTTP fetch when verifying tokens. Exact startup/runtime fetch details depend on version and caching.

**Do not drop issuer validation just because a JWK Set URI is configured.** JWKS indicates the configured key source; `iss` must still be verified against the expected issuer separately.

### 19.1. Audience Property If Supported by Boot

Example for Spring Boot versions that support it:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

Check whether the property is supported in your version, and verify whether a custom `JwtDecoder` bean overrides it. When a developer defines a custom `JwtDecoder` bean, Boot may not automatically attach all property validators to that bean.

## 20. Java Configuration: Issuer Discovery with `JwtDecoders`

A commonly used factory in Servlet Resource Server:

```java
@Bean
JwtDecoder jwtDecoder() {
    String issuer =
        "https://login.example.test/realms/shop";

    return JwtDecoders.fromIssuerLocation(issuer);
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
```

The factory uses issuer discovery via the mechanism supported by Spring Security. If you only need the same behavior as property configuration, creating a separate bean is not strictly necessary.

### 20.1. When Custom Validators Are Needed, Create a Controlled NimbusJwtDecoder

A more explicit example:

```java
@Configuration
public class OrdersJwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String JWKS =
        "https://login.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String EXPECTED_AUDIENCE =
        "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(EXPECTED_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaults,
                audience
            )
        );

        return decoder;
    }
}
```

Imports:

```java
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
```

This is an important example:

1. `NimbusJwtDecoder` verifies the JWT using keys fetched from the trusted JWKS.
2. `JwtValidators.createDefaultWithIssuer(...)` provides default validators along with issuer validation.
3. The custom audience validator requires `aud` to contain `orders-api`.
4. `DelegatingOAuth2TokenValidator<>` combines validators so all must pass together.

**Do not simply call `setJwtValidator(audience)` and accidentally overwrite issuer/timestamp validation.** When creating a custom decoder, the developer is responsible for keeping all required rules.

### 20.2. Requiring a Tenant Claim per Contract

If the API is tenant-scoped and the AS always issues `tenant_id`:

```java
OAuth2TokenValidator<Jwt> tenantRequired = jwt -> {
    Object value = jwt.getClaim("tenant_id");

    if (value instanceof String tenant && !tenant.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Required tenant claim is missing",
            null
        )
    );
};
```

It can be combined with defaults and audience. This is a **contract-specific custom rule**, not a default requirement for every JWT access token.

### 20.3. Do Not Patch Claims to Pass Validation

Do not do this:

```java
if (jwt.getAudience().isEmpty()) {
    // Wrong: turns a token missing audience into an API-accepted token.
    claims.put("aud", List.of("orders-api"));
}
```

If the AS issues tokens without the proper audience, fix the token-issuing configuration/contract rather than making the validator pass by injecting claims on the Resource Server side.

## 21. Spring WebFlux: Discovery Configuration with ReactiveJwtDecoder

With WebFlux, the interface is `ReactiveJwtDecoder` and the result is `Mono<Jwt>`.

Example:

```java
@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersSecurity {

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
            "https://login.example.test/realms/shop"
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

This is a WebFlux example; do not substitute Servlet `HttpSecurity`/`SecurityFilterChain`.

### 21.1. Reactive Nimbus and Explicit JWKS

When a custom decoder is needed:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withJwkSetUri(
                "https://login.example.test/realms/shop/protocol/openid-connect/certs"
            )
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
            "https://login.example.test/realms/shop"
        )
    );

    return decoder;
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

If the API requires audience validation, add an audience validator just as in the Servlet section, **rather than keeping only issuer validation**. A synchronous `JwtDecoder` does not automatically replace `ReactiveJwtDecoder`.

### 21.2. Do Not Perform Blocking Discovery on the WebFlux Event Loop

If the application implements a custom discovery/metadata client, avoid `RestTemplate` or `.block()` on the Netty event loop. Use Spring Security's reactive support or an appropriate reactive HTTP client with timeouts and controls.

## 22. Opaque Tokens in Servlet Spring Security

If the token contract is opaque:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/realms/shop/protocol/openid-connect/token/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Filter chain configuration:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Spring Security's `OpaqueTokenIntrospector` calls the AS to validate the token per configuration. If audience/client/tenant rules are needed, wrap the delegate implementation with a decorator.

### 22.1. Decorator Returning a Principal Only When the Contract Passes

Example:

```java
public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean matched =
            aud instanceof String text
                && "orders-api".equals(text);

        if (aud instanceof Collection<?> values) {
            matched = values.stream()
                .anyMatch("orders-api"::equals);
        }

        if (!matched) {
            throw new BadOpaqueTokenException(
                "Wrong audience"
            );
        }

        return principal;
    }
}
```

Imports:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

Notes:

- The delegate must check `active` first.
- If the AS does not return `aud` yet the contract requires audience, agree with the AS to return the claim or use another resource binding mechanism.
- Do not allow active tokens for the Payments API to pass through the Orders API.
- Do not catch the delegate's exception and fabricate a fake principal.
- A token-wide wrapper does not replace owner/tenant record authorization.

## 23. Signing Algorithms and Token Profile Are a Separate Contract

An AS has OIDC metadata:

```json
{
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
```

That does not prove the current access token uses RS256/ES256 under the same constraints.

An **access-token contract** should answer:

```text
Access token format:
  JWT JWS compact

Accepted access-token JWS algorithms:
  RS256

Expected header type:
  at+jwt, if AS implements RFC 9068 profile

Trusted public key set:
  issuer JWKS URL

Key rotation:
  publish new key before signing with it
  retain old key until old tokens expire

Token encryption:
  not used (or separately specified if JWE is used)
```

### 23.1. JWE Differs from JWS

- **JWS:** signed token; the Resource Server verifies the signature.
- **JWE:** encrypted token; the Resource Server needs appropriate decryption keys/processing before claims can be validated per profile.

A five-part compact token may be a JWE rather than a JWS. Do not blindly parse every token as a three-part JWT, and do not treat "Base64-decoded" as verified validity.

If the AS issues encrypted access tokens, the Resource Server must have a separate JWE contract and supported implementation; never disable encryption or accept plaintext tokens arbitrarily.

## 24. Sender-Constrained Access Tokens Require Additional Verification

Some AS deployments issue **sender-constrained** access tokens rather than bearer tokens usable by anyone holding the token string.

Two common mechanisms:

- **mTLS-bound access tokens** per RFC 8705.
- **DPoP-bound access tokens** per RFC 9449.

The JWT/introspection response may include `cnf` describing the confirmation key/thumbprint per profile. However, merely having a `cnf` claim **does not prove the current request actually possesses the key**.

### 24.1. mTLS

The Resource Server must inspect the client certificate on the TLS connection and match the thumbprint/binding per contract. If the API sits behind TLS-terminating gateways, establish a clear trust boundary so the backend does not trust a certificate header sent directly by an Internet client.

### 24.2. DPoP

DPoP requires verifying the proof JWT/HTTP binding, method, URI, timestamp, nonce/replay rules, and public key thumbprint per spec/contract. Do not simply accept `Authorization: DPoP ...` and treat it like a regular Bearer token.

**Do not assume a Spring Security Resource Server configured with JWT `issuer-uri` automatically supports every sender-constrained token mechanism.** Verify actual version capabilities and configuration.

### 24.3. Why Does This Relate to Metadata?

An AS can advertise certain DPoP/mTLS capabilities in metadata via extensions. However, metadata advertising support for a feature **does not mean every access token uses that feature**, or that the Resource Server already implements proof verification. The token/client/RS contract must align.

## 25. JWKS Rotation: Correct Metadata Yet Tokens Still Fail

Suppose the AS is using `kid=old-2026`, then rotates to `kid=new-2026`.

An operational plan:

1. The AS generates a new key pair.
2. The AS publishes the **new public JWK** at the trusted JWKS before issuing new tokens.
3. The AS retains the old public JWK while old tokens remain valid.
4. The AS begins signing new tokens with the new key.
5. Resource Servers refresh/cache JWKS and select keys by `kid`.
6. Once old tokens have expired and the transition is safe, the AS removes the old key.
7. Monitor failures, rollback plan, and timeline.

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS Endpoint
    participant RS as Resource Server
    AS->>JWKS: Publish public key NEW alongside OLD
    AS->>RS: New JWT header kid=NEW via client request
    RS->>JWKS: Refresh JWKS when cache/lookup requires
    JWKS-->>RS: Keys OLD + NEW
    RS->>RS: Verify signature with NEW
    Note over AS,RS: Keep OLD until valid old tokens have expired
    AS->>JWKS: Remove OLD after safe transition
```

### 25.1. New `kid` and Caching

If a Resource Server has not yet seen the new `kid` in its cache, the decoder may re-fetch the JWKS depending on the implementation. However, if the JWKS has not yet published the new key or the network is unavailable, the token has no trusted key for verification. **Do not disable signature validation** to work around rotation failures.

### 25.2. `kid` Can Be Duplicated or Missing

Key selection should not rely solely on `kid` while ignoring algorithm, key type, key use, and issuer context. If multiple keys cannot be safely disambiguated, the decoder must reject or handle them per the deployment contract rather than picking one arbitrarily.

### 25.3. JWKS Cache Differs from Access-Token Validation Cache

A decoder caches public keys to reduce HTTP requests while still verifying every JWT. Caching a key does not mean a JWT remains valid once `exp` has passed or if the token has the wrong audience.

## 26. Metadata/JWKS Outage and Failure Handling

Incidents that can occur:

| Symptom | Likely Cause | Impact |
|---|---|---|
| Metadata returns 404 | Wrong OIDC/RFC 8414 URL or issuer does not support that endpoint | Cannot perform discovery |
| Metadata issuer mismatch | Misconfigured realm, path, or reverse proxy | Result should not be trusted |
| TLS handshake failure | Certificate/truststore/mTLS/hostname issue | Cannot fetch metadata/JWKS |
| Malformed metadata JSON | Broken AS/gateway response | Discovery fails |
| `jwks_uri` unreachable | Network/egress/DNS/service outage | No fresh keys available |
| JWT has new `kid` but JWKS is stale | Unsynchronized rotation | Signature verification fails |
| Wrong JWT `iss` | Token from another issuer | Authentication rejected |
| Wrong JWT `aud` | Token intended for another API | Authentication rejected |
| Expired JWT `exp` | Token expired | Authentication rejected |
| Opaque introspection 401 | Wrong/insufficient introspection client credentials | Authentication cannot complete |
| Opaque introspection timeout | AS/network unavailable | Fail closed |
| Active token missing contract claim | Contract mismatch | Wrapper/validator rejects |

Infrastructure failure does not mean the token was revoked, yet **successful Authentication cannot be granted if verification cannot be completed**.

### 26.1. Startup Dependency Differs from Runtime Dependency

When creating a decoder from issuer discovery, some setups require HTTP metadata immediately at initialization; others defer fetching or use a known JWK URI. Therefore:

- Do not claim every Spring Security version always fails at startup when the AS is down.
- Do not claim every version is always completely lazy.
- Check behavior in your actual dependency version.
- Design appropriate readiness/startup checks, timeouts, and monitoring.

### 26.2. Timeouts and Retries

Network discovery/JWKS/introspection calls need timeouts, connection limits, and controlled retry/backoff. Retrying invalid JWTs or inactive tokens indefinitely solves nothing. An AS outage can cause cascading failures when multiple APIs attempt discovery/JWKS refreshes concurrently, so capacity planning is necessary.

## 27. Multi-Issuer Integration: Each Issuer Has Its Own Contract

An API may trust two issuers:

```text
Issuer A:
  https://login.example.test/realms/shop
  JWKS A
  audience: orders-api

Issuer B:
  https://partners.example.test/realms/partners
  JWKS B
  audience: orders-partners-api
```

Do not use a single decoder with JWKS A and accept tokens from issuer B, or merge all keys into an unbound pool without issuer constraints.

### 27.1. Routing Must Have an Issuer Allowlist

An authentication manager resolver may need to read the unverified `iss` **solely to select** among allowlisted issuers:

```text
unverified iss = https://partners.example.test/realms/partners

if issuer in trustedAllowlist:
    choose configured decoder for that issuer
    decode and verify signature + iss + aud + time
else:
    reject
```

Accepting an arbitrary issuer and dynamically building a decoder from that URL is dangerous. Reading an unverified claim **must never count as validating the claim**.

### 27.2. Claims Can Differ in Semantics Across Issuers

Issuer A uses:

```json
{"tenant_id": "shop-a", "scope": "orders.read"}
```

Issuer B uses:

```json
{"organization": "partner-17", "permissions": ["orders:read"]}
```

If the API allows both through, you need per-issuer resolvers/converters matching each issuer's contract. Never take a partner's `permissions` and map them directly to internal admin privileges without an explicit policy.

### 27.3. Subject Namespace

`(iss A, sub=user-123)` can differ from `(iss B, sub=user-123)`. Domain identity mapping should consider an issuer-qualified principal or a server-side mapped internal account ID.

## 28. Metadata Can Change, But Trust Should Not Expand Automatically

An AS upgrade might add:

- New scopes.
- New grant types.
- Additional supported signing algorithms.
- Token auth methods.
- New endpoints.
- Additional OIDC claims.

The Resource Server **should not automatically grant additional permissions** just because metadata adds new `scopes_supported`. Likewise, do not automatically allow a weaker/different signing algorithm just because a capability list changes. The access token contract and Resource Server policy still require independent review/deployment.

### 28.1. Changes Requiring Coordination with the API

| Change on AS Side | Resource Server Consideration |
|---|---|
| Issuer URI changes | Trusted issuer config, dual-issuer rollout or migration |
| JWKS URL changes | Fetch/caching/TLS/network, rotation |
| Signing algorithm changes | Algorithm allowlist, key type, decoder support |
| Audience mapping changes | Expected `aud`, OAuth resource/client request |
| `scope` from string to array | Authority converter |
| Tenant claim renamed | Claim validator/actor mapper |
| Access token from JWT to opaque | Decoder -> introspector architecture |
| Token lifetime changes | Exp/nbf/skew/revocation policy |
| New sender constraint | DPoP/mTLS proof verification |
| Roles structure changes | Domain permission mapping |
| Client ID behavior changes | Client allowlist/integration tests |

Do not fix mismatches by disabling validation "for compatibility." Use contract versioning, integration tests, and a migration path.

## 29. Defining the Contract Between AS, OAuth Client, and Resource Server

A contract document may contain fields such as:

```text
Issuer:
  https://login.example.test/realms/shop

Discovery:
  OIDC discovery enabled
  JWKS published at documented URL

Resource:
  Orders API identifier orders-api

Clients:
  shop-web uses authorization_code + PKCE
  trusted-worker uses client_credentials

Token type:
  JWT access token, signed JWS
  RFC 9068 profile enabled if AS supports it

Claims:
  iss: exact issuer
  aud: includes orders-api
  sub: stable subject within issuer namespace
  scope: space-delimited string
  tenant_id: active tenant as string
  exp: required
  nbf: optional per AS profile

Signing:
  RS256 accepted
  JWKS rotation overlap required

API authorization:
  GET /api/orders/** requires orders.read
  POST /api/orders requires orders.write
  Object/tenant ownership verified server-side

Revocation:
  Token TTL and urgent revoke strategy documented

Error contract:
  No/invalid token -> 401 Bearer challenge
  Valid token, insufficient authority -> 403
  Object not visible -> 403/404 per policy
```

In practice, the contract should also specify **who owns changes** (AS team vs. API team), staging/prod environments, TLS certificates, observability, security incident runbook, and compatibility windows.

### 29.1. Do Not Put Client Secrets in Public Contracts

Documentation should describe how secrets/credentials are provisioned, not record plaintext introspection client secrets, private JWKs, or refresh tokens. Public JWKS is public key material, while private signing keys must remain in the AS key management system.

## 30. HTTP Authorization After the Token Matches the Contract

The token has passed:

```text
Signature: valid
Issuer: correct
Audience: orders-api
Expiration: valid
Tenant claim: well formed
```

yet the client sends:

```http
DELETE /api/orders/order-42
Authorization: Bearer <VALID_READ_ONLY_TOKEN>
```

If the token only has `orders.read`, HTTP authorization must deny it.

Servlet example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("SCOPE_orders.delete")
    .anyRequest().denyAll()
)
```

Another question: the caller has `orders.read`, but order-42 belongs to a different tenant. **Object-level authorization** in the service/repository must still deny access. Do not mix token contract, action permission, and ownership.

### 30.1. 401 and 403 Are Different

| Failure | Category | Typical HTTP |
|---|---|---|
| Missing bearer token on protected endpoint | Unauthenticated | `401` |
| JWT wrong signature/issuer/audience/exp | Token authentication | `401 invalid_token` |
| Inactive opaque token | Token authentication | `401 invalid_token` |
| Valid token missing `orders.write` | Action authorization | `403` |
| Valid scope but order belongs to another user/tenant | Object authorization | `403` or `404` |
| Service business state disallows cancel | Business rule | Possibly `409` |
| JWKS/introspection outage | Infrastructure/authentication cannot complete | Fail closed; status depends on exception flow |

Do not conclude a token is expired just because you see a 401; it could also have the wrong issuer, audience, signature, or token type.

## 31. Inspecting Metadata with curl: What to Record

A manual verification procedure when integrating an AS:

### Step 1 — Determine the Exact Trusted Issuer

```text
https://login.example.test/realms/shop
```

This is pre-configured, never taken from an unverified token.

### Step 2 — Fetch Issuer Metadata

```bash
curl -i \
  "https://login.example.test/realms/shop/.well-known/openid-configuration"
```

If the AS uses RFC 8414, try the **exact RFC 8414 URL per the issuer contract**, without guessing:

```bash
curl -i \
  "https://login.example.test/.well-known/oauth-authorization-server/realms/shop"
```

Record the HTTP status, `Content-Type`, TLS certificate validation, `issuer` value, and `jwks_uri`.

### Step 3 — Verify Metadata Issuer

Expectation:

```text
configured_issuer == metadata.issuer
```

If they do not match, do not blindly change the expected issuer to whatever is in metadata; check base URL/proxy/realm config.

### Step 4 — Fetch JWKS from the Trusted URI

```bash
curl -i \
  "https://login.example.test/realms/shop/protocol/openid-connect/certs"
```

Record `keys`, `kid`, key types, and algorithms per contract. Never copy private keys; the JWK Set publishes appropriate public keys.

### Step 5 — Request a Test Token via the Proper Flow

Test OAuth clients use `authorization_code` + PKCE or `client_credentials` depending on the application type. Do not use the password grant just for a "quick test" if the AS/client does not support it or policy forbids it.

### Step 6 — Inspect Claims of the Signed Token

After the decoder verifies the signature, check:

```text
iss
aud
exp
nbf
sub
scope/scp
client_id or azp, if contract
tenant_id, if contract
typ/alg/kid, if contract
```

Never log/upload raw production tokens to untrusted systems.

### Step 7 — Test API Negative Cases

A token for the Payments API must be rejected by the Orders API. Expired/wrong-issuer/bad-signature tokens must be rejected. A valid token lacking the write scope must receive 403 on POST.

## 32. Testing with Real JWTs and Mocked JWKS

Unit testing token validation differs from unit testing HTTP authorization.

### 32.1. Testing the Decoder with Genuinely Signed JWTs

Prepare a test RSA/EC keypair (never use production keys) and a fake JWKS endpoint serving the public key. Generate test JWTs signed with the corresponding private key:

| JWT Fixture | Signature | Claims | Expectation |
|---|---|---|---|
| Valid Orders token | Trusted test key | Correct iss/aud/time | Decodes successfully |
| Wrong signature | Other key | Same claims as good token | Rejected |
| Unknown `kid` | Not in trusted JWKS | Valid claims | Rejected |
| Wrong issuer | Trusted signature | Different `iss` | Rejected |
| Wrong audience | Trusted signature | `aud=payments-api` | Rejected |
| Expired | Trusted signature | `exp` in the past | Rejected |
| Future `nbf` | Trusted signature | Token not yet valid | Rejected |
| Missing required tenant | Trusted signature | No tenant | Rejected per custom contract |
| Unexpected token type | Trusted signature | Wrong `typ` header | Rejected if policy requires |
| New rotated key | Trusted new key | Valid claims | Succeeds after appropriate JWKS refresh |

These tests catch decoder/validator bugs that mocked HTTP tests miss.

### 32.2. `jwt()` in Spring Security Test Does Not Replace Decoder Tests

MockMvc example:

```java
mockMvc.perform(get("/api/orders/order-42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority(
                "SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

This is useful for testing HTTP authorization with a simulated principal. However, `jwt()` **typically bypasses JWT signature verification**. To verify that issuer/JWKS/audience validators actually work, send signed JWT fixtures through the decoder or test the decoder directly.

The `200` status in the example also depends on controller/service/test fixtures being configured to return valid data.

### 32.3. Opaque Introspection Requires a Fake AS HTTP Server

Use WireMock/MockWebServer or an appropriate HTTP stub:

- Stub `active=true` with expected audience/scopes/tenant.
- Stub `active=false`.
- Stub wrong audience.
- Stub missing required claim.
- Stub timeout, 401 invalid credentials, malformed JSON, 503.
- Send requests with a **real Bearer header** through the Spring Security filter chain.
- Verify the real introspector is invoked; do not use `mockOpaqueToken()` for this test.

`mockOpaqueToken()` is useful for authorization tests, but bypasses actual HTTP introspection.

## 33. Testing Metadata and JWKS Dependencies

An integration test with a fake issuer can simulate:

```text
Trusted issuer test URI
  -> metadata HTTP endpoint
  -> jwks_uri pointing to test JWKS
  -> public test keys
  -> signed JWT requests
```

Cases to test:

1. Correct metadata `issuer`.
2. Wrong metadata `issuer`.
3. Non-existent discovery endpoint.
4. JWKS returning 200 with valid public keys.
5. JWKS returning HTML/malformed JSON.
6. TLS/connection/timeout failure (if test infrastructure supports it).
7. Key rotation adding a new `kid`.
8. Key rotation removing the old key at the right/wrong time.
9. JWT with wrong algorithm.
10. JWT with wrong audience.
11. API receiving a token from an issuer outside the allowlist.
12. Metadata/JWKS redirecting to a host outside the trust policy.

Do not call the production AS in unit tests just to check validation, because network/test credentials/rotation make tests flaky. Use dedicated fixtures and controlled integration environments.

### 33.1. Testing Real JWKS Caching

A new JWT with a new `kid` may require refreshing public keys. Tests must accurately simulate the JWKS/cache policy of the decoder in use. **Do not conclude key rotation tests passed just because a decoder accepted a mocked `Jwt`.**

### 33.2. Do Not Hardcode Perpetual Tokens

Test tokens with `exp` far in the future or omitted expiration can mask timestamp validation bugs. Use a clock/test fixtures with appropriate timestamps to test valid, expired, and not-before states.

## 34. Common Metadata Troubleshooting Scenarios

### 34.1. `/.well-known/openid-configuration` Returns 404

The issuer may not support OIDC or uses a different RFC 8414 path. Check the contract and published endpoints; never blindly trust a client-suggested endpoint.

### 34.2. Metadata `issuer` Does Not Equal Configured Issuer

There may be a wrong base path/realm, reverse proxy host/scheme mismatch, or misconfigured AS public URL. Fix the AS/proxy/issuer configuration per contract; do not disable validation.

### 34.3. `jwks_uri` Is Correct Yet JWT Still Returns 401

Possible reasons:

- Wrong JWT `iss`.
- Wrong JWT `aud`.
- Expired JWT or future `nbf`.
- Key/`kid` mismatch.
- Disallowed signing algorithm.
- Wrong token type/profile.
- Malformed JWT/JWS header.
- AS issued an encrypted token while the decoder only supports JWS.

**Successfully reading the JWKS does not prove a token will be accepted.**

### 34.4. Valid JWT Signature Yet Missing Scope

Token authentication succeeded, but the route requires a different authority. This is typically HTTP 403. Check actual granted scopes, the converter, and permission mapping—do not tweak JWKS.

### 34.5. 401 After Key Rotation

Check the metadata/JWKS URL, new key publication timing, cache freshness, `kid`, and old key retention period. Never disable signature verification to get past an incident.

### 34.6. Opaque Introspection Is Active Yet the API Rejects It

The token may have the wrong audience, tenant, client allowlist, token type, or be missing required claims. `active=true` does not mean a token is valid for every Resource Server.

### 34.7. AS Timeout Causing Widespread API Errors

Check network/egress/TLS/introspection credentials, HTTP connection pooling, and retries. The API must fail closed; optimize caching or degradation only per risk policy, never fabricating Authentication.

### 34.8. Multiple Applications Share an AS Yet Behave Differently

Each Resource Server may have different expected audiences, scope mappings, custom validators, or trusted issuers. Compare contracts and versions instead of assuming "same login server means any token works at every API."

## 35. Mistakes to Avoid

### Mistake 1 — Trusting Any Issuer Because Metadata Exists

An attacker can deploy a valid issuer of their own. Trusted issuers must be allowlisted before discovery.

### Mistake 2 — Taking `iss` from an Unverified JWT and Fetching Arbitrary JWKS

This can lead to trust injection/SSRF. Only route within an issuer allowlist; signature and issuer validators must verify after selecting the decoder.

### Mistake 3 — Confusing RFC 8414 URLs with OIDC Discovery URLs

For issuers with paths, well-known locations differ. Use the standard supported by the AS and the official discovery library.

### Mistake 4 — Trusting `jwks_uri` While Skipping Issuer Validation

JWKS is a key source; the JWT `iss` claim must still match the expected issuer.

### Mistake 5 — Treating Metadata `scopes_supported` as Caller Permissions

That is a list of capabilities, not the scopes granted in a specific token.

### Mistake 6 — Using `id_token_signing_alg_values_supported` as the Access-Token Alg Allowlist

That information applies to ID tokens. The access token contract must be independent.

### Mistake 7 — Accepting a JWT Just Because It Has `sub`

Unverified payloads can be tampered with. Even when signed, a token still needs audience, type/time/scopes.

### Mistake 8 — Accepting ID Tokens at an API

ID tokens are meant for OIDC clients. APIs require access tokens with the right audience and profile.

### Mistake 9 — Using `client_id` Instead of `aud`

A client can call multiple APIs. A token must be intended for the Resource Server itself.

### Mistake 10 — Not Checking `typ` When Required by Contract

One issuer signs multiple JWT types. Cross-JWT confusion can occur if relying solely on the signature.

### Mistake 11 — Letting an Untrusted Header Choose the JWT Algorithm

Only allow algorithms matching the key/issuer contract; never accept `none` for JWT bearer APIs.

### Mistake 12 — Using `jku`/`x5u` from a Token to Fetch Keys

Key URLs must come from trusted configuration/metadata, not from a caller-crafted token.

### Mistake 13 — Losing Default Checks When Adding an Audience Validator

Combine `JwtValidators.createDefaultWithIssuer(...)` with custom validators rather than accidentally wiping out issuer/timestamp policies.

### Mistake 14 — Backfilling Tenant/Audience for Tokens Missing Claims

That turns a contract-violating token into an API-accepted token. Renegotiate with the AS or reject.

### Mistake 15 — Accepting `active=true` for Every API

An opaque token can be active yet meant for a different resource. Enforce the AS contract for audience/resource binding.

### Mistake 16 — Failing to Distinguish Introspection Credentials from OAuth Caller Client ID

These two client IDs belong to different roles. Never compare them for equality arbitrarily.

### Mistake 17 — Hardcoding Keys and Forgetting Rotation

Old/new key mismatches cause outages; you need a JWKS/cache/rotation plan.

### Mistake 18 — Fabricating a Principal When Metadata/JWKS Times Out

That is *fail open*. A token cannot be trusted if it cannot be verified.

### Mistake 19 — Automatically Granting More Permissions When Metadata Changes

New scopes in metadata do not mean users hold those scopes. Authorization relies on the token and policy.

### Mistake 20 — Testing Only with `jwt()`/`mockJwt()`

Mocks do not prove signature/JWKS/issuer/audience checks. You need signed token integration tests.

### Mistake 21 — Treating Read Scope as Permission to View Every Record

Action permission does not replace object-level authorization, ownership, or tenant checks.

### Mistake 22 — Logging Raw Access Tokens and Secrets

Bearer tokens and introspection secrets are credentials. Never put them in logs, crash reports, or tickets.

### Mistake 23 — Ignoring Network/TLS/DNS and Egress Policy

Discovery/JWKS/introspection are outbound HTTP calls. They need appropriate truststores, timeouts, and retries/circuit breaking.

### Mistake 24 — Conflating Same-Subject Identities Across Multiple Issuers

`sub` must be interpreted within the issuer namespace; avoid mixing identities across issuers.

## 36. Issuer Integration Runbook for Orders API

**Step 1 — Record the trusted issuer:** Confirm the exact URL, environment, authority owner, and supported OIDC/OAuth metadata path.

**Step 2 — Read metadata:** Verify HTTPS/TLS, HTTP status, `issuer`, and `jwks_uri` or `introspection_endpoint`.

**Step 3 — Choose token mode:** JWT or opaque? If JWT, what signing key source and algorithms? If opaque, what introspection credentials and network contract?

**Step 4 — Lock down resource audience:** Does Orders API expect `aud=orders-api` or another identifier? Which resource does the OAuth client request tokens for?

**Step 5 — Lock down token type/profile:** Is RFC 9068 used, what is `typ`, how are `exp`/`nbf` required, are sender constraints used?

**Step 6 — Lock down permissions:** `scope`/`scp`/custom roles/permissions, authority prefix, tenant-scoped vs. global rights.

**Step 7 — Lock down identity:** `sub` namespace, service principals, tenant membership, claim conversions, and object-level authorization.

**Step 8 — Configure Spring Security:** `issuer-uri` or `jwk-set-uri` + validators, or opaque introspection + contract wrapper. Keep default deny.

**Step 9 — Negative testing:** Wrong issuer, audience, expired, invalid signature, wrong typ, wrong alg, missing claims, insufficient scope, cross-tenant access.

**Step 10 — Resilience testing:** JWKS rotation, AS outage, introspection timeout, changed metadata, clock skew, stale token.

**Step 11 — Observability:** 401/403 breakdown, metadata/JWKS HTTP latency, key-cache misses, issuer mapping, request ID; never log credentials.

**Step 12 — Change governance:** Maintain a contract version and rollout/rollback policy when the issuer changes signing alg, claims, keys, audience, or token format.

This process prevents treating metadata reading alone as proof that the Resource Server is secure.

## 37. An End-to-End Example

Suppose the AS publishes:

```text
Trusted issuer:
  https://login.example.test/realms/shop

Trusted JWKS:
  https://login.example.test/realms/shop/protocol/openid-connect/certs

Orders Resource Server:
  expected aud = orders-api
  accepted alg = RS256
  access-token type = at+jwt (per AS contract)
  required scope for GET orders = orders.read
```

The client sends:

```http
GET /api/orders/order-42
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

The JWT has:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "shop-a",
  "exp": 1900000000
}
```

The Resource Server must verify in logical order:

```text
1. Does the Bearer token have a supported format?
2. Does the JWS have a valid signature with a trusted key?
3. Is the signing algorithm allowed?
4. Does the JWT type/profile match the access-token contract?
5. Does iss match the trusted issuer?
6. Does aud contain orders-api?
7. Are exp/nbf and required claims valid?
8. Does Authentication have SCOPE_orders.read?
9. Is user-123 allowed to read order-42 in shop-a?
10. Does the response filter fields per policy?
```

**If steps 2–7 fail:** the token is not authenticated; typically responds with 401 per Bearer semantics.

**If step 8 fails:** the token is valid, but lacks operation permission; typically responds with 403.

**If step 9 fails:** the token is valid, but the resource is not authorized; responds with 403 or 404 per policy to avoid disclosing existence.

If a token has `aud=["payments-api"]`, even if both metadata and JWKS are correct, the Orders API must reject it. **Reading metadata properly is only a prerequisite for verifying tokens; it does not mean every token from the same issuer is a valid access token for the API.**

## 38. References

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata and well-known discovery for OAuth Authorization Servers.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `openid-configuration`, OpenID Provider metadata, and issuer discovery.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC ID token and differences from OAuth access tokens.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and registered claims.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set, and key properties.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS signatures and protected headers.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWT/JWE encryption model.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithms, issuer/key trust, and cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile, claims, and typ.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection for opaque/access tokens.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): requesting access tokens for a specific resource.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange/delegation when downstream tokens with a different audience are needed.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS sender-constrained tokens.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP sender constraints.
- [Spring Security Reference — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWKS, decoder, validators, and scope mapping.
- [Spring Security Reference — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and custom `OpaqueTokenIntrospector`.
- [Spring Security Reference — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, WebFlux issuer/JWKS.
- [Spring Security Reference — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): introspection in WebFlux.
- [Spring Security Reference — HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): action-level authorization after authentication.

**Conclusion:** Integrating an OAuth 2.0/OIDC issuer into a Spring Security Resource Server involves **two related but distinct contracts**. Metadata (RFC 8414/OIDC Discovery) helps identify the issuer, endpoints, and trusted JWKS/introspection infrastructure. The access token contract defines the JWT/opaque format, signing algorithms, type/profile, issuer, audience, time constraints, subject, scopes, tenant, and API-specific rules. The Resource Server must **trust the issuer before discovery**, verify the token before using claims, enforce the right audience and action/object authorization, and fail closed when metadata/JWKS/introspection cannot be verified. **A valid metadata document does not make every token from the same issuer a valid access token for the API.**