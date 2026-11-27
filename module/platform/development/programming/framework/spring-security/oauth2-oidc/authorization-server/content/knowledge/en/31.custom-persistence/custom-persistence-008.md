# Encrypting Sensitive Data and Testing Cross-Instance Compatibility

> **Chapter: Custom Persistence.** This lesson belongs to the **SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER** module, which covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. The focus is protecting OAuth/OIDC data in the persistence layer, managing encryption keys, and preserving readability across multiple instances during rolling deployments.

## 1. Why Does Custom Persistence Need Data Encryption?

An Authorization Server stores high-value data: client registrations, encoded client secrets, authorization codes, access tokens, refresh tokens, ID Tokens, principal attributes, consents, and grant metadata. Several values are bearer credentials; anyone obtaining an active token can exercise it. Other fields contain personally identifiable information, scopes, tenants, or user authentication data.

Encrypting data in the database reduces the blast radius when backups, snapshots, disks, or dumps are accessed without authorization. However, distinguish the layers of protection:

- **Encryption in transit:** TLS protects data moving between the application, database, cache, KMS, and other services.
- **Storage encryption:** database TDE, disk encryption, and backup encryption protect data files at the infrastructure layer.
- **Application-layer field encryption:** the application encrypts fields before writing; the database sees only ciphertext.
- **Secret/configuration management:** keys, passwords, and API credentials live in a secret manager/KMS, never in source code or container images.

These layers complement one another. TDE does not stop someone with database query privileges from reading data via SQL; field-level encryption mitigates that risk, though an application granted decryption permission can still read plaintext.

### 1.1. Define the Threat Model First

| Scenario | Helpful Controls | Limitations |
|---|---|---|
| Database dump/backup exposed | TDE, backup encryption, field encryption | Benefits drop sharply if keys are stored alongside the dump |
| Privileged SQL user reads tables | Field-level encryption and least-privilege DB roles | The application still must decrypt to process the protocol |
| Network traffic sniffed | TLS between components | TLS does not protect records once persisted |
| A pod is compromised | Least privilege, KMS policies, minimize plaintext and logs | A pod with decryption rights can still be abused |
| An instance uses a different key/serializer | Key versioning, schema versioning, compatibility tests | Encryption cannot fix incompatible contracts |
| Logs/APM record tokens | Redaction, logging policies, and secret scanning | DB encryption does not protect credentials already logged |

Do not encrypt every column reflexively. Classify data, identify who needs to read it, which queries need to search it, and retention periods. Data that does not need to be stored should not be stored at all.

## 2. Classifying Data in Spring Authorization Server

Spring Authorization Server separates models by purpose. Persistence design must identify sensitive data in each model.

| Model/Field | Data | Typical Appropriate Protection |
|---|---|---|
| `RegisteredClient.clientId` | OAuth client identifier | Unique index; classify per organizational policy |
| `RegisteredClient.clientSecret` | Credential for client authentication | One-way `PasswordEncoder`; never store plaintext |
| `redirectUris`, `scopes` | Protocol and permission configuration | Write access control, auditing; encrypt if containing sensitive metadata |
| `clientSettings`, `tokenSettings` | Client/token configuration | Versioned serialization; encrypt if needed |
| `OAuth2Authorization` token values | Authorization code, access/refresh tokens, ID Token per grant | Field/document encryption and separate lookup index |
| `OAuth2Authorization.attributes` | Principal, authorization request, claims, metadata | Minimize, filter fields, encrypt PII/credential-bearing attributes |
| `OAuth2AuthorizationConsent.authorities` | Scopes/permissions approved by the user | Access control, auditing; encryption per data classification |
| Signing private key / JWK private parameters | Token signing keys | HSM/KMS/secure keystore; never place in authorization database |
| Audit events | Actor, client, action, timestamp | Store only required metadata; never log tokens/secrets |

`OAuth2Authorization` can hold access tokens, refresh tokens, authorization codes, ID Tokens, and flow attributes. Examine both token metadata/claims and objects serialized inside attributes, not just the token value columns visible in the schema.

