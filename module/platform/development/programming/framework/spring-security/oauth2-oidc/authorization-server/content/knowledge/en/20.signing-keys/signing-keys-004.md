# JWK Set Endpoint and Publishable Public Key Fields

In OAuth 2.0 and OpenID Connect (OIDC), the Authorization Server typically signs JWT access tokens or ID Tokens with a private key. Resource Servers and Relying Parties need to fetch the corresponding public key to verify the signature. A **JSON Web Key (JWK)** describes a cryptographic key in JSON; a **JSON Web Key Set (JWKS)** is a collection of JWKs; the **JWK Set Endpoint** is the endpoint published by the Authorization Server for token recipients to download the set of public keys.

The critical deployment concern is not merely generating an RSA/EC key pair. The system must publish **only the proper public fields**, keep the private key strictly confidential, attach a **stable kid** to each key, publish both new and old keys during rotation, and ensure Resource Servers can verify tokens while keys are changing.

This lesson belongs to the **JWK and Key Management** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The content guides designing, configuring, securing, testing, and operating **Spring Security, Spring Authorization Server, and Spring Boot**, focusing on the JWK Set Endpoint and the JWK fields permitted for publication.

> **Safety rule:** The public JWKS must contain **only public keys and necessary public metadata**. Never include RSA/EC/OKP private parameters or symmetric secrets in this endpoint. The private key used for signing must be protected inside a keystore, HSM, KMS, or equivalent secret store.

## 1. Why Does an Authorization Server Need a JWK Set Endpoint?

Suppose the Authorization Server at https://identity.example.com issues JWTs with an RS256 signature. When orders-api receives an access token, the API needs to know which public key verifies the signature. Instead of manually distributing public keys to every Resource Server, the AS publishes a JWKS URL:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: identity.example.com
Accept: application/json
~~~

Illustrative response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "rsa-signing-2026-01",
      "n": "BASE64URL_ENCODED_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

The Resource Server fetches the JWKS, selects a key by the JWT header's kid, and then verifies the signature with the public key. The JWKS is **not a token store**, does not contain authorization codes, and does not contain private keys. The endpoint is usually publicly accessible so APIs and RPs can retrieve keys without user login.

### 1.1. Related Components

| Component | Meaning | Role |
|---|---|---|
| **JWK** | JSON describing a cryptographic key | Represents public/private key and key-type metadata |
| **JWK Set (JWKS)** | JSON object with a keys array | Publishes one or more JWKs |
| **JWK Set Endpoint** | HTTP endpoint returning JWKS | Lets Resource Servers/RPs retrieve public keys |
| **JWK Source** | Key source used by the AS | Supplies keys to token encoder and endpoint depending on config |
| **kid** | Key ID | Helps pick the right key in JWKS when verifying tokens |
| **jwks_uri** | JWKS URL in metadata | Enables client/resource server discovery of the key endpoint |
| **Private key** | Secret half of a key pair | Used to sign tokens, never published |
| **Public key** | Public half of a key pair | Used to verify signatures, can be published |

### 1.2. The JWK Set Endpoint Is Not a Login Endpoint

The JWK Set Endpoint does not authenticate users, issue tokens, or require consent. It publishes public keys so parties that already trust the issuer can verify signatures. The fact that the endpoint does not require browser login **does not mean** any issuer is trustworthy: Resource Servers must configure a trusted issuer and validate signatures, expiration, audience, and claims per policy.

## 2. Structure of a JWK Set and JWK

According to RFC 7517, a JWK Set is a JSON object with a keys member whose value is an array of JWKs:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-key-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "ec-key-2026-b",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "PUBLIC_X_COORDINATE",
      "y": "PUBLIC_Y_COORDINATE"
    }
  ]
}
~~~

This is illustrative JSON with abbreviated placeholder values, **not real keys**. A JWKS can contain multiple keys simultaneously, such as the current key and an older key still needed to verify unexpired tokens.

### 2.1. kty Is a Required Field

kty (Key Type) identifies the key family. Common values:

| kty | Key type | Primary public fields |
|---|---|---|
| RSA | RSA | n, e |
| EC | Elliptic Curve | crv, x, y |
| OKP | Octet Key Pair, e.g., Ed25519 | crv, x |
| oct | Symmetric key | k is a secret, **do not publish in public JWKS** |

Not every kty fits every JWS algorithm. For example, RS256 uses RSA; ES256 uses EC P-256; EdDSA uses an appropriate OKP key. The algorithm and key type must be compatible.

### 2.2. JWKS Has No Key Priority Order

The keys array is a set of keys; consumers should not infer the current key merely because an element appears first. Resource Servers must select keys based on kid, key type, algorithm, and configured policy. If a JWT omits kid while the JWKS contains multiple matching keys, key selection may become ambiguous or rejected; token issuance designs should attach kid consistently.

### 2.3. A JWKS Can Serve Multiple Key Purposes

An AS may use multiple key pairs for different purposes:

- Keys for signing JWT access tokens;
- Keys for signing OIDC ID Tokens;
- Keys for encrypting Request Objects or tokens if supported by deployment;
- Keys belonging to different algorithms or environments.

Do not expose every key from internal stores in the public JWKS. Publish only the public keys actually needed by consumers to verify tokens, accompanied by metadata distinguishing their purpose.

