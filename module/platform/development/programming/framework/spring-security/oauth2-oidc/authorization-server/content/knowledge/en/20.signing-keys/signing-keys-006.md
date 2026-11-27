# Persisting Keys Across Restarts and Sharing Keys Across Instances

## Lesson Objectives

In the **JWK and Key Management** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides you in designing storage and distribution for JWT signing keys so **Spring Authorization Server** preserves key identity across restarts and every instance in a cluster can verify tokens consistently. The content focuses on **Spring Security**, **Spring Authorization Server**, and **Spring Boot** applications running single or multiple replicas.

An Authorization Server cannot generate a new random signing key pair on every startup and expect old tokens to remain verifiable by Resource Servers. The private key must be protected and persisted stably; the corresponding public key must be published via JWKS with a stable **kid** identifier and trusted by Resource Servers. When deploying multiple instances, all instances must use the same active key set and a synchronized rotation strategy.

After this lesson, you will be able to:

- Distinguish private signing keys, public verification keys, JWK, JWK Set, and the JWKS endpoint.
- Understand why generating a new key at startup breaks old tokens after restarts or rolling deployments.
- Design durable storage using KMS/HSM, secret managers, keystores, or encrypted persistent storage.
- Configure Spring Authorization Server to use **JWKSource<SecurityContext>** and **NimbusJwtEncoder** backed by stable keys.
- Share keys properly across multiple Authorization Server instances, handling caching and rotation synchronization.
- Retain old public keys in JWKS while old tokens remain valid and caches may still hold them.
- Test restarts, scale-out, rolling deployments, failover, key rotation, and data recovery.
- Protect private keys, restrict signing permissions, audit operations, and establish a runbook for key compromise.

> **Running scenario:** An Authorization Server cluster runs three instances behind a load balancer. Each instance issues JWT access tokens for internal APIs. After instance A restarts or a request hits instance B, previously issued tokens must continue to verify. During rotation, tokens signed with the old key remain valid during the transition window, while new tokens use the new key.

## 1. Why Must Keys Remain Stable Across Restarts?

JWT access tokens are typically signed with a private key. The Resource Server receives the JWT and uses the public key to verify the signature. If the Authorization Server generates a new key pair on every restart, the public key the Resource Server previously relied on may no longer match tokens still in circulation.

Example:

~~~mermaid
flowchart TD
    A[Instance A startup] --> K1[Generate key K1]
    K1 --> T1[Issue JWT signed by K1]
    T1 --> R1[Resource Server verifies with public K1]
    A --> X[Restart]
    X --> K2[Generate unrelated key K2]
    K2 --> T2[Issue JWT signed by K2]
    T1 --> F[Old token still in circulation]
    R1 -->|Only K2 published| E[Signature verification fails for T1]
~~~

Token T1 has not expired yet, but its signature can no longer be verified if JWKS only publishes public key K2. Users may see APIs return 401 right after a deploy even though their access tokens are still valid.

Similar situations occur when:

- A new pod starts and generates its own key.
- Auto-scaling launches additional instances with different keys.
- Instance A signs a token, but the Resource Server fetches JWKS from instance B.
- A rolling deployment leaves some nodes using the old key set and others using the new key set.
- A database/secret store restores an inconsistent snapshot or loses key ID metadata.
- The old public key is removed from JWKS before old tokens and Resource Server caches expire.

**Principle:** Active signing keys must be persisted durably and distributed from a single trusted source. Every instance authorized to sign must select the exact same active key; every instance serving JWKS must return a consistent set of public keys.

## 2. Distinguishing Private Key, Public Key, JWK, and JWKS

| Concept | Contents | Who is allowed access? |
|---|---|---|
| Private signing key | Secret component used to sign JWTs. | Only the Authorization Server or KMS/HSM authorized to sign. |
| Public verification key | Public component used to verify signatures. | Resource Servers and token recipients. |
| JWK | JSON Web Key representation of a key; may hold public or private material. | Public JWK can be published; private JWK must be strictly protected. |
| JWK Set | A collection of JWKs in a JSON object with a `keys` field. | The public set is published via JWKS. |
| JWKS endpoint | HTTP endpoint returning the public JWK Set, often `/.well-known/jwks.json` per metadata. | Authorized clients/resource servers fetching public keys. |
| kid | Key ID in the JWS header, used to pick the right public key in JWKS. | Public, but must be unique within the relevant key set. |

