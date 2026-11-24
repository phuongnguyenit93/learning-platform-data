# 11.2. Key Generation, Provisioning, Storage, Usage, Rotation, and Revocation

## Learning Objectives

By the end of this lesson, you will be able to:

1. Describe the **cryptographic key lifecycle** from planning, key generation, provisioning, activation, storage, and usage to rotation, deactivation, revocation, archival, and destruction.
2. Distinguish **data encryption keys (DEKs)**, **key encryption keys (KEKs)**, **symmetric keys**, **private/public keys**, digital certificates, and access secrets; accurately determine each key's purpose, owner, and permissions.
3. Generate keys securely in Java 17+ using `KeyGenerator`, `KeyPairGenerator`, and `SecureRandom`; understand the limits of `KeyStore`, the role of KMS/HSM, and the principle of never exposing raw keys.
4. Design **key versions**, **cryptoperiods**, decrypt-only permissions for old keys, scheduled rotation, and **emergency rotation** when key compromise is suspected.
5. Explain why **disable/revoke**, **delete/destroy**, **re-encrypt**, **rewrap**, and **certificate revocation** differ; avoid rendering old data undecryptable or mistakenly trusting signatures from a compromised key.
6. Run a Java 17+ example simulating generating two AES key versions, saving/reloading a `PKCS12 KeyStore`, encrypting with AES-GCM using a key version, reading old ciphertext after rotation, and rejecting a retired key version.

**Scope:** This lesson belongs to **Java Advance – security-cryptography / 11. Key Lifecycle**. The focus is on controlling *the entire lifecycle and trust boundaries*, not merely picking an AES/RSA algorithm or a keystore file path.

---

## 1. Why Does Key Management Matter More Than a Single `Cipher` Call?

An application can encrypt properly with `AES/GCM/NoPadding` and still be insecure if:

- the AES key is hard-coded in the repository or a shared configuration;
- the same key is used across all tenants without access boundaries;
- copies of the key in logs, caches, backups, or crash dumps are uncontrolled;
- when the key needs to rotate, the system immediately deletes the old key and **loses the ability to decrypt historical data**;
- a signing key is compromised yet the system continues treating all new signatures as valid;
- an operator clicks **disable** and mistakenly believes ciphertext has been re-encrypted or that the attacker lost their copy of the key.

Cryptographic primitives solve operations like encrypt/decrypt, sign/verify, and HMAC; **key management** answers who is allowed to create, use, store, distribute, rotate, revoke, and destroy the keys used by those primitives.

Fundamental principle: **the security of ciphertext is no greater than the security of the key and the processes using that key**. If an adversary obtains a valid plaintext key, strong AES alone cannot protect messages encrypted under that key.

### 1.1. Concepts to Distinguish

| Term | Practical Definition | Pitfall |
| --- | --- | --- |
| **Secret key** | Symmetric key shared for operations like AES/HMAC | Whoever holds the key can generally perform operations permitted by the algorithm; policy must restrict it |
| **Private key** | Secret component of a key pair (RSA/ECDSA/Ed25519...) | The public key may be published; the private key must be protected |
| **Public key** | Public component used to verify signatures or corresponding cryptographic steps | An unauthenticated public key cannot by itself prove “the right owner” |
| **DEK – Data Encryption Key** | Key that encrypts payloads/files/records | Can be generated per object/tenant and wrapped by a KEK |
| **KEK – Key Encryption Key** | Key that wraps/unwraps DEKs or other key material | Compromising a KEK can affect many wrapped DEKs depending on scope |
| **Key ID / version** | Stable identity of a key object and version of key material | Not a secret, yet a client-supplied version must not be trusted arbitrarily while bypassing policy |
| **Cryptoperiod** | Time span during which a key is authorized for a given purpose | Ending the **encrypt new** period does not necessarily mean **decrypt old** is disallowed |
| **Rotation** | Transitioning from an old key/version to a new key/version | Rotating metadata does not automatically rekey existing data |
| **Rewrap** | Re-protecting a DEK using a new KEK | Does not change payload ciphertext if the DEK stays the same; cannot fix an exposed DEK |
| **Re-encrypt** | Decrypting and re-encrypting payload under a new DEK/key | I/O intensive; requires integrity checks, atomic migration, and backups |
| **Revoke / disable** | Withdrawing permissions / marking a key unusable in the management system | Does not erase raw key copies an adversary already saved |
| **Destroy** | Destroying key material with appropriate assurance/procedures | Simply deleting a file alias does not prove every copy, backup, or memory residue is gone |

### 1.2. Not All Key Types Share the Same Lifecycle

**AES data key:** Used for encrypt/decrypt, requires unique nonce management under the same key, and often still needs to decrypt historical data after stopping new encryptions. 

**HMAC key:** Used to create/verify MACs; after rotation it may be needed to verify old messages within an acceptance window. Creating a new MAC is not separated from verifying an old MAC in a shared-secret model; anyone holding the HMAC key can still compute new MACs, so “verify-only” cannot be enforced cryptographically if they hold the raw key.

**Private signing key:** Used to sign; the corresponding public key verifies. After retiring signing, the public key/cert or metadata may still be needed to verify historical signatures, taking into account **signing time**, trust chains, and private key compromise policies.

**TLS private key/certificate:** A certificate has an expiration date and can be revoked through PKI mechanisms; replacing a certificate does not automatically purge a leaked private key everywhere.

**KEK in KMS/HSM:** May be non-exportable; rotating a KEK involves wrapped DEKs, unwrap permissions, and service usage policies.

**Password-derived key:** Strength is bounded by the password and requires a KDF with salt and work factor; do not equate it with a strong random key. If changing the password protecting a DEK, you can rewrap the DEK instead of re-encrypting all data.

## 2. Key Lifecycle: Operational Stages and Usage States

An easy-to-remember model:

```text
Define purpose / threat model
                 │
                 ▼
            Key generation
                 │
                 ▼
     Registration / provisioning / authorization
                 │
                 ▼
            Activation (ACTIVE)
                 │
        ┌────────┴──────────┐
        ▼                   ▼
  Authorized usage     Backup / monitoring
        │
        ▼
  Scheduled rotation / end of originator use
        │
        ▼
  Stop creating new data with old key
  (DECRYPT-ONLY / DEACTIVATED per policy)
        │
        ▼
  End of historical read & evidence retention needs
        │
        ▼
    Destroy / crypto-erase

Whenever suspected key compromise is detected:
  COMPROMISED → block usage, notify, replace key,
  investigate scope, and handle affected data/signatures
```

NIST SP 800-57 Part 1 Rev. 5 defines states such as **pre-activation, active, deactivated, compromised, destroyed** and their transitions, separating permission to use a key to *protect new data* from permission to *process previously protected data*. The diagram above is an application-oriented learning model, not a verbatim copy of the standard's state machine.

