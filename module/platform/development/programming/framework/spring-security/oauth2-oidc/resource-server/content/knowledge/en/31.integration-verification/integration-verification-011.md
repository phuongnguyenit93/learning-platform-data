# DPoP or Key Binding When Supported by Version and Configuration

An OAuth 2.0 Bearer access token has one critical property: any party holding the token can present it to call an API, as long as the token remains valid and has sufficient permissions. If the token leaks through logs, browser storage, memory dumps, or a compromised dependency, someone else can use it until it expires or is revoked.

**Sender-constrained access tokens** reduce this risk by binding the token to a key that the client must prove it possesses when using the token. Two common mechanisms are:

- **DPoP (Demonstrating Proof of Possession):** the client signs a per-request proof JWT with its private key. The Resource Server verifies the proof and matches its public-key thumbprint against the token.
- **mTLS certificate-bound access tokens:** the client presents a certificate during mutual TLS authentication; the Resource Server matches the connection's certificate thumbprint against a confirmation claim in the token.

These mechanisms work only when the Authorization Server issues tokens following the right profile and the Resource Server actually verifies the proof/binding. Enabling JWT Resource Server, HTTPS, or mTLS on a connector **does not automatically prove tokens are key-bound**.

This lesson focuses on understanding DPoP per RFC 9449, contrasting it with mTLS, and verifying Spring Security version/configuration support. Exact API, DSL, and property names may vary across releases; verify capabilities on the exact version your project uses.

## 1. Why Bind Access Tokens to a Key?

With a standard Bearer token, the request carries only the token:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

The Resource Server verifies the token, then checks scopes and other policies. If an attacker steals the token string, they can replay an identical request from another machine.

With sender-constrained tokens, the client must prove possession of the private key bound to the token. A stolen token alone is insufficient to call the API if the attacker lacks the corresponding key.

| Mechanism | Proof Sent by Client on API Call | Binding in Access Token |
| --- | --- | --- |
| Bearer token | Access token only | No confirmation key required |
| DPoP | Access token + per-request signed DPoP proof JWT | `cnf.jkt`: public JWK thumbprint |
| mTLS certificate-bound | Access token + client certificate in TLS handshake | `cnf.x5t#S256`: X.509 certificate thumbprint |

Both DPoP and mTLS aim for proof of possession, yet use different key types and proof mechanisms. Never compare a JWK thumbprint directly against a certificate thumbprint.

### DPoP Does Not Replace TLS

DPoP protects token usage against standalone token theft. TLS remains mandatory to protect the confidentiality and integrity of HTTP requests, authenticate the server, and prevent eavesdropping or tampering in transit.

A DPoP proof does not encrypt the access token, does not replace TLS server certificate validation, and does not itself protect business data in responses.

## 2. How DPoP Works at the Protocol Level

DPoP is specified in RFC 9449. The client generates an asymmetric key pair and keeps the private key client-side. The public key goes into the DPoP proof JWT header. The client signs a fresh proof for each request it sends.

A DPoP proof has two parts:

**Protected header** typically contains:

- `typ` with value `dpop+jwt`.
- `alg` set to an accepted asymmetric signature algorithm.
- `jwk` holding the public JWK used to verify the proof; must contain no private key material.

**Payload** typically contains:

- `jti`: unique identifier of the proof.
- `htm`: HTTP method of the request.
- `htu`: target URI per DPoP rules, excluding query string and fragment.
- `iat`: proof creation timestamp.
- `ath`: hash of the access token when the proof is presented to a Resource Server.
- `nonce`: server-issued nonce if required by the server.

Illustrative payload at a Resource Server:

~~~json
{
  "jti": "proof-unique-id-7f8c",
  "htm": "GET",
  "htu": "https://orders.example.com/api/orders/123",
  "iat": 1794746400,
  "ath": "base64url-sha256-of-access-token",
  "nonce": "server-issued-nonce-if-required"
}
~~~

Illustrative protected header:

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

This is a structural example, not a validly signed proof. The public JWK contains only public parameters required for verification; private scalars/keys must never appear in the header.

## 3. Flow for Obtaining a DPoP-Bound Access Token