A JWK can represent RSA, EC, or other key types. Abbreviated public RSA JWK example:

~~~json
{
  "kty": "RSA",
  "kid": "auth-signing-2026-01",
  "use": "sig",
  "alg": "RS256",
  "n": "PUBLIC_MODULUS_BASE64URL",
  "e": "AQAB"
}
~~~

These are placeholders, not real usable keys. **Never publish** private fields such as RSA `d`, `p`, `q`, `dp`, `dq`, `qi` or EC private scalar `d`. Private JWKs must remain inside a secrets management system; the public JWKS returns only public parameters.

### 2.1. kid Is an Identifier, Not a Secret

A JWS header typically includes:

~~~json
{
  "alg": "RS256",
  "kid": "auth-signing-2026-01",
  "typ": "JWT"
}
~~~

The Resource Server uses `kid` to select the verification key in the JWKS. `kid` must stay stable for the same key material and differ across distinct keys currently published. Never use the current timestamp or a random number generated on each process startup as `kid` for the same private key.

**Do not blindly trust `alg` declared by the JWT itself.** The Resource Server must restrict accepted algorithms by policy. Key ID only helps select a key, not prove a token is valid; signatures and claims must still be verified.

## 3. Why Must Each Instance Not Generate Keys Independently?

A cluster with three instances A, B, C must guarantee:

- A can sign a JWT and B/C do not omit its public key from publication.
- Any Resource Server fetching JWKS behind a load balancer receives a valid public key set.
- A token signed by A still verifies when subsequent requests hit C.
- Newly scaled-out instances load the exact same key set and active state.
- Restarts do not assign a new key ID to the same key or lose the active signing private key.
- Rotation rolls out across an ordered, synchronized key set version.

Architecture diagram:

~~~mermaid
flowchart TB
    subgraph Cluster[Authorization Server cluster]
        A[AS instance A]
        B[AS instance B]
        C[AS instance C]
    end
    S[(Shared secure key store / KMS / HSM)]
    A -->|load active key / sign| S
    B -->|load active key / sign| S
    C -->|load active key / sign| S
    A --> JWKS[JWKS public endpoint]
    B --> JWKS
    C --> JWKS
    JWKS --> R1[Resource Server 1]
    JWKS --> R2[Resource Server 2]
    A -->|JWT signed by active key| API[Protected API]
~~~

The set of public keys published by every instance must be consistent. When using a KMS/HSM, the private key may never leave the signing device; the application calls signing APIs via a key handle. When using a keystore/secret manager, the application may load the private key into memory under granted permissions, but must never write plaintext arbitrarily to container images or temporary filesystems.

**Do not use a separate key per pod** if all tokens under the same issuer must be verified by Resource Servers through a shared JWKS, unless the architecture explicitly designs key distribution, JWKS aggregation, and rotation for each signing identity.

## 4. Choosing Durable Key Storage

No single storage option fits every organization. Choose based on security posture, compliance, operability, backup capabilities, and distributed signing needs.

| Approach | Where is the private key kept? | Pros | Risks/conditions |
|---|---|---|---|
| KMS/HSM | Key management device/service; app calls sign via API. | Key may never leave security boundary; clear auditing and IAM. | Requires acceptable latency, quota, HA, KMS permissions, and compatible signer/JWK integration. |
| Secret manager | Encrypted secret/keystore distributed to instances. | Easy integration with containers/orchestrators and rotation. | Guard read permissions; prevent leaks via env dumps/logs or filesystems. |
| PKCS#12/JKS on persistent secret volume | Keystore holding password-encrypted private key. | Integrates natively with Java KeyStore/JCA; easy to understand. | Password and volume must be protected; never bake into container image. |
| Encrypted database/object storage | Private key/JWK encrypted in access-controlled storage. | Centralizes metadata, key status, versions, and audit trail. | Requires KMS envelope encryption, transactions/locking, backup and recovery. |
| Local file on persistent disk | Private key/keystore on durable volume. | Simple for small deployments. | Hard to share across nodes; backup/permissions/rotation are manual. |
| Generate at startup | Each process generates a new pair. | Zero provisioning needed. | **Unsuitable** for issuers whose tokens must survive restarts or multi-instance setups. |

