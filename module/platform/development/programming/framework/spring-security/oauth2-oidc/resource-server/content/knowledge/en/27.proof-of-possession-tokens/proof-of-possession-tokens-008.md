# `iat`, `jti`, `nonce`, and Replay Controls by Implemented Mechanism

In **Spring Security OAuth 2.0/OIDC Resource Server**, a valid access token can be copied and replayed multiple times if an attacker steals the token. With bearer tokens, this is inherent to the credential: the Resource Server accepts whoever presents a valid token per policy, without knowing whether the sender is the original device. Therefore, the system must clearly understand which claims and anti-replay controls actually work.

Three commonly seen names are **`iat`**, **`jti`**, and **`nonce`**. They are not three ways of spelling the same control:

- **`iat` (Issued At)** states when the JWT was issued. Applications can use it to enforce a maximum age on a token or proof, yet a timestamp by itself does not prevent a token from being replayed.
- **`jti` (JWT ID)** is the identifier of a JWT. It only helps detect replay when the verifier has a stateful mechanism to recognize IDs that have already been used or revoked.
- **`nonce`** is a random value used to bind a message/token to a specific transaction. OIDC uses `nonce` to bind an ID token to an authentication request; DPoP can use a server nonce to strengthen proof freshness. These two usages have different purposes and verification points.

In a **proof-of-possession (sender-constrained) token** system, those claims must be placed within the proper **proof-of-possession** mechanism such as **DPoP** or **mutual TLS (mTLS)**. Simply adding `iat`, `jti`, or `nonce` to a JWT access token does not turn a bearer token into a token bound to the client's private key.

> **Core rule:** validate timestamps, identifiers, and nonces according to the exact issuing protocol; if true replay protection is needed, you must have state or proof of key possession. Never treat the mere presence of a claim as proof that it was verified.

This lesson is part of the **Proof-of-Possession Tokens** chapter. It progresses from the semantics of each claim to bearer replay, OIDC nonces, DPoP proofs, mTLS certificate binding, implementation in Spring Security Servlet/WebFlux, what state must be stored, cache lifetimes, and testing.

## 1. Three Claims, Three Distinct Roles

| Claim | Standard Meaning | Used For | What It Cannot Do Alone |
|---|---|---|---|
| **`iat`** | Time the JWT was issued (NumericDate) | Limiting token/proof age, detecting anomalous timestamps | Does not prove a token is fresh just because the timestamp looks recent; does not stop replay |
| **`jti`** | Unique identifier of the JWT per issuer | Correlation/auditing, revocation denylist, one-time-use proof replay cache | Does not detect a second submission without state and policy |
| **`nonce`** | Random value bound to a transaction/challenge | Binding an ID token to an OIDC request; server challenge in DPoP | Not a replay database; does not replace signature, audience, expiry, or sender binding |

### 1.1. An Example to Distinguish Them

Illustrative JWT access token:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iat": 1893459000,
  "exp": 1893459600,
  "jti": "at-7c4e8d...",
  "scope": "orders.read"
}
~~~

Significant fields:

- `iat` indicates when the token was issued; the verifier can reject overly old tokens per policy.
- `exp` defines expiration; the token must not be accepted after this point, accounting for configured clock skew.
- `jti` names the token; if the AS/RS maintains a denylist or token-usage tracking, it serves as the lookup key.
- `aud` specifies which API may accept the token; never skip it just because `iss` and the signature match.

The token above is **still a bearer token**. If an attacker copies the entire JWT string, they can replay the same token to `orders-api` until it expires or the RS receives revocation state. `iat` does not prevent that. `jti` does not prevent it without replay/denylist state. Nor is `nonce` automatically present or meaningful for this access token.

## 2. `iat`: Issuance Time and Limiting Token Age

### 2.1. Semantics of `iat`

RFC 7519 defines `iat` as **Issued At**: the time at which the JWT was issued, expressed as a NumericDate (seconds since the Unix epoch, potentially fractional per specification). This claim can be used to determine the age of a JWT.

Example:

~~~json
{
  "iat": 1893459000,
  "exp": 1893459600
}
~~~

In the example, the token was issued at 10:10:00 and expires at 10:20:00 when converted to the corresponding UTC timestamps. The span between `iat` and `exp` is 10 minutes.

`iat` differs from `exp`:

- `iat` answers "when was the token issued?"
- `exp` answers "from when is the token no longer accepted?"
- `nbf` answers "before when is the token not yet accepted?"

Do not replace an `exp` validator with an `iat` check. A token with a recent `iat` can still be expired if `exp` is in the past; a token with a distant `exp` can still be too old under policy if `iat` is too far in the past.

### 2.2. Checking Future `iat` Values

If `iat` lies far in the future relative to the Resource Server's clock, possible causes include:

- Unsynchronized AS/RS clocks.
- A tampered token or one signed by the wrong source.
- NumericDate/time-zone configuration bugs.
- An issuer minting tokens with an inaccurate clock.

A valid signature does not rule out clock bugs. You may permit a **small, explicitly defined clock skew**, but never accept arbitrary future timestamps.

Example policy:

~~~text
now = 10:10:00
iat = 10:10:20
allowed future skew = 30 seconds
=> iat condition may pass

now = 10:10:00
iat = 10:30:00
allowed future skew = 30 seconds
=> reject
~~~

### 2.3. Enforcing Maximum Age

Some APIs require tokens newer than a threshold, e.g., tokens issued within the last 15 minutes. Policy:

~~~text
iat <= now + allowedFutureSkew
AND
now - iat <= maxTokenAge + allowedClockSkew
~~~

This is an additional **freshness** constraint. It can limit how long a stolen token remains usable, yet does not stop replay inside that window. An attacker replaying a 30-second-old token still satisfies a 15-minute max-age rule.

### 2.4. `iat` Does Not Replace `exp`

Anti-pattern:

~~~java
if (jwt.getIssuedAt().isAfter(Instant.now().minusSeconds(300))) {
    accept(jwt);
}
~~~

This snippet checks only that the token was issued within 5 minutes; it skips signature, issuer, audience, expiry, not-before, and scopes. An expired JWT with a recent `iat` must still be rejected. Likewise, a token with an older `iat` yet a future `exp` may be rejected by a max-age policy.

### 2.5. `iat` in a DPoP Proof

