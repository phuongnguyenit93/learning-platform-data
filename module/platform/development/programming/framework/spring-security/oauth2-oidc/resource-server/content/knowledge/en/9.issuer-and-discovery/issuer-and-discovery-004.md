# How Discovery Finds `jwks_uri`

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, the API typically does not hold the secret key that the Authorization Server uses to sign JWTs. The API needs to know the corresponding **public key** to verify access token signatures. When configured with only an **issuer** address, how does the Resource Server obtain the key-set address?

The answer is **metadata discovery**: starting from a trusted **issuer URI**, Spring Security accesses a standard metadata endpoint, reads the **jwks_uri** field in the returned JSON, and uses that URL to fetch the **JWKS (JSON Web Key Set)** containing the public keys. Afterward, when a Bearer JWT arrives, the decoder selects the matching key, verifies the signature, and proceeds to validate claims.

The key point is that **discovery is not synonymous with JWT authentication**. Discovery only determines metadata and where to fetch keys; the Resource Server must still protect the metadata source, verify the signature, issuer, audience, expiration, and authorization policies.

## 1. Four Addresses or Artifacts Never to Confuse

Suppose an organization uses an OpenID Provider (OP)/Authorization Server with issuer:

~~~text
https://login.example.com/realms/shop
~~~

The components in the authentication chain:

| Component | Example | Role |
|---|---|---|
| **Issuer URI** | https://login.example.com/realms/shop | Publisher identifier; expected value matching the JWT's **iss** claim |
| **Metadata endpoint** | https://login.example.com/realms/shop/.well-known/openid-configuration | Returns JSON describing the issuer, endpoints, and where to fetch public keys |
| **jwks_uri** | https://login.example.com/realms/shop/protocol/openid-connect/certs | Value inside metadata pointing to the JWKS key set |
| **JWKS document** | JSON with a **keys** array fetched at jwks_uri | Contains public JWKs suitable for verifying asymmetrically signed tokens |

In another system, **jwks_uri** might be **https://keys.example.com/jwks.json** or a provider-specific path. There is no rule that it must always end in **/certs**, **/keys**, or **/.well-known/jwks.json**.

An illustration:

~~~mermaid
flowchart TD
    C[Resource Server configures issuer-uri] --> M[GET metadata endpoint over HTTPS]
    M --> J[Read issuer and jwks_uri in JSON]
    J --> K[GET jwks_uri over HTTPS]
    K --> S[JWKS JSON: keys array]
    S --> P[Select public JWK matching JWT kid and alg]
    P --> V[JwtDecoder verifies signature]
    V --> Q[Validate iss, aud, exp, nbf...]
    Q --> A[Check scope, role, and resource permissions]
~~~

**Issuer URI is not jwks_uri.** **Metadata JSON is not JWKS JSON.** **jwks_uri is a URL string**, not a list of keys.

## 2. Why Does Discovery Exist?

Without discovery, every Resource Server would have to know in advance:

- Which Authorization Server issues access tokens.
- Where the endpoint publishing public keys is located.
- Which algorithms/key types can be used.
- How to update configuration whenever the provider changes endpoint structure or rotates keys.

With discovery, the application configures a trusted issuer, and the Authorization Server publishes metadata under a uniform protocol. Spring Security can read the metadata to find **jwks_uri**, and then load public keys for JWT signatures.

However, discovery only helps **discover endpoints by contract**. It does not mean the API is allowed to trust whatever issuer a token sender declares, nor does it make JWTs from that issuer automatically authorized to read every resource.

### 2.1. Distinguishing Issuer Discovery and Metadata Discovery

In the OIDC specification, two concepts appear:

1. **Issuer discovery**: finding the issuer from a user identifier or external mechanism, such as WebFinger in certain OpenID Connect flows.
2. **Provider configuration discovery**: when the **issuer is already known**, locating the issuer's metadata document at a standard URL.

For a typical Spring Security Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
~~~

The application **already knows the issuer** from configuration. Spring Security performs **metadata discovery** to fetch keys; it does not need to accept a user's email address and call WebFinger before every request.

## 3. Which Metadata URLs Can Be Tried from an Issuer?

Two crucial specifications are:

- **OpenID Connect Discovery 1.0** for OpenID Provider metadata.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata** for Authorization Server metadata in general.

The same issuer can appear with **different .well-known locations** due to path construction rules in each specification.

Suppose the issuer has a path component:

~~~text
https://login.example.com/realms/shop
~~~

The corresponding URLs documented as supported by Spring Security JWT Resource Server include:

| Metadata type | Example URL | How it is constructed |
|---|---|---|
| **OIDC Provider Configuration** | https://login.example.com/realms/shop/.well-known/openid-configuration | Append **/.well-known/openid-configuration** to the end of the issuer |
| **OAuth metadata using openid-configuration suffix** | https://login.example.com/.well-known/openid-configuration/realms/shop | Insert **/.well-known/openid-configuration** between host and issuer path |
| **RFC 8414 OAuth Authorization Server Metadata** | https://login.example.com/.well-known/oauth-authorization-server/realms/shop | Insert **/.well-known/oauth-authorization-server** between host and issuer path |

If the issuer **has no path**, such as **https://login.example.com**, the first two OpenID patterns above usually both resolve to:

~~~text
https://login.example.com/.well-known/openid-configuration
~~~

The difference stands out most when the issuer has a path like **/realms/shop**. You cannot take a rule of thumb like “append .well-known to the host” and assume every provider and framework uses the same path.

### 3.1. OIDC Discovery Rule

According to **OpenID Connect Discovery 1.0**, provider configuration is located at:

~~~text
{issuer-without-trailing-slash}/.well-known/openid-configuration
~~~

For example:

~~~text
Issuer:
https://id.example.org/tenant-a

OIDC discovery:
https://id.example.org/tenant-a/.well-known/openid-configuration
~~~

When the issuer contains a path, OIDC appends **/.well-known/openid-configuration** after the issuer path. The OIDC specification requires metadata to be returned as JSON and include required values such as **issuer** and **jwks_uri**.

### 3.2. RFC 8414 Rule

RFC 8414 defines the OAuth metadata path by **inserting** the well-known segment between the host and the issuer path.

~~~text
Issuer:
https://id.example.org/tenant-a

OAuth metadata:
https://id.example.org/.well-known/oauth-authorization-server/tenant-a
~~~

RFC 8414 also permits OAuth applications to use other registered well-known suffixes, including **openid-configuration**; when using RFC 8414 insertion rules, the URL is:

~~~text
https://id.example.org/.well-known/openid-configuration/tenant-a
~~~

**Do not assemble URIs arbitrarily using string replacement in application code if the framework already supports discovery.** For URLs with hosts, ports, paths, and complex escaping, let a standard-compliant library handle it. The URLs in the table explain how endpoints are formed, not a command to call all endpoints manually.

### 3.3. How Does Spring Security Choose an Endpoint?

Spring Security Servlet JWT Resource Server documentation states that when configuring **issuer-uri**, the Authorization Server must support at least one of the corresponding metadata endpoint forms above.

Spring Security has a predefined discovery mechanism to find compatible metadata. **Do not assume every version probes all URLs in the exact same order or always falls back on every kind of error**: TLS errors, JSON errors, issuer mismatch, or invalid responses may fail immediately rather than trying the next endpoint. If a provider has specific quirks, verify the behavior of the exact Spring Security version in use.

Do not construct a JWKS URL yourself by guessing from the issuer's domain name. The **metadata endpoint** is what publishes the **jwks_uri** path.

## 4. How Does Spring Security Read Metadata JSON?

With the example issuer:

~~~text
https://login.example.com/realms/shop
~~~

The Resource Server may access the OIDC endpoint like this:

~~~http
GET /realms/shop/.well-known/openid-configuration HTTP/1.1
Host: login.example.com
Accept: application/json
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
~~~

This JSON is **abbreviated for illustration**, not a complete OIDC metadata document satisfying every required field of an OP.

Analyzing the fields:

| Field | Meaning for the Resource Server |
|---|---|
| **issuer** | Must match exactly the issuer configured as trusted |
| **jwks_uri** | HTTPS address to fetch the public key set |
| **authorization_endpoint** | OAuth/OIDC authorization endpoint, usually serving OAuth Clients |
| **token_endpoint** | Endpoint issuing access tokens to clients, not JWKS |
| **id_token_signing_alg_values_supported** | Algorithms advertised by the OP for signing **ID Tokens**; does not dictate all access token algorithms the API must trust |

**The standard field name is jwks_uri, not jwks_url.** Some prose explanations in docs or blog posts use **jwks_url** informally, but the metadata JSON field name in **OIDC Discovery** and **RFC 8414** is **jwks_uri**. When generating standard metadata responses, use the exact field name.

### 4.1. Is `jwks_uri` Always Required?

There is a difference between the two specifications:

- **OIDC Provider Metadata:** **jwks_uri** is **REQUIRED** in OIDC Discovery; the URL uses HTTPS and the public JWKS must not contain private/symmetric keys.
- **RFC 8414 OAuth Authorization Server Metadata:** **jwks_uri** is defined as **OPTIONAL** in the general OAuth metadata standard.

