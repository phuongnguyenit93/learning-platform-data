# Fetching JWKS over HTTPS and Enforcing Approved Sources

When a **Spring Security OAuth 2.0 Resource Server** receives a JWT Bearer Access Token, it needs a key to verify the token's signature. For asymmetric signing algorithms like RS256 or ES256, the Authorization Server holds the **private key** to sign, while the Resource Server fetches the **public key** from a **JSON Web Key Set (JWKS)**. The JWKS is typically published at an HTTPS endpoint.

Merely using a URL starting with `https://` is **not enough** to trust a JWKS. The system must also determine **whether it is an approved key source for the right issuer**, verify the TLS connection, restrict where the HTTP client is allowed to reach, and never let an unverified request or token dictate the key-loading address.

This lesson explains how to **fetch JWKS over HTTPS**, establish trust boundaries for **JWKS endpoints**, configure **Spring Boot + NimbusJwtDecoder**, mitigate key-source substitution/SSRF risks, and operate caching alongside the key lifecycle. Examples use **Spring Boot 3.x, Spring Security 6.x, Java 17+** in a Servlet API receiving JWT Access Tokens issued by an Authorization Server.

## 1. What Is a JWKS and Why Must the Resource Server Fetch It?

**JWK (JSON Web Key)** is a JSON structure representing a key. A **JWK Set** contains an array of JWKs under the `keys` property. An Authorization Server can publish public keys so Resource Servers can verify JWS signatures without holding the private signing key.

Illustrative JSON example of a JWK Set:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_A_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-2026-b",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_B_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

The `n` values are placeholders, not real keys usable for verifying tokens. Field meanings:

| Field | Meaning | Usage in Resource Server |
| --- | --- | --- |
| `keys` | Array of JWKs. | May contain multiple public keys to support key rotation. |
| `kty` | Key type, e.g., `RSA` or `EC`. | Must be compatible with the accepted JWS algorithm. |
| `kid` | Key identifier. | Helps locate a matching key; **not proof of a trusted key source**. |
| `use` | Intended use, e.g., `sig`. | Clarifies that the key is used for signature verification. |
| `alg` | Intended algorithm, e.g., `RS256`. | The decoder must enforce the **trusted configured** algorithm, not blindly trust any published algorithm. |
| `n`, `e` | Public RSA key parameters. | Used to verify RSA signatures. |

When a JWKS is published publicly for asymmetric signing, it **should contain only public key information**. Private parameters such as `d` must never appear in a public JWK Set. Private keys remain securely managed by the issuer.

### 1.1. How Does a JWT Reference a Key?

A JWT in JWS compact form typically has the structure:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
~~~

The JOSE header may look like:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-2026-b",
  "typ": "at+jwt"
}
~~~

The Resource Server reads `kid` to select a key within **the JWKS it already trusts**, then uses that public key to verify the signature. This is completely different from trusting a new URL supplied by the token itself. A token sender can write arbitrary `kid`, `alg`, or optional headers; **trust lies in the configured key source and the verification outcome**, not in strings inside the header.

### 1.2. Three Commonly Confused Concepts

| Concept | Question It Answers |
| --- | --- |
| **HTTPS/TLS** | Am I communicating with an endpoint matching the hostname over a protected channel? |
| **Trusted JWKS source** | Is the endpoint I am connecting to actually **authorized by the system to provide keys** for this issuer? |
| **JWT validation** | Was the token signed with a trusted key, and do claims such as `iss`, `aud`, `exp`, and `nbf` satisfy the API's requirements? |

These three layers complement one another. Having a valid HTTPS certificate alone does not prove a JWKS belongs to an issuer the API trusts. Having a valid signature alone does not prove the JWT is meant for the current API. Having the right scope does not replace validating the issuing source.

## 2. Trust Model: From Issuer to JWKS and JWT

Suppose `orders-api` accepts tokens from an Authorization Server:

~~~text
Trusted Issuer:
  https://login.example.test/realms/demo

Approved JWKS URI:
  https://login.example.test/realms/demo/protocol/openid-connect/certs

API Audience:
  orders-api
~~~

Intended processing chain:

~~~text
              Resource Server Trust Configuration
              -----------------------------------
              issuer = https://login.example.test/realms/demo
              jwks   = https://login.example.test/.../certs
              aud    = orders-api
              alg    = RS256
                              |
                              v
                        HTTPS/TLS connection
                              |
                              v
                   Approved JWKS endpoint
                              |
                  returns public keys / JWK Set
                              |
                              v
Client -- Bearer JWT --> NimbusJwtDecoder
                              |
                    Select matching public key
                    Verify JWS signature
                    Validate iss, aud, exp, nbf
                              |
                              v
                    JwtAuthenticationToken
                              |
                    Check scope/authority
                    Check resource permissions
                              |
                       Allow / deny