### 4.1. Recommended Model

A production setup typically includes:

1. **Key generation/provisioning** performed via a dedicated governance process, not randomly on every app startup.
2. **Private key** stored in a KMS/HSM or encrypted secret store; signing permission granted strictly to Authorization Server workloads.
3. **Key metadata** persisted stably: key ID, algorithm, use, active/retiring/revoked status, creation/activation/retirement timestamps, and version.
4. **Public JWK** published via JWKS and optionally stored alongside metadata.
5. **Active key selection** backed by a consistent configuration/record so every instance signs with the same key during a given phase.
6. **Rotation workflow** creating the new key, publishing the public key, switching the active signer, retaining the old key to verify old tokens, and only then removing it.
7. **Backup/recovery** tested regularly; private key backups must be protected on par with the original key.

Never write private keys to Git, Docker images, Kubernetes ConfigMaps, logs, public crash dumps, or unprotected temporary files. Secret managers and KMS must enforce least-privilege IAM, auditing, and anomaly alerting.

### 4.2. Encryption at Rest and Access Control

If private keys are stored in a database or object storage, use **envelope encryption**: key material encrypted with a data key, which is protected by KMS. Applications receive decrypt/sign permissions only within the necessary workload identity. Avoid inventing custom encryption schemes with a hardcoded password.

Public JWK read access can be broad; private key signing access must be narrow. If the application only needs to sign without reading/exporting the private key, prefer KMS/HSM signing APIs when compatible with your JWT encoder.

## 5. Creating a Stable JWK Once and Storing It in a Keystore

For development environments or small deployments, you can generate an RSA key pair **once** via a provisioning step, store it in a protected PKCS#12/JKS keystore, and mount the keystore as a secret volume. Every instance loads the same keystore and key ID.

### 5.1. Creating a Keystore with keytool

Example generating a test keystore:

~~~bash
keytool -genkeypair \
  -alias authorization-signing-2026 \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -dname "CN=Authorization Server Signing Key" \
  -storetype PKCS12 \
  -keystore auth-signing.p12
~~~

The command prompts for a password. This is a **one-time provisioning** action in a protected environment, not something run in a Docker entrypoint on every startup. For production, key size/algorithm, validity, password policy, and KMS/HSM usage must follow organizational standards and current cryptographic requirements.

The private key alias is `authorization-signing-2026`. Never commit `auth-signing.p12` or its password into source control or public artifacts.

### 5.2. Loading the Key Pair from PKCS#12 into a JWK

Illustrative Java example reading a keystore mounted from a secret volume, extracting private/public keys, and building an RSA JWK:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;

RSAKey loadSigningJwk(
        Path keystorePath,
        char[] storePassword,
        char[] keyPassword) throws Exception {

    KeyStore keyStore = KeyStore.getInstance("PKCS12");
    try (InputStream input = Files.newInputStream(keystorePath)) {
        keyStore.load(input, storePassword);
    }

    String alias = "authorization-signing-2026";
    RSAPublicKey publicKey =
            (RSAPublicKey) keyStore.getCertificate(alias).getPublicKey();
    RSAPrivateKey privateKey =
            (RSAPrivateKey) keyStore.getKey(alias, keyPassword);

    return new RSAKey.Builder(publicKey)
            .privateKey(privateKey)
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .keyID("authorization-signing-2026")
            .build();
}
~~~

This snippet illustrates key loading; real applications must handle specific exceptions, clear password char arrays when feasible, enforce file permissions, verify alias/certificate existence, confirm key pair matching, and avoid logging objects containing private keys. Never expose this helper via a public endpoint.

