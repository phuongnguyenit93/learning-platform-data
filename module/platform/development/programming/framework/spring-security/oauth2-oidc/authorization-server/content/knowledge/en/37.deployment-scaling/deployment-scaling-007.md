# Distributing Stable Signing Keys and Synchronizing System Clocks

When deploying Spring Authorization Server across multiple instances, every instance must issue JWTs verifiable with the same public key set and the same issuer identifier. At the same time, the token-issuing server and Resource Servers must maintain sufficiently accurate system clocks to interpret token timestamps uniformly. These two requirements directly determine whether authentication stays stable across scaling, restarts, rolling updates, or cross-region failovers.

This lesson explains how to manage immutable signing keys across replicas, publish and rotate keys via a JWK Set, synchronize clocks with NTP/chrony, configure Spring Authorization Server and Spring Security, and run verification checks before bringing the cluster into production.

## 1. Context and goals

Suppose the Authorization Server has three replicas behind a load balancer. Clients obtain access tokens from the token endpoint; backend APIs are protected by Spring Security Resource Server. Access tokens can be asymmetrically signed JWTs. Resource Servers fetch public keys from the Authorization Server's JWKS endpoint to verify signatures.

A sound deployment must preserve these invariants:

1. All replicas of the same Authorization Server share the same canonical issuer URL and the same centrally managed signing key set.
2. Every replica publishes the same JWKS capable of verifying tokens issued by any replica.
3. Each key has a stable, unique `kid` within the key set, which is recorded in the JWT protected header.
4. Private keys are used solely for signing at the Authorization Server or an authorized signing service; Resource Servers need only public keys.
5. Clocks on nodes running the Authorization Server and Resource Servers are synchronized with a trusted time source.
6. The token validator's clock skew setting is small, deliberate, and matched to measured time drift.

Typical deployment diagram:

~~~mermaid
flowchart TB
    C[Client] --> LB[Load balancer]
    LB --> A1[Authorization Server replica 1]
    LB --> A2[Authorization Server replica 2]
    LB --> A3[Authorization Server replica 3]
    K[Key store / KMS / HSM] --> A1
    K --> A2
    K --> A3
    A1 --> J[JWKS endpoint]
    A2 --> J
    A3 --> J
    J --> R[Resource Servers]
    N[NTP sources] --> T[chronyd / time service]
    T --> A1
    T --> A2
    T --> A3
    T --> R
~~~

Signing keys and time represent two distinct classes of infrastructure state. Keys determine whether a signature can be verified; time determines whether a token lies within its validity window. A cluster with identical keys but drifted clocks can still reject valid tokens. A cluster with accurate clocks where each replica uses its own keys can produce intermittent signature failures depending on which node the load balancer picks.

## 2. Why signing keys must be stable across replicas

### 2.1. Failures from generating new keys on every startup

Minimal Spring Authorization Server tutorials generate an RSA key pair at application startup and pass it into `JWKSource`. That is convenient for local trials on a developer machine. In multi-replica production, if each process generates its own key, nodes end up holding different public/private key pairs despite publishing the same issuer.

Common failure scenarios:

- Replica A signs tokens with key A.
- Replica B signs tokens with key B.
- The JWKS endpoint behind the load balancer sometimes returns public key set A and sometimes returns public key set B.
- A Resource Server may cache key set A and then receive a token signed with key B. If the cached key set lacks B, the signature is rejected.
- After a pod restarts, a new key is generated. Still-valid tokens issued before the restart can no longer be verified.

Because this depends on routing and caching, errors may appear sporadically per request or right after a deployment. Increasing replica count increases the probability of hitting the failure.

### 2.2. Shared key source

Generate keys in a controlled provisioning workflow, then store and distribute them to replicas via an appropriate secrets management mechanism, such as:

- An HSM or KMS service with signing permission controls.
- The deployment platform's secret manager, with versioned secrets and workload-scoped access control.
- An encrypted key store with access controls, auditing, and clear backup/restore procedures.

Every replica must read the same active key version and the same key metadata. If private keys are loaded into the process, grant read access only to the Authorization Server's service account. Never place private keys in Git, container images, ConfigMaps, logs, the JWKS endpoint, or build artifacts. Do not derive symmetric keys from guessable passwords.

