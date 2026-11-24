# Rotating Keys, Secrets, and Certificates Without Temporarily Widening Permissions

## 1. Objectives and Scope

This lesson belongs to **Spring Security reactive / secure deployment**. After completing it, you should be able to rotate JWT signing keys, secrets used by the application to authenticate with external services, and TLS/mTLS certificates while preserving the exact policy of **who may do what**. You will also know when a dual-version overlap window is required, when immediate revocation is mandatory, how to coordinate with Reactor/WebFlux, and how to verify before retiring the old version.

**Core principle:** *Credential rotation replaces the material proving identity; it does not grant additional privileges.* During cutover, you may temporarily accept **two signature-verification public keys**, **two application secrets with identical scope**, or **two certificates representing the exact same identity**. That never justifies adding new principals, loosening `scope`/`role`/`audience`, disabling authentication, or skipping hostname/signature checks.

Materials to distinguish:

| Material | Role | What Typically Changes | Permissions That Must Stay Invariant |
| --- | --- | --- | --- |
| JWT signing key (asymmetric) | Authorization server signs with **private key**; WebFlux resource server verifies with **public JWK** | New key pair, new `kid`, issuer's JWKS | `iss`, `aud`, lifetime, accepted algorithms, and scope/authority mapping |
| OAuth2 client secret, API key, DB password | Workload authenticates to a service provider or DB | Secret version in secret manager and at partner | Client identity, service account, DB privileges, granted scope list |
| TLS server certificate/private key | Proves HTTPS endpoint identity | Leaf certificate, private key, corresponding chain | Valid DNS/SAN, allowed trust anchors, and TLS policy |
| mTLS client certificate | Proves calling workload | Client certificate/private key and possibly issuer CA | Workload identity, SAN/SPIFFE ID (if used), server access policy |
| CA/trust bundle | Determines which identities are trusted | Trusted CA/intermediate or specific pin | Allowed identity set must remain constrained; never turn CA trust into API authorization |

Example: a resource server validates bearer tokens with `orders.read` signed by a valid issuer. When rotating signing key `k-old` to `k-new`, it may verify both signatures during a window, **yet still only accepts** the same issuer, audience, signature algorithm, expiry, and `orders.read` permission as before. A validly signed token never automatically gains `orders.write`.

## 2. Two Dimensions of Rotation: Compatibility and Privilege

A safe rotation must solve **two distinct problems**:

1. **Availability:** clients/servers not yet switched to the new key/secret/certificate can still process valid requests within the calculated window.
2. **Privilege invariance:** there is never a "temporarily loosened" privilege phase to avoid transition errors. New material must never turn a `reader` account into `admin`, allow a new audience, or skip certificate validation.

Separate three concepts:

- *Identity* — the authenticated principal/service account or certificate identity.
- *Credential/material* — what proves identity: private key, bearer token, secret, certificate.
- *Authorization* — that identity's permissions on specific resources.

One identity may hold multiple valid credentials during a transition; **authorization must be evaluated separately** per request/connection/token under the exact active policy. Both the authorization server's token-issuance policy and the resource server's access-decision policy must remain stable.

Anti-pattern to eliminate:

```java
// WRONG: altering access permissions just to make rotation "error-free".
return http.authorizeExchange(ex -> ex
        .anyExchange().permitAll())
    .build();
```

Similarly, never temporarily use `hasAnyRole("READER", "ADMIN")`, disable signature/JWT issuer checks, trust all CAs, switch a TLS client to `trustAll`, or grant namespace-wide `get/list secrets` permissions to a workload just so it can read a new secret.

## 3. Standard Rotation Model: Prepare → Coexist → Cut Over → Revoke

This model applies to planned rotations when material **has not been leaked**. If there is evidence of compromise, switch to the emergency procedure in section 10.

