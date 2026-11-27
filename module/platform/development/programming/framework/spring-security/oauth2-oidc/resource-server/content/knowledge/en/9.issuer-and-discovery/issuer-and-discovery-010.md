# Verifying Metadata, HTTPS, and Certificates in Each Environment

When a **Spring Security OAuth 2.0 Resource Server** is configured with `issuer-uri`, the application must know **which Authorization Server is trustworthy**, where to fetch token verification keys, and whether the JWT was genuinely issued for this API. That information is typically published via OAuth 2.0 / OpenID Connect (OIDC) **issuer discovery**, connected over **HTTPS**.

A configuration that looks simple:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
```

actually rests on several conditions: the domain resolves to the right system, the TLS certificate is valid for the Resource Server's JVM, the returned metadata describes the **right issuer**, the JWKS address has not been substituted, the JWT signature matches a trusted key, and claims such as `iss`, `aud`, and `exp` satisfy the API's contract.

**Lesson goal:** learn how to **verify metadata, HTTPS, and certificates across development, staging, and production environments**, catch configuration drift without disabling TLS verification, and distinguish two commonly confused key types: **TLS certificates securing transport** versus **JWK keys verifying JWT signatures**.

> **Illustrative context:** The Orders API runs Spring Boot 3.x / Spring Security 6.x on the Servlet stack; the Authorization Server has a dedicated issuer per environment. URLs in this lesson are example addresses, not live services. Spring Boot/Security version-dependent behaviors must be verified against your actual library version when deploying.

## 1. Four Trust Layers to Verify Separately

| Layer | Subject of verification | Question to answer | Component typically responsible |
|---|---|---|---|
| **Issuer configuration** | `issuer-uri`, tenant/realm identifier | Which **Authorization Server** does the API trust? | Resource Server configuration |
| **Discovery metadata** | `issuer`, `jwks_uri`, and related metadata | Does the discovered document match the **selected issuer**? | Spring Security / discovery config |
| **HTTPS and TLS certificates** | Domain name, certificate chain, trusted CA, validity window | Is the connection to metadata/JWKS endpoints a secure connection to the expected host? | TLS stack and JVM truststore |
| **JWT and access permissions** | JWS signature, `iss`, `aud`, `exp`, `scope` | Is the token valid, intended for this API, and sufficiently authorized? | `JwtDecoder`, validators, authorization policy |

These layers support one another yet **do not replace one another**:

- **Valid HTTPS** only verifies the connection to the host under the TLS certificate model; it does not prove every JWT issued by that host is allowed by the API.
- **Valid metadata** helps locate and identify a trusted key source; it does not replace verifying each token's signature.
- **Valid JWT signature** does not replace checking `iss` or `aud`. A token issued for the Inventory API cannot automatically be used on the Orders API.
- **Right `iss`** cannot rescue a configuration pointing to the wrong JWKS or skipping TLS certificate validation.
- **JWT keys (JWK)** and **TLS certificates** serve different boundaries. Both are “keys/certificates”, yet their usage and lifecycles differ.

## 2. An Issuer Is an Exact Identifier, Not Merely a Hostname

An Issuer URI is the stable identifier of the Authorization Server that the Resource Server chooses to trust. For example:

```text
https://login.example.com/realms/orders
```

In a JWT:

```json
{
  "iss": "https://login.example.com/realms/orders",
  "aud": ["orders-api"],
  "sub": "user-42",
  "exp": 2000000000
}
```

The Resource Server must compare `iss` against the configured issuer by **exact value**, not merely by hostname or an arbitrary prefix.

| Expected configuration | `iss` in JWT | Assessment |
|---|---|---|
| `https://login.example.com/realms/orders` | `https://login.example.com/realms/orders` | Right issuer if other token conditions also pass |
| `https://login.example.com/realms/orders` | `https://login.example.com/realms/billing` | Wrong realm / issuer |
| `https://login.example.com/realms/orders` | `https://login.staging.example.com/realms/orders` | Wrong environment |
| `https://login.example.com/realms/orders` | `http://login.example.com/realms/orders` | Wrong scheme |
| `https://login.example.com/realms/orders` | `https://login.example.com/realms/orders/` | Trailing `/` difference; must follow exact issuer contract |

Do not fix `iss` manually by replacing `http` with `https`, stripping tenant paths, or removing slashes to “make it match”. If the issuer is wrong, inspect the publisher, discovery, reverse proxy, and client configuration before changing verification policy.

### 2.1. Issuer Identifier Differs from Internal Backend Address

An organization may deploy its Authorization Server in Kubernetes at an internal address `http://identity-svc:8080`, while exposing it externally through a gateway:

```text
https://login.example.com/realms/orders
        │
        └── Reverse proxy / ingress (TLS)
                  │
                  └── identity-svc:8080 (private network)
```

If the published issuer is `https://login.example.com/realms/orders`, then:

- Metadata should declare `issuer` as that exact public identifier.
- JWTs should use that exact identifier in `iss`.
- The Resource Server must verify `iss` against that identifier.
- The TLS certificate for the public endpoint must be valid for **`login.example.com`**.
- The internal hostname `identity-svc` does not automatically become the issuer merely because the app runs there.

Reverse proxy operations must configure the external base URL / forwarded headers using the Authorization Server's supported mechanism, never letting the application generate an issuer that varies by each request's host.

