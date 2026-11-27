# Bearer Tokens and Sender-Constrained Tokens Have Different Protection Models

In **Spring Security OAuth 2.0/OIDC Resource Server**, an access token can be protected under two different models:

- **Bearer token**: any party in possession of the token can present it for use, as long as the token is still valid and the API accepts it.
- **Sender-constrained token**: the token is bound to a client key or certificate. When calling the API, the client must prove possession of the corresponding private key or the TLS certificate bound to the token.

This difference directly affects the risk of **stolen-token replay**. If an attacker obtains a bearer token, they can use it from another device while the token remains valid. If the token is bound to a key and the Resource Server verifies the proof properly, having only the access token is normally not enough to use it.

Two common sender-constrained mechanisms in OAuth 2.0 are:

1. **DPoP — Demonstrating Proof of Possession**, standardized in RFC 9449. The client signs a proof JWT for each HTTP request using a private key; the access token is bound to the corresponding public key.
2. **Mutual TLS certificate-bound access token**, standardized in RFC 8705. The access token is bound to the client's X.509 certificate; when calling the API, the client must establish a TLS connection with the matching client certificate.

> **Key principle:** JWT vs. opaque describes how a token is represented/verified; bearer vs. sender-constrained describes how a token is allowed to be used. An access token can be either JWT or opaque, and at the same time can be either bearer or bound to a key/certificate. Do not confuse the token format with the sender-proof mechanism.

This article explains the token issuance and usage flows, the `cnf` claim, DPoP proofs, mTLS certificate binding, how to configure Spring Security, what to check at a reverse proxy, how to test for replay, and how to choose the right model. The main Java examples use **Spring Security Servlet Resource Server**. WebFlux has its own API and filter model; do not copy Servlet classes directly into the reactive stack.

## 1. How Does a Bearer Token Work?

A client sends the access token in the HTTP `Authorization` header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

The Resource Server verifies the token according to its token type:

- JWT: verifies the signature with a trusted key, checks the issuer, audience, expiration, and other conditions.
- Opaque token: calls a trusted introspection endpoint to check the token's status and retrieve the necessary information.

If the token is valid and has the appropriate scope, the API allows the request to proceed.

### 1.1. Bearer Means "Whoever Has the Token Can Present It"

For example:

~~~text
Client A receives access token T
        |
        v
T is written to logs or extracted from memory
        |
        v
Attacker obtains T
        |
        v
Attacker sends Authorization: Bearer T
        |
        v
Resource Server sees a valid token
        |
        v
Request may be accepted
~~~

The Resource Server has no proof that the request came from the exact client that originally received the token. The token acts as a **possession-based credential**: whoever holds it can use it.

TLS protects the token in transit between the two TLS endpoints, but it does not protect the token once it is leaked from:

- Application, proxy, or tracing logs.
- Browser storage, mobile storage, or configuration files.
- Memory dumps, crash dumps, or telemetry.
- Clipboard, shell history, or support tickets.
- An intermediate service with read access to request headers.

### 1.2. A Bearer Token Is Not Synonymous with a JWT

A bearer token can be a JWT:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

or an opaque reference:

~~~http
Authorization: Bearer 4Y7dR2kq9v...
~~~

In both cases, if the token is a bearer token, the party holding it can present it. The fact that a JWT is signed does not prove the request was sent by the exact client that received the token.

**A JWT signature proves the token was issued by a source holding the corresponding signing key**, not that the current request sender possesses a client private key.

## 2. What Is a Sender-Constrained Token?

A sender-constrained token ties the access token to a **proof-of-possession credential**:

~~~text
Authorization Server
        |
        | Issues access token T
        | Binds T to public key K
        v
Client holds private key K_private
        |
        | Sends T + proof demonstrating possession of K_private
        v
Resource Server
        |
        | Verifies T
        | Verifies proof
        | Compares proof key against key binding in T
        v
Accepts only when both steps are valid
~~~

An attacker who obtains only the access token will not have enough information to create a valid proof, provided the private key is protected and the Resource Server actually verifies the binding.

### 2.1. The `cnf` Claim Describes the Bound Key/Certificate

In a JWT access token, RFC 7800 defines the **`cnf` (confirmation)** claim to represent confirmation information for the client's credential. Specific standards use different members inside `cnf`:

**DPoP:**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  },
  "exp": 2000000300
}
~~~

`cnf.jkt` is the JWK SHA-256 thumbprint of the public key used to sign the DPoP proof.

**mTLS certificate-bound access token:**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "svc:inventory-sync",
  "aud": ["orders-api"],
  "scope": "orders.import",
  "cnf": {
    "x5t#S256": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
  },
  "exp": 2000000300
}
~~~

`cnf.x5t#S256` is the SHA-256 thumbprint of the client X.509 certificate used to bind the token.

The thumbprint values here only illustrate the format; they are not real credentials.

### 2.2. Never Fabricate `cnf` at the Resource Server

`cnf` must be attached by the Authorization Server during the token issuance flow. The Resource Server reads this claim **after the token has been verified** and compares it against the request's proof/certificate.

Do not do this:

~~~java
// WRONG: adding cnf to the token yourself just to pass the check.
claims.put("cnf", Map.of("jkt", request.getHeader("X-Client-Key")));
~~~

A header sent by the client does not prove that the key or certificate was bound to the token by the AS.

## 3. Comparing the Three Protection Models

| Criterion | Bearer | DPoP | mTLS-bound token |
|---|---|---|---|
| Additional credential when calling API | None | DPoP proof JWT | Client certificate in TLS |
| Access token header | `Authorization: Bearer` | `Authorization: DPoP` | `Authorization: Bearer` |
| Additional header | None | `DPoP: <proof>` | No HTTP proof header required |
| Binding in access token | No `cnf` needed | `cnf.jkt` | `cnf.x5t#S256` |
| Where proof is verified | Token validation | Application layer | TLS handshake + token/certificate binding |
| HTTP method/URI binding | No | Yes, via `htm` and `htu` | Not in the way DPoP does |
| Access token hash binding | No | Yes, via `ath` | Not via DPoP `ath` |
| Required infrastructure | TLS | TLS + client key management | TLS mutual authentication + PKI |
| Common fit | General APIs | Mobile/native/public clients, clients where mTLS is hard to use | Service-to-service, PKI environments |
| Remaining risks | Stolen token can be replayed | Private key compromise or proof replay if controls are missing | Client certificate/private key compromise or proxy misconfiguration |

Both DPoP and mTLS increase resilience against the use of stolen access tokens. They do not eliminate risks such as compromised client endpoints, malware that can invoke the private-key signer, overly broad API scopes, or business-layer authorization bugs.

## 4. DPoP: Proof of Key Possession per HTTP Request