When sharing the same keystore across multiple instances, every instance must receive **the exact same version** of the secret and password via the secret manager, with least-privilege permissions. Updating the keystore requires a synchronized version/rollout mechanism—never overwrite a file actively used by running processes without a reload plan.

### 5.3. Creating JWKSource and JwtEncoder

Once a stable JWK is loaded, you can build the JWK source:

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

@Configuration(proxyBeanMethods = false)
class SigningKeyConfiguration {

    @Bean
    JWKSource<SecurityContext> jwkSource(RSAKey signingJwk) {
        return new ImmutableJWKSet<>(new JWKSet(signingJwk));
    }

    @Bean
    JwtEncoder jwtEncoder(JWKSource<SecurityContext> jwkSource) {
        return new NimbusJwtEncoder(jwkSource);
    }
}
~~~

This builds **a JWKSource from a loaded JWK Set**. A bean providing `RSAKey signingJwk` from a keystore/secret store as shown above is required. With `ImmutableJWKSet`, the JWK Set is a snapshot taken at application startup; replacing files/secrets later **does not automatically refresh** this bean. To rotate without restarts or support multiple keys dynamically, use a `JWKSource` capable of loading/refreshing key sets by version, or perform rotation via controlled rolling restarts.

Do not use the same `RSAKey` object containing private parameters to respond on a custom JWKS endpoint. The JWKS endpoint must return only public JWKs. Spring Authorization Server can share `JWKSource` to serve metadata/JWKS; verify that your version's public projection and endpoint configuration never serialize private parameters.

### 5.4. Why This Example Is Not an HSM Solution

`NimbusJwtEncoder` expects to retrieve an appropriate JWK to sign according to the encoder's mechanism. When private keys cannot be exported from an HSM/KMS, integration may require a signer/encoder adapter using a remote signing API, a JCA provider, or a vendor-compatible mechanism. Do not assume merely swapping a keystore file path for a KMS URI makes `NimbusJwtEncoder` sign remotely.

With an HSM/KMS, keep public JWK metadata (modulus/exponent or EC public point), key ID, and algorithm in `JWKSource`; delegate signing operations to the KMS/HSM. The adapter must guarantee returned signatures conform to the proper JWS format/algorithm, handle timeouts/retries/idempotency, and never fall back to an unapproved local key.

## 6. Sharing Keys Across Instances

### 6.1. Every Instance Needs the Same Key Set and Active Key

In a cluster, a straightforward approach is having every instance boot from the same keystore version mounted via a secret manager. This works well when rotations roll out in batches with controlled restarts.

With a dynamic key store or KMS/HSM, instances read from a shared source of key metadata and can sign with the same key ID. Ensure:

- The active key ID is published from a strongly consistent source.
- Every instance learns about the new key before beginning to sign with it.
- The new key's public key is already present on JWKS before new tokens are issued.
- Every instance retains the old public key while old tokens require verification.
- Instances refuse to sign if valid key state cannot be retrieved.
- No node generates a fallback key when the key store/KMS is temporarily unavailable.

### 6.2. Avoiding Race Conditions During Rotation

If active key state is stored in a database, never let each instance pick the active key via "latest key by timestamp" without clear transactions/versioning. Store an active-key configuration record with a monotonically increasing version updated via audited administrative actions.

Illustrative metadata model (example only, not a schema provided out-of-the-box by Spring Authorization Server):

| key_id | algorithm | status | created_at | sign_from | sign_until | verify_until | version |
|---|---|---|---|---|---|---|---|
| auth-signing-2026-01 | RS256 | RETIRING | 2026-01-01 | 2026-01-01 | 2026-11-01 | 2026-11-02 | 7 |
| auth-signing-2026-11 | RS256 | ACTIVE | 2026-11-01 | 2026-11-01 | — | — | 8 |

Statuses like ACTIVE/RETIRING/REVOKED are **application conventions**, not built-in JWK enums. Define state transitions and approval permissions explicitly. Across multiple regions, account for propagation delays and activation timestamps; never switch active before all Resource Servers can fetch the new public key per SLA.

