# JWK, kid, Key Caching, and Signing Key Rotation

## 1. Why Are JWKS and Key Rotation Important for a JWT Resource Server?

A Spring WebFlux application protected by Spring Security OAuth2 Resource Server may receive a request:

~~~http
GET /api/key-info HTTP/1.1
Host: api.example.test
Authorization: Bearer <signed-access-token>
~~~

The Authorization Server issues JWT access tokens signed with a **private signing key**. The Resource Server must verify the signature with a matching **public verification key** before trusting the issuer, audience, subject, scopes, and other claims.

When the identity provider rotates its signing key pair:
- New JWTs may carry a new `kid` in the JOSE header.
- The public key set published via **JWKS** includes the new public key.
- Multiple WebFlux instances may still hold the **old JWKS in cache**.
- If the signer uses the new key before verifiers receive the new public key, a brand-new, valid JWT may receive **401**.
- If the old public key is removed before all access tokens signed by the old private key expire, unexpired tokens may be rejected after a cache refresh.
- If the old private key is compromised, keeping that key around too long just to “avoid 401s” allows forged JWTs to keep verifying.

This lesson covers **JWK, kid, key caching, and signing key rotation** in the context of Spring Security Reactive's **Resource Server JWT**. It is not a lesson on issuing access tokens or OAuth2 Login: the Resource Server **verifies tokens** and is not responsible for issuing JWTs to clients.

### Learning Objectives

After this lesson, you can:

1. Explain JWK, JWKS, and `kid`, distinguishing public keys from private keys.
2. Trace the flow from Bearer JWT through `NimbusReactiveJwtDecoder` to key selection, signature verification, and claims validation.
3. Analyze `kty`, `kid`, `alg`, `use`, `n`, `e`, and the private key parameters that must never be published.
4. Identify the distinct caches of the JWK source, HTTP client, CDN, and individual processes.
5. Plan a safe A → A+B → B rollout, calculating when to remove key A from token lifetime and clock skew.
6. Distinguish planned key rotation from emergency revocation when a private key is compromised.
7. Properly configure `issuer-uri`, `jwk-set-uri`, `audiences`, and allowed algorithms in Spring Boot WebFlux.
8. Run a Java 17+ project yourself with **real RSA-signed JWTs and a local JWKS server**, without needing a real IdP.
9. Recognize that `mockJwt()` or a mock decoder **does not prove** signature verification or JWKS caching works.
10. Debug 401/403, key propagation, key ID collisions, endpoint outages, and multi-region deployments.

## 2. What Is a JWK?

**JWK — JSON Web Key**, standardized in RFC 7517, is a JSON representation of a cryptographic key and its metadata. For an RSA public verification key:

~~~json
{
  "kty": "RSA",
  "kid": "signing-rsa-2027-b",
  "use": "sig",
  "alg": "RS256",
  "n": "base64url-rsa-modulus-example-only",
  "e": "AQAB"
}
~~~

This is **illustrative JSON**, not a real public key capable of verifying a JWT. `n` is the Base64URL-encoded RSA modulus, and `e` is the public exponent. For real RSA, these values must come from a securely generated key pair.

| Field | Meaning | Implementation rule |
| --- | --- | --- |
| `kty` | Key type, e.g., RSA, EC, OKP, oct | Must be compatible with the signing algorithm and key selector |
| `kid` | Key ID — identifier to look up candidate keys | Not proof of a valid signature |
| `use` | Intended use, typically `sig` | Do not use encryption-only keys to verify signatures |
| `key_ops` | Operations such as `verify` or `sign` | Must match policy if declared by the provider |
| `alg` | Intended algorithm, such as `RS256` | Never enable all algorithms based on an untrusted token |
| `n` and `e` | RSA public modulus and exponent | Safe to publish in public JWKS |
| `crv`, `x`, `y` | Common EC key components | Do not confuse with RSA modulus |
| `x5c`, `x5t` | Certificate chain/thumbprint when present | Requires trust policy; does not implicitly elevate privileges |
| `d`, `p`, `q`, `dp`, `dq`, `qi` | RSA private parameters | **Never publish in public JWKS** |
| `k` for `oct` | Symmetric secret key | Never expose on a public JWKS endpoint |

**Public keys may be published; private signing keys must remain secret** inside the Authorization Server/HSM/KMS. A Resource Server does not need the private signing key to verify RSA/ECDSA-signed JWTs. If anyone can download a private JWK from a public endpoint, it is a critical security incident requiring immediate containment and emergency key rotation.

### 2.1. JWK vs. JWT, JWS, and Access Tokens

- **JWK:** metadata and public material for a single key.
- **JWK Set/JWKS:** list of JWKs inside a `{"keys":[...]}` object.
- **JWS:** mechanism for signing payloads with JOSE; compact JWS typically has three segments.
- **JWT:** token carrying claims such as `iss`, `sub`, `aud`, `exp`.
- **OAuth access token:** credential sent to a resource server; can be a JWT or opaque.
- **OIDC ID token:** authentication result for an OAuth/OIDC client; do not use in place of an access token to a business API.

A JWT payload can be Base64URL-decoded without any secret. The signature **does not encrypt claims**, so never put passwords, private keys, access secrets, or unnecessary personal data into claims.

### 2.2. Why Use Public Keys Instead of Shared Secrets Across Multiple APIs?

If multiple resource servers share an HMAC symmetric secret, a single compromised API holds enough key material to forge new signatures. With asymmetric signing, Resource Servers normally hold only **public verification keys**; the private signing key remains within a separate trust boundary.

Of course, public keys alone do not make authorization right: the API must still verify issuer, audience, expiry, scopes, tenant, and object ownership.

## 3. JWKS: One Key Set, Multiple kids

A JWKS typically looks like:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-A",
      "use": "sig",
      "alg": "RS256",
      "n": "public-modulus-A-example",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-B",
      "use": "sig",
      "alg": "RS256",
      "n": "public-modulus-B-example",
      "e": "AQAB"
    }
  ]
}
~~~

The moduli here are schematic only, not real RSA material. The key point is that **A and B coexist** during the rollover window. Spring Security Reactive downloads JWKS and selects matching candidate keys; it does not just pick `keys[0]` or the last key by array position.