| Phase | Operator Actions | What Must Be Verified |
| --- | --- | --- |
| 0. Inventory | List issuer, secret/cert ID, owner, environment, consuming workloads, refresh method, TTL, caches, long-lived connections, expiration deadline | No missed consumers or hardcoded clients |
| 1. Prepare | Generate new material, store in secret manager/KMS/CA, set least-privilege read access, check format/SAN/cert chain | New credential represents **the same identity and permissions**, no wildcard trust |
| 2. Pre-distribute | Publish public verification key/JWKS, add the new credential in the auth system or proper trust chain | Consumers see the new version before use; canary test |
| 3. Activate | Switch signer or new clients to use the new version; roll out via canary/rolling deployment | AuthN/AuthZ succeed; no abnormal spikes in 401/403, TLS handshakes, or latency |
| 4. Overlap window | Keep old version valid for the exact approved duration | No new tokens/sessions issued with old material; no widened scope, issuer, or CA |
| 5. Revoke/cleanup | Stop accepting old version; delete old version from secret store/JWKS/trust once conditions are met | All clients on new version; old tokens expired; caches expired; no leaked backups |
| 6. Verify | Intentionally test with old material and wrong-privilege material | Properly rejected; mark old version revoked and archive operational evidence |

Switching **readers before writers** is the standard rule for JWT keys: publish the new public key so verifiers learn it first, then switch the private key used to sign new tokens. For client secrets, provision acceptance of the new secret on the provider side before rolling out to clients; for TLS CAs, align trust chains across parties before changing leaf/client certs.

**There is no fixed formula for the overlap window.** It depends on token lifetime, the last `exp` of tokens signed by the old key, clock skew, JWKS caching, consumer refresh intervals, deployment/rollback duration, and connection lifetimes. Keep overlap only until real conditions are satisfied. Too long an overlap extends old credential exposure; too short an overlap breaks legitimate users.

## 4. Rotating JWT Signing Keys in Spring Security WebFlux

### 4.1. Valid Architecture

```text
Authorization Server / Identity Provider
  Signing keys: old private key -> new private key
  Public JWK Set: {old public JWK, new public JWK} during overlap window
                          |
                          | HTTPS + cache/refresh
                          v
Spring Security Reactive Resource Server
  Bearer token -> ReactiveJwtDecoder -> verify signature
                                   -> iss / aud / exp / nbf
                                   -> scope/authority
                                   -> authorizeExchange()
                          |
                          v
                     API protected
```

The `kid` header helps the verifier select the matching public JWK; it is **only a hint supplied by the token**, not proof of trust. Always verify the signature, allowed algorithm, and all required claims. Never use `kid` to read arbitrary file paths or call token-specified URLs; never accept `alg=none`. In multi-tenant setups, bind issuer/JWKS via configuration or an allowlist—never let a bearer token choose its own trusted issuer.

In a Spring Boot 3.3 project with WebFlux, add the corresponding starters and let Spring Boot manage dependency versions:

```groovy
// build.gradle of a Spring Boot application with dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Specific issuer, JWKS, and audience configuration for **one system**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://id.example.org/tenant-a"
          jwk-set-uri: "https://id.example.org/tenant-a/jwks"
          audiences:
            - "orders-api"
```

`issuer-uri` validates the `iss` claim. Also provide `jwk-set-uri` when you want to specify the JWKS endpoint upfront rather than relying on startup discovery. Spring Security reactive supports new public keys in JWKS and refreshes verification keys under the decoder's refresh/cache rules. **Do not replace the decoder with a hardcoded single-public-key implementation** if ongoing rotation is required. If declaring a custom `ReactiveJwtDecoder`, preserve all mandatory validators (issuer, audience, timestamps) and the refresh/caching strategy.

Illustrative WebFlux policy:

```java
// ApiSecurityConfig.java in a Spring-scanned package
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {
    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Spring Security maps standard JWT scopes to authorities prefixed with `SCOPE_` by default. At **every point during rotation**, the order-reading path still requires `SCOPE_orders.read`; undeclared operations remain denied. This is a configuration component of a Spring WebFlux application, not a standalone `main` program. Configure readiness/management endpoints per your infrastructure; never change `anyExchange().denyAll()` to `permitAll()` just to run health checks.

### 4.2. JWT Signing Workflow with `kid` and JWKS

Suppose the IdP signs JWTs with a 15-minute max lifetime, `kid=k1`. A sample timeline:

| Time | Published JWKS | Key Signing New Tokens | Expectation |
| --- | --- | --- | --- |
| T0 | `k1` | `k1` | Existing tokens valid |
| T1 | `k1`, `k2` | `k1` | Resource servers learn `k2` via refresh; canary verified |
| T2 | `k1`, `k2` | **`k2`** | New tokens use `k2`; unexpired `k1` tokens still accepted |
| T3 | `k1`, `k2` | `k2` | No valid `k1` tokens remain per TTL + skew; consumers/caches verified |
| T4 | **`k2`** | `k2` | Remove `k1`; tokens signed with `k1` rejected once verifiers refresh JWKS |

T1 must be early enough for distributed JWKS caches to learn the new key. T3 must be late enough relative to **the last `k1` token issued**, not just when `k2` was created. T4 may not take effect immediately on every consumer if stale caches have not refreshed; therefore monitor cache TTLs, timeouts when the IdP is unreachable, and actual refresh behavior.

If policy requires **immediate revocation** of stolen tokens, offline-verified self-contained JWTs do not achieve instant revocation simply by deleting a JWK at the IdP. Consumers with cached keys can still verify signatures until caches expire or are invalidated. You need revocation/denylist mechanisms, short token lifetimes, opaque tokens/introspection, or session controls matching requirements, tested empirically.

### 4.3. Do Not Drift Permissions While Changing Keys

The dangerous failure is not having two public JWKs, but altering policy:

- Do not add another issuer as a fallback if the current issuer's JWKS fails.
- Do not drop `aud` checks or switch to a wildcard audience.
- Do not widen allowed signing algorithms to "any algorithm" to accept mismatched tokens.
- Do not trust privileges from unverified claims, or trust `role=admin` merely because a JWT payload decodes.
- Do not give `k1` or `k2` tokens separate version-based policies. Permissions come from verified identity/claims and a consistent authorization model.
- When the JWKS source is unreachable, either use a bounded stale cache or fail authentication per approved policy; never accept unverified signatures.

Never deploy a **private signing key** onto a resource server whose role is solely verification. Private keys belong to the signer/authorization server or HSM/KMS; JWKS publishes only public keys, **never private keys**.

## 5. Rotating Secrets for OAuth2 Clients, API Keys, and DBs

Unlike JWT public verification keys, client secrets, API keys, and DB passwords are **secrets presented directly to authenticate**. Rollover relies on two distinct secrets representing the exact **same identity with the same permissions** for a short window, when supported by the provider.

### 5.1. OAuth2 Client Credentials

Example: WebFlux app `orders-api` calls `inventory-api` using OAuth2 `client_credentials`:

- Client registration uses `client-id=orders-reader` with maximum scope `inventory.read`.
- Secret v1/v2 only changes how the client proves it is `orders-reader`; **never grant `inventory.write`**, extra grant types, audiences, or roles.
- At the IdP, create secret v2 for the existing client if the IdP allows multiple active secrets; roll v2 out to the app; verify new token acquisition; revoke v1.
- If the IdP allows only one secret, use a provider-controlled rotation technique (e.g., a parallel client identity with **equivalent** policy and monitored cutover), accept planned downtime, or use supported key/cert-based auth. Never assume every provider supports dual secrets.

Spring Security reactive provides `ReactiveOAuth2AuthorizedClientManager` and `WebClient` integration to acquire/refresh access tokens across their lifecycle. **Changing a client secret does not revoke previously issued access tokens**, nor will startup-constructed `ClientRegistration` or authorization manager beans automatically reload a new secret. Define how configuration loading, authorized-client caching, token refresh, registration recreation, or rolling restarts work by design. Verify that *a fresh token request after cutover* uses secret v2, rather than relying on a request succeeding with an unexpired old access token.

For systems requiring mTLS or `private_key_jwt` instead of static client secrets, use IdP-supported mechanisms with pinned approved policies. Do not hand-roll JWT client authentication missing `aud`, `iss`, `sub`, `jti`, or provider replay protections.

### 5.2. Secret Manager and Reactive Boundaries

Applications should receive secrets at runtime from a secret manager/mounted volume or workload identity authorized for the exact secret path. Never record secrets in Git, Docker images, logs, command-line arguments, exceptions, trace attributes, or responses. Do not place raw secret values into the Reactor `Context` just to pass them across operators; for short-lived material, use dedicated components and limit lifetime/observability.

If the secret manager SDK offers only a **blocking** API, never invoke it directly on the Netty event loop:

```java
// Integration snippet, not a standalone program.
// secretClient.readCurrent() is a hypothetical blocking provider SDK call.
Mono<SecretVersion> fetched = Mono.fromCallable(
            () -> secretClient.readCurrent("orders/inventory-client"))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(3));