## 3. Publishable Public JWK Fields

RFC 7517 defines common JWK fields. That a field is permitted by the standard **does not mean** every application should include it on every key. The AS should publish only necessary, accurate metadata without leaking secrets.

| Field | Meaning | Publishable? | Notes |
|---|---|---|---|
| kty | Key type | **Yes, required** | E.g., RSA, EC, OKP |
| kid | Key ID | **Yes** | Recommended for key selection during rotation |
| use | Key intended use | **Yes** | sig for signing/verification; enc for encryption |
| key_ops | Permitted operations | **Yes** | For public signing keys, typically verify |
| alg | Intended algorithm | **Yes** | E.g., RS256, PS256, ES256 |
| x5u | URL to X.509 certificate/chain | Conditional | Use only trusted URLs; carries unintended fetch risk |
| x5c | Base64 DER X.509 certificate chain | Conditional | Certificate holds public key; must not contain private key |
| x5t | Certificate SHA-1 thumbprint | Conditional | Used to identify certificate, not a secret |
| x5t#S256 | Certificate SHA-256 thumbprint | Conditional | Exact member name format per RFC |
| n, e | RSA modulus and public exponent | **Yes** | RSA public components |
| crv, x, y | EC curve and public coordinates | **Yes** | x, y are public coordinates |
| crv, x | OKP curve and public key bytes | **Yes** | E.g., Ed25519 |
| d, p, q, dp, dq, qi, oth | RSA private components | **No** | Never include in public JWKS |
| d | EC/OKP private scalar | **No** | Never publish |
| k | Symmetric key material for oct | **No** | Actual secret |

### 3.1. use — Key Purpose

use typically takes two values:

- sig: key used for digital signatures and signature verification;
- enc: key used for encryption/decryption.

For public keys used to verify signed JWTs, use is typically set to sig. Never set use to enc for a key used solely to sign tokens. If a key is used for multiple purposes, consider separating key pairs to reduce confusion and cross-protocol risks.

### 3.2. key_ops — Permitted Operations

key_ops is an array of cryptographic operations, for example:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-verify-01",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "RS256",
  "n": "PUBLIC_MODULUS",
  "e": "AQAB"
}
~~~

The public key only needs the verify operation in this example. The private key on the AS side can perform sign, but **never publish a JWK containing key_ops sign alongside private material**.

RFC 7517 recommends not using use and key_ops together. If an implementation publishes both, they must be consistent. For instance, use sig must align with key_ops verify on a public verification key.

### 3.3. alg — Intended Algorithm

alg describes the JWA algorithm the key is intended for, for example:

| Algorithm | Key type | Purpose |
|---|---|---|
| RS256 | RSA | RSASSA-PKCS1-v1_5 with SHA-256 |
| PS256 | RSA | RSASSA-PSS with SHA-256 |
| ES256 | EC P-256 | ECDSA with SHA-256 |
| EdDSA | Appropriate OKP | Edwards-curve signature per JWA |

The Resource Server must configure an **algorithm allowlist** and verify compatibility with the issuer/key. Never blindly trust alg in a JWT header, never accept none, and never allow an attacker to trick a verifier into switching from an asymmetric algorithm to HMAC/shared secret.

### 3.4. kid — Key Identifier

kid is a key identifier string, typically present in the JWT protected header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "JWT"
}
~~~

The verifier reads kid, looks up the JWK with the matching kid in the fetched JWKS, and verifies the signature. kid:

- Should be unique within the JWK Set at any given time;
- Must stay stable throughout the key pair's lifecycle;
- Should not be reused for a different key pair after rotation;
- Is not a password, not a private key, and not necessarily a cryptographic fingerprint.

Do not change kid arbitrarily for the same key pair across restarts, as caches and already-issued tokens would no longer find the matching key.

## 4. Public Fields and Private Fields by Key Type

### 4.1. RSA

An RSA public key JWK uses the fields:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-signing-2026-01",
  "use": "sig",
  "alg": "RS256",
  "n": "BASE64URL_MODULUS",
  "e": "AQAB"
}
~~~

- n: RSA modulus;
- e: public exponent;
- d: private exponent;
- p, q: two prime factors;
- dp, dq, qi: CRT private parameters;
- oth: additional private info in multi-prime RSA.

**Only n and e are basic RSA public components.** The fields d, p, q, dp, dq, qi, and oth must not appear in the public JWKS. An internal private RSA JWK typically holds all of these fields so the AS can sign tokens, while the public endpoint must return the public projection.

### 4.2. Elliptic Curve (EC)

EC P-256 example:

~~~json
{
  "kty": "EC",
  "kid": "ec-signing-2026-01",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "BASE64URL_PUBLIC_X",
  "y": "BASE64URL_PUBLIC_Y"
}
~~~

crv, x, and y are public information. d is the private scalar and **must not be published**. Coordinates must be encoded according to JWK rules; do not take an arbitrary hex string and put it directly into JSON.

### 4.3. Octet Key Pair (OKP)

For Ed25519, the public JWK looks like:

~~~json
{
  "kty": "OKP",
  "kid": "ed25519-signing-2026-01",
  "use": "sig",
  "alg": "EdDSA",
  "crv": "Ed25519",
  "x": "BASE64URL_PUBLIC_KEY"
}
~~~