When requesting a token, the client sends a DPoP proof to the token endpoint. At this stage there is no access token yet to hash into `ath`, so proofs sent to the token endpoint omit `ath` as used at Resource Servers.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    C->>C: Create proof JWT with private key
    C->>AS: POST /token + DPoP proof
    AS->>AS: Verify proof signature, htm, htu, iat, jti, nonce
    AS->>AS: Compute JWK thumbprint (jkt)
    AS-->>C: Access token + token_type=DPoP
    Note over AS,C: Token is bound to the proof's public key
~~~

The Authorization Server can issue an access token carrying a confirmation claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "base64url-jwk-thumbprint"
  }
}
~~~

The `jkt` value is the JWK thumbprint computed per RFC 7638. It represents the public key inside the proof—not a hash of the full proof JWT, and not an X.509 certificate thumbprint.

The token response can set `token_type` to `DPoP`. The client must store the access token together with its matching private key. If the Authorization Server neither emits a confirmation binding nor returns the DPoP token type profile, do not treat the token as DPoP-bound merely because the token request included a proof.

## 4. Flow for Calling the Resource Server

When calling an API, the client presents the access token with the `DPoP` scheme and sends the proof in the `DPoP` header:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: DPoP <access-token>
DPoP: <signed-dpop-proof-jwt>
~~~

The Resource Server must verify both the access token and the proof. Conceptual sequence:

1. Identify that the request uses the `DPoP` authorization scheme.
2. Verify the access token per the issuer's profile: signature or introspection, issuer, audience, expiry, token type, and required claims.
3. Read `cnf.jkt` from the verified token.
4. Parse the DPoP proof and inspect its protected header, public JWK, `typ`, and `alg`.
5. Verify the proof signature using the public JWK inside the proof.
6. Compute the JWK thumbprint and compare it with `cnf.jkt` in the access token.
7. Validate `htm`, `htu`, `iat`, `jti`, and `ath`.
8. Validate `nonce` if required by the server.
9. Prevent replay by detecting whether `jti` was already used within the validity window.
10. Only then enforce scope/role, tenant, and object-level authorization.

~~~mermaid
flowchart TD
    A["Request: Authorization DPoP + DPoP proof"] --> B["Verify access token"]
    B --> C{"Valid token with cnf.jkt?"}
    C -- "No" --> X["Reject"]
    C -- "Yes" --> D["Verify DPoP proof signature"]
    D --> E["Compute JWK thumbprint"]
    E --> F{"Thumbprint matches cnf.jkt?"}
    F -- "No" --> X
    F -- "Yes" --> G["Validate htm, htu, iat, ath, nonce"]
    G --> H["Replay check jti"]
    H --> I{"Valid proof?"}
    I -- "No" --> X
    I -- "Yes" --> J["Scope, role, tenant, object policy"]
    J --> K["Process API"]
~~~

**Never skip one step simply because another passed.** A valid token signature does not prove the sender holds the client's private key. A valid proof signature does not prove the access token is accepted by the issuer.

## 5. DPoP Proof Claims

| Claim / Header | Where It Appears | Purpose |
| --- | --- | --- |
| `typ=dpop+jwt` | Protected header | Identifies the JWT proof type |
| `alg` | Protected header | Allowed signing algorithm |
| `jwk` | Protected header | Public key used to verify the proof |
| `jti` | Payload | Unique ID for replay protection |
| `htm` | Payload | HTTP method of the request |
| `htu` | Payload | Target URI normalized per DPoP rules |
| `iat` | Payload | Proof creation timestamp |
| `ath` | Payload at Resource Server | Binds proof to the presented access token |
| `nonce` | Payload when required by server | Binds proof to a recent server challenge |

### htm Must Match the HTTP Method

If the request is a GET, the proof must declare matching `htm`. A proof minted for GET cannot be reused to send a POST.

### htu Must Match the Target URI

`htu` binds the proof to the target URI under DPoP normalization rules. Query strings and fragments are excluded from `htu`. Scheme, host, port, and path must be computed strictly per the RFC.

Behind a reverse proxy, the application may see only an internal connection such as `http://service:8080`, while the client calls `https://orders.example.com`. If the two sides construct `htu` from different URIs, valid proofs get rejected—or misconfiguration can weaken URI verification.