| State | What Is Allowed? | What Must Be Blocked / Handled Carefully |
| --- | --- | --- |
| **PENDING / PRE-ACTIVATION** | Metadata entry, key ownership verification, preparation, and approval | Not yet used for production encrypt/sign |
| **ACTIVE** | Operations matching intended purpose, policy, cryptoperiod, and quota | Do not grant unrestricted access; audit, check nonces, enforce policy |
| **DECRYPT-ONLY / DEACTIVATED** | Only reading old data or verifying history if policy/key type permits | Do not encrypt/sign new data with the old key |
| **SUSPENDED** | Temporarily paused during investigation/policy check; recoverable if not compromised | Do not keep granting access at the application layer merely because key material still exists |
| **REVOKED / COMPROMISED** | Only tightly controlled investigation/recovery actions | Do not create new trusted data/signatures; handle old data per incident plan |
| **DESTROYED** | Non-sensitive *evidence metadata* may be retained | Key can no longer be used to decrypt/sign; must not claim destroyed if key copies remain |

**Watch your terminology:** “Stopped encrypting with the old key” is routine **deactivation/rotation**. “Discovered the key was stolen” is a **compromise**, requiring emergency response; it cannot be handled with the same simple routine and declared over.

### 2.1. Cryptoperiod Is a Risk-Based Decision

Cryptoperiod should depend on the algorithm, key purpose, data volume, impact of compromise, invocation count/nonce limits, data classification, and compliance requirements. **There is no single 90-day or 1-year schedule that fits every key.** Set automated schedules and justified rotation triggers; never copy one number from an example blindly across all systems.

A DEK used for encryption for only a single day may still be needed for years to decrypt records within their retention period. That is why NIST separates the **originator-usage period** (creating new protection) from the **recipient-usage period** (processing legacy protected data).

## 3. Step 1 – Key Generation: Right Algorithm, Size, and Entropy Source

### 3.1. Define Intent Before Creating a Key

Before calling any API, specify at minimum:

- **Key purpose:** encryption, decryption, signing, verification, HMAC, key wrapping, or handshake;
- **Algorithm / size:** AES-128/256, HMAC-SHA256, RSA, or Ed25519 depending on protocol and policy;
- **Owner/tenant/service/asset:** which entity owns the key and who is accountable;
- **Exportability:** can raw key bytes be exported, or must they remain non-exportable inside an HSM/KMS?
- **Allowed operations:** encrypt/decrypt, sign/verify, wrap/unwrap, and specific context;
- **Environment:** production/staging/test must isolate key material; never share a key across all three;
- **Lifetime/volume:** validity window, quota, rotation triggers, encryption/nonce count limits;
- **Recovery:** backup/escrow/wrapped form, and whether the application needs to decrypt legacy data.

A strong key used for the wrong purpose, wrong tenant, or wrong algorithm is still a security failure. Do not choose RSA just because “the key is longer”; never reuse one key for both encryption and MAC, or across multiple protocols, without explicit key separation design.

### 3.2. Generating an AES Secret Key in Java 17+

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

SecureRandom rng = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, rng);
SecretKey key = generator.generateKey();
```

This is an **illustrative snippet that belongs inside a method handling checked exceptions**. In Java 17 with standard providers, AES-256 is supported; in restricted environments/providers, check policy and actual algorithm availability. In the full runnable program in Section 12, AES-128 is used for broad portability across Java 17 environments, which does not imply AES-128 fits every threat model.

Key points:

1. `KeyGenerator` requests a **key for the AES algorithm**, not a password.
2. `SecureRandom` is the API for cryptographically strong bits; never use `Random`, `ThreadLocalRandom`, timestamps, concatenated UUIDs, or hard-coded seeds.
3. `SecretKey` is a key reference object. A provider may store the key outside software memory, and `key.getEncoded()` may return `null` for non-exportable keys.
4. **Never print raw keys** via `Base64.getEncoder().encodeToString(key.getEncoded())` into logs or config files.
5. A 256-bit output hashed from a weak password is not equivalent to a 256-bit key from a CSPRNG; if the input is a password, you need a KDF and password policy.

### 3.3. Generating a Signing Key Pair in Java

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();
// pair.getPrivate() must be protected.
// pair.getPublic() can be published via a trusted mechanism.
```

This is an illustrative snippet requiring checked exception handling and provider support checks. `Ed25519` is for **digital signatures**; do not use an Ed25519 key pair as an AES encryption key.

`KeyPairGenerator.getInstance("RSA")` can also be used in compatible protocols/PKI, but key size and scheme/padding must follow policy. For TLS, generating a key pair alone does not issue a **CA-trusted certificate**; CSR generation, certificate issuance, chain validation, and trust policy are separate steps.

### 3.4. Prefer Generating Keys Inside the Right Security Boundary

- **Software-generated/exportable:** Java `KeyGenerator` or `KeyPairGenerator` returns key objects that are easy to integrate, but process RAM and backups must be protected.
- **Provider-backed:** HSM/PKCS#11 can generate keys on the hardware token and forbid exporting private/raw keys, reducing copies of key material.
- **Cloud KMS:** can generate and use keys within the managed service, or generate a temporary plaintext DEK + wrapped key. Usage and export policies vary by provider/API; **never assume every KMS key is exportable or every KMS call returns raw keys**.

If policy requires non-exportability, do not generate an exportable key in the application, import a copy, and claim “the key never left the HSM.” Verify where the key was actually generated and every path raw bytes travel through.

### 3.5. Testing Entropy Does Not Mean Eyeballing Randomness

A loop printing 100 distinct keys does not prove a generator is secure. `SecureRandom` quality depends on the implementation/provider and entropy source; never substitute time or predictable values as a seed. In high-assurance systems, inspect JDK/provider configuration, container/VM entropy environments, CSPRNG operational standards, and compliance policies.

## 4. Step 2 – Provisioning: Delivering Keys to the Right Authorized Party

**Key provisioning** is not emailing/chatting raw keys or copying a keystore file to every service. It is the workflow ensuring the right entity **is registered, authorized, and able to use the key for its exact purpose**.

A typical workflow includes:

1. **Request:** service/owner declares purpose, key type, algorithm, environment, tenant, retention, and export requirements.
2. **Approval:** policy/IAM and separation of duties determine who can create/activate/access/delete.
3. **Create or import:** key is generated within a secure boundary and tagged with key ID/metadata. Imports must verify origin, algorithm, format, and secure transport.
4. **Owner binding:** key ID ↔ service identity / tenant / dataset / operation / environment. Never trust arbitrary alias names sent in external requests.
5. **Authorization:** grant only the required `Encrypt`/`Decrypt`/`GenerateDataKey`/`Sign`/`Verify`/`Wrap`/`Unwrap`; avoid granting admin/disable/delete rights to runtime apps.
6. **Activation:** allow use only within permitted time, quota, and state; configure monitoring/auditing.
7. **Verification:** run tests without real production data to confirm identity, key version, and expected operations.