The JWKS URL is not fixed across all providers. Some providers expose OIDC Discovery/Authorization Server Metadata with a `jwks_uri` field; others provide the URI directly. Always use the **address published by the trusted issuer**, never guessing a path and assuming it is correct.

### 3.1. Distinguishing Endpoints and Contents

- `issuer-uri` identifies the issuer that the JWT `iss` must match.
- `jwk-set-uri` identifies the source of public keys used by the Resource Server.
- `audiences` identifies the resource the token must be issued for.

Having a JWKS with public keys from the right issuer **does not replace** audience validation. A web client's OIDC ID token may also be signed by the same issuer's keys; the API must still reject the ID token if `aud` does not target the API.

### 3.2. What Happens If a JWKS Contains Multiple Key Types?

A JWKS can contain RSA, EC, signing keys, and encryption keys. Key selection must inspect `kid`, `kty`, `use/key_ops`, `alg`, and the verifier's policy. Never let a client pick an arbitrary key by altering the header and bypassing signature verification.

## 4. kid Is a Selector, Not a Signature

A JWS-formatted JWT typically looks like:

~~~text
BASE64URL(protectedHeader).BASE64URL(payload).BASE64URL(signature)
~~~

Illustrative header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-B",
  "typ": "at+jwt"
}
~~~

`kid` in the JWT header helps locate the key with the matching ID in the trusted JWKS. After finding it, the verifier **must still verify the JWS signature using that public key**, and then validate claims. An attacker can write `kid=rsa-B` into a token, but unless the signature was produced by the valid private key B, the token must still be rejected.

### 4.1. Sequence from Bearer JWT to Controller

~~~text
HTTP Authorization: Bearer <JWT>
      |
      v
ServerBearerTokenAuthenticationConverter
      |
      v
JwtReactiveAuthenticationManager
      |
      v
ReactiveJwtDecoder / NimbusReactiveJwtDecoder
      |
      +--> Parse UNTRUSTED header (kid, alg)
      +--> Look up public keys from trusted JWKS/cache
      +--> Select candidates by kid/kty/use/alg
      +--> Verify JWS signature
      +--> Validate iss, aud, exp, nbf, typ/profile policy
      |
      +--> Wrong key/signature/claim: 401
      |
      v
JwtAuthenticationToken (principal=Jwt)
      |
      v
scope/scp -> SCOPE_* authorities
      |
      +--> Insufficient permission: 403
      |
      v
WebFlux controller -> service -> data
~~~

This is a conceptual pipeline; CORS/CSRF filters, matchers, and custom `SecurityWebFilterChain`s can affect the actual execution order.

### 4.2. When kid Is Missing or Unknown

JOSE does not require every token to carry `kid`; some verifiers may try candidate keys per policy. Do not promise that a token missing `kid` “always returns 401” or “is always accepted”: behavior depends on the JWK source, algorithm, and library. With multiple signing keys, the issuer should provide a **clear and stable kid**.

If a JWT carries a new `kid` while the cache holds an older set, the decoder may attempt to refresh keys per the implementation/refresh policy. Do not promise that **every unknown kid immediately triggers a JWKS fetch**, as that could also be abused for DoS.

### 4.3. Kid Collisions and Kid Reuse

RFC 7517 recommends that distinct keys within the same JWK Set use **distinct kids**. Do not rotate an RSA private key from material A to B while keeping `kid="default"` unless there is a very explicit reason/spec and thorough testing; libraries/caches may pick the wrong key or retain the old public key under the same ID.

Good design: a **versioned kid** per signing key version. Never treat `kid` as a secret or a global identifier across all issuers.

### 4.4. Never Open URLs or Files from an Untrusted kid

Wrong:

~~~java
// DANGEROUS PSEUDOCODE: kid is input from an unverified token.
Path keyPath = Path.of("/trusted-keys/" + rawKid + ".pem");
PublicKey key = readPublicKey(keyPath);
~~~

If custom code does not validate path/characters, an attacker can inject path traversal/injection. Similarly, RFC 8725 warns against using `kid` to construct unsanitized SQL/LDAP lookups.

`jku`/`x5u` in a JWT header can be attacker-supplied URLs; never follow an arbitrary URL to fetch keys — that poses SSRF and key substitution risks. For production, use a trusted issuer/JWKS URL allowlist in server configuration.

## 5. Which Classes Does Spring Security Reactive Use?

| Class | Role |
| --- | --- |
| `ServerHttpSecurity` | Reactive security DSL |
| `SecurityWebFilterChain` | WebFilter chain protecting requests |
| `ServerBearerTokenAuthenticationConverter` | Extracts Bearer token from `ServerWebExchange` |
| `JwtReactiveAuthenticationManager` | Orchestrates token authentication |
| `ReactiveJwtDecoder` | Async contract to decode/verify JWTs |
| `NimbusReactiveJwtDecoder` | Common implementation using Nimbus JOSE/JWKS |
| `JwtAuthenticationToken` | Authentication for a verified JWT |
| `JwtValidators` / `JwtClaimValidator` | Validates issuer, timestamps, audience, and extra policy |
| `ReactiveSecurityContextHolder` | Accesses `SecurityContext` inside Reactor Context |

**Do not use Servlet classes** such as `HttpSecurity`, `SecurityFilterChain`, `BearerTokenAuthenticationFilter`, and `NimbusJwtDecoder` to configure a WebFlux resource server. The `Jwt` model may be shared, but the filter chain and decoder are Reactive.

### 5.1. Automatic Detection of New Keys Does Not Mean “Instantaneous”

Per Spring Security Resource Server Reactive, the resource server can automatically pick up new public keys when the Authorization Server publishes them. However:
- Each process/instance may see a different version of JWKS.
- HTTP caches/proxies/CDNs may retain old JSON.
- A decoder with a warm cache will not necessarily observe the new key at a predictable exact instant.
- There is no guarantee every new token is accepted instantaneously after the issuer switches signing keys.
- Losing connectivity to JWKS must never turn into “skipping signature verification”.

**Therefore, safe rollover still requires pre-publishing, overlap, and operational coordination.**

### 5.2. Default Trusted Algorithms

In Spring Security 6.5 Reactive documentation, `NimbusReactiveJwtDecoder` in standard setups defaults to trusting only `RS256`. If the real provider uses RS512/ES256, review and configure the corresponding algorithm allowlist. Never accept `alg=none` or arbitrary algorithms suggested by the JWT header.