~~~

**Issuer** and **JWKS URI** do not have to share the same hostname or path. An organization may host its Authorization Server on a public hostname and distribute the JWKS through a managed internal endpoint. However, the **issuer → approved key source** relationship must be established through trusted configuration, never inferred from an unverified Bearer token.

## 3. Why Is HTTPS Alone Insufficient?

Suppose a token carries the JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "key-of-attacker",
  "jku": "https://keys.attacker.example.test/jwks.json"
}
~~~

The `jku` field in JOSE is a reference to a JWK Set URI. If a custom implementation sees `jku` and **automatically fetches keys from that address**, an untrusted party can publish their own public key, sign a JWT with their corresponding private key, and trick the system into verifying with the key they provided.

The endpoint nominated by the token sender can even be **real HTTPS with a valid certificate**. TLS only proves the connection matches that endpoint's hostname; it does not turn an arbitrary hostname into an **authorized Authorization Server**.

This is a form of **key-source substitution**; depending on how the software handles URLs, it can also lead to **server-side request forgery (SSRF)**, such as making HTTP requests from the Resource Server to internal networks or infrastructure metadata endpoints.

### 3.1. Externally Controllable Data Sources

| Value | Who Can Control It? | What Should a Secure Application Do? |
| --- | --- | --- |
| JWT header `kid` | The token sender can craft it. | Use only to select a key **within an already-approved JWKS**. |
| JWT header `jku` or `x5u` | May be supplied by the token creator. | Never automatically fetch from URLs in an unverified token. |
| JWT claim `iss` | Can be spoofed prior to signature verification. | Use to route against an **issuer allowlist** if needed; re-verify the issuer afterward. |
| HTTP query, path, or header containing `jwksUrl` | Arbitrarily modified by the client. | Never use it as the JWKS URI for the decoder validating that request. |
| Issuer metadata | Depends on the discovery endpoint. | Discover only permitted issuers; control TLS and the returned JWKS endpoint. |
| `jwk-set-uri` in operational config | Managed by administrators/deployment system. | Define from trusted config sources, and enforce allowlists and egress policies. |

**Reading the `iss` claim does not mean trusting it.** A multi-issuer resolver may read the unverified `iss` to look up a decoder, but must check it against an allowlist before creating or fetching a decoder, then verify the signature and re-validate `iss` on the decoded token.

### 3.2. URLs That Look "Allowed" but Must Be Rejected

Suppose policy allows only:

~~~text
https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

The following examples **must never automatically be treated as equivalent**:

~~~text
http://login.example.test/realms/demo/protocol/openid-connect/certs
https://login.example.test.attacker.example/realms/demo/protocol/openid-connect/certs
https://login.example.test@attacker.example/jwks.json
https://login.example.test:9443/other-keys
https://attacker.example/redirect-to-login-jwks
https://127.0.0.1:8443/admin/keys
https://169.254.169.254/latest/meta-data/
~~~

These URLs illustrate defects involving **scheme, hostname, userinfo, port, redirects, or internal network targets**. They do not belong in operational configuration. A rule checking "the URL simply starts with `https://login.example.test`" is inadequate because it can mistakenly match longer hostnames.

## 4. Spring Boot Configuration: Fetching JWKS Directly over HTTPS While Still Validating Issuer

### 4.1. Dependencies

Gradle (Groovy DSL) example for a Spring Boot Servlet application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The standard Resource Server starter provides Bearer token handling components and pulls in **Spring Security JOSE** for JWT processing. If configuring individual modules without the starter, a JWT Resource Server typically needs both `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose` at compatible versions.

### 4.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Meaning:

- **`issuer-uri`**: requires the `iss` claim to match the trusted issuer.
- **`jwk-set-uri`**: tells the decoder directly where to fetch the JWK Set. With corresponding auto-configuration, it avoids running metadata discovery just to locate `jwks_uri`.
- **`audiences`**: requires the `aud` claim to contain `orders-api` on Spring Boot versions supporting this property; on earlier versions, add a custom audience validator.
- Signature and claim verification are performed by the configured Spring Security JWT decoder and validators.

**Why still declare `issuer-uri`?** If you configure only `jwk-set-uri`, the decoder knows the key source but derives no issuer policy from that property. The API must identify the trusted issuer because public keys could be shared across contexts.

Example configuration **missing an issuer constraint**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

This configuration can verify signatures against the public keys, but **you must not assume it validates `iss` the way a configuration with `issuer-uri` does**. When `issuer-uri` is omitted, an issuer validator must be added explicitly.

### 4.3. Difference Between Issuer Discovery and a Direct JWKS URI

