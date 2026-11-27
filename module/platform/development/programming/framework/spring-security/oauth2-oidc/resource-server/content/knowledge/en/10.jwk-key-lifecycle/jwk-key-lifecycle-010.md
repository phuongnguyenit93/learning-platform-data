# `jku`, `x5u`, and Embedded Keys Are Not Automatically Trusted Sources

In a **Spring Security OAuth 2.0/OIDC Resource Server**, JWT access tokens are typically signed by the Authorization Server and verified by the API using the **trusted issuer's public key**. JSON Web Signature (JWS) allows JOSE headers to carry several key-related parameters, such as **kid**, **jku**, **jwk**, **x5u**, **x5c**, and **x5t#S256**. These fields assist with identifying or distributing keys, yet a token **self-declaring** a key's location or value **is not enough to turn that key into a trusted verification source**.

If a Resource Server trusts a key nominated by an unverified token itself, an attacker can generate their own key pair, sign a JWT claiming **scope = admin**, and point the server to their own public key. The cryptographic math still checks out, yet it proves only that the token was signed with **the attacker's key**, not that it was issued by the system's delegated Authorization Server.

This lesson explains the exact role of key-related JOSE headers, the trust chain when using issuer/JWKS, key-substitution and SSRF risks, secure Spring Security configuration, and one legitimate special case where proof-of-possession is explicitly designed.

## 1. Valid Signature Under Which Key—and Who Vouched for That Key?

There are two **distinct** questions:

1. **Cryptographic verification:** does the JWT signature match the public key being used?
2. **Trust establishment:** does that public key genuinely belong to an **issuer configured as trusted by the API**, and is it permitted to verify this token type?

Answering only the first question lets the system accept signatures created by **anyone who generates their own key pair**.

Example request:

~~~http
GET /api/admin/reports HTTP/1.1
Host: orders.example.com
Authorization: Bearer <compact-jws>
~~~

JWT with an illustrative protected header:

~~~json
{
  "alg": "RS256",
  "kid": "my-key",
  "jku": "https://attacker.example/keys.json",
  "typ": "at+jwt"
}
~~~

And illustrative payload:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "administrator",
  "aud": ["orders-api"],
  "scope": "reports.export",
  "exp": 1893456000
}
~~~

An attacker can write those claims themselves, generate an RSA key pair, and sign the JWT with their own private key. If the Resource Server **downloads the JWKS from the JWT-declared `jku`** and verifies using that fetched key, the signature passes even though **the issuer in the payload is purely self-asserted**.

Foundational principle:

> **A key is trusted only when the system establishes a trust relationship between that key and a trusted issuer or validation policy prior to trusting the token. A key embedded in a JWT or a URL named by a JWT never proves that relationship on its own.**

This remains true even when **jku** is an HTTPS URL, the JWT is well-formed, **kid** matches, and the verification algorithm executes faithfully.

## 2. Key-Related JOSE Headers

JWS uses JOSE Header Parameters to convey metadata for signature processing. Some parameters are optional and may appear in protected or unprotected headers depending on JWS structure; for the common **JWS Compact Serialization** of access tokens, the JOSE header is the protected header.

| Parameter | Data Carried | What Is It For? | Establishes Independent Trust? |
|---|---|---|---|
| **alg** | Algorithm name, e.g., **RS256**, **ES256** | Indicates the JWS algorithm used | **No**; the API must restrict permitted algorithms |
| **kid** | Key identifier string | Hints at key selection within a trusted key set | **No** |
| **jku** | **JWK Set URL** | Points to a JSON resource containing a JWK Set | **No** |
| **jwk** | A **JWK JSON object** | Embeds key material directly in the header | **No** |
| **x5u** | **X.509 URL** | Points to an X.509 certificate or certificate chain resource | **No** |
| **x5c** | Array of X.509 certificates | Embeds the certificate chain directly in the header | **No** |
| **x5t** | Certificate SHA-1 thumbprint | Aids certificate identification | **No** |
| **x5t#S256** | Certificate SHA-256 thumbprint | Aids certificate identification via SHA-256 | **No** |
| **typ** | Object/token type | Hints at token/profile type, e.g., **at+jwt** | **No** |

An example JOSE protected header combining multiple parameters:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11",
  "jku": "https://login.example.com/keys/jwks.json",
  "x5t#S256": "<certificate-thumbprint-base64url>"
}
~~~

These values are **illustrative**, not a real token for calling an API. Even when the hostname looks like an identity provider, the Resource Server must never treat **jku** as a command to fetch keys outside trust policy.

### 2.1. **kid** Selects a Key; It Does Not Define Who Is Trusted