### 6.3. JWKS Endpoint Must Return a Consistent Public Key Set

Example JWKS carrying two public keys during the overlap window:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "auth-signing-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "OLD_PUBLIC_MODULUS",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "auth-signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "NEW_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

In this example, JWKS returns both old and new public keys so Resource Servers can verify in-flight tokens. Never return private fields. If instances behind a load balancer serve different JWKS payloads during the same phase, Resource Servers may fetch inconsistent sets and fail randomly per node.

Resource Servers may cache the JWKS. After adding the new key, account for Resource Server cache/refresh durations. Never issue tokens with the new key before its public key is published and reachable; never delete the old key immediately upon stopping signing with it.

## 7. Rotation: Add the New Key First, Remove the Old Key Later

A safe rotation workflow has three main phases:

~~~mermaid
flowchart LR
    A[Phase 1: Publish new public key] --> B[Phase 2: Switch active signer]
    B --> C[Phase 3: Retire old public key after overlap]
    A --> A1[Both public keys visible]
    B --> B1[New JWTs use new kid]
    C --> C1[Old tokens expired/cache window passed]
~~~

### 7.1. Phase 1 — Provision and Publish the New Public Key

1. Create a new key pair in KMS/HSM/keystore via governance procedures.
2. Assign a new key ID, such as `auth-signing-2026-11`.
3. Store metadata, public JWK, and private signing handle in the key store.
4. Update JWKS to publish the **new public key**, keeping the old key.
5. Wait for propagation and JWKS cache refreshes per SLA; verify from Resource Servers/regions.

During this phase, the Authorization Server continues signing with the old key. The new public key is not used to sign tokens until you are confident consumers can verify it.

### 7.2. Phase 2 — Switch the Active Signer

1. Update the active key ID in a versioned/transactional operation.
2. Instances load the new active key or receive a reliable reload event.
3. Verify new JWTs carry the new `kid` header and valid signatures.
4. Confirm every instance signs with the new key; unsynchronized nodes must not continue signing with stale state if policy requires uniformity.
5. Keep the old public key in JWKS so older tokens continue to verify.

Do not rotate by swapping the private key on a single pod and hoping other nodes update automatically. Use secret versions, synchronized rollouts, or stateful key distribution mechanisms.

### 7.3. Phase 3 — Remove the Old Public Key

Remove the old public key only when:

- The last token signed with the old key has expired per maximum TTL.
- Resource Server clock skew/leeway has been accounted for.
- Relevant JWKS caches and introspection caches have elapsed past required durations.
- No valid tokens/cookies/queues/jobs still depend on the old key.
- No rollback could require the old key to verify newly issued tokens from the prior window.

For example, if the maximum access token TTL is 15 minutes and 2 minutes of clock skew are allowed, do not delete the old public key exactly 15 minutes after the last signature. Add propagation/cache durations plus an agreed operational safety margin.

### 7.4. Normal Rotation Differs from Compromise Handling

If a private key is **exposed**, do not wait for old tokens to expire under normal rotation. Execute incident response: halt signing with the compromised key, remove the key from trusted sets per emergency severity, switch to a clean key, identify potentially forged tokens, evaluate session/token revocation, instruct Resource Servers to refresh JWKS/denylists, and preserve audit evidence.

Removing a compromised public key from JWKS may cause previously issued legitimate tokens to fail, yet this can be necessary when risk demands it. Emergency procedures must be rehearsed, with pre-assigned owners and approvals.

## 8. Separating Token Signing Configuration and JWKS Publication

The Authorization Server needs two related but distinct capabilities:

- **Signing path:** obtain the private key or key handle to sign tokens.
- **Verification/publication path:** expose the corresponding public keys via JWKS.

A JWK Set may hold both private and public parameters in signer memory, yet the JWKS response must output only public keys. When using a KMS/HSM, the signer can keep the private key outside the process while `JWKSource` holds only public key metadata.