Never trust `X-Forwarded-Host`, `Forwarded`, or `X-Forwarded-Proto` headers supplied directly by clients. Use forwarded metadata only from trusted proxies after the proxy strips spoofed headers and writes verified values. Configuring an explicit external base URL is often easier to control than inferring dynamically from requests.

### iat and jti

`iat` bounds proof age. The server needs reasonable clock skew to absorb minor drift without letting old proofs remain usable too long.

`jti` must be unique enough for the server to detect previously used proofs. Without replay detection, an attacker could capture a proof still inside its time window and replay it.

### ath Binds the Proof to the Access Token

At the Resource Server, `ath` is computed as:

~~~text
BASE64URL-NOPAD(SHA-256(ASCII(access_token)))
~~~

Java helper example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

final class DpopTokenHash {

    private DpopTokenHash() {
    }

    static String ath(String accessToken) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "SHA-256 is unavailable", exception);
        }
    }
}
~~~

Compare `ath` against the value computed from the exact access token in the Authorization header. Never hash `"Bearer "` or `"DPoP "` prefixes along with the token; the input is the raw token value per protocol rules. Never log the access token while debugging.

## 6. JWK Thumbprints and cnf.jkt

The Resource Server must prove that the public key used to sign the DPoP proof is the exact key the Authorization Server bound to the access token.

Sequence:

- Extract the public JWK from the proof header.
- Verify the proof signature with that key.
- Compute the JWK thumbprint per RFC 7638.
- Compare the thumbprint against `cnf.jkt` in the verified access token.

For RSA, EC, and other key types, the canonical member set for computing thumbprints differs per JWK rules. Never serialize the full JWK JSON directly and hash the raw JSON string; field ordering, whitespace, and extra metadata will alter the hash. Use an RFC 7638-compliant implementation.

Never use the self-declared public key inside the proof to verify the access token's signature unless a specific token profile/issuer mandates otherwise. In DPoP, the public JWK verifies the proof; the access token is verified via issuer keys or introspection. Those are two separate key roles.

## 7. Nonces and Replay Protection

A DPoP proof is a signed JWT, yet a valid signature alone does not stop replay. An attacker can copy a minted proof and resend it while it remains within the acceptance window unless the server tracks used `jti` values.

### Replay Cache

The Resource Server can store pairs such as issuer/key thumbprint and `jti` in a shared store with a TTL matching the proof acceptance window. When a valid proof is used the first time, record `jti` atomically; any subsequent request with the same `jti` must be rejected.

In multi-instance environments, an in-memory replay cache inside each pod is insufficient. An attacker can send the first request to pod A and replay it to pod B. Use a shared store or request partitioning with equivalent guarantees.

Bound cache capacity and TTL to prevent unbounded `jti` flooding. Do not keep replay entries longer than needed, yet never evict them before the proof's acceptance window expires.

### Server Nonces

The server may require clients to include a fresh server-issued nonce inside proofs. When the server returns `DPoP-Nonce`, the client mints a new proof containing that nonce and retries the request. Nonces must be verified per server policy; never reuse an old proof by tacking a nonce onto an HTTP header.

Nonces strengthen replay protection and freshness control. They do not replace signature validation, `htm`/`htu`, `ath`, or `jti` replay detection when required by the profile.

### Clock Skew

Clocks across clients, ingress proxies, Resource Servers, and Authorization Servers can drift. Synchronize NTP and set reasonable acceptance windows. Never widen the `iat` window excessively to hide clock issues; doing so expands the replay window.

## 8. Comparing DPoP, mTLS Certificate-Bound, and Bearer

| Attribute | Bearer | DPoP | mTLS Certificate-Bound |
| --- | --- | --- | --- |
| Proof of possession | No | Proof JWT signature | Client certificate in TLS handshake |
| Client key | Not required | Private key matching public JWK | Private key matching X.509 certificate |
| Confirmation claim | Not required | `cnf.jkt` | `cnf.x5t#S256` |
| API call headers | `Authorization: Bearer` | `Authorization: DPoP` and `DPoP` proof | Authorization token and mTLS client cert |
| Proof bound to HTTP method/URI | No | Yes, via `htm`/`htu` | Not in the DPoP sense |
| TLS client certificate required | No | No | Yes |
| Replay defense | Primarily token/transport | `jti`, time window, `nonce`, and `ath` | Relies on mTLS proof and operational profile |
| Best fit | Standard OAuth integrations | Clients able to hold keys and sign per-request proofs | Systems with PKI/mTLS and certificate management |