### 2.1. Hash, Encrypt, or Omit?

| Data | Handling | Rationale |
|---|---|---|
| Client secret | `PasswordEncoder` (one-way) | Server only needs to verify secrets sent by callers |
| User password | Dedicated password hashing | No valid use case to recover plaintext |
| Access/refresh tokens stored in authorization | Encrypt at rest; separate lookup index if needed | Protects credentials while still supporting lookups |
| Authorization code | Encrypt at rest, short retention | Short-lived yet high-value credential |
| PII/claims in attributes | Minimize and encrypt per field/document | Limits personal data exposure |
| Client ID | Plain index if policy allows | Protocol lookups regularly search by client ID |
| Token lookup key | HMAC-SHA-256 with separate key | Equality lookup without storing plaintext tokens |
| Signing private key | KMS/HSM or dedicated keystore | Separate trust boundary from authorization records |
| Expired/unneeded data | Retention/cleanup | Reduces volume of sensitive data at rest |

Do not confuse `PasswordEncoder` with encryption. Hashes cannot be decrypted; encryption can be decrypted with the key. If the system must retain an upstream service credential to re-send it, that is a different data class: use a secret manager or envelope encryption with a dedicated key purpose.

## 3. Envelope Encryption Architecture

A common design is **envelope encryption**: the application encrypts payloads with a Data Encryption Key (DEK); a Key Encryption Key (KEK) inside KMS/HSM protects the DEK.

~~~mermaid
flowchart TD
    A["Authorization data / sensitive fields"] --> B["Serialize canonical payload"]
    B --> C["DEK: AES-GCM encrypt + AAD"]
    C --> D["Ciphertext + nonce + tag"]
    E["KMS / HSM KEK"] --> F["Wrap DEK"]
    F --> G["Wrapped DEK + key version"]
    D --> H["Encrypted persistence record"]
    G --> H
    H --> I["Database / Redis / backup"]
    I --> J["Authorized AS instance"]
    J --> K["KMS unwrap DEK"]
    K --> L["AES-GCM authenticate + decrypt"]
    L --> M["Deserialize versioned payload"]
~~~

- **DEK:** data key used to encrypt plaintext; may be generated per record, tenant, or data group depending on performance and blast radius.
- **KEK:** key managed in KMS/HSM used to wrap/unwrap DEKs.
- **Ciphertext:** encrypted data and authentication tag.
- **Nonce/IV:** unique value per key for every AES-GCM encryption.
- **AAD (Additional Authenticated Data):** unencrypted metadata authenticated alongside the ciphertext, such as tenant ID, record ID, field purpose, and format version.
- **Key ID/version:** identifies which key/version to use for decryption; contains no key material.

The database can store the wrapped DEK alongside the ciphertext. The actual KEK must reside in KMS/HSM or a separate trust boundary. An instance can only decrypt when granted the appropriate KMS permissions.

### 3.1. Why Is Authenticated Encryption Required?

Encrypted data requires both confidentiality and integrity. Encrypting without authentication allows attackers to tamper with ciphertext, causing subtle errors or altered plaintext upon decryption.

Prefer authenticated encryption such as AES-GCM. GCM produces an authentication tag; decryption must fail if the ciphertext, tag, or AAD is modified. Never invent your own cipher, mode, padding, or encryption protocol.

### 3.2. Nonces Must Be Unique for a Given Key

With AES-GCM, **never reuse the same nonce/IV with the same key across different plaintexts**. This is a core security invariant. When multiple pods share a DEK, nonce uniqueness is a cluster-wide requirement, not per JVM.

A 96-bit nonce generated by `SecureRandom` is a common choice when usage volume and collision risk are properly managed. In high-throughput systems, design controlled nonce allocation/usage limits or rely on a responsible KMS/library. Track encryption counts per key and rotate before reaching the threshold defined by your threat model/applicable standards. Never derive nonces from `currentTimeMillis` or in-RAM per-pod counters.