In DPoP (RFC 9449), the `iat` of the **proof JWT** helps the RS/AS determine whether the proof is fresh enough. Proofs are typically accepted only within a short time window. That is a per-HTTP-request proof freshness check, distinct from the `iat` of a longer-lived access token.

Do not confuse them:

| Location of `iat` | Meaning |
|---|---|
| Access token JWT | When the token was issued; can enforce policy-based max token age |
| OIDC ID token | When the authentication token was issued by the OP; RP checks timing per OIDC |
| DPoP proof JWT | When the proof of key possession for the HTTP request was created; RS checks proof window |
| Client assertion JWT | When the client authentication assertion was created; AS checks freshness/replay per profile |

A validator written for access tokens must not blindly apply the same thresholds to DPoP proofs, ID tokens, and client assertions.

## 3. `jti`: JWT Identifier and Limits of Replay Detection

### 3.1. `jti` Is an Identifier, Not a Stateful Mechanism

RFC 7519 defines `jti` as the JWT ID, an identifier for the JWT. The issuer should ensure values are sufficiently unique to avoid collisions. This claim is useful for:

- Correlation/auditing of a specific token.
- A denylist when a token is revoked.
- Detecting reused proof JWTs.
- Replay prevention for one-time assertions, if the verifier records used IDs.

However, merely adding `jti` to a payload does not stop a second request. If the RS processes tokens completely statelessly, it has no way to know whether `jti` appeared in an earlier request.

### 3.2. Two Different Policies: Denylist vs. One-Time Use

**Denylist/revocation**:

~~~text
token jti = J
store contains (issuer, J) -> revoked
=> reject
~~~

**One-time-use replay cache**:

~~~text
proof jti = P
first use: atomically record P -> accept
second use: P already exists -> reject
~~~

These are two distinct policies:

- A denylist stores revoked tokens; tokens absent from the store can still be used multiple times while valid.
- A replay cache stores already-used proofs; a used proof must not be accepted a second time within the anti-replay window.

Do not apply one-time use to standard OAuth access tokens if the protocol/client is designed to reuse that token across requests. Bearer access tokens are normally reused throughout their lifetime; blocking every second use breaks that contract. To prevent replay of stolen bearer tokens, use sender-constrained tokens or an appropriate revocation/freshness policy.

### 3.3. Namespace `jti` by Issuer

Two different issuers can both mint `jti=12345`. Therefore, never use `jti` alone as a global key.

Logical keys:

~~~text
revocation-key = (verified-issuer, jti)
proof-replay-key = (proof-key-thumbprint, jti)
~~~

Depending on proof type, additional client/tenant/endpoint namespacing may be needed. Crucially, the key must be constructed from **verified information**, never from an arbitrary issuer inside an unverified token.

### 3.4. Collisions, Entropy, and Issuance

Issuers should generate `jti` using a cryptographically secure random source or an identifier scheme with negligible collision probability over the token issuance volume. Do not use predictable counters if token IDs could be abused to probe or guess cache entries. `jti` does not need to be secret to function as an identifier, but it must not leak sensitive internal information in its value.

### 3.5. Atomicity in the Replay Cache

If two identical requests arrive concurrently, this approach:

~~~text
if not exists(jti):
    insert(jti)
    accept
else:
    reject
~~~

has a race condition if checking and inserting are non-atomic. Both requests can simultaneously observe "does not exist" and both get accepted.

You must use an **atomic insert-if-absent / SET NX / unique constraint** operation:

~~~text
insert-if-absent(key, ttl)
  inserted = true  -> first use, accept
  inserted = false -> replay, reject
~~~

In multi-instance systems, the replay store must be shared or strongly synchronized. A local cache inside each pod cannot detect a proof replayed to another pod.

### 3.6. Replay Entry TTL

A replay entry must live at least until the proof is no longer valid:

~~~text
entry TTL >= maxProofAge + allowedClockSkew
~~~

Or, if the verifier computes a specific proof expiration timestamp:

~~~text
entry TTL = proofExpiry - now + safetyMargin
~~~

Do not retain entries indefinitely, as that grows memory/storage. Do not set a TTL shorter than the proof acceptance window, or an old proof can be replayed after the entry expires while its timestamp is still accepted.

## 4. `nonce`: Binding a Token/Proof to a Transaction

A `nonce` is a value typically generated randomly by the recipient or client per protocol. It helps prove that a message was created in response to a specific transaction/challenge rather than simply being a pre-issued valid token.

However, `nonce` has multiple contexts:

1. **OIDC nonce:** The RP generates a value in the authentication request and checks that the returned ID token contains the exact same value.
2. **DPoP server nonce:** The AS/RS issues a challenge so the client includes the nonce in its next DPoP proof.
3. **A nonce from another protocol:** Meaningful only according to that protocol's specification.

Never substitute an OIDC nonce for a DPoP nonce, or treat an arbitrary `nonce` claim inside an access token as proof that the current request is fresh.

## 5. OIDC Nonce: Binding an ID Token to an Authentication Request

### 5.1. OIDC Flow

When initiating OpenID Connect authentication, the RP can generate a random nonce and store it tied to the authentication transaction:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as OIDC Relying Party
    participant OP as OpenID Provider
    RP->>RP: Generate random nonce N
    RP->>RP: Store N with auth transaction
    B->>OP: Authorization request + nonce=N
    OP-->>B: Redirect with authorization response
    B->>RP: Authorization code
    RP->>OP: Token request
    OP-->>RP: ID token with nonce=N
    RP->>RP: Verify ID token signature/iss/aud/time
    RP->>RP: Compare ID token nonce with stored N
    RP-->>B: Complete login if all checks pass
~~~

The nonce binds **the received ID token** to the request initiated by the RP. If an attacker replays an ID token from an older authentication transaction, the nonce will not match the active transaction.

### 5.2. Exact Verification

If the RP sent `nonce=N` in the authorization request, OIDC Core requires the corresponding ID token to carry a `nonce` claim with the **exact same value**. The RP must store the expected value securely and compare it when processing the response.

Do not:

- Accept a missing nonce when the request sent a nonce.
- Compare partially, by prefix, or arbitrarily case-insensitively.
- Use a static nonce across all logins.
- Read the expected nonce from an attacker-controlled callback query parameter.
- Reuse a nonce after the transaction has completed.