DPoP is defined in **RFC 9449**. The client generates a key pair:

~~~text
K_private: private key, held only by the client
K_public:  public key, published in the DPoP proof
~~~

The client sends a proof JWT signed with `K_private`. The Authorization Server associates the access token with the thumbprint of `K_public`. When calling the Resource Server, the client continues sending a fresh proof to demonstrate possession of the private key.

### 4.1. Token Issuance Flow

~~~text
1. Client generates or selects a DPoP key pair
             |
             v
2. Client sends token request to Authorization Server
   with a DPoP proof in the DPoP header
             |
             v
3. Authorization Server verifies the proof JWT
             |
             v
4. Authorization Server extracts the public JWK
   and computes the JWK thumbprint
             |
             v
5. AS issues an access token containing cnf.jkt
             |
             v
6. Token response indicates token_type = DPoP
~~~

Example token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: eyJraWQiOiJjbGllbnQta2V5IiwidHlwIjoiZHBvcCtqd3QifQ...

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
client_id=storefront-web&
code_verifier=PKCE_VERIFIER
~~~

The proof at the token endpoint typically includes the `htm`, `htu`, `iat`, and `jti` claims, and may include `nonce` if required by the AS. It does not need `ath` yet because the client is not presenting an access token in this request.

The token response might look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "DPoP",
  "expires_in": 600
}
~~~

`token_type=DPoP` informs the client that the access token is bound to the public key from the DPoP proof.

### 4.2. What Components Does a DPoP Proof Have?

A DPoP proof is a JWT with a header like:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<public-key-x>",
    "y": "<public-key-y>"
  }
}
~~~

The `jwk` header contains the public key; private key parameters must not be included in the proof.

For a protected resource request, the payload typically contains:

~~~json
{
  "jti": "unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "iat": 2000000000,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

| Claim | Meaning |
|---|---|
| `jti` | Unique ID of the proof, used to detect proof replay |
| `htm` | HTTP method of the request |
| `htu` | HTTP target URI following RFC 9449 canonicalization rules |
| `iat` | Timestamp when the proof was created |
| `ath` | Hash of the access token being sent |
| `nonce` | Server-required nonce, when applicable |

`htu` is computed according to RFC 9449 rules; query strings and fragments are omitted from this target URI value. When behind a reverse proxy, the Resource Server must determine the exact public URI that the client used.

### 4.3. Protected Resource Request

Unlike a bearer token, a DPoP access token uses the `DPoP` scheme:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: SIGNED_DPOP_PROOF_JWT
~~~

The Resource Server must verify at least:

1. The access token is valid according to issuer, audience, expiration, signature, or introspection.
2. The access token contains the `cnf.jkt` binding.
3. The DPoP proof JWT has `typ=dpop+jwt` and an allowed signing algorithm.
4. The proof signature is valid against the public JWK in the proof.
5. The thumbprint of the public JWK matches `cnf.jkt` in the access token.
6. `htm` matches the actual HTTP method.
7. `htu` matches the request URI according to standard rules.
8. `ath` matches the hash of the sent access token.
9. `iat` is within the accepted time window.
10. `jti` has not been used before.
11. `nonce` matches if the Resource Server requires a nonce.

**Do not skip any step just because the DPoP proof signature is valid.** A proof signed with an arbitrary key must still be rejected if the public key does not match the access token's `cnf.jkt`.

### 4.4. `ath` Prevents Pairing a Proof with Another Token

Suppose a client holds:

~~~text
Access token A
Access token B
```

If the proof were signed only for the method/URI without binding the token, an attacker could try pairing the proof with a different access token.

`ath` binds the proof to the exact access token being sent. Conceptually:

~~~text
ath = BASE64URL-ENCODE(SHA-256(access_token))
```

The Resource Server computes the hash itself from the received token and compares it with the `ath` claim. Do not take `ath` from another request header or trust a client-supplied result without recomputing it.

### 4.5. Nonces and Challenges

A Resource Server can require clients to use a nonce. The server returns a header such as:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: SERVER_NONCE
WWW-Authenticate: DPoP error="use_dpop_nonce"
~~~

The client creates a new proof containing the corresponding `nonce` claim and resends the request. Nonces help reduce the risk of attackers pre-generating proofs in advance and replaying them later.

Nonces do not replace `jti` replay detection. The two mechanisms complement each other and should be implemented according to RFC 9449 and the server's contract.

## 5. DPoP Replay Attacks and Prevention

DPoP proofs are short-lived, yet an intercepted proof can still be replayed within the acceptance window if the server does not track reuse.

For example:

~~~text
Client sends proof with jti=proof-123
        |
        v
Attacker intercepts the request
        |
        v
Attacker replays the exact same proof-123
        |
        v
If the server does not store used jti values,
the proof may be processed again
~~~

The Resource Server needs to:

- Require `jti` to be present and unique per proof.
- Limit proof age via `iat` and clock skew.
- Store seen `jti` values for an appropriate duration.
- Use an insert-if-absent operation or equivalent atomic mechanism so two nodes cannot simultaneously accept the same proof.
- Retain cache entries long enough to cover the entire validity window of a proof.
- Synchronize clocks across nodes.

### 5.1. Replay Cache in Spring Security

Spring Security includes `DPoPProofReplayValidator` starting in **6.5.12**. This validator verifies that `iat` is within the accepted window and that `jti` has not been used yet; `jti` is stored in a Spring Cache to ensure each proof is used only once.

The API includes:

- `DPoPProofReplayValidator`
- `DPoPProofReplayValidator.InMemoryCache`
- `DPoPProofJwtDecoderFactory`

`InMemoryCache` uses a `ConcurrentHashMap`, which is suitable for a single node or testing environments. The documentation warns that this implementation is only suitable for single-node setups; multi-replica systems need a distributed cache such as Redis or Hazelcast so all instances share the same replay state.

Example of creating the validator:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.jwt.DPoPProofReplayValidator;
import org.springframework.security.oauth2.jwt.DPoPProofReplayValidator.InMemoryCache;

DPoPProofReplayValidator replayValidator =
    new DPoPProofReplayValidator(new InMemoryCache());

replayValidator.setClockSkew(Duration.ofSeconds(30));
~~~

This example creates the validator. To apply a custom validator to the proof decoder, use the `DPoPProofJwtDecoderFactory.setJwtValidatorFactory(...)` extension point and retain the framework's default validators. Do not replace them with a validator that checks only `jti`, as doing so could drop the `htm`, `htu`, `jkt`, `ath`, and `iat` checks.

### 5.2. Customizing the Proof Validator Factory

In Spring Security 6.5.12+, the factory provides `createDefaultJwtValidatorFactory(...)` to combine the default checks with additional validators:

~~~java
DPoPProofJwtDecoderFactory proofDecoderFactory =
    new DPoPProofJwtDecoderFactory();

proofDecoderFactory.setJwtValidatorFactory(
    DPoPProofJwtDecoderFactory.createDefaultJwtValidatorFactory(
        List.of(replayValidator)
    )
);
~~~

When manually wiring `DPoPAuthenticationProvider`, you can pass the factory via `setDPoPProofVerifierFactory(...)`. If using the high-level DPoP DSL in Spring Security 7.1, check the corresponding extension API for that version; do not assume every custom provider can be swapped directly from every configurer.

### 5.3. Replay Cache in Multi-Node Environments

~~~text
API instance A ----+
                   |
API instance B ----+---- Shared replay cache
                   |
API instance C ----+
~~~

If each node uses its own in-memory cache:

- The first request hits node A, which stores `jti`.
- The attacker replays the proof to node B.
- Node B has not seen `jti` and may accept it again.

The replay cache must have atomic semantics across the entire cluster. It also needs a TTL to automatically evict entries after the proof expires in order to bound memory/storage usage.

## 6. mTLS-Bound Access Tokens: Binding to an X.509 Certificate

DPoP uses a proof JWT at the HTTP application layer. An **mTLS-bound access token** uses a client certificate during the TLS handshake.

The client holds:

~~~text
Client certificate
Client private key
```

When connecting to the API, the client and server perform mutual TLS:

~~~text
Client                               Resource Server
  |                                        |
  | ClientHello                            |
  |--------------------------------------->|
  |                                        |
  | Server certificate                    |
  |<---------------------------------------|
  |                                        |
  | Client certificate                     |
  |--------------------------------------->|
  |                                        |
  | Client proves private-key possession  |
  |<-------------------------------------->|
  |                                        |
  | TLS channel established               |
~~~

The TLS stack verifies the certificate chain against the server's trust store and policy. Next, the Resource Server needs to **compare the connection's client certificate against the binding in the access token**.

### 6.1. The `cnf.x5t#S256` Claim

A certificate-bound access token may contain:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "svc:inventory-sync",
  "aud": ["orders-api"],
  "scope": "orders.import",
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERT_THUMBPRINT"
  },
  "exp": 2000000300
}
~~~