## 3. What Is Discovery Metadata?

In OAuth 2.0 and OIDC, the Authorization Server can publish a JSON metadata document so clients and Resource Servers can locate relevant endpoints/keys.

Two common standards:

1. **OpenID Connect Discovery 1.0** with the OIDC Provider Configuration document at `.well-known/openid-configuration` per OIDC URL rules.
2. **RFC 8414 — OAuth 2.0 Authorization Server Metadata** at `.well-known/oauth-authorization-server` per URL derivation rules from the issuer.

Spring Security supports resolving provider metadata from the issuer in compatible models. **Do not concatenate URL strings assuming one path is always right**: when an issuer contains a path/realm, the `.well-known` placement in OIDC and OAuth Authorization Server Metadata can differ per specification.

Example issuer:

```text
https://login.example.com/realms/orders
```

An OIDC provider may serve metadata like:

```text
https://login.example.com/realms/orders/.well-known/openid-configuration
```

With RFC 8414, placing `.well-known/oauth-authorization-server` relative to an issuer path has its own rule, for example:

```text
https://login.example.com/.well-known/oauth-authorization-server/realms/orders
```

Depending on vendor and version, real endpoints may support multiple patterns or follow one specific standard. **Start from the registered issuer**, let the library's discovery handle supported mechanisms, and inspect the real JSON rather than guessing URLs.

### 3.1. Example Issuer Metadata

```json
{
  "issuer": "https://login.example.com/realms/orders",
  "authorization_endpoint": "https://login.example.com/realms/orders/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/orders/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/orders/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

This is **illustrative JSON**: required/optional fields vary by standard and provider role; endpoint names may differ. What a Resource Server needs most when verifying JWTs are **issuer and JWKS URI**, whereas Authorization Code / token endpoints are mainly used by OAuth/OIDC Clients.

### 3.2. What Must Be Verified in Metadata?

| Item | Correct interpretation | When it fails |
|---|---|---|
| **Valid JSON** | HTTP response is well-structured metadata, not an HTML login page or gateway error | Do not trust metadata; check endpoint, redirects, proxy |
| **Right `issuer`** | Metadata issuer equals the configured `issuer-uri` exactly | Reject / fix source configuration |
| **Trusted `jwks_uri`** | Verification key endpoint published by the trusted issuer via metadata and valid TLS | Never follow arbitrary addresses or token-suggested URLs |
| **Valid HTTPS** | Connections to metadata and JWKS have valid certificate chain/hostname | Never disable checks; fix certificates, truststore, DNS |
| **Endpoint actually reachable** | Serves metadata/JWKS per protocol, network rules, and proxy | Fix network policy, DNS, ingress, firewall |
| **Compatible signing algorithm** | Issuer signs JWTs with an algorithm allowed by the Resource Server | Align signing contract; never open freely based on `alg` in token |
| **Environment/tenant name** | Metadata does not cross-wire staging ↔ production or realm A ↔ realm B | Separate issuers and inspect deployment config |

**Never take metadata from client-supplied requests.** A Resource Server trusts only its configured issuer or set of allowed issuers. If an app is multi-issuer, each issuer must be registered/allowlisted and verified separately.

### 3.3. Not All Metadata Endpoints Need to Be Public

Metadata documents can publish `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, `introspection_endpoint`, `revocation_endpoint`, and `jwks_uri` depending on deployment. Having a URL in metadata **does not mean** every endpoint is unconditionally accessible or that the Resource Server needs to call all of them.

- `authorization_endpoint`: serves authorization redirect flows from OAuth clients.
- `token_endpoint`: issues/refreshes tokens after client completes a grant and authenticates as needed.
- `jwks_uri`: publishes public signing keys for JWT verification.
- `introspection_endpoint`: serves opaque token validation under dedicated authentication permissions.
- `revocation_endpoint`: serves token revocation according to Authorization Server policy.

For a **JWT** Resource Server, usually only discovery/JWKS and verification policies are needed. Never place a token endpoint client secret into a Resource Server merely because `token_endpoint` appears in metadata.

## 4. From Discovery to JWT Verification: The Trust Flow

```mermaid
sequenceDiagram
    autonumber
    participant RS as Spring Resource Server
    participant TLS as HTTPS / TLS trust
    participant AS as Authorization Server
    participant JWKS as JWKS endpoint
    participant C as OAuth Client
    RS->>TLS: Connect to configured discovery URL
    TLS->>AS: HTTPS + verify hostname/certificate
    AS-->>RS: Metadata JSON (issuer, jwks_uri, ...)
    RS->>RS: Verify issuer in metadata matches config
    RS->>TLS: Connect to trusted jwks_uri
    TLS->>JWKS: HTTPS + verify certificate
    JWKS-->>RS: JWKS containing public keys
    C->>RS: GET /api/orders + Bearer access token
    RS->>RS: Verify JWS with allowed key/alg
    RS->>RS: Check iss, aud, exp, nbf, scope...
    alt All conditions satisfied
        RS-->>C: Return data if authorized
    else Token or verification infrastructure fails
        RS-->>C: Reject per policy and error status
    end
```

This flow is conceptual: Spring may fetch metadata/JWKS **at startup or on demand**, depending on configuration/version and caching. When keys are cached, an HTTP request to JWKS does not necessarily occur on **every API call**.