In systems using asymmetric keys, the Authorization Server retains signing authority with the private key; Resource Servers download only the public key for verification. This model fits scenarios where many APIs must verify tokens without being allowed to mint tokens themselves. Choose signature algorithms based on organizational cryptographic policy, client compatibility, and library support. All issuers and verifiers must agree on allowed algorithms; never trust the algorithm declared by an untrusted input token alone.

If your KMS/HSM does not permit exporting the private key, you cannot assume you can construct an RSA JWK containing the private key and wrap it directly in `ImmutableJWKSet`. Depending on the provider, integration may use a Java Cryptography Architecture provider / PKCS#11 to expose the key as a `PrivateKey` handle, or implement a `JwtEncoder` calling a remote signing service. You then configure Spring Authorization Server's `JwtGenerator`/`OAuth2TokenGenerator` to use that encoder. That integration is provider-specific; `JWKSource` by itself does not turn an HTTP KMS API into a remote signer.

### 2.3. JWK, JWK Set, and kid

A JWK is a JSON representation of a cryptographic key. A JWK Set is a JSON object with a `keys` field containing a list of JWKs. For an RSA key used for signature verification, a public JWK typically contains fields such as:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "as-signing-2026-01",
  "n": "base64url-modulus",
  "e": "AQAB"
}
~~~

This is a structural example, not a usable key. Public JWKs must not contain private parameters such as `d`, `p`, `q`, `dp`, `dq`, or `qi`; for symmetric keys, the `k` field must never be published.

`kid` is the key identifier. A JWT signed by a key normally carries the matching `kid` in its protected header. Resource Servers use this value to locate the right JWK in the key set. During rotation, each key needs its own `kid`; never reuse a `kid` for a new key pair. RFC 7517 clearly describes key lookup and the role of `kid` during key rollover.

The JWKS endpoint publishes only public keys. Resource Servers need access to the current public key as well as older public keys still required to verify unexpired tokens. Private keys are neither needed by nor distributed to Resource Servers.

## 3. Configuring Spring Authorization Server with a stable key source

### 3.1. JWKSource and the JWK Set endpoint

Spring Authorization Server configures the JWK Set endpoint when the application registers a `JWKSource<SecurityContext>` bean. By default, the endpoint typically lives at `/oauth2/jwks`; verify the actual endpoint path against your application configuration and published metadata.

The example below illustrates integrating with an application-implemented key loader. `SigningKeyLoader` is an internal interface in this example, not a built-in Spring API. Its implementation must read the provisioned key version from the key store/KMS/HSM and return the JWK Set used for signing.

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SigningKeyConfiguration {

    @Bean
    JWKSource<SecurityContext> jwkSource(SigningKeyLoader signingKeyLoader) {
        // The key set must be loaded from a shared, controlled storage source.
        // The key set contains the active private key and public keys that must
        // be retained to verify previously issued JWTs.
        JWKSet signingJwkSet = signingKeyLoader.loadJwkSet();

        return new ImmutableJWKSet<>(signingJwkSet);
    }
}
~~~

A minimal contract for the application-defined adapter can look like this:

~~~java
import com.nimbusds.jose.jwk.JWKSet;

public interface SigningKeyLoader {

    JWKSet loadJwkSet();
}
~~~

`ImmutableJWKSet` is appropriate when the application loads a key snapshot at startup. If keys need to be updated while the process is running, you need a refresh mechanism or a dynamic `JWKSource` that reads the active key version. Do not replace a key file on a single node and assume all replicas and caches have picked up the new version.

You can declare a fixed public issuer so all replicas advertise the same identifier:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

The issuer must be the canonical URL trusted by clients and Resource Servers. Never let the issuer vary by internal hostname, pod address, random port, or untrusted request host. When running behind a reverse proxy/load balancer, configure forwarded headers and the public base URL properly so metadata and endpoints do not accidentally return internal URLs.