Nonces should have sufficient randomness, be tied to the transaction, and be consumed once. Storage/cleanup must account for multiple tabs and concurrent logins.

### 5.3. OIDC Nonce Is Not `state` or PKCE

These values protect different parts of the flow:

| Mechanism | Creator | Binding | Purpose |
|---|---|---|---|
| `state` | OAuth/OIDC client | Authorization response to request/transaction | Mitigates CSRF and flow mix-up |
| `nonce` | OIDC RP | ID token to authentication request | Mitigates ID token replay/mix-up |
| PKCE verifier/challenge | OAuth client | Authorization code to the client that started the flow | Prevents code interception/injection |
| DPoP nonce | AS/RS | DPoP proof to a recent server challenge | Improves freshness, mitigates certain replays |

Do not drop one mechanism just because another is enabled. In the authorization code flow, use PKCE per modern best practices; use `state` to bind transactions; use OIDC `nonce` when using OIDC and validating ID tokens.

### 5.4. OIDC Nonces Are Checked at the RP, Not the Resource Server

In a standard architecture:

- `oauth2Login()` / the OIDC client handles the authorization response, ID token, and nonce.
- The Resource Server handles access tokens sent via `Authorization: Bearer`.

The Resource Server must not demand an OIDC `nonce` in every access token merely because the API integrates with OIDC. Access tokens and ID tokens follow different profiles; the OIDC nonce serves the RP's authentication transaction.

If an API accepts a custom token protocol featuring a nonce, explicitly define the issuer, audience, transaction binding, storage, and replay semantics. Never infer from OIDC Core that every access token must contain a nonce.

## 6. Bearer Token Replay and Sender-Constrained Tokens

### 6.1. Why Can Bearer Tokens Be Replayed?

Bearer tokens carry possession semantics: whoever holds the token can present it. If an attacker obtains the token from:

- Browser storage / XSS.
- A compromised mobile device.
- Reverse proxy / application logs.
- Trace / APM / error reports.
- URLs, query strings, or referrers.
- Networks lacking TLS protection.
- An intermediate service with read access to headers.

then the attacker can resend that token to the API. `iat` and `exp` bound the window, yet do not prove the sender is the original client.

### 6.2. Controls by Layer

| Control | Effect | Limitation |
|---|---|---|
| TLS | Protects tokens in transit | Does not prevent theft at endpoints/logs/storage |
| Short access-token lifetime | Limits replay duration | Does not prevent replay within lifetime |
| `jti` denylist | Revokes specific tokens | Requires state and lookup |
| Proof replay cache | Blocks reuse of the same proof | Must be atomic, distributed, and properly TTL'd |
| OIDC nonce | Binds ID token to login request | Does not bind bearer API requests |
| DPoP | Binds access token to public key and per-request proofs | Client must protect private key; RS must verify proof/replay |
| mTLS-bound token | Binds token to client certificate | Requires PKI/TLS client auth and proper implementation |

### 6.3. Key-Bound Tokens Change the Model

With bearer tokens:

~~~text
Whoever has the token -> can try using the token
~~~

With sender-constrained tokens:

~~~text
Whoever has the token + the matching private key/certificate
    -> can produce evidence accepted by the RS
~~~

DPoP uses a public/private key at the HTTP application layer; mTLS uses a client certificate at the TLS layer. `iat`, `jti`, and `nonce` support proof freshness/replay handling, while `cnf` or certificate thumbprints bind the token to the key.

## 7. DPoP: `iat`, `jti`, `htm`, `htu`, `ath`, and `nonce`

**Demonstrating Proof of Possession (DPoP)** per RFC 9449 is the OAuth mechanism to sender-constrain an access token to a client's public key. The client creates a DPoP proof JWT and sends it with each request; the proof is signed with the private key, and the public key resides in the proof header.

### 7.1. DPoP Proof Header

Illustrative example:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-x-coordinate",
    "y": "public-y-coordinate"
  }
}
~~~

The header contains the public JWK (never the private key). `typ` and the algorithm must satisfy RFC 9449; never accept `none` or an insecure client-chosen algorithm.

### 7.2. DPoP Proof Payload

Example:

~~~json
{
  "jti": "proof-unique-9f2a",
  "htm": "GET",
  "htu": "https://api.example.com/orders/123",
  "iat": 1893459000,
  "ath": "base64url-sha256-of-access-token",
  "nonce": "server-issued-nonce"
}
~~~

Core claims:

- `jti`: unique identifier of the proof; RS/AS can use it to detect proof replay.
- `htm`: HTTP method of the request, e.g., `GET`; must match the actual request.
- `htu`: HTTP target URI per DPoP rules; must match the request URI after proper proxy/normalization handling.
- `iat`: proof creation timestamp; RS/AS enforces a freshness window.
- `ath`: access token hash bound to the proof when calling a Resource Server.
- `nonce`: challenge issued by the AS/RS when nonces are enabled.

A DPoP proof is **one proof per HTTP request**. The client generates a fresh proof for each new request rather than reusing the same proof JWT across requests.

### 7.3. Request Headers

When calling a Resource Server, the client sends both the access token and the proof:

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN
DPoP: SIGNED_DPOP_PROOF_JWT
~~~

For a DPoP-bound access token, the authorization scheme is `DPoP` per RFC 9449—do not simply treat it as an unbound bearer token.

### 7.4. Verification at the Resource Server

The RS must verify the proof per RFC 9449 and token binding:

1. The DPoP JWT signature is valid against the public JWK in the proof header.
2. `typ` is `dpop+jwt` and `alg` is an accepted algorithm.
3. The public key thumbprint matches `cnf.jkt` in the verified access token.
4. `htm` matches the request method.
5. `htu` matches the target URI per DPoP normalization rules.
6. `iat` is within the allowed freshness window.
7. `jti` has not appeared in the replay cache for the corresponding key/proof namespace.
8. `ath` matches the hash of the presented access token.
9. If a server nonce is required, `nonce` matches a valid, active nonce.
10. The access token still passes independent issuer/audience/time/scope validation.

Checking only the proof signature is insufficient. A validly signed proof created for `POST /orders/123` cannot be reused for `GET /orders/123` when `htm` is checked; proofs for another URI must also be rejected.

### 7.5. Why Is `ath` Needed?