## 4. Designing Versioned Encrypted Records

Do not store ciphertext as an unannotated string without metadata. Records need enough information for any instance to determine how to decrypt them:

| Field | Example | Purpose |
|---|---|---|
| `format_version` | 1 | Envelope/encoding version |
| `schema_version` | 3 | Payload schema version |
| `algorithm` | AES-256-GCM | Algorithm and mode |
| `key_id` | as-data-key-v4 | ID/version of the KEK or key profile |
| `wrapped_dek` | Base64 bytes | DEK wrapped by the KEK |
| `nonce` | Base64 12 bytes | GCM IV |
| `ciphertext` | Base64 bytes | Ciphertext plus tag per format |
| `aad_version` | 1 | Rules for constructing AAD |
| `created_at` | UTC timestamp | Auditing/diagnostics |

Never store plaintext keys in records. `algorithm`, `format_version`, and `key_id` must be checked against an allowlist; never let database values select an arbitrary crypto provider or class.

### 4.1. AAD Binds Ciphertext to Its Context

AAD can include the verified tenant/issuer, registration ID or authorization ID, field name/purpose, and envelope format version. If an attacker copies ciphertext from tenant A into a record for tenant B, the differing AAD causes GCM authentication to fail.

AAD must be built with identical canonical encoding across all instances; avoid ambiguous string concatenation that could cause representation collisions. Tenant IDs must come from a verified issuer/tenant context, never from request bodies. When changing tenants or AAD schemes, perform explicit re-encryption or migration. Never put secret data into AAD because AAD is not encrypted.

## 5. AES-GCM Example with Java Cryptography Architecture

The snippet below illustrates AES-GCM primitives using a 256-bit DEK provided by the key-management layer. Generating, wrapping, distributing, caching, and rotating DEKs/KEKs belong to the application's dedicated KMS/key service.

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class AesGcmPayloadCipher {

    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecureRandom secureRandom = new SecureRandom();

    EncryptedPayload encrypt(
            byte[] plaintext,
            SecretKey dek,
            byte[] associatedData,
            String keyId) throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_BYTES];
        secureRandom.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(associatedData);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new EncryptedPayload(1, keyId, nonce, ciphertextAndTag);
    }

    byte[] decrypt(
            EncryptedPayload payload,
            SecretKey dek,
            byte[] associatedData) throws GeneralSecurityException {

        if (payload.formatVersion() != 1) {
            throw new IllegalArgumentException("Unsupported envelope version");
        }

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, payload.nonce()));
        cipher.updateAAD(associatedData);

        // AEADBadTagException indicates an integrity/authentication failure.
        return cipher.doFinal(payload.ciphertextAndTag());
    }

    record EncryptedPayload(
            int formatVersion,
            String keyId,
            byte[] nonce,
            byte[] ciphertextAndTag) {
    }
}
~~~

This is a primitive example, not a complete persistence solution. The application must:

1. Obtain DEKs from KMS/key service; never hardcode keys in classes or configuration.
2. Wrap the DEK with the KEK and store `wrapped_dek` alongside `key_id`.
3. Persist `nonce`, ciphertext/tag, and version fields.
4. Build canonical AAD from tenant, record ID, purpose, and version.
5. On decryption, fetch the exact key by key ID, reconstruct exact AAD, and verify the tag.
6. If decryption fails, reject the record and alert; never return an empty object or ignore tag errors.

`Cipher` is a per-operation mutable object; never share one `Cipher` instance across threads. In production, use well-maintained, vetted crypto/key-management libraries, restrict decryption permissions by workload, and establish a key-compromise response procedure.

## 6. Building Deterministic AAD Across Instances

AAD is part of the storage contract. If pod A uses an uppercase tenant ID while pod B uses lowercase, or one pod concatenates fields in a different order, decryption fails even with the right key and ciphertext.

Example helper using length-prefixing to avoid ambiguity when concatenating fields:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

final class AadFactory {

    private AadFactory() {
    }