However, a **Resource Server that verifies JWTs with public keys via JWKS** must have sufficient key-retrieval information: metadata containing a usable **jwks_uri** or a trusted URL/key configured by another method. A valid RFC 8414 document that does not publish `jwks_uri` will not suffice to set up JWKS-based JWT verification from discovery alone.

**Do not use authorization_endpoint or token_endpoint to guess JWKS.** Those are endpoints with distinct roles.

### 4.2. Checking the Issuer Right in Metadata

According to OIDC Discovery and RFC 8414, the **issuer** field in metadata must correspond exactly to the issuer used to construct the metadata URL.

For example:

~~~text
Configured issuer-uri:  https://login.example.com/realms/shop
Metadata issuer:        https://login.example.com/realms/other
~~~

This case is an **issuer mismatch**. Do not use `jwks_uri` from a mismatched-issuer response as a trusted key source.

Watch out for differences in:

- Hostname or port.
- Scheme **https** versus **http**.
- Path or tenant/realm.
- Trailing slash on the path if issuer/provider returns a different one.
- String encoding or normalization variants that the protocol does not permit changing automatically.

Do not silently strip slashes, swap hosts, or tweak the issuer in JWTs to make them “match” without checking the OP's contract. The issuer is a security identifier, not merely a convenient URL to connect to.

## 5. Next Step: What Does `jwks_uri` Return?

After reading metadata and obtaining **jwks_uri**, the Resource Server fetches the JWKS:

~~~http
GET /realms/shop/protocol/openid-connect/certs HTTP/1.1
Host: login.example.com
Accept: application/json
~~~

Example body:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-key-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-base64url-old>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "shop-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-base64url-new>",
      "e": "AQAB"
    }
  ]
}
~~~

The **n** values in angle brackets in the example are illustrative placeholders only; a real JWKS must contain valid JWK modulus values.

Fields to understand:

- **keys**: array of JWKs in the JWKS document.
- **kty = RSA**: RSA key type.
- **kid**: key identifier, used to select the right signing key when multiple public keys exist.
- **use = sig**: key intended for signature/verification.
- **alg = RS256**: expected algorithm used with the key; does not replace the list of algorithms allowed by the API.
- **n/e**: RSA public key components, encoded as Base64URLUInt.

**Never place private keys, RSA d/p/q, or symmetric secret k into a public JWKS.** Public keys allow recipients to check signatures, while private keys belong strictly on the issuer side or in a controlled key management system.

### 5.1. Finding a Key with `kid`

Suppose the JOSE header of an access token contains:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "shop-key-2026-11"
}
~~~

After establishing a trusted issuer and JWKS source, the decoder uses **kid** to find the key with the matching name, while verifying compatibility of key type, algorithm, and key use.

**kid only helps locate the key.** An attacker can also craft a JOSE header with that `kid`, but cannot produce a valid signature without the private key. Therefore, verifying the signature after selecting the key is the decisive cryptographic step.

A JWKS can hold multiple keys to support rotation; not every key must be tried unconditionally for every JWT.

## 6. Processing Chain from Issuer to Accepting a JWT

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server / OP
    participant API as Spring Resource Server
    participant C as OAuth Client

    Note over API: Trusted issuer-uri configured
    API->>AS: GET .well-known metadata over HTTPS
    AS-->>API: 200 JSON with issuer and jwks_uri
    API->>API: Validate metadata, extract jwks_uri
    API->>AS: GET jwks_uri over HTTPS
    AS-->>API: JWKS JSON containing public keys
    API->>API: Cache appropriate public keys
    AS-->>C: Issue signed JWT access token
    C->>API: Authorization: Bearer JWT
    API->>API: Select JWK by kid, verify signature
    API->>API: Check iss, aud, exp, nbf, and permissions
    API-->>C: 200 if eligible or reject
~~~

The diagram illustrates **logical relationships**. In real deployments, metadata discovery may run during decoder initialization or **be deferred until the first JWT request**, and JWKS can be loaded/cached on demand. Exact network ordering depends on the Spring Security version and how `JwtDecoder` is created.

What remains invariant is: **trusted configured issuer → metadata contains jwks_uri → JWKS contains public key → JwtDecoder verifies JWT → validate claims and permissions**.

### 6.1. Discovery Does Not Run on Every Request

In a typical deployment:

1. Metadata is downloaded when the decoder needs to determine the key source, not necessarily re-downloaded on every HTTP request.
2. Public keys in the JWKS are cached for a period of time.
3. JwtDecoder uses the cache to verify many JWTs.
4. When the issuer rotates keys, the library can refresh the JWKS according to cache/miss policy.
5. When the JWKS endpoint errors, the decoder may use cached keys depending on library behavior; tokens needing an uncached key will not be accepted.

Do not claim that **every token requires two network requests**. Likewise, do not claim metadata/JWKS endpoints can stay disconnected indefinitely without affecting verification, because caches and key rotation have limits.

### 6.2. Does Discovery Happen at Startup or on the First Request?

Spring Security 6.5/7.1 JWT Resource Server documentation describes discovery being **deferred until the first request carrying a JWT** in the corresponding auto-configuration; for Servlet, this deferral can be managed by **SupplierJwtDecoder**. This reduces the Resource Server's startup dependency on the Authorization Server's network availability.

However, **manually calling** issuer discovery methods during `JwtDecoder` bean initialization or building a decoder via another API can trigger early network access. Custom bean wiring can also alter deferral behavior. Therefore:

- Do not rely on assuming every Boot/Security version contacts the issuer at startup.
- Do not rely on assuming every custom JwtDecoder defers discovery.
- When startup must not depend on the issuer, use the appropriate configuration or **direct jwk-set-uri**, and test behavior on your actual version.

**Deferring discovery does not let the system validate tokens while issuer/JWKS are unavailable.** If no trusted key is available when verification is needed, JWT authentication must fail as configured—never skip signature verification.

## 7. Spring Boot: Specifying `issuer-uri` to Auto-Find `jwks_uri`

With Spring Boot and Spring Security Resource Server, a common configuration is:

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

**issuer-uri** serves two important purposes:

- Identifies the trusted issuer for metadata/JWKS discovery.
- Configures validation of the JWT's **iss** claim per the Resource Server configuration.

**audiences** ensures the JWT's **aud** claim contains **orders-api**, because tokens signed by the right issuer could still have been issued for another API. Spring Security cannot infer the business audience from `jwks_uri` alone.

Dependencies for OAuth2 Resource Server and JOSE JWT are required. With Spring Boot 3.x, typically use **spring-boot-starter-oauth2-resource-server**; with Boot 4.x, use **spring-boot-starter-security-oauth2-resource-server**. Let Spring Boot manage the corresponding Security versions.

### 7.1. Servlet SecurityFilterChain Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

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

When the API receives a JWT, the Resource Server uses the JwtDecoder configured from issuer/JWKS and maps validated scopes to authorities like **SCOPE_orders.read**.

**Discovery does not grant permissions.** A token with a valid signature, right iss/aud, and valid lifetime still cannot read business data if it lacks scope or is denied by tenant/ownership policies.

### 7.2. Do Not Confuse JWT Access Tokens and OIDC ID Tokens

An OpenID Provider can sign **ID Tokens** and **access tokens** with the same key set. Being able to fetch JWKS and verify signatures **does not prove** an ID Token can be used to call an API.

The Resource Server must accept **access tokens with the right audience and token profile**, not unconditionally accept any JWT signed by the issuer.

## 8. Specifying `jwk-set-uri` Directly When Not Using Discovery

Some Authorization Servers:

- Do not publish compatible OIDC/OAuth metadata endpoints.
- Publish metadata missing the `jwks_uri` needed by the API.
- Host metadata at a non-contract URL that the framework cannot automatically locate.
- Require the Resource Server to know the key endpoint directly in config to control initialization timing.

Once administrators provide a **trusted JWKS URI**, you can declare:

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

In this configuration:

- **jwk-set-uri** explicitly states where to fetch public keys, so Spring Security does not need discovery metadata to locate the endpoint.
- **issuer-uri** still defines the issuer and enables **iss** validation.
- **audiences** is still needed if the API requires **aud** validation.
- JWT signatures and lifetimes must still be checked.

This approach fits when you want to avoid a metadata discovery step or when the provider uses non-standard endpoints, **provided the JWKS source is trusted and configured accurately**.

An easy mistake:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

If only **jwk-set-uri** is configured without corresponding issuer checks, the API risks verifying tokens only against the key set without an **iss** policy. To use this style safely, you must manually attach the required validators for issuer, audience, and token profile. For typical setups, keep **issuer-uri** and **audiences**.

### 8.1. Supplying JWKS URI in the DSL or a Custom JwtDecoder

Spring Security allows specifying a JWK Set URI directly via Resource Server config or building a custom decoder. Java example:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(
            "https://login.example.com/realms/shop/protocol/openid-connect/certs")
        .build();

    decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(
        "https://login.example.com/realms/shop"));

    return decoder;
}
~~~