A proof key may be used to sign many proofs. `ath` binds a specific proof to the access token being sent. Without checking `ath`, a valid proof could be transplanted onto another token in improperly bound scenarios. The RS must compute the hash using the RFC 9449 algorithm/rules, rather than hashing arbitrary token representations.

### 7.6. `cnf.jkt` Binds the Access Token to the Key

A DPoP-bound access token may contain:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "sub": "user-842",
  "cnf": {
    "jkt": "thumbprint-of-client-public-jwk"
  },
  "scope": "orders.read"
}
~~~

`cnf.jkt` is the public key's thumbprint. The RS computes the thumbprint from the JWK in the DPoP proof and compares it with the verified claim in the access token. If they mismatch, someone holding only the access token without the corresponding private key cannot prove authorization to use the token.

### 7.7. DPoP Server Nonces

The AS/RS can issue a nonce for the client to include in its next proof. Conceptual flow:

~~~mermaid
sequenceDiagram
    participant C as DPoP Client
    participant RS as Resource Server
    C->>RS: Access token + DPoP proof (no/old nonce)
    RS-->>C: DPoP-Nonce challenge
    C->>C: Create fresh proof with nonce
    C->>RS: Same operation + new proof + server nonce
    RS->>RS: Verify signature, htm, htu, iat, jti, ath, nonce
    RS-->>C: Resource response if valid
~~~

Nonces must be issued and verified per RFC 9449, with appropriate lifetimes and scopes. A server nonce does not replace a `jti` replay cache in all deployments; nonces ensure proofs answer a recent server challenge, while replay detection tracks used proof IDs.

### 7.8. DPoP `jti` Is Not the Access-Token `jti`

A DPoP request can carry:

- `jti` in the **access token JWT**: identifies the access token.
- `jti` in the **DPoP proof JWT**: identifies the proof for the HTTP request.

The two values have different lifecycles and purposes. The proof replay cache must use the proof's `jti` (with proper namespace/key binding); an access-token denylist must use the access token's `jti` scoped by issuer. Never share a single cache key without distinguishing token types.

## 8. mTLS-Bound Access Tokens

**OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens** (RFC 8705) defines how to bind an access token to a client certificate. In this model, the token may contain a confirmation claim:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "sub": "service-order-worker",
  "cnf": {
    "x5t#S256": "base64url-certificate-thumbprint"
  },
  "scope": "orders.reconcile"
}
~~~

The Resource Server:

1. Validates the access token.
2. Retrieves the client certificate verified on the TLS connection.
3. Computes the certificate's SHA-256 thumbprint per RFC 8705.
4. Compares it against `cnf.x5t#S256`.
5. Rejects if the certificate mismatches or is absent per policy.

An attacker who copies only the access token without the client certificate's private key cannot complete matching TLS client authentication.

### 8.1. How mTLS Differs from DPoP

| Property | DPoP | mTLS-Bound Token |
|---|---|---|
| Proof key | Client's public/private JWK | Private key of X.509 client certificate |
| Where is the proof? | DPoP JWT in HTTP header | TLS handshake / client certificate |
| Request binding | `htm`, `htu`, `ath`, `jti`, `iat`, optional nonce | TLS connection and certificate thumbprint |
| Replay control | Proof freshness + replay cache/nonce | Certificate-bound transport; TLS protects each connection |
| Infrastructure | Client generates/signs DPoP proofs | Requires PKI, certificate issuance/rotation, and TLS client auth |
| Proxies | Must handle URI/method/headers accurately | Must preserve/delegate trust of client cert across TLS terminator |

Never treat mTLS `cnf` as a claim only for logging. The RS must actually verify the certificate and compare thumbprints.

### 8.2. TLS Termination at Reverse Proxies

If TLS terminates at a load balancer/proxy, the backend application may not directly see the client certificate. A trust contract is then required:

- The proxy authenticates the client certificate.
- The proxy strips any caller-supplied forwarded certificate headers.
- The proxy attaches a protected internal header or forwards certificate identity via a trusted mechanism.
- Network policy prevents callers from bypassing the proxy to reach the backend directly.
- The application trusts headers only from authenticated proxies.

Without protecting this boundary, an attacker can send a forged `X-Client-Cert` header to spoof certificate binding.

## 9. Spring Security: Checking `iat` on JWT Access Tokens

Spring Security Resource Server uses `JwtDecoder` and `OAuth2TokenValidator<Jwt>` to validate JWTs. Default validators typically check the issuer and standard timestamps like `exp`/`nbf`; **enforcing a max age via `iat` is an additional policy** the application must define if needed.

### 9.1. Validator Checking `iat` and Max Age

Example for Servlet JWT Resource Server:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class IssuedAtValidator implements OAuth2TokenValidator<Jwt> {

    private final Clock clock;
    private final Duration maxAge;
    private final Duration allowedFutureSkew;

    public IssuedAtValidator(
            Clock clock,
            Duration maxAge,
            Duration allowedFutureSkew) {
        this.clock = clock;
        this.maxAge = maxAge;
        this.allowedFutureSkew = allowedFutureSkew;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant issuedAt = jwt.getIssuedAt();
        if (issuedAt == null) {
            return failure("Missing iat");
        }

        Instant now = clock.instant();
        if (issuedAt.isAfter(now.plus(allowedFutureSkew))) {
            return failure("iat is too far in the future");
        }

        if (issuedAt.isBefore(now.minus(maxAge).minus(allowedFutureSkew))) {
            return failure("Access token is too old");
        }

        return OAuth2TokenValidatorResult.success();
    }

    private OAuth2TokenValidatorResult failure(String description) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", description, null));
    }
}
~~~

Combine the validator with issuer/default validators and audience:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(trustedJwkSetUri)
    .build();

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(expectedIssuer);

OAuth2TokenValidator<Jwt> audience = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

OAuth2TokenValidator<Jwt> issuedAt =
    new IssuedAtValidator(
        Clock.systemUTC(),
        Duration.ofMinutes(15),
        Duration.ofSeconds(30));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        defaults, audience, issuedAt));
~~~

`expectedIssuer`, `trustedJwkSetUri`, and audience must come from managed configuration. Signing algorithms must also be restricted per issuer contract. Values like `maxAge=15 minutes` and 30-second skew are illustrative policies; there is no universal setting for all systems.

### 9.2. Why Inject `Clock`?