Example if you genuinely need RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - orders-api
          jws-algorithms:
            - RS512
~~~

**This is an alternative configuration** for RS512 tokens, not to be used simultaneously with the RS256 project below. If a token is signed with RS256 while the decoder only allows RS512, authentication failure is expected.

## 6. What Does the JWKS Cache Hold and Where Does It Live?

If every request called the IdP for public keys, the API would become network-bound on the request path, increasing latency and risking IdP overload under high traffic. JWKS caching lets the decoder verify many JWTs using previously fetched public keys.

| Layer | Example data | Risk when stale |
| --- | --- | --- |
| Local decoder/JWK source | JWKS JSON or candidate public keys | Has not seen B yet, or still holds A |
| HTTP client/gateway to IdP | JWKS response cache | May return an older key set |
| CDN in front of JWKS endpoint | Public JWKS JSON per edge region | One region updates slowly |
| Each WebFlux pod | Separate process-local cache | Pod 1 sees B, pod 2 does not yet |
| Custom shared cache | JWKS keyed by URL/issuer | Key collisions if trust is not partitioned properly |
| Hardcoded PEM/public key | Key snapshot from deployment | Does not follow JWKS rotation automatically |
| Browser/private cache | API responses/cookies | **Not** the Resource Server's JWT public key cache |

Do not confuse this with `CacheControl.noStore()` for HTTP responses containing sensitive data. JWKS publishes only **public keys**; the JWKS endpoint's HTTP caching policy can be public, as long as private signing keys never appear there.

### 6.1. Three Distinct “Clocks”

1. **JWT exp/nbf:** how long a token is permitted to be used.
2. **JWKS cache freshness/TTL:** how long a decoder or intermediary keeps an older key set snapshot.
3. **Rotation overlap:** how long JWKS publishes A+B concurrently so both A and B tokens remain verifiable.

For example, a 20-minute TTL for token A and a 5-minute JWKS cache does **not** mean you can remove A just 5 minutes after switching signing keys. A token A issued right before the switch can remain valid for nearly 20 minutes.

### 6.2. Do Not Copy Servlet Cache Defaults into Reactive

Spring Security Servlet documents `NimbusJwtDecoder` and its `.cache(Cache)` builder. **Reactive** uses `NimbusReactiveJwtDecoder`, which has a different builder API (e.g., `webClient(...)`, `jwtProcessorCustomizer(...)`). Do not copy:

~~~java
// DO NOT USE on the Reactive builder if the API lacks a cache method.
NimbusReactiveJwtDecoder.withJwkSetUri(uri)
        .cache(cacheManager.getCache("jwks"))
        .build();
~~~

This is a **non-compiling anti-example on the 6.5 Reactive builder**. Never claim every Reactive deployment caches for “exactly 5 minutes” based on a number from Servlet docs. If you need a rotation SLA, inspect your Spring Security/Nimbus version, JWK source type, HTTP client/caching, CDN behavior, and integration test results on your own system.

### 6.3. A JWKS HTTP Response May Carry Caching Headers

~~~http
HTTP/1.1 200 OK
Content-Type: application/jwk-set+json
Cache-Control: public, max-age=300
ETag: "keyset-version-42"
~~~

**This is an illustrative policy**, not a mandatory Spring Security/IdP default. HTTP `Cache-Control` at the issuer/CDN does not by itself prove the Nimbus Reactive decoder uses exactly 300 seconds as its TTL. You must inspect the actual caching layers governing key freshness.

### 6.4. Unknown kid Storms

If an attacker sends many JWTs with random `kid` headers, a naive implementation might fetch JWKS thousands of times, spiking IdP load and latency. Countermeasures:
- Rely on the JOSE/JWK source library's bounded refresh/caching mechanisms.
- Rate-limit/risk-control invalid requests before overload occurs.
- Never log raw `kid` as an unbounded-cardinality metric label.
- Bound response sizes and timeouts on trusted JWKS endpoints.
- Never build custom “on unknown kid, fetch unconditionally on every request” logic.

**Never fall back to accepting JWTs** when JWKS fetching fails.

## 7. Normal Rotation Plan: A → A+B → B

Recommended workflow for **planned signing-key rollover**:

1. **Generate signing key B** securely inside KMS/HSM/Authorization Server; keep private B at the signing boundary, never copying it to Resource Servers.
2. **Assign a new kid B**, distinct from kid A. Maintain a key/version inventory for auditing.
3. **Publish public B first**: JWKS serves A+B while the issuer still signs new JWTs with private A.
4. **Wait for propagation**: allow caches, CDNs, regions, and resource-server pods to receive the JWKS containing B. Canary/staging tokens can confirm this.
5. **Switch issuer to sign with B**: new JWTs carry `kid=B`; previously issued A tokens may still be valid.
6. **Keep public A+B**: both old A JWTs and new B JWTs verify during the overlap period.
7. **Wait out remaining lifetime of A tokens**: measure from *the actual last moment A was used to sign*, not just the planned schedule.
8. **Remove public A** after max token lifetime, allowed clock skew, retries/offline clients, and a safety margin.
9. **Retire private A** per key management policy, completing audit and monitoring.

~~~text
T0                 T1                  T2                   T3
|------------------|-------------------|--------------------|
JWKS: [A]          JWKS: [A,B]         JWKS: [A,B]          JWKS: [B]
Signer: A          Signer: A           Signer: B             Signer: B
                   ^                   ^                    ^
                   |                   |                    |
              Pre-publish      Switch signing        Remove A after
              public B         to private B          last A-token expiry
~~~

**The order must not be reversed**: publish B before signing with B; retain A until no A tokens must still be accepted.

### 7.1. Calculating When to Remove A

A planning condition:

~~~text
T_remove_A >= T_last_A_token_issued
              + max_validity_of_A_tokens
              + allowed_clock_skew
              + operational_safety_margin
~~~

In addition, B must be sufficiently distributed **before** switching signing. If there are variable token TTLs, token exchange, background jobs, offline clients, or multi-region signers, use the true maximum and appropriate operational scenarios.

### 7.2. Timing Example

