# JWK, JWK Set, JWKSource, and Token Signing Keys

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, JWT-formatted access tokens are typically signed with the Authorization Server's private key. The Resource Server uses the corresponding public key to verify the signature before trusting claims such as issuer, audience, subject, scope, and expiration.

For components to exchange keys in a unified format, the JOSE ecosystem uses **JSON Web Key (JWK)** and **JSON Web Key Set (JWKS)**:

- **JWK** describes a cryptographic key along with the metadata needed to use the key.
- **JWK Set** is a collection of multiple JWKs, typically published at an endpoint so clients and Resource Servers can retrieve public keys.
- **JWKSource** is an abstraction that provides keys based on a selector, typically used by the JWT signing encoder and the JWK Set endpoint.
- **Signing key** is the key used to create a JWS signature; in the asymmetric model, the private key is kept at the Authorization Server while the public key is published to verifiers.

Running example: The Authorization Server issues a JWT access token for <code>orders-web</code>. The token has a header containing <code>kid</code> to identify the signing key. The Orders API fetches the JWKS from the Authorization Server, finds the public key with the matching <code>kid</code>, verifies the signature, and then checks issuer, audience, expiry, and scope. When the Authorization Server rotates keys, the API needs to pick up the new public key while still verifying older tokens that have not expired.

After this lesson, you will be able to:

1. Distinguish between JWK, JWK Set, JWKS endpoint, and <code>JWKSource&lt;SecurityContext&gt;</code>.
2. Understand JWK fields such as <code>kty</code>, <code>use</code>, <code>alg</code>, <code>kid</code>, and public/private parameters.
3. Generate an RSA JWK for JWT signing and configure a key source for Spring Authorization Server.
4. Explain the relationship between <code>JWKSource</code>, <code>JwtEncoder</code>, <code>JwtGenerator</code>, and the JWK Set endpoint.
5. Publish public JWKs via an endpoint and discovery metadata so Resource Servers can retrieve verification keys.
6. Build a rotation workflow, retain old keys during the compatibility period, and retire keys safely.
7. Protect private keys using a secret manager, KMS, or HSM, handle compromise incidents, and test rotation.

**Version scope:** Java examples use Spring Authorization Server 1.x / Spring Security 6.x APIs on the Servlet stack. Newer Spring Security releases that integrate Authorization Server may change packages or configuration styles. Nimbus JOSE + JWT is the JOSE library commonly used by Spring Security; check your application's dependencies/versions before copying examples.

## 2. What Are JWK and JWK Set?

### 2.1. JWK: Representing a Single Key

A JWK is a JSON structure describing a key according to RFC 7517. A public RSA JWK used for signature verification might look like this:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "as-signing-2026-01",
  "n": "base64url-encoded-modulus",
  "e": "AQAB"
}
~~~

This is illustrative data; <code>n</code> and <code>e</code> are not real key values. The fields:

| Field | Meaning |
| --- | --- |
| <code>kty</code> | Key type, e.g., <code>RSA</code>, <code>EC</code>, <code>OKP</code>, or <code>oct</code>. |
| <code>use</code> | Intended use, typically <code>sig</code> for signing/verification or <code>enc</code> for encryption/decryption. |
| <code>alg</code> | Intended JOSE algorithm, e.g., <code>RS256</code> or <code>ES256</code>. |
| <code>kid</code> | Key ID, helping the recipient select the right key from a set of multiple keys. |
| <code>n</code>, <code>e</code> | RSA public parameters: modulus and public exponent. |

Not every field is required for every JWK type. Private parameters such as <code>d</code>, <code>p</code>, <code>q</code>, <code>dp</code>, <code>dq</code>, <code>qi</code> in RSA or <code>d</code> in EC/OKP must be protected. A public RSA JWK only needs the appropriate public parameters; **do not include private parameters in the public JWKS**.

### 2.2. JWK Set: A Collection of Keys

A JWK Set is a JSON object containing a <code>keys</code> array. For example, when the Authorization Server is publishing both the current key and the previous key to verify unexpired tokens:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "as-signing-2026-02",
      "n": "public-modulus-for-new-key",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "as-signing-2025-12",
      "n": "public-modulus-for-previous-key",
      "e": "AQAB"
    }
  ]
}
~~~

A JWKS can contain multiple keys because the system needs to support multiple algorithms, multiple issuer keys, or a rotation window. Element order should not be used to decide which key is current; rely on <code>kid</code>, <code>alg</code>, and verification policy instead.

### 2.3. Differences Between JWK, JWK Set, and JWKS Endpoint

| Concept | Role |
| --- | --- |
| **JWK** | A single key along with its metadata. |
| **JWK Set** | A collection of multiple JWKs in a single JSON structure. |
| **JWKS** | Common abbreviation for JSON Web Key Set; not a separate key type. |
| **JWKS endpoint** | HTTP URL published by the Authorization Server to return the public JWK Set. |
| **JWKSource** | Server-side API providing keys to the encoder/filter by selector; not an HTTP URL. |