### 8.1. Checking the JWKS Endpoint

After configuring the issuer and `JWKSource`, fetch the corresponding OIDC/OAuth2 Authorization Server metadata to find the JWKS URL. The URL may vary by version/configuration. Inspect the live endpoint:

- Returns a JSON JWK Set with top-level `keys`.
- Contains a public key for every `kid` currently used to sign tokens.
- Contains zero RSA/EC private parameters.
- Is not cached too long by proxies when rotation requires refreshes.
- Uses consistent HTTPS, hostname, and issuer.
- All instances behind the load balancer return matching public key sets.

Do not hardcode an internal node's JWKS URI inside Resource Servers. Use issuer metadata/discovery or configure the public JWKS URI consistent with your system's trust model.

### 8.2. Issuing a Token and Inspecting kid

Obtain a JWT access token in a test environment, decode the **header** to verify `kid` and `alg`, and then verify the signature using the public JWKS. Decoding the payload is not token verification. Resource Servers must check `iss`, `aud`, `exp`, and scopes/claims.

A token signed with a key ID absent from JWKS may be rejected until the key is published. If a token header carries an existing `kid` while key material was swapped, signature verification must fail; never reuse a `kid` for a different key.

## 9. Testing Restarts, Scale-Out, and Recovery

Testing a single token issuance on a single instance is insufficient. The core challenge of this topic is **keys surviving process lifecycle and topology changes**.

### 9.1. Test Matrix

| Scenario | Expected result |
|---|---|
| Issue token, restart same instance | Old token still verifies; new JWTs use the same active key if not rotated. |
| Issue token on A, verify via B | Signature valid; public key present in shared JWKS. |
| Scale from 1 to 3 instances | Every node uses the same key set/active key ID. |
| Request JWKS repeatedly via load balancer | No node returns a missing/divergent public key set outside planned rotation. |
| Rolling deploy | Tokens signed by both old and new nodes verify during overlap. |
| Rotation phase 1 | JWKS shows both old and new keys; signer still uses old key. |
| Rotation phase 2 | New JWTs carry new kid; old JWTs still verify. |
| Rotation phase 3 | Old public key removed only after token/cache windows elapse. |
| KMS/HSM temporarily unavailable | Server does not fall back to unapproved keys; logs error and emits metric. |
| Secret manager unreachable at startup | Instance fails readiness/startup per policy; does not generate a new key. |
| Restore DB/keystore from backup | Key ID, key material, and active version match; unexpired tokens still verify. |
| Private key revoked/compromised | Emergency runbook halts signing, updates JWKS/trust, and handles affected tokens. |
| Two keys share kid with different material | Test detects and blocks; kid is never reused. |

### 9.2. Java Test Example

The test below illustrates the concept: a token signed before a restart must verify using the public JWK reloaded from the same key store after restart. It is not a complete integration test:

~~~java
@Test
void tokenSignedBeforeRestartRemainsVerifiable() throws Exception {
    RSAKey beforeRestart = keyStoreLoader.load("auth-signing-2026-01");
    JwtEncoder encoderBefore = new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(beforeRestart)));

    String token = issueTestJwt(encoderBefore, "inventory-api");

    // Simulate new process: reload the same key version from persistent store.
    RSAKey afterRestart = keyStoreLoader.load("auth-signing-2026-01");
    JwtDecoder decoderAfter = decoderFor(afterRestart.toPublicJWK());

    assertThat(decoderAfter.decode(token).getSubject())
            .isEqualTo("inventory-worker");
}
~~~

`keyStoreLoader`, `issueTestJwt`, and `decoderFor` are hypothetical helpers to implement in your test fixture. In real integration tests, restart the application context/instance or create two independent app contexts backed by the same key store; do not merely share an in-memory object, as that fails to test persistence.

### 9.3. Real Multi-Instance Testing