Illustrative assumptions:
- 10:00: JWKS publishes A+B.
- 10:15: regions verified; issuer stops signing with A and starts signing with B.
- JWT A has a maximum lifetime of 20 minutes.
- Allowed clock skew is 1 minute and safety margin is 4 minutes.

Earliest time to remove A under these assumptions:

~~~text
10:15 + 20 min + 1 min + 4 min = 10:40
~~~

Do not use this timestamp on a real system if any signer still issued JWT A after 10:15 or if access tokens live longer than 20 minutes.

### 7.3. Why Not Keep A Forever?

Keeping public A after retirement leaves the trust surface wider than necessary and makes it harder to prove old signing keys have been eliminated. It may not create immediate danger while private A remains safe, but long-term operations require explicit key retirement.

### 7.4. Why Not Remove A Immediately Upon Signing with B?

Because A tokens may still have a valid `exp`. Once a decoder fetches the B-only JWKS, it will not find A; after cache refresh, a user holding an unexpired A token will receive 401. Planned rotation needs an **overlapping window**, not a single-point switch flip.

## 8. Emergency Rotation When a Private Key Is Compromised

Planned rotation optimizes for continuity. A **compromised private signing key** is a different scenario: an attacker holding private A can forge tokens with `kid` A as long as verifiers still accept public A.

Thus incident response may require:
- Immediately stopping all signing with A.
- Pre-publishing public B if feasible, and switching signers to B.
- Removing A from trust policies/JWKS **earlier** than A tokens' expiry, accepting that some legitimate tokens will get 401.
- Purging or invalidating caches where supported; verifying per instance/region.
- Possibly restarting/redeploying verifiers holding A when stale trust must be evicted faster.
- Revoking credentials/refresh tokens and coordinating with affected users/clients.
- Investigating the scope of key exposure: KMS, backups, pipelines, logs, and IAM.
- Monitoring for token substitution, forged claims, and anomalous behavior.

**Updating JWKS at the origin does not mean all caches stop trusting A immediately.** Asynchronous propagation effects belong in the playbook. Never skip signature verification or broaden allowed algorithms to “reduce 401s”.

## 9. Configuring Spring Boot WebFlux Resource Server JWT

A clear configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - orders-api
~~~

- `issuer-uri` is used to validate `iss`.
- `jwk-set-uri` specifies where to fetch public keys, avoiding JWKS URL discovery at initialization.
- `audiences` requires JWTs to be issued for the right resource server.
- Key selection uses matching headers/JWK, yet still requires signature verification.

**These URLs are example data; there is no real IdP.** Production must use trusted HTTPS issuer/JWKS. When only `issuer-uri` is configured, Spring Security 6.5 Reactive can defer discovery until the first Bearer request via `SupplierReactiveJwtDecoder`. When building a custom decoder, lazy initialization behavior can differ; never assume custom beans never contact the IdP at startup.

### 9.1. If a Custom ReactiveJwtDecoder Is Needed

Snippet example:

~~~java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuerUri),
                new JwtClaimValidator<List<String>>(
                        "aud",
                        aud -> aud != null && aud.contains("orders-api"))));
~~~

This is an **in-method snippet**, needing imports and `jwkSetUri`/`issuerUri` variables. Why configure validators explicitly: a custom `ReactiveJwtDecoder` can **replace** Boot's auto-configuration. Merely verifying the signature against a trusted JWKS **does not automatically ensure** issuer/audience match if you forget to attach validators.

### 9.2. WebClient Timeout/Proxy for JWKS

The reactive builder supports `webClient(...)`:

~~~java
// Customization snippet; requires WebClient, Reactor Netty, and imports.
WebClient jwksClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(
                HttpClient.create()
                        .responseTimeout(Duration.ofSeconds(5))))
        .build();

NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
                .webClient(jwksClient)
                .build();
~~~

If using a custom decoder bean as above, you must add the corresponding issuer and audience validators and configure algorithms matching the issuer. Never block the Reactor event loop to fetch JWKS manually with `block()` or `RestTemplate` inside `AuthenticationWebFilter`.

## 10. Runnable Java 17+ Code: Local JWKS and Rotation Tests

The project includes:
- A Spring Boot WebFlux JWT Resource Server app with public/protected routes.
- Real integration tests generating **two RSA key pairs** and genuinely signed JWS tokens, serving **public JWKS** from JDK `HttpServer` on `127.0.0.1`.
- Real `NimbusReactiveJwtDecoder` verifying signature, `iss`, `aud`, and expiry.
- HTTP tests sending Bearer headers through `SecurityWebFilterChain` with a mock decoder to verify status/authorities; **do not confuse mocks with crypto validation**.

### 10.1. Project Structure

~~~text
webflux-jwks-rotation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── JwksRotationTest.java
        └── ResourceServerHttpTest.java
~~~

### 10.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-jwks-rotation'
~~~

### 10.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('compileTestJava') {
    options.compilerArgs.addAll(['--add-modules', 'jdk.httpserver'])
}

tasks.named('test') {
    useJUnitPlatform()
    jvmArgs '--add-modules', 'jdk.httpserver'
}
~~~

Gradle requires JDK 17+ and compatible dependencies. Test code uses `com.sun.net.httpserver.HttpServer` from the `jdk.httpserver` module to run a local server. No real IdP is started and no extra mock-server dependency is needed.

### 10.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-jwks-rotation
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - orders-api
~~~

When running the app without an IdP, the public endpoint still works; protected JWT requests cannot verify against the placeholder URLs. Tests use local JWKS or a mocked decoder, requiring no connection to the dummy hostname.

### 10.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Bearer-only ONLY: no browser cookie login/Basic.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/key-info")
                                .hasAuthority("SCOPE_keys.read")
                        .pathMatchers(HttpMethod.GET, "/api/subject")
                                .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

`NoOpServerSecurityContextRepository` does not persist authentication across sessions, though it does not forbid `WebSession` usage in unrelated code. `csrf(...disable)` here **applies only to this Bearer-only demo API**; if the system uses cookies/Basic/form/OIDC login with browser ambient credentials, design CSRF per security chain/route.

### 10.7. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/key-info")
    public Mono<Map<String, String>> keyInfo(
            @AuthenticationPrincipal Jwt jwt) {

        Object kid = jwt.getHeaders().get("kid");
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "kid", kid == null ? "absent" : kid.toString()));
    }

    @GetMapping("/api/subject")
    public Mono<Map<String, String>> subject(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }
}
~~~