Example authorization model:

| Role | Permissions to Grant | Permissions to Avoid |
| --- | --- | --- |
| Application writer | `Encrypt` or `GenerateDataKey` for permitted keys/context | `DeleteKey`, exporting KEK, managing other tenants' keys |
| Application reader | `Decrypt`/`Unwrap` for specific objects and conditions | Unlimited create/rotate, delete key, key admin |
| Key administrator | Create, configure policy, schedule rotation upon approval | Reading plaintext data unless required |
| Incident responder | Disable, audit, trigger emergency workflows under controls | Unilaterally destroying keys before evaluating recovery/retention |
| Auditor | Read-only metadata, logs, status, and rotation history | Raw key material or plaintext |

A service permitted to decrypt every tenant effectively holds a “master skeleton key” even with strong AES. Combine IAM, resource policies, key aliases/context, business authorization, and audit logs. KMS cryptographic permissions do not replace **business-object authorization checks**.

### 4.1. Distributing Public Keys vs. Secret Keys Differs

- **Public key:** can be distributed, but requires **authenticity/binding** via certificates, pinned keys, a trusted registry, or a trusted channel; a public key is not a secret.
- **Private/secret key:** transport only via secure key transport/wrapping mechanisms, HSM/KMS workflows, or protected keystores. If raw keys enter RAM, assess the process, logs, crash dumps, network transfer, and recipient.
- **Wrapped DEK:** still requires authenticated key wrapping and context binding (tenant, object, version), not “Base64 of the key” or XOR with a password hash.
- **Certificate:** contains a public key and identity/issuer/signature details; it is **not** the same thing as a private key. A CA-issued certificate does not imply the private key is securely protected.

**The provisioning path is part of the lifecycle**, because even a very strong key can leak through one copy over an insecure channel.

## 5. Step 3 – Storage: KeyStore, KMS, HSM, and Backups

| Option | What Does It Store? | When Is It Appropriate? | Limitations |
| --- | --- | --- | --- |
| Java `KeyStore` type `PKCS12` | Private key + certificate chain, `SecretKeyEntry` when supported by provider, or certs | App/tool needing password/file-protected key storage | Both file and password are assets to protect; lacks centralized IAM/audit like KMS |
| Java `KeyStore` type `PKCS11` | Key/token references via a PKCS#11 provider | HSM/hardware tokens and hardware-backed requirements | Depends on device, provider, session/login, and token configuration |
| Cloud KMS | KEK/key object, key policy, versions, encrypt/decrypt or wrap/unwrap | Multi-service systems, centralized permissions, audit, rotation | Availability, permissions, network/latency, vendor lock-in |
| HSM | Key operations inside a secure hardware module, potentially non-exportable | Compliance, signing authority, KEKs/high-value assets | Cost/administration, quota, HSM-specific backup/recovery |
| Envelope encryption | Data ciphertext + wrapped DEK; KEK in KMS/HSM | Large data volumes, KEK rotation, multi-tenant | Must retain wrapped DEK, key ID/context, and handle temporary plaintext DEK in RAM |
| Secret manager | Secrets managed via API and policy | Storing app/software secrets requiring retrieval | Does not automatically replace all KMS/HSM functions or guarantee non-exportability |

**Note:** Having a `.p12` file does not automatically give you an HSM's security posture. `PKCS12` is a password-protected keystore format; if both the file and password are compromised, the keys are exposed. Never store `keystore.p12` and its unlock password in the same repository or container image and assume secrets are separated.

### 5.1. Distinguishing Keystore and Truststore

**A keystore for the application's own identity** typically holds a private key with its certificate chain, or a secret key. **A truststore** holds trust anchors/public certificates the application trusts for TLS/PKIX. Storing a certificate in a truststore **does not** mean you hold the matching private key; the truststore also requires integrity protection so attackers cannot inject rogue trust anchors.