An issuer's JWKS can contain multiple keys with distinct **kid**s for signing key rotation:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus-old>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus-new>",
      "e": "AQAB"
    }
  ]
}
~~~

Both **n** values are placeholders; a real JWKS carries valid JWK modulus values. If a JWT carries **kid = signing-2026-11**, the decoder looks up the matching key **inside the JWKS already published by the trusted issuer**.

Never use **kid** to build uncontrolled URLs, file paths, or database queries. A `kid` string can be fabricated by an attacker; only the signature verified with a trusted key carries cryptographic meaning.

### 2.2. **jku** Is a JWKS URL

Per JWS, **jku** is a URI pointing to a resource containing a **JWK Set**, i.e., JSON with a **keys** array. Example:

~~~json
{
  "alg": "RS256",
  "kid": "key-a",
  "jku": "https://issuer.example.org/public/jwks.json"
}
~~~

If the verifier **already has a policy trusting this URL**, `jku` can reference the key source. However, an arbitrary JWT has no authority to expand the set of key sources trusted by an API.

**An HTTPS URL protects transport and verifies the TLS identity of that hostname; it never proves that hostname is authorized to issue JWTs for your API.** An attacker's domain can also serve valid HTTPS.

### 2.3. **jwk** Is an Embedded Key Inside the Header

Example of an embedded RSA public JWK:

~~~json
{
  "alg": "RS256",
  "jwk": {
    "kty": "RSA",
    "n": "<base64url-rsa-modulus>",
    "e": "AQAB"
  }
}
~~~

**`jwk` is not `jwks_uri`.** It places a key object directly inside the JOSE header. If an outsider crafts a token embedding their own public key, verifying the signature with that key never proves the issuer minted the token.

In standard OAuth2 Resource Servers, never use **jwk** inside an access token to dynamically replace verification keys sourced from a trusted issuer/JWKS.

### 2.4. **x5u** Points to an X.509 Certificate Chain

Example:

~~~json
{
  "alg": "RS256",
  "x5u": "https://certs.example.org/signing-chain.pem"
}
~~~

Per JWS, `x5u` points to a resource containing an X.509 certificate or certificate chain in the appropriate PEM format. It supplies data to extract a public key and certificate metadata.

**A downloadable certificate is not automatically trusted.** If an attacker issues a certificate for their own public key and puts that URL in `x5u`, the Resource Server must never treat the certificate as proof that the real Authorization Server signed the token.

### 2.5. **x5c** Is an Embedded Certificate Chain

Instead of a URL, JWS can embed certificates directly:

~~~json
{
  "alg": "RS256",
  "x5c": [
    "<base64-der-leaf-certificate>",
    "<base64-der-intermediate-certificate>"
  ]
}
~~~

Elements of **x5c** are Base64 strings representing DER-encoded certificates—distinct from the Base64URL encoding used by JWK numeric components. This chain **can supply input for certificate path validation**, yet never replaces checking trust anchors, certificate validity, usage constraints, and binding to the issuer.

Thumbprints **x5t** or **x5t#S256** also merely identify a certificate; a token-supplied thumbprint cannot grant access on its own unless matched against a value pre-confirmed and pinned from a trusted source.

## 3. The Safe Path: Configured Issuer, Metadata Publishes `jwks_uri`

In OIDC/OAuth2 architectures, Resource Servers normally start from an administrator-configured issuer URI:

~~~text
https://login.example.com/realms/shop
~~~

The issuer exposes metadata via a standard discovery endpoint. Metadata may contain:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Spring Security uses this information to establish verification keys for access tokens. Standard trust chain:

~~~mermaid
flowchart TD
    C[Resource Server configures trusted issuer] --> M[Discover issuer metadata over HTTPS]
    M --> J[Read jwks_uri from metadata matching issuer]
    J --> K[Fetch JWKS over HTTPS]
    K --> P[Select public key matching kid / alg]
    P --> V{JWS signature verification succeeds?}
    V -->|No| R[401]
    V -->|Yes| Q{iss / aud / exp / nbf and profile valid?}
    Q -->|No| R
    Q -->|Yes| A{Scope + resource permissions satisfied?}
    A -->|No| D[403 or 404 per policy]
    A -->|Yes| OK[Allow API processing]
~~~

The critical difference between **jwks_uri** and **jku**:

- **jwks_uri** in metadata comes from a discovery flow anchored at **an issuer the API already configured as trusted**.
- **jku** is a JOSE Header Parameter coming from **the incoming request's token**. Unless the application has an explicit trust contract binding it, it is merely a caller-asserted hint.

