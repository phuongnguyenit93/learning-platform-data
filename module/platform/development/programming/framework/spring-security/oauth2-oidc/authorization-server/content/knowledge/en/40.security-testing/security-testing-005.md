# Testing DPoP, mTLS, and token binding mismatch cases

In an OAuth 2.0/OpenID Connect Authorization Server built with Spring Authorization Server, access tokens are often treated as bearer tokens: any party holding the token can attempt to use it. If a token leaks through logs, browsers, proxies, or an intermediary service, whoever obtains the token can call APIs until the token expires or is revoked.

DPoP (Demonstrating Proof of Possession, RFC 9449) and mutual TLS (mTLS, RFC 8705) add proof of key possession by the client. The Authorization Server binds the token to the client's public key or certificate; the Resource Server verifies the proof on every API call. This lesson focuses on how to test both sides of the binding, especially when a token was issued for key A but the request proves possession of key B.

## Testing objectives

After this lesson, you will be able to:

- Distinguish bearer tokens from access tokens bound with DPoP or mTLS.
- Verify the structure and signature of a DPoP proof, per-request claims, nonces, and anti-replay mechanisms.
- Verify the key confirmation claim in the access token: `cnf.jkt` for DPoP and `cnf.x5t#S256` for mTLS.
- Verify that the Resource Server rejects tokens when the key proof mismatches.
- Design tests at the unit, Authorization Server integration, Resource Server, and real TLS levels.
- Identify misconfigurations at reverse proxies where TLS terminates before the Spring application.

## 1. Understanding what is being bound

A bearer token only needs to be presented. A sender-constrained token requires the API caller to prove possession of the key used when the token was issued. Verifying the access token's JWT signature remains necessary, but insufficient: the Resource Server must also verify that the request's proof matches the binding information inside the token.

| Mechanism | Proof in request | Binding information in token | Verification point |
|---|---|---|---|
| DPoP | JWT proof signed with client's private key, sent in `DPoP` header | `cnf.jkt`: thumbprint of the public JWK | Authorization Server at token endpoint and Resource Server at APIs |
| mTLS | Client certificate presented during TLS handshake | `cnf.x5t#S256`: thumbprint of the client certificate | TLS endpoint and Resource Server |
| Standard Bearer | No proof of key possession | No sender constraint | Resource Server validates the token |

DPoP and mTLS address the same risk category using two different types of proof. DPoP uses signatures at the HTTP layer; mTLS uses certificates at the TLS layer. A system can support both client types, provided it knows the exact binding type for each token.

Also distinguish two commonly confused concepts:

- **mTLS client authentication** authenticates the client when it connects to the Authorization Server. Methods such as `tls_client_auth` or `self_signed_tls_client_auth` address client authentication.
- **Certificate-bound access tokens** bind the access token to a certificate. The Resource Server must verify the certificate of the connection using the token.

A connection using mTLS for client authentication does not automatically prove that the issued access token is bound to that certificate. Tests must verify both decisions if the system requires both.

PKCE also does not replace DPoP or mTLS. PKCE protects the authorization code exchange; DPoP and mTLS protect token usage after the token is issued. These mechanisms can be used together.

## 2. Testing the DPoP flow

### 2.1. What makes up a DPoP proof?

The client generates an asymmetric key pair and keeps the private key on the client side. For each request requiring proof, the client builds a short-lived JWT, signs it with the private key, and sends it in the `DPoP` header.

The proof JWT header has these key components:

- `typ` must be `dpop+jwt`.
- `alg` must be an asymmetric signing algorithm allowed by the system. Never accept `none`.
- `jwk` contains the public JWK so the server can verify the signature. It must never contain private key material.

The proof payload typically contains:

- `jti`: unique identifier of the proof, used to detect replays.
- `htm`: HTTP method of the request, uppercase matching the actual method.
- `htu`: target URI of the request. This value excludes query string and fragment; scheme, host, port, and path must still match the target URI determined by the server.
- `iat`: proof creation timestamp.
- `nonce`: server-issued nonce when policy requires it.
- `ath`: hash of the access token, mandatory when the proof is sent to a Resource Server alongside an access token.