The thumbprint is calculated over the DER-encoded X.509 certificate:

~~~text
x5t#S256 =
    BASE64URL-ENCODE(
        SHA-256(DER-ENCODED-CERTIFICATE)
    )
~~~

The Resource Server retrieves the certificate already verified by the TLS layer, recomputes the thumbprint, and compares it against the `cnf.x5t#S256` claim.

If an attacker obtains only the access token without the certificate's private key, they cannot establish a TLS connection with the matching client certificate.

### 6.2. The Access Token Still Uses Authorization: Bearer

An mTLS-bound access token is typically presented in the header:

~~~http
GET /api/import/jobs HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The difference lies in the **TLS connection**: the client must present the matching certificate during the handshake. There is no `DPoP` proof header.

Therefore:

- DPoP: `Authorization: DPoP` scheme, plus a `DPoP` header.
- mTLS-bound: `Authorization: Bearer` scheme, with the client certificate presented at the TLS layer.

Do not attempt to read a certificate from an arbitrary header and treat it as mTLS. The certificate must come from a verified TLS connection or a trusted gateway with a secure mechanism for forwarding certificate identity.

## 7. Configuring mTLS-Bound Token Issuance at the Authorization Server

The Resource Server cannot enforce token binding on its own if the AS does not issue tokens containing certificate confirmation.

With **Spring Authorization Server**, you can register a client using TLS client authentication and enable certificate-bound access tokens.

~~~java
RegisteredClient mtlsClient =
    RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("inventory-sync")
        .clientAuthenticationMethod(ClientAuthenticationMethod.TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.import")
        .clientSettings(ClientSettings.builder()
            .x509CertificateSubjectDN(
                "CN=inventory-sync,OU=Workloads,O=Example")
            .build())
        .tokenSettings(TokenSettings.builder()
            .x509CertificateBoundAccessTokens(true)
            .build())
        .build();
~~~

The example requires imports from Spring Authorization Server, including `RegisteredClient`, `ClientAuthenticationMethod`, `AuthorizationGrantType`, `ClientSettings`, `TokenSettings`, and `UUID`.

Meaning:

- `TLS_CLIENT_AUTH`: the AS authenticates the OAuth client using a TLS client certificate.
- `x509CertificateSubjectDN(...)`: binds the certificate identity to the client configuration.
- `x509CertificateBoundAccessTokens(true)`: requests that issued access tokens include the certificate thumbprint binding.

This is **Authorization Server**-side configuration. It does not automatically configure the ingress, TLS connector, or Resource Server verification of the binding claim. The API side must still receive the proper client certificate and verify `cnf.x5t#S256`.

## 8. Verifying Certificate Binding at the Resource Server

Spring Security `oauth2ResourceServer().jwt()` can verify the JWT signature and claims, but verifying `cnf.x5t#S256` also requires the **current request's** certificate.

`JwtDecoder` receives only the token; it does not inherently know which TLS client certificate was used for the HTTP request. Therefore, a request-aware step is needed after the JWT is verified.

### 8.1. Processing Flow

~~~text
HTTP request
    |
    +-- TLS layer verifies client certificate
    |
    +-- BearerTokenAuthenticationFilter extracts access token
    |
    +-- JwtAuthenticationProvider verifies JWT
    |
    +-- Request-aware verifier retrieves certificate from request
    |
    +-- Computes SHA-256 thumbprint of the certificate
    |
    +-- Compares with JWT cnf.x5t#S256
    |
    +-- Match -> Authentication proceeds
    |
    +-- Mismatch/missing -> Authentication fails
~~~

### 8.2. Binding Verification Interface

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.jwt.Jwt;

public interface CertificateBoundAccessTokenVerifier {

    void verify(HttpServletRequest request, Jwt jwt);
}
~~~

This is an application-defined interface. The implementation must obtain the certificate from the TLS request attribute or from a trusted gateway adapter.

### 8.3. Example Verifier for a Servlet Container Terminating TLS Directly

~~~java
package com.example.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public class ServletCertificateBoundAccessTokenVerifier
        implements CertificateBoundAccessTokenVerifier {

    private static final String CERTIFICATE_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    @Override
    public void verify(HttpServletRequest request, Jwt jwt) {
        Object rawConfirmation = jwt.getClaims().get("cnf");

        if (!(rawConfirmation instanceof Map<?, ?> confirmation)) {
            throw new BadCredentialsException(
                "Certificate confirmation is missing");
        }

        Object rawThumbprint = confirmation.get("x5t#S256");

        if (!(rawThumbprint instanceof String expected)
                || expected.isBlank()) {
            throw new BadCredentialsException(
                "Certificate thumbprint is missing");
        }

        Object rawCertificates =
            request.getAttribute(CERTIFICATE_ATTRIBUTE);

        if (!(rawCertificates instanceof X509Certificate[] certificates)
                || certificates.length == 0) {
            throw new BadCredentialsException(
                "Client certificate is required");
        }

        String actual = sha256Thumbprint(certificates[0]);

        boolean matches = MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.US_ASCII),
            actual.getBytes(StandardCharsets.US_ASCII)
        );

        if (!matches) {
            throw new BadCredentialsException(
                "Access token is bound to another certificate");
        }
    }

    private static String sha256Thumbprint(X509Certificate certificate) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(certificate.getEncoded());

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (Exception ex) {
            throw new BadCredentialsException(
                "Could not calculate client certificate thumbprint", ex);
        }
    }
}
~~~