DPoP is often more practical when clients cannot or prefer not to present client certificates in TLS handshakes. mTLS suits backend-to-backend services, gateways, and environments with existing PKI. Choose based on client, issuer, Resource Server, proxy, and operational capabilities.

## 9. When Does Spring Security Support DPoP?

DPoP capability depends on the **Spring Security version**, relevant modules, the Authorization Server, and runtime configuration. Never infer support simply because a project includes `oauth2-resource-server` or a recent Spring Boot release.

Before writing configuration, verify both sides:

| Component | Questions to Confirm |
| --- | --- |
| OAuth Client | Does it generate DPoP proofs and store private keys securely? |
| Authorization Server | Does the token endpoint verify proofs and issue `token_type=DPoP`? |
| Token format | Do JWT/opaque tokens carry `cnf.jkt` per profile? |
| Resource Server | Does it support the `DPoP` authorization scheme and `DPoP` proof header? |
| Proof validator | Does it check `typ`, `alg`, JWK, signature, `htm`, `htu`, `iat`, `jti`, `ath`, and `nonce`? |
| Replay defense | Is there a suitable replay cache across multiple instances? |
| Reverse proxy | Is the external URI for `htu` resolved accurately? |
| Tests | Do integration tests verify token and proof together? |

### Inspect the Actual Resolved Version

Check the resolved version from Spring Boot's BOM or dependency management, not just what appears at first glance in build files. Spring Security Test, Resource Server, JOSE, and related OAuth modules should align on the same release train.

Check reference docs, release notes, and APIs for that exact version to confirm:
- Whether DPoP is supported on the Resource Server.
- Whether DPoP is supported on the Authorization Server/client.
- Where support is enabled in configuration.
- Whether extra dependencies or validators are required.
- Whether DPoP proofs are checked automatically in the security chain or require a separate component.
- Which token types and algorithms are supported.

Never copy a DSL or property from another release assuming it exists. Never invent placeholder properties such as `dpop-enabled` if the framework does not define them.

### Authorization Server and Resource Server Are Independent Pieces

An Authorization Server might issue DPoP-bound tokens while a Resource Server does not yet verify proofs. Conversely, a Resource Server might verify proofs while the issuer still emits Bearer tokens lacking `cnf.jkt`.

Enable DPoP mode only when client, issuer, and Resource Server all agree on the profile. If one link is missing, use another sender-constraining mechanism supported end-to-end, or keep the current Bearer policy with an appropriate risk assessment; never pretend binding is enforced when it isn't.

## 10. Configuring Spring Security Based on Actual Capabilities

No single YAML snippet or DSL works across every Spring Security version and Authorization Server. Exact configuration depends on the release and implementation. Follow this sequence:

1. Check the actual resolved dependency versions.
2. Read the official documentation for that exact version covering DPoP Resource Server and Authorization Server.
3. Confirm the token endpoint can issue DPoP-bound tokens.
4. Confirm the Resource Server accepts the `DPoP` scheme and proof header.
5. Configure trust/issuer/audience/algorithms as with other tokens.
6. Configure proof validation and replay protection.
7. Configure external URI/proxy handling if applicable.
8. Write integration tests before enabling the policy in production.

### If the Framework Has Built-In Support

Use the exact APIs published by that release. Verify:
- How DPoP is enabled.
- Whether `cnf.jkt` is verified automatically.
- Whether `ath`, `htm`, `htu`, and `nonce` are checked automatically.
- Whether a replay cache is provided or must be supplied by the application.
- How the `DPoP` scheme is handled differently from `Bearer`.
- How error responses and `DPoP-Nonce` headers are emitted.

Do not flip one toggle and overlook checks that the documentation leaves to application configuration.

### If the Framework Lacks Built-In Support

Three implementation paths exist:

- Upgrade to a compatible version that includes full support.
- Enforce DPoP at an API gateway or a dedicated, battle-tested security component.
- Integrate a maintained DPoP/JWT library with a clean adapter and test thoroughly against the RFC.

Writing a standalone filter checking only `htm` or proof signatures is insufficient for DPoP. You need token binding, `ath`, nonces, `jti` replay detection, URI normalization, algorithm allowlists, and proper failure handling.