When calling the token endpoint, the proof is bound to the token endpoint's method and URI. When calling a Resource Server, the proof must be bound to the API request and include `ath`. The `ath` value is computed as SHA-256 over the access token string, then encoded as unpadded URL-safe Base64.

### 2.2. Checking the issued token

When the Authorization Server accepts a DPoP proof at the token endpoint, the issued access token must carry a binding to the public key that signed the proof. For a JWT access token, this information typically resides in the claim:

~~~json
{
  "cnf": {
    "jkt": "thumbprint-of-public-jwk"
  }
}
~~~

The thumbprint must be computed per JWK thumbprint rules (RFC 7638). Use a proven JOSE library to compute the thumbprint; do not construct JSON manually or rely on `kid`, as `kid` is merely a label assigned by the JWK issuer.

Token endpoint responses for DPoP-bound tokens use `token_type: DPoP`. The client must retain the corresponding private key to generate proofs when using the access token. If the system supports DPoP-bound refresh tokens, refresh operations must also prove possession of the bound key.

For opaque access tokens, the Resource Server typically receives confirmation data via introspection or an equivalent metadata-sharing mechanism. Do not assume every access token is a JWT or that the Resource Server can always read claims directly.

### 2.3. Checking requests at the Resource Server

A DPoP-bound API request typically looks like:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP eyJ...access-token...
DPoP: eyJ...proof-jwt...
~~~

The Resource Server needs to perform all of the following steps:

1. Verify the access token: signature or introspection, issuer, audience, expiration, and other token constraints.
2. Read `cnf.jkt` from the verified token.
3. Verify the DPoP proof header and signature; accept only valid public JWKs and allowlisted algorithms.
4. Compute the thumbprint from the public JWK in the proof and compare it with `cnf.jkt`.
5. Compare `htm` and `htu` against the current request.
6. Check that `iat` falls within the accepted window, and validate the nonce if policy requires it.
7. Check that `jti` has not already been used within the anti-replay window.
8. Recompute `ath` from the submitted access token and compare it with the claim in the proof.

If even one step fails, the request must be rejected. In particular, a proof with a valid signature must still not be accepted if the proof's public key has a different thumbprint from the one in the access token.

### 2.4. Common pitfalls when verifying DPoP

**URIs behind a reverse proxy:** The application may see an internal HTTP connection while the client called an external HTTPS URL. If the application constructs `htu` from the internal request, valid proofs from clients will be rejected or verification may be weakened. Trust `Forwarded` or `X-Forwarded-*` only from explicitly trusted proxies; test external scheme, host, port, and path.

**Distributed replay protection:** Once one node accepts a `jti`, no other node in the cluster may accept the same proof again. The replay store must support atomic writes, retention aligned with the `iat` window, and sufficient key scoping to distinguish proofs. Test two concurrent requests sent to two nodes.

**Clock skew:** Use a replaceable `Clock` in tests to verify overly old proofs and proofs with future `iat` values. The allowed window must be small and explicitly configured.

**Nonce:** If the server requires a nonce, test missing nonce, wrong nonce, expired nonce, and valid nonce cases. When requesting a fresh nonce, the response should supply the nonce per the system's DPoP contract, typically via the `DPoP-Nonce` header.

**Unsafe JWKs:** Reject JWKs containing private key material, disallowed algorithms, or incompatible key types. Never treat an arbitrary `kid` as proof of key possession.

## 3. Testing the mTLS flow

### 3.1. Certificates used to bind tokens

In mTLS, the client presents an X.509 certificate during the TLS handshake. The Authorization Server can use that certificate to authenticate the client, to bind the access token, or for both purposes.

For certificate-bound access tokens per RFC 8705, the confirmation claim typically has the form:

~~~json
{
  "cnf": {
    "x5t#S256": "thumbprint-of-client-certificate"
  }
}
~~~

The `x5t#S256` thumbprint is the SHA-256 hash of the client certificate's DER encoding, encoded as unpadded URL-safe Base64. When the Resource Server receives the token, it obtains the client certificate from the verified TLS connection, computes its thumbprint, and compares it against the value in the token.

mTLS certificate-bound access tokens are still commonly sent using the OAuth 2.0 `Bearer` scheme. The binding is enforced by the certificate on the TLS connection. Thus, seeing `Authorization: Bearer` alone is not enough to conclude a token is an unbound bearer token; the Resource Server must still check `cnf.x5t#S256`.