In default configurations, `OAuth2AuthorizationServerConfiguration` can provide the `SecurityFilterChain` and protocol endpoints. A `JWKSource<SecurityContext>` bean is required for the JWK Set endpoint to be configured. If using OpenID Connect UserInfo or endpoints that need to decode JWTs, register a `JwtDecoder` using Spring Authorization Server's utility:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import com.nimbusds.jose.jwk.source.JWKSource;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Do not copy the random RSA key generation snippet from the Getting Started documentation verbatim into multi-replica production. In production, key generation belongs to a dedicated provisioning process; the application bean only loads or uses managed keys.

### 3.2. Resource Server fetching public keys

When the Authorization Server publishes standard metadata and a JWKS endpoint, a Spring Boot Resource Server can auto-discover public keys via the issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

`issuer-uri` must match the `iss` claim in JWTs exactly. Spring Security uses the Authorization Server's metadata to locate the JWKS URI, fetch public keys, and verify signatures; the default setup also validates the issuer and the `exp` and `nbf` timestamp claims.

If the Resource Server needs to start independently of the Authorization Server's availability, you can also declare the JWKS URI explicitly:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
          jwk-set-uri: https://auth.example.com/oauth2/jwks
~~~

This skips the metadata call for discovering the JWKS URI at startup while keeping `issuer-uri` to validate the `iss` claim. The JWKS URI must be a trusted configured HTTPS address; never take arbitrary URIs from a token's `jku` or `x5u` headers.

If the same issuer issues tokens for multiple APIs, Resource Servers must also verify `aud` so tokens are accepted only by the intended target API. You can use Spring Boot's `audiences` property or add an `OAuth2TokenValidator` as required. A passing signature check does not replace validating issuer, audience, expiration, and authorization scopes.

### 3.3. Verifying configuration before scaling

Before increasing replica count, query the JWKS endpoint directly via the public path and per replica if internally reachable:

~~~bash
curl -fsS https://auth.example.com/oauth2/jwks
~~~

Compare the `kid`, `kty`, `alg`, and public key material across responses. You can compare JWK thumbprints to avoid sensitivity to JSON property ordering. Verify the response contains only public keys.

A practical verification procedure:

1. Call the JWKS endpoint through the load balancer multiple times and against each replica.
2. Confirm every response contains the same set of `kid` values and matching public keys.
3. Request tokens multiple times so different replicas issue tokens.
4. Inspect the protected header of each JWT and confirm its `kid` is present in JWKS.
5. Use the Resource Server or an independent test tool to verify signatures of tokens from every replica.
6. Restart one replica and repeat the checks. `kid` and public keys must not change simply because a process restarted.

In production, track JWT verification failures by cause. Distinguish signature errors, unknown `kid`, issuer mismatches, audience mismatches, and expired tokens. Never log access token values or private keys for diagnostics.

## 4. Rotating signing keys safely

Periodic key rotation limits the exposure window of any single key and reduces blast radius when a key must be replaced. However, removing an old public key too early causes unexpired tokens to be rejected. Therefore, an overlap window between the old key and the new key is required.

### 4.1. Planned key rotation procedure

Suppose the current key has `kid=as-signing-2026-01`, and the new key has `kid=as-signing-2026-07`.

~~~mermaid
sequenceDiagram
    participant K as Key store
    participant A as Authorization Server replicas
    participant R as Resource Servers
    K->>K: Generate new key and new kid
    K->>A: Deliver new key to token issuer
    A->>R: JWKS publishes both old and new public keys
    R->>R: Fetch/cache new public key
    A->>A: Switch all replicas to sign with new kid
    A->>R: New JWT carries new kid
    R->>R: Verify JWT with new public key
    Note over A,R: Retain old public key while old tokens remain valid
    K->>A: Revoke signing permission for old private key
    A->>R: JWKS drops old public key after overlap period
~~~

Execution sequence:

1. **Generate the new key:** create the key pair in KMS/HSM or the key management workflow; assign a new `kid` and record its fingerprint, algorithm, creation timestamp, and key version.
2. **Distribute the public key first:** update JWKS to include the new public key alongside the old public key. Wait until every replica serving JWKS and relevant caches can see the new key.
3. **Switch signing:** transition replicas to sign with the new private key. During a rolling update, tokens signed by both old and new keys may temporarily coexist; JWKS must advertise both during this window.
4. **Monitor:** confirm new tokens carry the new `kid` and verify cleanly on all Resource Servers.
5. **Retire the old key:** stop signing with the old private key. Keep the old public key until every JWT signed by it has expired plus clock skew, cache TTLs, and configuration propagation time.
6. **Decommission:** after the overlap window, remove the old public key from JWKS and archive the key record according to audit/recovery policy.