What never changes is that trusting a JWT must follow an unbroken valid trust path:

```text
Configured issuer
        ↓
Metadata with right issuer + trustworthy HTTPS
        ↓
JWKS URI published by issuer + trustworthy HTTPS
        ↓
Accepted public key / verification algorithm
        ↓
Valid JWT signature and claims
        ↓
Orders API authorization policy
```

If a critical link breaks, never “let it through” by dropping signature checks or disabling TLS verification.

## 5. Distinguishing TLS Certificates from JWT Signing Keys

This is a common point of confusion when debugging “certificate”, “key”, and “signature” errors.

| Attribute | TLS / HTTPS certificate | JWT signature verification key / JWKS |
|---|---|---|
| Goal | Secures transport and authenticates TLS endpoint identity | Verifies token bears a valid signature under a trusted issuer key |
| Where used | Resource Server → metadata/JWKS endpoint connection | `JwtDecoder` verifying Bearer JWT |
| How verified | Hostname/SAN, certificate chain, CA trust, validity dates, TLS policy | JWS signature, algorithm, matching `kid`/key, issuer/audience/time/claims |
| Published material | Server certificate and required intermediates | Public JWKs for asymmetric signatures |
| Secret kept private | TLS private key on server/gateway | JWT private signing key on Authorization Server |
| Rotation | Renew/reissue TLS certificate and chain | Rotate signing key, publish new public key via JWKS |
| Typical error | `PKIX path building failed`, hostname mismatch | `Invalid signature`, unknown `kid` / no matching key |

An **expired TLS certificate** can prevent Spring from fetching metadata or JWKS even though JWTs are actually validly signed. Conversely, completely valid TLS never makes a JWT with a bad signature valid.

**JWKS is not a CA truststore.** Public JWKs are used for token verification; the JVM truststore holds CAs/certificates trusted when establishing TLS connections. Do not import an entire JWKS into the Java truststore thinking that solves HTTPS verification.

In some JWKs, `x5c` or `x5t` fields can bind an X.509 certificate to a signing key. Even then, that **does not turn a token signing certificate into a TLS certificate for a hostname**. The system must verify each purpose under its respective standard.

## 6. What Must HTTPS and Certificates Verify?

### 6.1. Certificate Chain and Trusted CA

When the Resource Server connects to:

```text
https://login.example.com/realms/orders/.well-known/openid-configuration
```

the TLS client in the JVM receives the server's certificate chain and must establish a trust path to a **trust anchor** (a CA or certificate trusted by the JVM), enforcing PKIX/TLS policy constraints.

Illustrative chain:

```text
login.example.com (leaf/server certificate)
        │ signed by
        ▼
Intermediate CA
        │ signed by
        ▼
Trusted Root CA in JVM truststore
```

Typical requirements include:

- The leaf certificate is currently valid per system clock.
- The URL hostname is covered by a valid **Subject Alternative Name (SAN)**.
- The chain leads to a trusted CA/trust anchor with all required intermediate certificates.
- Certificate/key usage, algorithms, and TLS policy are supported by the JVM.
- Connection uses TLS per environment requirements, never silently downgrading to HTTP.
- The gateway returns the right certificate when multiple domains share an IP; **SNI** can affect which certificate is selected.

If a browser on your laptop opens the URL while the Java app inside a container fails, **that does not mean JVM certificate validation is wrong**. The laptop and the JVM/container may use **two different truststores**.

### 6.2. Hostname Verification and SAN

For example, metadata is called via:

```text
https://login.example.com/.well-known/openid-configuration
```

The TLS certificate must be valid for `login.example.com` (per SAN and hostname verification rules). A certificate having only SAN `identity.internal.example.com` must not be accepted for the public URL above simply because both hostnames resolve to the same IP.

Typical scenarios:

| Target URL | Certificate SAN | Conclusion |
|---|---|---|
| `https://login.example.com` | `DNS:login.example.com` | Matches if chain and dates are also valid |
| `https://login.example.com` | `DNS:identity.example.com` | Hostname mismatch |
| `https://login.staging.example.com` | `DNS:login.example.com` | Does not match the staging hostname |
| `https://10.0.0.10` | Only `DNS:login.example.com` | Not valid for an IP address |
| `https://login.example.com` | `DNS:*.example.com` | May match one subdomain level per wildcard rules, still requires chain and policy checks |

Do not “fix” a mismatch by disabling hostname verification. Fix the URL, DNS, SNI, ingress, or certificate SAN to match the actual domain used.

### 6.3. A TLS Certificate Does Not Directly Verify the JWT Issuer

An HTTPS endpoint with a valid certificate can still publish metadata with an `issuer` different from what the Resource Server expects:

```json
{
  "issuer": "https://login.example.com/realms/other-tenant",
  "jwks_uri": "https://login.example.com/realms/other-tenant/keys"
}
```

Even with valid HTTPS, this metadata **must not** be accepted for issuer `https://login.example.com/realms/orders`. Verifying `issuer` as well prevents realm/tenant mix-ups and reverse proxy misrouting.

### 6.4. Certificates from an Internal CA or Self-Signed

In internal environments, an organization may use a **private CA** instead of a public CA. The JVM must trust the right approved CA or trust anchor. Options include:

- Issuing server certificates from the internal CA and placing the exact CA certificate in the application's truststore.
- Using managed secrets/config mounts in Kubernetes to supply truststores per workload.
- If the service already has a certificate trusted by a standard CA, prefer using the runtime's standard truststore.
- For truly isolated local development, you can generate a separate dev CA/certificate; never carry dev keys or truststores into staging/prod.

**Disabling TLS checks using a TrustManager that accepts every certificate or a HostnameVerifier that always returns true is strongly discouraged.** Doing so removes part of the trust boundary for fetching metadata/JWKS, making it easy for a man-in-the-middle to swap verification keys.

## 7. Separating Configuration Across Development, Staging, and Production

Each environment needs a **clearly defined identity source**, trusted certificates, and appropriate network policies. For example:

| Environment | Expected issuer | Expected JWKS | Certificate / CA |
|---|---|---|---|
| **Development** | `https://login.dev.example.com/realms/orders` | JWKS of the **dev issuer** | Public CA or dedicated dev CA, trusted only in dev |
| **Staging** | `https://login.staging.example.com/realms/orders` | JWKS of the **staging issuer** | CA trusted by staging environment, SAN matching staging hostname |
| **Production** | `https://login.example.com/realms/orders` | JWKS of the **production issuer** | Valid, trusted production TLS certificate with dedicated ops/rotation policy |

Do not share **one common issuer** across all environments merely to reduce configuration variables if the environments have independent security boundaries. Dev tokens should not be accepted in production simply because `sub` or `kid` happens to match.

### 7.1. Configuration Files Using Spring Boot Profiles

You can use per-environment Spring profile files, such as:

**`application-dev.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.dev.example.com/realms/orders
          audiences:
            - orders-api-dev
```

**`application-staging.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.staging.example.com/realms/orders
          audiences:
            - orders-api-staging
```

**`application-prod.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          audiences:
            - orders-api
```

`aud` names are illustrative examples to show separation. Audience must match the exact token contract issued by the Authorization Server. The `audiences` property is available in supported Spring Boot versions; on other versions, configure an explicit `aud` validator.

**Never commit CA private keys, HMAC JWT signing secrets, OAuth client secrets, or real truststore passwords into YAML.** If a truststore must be supplied, deliver the file and password through an organization-managed secret mechanism.

### 7.2. Values to Manage as an “Environment Contract”

At minimum, each environment should publish to deployment teams:

- **Canonical issuer identifier** (exact URL, including scheme, host, port/path, and trailing slash if any).
- **Discovery type/metadata endpoint** actually supported (OIDC, OAuth AS Metadata).
- **JWKS URI** published by the issuer, signing algorithm details, and key rotation policy.
- **Resource identifier / audience** of the Orders API.
- **CA/truststore policy** and who owns issuing/renewing TLS certificates.
- **Egress/DNS/proxy** so the Resource Server can reach metadata/JWKS.
- **Token lifetimes, clock skew, scopes/authorities**, and error handling rules.
- **Owners and incident runbooks** for wrong issuer, expired certificates, or failed signing key rotation.

These details must be aligned across the Authorization Server operations team, Resource Server team, and infrastructure team. “The URL opens in my browser” does not substitute for direct runtime verification.

## 8. Configuring Spring Security Resource Server for Issuer Discovery

### 8.1. Common Case: Configuring Only `issuer-uri`

For Spring MVC on Spring Boot 3.x / Spring Security 6.x, Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          audiences:
            - orders-api
```

Security chain:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

In this model, Spring Security uses the issuer to locate the related configuration, set up `JwtDecoder`, fetch matching verification keys, and validate configured claims. The `SCOPE_orders.read` authority depends on JWT scope/authority mapping; add a custom converter if the issuer uses a different convention.

**Do not assume issuer alone is enough:** the Resource Server must still verify **audience**, access token type/`typ` when following RFC 9068 profiles, timestamps, algorithms, and business rules. If using a custom `JwtDecoder`, ensure all required validators remain applied.

### 8.2. Declaring Both `issuer-uri` and `jwk-set-uri`

When you want to configure the JWKS URI explicitly from **already-verified** metadata:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          jwk-set-uri: https://login.example.com/realms/orders/protocol/openid-connect/certs
          audiences:
            - orders-api
```

Meaning:

- `issuer-uri` retains its role as the **trusted issuer identifier**, used to validate `iss`.
- `jwk-set-uri` supplies the **address to fetch public JWKs** instead of requiring discovery from metadata to locate keys during decoder setup.
- `audiences` illustrates target resource validation in supported Spring Boot versions.

This is a way to **reduce reliance on metadata discovery at startup** documented in Spring Security for compatible versions, yet the Resource Server may still need to contact the **JWKS endpoint when keys are required**, such as when verifying the first token or encountering an uncached `kid`. Do not infer that declaring `jwk-set-uri` means the application never needs network access.

**Configuration risk:** entering the JWKS URI of another tenant or environment can cause signature failures or create a broken trust boundary. The `jwk-set-uri` value must come from a trusted contract/metadata and be governed alongside the issuer; never accept arbitrary URLs from HTTP requests or a token's JOSE header.

### 8.3. Why Can Startup Fail Because of Metadata?

