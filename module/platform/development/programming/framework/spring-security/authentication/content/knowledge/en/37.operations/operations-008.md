# Rotating Keys, API Keys, and Certificates in Spring Security Authentication Operations

## 1. Why Must Secrets and Keys Be Rotated?

**Rotation** is the controlled process of introducing new secrets/keys into active use and phasing out old ones. Its purpose is to limit how long a compromised credential can be exploited, maintain cryptographic compliance, prevent sudden certificate expirations, and make changing security assets a testable, rollback-capable, auditable routine.

In a Spring Security authentication system, at least four artifact types have distinct lifecycles:

1. **JWT / JWS signing keys:** the Authorization Server or IdP holds the **private signing key**; the Resource Server fetches the **public verification key** via JWKS or trusted configuration. Rotation affects unexpired tokens, JWK caches, `kid`, and algorithms.
2. **API keys / client secrets:** confidential credentials used by applications or integration clients. Rotation usually requires **two temporarily valid keys**, client updates, monitoring old-key usage, and intentional revocation.
3. **TLS / mTLS X.509 certificates:** include the leaf certificate, matching private key, intermediate chain, and client/server **trust anchors**. Rotation happens at TLS termination points, reverse proxies, HTTP clients, or service meshes. TLS certificates are **not** JWT signing keys merely because both use RSA/EC.
4. **Symmetric keys or data encryption keys:** HMAC JWTs, application secrets, encryption keys, or KEKs may require **decrypting/verifying older versions** while encrypting/signing only with the new key. Rotating the key does not automatically re-encrypt legacy data or revoke already-issued tokens.

Different rotation cases:

| Artifact | Who Holds the Secret/Private Key? | Who Must Be Updated? | When Is Rotation Complete? |
| --- | --- | --- | --- |
| JWT asymmetric signing key | Authorization Server/HSM/KMS | JWKS and all Resource Server verifiers | New tokens signed with K2; old JWTs age out per TTL; K1 retired on schedule |
| HMAC secret | Both signer and verifier know the secret | All verifiers and the signer | K2 creates MACs; K1 stops verifying once no valid messages remain |
| API key | Client sends key; server stores hash/metadata | Each client/integration and auth service | All clients use new key; old key revoked, old usage = 0 |
| TLS server certificate | TLS terminator (Ingress/Proxy/embedded server) holds private key | Server endpoints, sometimes client truststores | New cert served, hostname/chain valid, old key no longer used |
| mTLS client certificate | Client holds private key | Client, server trust policy/identity mapping | New client completes handshakes; old cert blocked per policy |
| Encryption-at-rest key | KMS/HSM or app, per envelope design | Encrypt/decrypt services and key metadata | New data uses new key; legacy data readable or rewrapped/re-encrypted |

**Warning:** "Rotation finished" does not mean "all old credentials are immediately invalid". Planned rotation usually requires an overlap window to avoid downtime; when **key compromise is suspected**, keeping an old overlap extends the attacker's access window. You must run an **incident runbook** distinct from maintenance rotation.

## 2. Lifecycle and Trust Boundaries per Artifact

### 2.1. Standard Lifecycle

```text
Inventory & owner
      |
      v
Generate K2 with CSPRNG / approved KMS/HSM
      |
      v
Store securely -> authorize access -> tag version and purpose
      |
      v
Deploy verification/trust for K2 BEFORE active use (where needed)
      |
      v
Switch producer/signing/encryption/client to K2
      |
      v
Observe traffic: K1 last-used, K2 success, error rate, latency
      |
      v
Retire K1 by policy; revoke when necessary
      |
      v
Delete/destroy unused material according to retention/backup rules
      |
      v
Audit evidence & next rotation schedule
```

To control changes, maintain a **credential inventory** listing owner, issuer, environment, purpose, key ID/certificate serial, service dependencies, creation/expiration timestamps, rotation schedule, approvers, and rollback plan. Never store raw secrets in the inventory.

### 2.2. Distinguishing Operations

- **Generate:** create a new key/secret with policy-compliant entropy, algorithm, and size. Private keys are not something copied out of source repositories.
- **Publish trust:** deliver a new public JWK/valid trust anchor to verifiers or issue a new API key to a verified client.
- **Activate:** the producer begins signing/encrypting/sending the new credential; keep this separate from publishing trust.
- **Expire:** a token/certificate reaches `exp`/`notAfter` over time; does not mean the key was revoked.
- **Retire:** stop issuing new credentials with the old key, then stop verifying/accepting it once the validity window ends.
- **Revoke:** intentionally reject a credential/key immediately per policy, potentially disrupting unexpired tokens/certs.
- **Destroy:** erase private/secret material after ensuring no legitimate decryption, investigation, or recovery needs remain; backups and recovery keys require separate policy.

### 2.3. Role of KMS/HSM/Secret Manager

Never put private keys, API keys, or keystore passwords directly in Git, Docker images, issue trackers, or logs. Choose a secret manager/KMS/HSM with IAM permissions, auditing, versioning, rotation policies, and restricted private-key export. With an HSM, **non-exportable** keys reduce risk, though they do not eliminate signing abuse if KMS credentials are stolen. Separate permissions for creating, activating, revoking, and reading metadata; enforce **least privilege** and audited break-glass access.

Different data sources require different trust handling:

- **Configured JWKS URL from a trusted issuer:** public verification keys may be downloaded from the trusted IdP endpoint. It is **not** a place to store private signing keys.
- **Client-supplied JWS header:** `kid`/`alg` inside a token are **untrusted input** that must be checked against an allowlist and predefined key set.
- **Certificate from a TLS peer:** must validate chain, SAN, validity window, EKU, and expected identity; accepting an arbitrary certificate grants no authority in Spring Security.
- **API key received over HTTP:** a bearer secret; simply looking up a key ID/hash does not replace verifying owner, status, expiry, and permissions.

## 3. Rotating JWT Signing Keys via a JWK Set: K1 → K2

### 3.1. JWT and JWKS Flow in Spring Security

In an OAuth2/OIDC system:

```text
Authorization Server / IdP
  Private signing key K1
     |
     | sign JWT {iss, aud, sub, exp, ...} ; JWS protected header kid=k1
     v
Client receives Bearer JWT
     |
     | Authorization: Bearer <jwt>
     v
Spring Security Resource Server
  NimbusJwtDecoder / JwtAuthenticationProvider
     |
     | fetch JWKS from issuer-configured trusted URL (cached)
     | select public key by kid and algorithm policy
     | verify signature + iss/aud/exp/nbf + roles/scopes
     v
Authentication / authorization -> API resource
```