Matching domains alone is not absolute safety either. Trust also depends on validating `issuer` inside metadata, HTTPS certificates, source validation rules, redirect/network boundaries, and API configuration. Even so, a JWKS URI obtained from a trusted issuer forms a **clear, rooted trust chain**, whereas an arbitrary `jku` inside a JWT does not.

### 3.1. A Protected Header Still Does Not Establish Trust

One might argue: "If `jku` sits inside the signed protected header, why not trust it?"

The problem is **the signature is not trusted** until a trusted key is identified. If key selection relies entirely on **the `jku` supplied by that very protected header**, you get a circular loop:

~~~text
Trust jku because the JWT is signed
  -> to verify the JWT, fetch the key from jku
  -> retrieve the sender's key
  -> verify signature with that key
  -> conclude jku is trustworthy
~~~

This is circular reasoning: the token chooses the key used to validate itself. **A protected header prevents tampering after signing**, yet never proves who had the right to sign.

### 3.2. Unverified JWT Headers Can Support Bounded Lookups

Not all reading of a JOSE header before verification is forbidden. A decoder needs to read **alg** or **kid** to select the algorithm and candidate key. What matters is using those values **strictly within the key and algorithm sets already permitted by the Resource Server**.

For example:

~~~text
Allowed issuer: https://login.example.com/realms/shop
Trusted JWKS:  https://login.example.com/realms/shop/protocol/openid-connect/certs
Allowed alg:   RS256

JWT kid:       signing-2026-11
JWT jku:       https://random.example/jwks.json
~~~

The decoder may look up **kid** inside the trusted JWKS. It must never follow **jku** to another source simply because the JWT says so. If no matching key exists in the trusted set, the result is verification failure or a policy-governed refresh of the trusted key set—never pivoting to an arbitrary hostname.

## 4. Attack When Automatically Trusting **jku**

Consider a flawed implementation with this logic:

~~~text
1. Receive Bearer JWT.
2. Parse JOSE header to extract jku.
3. Download JWKS from jku.
4. Select key by kid.
5. Verify signature with the downloaded key.
6. Accept claims and grant access.
~~~

An attacker can:

1. Generate a personal RSA key pair, keeping the private key.
2. Publish the public key at **https://attacker.example/jwks.json**.
3. Craft a JWT claiming **iss** as the real issuer, **aud** as the API, and admin scopes.
4. Point **jku** in the header to their JWKS.
5. Sign the token with their own private key.
6. Send the token to the flawed API.

~~~mermaid
sequenceDiagram
    participant X as Attacker
    participant API as Vulnerable Resource Server
    participant H as Attacker JWKS
    X->>X: Generate RSA key pair and forged-privilege token
    X->>H: Publish public JWK
    X->>API: Bearer JWT with jku=https://attacker.example/keys
    API->>H: GET token-nominated jku
    H-->>API: Attacker's public key
    API->>API: Verify token with attacker's key
    Note over API: Signature valid, yet issuer never established
    API-->>X: Unauthorized access if claims are trusted
~~~

The bug is not in the RS256 algorithm or signature math. The bug lies in **key-source selection**. Switching to ES256, EdDSA, or another JOSE library does nothing to fix it if the trust model still accepts caller-chosen key sources.

Post-signature issuer validation does not rescue a design where the attacker sets **iss** freely and signs with a key the API just trusted. You must establish **trusted issuer key sources upfront**.

## 5. Attack with Directly Embedded **jwk**

A similar flaw requiring zero outbound network calls:

~~~text
JWT header:
  alg = RS256
  jwk = sender's public key

JWT payload:
  iss = spoofed trusted issuer
  scope = admin

JWT signature:
  computed with matching private key
~~~

If a Resource Server blindly verifies JWTs using **header.jwk**, any caller can craft arbitrary tokens and prove they were signed by **the very key they just handed over**.

That is cryptographically a **self-signed token**, proving nothing about Authorization Server issuance. Without confirming that the JWK is **authorized** to sign access tokens for the issuer/API, never use it to create an authenticated principal.

A rule worth memorizing:

> **A key can verify a signature while belonging to the wrong issuing party.**

The exact same issue applies to **x5c** embedding a self-signed certificate or a certificate unbound to the issuer; extracting a public key from a certificate does not grant token-issuance authority.

## 6. Attacks with **x5u**, **x5c**, and Certificate Limitations

**x5u** points to a hosted certificate or chain. **x5c** embeds a certificate chain directly. Turning a certificate into a trusted JWT verification key requires, depending on application profile:

1. Validating structure, validity period, key usage, chain signatures, and an appropriate trust anchor.
2. Ensuring the certificate or public key is genuinely **bound to the delegated issuer** by contract (pinning, metadata, registry, or dedicated PKI policy).
3. Ensuring the certificate is permitted for that algorithm and token type.
4. Verifying the JWT signature with the corresponding public key.
5. Validating issuer, audience, timestamps, token type, and authorization rules.