For example, <code>https://auth.example.com/oauth2/jwks</code> can be a JWKS endpoint, whereas <code>JWKSource&lt;SecurityContext&gt;</code> is a Java bean in the Authorization Server application.

## 3. Token Signing Keys: Public Key and Private Key

### 3.1. Asymmetric Signature Model

For JWS using an asymmetric algorithm such as RS256:

~~~mermaid
flowchart LR
    A["Authorization Server"] --> B["JWT Header + Claims"]
    B --> C["Sign with RSA private key"]
    C --> D["JWT: header.payload.signature"]
    D --> E["Client / Resource Server"]
    E --> F["Fetch public key from JWKS"]
    F --> G["Verify signature + validate claims"]
~~~

The private key is used only inside the Authorization Server's trust boundary for signing. The public key can be published so Resource Servers can verify signatures. Anyone possessing the public key **cannot derive the private key** if the algorithm and key size are chosen securely.

**A signed JWT does not mean an encrypted JWT.** A compact JWS typically has three dot-separated parts; the header and payload are readable after Base64URL decoding. Do not put passwords, client secrets, private keys, or unnecessary sensitive data into a JWT just because the token is signed.

### 3.2. Signing vs. Encryption

| Purpose | Common JWK metadata | Capability |
| --- | --- | --- |
| JWS signing | <code>use=sig</code>, JWS algorithm such as <code>RS256</code> | Recipient verifies integrity and signing origin. |
| JWE encryption | <code>use=enc</code>, appropriate key management and content encryption algorithms | Protects confidentiality of the content for the recipient. |

This lesson focuses on **access token/ID Token signing keys**. Do not arbitrarily reuse a public/private signing key for key encryption; also never use <code>alg=none</code> or weak algorithms to simplify implementation.

### 3.3. Choosing Key Type and Algorithm

| Key type/algorithm | Notes |
| --- | --- |
| RSA + RS256 | Common, widely compatible; use at least a 2048-bit modulus, consider 3072-bit depending on policy. |
| EC P-256 + ES256 | Shorter signatures; requires libraries and Resource Servers to support the exact curve/algorithm. |
| Ed25519/EdDSA | Suitable for supporting systems; verify compatibility across the entire stack and deployment policy. |
| HMAC such as HS256 | Same secret shared between signer and verifier; unsuitable for a public JWKS model across multiple independent Resource Servers if you do not want to share signing capability. |

Do not choose the algorithm based on the header sent by an incoming token. The Resource Server must configure an allow-list of trusted algorithms and verify compatible key type/curve/use. For an Authorization Server serving multiple Resource Servers, asymmetric signing is generally preferable because only the public key is distributed.

## 4. Important JWK Parameters

### 4.1. Common Metadata

| Parameter | Meaning and notes |
| --- | --- |
| <code>kty</code> | Key type. Must match the algorithm and key parameters. |
| <code>kid</code> | Unique identifier within the key set according to policy. Must change when creating a new key. |
| <code>use</code> | <code>sig</code> for signing/verification, <code>enc</code> for encryption/decryption. |
| <code>key_ops</code> | Permitted operations, e.g., <code>sign</code>, <code>verify</code>, <code>encrypt</code>, <code>decrypt</code>. Must be compatible with <code>use</code>. |
| <code>alg</code> | Intended JOSE algorithm; not proof that the recipient must accept that algorithm. |
| <code>kid</code> | Placed in the JWT protected header so the verifier can select the matching key. |
| <code>x5c</code> | Certificate chain if present; must be validated against trust/certificate policy separately. |
| <code>x5t</code>, <code>x5t#S256</code> | Certificate thumbprint according to the respective convention. |

In the list above, <code>kid</code> is mentioned again because it is a frequent source of bugs during rotation. Do not reuse one <code>kid</code> for two different keys: Resource Servers may cache keys by ID and verify with the wrong key or fail to refresh the right key.

### 4.2. RSA Parameters

A public RSA JWK typically contains:

- <code>n</code>: modulus.
- <code>e</code>: public exponent.

A private RSA JWK may also contain:

- <code>d</code>: private exponent.
- <code>p</code>, <code>q</code>: prime factors.
- <code>dp</code>, <code>dq</code>, <code>qi</code>: CRT parameters.

Private fields **must not appear in the public JWKS response**. Do not print a full JWK object to debug logs if that object contains a private key.

### 4.3. Public JWK and Private JWK

A JWK built from an RSA key pair can hold both public and private material on the server side:

~~~java
RSAKey signingJwk = new RSAKey.Builder(publicKey)
    .privateKey(privateKey)
    .keyID("as-signing-2026-01")
    .keyUse(KeyUse.SIGNATURE)
    .algorithm(JWSAlgorithm.RS256)
    .build();