```

Import `reactor.core.publisher.Mono`, `reactor.core.scheduler.Schedulers`, and `java.time.Duration`, along with the provider's `SecretVersion`/`secretClient` types. **Never log `SecretVersion` if it contains secret values.** Configure bounded retries/backoff and alerting; never turn secret-read failures into `permitAll`, bypass authentication, or "use an arbitrary fallback secret." If a truly non-blocking SDK exists, prefer it over `boundedElastic`.

When swapping secrets in memory, an immutable snapshot/atomic reference ensures new requests use a consistent version. Still, check impacts on connection pools, client beans, and long-lived sessions. Swapping an `AtomicReference` inside a JVM does not notify the IdP, recycle connection pools, or synchronize across pods.

### 5.3. Database Passwords and Pools

Rotating the password of the **same DB user** is only seamless if the server supports a dual-credentials window, existing connections keep working, and the pool opens new connections with the new password. For systems without dual-password support, you can prepare a v2 account **with the exact same verified least privileges**, update the app, then disable v1—provided parallel accounts comply with approved operational policy and do not create privilege escalation paths.

For R2DBC/reactive DBs or async client pools, verify: whether the pool can recreate its connection factory when the secret changes; how long open connections live; and during rollback how many pods hold v1. If the library reads passwords only at startup, perform rolling restarts/redeploys rather than assuming open connections immediately switch credentials.

## 6. Rotating HTTPS/mTLS Certificates

### 6.1. Mandatory TLS Components

Server certificates must have a SAN matching the hostname clients call, be unexpired, chain validly to an allowed trust anchor, and use approved algorithms/extended key usages. The new private key must actually match the public key in the new certificate. When replacing a leaf certificate signed by the **same CA**, clients usually need no trust store loosening. When changing CAs, a trust-anchor transition window may be needed; trust only intended CAs rather than importing unrelated CA bundles.

**mTLS involves two separate steps:** TLS validates both peers' certificates, then the system must map the certificate identity (e.g., SAN or SPIFFE workload identity) to an authorized principal. Merely being signed by a trusted CA **does not mean** the certificate holder can access every endpoint. Never change `client-auth: need` to `want`/`none` to work around rotation errors; never skip hostname verification when a certificate has the wrong SAN.

### 6.2. Spring Boot WebFlux / Netty SSL Bundles

Spring Boot 3.3 provides `SslBundle` from PEM/JKS/PKCS12 and supports reloading file-based PEM bundles on compatible embedded Netty servers. Example server TLS with infrastructure-managed cert and key files:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/app/tls/tls.crt"
            private-key: "file:/etc/app/tls/tls.key"

server:
  ssl:
    bundle: "webserver"
```

This is a **one-way server TLS** example. To require inbound mTLS, configure trust material and enforce client certificates—for example, the **same bundle** extended with:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/app/tls/tls.crt"
            private-key: "file:/etc/app/tls/tls.key"
          truststore:
            certificate: "file:/etc/app/tls/trusted-client-ca.pem"

server:
  ssl:
    bundle: "webserver"
    client-auth: "need"