Injecting `Clock` makes time-based policies testable at fixed instants without waiting. Use `Clock.systemUTC()` in production, and `Clock.fixed(...)` in tests to deterministically test fresh vs. stale tokens.

### 9.3. Do Not Confuse an `iat` Validator with Replay Prevention

Two requests carrying the same access token share the same `iat`. While the token remains within the max-age window, both pass the validator. That is normal for reusable bearer access tokens. To reject revoked tokens, use a denylist; to make DPoP proofs single-use, use a replay cache on the proof `jti`.

### 9.4. Missing or Mistyped `iat`

If policy requires `iat`, tokens lacking the claim must be rejected. Parsers/decoders may reject mistyped claims before the validator runs; never coerce arbitrary strings into timestamps. For legacy issuers that omit `iat`, make a controlled compatibility decision with a deprecation timeline; never silently accept missing claims when your threat model requires max-age checks.

## 10. Spring Security: `jti` Denylist for Access Tokens

An access-token `jti` can support revoking specific tokens. To use it:

1. The AS mints a sufficiently unique `jti`.
2. The Resource Server verifies the JWT first.
3. The RS extracts `iss`, `jti`, and `exp` from the verified `Jwt`.
4. The RS checks `(iss, jti)` in the revocation store.
5. If an entry exists, authentication is rejected.

### 10.1. Store Interface for Servlet

~~~java
public interface RevokedAccessTokenStore {
    boolean isRevoked(String verifiedIssuer, String jwtId);
}
~~~

A manager can wrap the JWT manager:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;

public final class RevocationCheckingAuthenticationManager
        implements AuthenticationManager {

    private final AuthenticationManager delegate;
    private final RevokedAccessTokenStore revokedStore;

    public RevocationCheckingAuthenticationManager(
            AuthenticationManager delegate,
            RevokedAccessTokenStore revokedStore) {
        this.delegate = delegate;
        this.revokedStore = revokedStore;
    }

    @Override
    public Authentication authenticate(Authentication request) {
        Authentication authenticated = delegate.authenticate(request);

        if (!(authenticated instanceof JwtAuthenticationToken jwtAuth)) {
            throw new BadCredentialsException(
                "Expected a verified JWT authentication");
        }

        var jwt = jwtAuth.getToken();
        if (jwt.getIssuer() == null || jwt.getId() == null) {
            throw new BadCredentialsException(
                "Verified issuer and jti are required");
        }

        boolean revoked = revokedStore.isRevoked(
            jwt.getIssuer().toString(), jwt.getId());

        if (revoked) {
            throw new BadCredentialsException("Access token revoked");
        }
        return authenticated;
    }
}
~~~

This is a synchronous pattern for Servlet. `delegate` must be a manager using a decoder that already validates signature/issuer/audience/time. The store should be indexed/cached by issuer and `jti`, with TTL bounded to `exp` plus clock skew. If the store fails, policies for sensitive APIs typically fail closed or return service-unavailable; never turn a database error into "not revoked."

### 10.2. Never Use an Unverified `jti`

Do not do this:

~~~java
String jti = parseUnverifiedJwt(bearer).get("jti");
if (revocationStore.contains(jti)) {
    reject();
}
// Otherwise trust the token!
~~~

This both skips token validation and lets an attacker control the lookup key. Even if a denylist lookup occurs after parsing for routing optimization, results are meaningful only after the token is verified and the issuer namespace is trusted.

### 10.3. TTL and Cleanup

If an access token expires at `exp`, the denylist entry can be evicted after:

~~~text
exp + acceptedClockSkew + smallSafetyMargin
~~~

If evicted before the RS stops accepting the token (e.g., validator allows 60 seconds of clock skew while denylist TTL stops at `exp`), a revoked token could slip through during the skew window. Synchronize TTL with actual time validation policies.

### 10.4. A `jti` Denylist Is Not a One-Time Access Token

An unrevoked token can be used multiple times. The store above asks only "has this token been revoked?", not "has this token ever appeared before?". If every access token must be strictly single-use, you need a specialized protocol/contract, stateful consumption, and client retry/idempotency handling; do not apply that by default to standard OAuth bearer access tokens.

## 11. DPoP Replay Cache and Spring Security Integration

DPoP requires the verifier to check proofs per request. The proof's `jti` must be tracked so the same proof cannot be replayed within the acceptance window.

### 11.1. Proof Replay Store

Conceptual interface:

~~~java
public interface DpopProofReplayStore {
    boolean markIfNew(String key, Duration ttl);
}
~~~

Return value:

- `true`: the key did not exist and was atomically recorded; the proof may proceed if all other checks pass.
- `false`: the key already existed; the proof is a replay and must be rejected.

The key can be built from:

~~~text
key = thumbprint(public JWK) + ":" + proof.jti
~~~

Do not use `jti` alone across multiple clients/keys. The thumbprint must be computed from an RFC-validated and canonicalized JWK, never from an arbitrary header string.

### 11.2. Verifier Pseudocode

~~~text
verifyDpopRequest(request, accessToken, proof):
    parse proof JWT under size/format limits
    verify proof signature with proof public JWK
    require typ = dpop+jwt
    validate allowed asymmetric algorithm
    validate htm == actual HTTP method
    validate htu == normalized external request URI
    validate iat within freshness window
    validate nonce if server nonce policy is enabled
    validate ath == hash(accessToken)

    decode and validate access token independently
    require accessToken.cnf.jkt == thumbprint(proof.publicJwk)

    key = thumbprint(proof.publicJwk) + ":" + proof.jti
    if replayStore.markIfNew(key, proofWindow) == false:
        reject replay

    continue with scope and domain authorization
~~~

Execution order can be optimized by cost, but never record `jti` as a valid proof before required bindings are verified. If an attacker can send junk proofs to claim another client's `jti`, the replay store can be poisoned/DoS'd. Key namespacing and validation order matter.

### 11.3. Atomic Replay Checks

A Redis implementation can use the equivalent of `SET key value NX EX seconds` to guarantee atomic check-and-set. In a database, use a unique constraint/insert transaction. Never use:

~~~java
if (!redis.exists(key)) {
    redis.set(key, value, ttl);
}
~~~

because two concurrent requests can both pass `exists` before either writes.

### 11.4. Reverse Proxies and `htu`

DPoP `htu` binds the proof to the request URI. If the app sits behind a reverse proxy:

- External `Host`, scheme, and path may differ from the backend URI.
- `Forwarded`/`X-Forwarded-*` headers must be trusted only from configured proxies.
- Never let clients inject forwarded hosts to make URI validation match a forged proof.
- Normalize URIs strictly per RFC 9449 without adding queries/fragments or custom canonicalization.
- Test path encoding, ports, schemes, and proxy rewrites.

If the resolver uses the backend URI while the client signed the public URI, all valid DPoP requests may be rejected. Conversely, trusting arbitrary forwarded headers lets an attacker get proofs validated against the wrong URI.

### 11.5. Does Spring Security Have Built-In DPoP or Need an Extension?

DPoP support varies by Spring Security version and Authorization Server/Resource Server integration. Never assume a standard `oauth2ResourceServer().jwt()` setup automatically:

- Reads the `DPoP` header.
- Verifies the proof JWT.
- Checks `cnf.jkt`.
- Checks `ath`, `htm`, `htu`, and nonces.
- Uses a distributed replay store.

Check your exact version and provider. If your stack lacks full built-in DPoP support, integrate an RFC 9449-compliant implementation into the authentication pipeline before issuing an `Authentication`, or use a supporting gateway/resource server. Never write a filter that merely parses `jti` and call it DPoP.

## 12. Spring Security WebFlux: Handling Non-Blocking Stateful Replay Checks

In WebFlux, `ReactiveJwtDecoder` and `ReactiveAuthenticationManager` validate tokens in a reactive chain. When adding a denylist or replay store, lookups must be composed asynchronously.

### 12.1. Reactive Revocation Store

~~~java
public interface ReactiveRevokedAccessTokenStore {
    Mono<Boolean> isRevoked(String verifiedIssuer, String jwtId);
}
~~~

A `ReactiveAuthenticationManager` wrapper can do:

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;
import reactor.core.publisher.Mono;

public final class RevocationCheckingReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveAuthenticationManager delegate;
    private final ReactiveRevokedAccessTokenStore revokedStore;

    public RevocationCheckingReactiveAuthenticationManager(
            ReactiveAuthenticationManager delegate,
            ReactiveRevokedAccessTokenStore revokedStore) {
        this.delegate = delegate;
        this.revokedStore = revokedStore;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        return delegate.authenticate(request)
            .switchIfEmpty(Mono.error(
                new BadCredentialsException("No authentication result")))
            .flatMap(auth -> {
                if (!(auth instanceof JwtAuthenticationToken jwtAuth)) {
                    return Mono.error(new BadCredentialsException(
                        "Expected verified JWT authentication"));
                }

                var jwt = jwtAuth.getToken();
                if (jwt.getIssuer() == null || jwt.getId() == null) {
                    return Mono.error(new BadCredentialsException(
                        "Verified issuer and jti are required"));
                }

                return revokedStore.isRevoked(
                        jwt.getIssuer().toString(), jwt.getId())
                    .flatMap(revoked -> revoked
                        ? Mono.error(new BadCredentialsException(
                            "Access token revoked"))
                        : Mono.just(auth));
            });
    }
}
~~~

This is an illustrative reactive pattern; `Mono` and project interfaces must be provided. `delegate` must be a `JwtReactiveAuthenticationManager` backed by a `ReactiveJwtDecoder` configured with issuer/audience/time validators. Never invoke blocking Redis/DB calls on the Netty event loop and never call `subscribe()` inside the manager.

### 12.2. Reactive Replay Cache

For DPoP proofs, the interface might be:

~~~java
public interface ReactiveDpopProofReplayStore {
    Mono<Boolean> markIfNew(String proofKey, Duration ttl);
}
~~~

Pipeline:

~~~java
return verifyProofCryptographically(proof)
    .flatMap(verifiedProof -> {
        String replayKey = verifiedProof.keyThumbprint()
            + ":" + verifiedProof.jti();
        return replayStore.markIfNew(replayKey, proofTtl)
            .flatMap(firstUse -> firstUse
                ? Mono.just(verifiedProof)
                : Mono.error(new InvalidDpopProofException(
                    "DPoP proof replayed")));
    });
~~~

`verifyProofCryptographically` here represents a complete DPoP verifier; it is not a helper built into every Spring Security version. It must check headers, signatures, `htm`, `htu`, `iat`, `ath`, nonces, and access-token `cnf` per RFC 9449. The replay store is only **one part** of full validation.

### 12.3. Reactor Context Does Not Replace a Replay Store

Reactor Context carries the `SecurityContext` for reactive execution. It is not shared memory across requests/pods and cannot detect whether a `jti` was previously used. Never store sets of proof IDs in a request-local variable or Reactor Context and treat that as distributed replay protection.

## 13. DPoP Nonce vs. OIDC Nonce: Avoiding Confusion

| Property | OIDC `nonce` | DPoP Server `nonce` |
|---|---|---|
| Who creates it? | OIDC RP / client | AS or Resource Server |
| Bound to | Authentication request | DPoP proof / request |
| Where is it sent? | Authorization request, then appears in ID token | DPoP proof JWT |
| Who verifies it? | OIDC RP | DPoP verifier at AS/RS |
| Purpose | Binds ID token to login transaction, prevents replay/mix-up | Challenge/freshness for proof, strengthens anti-replay |
| Replaces `jti` replay cache? | No | Not necessarily; depends on policy, proof replay per RFC still needed |
| Used for regular access tokens? | Not by default | Only when required by DPoP flow |

A claim named `nonce` has no universal global semantics. Always identify the **token/proof profile** being processed before validating it.

## 14. Client Assertions and Replay Controls

Some OAuth clients use JWT client assertions to authenticate to the token endpoint. The assertion may contain `iss`, `sub`, `aud`, `exp`, `iat`, and `jti` per the applicable profile.

The AS can:

- Check that the audience matches the exact token endpoint.
- Require short assertion lifetimes.
- Check `iat` within an accepted window.
- Record `jti` to reject reused assertions.

This is **client authentication at the AS**, not access-token authentication at the Resource Server. Do not share a single replay cache between client assertions, DPoP proofs, and access tokens without separating namespaces/semantics.

If the AS does not record used `jti` values, a valid assertion may be replayable within its validity window depending on the contract. Client assertion profiles must be validated per the specific RFC/provider configuration.

## 15. Issuing Tokens and Proofs Properly