In some auto-configuration setups, initializing `JwtDecoder` from an issuer can query the discovery endpoint to fetch metadata and `jwks_uri`. If the issuer is unreachable, TLS fails, or the document is invalid, the application may fail right at startup. Different versions/configurations fetch at different times; therefore, **never assert that every Spring version always fetches at startup or always fetches lazily**.

Distinguish:

- **Startup dependency:** the application needs metadata to initialize the decoder.
- **Runtime dependency:** the API needs to fetch a new signing key or refresh the JWKS cache while verifying JWTs.
- **Temporary network outage:** some tokens may still verify with cached keys, while key rotation or starting new instances can be affected.

The right fix is governing dependencies, timeouts/caching, readiness, ingress/networking, and metadata/JWKS configuration. Never switch to “accept JWT without signature” to bypass connection errors.

## 9. Verifying HTTPS and Metadata from the Actual Runtime Environment

Testing on a laptop can differ from testing inside a **container/pod/VM** because DNS, proxies, network policies, and truststores differ. When errors occur, run checks from the **runtime or a diagnostic environment with equivalent network and certificate trust configuration**.

### 9.1. Checking Metadata with curl

Example on a machine with curl:

```bash
curl --verbose --fail \
  --header "Accept: application/json" \
  "https://login.example.com/realms/orders/.well-known/openid-configuration"
```

Observe:

1. Does DNS resolve the right hostname?
2. Do TCP/TLS connect cleanly?
3. Does the TLS certificate verify successfully?
4. Is the HTTP response `200` and JSON metadata?
5. Does `issuer` in the JSON **match exactly** the expected issuer?
6. Is `jwks_uri` HTTPS and from a trusted source?
7. Was the response redirected to a login page, reverse proxy HTML, or another tenant?

The command above assumes the provider supports that specific **OIDC Discovery path**. If the system follows RFC 8414 or uses a different issuer path, use the metadata URL per the provider's docs.

On Windows PowerShell, `curl` may be an alias for `Invoke-WebRequest`; invoke **`curl.exe`** if you want native curl syntax.

**Never use `-k` or `--insecure` to claim an environment passed TLS verification.** Those flags intentionally skip certificate checks and hide real problems.

### 9.2. Checking the JWKS URI

Take `jwks_uri` from verified metadata, for example:

```bash
curl --verbose --fail \
  "https://login.example.com/realms/orders/protocol/openid-connect/certs"
```

The response may look like:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "orders-signing-2026-01",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_EXAMPLE",
      "e": "AQAB"
    }
  ]
}
```

`n` in the illustrative JSON is **not a real public key**. What to verify is that the endpoint returns a **well-structured JWK Set** with the required public keys, `kid`/algorithm matching issued tokens, and exposes no symmetric secrets or private keys.

Watch out for `kty=oct` JWKs: those represent **symmetric keys**, and HMAC secrets must never be exposed on a public JWKS. For asymmetric algorithms, public JWKs can be published safely by design.

### 9.3. Checking Certificate Chain and SNI with OpenSSL

```bash
openssl s_client \
  -connect login.example.com:443 \
  -servername login.example.com \
  -showcerts \
  -verify_return_error
```

Items to inspect in output:

- The leaf certificate matches the domain name and is unexpired.
- The server sends all required intermediate certificates.
- SNI selects the right virtual host/certificate.
- A trust path reaches an appropriate CA if the OpenSSL host has a matching truststore.
- The TLS handshake completes without certificate or protocol errors.

**Limitation:** OpenSSL uses the command environment's own trust store; success on a debug machine **does not prove** the application container's JVM truststore trusts that CA too. Use this tool to inspect the chain and certificates, then compare against the JVM truststore.

### 9.4. Checking the JVM Truststore with keytool

Check which truststore type/config the JVM uses, then inspect relevant certificates/aliases. For example, with an organization-managed PKCS12 truststore:

```bash
keytool -list -v \
  -keystore /opt/app/certs/truststore.p12 \
  -storetype PKCS12
```

The command may prompt for the truststore password; **never put passwords in commands recorded in shell history or CI logs**. Not all deployments use a custom truststore: the JVM normally uses the runtime's default truststore unless configured otherwise.

Approved CAs can be added to a custom truststore through infrastructure processes (for example, `keytool -importcert` after verifying fingerprint/certificate origin via an independent channel). **Never casually import a leaf certificate seen during a suspect connection**, as doing so could pin an attacker's certificate.

### 9.5. Checking System Time

TLS certificates have `notBefore`/`notAfter`; JWTs have `iat`, `nbf`, `exp`. If a host/pod clock drifts significantly, both TLS and JWT validation can fail.

- Synchronize VM/node clocks using NTP or a reliable time service.
- Check TLS certificate validity dates against actual runtime clock time.
- Use only a small, well-justified, consistent clock skew for JWTs.
- Never inflate clock skew hugely to “fix” expired tokens or certificates.

## 10. Java Truststores and Container Environments

### 10.1. Default Truststore vs. Custom Truststore

Java applications normally verify HTTPS through TLS/JSSE using the JVM truststore or a specific HTTP client TLS config. In container environments, a JVM image may have a different CA list from your local machine.

If the organization uses a private CA, one configuration option is supplying a **PKCS12 truststore** to the JVM:

```text
-Djavax.net.ssl.trustStore=/opt/app/certs/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Supply the truststore password if needed via a secure secret mechanism—never hardcode it in examples, source code, or logs. These are standard JSSE **system properties**; custom HTTP client frameworks may use their own TLS configuration.