This snippet **illustrates only how to select the JWK source and issuer validator**. If creating a custom JwtDecoder, you must add an **audience validator** and token-type/profile rules according to API policy. When providing a custom **@Bean JwtDecoder**, Boot's auto-configuration may back off; do not assume properties like **audiences** automatically attach to a custom decoder.

Additionally, configure allowed verification algorithms, HTTP/TLS client settings, and timeouts/caching when customizing deeply. Never drop default validators when replacing the decoder.

## 9. Verifying Discovery with curl and jq

In an authorized environment, operators can inspect **metadata** without putting real access tokens into commands.

Suppose the issuer is:

~~~text
https://login.example.com/realms/shop
~~~

### 9.1. Step 1: Fetch OpenID Provider Configuration

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

If **jq** is available, display only the two key fields:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/.well-known/openid-configuration \
  | jq '{issuer, jwks_uri}'
~~~

Expected result (illustrative):

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Check that:

1. The response returns valid JSON over HTTPS.
2. **issuer** matches the `issuer-uri` configured by the application exactly.
3. **jwks_uri** is present and is an HTTPS URL used to fetch keys.
4. The endpoint matches the provider and environment (dev/staging/prod).

If the OIDC URL returns 404, do not jump to concluding the provider does not support discovery. When the issuer has a path, also check the **RFC 8414** locations supported by your Spring Security version and consult the provider's docs.

### 9.2. Step 2: Fetch JWKS from `jwks_uri`

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

If you only want to inspect key structure:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '.keys[] | {kid, kty, use, alg}'
~~~

Illustrative result:

~~~json
{
  "kid": "shop-key-2026-11",
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256"
}
~~~

Here **jwks_uri** was obtained from valid metadata before calling it. Never write a client that automatically downloads JWKS from a URL advertised by an unverified Bearer token.

### 9.3. Checking with PowerShell

On Windows PowerShell:

~~~powershell
$issuer = 'https://login.example.com/realms/shop'
$metadataUrl = "$issuer/.well-known/openid-configuration"

$metadata = Invoke-RestMethod -Uri $metadataUrl -Method Get
$metadata.issuer
$metadata.jwks_uri

$jwks = Invoke-RestMethod -Uri $metadata.jwks_uri -Method Get
$jwks.keys | Select-Object kid, kty, use, alg
~~~

This example only illustrates fetching metadata/JWKS from a **known preconfigured issuer**. For production systems, enforce certificate checks, URL trust policies, redirects, and HTTP error handling in the client. Never use flags that disable TLS verification just to “make discovery work”.

## 10. Common Errors When Spring Security Cannot Find `jwks_uri`

### 10.1. Wrong `issuer-uri` or Wrong Trailing Slash

For example:

~~~text
Configured issuer:
https://login.example.com/realms/shop/

Issuer in metadata:
https://login.example.com/realms/shop
~~~

Trailing slash differences can lead to malformed constructed URLs or mismatches during issuer comparison. Take the **canonical issuer** published by the provider and use it consistently across config, metadata, and the JWT's **iss** claim.

Never strip or add slashes to issued token data just to avoid errors.

### 10.2. Metadata Endpoint Returns 404

Possible causes:

- The provider does not support the corresponding endpoint.
- The issuer has a path, but the URL was probed using a different OIDC/RFC 8414 rule.
- Reverse proxy routing does not expose the **.well-known** path properly.
- The Authorization Server is deployed under a different context path than the external issuer.
- A gateway layer blocks the metadata endpoint.

How to handle: verify the actual issuer, test standard metadata URLs supported by Spring Security documentation, confirm metadata for the right tenant/realm, and adjust the proxy/provider. If the provider truly lacks compatible discovery, configure a trusted **jwk-set-uri** directly.

### 10.3. Metadata Has `jwks_url` Instead of `jwks_uri`

JSON like the following does not use the standard field name:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_url": "https://login.example.com/keys"
}
~~~

Under OIDC Discovery/RFC 8414, the standard metadata field must be **jwks_uri**. If a provider returns a proprietary name like **jwks_url**, fix the provider or use a controlled explicit configuration; do not assume Spring Security will recognize that custom field automatically.

### 10.4. Metadata Issuer Does Not Match Configured Issuer

~~~json
{
  "issuer": "https://login.example.com/realms/other",
  "jwks_uri": "https://login.example.com/realms/other/certs"
}
~~~

If the API is configured to trust **/realms/shop**, do not accept responses for **/realms/other**. Check the URL being called, proxy rewrites, realm/tenant, and provider info. An issuer mismatch is a **security issue**, not merely a formatting error.