JWK publicOnly = signingJwk.toPublicJWK();
~~~

<code>signingJwk</code> holds the private key for the server to sign; <code>publicOnly</code> retains only the public part. Public endpoints must return only the public representation. Do not serialize <code>signingJwk</code> verbatim into an HTTP response or client configuration.

## 5. What Is JWKSource and How Is It Used?

### 5.1. The JWKSource Contract

<code>JWKSource&lt;C&gt;</code> is a Nimbus JOSE + JWT abstraction for supplying keys matching a <code>JWKSelector</code> and an optional context. With Spring Authorization Server, the commonly used type is:

~~~java
JWKSource<SecurityContext>
~~~

The selector describes search criteria, such as an RSA key used for signing with RS256 and/or a specific <code>kid</code>. The key source returns matching JWKs. This allows the encoder to select a private key for signing tokens and the JWK Set endpoint to serve public keys in a consistent way.

| Component | Responsibility |
| --- | --- |
| <code>JWKSet</code> | Holds a set of JWKs. |
| <code>JWKSelector</code> | Describes key filtering criteria. |
| <code>JWKSource</code> | Returns the list of JWKs matching the selector. |
| <code>ImmutableJWKSet</code> | Simple implementation reading from a fixed JWK Set. |
| Key repository/KMS adapter | Dynamic implementation retrieving keys from a managed store or HSM/KMS. |

### 5.2. ImmutableJWKSet for Demos

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey rsaKey = generateRsaSigningKey();
    JWKSet jwkSet = new JWKSet(rsaKey);
    return new ImmutableJWKSet<>(jwkSet);
}
~~~

<code>generateRsaSigningKey()</code> is a helper defined in the next section. This example is convenient for learning, but **not suitable for production if a new key is generated on every application startup**: after a restart, old JWT tokens may no longer have a matching public key for verification.

### 5.3. JWKSource Is Not Just a JSON File

A public JWKS file can be used for verification, but the server also needs the private signing key. In practice, a JWKSource can:

- Read private JWKs from a controlled keystore or secret manager.
- Query public metadata and invoke signing operations from a KMS/HSM.
- Provide both the active key and previous public keys during a rotation window.
- Filter keys by <code>kid</code>, algorithm, key use, and status.

When using a KMS/HSM, exporting the private key into the Java heap is not necessarily required. A custom <code>JwtEncoder</code> or signing adapter compatible with the key system may be needed. The design must ensure that the public JWK metadata and the signing operation point to **the same key material**; otherwise, generated signatures will not match the published public key.

## 6. Generating an RSA Signing Key in Java

### 6.1. Key Generation Example for Demo Environments

~~~java
static RSAKey generateRsaSigningKey() {
    try {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair keyPair = generator.generateKeyPair();
        RSAPublicKey publicKey =
            (RSAPublicKey) keyPair.getPublic();
        RSAPrivateKey privateKey =
            (RSAPrivateKey) keyPair.getPrivate();

        return new RSAKey.Builder(publicKey)
            .privateKey(privateKey)
            .keyID(UUID.randomUUID().toString())
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .build();
    } catch (GeneralSecurityException ex) {
        throw new IllegalStateException(
            "Cannot generate RSA signing key", ex);
    }
}
~~~

This snippet uses Java's <code>KeyPairGenerator</code> and the Nimbus builder. You need to import types from <code>java.security</code>, <code>java.security.interfaces</code>, and <code>com.nimbusds.jose.jwk</code>. A UUID <code>kid</code> is only an example; production should use a stable, unique ID with governance and audit rules.

**Do not regenerate keys on every production deployment.** If keys only live in memory, restarts break verification for JWTs signed by the previous key. Load keys that have been generated and stored durably via a secret manager, protected keystore, or KMS/HSM. Creating a new key is a controlled administrative process.

### 6.2. JWKSource Bean Used in Spring Authorization Server

With a demo key:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey rsaKey = generateRsaSigningKey();
    JWKSet jwkSet = new JWKSet(rsaKey);
    return new ImmutableJWKSet<>(jwkSet);
}
~~~

Spring Authorization Server can use the <code>JWKSource&lt;SecurityContext&gt;</code> bean to configure JWT signing and the JWK Set endpoint. In a real application, replace demo key generation with loading managed keys; never let each instance generate its own key pair and publish the same issuer with inconsistent JWKS.

### 6.3. Creating JwtDecoder for Features That Need JWT Verification

In configurations that require a <code>JwtDecoder</code>, such as enabling OIDC UserInfo or endpoints that verify JWTs:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration
        .jwtDecoder(jwkSource);
}
~~~