- Run at least two Authorization Server instances pointing to the same key store version.
- Call the Token Endpoint via instance A, then verify the token at a Resource Server configured to fetch JWKS via instance B.
- Repeat with the load balancer routing JWKS requests across different nodes.
- Perform a rotation under active token issuance traffic; confirm no tokens are issued with an unpublished kid.
- Stop one instance and verify surviving nodes continue issuing tokens with the right key.
- Simulate KMS/secret manager loss and verify readiness checks and alerts.
- Restore a backup in staging and verify old tokens, key IDs, JWKS, and rotation state.

## 10. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Old JWTs fail after restart | Startup generates a new key or key store is non-persistent. | Load the same key material and kid from a persistent source. |
| Token signed by A fails verification via B | Each instance has its own key or node JWKS payloads diverge. | Use a shared key source/metadata and verify public JWKS via load balancer. |
| JWKS has key but signature fails | Public key does not match signing private key, kid was reused, or wrong key. | Check key fingerprints/pairs, kid, and signing configuration. |
| JWKS missing kid of new token | Signer switched before public key was published/refreshed. | Publish key first, wait for propagation, then switch active. |
| Old tokens fail immediately on rotate | Old public key removed too early or Resource Server cache mismatch. | Maintain overlap for TTL + skew + cache window. |
| New instance fails to start | Secret/KMS permissions, wrong key alias/password, or network issue. | Check IAM, secret version, keystore alias, and redacted readiness logs. |
| One node signs with old key after cutover | Active key state out of sync or cache failed to reload. | Use versioning/coordination, drain stale node, or fail closed. |
| JWKS exposes private parameters | Serializing private JWK object instead of public projection. | Publish public JWKs only; test responses for absence of private fields. |
| KMS signing slow/timeouts | Quota, network, or HSM capacity. | Configure timeouts, bulkheads, metrics, and capacity plans; never fall back to weak keys. |
| Backup restored but tokens still fail | Backup missing private key, key version, or active metadata. | Back up material and metadata together; rehearse recovery. |
| Resource Server does not see new key | Long JWKS cache or refresh strategy not triggering. | Tune caching/refreshing and publish key before use. |
| Same kid but key changed | Kid is not unique/stable. | Never reuse kid; assign a new ID for new key material. |

## 11. Operations Runbook and Access Control

### 11.1. Least-Privilege Access

- Authorization Server runtime receives only **sign** permission or read access to the exact private key needed; do not grant key admin/delete rights unnecessarily.
- Resource Servers need only public JWKS or introspection permissions; they never need private signing keys.
- CI/CD deploys only secret references/versions; never reads/exports private keys.
- Rotation operators have approved, audited permissions rather than shared daily application accounts.
- Backup operators and incident responders have dedicated roles with MFA/approvals and audit logging.

### 11.2. Recommended Metrics and Alerts

- Active key ID per instance (public metadata only).
- JWT signing success/failure counts, latency, and KMS/HSM errors.
- Timestamp of public JWK publication and propagation lag.
- Number of instances still using the old key version after cutover.
- JWKS response consistency/hash by version (never hash private material into logs).
- Unusual secret/key access, export attempts, and permission denials.
- Key expiration / certificate expiration timestamps (when certificates are used).

Never put private keys, keystore passwords, KMS credentials, or raw JWTs into metric labels. Never send key material over chat or logs during troubleshooting.

### 11.3. Backup and Disaster Recovery

Backups must cover **recoverable keys**, public metadata, key IDs, active/retiring states, versions, and procedures to regain KMS access. With non-exportable HSMs, recovery relies on the device/service's official backup/replication mechanism; never assume a database snapshot alone contains the private key.

Rehearse at least:
1. Restoring the key store in an isolated environment.
2. Booting a new Authorization Server with the backed-up key version.
3. Verifying unexpired JWTs signed prior to the incident.
4. Issuing new tokens and verifying them with Resource Servers.
5. Checking JWKS, issuer, kid, and active key state.
6. Confirming audit logs and permissions post-restore.

## 12. Hands-On Exercise

**Context:** The Authorization Server initially ran a single instance using an RSA key generated at startup. After deploying three replicas behind a Kubernetes Service, APIs intermittently return 401 for freshly issued tokens. Upon restarts, most active tokens also fail.