### 10.5. TLS or Trust Store Errors

Logs may contain messages such as:

~~~text
PKIX path building failed
SSLHandshakeException
certificate verify failed
~~~

Common causes are an internal CA not yet trusted in the JVM trust store, hostname not matching SAN, or expired certificates.

Fix: configure the proper certificate chain, update the trusted trust store, and verify hostnames. Never use **trust-all certificates**, **curl -k**, or disable SSL verification in production. The fact that metadata/JWKS only hold public keys **does not make TLS verification unnecessary**.

### 10.6. Unreachable from Inside a Container

A developer's laptop may call metadata successfully, while a container in Kubernetes lacks DNS, egress proxy, or proper routing.

Check from the **Resource Server's actual environment**:

- DNS resolution of the issuer hostname.
- Outbound network policy, egress gateway, proxy.
- JVM TLS handshake/trust store.
- Timeouts or redirects.
- Whether the metadata/JWKS endpoint is exposed and returning valid JSON.

Do not confuse public hostnames/URLs with internal addresses that have a different issuer; the token's **iss** must still match the issued issuer.

### 10.7. `jwks_uri` Exists, but JWKS Is Empty or Lacks a Matching Key

For example, the JWT has **kid = key-b**, while the JWKS cache only holds **key-a**. This is no longer a metadata lookup failure; it is a **key selection or loading failure**. Check rotation, JWKS caching, algorithm/kty, and when the new key was published.

### 10.8. Metadata Works, Yet JWTs Always Return 401

Successful discovery only proves the API found the key source. Tokens can still be rejected because:

- Signature does not match the JWK.
- **kid** is missing or no matching key is found.
- **alg** is not permitted by the API.
- JWT's **iss** differs from the trusted issuer.
- **aud** does not contain the Resource Server's audience.
- **exp** is expired or **nbf** is not yet active.
- Token is an OIDC **ID Token** instead of an access token with the right profile.
- Custom JwtDecoder configuration is missing validators or uses the wrong token type.

Pinpoint the exact failing step and fix the policy/configuration. Never drop signature/issuer/audience validation to turn 401 into 200.

## 11. Security Considerations When Using Discovery

### 11.1. Never Let the JWT Pick the Issuer or `jwks_uri`

An unverified token might contain:

~~~json
{
  "iss": "https://attacker.example",
  "sub": "admin",
  "scope": "orders.write"
}
~~~

If the API reads this **iss** and automatically discovers metadata from any hostname, an attacker can publish a JWKS holding their own public key, self-sign a JWT, and trick the API into trusting the forged token.

The right approach is:

1. The Resource Server has a **trusted configured issuer-uri** or an allowlist of permitted issuers.
2. Use **only that permitted issuer** to discover metadata.
3. Validate metadata issuer against the contract.
4. Use only **jwks_uri** originating from a trusted source.
5. Verify signature and claims before granting permissions.

In multi-issuer/multi-tenant systems, use a resolver designed with a tenant/issuer allowlist; never turn an arbitrary **iss** claim into an uncontrolled key-fetching endpoint.

### 11.2. Prevent SSRF via Discovery Endpoints

Metadata/JWKS URLs are network targets fetched by the Resource Server. If callers or JWTs can arbitrarily dictate URLs, they can force the server to send requests to internal addresses, cloud metadata services, or unrelated systems.

Mitigations include:

- Allow only registered trusted issuers.
- Use HTTPS only and verify hostnames/certificates.
- Govern egress/DNS, redirects, and allowed hosts per your threat model.
- Never use **jku**, **jwk**, or **x5u** from an unverified JWT to load arbitrary keys.
- Never expose a debug endpoint accepting a URL where the server fetches metadata/JWKS without restrictions.

**JWKS can be hosted on a different domain from the issuer** if the provider system is architected that way; strict same-origin is not mandatory. However, trusting that external URL must derive from trusted metadata/issuer plus governed network/TLS policies.

### 11.3. JWKS Is Public, but Transport Integrity Still Matters

Anyone can download public keys; that is the proper design for asymmetric signatures. Yet if an attacker **replaces the JWKS** with their own public keys over an unauthenticated channel, they can subvert the API's signature-checking foundation.

Therefore:

- Metadata endpoints and `jwks_uri` must use HTTPS.
- Clients must verify certificate chains and hostnames.
- Never allow reverse proxies to rewrite metadata issuer/`jwks_uri` to an unintended environment.
- Public JWKS contains only public signing keys; never private signing keys or HMAC secrets.
- Administrative permissions over issuer/JWKS and DNS/routing changes must be protected.