**Design warning:** specifying a custom truststore can replace the default CA set in certain configurations. If the service calls other HTTPS endpoints as well, an overly narrow truststore can break them. Truststore generation workflows must explicitly define allowed CAs and trust levels.

### 10.2. Certificate at Ingress Differs from Certificate at Backend

Suppose TLS terminates at ingress:

```text
Spring Resource Server ── HTTPS ──> Identity Ingress
                                      │ TLS termination
                                      ▼
                                Identity service
```

The Resource Server acts as a **TLS client** to ingress, so the certificate it sees is **ingress's certificate for the target endpoint hostname**. Any internal certificate between ingress and the identity service is a separate layer depending on internal network policy and may also use TLS/mTLS.

If the resource server connects directly to a service address instead of ingress, design TLS hostnames and trust for the **address actually connected to**. Never arbitrarily switch an HTTPS issuer URL to internal HTTP just to avoid certificate errors.

### 10.3. Forward Proxies and TLS Interception

In some corporate networks, outbound HTTPS passes through a proxy performing TLS inspection. In that case, the JVM may see a certificate signed by the **enterprise proxy CA** rather than the original destination's CA.

Verify:

- Is the proxy authorized by the organization for metadata/JWKS connections?
- Does the JVM trust the enterprise CA per policy?
- Does the proxy alter metadata/JWKS contents or route to a different tenant?
- Is the path secured, audited, and prevented from granting unintended modification rights over metadata/JWKS?

Never import an unfamiliar CA just to silence `PKIX path building failed`. Trusting a CA authorizes it to vouch for hostnames within its scope, so it must be a verified infrastructure decision.

## 11. Common Errors and Root-Cause Identification

| Symptom / error | Common cause | Where to check |
|---|---|---|
| `PKIX path building failed` | JVM cannot find a chain to a trusted CA; missing intermediate/private CA | Check certificate chain, JVM/runtime CAs, truststore |
| `No subject alternative DNS name matching ... found` | URL hostname is not in certificate SAN | Check DNS, endpoint URL, ingress, SAN/SNI |
| `certificate has expired` or `not yet valid` | Certificate outside validity window or clock skew | Check certificate dates and runtime clock |
| Works with curl on laptop but fails in Java container | Different truststore/proxy/DNS | Run diagnostics from pod/VM; inspect JVM TLS config |
| Discovery returns `404` | Wrong well-known path, wrong issuer path, provider lacks that endpoint | Check OIDC vs. RFC 8414 discovery and canonical issuer URL |
| Discovery returns HTML/login page | Proxy misrouting, endpoint protected, or unexpected redirect | Inspect status, redirects, response body, ingress route |
| Metadata `issuer` mismatch | Wrong realm, external base URL, proxy scheme/host, staging/prod cross-wiring | Compare exact issuer against metadata and JWT `iss` |
| `jwks_uri` points to wrong host/tenant | Misconfigured metadata or reverse proxy; wrong hardcoded config | Use only JWKS URL matching verified issuer |
| Validly signed JWT, wrong `iss` | Token from another issuer/environment | Inspect verified token `iss` claim and config |
| Wrong JWT `aud` | Token issued for another API | Check resource indicator, client request, and audience config |
| No matching `kid` found in JWKS | Signing key just rotated, stale cache, or wrong JWKS endpoint | Inspect keyset/`kid`/rotation/caching |
| JWKS connection error on token with new `kid` | Missing egress, DNS, certificate, or JWKS outage | Check runtime → JWKS connectivity and key-dependent readiness |
| JWT `exp` expired | Old token or clock drift | Request a fresh token, verify time sync; never remove `exp` validation |
| `403` after successful token verification | Insufficient scope/authority or object permission | Inspect converter, resource policy, tenant/ownership checks |

“JWT invalid” and “TLS certificate invalid” live at **different layers**. If discovery/JWKS TLS is failing, tweaking `JwtAuthenticationConverter` will not help. If `aud`/`iss` is wrong, importing more CAs will not change the JWT contents.

### 11.1. Metadata Issuer Replaced by Internal Address

**Symptom:**

```text
Resource Server config:
  https://login.example.com/realms/orders

Metadata issuer:
  http://identity-svc:8080/realms/orders
```

The TLS connection to ingress may be completely valid, yet the metadata issuer differs from configuration. Fix the **external issuer/base URL** or forwarded headers/reverse proxy config on the Authorization Server so it publishes the real issuer, rather than letting the API accept both internal and public issuers without a contract.

### 11.2. Certificate Error in Staging While Production Works

Staging might use an internal CA, lack `login.staging.example.com` in SAN, or its container truststore might omit the right CA. How to resolve:

1. Verify the actual staging endpoint and hostname.
2. Inspect the certificate chain/SAN from staging's network.
3. Confirm the approved CA is loaded properly into the JVM truststore.
4. Verify the pod uses the right JVM image and truststore mount.
5. Re-run normal TLS verification—**never** use `--insecure` or `trustAll`.

Do not mechanically copy the production truststore to staging if the two environments have different CA policies and certificate chains.