x is the public key bytes; d is the private key bytes and must not appear in the public JWKS. Ensure libraries, JWA profiles, and Resource Servers support the corresponding algorithm.

### 4.4. Symmetric Key (oct)

Example JWK structure for a symmetric key:

~~~json
{
  "kty": "oct",
  "kid": "hmac-key-01",
  "alg": "HS256",
  "k": "BASE64URL_SECRET_KEY_MATERIAL"
}
~~~

The field k **is the secret itself**. Never publish an oct JWK containing k at a public JWK Set Endpoint. For architectures with an Authorization Server and multiple independent Resource Servers, asymmetric signing is generally preferable: the AS holds the private key to sign, and RSs receive only the public key to verify. With HMAC, every party holding the secret to verify can also sign tokens, widening the trust boundary.

## 5. X.509 Certificates and Thumbprints

A JWK can include certificate-related metadata:

| Field | Description | Notes |
|---|---|---|
| x5u | URL to X.509 certificate/chain | Consumers may fetch the URL; publish only organization-controlled endpoints |
| x5c | Array of Base64 DER certificates | Certificate holds public key and certificate info |
| x5t | SHA-1 thumbprint of certificate | Not a secret; legacy compatibility |
| x5t#S256 | SHA-256 thumbprint of certificate | Stronger thumbprint property than SHA-1 |

### 5.1. x5c Is Not a Private Key

A public X.509 certificate can be distributed via JWKS. It contains the public key and metadata such as subject, issuer, validity, serial, extensions, and CA signature. **The corresponding private key is not in the certificate.** Still, publishing certificates reveals infrastructure metadata, so publish only the necessary chain.

### 5.2. Be Careful with x5u

If a JWK publishes x5u, consumers may fetch the certificate from that URL depending on implementation. The URL must belong to a trusted domain, use HTTPS, avoid uncontrolled content changes, and never point arbitrarily to internal addresses. Resource Servers must not let token headers specify arbitrary jku/x5u URLs to decide where to load keys; obtain the JWKS URI from a configured trusted issuer/discovery.

### 5.3. Thumbprints Do Not Replace kid

kid is a key identifier assigned by the issuer for key selection; x5t/x5t#S256 are certificate thumbprints. They can serve different purposes. Do not compute a thumbprint and assume it always equals kid; the two match only when a deployment explicitly defines that convention.

## 6. What Must Never Be Published

The public JWKS must never contain:

- RSA private exponent d;
- RSA factors p, q and CRT values dp, dq, qi, oth;
- EC/OKP private scalar/bytes d;
- Symmetric key material k;
- Private key PEM/PKCS#8 or keystore passwords;
- KMS/HSM secrets or key vault access credentials;
- Unnecessary internal metadata that could leak file paths, accounts, topology, or sensitive operational details.

A severe mistake is calling toJSONString() on a private JWK/JWKSet and returning it directly from an HTTP endpoint. **Private JWKs may be used internally to sign tokens; the public JWKS must be a public-only representation.**

### 6.1. Public Projection

With Nimbus JOSE/JWT, JWK provides APIs to create a public projection such as toPublicJWK(), and JWK Set provides corresponding methods to produce a public set. Use the library's proper API rather than stripping a few JSON fields via string manipulation:

~~~java
// Illustrative example with Nimbus JOSE + JWT.
JWK privateSigningKey = loadPrivateSigningKey();

JWK publicSigningKey = privateSigningKey.toPublicJWK();

JWKSet publicJwkSet = new JWKSet(publicSigningKey);
String jsonForPublication = publicJwkSet.toString();
~~~

loadPrivateSigningKey() represents loading the key from a keystore/KMS; it is not a built-in API. This snippet demonstrates public projection and does not replace Spring Authorization Server's official endpoint. With multiple keys, build the JWK Set from a list of public projections.

### 6.2. Automated Checks Before Publishing

A validation job can verify:

1. Every published JWK has a valid kty and unique kid;
2. No private fields exist for each key type;
3. No oct JWK containing k is present;
4. use, key_ops, and alg are consistent;
5. RSA modulus/curve/coordinates have appropriate sizes and formats;
6. Keys are authorized for publication and belong to the right issuer/environment;
7. JWKS contains no test keys or keys from another tenant.

Do not check field names alone; parse the JWK with a JOSE library and verify the public projection derived from the key material.

## 7. JWK Set Endpoint in Spring Authorization Server

Spring Authorization Server uses **JWKSource<SecurityContext>** as its JWK source. When configured with an appropriate key source, the token generator can use the key material to sign JWTs; the JWK Set Endpoint serves public keys to consumers. The default path is typically **/oauth2/jwks**, configurable via AuthorizationServerSettings in supporting versions.

### 7.1. Generating an RSA Key Pair for Demo Environments

The example below generates an in-memory RSA key for illustration:

~~~java
private static KeyPair generateRsaKey() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    return generator.generateKeyPair();
}
~~~

RSA 2048 is a common, widely supported baseline; organizational policy may require larger sizes or different algorithms. **Do not regenerate a new key every time a production application starts**, because on restart the AS loses the old private key while old tokens are still unexpired.