This is a common configuration pattern in Spring Authorization Server. Do not confuse the Authorization Server's <code>JwtDecoder</code> with the Resource Server's decoder: the two components may share the same issuer/JWK, but their purpose, audience validation, and policies can differ.

## 7. Connecting JWKSource with JwtEncoder and JwtGenerator

### 7.1. The JWT Creation Chain

Spring Authorization Server uses token generators to create tokens by grant and token type. For JWTs:

1. The provider verifies the authorization grant and creates an <code>OAuth2TokenContext</code>.
2. <code>JwtGenerator</code> receives the context and creates a <code>JwtEncodingContext</code>.
3. Customizers can add claims or JWS headers in the context.
4. <code>JwtEncoder</code> encodes and signs the JWT.
5. The result is saved in <code>OAuth2Authorization</code> and returned to the client in the token response.

<code>JwtEncoder</code> is the abstraction for encoding/signing JWTs. In a Nimbus setup, <code>NimbusJwtEncoder</code> is typically used with <code>JWKSource&lt;SecurityContext&gt;</code>. <code>JwtGenerator</code> does not generate keys itself; it requires a compatible encoder and key source.

### 7.2. Selecting the Right Key When Multiple JWKs Exist

When a JWK Set contains multiple keys, signing key selection must resolve to **a single matching private key** for the JWT's algorithm and metadata. The <code>kid</code> in the protected header helps the Resource Server locate the corresponding public key after the token is issued. Do not assume that merely adding multiple JWKs to a set makes every encoder automatically pick the "newest key" by array order.

With the Nimbus encoder, the selector is built from the header/algorithm and JWKSource. If multiple private keys match the selector, the encoder may fail to resolve a unique key. The design should:

- Have exactly one active signing key per algorithm/selector in use, or
- Configure explicit selection by <code>kid</code>/policy in a compatible encoder, and
- Test that the actual <code>kid</code> header matches the published public JWK.

Do not set an arbitrary <code>kid</code> in a customizer without ensuring JWKSource holds the matching private key. Conversely, do not publish a public JWK with a <code>kid</code> that collides with another key.

### 7.3. Combined Endpoint Configuration Example

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, Customizer.withDefaults())
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .jwkSetEndpoint("/oauth2/jwks")
            .build();
    }
}
~~~

This covers endpoint and issuer configuration; the application still needs a RegisteredClientRepository, authorization services, token generator, JWKSource, user authentication, and related beans. <code>getEndpointsMatcher()</code> selects endpoints managed by the Authorization Server. The <code>/oauth2/jwks</code> path is a common default and is written explicitly here for readability; if changed, update discovery metadata and Resource Servers.

When a <code>JWKSource&lt;SecurityContext&gt;</code> bean is present, Spring Authorization Server can configure the JWK Set endpoint. The endpoint returns the **public JWK Set** for verifiers; inspect the actual deployed response and ensure no private parameters are exposed. Do not write a custom controller that serializes internal full JWK objects.

## 8. JWKS Endpoint and Discovery Metadata

### 8.1. JWK Set Endpoint

A public JWKS endpoint may respond to:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.com
Accept: application/jwk-set+json, application/json
~~~

Abbreviated response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=...

{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "as-signing-2026-01",
      "n": "public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Specific cache headers depend on the server/proxy. Public JWKS is commonly cached to reduce load; cache duration directly affects how quickly Resource Servers pick up new or revoked keys.

### 8.2. Discovery Points to jwks_uri

OAuth Authorization Server Metadata per RFC 8414 and OIDC Discovery publish metadata such as <code>issuer</code>, protocol endpoints, and <code>jwks_uri</code>. Clients/Resource Servers should obtain the JWKS URL from the discovery metadata of a **configured trusted issuer**, rather than hard-coding or trusting a host supplied by an incoming token.

~~~json
{
  "issuer": "https://auth.example.com",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "token_endpoint": "https://auth.example.com/oauth2/token"
}
~~~

This is illustrative JSON with other metadata omitted. When deploying OIDC, the OIDC discovery endpoint has paths and metadata per OpenID Connect Discovery; do not assume RFC 8414 metadata and OIDC discovery are identical documents across all configurations.

### 8.3. Verifying Public JWKS

During deployment or after each rotation, verify:

- The response is a JSON JWK Set with a <code>keys</code> array.
- Each public key has a unique <code>kid</code> per policy.
- <code>kty</code>, <code>use</code>, and <code>alg</code> are appropriate.
- No <code>d</code>, <code>p</code>, <code>q</code>, <code>dp</code>, <code>dq</code>, <code>qi</code>, or equivalent private material is present.
- The issuer in discovery matches the JWT issuer.
- <code>jwks_uri</code> uses HTTPS and a trusted hostname.
- The Resource Server can fetch the set, select the right key, and verify a real token.

Do not allow the Resource Server to dynamically fetch arbitrary <code>jku</code>/<code>x5u</code> URLs from JWT headers without an explicit policy; doing so can open up SSRF or key substitution. The trust anchor must be the configured issuer/JWKS URI or verified discovery.

## 9. Resource Server Verifying JWTs with JWKS

### 9.1. Verification Flow

A JWT access token signed with a private key has an illustrative header:

~~~json
{
  "alg": "RS256",
  "kid": "as-signing-2026-01",
  "typ": "JWT"
}
~~~

The Resource Server reads <code>kid</code>, looks up the matching JWK in the fetched JWKS, and uses the public key to verify the signature. If no matching key is found, it may refresh the JWKS according to policy and retry. A valid signature only proves the token was signed by the corresponding private key; **it does not prove the token is intended for this API**.

After signature verification, the Resource Server must also check:

1. <code>iss</code> matches the trusted issuer.
2. <code>aud</code> contains the current resource server/API.
3. <code>exp</code>, <code>nbf</code> (if present), and clock skew are valid.
4. The signing algorithm is in the allow-list and compatible with the key.
5. Scopes/authorities are sufficient for the resource request.
6. Additional policies such as tenant, token type, client, or revocation status if required by the architecture.

### 9.2. Configuring Resource Server Using Issuer

A common configuration approach in Spring Security:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return JwtDecoders.fromIssuerLocation(
        "https://auth.example.com");
}
~~~