### 11.3. Signing Key Rotation Failures

A new token carries `kid=signing-key-2026-02` while one Resource Server's JWKS cache only holds `signing-key-2026-01`. Causes can include:

- The issuer began signing with the new key before JWKS published the corresponding public key.
- A gateway/cache served overly stale JWKS.
- The Resource Server could not reach the JWKS URI when refresh was needed.
- The JWKS URI was hardcoded to an old environment/tenant.

Coordinate rotation by publishing the new public key before the issuer signs with it, retaining old keys per policy while old tokens remain valid, and monitoring verification errors. Never “fix” this by disabling signature verification.

## 12. Metadata and HTTPS with Multiple Issuers / Tenants

A Resource Server can serve multiple tenants and trust multiple Authorization Servers, yet must control the **set of permitted issuers**.

For example, an API may accept tokens from:

```text
https://login.example.com/realms/tenant-a
https://login.example.com/realms/tenant-b
```

Even sharing one TLS hostname/certificate, the two issuers can have **different metadata, JWKS, and audience contracts**.

Conditions to protect tenant boundaries:

- Allow only formally configured/registered issuers.
- Each tenant's metadata `issuer` must match that tenant's identifier exactly.
- Never treat `kid` as a global key identifier across issuers; `kid` is meaningful only within a trusted key set.
- A JWT from tenant A does not by default have access to tenant B's resources, even if the token is valid.
- If dynamically selecting an `AuthenticationManager`, use unverified data only for **preliminary routing within an allowlist**, after which the chosen decoder must still verify issuer/signature/audience.
- Never let a request specify an arbitrary `issuer_uri` or `jwks_uri` and force the server to fetch it; that pattern easily creates **SSRF** and token trust confusion.

A valid HTTPS certificate for a shared hostname does not replace distinguishing realms/tenants at the OAuth/OIDC layer.

## 13. Verification Rules That Must Never Be Bypassed

### 13.1. Never Trust Keys Fetched from Arbitrary URLs Inside the JWT

A JOSE header may carry `kid` and occasionally key-reference fields such as `jku` or `x5u`. Never let a client-sent JWT **dictate a new key source** that the Resource Server fetches and trusts.

Trust must originate from the **configured issuer/allowlist**, metadata verified over HTTPS, and a JWK Set accepted by policy. `kid` only helps select a key within that set.

### 13.2. Accept Only Contract-Permitted Algorithms

If the Authorization Server uses `RS256`, the Resource Server must verify using the matching public key and never allow a token to switch itself to `HS256` or `alg=none`.

- Restrict algorithms via appropriate decoder configuration.
- Never use RSA public key bytes as an HMAC shared secret.
- Never skip signature verification when JWKS cannot be fetched.
- For **RFC 9068** JWT access tokens, verify `typ=at+jwt` / `application/at+jwt` and required claims per profile contract.

### 13.3. Always Verify Audience and Permissions

For example, a token contains:

```json
{
  "iss": "https://login.example.com/realms/orders",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
```

It may be issued by the right issuer with a valid signature, yet the Orders API **must reject it** because `aud` does not contain `orders-api`. Even after a token passes issuer/audience/time checks, the endpoint must still enforce scopes and business permissions per order/tenant.

### 13.4. Do Not Confuse ID Tokens with Access Tokens

In OIDC, an ID token proves a login result **to the client**. Both ID tokens and access tokens may be JWSs signed by keys in the same system. If the Resource Server checks only signatures while ignoring token type and audience, it risks mistakenly accepting ID tokens.

Therefore, the contract must specify **which access token type**, which `aud`, and which validators the API accepts. Being able to fetch OIDC metadata does not authorize the API to treat ID tokens as Bearer access tokens.

### 13.5. TLS Certificates and mTLS

If the organization requires **mutual TLS (mTLS)**, the Resource Server (acting as an HTTP client when fetching metadata/JWKS) may need to present a client certificate to connect to the server. This is an **additional TLS authentication layer** requiring its own keystore/client key, separate from JWT signing keys.

mTLS can also bind access tokens to clients under corresponding OAuth profiles; that is a different contract from **the Resource Server fetching JWKS over HTTPS**. Do not confuse simply enabling standard HTTPS with having sender-constrained tokens.

## 14. Verification Across the Deployment Lifecycle

### 14.1. Before Promoting an Environment to Service

The following table can be used for cross-team handoff:

| Check | Dev | Staging | Production |
|---|---|---|---|
| Official Issuer URL confirmed | Yes | Yes | Yes |
| HTTPS endpoint uses valid certificate/CA | Yes | Yes | Yes |
| Hostname SAN matches configured URL | Yes | Yes | Yes |
| Runtime JVM trusts the right CA per policy | Yes | Yes | Yes |
| Metadata JSON valid, exact `issuer` match | Yes | Yes | Yes |
| `jwks_uri` trusted and reachable from runtime | Yes | Yes | Yes |
| Public keys/`kid` match environment tokens | Yes | Yes | Yes |
| `iss`, `aud`, `exp`/`nbf` verified | Yes | Yes | Yes |
| ID tokens or tokens from other environments rejected | Yes | Yes | Yes |
| Scopes/authorities and business permissions enforced | Yes | Yes | Yes |
| Owners and certificate/key rotation schedules/alerts defined | Yes | Yes | Yes |