In Java:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
store.load(inputStream, password);
Key key = store.getKey("data-v1", password);
```

This is a **non-standalone snippet**: it needs imports for `java.security.KeyStore` and `java.security.Key`, plus `inputStream`, `password`, and checked exception handling. The key may not exist, the password may be wrong, or the keystore/provider may not support the entry type. `getKey` returns a `Key` reference; it does not enforce application-level permissions, quotas, or cryptoperiods.

### 5.2. Principles for Storing Keys in Production

1. **Limit exportability:** if raw keys are not needed, prefer executing operations inside KMS/HSM.
2. **Least privilege:** runtime processes may only use the exact key/operation needed; never grant delete/rotate to every service.
3. **Independent access controls:** file permissions, secret distribution, token/service identity, network, and IAM.
4. **Encryption + integrity:** wrapped DEKs/PKCS12/passwords must be protected, and key metadata/aliases must also have integrity protection.
5. **Backup and recovery:** backing up keys differs from backing up ciphertext. Losing the key while keeping the data ≠ recoverable data.
6. **Audit:** track create/import/activate/use/rotate/disable/delete/export, while **never logging raw keys, passwords, or plaintext**.
7. **Environment isolation:** separate dev/test/prod and tenants/scopes; never copy a prod keystore onto a developer laptop.
8. **Copy lifecycle:** track caches, disaster-recovery replicas, snapshots, exported keystores, laptops, build pipelines, and CI artifacts.
9. **Approval for destructive actions:** delete/destroy requires checking retention, legal hold, legacy data version dependencies, and two-person control where appropriate.

### 5.3. Key Backups Must Not Create Unmanaged Copies

Key backups must have encryption, ownership, access policies, an inventory, and regular restore tests. Recovery capability must be **drilled**, not assumed from a “backup enabled” checkbox. If an HSM/KMS key is non-exportable, understand the product's own backup/restore capabilities and regional/account boundaries.

When performing **crypto-shredding/cryptographic erasure**, identify every DEK/KEK copy to destroy, wrapped copies, backups, and cache locations. Deleting a single cryptographic blob does not guarantee data is unrecoverable if the key survives in another copy.

## 6. Step 4 – Key Usage: Correct Scope and Cryptographic Constraints

### 6.1. Never Reuse the Same Key for Every Need

**Key usage separation:** An AES key for data encryption should be separated from HMAC keys, key-wrapping keys, signing keys, JWT secrets, and other protocols unless a standard algorithm specification defines safe subkey derivation. Having 256 bits of entropy does not mean a key can be reused endlessly across purposes.

For example:

- `data-v7`: AES-GCM for tenant A records;
- `wrap-v3`: KEK wrapping tenant A DEKs;
- `sign-v5`: private key signing messages;
- `tls-server-v2`: private key for TLS server identity.

A key ID must map to **one unambiguous key material + purpose + policy + version**. If an application user edits `keyId` in JSON to target another tenant's key, the backend must reject it even if the key ID lookup succeeds.

### 6.2. AES-GCM: Unique Nonce Under the Same Key

Every `AES/GCM/NoPadding` call using the **same key** must avoid reusing the **same nonce**. Nonce reuse severely breaks GCM's confidentiality and authenticity. Typically a 12-byte (96-bit) nonce and 128-bit tag are used; the uniqueness scheme must account for encryption volume, concurrency, restarts/snapshots, and provider behavior.

```java
byte[] nonce = new byte[12];
secureRandom.nextBytes(nonce);

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, aesKey,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(metadataBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintextBytes);
```

This is a **non-standalone snippet**: it requires JCA/JCE imports, variables `secureRandom`, `aesKey`, `metadataBytes`, `plaintextBytes`, and exception handling. In production, AAD should bind **key version, tenant, object, schema/operation** per design, and the decryptor must supply the exact same bytes. A nonce can be public, but it must be stored alongside ciphertext if decryption is required.

**Adding key version to AAD does not prevent nonce reuse.** Likewise, rotation does not retroactively fix ciphertexts already created with a repeated key–nonce pair in the past.

### 6.3. Restricting Permissions: Encrypt-Only and Decrypt-Only

When an app stops using key v1 for **new encryptions**, it may still need v1 to decrypt old records. The protocol should enforce:

- Encryption always fetches the **active key version** from a trusted key registry, never from caller parameters.
- Decryption reads the key ID/version from an authenticated/protected envelope and verifies that this version is permitted to decrypt the matching record/context.
- Key v1 transitions to **decrypt-only** or deactivated processing mode per KMS/policy semantics; it must not mint new ciphertexts.
- Retention and migration track how much v1 data remains and where, before retiring/destroying it.
- Never use key version as the sole authorization check: version is metadata, requiring role/owner/tenant binding and integrity.

**HMAC note:** Because the same secret key performs both MAC generation and verification, setting “verify-only” in a system sharing raw HMAC keys cannot prevent someone holding the raw key from computing new MACs. Enforce this at a service/HSM boundary or switch schemes when capabilities must be separated.

### 6.4. Observing Operations Without Exposing Secrets

Logs should record **key ID/version, service principal, operation name, outcome, timestamp, request ID, policy decision**, and standardized error codes. Never log `SecretKey.getEncoded()`, passwords, bearer tokens, plaintext, or IV+key together as a debug dump. Audit less obvious channels: crash dumps, heap dumps, APM traces, exception stacks, metrics labels, and test fixtures.

Not every failed key access is an attack, yet sudden spikes in wrong-key/tenant `Decrypt` calls, `AccessDenied`, nonce duplication, or unexpected policy changes must be monitored.

## 7. Step 5 – Routine Rotation

**Rotation** typically means starting to use **new key material** or a new key version for new operations while maintaining a path to handle legacy data. Switching an alias `current=v2` does not automatically re-encrypt v1 data.

### 7.1. Symmetric Key Version Workflow v1 → v2

```text
Before:
  ACTIVE encryption key = v1
  Old record: [version=v1, nonce1, ciphertext1, tag1]

Create v2:
  Generate(v2) → Policy/QA → ACTIVE for new writes
  Deactivate v1 for new encryption; keep v1 for permitted reads

During migration:
  New record: [version=v2, nonce2, ciphertext2, tag2]
  Old record still decrypts with v1 when needed

If the goal is to retire v1:
  Authenticate/decrypt v1 record → re-encrypt with v2 + fresh nonce
  → verify readback + atomic switch → confirm no remaining dependencies
  → destroy v1 per policy and inspect backups
```

Decision table:

| State | Encrypt New Record | Decrypt v1 Record | Decrypt v2 Record |
| --- | --- | --- | --- |
| Not rotated yet, v1 active | v1 | Yes | No v2 exists |
| v2 activated | **v2** | **Yes** within read window/policy | Yes |
| Fully migrated + confirmed no v1 remains | **v2** | No if v1 key was destroyed | Yes |
| v1 compromised | No v1 | Special handling only per incident plan | Yes if v2 was created/kept securely |

The condition **“all data migrated”** includes backups, replicas, archives, delayed messages, and rarely accessed records; missing any of them before deleting v1 can render historical data undecryptable. Never let one node keep encrypting under v1 while another node prepares to delete v1; rotation must be coordinated with rollouts and an active-version registry.

### 7.2. Envelope Encryption: Rewrap vs. Re-Encrypt

Suppose a large file is encrypted with a **random DEK**:

```text
payloadCiphertext = AES-GCM(DEK, plaintext, nonce)
wrappedDEK_v1    = Wrap(KEK_v1, DEK)
```

When only rotating the **KEK**, we can do:

```text
DEK = Unwrap(KEK_v1, wrappedDEK_v1)
wrappedDEK_v2 = Wrap(KEK_v2, DEK)