```

This is a sample configuration in an app using the Netty SSL server and a certificate identity-mapping policy. **Do not** copy both standalone `spring`/`server` blocks into the same file without merging YAML; pick one model. Before rollout, verify properties on the project's exact Spring Boot/Netty version and observe the actual certificate presented during handshake.

`reload-on-update` watches files and reloads on change; that **does not mean** every library, outbound `WebClient`, SSL context cache, or open connection automatically adopts the new material. Established TLS connections do not normally re-handshake immediately; bound connection lifetimes or recreate clients/pools as needed. If the environment does not support full hot reload, rolling restarts gated by readiness/liveness are a valid path with canary and rollback.

### 6.3. Scenarios for Rotating CAs and mTLS Client Certificates

When rotating root/intermediate CAs for mTLS clients:

1. Validate the list of accepted workload identities, SANs/EKUs, and application ACLs; clarify which identities the new CA is permitted to issue.
2. Provision trust only for the approved CA; bind authorization to **specific client identities** rather than "any cert under this CA."
3. Issue new client certificates with the exact identity, distribute private keys securely, and test one canary client.
4. Cut remaining clients over to new certificates; monitor handshake errors and application `403`s separately.
5. Remove the old CA/certificate from trust on schedule; if the old CA is compromised, follow the emergency procedure with identity revocation/rotation and controlled disruption.

**Changing a public trust anchor** differs from rotating a leaf certificate. Do not treat "temporarily trusting both CA A and CA B" as harmless: it can expand the set of accepted certificates. If CA overlap is necessary, constrain it by SAN/name constraints, workload mapping, policy, and a strict time bound. Never widen principal/role lists just because the trust store holds an extra CA.

## 7. Distribution Infrastructure: Kubernetes and Secret Managers

In Kubernetes, secrets can be attached to Pods as files or environment variables. When material must update while the app runs:

- Secrets mounted as normal volumes are updated by kubelet **eventually**, not instantaneously; the app needs a matching reread/reload/rollout mechanism.
- Secrets injected via environment variables are read only at container startup; updating the Kubernetes Secret **does not update the env of running processes**.
- Secrets mounted via `subPath` do not receive normal secret volume updates.
- Create new secret versions scoped to the specific workload, restrict RBAC/KMS, canary-deploy, verify non-secret checksums/metadata, and only then revoke the old version.

Deployment excerpt illustrating **volume mount only**, not a complete manifest:

```yaml
spec:
  template:
    spec:
      automountServiceAccountToken: false
      containers:
        - name: orders-api
          image: registry.example.org/orders-api:1.0
          volumeMounts:
            - name: tls-material
              mountPath: /etc/app/tls
              readOnly: true
      volumes:
        - name: tls-material
          secret:
            secretName: orders-server-tls
```

When the app does not call the Kubernetes API, disabling default service-account token mounting shrinks the attack surface. Pods **do not need namespace-wide RBAC `list secrets`** to use kubelet-mounted volumes. If using a CSI driver/external secrets operator, verify its exact sync timing and rollback behavior; do not assume identical update semantics to native Secret volumes.

When swapping a certificate/private-key pair, never let a process read a new certificate with an old key in a half-updated state. Use platform-supported atomic directory/symlink version publishing and verify compatible reload steps; design rollback for the **entire** cert-key pair. Grant tight file permissions, avoiding solutions that run the app as root just to read secrets.

## 8. Authorization Must Not Change Across Cutover

"Having two valid credentials" is completely different from "granting extra privileges":

| Scenario | Valid During Overlap? | Why |
| --- | --- | --- |
| Public JWKs `k1` and `k2` from the **same allowed issuer** used to verify | Yes, for a defined window | Two signature verification keys, same validator and policy |
| Secrets `v1` and `v2` for the **same OAuth client**, same grants/scopes | Yes, if IdP supports it | Facilitates technical cutover |
| New leaf cert for the exact SAN, same trust level | Yes | Endpoint identity unchanged |
| Accepting tokens from a different issuer because old JWKS failed | **No** | Changes trusted identity source |
| Setting `anyExchange().permitAll()` or adding `SCOPE_admin` | **No** | Widens authorization |
| Switching TLS trust manager to trust-all | **No** | Disables identity verification |
| Granting wildcard secret-manager permissions to service account | **No** | Widens secret read access |
| Keeping old and new CAs without binding certificate identity | Needs redesign | CA overlap can widen accepted workloads |

When a resource server accepts two JWT variants in the same window, **the same `SecurityWebFilterChain` must decide authorization for both**. JWKS provides only public verification material. If the signer emits different claims/scopes, that is a policy change requiring separate review—do not bundle it into rotation.

To prevent "temporary" privileges, enforce an invariant baseline like this:

```text
Before rotation:
  principal = orders-reader
  scope     = orders.read
  audience  = inventory-api
  issuer    = https://id.example.org/tenant-a