An illustrative JWKS containing only **public** fields:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "auth-2026-10-k1",
      "n": "<public-rsa-modulus>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "auth-2026-11-k2",
      "n": "<new-public-rsa-modulus>",
      "e": "AQAB"
    }
  ]
}
```

This is **mock JSON**; `n` is a placeholder, not a valid JWK for verification. For RSA, a private JWK may contain `d`/`p`/`q`/`dp`/`dq`/`qi`, which must **never be published** in public JWKS. `kid`, `kty`, `alg`, and `use` help select/constrain keys; `kid` alone **does not prove** the endpoint supplying the key is trustworthy.

**Prevent key injection:** never automatically fetch attacker-controlled `jku`/`x5u` URLs from JWS headers, and never accept `alg=none` or arbitrary HS256/RS256 switching. Trust anchors are the **controlled issuer + JWKS URI/operator config**, not links inside the token. `iss`/`aud`, key type, algorithm, and tenancy must match policy.

### 3.2. Planned Zero-Downtime Rotation Workflow

Suppose K1 signs JWTs with a max TTL of 15 minutes and verifiers cache JWKS for a few minutes:

1. **T-1: Prepare K2.** Generate a new key pair in KMS/HSM or a protected keystore; assign a `kid=k2` **distinct** from k1. Never reuse K1 under a new kid.
2. **T0: Publish public K2 while still signing with K1.** Trusted JWKS must contain both K1 and K2 simultaneously. Verify live endpoints, HTTP caches/CDNs, regions, and that every Resource Server can fetch public K2.
3. **T0 + propagation:** wait for JWKS cache refresh accounting for edges, failovers, and networks. Spring Security 6.5 reference notes Resource Server caches JWK sets in memory for roughly **5 minutes** by default; custom caches/CDNs may vary. Never switch the signer before verifiers see K2.
4. **T1: Switch active signing key to K2.** New JWTs carry `kid=k2` and are signed with private K2. From now on, **stop issuing new JWTs with K1**. Public K1 remains in JWKS so unexpired JWTs keep verifying.
5. **T1 + TTL + skew/buffer:** wait until **the last JWT signed with K1** has expired under verification rules, including allowed clock skew, processing delays, and edge consumers. For example, if the last K1 JWT was signed at 09:00 with a 15-minute TTL and 1-minute skew → keep public K1 past **09:16** (plus SLO buffer).
6. **Retire K1 public trust:** remove K1 from JWKS once no valid tokens depend on it; canary across APIs/regions; monitor `kid not found`, 401s, and JWT signature errors. Then disable/destroy private K1 per retention/break-glass policy. Private K1 should have **stopped signing right at T1**.
7. **Audit/close:** record change ID, owner, publish/switch/retire timestamps, verifier health, remaining K1 JWT/old-kid attempts (without secrets), and the next scheduled rotation.

**The overlap window is not an arbitrary 5 minutes.** It depends on when the **last** K1 token was issued, max token lifetime, allowed skew, JWKS distribution, and intermediate caches. If JWT TTL is 2 hours, removing public K1 after 5 minutes will trigger 401s on valid traffic.

### 3.3. Canaries, Rollback, and Availability

- Canary K2 signing on an internal test tenant/client first, verifying Resource Servers across all regions accept `kid=k2`.
- Verify both **unexpired K1 tokens** and **new K2 tokens** during overlap; verify tokens signed with unknown keys, fake `kid`s, wrong issuer/audience, or expired timestamps are rejected.
- Rollback if K2 failed to propagate: revert to **signing with K1** only during normal rotation **if K1 was not compromised/retired** and remains under control. If K1 is compromised, never "roll back" to K1 for availability.
- Check cache TTLs, DNS, proxies/CDNs, issuer metadata, JWK set caches, and verifiers with pinned public keys; a pod with a hard-coded key can cause an outage.
- If the public JWKS endpoint becomes temporarily unreachable, verifiers may use current cached keys depending on config and version, yet fail on uncached K2 tokens. **Never fail open** (accepting unverified JWTs) to suppress 401s.

## 4. Configuring Spring Boot 3.x / Spring Security 6.5 Resource Server

This example **verifies JWTs** rather than holding the private JWT signing key. It uses Spring Boot 3.x + Spring Security 6.5 Servlet on Java 17+. In real deployments, substitute trusted OAuth provider issuer/JWKS/audience values, use HTTPS, and verify metadata and dependency versions.

### 4.1. Gradle Dependencies

In a Spring Boot project with matching `build.gradle` and plugins:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 4.2. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/tenant-a
          jwk-set-uri: https://idp.example.test/tenant-a/jwks
          audiences: api://orders
          jws-algorithms: RS256
```

Explanation:

- `issuer-uri` defines the `iss` policy; adding `jwk-set-uri` lets the Resource Server start without calling issuer discovery at startup while still validating the `iss` claim from `issuer-uri`.
- `jwk-set-uri` must point to an **operator-trusted URL**, never taken from token claims or headers. Exact endpoint paths vary by IdP; there is no single mandatory JWKS path across all issuers.
- `audiences` requires `aud` to match this API (property name/config per Spring Boot/Security version). Validly signed tokens for another API must be rejected.
- `jws-algorithms` restricts accepted algorithms, e.g., **RS256** only. Never allow arbitrary algorithms requested by the token's `alg` header.

**Version note:** this aligns with Spring Boot 3/Spring Security 6.5 documentation. Declaring a custom `JwtDecoder` bean can **override Boot's auto-configuration**, causing `issuer-uri`/`audiences` not to apply automatically as assumed. With a custom decoder, configure `JwtValidator` for issuer/audience/exp/nbf and algorithm trust **explicitly** and write negative tests.

### 4.3. SecurityFilterChain Accepting JWTs

File `src/main/java/com/example/orders/ApiSecurityConfig.java` (inside a Spring Boot project with `@SpringBootApplication`):

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

This is an **app config fragment**, not runnable standalone with `javac`: it needs a web app, real issuer, real trust material, and valid tokens. Fine-grained API permissions like `SCOPE_orders.read`/tenant and object ownership must be added separately; the snippet illustrates only the verification lifecycle.