payloadCiphertext stays identical because the DEK did not change.
```

This is **rewrap**: changing the DEK's protection mechanism without reprocessing gigabytes of ciphertext. However, if the **DEK was exposed**, rewrapping does not make the payload safe again: you must generate a new DEK and **re-encrypt the data**. If KEK v1 was compromised and the attacker already captured `wrappedDEK_v1`, they may have already recovered the DEK; conduct an incident investigation instead of merely rewrapping and assuming safety.

A KMS may provide dedicated re-encrypt/wrap key operations without returning the plaintext DEK to the application. Check each provider's specification, policies, and key types; do not assume all KMS offerings expose the same API.

### 7.3. Signing Key Rotation Differs from Data Encryption Keys

For a private signing key `sign-v1`:

1. Create and activate `sign-v2`, publishing the corresponding public key/certificate through a trusted channel.
2. Stop issuing **new** signatures with private key v1.
3. Verifiers continue accepting **valid historical** v1 signatures according to signing-time, validity, and compromise policies.
4. After the required period, stop accepting v1 or apply long-term timestamp/attestation preservation workflows.

Distinguish **keeping the public key available to verify** from **allowing the private signing key to continue signing**. Do not delete all old public keys while historical signatures still require verification. If v1 was compromised, the situation is harder: forged new signatures may exist, and historical signatures require evaluation with proper timestamps/trust evidence.

### 7.4. Controlled Zero-Downtime Rollout Scenario

A sound production rotation generally follows:

1. **Prepare:** create v2, configure permissions, backups/restore, check compatibility and version-aware parsers.
2. **Deploy readers first:** ensure every instance can decrypt both v1 and v2 (subject to authorization) before switching writers.
3. **Activate v2 writers:** update the active version via a trusted registry/configuration and monitor whether any writer still emits v1.
4. **Observe:** track v2 encrypt rates, v1/v2 decrypt rates, latency, error rates, audit logs, and replication consistency.
5. **Re-encrypt/rewrap (if needed):** run checkpointed, idempotent migrations that verify tags and prevent data loss on rollback.
6. **Retire old:** only after checking inventory/dependencies, backup/DR, retention, approvals, and rollback policy.
7. **Document:** record actor, timestamp, reason, incident/ticket, key IDs, and verification results.

With multi-region setups, stale caches, and asynchronous queues, an overlap window where both v1 and v2 appear is common. The protocol must clearly govern decrypt permissions and maintain **a single source of truth for the active encryption version**, rather than relying on each machine's local wall-clock time to choose a key.

## 8. Step 6 – Revocation and Incident Response on Key Compromise

Revocation is not just “faster rotation.” **When key compromise is suspected**, assume an attacker may hold a copy of the raw key or may have already executed unauthorized cryptographic operations.

### 8.1. Actions That Do Different Things

| Action | Actual Effect | What Does It Not Guarantee? |
| --- | --- | --- |
| **Disable key** in KMS/policy | Blocks new operations through the policy-enforcing KMS | Does not delete exported/cached raw keys or stop decryption using a copy |
| **Revoke access grant / IAM** | Removes an identity's permission to encrypt/decrypt/sign | Does not destroy secrets that the identity copied earlier |
| **Rotate key** | Generates new material and directs new operations to v2 | Does not alter old ciphertext or revoke v1 copies |
| **Rewrap DEK** | Protects the DEK under a new KEK | Does not rescue data if the DEK itself was compromised |
| **Re-encrypt payload** | Creates new ciphertext under a new DEK and fresh nonce | Cannot “un-read” plaintext the attacker already decrypted earlier |
| **Revoke certificate** | Announces the certificate/key identity is no longer trusted for its purpose/from a point in time per PKI policy | Does not delete the private key or guarantee all clients check revocation immediately |
| **Delete/destroy key** | Removes key material per procedure, potentially achieving cryptographic erasure | Does not prove all backups or cached copies disappeared |
| **Expire credentials/tokens** | Blocks API calls using old credentials at the control plane | Does not change the encryption key if those are separate secrets |

### 8.2. Incident Response for Suspected DEK Compromise

For example, AES key `data-v1` was written into a log:

1. **Isolate the leak source:** stop log emission and unnecessary read access, preserving forensic evidence per procedure.
2. **Assess scope:** key version, tenants, data sets, wrapped DEKs, logs/backups, retention, and exposure window.
3. **Block new data creation:** disable v1 for new encryptions and activate v2 from a secure source; consider blocking v1 decrypt via API except for a restricted recovery pipeline.
4. **Handle legacy ciphertext:** if confidentiality must be restored going forward, decrypt from trusted data stores and re-encrypt with a new DEK/fresh nonce; recognize the adversary may already have read old ciphertext.
5. **Revoke related credentials/grants:** IAM keys, deployment secrets, service accounts, key grants, and all v1 copies.
6. **Migrate and verify:** inspect all primaries/replicas/backups in scope; preserve history and evidence.
7. **Retire/destroy** v1 once legal, recovery, and incident plans allow; report and update detection controls.

Do not blindly delete v1 the instant compromise is spotted if the system needs it to recover/migrate and has no trusted alternative backup. Conversely, never keep using v1 for new encryption simply because “it is still needed for decryption.” This is a balance between containment and recovery that requires an approved runbook.

### 8.3. Revoking a Private Signing Key / TLS Certificate

If a private signing key or TLS private key is exposed:

- Activate a new key pair and distribute the new public key/certificate through a trusted channel.
- Stop **new signing/new handshakes** with the old private key in controlled systems.
- For X.509 certificates, perform revocation at the CA or equivalent mechanism (CRL/OCSP or provider workflow) and verify relying party behavior.
- Review **issued signatures**: mathematical signature verification alone does not tell whether a signature was created *before or after the compromise*. Signed timestamps or trusted time evidence may be needed in long-term signature archives.
- If verifiers pin the public key without PKI, update the trusted-key registry/pins directly per protocol; CRL/OCSP may not apply.

**Do not confuse:** revoking a certificate does not destroy the private key on a compromised host. And public keys are usually non-secret, so deleting them is not how you “lock out an attacker”; update verifier trust policies and revoke access to the private key.

### 8.4. Revocation and Backups

A system backup storing **old key material** can reintroduce a key “deleted from the active store” after disaster recovery. Runbooks must maintain revoked/compromised status as trusted metadata reapplied **after restore**, rather than restoring an old raw keystore and accidentally re-enabling v1.

If a service is compromised, check secret copies in container images, environment variables, CI logs, crash dumps, snapshots, terminal histories, and build artifacts. Clicking rotate in a dashboard does not erase those copies.

## 9. Step 7 – Destruction, Archival History, and Auditability

**Key destruction** can be an irreversible, data-losing action. Perform it only when:

- the key's cryptoperiod has ended and no valid data still requires decrypt/sign/recovery under policy;
- data has been migrated or is explicitly authorized to become unrecoverable;
- backups, archives, replicas, and recovery copies have been assessed;
- approvals and retention/legal-hold checks are satisfied;
- destruction meets product/environment requirements with audit evidence.

**Crypto-erasure** makes encrypted data undecryptable by destroying the required key material; its effectiveness depends on **no usable key copies remaining**, no recovery paths surviving, and the key genuinely being the sole point of control. Never claim `KeyStore.deleteEntry(alias)` on a file or deleting a database row constitutes complete cryptographic erasure.

After destruction, non-sensitive metadata may still need to be retained: key ID, version, purpose, created/activated/retired timestamps, owner, algorithm, policy approvals, rotate/revoke/destroy events, and audit reconciliation; **never retain raw secrets** just for audit.

### 9.1. Key Destruction Is Not User Data Deletion

Deleting a record's DEK may leave ciphertext behind that cannot be read via normal mechanisms. This is an explicit policy decision; if a user requests **data deletion**, the system must also handle plaintext copies, searchable indexes, caches, logs, and separate retention obligations. Encryption and key destruction do not replace the full data-governance workflow.

### 9.2. Do Not Expect Absolute Zeroization from Java Objects

A `SecretKey` or `PrivateKey` may live on the Java heap, in native provider memory, or on a hardware token. Not every implementation lets you immediately wipe all copies; GC gives no guarantee of immediate or secure erasure. You can wipe application-owned `byte[]` buffers with `Arrays.fill` where appropriate, yet that **does not** prove every copy is gone. For strict control requirements, prefer non-exportable KMS/HSM keys and audited operational procedures.

## 10. Key Registry: Key Inventory and Metadata

A mature system needs a **key inventory/registry** rather than guessing keys from filenames or environment variables. Suggested business schema:

| Field | Meaning |
| --- | --- |
| `key_id` | Stable logical key identifier, containing no key material |
| `version` | Version of key material, e.g., 1, 2, 3 |
| `algorithm`, `length` | AES-256, Ed25519, RSA..., required parameters |
| `purpose` | Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap |
| `owner`, `tenant`, `environment` | Identity/responsibility boundaries |
| `state` | PRE-ACTIVE, ACTIVE, DECRYPT-ONLY, REVOKED, DESTROYED... |
| `created_at`, `activated_at`, `retired_at` | Lifecycle milestones and cryptoperiod |
| `provider_ref` | KMS key ARN/URI, HSM label, keystore alias... |
| `origin`, `exportable` | Origin of generation/import; raw key export policy |
| `rotation_policy` | Time/usage/incident triggers; owner responsible for rotation |
| `dependencies` | Datasets, wrapped DEKs, certificates, and backups |
| `approval/audit_ref` | Ticket, identity, action/outcome, and evidence |

**Never** store raw keys, private key bytes, passwords, or master secrets inside registry metadata. A key version may be written in a ciphertext header, yet the backend must **never** grant access based solely on that header: verify key/tenant/object binding and integrity.

### 10.1. Sample Envelope Record

```text
version=2
tenant=TENANT-A
key_id=data-tenant-a
key_version=7
nonce=<12 bytes>
ciphertextAndTag=<...>
aad=canonical(version,tenant,key_id,key_version,record_id)
```

This is a **conceptual format**, not a production parser/schema. In AES-GCM, AAD is authenticated but not encrypted. The decryptor must pass the exact same encoding/AAD and key version, and still enforce authorization to prevent swapping records across tenants/objects.

If multiple records are encrypted with AES-GCM under the same key, the nonce design must ensure no key/nonce pair repeats; never rely on differing logical key versions if the underlying raw key is actually identical.

## 11. Relationship with Java `KeyStore`, `keytool`, and TLS

### 11.1. Java `KeyStore` Is Key Storage, Not a Key-Lifecycle Service

`KeyStore` supports entries such as `SecretKeyEntry`, `PrivateKeyEntry`, and `TrustedCertificateEntry` depending on store type/provider. Calling:

```java
KeyStore ks = KeyStore.getInstance("PKCS12");
ks.load(null, password);
ks.setEntry("data-v1",
    new KeyStore.SecretKeyEntry(aesKey),
    new KeyStore.PasswordProtection(password));