This example assumes:

- The Servlet container receives the TLS client certificate directly.
- The container has already verified the certificate chain against the trust store.
- The request attribute holds the client certificate chain per the Servlet contract.
- The first certificate in the chain is the client certificate.

The request attribute name and how the certificate is supplied depend on the Servlet container/version. If TLS terminates at an ingress or API gateway, this attribute may not be present.

### 8.4. Wrapping the JWT AuthenticationManager with a Request-Level Check

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

@Configuration
public class CertificateBoundResourceServerConfig {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            certificateBoundAuthenticationManagerResolver(
                JwtDecoder jwtDecoder,
                CertificateBoundAccessTokenVerifier verifier) {

        AuthenticationManager jwtManager =
            new ProviderManager(
                new JwtAuthenticationProvider(jwtDecoder));

        return request -> authentication -> {
            var result = jwtManager.authenticate(authentication);

            if (!(result instanceof JwtAuthenticationToken jwtAuthentication)) {
                throw new BadCredentialsException(
                    "A verified JWT access token is required");
            }

            verifier.verify(request, jwtAuthentication.getToken());

            return result;
        };
    }
}
~~~

Additional imports for this example include `BadCredentialsException`. The resolver returns a manager bound to the current request; do not store `HttpServletRequest` in a singleton or a field shared across requests.