Do not use subject DN or serial number as a substitute match. Two certificates can share the same subject while having different keys and different DER encodings. Tests should create two such certificates to confirm the application compares thumbprints properly.

### 3.2. Checking both connection points

At the token endpoint, verify that:

- The TLS handshake requires a client certificate per policy.
- The certificate chain is verified against the appropriate truststore.
- Client identity is mapped according to client registration policy.
- When issuing a certificate-bound token, the `cnf.x5t#S256` claim matches the actual accepted certificate.
- mTLS client authentication and token binding are tested independently.

At the Resource Server, verify that:

- The request presents the exact certificate bound to the token.
- The certificate is obtained from a verified TLS connection, not from an arbitrary client-supplied header.
- The thumbprint is computed from the leaf certificate designated by the system for binding.
- The token is rejected if the certificate is absent or the thumbprint mismatches.

If TLS terminates at an ingress or reverse proxy, the backend application does not directly observe the original TLS client certificate. In that case, the proxy must verify the certificate and forward certificate data over a protected internal channel. The proxy must strip externally supplied certificate headers from clients before adding its own trusted header. Test both the path through the proxy and direct access to the application to catch header spoofing or bypassed verification layers.

### 3.3. Handling certificate lifecycle

A token bound to certificate A does not automatically become valid for certificate B after the client rotates certificates. Test the transition policy explicitly:

- The old token continues working with certificate A within its allowed lifetime.
- The old token is rejected when requests use certificate B.
- The client obtains a new token bound to certificate B.
- Certificates that are expired, revoked, or outside the trust chain are rejected per TLS policy.
- A new certificate with the same subject as the old certificate is still treated as a different certificate if its thumbprint differs.

A certificate error during the TLS handshake can close the connection before an HTTP request reaches the application. For these cases, tests must verify that the handshake fails or the connection is refused; do not necessarily expect an HTTP status such as 401.

## 4. Integrating tests with Spring Authorization Server

Spring Authorization Server provides extension points for client authentication, the token endpoint, and token issuance. How DPoP or certificate-bound tokens are implemented depends on your Spring Authorization Server version, Spring Security version, servlet container, and TLS termination architecture. Therefore, tests must confirm behavior across the full stack rather than only asserting that a bean is configured.

For JWT access tokens, an application can use `OAuth2TokenCustomizer<JwtEncodingContext>` to embed confirmation data into the token. The example below illustrates where to attach the claim; `SenderConstraintContextResolver` is an application-defined component:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer(
        SenderConstraintContextResolver bindingResolver) {

    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            Map<String, Object> confirmation =
                    bindingResolver.resolve(context);

            if (!confirmation.isEmpty()) {
                context.getClaims().claim("cnf", confirmation);
            }
        }
    };
}
~~~

This snippet illustrates only the step of placing the claim into the JWT. It does not verify DPoP proofs, prevent replays, verify TLS client certificates, or make the Resource Server automatically enforce token binding. Those responsibilities must be implemented at the appropriate request-handling points or provided by a supporting framework version/component.

If using opaque tokens, verify that the introspection response provides the required confirmation info and that the Resource Server actually uses it. If using JWTs, inspect claims inside the issued signed token rather than only checking an in-memory object before encoding.

Tests should be divided by responsibility:

| Test layer | Component to verify | Passing evidence |
|---|---|---|
| Unit | DPoP proof verifier, JWK thumbprint, certificate thumbprint, replay store, nonce, and clock | Valid inputs accepted; each invalid condition rejected |
| Authorization Server integration | Token endpoint and token issuance step | Token issued with right type and `cnf` matching key/certificate |
| Resource Server integration | Filter or component verifying sender constraint | Token accepted only when proof/certificate matches |
| HTTPS end-to-end | TLS connector, truststore, and client certificate | Real handshake and requests obey mTLS policy |
| Proxy/deployment | Ingress, forwarded headers, and certificate forwarding path | Cannot spoof URI or certificate via untrusted headers |

## 5. Token binding test matrix