Never automatically fall back from a DPoP-bound token to Bearer when a proof is missing or invalid. That defeats sender constraining.

## 11. Outlining Verification Order Inside the Resource Server

Whether using built-in support or an adapter, logical ordering must ensure data is trusted before use:

**Step A — Authenticate the access token**

- Parse the expected authorization scheme.
- Verify the signature or introspection response.
- Verify issuer, audience, expiry, and token profile.
- Confirm the token was issued under the DPoP profile.
- Extract `cnf.jkt` from the verified token.

**Step B — Verify the DPoP proof**

- Accept only `typ` `dpop+jwt`.
- Accept only asymmetric algorithms in the allowlist.
- Reject headers containing private key material or invalid JWKs.
- Verify the proof signature.
- Compute the JWK thumbprint and match against `cnf.jkt`.
- Validate `htm`, `htu`, `iat`, and `ath`.
- Validate `nonce` if required by policy.
- Record `jti` via replay protection.

**Step C — Authorization**

- Map scopes/permissions to `GrantedAuthority`.
- Enforce roles and functional permissions.
- Enforce tenant, owner, membership, and object-state rules.
- Invoke controller/service.

Never grant permissions from claims in an unverified proof. Never use the JWK inside the proof to verify the access token's issuer signature.

## 12. JWT vs. Opaque Tokens in DPoP

DPoP binding works regardless of whether the access token is a JWT or opaque. What matters is that the Resource Server obtains a trustworthy confirmation claim.

### JWT Access Tokens

The Resource Server verifies the JWT signature, issuer, audience, timestamps, and profile, then reads `cnf.jkt` from the verified claims.

### Opaque Access Tokens

The Resource Server calls the introspection endpoint. The response must supply active status and confirmation data per contract, for example:

~~~json
{
  "active": true,
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "base64url-jwk-thumbprint"
  }
}
~~~

If introspection returns `active=true` without the required `cnf.jkt`, the Resource Server lacks the data needed to verify DPoP binding. Never infer key binding from `client_id` or because the token was issued over TLS.

## 13. Reverse Proxies and Determining htu

A DPoP proof binds to the target URI. Reverse proxies may alter scheme, host, port, or path when forwarding requests:

~~~text
Client
  |
  | https://api.example.com/v1/orders/123
  v
Ingress
  |
  | http://orders-service:8080/internal/orders/123
  v
Resource Server
~~~

The client builds `htu` from the external URI, while the backend sees an internal URI. If the backend compares against its internal request URI, proofs will mismatch.

Agree on URI resolution:
- Use explicit external origin/path mapping configuration if architecture permits.
- Or trust forwarded metadata only from proxies in a trusted proxy list.
- Proxies must strip client-supplied forwarded headers and write verified values.
- Test multi-proxy hops, path rewrites, port mappings, and TLS termination.
- Never accept arbitrary request hosts to construct `htu`; that enables host confusion or validation bypasses.

Integration tests must exercise the same topology/proxy rules as deployment. Tests hitting controllers directly can miss URI normalization bugs.

## 14. Replay Caches and Multi-Instance Scaling

Suppose a valid proof has `jti = P-100`. If pod A handles the first request, pod A records `P-100` as used. A replayed request landing on pod B must observe that same state.

| How `jti` Is Stored | Behavior | Assessment |
| --- | --- | --- |
| Per-instance in-memory | Pod A and B hold separate state | Insufficient for multi-instance clusters |
| Shared cache/store with atomic insert | All instances share replay state | Suitable if TTL and consistency are sound |
| Sticky sessions | One client usually hits one instance | Does not guarantee replay defense when routing shifts |
| No `jti` storage | Unexpired proofs can be replayed | Fails replay detection |

A replay cache requires:
- Atomic insert-if-absent or equivalent operation.
- TTL aligned with the proof acceptance window and clock skew.
- Key namespacing by issuer/key thumbprint to prevent collisions.
- Capacity caps, rate limits, and metrics.
- Fail-closed handling during outages on DPoP-required endpoints.

If the replay store is unreachable, never silently skip the replay check and accept the proof. Define explicitly whether endpoints reject requests or return a dependency error per operational contract.

## 15. Client-Side Key Management