**Danger point:** a resource server with a JWT decoder is **not** the Authorization Server issuing JWTs. Never place the private signing key inside a resource-server container just because it verifies signatures. For asymmetric JWS, resource servers need only **public keys** from the trusted issuer.

### 4.4. JWK Cache and Failure Behavior During Rotation

Per Spring Security 6.5 reference, Resource Server caches the JWK set in memory for around **5 minutes** by default, customizable via `NimbusJwtDecoder`/Spring Cache. Depending on Nimbus versions and cache implementations, refresh behavior upon encountering an unknown `kid` varies; never promise "every verifier refreshes instantaneously on every new kid".

Key cases to watch:

| Scenario | Expected Outcome | Where to Investigate |
| --- | --- | --- |
| Unexpired K1 token, JWKS has K1+K2 | 200 (if authorized) | Check issuer, audience, signature |
| New K2 token, verifier cache lacks K2 | May 401 during propagation window | Check cache TTL/HTTP caching, publish timing, and rollout |
| K1 retired while K1 tokens still within `exp` | 401 once verifier cache expires or refreshes | Old-key retirement happened too early |
| JWKS endpoint temporarily down | Depends on cache/HTTP timeouts; not always 100% immediate failure | Circuit/last-known-good cache policy; never accept unverified tokens |
| Duplicate `kid` with different public key | Wrong key selected / verification fails; hard to diagnose | Never reuse a `kid` within a trust domain |
| Token with attacker `jku` header URL | Must never fetch arbitrary keys from headers | Pin JWKS URL per issuer/operator |
| New issuer sharing a JWKS | Must not blindly trust the new issuer | Validate `iss`/tenant/aud independently of key match |
| Valid token lacking scope | 403 per auth policy | Do not blame key rotation when decoding already succeeded |

**Monitor JWK rollovers via:** `401 invalid_token` rates, unknown kids, JWKS fetch failures/timeouts, broken down by issuer, environment, region, key ID (metadata), issuance timestamp, and verifier version. Never log raw JWTs or `Authorization` headers.

## 5. Symmetric Keys, Signing Keys, and Data Encryption Keys: Do Not Use One Playbook for All

### 5.1. HMAC JWTs (HS256)

With HS256, **the same secret** both signs and verifies. You cannot publish a public JWKS to "share the secret": any partner holding an HMAC secret can also **forge signatures** if compromised or untrusted. Use HMAC only when the trust model fits; across separate organizations, asymmetric RSA/EC cleanly separates signing from verification.

To rotate HS256:

- Generate a strong secret H2 in the secret manager; deploy H2 to **all authorized verifiers** first.
- Switch the signer to H2, tagging new tokens with a controlled key version/`kid`.
- Verifiers keep H1/H2 during the overlap window covering max JWT TTL and skew; never guess secrets from `alg` or brute-force the entire keystore unboundedly.
- After retirement, disable H1. If H1 leaks, revoke early and accept disruption to old tokens per incident policy.

### 5.2. Encryption Keys (AES, Data Encryption Keys, KEKs)

JWT signing keys differ from **data encryption keys**. Rotating an encryption key leaves older data decryptable only with the old key. Envelope encryption typically uses:

- **DEK (Data Encryption Key):** encrypts data or individual objects.
- **KEK (Key Encryption Key):** encrypts/wraps DEKs. Some KMSs rotate KEKs while retaining old versions for decryption, avoiding immediate re-encryption of all data.
- **Key version metadata:** each ciphertext carries a version/identifier to pick the authorized decryption key. Never trust the identifier while skipping integrity/tag verification.
- **Read old / write new:** the app encrypts new writes with K2, decrypts K1/K2 data by version, and migrates/rewraps gradually.
- **Emergency:** if a DEK/KEK leaks, assess exposed data and re-encrypt; merely rotating JWT signing keys does nothing to protect leaked historical ciphertexts.

**Never delete an old encryption key before verifying all readable data and backups have been re-encrypted/rewrapped.** Equally, never leave a compromised key active online indefinitely out of fear of data loss; execute a migration/isolation/incident plan. Key rotation protects both confidentiality **and** availability.

### 5.3. Secrets Signing Cookies, CSRF, or Remember-Me

Some apps have secrets signing remember-me cookies or application tokens. Rotating that secret can **log everyone out at once** if the server stops accepting tokens signed by the old secret—which may be intentional during an incident. Do not blindly apply the JWKS/public-key overlap playbook to cookie HMACs or session stores without knowing which layer actually verifies signatures. Spring Security CSRF token lifecycles, remember-me, and OAuth JWTs use distinct mechanisms.

## 6. Rotating API Keys: Two Valid Keys Briefly

### 6.1. What Kind of Credential Is an API Key?

API keys commonly identify/authorize **service-to-service or partner integrations**, typically as bearer strings: whoever holds the key can call the API within its scope. It is not by default an OAuth access token, lacks built-in JWT signatures/issuer/audience, and **Spring Security does not ship a single universal API-key authentication scheme for all projects**.

Apps may use a custom `AuthenticationFilter`/`AuthenticationProvider`, a gateway, or a dedicated filter reading `X-API-Key` or a custom `Authorization` scheme. Never accept API keys in URL query strings (easily leaked in logs/history/referrers). Always require HTTPS and never log key headers.

Each key should carry metadata:

| Field | Role | Notes |
| --- | --- | --- |
| `keyId` | Public ID, not secret | For lookup/auditing and identifying which key clients must rotate |
| `secretHash` | Digest of a **high-entropy secret** or HMAC with proper pepper | Never store plaintext keys in ordinary DBs |
| `ownerClientId` | Registered service/client | Never trust client-asserted owners in requests |
| `scope/role/resource` | Least privilege | Separate prod deploy keys from dev/test |
| `createdAt/lastUsedAt` | Lifecycle tracking | Metrics must not contain the full key |
| `expiresAt/revokedAt` | Retirement controls | Check expiry, revocation, and client status |
| `environment/tenant` | Scope boundary | Never reuse keys across tenants/environments |
| `rotationGroupId` | Links K1/K2 for a client (if needed) | Supports overlap and progress reporting |

With structured prefixes like `ak_live_<public-id>.<random-secret>`, the **public ID** must never serve as an authentication factor. Grant `Authentication`/scopes only once the secret verifies and the key record is active.

