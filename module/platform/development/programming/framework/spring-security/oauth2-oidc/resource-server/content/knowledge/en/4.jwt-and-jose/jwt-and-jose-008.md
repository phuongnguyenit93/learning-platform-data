# JWK, JWKS, and Representing Public Keys

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, the Authorization Server issues digitally signed JWT access tokens; the Resource Server needs **trusted public keys** to verify signatures before using claims in the token. JOSE defines a JSON format for representing keys called **JSON Web Key (JWK)**, and a format for publishing a collection of keys called **JSON Web Key Set (JWKS)**. This is the foundation allowing APIs to verify JWTs without sharing the private signing key.

For example, the Resource Server receives:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
~~~

The JWT may contain a JOSE header declaring algorithm **RS256** and key identifier **kid = shop-sign-2026-11**. The Resource Server picks the matching public key from the trusted issuer's JWKS, verifies the signature, and then validates issuer, audience, lifetime, and access permissions. **Having JWK/JWKS only solves key representation and management; it does not complete token authentication and authorization on its own.**

## 1. Placing JWK and JWKS Properly Within JOSE

**JOSE (JSON Object Signing and Encryption)** is the standard suite for JSON-based signing, encryption, and security key representation. Concepts commonly seen together:

| Concept | Role | Distinctions to keep in mind |
|---|---|---|
| **JWS (JSON Web Signature)** | Describes data and a digital signature/MAC to verify integrity and origin | Does not encrypt content |
| **JWE (JSON Web Encryption)** | Describes encrypted data and encryption metadata | Different purpose from JWS; JWTs can use JWE |
| **JWT (JSON Web Token)** | Format representing a claims set as a token; can be protected with JWS/JWE | Claims and signatures are two separate aspects |
| **JWK (JSON Web Key)** | Represents **a single key** in JSON | Can represent a public key, private key, or symmetric key depending on fields |
| **JWKS (JSON Web Key Set)** | Collection of **multiple JWKs** in one JSON object | Merely a key-set format, not a token |
| **kid (Key ID)** | Key identifier hint to pick the right JWK from a key set | Not a signature, not an independent source of trust |

Visualizing the flow:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|Signs JWT with private key| T[JWT / JWS]
    AS -->|Publishes public JWK| S[JWKS endpoint]
    CL[Client] -->|Bearer JWT| RS[Spring Security Resource Server]
    T -.-> CL
    RS -->|Fetches public key by issuer + kid| S
    RS -->|Verifies signature and claims| V{Token valid?}
    V -->|Yes| A[Check API/resource permissions]
    V -->|No| D[401 Unauthorized]
~~~

**Public keys used to verify signatures** may be shared publicly. **Private keys used to sign** must remain on the token issuer or in a controlled key management system (KMS/HSM); Resource Servers normally do not need and must never receive the private key.

JWK is not the only key format. The same RSA or EC key can be represented as a JWK, PEM/DER, or inside an X.509 certificate; the packaging differs while the underlying mathematical key material corresponds.

## 2. Structure of a JWK

A JWK is a JSON object. Which fields appear depends on the **key type (kty)** and intended usage.

Example **RSA public key** JWK, with a placeholder modulus to illustrate structure:

~~~json
{
  "kty": "RSA",
  "kid": "shop-sign-2026-11",
  "use": "sig",
  "alg": "RS256",
  "n": "<base64url-encoded-RSA-modulus>",
  "e": "AQAB"
}
~~~

This example is **not a usable key for testing**, because **n** is a placeholder. In real data, **n** and **e** must be valid Base64URL values per the JWK specification. **AQAB** commonly represents the RSA public exponent 65537.