The decoder can use discovery metadata to find the JWK Set URI and construct an appropriate decoder. Real-world configurations should add validators for audience and API-specific policies. Do not verify only the signature while skipping <code>aud</code>; a token valid for the Orders API is not necessarily valid for the Billing API.

### 9.3. Errors When kid Is Not Found

Common causes:

- The Resource Server is caching an old JWKS and has not fetched the new public key yet.
- The Authorization Server started signing with the new key before publishing its public key.
- The <code>kid</code> in the JWT does not match the <code>kid</code> in the JWKS.
- Multiple JWKs share the same <code>kid</code> or have incompatible <code>alg</code>/<code>use</code> metadata.
- A reverse proxy/cache is returning a stale JWKS or a response from the wrong issuer.
- The private key used for signing does not correspond to the published public key.

Do not fix this error by disabling signature validation or accepting tokens when no key is found. Fix the key distribution workflow and caching.

## 10. Safe Signing Key Rotation

### 10.1. Why Keep the Old Public Key?

When a token is signed with key K1, that token still needs public key K1 for verification until the token expires or is invalidated by another mechanism. If the Authorization Server removes K1 from the JWKS immediately when it starts signing with K2, Resource Servers cannot verify still-valid K1 tokens.

### 10.2. Standard Rotation Workflow

~~~mermaid
flowchart TD
    A["Signing with K1; JWKS publishes public K1"] --> B["Generate K2 in KMS/HSM or secure key store"]
    B --> C["Publish public K2 in JWKS"]
    C --> D["Wait for Resource Server caches/replicas to receive K2"]
    D --> E["Switch active signing to K2"]
    E --> F["Sign new tokens with kid=K2"]
    F --> G["Retain public K1 in JWKS"]
    G --> H["Wait for K1 tokens to expire + clock skew + cache margin"]
    H --> I["Remove public K1 from JWKS per policy"]
    I --> J["Archive/destroy private K1 per governance process"]
~~~

The order of **pre-publishing the new public key before signing with the new private key** gives Resource Servers time to fetch the key. Keeping the old public key ensures older unexpired tokens continue to verify cleanly.

### 10.3. Timelines to Calculate Before Removing the Old Key

Do not wait only for <code>accessTokenTimeToLive</code>. Determine:

- When the last token signed with K1 was issued.
- The longest lifetime of any JWT type using K1 (access tokens, ID Tokens, or other JWTs).
- Clock skew tolerance on Resource Server validators.
- JWKS cache duration and propagation delay through CDNs/proxies.
- How long offline clients/APIs may retain old metadata.
- Whether any long-lived tokens or special profiles exist.

Only remove public K1 after every token needing verification with it has expired per policy, plus a reasonable safety buffer. If any JWTs have a longer lifetime than expected, factor them into the plan.

### 10.4. Two-Key JWK Set Example

During rotation, JWKSource can hold the active private key K2 for signing and the public key K1 for verifying older tokens. One internal representation:

~~~java
JWKSet signingAndVerificationSet =
    new JWKSet(List.of(
        activePrivateKeyK2,
        previousPublicKeyK1
    ));

JWKSource<SecurityContext> jwkSource =
    new ImmutableJWKSet<>(signingAndVerificationSet);
~~~

This is an illustrative model for a fixed key store. <code>activePrivateKeyK2</code> is a JWK containing private material for signing; <code>previousPublicKeyK1</code> must be a public-only JWK. The encoder must select K2 when signing, while the JWK Set endpoint publishes only the public representations of both K1 and K2. If the encoder cannot uniquely resolve a private key, configure explicit key selection; do not rely on <code>List</code> ordering.