### 6.2. Zero/Minimal-Downtime API Key Runbook

1. **Inventory client and permissions:** client A uses key A1; record scopes, owner, traffic pattern, contacts, and deploy schedule.
2. **Issue A2** via CSPRNG (sufficient entropy, e.g., 256-bit random) in the secret manager/secure admin UI; display **once** over an authenticated secure channel. Keep A1 active temporarily.
3. **Deploy A2 to the client** via secret manager/config/secure CI pipeline without printing the key in logs or build artifacts. Canary one instance, then roll out the fleet.
4. **Dual-accept:** the server accepts both A1 and A2 with the same owner/scopes (or reduced scopes per policy). Never accidentally elevate A2's privileges.
5. **Observe:** track A1 last-used by key ID, region, and client; confirm A2 traffic is healthy. Check batch/offline consumers that may not call the API daily.
6. **Announce deadline** and **disable A1** after the agreed window, then permanently revoke it. Verify A1 returns 401/403 per app scheme while A2 continues working.
7. **Record rotation evidence:** who issued, who confirmed, revocation timestamp, old-key usage dropping to 0, and any downstream incidents. Never paste secret values into tickets.

**If A1 leaked:** do not always wait for every client to update before revoking; consider immediate revocation, scope reduction, client isolation, abuse monitoring, and rotating dependent credentials. Emergency plans prioritize containment even at the cost of disruption.

### 6.3. Why Not Overwrite a Single Key Slot in Place?

A "one key per client row in DB" design causes partially rolled-out client pods still sending A1 to fail with 401 immediately once overwritten with A2. Dual-active keys with a **bounded deadline** allow observable cutover. Overlap **does not mean issuing two permanent keys**: every key needs expiration, a revoke switch, and auditing.

**Common failures:** client has the new key while the server still caches the revoked key, CD pipeline prints raw keys, the new key accidentally gets broader scopes than the old one, metrics expose key values, A1 stays alive past deadline, or A2 is accepted without verifying owner/tenant.

## 7. API Keys + Spring Security: What Must You Design Yourself?

### 7.1. Authentication and Authorization Must Stay Separate

If an app accepts `X-API-Key`, the receiving component must:

1. Extract from the exact header and bound length/format; reject duplicate headers if policy forbids them.
2. Verify the **secret** against the record in a trusted DB/secret manager; key ID is only a lookup hint.
3. Check revoked/expired/disabled status, owner, tenant, environment, allowed APIs/scopes, and rate limits.
4. Produce a provider-verified `Authentication` mapped to minimal `GrantedAuthority`s.
5. Use Spring Security authorization for `hasAuthority(...)` and resource ownership in controllers/services.
6. Never mark `authenticated=true` merely because "the header is present".

**Choose the right mechanism:** if OAuth2 scopes/delegation/client auth are needed, consider OAuth2 Client Credentials or mTLS rather than building custom API keys everywhere. API keys lack built-in expiry/`jti`/replay protection like JWTs; they are bare opaque secrets unless you add metadata.

### 7.2. SecurityFilterChain Integration Outline

Below is a **policy outline** for an app that already has a properly implemented custom `AuthenticationProvider`/filter; concrete API-key authentication does not exist automatically in Spring Boot:

```java
@Bean
SecurityFilterChain apiKeyChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/partner/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/partner/health").permitAll()
            .anyRequest().hasAuthority("SCOPE_partner.read"))
        // Register the dedicated AuthenticationFilter/Provider in the real config.
        // Permit only the health route with permitAll(), NOT all of /partner/**.
        .build();
}
```

You must import `HttpSecurity`/`SecurityFilterChain`, declare the bean, and wire the filter/handler per your Spring Security version. **This snippet does not authenticate API keys**; copied verbatim without a provider/filter, all unauthenticated requests are denied. Do not treat it as a complete API-key implementation.

A stolen API key can **be replayed until revoked or expired** because it is a bearer secret. IP restrictions or mTLS client certificates narrow abuse windows, though IP allowlists are not cryptographic proof; account for client NAT/proxies/CDNs and IP changes.

## 8. Rotating TLS Certificates: Certificates, Private Keys, Chains, and CAs

### 8.1. TLS Certificates Differ from JWT/JWKS

An X.509 TLS server certificate holds fields such as Subject/SAN, issuer, serial, `notBefore`/`notAfter`, public key, signature, and extensions (EKU/KeyUsage). The TLS server must hold the matching private key (or use KMS/HSM) and present the proper **certificate chain** during the TLS handshake.

Distinguish these components:

| Component | Example | If Rotated Incorrectly |
| --- | --- | --- |
| **Leaf server certificate** | `api.example.test`, SAN=DNS:api.example.test | Handshake fails due to expiry/hostname mismatch |
| **Intermediate CA certificate** | Intermediate CA in full chain | Clients lacking intermediates fail with `unknown_ca` |
| **Trust anchor / root CA** | Public CA trusted by OS/JVM or internal private CA | Clients reject new server/client certificates |
| **Server private key** | Private key matching leaf cert | Handshake fails if cert and key mismatch; leak enables impersonation |
| **mTLS client certificate** | Service A proving identity to server B | Client denied or mapped to wrong principal when cert rotates |

**Rotating a leaf cert** is not **rotating a root CA**. On public CA renewals, clients keep trusting the new chain through existing truststores. With **private PKI / cross-signing / mTLS**, rotating a CA/trust anchor requires **two-way, properly ordered** trust rollout; removing the old CA before new clients are active breaks handshakes.

### 8.2. ACME and Renewal

**RFC 8555 (ACME)** defines a protocol for clients to request/renew certificates, prove identifier/domain control, and manage ACME accounts. The ACME account key **signs requests to the CA**—it is **not** the leaf certificate private key and certainly not a JWT signing key.

Workflow:

1. Monitor certificate expiry across **all live endpoints** (domains, regional LBs, internal gRPC, outbound mTLS), not just files in a repo.
2. Generate CSR/new key pair per policy; verify SAN/EKU/KeyUsage, chain, domain/service names, and private-key access controls.
3. Use an ACME client (or internal CA) to obtain the new cert **before** the old cert expires, with monitoring and retry schedules; rotate per SLO well before 1 day remains.
4. Install the new cert + private key at ingress/Load Balancers/embedded servers; update the fullchain properly.
5. Verify new handshakes with SNI and strict hostname validation; canary from **real clients** (JVM truststores, mobile apps, service meshes) and watch TLS handshake errors.
6. Once all endpoints serve the new cert, remove old cert/key material from deployments. If the old private key leaked, coordinate CA revocation and trust/incident policies.