### 7.2. Declaring JWKSource

Example Nimbus JWKSource using an RSA public/private key:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws GeneralSecurityException {
    KeyPair keyPair = generateRsaKey(); // Demo only; production loads managed key.

    RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
    RSAPrivateKey privateKey = (RSAPrivateKey) keyPair.getPrivate();

    RSAKey rsaJwk = new RSAKey.Builder(publicKey)
        .privateKey(privateKey)
        .keyUse(KeyUse.SIGNATURE)
        .algorithm(JWSAlgorithm.RS256)
        .keyID("rsa-signing-demo-01")
        .build();

    JWKSet privateJwkSet = new JWKSet(rsaJwk);

    return (selector, context) -> selector.select(privateJwkSet);
}
~~~

In the example, privateJwkSet is kept **inside the AS** so the signer can use the private key. When publishing JWKS, the endpoint must return the **public projection**, never this private JWK directly. Spring Authorization Server/Nimbus's official endpoint handles publishing logic per your version's integration; if writing a custom endpoint, explicitly convert to a public JWK Set and test that no private fields leak.

keyID("rsa-signing-demo-01") is a fixed value for illustration only. Production must obtain kid from a key-management system or stable metadata, never generating a different ID across restarts for the same key.

### 7.3. Configuring the JWK Set Endpoint Path

You can declare AuthorizationServerSettings:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .jwkSetEndpoint("/oauth2/jwks")
        .build();
}
~~~

This configuration snippet illustrates issuer and path; other endpoints use the version's defaults unless overridden. The final public path also depends on reverse proxies/context paths. **The issuer must match exactly** with the iss claim in tokens and the metadata used by Resource Servers.

### 7.4. SecurityFilterChain and Accessibility

Typical Authorization Server filter chain skeleton:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    return http.build();
}
~~~

This is a filter chain skeleton; you must also configure other beans such as RegisteredClientRepository, OAuth2AuthorizationService, issuer, JWKSource, and a login chain. The JWKS endpoint must **be fetchable by Resource Servers/consumers without user login** by design of public key distribution. Verify matchers/filter ordering in your exact version so you do not accidentally guard the JWK Set Endpoint with form login or HTML redirects.

Do not expose key management, key upload, or key rotation endpoints publicly just because JWKS is a public endpoint. **Only GET public JWKS is exposed publicly**; private key administrative operations require dedicated authentication, authorization, and protection.

## 8. Discovery and jwks_uri

A Resource Server should not hardcode a URL supplied by an untrusted token. It must know a **trusted issuer** and obtain the keys endpoint from that issuer's metadata.

### 8.1. OAuth 2.0 Authorization Server Metadata

RFC 8414 defines metadata that can contain jwks_uri:

~~~json
{
  "issuer": "https://identity.example.com",
  "authorization_endpoint": "https://identity.example.com/oauth2/authorize",
  "token_endpoint": "https://identity.example.com/oauth2/token",
  "jwks_uri": "https://identity.example.com/oauth2/jwks"
}
~~~

### 8.2. OpenID Connect Discovery

If the AS enables OIDC Provider Configuration, the OpenID Provider metadata document at the corresponding discovery path also publishes jwks_uri. jwks_uri is the URL for consumers to fetch the JWK Set; **it is not a key itself**, nor is it a URL dictated by a JWT header.

### 8.3. Configuring Spring Resource Server

A Resource Server can configure the issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
~~~

Spring Security uses the issuer's metadata to locate the JWKS URI and validate the issuer in JWTs per configuration. If you want to specify the JWKS URI explicitly, configure jwk-set-uri accordingly; you must still maintain iss validation to avoid verifying signatures from a URL without binding the issuer.

Example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
          jwk-set-uri: https://identity.example.com/oauth2/jwks
~~~

Setting jwk-set-uri alone should not cause the application to skip issuer validation. Check the behavior of your Spring Security/Boot version and configure validators if building a custom JwtDecoder.

## 9. Which Public Key Does the Resource Server Choose?

A JWS JWT has a protected header, for example:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "JWT"
}
~~~

During verification:

1. The Resource Server already knows the trusted issuer/JWKS URI.
2. It fetches or uses a cached JWKS.
3. Reads kid from the protected header.
4. Selects the public JWK matching kid, kty, alg, and verifier policy.
5. Verifies the signature.
6. Continues checking issuer, timestamps, audience, and claims/permissions.

**A valid signature only proves the token was signed with the corresponding private key**; it does not by itself prove the token is intended for the current API or carries the required scopes.

### 9.1. kid Not Found in Cache

When a new JWT carries a kid not yet in the JWKS cache:

- The consumer may refresh the JWKS per library mechanics;
- If the new key is still absent from the response, the token must be rejected;
- Never fall back to another arbitrary key just to "keep requests working";
- Monitor unknown-kid events to detect broken rotations or forged tokens.

Avoid unbounded JWKS refreshes on every request carrying an unknown kid, as attackers can trigger a **JWKS refresh storm**. Use caching, refresh throttling, and sensible timeouts.

### 9.2. Duplicate kid

Two different keys sharing the same kid can cause verifiers to pick the wrong key or behave inconsistently. Every JWK Set must ensure kid uniqueness within the set; never reuse an ID for a new key pair while the old key is still published.