During and after rotation:
  principal = orders-reader
  scope     = orders.read
  audience  = inventory-api
  issuer    = https://id.example.org/tenant-a

Only credential version (v1 -> v2) changes.
```

If any principal/scope/audience/issuer/ACL must change, handle it as a **separate authorization change request** with independent testing and approval. Never bundle "temporary extra permissions" into a credential rotation plan.

## 9. Java 17 Demo: Promote Only Versions That Preserve Scope

The following example is a mental-model exercise for version management. It **contains no real secrets**, does not replace IAM/IdP, does not sync across pods, and is not production credential code. Its goal is to show the invariant: only change versions when permissions remain identical.

Save as `RotationInvariantDemo.java`:

```java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public final class RotationInvariantDemo {
    private static final Set<String> APPROVED_SCOPES =
            Set.of("orders.read");

    record Credential(String version, Set<String> scopes) {
        Credential {
            Objects.requireNonNull(version);
            scopes = Set.copyOf(scopes);
        }
    }

    private static final AtomicReference<Credential> ACTIVE =
            new AtomicReference<>(
                    new Credential("v1", APPROVED_SCOPES));

    static void promote(Credential candidate) {
        if (!candidate.scopes().equals(APPROVED_SCOPES)) {
            throw new IllegalArgumentException("scope drift");
        }
        ACTIVE.set(candidate);
    }

    public static void main(String[] args) {
        System.out.println("before=" + ACTIVE.get().version());
        promote(new Credential("v2", Set.of("orders.read")));
        System.out.println("after=" + ACTIVE.get().version());
        try {
            promote(new Credential(
                    "v3", Set.of("orders.read", "orders.write")));
        } catch (IllegalArgumentException e) {
            System.out.println("reject=" + e.getMessage());
        }
        System.out.println("active=" + ACTIVE.get().version());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac --release 17 RotationInvariantDemo.java
java RotationInvariantDemo
```

Stdout output:

```text
before=v1
after=v2
reject=scope drift
active=v2
```

`AtomicReference` creates an atomic promotion point within one JVM. In real systems, policies/invariants are enforced across IdP, IAM, DB grants, API authorization, gateways, and/or secret managers; consistent transactions/rollouts, client refresh mechanisms, observability metrics, drift detection, and permission checks across all components are needed—not just a single `Set` comparison.

## 10. Emergency Rotation When Key or Secret Compromise Is Suspected

Never mechanically apply a normal overlap schedule during a compromise. An exposed v1 credential may already be used to impersonate the identity; keeping v1 valid just to avoid downtime can amplify damage.

Response depends on material type:

- **Compromised JWT signing private key:** stop issuing tokens with the old key, issue a new key and update verifiers' trust configs as fast as possible; revoke/block old tokens via available mechanisms, check JWKS caches, token lifetimes, and copies; audit previously signed tokens. Communicate availability impact openly when invalidating old tokens.
- **Compromised OAuth2 client secret/API key:** revoke the secret at the IdP/provider, issue a new secret with the exact least-privilege identity/permissions, update workloads, and locate/invalidate issued tokens if supported. Changing the secret alone does not guarantee all old access tokens are revoked.
- **Compromised TLS private key:** revoke/replace the certificate, rotate the private key, deploy the new trust chain; check OCSP/CRL and how each client actually handles revocation; never assume every client checks OCSP or all old TLS sessions terminate automatically.
- **Compromised CA/CA private key:** review all identities that could be forged, replace trust anchors and identity bindings, and do not temporarily trust certificates issued by that CA.

Emergencies may require **fail closed** or controlled downtime, especially when cached consumers cannot be flushed immediately. Document decisions with an accountable owner and strict time limit; never turn an emergency exception into a long-lived `permitAll` rule.

## 11. Testing Before, During, and After Rotation

### 11.1. JWT/Authorization Test Matrix

| Case | Expectation |
| --- | --- |
| `k1` token before T2, valid `iss/aud/exp/scope` | `200` on permitted endpoint |
| `k2` token after T2, same valid claims | `200` on permitted endpoint |
| Unexpired `k1` token during overlap | Verified up to approved cutoff; no extra scopes |
| `k1` token after expiry or true key revocation | `401` (invalid token); account for verifier key cache |
| Token with unknown signature, unknown `kid`, `alg=none` | `401` |
| Valid token missing `orders.read` | `403` on scope-protected endpoint; `401` if token fails authentication |
| Valid signature but wrong `iss` or `aud` | `401` |
| JWKS endpoint down | Controlled behavior per cache/timeout policy; never bypass verification |

HTTP status codes distinguish **authentication** (401 when identity cannot be proven) and **authorization** (403 when authenticated without sufficient permissions). Depending on filter chains, custom exception handlers, opaque tokens, or operational errors, exact statuses may vary; tests must assert against intended policy.

### 11.2. Secret and TLS Test Matrix

1. **Client credentials:** declare secret v2 successful only after forcing a fresh token request; verify v1 is rejected after revocation. New token's scope/identity/audience must match baseline.
2. **Concurrent requests:** canary and old pods run together without mixing secrets/certs across requests or leaking credentials in `Reactor Context`, MDC, logs, or traces.
3. **Long-lived connections:** verify connection pools, WebSockets/HTTP2 (if any), and never assume TLS renegotiation; confirm new handshakes serve the new certificate.
4. **mTLS:** valid client certificate with matching workload identity is allowed; a certificate with a valid chain whose identity is not in the allowlist must still be rejected.
5. **Invalid certificates:** SAN mismatch, expired, key mismatch with certificate, untrusted chain; never use trust-all as a workaround.
6. **Distribution failures:** slow secret manager/JWKS/volume refresh where one pod holds an old version; bounded retries, alerts, and deterministic rollback.
7. **Revocation:** after overlap ends, intentionally present old credentials and verify no new sessions/connections succeed; verify caches are not bypassed.
8. **Permissions:** compare `principal, scope, role, audience, route policy, DB grants, CA/SAN allowlist` before and after. No unapproved additions.

Never test with production keys/secrets; use short-lived staging/canary material under matching policies. Build negative test suites with badly signed tokens, missing scopes, and wrong-SAN certs. Always measure both **security and availability**.

## 12. Observability, Rollback, and Operations

Signals to track:

- **Security metrics:** failed token verifications, unknown `kid`, `iss/aud` mismatches, 401 authentication failures, 403 authorization denials, TLS handshake failures, client secrets rejected by providers. Track baselines and separate intentional test errors from real failures.
- **Rollout metrics:** active version per workload (opaque identifier only), updated pod counts, time until last old token `exp`, certificate expiration, SSL reload success/failure counts, canary traffic ratio.
- **Stability metrics:** latency, 5xx from IdP/secret-store dependencies, connection timeouts, new pool connection failures, collector status, and health checks.

Logging should record only `credentialVersion=v2` or non-reversible hashes/identifiers—**never print raw secrets, authorization headers, JWTs, private keys, or certificate private-key PEMs**. Avoid high-cardinality metric labels using full tokens, user IDs, large serial numbers, or secret values. Initiating rotation should not require global admin rights: operators/automation need rights to create versions within scope, reviewers approve policy, and workloads read only their own credentials.

Rollback also has boundaries: when secret v1 **has not been revoked and was not leaked**, you may temporarily revert to v1 within the approved window and investigate root cause. When v1 **was compromised/revoked**, rolling back to v1 is unsafe; fix v2, issue v3, or halt cleanly. Never roll back via `permitAll`, `trustAll`, disabling JWT validation, or granting `admin`.

### Pre-Cutover Abbreviated Runbook

```text
[ ] Inventory of owners/consumers/TTL/caches and old secret/cert copies ready.
[ ] Before-after policy compared: principals, scopes, aud, iss, roles,
    API routes, DB grants, SAN, CA trust, and mTLS identity.
[ ] New material issued in proper store; private key/secret protected.
[ ] Verifiers/trust consumers ready to accept new material.
[ ] Canary passes both positive tests and wrong-privilege rejection tests.
[ ] Writer/client cutover monitors 401/403, TLS, 5xx, and latency.
[ ] Overlap end milestone set based on real token TTL/cache/connection lifetimes.
[ ] Old version revocation tested and new clients confirmed healthy.
[ ] Separate rollback plans defined for normal cutover vs. incident.
[ ] Temporary operator privileges revoked, old versions/copies cleaned, audit saved.
```

Operational privileges granted to automation (if needed) must be dropped to least privilege immediately after finishing; **never** grant read access to every project's secrets while waiting. For multi-region production, verify each region and consumer group before removing old versions.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Removing `k1` from JWKS right after signer switches to `k2` | Unexpired `k1` tokens suddenly get 401 | Publish `k2` early, wait TTL + skew + reasonable cache time before removing `k1` if uncompromised |
| Relying on `kid` or JWT payload without verifying | Can trust attacker-crafted data | Use `ReactiveJwtDecoder` configured with issuer/JWKS/validators |
| Using `permitAll`/skipping issuer check during IdP outage | Privilege escalation | Fail closed per policy, alert, fix IdP/cache |
| Updating secret only in Vault while bean keeps v1 | Client keeps requesting tokens with old secret | Use reload/registration recreation/rolling restart, force fresh token request |
| Rotating DB password with open pool without testing new connections | Delayed failures when connections recreate | Canary opens new connections, drain old pool cleanly |
| Reloading TLS server cert assuming outbound `WebClient` updated too | Outbound still uses old trust/SSL context | Check each consumer; refresh/recreate outbound clients/pools separately |
| Opening truststore to any CA, dropping hostname checks | Accepts out-of-scope identities | Trust only approved CAs + SAN/name constraints + authorization identity |
| Mounting K8s Secret via `subPath` and waiting for hot reload | Container file never updates | Use normal directory mount or rolling restart |
| Logging tokens/secrets while debugging rotation failure | New leak, larger blast radius | Log safe identifier/version/status, redact all credentials |
| Revoking old signing key while forgetting JWKS cache | Old tokens remain verifiable for a window | Configure proper TTL/cache/revocation, test all verifiers |
| Issuing secret v2 with broader grants/scopes than v1 | Unintended privilege expansion | Diff policies and block promotion on drift |

## 14. Summary

A successful rotation satisfies **continuity**, **accurate authentication**, **invariant authorization**, and **verifiable revocation** simultaneously. With Spring Security reactive, use `ReactiveJwtDecoder` with JWKS/issuer/audience to support JWT key rotation while keeping `SecurityWebFilterChain` unchanged; for OAuth clients/API keys/DBs, coordinate secret lifecycles with caches and clients/pools; for TLS/mTLS, use appropriate SSL bundles/rollouts while verifying chains and certificate identities. Allow coexisting versions **of equal-privilege material** only when needed; never loosen IAM, API authorization, or TLS trust uncontrollably to mask cutover errors.

## Reference Documentation

- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Boot 3.3 — Resource Server configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Boot 3.3 — SSL bundles and reload: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Kubernetes — Secret distribution/update behavior: https://kubernetes.io/docs/concepts/configuration/secret/
- OWASP Cheat Sheet — Secrets Management: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