**Revoked certificates:** CAs publish CRLs or OCSP; whether clients detect revocation depends on client checks (hard-fail vs. soft-fail, stapling, caching). **Do not claim that calling CA revoke immediately blocks the cert across every client.** For internal mTLS services, enforce explicit revocation/serial allowlists or short-lived certs checked at the TLS terminator.

### 8.3. Inspecting Certs Without Exposing Private Keys

With OpenSSL on a test machine:

```bash
# Check SAN and validity without printing the private key:
openssl x509 -in server.crt -noout -dates -issuer -subject -ext subjectAltName

# Observe the certificate/chain actually presented by the server:
openssl s_client -connect api.example.test:443 \
  -servername api.example.test -showcerts </dev/null
```

**Warning:** `s_client -showcerts` displaying a chain **does not prove** Java clients accept the SAN/CA/hostname. Test with real JVM truststores and HTTP clients; verify nobody enabled `trustAll` or disabled hostname verification to hide certificate errors.

Never run `openssl rsa -in server.key -text` on a shared terminal: it can print the private key into logs/shell history. To check cert/key pairing, compare public keys derived from the cert and private key inside a protected environment, never pasting private keys into tickets.

## 9. Spring Boot SSL Bundles: Swapping Certs Without Restarting When Supported

Spring Boot 3.x supports **SSL bundles** for JKS/PKCS12 or PEM. On Spring Boot versions supporting `reload-on-update` and compatible consumers (per docs: **Tomcat and Netty web servers**), updated certificate/key files can reload dynamically. Spring Boot **does not request or renew Let's Encrypt certificates itself**; ACME/Certbot or an external tool provides the updated files.

Example for embedded HTTPS Tomcat/Netty with operator-managed PEM files:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: file:/run/tls/fullchain.pem
            private-key: file:/run/tls/privkey.pem
server:
  port: 8443
  ssl:
    bundle: webserver