With `issuer-uri` alone, Spring Security can query OIDC Provider Metadata or OAuth 2.0 Authorization Server Metadata to discover **`jwks_uri`**:

~~~json
{
  "issuer": "https://login.example.test/realms/demo",
  "jwks_uri": "https://login.example.test/realms/demo/protocol/openid-connect/certs"
}
~~~

When the JWKS URI is known in advance, direct configuration avoids relying on **discovery to find the key endpoint**. However, network calls to retrieve new/rotated JWKs, caching policy, and fetch timing still depend on the library version and configuration.

| Scenario | JWKS Source | `iss` Constraint |
| --- | --- | --- |
| `issuer-uri` only with supporting auto-config | Discovered via issuer metadata. | Enforced from trusted issuer. |
| `jwk-set-uri` only | Direct URI. | **Must be explicitly validated** if the API expects a fixed issuer. |
| `issuer-uri` + `jwk-set-uri` | Direct URI. | Enforced from the declared issuer in supporting auto-config. |
| Manually built `NimbusJwtDecoder.withJwkSetUri` | Direct URI passed in code/config. | Explicitly attach `JwtValidators.createDefaultWithIssuer` and other validators. |

Keeping an HTTPS JWKS endpoint available **does not mean the Resource Server can run completely offline**. The decoder still needs to fetch keys on a cache miss, when a new `kid` appears, or when refreshing the JWK Set.

## 5. Designing an Allowlist for JWKS Sources

An "allowlist" is the set of administrator-approved sources allowed to supply keys. There are multiple control layers:

1. **Allowed issuer list:** which `iss` values the API accepts.
2. **Issuer → JWKS endpoint mapping:** which endpoint each issuer retrieves keys from.
3. **Strict URL checks:** scheme, host, port, path, and query per policy.
4. **Outbound connection controls:** the Resource Server's network/firewall/proxy permits connections only to approved destinations.
5. **TLS controls:** valid certificate and hostname, managed truststore, and verification never disabled.

No single URL-string check replaces all of these layers. For example, application-level host checks on a URL string can be bypassed by DNS, redirects, or proxies; connection settings and network policies must work together.

### 5.1. Exact URI Allowlist vs. Domain-Only Allowlist

| Check Strategy | Advantages | Risks / Prerequisites |
| --- | --- | --- |
| **Exact HTTPS JWKS URI match** | Difficult to misread hostname/path/port; ideal for a fixed issuer. | Endpoint changes require controlled configuration updates. |
| **Hostname + scheme/port/path allowlist** | Flexible across multiple managed realms/tenants. | Must strictly check path, suffixes, redirects, and DNS; never use `startsWith`. |
| **Broad wildcard across domains** | Easy initial setup. | Widens trust surface; compromise of any subdomain creates a rogue key source. |
| **Blindly trusting any HTTPS JWKS URL** | Seems convenient for dynamic tenants. | **Unacceptable**: any external party can pick a valid HTTPS host and serve their own keys. |

For an API trusting a single issuer, **pinning the exact approved JWKS URI** is usually clearest. For multi-issuer setups, maintain an approved **issuer → JWKS URI map**; changes to that mapping must be controlled like security policy changes.

### 5.2. Example URI Allowlist Validation at the Configuration Layer

Suppose an application component receives a JWKS URL from managed deployment configuration—**never** from an HTTP request. We can validate the URL before building the decoder:

~~~java
import java.net.URI;
import java.util.Set;

public final class TrustedJwksEndpoints {

    private static final Set<String> ALLOWED_URI_STRINGS = Set.of(
        "https://login.example.test/realms/demo/protocol/openid-connect/certs"
    );

    private TrustedJwksEndpoints() {}

    public static URI requireApproved(String configuredUrl) {
        URI uri = URI.create(configuredUrl);

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || !ALLOWED_URI_STRINGS.contains(configuredUrl)) {
            throw new IllegalArgumentException(
                "JWKS endpoint is not approved");
        }

        return uri;
    }
}
~~~

This example uses **exact policy-based URI string matching**, rejecting URLs containing queries, fragments, userinfo, or unapproved addresses. In multi-environment deployments, the allowlist can come from organization-controlled deployment config; it must still be pre-approved. If more flexible URI rules are needed, use a proper URI parser and structured policy rather than naive prefix matching.

**Limitation of this example:** validating a URI at the application layer **does not by itself stop HTTP redirects or DNS rebinding**. Nor does it guarantee that proxies, egress gateways, and the HTTP client actually connect to the approved destination. You must combine this with infrastructure egress controls and HTTP client hardening (Section 7).

### 5.3. Do Not Take a URL from a Token and "Sort of Check It"

Anti-pattern example:

~~~java
// DO NOT DO THIS: an unverified token can be controlled by the sender.
String jwksUrl = unverifiedJwtHeader.get("jku");
JwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUrl)
    .build();