| Property | Meaning | Required for every JWK? |
|---|---|---|
| **kty** | Key type: RSA, EC, OKP, oct... | Yes |
| **kid** | Key identifier aiding selection/rotation | No; very useful when multiple keys exist |
| **use** | Declared intended usage: **sig** (signing/verification) or **enc** (encryption/decryption) | No |
| **key_ops** | Key operations supported, such as **sign**, **verify**, **encrypt**, **decrypt** | No |
| **alg** | Algorithm intended for use with the key, e.g., RS256, PS256, ES256 | No |
| **n**, **e** | RSA modulus and public exponent | Yes for RSA public keys |
| **crv**, **x**, **y** | Curve name and public point coordinates | Yes for EC public keys |
| **x5c** | X.509 certificate chain associated with the key | No |
| **x5t**, **x5t#S256** | X.509 certificate thumbprints | No |

Do not confuse **use** and **key_ops** with user business permissions. They describe whether the **cryptographic key** is intended for signing/verifying or encrypting/decrypting. They are not equivalent to OAuth scopes or roles.

### 2.1. RSA Key Type

A public RSA JWK contains:

- **kty = RSA**
- **n**: modulus, a positive integer encoded as Base64URLUInt.
- **e**: public exponent, also Base64URLUInt.

Abbreviated example:

~~~json
{
  "kty": "RSA",
  "n": "<base64url-rsa-modulus>",
  "e": "AQAB",
  "kid": "rsa-01"
}
~~~

To verify an **RS256** signature, the Resource Server uses **n/e** to reconstruct the RSA public key, then runs RSA signature verification with SHA-256 per JWS.

**n/e are not secret.** Conversely, an RSA private JWK may contain **d**, **p**, **q**, **dp**, **dq**, **qi**, and other private parameters. Those values **must never be published in a public JWKS**.

### 2.2. EC Key Type

An Elliptic Curve public key typically has:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "<base64url-x-coordinate>",
  "y": "<base64url-y-coordinate>",
  "kid": "ec-01",
  "use": "sig",
  "alg": "ES256"
}
~~~

- **crv** selects the curve, such as P-256, P-384, or P-521.
- **x** and **y** are public point coordinates on the curve.
- **d** (if present) is the private key component and must never be published.
- **ES256** typically uses ECDSA over P-256 with SHA-256.

The **x/y** placeholders only illustrate field names, not valid coordinates. With EC, coordinate sizes and encoding must strictly match the chosen curve. Verifiers must also validate public point validity and algorithm constraints through a trusted cryptographic library.

### 2.3. OKP Key Type

JOSE also supports **Octet Key Pair (OKP)** curves such as Ed25519:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "x": "<public-key-base64url>",
  "kid": "ed25519-01",
  "use": "sig",
  "alg": "EdDSA"
}
~~~

With OKP, the public component is **x**; the private key uses **d**. There is no **x/y** coordinate pair as in EC JWKs. EdDSA support depends on the Spring Security version, Nimbus JOSE, and token issuer; never assume a library supports it merely because an OKP key appears in a JWKS.

### 2.4. Symmetric Key Type **oct**

A JWK with **kty = oct** represents a symmetric secret key, such as a key used with HMAC:

~~~json
{
  "kty": "oct",
  "k": "<secret-key-material-base64url>",
  "alg": "HS256"
}
~~~

Here the **k** field **contains a secret**, not a public key. If this JWK is exposed in a publicly accessible JWKS, anyone can learn the HMAC key and forge MACs. Therefore:

> **A public JWKS used to verify asymmetrically signed JWTs should contain only public keys. Never publish JWKs containing private key parameters or symmetric secret keys.**

Distinguish **JWK as a general format** from a **public JWKS as a filtered key set safe for distribution**. The spec does not make every JWK public.

## 3. Encoding Rules for Key Values

Many integration bugs come from confusing key encodings with raw bytes or text.

### 3.1. Base64URL Differs from Standard Base64

Base64URL modifies two characters to be URL-safe:

| Standard Base64 | Base64URL |
|---|---|
| **+** | **-** |
| **/** | **_** |
| May include **=** padding | Standard JWK/JWS representations omit padding |

For RSA keys, **n/e** are encoded as **Base64URLUInt**, meaning the positive integer as big-endian octets encoded in unpadded Base64URL per JOSE rules. You cannot replace them with decimal strings, raw PEM blocks, or Base64 of printable text.

For EC keys, **x/y** are fixed-length octet strings per curve encoded in Base64URL. Coordinate lengths cannot be altered arbitrarily without corrupting the key.

### 3.2. JWK, PEM, and X.509 Certificates

| Representation | Contents | Typical markers |
|---|---|---|
| **JWK** | Key components in JSON: kty, n/e, crv/x/y... | JSON object |
| **JWKS** | JSON object with a **keys** array containing JWKs | **{ "keys": [...] }** |
| **PEM public key** | DER public key wrapped in Base64 with BEGIN/END lines | **-----BEGIN PUBLIC KEY-----** |
| **X.509 certificate** | Public key plus subject, issuer, validity, cert signature, and metadata | **-----BEGIN CERTIFICATE-----** |

A JWKS may include **x5c** to supply a certificate chain, though that **does not turn a JWK into an X.509 certificate**. In JWK, **x5c** values use standard Base64 of DER certificates, unlike the Base64URL used for **n/e/x/y**.

If certificates are used to authenticate an issuer or key, understand the trust policy and validate the certificate chain properly. **The mere presence of x5c does not prove a key is trustworthy.** The same token can be verified using a trusted raw public key without needing x5c.

## 4. JWKS: A Set of Keys in JSON

A **JWKS** is a JSON object with a **keys** property holding an array of JWKs. Example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-sign-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "<old-public-modulus>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "shop-sign-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<new-public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

The **n** values here are placeholders. In a real JWKS, both JWKs require valid public key data. Having multiple keys lets the Authorization Server **rotate signing keys** while still allowing Resource Servers to verify older non-expired tokens.

A JWKS may contain keys of different types or algorithms. Not every key in the set is suitable for every token. When selecting a key, consider at least **kid**, **kty**, permitted algorithms, **use/key_ops** if declared, and issuer trust policy.

### 4.1. What Does **kid** Do?

Example JWT with JOSE protected header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "shop-sign-2026-11"
}
~~~

Upon receiving the token, the Resource Server can:

1. Identify the issuer and its corresponding trust configuration.
2. Select the **JWKS of the configured trusted issuer**, never relying on a URL arbitrarily supplied by the token.
3. Locate the JWK with matching **kid** that fits the permitted verification algorithm.
4. Verify the signature using the public key from that JWK.
5. Validate required claims and authorization policies.

**kid is a lookup key, not security proof.** Anyone can put any **kid** in a self-crafted JWT; only when signature verification succeeds using a key from a trusted source does the token pass cryptographic authentication.

JOSE does not require every JWS to include **kid**. When a JWKS holds multiple keys, assigning a unique, stable **kid** to each key enables efficient selection and rotation. Avoid reusing the same **kid** for different key material in an active set, as that can cause wrong-key selection or cache conflicts.

### 4.2. **alg** in JWK vs. JOSE Header

- **alg** in the JWS protected header indicates the algorithm the token claims was used to produce the signature/MAC.
- **alg** in a JWK (if present) indicates the algorithm intended for use with that key.

Neither **replaces the Resource Server's permitted-algorithm configuration**. The API must explicitly restrict accepted algorithms, such as RS256, per contract with the Authorization Server; never blindly trust self-declared token values.

For instance, if the API expects only RSA RS256 signatures, a token declaring **HS256** must never cause the server to reinterpret an RSA public key as a shared secret to check a MAC. That is **algorithm confusion**. A token declaring **alg = none** must also never be treated as a valid signed access token when the API requires signed JWTs.

### 4.3. **use**, **key_ops**, **x5c**, and Thumbprints

- **use = sig** indicates a key intended for signing/verification; **use = enc** is for encryption/decryption.
- **key_ops** declares specific operations, such as **verify**. If both **use** and **key_ops** appear, they must be consistent per specification.
- **x5c** is optional certificate metadata tied to the public key.
- **x5t** and **x5t#S256** are X.509 certificate thumbprints; not synonymous with **kid**.
- **JWK Thumbprint** per RFC 7638 is a canonical hash computed from specified public key fields; it can serve as a basis for generating key IDs, though **kid is not required to be a thumbprint**.

These properties help describe and select keys. They do not alter requirements to verify the JWKS source, verification algorithm, and token validity.

## 5. JWKS Endpoint and OIDC/OAuth Metadata Discovery

An Authorization Server commonly publishes its public JWKS over HTTPS, for example:

~~~text
https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

This is merely a URL style example; **there is no universal rule requiring every issuer to use `/jwks.json` or `/certs`**. Obtain the exact endpoint from metadata published by the Authorization Server or trusted configuration.

In OIDC, the **OpenID Provider Configuration** document provides the **jwks_uri** field:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token"
}
~~~

The JSON above illustrates relevant fields, not a complete metadata document. OAuth 2.0 Authorization Server Metadata under RFC 8414 also defines **jwks_uri**.

### 5.1. Chain of Trust

The Resource Server must be configured with a **trusted issuer** (or an administratively trusted JWKS URI). Only then does it fetch metadata/JWKS over HTTPS with certificate verification.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as OAuth Client
    participant API as Spring Resource Server
    AS->>AS: Holds private signing key
    AS-->>C: Issues signed JWT access token
    C->>API: Authorization: Bearer JWT
    API->>AS: Fetch trusted issuer metadata/JWKS over HTTPS
    AS-->>API: Public JWK Set (with matching kid)
    API->>API: Verify JWT signature with public key
    API->>API: Validate iss, aud, exp, nbf, and permissions
    API-->>C: 200 if authorized; otherwise deny
~~~

In practice, keys are usually cached, so **not every request calls the JWKS endpoint**. Initial fetch, cache misses, refreshes on encountering a new **kid**, and refresh intervals depend on library and deployment configuration.

**Never use an unverified `iss` string from a token to arbitrarily fetch any URL.** In multi-issuer systems, choose only among pre-registered trusted issuers/JWKS; a token from another issuer must never pick its own verification key source.

### 5.2. JOSE Headers Containing URLs Must Be Handled Carefully

JOSE headers can include parameters such as **jku** (JWK Set URL), **jwk** (embedded key), and **x5u** (certificate URL). While useful in certain protocols, they create severe danger if an externally supplied JWT can force the Resource Server to load keys from arbitrary locations.

Example of an **unsafe** design:

~~~text
Receive arbitrary JWT
  -> read token's jku
  -> fetch key from token-specified URL
  -> use that key to accept the token
~~~

An attacker can sign their own token, host their own public key, and point **jku** to that key. Beyond accepting forged tokens, fetching uncontrolled URLs can introduce SSRF vulnerabilities.

The proper pattern for a typical Resource Server is to obtain the JWKS from the **configured trusted issuer or URI**, restrict redirects/hosts and certificates, and match **kid**. Never trust a key merely because the token included or linked to it.

## 6. Configuring Spring Security Resource Server with JWKS

Suppose the Orders API trusts only issuer:

~~~text
https://login.example.com/realms/shop
~~~

and valid access tokens must carry audience **orders-api**.

### 6.1. Using **issuer-uri** for Discovery

With Spring Boot and Spring Security versions supporting JWT Resource Server configuration, declare:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Under the corresponding default behavior, Spring Security can obtain verification keys from the issuer's metadata/JWKS and use public keys to verify JWT access tokens. **issuer-uri** sets up issuer validation; audience is governed by the API's own policy rather than inferred from a JWK.

Endpoint protection configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Here **SCOPE_orders.read** is an authority that Spring Security can map from the JWT access token's **scope/scp** claim. Verifying a JWT with JWKS does not synthesize scopes or roles by itself. Only tokens passing both authentication and applicable permission policies are granted access.

**Version note:** Supported configuration properties and algorithms can vary across Spring Boot/Spring Security versions. Always verify against your project's version documentation. The examples here present the common JWT Resource Server pattern.

### 6.2. Specifying the JWKS URI Directly

When the exact endpoint is known, you can also configure **jwk-set-uri**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Direct configuration tells the Resource Server where to fetch public keys without depending on metadata discovery at startup. **Keeping issuer-uri** ensures validation of the issuer claim. Configuring only a JWKS URI without corresponding issuer validation can omit **iss** verification depending on how `JwtDecoder` is configured—a security mistake to avoid.

**Never configure the JWKS URI from a client request.** This URI belongs to the service's trust policy, must be administratively managed, served over HTTPS, and restricted to valid verification sources.

### 6.3. Restricting Accepted Signing Algorithms

For tokens using RS256, you can explicitly select the verification algorithm when constructing **JwtDecoder** if customization is needed:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(
                "https://login.example.com/realms/shop/protocol/openid-connect/certs")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(
            "https://login.example.com/realms/shop"
        ));
        return decoder;
    }
}
~~~

This example shows that **accepting RS256 is an API configuration decision**. When defining a custom `JwtDecoder` like this, **ensure audience validation** and all other system checks are included explicitly; do not expect Spring Boot's automatic properties to apply once you replace the decoder bean. For simpler setups, Spring Boot properties as in Section 6.1 are usually easier to maintain.

**Never skip `iss/aud/exp/nbf` validation just because signature verification passed.** A validly signed token could belong to another service or be expired.

### 6.4. Resource Servers Do Not Need the Issuer's Private Key

With RS256/ES256/EdDSA:

- The Authorization Server holds the private key and signs tokens.
- The public JWKS contains public keys.
- The Resource Server fetches public keys and verifies signatures without being able to sign tokens on the issuer's behalf.

If HS256 is used, both signer and verifier must hold the same HMAC secret. Distributing that secret across many Resource Servers expands the set of parties able to impersonate the issuer; a public JWKS is unsuitable for distributing secrets. In multi-API architectures, asymmetric signatures cleanly separate responsibilities and minimize where signing keys live.

## 7. Practice: Tracing a JWT from Header to Public JWK

Suppose the Authorization Server issues a JWT with JWS protected header:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "shop-sign-2026-11"
}
~~~

And payload (abbreviated):

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

These are illustrative components, not a real independently verifiable JWT. In JWS Compact Serialization, the three parts are separated by dots:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Verification steps:

1. The API receives the **Bearer JWT** and decodes the JWS structure enough to inspect the header and claims; at this stage the data is **untrusted**.
2. The API selects the issuer from its configured trust list and fetches that issuer's JWKS.
3. The API locates the key matching **kid = shop-sign-2026-11**; confirms **kty = RSA**, permitted algorithm RS256, key usage, and necessary constraints.
4. The API uses the public key in the JWK to verify the JWS signature over the corresponding encoded header and payload.
5. If signature verification succeeds, the API checks **iss**, **aud**, **exp**, **nbf** (if present), and required claim policies including token type where applicable.
6. The API enforces **orders.read**, tenant, order ownership, or other rules before returning data.

Note: **Base64URL decoding** to view claims is **not authentication**. Prior to signature verification, anyone can alter the payload. Use unverified data solely to assist safe policy lookup, never to grant permissions.

## 8. Rotation: When the Authorization Server Changes Signing Keys

Signing keys must be rotated periodically or immediately upon suspected compromise. JWKS enables transitioning between old and new keys without invalidating all existing valid JWTs immediately.

Example:

| Time | Authorization Server | Public JWKS | Impact on Resource Server |
|---|---|---|---|
| **T0** | Signing with key A | Public key A, kid A | Verifies existing JWTs with A |
| **T1** | Preparing key change | Public keys A **and B** | Can fetch/cache key B before needed |
| **T2** | Begins signing new tokens with B | Public keys A **and B** | Verifies old tokens with A, new tokens with B |
| **T3** | Tokens signed with A expire and caches refresh | Only public key B remains | Retires A once no valid tokens need it |

Good practice is **publish-before-use**: publish the new public key before signing tokens with the new private key so Resource Servers have time to observe it. The overlap window must account for access token lifetimes, clock skew, JWKS caching, refresh latency, and revocation mechanisms.

### 8.1. Why Keep the Old Key for a While?

A JWT signed with key A **is not automatically re-signed** when the issuer switches to key B. To verify still-unexpired tokens signed by A, the Resource Server still needs public key A. Removing A from the JWKS too early causes tokens valid per **exp** to be rejected because their verification key is gone.

If private key A is compromised, the situation changes: the issuer may need to **revoke or remove A immediately** to curb forged tokens, even if some valid tokens are disrupted. Routine JWKS rotation is not an instant token-revocation mechanism; separate incident-response policies are required.

### 8.2. Caching and Unseen **kid** Values

Resource Servers typically cache the JWKS to avoid network calls on every token. Upon seeing a new **kid**, a library may attempt to refresh keys, though exact behavior depends on the implementation, cache TTL, and rate limits.

Common operational issues:

- Issuer starts signing with B while the JWKS still lists only A.
- JWKS includes B, yet a proxy/CDN cache still serves an old response.
- A **kid** is reused for different key material, causing caches and key selectors to pick the wrong key.
- JWKS source is unreachable; tokens with a **kid** absent from cache cannot be verified.
- Resource Server receives a token from another issuer and tries to find its **kid** in the current JWKS.

Monitor authentication failure counts, JWKS fetch status, and key rotation timing. Never work around JWKS connectivity errors by **skipping signature verification** or accepting unverified tokens. When a valid cached public key is already present, token verification behavior depends on decoder and cache design; do not assume the JWKS endpoint must be hit on every single request.

## 9. Common Security and Operational Pitfalls

### 9.1. Publishing a Private Key in the JWKS

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "n": "<modulus>",
      "e": "AQAB",
      "d": "<PRIVATE-EXPONENT-DO-NOT-PUBLISH>"
    }
  ]
}
~~~

The **d** field is secret material. If a public JWKS exposes the private exponent or other private parameters, attackers can use that key to sign forged JWTs indistinguishable from the issuer's. The signing key must be rotated urgently under incident response procedures—not merely masked in logs or UIs.

### 9.2. Treating **kid** as Determining Trust

A string **kid = admin** grants no admin privileges and proves no key validity. **kid** only helps find a key in an already trusted source. Likewise, never concatenate **kid** into file paths or SQL queries without strict validation.

### 9.3. Trusting **jku** or **jwk** Supplied by an Arbitrary Token

A JWT cannot choose the public key an API uses to accept its own signature. Key sources must be configured server-side or resolved via fixed trust policies, never via arbitrary sender-provided URLs.

### 9.4. Omitting Issuer and Audience Validation

An access token validly signed by the same identity provider may still be intended for a different API. The Resource Server must check matching **aud** and **iss** per contract; having the right JWK does not authorize access to every API.

### 9.5. Confusing an ID Token with an Access Token

An OIDC ID Token may be signed with a key from the exact same OpenID Provider JWKS. That **does not mean** the ID Token is an access token for the Resource Server. Validate audience, ecosystem token type/profile, and API-specific policies.

### 9.6. Allowing Unrestricted Token-Chosen Algorithms

**alg = none**, substituting HS256 for RS256, or downgrading to weak/unapproved algorithms can lead to invalid verification if the library or config is overly permissive. Resource Servers must constrain allowed algorithms and compatible key types.

### 9.7. Serving JWKS Over HTTP or Disabling TLS Verification

A JWKS holds only public keys, yet its **integrity and authenticity** are critical. If swapped with an attacker's public key, the Resource Server risks verifying attacker-signed tokens. Thus the JWKS endpoint requires HTTPS with certificate verification—never assume "it's only public keys so HTTP is fine."

### 9.8. Sharing One JWKS Across All Tenants/Issuers

In multi-tenant systems, each issuer may use distinct key sets; **kid** values can collide across issuers. Key lookup and validators must be bound to the trusted issuer, not solely to a global **kid**.

### 9.9. Confusing **JWK use = sig** with Business Permissions

**use = sig** indicates the public key is intended for signatures. It is not the **orders.read** permission or **ROLE_ADMIN**. Scopes, roles, permissions, and per-resource rules belong to Resource Server authorization.

## 10. Illustrative Scenarios: Which API Should Accept the Token?

Suppose the Orders API trusts issuer **https://login.example.com/realms/shop**, audience **orders-api**, algorithm **RS256**, and permission **orders.read**.

| Case | Expected outcome | Reason |
|---|---|---|
| JWT signed RS256 with private key matching trusted JWK, valid issuer/audience, unexpired, sufficient scope | May proceed after business checks | JWT authentication and permissions match |
| JWT uses matching **kid**, but signature fails against public key | **401** | kid does not substitute for signature |
| JWT signed by valid issuer, but audience is **payments-api** | **401** | Token not issued for Orders API |
| JWT header has **jku** pointing to sender's self-hosted JWKS | **Reject arbitrary key source** | jku is outside trust policy |
| Validly signed JWT, but expired | **401** | Invalid **exp** |
| Validly signed JWT meeting token checks, but missing **orders.read** | **403** | Valid token lacking business permission |
| JWT signed with key B, JWKS cache knows only A | Cannot verify until B is fetched | Requires coordinating rotation and cache |
| Public JWKS contains **d** or **k** secret | Key compromise incident to remediate | Public endpoints must never leak secrets |

Status codes apply to typical Bearer API designs. Some systems return 404 to hide resource existence; that is an additional authorization policy.

## 11. Reading a Real JWKS Safely Without Exposing Secrets

To inspect a public JWKS structure in an authorized environment, query the known HTTPS endpoint (hypothetical example):

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

If **jq** is available, view only public key metadata:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '.keys[] | {kid, kty, use, alg, crv}'
~~~

Illustrative output:

~~~json
{
  "kid": "shop-sign-2026-11",
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "crv": null
}
~~~

You never need to copy a private key to debug a Resource Server. Seeing **d**, **p**, **q**, or **k** containing a symmetric secret in a public JWKS signals a severe misconfiguration. Being able to download a public key with curl **does not prove a token is valid**; JWTs must still pass signature verification and API validators.

When running token tests, use only synthetic or test-environment tokens; never record real access tokens in docs, issue trackers, shared logs, or shared shell commands.

## 12. Questions to Answer When Designing JWKS for a Resource Server

1. **Which issuers are trusted?** Does each API/tenant have an explicit issuer and corresponding JWKS source configured?
2. **How are keys obtained?** Via verified OIDC/OAuth metadata or an administratively configured JWKS URI?
3. **What does the key set contain?** Only public keys and appropriate metadata; could any private/symmetric secrets leak?
4. **Which algorithms verify signatures?** Are RS256/ES256/permitted algorithms restricted to match the token contract?
5. **How is `kid` managed?** Is there a clear `kid` assignment policy, avoiding reuse across key material changes and supporting overlap rotation?
6. **What checks follow signature verification?** Are issuer, audience, lifetime, token type, scopes/permissions, and resource rules configured?
7. **What happens if the JWKS is temporarily unreachable?** Are caching, monitoring, and rotation procedures in place; are unverifiable tokens strictly rejected?
8. **How is key compromise handled?** Are emergency key rotation, shortened lifetimes, revocation (where supported), and operational communication planned?

## Conclusion

A **JWK** represents a single cryptographic key in JSON; a **JWKS** is a collection of JWKs enabling an Authorization Server to publish **public keys** for verifying JWT signatures. Fields like **kty**, **n/e**, **crv/x/y**, **kid**, **use**, and **alg** describe and aid key selection, yet **do not establish trust by themselves**.

In Spring Security Resource Server, fetch the JWKS from a configured trusted issuer source, verify the JWS with the appropriate key and algorithm, and validate **iss**, **aud**, lifetime, and business permissions before returning data. Proper JWKS management also requires overlap-aware key rotation, appropriate caching, and strictly never exposing private keys or symmetric secrets on public endpoints.

### References

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0 — OpenID Provider Metadata](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