```

Conditions:

- `/run/tls/fullchain.pem` holds a valid cert+chain; `privkey.pem` matches the leaf public key. Filesystem permissions must restrict read access to the service account only.
- Ensure **both files** update atomically (atomic deployment/rename or file-watcher quiet period) to prevent a window where the new cert pairs with the old private key and breaks handshakes.
- Use reload only when **Boot version + web server consumer** support it. When TLS terminates at an Ingress/LB, replace the cert at the LB rather than `server.ssl.bundle` in the JVM.
- If loading PEMs from the JAR classpath, file watchers usually do not detect updates like external `file:` mounts; check how secrets/volumes are mounted.
- After updating, **test live handshakes** on every listener/region rather than treating "new file written" as completed rotation.
- Coordinate renewal separately: Boot does not manage ACME challenges or auto-renew expiring certificates.

**Rollback for planned cert rotation:** if the new cert has a bad SAN/chain, you can temporarily revert to the old cert **only if it is still valid and uncompromised**. If the old private key leaked, rolling back to it is a severe hazard—prioritize containment over availability.

## 10. mTLS: Rotating Client Certificates and Truststores

With **mutual TLS**, both sides can present certificates: the server proves identity to the client, and **the client proves identity** to the server. When a client cert approaches expiry:

1. Issue a new client certificate/key with EKU `clientAuth`, proper SAN/subject identity, and lifetime per private PKI.
2. If under the same trusted CA, the server may not need a new CA, though identity/serial/pinning mappings must be updated if used.
3. If changing CAs: **deploy the new CA trust at the server first** before clients begin presenting new certs; keep old CA trust temporarily bounded during migration.
4. Roll out the new client cert/key via secret manager/service mesh; test outbound connections against the real TLS terminator and server authorization.
5. Revoke/retire old client certs; update CRL/OCSP/serial allowlists per enforcement mechanism. Verify the server **actually enforces** revocation checks rather than merely exposing a "revoke" API.
6. Test missing certs, expired certs, wrong CAs, wrong SANs/identities, mismatched keys, revoked old certs, and cross-tenant certs.

Spring Security supports Servlet X.509 pre-authentication via `http.x509(...)`, yet when TLS terminates at a proxy, **never blindly trust an `X-Client-Cert` header from the Internet**. Enforce the chain of trust from LB/proxy, strip client-supplied headers at the edge, and trust forwarded details only over an authenticated proxy channel.

**Do not confuse mTLS certificate identity with OAuth scopes/roles:** X.509 proves the peer holds the private key for a trusted certificate; the app still maps the principal and checks authorization. A TLS-valid certificate does not automatically grant `ROLE_ADMIN` or cross-tenant access.

## 11. Incident Rotation: Compromised Keys Differ from Planned Rotation

### 11.1. Incident Indicators

- Secret/API key or private JWT signing key found in public Git, container images, build logs, issues/tickets, emails, or package artifacts.
- HSM/KMS audits showing anomalous signing operations, suspected key exports, or logins from unexpected geographies.
- Bearer tokens with an old `kid` or revoked key appearing past retirement; revoked API keys still being presented.
- TLS private key or ACME account key found on an untrusted host; unauthorized certificate issuance.
- Validly signed JWTs with anomalous claims/issuers/client patterns suggesting signer credential compromise.

### 11.2. Containment-First Runbook

1. **Declare incident & scope:** identify credential type, tenant/env, dependent accounts/endpoints, and log trustworthiness. Never paste leaked secrets into public chat to ask colleagues.
2. **Block/revoke compromised credential:** disable old API keys, swap signing keys and purge the compromised public key from verify trust where appropriate; trigger forced logouts/denylists/reauthentication if needed. Prioritize cutting off attacker access.
3. **Generate independent replacement** from a trusted source on a separate/isolated KMS/HSM if the old trust root is at risk; never reuse old keypairs/certs.
4. **Propagate verify-policy changes** to all nodes, JWKS caches/CDNs/edges, service meshes/truststores, and downstream consumers. If verifiers still cache compromised public K1, an attacker can keep minting validly signed tokens until caches clear/expire.
5. **Test rejection:** a JWT signed with compromised K1 even with valid `exp` must be rejected once policy revokes K1; revoked API keys must fail; compromised mTLS certs must fail handshake/authorization.
6. **Audit impact:** identify affected data, requests, and sessions; search API logs by key ID/correlation without logging secrets; follow breach notification and legal policies.
7. **Root cause and prevention:** deploy secret scanning, tighten IAM, sanitize CI logs, restrict egress, automate rotation, and improve alerts.
8. **Recovery/rollback:** move forward to **new trusted material**; never restore compromised K1 as a "quick rollback".

**Accept the trade-off:** immediately retiring public K1 may cause legitimate users' JWTs to hit 401 and force token refresh. That disruption may be necessary when a key leaks; keeping K1 alive "to avoid downtime" lets attackers forge JWTs. Never apply the planned-overlap runbook mechanically during a compromise.

### 11.3. Do Not Confuse Revocation Mechanisms

| Compromised Credential | Direct Containment | What Does Not Happen Automatically |
| --- | --- | --- |
| JWT signing private key | Stop signing, remove key from trusted verification, invalidate caches, revoke tokens/re-auth as needed | Rotating TLS certs does not revoke JWTs |
| API key | Server disables/revokes key ID, issues new key, monitors abuse | Rotating JWT signers does not invalidate API keys |
| TLS leaf private key | Issue new cert/key, deploy, revoke old cert, check trust behavior | Logging out `HttpSession` does not fix a leaked cert |
| ACME account private key | Roll over/deactivate ACME account key per RFC 8555; audit for unauthorized cert issuance | Rotating leaf certs does not rotate the ACME account key |
| Refresh token | Revoke/rotate refresh token family, run incident checks | Deleting an `HttpSession` does not revoke refresh tokens at the IdP |
| Database encryption key | Key lifecycle/rewrap/re-encrypt, assess data exposure | Issuing a new key alone does not re-encrypt old ciphertexts |

## 12. Automated and Manual Testing: Before / During / After Sequence

A safe rotation must be tested **state by state**, not merely "deploy succeeded with 200". Use isolated fixtures and test clients; never test production tokens against unauthorized targets.

| ID | Stage | Operation | Expected Result |
| --- | --- | --- | --- |
| J01 | Before rotation | Valid K1 JWT, right iss/aud/exp | Accepted |
| J02 | Preparing K2 | JWKS has K1+K2, signer still K1 | K1 JWT still accepted |
| J03 | After cache propagation | Valid K2 token | Verified in every region |
| J04 | During overlap | Unexpired K1 JWT + new K2 JWT | Both verify |
| J05 | After K1 retirement | K1 JWT even with mathematically valid signature | Rejected under new trust policy |
| J06 | All stages | JWT `kid` not in trusted JWKS | Rejected |
| J07 | All stages | Header `jku` pointing to attacker site | Not fetched / untrusted key |
| J08 | All stages | JWT `alg=none` or algorithm confusion | Rejected |
| J09 | All stages | Valid signature but wrong issuer | Rejected |
| J10 | All stages | Right issuer but wrong audience/tenant | Rejected |
| J11 | All stages | Expired JWT | Rejected |
| J12 | JWKS unreachable | Verifier cache lacks K2 | Fails closed; never accepts unknown tokens |
| A01 | New API key issued | A1+A2 active | Authorized client can use both during overlap |
| A02 | During overlap | Another client sends key A2 | Must not assume the other owner's identity |
| A03 | A1 revoked | A1 request | Unauthorized, zero side effects |
| A04 | A1 revoked | A2 request | Continues working per scope |
| A05 | Expired API key | Use key past `expiresAt` | Rejected |
| A06 | API key used out of scope | Call admin route | Rejected despite valid key |
| A07 | Multi-pod revoke | Present A1 to every region | No pod accepts cached revoked key |
| C01 | Before cert rotation | TLS handshake/SNI/hostname | Passes with real JVM truststore |
| C02 | New cert deployed | Fullchain + SAN/EKU/expiry + keypair | Passes |
| C03 | Wrong hostname cert | Connect from real client | Fails; never disable hostname verification |
| C04 | Expired cert / unknown CA | Connect | Fails |
| C05 | New mTLS client cert | Same allowed service identity | Passes with right authorities |
| C06 | Old mTLS client cert revoked | Connect | Fails per revocation policy |
| C07 | TLS reload | Update cert files | New handshakes serve new cert |
| I01 | Compromised JWT K1 | Immediately after retire/invalidate | Forged K1 tokens rejected across all verifiers |
| I02 | Compromised API key | Revoke A1 | A1 rejected immediately; A2 continues if safe |
| I03 | Rollback | New key deployment broken | Roll back to old only if **uncompromised** |

**Beyond HTTP status:** assert real authorization, zero DB writes/payments on failed auth, unchanged session identities, and no raw secrets in caches or metrics. Test multi-region canaries and retry/circuit behavior when JWKS, KMS, or CA endpoints flake.

## 13. Standalone Java 17: Simulating Two-Key Signing Overlap and API-Key Rollover

This lab runs on Java 17 **without Spring, JWT, KMS, or TLS**. It intentionally performs real RSA SHA-256 signing/verification and simulates hashed 256-bit random API keys in a store. Goal: illustrate **public key K1/K2 overlap**, signer switch, trust retirement, and **API key dual acceptance → revoking the old key**.

**Do not copy directly into production:** the code keeps private RSA keys on the heap instead of KMS/HSM, does not build JWS/JWT serialization, skips issuer/audience/token expiry checks, and has no DB transactions or auditing. SHA-256 of a **random 256-bit API key** illustrates lookup; real systems need anti-enumeration/constant-time checks, rate limits, a secret manager, key ID/owner/scope separation, and cache invalidation. Never print raw keys to stdout.

Save as `CredentialRotationLab.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Instant;
import java.util.*;

public final class CredentialRotationLab {

    record SignedPayload(String kid, String body, byte[] signature) {}
    record ClientKey(String owner, Instant expiresAt) {}

    private static final SecureRandom RANDOM = new SecureRandom();

    static String randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    static String sha256Hex(String secret) throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hashed = digest.digest(
                secret.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(hashed);
    }

    static final class SigningKeys {
        private final Map<String, PublicKey> trusted = new HashMap<>();
        private final Map<String, PrivateKey> signing = new HashMap<>();

        void create(String kid) throws GeneralSecurityException {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            KeyPair pair = generator.generateKeyPair();
            signing.put(kid, pair.getPrivate());
            trusted.put(kid, pair.getPublic());
        }