In production, the key source is usually dynamic and centrally managed; instead of manually constructing a new ImmutableJWKSet on each rotation, update the key store/version in a controlled manner and ensure all instances observe the same state.

### 10.5. Emergency Rotation When a Private Key Is Compromised

If private key K1 is suspected of compromise:

1. Activate the incident response process and restrict access to the KMS/HSM/secret store.
2. Stop using K1 for signing; generate a new K2 inside the trust boundary.
3. Publish public K2 and switch the signer to K2 under the emergency procedure.
4. Remove public K1 from the JWKS so Resource Servers stop trusting tokens signed with the exposed key, after assessing impact and cache behavior.
5. Instruct Resource Servers to refresh JWKS or invalidate caches operationally; stale caches may still accept K1 tokens for some window.
6. Identify affected tokens/authorizations and revoke them using introspection/denylist capabilities or application-level controls.
7. Investigate private key access scope, logs/audit trails, backups, and systems that received the key.

With offline-verified JWTs, removing a public key from the JWKS **does not guarantee all Resource Servers stop accepting tokens immediately** because the public key may already be cached. If immediate revocation is required, supplemental mechanisms such as introspection, a denylist, or centralized state checks with clear synchronization SLAs are needed.

## 11. Storing and Protecting Private Keys

### 11.1. Do Not Store Private Keys in Source Code

Do not:

- Commit PEM files, private JWKs, or keystores with passwords/private keys to Git.
- Place private keys in <code>application.yml</code>, Docker images, or unprotected environment variables.
- Print full JWKs, private keys, or secrets in logs, exceptions, or metrics.
- Share the same private key across dev, test, staging, and production.
- Grant all developers/services read access to the private key solely for testing JWTs.

### 11.2. Storage Options

| Solution | When suitable | What must be protected |
| --- | --- | --- |
| Protected keystore | Small/medium apps, simple key lifecycle. | File, password, filesystem permissions, backups, and mount permissions. |
| Secret manager | Cloud/container infrastructure needing access control and audit. | IAM, secret versions, rotation, and read permissions. |
| KMS | Need controlled signing operations, audit, and separation of keys from app. | IAM policy, key policy, rate limits, and availability. |
| HSM | High physical key protection / compliance requirements. | HSM cluster, backup/restore, operator roles, and ceremony procedures. |

A KMS/HSM can allow signing without exporting the private key. In that case, a <code>JwtEncoder</code> or crypto adapter compatible with the system's signing API is needed; <code>JWKSource</code> still needs to supply public metadata for Resource Server verification.

### 11.3. Access Control and Auditing

Separate permissions clearly:

- The runtime signer only has permission to sign with the active key, not to export the private key.
- The public JWKS service only needs public key metadata.
- Rotation administrators have permission to create/activate keys under an approval workflow.
- Resource Servers only fetch the JWKS and need no access to private keys.
- Backup/restore permissions must be audited, encrypted, and backed by tested recovery procedures.

Periodically audit who has permission to invoke signing operations, abnormal signing request volumes, which key version is active, and the timestamp of the most recent rotation.

## 12. Testing JWK, JWKS, and Signatures

### 12.1. Unit Testing That Public View Contains No Private Material

Example with Nimbus:

~~~java
@Test
void publicJwkDoesNotExposePrivateKey() {
    RSAKey privateJwk = generateRsaSigningKey();

    RSAKey publicJwk = privateJwk.toPublicJWK();

    assertThat(publicJwk.isPrivate()).isFalse();
    assertThat(publicJwk.getKeyID())
        .isEqualTo(privateJwk.getKeyID());
    assertThat(publicJwk.getModulus())
        .isEqualTo(privateJwk.getModulus());
}
~~~

This test verifies the Java-side JWK conversion. You still need to test the **actual JWKS HTTP response** to confirm the endpoint/proxy does not inadvertently return private parameters.

### 12.2. Signing and Verification Integration Test

A test can:

1. Create a test RSA JWK and JWKSource.
2. Use <code>JwtEncoder</code>/<code>JwtGenerator</code> to sign a JWT access token.
3. Read the <code>kid</code> and <code>alg</code> headers.
4. Fetch the corresponding public JWK from the JWKS endpoint.
5. Use <code>JwtDecoder</code> to verify the signature and check issuer/audience/expiry.
6. Modify the payload while keeping the old signature; verification must fail.

Do not merely Base64URL-decode the token and claim it is valid. Decoding does not verify the signature.

### 12.3. Rotation Test Matrix