DPoP protects against standalone token theft; the client's private key becomes a critical asset to protect.

Typical requirements:
- Generate keys with a proper cryptographic random generator.
- Prefer OS keystores, secure enclaves, TPMs, or HSMs where supported by the client platform.
- Never store private JWKs in logs, source control, inappropriate local storage, or telemetry.
- Isolate keys by application/client/device per threat model.
- Maintain procedures to rotate keys and register new public keys.
- Never share one private key across dev, staging, and production.
- On key loss/compromise, revoke/rotate tokens and register fresh keys.

### Key Rotation

Access tokens bound to an old `jkt` do not automatically transfer to a new key. When a client rotates keys, it must request a new token bound to the new public key and transition per rollout design.

~~~text
Key A -> public JWK thumbprint JKT-A
Token T1 -> cnf.jkt = JKT-A

Client creates Key B -> thumbprint JKT-B
Client requests new token with proof from Key B
Token T2 -> cnf.jkt = JKT-B

T1 + proof from B -> mismatch
T2 + proof from B -> match
~~~

Never edit `cnf.jkt` in an existing token. Only the Authorization Server issues new tokens through trusted flows.

## 16. Failure Behavior and HTTP Responses

DPoP adds failure scenarios beyond standard invalid-token errors:

| Scenario | Reason | Expected Behavior |
| --- | --- | --- |
| Missing DPoP proof for bound token | Missing proof of possession | Reject |
| Invalid proof signature | Untrusted proof | Reject |
| Disallowed `typ` or `alg` | Wrong proof profile | Reject |
| `cnf.jkt` mismatch | Wrong key used | Reject |
| `htm`/`htu` mismatch | Proof minted for a different request | Reject |
| `ath` mismatch | Proof bound to a different token | Reject |
| `iat` too old or too far in the future | Proof outside time window | Reject |
| Reused `jti` | Replay | Reject |
| Missing/invalid `nonce` when required | Challenge unsatisfied | Return challenge/error per DPoP profile |
| Replay store outage | Cannot guarantee replay defense | Fail closed or dependency error per policy |
| Expired access token / wrong issuer | Invalid token | 401 |
| Valid token missing scope | Authorization denied | 403 |

Exact error codes and headers must follow RFC 9449, OAuth error responses, and your active implementation/version. When the server requires a nonce, the client reads the `DPoP-Nonce` response header, mints a fresh proof containing the nonce, and retries per rules. Never retry infinitely; enforce retry limits and timeouts.

Never log raw tokens, DPoP proofs, or private keys. Log correlation IDs, failure categories, sanitized issuer/client identifiers, and aggregate metrics.

## 17. Testing DPoP Across Layers

Never rely on a single integration test returning 200. Organize tests by capability:

| Layer | Goal | How to Test |
| --- | --- | --- |
| Proof construction | Valid header/payload | Unit test client proof builder |
| Proof signature | Private key signs, public key verifies | Cryptographic unit tests |
| JWK thumbprint | `jkt` computed per RFC 7638 | Test vectors and independent implementation |
| `ath` | Matches access token hash | SHA-256/Base64URL test vectors |
| Token binding | `cnf.jkt` matches proof JWK | Resource Server validator tests |
| Request binding | `htm`/`htu` match request | WebFlux/Servlet integration tests |
| Freshness | `iat` and clock skew | Boundary tests |
| Replay | `jti` cannot be used twice | Shared replay-store integration tests |
| Nonce | Server challenge and client retry | End-to-end tests |
| AS issuance | Right token type and `cnf` | Token endpoint integration tests |
| RS acceptance | Valid token + proof accepted | HTTP integration tests through filter chain |
| Proxy behavior | External URI matches | Tests through ingress/proxy topology |

### Positive Case

- Client has a test key pair.
- Test Authorization Server issues a token with matching `cnf.jkt`.
- Client mints a fresh DPoP proof for the exact GET URI.
- `ath` hashes the exact access token.
- `jti` has not been used.
- Valid nonce if required.
- Resource Server accepts token/proof, then checks scope.

### Negative Cases