    static byte[] create(
            String tenantId,
            String recordId,
            String purpose,
            int formatVersion) {

        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            writeUtf8(out, tenantId);
            writeUtf8(out, recordId);
            writeUtf8(out, purpose);
            out.writeInt(formatVersion);
            out.flush();
            return bytes.toByteArray();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot build AAD", ex);
        }
    }

    private static void writeUtf8(DataOutputStream out, String value)
            throws IOException {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }
}
~~~

All instances must use the exact same canonicalization and encoding. Never silently alter canonicalization algorithms during a rolling deployment.

## 7. Looking Up Tokens Without Storing Plaintext Tokens

Custom `OAuth2AuthorizationService.findByToken(token, tokenType)` needs to look up by token value. Storing raw tokens in an index column risks exposing bearer credentials in a database dump.

One design uses a **keyed HMAC index** separate from encryption keys:

~~~text
lookup_digest = HMAC-SHA-256(
    token_lookup_key,
    token_type || 0x00 || raw_token
)
~~~

The persistence record stores `token_lookup_key_id`, `token_lookup_digest`, and the encrypted authorization payload. On `findByToken`, the adapter recomputes the HMAC using the corresponding key and queries by digest. The HMAC key must be independent of DEKs/KEKs and managed/rotated separately. Use canonical encoding for token type and token bytes; never log raw tokens.

An HMAC digest is strictly a lookup index—it cannot recover the token and does not replace ciphertext. When the full `OAuth2Authorization` must be returned, decrypt the payload after locating the record. For self-contained JWTs, if only revocation lookup by verified `jti` is needed, you can index by `jti`; the choice depends on protocol flows and query contracts.

### 7.1. Rotating the HMAC Lookup Key

When rotating an HMAC key, old digests cannot be recomputed from existing digests. Migration approaches:

- Maintain multiple index versions during the transition window; lookups check the current key version and still-readable older versions.
- Backfill new digests by decrypting records to obtain token values, computing new HMACs, and writing new index entries.
- Switch all writers to the new key once every reader understands both versions.
- Remove old indexes/keys only after verifying migration, backups, and retention policies.

Never rotate the HMAC key and immediately delete the old key while records in the database still carry only old digests.

## 8. Client Secrets and PasswordEncoder

`RegisteredClient.clientSecret` is a value encoded by a `PasswordEncoder`. It is verified during client authentication; the server never needs to decrypt the original secret.

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;

String encodedSecret = passwordEncoder.encode(rawClientSecret);