~~~

This turns the token sender into the entity choosing which key source verifies the token. Likewise, never take an arbitrary URL from an unverified `iss` and allow fetching issuer metadata/JWKS from it.

In standard Spring Security applications, `NimbusJwtDecoder.withJwkSetUri(...)` takes an **application-configured URI**. Preserve that boundary and avoid building dynamic mechanisms that accept `jku`, `x5u`, or a client-supplied `jwksUrl` parameter.

## 6. Configuring `NimbusJwtDecoder` with an Approved JWKS Source

If you need to define a bean manually instead of relying on Spring Boot auto-configuration, validate against the allowlist first and then configure the decoder and validators.

This example uses a custom property **`app.security.jwt.jwks-uri`** supplied by deployment config; it is not a Spring Boot auto-configuration property:

~~~yaml
app:
  security:
    jwt:
      jwks-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

Java bean:

~~~java
import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
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
public class ApprovedJwksDecoderConfig {

    private static final String TRUSTED_ISSUER =
        "https://login.example.test/realms/demo";
    private static final String API_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder(Environment environment) {
        String configuredUrl = environment.getRequiredProperty(
            "app.security.jwt.jwks-uri");
        URI trustedJwks =
            TrustedJwksEndpoints.requireApproved(configuredUrl);

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwks.toString())
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(API_AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience is not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

With these two Java classes:

- **`requireApproved`** permits only allowlisted JWKS endpoints.
- **`withJwkSetUri`** loads public keys from the selected endpoint.
- **`jwsAlgorithm(RS256)`** restricts the verification algorithm per the issuer contract.
- **`createDefaultWithIssuer`** preserves issuer checks and default JWT conditions such as expiration.
- **`audienceValidator`** requires the token to be issued for `orders-api`.

When you declare a custom **`JwtDecoder`** bean, Spring Boot generally will not create another auto-configured decoder. Therefore, do not rely on `issuer-uri` or `audiences` properties in YAML while **forgetting to wire validators into your custom decoder**.

**This is illustrative code for an environment with one issuer and one JWKS endpoint.** Real deployments require per-environment mappings, network egress policies, and hardened HTTP client behavior. The issuer, audience, and allowed URI in the example must be replaced with your actual token contract.

### 6.1. Why Include an Issuer Validator if the Signature Is Already Verified?

A JWT might be validly signed by a key in the JWKS while carrying claims:

~~~json
{
  "iss": "https://another-issuer.example.test",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

A valid signature **does not justify skipping the `iss` claim**. To accept a token, the issuer must match the trusted authority, and the audience must match the current API. If a key is ever shared across systems, enforcing the issuer constraint becomes even more critical.

When calling **`setJwtValidator`**, include all required rules in the final validator chain. Never register just an audience validator and accidentally drop issuer/time checks.

### 6.2. Enabling Resource Server in `SecurityFilterChain`

Example of an API accepting only Bearer Access Tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this setup, the configured `JwtDecoder` verifies the token before Spring Security checks **`SCOPE_orders.read`** or **`SCOPE_orders.write`**. Disabling CSRF in the example is appropriate only for a pure Bearer-header API that does not use session cookies; web flows using OIDC Login require designing CSRF per security filter chain.

The JWKS URI is **Resource Server configuration**, never derived from the JWT or from headers of the incoming request being verified.

## 7. Protecting the JWKS Fetch Path: TLS, Redirects, DNS, and Egress

### 7.1. Use HTTPS with Real Certificate Verification

The HTTP client accessing JWKS must enforce:

1. The URI uses **`https`**, with no automatic downgrade to HTTP when HTTPS fails.
2. The server certificate is valid against the **truststore** authorized for the runtime.
3. **Hostname verification** matches the URL's host. A certificate valid for a different host is insufficient.
4. The certificate chain is unexpired and accepted under the system's TLS policy.
5. Truststores, enterprise CAs, reverse proxy TLS, or mTLS (if used) are managed by infrastructure and operational procedures.

Never install a `TrustManager` that accepts all certificates or disable hostname verification just to "get rid of SSL errors." That strips TLS of endpoint authentication. If the system uses an internal CA, configure the truststore to trust that specific internal CA instead of trusting all certificates.

**Certificate pinning** can be useful in specialized models, though it increases rotation overhead; it is not a universal requirement for every Resource Server. In most deployments, standard TLS verification, approved endpoint mapping, and clear egress controls are required.

### 7.2. HTTP Redirects Can Change the Final Destination

Suppose the approved URI is:

~~~text
https://login.example.test/keys
~~~

but the server returns `302 Location: https://other-host.example.test/keys`. If the HTTP client follows redirects without validating the new target, **the actual connection can reach an unapproved source**.

A secure design should:

- **Disallow redirects** when fetching JWKS unless there is an approved operational need; or
- Allow redirects only under strict policy, validating **every new destination** (scheme/host/port/path) and enforcing network egress policy on each connection.

A URL passing an initial allowlist check **does not guarantee subsequent redirects are also allowed**. Actual redirect behavior depends on the underlying HTTP client beneath Nimbus/Spring Security and application settings; configure it explicitly at the HTTP client or egress gateway layer.

### 7.3. DNS and Actual Network Destinations

An approved hostname may resolve to multiple IPs over time. The threat model must consider:

- Tampered or misrouted DNS.
- DNS rebinding: the host initially resolves to an allowed IP, then switches to a different address.
- Connections targeting loopback, internal networks, link-local ranges, or cloud metadata service addresses.
- HTTP proxies or service meshes altering outbound routing unexpectedly.

Do not perform a one-off `InetAddress.getByName` check and assume all future connections use that same IP. Full protection requires **network policies, firewalls/egress proxies, and DNS controls** aligned with the JWKS fetch policy. Combine TLS hostname verification with blocking outbound traffic to disallowed networks.

For a service that only needs to call an IdP/JWKS, configuring egress rules permitting **only required destinations** limits SSRF impact if application code has a bug. Java URI allowlists and infrastructure egress policies act as **two independent layers of defense**.

### 7.4. Timeouts, Size Limits, and Load Controls

Fetching JWKS is an outbound HTTP call from the Resource Server to another service. Pay attention to:

- **Connection timeout** and **read timeout** to avoid tying up resources when an endpoint hangs.
- Connection limits and refresh rate limits to prevent abnormal load.
- Response size limits and JWK count/format bounds according to infrastructure and HTTP client capabilities.
- Content-type restrictions, safe JSON parsing, and error response handling.
- Caching public keys so JWKS is not fetched on every request.

Default behavior, HTTP client configuration APIs, and cache lifetimes can vary across Spring Security/Nimbus versions. When a custom policy is needed, configure an application-managed HTTP client and wire it into `NimbusJwtDecoder` using your version's API. **Never arbitrarily set huge timeouts or disable TLS checks to work around connection errors.**

## 8. When Using Issuer Discovery, Must the Returned `jwks_uri` Still Be Checked?

**Yes—the JWKS source must still stay within the designed trust boundary.** Even starting from an approved issuer, the system is reading `jwks_uri` from network-fetched metadata.

Example metadata:

~~~json
{
  "issuer": "https://login.example.test/realms/demo",
  "jwks_uri": "https://keys.example.test/oauth2/jwks"
}
~~~

Having the JWKS on a different host **is not automatically wrong**: an Authorization Server may publish keys on a dedicated hostname. However, if your organization's security policy permits only `login.example.test`, you must explicitly approve `keys.example.test` or use a fixed `jwks_uri` configuration.

Design questions to answer:

- Is metadata fetched from an **approved issuer** over valid HTTPS?
- Does the `issuer` value in metadata match the configured issuer?
- Is `jwks_uri` within the set of permitted key-source endpoints?
- Can the HTTP client fetching metadata/JWKS follow redirects outside the allowlist?
- Does egress policy block unapproved sources even if application configuration is wrong?

If you need **very tight control over the JWKS address**, configuring `issuer-uri` alongside an exact **`jwk-set-uri`** is often simpler to govern. It decouples *identifying the issuer* from *selecting the key endpoint*, while avoiding accepting dynamic `jwks_uri` values.

## 9. Multi-Tenant and Multi-Issuer: Allowlisting Issuer–JWKS Pairs

In multi-tenant or multi-issuer systems, one Resource Server may accept tokens from multiple Authorization Servers:

~~~text
Issuer A: https://login-a.example.test/realms/a
JWKS A:   https://login-a.example.test/realms/a/certs

Issuer B: https://login-b.example.test/realms/b
JWKS B:   https://login-b.example.test/realms/b/certs
~~~

Never replace a fixed issuer with a strategy like:

~~~text
JWT.iss -> construct /.well-known/... URL -> fetch keys -> trust issuer
~~~

for any URI a client supplies. Doing so lets an external party stand up their own issuer and public keys and make the Resource Server accept forged tokens.

Instead, the system can maintain a table:

| Approved Issuer | Approved JWKS URI | Applicable API Audiences |
| --- | --- | --- |
| `https://login-a.example.test/realms/a` | `https://login-a.example.test/realms/a/certs` | `orders-api` |
| `https://login-b.example.test/realms/b` | `https://login-b.example.test/realms/b/certs` | `orders-api` |

A multi-issuer resolver, such as **`JwtIssuerAuthenticationManagerResolver`** in Spring Security Servlet, can pick the AuthenticationManager/decoder for **pre-approved** issuers. The unverified `iss` claim only selects a branch from the allowlist; **it is never authentication proof**.

~~~text
Bearer JWT
   |
   v
Read unverified iss to select branch
   |
   v
Is issuer in allowlist?
   | No                    | Yes
   v                       v
Reject              Select approved decoder/JWKS
                           |
                           v
                  HTTPS/TLS + egress controls
                           |
                           v
                  Verify signature
                  Re-validate iss
                  Validate aud, exp, nbf
                           |
                           v
                      Authorization
~~~

**Avoid sharing a key-source cache across issuers indexed solely by `kid`**. Two different issuers can choose the same `kid` value; trusted keys must always remain bound to their corresponding **JWKS/issuer source**. Scope/role/tenant rules may also differ across issuers and require separate mapping conventions.

## 10. Caching and Key Lifecycle

### 10.1. Why Cache the JWKS?

Resource Servers often handle high volumes of Bearer requests. Fetching the JWKS on every request causes:

- Higher authentication latency due to network round trips.
- Overload on the Authorization Server/JWKS endpoint.
- Any transient network glitch to disrupt large numbers of requests.
- Uncontrolled endpoints to become a resource-exhaustion vector.

Nimbus/Spring Security provides JWK Set caching depending on version and configuration. The goal is to **reuse verified public keys** while **refreshing when needed** to handle key changes.

Caching reduces load, **never replacing allowlists or HTTPS**. A public key fetched from the wrong source remains dangerous if cached long-term.

### 10.2. Proper Rotation Workflow

Suppose an issuer uses `key-A`, then transitions to `key-B`:

~~~text
T0: JWKS publishes key-A; tokens signed with key-A
T1: JWKS publishes both key-A and key-B
T2: Authorization Server starts signing new tokens with key-B
T3: Resource Server continues accepting unexpired older key-A tokens
T4: Last key-A token expires (or is handled per policy)
T5: JWKS removes key-A
~~~

Publishing **key-B before using key-B to sign** gives decoders a chance to refresh the JWKS and avoids rejecting new tokens during transition. Keeping **key-A** while old tokens remain valid allows the system to keep verifying them.

In a key compromise incident, emergency revocation plans differ from normal rotation: you must consider shortening token acceptance windows, flushing JWKS/caches, blocking abuse, and potentially updating validation policies.

### 10.3. What Happens If the JWKS Endpoint Goes Down?

| State | Expected Behavior |
| --- | --- |
| Decoder already holds the trusted public key in cache for the token | Can continue verifying according to active cache/TTL policy. |
| Decoder needs a public key not yet cached | Must fetch from the trusted JWKS; if unreachable, **never accept unverified tokens**. |
| JWKS returns malformed data or no matching key | Reject the affected token and log the operational error safely. |
| JWKS moves to a new endpoint outside the allowlist | Block spontaneous source changes; update policy and configuration through approved processes. |
| JWKS is served from another source via redirect | Do not trust redirects blindly; enforce designed policy on the final destination. |

Never fall back to "just decode the payload and check `exp`" when the JWKS fails. That **skips signature verification** and turns a self-asserted token into a trusted credential.

### 10.4. Token Permissions Changing During Its Lifetime

JWKS is a **signing-key verification** mechanism, not a real-time authorization database. A validly signed JWT can still carry permissions that were updated at the origin system until the token expires or the Resource Server runs additional checks. Thus, JWKS rotation **does not automatically revoke active tokens**, and `scope` checks do not replace data access rules requiring real-time freshness.

## 11. Testing the HTTPS and Allowlist Boundary

Testing should verify two distinct groups:

1. **JWKS source policy tests:** only approved URLs/issuers may load keys; redirects or off-allowlist URLs are blocked; TLS must be verified.
2. **JWT verification tests:** given a valid key source, signature/issuer/audience/lifetime/algorithm must be checked, and authorization must still rely on scopes/roles.

### 11.1. Scenario Matrix

| Scenario | Expected Result |
| --- | --- |
| Exact HTTPS URI in allowlist, valid cert/hostname | Permitted to fetch JWKS and verify JWT per configuration. |
| JWKS URI uses HTTP | Rejected in configuration/policy; no TLS downgrade. |
| URL has a hostname resembling the trusted source | Not in allowlist; do not fetch keys. |
| URL contains userinfo or unapproved port/path | Not treated as an approved key source. |
| Valid JWKS endpoint redirects to an unknown host | Do not follow policy-violating redirects. |
| Allowed hostname resolves to a forbidden network/target | Egress policy blocks connection; do not grant access. |
| TLS certificate has wrong hostname, is expired, or untrusted CA | Never skip certificate/hostname verification. |
| Token header has `jku` or `x5u` pointing to another endpoint | Do not fetch keys from that URL. |
| JWT has unknown `kid` and JWKS has no matching key | Token authentication fails. |
| Validly signed JWT, issuer not in allowlist | Reject JWT. |
| Validly signed JWT, right issuer, different API audience | Reject JWT. |
| Valid JWT with `orders.read` | Proceeds to authorization for the corresponding GET endpoint. |
| Valid JWT missing `orders.read` | Typically **403** at endpoints requiring that scope. |
| JWKS temporarily unreachable, decoder lacks the key | Do not skip verification; fail safely. |

### 11.2. Unit Tests for Configuration Allowlists

Using the `TrustedJwksEndpoints` helper from Section 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedJwksEndpointsTest {

    @Test
    void approvedUriIsAccepted() {
        var uri = TrustedJwksEndpoints.requireApproved(
            "https://login.example.test/realms/demo/protocol/openid-connect/certs");

        assertEquals("https", uri.getScheme());
    }

    @Test
    void httpAndUnexpectedHostsAreRejected() {
        assertThrows(IllegalArgumentException.class, () ->
            TrustedJwksEndpoints.requireApproved(
                "http://login.example.test/realms/demo/protocol/openid-connect/certs"));

        assertThrows(IllegalArgumentException.class, () ->
            TrustedJwksEndpoints.requireApproved(
                "https://login.example.test.attacker.example/jwks.json"));
    }

    @Test
    void queryStringIsNotPartOfApprovedUri() {
        assertThrows(IllegalArgumentException.class, () ->
            TrustedJwksEndpoints.requireApproved(
                "https://login.example.test/realms/demo/protocol/openid-connect/certs?x=1"));
    }
}
~~~

This test verifies **Java-level URL matching**. It makes no HTTP connections, so it **does not test TLS, DNS, redirects, or egress**. Those require network/HTTP client tests and deployment policy verification.

### 11.3. Testing `JwtDecoder` with Test Keys

In JWT decoder tests, generate a test-only RSA key pair, sign JWTs with the test private key, and verify with the test public key or a local JWKS endpoint. Include cases for:

- **Valid signature + issuer + audience + lifetime:** decodes successfully.
- **Invalid signature:** decoder rejects even if claims look valid.
- **Wrong issuer with valid signature:** decoder rejects via issuer validator.
- **Wrong audience with valid signature/issuer:** decoder rejects via audience validator.
- **Expired `exp` or future `nbf`:** decoder rejects.
- **`kid` matching no key in JWKS:** cannot verify and must reject.
- **Algorithm differing from config:** must not switch algorithms merely because the header requests it.

**MockMvc `jwt()`** from `spring-security-test` is convenient for testing endpoint authorization, but it creates a mock Authentication and **does not exercise `NimbusJwtDecoder` signature/JWKS verification**. To test the key-loading path, pass **real signed JWTs through the decoder** or write integration tests sending JWTs in `Authorization: Bearer` against a mock JWKS server.

### 11.4. Integration Test with a Local JWKS HTTP Server

Test design can look like:

~~~text
Test fixture
  |-- Generate test-only RSA private/public key pair
  |-- Publish public key at test JWKS endpoint
  |-- Sign JWTs with valid/invalid claims per test case
  |
  v
HTTP request: Authorization: Bearer <signed-test-jwt>
  |
  v
Spring BearerTokenAuthenticationFilter
  |
  v
NimbusJwtDecoder.withJwkSetUri(test JWKS endpoint)
  |
  +-- fetch JWKS
  +-- verify signature
  +-- check issuer/audience/lifetime
  |
  v
SecurityFilterChain: scope and policy -> 200 / 401 / 403
~~~

If JWKS tests use localhost/HTTP, restrict that exception **exclusively to isolated test environments**, never production config. For TLS security tests, stand up an HTTPS test endpoint with appropriate certificate/CA fixtures and verify that invalid-certificate connections are rejected. Never use production keys or Access Tokens in tests.

## 12. Observability, Logging, and Safe Error Handling

The Resource Server needs signals to spot JWKS or rotation failures without leaking credentials. Operational data safe to log includes:

- **Error category**: JWKS connection failure, TLS verification failure, unknown key ID, issuer mismatch, audience mismatch, expired token.
- **Configured service/issuer name** and controlled configuration identifiers, when permitted.
- **System-generated request ID** and timestamp.
- **Grouped error counts**, JWKS fetch latency, 401/403 rates, and cache hit/miss ratios if exposed by the library.
- **Health of approved JWKS endpoints**, such as connection, DNS, or certificate errors.

Never log:

- Raw JWTs or `Authorization` headers.
- Client secrets, refresh tokens, private signing keys, or sensitive TLS keystore details.
- Full HTTP requests/responses if they may contain tokens or untrusted payloads.
- Arbitrary unverified URL strings from tokens/clients treated as "trusted endpoints" in logs or monitoring.

### 12.1. HTTP 401 vs. HTTP 403

In a properly configured Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

normally appears when no token is present or the token cannot be authenticated (invalid signature, wrong issuer/audience, expired token, etc.). An authenticated JWT lacking permission for the endpoint typically receives:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Exact `WWW-Authenticate` details depend on the scenario and framework. Never reflect raw exceptions, sensitive internal URLs, stack traces, or tokens in error response bodies.

### 12.2. An Operational Scenario

**Scenario:** The Authorization Server starts signing with key `rsa-2026-b`, yet several Resource Server instances still hold only `rsa-2026-a` in cache.

Investigation steps:

1. Verify the **approved** JWKS endpoint actually publishes both the old and new keys during transition.
2. Check the failing token's `kid` and the published public key list using safe operational tooling, **without logging the raw token**.
3. Check TLS, egress connectivity, and refresh/cache timing on each instance.
4. Confirm issuer/audience/lifetime are still valid; a 401 can come from another validator, not only the key.
5. Resolve key distribution/refresh per the rotation plan while preserving the rule **never accept unverified tokens**.

If the JWKS URI changes to a new hostname, update the approved source list through a controlled configuration process. Never automatically add a new hostname simply because a JWT or error response suggests it.

## 13. Misconceptions to Avoid

| Misconception | Correct Understanding |
| --- | --- |
| "JWKS over HTTPS is completely safe." | HTTPS authenticates the connection to a hostname; the endpoint must still be **authorized to provide keys** for the issuer. |
| "If a JWT has `jku`, the Resource Server must fetch that URL." | Never fetch key sources chosen by an unverified token; use managed issuer/JWKS config. |
| "`kid` is proof of the issuer." | `kid` is only a key identifier; trust comes from the **JWKS source** and verified signature. |
| "Checking that the hostname starts with a trusted domain is enough." | Prefix matching misidentifies hostnames, userinfo, ports, and paths; use proper URI parsing and explicit allowlists. |
| "Validating URLs in Java blocks all SSRF." | Redirects, DNS, proxies, and actual egress must be controlled separately. |
| "With the right JWKS, we can skip issuer checks." | Key source and the `iss` claim are two separate constraints. |
| "A valid issuer means the JWT can call every API." | You must still check **audience** and scope/permission authorization. |
| "Using `jwk-set-uri` directly means the network is never needed." | The decoder still fetches public keys on cache misses or when new keys appear. |
| "Having one public key makes key rotation automatic." | Rotation requires timely publication of multiple keys, cache refreshes, and expiration policies. |
| "If the JWKS fails, let tokens through to preserve uptime." | Never accept unverified tokens; handle operational outages while keeping trust boundaries intact. |
| "A signed JWT keeps its payload secret." | JWS JWT payloads are readable; avoid storing unnecessary sensitive data. |
| "MockMvc `jwt()` already tests JWKS." | It tests behavior with a mock Authentication; testing JWKS requires a real decoder/HTTP path. |

## 14. Practical Implementation Workflow

1. **Define the token contract:** issuer, Resource Server audience, JWT/JWS type, algorithm, lifetime, scopes, and token profile requirements.
2. **Publish a trusted key source:** choose an HTTPS JWKS endpoint managed by the Authorization Server/approved party; never put private keys in a public JWKS.
3. **Establish the issuer → JWKS allowlist:** pin URIs or manage controlled mappings; never accept URLs from clients/tokens.
4. **Configure Spring Security:** `issuer-uri` + `jwk-set-uri` and audiences on supported Boot versions, or `NimbusJwtDecoder` with explicit issuer/audience validators.
5. **Configure TLS and egress:** enforce hostname/certificate validation, outbound restrictions, and policy-driven redirect, DNS, and proxy handling.
6. **Configure key lifecycle:** TTL/cache, pre-rotation key publication, retaining old keys while tokens remain valid, and safe outage handling.
7. **Write negative tests:** HTTP, off-allowlist URLs, redirects to unknown hosts, TLS failures, untrusted `jku`, bad signatures, wrong issuer/audience, missing new keys, and insufficient permissions.
8. **Operate and monitor:** track verification failures and JWKS connectivity without exposing JWTs, secrets, or private data.

**Final rule:** A Resource Server must use only **public keys fetched from an approved JWKS source**, retrieved over **verified HTTPS/TLS**, while validating **issuer, audience, lifetime, and access permissions**. A wrong key source renders a "valid" signature meaningless; a right key source still does not replace API-specific token acceptance policies.

## References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