| Scenario | Expected result |
| --- | --- |
| Token signed with K1, JWKS has public K1 | Resource Server verifies successfully if claims are valid. |
| JWKS has K1 and K2, new token signed with K2 | Resource Server selects K2 by <code>kid</code>. |
| Publish K2 before starting to sign with K2 | Resource Server can fetch the public key before receiving new tokens. |
| Unexpired K1 token, K1 still in JWKS | Old token continues to verify. |
| Remove K1 while K1 token is still unexpired | Test must detect that Resource Server fails verification after cache refresh; procedure must not remove prematurely. |
| JWT has a nonexistent <code>kid</code> | Rejected; no fallback to an arbitrary key. |
| Two JWKs share the same <code>kid</code> | Deployment validation fails or raises a critical alert. |
| Public JWKS contains <code>d</code> or private RSA params | Security test fails. |
| Algorithm in JWT is outside allow-list | Resource Server rejects. |
| JWK <code>use</code>/<code>alg</code> is incompatible | Key is not used for that signature. |
| JWKS cached too long during rotation | Review cache policy and refresh mechanism. |
| JWT issuer differs from configured issuer | Resource Server rejects despite valid signature. |
| Audience does not match API | Resource Server rejects. |
| KMS unavailable | Do not issue malformed/unsigned tokens; report error and alert. |

### 12.4. Testing Endpoints and Discovery

With <code>MockMvc</code> or HTTP integration tests:

- GET <code>/.well-known/openid-configuration</code> when OIDC is enabled and check <code>jwks_uri</code>.
- GET RFC 8414 Authorization Server metadata if configured, checking issuer and JWK Set URI.
- GET <code>/oauth2/jwks</code>, verifying status/content type and public-only JWK fields.
- Verify JWKS contains both new and old keys during the rotation phase.
- After removing the old key, verify the response no longer includes that key according to policy timing.
- Check that reverse proxies/caches do not serve responses from another issuer or environment.

Do not use a mock endpoint returning static JSON as proof that <code>JWKSource</code>, <code>JwtEncoder</code>, and the Resource Server are wired correctly.

## 13. Common Errors and Troubleshooting

### Error 1: Generating a New Key on Every Restart

**Symptom:** Tokens issued right before a restart fail verification after the server restarts.

**Cause:** The old key lived only in RAM and was replaced with a new key pair.

**Fix:** Use durable key storage; retain the old public key in JWKS until its tokens expire.

### Error 2: Public JWKS Contains Private Key Parameters

**Symptom:** The JSON response includes <code>d</code>, <code>p</code>, <code>q</code>, or other private parameters.

**Cause:** A custom controller serialized the full JWK instead of its public representation.

**Fix:** Use the framework's JWK Set endpoint or export only <code>toPublicJWK()</code>/<code>toPublicJWKSet()</code>; add tests scanning for private fields.

### Error 3: JWT Has a kid Not Present in JWKS

**Symptom:** Resource Server reports it cannot find the signing key.

**Cause:** Wrong kid, key was not pre-published, stale JWKS cache, or signer used a different key from JWKSource.

**Fix:** Check the JWT header, JWKS, active key ID, cache, and KMS mapping.

### Error 4: JWKS Has Multiple Matching Private Keys

**Symptom:** The encoder cannot select a unique signing key or raises an encoding error.

**Cause:** Multiple keys match the selector/algorithm without an explicit selection policy.

**Fix:** Keep only one active matching private signing key or route keys explicitly by kid/encoder; still retain old public keys for verification.

### Error 5: Resource Server Trusts Signature Without Checking Audience

**Symptom:** An Orders API token is accepted when calling the Billing API.

**Cause:** Validating signature/issuer only without audience validation.

**Fix:** Configure an audience validator and per-Resource-Server scope/authorization policies.

### Error 6: Removing the Old Key Immediately When Activating the New Key

**Symptom:** APIs fail to verify older tokens right after rotation.

**Cause:** Did not wait for older access/ID tokens to expire and caches to synchronize.

**Fix:** Pre-publish the new key, switch the signer, keep the old public key through the compatibility window, and only then retire it.

### Error 7: Confusing JWKSource with JWKS URL

**Symptom:** Encoder configuration is given an HTTP URL, or Resource Server is given a server Java bean.

**Cause:** Confusing the in-app key source abstraction with the HTTP key-publishing endpoint.

**Fix:** The server uses <code>JWKSource</code>; clients/Resource Servers fetch JWKS via the URL published in discovery.

### Error 8: Using HMAC While Publishing the Secret via JWKS

**Symptom:** Resource Servers can forge tokens because they received the shared secret.

**Cause:** Confusing an HMAC verification secret with a public key.

**Fix:** Never publish symmetric secrets; use asymmetric signing when multiple independent parties need to verify tokens.

### Error 9: Trusting Client-Supplied kid/Headers to Select Trust Key

**Symptom:** An attacker controls the key source or forces the server to fetch keys from an untrusted URL.