Use two independent DPoP key pairs (A and B), two independent certificates (A and B), a controllable clock, and a replay store that can be reset between tests. The token issued for A is the central fixture: every mismatch test must use this token while presenting proof for B.

### 5.1. DPoP

| Case | Test input | Expected outcome |
|---|---|---|
| Valid proof | Valid signature, valid `htm`, `htu`, `iat`, `jti`; key matches `cnf.jkt` | Request accepted |
| Missing proof | No `DPoP` header in a DPoP-required flow | Token endpoint or Resource Server rejects per error contract |
| Malformed proof | Broken JWT, missing required claim, or `typ` not `dpop+jwt` | Proof rejected |
| Invalid signature | Payload signed with a key different from header's public JWK | Proof rejected |
| Invalid algorithm | `alg=none`, symmetric algorithm, or algorithm outside allowlist | Proof rejected |
| Contains private key material | JWK in proof includes private key fields | Proof rejected |
| Token binding mismatch | Token has A's `cnf.jkt` but proof uses public key B | Token not accepted |
| Wrong HTTP method | `htm` is GET while actual request is POST | Proof rejected |
| Wrong target URI | `htu` has wrong scheme, host, port, or path | Proof rejected |
| Proof too old or in future | `iat` outside allowed window | Proof rejected |
| Replay | Resubmit same proof with same `jti` within anti-replay window | Resubmission rejected |
| Wrong access-token hash | `ath` is not the hash of the submitted access token | Request rejected |
| Missing nonce | Server requires nonce but proof omits it | Server demands nonce per contract |
| Wrong or expired nonce | Proof uses an old nonce or nonce from another session | Proof rejected or fresh nonce required |
| Wrong token scheme | Sending `Authorization: Bearer` for a token requiring DPoP | Request rejected |
| Refresh with different key | Refresh token bound to A but refresh proof uses B | Refresh request rejected |

### 5.2. mTLS

| Case | Test input | Expected outcome |
|---|---|---|
| Valid certificate | Certificate A is trusted and matches `cnf.x5t#S256` | Request accepted |
| Missing client certificate | Connection presents no certificate in an mTLS-required flow | TLS handshake or request rejected |
| Wrong certificate | Token bound to A but connection uses B | Token not accepted |
| Same subject, different key | A and B share subject DN but have different DER encodings | B is rejected |
| Expired certificate | Client presents an expired certificate | TLS handshake rejected per policy |
| Untrusted chain | Certificate not accepted by truststore | TLS handshake rejected |
| Revoked certificate | Certificate is revoked and system checks revocation status | Connection rejected per revocation policy |
| Header spoofing | Client sends a header containing certificate info | Header stripped by proxy; cannot replace TLS certificate |
| Certificate rotation | Old token for A sent with new certificate B | Old token rejected; new token must be issued for B |
| mTLS client auth only | Client certificate used for login but token lacks binding claim despite policy requirement | Test catches token issuance defect |
| Access via proxy | Proxy verifies A and forwards certificate data over trusted channel | Valid request accepted; client headers cannot override |

### 5.3. Cross-testing both mechanisms

Beyond individual test suites, confirm that the Resource Server does not confuse proof types:

- A DPoP-bound token must not be accepted merely because the request has a valid client certificate.
- A certificate-bound token must not be accepted merely because the request has a valid DPoP proof.
- Tokens without a `cnf` claim must follow configured bearer policy; never inadvertently bypass a client's sender-constraint requirement.
- If the system intentionally supports tokens bound to multiple factors simultaneously, test the combination rule explicitly. If no such rule is defined, reject ambiguous `cnf` configurations rather than guessing.

## 6. Generating DPoP proofs in tests

You can use Nimbus JOSE + JWT to generate proofs with test keys. The snippet below illustrates creating a proof for the token endpoint; method and URI values must match the request sent by the test:

~~~java
ECKey keyA = new ECKeyGenerator(Curve.P_256)
        .keyID("dpop-test-a")
        .generate();

JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.ES256)
        .type(new JOSEObjectType("dpop+jwt"))
        .jwk(keyA.toPublicJWK())
        .build();

JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .jwtID(UUID.randomUUID().toString())
        .issueTime(Date.from(clock.instant()))
        .claim("htm", "POST")
        .claim("htu", "https://as.example.test/oauth2/token")
        .build();