A certificate chaining to a **public CA** does not automatically prove it is allowed to sign JWTs for **login.example.com**. Public CAs validate identity for certificate issuance purposes; they do not confer OAuth access-token-signing authority for an issuer onto anyone holding a valid TLS certificate.

### 6.1. Is HTTPS When Fetching `x5u` Enough?

**No.** HTTPS ensures the client connects to the matching TLS hostname/certificate and protects data in transit. Yet **https://attacker.example/cert.pem** can be served securely with a valid TLS certificate owned by the attacker. TLS checks out, while the contents still are not an API-authorized token-signing source.

Likewise, TLS on a **JWKS endpoint** must be verified to prevent key substitution in transit, yet it is only one link in the trust chain. The endpoint origin itself must be administratively trusted beforehand.

### 6.2. `x5t` and `x5t#S256` Are Only Identification Hints

A token header containing:

~~~json
{
  "alg": "RS256",
  "x5t#S256": "<base64url-sha256-thumbprint>"
}
~~~

A thumbprint aids certificate lookup. If the Resource Server **already pinned** a thumbprint from trusted configuration, it can match and apply policy. However, a thumbprint supplied by the incoming token never proves a certificate is trustworthy; an attacker can generate both a certificate and its thumbprint.

When a thumbprint is needed, prefer **x5t#S256** over legacy SHA-1 thumbprints, while still validating the trust chain and issuer binding per system model.

## 7. SSRF: Network Risks When Auto-Fetching `jku` or `x5u`

Automatically fetching URLs inside a JWT causes not only **key substitution** but also **Server-Side Request Forgery (SSRF)**. An attacker can coerce the Resource Server into issuing HTTP requests from inside the server's network to targets unreachable by external clients.

Examples of targets an arbitrary JWT must never be able to specify:

~~~text
http://127.0.0.1:8080/internal
http://169.254.169.254/
http://localhost/admin
http://internal-service.cluster.local/keys
https://attacker.example/redirect-to-internal
~~~

These addresses merely illustrate the hazard; never probe unauthorized internal URLs. Resource Servers often run inside cloud/Kubernetes networks with privileges different from the token sender, amplifying SSRF impact.

### 7.1. Checking "URL Starts with `https`" Is Insufficient

A URL can still:

- Point to an attacker-controlled server holding a valid HTTPS certificate.
- Issue an HTTP redirect to another host or IP.
- Use a DNS hostname whose resolution shifts over time.
- Abuse IP formats, IPv6, userinfo, ports, or tricky encodings to bypass naive filters.
- Point to a URL matching a naive allowlist by name yet routing outside network policy after redirects/proxies.

Therefore, if a protocol **genuinely requires** dynamic fetching of **jku/x5u**, you need controls covering **both key trust and network-fetch safety**. Never rely on a naive string check like checking whether the hostname contains **login**.

### 7.2. Minimum Controls When a Protocol Requires Dynamic Key URLs

For an explicitly approved design permitting a bounded set of sources:

- Define an **allowlist of issuers and key endpoints** upfront; never read the whitelist from the token itself.
- Require HTTPS with full certificate chain and hostname checks; never use **trust-all**.
- Strictly block or restrict redirects; if allowed, re-validate every redirect target.
- Enforce connect/read timeouts, response size limits, content-type checks, and rate limits to prevent DoS.
- Validate DNS/IP/network destinations at each step; block loopback, link-local, internal metadata, and private networks outside allowed boundaries.
- Enforce egress firewalls and network policies/service-mesh rules restricting where the Resource Server can connect.
- Never forward Authorization headers, tokens, cookies, or client secrets when fetching JWKS/certificates.
- Use bounded caching and cap distinct URL/`kid` fetches so attackers cannot force mass downloads.
- Emit safe telemetry without logging raw JWTs or secrets.

**A network allowlist does not replace issuer trust.** A JWKS endpoint sitting on an allowed network still has no authority to sign JWTs for an API unless bound by token-issuance policy.

In standard Spring Security JWT Resource Servers, prefer the simpler rule: **never let tokens choose key sources**; rely on **trusted `issuer-uri`/`jwk-set-uri` configuration**.

## 8. Configuring Spring Boot Resource Server with a Fixed Trust Chain

A JWT-based Spring Boot API should have Spring Security fetch public keys from an administratively configured issuer/JWKS.

Example **application.yml**:

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

In supported Spring Boot configurations:

- **issuer-uri** identifies the Authorization Server trusted by the API.
- Spring Security can use metadata discovery to locate the issuer's **jwks_uri**.
- **audiences** requires access tokens to be intended for **orders-api**.
- The decoder uses the matching public keys and applies configured token validators.

If the exact JWKS URI is already known, you can also specify:

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

**Here `jwk-set-uri` comes from trusted configuration**, never from a client-supplied **jku** header in the JWT. Keeping **issuer-uri** preserves standard **iss** validation; audience should still be verified explicitly.

Version notes to check against your exact Spring Boot/Security release:

- Spring Boot 3.x typically uses **spring-boot-starter-oauth2-resource-server**.
- Spring Boot 4.x introduces the starter **spring-boot-starter-security-oauth2-resource-server**.
- Use Boot's dependency management/BOM; never mix major versions of Spring Security modules.
- Defining a custom `JwtDecoder` bean can alter auto-configuration; preserve issuer, audience, timestamp, and token-profile validators per policy.

### 8.1. `SecurityFilterChain` Enforces Permissions After Authentication

Spring Security Servlet example:

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
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
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

Even after a token verifies against the trusted JWKS, the API must still authorize access. **SCOPE_orders.read** permits only a category of operations; tenant, owner, and order-state checks must be enforced per business policy.

### 8.2. Using `NimbusJwtDecoder` with a Configured JWKS URI

When configuring the decoder manually:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String TRUSTED_JWKS_URI =
        "https://login.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(TRUSTED_JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience does not include orders-api",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, audience)
        );
        return decoder;
    }
}
~~~

This snippet expresses five explicit decisions:

1. **TRUSTED_JWKS_URI** is an API-managed constant, never read from the JWT **jku** header.
2. **RS256** is pinned as the accepted algorithm per the issuer contract.
3. **JwtValidators.createDefaultWithIssuer** includes standard lifetime and issuer checks.
4. The audience validator rejects JWTs not intended for **orders-api**.
5. The decoder fails if signature or validators fail; the API never creates an authenticated principal for forged tokens.

When customizing a decoder, check access-token profile rules such as **typ = at+jwt** per your provider; never accept an OIDC ID Token as a Bearer access token merely because both JWTs are signed by the same OP.

Crucially, this example never reads **jku**, **x5u**, or **jwk** from the JOSE header to build URLs or public keys. Key selection stays restricted to the trusted JWKS configured on the decoder.

## 9. Dangerous Code Patterns to Spot During Reviews

An anti-pattern expressed in pseudocode:

~~~java
// WRONG - illustrates design flaw only; not a complete JOSE API.
String rawToken = readAuthorizationBearer(request);
Map<String, Object> header = parseHeaderWithoutVerification(rawToken);
String keyUrl = (String) header.get("jku");

// URL chosen by the token itself.
JwkSet attackerControlledKeys = fetchJwks(keyUrl);

boolean signatureMatches = verifySignature(rawToken, attackerControlledKeys);
if (signatureMatches) {
    // The token sender could sign using a key they hosted at jku.
    acceptClaimsAsAuthenticated(rawToken);
}
~~~

The function names above are **illustrative**, not Spring Security APIs. The dangerous bug is **reading `keyUrl` from an unverified JWT** and treating whatever keys come back as trusted issuer keys.

A closely related variant:

~~~java
// WRONG - self-verifying pattern using an embedded key.
Map<String, Object> header = parseHeaderWithoutVerification(rawToken);
PublicKey key = parseJwk((Map<?, ?>) header.get("jwk"));
boolean valid = verifySignature(rawToken, key);
~~~

Even when **valid = true**, the question "Who authorized this key to sign access tokens?" remains unanswered. A valid signature against a self-supplied key is never enough for authentication.

How to fix this in Spring Security applications:

- Use **JwtDecoder** with a trusted issuer/JWKS.
- Never construct **JwtAuthenticationToken** directly from unverified token claims outside a decoder.
- Never let token-supplied **jku**, **x5u**, **jwk**, or **kid** cross trust boundaries.
- Reject JWTs that fail verification against the configured contract.

## 10. Multi-Issuer, Multi-Tenant, and Dynamic Key Selection

A SaaS system may accept tokens from multiple issuers, e.g.:

~~~text
Tenant A: https://login.example.com/realms/a
Tenant B: https://login.example.com/realms/b
Tenant C: https://identity.partner.example/oidc
~~~

The system may need to pick a **JwtDecoder** based on issuer/tenant. In this model, **dynamic selection does not mean trusting every issuer**.

Rules:

1. Maintain an **allowlist of permitted issuers**, each with its own trust configuration.
2. If reading the unverified **iss** claim for routing, use it strictly as a **lookup hint into the allowlist**.
3. Each decoder verifies tokens against its registered issuer's JWKS and validates **iss**, **aud**, lifetime, and other checks.
4. Unverified claims must never register a new issuer or JWKS URL at runtime.
5. Business logic must still verify tenant/membership on data even for tokens from a valid issuer.

Spring Security offers multi-tenancy mechanisms such as **JwtIssuerAuthenticationManagerResolver** where appropriate; production deployments must configure it to accept only pre-approved issuers. Never create a resolver that defaults to fetching any issuer URL supplied by a client.

### 10.1. Why Not Rely on Domain Names Alone?

One issuer host can serve multiple realms or tenants on the same hostname. A token signed by **/realms/a** must not automatically be accepted for **/realms/b**.

Conversely, a trusted issuer may publish **jwks_uri** on a different hostname via verified metadata. Thus neither "same domain is always safe" nor "different domain is always wrong" suffices. You need an explicit **issuer → metadata/JWKS** mapping governed in API policy.

## 11. Special Case: Embedded Keys Can Be Used in DPoP

A commonly misunderstood exception is **DPoP (Demonstrating Proof-of-Possession)**, defined by **RFC 9449**. A DPoP proof is a JWT that can carry a public **jwk** in its JOSE header, signed by the matching private key.

Why can DPoP use an embedded key?

Because the protocol **does not treat the public key inside the DPoP proof as the issuer signing the access token**. Instead, the server verifies completely different bindings:

- The DPoP proof is signed by the private key matching the embedded public JWK.
- The proof carries bindings such as HTTP method (**htm**), HTTP URI (**htu**), timestamp (**iat**), replay identifier (**jti**), nonce when required, and other protocol constraints.
- The access token itself was issued by the Authorization Server and verified through a trusted path.
- The access token is **sender-constrained**, typically carrying **cnf.jkt** as a JWK thumbprint; the API compares that against the key in the DPoP proof.
- The Resource Server validates the binding across access token, DPoP proof, and incoming HTTP request.

Thus, **jwk in a DPoP proof** proves *the caller possesses the private key bound to an issuer-verified access token*. It is never used to self-verify and authenticate a token minted by an attacker.

~~~mermaid
flowchart LR
    AT[Access token from trusted issuer] --> V[Signature / introspection check]
    V --> C[Read verified cnf.jkt]
    P[DPoP proof with embedded JWK] --> S[Verify proof signature]
    S --> T[Check htm, htu, iat, jti, nonce...]
    C --> M{Proof key thumbprint matches cnf.jkt?}
    T --> M
    M -->|Yes, and all checks pass| OK[Valid proof-of-possession]
    M -->|No| NO[Reject]
~~~

You cannot turn an ordinary Bearer Resource Server into a DPoP Resource Server merely by accepting **header.jwk**. DPoP requires full protocol handling, token binding, and replay protection. It proves the broader rule: **an embedded key has value only inside an explicitly defined trust policy**.

## 12. Embedded Keys and the JWT Signing Key Lifecycle

Within **JWK and key lifecycle**, distinguish issuer-controlled rotation from arbitrary per-token key substitution.

### 12.1. Proper Rotation: Issuer Swaps Public Keys at a Trusted JWKS

Suppose an issuer has public key A and rotates to B:

| Time | Key Used by Issuer to Sign JWTs | JWKS Published at Trusted URL | Resource Server |
|---|---|---|---|
| **T0** | A | A | Verifies tokens with A |
| **T1** | A | A and B | Can pre-cache B |
| **T2** | B | A and B | Accepts unexpired old A tokens and new B tokens |
| **T3** | B | B | Stops trusting A after suitable overlap window |

The JWKS origin remains an issuer-managed endpoint; the key set evolves under control. **kid** assists selecting keys from that set—never granting tokens the right to inject new keys.

Operational requirements:

- Publish new public keys before signing new tokens whenever possible.
- Retain old keys long enough for unexpired tokens, except during emergency revocation.
- Configure JWKS decoder cache/refresh policies.
- Never reuse the same **kid** for different key material while old caches persist.
- When a signing key is compromised, follow incident rotation/revocation procedures—never just swap `kid` in headers.
- Never publish private keys or symmetric secrets inside a public JWKS.

### 12.2. Why Blindly Accepting `jku` Breaks the Key Lifecycle

If every token could point to its own JWKS, the issuer loses control over which keys the Resource Server accepts. The issuer removing key A from the trusted JWKS would not stop someone from supplying key A or another key via their own **jku**.

That undermines rotation and compromised-key response. Key sources must have a **governed lifecycle**, never gaining trust simply by appearing in a request's JOSE header.