### 15.1. Issuer Minting Access Tokens

For JWT access tokens, the AS should:

- Issue `iat`, `exp`, and claims per the token profile.
- Mint sufficiently unique `jti` values when identification/revocation/auditing is needed.
- Set `aud` to the exact Resource Server.
- Never add an arbitrary `nonce` and claim the token cannot be replayed.
- When supporting sender-constrained tokens, attach `cnf` with the verified public key/certificate.
- Avoid issuing tokens with lifetimes longer than required by policy.

### 15.2. Client Creating DPoP Proofs

For each request:

1. Generate a fresh `jti`; never reuse an earlier proof.
2. Set `iat` near the current time.
3. Set `htm` to the exact method and `htu` to the exact target URI.
4. Set `ath` for the access token being sent to the RS.
5. Include the server's nonce if required by the server.
6. Sign the proof with the private key matching the key bound to the access token.
7. Send the access token and proof in the proper headers.

The private key must be protected in appropriate platform secure storage/keystore/HSM; if the private key is stolen, DPoP binding no longer stops that attacker.

### 15.3. Token Refresh and Key Rotation

If an access token is bound to DPoP key A, the new token after refresh may:

- Remain bound to key A per contract; or
- Be issued bound to a new key B through an AS-supported flow.

The client cannot modify `cnf.jkt` in the token. If the private key is lost/compromised, run a new token/key issuance flow and revoke old tokens per policy.

With mTLS, certificate rotation must also be coordinated between the AS and RS; old tokens bound to an old certificate thumbprint may stop working with a new certificate. Do not disable binding checks to ease transitions.

## 16. Common Implementation Mistakes

| Anti-pattern | Why It Is Wrong | Right Approach |
|---|---|---|
| Checking only a recent `iat` | Token can still be replayed within the window | Sender constraints or replay state |
| Assuming `jti` makes a token one-time-use | `jti` is only an identifier | Use an atomic store and token-appropriate policy |
| Using a per-pod local replay cache | Replay to another pod still succeeds | Distributed store / appropriate consistency |
| Using `jti` alone as cache key | Different issuers/clients/keys can collide | Namespace by verified issuer or proof key thumbprint |
| Replay entry TTL shorter than proof acceptance window | Proof replayed after entry expires | Derive TTL from freshness window + skew |
| Using an OIDC nonce for API bearer tokens | Nonce belongs to login transaction/ID token | Use access-token validation and sender constraints |
| Using a static nonce for every login | Not bound to an individual transaction | Random nonce per authentication transaction |
| Not comparing nonce in the ID token | Breaks request/response binding | RP checks exact match |
| Reusing a DPoP proof multiple times | Same proof can be replayed | Generate a fresh proof for every request |
| Verifying only the DPoP signature | Skips method, URI, token, freshness, key binding | Enforce full RFC 9449 validation |
| Not checking `ath` | Proof is not bound to the exact access token | Compute and compare access-token hash |
| Not checking `cnf.jkt` | Token can be used with another proof key | Compare JWK thumbprint against access token |
| Blindly trusting `X-Forwarded-Host` when checking `htu` | Attackers can manipulate URI binding | Trusted proxy configuration |
| Using access-token `jti` as proof `jti` | Mixes lifecycles and namespaces | Separate token IDs and proof IDs |
| Calling `block()` in WebFlux replay lookup | Blocks event loop | Reactive store and compose `Mono` |
| Accepting tokens when replay store times out | Cannot verify whether proof/token was revoked/replayed | Fail closed or return service error per SLA |
| Requiring an OIDC nonce in every access token | Confuses ID token profile with access token profile | Validate per exact token type |
| Thinking mTLS needs only the `cnf` claim | Fails to verify certificate at TLS | Compare thumbprint with verified certificate |

## 17. Testing Timestamps, Nonces, and Replay

A test suite must prove **which conditions are checked and what state is stored**. Checking only that a token contains a claim is insufficient.

### 17.1. `iat` Matrix

| Token/proof | Result |
|---|---|
| Current `iat`, future `exp`, valid issuer/audience | Passes freshness check |
| `iat` further in the future than skew | Reject |
| `iat` older than max age | Reject per policy |
| Missing `iat` when required by profile | Reject |
| Fresh `iat`, but past `exp` | Reject due to expiry |
| Valid `iat`, but invalid signature | Reject |
| Clock skew within configured threshold | Handled per policy |

Use `Clock.fixed(...)` for deterministic tests; never rely on `Thread.sleep`.

### 17.2. `jti` Matrix

| Scenario | Result |
|---|---|
| Two distinct access tokens with different `jti`s | Both can be valid |
| Access token `jti` in denylist for same issuer | Reject |
| Same `jti`, different issuer | Not confused as the same token |
| First use of DPoP proof `jti` | Can accept if all other checks pass |
| Second use of DPoP proof with same key + `jti` | Reject replay |
| Two concurrent requests with same proof | Only one wins atomic insert |
| Replay store unavailable | Fail closed or service error per policy |
| Replay entry TTL expires while proof is still in acceptance window | Test must catch broken TTL config |

### 17.3. OIDC Nonce Matrix

- Authorization request generates a random nonce N and stores it with the transaction.
- ID token with nonce N and valid issuer/audience/time/signature → RP completes login.
- ID token missing nonce when request sent nonce → reject.
- ID token nonce differs from N → reject.
- Repeated callback with already-consumed transaction → reject or handle idempotently per flow.
- Two login tabs have two distinct nonces; tab A's callback cannot use tab B's nonce.
- Never read the expected nonce from a callback query parameter.

### 17.4. DPoP Matrix

| Change in Proof/Request | Result |
|---|---|
| Invalid proof signature | Reject |
| `typ` is not `dpop+jwt` | Reject |
| Disallowed `alg` | Reject |
| `htm` differs from HTTP method | Reject |
| `htu` differs from target URI | Reject |
| `iat` too old / too far in the future | Reject |
| `jti` already used within replay window | Reject |
| `ath` does not match access token | Reject |
| JWK thumbprint differs from access token `cnf.jkt` | Reject |
| Nonce required, but missing/wrong | Reject/challenge per RFC |
| Fresh proof, valid token binding, valid scope | Can proceed to authorization |

### 17.5. MockMvc / WebTestClient and Integration Testing