### 11.4. Validate Algorithm and Key Use

A JWKS can contain multiple key types. The Resource Server must select keys matching **kid**, **kty**, permitted **alg**, and **sig/verify** key use if declared.

JWT signatures must only be verified with algorithms trusted by the application (for instance, RS256 per contract). Never let a token switch itself from RS256 to HS256 or **alg = none** to bypass verification.

### 11.5. CORS and Metadata Publishing Permissions

Metadata and JWKS are normally published publicly so clients can discover endpoints and public keys; no user access token needs to be attached to JWKS requests. However, publishing metadata publicly does not mean exposing token endpoint secrets or private keys.

CORS is a browser policy; a Resource Server running server-to-server does not need CORS to call JWKS, and enabling CORS does not replace TLS. Never send a user's Bearer token to metadata/JWKS endpoints just to read public keys.

## 12. JWKS Rotation After Discovery

A major benefit of JWKS is the ability to rotate signing keys without redeploying every Resource Server.

Suppose:

| Phase | Key used by issuer to sign JWT | Published JWKS | Desired outcome |
|---|---|---|---|
| **T0** | key A | Public key A | JWTs signed with A are verified |
| **T1** | Still signing with A | Public keys A and B | Resource Server can receive B ahead of time |
| **T2** | Start signing with B | Public keys A and B | Old JWTs (A) and new JWTs (B) are both verified |
| **T3** | Signing only with B; A tokens expired | Public key B | A can be removed after the transition window |

**Discovery of the JWKS URI** normally does not need to change during rotation; only the JWKS contents at that URI update. JwtDecoder can refresh its key cache per deployment policy.

Points to coordinate:

- **Publish-before-use:** publish public key B before signing access tokens with private key B.
- **Overlap:** keep key A while tokens signed by A remain valid, except in emergency revocation due to key compromise.
- **Cache:** account for TTLs and cache refresh across the Resource Server and proxies/CDNs.
- **kid:** never carelessly reuse the same `kid` for different key material while caches are active.
- **Failure policy:** if a verification key is missing, reject the token rather than accepting unsigned tokens.

When a private signing key is compromised, emergency rotation may cause some legitimate tokens to be rejected; that is a deliberate security trade-off requiring an incident response process, not a “discovery bug”.

## 13. Comparing Three Common Configurations

| Configuration | Metadata discovery? | Automatic `iss` check? | When to use? |
|---|---|---|---|
| Only **issuer-uri** | Yes, per Spring Security and supported endpoints | Yes, under standard configuration | Provider supports OIDC/OAuth metadata |
| **issuer-uri + jwk-set-uri** | No discovery needed to find JWKS URL | Yes, under standard configuration | JWKS endpoint is known and you want to reduce metadata discovery dependency |
| Only **jwk-set-uri** | No | Do not assume it is present unless an issuer validator is set | Use only with explicitly configured issuer/audience/token profile validators |

In all three cases, validate **audience**, lifetime, algorithm, token type, and business permissions per API policy. **Configuring `jwk-set-uri` directly does not mean skipping signature verification.**

### 13.1. What Cannot Be Inferred from Discovery

Discovery **does not** establish that:

- The current Bearer token is definitely valid.
- JWTs from the issuer can be used across any arbitrary API.
- Scopes **openid/profile/email** are business permissions.
- The access token has been granted **orders.read**.
- The user owns a specific order record.
- The Resource Server will immediately know when a user's permissions are revoked.
- Proxy, TLS, DNS, and cache settings are all secure.

Discovery is only the step that establishes the **key-source trust configuration**. Authentication and authorization decisions must still be enforced independently.

## 14. Reading Errors in the Right Order

When the API fails to authenticate a JWT, pinpoint which layer is failing:

~~~mermaid
flowchart TD
    A[Resource Server receives Bearer JWT] --> B{Valid issuer-uri configured?}
    B -->|No| C[Fix configured issuer]
    B -->|Yes| D{Metadata endpoint reachable?}
    D -->|No| E[Check well-known URL, proxy, DNS, and TLS]
    D -->|Yes| F{Metadata issuer matches and has jwks_uri?}
    F -->|No| G[Fix provider metadata or configure JWKS directly]
    F -->|Yes| H{JWKS loaded and matching key selected?}
    H -->|No| I[Check jwks_uri, cache, kid, alg, and rotation]
    H -->|Yes| J{Signature and JWT claims valid?}
    J -->|No| K[Check signature, iss, aud, exp, nbf, typ]
    J -->|Yes| L{Sufficient endpoint/resource permissions?}
    L -->|No| M[Check scope, role, owner, tenant]
    L -->|Yes| N[Allow business processing]