Design and implement a remediation plan:

1. Explain why each pod having an independent key pair causes these failures.
2. Choose KMS/HSM, secret manager, or PKCS#12 on a persistent secret volume; explain trade-offs and access permissions.
3. Provision a stable RSA key pair with a dedicated key ID; store the private key securely and prepare the public JWK for publication.
4. Configure `JWKSource<SecurityContext>` and `JwtEncoder` using the same key version across all instances.
5. Verify JWKS contains only public parameters and each key has a stable kid.
6. Run two instances, issue a token from A, and verify via a Resource Server fetching JWKS from B.
7. Restart/scale-out/rolling-deploy; verify unexpired old tokens continue working.
8. Execute a three-phase rotation: publish the new key, switch the signer, and remove the old key after overlap.
9. Simulate KMS/secret manager unavailability; verify no fallback key is auto-generated.
10. Write a key-compromise runbook and rehearse backup/recovery in staging.

**Completion criteria:** issued tokens verify across restarts/replicas; all nodes share the same key set and active key; public JWKS leaks no private material; rotation does not break unexpired tokens; recovery restores both keys and metadata.

## 13. Pre-Production Checklist

- [ ] Private signing keys are provisioned stably, not regenerated on every startup.
- [ ] Durable, encrypted storage is in place; signing permissions follow least privilege.
- [ ] Public keys are published via JWKS; zero private parameters appear in responses.
- [ ] kid is stable for a given key and never reused for different key material.
- [ ] JWKSource/JwtEncoder are configured from a trusted key source.
- [ ] All instances sign with a consistent active key and publish matching public keys.
- [ ] New/scaled-out/restarted instances load the exact same key version.
- [ ] Immutable JWK Set snapshots are reloaded/restarted cleanly during rotation.
- [ ] JWKS caching/propagation is accounted for before signing with a new key.
- [ ] Old public keys remain published throughout an overlap covering TTL, clock skew, and cache windows.
- [ ] Key compromise has dedicated emergency rotation/revocation procedures.
- [ ] KMS/HSM/secret manager has HA, quota monitoring, timeouts, auditing, and alerts.
- [ ] Backup/recovery includes key material or HSM backup mechanisms plus metadata.
- [ ] Tokens are tested across restarts, instances, rolling deployments, rotations, and failovers.
- [ ] Resource Servers verify signatures, issuer, audience, expiry, and policies.
- [ ] Zero private keys, passwords, raw JWTs, or secrets exist in Git/logs/traces/images.

## Summary

JWT signing keys must **persist stably across process lifecycles** and be shared from a trusted source across all instances under the same issuer. Spring Authorization Server uses **JWKSource** to supply keys to **NimbusJwtEncoder** and serve public JWKs per configuration. The framework does not automatically turn an in-memory startup key into durable key storage; applications must design provisioning, storage, access control, active key selection, rotation, and recovery.

During rotation, **publish the new public key first**, switch the signer once consumers can verify it, and remove the old public key only when old tokens and caches no longer need it. KMS/HSM, secret managers, or encrypted keystores can all work well if signing permissions, synchronization, HA, auditing, and disaster recovery are designed thoroughly. Success is proven by testing tokens across restarts, scale-out, rolling deployments, and failover—not merely by having one instance mint a JWT.

## References

1. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): JWKSource, NimbusJwtEncoder, JWT token generation, and token customization.
2. [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): Authorization Server configuration, issuer, and JWKS endpoint.
3. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification and fetching public keys via JWKS.
4. [Nimbus JOSE + JWT — JWK Set](https://connect2id.com/products/nimbus-jose-jwt/examples/jwk-set): representing JWK/JWK Set and public/private key material.
5. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set, key use, key operations, and public/private key parameters.
6. [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS protected header, algorithm, and kid.
7. [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): signing algorithms and key parameters.
8. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata endpoints and jwks_uri.
9. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata and jwks_uri for OIDC.
10. [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): cryptographic key lifecycle, protection, backup, and rotation.
11. [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): key storage and secrets management.