The `/api/key-info` endpoint returns `kid`/subject **solely for post-authentication illustration**; production may restrict or omit key identifiers, and must never return raw JWTs, private keys, access tokens, or all claims. `kid` alone does not guarantee token safety—only passing signature verification and validators lets the controller run.

## 11. JwksRotationTest.java — Real RSA Signing, Local Public JWKS

Create `src/test/java/demo/JwksRotationTest.java`:

~~~java
package demo;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JwksRotationTest {

    private static final String ISSUER =
            "https://idp.example.test/issuer";
    private static final String AUDIENCE = "orders-api";

    private HttpServer server;
    private final AtomicReference<String> jwks =
            new AtomicReference<>();
    private KeyMaterial keyA;
    private KeyMaterial keyB;

    private record KeyMaterial(
            String kid, RSAPrivateKey privateKey, RSAKey publicJwk) {
    }

    @BeforeEach
    void setup() throws Exception {
        keyA = generateKey("rsa-A");
        keyB = generateKey("rsa-B");
        publish(keyA);

        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/jwks", exchange -> {
            byte[] body = jwks.get()
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/jwk-set+json");
            exchange.getResponseHeaders().set(
                    "Cache-Control", "no-cache");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
    }

    @AfterEach
    void cleanup() {
        if (server != null) {
            server.stop(0);
        }
    }

    private static KeyMaterial generateKey(String kid)
            throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        RSAKey publicJwk = new RSAKey.Builder(
                (RSAPublicKey) pair.getPublic())
                .keyID(kid)
                .keyUse(KeyUse.SIGNATURE)
                .algorithm(JWSAlgorithm.RS256)
                .build();
        return new KeyMaterial(
                kid,
                (RSAPrivateKey) pair.getPrivate(),
                publicJwk);
    }

    private void publish(KeyMaterial... keys) {
        // Only public JWKs are serialized to the HTTP endpoint.
        List<JWK> publicKeys = Arrays.stream(keys)
                .map(k -> (JWK) k.publicJwk())
                .toList();
        jwks.set(new JWKSet(publicKeys).toString());
    }

    private NimbusReactiveJwtDecoder decoder() {
        String uri = "http://127.0.0.1:"
                + server.getAddress().getPort() + "/jwks";
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withJwkSetUri(uri).build();

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(
                                ISSUER),
                        new JwtClaimValidator<List<String>>(
                                "aud",
                                aud -> aud != null
                                        && aud.contains(AUDIENCE))));
        return decoder;
    }

    private static String sign(
            KeyMaterial signingKey,
            String issuer,
            String audience,
            Instant expiresAt) throws JOSEException {

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("reader-42")
                .audience(audience)
                .issueTime(Date.from(now.minusSeconds(20)))
                .notBeforeTime(Date.from(now.minusSeconds(20)))
                .expirationTime(Date.from(expiresAt))
                .claim("scope", "keys.read")
                .build();

        SignedJWT signedJwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID(signingKey.kid())
                        .build(),
                claims);
        signedJwt.sign(
                new RSASSASigner(signingKey.privateKey()));
        return signedJwt.serialize();
    }

    private String validToken(KeyMaterial key)
            throws JOSEException {
        return sign(key, ISSUER, AUDIENCE,
                Instant.now().plusSeconds(600));
    }

    @Test
    void firstVersionValidWithAOnly() throws Exception {
        StepVerifier.create(
                decoder().decode(validToken(keyA)))
                .assertNext(jwt -> {
                    assertEquals("reader-42", jwt.getSubject());
                    assertEquals("rsa-A",
                            jwt.getHeaders().get("kid"));
                })
                .verifyComplete();
    }

    @Test
    void overlapAllowsBothOldAndNewTokens()
            throws Exception {
        publish(keyA, keyB);
        String a = validToken(keyA);
        String b = validToken(keyB);

        NimbusReactiveJwtDecoder d = decoder();

        StepVerifier.create(d.decode(a))
                .assertNext(jwt -> assertEquals("rsa-A",
                        jwt.getHeaders().get("kid")))
                .verifyComplete();
        StepVerifier.create(d.decode(b))
                .assertNext(jwt -> assertEquals("rsa-B",
                        jwt.getHeaders().get("kid")))
                .verifyComplete();
    }

    @Test
    void freshDecoderAfterRetirementRejectsA()
            throws Exception {
        String tokenA = validToken(keyA);
        publish(keyB);

        StepVerifier.create(decoder().decode(tokenA))
                .expectError(JwtException.class).verify();

        StepVerifier.create(
                decoder().decode(validToken(keyB)))
                .assertNext(jwt -> assertEquals("rsa-B",
                        jwt.getHeaders().get("kid")))
                .verifyComplete();
    }

    @Test
    void signedTokensWithWrongClaimsAreRejected()
            throws Exception {
        NimbusReactiveJwtDecoder d = decoder();

        String wrongIssuer = sign(keyA,
                "https://other.example.test", AUDIENCE,
                Instant.now().plusSeconds(600));
        String wrongAudience = sign(keyA,
                ISSUER, "other-api",
                Instant.now().plusSeconds(600));
        String expired = sign(keyA,
                ISSUER, AUDIENCE,
                Instant.now().minusSeconds(3600));

        StepVerifier.create(d.decode(wrongIssuer))
                .expectError(JwtException.class).verify();
        StepVerifier.create(d.decode(wrongAudience))
                .expectError(JwtException.class).verify();
        StepVerifier.create(d.decode(expired))
                .expectError(JwtException.class).verify();
    }

    @Test
    void kidAWithPrivateKeyBFailsSignature()
            throws Exception {
        // Header kid A, but signature generated by private B.
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(ISSUER)
                .subject("reader-42")
                .audience(AUDIENCE)
                .issueTime(Date.from(
                        Instant.now().minusSeconds(20)))
                .expirationTime(Date.from(
                        Instant.now().plusSeconds(600)))
                .build();

        SignedJWT forgery = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID("rsa-A").build(),
                claims);
        forgery.sign(new RSASSASigner(
                keyB.privateKey()));

        StepVerifier.create(
                decoder().decode(forgery.serialize()))
                .expectError(JwtException.class).verify();
    }
}
~~~