### 9.3. Token Without kid

A JWK Set containing only one matching key may allow some verifiers to pick the key by algorithm, but you should not rely on this behavior in a rotating system. With multiple keys, a token without kid may fail key resolution and be rejected. **The AS should emit kid consistently** in JWT headers.

## 10. Rotation: Publishing Old and New Keys

Signing keys must not live forever. During rotation, the AS must replace the private signing key and update the public JWKS without causing Resource Servers to reject valid previously issued tokens.

### 10.1. Why Not Delete the Old Key Immediately?

Suppose:

- Key K1 signed tokens until 10:00;
- The AS switches to signing new tokens with K2 at 10:00;
- Old tokens signed with K1 remain valid until 10:10.

If the JWKS drops K1 immediately at 10:00, a Resource Server fetching fresh JWKS cannot verify old tokens even though they are within exp. Therefore, **keep public K1 in the JWKS for an overlap window** long enough for old tokens to expire and consumer caches to update.

### 10.2. Recommended Rotation Workflow

~~~mermaid
flowchart TD
    A[Signing with K1; JWKS has K1] --> B[Generate K2 in KMS/HSM or keystore]
    B --> C[Publish public K2 to JWKS, keep K1]
    C --> D[Wait for consumers to fetch K2; verify key visibility]
    D --> E[Switch signer to private K2; new JWTs carry kid K2]
    E --> F[Retain public K1 during overlap window]
    F --> G[K1 tokens expire + cache grace completes]
    G --> H[Remove public K1 from JWKS]
    H --> I[Destroy/archive private K1 per key lifecycle]
~~~

The sequence above is **normal rotation**. If K1 is compromised, you cannot wait out a normal overlap schedule: stop signing with K1, remove/deny the key per incident response, and accept that in-flight tokens signed with K1 must be handled based on risk level. Emergency plans differ from scheduled rotation plans.

### 10.3. Calculating the Overlap Window

The overlap window must account for:

- Maximum lifetime of tokens signed with K1;
- Clock skew tolerated at Resource Servers;
- Cache TTL/refresh behavior of JWKS consumers;
- Replication/deployment lag;
- In-flight request durations or downstream systems holding tokens;
- Operational SLAs when consumers cannot reach JWKS.

Do not set the overlap equal only to the access token TTL if JWKS caching or clock skew can cause consumers to still need K1 longer.

### 10.4. Do Not Rotate kid Without Rotating the Key

If the key pair stays the same while kid changes, old tokens still carry the old kid. Once JWKS publishes only the new ID, verifiers cannot locate the old key from token headers. When the key pair changes, assign a new kid; when the key pair does not change, keep kid stable.

## 11. Protecting Private Keys and Key Sources in Production

Generating an RSA key inside a bean is suitable only for learning/testing. Production requires lifecycle management for private keys:

| Key source | When suitable | Controls |
|---|---|---|
| Java KeyStore (PKCS12/JKS) | App infrastructure manages keystores | Protect password, file permissions, backups, rotation |
| HSM | Signing keys require hardware protection | Access policy, auditing, HA, and backup/restore procedures |
| Cloud KMS | Cloud infrastructure with key management | Least-privilege IAM, key versions, signing permissions, auditing |
| Secret manager + encrypted key | Smaller systems with managed secret vault | Encryption, access control, rotation, avoid env/log leaks |
| Ephemeral in-memory key | Short-lived unit tests/dev | Never use for production or tokens surviving restarts |

### 11.1. Separating Signing Permissions from Public Key Reads

- Only the Authorization Server or signing service gets sign permission.
- Resource Servers need only public keys to verify.
- Do not distribute private keys to all microservices "for convenience."
- The JWKS endpoint is not a private-key retrieval endpoint.
- If the KMS supports a sign operation, the AS can sign without the private key leaving the KMS; the public key is still published via JWKS.

### 11.2. Environment Separation

Avoid sharing the same key pair across development, staging, and production. Every issuer/environment should have its own key set; if a staging private key leaks, it must not allow forging production tokens. Issuer metadata and JWKS URIs must clearly distinguish environments.

### 11.3. JWKS Read Access vs. Key Administration Access

The public JWKS can be read broadly, but the following operations require strict authorization:

- Uploading or registering key pairs;
- Selecting the active signing key;
- Revoking keys;
- Modifying kid, alg, use, or key purpose;
- Changing KMS key policies or service identities;
- Exporting private keys/backups.

Never use a public JWKS endpoint as an administrative interface. Separate administrative APIs and require strong authentication/auditing.

## 12. Algorithms, Key Types, and Verification Policies

| Token signing algorithm | JWK key type | Common public members | Notes |
|---|---|---|---|
| RS256 / PS256 | RSA | n, e | Check sufficient modulus strength, proper allowlist |
| ES256 | EC | crv=P-256, x, y | Curve and algorithm must match |
| EdDSA | OKP | crv, x | Use only when libraries and verifiers support it |
| HS256 | oct | k | k is secret, do not publish in public JWKS |

### 12.1. Never Use an alg Chosen by the Token

Verifiers must enforce an algorithm policy for the issuer, such as allowing only RS256. Reject:

- alg=none;
- HMAC when the issuer is designed for RSA/EC and the verifier treats the public key as an HMAC secret;
- Weak algorithms or algorithms no longer approved by policy;
- JWKs from a different issuer or a URL specified by the token header itself.

### 12.2. use, key_ops, and alg Must Be Consistent

Example public signing JWK:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-verify-01",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "RS256",
  "n": "PUBLIC_MODULUS",
  "e": "AQAB"
}
~~~

Do not put key_ops sign in a public JWK to suggest consumers sign with the public key. Even if alg is omitted from the published JWK, the verifier must still maintain an allowlist and determine the algorithm from trusted configuration.

### 12.3. One Key for Multiple Algorithms?

Do not assume a single key pair should be used across multiple algorithms or purposes. If the same key has multiple algs or purposes, inspect profiles, JWA constraints, and consumer selection logic. Separating keys by purpose/algorithm is usually easier to audit, rotate, and revoke.

## 13. JWKS Caching and Availability

Resource Servers typically cache the JWKS to avoid fetching the endpoint on every API request. This improves latency and reduces load, but directly affects key rotation.

### 13.1. Caching Too Long

If JWKS is cached too long, consumers may not see K2 when the AS begins signing new tokens with K2. New JWTs carrying kid=K2 will be rejected. During rotation, you must:

1. Publish public K2 first;
2. Wait for consumers to refresh/cache K2;
3. Only then sign new tokens with K2.

### 13.2. Caching Too Short

Caching too briefly causes heavy traffic to the JWKS endpoint, increases network dependency, and creates load spikes when many services refresh simultaneously. Use sensible TTLs, HTTP cache headers (such as Cache-Control, ETag/conditional requests if supported), timeouts, and bounded retries.

**Do not assume Spring Authorization Server always returns a specific cache TTL** across all versions/configurations. Inspect actual HTTP responses and reverse proxy/CDN configurations if present.

### 13.3. Unknown kid and Refresh Storms

If every request with an unknown kid triggers a JWKS fetch, attackers can flood the system with forged JWTs containing random kids to overload the AS. Consumers should implement refresh throttling/single-flight coalescing, timeouts, retry limits, and reject tokens if the key is still missing after a reasonable refresh.

### 13.4. JWKS Endpoint Unavailability

During a temporary JWKS endpoint outage:

- Consumers with cached public keys can continue verifying tokens per cache policy;
- Newly started consumers or requests hitting an uncached kid may fail verification;
- Never fall back to an arbitrary issuer/key;
- Maintain HA, backups, monitoring, and endpoint recovery plans.

Do not rely on stale caches indefinitely if a key may have been compromised; freshness policies must balance availability with key revocation capability.

## 14. JWK Set Endpoint and OIDC/OAuth Metadata

A system should publish consistent metadata:

| Metadata | Meaning |
|---|---|
| issuer | Issuer identifier, must match iss claim |
| jwks_uri | JWK Set Endpoint URL |
| authorization_endpoint | Authorization endpoint |
| token_endpoint | Token issuance endpoint |
| revocation_endpoint | Token revocation endpoint if supported |
| introspection_endpoint | Introspection endpoint if supported |
| pushed_authorization_request_endpoint | PAR endpoint if supported |

Discovery helps clients/Resource Servers locate endpoints without arbitrary hardcoding. However, **discovery metadata must come from a trusted issuer**; never read jwks_uri from an untrusted token or caller query parameter.

### 14.1. Issuer URL Must Be Stable

If the AS changes issuer or a reverse proxy produces different URLs between metadata and the JWT iss claim, Resource Servers may reject tokens. Configure the exact public issuer, handle forwarded headers from trusted proxies properly, and test metadata/JWKS from outside the cluster.

### 14.2. Never Use jku in Token Headers as a Trust Anchor

JWTs can carry headers such as jku or x5u; never allow a token to point a verifier to an arbitrary URL to fetch keys. Resource Servers must use the JWKS URI from configured/trusted issuer discovery, or an explicitly provisioned trust mechanism.

## 15. Testing the JWK Set Endpoint

Testing must prove that **the endpoint returns a public-only JWKS**, tokens are signed with the corresponding private key, and Resource Servers verify tokens via kid. A single HTTP 200 check is not enough.

### 15.1. Test Matrix

| Scenario | What to verify |
|---|---|
| GET JWK Set Endpoint | Returns JSON object with keys array |
| Without login cookie | Public JWKS remains accessible by design |
| RSA signing key | Publishes only kty, kid, n, e, and needed metadata |
| EC signing key | Publishes only crv, x, y, and metadata |
| OKP signing key | Publishes only crv, x, and metadata |
| Private RSA field present | Test must **fail** |
| EC/OKP private d present | Test must **fail** |
| Symmetric JWK oct/k present | Test must **fail** |
| Duplicate kid | Configuration rejected or flagged before publish |
| Conflicting use/key_ops | Validation detects mismatch |
| Disallowed alg | Resource Server rejects token |
| JWT with valid kid | Verifier picks matching public key and verifies |
| JWT with unknown kid | Controlled JWKS refresh, then rejected if absent |
| Rotation K1 → K2 | Consumer verifies both old and new tokens during overlap |
| Removing K1 too early | Test detects verification failures for old tokens |
| JWKS endpoint outage | Consumer follows cache/fail policy properly |
| Metadata jwks_uri issuer mismatch | Integration test detects mismatch |
| Wrong JWT aud | RS rejects despite valid signature |