RegisteredClient registeredClient = RegisteredClient
        .withId("registration-orders-service")
        .clientId("orders-service")
        .clientSecret(encodedSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();
~~~

Never store raw client secrets, never use `NoOpPasswordEncoder` in production, and never store reversibly encrypted client secrets just to allow viewing them later. If a client loses its secret, the right procedure is to rotate and issue a new secret.

If the system must retain an upstream service credential for outbound calls, use a secret manager or envelope encryption with a dedicated key purpose, auditing, and access policy.

## 9. Spring Authorization Server Serialization Must Be Consistent

Encrypting bytes is not enough if instances deserialize the same payload into different objects. Spring Authorization Server uses types such as `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationConsent`, token metadata, Spring Security `Authentication`, and authorization request attributes.

The Spring Authorization Server JPA guide demonstrates registering Jackson modules:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.Module;
import java.util.List;
import org.springframework.security.jackson2.SecurityJackson2Modules;
import org.springframework.security.oauth2.server.authorization.jackson2.OAuth2AuthorizationServerJackson2Module;

ObjectMapper objectMapper = new ObjectMapper();

ClassLoader classLoader = getClass().getClassLoader();
List<Module> securityModules =
        SecurityJackson2Modules.getModules(classLoader);

objectMapper.registerModules(securityModules);
objectMapper.registerModule(
        new OAuth2AuthorizationServerJackson2Module());
~~~

This is illustrative module registration. The application must configure a mapper matching its actual model and use the same contract for reading and writing. Do not assume every custom POJO or `Authentication` deserializes automatically merely from registering modules.

### 9.1. Avoid Java Native Serialization and Unrestricted Default Typing

Avoid Java native serialization of arbitrary objects from databases/caches whenever possible. Never enable unrestricted Jackson default typing on untrusted persistence payloads: type metadata can widen the deserialization attack surface.

Instead:

- Use DTO/payload models with explicit schemas.
- Allow only required subtypes via an allowlist.
- Register the official Spring Security/SAS Jackson modules.
- Control custom `Authentication`/attribute types with dedicated serializers.
- Bound payload size, nesting depth, and input validation.
- Keep serialization schema versions separate from encryption envelope versions.

### 9.2. Schema Versioning and Migration

Records should carry a `schema_version`. When adding fields, prefer additive changes with clear, meaningful defaults. When renaming/removing fields or changing types, provide migrations or readers supporting older versions.

Never deserialize legacy data by silently turning errors into default objects; doing so can turn an authorization into a completely different configuration unnoticed. If a payload version is unsupported, fail closed, log a correlation ID, and route the record through a repair/migration process.

## 10. Cross-Instance Compatibility in a Cluster

In production, any pod can serve any request. One pod writes an authorization; another pod may read, introspect, refresh, or revoke that exact record.

| Component | Cross-Instance Requirement |
|---|---|
| Crypto envelope | Same format version, algorithm allowlist, and encoding |
| Key access | Permission to read required key versions in KMS/HSM |
| AAD | Same canonicalization, tenant/issuer resolution, and field purpose |
| Serializer | Compatible schemas and Jackson modules |
| Custom types | Same allowlist and serializer/deserializer |
| Database schema | All running app versions can read/write the schema during rollout |
| Token lookup index | Same HMAC key versions and canonical token types |
| Time handling | Consistent UTC, clock synchronization, and expiry policy |
| Cache | Invalidation/TTL never keeps stale data past policy |
| Issuer/tenant | Same public issuer mapping and tenant isolation |

### 10.1. Key Mismatch Errors Across Pods

~~~mermaid
sequenceDiagram
    participant A as AS pod A
    participant DB as Shared database
    participant B as AS pod B
    A->>A: Encrypt record with key version v4
    A->>DB: Store key_id=v4 + ciphertext
    B->>DB: Read record
    B->>B: Only has key v3
    B-->>B: Cannot decrypt
    Note over A,B: Request fails even though database and ciphertext are intact
~~~

This error typically arises during partial rollouts when a pod has not yet received KMS permissions or its key cache has not refreshed. Never handle it by ignoring decryption failures or trying random keys. Ensure key distribution/permissions are active across all readers before writers begin emitting records under the new key.

### 10.2. Reader-First Rolling Deployment

1. **Deploy compatible readers first:** the new version reads both old and new formats while still writing the old format.
2. **Verify across the entire cluster:** all running pods hold the new key permissions and code to read the new format.
3. **Switch writers:** enable the feature flag/configuration to write the new format/schema.
4. **Backfill:** migrate old records in batches with checkpoints and safe retries.
5. **Observe:** monitor decryption failures, deserialization errors, unknown key IDs, stale caches, and latency.
6. **Retire old readers:** only after no old-format records remain and backup/restore requirements are satisfied.

If old pods cannot read the new format, never enable the new writer while old pods still receive traffic. Use expand/contract migrations so database schemas remain compatible throughout the rollout.

## 11. Key Rotation and Reading Historical Data

Distinguish between:

- **KEK rotation:** replacing the key that wraps DEKs. DEKs can be re-wrapped under the new KEK without re-encrypting payloads if KMS supports envelope models.
- **DEK rotation:** replacing the data-encryption key. Moving older ciphertexts onto a new DEK requires decrypting and re-encrypting the data.

Records should store `key_id`/version so readers know which key to invoke. Every instance needs decryption permission for still-active key versions.

### 11.1. Routine Rotation Procedure

1. Create a new key version in KMS/HSM.
2. Grant decryption permission on the old key and encrypt/wrap permission on the new key to all required instances.
3. Deploy code/configuration capable of reading both old and new versions.
4. Switch writers to the new key.
5. Re-wrap DEKs or re-encrypt payloads per the chosen strategy.
6. Verify remaining old-version record counts and decryption outcomes.
7. Retain the old key long enough for backup restores and unmigrated records.
8. Retire/destroy the old key only once retention, backup, and disaster recovery policies allow.

### 11.2. Rotation on Key Compromise

If key compromise is suspected, determine the scope of data protected by that key. You may need to halt new encryption with the compromised key, provision a new key, re-encrypt data, and lock down backup access. Routine rotation and incident response are distinct procedures; compromise may require emergency action.

Never delete an old key before assessing whether backups still need decryption. Conversely, retaining a compromised key indefinitely is unsafe as well. Explicitly decide retention windows, access controls, and cryptographic erasure plans.

### 11.3. All Pods Must Share the Same Key Registry

Never let individual pods generate their own AES key on startup. If pod A generates key A and pod B generates key B, records written by A cannot be read by B; a restart may also permanently destroy the only key able to decrypt existing data.

Keys must be provisioned from KMS/HSM/a secure key service with explicit IDs/versions. Pods share the same key registry and policy; they do not even need raw key material if KMS performs remote encrypt/decrypt operations.

## 12. Configuring Secrets and Keys Outside Application Artifacts

Never commit KEKs, DEKs, HMAC keys, database passwords, or client secrets into source code, application YAML, container images, or Git history. Spring Boot supports externalized configuration and configuration trees to load secrets from mounted files; larger systems can integrate Vault/KMS through appropriate mechanisms.

Example configuration reading secrets from a mounted configuration tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Non-sensitive configuration such as key aliases/versions can bind via `@ConfigurationProperties`, while actual key access is governed by KMS IAM policies. Configuration trees are a config/secret delivery mechanism, not a KMS replacement; enforce file permissions and runtime isolation.

Core principles:

- Separate key material from databases and application images.
- Use a dedicated service identity per workload.
- Grant encrypt/decrypt permissions only for required keys/tenants.
- Audit KMS operations, especially decrypt/unwrap calls.
- Maintain key backup/restore procedures and test recovery.
- Never print keys, DEKs, plaintexts, or serialized token payloads in logs.
- Use controlled secret rotation rather than manually swapping keys pod by pod.

## 13. Testing Cross-Instance Compatibility and Security

A single-JVM encrypt/decrypt unit test is not sufficient. You must prove that **another instance**, with an independent key registry and serializer, can still read written data.

### 13.1. Crypto Tests

| Test | Action | Expected Result |
|---|---|---|
| Round trip | Encrypt on pod A, decrypt on pod B | Exact plaintext recovered |
| Ciphertext tamper | Flip one byte in ciphertext/tag | Decryption fails |
| Nonce tamper | Modify nonce | Decryption fails |
| Wrong key | Use a different DEK | Decryption fails |
| Wrong AAD | Change tenant/record/field purpose | Decryption fails |
| Unknown key ID | Pod lacks key version | Fails closed and alerts |
| Unsupported format | Unsupported record version | Never returns a default object |
| Nonce uniqueness | Generate nonces across multiple pods under one key | Zero reuse detected; usage tracked |
| Key rotation | Encrypt with v4, read with reader holding v3/v4, re-encrypt v4 | Old data readable; new records use v4 |
| KMS unavailable | KMS times out/denies access | Never falls back to plaintext writes |

### 13.2. Serialization Compatibility Tests

| Test | Writer | Reader | Expected Result |
|---|---|---|---|
| Baseline | App v1 | App v1 | Round trip |
| Backward read | App v1 | App v2 | v2 reads v1 payloads |
| Forward compatibility | App v2 (additive field) | App v1 | Allowed only if contract guarantees unknown fields are safe; otherwise hold v2 writer |
| Rolling deployment | Pods v1 and v2 running together | Shared DB | No record becomes unreadable to serving pods |
| Custom type | Serializer with custom `Authentication` | Another instance | Type is allowlisted and deserializes cleanly |
| Corrupt JSON | Payload missing field/invalid type | Any pod | Raises error; never creates empty authorization |
| Schema migration | Old schema → new schema | New reader | Values and semantics preserved |
| Module mismatch | Different Jackson/SAS module version | Reader | Incompatibility caught before production |

### 13.3. Integration Tests with a Real Database/Cache

Run at least two independent application contexts or processes connected to shared persistence and shared KMS test keys:

1. Pod A creates a `RegisteredClient` and saves an authorization with test access/refresh tokens.
2. Pod B reads via `RegisteredClientRepository`/`OAuth2AuthorizationService`.
3. Pod B verifies token lookup, metadata, principal attributes, and token active state.
4. Pod B refreshes or revokes per the test flow; pod A reads back the updated state.
5. Restart pod A with an empty cache; data remains readable.
6. Revoke KMS permissions on a test pod; requests must fail explicitly without plaintext fallback.
7. Run migration/rotation while both app versions serve requests.
8. Restore a backup into an isolated environment and verify required key versions still decrypt.

### 13.4. Multi-Tenant and Isolation Tests

- Ciphertext from tenant A cannot be decrypted with tenant B's AAD.
- Tenant/issuer lookups never return records from another tenant.
- KMS policies scope keys/tenants per workload.
- Database `key_id` values cannot select an arbitrary KMS resource outside an allowlist.
- Missing or unverified tenant context must fail closed.
- Cache keys must include tenant/issuer when data is partitioned by tenant.

## 14. Troubleshooting and Schema/Key Change Runbook

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Pod A writes fine, pod B cannot decrypt | Differing key versions/permissions | Sync KMS grants and key registry before switching writers |
| `AEADBadTagException` | Ciphertext, nonce, tag, or AAD modified; wrong key | Check record version, AAD canonicalization, and key ID |
| Decryption fails for only one tenant | Inconsistent tenant context/normalization | Normalize tenant ID and verify AAD |
| Authorization fails to deserialize after deploy | Differing Jackson modules/custom types/versions | Align serializer config, schema migration, and allowlist |
| Old records unreadable after rotation | Old key deleted prematurely | Restore key access or recover from valid backup key escrow |
| New pod writes records, old pod fails | Writer-first rollout | Deploy compatible readers first, then enable writer |
| Token lookup slow or misses | Mismatched HMAC key/version/index | Check canonicalization and index migration |
| Client secret exposed in DB | Stored raw secret instead of `PasswordEncoder` | Rotate secret and fix write path |
| DB dump still shows plaintext tokens | Payload encrypted yet index/other columns still raw | Encrypt lookup payloads and use HMAC index |
| KMS latency spikes | Calling KMS per field/record without caching policy | Use envelope DEKs with controlled pooling/retry/caching |
| Database restored yet cannot decrypt | Missing backup keys/versions | Test key backups and disaster recovery procedures |
| Ciphertext tampered yet app returns empty object | Overly broad catch-and-fallback | Fail closed, classify error, and alert |

### 14.1. Pre-Deployment

- Identify active record types, schema versions, envelope versions, and key versions.
- Verify every running instance can read the format about to be deployed.
- Verify KMS permissions for each service identity.
- Take a backup and verify restore/decryption in an isolated environment.
- Prepare dashboards for decryption failures, unknown key IDs, deserialization errors, lookup misses, and KMS latency.
- Write migrations with checkpoints, idempotency, and rollback/forward-recovery plans.

### 14.2. During Rollout

1. Deploy new readers without enabling the new writer format.
2. Wait for the full cluster to become healthy and verify cross-instance reads.
3. Enable the new writer via canary/feature flag.
4. Monitor error rates and read data back from other pods.
5. Backfill in rate-limited batches.
6. Retain old readers/keys until migrations and backup policies allow retirement.

### 14.3. Post-Rollout

- Count records by schema/key version.
- Confirm no legacy records still require old readers/keys.
- Verify backup/restore with retained key versions.
- Revoke unused key permissions and audit changes.
- Update runbooks, inventories, and test fixtures.
- Never delete an old key simply because live production traffic no longer reads it; backups may still require that key.

## 15. Production Checklist and Self-Assessment Questions

- [ ] Classified data across `RegisteredClient`, `OAuth2Authorization`, `Consent`, tokens, attributes, and signing keys.
- [ ] Client secrets/user passwords use one-way `PasswordEncoder`/password hashing, never plaintext.
- [ ] Tokens/PII requiring protection are encrypted with authenticated encryption.
- [ ] AES-GCM nonces are unique per key cluster-wide; usage/rotation policies exist.
- [ ] AAD is canonical and includes required tenant/record/purpose and version fields.
- [ ] Envelopes include format version, schema version, and key ID.
- [ ] DEKs and KEKs are separated; KEKs reside in KMS/HSM/a secure key service.
- [ ] HMAC lookup keys are independent of encryption keys; raw tokens never appear in indexes/logs.
- [ ] Legacy key versions remain readable throughout migration/backup retention windows.
- [ ] All pods hold compatible key permissions and serializer modules/allowlists.
- [ ] Jackson uses required Security/SAS modules; unrestricted default typing is disabled.
- [ ] Schema migrations follow reader-first and expand/contract practices.
- [ ] Cache invalidation, issuer/tenant context, and UTC/clock policies are consistent.
- [ ] KMS/database outages never fall back to plaintext or default objects.
- [ ] Tests cover crypto, tampering, wrong keys, wrong AAD, key rotation, old/new serializers, and multi-pod execution.
- [ ] Backup/restore procedures verify recovery of required keys.
- [ ] Logs, traces, and metrics contain no tokens, secrets, plaintext payloads, or key material.
- [ ] Runbooks exist for key compromise, failed migrations, and rollback/forward recovery.

**Self-Assessment Questions**

1. Why should `RegisteredClient.clientSecret` be stored with `PasswordEncoder` instead of reversible encryption?
2. What is the difference between TDE, field-level encryption, and TLS?
3. How do the roles of DEK and KEK differ in envelope encryption?
4. Why does AES-GCM require a unique nonce for a given key?
5. When multiple pods share a DEK, at what scope must nonce uniqueness be guaranteed?
6. How does AAD prevent tenant A's ciphertext from being copied into tenant B's record?
7. Why should raw access/refresh tokens not be stored in lookup index columns?
8. How does an HMAC lookup digest differ from ciphertext?
9. During KEK rotation, how does re-wrapping a DEK differ from rotating the DEK?
10. Why must every pod be able to read an old key version before a new pod writes with a new key version?
11. What problem do `SecurityJackson2Modules` and `OAuth2AuthorizationServerJackson2Module` solve?
12. Why is unrestricted Jackson default typing dangerous for persistence data?
13. When schema v2 is written while v1 pods are still running, what compatibility condition is required?
14. If decryption fails due to an AEAD tag mismatch, why must you never return a default authorization?
15. What test proves pod A can write and pod B can read the same authorization after a restart?
16. Why can backing up encrypted data without backing up keys prevent service recovery?

## References

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationConsent`, and token models.
- [Spring Authorization Server — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): serialization of `RegisteredClient`/`OAuth2Authorization` and Jackson modules.
- [Spring Authorization Server — How-to: Implement core services with Redis](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-redis.html): custom converters and Redis persistence.
- [Spring Security — Jackson Modules](https://docs.spring.io/spring-security/reference/servlet/integrations/jackson.html): `SecurityJackson2Modules` and support for security objects.
- [Spring Security Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html): symmetric encryptors, AES-GCM, and password encoding; verify APIs against your Spring Security version.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): external configuration, config trees, and secret injection; Spring Boot does not provide built-in property encryption.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): AEAD, key separation, DEK/KEK, key storage, and rotation.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key management, rotation, backups, and cryptoperiods.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): authenticated encryption and IV uniqueness requirements.