### 11.1. Five Verified Behaviors

1. **Real RSA signature:** with only public A in JWKS, tokens signed with private A and valid issuer/audience verify.
2. **Overlap:** when JWKS contains public A+B, the decoder accepts both JWT A and B.
3. **Removing A:** a **fresh decoder** seeing B-only JWKS rejects JWT A and accepts JWT B.
4. **Wrong claims:** validly signed tokens with wrong issuer, audience, or expiration are rejected.
5. **Forged kid:** header claiming kid A signed with private B fails signature verification.

**This test does not prove caches automatically refresh instantaneously.** Each phase uses a fresh decoder or sees A+B JWKS from the start. To test stale-key caching, reuse a decoder warmed with A, change the test server's JWKS, and measure refresh behavior over time/conditions for your specific version.

`HttpServer` runs on localhost over HTTP **solely for testing**; production JWKS uses HTTPS/trusted issuers with no private material in responses. RSA private keys live only in test memory and are never serialized by `publish`.

## 12. ResourceServerHttpTest.java — HTTP 401/403 with Mock Decoder

The second test class sends Bearer headers through the WebFlux `SecurityWebFilterChain`. It uses `@MockitoBean ReactiveJwtDecoder` to simulate decoded JWTs, so it **does not test signatures or JWKS caching**.