## 13. Common Mistakes and How to Handle Them

| Mistake | Risk | Correct Approach |
|---|---|---|
| Reading **jku** from JWT and fetching JWKS from that URL | Key substitution, forged tokens, SSRF | Fetch JWKS only from trusted issuer/JWKS URIs |
| Using embedded **jwk** to verify the JWT itself | Self-signed tokens treated as issuer-issued | Bind keys to trusted issuers or dedicated PoP protocols |
| Fetching **x5u** and trusting the certificate without checks | Forged or unauthorized signing certificates | Verify chain, trust anchor, and identity/key binding per profile |
| Treating **x5c** as signing authorization | Embedded certificate supplied by token itself | Never auto-trust embedded certs; enforce trust policy |
| Trusting token-supplied **x5t#S256** | Fingerprint of an unauthorized key | Compare only against pre-configured trusted pins |
| Treating **kid** as a globally unique key source | `kid` collisions across issuers or attacker spoofing | Look up only inside a trusted issuer's key set |
| Checking only that **alg** is non-empty | Algorithm confusion or **none** | Enforce an issuer/API-agreed algorithm allowlist |
| Verifying signature while skipping **iss/aud** | Tokens for other APIs or issuers accepted mistakenly | Validate issuer, audience, timestamps, and token profile |
| Allowing open redirects when fetching `jku`/`x5u` | SSRF or switching to untrusted hosts | Never fetch URLs from tokens; if protocol requires, lock allowlists and redirects |
| Treating HTTPS as enough to trust `jku` | Attackers can also hold valid TLS certs | HTTPS and authorized issuer origin are two independent requirements |

### 13.1. What If a JOSE Header Still Contains `jku` or `x5u`?

Just because a token includes **jku** or **x5u** does not mean the server must access that URL. A Resource Server can process the token solely against its independent issuer/JWKS policy if supported by the implementation and profile, or **reject** unexpected headers under a strict policy.

The non-negotiable rule is **never letting those fields silently change the trust source**. In specialized JOSE protocols that genuinely require `jku`/`x5u`, build URL/certificate trust policies before using them.

### 13.2. Can `x5c` Be Trusted If Signed by a Public CA?

**Not automatically.** A certificate chain valid under a public CA may verify identity or constraints for that certificate's purpose, yet does not mean the private key holder is authorized to issue OAuth2 access tokens for a given issuer. You need explicit delegation to the issuer, key-usage/algorithm alignment, and token-profile checks.

### 13.3. What If the Issuer's JWKS Lacks the Matching `kid`?

This could be key rotation or a stale cache. The decoder may refresh the **configured trusted JWKS URL** per cache policy. If still no matching key exists, reject the token. Never fall back to the JWT's **jku** or an arbitrary host to "fix a 401."

### 13.4. What If a Token Is Signed by the Right Issuer but `aud` Targets Another API?

Reject it if the audience does not match the Resource Server. Having a trusted JWKS/key only enables signature verification; **audience validation** remains mandatory for accepting access tokens.

### 13.5. Is Accepting an Embedded Key Ever Valid?

Yes, when a protocol **explicitly defines** that key as input to a separate verification step and provides an **independent trust anchor** tying it to an authorized party. DPoP is one example. However, **an embedded `jwk` inside an access token** is never accepted by default as the issuer's signing key.

## 14. Observability and Error Handling Without Leaking Tokens

In production, separate failures by layer:

1. **Cannot locate issuer/JWKS:** check `issuer-uri`, metadata, `jwk-set-uri`, HTTPS/certificates, DNS/egress.
2. **No matching key:** check `kid`, `kty`, algorithm allowlist, JWKS cache, and rotation.
3. **Invalid signature:** tampered token, wrong key, wrong issuer, or unsupported algorithm.
4. **Invalid claims:** issuer, audience, `exp`/`nbf`, or token profile failed.
5. **Insufficient permissions:** valid token lacking scope, role, tenant, or ownership.

For standard Bearer Resource Servers:

| Scenario | Typical HTTP Status |
|---|---|
| Invalid JWT signature or no trusted key | **401 Unauthorized** |
| Wrong issuer/audience or expired JWT | **401 Unauthorized** |
| Authenticated JWT lacking authority or business permission | **403 Forbidden**, occasionally **404** under data-hiding policies |
| Valid JWT with sufficient permissions | API proceeds with business logic |

Never write raw JWTs into logs, exception messages, metric labels, or bug tickets. A leaked Bearer token can be replayed while still valid. Log request IDs, status codes, normalized failure reasons, and sanitized JWKS fetch telemetry instead.