~~~

Specific scenarios:

**Scenario A: metadata 200, JWKS 200, JWT 401.** Discovery likely succeeded. Check token signature, kid, issuer, audience, expiration, and type. Stop changing **.well-known** paths if the API has already fetched the JWKS.

**Scenario B: right issuer URI but metadata 404.** Check all three compatible well-known locations, especially when the issuer has a path; inspect proxy rewrites and provider docs.

**Scenario C: metadata JSON has `jwks_uri` but invalid certificate.** Fix the trust chain, hostname, and certificate on the JWKS host; never disable TLS verification.

**Scenario D: new tokens fail after rotation.** Check kid and JWKS cache; confirm the new public key was published before the new private key began signing JWTs.

**Scenario E: valid token but 403.** Discovery and signature are likely completely fine. Check business authorization policies and scope mappings rather than tinkering with keys.

## 15. Reasoning Exercise

Given trusted issuer:

~~~text
https://auth.example.org/teams/finance
~~~

And metadata:

~~~json
{
  "issuer": "https://auth.example.org/teams/finance",
  "jwks_uri": "https://keys.example.org/finance/public-jwks.json"
}
~~~

A JWT arriving at the Orders API has:

~~~json
{
  "iss": "https://auth.example.org/teams/finance",
  "aud": ["payments-api"],
  "scope": "payments.read"
}
~~~

Determine:

1. What is the **OIDC discovery URL**?
2. What is the **RFC 8414 OAuth discovery URL**?
3. Is it allowed to fetch JWKS from hostname **keys.example.org**?
4. After the JWT verifies with the right public key, should the Orders API accept the token above?

**Analysis:**

- OIDC discovery: **https://auth.example.org/teams/finance/.well-known/openid-configuration**.
- RFC 8414 OAuth: **https://auth.example.org/.well-known/oauth-authorization-server/teams/finance**.
- **jwks_uri** may use a different host from the issuer if it originates from metadata validated against the trusted issuer, uses HTTPS with a valid certificate, and is permitted by egress/allowlist policy. Do not default to “every external host is trusted”.
- **The Orders API must reject it** if it requires audience **orders-api**. The token above has audience **payments-api**, even though its signature is valid and its issuer matches; using the right key does not replace audience validation.

This exercise cleanly separates **finding keys** from **verifying which Resource Server a token is intended for**.

## 16. Questions to Answer Before Putting a Resource Server into Production

1. **Which issuer is the trust anchor?** Are scheme/host/port/path right and aligned with the `iss` claim?
2. **Which metadata endpoint is supported?** OIDC discovery, RFC 8414, or does the provider require specifying the JWKS URI directly?
3. **What fields does metadata return?** Does it contain a matching **issuer** and standard **jwks_uri**?
4. **Is the JWKS secure?** Does it contain only public keys, over verified HTTPS, with no exposed private/symmetric secrets?
5. **Which verification algorithms are permitted?** Does the decoder properly check `kid`/`kty`/`use` and restrict `alg`?
6. **Are all required claims checked?** Are issuer, audience, timestamps, and access-token type/profile clearly defined?
7. **How do initialization and caching behave?** When does discovery run, and how are timeouts/rotation/JWKS outages handled?
8. **Does multi-tenancy constrain issuers?** Is there an allowlist or safe resolver, avoiding trusting token-proposed issuers?
9. **Where is authorization enforced?** Are scopes/roles and tenant/owner permissions checked in web/method/domain policies?
10. **How are incidents observed?** Are request IDs, network errors, and validator failures logged safely without logging real access tokens?

## Conclusion

Spring Security finds **jwks_uri** by starting from a **trusted configured issuer-uri**, accessing standard OpenID Connect or OAuth 2.0 metadata, reading **issuer** and **jwks_uri**, and then fetching the JWKS from the published address. OIDC and RFC 8414 construct **.well-known URLs** differently when the issuer contains a path, so you must understand the specification and endpoints your provider supports.

**jwks_uri is not a token, not an issuer, and not a permission.** It is the address of the public key set used for signature verification. After discovery, JwtDecoder must still verify signatures with trusted keys/algorithms, check **iss**, **aud**, lifetimes, and token profile, and only then does the Resource Server evaluate business permissions. If discovery cannot be used, **jwk-set-uri** can be specified directly while preserving equivalent trust constraints.

### References

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Boot — OAuth2 Resource Server Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [OpenID Connect Discovery 1.0, Section 3–4](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