`src/test/java/demo/ResourceServerHttpTest.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ResourceServerHttpTest {

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        when(jwtDecoder.decode("read-token"))
                .thenReturn(Mono.just(jwt(
                        "read-token", "keys.read")));
        when(jwtDecoder.decode("other-scope-token"))
                .thenReturn(Mono.just(jwt(
                        "other-scope-token", "profile")));
        when(jwtDecoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("invalid test JWT")));
    }

    private Jwt jwt(String value, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .header("kid", "rsa-A")
                .claim("iss", "https://idp.example.test/issuer")
                .claim("sub", "reader-42")
                .claim("aud", List.of("orders-api"))
                .claim("scope", scope)
                .issuedAt(now.minusSeconds(30))
                .expiresAt(now.plusSeconds(600))
                .build();
    }

    @Test
    void publicPingIs200() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void noBearerIs401() {
        client.get().uri("/api/key-info")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueMatches(
                        "WWW-Authenticate", "Bearer.*");
    }

    @Test
    void invalidJwtIs401() {
        client.get().uri("/api/key-info")
                .headers(h -> h.setBearerAuth("bad-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongScopeIs403() {
        client.get().uri("/api/key-info")
                .headers(h -> h.setBearerAuth(
                        "other-scope-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void correctScopeYieldsSafeKidMetadata() {
        client.get().uri("/api/key-info")
                .headers(h -> h.setBearerAuth("read-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("reader-42")
                .jsonPath("$.kid").isEqualTo("rsa-A")
                .jsonPath("$.tokenValue").doesNotExist();
    }

    @Test
    void authenticatedSubjectRouteNeedsNoReadScope() {
        client.get().uri("/api/subject")
                .headers(h -> h.setBearerAuth(
                        "other-scope-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("reader-42");
    }

    @Test
    void undefinedRouteIsDenied() {
        client.get().uri("/api/undefined")
                .headers(h -> h.setBearerAuth("read-token"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

What the tests prove:
- Public route returns 200.
- Protected route with missing/invalid Bearer → 401, typically with a Bearer challenge.
- Valid mock Jwt lacking `SCOPE_keys.read` → 403.
- Correct scope → 200 and controller returns only permitted metadata.
- A route requiring only `authenticated` does not require `keys.read`.
- Undeclared routes are denied per `anyExchange().denyAll()`.

**Do not** send `read-token` or `other-scope-token` to production: they are not three-part signed JWTs and are accepted only by the mock decoder in tests.

## 13. Running Gradle, curl, and Expected Outcomes

In the project directory:

~~~bash
gradle test
~~~

Or use `./gradlew test` if a Gradle Wrapper is generated. Across the test classes above, **12 @Test methods** are expected (5 real JWT/JWKS signing + 7 HTTP mocked decoder). These tests must be run to confirm compilation and behavior in the learner's environment; **no claim is made here that Gradle was executed**.

Run the app:

~~~bash
gradle bootRun
~~~

Then:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expect 200 and body `pong`.

~~~bash
curl -i http://localhost:8080/api/key-info
~~~

Expect 401 along with `WWW-Authenticate: Bearer` for requests without a token.

~~~bash
curl -i http://localhost:8080/api/key-info \
  -H 'Authorization: Bearer not-a-real-signed-jwt'
~~~

This string is not a valid JWS, so authentication must reject it; **401** is typical. Since JWKS config in `application.yml` points to a dummy hostname, specific network failure/exception handling can affect the response; see the real-signed JWT tests in Section 11 for IdP-independent signature testing.

### 13.1. Testing Against a Real IdP in Staging

After replacing issuer/JWKS with a trusted provider, obtain a valid access token with `aud=orders-api` and `scope=keys.read` via the appropriate grant, then call:

~~~bash
curl -i https://api-staging.example.test/api/key-info \
  -H 'Authorization: Bearer <staging-access-token>'
~~~

This is a template; there is no real token. Avoid storing production tokens in shell history or public logs. Valid JWT + right scope → 200; wrong JWT signature/issuer/audience/expiry → 401; valid JWT lacking scope → 403.

### 13.2. Real JWT Tests vs. mockJwt() Tests

| Test type | Real Bearer header? | Real RSA/JWS verify? | What can be concluded |
| --- | --- | --- | --- |
| `mockJwt()` | Not required | No | Authorization/controller once authenticated |
| `ResourceServerHttpTest` mock decoder | Yes | No | Bearer filter, scope mapping, 401/403/200 |
| `JwksRotationTest` JDK HTTP JWKS | Direct decode | **Yes** | Signature/kid/issuer/aud/expiry and key overlap with fresh decoders |
| Reused warm decoder + JWKS change | Depends on test | Yes | Cache refresh/stale-key behavior for a specific version |
| Real IdP staging | Yes | Yes | Network/proxy/TLS/JWKS/CDN/rotation end-to-end |

Passing one test type does not automatically prove every layer; in particular, **`mockJwt()` neither signs JWTs nor verifies kid**.

## 14. Methodical Stale-Cache Testing

Tests in the project swap public keys at the JWKS endpoint but **instantiate fresh decoders** when observing a fixed snapshot. To measure caching:
1. Create decoder D when JWKS serves only A.
2. Decode JWT A so D loads/caches JWKS A.
3. Publish A+B; measure whether D accepts token B and after how long.
4. Repeat under realistic network and TTL conditions; never assume an unknown `kid` always fetches immediately.
5. Publish B-only; measure how long D continues accepting JWT A.
6. Compare with a fresh decoder D2 initialized on B-only; D2 will not have A.
7. Add 2–3 decoder instances to simulate multiple pods.
8. Simulate JWKS 503/timeout/invalid JSON and bounded unknown-kid bursts.
9. Check HTTP caching at proxies/CDNs if present; measure fetch count and latency.
10. Tie results to the exact Spring Security/Nimbus version and configuration.

**Do not write `Thread.sleep(300)` and treat it as Spring's SLA.** Timing depends on schedulers, event loops, cache implementations, HTTP clients, and networks. Timeout/cache tests need reliable bounds and product policies rather than extrapolation from a single local run.

### 14.1. Why Can Wrong Cache Hits Be a Major Issue?

If a cache retains public key A after the issuer removed A, an A-signed JWT with a valid signature and unexpired claims **can** still verify on an instance until its cache updates. That is why emergency compromise response cannot rely solely on a new JWKS HTTP response.

Conversely, when a fresh cache lacks B, token B can get 401 even when signed properly by the new issuer key. Pre-publishing B and waiting for propagation shrinks this window.

## 15. Key Rotation Symptoms and Causes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Token B gets 401 right after switch | Public B has not reached cached JWKS | Pre-publish B, measure propagation |
| Unexpired Token A gets 401 while B works | A removed too early | Overlap until A tokens expire |
| Only one pod/region returns 401 | Out-of-sync local cache/edge | Inspect key set per instance |
| `kid` exists in JWKS but signature fails | Wrong private key or tampered token | Check signer and JOSE signature |
| Same `kid` but different key bytes | Kid reused/collision | Assign a distinct kid per key version |
| All tokens return 401 after deploy | Wrong issuer/audience/alg/JWKS URL | Check trust configuration |
| Token verified, but API returns 403 | Insufficient scope/role/tenant | Check authorization; do not blame JWKS |
| JWKS endpoint returns 5xx | IdP/network outage | Resilience; never bypass verification |
| JWKS endpoint returns private key | Key disclosure | Incident response / immediate rotation |
| Issuer A has `kid=default` and Issuer B does too | Multi-tenant key collision in shared cache | Partition by trusted issuer |
| 401 spike + heavy JWKS fetches | Unknown-kid flooding or cache misses | Rate limits, refresh bounds |
| B accepted only after restart | Decoder/cache not refreshing as expected | Check TTL/library/cache config |
| Token uses `ES256`, decoder only `RS256` | Algorithm policy mismatch | Review then configure trusted alg |
| API accepts ID token due to shared issuer/JWKS | Audience/token-type confusion | Validate `aud`/`typ`/scope |

Never fix these errors with `alg=none`, disabling issuer/audience validation, or accepting arbitrary request-supplied public keys.

## 16. Monitoring and Operational Runbook

Useful metrics:
- 401 rate by route, instance, region, and signer switch timestamps.
- JWT validation failures categorized as “unknown key”, “signature”, “issuer”, “audience”, “expiry” at a level that **exposes no secrets** and aligns with library instrumentation.
- JWKS fetch successes/errors/timeouts/latency.
- Controlled key-set version or trusted kid list; never use attacker-supplied `kid` as an unbounded metric label.
- Cache refresh count/age when exposed by the JWK source.
- Canary A/B token validation in permitted environments.
- IdP key rotation events and publish/sign/removal timelines.

On-call steps when JWT B returns 401:
1. Identify when token B was signed and what `kid` it carries.
2. Verify whether the trusted origin JWKS URL already includes B.
3. Check if CDNs/edges/proxies are still serving A-only JWKS.
4. Check issuer, audience, and allowed algorithm configuration on the resource server.
5. Check individual pods/regions rather than only the aggregate load balancer.
6. Use a valid test token without logging raw JWTs.
7. If B has simply not propagated yet, consider delaying the signing switch per runbook.
8. If A was compromised, execute the emergency procedure — do not re-enable A merely to stop 401s.
9. Review TTL, propagation, rollback, and key publication pipelines.

### 16.1. Safe Logging

Log only route templates, status, correlation IDs, validation failure categories, latency, or normalized key versions. Never log `Authorization` headers, raw JWTs, signing keys, private JWKs, full claims containing PII, or tokens in URLs. Since JWT headers/`kid` come from untrusted input, bound cardinality before indexing them as labels or log fields.

## 17. Multi-Issuer and Key Trust Boundaries

In a multi-issuer system:
- Issuer A and B may both use `kid="key-1"` with different public keys.
- A global map keyed **solely by kid** is the wrong model.
- Trust must be separated by approved issuer/JWKS source and audience/resource policy.
- Unverified `iss` claims from payloads may only act as a **routing hint into an allowlist**, never as an arbitrary URL to fetch JWKS.
- If using `JwtIssuerReactiveAuthenticationManagerResolver`, allow only trusted issuers; never accept dynamic issuers from the Internet.
- After signature verification, still check tenant/ownership and API scopes.

Model:

~~~text
trusted issuer A -> decoder A -> JWKS A -> allowed API audiences -> tenant A policy
trusted issuer B -> decoder B -> JWKS B -> allowed API audiences -> tenant B policy
unrecognized issuer -> reject
~~~

Token substitution risk: the same issuer may issue ID tokens for another client and access tokens for other APIs. **Same signature/kid does not mean same purpose**. Verify `aud`, access-token profile (RFC 9068 where applicable), and role/permission policy.

## 18. Pre-Production Checklist

### JWK/JWKS
- [ ] Public JWKS contains **no** private RSA parameters or symmetric secret `k`.
- [ ] Signing private keys stay in IdP/KMS/HSM, never distributed to APIs.
- [ ] Distinct `kid` per key material; avoid reuse/collision within an issuer.
- [ ] JWK `kty`, `use/key_ops`, `alg` match signature verification.
- [ ] JWKS URL/issuer pinned or allowlisted, over secure HTTPS/TLS.
- [ ] No arbitrary `jku`/`x5u` or unsafe `kid` file/SQL lookups.
- [ ] Do not pick keys by array index `keys[0]`.
- [ ] Never skip signature verification due to cache errors.

### Caching and Rotation
- [ ] Known Spring Security/Nimbus version and actual JWK caching behavior.
- [ ] Cache TTL, unknown-kid behavior, timeouts, and CDN tested.
- [ ] Public B pre-published before the issuer switches signing to B.
- [ ] A+B retained while A tokens remain unexpired.
- [ ] Formula using max TTL + skew + margin governs A removal.
- [ ] Monitoring for A/B canary, JWKS fetches, and 401s per pod/region.
- [ ] Controlled rollback plan exists for planned rotation.
- [ ] Separate **emergency** key-compromise runbook exists apart from planned rotation.
- [ ] Plan exists to handle stale caches if A is compromised.
- [ ] Multi-issuer caches partitioned by trust source.

### Spring Reactive Security
- [ ] Correct `ServerHttpSecurity`/`SecurityWebFilterChain`/`ReactiveJwtDecoder`.
- [ ] JWT `iss`, `aud`, `exp`/`nbf`, and allowed algorithms validated.
- [ ] ID tokens never used as Bearer access tokens.
- [ ] `SCOPE_`/role mapping and object/tenant authorization checked separately.
- [ ] CSRF disabled only when Bearer-only with no browser ambient credentials per threat model.
- [ ] CORS preflight not wrongly intercepted by authentication in SPAs.
- [ ] Never log raw JWTs, private keys, or sensitive credential metadata.
- [ ] Never call `block()` inside the reactive authentication path.

### Testing
- [ ] RSA-signed JWT A succeeds against public JWK A.
- [ ] JWKS A+B accepts JWTs signed by A and B.
- [ ] Fresh decoder on B-only JWKS rejects JWT A.
- [ ] JWT with wrong `iss`/`aud`/`exp` fails despite valid signature.
- [ ] Kid A + private B fails signature check.
- [ ] HTTP Bearer missing token 401; missing scope 403; right scope 200.
- [ ] Warm-cache behavior tested separately, not inferred from fresh decoders.
- [ ] Unknown-kid flooding / JWKS outages are bounded.
- [ ] Multi-instance/region canary and emergency rotation rehearsed.

## 19. Self-Check Questions

**1. How do JWK and JWKS differ?**

> A JWK describes one key; a JWKS contains a set of keys in a JSON `keys` structure.

**2. Is `kid` a secret?**

> No. It is an identifier for looking up candidate public keys; signature and claims must still be verified.

**3. What are `n` and `e` in an RSA public JWK used for?**

> Constructing the RSA public verification key; the private signing exponent is not needed to verify.

**4. Can RSA private `d` be exposed on a JWKS endpoint?**

> No. That exposes the signing key and enables forging JWTs.

**5. Why is there an A+B JWKS phase?**

> So both old A tokens and new B tokens can verify during rollout.

**6. Why must B be published before the signer uses B?**

> Resource Servers and caches need to know public B; otherwise B tokens may receive 401.

**7. When should A be removed in a planned rotation?**

> After the last A token could still be valid plus clock skew and a design safety margin.

**8. If private A is compromised, should you wait for all A tokens to expire?**

> Not by default; rapid emergency revocation is usually required, accepting that legitimate tokens get rejected.

**9. Does JWT `exp` mean the same thing as JWKS cache TTL?**

> No. One is the token's lifetime; the other is the freshness of cached public keys.

**10. Why shouldn't Servlet `NimbusJwtDecoder.cache(...)` be used in Reactive?**

> They are different builders; consult the `NimbusReactiveJwtDecoder` API for your version.

**11. What if a JWT has a valid `kid` but is signed by a different private key?**

> Signature verification fails; `kid` does not replace the signature.

**12. Can two issuers' JWKS collide on `kid`?**

> Yes; never merge key stores solely by `kid`—preserve trust boundaries per issuer.

**13. Must an HTTP JWKS endpoint always return `max-age=300`?**

> No. That is an example; TTL must fit your rotation/cache SLA and library behavior.

**14. Why doesn't `mockJwt()` prove key rotation is safe?**

> Mocks bypass RSA verification and JWKS lookup; you must use real signed JWTs and a real decoder.

**15. If B tokens return 401 on only some pods, what do you check first?**

> Local caches, JWKS CDN/edge propagation, trusted issuer/JWKS config, algorithms, and network.

**16. Does key rotation automatically issue new tokens to clients?**

> No. The Resource Server only verifies; the Authorization Server and OAuth Client handle token issuance/refresh.

## 20. Summary and Official References

With **Spring Security Reactive Resource Server JWT**, a valid JWT needs more than a matching `kid` header. The Resource Server must fetch **public keys from a trusted JWKS**, pick candidates per key/algorithm policy, verify the signature and check `iss`, `aud`, `exp`/`nbf`, and only then enforce scopes/roles/tenant/ownership.

Normal rollover flow:

~~~text
Generate private/public B
    -> Publish public A+B
    -> Allow time for JWKS caches and regions to observe B
    -> Switch signer A to B
    -> Keep A+B until last A token can no longer be accepted
    -> Remove public A, retire private A and monitor
~~~

When a key is compromised, an emergency plan is required to revoke trust in A early, even if some older JWTs get 401. Do not treat Servlet cache TTLs as promises for Reactive, and never treat a fresh-decoder test as proof that a warm cache refreshed; always measure on your actual dependency versions and infrastructure.

### Official References

- Spring Security 6.5 — OAuth2 Resource Server JWT (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Bearer Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html
- Spring Security 6.5 — WebFlux OAuth2 Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security Javadoc — NimbusReactiveJwtDecoder: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- Spring Security Javadoc — JwkSetUriReactiveJwtDecoderBuilder: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder.html
- Spring Boot 3.5 — Spring Security: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- RFC 7517 — JSON Web Key: https://www.rfc-editor.org/rfc/rfc7517
- RFC 7515 — JSON Web Signature: https://www.rfc-editor.org/rfc/rfc7515
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750