The minimum retention duration for the old public key must cover:

- Maximum lifetime of access tokens, ID tokens, and any other JWTs signed with the old key.
- Clock skew tolerated by Resource Servers.
- JWKS cache duration and refresh intervals on Resource Servers.
- Deployment time for all replicas and gateways to receive the updated configuration.

No single fixed number fits every system. Calculate it from actual token settings, actual cache behavior, and measured rollout times. If a Resource Server caches JWKS longer than expected, removing the old key from the endpoint does not mean every cache has forgotten it; conversely, a cache that has not picked up the new key yet can reject new tokens during transition.

### 4.2. When a key is compromised

When there is evidence that a private key has been compromised, the emergency procedure differs from routine rotation:

1. Generate a replacement key in the trusted store and switch all replicas to the new key.
2. Remove the compromised public key from JWKS as quickly as possible so Resource Servers stop trusting tokens signed with it.
3. Identify potentially affected tokens, clients, authorizations, and systems; revoke related authorizations/refresh tokens where supported by the system.
4. Purge or refresh JWKS caches at gateways and Resource Servers via established operational mechanisms.
5. Inspect logs/audits, determine the scope of exposure, and preserve incident evidence.

Removing the old public key invalidates previously issued tokens signed by the revoked key. This is a deliberate trade-off when shutting down a compromised key; notifying and coordinating with dependent APIs must be part of the incident runbook.

## 5. Synchronizing time for Authorization Server and Resource Servers

### 5.1. JWTs use UTC time

RFC 7519 defines `NumericDate` as the number of seconds from `1970-01-01T00:00:00Z` UTC, ignoring leap seconds. Key time claims include:

| Claim | Meaning | Interpretation |
|---|---|---|
| iat | Issued At | Timestamp when the token was issued; can be used to evaluate token age |
| nbf | Not Before | Token must not be accepted before this timestamp |
| exp | Expiration Time | Token must not be accepted on or after this timestamp |

For `exp`, the current time must be strictly before the expiration time. For `nbf`, the current time must be on or after the validity start timestamp. The RFC allows a small leeway to account for clock skew. Do not turn this leeway into minutes or hours to mask unstable time infrastructure.

`iat` indicates issuance time and can assist token age checks. Do not treat `iat` as `nbf`: the two claims have different semantics. If business logic requires a maximum token age, design a dedicated validator aligned with requirements and JWT rules.

Setting server timezones to UTC keeps logs, operational schedules, and incident investigations consistent, but changing the timezone does not synchronize the clock. NTP adjusts the system clock; UTC is a standard time representation.

### 5.2. Consequences of clock drift

Suppose the Authorization Server issues a token with `nbf=10:00:00Z`, `exp=10:05:00Z`.

- If a Resource Server's clock runs 90 seconds fast, the token may be treated as prematurely expired.
- If a Resource Server's clock runs 90 seconds slow, the token may still be accepted past its real-time `exp`; configured clock skew extends that window further.
- If the Authorization Server's clock runs slow, newly issued tokens may carry `iat`/`nbf` in the past relative to real time; if it runs fast, tokens may not yet have reached `nbf` according to a Resource Server's clock.
- Clock drift also makes logs across services hard to correlate, impacting audits, TLS certificates, refresh schedules, and expiration jobs.

Clock skew is a tolerance safeguard at the token validation layer. It does not fix OS clocks and does not replace NTP.

### 5.3. Synchronizing with NTP and chrony

On Linux, `chronyd` synchronizes the system clock against one or more NTP sources. Chrony documentation recommends at least three time sources to improve detection of faulty sources and maintain reliability. Inside internal networks, organization-managed NTP servers can be used; nodes should adhere to the same time-source policy.

Illustrative configuration example in `/etc/chrony/chrony.conf`:

~~~conf
server ntp1.example.net iburst
server ntp2.example.net iburst
server ntp3.example.net iburst

driftfile /var/lib/chrony/drift
makestep 1 3
rtcsync
~~~