SignedJWT proof = new SignedJWT(header, claims);
proof.sign(new ECDSASigner(keyA));

String dpopHeader = proof.serialize();
~~~

For requests to the Resource Server, create a new proof for that request and add the `ath` claim:

~~~java
String ath = Base64URL.encode(
        MessageDigest.getInstance("SHA-256")
                .digest(accessToken.getBytes(StandardCharsets.US_ASCII))
).toString();
~~~

Then include `ath` in the payload before signing the proof. Never reuse a token endpoint proof for an API request: method, URI, access-token hash, and `jti` are each bound to a specific request.

To prove a mismatch, issue the token with key A and create the proof with key B. Do not just change `kid`: use an independent key pair so the thumbprints genuinely differ. The test must observe the result at the Resource Server, where token and proof are matched.

## 7. Example Resource Server integration test

Suppose the `/api/orders/42` endpoint requires DPoP. The test can send an access token issued for key A together with a proof signed by key B:

~~~java
mockMvc.perform(get("/api/orders/42")
        .header(HttpHeaders.AUTHORIZATION, "DPoP " + accessTokenBoundToA)
        .header("DPoP", createProof(keyB, "GET",
                "https://api.example.test/api/orders/42",
                accessTokenBoundToA)))
    .andExpect(status().isUnauthorized());
~~~

This is a test pattern for application-defined endpoints and helpers. Add a corresponding test with key A to prove the same token is accepted when the proof matches. For mTLS tests in MockMvc, you can set the request attribute containing the certificate to test application logic; however, that only simulates container-provided data and does not test the TLS handshake.

An end-to-end mTLS test must run an HTTPS server configured to require client certificates, a test truststore, and two client keystores A/B. Call the same endpoint with certificates A and B to verify the certificate comes from a real TLS connection. Tests routed through an ingress should include a case where the client sends a forged certificate header to prove the proxy strips that header.

## 8. Verifying error responses and operability

Verify error contracts at the HTTP boundary rather than depending on internal exception names:

- Invalid DPoP proofs at the token endpoint are typically returned with OAuth error `invalid_dpop_proof`.
- When the server requires a new nonce, the response may use `use_dpop_nonce` and provide `DPoP-Nonce`.
- The Resource Server may return 401 with a DPoP challenge when a proof is invalid; invalid or binding-mismatched tokens must be rejected as unauthorized tokens.
- A failed mTLS handshake may close the connection before the application produces an HTTP response.
- Never return raw access tokens, raw DPoP proofs, private keys, or sensitive certificate contents in error responses or logs.

A stable test suite should assert status codes, error codes, or challenge headers according to the application's public contract. Avoid locking tests to exception messages or stack traces, as those details can change when upgrading Spring Security or JOSE libraries.

When running in a cluster, test the shared replay store across nodes and ensure anti-replay writes are atomic. When running behind a proxy, test how external URIs are resolved and where client certificate data originates. When rotating keys or certificates, test the lifetime of old tokens, the issuance flow for new tokens, and policy-driven revocation.

## 9. Completion checklist

Before promoting sender-constrained mechanisms to an integration environment, confirm:

- [ ] DPoP tokens contain `cnf.jkt` matching the public JWK that signed the proof.
- [ ] mTLS tokens contain `cnf.x5t#S256` matching the accepted client certificate.
- [ ] The Resource Server verifies the token signature before trusting the `cnf` claim.
- [ ] The Resource Server matches the proof/certificate against `cnf` on every request requiring sender constraint.
- [ ] DPoP checks `typ`, algorithm, signature, `htm`, `htu`, `iat`, `jti`, `ath`, and nonce per policy.
- [ ] Replay detection works across multiple nodes and under concurrent requests.
- [ ] mTLS verifies certificate chains at the TLS endpoint and ignores client-supplied certificate headers.
- [ ] Old tokens are rejected when used with a different key or certificate.
- [ ] Tests through reverse proxies verify accurate external URIs and client certificates.
- [ ] Error responses do not leak tokens, proofs, or private keys.

A solid test suite must prove both the valid path and binding-mismatch paths. Checking only that the issued token contains a `cnf` claim is insufficient; proof of key possession must be verified on every request that uses the token.