This table is **technical guidance**, not output already executed on a system. Each deployment must record evidence in its real environment: endpoint, timestamp, certificate fingerprint/chain from a trusted source, metadata version, Java runtime image, and corresponding test results.

### 14.2. Monitoring While Running in Production

Monitor meaningful signals:

- Discovery/JWKS fetch failures broken down by DNS, TCP, TLS, and HTTP status.
- JWT verification failure trends by `invalid_signature`, `invalid_issuer`, `invalid_audience`, `expired`, or `unknown_kid`, without logging raw tokens.
- TLS certificate expiration dates and scheduled certificate renewals.
- Whether the issuer publishes new keys in JWKS before signing with them.
- JWKS access latency and cache status during rotation.
- `iss` drift after deployments changing ingress/hostnames.
- Issuer/truststore configuration discrepancies across replicas/pods.

Never put tokens, client secrets, private keys, refresh tokens, or sensitive personal claim data into logs/traces. Use request IDs, error codes, approved issuer identifiers, and infrastructure status for logging.

### 14.3. Responding When Discovery or JWKS Fails

Options depend on availability requirements and caching models, while the principle never changes:

- If the **required trusted key** cannot be obtained to verify a JWT, the Resource Server **cannot declare the token valid**.
- If a cached public key is present and still valid, tokens can be verified from cache per library/configuration mechanics; understand the limits when the issuer rotates/revokes keys.
- If verification cannot proceed, return an appropriate error or mark the service unready per policy—**never accept unverified tokens**.
- Fix the root cause in metadata, networking, certificates, JWKS, or rotation.
- Never switch to a “similar-looking” issuer or another environment simply because the primary environment is failing.

Protecting token verification is part of the API's security boundary, so availability goals must be met through infrastructure and caching design, never by loosening trust.

## 15. End-to-End Example: Staging from 401 to Root Cause

Suppose a staging client obtains an access token and calls:

```http
GET /api/orders/42 HTTP/1.1
Host: api.staging.example.com
Authorization: Bearer STAGING_ACCESS_TOKEN
```

The application is deployed with:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.staging.example.com/realms/orders
          audiences:
            - orders-api-staging
```

Several scenarios:

**Scenario A — Metadata issuer points to production**

```json
{
  "issuer": "https://login.example.com/realms/orders",
  "jwks_uri": "https://login.example.com/realms/orders/keys"
}
```

HTTPS may succeed, yet issuer discovery **is not staging**. Fix the Authorization Server's URL/routing/base URL or environment config. Never change `issuer-uri` to production just to make staging tokens “work”.

**Scenario B — Metadata is right, yet certificate chain lacks intermediate**

When Java connects over HTTPS, TLS validation fails and the decoder cannot fetch metadata/JWKS. Fix the certificate chain served by ingress or the truststore with the approved CA. Never enable `trustAll`.

**Scenario C — TLS and metadata are right, yet token has `aud=orders-api`**

The staging issuer emitted a token with the production audience. The JWT signature may be valid, yet the staging Resource Server must reject it because audience does not match `orders-api-staging`. Fix the resource indicator/client registration and token issuance policy at the Authorization Server.

**Scenario D — Token has right issuer/audience, yet signing key just rotated**

The new token has a `kid` not yet cached on some pods; some requests fail while other pods succeed. Check live JWKS, caching, network egress, and the rotation plan. Never disable signature verification and never hardcode old public keys permanently.

**Scenario E — Valid token, yet returns 403**

Once authentication succeeds, 403 typically indicates an **authorization** issue: missing `orders.read`, wrong scope/authority mapping, or lacking permission on order 42. Do not tweak certificates or issuer when authentication already passed.

## 16. Summary of the Mental Model

```text
TRUST CONFIGURATION
  issuer-uri = exact issuer identifier, right environment/tenant
                  │
                  ▼
DISCOVERY
  valid metadata and metadata.issuer = issuer-uri
  jwks_uri is a verified public keys source
                  │
                  ▼
TLS CONNECTION
  HTTPS → hostname/SAN → certificate chain → CA/JVM truststore
                  │
                  ▼
JWT VERIFICATION
  Right signature / algorithm / key
  Right iss / aud / exp / nbf / token type
                  │
                  ▼
API AUTHORIZATION
  scope / authority / tenant / resource permissions
```

When a **Spring Security Resource Server** uses issuer discovery, treat `issuer-uri`, discovery metadata, the HTTPS certificate chain, and JWKS as **one trust chain verified per environment**. Development, staging, and production can share the same configuration model, yet each must enforce issuer and certificate policies matching its own boundaries. **Fixing the cause at the failing layer**—discovery, TLS, JWT validation, or authorization—keeps the system working properly while preserving security requirements.

## 17. Standards and Reference Documents

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata and `.well-known` placement rules.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer, and OIDC discovery.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`, and JWT claims.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): how JWS signatures are verified.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm restrictions, issuer/audience validation, and token confusion.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, `jwk-set-uri`, `JwtDecoder`, and validators for the Servlet stack.

Standards define the **verification contract**, while network reachability and CA/truststore loading must be verified on the **specific JVM/container/host**. An issuer working on a laptop is not enough to prove the production API can fetch metadata/JWKS safely.