Meaning:

- `server` declares an NTP source; `pool` can be used if a DNS name resolves to multiple servers.
- `iburst` speeds up initial synchronization.
- `driftfile` stores the clock frequency error estimate so chrony starts up more stably.
- `makestep 1 3` permits stepping the clock when offset exceeds threshold during the first three updates. Stepping time can affect running processes, so configure thresholds and timing to fit operational policy.
- `rtcsync` keeps the hardware RTC updated from the system clock on supported platforms.

Use the following commands to check status:

~~~bash
# OS synchronization status
timedatectl status

# Offset between system clock and selected time source
chronyc tracking

# List of sources, currently selected source, and reachability
chronyc sources -v

# Quality statistics of time sources
chronyc sourcestats
~~~

In `chronyc sources -v` output, `*` typically marks the currently selected source; `+` marks combined sources. Monitor fields such as `Reach`, `LastRx`, `Last sample`, `offset`, and `root dispersion`. If `Reach` is `0`, the host is not receiving valid responses from that source; check DNS, firewall, and UDP port 123.

On Windows Server, use the Windows Time Service and inspect with:

~~~powershell
w32tm /query /status
w32tm /query /source
~~~

Do not configure multiple services to adjust the system clock on the same host without an explicit design. Let a single chosen time synchronization service run and monitor it.

### 5.4. Nodes, containers, and Kubernetes

In standard container deployments, containers share the kernel's realtime clock on the host node. Therefore, time synchronization must be configured and monitored at the host/worker-node level. Do not simply install an NTP client inside an application image and assume every pod is synchronized.

Verification steps:

1. Confirm all worker nodes use the same trusted NTP source group.
2. Monitor clock offset and sync status on every node.
3. Ensure new nodes are synchronized before receiving workloads that issue or verify JWTs.
4. Re-check after VM resume, node reboot, network changes, or NTP connectivity loss.
5. Alert when time sources become unreachable or offset exceeds operational thresholds.

If a platform uses time namespaces or specialized time virtualization, verify actual behavior in the environment rather than assuming all containers observe the exact same clock.

## 6. Configuring clock skew in Spring Security

Spring Security Resource Server uses `JwtTimestampValidator` to check the validity window based on `exp` and `nbf`. Current documentation describes a default clock skew of 60 seconds. You can set an explicit tolerance when operational requirements call for a different value.

Example configuring a servlet Resource Server using issuer discovery and a 30-second tolerance:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuerUri = "https://auth.example.com";

    NimbusJwtDecoder decoder =
            (NimbusJwtDecoder) JwtDecoders.fromIssuerLocation(issuerUri);

    OAuth2TokenValidator<Jwt> validator =
            new DelegatingOAuth2TokenValidator<>(
                    new JwtIssuerValidator(issuerUri),
                    new JwtTimestampValidator(Duration.ofSeconds(30))
            );

    decoder.setJwtValidator(validator);
    return decoder;
}
~~~

This is an illustrative configuration for when you need to construct `JwtDecoder` manually. If you already use Spring Boot's `issuer-uri` property without custom validators, you can keep auto-configuration. When declaring `JwtDecoder` manually, ensure the validator still checks issuer, timestamps, audience, and application-specific constraints; do not accidentally replace the entire default validator with one that checks only timestamps.

The 30-second leeway in the example is illustrative, not a fixed recommendation. Choose the value based on measured offset metrics across nodes and security requirements. If you constantly have to raise clock skew to make requests succeed, address the root cause of the clock drift.

You can use `JwtTimestampValidator#setClock` to test logic with a fixed clock so tests do not depend on wall-clock time:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator validator =
        new JwtTimestampValidator(Duration.ofSeconds(30));

validator.setClock(
        Clock.fixed(
                Instant.parse("2026-11-16T10:00:00Z"),
                ZoneOffset.UTC
        )
);
~~~

A fixed clock is only for tests or logic requiring deterministic time control. Never put a mocked clock into production configuration.

For measuring elapsed durations within a single process, such as timeouts or request processing latency, use a monotonic clock like `System.nanoTime()` instead of subtracting two `Instant` values. Wall-clock time can be stepped or adjusted by NTP; monotonic clocks are better suited for measuring elapsed intervals.