### 15.2. MockMvc Test for Endpoint Returning JWKS

Test skeleton example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwkSetEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void jwksEndpointReturnsPublicKeySet() throws Exception {
        mvc.perform(get("/oauth2/jwks")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.keys").isArray())
            .andExpect(jsonPath("$.keys[0].kty").value("RSA"))
            .andExpect(jsonPath("$.keys[0].kid").isNotEmpty())
            .andExpect(jsonPath("$.keys[0].n").isNotEmpty())
            .andExpect(jsonPath("$.keys[0].e").isNotEmpty())
            .andExpect(jsonPath("$.keys[0].d").doesNotExist())
            .andExpect(jsonPath("$.keys[0].p").doesNotExist())
            .andExpect(jsonPath("$.keys[0].q").doesNotExist());
    }
}
~~~

This is a **test skeleton** requiring imports, a JWKSource bean, a signing key fixture, and SecurityFilterChain configuration. The test assumes the first key is RSA; if JWKS has multiple keys or unordered elements, match by kid rather than fixing index [0]. Add checks for EC/OKP/symmetric keys if supported by your application.

### 15.3. Testing Public Projection at the JWK Level

An additional unit test can parse the response into a Nimbus JWKSet and verify:

~~~java
JWKSet publicSet = JWKSet.parse(jwksJson);

for (JWK jwk : publicSet.getKeys()) {
    assertThat(jwk.isPrivate()).isFalse();
    assertThat(jwk.getKeyID()).isNotBlank();
    assertThat(jwk.getKeyType()).isNotNull();
}
~~~

This illustrates Nimbus JOSE/JWT usage; check the API of your project's library version. isPrivate() is a useful check, though it does not replace key-type-specific schema/field validation. For oct, ensure no key material k is published.

### 15.4. End-to-End Signing and Verification Testing

1. Issue a JWT access token from the AS using private key K1.
2. Read the JWT header, verify kid=K1.
3. Fetch JWKS from the public endpoint and locate the JWK with K1.
4. Use that public key to verify the signature.
5. Also verify iss, exp, aud, scope, and token profile.
6. Rotate to K2 and repeat with new tokens; K1 tokens still verify during overlap.
7. After removing K1, test that expired K1 tokens are no longer accepted; verify behavior per cache policy.

Do not rely solely on tests calling a mocked JwtDecoder; include an integration test exercising a real public JWKS endpoint or equivalent environment.

## 16. Observability and Operations

| Metric/event | Purpose | Notes |
|---|---|---|
| JWKS request count/latency | Understand usage and endpoint performance | Distinguish normal consumers from refresh storms |
| Unknown kid | Detect broken rotation or forged tokens | Do not log full tokens |
| Signature verification failures | Detect wrong key/issuer/alg tokens | Classify clock/issuer/rotation causes |
| Active signing key ID | Know which key the AS is currently signing with | Log kid only, never private material |
| Rotation started/completed | Track overlap and old key removal | Record who approved in audit logs |
| JWKS publish version | Compare across nodes/caches | Never use private key fingerprints in public metrics |
| KMS/HSM signing failures | Monitor token issuance health | Alert on latency/errors and fallback policy |
| Key expiry/certificate expiry | Prevent unexpected cert expiration | Alert ahead of time per runbook |

### 16.1. Auditing Key Lifecycle

Actions to create, import, activate, deactivate, rotate, revoke, or destroy keys must be audited: administrative actor, key ID, algorithm, purpose, timestamp, approval/change ticket, and outcome. **Never record private keys, keystore passwords, HSM credentials, or raw secrets** in audit logs.

### 16.2. When Private Key Exposure Is Detected

Incident response must:

1. Stop using the compromised key to sign new tokens;
2. Create/activate a new key and update JWKS per emergency procedure;
3. Assess tokens already issued under the compromised kid;
4. Revoke/deny tokens or reduce TTLs per SLA and RS capabilities;
5. Notify/update consumer caches and handle unknown kids;
6. Investigate leak source, KMS/HSM access permissions, backups, and pipelines;
7. Preserve audit records and evidence per policy.

During an incident, **do not keep the old public key just to avoid compatibility errors if the private key is compromised and attackers can forge tokens**. Emergency removal must be paired with mechanisms to reject tokens signed by that key; if you only delete from JWKS while RSs still cache the key, some consumers may continue trusting forged tokens until caches expire.