- Proof signed with a different key.
- Token bound to JKT-A while proof uses JKT-B.
- Missing `cnf.jkt`.
- Missing `DPoP` header.
- `Bearer` authorization scheme sent for a token requiring DPoP.
- `ath` computed from a different token.
- Wrong HTTP method.
- URI with wrong host, port, scheme, or path.
- Expired proof or future `iat`.
- Replayed `jti`.
- Wrong or missing nonce.
- Bad access token signature/expired/wrong audience.
- Introspection returning `active=false` or omitting `cnf.jkt`.
- Unavailable replay store.

Each test must isolate failure at the token, proof, or authorization layer so an earlier failure never masks the condition under test.

## 18. Mocking Identity Does Not Test DPoP Proofs

A test using mock JWTs or mock users is helpful for scope/role checks, yet proves nothing about DPoP enforcement.

| Test Approach | Tests DPoP Proof? |
| --- | --- |
| `mockJwt()`/`mockUser()` | No |
| Mock access-token Authentication in `SecurityContext` | No |
| Bearer/DPoP header with mocked decoder | Tests only filter wiring per mock behavior; verifies no real signature |
| Proof validator unit test with test key | Can test proof logic |
| Resource Server integration with signed token/proof | Yes |
| End-to-end through test AS and Resource Server | Yes, when both sides use real implementations |

To verify DPoP, requests must carry both the access token and the DPoP proof through the real authentication mechanism. Helpers that pre-build Authentication bypass the core of sender constraining.

## 19. DPoP vs. mTLS Certificate-Bound Tokens in Spring Security

If your version/configuration does not yet support DPoP while the platform supports certificate-bound access tokens, mTLS per RFC 8705 can serve as the sender-constraining mechanism.

With mTLS certificate-bound tokens:
- Client presents a certificate during the TLS handshake.
- Token carries `cnf.x5t#S256`.
- Resource Server extracts the verified leaf client certificate.
- Computes the SHA-256 thumbprint over the DER certificate.
- Matches it against the token claim.

With DPoP:
- Client signs a proof JWT with its private key.
- Token carries `cnf.jkt`.
- Resource Server verifies the proof and JWK thumbprint.
- Checks request binding, `ath`, freshness, nonce, and replay.

The two mechanisms require different integrations in Spring Security and proxies. Never use mTLS properties to simulate DPoP or vice versa. Confirm framework and Authorization Server support for the exact profile before choosing.

## 20. Environment Capability Matrix Before Enabling

Dev, staging, and production may differ in issuers, proxies, key stores, token types, and framework support. Build a matrix ahead of rollout:

| Item | Dev | Staging | Production |
| --- | --- | --- | --- |
| Spring Boot/Security version | Resolved version | Release candidate/target version | Approved version |
| Client-side DPoP support | Tested/not yet | Tested/not yet | Tested/not yet |
| AS-side DPoP support | Tested/not yet | Tested/not yet | Tested/not yet |
| Resource Server DPoP support | Tested/not yet | Tested/not yet | Tested/not yet |
| Token type and `cnf.jkt` | Confirmed/not yet | Confirmed/not yet | Confirmed/not yet |
| Algorithm allowlist | Test keys | Production-like | Security policy |
| JWK thumbprint | Test vectors | Cross-checked | Contract |
| `ath`/`htm`/`htu` | Tested/not yet | Tested/not yet | Tested/not yet |
| Nonce/replay cache | Local/shared test | Cluster test | Shared store/SLO |
| Proxy external URI | Local route | Staging ingress | Trusted proxy configuration |
| Clock synchronization | NTP | NTP | NTP/monitoring |
| Key storage/rotation | Dedicated dev keys | Dedicated staging keys | Secure keystore/HSM as needed |
| Failure responses | 401/nonce | 401/nonce/503 | Contract and alerts |
| Revocation/incident process | Tested | Runbook rehearsal | Operational runbook |

Never mark support as "enabled" merely because a dependency is present. Require proof via bound token responses, Resource Server proof verification, and rejected negative tests.

## 21. Version Verification Checklist

Before writing code or changing configuration, confirm:

1. Exact resolved Spring Boot and Spring Security versions.
2. Matching release documentation describes DPoP for client, AS, or Resource Server roles.
3. OAuth client generates proofs compliant with RFC 9449.
4. Authorization Server verifies proofs and issues tokens with `cnf.jkt`.
5. Token responses use the profile's `token_type`.
6. Resource Server accepts the `DPoP` authorization scheme.
7. Resource Server verifies proof signature, `typ`, `alg`, and JWK.
8. Resource Server compares computed JKT against `cnf.jkt`.
9. Resource Server checks `htm`, `htu`, `iat`, `ath`, and `nonce`.
10. Replay protection works across instances.
11. Proxies preserve accurate URIs and block client-spoofed forwarded headers.
12. Negative tests prove invalid tokens/proofs are rejected.
13. TLS remains enabled with server certificate validation active.
14. Metrics/logs never leak tokens, proofs, or private keys.

If any mandatory capability is missing, document the limitation and pick a fully supported sender-constraining mechanism. Never ship half-baked DPoP and advertise tokens as key-bound.

## 22. Common Misconceptions

**"Enabling HTTPS means tokens cannot be stolen."** HTTPS protects the transport; tokens can still leak at endpoints, logs, memory, or client storage.

**"Having a DPoP header makes the request safe."** You must verify proof, key binding, `htm`, `htu`, `iat`, `ath`, `nonce`, and replay.

**"A valid proof signature is enough."** The proof must also use the exact key bound in `cnf.jkt` and match the request and access token.

**"cnf.jkt is the hash of the JWT proof."** No. It is the JWK thumbprint per RFC 7638.

**"cnf.jkt and cnf.x5t#S256 are the same."** No. One binds a JWK; the other binds an X.509 certificate.

**"A DPoP proof can be reused across requests."** It shouldn't be. `jti`, `htm`, `htu`, `iat`, and `ath` bind the proof to the request/token; mint a new proof per request.

**"ath is unnecessary since the token already has cnf."** `ath` binds the proof to the presented access token at the Resource Server; `cnf.jkt` binds the token to the key. They are distinct checks.

**"A local replay cache suffices for a cluster."** Not if replayed requests can hit another instance. Use shared/atomic replay detection or equivalent guarantees.

**"Proxies can infer htu from any X-Forwarded-Host."** Trust metadata only from authenticated proxies with explicit trust rules.

**"Resource Server JWT support implies DPoP support."** No. JWT decoding and DPoP proof validation are separate capabilities.

**"If the Authorization Server issues DPoP tokens, the backend is automatically protected."** Not unless the Resource Server validates proofs and `cnf.jkt`.

**"We can fall back to Bearer when a DPoP proof fails."** That voids sender constraining and lets stolen tokens be used.

## 23. Implementation Workflow

1. **Define the threat model:** where tokens could leak, how clients protect keys, and which endpoints require sender constraining.
2. **Check versions:** confirm Spring Security and the Authorization Server support DPoP or mTLS-bound tokens per profile.
3. **Lock the mechanism:** DPoP or mTLS; never mix claims or proofs between the two.
4. **Configure the client:** generate and protect key pairs, mint per-request proofs, handle nonces and `token_type`.
5. **Configure the issuer:** verify proofs at the token endpoint and issue access tokens with `cnf` bindings.
6. **Configure the Resource Server:** verify token, proof, thumbprint, request binding, and replay.
7. **Configure proxies:** ensure external URIs and forwarded metadata come from trusted sources.
8. **Configure operations:** shared replay cache, NTP, rate limits, timeouts, key rotation, and metrics.
9. **Write positive tests:** valid token and proof are accepted.
10. **Write negative tests:** key mismatch, token mismatch, `ath`, `htm`, `htu`, `nonce`, `iat`, `jti` replay, and wrong audience/scope are all handled properly.
11. **Test against real topology:** test through ingress and across multiple Resource Server instances.
12. **Deploy per environment:** keep separate keys, issuers, client registrations, and replay stores across dev/staging/production.

**Key takeaway:** DPoP binds an access token to a client's public key via `cnf.jkt` and requires the client to prove possession with a per-request proof JWT. The Resource Server must verify both the access token and the proof, match key thumbprints, check `htm`/`htu`/`iat`/`ath`/`nonce`, and block `jti` replays. mTLS certificate-bound tokens are a distinct key-binding mechanism using `cnf.x5t#S256` and client certificates. Enable either mechanism only when client, Authorization Server, Resource Server, proxy, and Spring Security version all support the exact profile; JWT Resource Server or HTTPS alone is not enough.