```

only creates and adds an entry. It **does not provide** a rotation scheduler, IAM, tenant isolation, revocation logs, data migration, or remote auditing. `KeyStore` exposes `deleteEntry`, yet that only deletes an entry in the current store instance, not proof that every copy of v1 is gone.

Protect the password used with `PKCS12` separately from the encrypted data; hard-coding store passwords in source code is suitable only for demos, never production.

### 11.2. `keytool` and Certificates

Example generating an RSA pair + self-signed certificate in a PKCS12 file for **testing**:

```shell
keytool -genkeypair -alias service-sign-v1 -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -keystore service-sign.p12 -storetype PKCS12 -validity 365
```

This command runs interactively prompting for password/subject; it has no fixed stdout. **A self-signed certificate is not automatically trusted by other clients**. Production requires proper CA/PKI or trusted-key distribution, private key protection policies, and rotation plans before expiry.

Inspect aliases/public certificates in a keystore:

```shell
keytool -list -v -keystore service-sign.p12 -storetype PKCS12
```

**Never** pass real passwords via command-line arguments where process lists or shell history may expose them. Never place private key files and store passwords together in repositories, Docker images, or public backups.

### 11.3. TLS Certificate Rotation

TLS typically requires updating the key pair/certificate chain, server/client trust configuration, OCSP/CRL or PKI policies, and synchronized deployment. Having a new certificate on disk does not mean running connections/server instances have reloaded it. Verify real handshakes, trust chains, hostnames, `notBefore`/`notAfter`, private-key possession, rollback, and overlapping certificate validity windows.

**Remember:** changing a certificate or alias does not automatically rotate data encryption keys in your database. Distinct key purposes require distinct inventories and lifecycles.

## 12. Standalone Java 17+ Program: Generate, Store, Encrypt, Rotate, and Retire

Create file **`KeyLifecycleDemo.java`**. This demo simulates a small lifecycle of two **AES data keys**:

1. Generate v1 with `KeyGenerator`, store it in a `PKCS12 KeyStore`, and encrypt a record with v1.
2. Generate an independent v2, store v2; serialize the KeyStore to a byte buffer and reload it to demonstrate **store/load** without creating actual files.
3. Start encrypting new data with v2; still decrypt the v1 record using the stored v1, proving rotation does not force losing legacy data.
4. Use `AES/GCM/NoPadding` with a 12-byte nonce, 128-bit tag, and AAD bound to the key version; test tampering with the tag or specifying the wrong version.
5. Delete the v1 alias from the *active* store and verify the v1 record **can no longer be decrypted through this store**. This only simulates retirement, **not a production destroy/compromise response procedure**.

**Known limitations:** The password literal and in-memory KeyStore are for demonstration only, **not for protecting real data**. In real applications, keystore passwords must come from secret management; runtime policy must enforce encrypt/decrypt permissions by state/tenant/authorization; and you need secure persistence, backups, auditing, large-scale nonce uniqueness, and key migration. JDK 17 with standard PKCS12 providers supports `SecretKeyEntry`; third-party providers may have their own restrictions.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyLifecycleDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private record Envelope(
            int keyVersion, byte[] nonce, byte[] ciphertextAndTag) {}

    private static SecretKey newAesKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RNG); // Universal baseline for this demo.
        return generator.generateKey();
    }

    private static String alias(int version) {
        return "data-v" + version;
    }

    private static void put(KeyStore store, int version,
            SecretKey key, char[] password) throws Exception {
        store.setEntry(alias(version),
                new KeyStore.SecretKeyEntry(key),
                new KeyStore.PasswordProtection(password));
    }

    private static SecretKey read(KeyStore store, int version,
            char[] password) throws Exception {
        KeyStore.Entry entry = store.getEntry(alias(version),
                new KeyStore.PasswordProtection(password));
        if (!(entry instanceof KeyStore.SecretKeyEntry secret)) {
            throw new GeneralSecurityException(
                    "Key version unavailable");
        }
        return secret.getSecretKey();
    }

    // Domain separation + key version are authenticated as AAD.
    private static byte[] aad(int version) {
        return ("key-lifecycle-demo:v1:version=" + version)
                .getBytes(StandardCharsets.UTF_8);
    }

    private static Envelope seal(int version, SecretKey key,
            byte[] plaintext) throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(version));
        return new Envelope(
                version, nonce, cipher.doFinal(plaintext));
    }

    private static byte[] open(Envelope envelope, KeyStore store,
            char[] password) throws Exception {
        SecretKey key = read(store, envelope.keyVersion(), password);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(aad(envelope.keyVersion()));
        return cipher.doFinal(envelope.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: password literal is NOT safe for production.
        char[] password = "demo-only-store-pass".toCharArray();
        try {
            KeyStore firstStore = KeyStore.getInstance("PKCS12");
            firstStore.load(null, password);

            SecretKey keyV1 = newAesKey();
            put(firstStore, 1, keyV1, password);

            byte[] payload =
                    "encrypted customer record".getBytes(
                            StandardCharsets.UTF_8);
            Envelope oldRecord = seal(1, keyV1, payload);

            // Rotation: new key for new encryption.
            SecretKey keyV2 = newAesKey();
            put(firstStore, 2, keyV2, password);
            Envelope newRecord = seal(2, keyV2, payload);

            // Demonstrate serialization + reload of the key store.
            ByteArrayOutputStream serialized =
                    new ByteArrayOutputStream();
            firstStore.store(serialized, password);
            KeyStore restored = KeyStore.getInstance("PKCS12");
            restored.load(new ByteArrayInputStream(
                    serialized.toByteArray()), password);

            boolean bothPresent =
                    restored.containsAlias(alias(1))
                    && restored.containsAlias(alias(2));
            boolean oldReadable = Arrays.equals(
                    payload, open(oldRecord, restored, password));
            boolean newReadable = Arrays.equals(
                    payload, open(newRecord, restored, password));

            // A different key version must NOT silently work.
            Envelope wrongVersion = new Envelope(
                    2, oldRecord.nonce(),
                    oldRecord.ciphertextAndTag());
            boolean wrongVersionRejected = false;
            try {
                open(wrongVersion, restored, password);
            } catch (AEADBadTagException expected) {
                wrongVersionRejected = true;
            }

            // GCM detects a changed authentication tag.
            byte[] changed = newRecord.ciphertextAndTag().clone();
            changed[changed.length - 1] ^= 1;
            Envelope tampered = new Envelope(
                    2, newRecord.nonce(), changed);
            boolean tamperRejected = false;
            try {
                open(tampered, restored, password);
            } catch (AEADBadTagException expected) {
                tamperRejected = true;
            }

            // Retire the v1 alias from the store used for lookups.
            restored.deleteEntry(alias(1));
            boolean v1RetiredFromStore =
                    !restored.containsAlias(alias(1));
            boolean oldUnavailable = false;
            try {
                open(oldRecord, restored, password);
            } catch (GeneralSecurityException expected) {
                oldUnavailable = true;
            }

            System.out.println("bothVersionsRestored=" + bothPresent);
            System.out.println("oldRecordReadableAfterRotation="
                    + oldReadable);
            System.out.println("newRecordReadable=" + newReadable);
            System.out.println("wrongVersionRejected="
                    + wrongVersionRejected);
            System.out.println("tamperRejected=" + tamperRejected);
            System.out.println("v1AliasRetired=" + v1RetiredFromStore);
            System.out.println("oldUnavailableThroughStore="
                    + oldUnavailable);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Compile and run in the directory containing the file:

```shell
javac KeyLifecycleDemo.java
java KeyLifecycleDemo
```

**Expected stdout on standard Java 17 supporting PKCS12 `SecretKeyEntry` and AES/GCM:**

```text
bothVersionsRestored=true
oldRecordReadableAfterRotation=true
newRecordReadable=true
wrongVersionRejected=true
tamperRejected=true
v1AliasRetired=true
oldUnavailableThroughStore=true
```

### 12.1. Explaining the Results

- `bothVersionsRestored=true`: the KeyStore holds aliases v1 and v2 and can reload from its serialized form. This **does not** mean password protection, backups, and access controls meet production standards.
- `oldRecordReadableAfterRotation=true`: introducing v2 does not invalidate v1; old records still require v1 for decryption. This is the crucial **decrypt-old / encrypt-new** phase during migration.
- `newRecordReadable=true`: key v2 encrypts/decrypts successfully with AES-GCM, matching AAD and nonce.
- `wrongVersionRejected=true`: taking v1 ciphertext and labeling it key version 2 causes decryption to use key v2 and AAD v2, so the GCM tag mismatches. Never “try every key until decryption succeeds” to bypass ownership and policy.
- `tamperRejected=true`: modifying the authentication tag triggers `AEADBadTagException`, and the application must reject the ciphertext.
- `v1AliasRetired=true`: alias v1 was deleted **from the `restored` KeyStore object**, not from all copies.
- `oldUnavailableThroughStore=true`: looking up v1 through **the active store** fails, so `oldRecord` cannot be decrypted via that path. This is **not proof of crypto-erasure**: `keyV1`, `firstStore`, and the serialized bytes still exist in the demo program. This distinction is critical when defining “key destruction.”

**Lesson warning:** The code generates a new random nonce per encryption at demo scale. Production systems with large ciphertext volumes must design nonce uniqueness and usage limits per key and environment, never trusting that random implies zero collisions. `Envelope` is a record holding mutable arrays and is not a production parser/format; it lacks defensive copies, tenant ID, record ID, key registry/IAM, and real data persistence.

### 12.2. Why Not “Delete v1 Immediately After Creating v2”?

Calling `deleteEntry("data-v1")` the moment v2 becomes active renders unmigrated v1 records unreadable through the current store. In real systems, millions of records and unscanned backups may exist. You need a **migration plan, inventory data, read compatibility, restore tests, and retention policies** before retiring/destroying keys.

If v1 is **compromised**, you may need to revoke new usage immediately while keeping a tightly restricted recovery path for re-encryption. That is an emergency workflow distinct from scheduled rotation.

### 12.3. What the Demo Intentionally Omits

The demo does not provision user credentials, persist key files to disk, write audit logs, use a KMS/HSM, issue certificates/PKI, guarantee wiping raw keys from RAM, or enforce decrypt-only permissions or real compromised states. It lets you observe the **difference between creating a new version, reading legacy data, and deleting an alias from lookup**; real products require permission boundaries and server-side state management.

## 13. Common Mistakes, Consequences, and Fixes

| Mistake | Consequence | Proper Practice |
| --- | --- | --- |
| Hard-coding keys/passwords in source, images, or shared env | Leaked across deployments, hard to rotate | KMS/HSM/secret manager, IAM/ACL, secure distribution |
| Generating AES keys with `Random`, `Math.random()`, timestamps | Keys can be predicted | `KeyGenerator`/`SecureRandom` or HSM/KMS key generation |
| Storing private keys and certificates in a public repository | Anyone reading the repo can impersonate the subject | Public certificates can be shared; private keys must stay secret |
| Sharing the same raw key between prod and test | Test environment compromise affects prod | Separate key material and policies by environment |
| Using one shared key for all tenants | Cross-tenant exposure if decrypt permissions are broad | Key scoping/authorization by tenant and context |
| Granting runtime `DeleteKey`/admin permissions | An app bug can wipe all data | Least privilege, separation of duties, approvals |
| Allowing all key versions to encrypt by default | App writes new records with retired keys | Trusted active-version registry; state-bound encryption permission |
| Rotating without storing key version in the envelope | No way to know which key decrypts history | Versioned/authenticated metadata, policy-checked lookup |
| Deleting old keys before migration completes | Backups/v1 records become unrecoverable | Readers supporting old versions, checkpoints, full dependency checks |
| Thinking rewrap saves data after a DEK leak | Exposed DEK still decrypts old ciphertext | Rotate DEK + re-encrypt + incident response |
| Reusing an AES-GCM nonce under the same key | Breaks confidentiality and authenticity | Nonce uniqueness, usage limits, coordination across restarts |
| Clicking “Disable” and assuming the attacker lost the key | Exported/cached raw copies outside KMS still work | Scope compromise, re-encrypt, revoke credentials, investigate |
| Hitting delete immediately during an incident | Loses ability to re-encrypt/recover during incident | Controlled containment first; destroy per runbook |
| Treating `KeyStore.deleteEntry` as secure wipe | Keys remain in backups, memory, clones | Trace all key material; destroy to required assurance |
| Replacing a cert without checking TLS trust chain/reload | Server/client keeps running old config; handshake failures | Real handshake tests, overlapping rollouts, PKI revocation |
| Logging raw keys or `getEncoded()` | Secret exposure creating hard-to-purge copies | Log only key ID/version/operation/outcome |
| Letting client-supplied key ID authorize arbitrary decryption | Cross-tenant data access | Key↔tenant↔resource binding, server-side authorization |
| Having no key backups | Losing the key = losing all ciphertext | Policy-driven backup/restore drills, protecting all copies |
| Not tracking expiration/cryptoperiod | Overdue or orphaned keys in use | Inventory + alerts + scheduled/event-driven rotation |
| Restoring a backup keystore containing a revoked key | Accidentally reactivating a compromised key | Restore must reapply denylist/status from a trusted registry |

## 14. Practice Scenarios with Answers

**Scenario A – App upgraded v1 → v2 but cannot read old records.**  
Likely causes include omitting key version, deleting v1 too early, or a parser that only supports the active key. Solution: versioned envelopes, v1 decrypt permission during migration, reader-first rollout, data inventory, and QA before retirement.

**Scenario B – KEK in KMS rotated, yet old wrapped DEKs were not rewrapped.**  
If policy allows old key versions for unwrap, data may still be readable, though dependency on old key material remains; verify exact provider semantics and schedule rewrap/retirement. Do not confuse “KMS auto-rotation” with “all ciphertexts switched to new key material.”

**Scenario C – A former employee holds a copy of a raw AES key.**  
Revoking IAM/KMS grants blocks API calls on current systems, **but does not invalidate the copied raw key**. Identify affected ciphertexts and the exposure window, re-encrypt under a new key, restrict copies, and review other exposed permissions/secrets.

**Scenario D – A signing key expired, yet old contracts must still be verified.**  
Stop using the private key for new signatures; retain the public key/certificate and signing-time evidence per long-term signature policy. If the private key was compromised, do not rely solely on `Signature.verify == true`; evaluate compromise status, time evidence, and trust.

**Scenario E – To “delete data,” only the DEK in the primary keystore was deleted.**  
Check wrapped copies, backups, replicas, process memory, snapshots, and recovery policies; plaintext copies and search indexes must also be handled. Deleting a single alias does not prove all secrets are gone.

**Scenario F – While deploying v2, an old node keeps encrypting with v1.**  
Use an active-version registry, key-management layer enforcement, reader-first deployment, and audit monitoring of encrypt counts by version; fix any v1 writers before retirement.

**Scenario G – 10,000 records are encrypted with AES-GCM under the same key using a random nonce each time. Can it be assumed safe forever?**  
No. Follow GCM nonce/usage limits for system scale, collision probability, concurrency/restarts, threat model, and provider standards. When needed, use coordinated nonce counters and rotate keys before hitting limits.

**Scenario H – Tenant A tries to decrypt tenant B's record by changing `keyId` in the request.**  
The backend must reject it based on tenant/resource authorization and key binding, even if `keyId` is valid and exists in KMS. Cryptography alone does not enforce business authorization.

## 15. Pre-Go-Live Operations Checklist

- [ ] **Inventory:** does every key have an owner, purpose, algorithm, ID/version, environment, state, cryptoperiod, and dependencies?
- [ ] **Generation:** generated with an appropriate CSPRNG/HSM/KMS, proper key size, no fixed seeds or unnecessary exports?
- [ ] **Provisioning:** provisioned to the right service/tenant with least-privilege IAM, approvals, and secure distribution channels?
- [ ] **Storage:** keystore files and passwords separated, backups encrypted, HSM/KMS policies clear, restores tested?
- [ ] **Usage:** encryption key selected via active-version registry, valid AAD/nonces, authentication tags verified, object-level decrypt authorization?
- [ ] **Rotation:** reader-first rollout, old decrypt-only support, migration/rewrap/re-encryption where needed, zero remaining old dependencies confirmed?
- [ ] **Revocation:** incident runbook for suspected compromise, access revocation, assessment of copies and affected data/signatures?
- [ ] **Destruction:** destruction criteria defined, retention/legal hold checked, and method to verify no usable key copies remain?
- [ ] **Audit:** non-sensitive metadata logged, usage anomalies monitored, create/activate/rotate/disable/delete traced?
- [ ] **Recovery:** plans for KMS/HSM outage, lost keystore password, disaster recovery, proper key escrow, and reapplying revoked status after restore?

**Key takeaway to remember:** Generating a key securely is only step one. **Provisioning to the right entity, storing in the right place, controlling usage, rotating versions safely, revoking with proper semantics, and destroying once dependencies end** together form a trustworthy key lifecycle.

## References

- [NIST SP 800-57 Part 1 Rev. 5 – Recommendation for Key Management: General](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key types, lifecycle states, cryptoperiods, key generation/backup/revocation/destruction.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key inventory, least privilege, storage, key rotation, and monitoring.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): key handling, AEAD, key storage, ciphertext, and key lifecycle.
- [Java SE 17 – KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): generating secret keys by algorithm.
- [Java SE 17 – KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): generating key pairs.
- [Java SE 17 – SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographic randomness source for key material and nonces.
- [Java SE 17 – KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): `SecretKeyEntry`, `PrivateKeyEntry`, `setEntry`, `getEntry`, `store/load`, and `deleteEntry`.
- [Java SE 17 – Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html) and [GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): AES-GCM, tags, nonces, AAD, and authentication.
- [JDK 17 keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): creating and managing key pairs/certificates and PKCS12 keystores.
- [NIST SP 800-38D – Galois/Counter Mode](https://csrc.nist.gov/pubs/sp/800/38/d/final): AEAD properties and AES-GCM nonce/IV requirements.