        SignedPayload sign(String kid, String payload)
                throws GeneralSecurityException {
            PrivateKey key = signing.get(kid);
            if (key == null) {
                throw new InvalidKeyException("No active signer for kid");
            }
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(key);
            signer.update(payload.getBytes(StandardCharsets.UTF_8));
            return new SignedPayload(kid, payload, signer.sign());
        }

        boolean verify(SignedPayload token) throws GeneralSecurityException {
            PublicKey trustedKey = trusted.get(token.kid());
            if (trustedKey == null) {
                return false; // kid selected from local trusted set
            }
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(trustedKey);
            verifier.update(token.body().getBytes(StandardCharsets.UTF_8));
            return verifier.verify(token.signature());
        }

        void stopSigning(String kid) {
            signing.remove(kid);
        }

        void retirePublic(String kid) {
            trusted.remove(kid);
        }
    }

    static final class ApiKeyStore {
        private final Map<String, ClientKey> byHash = new HashMap<>();

        String issue(String owner, Instant expiresAt)
                throws GeneralSecurityException {
            String value = randomSecret();
            byHash.put(sha256Hex(value), new ClientKey(owner, expiresAt));
            return value; // return secret to the client exactly once
        }

        boolean accepts(String value, String expectedOwner, Instant now)
                throws GeneralSecurityException {
            ClientKey found = byHash.get(sha256Hex(value));
            return found != null
                    && found.owner().equals(expectedOwner)
                    && now.isBefore(found.expiresAt());
        }

        void revoke(String value) throws GeneralSecurityException {
            byHash.remove(sha256Hex(value));
        }
    }