Wire the resolver into the Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> certificateBoundResolver)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/import/**")
                .hasAuthority("SCOPE_orders.import")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(certificateBoundResolver))
        .build();
}
~~~

This configuration uses the resolver to replace the default authentication manager; do not also add `.jwt()` on the same configurer. The `JwtDecoder` inside the manager must still verify the issuer, audience, signature, expiry, and token profile according to the contract.

**Limitation:** this is an integration skeleton for JWT access tokens. Opaque tokens require a manager that uses an introspector, extracts `cnf` from the verified introspection principal, and then performs the same certificate comparison. Never accept a token just because the TLS certificate is valid; binding between the certificate and the token remains mandatory.

### 8.5. Is `http.x509()` Enough to Verify mTLS-Bound Tokens?

No.

~~~java
http.x509(Customizer.withDefaults());
~~~

Spring Security's X.509 support can authenticate an identity based on a client certificate. However, certificate authentication and OAuth access-token certificate binding are two different checks:

- X.509 authentication: which principal does the certificate represent?
- Certificate-bound token: does the request's certificate match the thumbprint bound inside the access token?

Simply enabling `http.x509()` does not automatically check `cnf.x5t#S256` inside a bearer JWT.

## 9. mTLS Behind a Reverse Proxy and API Gateway

In many production systems, TLS terminates at a load balancer or gateway:

~~~text
Client -- mTLS --> API Gateway -- HTTPS/mTLS --> Spring Resource Server
~~~

In that case, the Spring application may see only the gateway's TLS connection, not the client's original certificate. If the gateway forwards the certificate identity via a header, a clear trust contract is required:

1. The gateway must verify the client certificate during the TLS handshake.
2. The gateway must strip any header of the same name sent by the client.
3. The gateway must write the certificate header only after verification.
4. The gateway → application channel must be protected, preferably with mTLS or an equivalent workload identity mechanism.
5. The application must trust the header only from an authenticated gateway, and must not accept direct requests bypassing the gateway.
6. Certificate forwarding must preserve the exact DER/fingerprint or an unambiguous standardized format.
7. Do not use a text DN instead of a thumbprint if the token is bound by `x5t#S256`.

**Never trust `X-Client-Cert` from the Internet.** If an attacker sends a header containing a matching certificate thumbprint, the Resource Server can be tricked if the gateway fails to strip/overwrite the header or if the app can still be reached directly.

### 9.1. Why Not Simply Trust `X-Forwarded-Client-Cert`?

A header name does not prove its origin. Only trust proxy metadata when:

- Network policy ensures requests come solely from the proxy.
- The proxy has actually verified the certificate.
- Any previously client-supplied header has been stripped.
- Integrity/authentication exists on the proxy-to-app hop.
- Direct access paths to the app are restricted.

If these conditions cannot be met, deploy TLS pass-through or a gateway security integration capable of forwarding certificate identity reliably.

## 10. Detailed Comparison: DPoP vs. mTLS

### 10.1. DPoP

**Advantages:**

- Does not require a client certificate at the TLS layer.
- Can work well for mobile/native/public clients.
- Each request includes a proof bound to the HTTP method and URI.
- Can be used with JWT or opaque access tokens if the AS/Resource Server supports binding via token/introspection.
- Can use keys stored in secure hardware/keystore if supported by the client platform.

**Costs and limitations:**

- The client must generate a proof for every request.
- Requires managing private keys and key lifecycles.
- The Resource Server must verify the proof, `ath`, `jkt`, `htm`, `htu`, `iat`, `jti`, and nonce if applicable.
- The replay cache must be shared across instances.
- A reverse proxy can alter the URI observed by the Resource Server; the canonical public URI must be determined accurately.
- DPoP does not sign the request body; it is not a transaction signing mechanism.
- If malware controls the application or can call the key signer, DPoP by itself cannot stop the malware from using the token.

### 10.2. mTLS-Bound Tokens

**Advantages:**

- Leverages standard TLS mutual authentication.
- Well-suited for service-to-service communication in PKI environments.
- No extra DPoP proof JWT is needed per request.
- Can use certificates/private keys in an HSM, keystore, or workload identity infrastructure.
- The TLS client certificate is already validated at the transport layer; the Resource Server only needs to ensure token binding is also verified.

**Costs and limitations:**

- Requires issuing, renewing, revoking, and rotating certificates.
- Requires configuring trust stores and mutual TLS at the ingress/server.
- Reverse proxy/TLS termination must forward client identity securely.
- Certificate renewal can change the thumbprint; old tokens remain bound to the old certificate.
- If the certificate's private key is stolen, an attacker can prove possession.
- Operating a PKI is more complex than standard bearer tokens.

### 10.3. Choosing by Environment

| Context | Starting Point to Consider |
|---|---|
| Public API for browser/native/mobile | Bearer if acceptable under the threat model; DPoP when token replay risk must be reduced |
| Mobile app with hardware-backed keys | DPoP |
| Service-to-service in Kubernetes/service mesh | mTLS-bound token if supported by PKI and gateway |
| Backend with centrally managed HSM/client certificates | mTLS-bound token |
| Many legacy clients supporting only Bearer | Bearer during migration, adding sender-constrained for new clients |
| System needing strong replay protection across multiple API nodes | DPoP with shared replay cache, or mTLS depending on architecture |
| API behind a gateway that already has mTLS identity | Can use mTLS-bound tokens, provided binding is verified end-to-end |

No single model fits every system. Evaluate how private keys/certificates can be protected, where tokens are stored, proxy architecture, replica count, and revocation requirements.

## 11. Token Format and Sender Constraint Are Two Independent Axes

| Token representation | Bearer | Sender-constrained |
|---|---|---|
| JWT | Signed JWT without confirmation binding | JWT with `cnf.jkt` or `cnf.x5t#S256` |
| Opaque | Introspection returns active status and authorities | Introspection also returns `cnf` so the Resource Server can verify proof/certificate |

For example:

**JWT bearer:**

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

**JWT DPoP-bound:**

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "PUBLIC_JWK_THUMBPRINT"
  },
  "exp": 2000000300
}
~~~

**JWT mTLS-bound:**

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.import",
  "cnf": {
    "x5t#S256": "CLIENT_CERT_THUMBPRINT"
  },
  "exp": 2000000300
}
~~~

An opaque token might introspect to:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "PUBLIC_JWK_THUMBPRINT"
  }
}
~~~

or:

~~~json
{
  "active": true,
  "scope": "orders.import",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "CLIENT_CERT_THUMBPRINT"
  }
}
~~~

For opaque tokens, the Resource Server must obtain confirmation data from a trusted introspection endpoint. Do not infer binding from request headers.

## 12. Basic Bearer Resource Server Configuration with Spring Security

If an API accepts only bearer JWTs, a common Servlet configuration is:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BearerResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

For opaque tokens, use:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

In a bearer-only API, the token is verified per request; there is no step proving the request was sent by the exact private key/certificate that received the token. That is what DPoP or mTLS-bound tokens add.

## 13. DPoP Integration in Spring Security

Spring Security provides DPoP APIs at multiple levels depending on version:

| API | Version Milestone | Role |
|---|---|---|
| `DPoPAuthenticationProvider` | 6.5 | Provider that authenticates DPoP-bound access tokens |
| `DPoPProofJwtDecoderFactory` | 6.5 | Creates a decoder to verify DPoP proof JWTs |
| `DPoPProofReplayValidator` | 6.5.12 | Checks `iat` and verifies `jti` has not been reused |
| `DPoPProofReplayValidator.InMemoryCache` | 6.5.12 | In-memory replay cache for single-node setups |
| `OAuth2ResourceServerConfigurer.dPoP(...)` | 7.1 | DSL enabling DPoP-bound access token support |

**Do not assume Spring Security 6.4 or 6.5 has the same DSL as 7.1.** In 6.5 projects, the lower-level provider/factory APIs exist but require corresponding wiring. The high-level `dPoP(...)` DSL is introduced in 7.1.

### 13.1. JWT Resource Server with DPoP on Spring Security 7.1+

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DPoPResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults()))
            .build();
    }
}
~~~

Here:

- `.jwt(...)` configures JWT access token verification.
- `.dPoP(...)` enables DPoP-bound access token support.
- The DPoP proof is sent in the `DPoP` header.
- The access token uses the `DPoP` scheme in the `Authorization` header.
- Scope authorization still runs after authentication.

This configuration requires the Authorization Server to issue access tokens with proper DPoP binding. Enabling DPoP only at the Resource Server does not turn old bearer tokens into sender-constrained tokens.

### 13.2. Opaque Resource Server with DPoP

If AS introspection supports DPoP-bound opaque tokens and returns confirmation data according to the contract, you can configure an opaque token manager together with DPoP support using the version's API:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
    .dPoP(Customizer.withDefaults()))
~~~

The Resource Server must retrieve `cnf.jkt` from the introspection result and verify it against the public key in the proof. If the AS does not return binding data, the Resource Server cannot prove the opaque token is bound to the DPoP key.

### 13.3. Customizable Points in the DPoP Configurer

`DPoPConfigurer` in Spring Security 7.1 provides these extension points:

- `requestMatcher(...)`: selects requests belonging to the DPoP flow.
- `authenticationConverter(...)`: converts the HTTP request into a `DPoPAuthenticationToken`.
- `authenticationSuccessHandler(...)`: handles post-authentication success.
- `authenticationFailureHandler(...)`: handles proof/token errors.

By default, it uses `DPoPAuthenticationConverter` and `DPoPAuthenticationEntryPoint`. Customize these only when there is a clear requirement for request matching, response handling, or integration; do not rewrite proof validation just to change the JSON error format.

### 13.4. What Does Spring Security DPoP Verify?

The DPoP provider and proof decoder work with:

- The access token and token authentication manager.
- The DPoP proof JWT.
- The public JWK and `jkt` binding.
- The HTTP method and resource URI.
- The access token hash `ath`.
- `iat`, `jti`, and other proof requirements.

With a custom decoder/factory, you must retain the framework's default validators. Replacing the validator yourself can accidentally drop method, URI, key binding, or token hash checks.

### 13.5. Replay Cache and Multi-Replica Deployment

Spring Security provides `DPoPProofReplayValidator`, but `InMemoryCache` is suitable only for a single node. If the API runs multiple instances behind a load balancer, a distributed cache is required so every node recognizes previously used `jti` values.

Do not treat the mere presence of `jti` as sufficient. Replay protection requires **storing and checking prior usage state**.

## 14. mTLS-Bound Tokens in Spring Security

Spring Security supports X.509 client certificate authentication via:

~~~java
http.x509(Customizer.withDefaults());
~~~

However, as explained earlier, X.509 authentication is independent of verifying the token's `cnf.x5t#S256`. For an OAuth Resource Server, a request-aware integration layer is needed:

1. Verify the JWT/opaque access token using the Resource Server mechanism.
2. Obtain the client certificate verified by the TLS stack/gateway.
3. Compute the SHA-256 thumbprint over the DER certificate.
4. Read `cnf.x5t#S256` from the authenticated token/introspection principal.
5. Perform a constant-time / secure comparison.
6. Reject if the certificate is missing, the token lacks a binding, or the thumbprint differs.

Do not simply enable `http.x509()` and conclude that bearer tokens are now certificate-bound.

## 15. Do Not Confuse mTLS Client Authentication with Certificate-Bound Access Tokens

These two features are related, but not identical.

| Feature | What Does It Verify? |
|---|---|
| TLS client authentication at the token endpoint | The client requesting a token has a certificate accepted by the AS |
| Certificate-bound access token | The issued token is bound to the certificate thumbprint |
| mTLS at the Resource Server | The API request is established using a valid client certificate |
| `cnf.x5t#S256` verification | The request's certificate is the exact certificate bound to the token |

A client can authenticate to the AS using mTLS, yet if the access token is not bound to the certificate, that token can still behave as a regular bearer token.

Conversely, if the AS issues a certificate-bound access token but the API does not require a client certificate or verify the thumbprint, the Resource Server has not fully enforced the sender constraint.

## 16. Do DPoP and mTLS Replace TLS?

No.

DPoP is a proof at the application layer; mTLS uses TLS client certificates. Both still require HTTPS/TLS to protect the confidentiality and integrity of requests and responses.

DPoP does not replace:

- TLS server authentication.
- Encryption of data in transit.
- CORS policy.
- CSRF policy when credentials are automatically sent by the browser.
- Scope/role/tenant-based authorization.
- Protection of the request body from business logic bugs.

mTLS does not replace:

- Issuer/audience validation of the access token.
- Scope authorization.
- Verifying certificate binding in `cnf`.
- Object-level authorization.
- Token expiry and revocation management.

## 17. DPoP Does Not Sign the Entire HTTP Request

A common misconception is that a DPoP proof protects every byte of the request. DPoP binds specific components such as:

- HTTP method (`htm`).
- Target URI (`htu`).
- Access token (`ath`).
- Proof key (`jkt`).
- Timestamp and proof ID (`iat`, `jti`).

By default, DPoP does not sign the request body or every HTTP header. Therefore, it is not a transaction signing or message-level signature mechanism.

If the business logic requires verifying money transfer details, transaction payloads, or idempotency semantics, an appropriate additional mechanism is needed. Do not infer that DPoP signed a JSON body simply because the proof JWT is signed.

## 18. Protecting Private Keys and Certificates

Sender constraints are only effective if the private key is protected.

### 18.1. For DPoP

- Store private keys in the OS keystore, secure enclave, or hardware-backed keystore where supported by the platform.
- Never place private keys in JavaScript bundles, logs, or analytics.
- Prefer non-exportable keys when permitted by the client platform.
- Have a process for rotating keys and registering new keys with the AS.
- When a key is lost/compromised, revoke/rotate tokens and bind a new key.
- Do not reuse the same private key across too many clients/tenants without a clear reason and policy.

### 18.2. For mTLS

- Store private keys in a controlled HSM, keystore, or secret manager.
- Manage certificate issuance, renewal, revocation, and trust anchors.
- Monitor expiry and rotation schedules.
- Restrict private key usage permissions to the intended workload.
- When a certificate changes, handle existing access tokens bound to the old thumbprint.
- Check certificate revocation policies according to your PKI; do not assume the TLS stack automatically performs CRL/OCSP checks the way your system expects.

## 19. Token Theft: Sender Constraints Reduce Risk but Do Not Eliminate All Risk

| Scenario | Bearer | DPoP/mTLS |
|---|---|---|
| Only the access token is stolen from logs | Can be reused | Missing private key/certificate, so insufficient |
| Both the token and DPoP private key are stolen | Can be used | Can generate valid proofs |
| Both the token and mTLS private key are stolen | Can be used | Can establish TLS with the certificate |
| Client process is compromised | Can use token | Can invoke key signer or use certificate |
| Replaying the same DPoP proof | No proof | Blocked if `jti` replay protection is active |
| Using a proof for a different HTTP method | No method binding | DPoP `htm` mismatch |
| Using a proof for a different URI | No URI binding | DPoP `htu` mismatch |
| Using a different certificate than the token binding | No binding | mTLS thumbprint mismatch |

If an attacker compromises the client itself or can invoke the device's private key signer, sender constraints cannot solve that alone. Endpoint hardening, secure storage, anti-malware, short token lifetimes, least privilege, and monitoring are still required.

## 20. DPoP, Nonces, and Reverse Proxies

DPoP verifies the URI that the client called. However, when the API sits behind a proxy:

~~~text
Client calls:
https://api.example.com/api/orders

Proxy forwards to:
http://orders-service:8080/api/orders
~~~

The Resource Server sees the internal URI `http://orders-service:8080/api/orders`, whereas the DPoP proof has `htu=https://api.example.com/api/orders`.

If the URI comparison is wrong, valid requests are rejected. If arbitrary client-sent `X-Forwarded-Host` or `X-Forwarded-Proto` headers are trusted, an attacker can influence the URI value being checked.

You need to:

- Configure trusted proxy addresses.
- Have the proxy strip client-sent forwarded headers.
- Use forwarded metadata only from authenticated proxies.
- Configure the application to reconstruct the external URI consistently.
- Test host, port, path, reverse-proxy prefix, and HTTPS scheme.
- Never disable `htu` validation just to make requests pass.

## 21. 401, 403, and Sender Proof Errors

| Case | Typical Result | Explanation |
|---|---|---|
| No token sent to private API | 401 | Unauthenticated |
| Bearer token invalid signature/expired | 401 | Invalid token |
| DPoP-bound token sent with `Bearer` scheme | Authentication rejected | Missing DPoP proof per contract |
| Missing DPoP proof | Authentication rejected | Possession not proven |
| Invalid DPoP proof signature | Authentication rejected | Invalid proof |
| `cnf.jkt` differs from proof key | Authentication rejected | Token used with a different key |
| `ath` does not match token | Authentication rejected | Proof bound to a different access token |
| Wrong `htm` or `htu` | Authentication rejected | Proof not intended for the current request |
| Replayed DPoP proof | Authentication rejected | `jti` already used |
| Missing mTLS client certificate | TLS handshake or authentication failure | No certificate presented |
| `cnf.x5t#S256` differs from certificate | Authentication rejected | Token bound to a different certificate |
| Valid token and proof, but missing scope | 403 | Authorization failure |
| Valid token/proof, but wrong tenant ownership | 403/404 per policy | Business authorization |

Actual status codes depend on the entry point, TLS terminator, exception handler, and Spring Security version. A TLS handshake failure can occur before the HTTP request reaches the application, so a JSON 401/403 from a controller is not guaranteed.

### 21.1. DPoP Nonce Challenge

When the server requires a nonce, the client may have to receive a challenge and then send a new request with a new proof. The client should not resend the exact old proof; each request needs a proof with a fresh `jti` and an appropriate `iat`.

### 21.2. Do Not Confuse Authentication and Authorization

DPoP/mTLS proves sender possession. It does not grant scopes.

~~~text
Valid token + valid sender proof
            |
            v
Authentication successful
            |
            v
Check SCOPE_orders.read
            |
            v
Check tenant/order ownership
            |
            v
Allow or deny
~~~

A token bound to the right certificate but missing `orders.write` must still receive 403 when calling a write endpoint.

## 22. Testing Bearer and Sender-Constrained Tokens

A test suite should verify both token validation and proof binding.

### 22.1. DPoP Matrix

| Test case | Expected result |
|---|---|
| DPoP-bound access token + proof with matching key | Authentication succeeds |
| Valid token but missing DPoP proof | Rejected |
| Proof signed with a different key | Rejected |
| Mismatched `cnf.jkt` | Rejected |
| Mismatched `ath` hash | Rejected |
| Wrong `htm` method | Rejected |
| Wrong `htu` URI | Rejected |
| `iat` too old / too far in the future | Rejected |
| Reused `jti` | Rejected |
| Nonce required but missing/wrong | Rejected or challenged again |
| Invalid JWT signature | Rejected even with valid DPoP proof |
| Wrong issuer/audience | Rejected even with valid DPoP proof |
| Missing scope | Authentication passes, authorization returns 403 |
| User belongs to a different tenant | Business authorization rejects |

### 22.2. mTLS Matrix

| Test case | Expected result |
|---|---|
| Trusted client certificate, thumbprint matches token | Authentication succeeds |
| No client certificate | TLS/authentication failure |
| Certificate not accepted by trust store | TLS handshake failure |
| Valid certificate, but thumbprint differs from token | Authentication rejected |
| Invalid JWT signature, even with right certificate | Authentication rejected |
| Wrong audience, even with right certificate | Authentication rejected |
| Token missing `cnf.x5t#S256` on endpoint requiring mTLS binding | Rejected |
| Opaque introspection returns `active=false` | Rejected |
| Valid token, but missing scope | 403 |
| Certificate rotated, but client uses old token | Rejected if thumbprint no longer matches |

### 22.3. Testing Replay Across Multiple Nodes

An important test:

~~~text
1. Send proof P to instance A -> succeeds.
2. Resend the exact same proof P to instance B.
3. Instance B must see that jti has already been used.
4. The second request is rejected.
~~~

If tests run only on a single instance with `InMemoryCache`, they do not prove replay protection works in a cluster.

### 22.4. Testing DPoP with Mock Authentication Is Not Enough

A `MockMvc.with(jwt())` test can attach JWT authentication directly and bypass DPoP proof validation. It is useful for testing scopes/HTTP authorization, but it does not prove:

- `Authorization: DPoP` is parsed correctly.
- The proof JWT is verified.
- `cnf.jkt` matches.
- `ath`, `htm`, and `htu` are compared.
- The `jti` replay cache works.

To test thoroughly, send real HTTP requests through the filter chain with an access token and a proof JWT signed by a test key pair. mTLS tests need a test server/client performing a TLS handshake with test certificates.

### 22.5. Never Use Production Private Keys in Tests

Generate dedicated keys/certificates for tests:

~~~text
DPoP test:
  private key -> signs proof
  public JWK -> proof header
  access token -> matching cnf.jkt

mTLS test:
  test CA -> signs client certificate
  test private key -> TLS handshake
  access token -> matching cnf.x5t#S256
~~~

Never use real production private signing keys or client certificates in test fixtures.

## 23. Observability and Operations

Track separate metric groups:

| Metric/event | Meaning |
|---|---|
| `dpop_proof_invalid_signature` | Invalid proof signature |
| `dpop_jkt_mismatch` | Proof public key does not match token |
| `dpop_ath_mismatch` | Proof bound to a different token |
| `dpop_htm_mismatch` | HTTP method mismatch |
| `dpop_htu_mismatch` | URI mismatch |
| `dpop_nonce_required` | Server requires a nonce |
| `dpop_replay_detected` | `jti` has already been used |
| `mtls_certificate_missing` | Request missing client certificate |
| `mtls_certificate_untrusted` | TLS trust validation failed |
| `mtls_thumbprint_mismatch` | Certificate does not match token |
| `token_signature_invalid` | Invalid JWT access token |
| `token_expired` | Token expired |
| `authorization_denied` | Missing scope/role or business permission |

The metric names above are suggestions for instrumentation; this does not imply all of them are emitted automatically by Spring Security.

Do not log:

- Raw bearer/DPoP access tokens.
- Full DPoP proof JWTs.
- Private keys or client certificate private key material.
- Client secrets.
- Full certificate chains if policy restricts it.
- Unnecessary PII claim contents.

You may log hashed `kid`/thumbprints or internal references, error types, request IDs, and issuer references according to policy.

## 24. Migration Workflow from Bearer to Sender-Constrained

A practical rollout path:

**Step 1 — Inventory clients.** Identify which clients can hold private keys, which support client certificates, and which only support bearer tokens.

**Step 2 — Choose the mechanism.** DPoP for clients needing application-layer proofs; mTLS for workloads with PKI; retain bearer for legacy clients during transition if the threat model permits.

**Step 3 — Update the Authorization Server.** Issue `token_type=DPoP` and `cnf.jkt`, or issue certificate-bound access tokens with `cnf.x5t#S256`.

**Step 4 — Configure the Resource Server.** Enable DPoP support or implement a certificate binding verifier matching the version/framework.

**Step 5 — Protect keys/certificates.** Establish secure storage, rotation, revocation, and provisioning workflows.

**Step 6 — Protect against replay.** Configure nonces if needed, replay cache, and shared state across nodes.

**Step 7 — Verify reverse proxies.** Ensure `htu` and client certificate identity are forwarded across a clear trust boundary.

**Step 8 — Run negative tests.** Stolen tokens, invalid proofs, wrong certificates, replays, wrong audiences, missing scopes.

**Step 9 — Roll out with observability.** Start with clients that can support it, measuring errors and latency.

**Step 10 — Narrow down bearer usage.** Once telemetry shows clients have migrated, enforce sender constraints on routes/clients requiring high protection.

Do not enforce DPoP or mTLS before both the AS and clients support it; if only the Resource Server changes, old bearer tokens will not automatically gain bindings.

## 25. Misconceptions to Avoid

**"A signed JWT cannot be replayed."** False. A stolen bearer JWT can still be reused until it expires or is rejected by another mechanism.

**"Bearer tokens and JWTs are opposite types."** False. Bearer is a token usage model; JWT is a representation format.

**"Sender-constrained tokens are always JWTs."** False. Opaque tokens can be bound to a key/certificate if introspection returns confirmation data.

**"DPoP only needs a valid proof signature."** False. You must also verify `jkt` binding, `ath`, `htm`, `htu`, timestamps, `jti`, and nonce when required.

**"A DPoP proof can be reused across multiple requests."** No. Each request needs an appropriate proof; replay protection must reject previously used `jti` values.

**"DPoP signs the request body."** No. DPoP binds the method, URI, and access token, but does not sign the entire body by default.

**"mTLS client authentication at the token endpoint automatically makes all access tokens certificate-bound."** No. The AS must be configured to issue tokens with certificate binding, and the Resource Server must verify the confirmation claim.

**"Enabling `http.x509()` already checks `cnf.x5t#S256`."** False. X.509 authentication does not automatically compare the certificate against the token binding.

**"Simply trusting `X-Client-Cert` from the gateway is enough."** False if the gateway has not stripped client-sent headers, the proxy-to-app channel is unprotected, or the app has access paths bypassing the proxy.

**"DPoP replaces HTTPS."** False. DPoP is an application-layer proof; TLS is still required.

**"mTLS replaces issuer/audience validation."** False. Certificate binding does not prove the token was issued by a trusted AS for the right API.

**"If a token has `cnf`, the API automatically knows how to verify it."** False. The Resource Server must have appropriate integration to verify the request's proof/certificate.

**"An in-memory DPoP replay cache works for any cluster."** False. An in-memory cache is shared only within a single process/node.

**"A non-exportable DPoP private key means malware cannot use it."** Not necessarily. Malware can drive the application to call the key signer even without reading the key bytes.

**"Sender constraints replace scope and object authorization."** False. They prove possession, not permission to access resources.

**"An old bearer token can be converted to DPoP by adding a DPoP header."** False. The AS must issue a token with a `cnf.jkt` binding; a proof header does not retroactively bind a key to an old token.

## 26. Self-Check Questions

**1.** What does a bearer token mean?

> Any party possessing the token can present it for use; the Resource Server does not require a separate proof of a client key.

**2.** What does a sender-constrained token add?

> The token is bound to a public key or client certificate; the request must demonstrate possession of the corresponding credential.

**3.** Which mechanism uses `cnf.jkt`?

> DPoP; it contains the JWK SHA-256 thumbprint of the public key that signs the proof.

**4.** Which mechanism uses `cnf.x5t#S256`?

> mTLS certificate-bound access tokens; it contains the SHA-256 thumbprint of the client's X.509 certificate.

**5.** Which scheme is used to send a DPoP access token?

> `Authorization: DPoP <access-token>`, accompanied by a `DPoP` header containing the proof JWT.

**6.** Which scheme is typically used to send an mTLS-bound access token?

> `Authorization: Bearer <access-token>`, while the client must present the matching certificate in the TLS handshake.

**7.** What is the purpose of `ath` in a DPoP proof?

> Binds the proof to the exact access token sent in the request using a SHA-256 hash.

**8.** What are `htm` and `htu` used for?

> Binding the proof to the HTTP method and URI of the request.

**9.** Why must `jti` be checked?

> To detect proofs that have already been used and prevent replay.

**10.** Starting from which version does Spring Security have the DPoP DSL?

> `OAuth2ResourceServerConfigurer.dPoP(...)` is available from Spring Security 7.1; lower-level provider/factory APIs exist from 6.5.

**11.** Starting from which version is `DPoPProofReplayValidator` available?

> Spring Security 6.5.12.

**12.** Is `DPoPProofReplayValidator.InMemoryCache` suitable for a multi-node cluster?

> No. A distributed cache is required so every node sees used `jti` values.

**13.** Does `http.x509()` automatically verify a token's `cnf.x5t#S256`?

> No. The thumbprint of the request's certificate must be compared against the confirmation claim in the access token.

**14.** Why must you be careful when TLS terminates at a reverse proxy?

> The Resource Server may see only the proxy's certificate; a forwarded client certificate should be trusted only if the proxy is authenticated and headers cannot be spoofed by clients.

**15.** Does DPoP sign the request body?

> Not by default. It binds the method, URI, and access token; transaction/body integrity requires another mechanism if business logic demands it.

**16.** Does a sender-constrained token replace scope authorization?

> No. After authentication and proof verification, the API must still check scopes, roles, tenants, and resource permissions.

## 27. References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens and how they are sent in the HTTP Authorization header.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, key binding, `jkt`, `ath`, `htm`, `htu`, nonce, and replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): TLS client authentication and certificate-bound access tokens.
- [RFC 7800 — Proof-of-Possession Key Semantics for JWTs](https://www.rfc-editor.org/rfc/rfc7800): the `cnf` claim and confirmation methods.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK, public keys, and JWK thumbprint context.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims and token timestamps.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): retrieving status and claims of opaque tokens.
- [Spring Security — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP flow, `cnf.jkt`, request headers, and proof.
- [Spring Security — OAuth2ResourceServerConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html): `dPoP(...)` and Resource Server configurations; DPoP DSL from 7.1.
- [Spring Security — DPoPConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.DPoPConfigurer.html): request matcher, converter, and success/failure handlers.
- [Spring Security — DPoPAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html): provider that authenticates DPoP-bound tokens.
- [Spring Security — DPoPProofJwtDecoderFactory API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofJwtDecoderFactory.html): decoder factory and default proof validators.
- [Spring Security — DPoPProofReplayValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.html): replay validation, `iat`, `jti`, cache, and clock skew.
- [Spring Security — DPoPProofReplayValidator.InMemoryCache API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.InMemoryCache.html): single-node limitations and distributed cache options.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring clients and certificate-bound access tokens.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): client certificate authentication in Servlet security.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWT access tokens, issuer, audience, and JWK Set.

**Conclusion:** Bearer tokens allow any party holding the token to present it for use; sender-constrained tokens additionally require a proof bound to the client's key or certificate. DPoP accomplishes this with a per-request proof JWT and `cnf.jkt` binding; mTLS accomplishes it with a TLS client certificate and `cnf.x5t#S256` binding. Spring Security provides a built-in DPoP DSL starting in 7.1, while mTLS certificate-bound tokens require ensuring the Resource Server compares the request's actual certificate against the token's confirmation claim. Regardless of the mechanism used, issuer/audience/expiration, scopes, and resource permissions must still be verified; sender constraints reduce the risk of stolen-token replay, but do not replace TLS, key protection, or authorization.