## 17. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Returning raw private JWKSet from endpoint | Private key leak, attacker forges tokens | Publish public projection only |
| Publishing d, p, q, dp, dq, qi, oth | RSA private material leak | Validate fields per key type |
| Publishing EC/OKP d | Private scalar/bytes leak | Strip private fields |
| Publishing oct.k | Secret leaked to every consumer | Never publish symmetric keys in public JWKS |
| Sharing one key pair across all environments | Compromise spreads to production | Separate keys/issuers per environment |
| Generating new keys on every restart | Old tokens fail verification | Store keys durably in KMS/HSM/keystore |
| Changing kid randomly | Consumers cannot find key for old tokens | Keep kid stable per key pair |
| Deleting old key immediately on rotation | Old JWTs fail signature check | Overlap per token TTL and caches |
| Not publishing K2 before signing with K2 | RS does not yet know new public key | Publish → warm caches → switch signer |
| Trusting token-specified jku/x5u | SSRF/key substitution | Derive JWKS URI from trusted issuer anchor |
| Checking signature only, skipping audience | API A token works at API B | Validate aud and scope |
| Using oct in public JWKS | Secret leaked in distributed setup | Use asymmetric signing for distributed consumers |
| No alg allowlist | Algorithm confusion/downgrade | Allowlist per issuer/resource |
| JWKS endpoint requires user login | Resource Server cannot fetch keys | Allow public JWKS GET by design |
| Unbounded fetch on unknown kid | JWKS refresh DoS | Cache, throttle, timeout |
| Testing only HTTP 200 | Misses private fields or rotation bugs | Test schema, token verification, and rotation |

## 18. Pre-Production Checklist for JWK Set Endpoint

1. **Key source:** are private keys stored in a KMS/HSM/keystore with access control, backups, and rotation?
2. **Public-only:** does JWKS exclude d, RSA CRT fields, EC/OKP d, and symmetric k?
3. **Key metadata:** are kty, kid, use, key_ops, and alg compatible with unique kid values?
4. **Key purpose:** are signing keys separated from encryption keys without misuse?
5. **Endpoint:** does public JWKS GET work without login while keeping key admin APIs locked down?
6. **Discovery:** is jwks_uri obtained from a trusted issuer and matched to the real endpoint?
7. **Issuer:** does issuer metadata match the iss claim and public URL behind proxies accurately?
8. **Verifier:** do RSs verify signature, issuer, algorithm allowlist, expiry, audience, and scope?
9. **Rotation:** are new keys published before signing, old keys retained for overlap, and kids never reused?
10. **Cache:** are TTL/refresh throttling, unknown kid handling, outages, and stale keys addressed?
11. **Multi-node:** do all AS nodes share consistent key sets and the same active signing key?
12. **Incident response:** can you halt signing with a compromised key, remove it, and handle issued tokens?
13. **Testing:** are public-only endpoint responses, end-to-end verification, and rotation covered by tests?
14. **Audit:** are key changes logged while private material stays out of all logs?

## 19. Applied Exercises

**Scenario A — Public JWKS exposes a private key.** A response contains kty=RSA, n, e, d, p, q. Explain the severity, incident response actions, and why merely removing the fields from the endpoint is insufficient if the private key may have been downloaded.

**Scenario B — Rotating K1 to K2.** Access tokens signed with K1 have a 10-minute TTL, and JWKS cache is up to 30 minutes. When should you publish K2, switch the signer, and remove K1? List additional factors such as clock skew/replication.

**Scenario C — Unknown kid.** An API receives thousands of forged tokens with random kids. How do you perform bounded JWKS refreshes while still recognizing legitimate new keys?

**Scenario D — Two Resource Servers.** orders-api and billing-api trust the same issuer. Why is a valid signature insufficient for billing-api to accept a token issued for orders-api?

**Hints:** A is private key compromise: stop signing, emergency rotate, address tokens under the old kid and caches. B must publish K2 first, wait for consumers to pick up the key, switch the signer, and retain K1 at least for token lifetime plus cache/clock/replication margins. C uses caching, single-flight/throttling, timeouts, and rejection if the key still does not exist. D requires validating audience, scope, and API permissions.

## 20. Summary

The **JWK Set Endpoint** publishes a set of **public JWKs** so Resource Servers and OIDC Relying Parties can verify signatures of tokens issued by the Authorization Server. A JWK Set is a JSON object containing a keys array; each JWK requires kty and may include kid, use, key_ops, alg, certificate metadata, and key-type-specific public parameters.

For **RSA**, the primary public parameters are n and e; for **EC**, crv, x, y; for **OKP**, crv, x. Private fields such as RSA d/p/q/dp/dq/qi/oth, EC/OKP d, and symmetric oct.k must never appear in the public JWKS.

In **Spring Authorization Server**, JWKSource<SecurityContext> supplies keys for token generation and the JWK Set Endpoint in supporting versions/configurations. Production must store private keys securely, keep kid stable, publish jwks_uri through trusted metadata, and rotate keys via **publish new key → switch signer → retain old key through overlap → remove old key safely**.

Resource Servers must verify signatures alongside issuer, expiration, audience, algorithm, and scope. The JWK Set Endpoint is the public piece of trust distribution, yet **the trust anchor remains the configured trusted issuer**, not any URL or key self-declared by a token.

## 21. References

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWK Set, kty, use, key_ops, alg, kid, X.509 fields, and public/private parameters.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): RSA, EC, HMAC, and JWS/JWE algorithms.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, kid, algorithms, and signature verification.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): jwks_uri, issuer, and discovery metadata.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider metadata and jwks_uri.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile and validation.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): JWKSource, token generation, AuthorizationServerSettings, and JWK Set Endpoint.
- [Spring Security Resource Server — JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWK Set URI, JwtDecoder, and validation.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JWK/JWKSet, public projections, and JOSE implementation.