**Cause:** Treating <code>kid</code>/<code>jku</code>/<code>x5u</code> from an unverified JWT as a trust anchor.

**Fix:** Only select keys from a JWKSource/JWKS bound to a trusted issuer and allow-listed algorithms.

## 14. Key Operations and Governance

### 14.1. Key Lifecycle Workflow

Signing key governance requires a defined workflow with clear ownership:

1. **Create:** generate the key in a KMS/HSM or protected environment; assign a unique ID and metadata.
2. **Verify:** check public key, algorithm, size/curve, key usage, and signer mapping.
3. **Pre-publish:** publish the new public JWK and wait for Resource Servers to pick it up.
4. **Activate:** switch the signer to the new key; record timestamp and the human/automation operator.
5. **Monitor:** track JWT <code>kid</code> values, signature errors, JWKS cache hits, and token issuance.
6. **Retire:** wait for old tokens to expire plus cache margin; remove the old public JWK.
7. **Archive/destroy:** handle the old private key per policy, backup, audit, and regulatory requirements.

### 14.2. Configuring JWKS Cache

Caching prevents Resource Servers from fetching the JWKS on every request. However, caching too long delays picking up new keys and compromised-key removals; caching too briefly increases load and dependency on Authorization Server availability.

Choose cache TTL based on:

- Expected rotation frequency.
- Maximum JWT lifetime.
- Number of Resource Servers/instances.
- CDN/reverse proxy propagation time.
- Refresh behavior upon seeing an unknown <code>kid</code>.
- Emergency key removal procedures.

Do not assume every Resource Server will automatically refresh the JWKS immediately upon seeing an unknown kid; cache/refresh behavior depends on the decoder and HTTP caching. Test specifically with the Spring Security version you deploy.

### 14.3. Metrics and Alerts

Useful signals:

- Token issuance count by <code>kid</code> and algorithm.
- Timestamp when the active key changed.
- Number of published JWKs, keys approaching expiration, or missing public counterparts.
- Rates of signature errors, unknown kid errors, and issuer/audience mismatches.
- KMS/HSM signing errors, latency, and quota usage.
- Timestamp when public JWKS updated across nodes/edges.
- Unusual access events targeting private keys or signing operations.

Logs should only record safe metadata such as kid, client ID per policy, request ID, and error codes; avoid logging raw JWTs unless necessary, and never log private JWKs or credentials.

## 15. Hands-On Exercise

You are building an Authorization Server for two Resource Servers: <code>orders-api</code> and <code>billing-api</code>. JWT access tokens are signed with RSA; both APIs share the same issuer but require different audiences. The system requires quarterly key rotation and runs across three Authorization Server instances.

1. Create an RSA JWK with <code>kty</code>, <code>use</code>, <code>alg</code>, <code>kid</code>, and public/private parameters. Explain which parts are allowed to appear in the JWKS.
2. Create a <code>JWKSet</code> and <code>JWKSource&lt;SecurityContext&gt;</code> using <code>ImmutableJWKSet</code> for a demo.
3. Connect JWKSource with <code>JwtEncoder</code>/<code>JwtGenerator</code> and Spring Authorization Server's JWK Set endpoint.
4. Use discovery metadata to retrieve <code>jwks_uri</code>; configure the Resource Server to validate issuer, signature, audience, and scope.
5. Design two tokens with different audiences; prove that an Orders token is rejected by the Billing API even though both are signed by the same key.
6. Describe a K1 → K2 rotation: pre-publish timing, switching the signer, retaining public K1, and conditions for removing K1.
7. Test an unexpired K1 token while JWKS contains both K1 and K2; verify the <code>kid</code> header of a newly issued token.
8. Simulate a stale JWKS cache and an unknown kid, and define a safe refresh approach.
9. Design a KMS/HSM adapter so the private key does not have to be exported to the Java heap; explain how to ensure the public JWK matches the signing key.
10. Write an emergency rotation runbook for a compromised private key and explain why offline JWTs may still be accepted during the cache window.

**Completion criteria:** You can explain and demonstrate that **the Authorization Server signs with a protected private key**, **the Resource Server accepts only public JWKs from a trusted issuer**, **kid accurately links tokens to public keys**, and **rotation does not unexpectedly break still-valid tokens**.

## 16. Reference Documentation

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK structure, JWK Set, and key parameters.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JOSE signatures, protected headers, and verification.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata and JWKS URI.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): discovery metadata and <code>jwks_uri</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): JWKSource, JwtEncoder, and token generation.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): JWK Set endpoint and Authorization Server configuration.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): configuring <code>JWKSource&lt;SecurityContext&gt;</code> and <code>JwtDecoder</code>.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWTs via issuer/JWK Set URI.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JWK/JWKSet/JWKSource APIs and JOSE handling in Java.