`mockJwt()`/`jwt()` can inject a mock `Authentication` and bypass `JwtDecoder`, the DPoP verifier, or the replay store. They are useful for testing HTTP authorization after authentication, but they do not prove:

- The real `iat` validator ran.
- The `jti` store was invoked atomically.
- The OIDC nonce was compared against the stored transaction.
- DPoP `ath`, `htm`, `htu`, and `cnf.jkt` were checked.
- Replayed proofs are blocked across multiple application instances.

For Servlet, send test-key-signed Bearer tokens/JWTs through the filter chain. For WebFlux, send real requests via `WebTestClient` and compose the reactive manager/store. Use Redis/a test database or a fake store with atomic semantics to test concurrency. DPoP tests should use a test client key pair, proof signer, and the system's real verifier.

## 18. Operating Replay Protection in Distributed Systems

### 18.1. Consistency Matters More Than Just Having a Cache

Suppose:

~~~text
Request proof P -> RS instance A -> cache A: not found -> accept
Replay proof P  -> RS instance B -> cache B: not found -> accept
~~~

Local replay protection is insufficient. Instances must share a replay store or use a partitioning/routing scheme ensuring proofs in the same namespace are checked in a single place with strong enough consistency.

### 18.2. Availability and Fail-Closed Behavior

If the DPoP replay store is unreachable, the RS does not know whether a proof has already been used. Options:

- **Fail closed:** reject requests or return service-unavailable; appropriate when replay prevention is mandatory.
- **Fail open:** accept proofs despite being unable to check replay; increases availability at the cost of losing anti-replay guarantees during the outage.

This is a threat-model/SLA decision, not a cache detail. Never silently fail open.

### 18.3. Capacity and Cardinality

DPoP proofs can generate one entry per request. You need:

- Short TTLs sufficient to cover the proof window.
- Storage with adequate throughput.
- Key hashing/namespacing to avoid storing unnecessary sensitive data.
- Metrics for cache hits, replay rejections, store latency, and errors.
- Per-client/key rate limits to prevent replay-store exhaustion.
- Automatic TTL-based cleanup.

Never log full proof JWTs or private/public key material; log proof outcomes, truncated key thumbprints, and request correlation IDs per policy.

### 18.4. Idempotency Is Not Replay Prevention

A client may retry a legitimate HTTP operation after a timeout when it does not know whether the server processed it. DPoP replay prevention blocks **the same proof**; the client can generate a fresh proof for the retry. For a POST creating an order, a fresh proof would still execute the same business action again. Therefore, the API needs an **Idempotency-Key** or contract-defined business idempotency for non-repeatable operations.

Never use proof `jti` to replace a business idempotency key; the two mechanisms protect different layers:

- DPoP `jti`: the proof JWT cannot be reused.
- Idempotency key: a business operation is not executed twice due to retries.

## 19. Workflow for Choosing Controls by Requirement

| Requirement | Suitable Mechanism | What Must Be Implemented |
|---|---|---|
| Reject overly old tokens | `iat` + max-age validator | Clock, skew, max age, tests |
| Revoke specific JWTs before `exp` | `jti` denylist | Issuer-scoped store, TTL, consistency |
| Prevent replay of a DPoP proof | Proof `jti` replay cache | Atomic insert, TTL, distributed store |
| Bind ID token to login request | OIDC `nonce` | RP transaction storage and exact match |
| Strengthen DPoP proof freshness | DPoP server nonce | Issue/validate nonces per RFC 9449 |
| Prevent replay of stolen bearer tokens | DPoP or mTLS-bound tokens | Private key/certificate binding and RS enforcement |
| Revoke opaque access tokens | RFC 7662 introspection | `active`, audience/resource binding, cache TTL |
| Prevent retries from duplicating business actions | Idempotency key | Business store / atomic operation |

Do not pick `iat`, `jti`, or `nonce` merely because a claim is easy to add to a JWT. Start from the threat:

1. Can an attacker replay the **access token** or the **proof JWT**?
2. Do you need to block every second use or revoke specific tokens?
3. Do you need to prove the caller possesses a private key?
4. Does the server have shared state?
5. What is the maximum acceptable latency?
6. Which token profile governs the claim's semantics?

## 20. Conclusion

~~~text
iat
  = WHEN was this JWT issued?
  -> freshness / max-age / future-time validation
  -> does not stop replay by itself

jti
  = WHICH JWT/proof is this?
  -> audit / denylist / replay cache key
  -> needs state and atomic policy to detect reuse

nonce
  = WHICH transaction/challenge is this bound to?
  -> OIDC request <-> ID token
  -> DPoP server challenge <-> proof
  -> semantics depend on protocol

SENDER CONSTRAINT
  DPoP: cnf.jkt + signed per-request proof
  mTLS: cnf.x5t#S256 + authenticated client certificate

REPLAY DEFENSE
  freshness + correct binding + state/atomicity
  + distributed enforcement + explicit failure policy
~~~

`iat`, `jti`, and `nonce` are building blocks with distinct purposes. `iat` supports freshness checks; `jti` supplies an identifier for denylists or stateful detection of reused proofs; OIDC `nonce` binds an ID token to an authentication request. None of these claims alone proves the caller holds a key or turns a bearer access token into a one-time credential.

In a **proof-of-possession token** architecture, DPoP combines public-key binding (`cnf.jkt`) with per-request HTTP proofs, while mTLS binds tokens to a verified certificate (`cnf.x5t#S256`). The Resource Server must thoroughly verify signatures, audience, timestamps, request binding, token binding, and replay state according to the exact profile. With Spring Security, standard JWT validators provide the foundation; denylist/replay caches and DPoP/mTLS integrations must be wired explicitly into the authentication pipeline, especially keeping I/O non-blocking in WebFlux.

## References

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iat`, `jti`, `nonce`, `exp`, `nbf`, and NumericDate.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC authentication requests, ID Token validation, and `nonce`.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof JWTs, `jti`, `iat`, `htm`, `htu`, `ath`, nonces, and `cnf.jkt`.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication and `cnf.x5t#S256`.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): replay, sender-constrained tokens, and securing OAuth deployments.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, refresh tokens, and authorization grants.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer-token semantics and threat model.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): calculating JWK thumbprints used in key binding.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): checking token status.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, validators, and authorities.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and WebFlux authentication.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC client authentication and ID token processing.
- [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html): custom JWT claim validation.