    public static void main(String[] args) throws Exception {
        SigningKeys jwk = new SigningKeys();
        jwk.create("k1");
        SignedPayload old = jwk.sign("k1", "user=alice");

        jwk.create("k2");
        SignedPayload fresh = jwk.sign("k2", "user=alice");

        System.out.println("oldDuringOverlap=" + jwk.verify(old));
        System.out.println("newDuringOverlap=" + jwk.verify(fresh));

        jwk.stopSigning("k1");
        System.out.println("oldVerifiableAfterSwitch=" + jwk.verify(old));

        jwk.retirePublic("k1");
        System.out.println("oldDeniedAfterRetire=" + !jwk.verify(old));
        System.out.println("newStillWorks=" + jwk.verify(fresh));

        SignedPayload tampered = new SignedPayload(
                "k2", "user=bob", fresh.signature());
        System.out.println("tamperedRejected=" + !jwk.verify(tampered));

        ApiKeyStore api = new ApiKeyStore();
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String a1 = api.issue("service-a", now.plusSeconds(3600));
        String a2 = api.issue("service-a", now.plusSeconds(7200));

        System.out.println("oldKeyInitiallyWorks=" +
                api.accepts(a1, "service-a", now));
        System.out.println("newKeyWorks=" +
                api.accepts(a2, "service-a", now));
        System.out.println("wrongClientDenied=" +
                !api.accepts(a2, "service-b", now));

        api.revoke(a1);
        System.out.println("oldKeyRevoked=" +
                !api.accepts(a1, "service-a", now));
        System.out.println("newKeyStillWorks=" +
                api.accepts(a2, "service-a", now));
        System.out.println("keyExpired=" +
                !api.accepts(a2, "service-a", now.plusSeconds(7201)));
    }
}
```

Run:

```bash
javac CredentialRotationLab.java
java CredentialRotationLab
```

**Exact stdout**, independent of the randomly generated RSA/API key values:

```text
oldDuringOverlap=true
newDuringOverlap=true
oldVerifiableAfterSwitch=true
oldDeniedAfterRetire=true
newStillWorks=true
tamperedRejected=true
oldKeyInitiallyWorks=true
newKeyWorks=true
wrongClientDenied=true
oldKeyRevoked=true
newKeyStillWorks=true
keyExpired=true
```

Explanation:

- While both K1 and K2 public keys are trusted, both old and new signatures verify.
- Stopping **signing** with K1 does not remove the ability to **verify** K1 signatures before K1 public trust is retired.
- After retiring public K1, K1's mathematical signature remains valid, yet **the system no longer trusts that key**.
- Changing the payload from Alice to Bob without re-signing fails signature verification.
- API keys A1/A2 remain active together during overlap; revoking A1 does not break A2; expired keys or wrong owners are rejected.

**Boundaries:** `SigningKeys` is an in-RAM local keystore with no JWKS endpoint/cache or JWT expiration; `ApiKeyStore` has no distributed cache or transactions. In production, key lifecycles run through KMS/secret managers, key IDs, scoped OAuth/API policies, and real integration tests.

## 14. Monitoring and SLOs: What Should You Measure After Rotation?

Safe operations observe **exactly where keys are used** without leaking secrets:

| Metric / Signal | How It Is Used | Notes |
| --- | --- | --- |
| JWT `issued_by_kid` (K1/K2) | Confirm signer actually switched | Log `kid` metadata only, never JWTs |
| JWT verification pass/fail by kid/issuer/region | Spot stale verifier JWKS or mismatched keys | Never log raw `Authorization` |
| JWKS fetch/cache hits/errors/latency | Track cache propagation and dependency health | Distinguish network 401s from missing-scope 403s |
| API key usage by key ID, owner, and version | Decide when to safely revoke old A1 | Never emit secret/hash as high-cardinality metric labels |
| Revoked/expired API key attempts | Detect un-updated clients or abuse | Redact sensitive identities per audit policy |
| TLS cert remaining lifetime | Alert before expiry | Measure **the cert actually served** on every listener/SNI, not just files |
| TLS handshake failures by trust reason | Wrong SAN, CA, chain, expiry, or key mismatch | Never disable verification to "reduce errors" |
| mTLS principal mapping failures | Spot new certs not yet trusted by policy | Verify account/service identity mappings |
| Secret-manager/KMS signing errors | HSM permissions, throttling, outages | Never fail open or fall back to local generated keys |
| Rotation change audit | Prove completion, rollback, and retirement steps | Who/when/version, never raw secrets |

### Concise Alerts

- Old keys remain **in use** past switch deadline, or revoked secrets are still accepted.
- Spike in `401/invalid_token` after JWT signer switch; unknown-kid errors by region/pod.
- Live certificate at a public endpoint drops below warning threshold while renewal automation fails.
- Rising TLS handshake or mTLS auth failures after a deployment.
- Prolonged unreachable JWKS/KMS/secret manager without visibility into when stale caches expire.
- Long-lived API keys lacking owner, purpose, or rotation schedule.

**Never measure by logging raw tokens or private keys.** A `kid` or cert serial can serve as metadata if permitted by policy; place them in metrics with bounded cardinality and access-controlled dashboards.

## 15. Troubleshooting: Symptom → Broken Layer

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| K2 JWTs start returning 401 | JWKS not published / verifier cache TTL | Check JWKS/issuer, `kid`, cache refresh, and rollout order |
| Unexpired K1 tokens get 401 | K1 removed too early; clock skew/TTL larger than expected | Check last-issued time and max token lifetime; restore K1 **if uncompromised** |
| JWT with non-configured `alg` denied | Verifier restricts to RS256 per policy | Do not relax algorithm allowlists carelessly |
| Validly signed JWT has wrong `aud` | Token issued for another API | Fix issuer/client/resource audience; never drop validation |
| JWKS contains private `d` | Private key material accidentally published | Treat as compromise incident; remove immediately and rotate |
| Verifier fetches JWKS from `jku` header | Key injection / SSRF vulnerability | Pin trusted URI per issuer; block remote URLs inside tokens |
| New API key does not work | Client did not deploy secret; stale key-store cache | Verify key ID/owner/expiry and cache invalidation |
| Old key still accepted after revoke | Stale regional cache, duplicate credential, unsynced revocation | Check consistency/quorum; revoke across every node |
| Valid API key gets 403 | Insufficient scope/tenant/owner | Check authorization; do not force re-login |
| Client sends key in URL | Bad debug habit; leaks into logs/history | Move to `Authorization`/custom header; scrub logs |
| Cert issued but handshake fails | Wrong SAN, mismatched private key, missing fullchain | Verify cert+key match and live server SNI |
| New cert exists but old cert still served | Reload disabled/unsupported consumer/Ingress stale | Inspect TLS terminator, reload support, and listener deployment |
| Unexpired TLS cert triggers `unknown_ca` | Truststore/CA/intermediate not updated | Roll out trust in order; never use trust-all |
| New mTLS client cert lacks permissions | Principal mapper/pinning/serial allowlist not updated | Check identity mapping + authorization |
| Old revoked X.509 still handshakes | Client/server skips CRL/OCSP/serial checks | Audit revocation enforcement; never assume every client blocks |
| Rotating TLS cert did not revoke JWTs | TLS and JWT are separate trust domains | Determine whether JWT issuer signing key rotation is also needed |
| Compromised KMS private key kept in overlap | Wrongly applied planned-rotation runbook | Emergency containment and revocation instead of keeping trust |
| Old encryption key deleted, data unreadable | Missed rewrap/re-encrypt/backups | Restore from key management recovery plan and run migration |
| Boot SSL bundle reload enabled, ACME not renewing | Boot only reloads files; it does not request certs | Configure Certbot/ACME client/CA automation separately |
| Only 302 seen in login test | Frontend redirect; does not prove key validity | Assert exact principal, token verification, and resource access |
| New Spring Resource Server lacks `aud` policy | Custom `JwtDecoder` overrode Boot validation | Add explicit validators and negative-test wrong-audience |

## 16. Shift-Handoff Checklist and Runbook

### Before the Change

- [ ] Identified **exact credential type** (JWT signing/public key, HMAC, API key, TLS/mTLS cert, encryption KEK/DEK), owner, tenant, and environment.
- [ ] Complete inventory of all consumers/signers/verifiers, keystores, secret managers, and SNI endpoints affected.
- [ ] Documented max token TTL + clock skew, JWK/cache propagation delay, cert expiry, and API key client rollout timeline.
- [ ] New key/secret generated by CSPRNG/KMS/HSM without entering repos, logs, or CI stdout.
- [ ] Planned rollback path exists **only if old credential is uncompromised**; separate emergency runbook ready.
- [ ] Defined permissions and approvals for issuance, revocation, and auditing.

### During the Change

- [ ] For JWT: publish public K2 **before** signing K2 JWTs; maintain public K1 overlap per TTL without putting private K1 in JWKS.
- [ ] For API keys: issue A2 securely, canary client, monitor A1 usage, revoke A1 past deadline.
- [ ] For TLS/mTLS: cert+key match, accurate SAN/EKU/chain, truststores updated first on CA change, right terminator reloaded.
- [ ] Never disable JWT signature checks, hostname verification, or TLS trust to "silence 401/SSL errors".
- [ ] Canary across issuers, audiences, tenants, regions, clients, and service-to-service workloads.
- [ ] KMS/JWKS/DB outages follow fail-closed policy and alert; never mint `Authentication` without verification.

### After the Change

- [ ] New JWTs signed with K2 accepted by all verifiers; K1 retired on schedule; unknown kid/alg/wrong aud fail.
- [ ] API key A1 revoked, A2 scope/owner accurate, no cache/pod still accepts A1.
- [ ] Live TLS endpoints serve new cert; hostname/chain/expiry verified by JVM clients; old cert handled per PKI policy.
- [ ] New mTLS cert maps to exact principal; old cert loses access per policy.
- [ ] Legacy encrypted data stays readable if migration is ongoing; key backups/recovery managed.
- [ ] Audit records change ID, owner, timestamps, secret versions, completion status, negative test results, dashboards, and next rotation date.
- [ ] Distinguish "rotated JWT key" from "revoked all JWTs" and "rotated cert" from "revoked old cert on every client".

**Closing principle:** Safe planned rotation follows **publish new trust → switch producer/client → observe → retire old trust**; during a key compromise, prioritize **containment and revocation**. JWT signing keys, API keys, TLS/mTLS certificates, and encryption keys have different trust anchors and revocation paths. Changing one config value and restarting a service never proves all old tokens or certificates have ceased to be accepted.

### Primary Sources and References

- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Resource Server Authentication](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot — SSL Bundles and Reloading SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot 3.4 — SSL Bundles](https://docs.spring.io/spring-boot/3.4/reference/features/ssl.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 5280 — X.509 PKI Certificate Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 8555 — Automatic Certificate Management Environment (ACME)](https://www.rfc-editor.org/rfc/rfc8555)
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705)