### 14.1. Inspecting a Valid JWKS with `curl` Without Real Tokens

Once you know the **trusted JWKS URI** from configuration/metadata:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '.keys[] | {kid, kty, use, alg}'
~~~

This inspects only public key metadata and needs no user access token. Never swap the URL for an arbitrary **jku** taken from an unverified JWT.

To inspect discovery metadata:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/.well-known/openid-configuration \
  | jq '{issuer, jwks_uri}'
~~~

Issuer/provider paths are illustrative; look up real endpoints from your configured issuer and OIDC/RFC 8414 specs. Never run **curl -k**, disable certificate verification, or downgrade to HTTP to "work around" TLS errors.

## 15. Testing Paths That Risk Trusting the Wrong Key

Key test cases for your test environment:

| Scenario | Expected Outcome |
|---|---|
| Valid JWT signed with issuer's private key, valid **iss/aud/exp**, sufficient permissions | Authenticates and proceeds to authorization |
| JWT signed by untrusted key with **jku** pointing to sender's JWKS | **Rejected** |
| JWT signed by untrusted key with matching public **jwk** embedded in header | **Rejected** |
| JWT signed by untrusted key with **x5u** pointing to sender's cert | **Rejected** |
| JWT carrying sender's self-signed **x5c** certificate | **Rejected** |
| JWT carrying **kid** of a trusted key but invalid signature | **Rejected** |
| JWT declaring **alg = none** or disallowed algorithm | **Rejected** |
| Valid JWT signature, yet **aud** targets another resource | **Rejected** |
| Issuer rotates keys in trusted JWKS, two keys valid during overlap | JWT matching eligible key verifies per policy |
| Old key removed and JWT can no longer verify | **Rejected**, no fallback to JWT-supplied URL |
| JWKS endpoint temporarily unreachable and key is uncached | Cannot verify new token; never skips verification |

Authorization tests using mock JWTs in Spring Security Test **do not replace** real decoder/signature tests: a mock `Authentication` skips trust checks. For integration tests, use test-only issuers/JWKS and private keys, send test tokens through the real security chain, and assert rejections properly.

To test SSRF resistance, you do not need to hit real internal networks. Verify by design that no outbound request is made to JWT-supplied **jku/x5u** URLs, or use a mock HTTP server and assert no outbound requests leave the configured allowlist.

## 16. Design and Review Checklist

Before approving any JWT/JWS/JWK change, verify:

1. **What is the trust anchor?** Which Issuer URI, JWKS URI, or pinned keys are administratively configured?
2. **Where does the key selector fetch keys?** Strictly trusted sources, or header-supplied locations?
3. **Are `jku`/`x5u`/`jwk`/`x5c` processed?** If yes, which protocol requires them and how is trust established?
4. **Is there SSRF risk?** Which URLs can be fetched, and how are redirects, DNS, IPs, and egress constrained?
5. **Are algorithms and key types allowlisted?** Are algorithm confusion, `alg=none`, and key mismatches blocked?
6. **Are claims validated?** Issuer, audience, `exp`/`nbf`, token type/profile, and domain constraints?
7. **Does multi-tenancy enforce an issuer allowlist?** Is accepting arbitrary token-asserted issuers prevented?
8. **How is rotation managed?** Issuer JWKS, caching, overlapping keys, and emergency revocation?
9. **Where are business permissions enforced?** Scopes are only a first gate; are record ownership and tenants checked?
10. **Do tests cover attacker-supplied keys?** Including `jku`, `jwk`, `x5u`, `x5c`, and spoofed issuers?

Whenever you spot **readHeader("jku")**, **fetchJwks(urlFromToken)**, or **verifyWith(header.get("jwk"))** in code review, audit the trust policy immediately. That is one of the highest-risk spots in any JWT authentication layer.

## Conclusion

JOSE header fields **jku**, **x5u**, **jwk**, **x5c**, **kid**, and thumbprints can help **locate or describe keys**. They **never authorize a token to choose an API-trusted issuing authority**. A signature verified with a caller-supplied public key proves only that the caller holds the matching private key—it never proves the caller is a legitimate Authorization Server.

In **Spring Security OAuth 2.0/OIDC Resource Server**, the standard approach is configuring **issuer-uri**, resolving **jwks_uri** via trusted issuer discovery or configuring **jwk-set-uri** explicitly, restricting algorithms, and validating signature, issuer, audience, lifetime, and business permissions. Only accept embedded keys in specialized protocols that provide an independent trust anchor and full binding/verification logic.

### References

- [RFC 7515 — JSON Web Signature (JWS), JOSE Header Parameters](https://www.rfc-editor.org/rfc/rfc7515#section-4.1)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof-of-Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