## 7. Monitoring and troubleshooting

### 7.1. Metrics to monitor

| Category | Metric or event | Meaning |
|---|---|---|
| Signing keys | Active signing `kid` per replica | Detects a node using the wrong key version |
| JWKS | Set of `kid` values, public key fingerprints, update timestamps | Detects inconsistent JWKS or slow updates |
| JWT verification | Signature errors, unknown `kid`, issuer/audience mismatches | Distinguishes key distribution failures from token configuration errors |
| Time | Clock offset, root dispersion, selected NTP source | Detects unsynchronized nodes |
| Platform | Node reboot, VM resume, NTP source unreachable | Identifies causes of clock drift |
| Tokens | `expired` and `not-before` error rates | Detects time issues or TTL misconfiguration |

Never log raw token values, private keys, or KMS secrets. For verification errors, log the error category, configured issuer, sanitized `kid`, and request correlation ID according to security policy.

### 7.2. Quick diagnostic table

| Symptom | Possible cause | Resolution |
|---|---|---|
| Signature errors appear only as load increases | Replicas sign with different keys | Compare JWKS and `kid` per replica |
| New token has a `kid` but Resource Server reports key not found | JWKS/cache not yet updated | Check endpoint, cache TTL, and refresh mechanism |
| Unexpired token reported as expired | Resource Server clock running fast or wrong `exp` | Check `chronyc tracking`, `exp`, and clock skew |
| Newly issued token reported as not yet valid | Issuer/verifier clocks drifted or `nbf` set wrong | Compare UTC across nodes and inspect `nbf` claim |
| Errors appear after restart | Application generates a new key on startup | Load provisioned keys from a stable source |
| Only one API rejects tokens | That API's audience or issuer config is wrong | Check `iss`, `aud`, metadata, and validators |

### 7.3. Post-deployment verification runbook

After every Authorization Server rollout or key set change:

1. Verify replicas are ready and share the same issuer.
2. Fetch JWKS through the load balancer and from individual replicas; compare `kid` values and public key fingerprints.
3. Issue tokens through each replica if individually routable; confirm the header `kid`.
4. Verify each token using Resource Servers representative of each deployment zone.
5. Check clock offset on both Authorization Server and Resource Server nodes.
6. Confirm logs show no spikes in signature, unknown `kid`, expired, or not-before errors.
7. Record key version, fingerprint, rollout time, and verification results in the audit record.

If the deployment includes a key change, additionally verify the overlap window and that old tokens remain verifiable before removing the old public key.

## 8. Operations checklist

- [ ] All replicas use a single public, stable issuer URL.
- [ ] Signing keys are provisioned and stored in KMS/HSM/secret manager or a controlled key store.
- [ ] Restarting a replica never generates an unplanned new signing key.
- [ ] Each key has a unique `kid` and algorithms are explicitly allow-listed.
- [ ] The JWK Set endpoint publishes only public keys.
- [ ] Every replica's JWKS contains the exact same required key set.
- [ ] Resource Servers verify signatures, issuer, audience, and timestamps.
- [ ] Key rotation publishes the new public key before switching signing.
- [ ] Old public keys are retained long enough for unexpired tokens and JWKS caches.
- [ ] All nodes use trusted NTP sources with clock offset monitoring.
- [ ] Clock skew is explicitly set based on metrics and kept small.
- [ ] Runbooks include steps for compromised private keys and node clock desynchronization.

## 9. References

1. [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): configuring `JWKSource`, `JwtDecoder`, and RSA key examples.
2. [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): default endpoints and JWK Set endpoint registration conditions.
3. [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, JWKS URI, JWT verification, and validator customization.
4. [Spring Security API — JwtTimestampValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html): configuring clock skew and the clock used for timestamp checks.
5. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set, public/private key material, and `kid` in key rollover.
6. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `NumericDate` and the `exp`, `nbf`, and `iat` claims.
7. [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): verifying algorithms, issuer, audience, and handling untrusted headers/claims.
8. [chrony — Frequently Asked Questions](https://chrony-project.org/faq.html): configuring NTP clients, number of time sources, and diagnosing clock synchronization.

