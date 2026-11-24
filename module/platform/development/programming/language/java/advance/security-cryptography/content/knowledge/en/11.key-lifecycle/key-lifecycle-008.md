# 11.8. Key Backup, Recovery, and Handling Lost or Compromised Key Incidents

## 1. Why Is Key Backup Different from Data Backup?

In a cryptographic system, a **key** may be the sole condition for decrypting databases, recovering files, authenticating messages, verifying legacy signatures, or unwrapping wrapped data keys. An intact ciphertext backup **is useless for decryption** if the required key is lost and no valid recovery path exists.

At the same time, backing up keys increases the number of locations where secrets can be stolen. Key management must therefore balance **availability** against **confidentiality, integrity, authenticity, and usage control**.

Three scenarios must be distinguished:

1. **Key temporarily inaccessible with no sign of compromise:** e.g., temporary KMS node outage, accidentally deleted keystore, or failed key storage hardware. The goal is restoring the exact versioned secret into a trusted environment, then verifying data and applications. Do not automatically conclude the key was compromised.
2. **Key permanently lost:** no backup, escrow, approved reconstruct/re-derive path, or provider recovery mechanism exists. If data was encrypted solely under that key, in principle **plaintext cannot be recovered by generating a new key**. This is an inherent consequence of cryptographic security.
3. **Key compromised or suspected compromised:** an attacker may know the key or invoke signing/decryption operations. **Simply restoring a backup or renaming an alias does not make the old key safe again.** You must isolate, assess scope, replace keys, update data protection, revoke related permissions, and handle fallout.

This lesson focuses on the **key lifecycle** in Java/JCA/JCE, not merely calling `KeyStore.load`. The goal is designing backup/restore policies, distinguishing key loss from key compromise, running incident response, choosing when to *rotate*, *rewrap*, *re-encrypt*, or *revoke*, and understanding the limits of rescuing data via backups.

## 2. Terminology to Use Consistently

| Term | Meaning | Remember |
| --- | --- | --- |
| **Backup** | Protected copy kept for incident recovery | Has creation schedules, protection, restore tests, and retention/deletion policies |
| **Recovery/restore** | Restoring ability to use the exact key/version for permitted functions | Must verify integrity and recovery authorization |
| **Archive** | Retaining material or metadata for historical access/auditing | Not enabled by default to protect new data |
| **Key rotation** | Switching to a new key/version for new operations | Does not automatically change encryption on legacy ciphertexts |
| **Rewrap** | Unwrapping a DEK and wrapping **the same DEK** with a new KEK | Does not change the DEK secret encrypting payloads |
| **Re-encrypt/rekey** | Decrypting old data and re-encrypting with a **new DEK and new nonce** per protocol | Requires accessible data and authorized access to the old key in a safe environment |
| **Revoke/disable** | Prohibiting or restricting use of a key/certificate/credential | Does not render copies already stolen by an attacker useless |
| **Destroy/crypto-erasure** | Destroying copies of key material per policy, making encrypted data unrecoverable if no other path remains | Must account for backups, archives, snapshots, replicas, and derived keys |
| **KeyId/keyVersion** | Identifier and version used to locate the right key for decryption/verification | Never treat a client-supplied keyId as trusted proof by itself |

**Backup is not replication.** A multi-replica system can propagate an accidental deletion or corrupted key to every replica. An independent, immutable, or isolated backup defends better against those faults, yet still requires read-access controls and restore testing.

**Backup is not permanent usage permission.** A key past its period for **creating** new ciphertexts/signatures may still be needed to **decrypt** old data or **verify** historical signatures. Policies must distinguish *originator-usage period* from *recipient-usage period* per key type and applicable regulations; restoring a key does not automatically restore permission to create new protected data.

## 3. Not Every Key Should Be Backed Up the Same Way

The first question in a recovery plan: **what key is it, who owns it, what is it used for, and what is the impact if it is gone?**

| Key Type | If Lost | Backup/Restore Strategy to Consider | If Suspected Compromised |
| --- | --- | --- | --- |
| Symmetric **DEK** (*data-encryption key*) | Cannot decrypt records using only that DEK | Wrap DEK with a KEK, keep wrapped DEK and metadata; back up raw DEKs separately only per policy | Generate a new DEK and **re-encrypt** affected data; assess data that may have been read |
| **KEK** (*key-encryption key*) | Cannot unwrap DEKs under that KEK | KMS/HSM versioning, backups, or redundancy via vendor-approved mechanisms | Create a new KEK; *rewrap* still-trusted DEKs; if old wrapped DEKs could have been captured by an attacker, evaluate **re-encrypting with new DEKs** |
| **Master/root key** | Can lose recovery across many key branches | Dedicated DR workflows, quorum, official HSM replication/backup, multiple fault domains | Severe incident: map full key hierarchy and blast radius; perform controlled replacement |
| **Digital signing private key** | Cannot create **new** signatures under the old identity/key | Generally **avoid backing up** and do not archive private signing keys solely to check old signatures; policy may require generating a new pair | Stop signing, revoke/mark key compromised, issue new public key/cert, review signatures created during suspected window |
| **Decryption/transport private key** | May fail to decrypt key material sent to the matching public key | Recoverable per policy, protected as a secret; do not equate with a signing key | Replace key pair; recover data and re-protect if needed |
| **Public key/certificate** | Loss of verification/identification if trust metadata is missing | Keep public copies, cert chains, trust anchors, and version info | When matching private key leaks, revoke/mark trust untrusted—do not merely swap the public key file |
| **HMAC key/API shared secret** | Cannot verify old tags/tokens; potential protocol outage | Back up per purpose, manage lifetimes and versions; avoid unnecessary secret sprawl | Rotate, reject tags/tokens created under the exposed key per policy; coordinate with partners |
| **Ephemeral session key** | Temporary session lost; may require re-handshake | Usually **do not back up**; establish a new session | Terminate session, renegotiate keys, investigate scope |
| **Password-derived key** | Cannot re-derive if password, salt, or required parameters are lost | Protect password/credentials per policy; always retain salt, algorithm, cost, and non-secret metadata needed for derivation | Rotate credentials/derived keys when possible; assess whether protected data was exposed |

**Important point on signing keys:** NIST SP 800-57 Part 1 Rev. 5 states that backing up **private signature keys** is discouraged in most cases and archiving private signature keys does not align with that policy. Keeping public keys/certificates to verify historical signatures is **different** from keeping private keys able to keep signing. Always follow specific organizational and industry regulations.

**Non-exportable keys:** if a private/secret key was created inside an HSM or KMS with a non-exportable policy, never try calling `getEncoded()` or copying raw keys to “back it up.” Many providers return `null` or forbid export. Backups/replication must go through **officially supported HSM/KMS features** (secure key backup, HSM-to-HSM cloning, multi-region replicated keys, disaster-recovery domains) where available; these mechanisms have their own permission, key-type, geographic, and operational constraints.

## 4. Designing Envelope Encryption to Shrink Recovery Scope

For large-scale data, consider *envelope encryption*:

- **DEK:** a random key for an object, group of objects, or partition per policy. The DEK encrypts data using an AEAD, such as `AES/GCM/NoPadding`.
- **KEK:** a key used to *wrap/unwrap* DEKs. The KEK can be managed by a KMS/HSM, while stored DEKs remain in **wrapped form**.
- **Metadata:** binds the record to `keyId`, `keyVersion`, algorithm, parameters, nonce/IV, AAD, record version, wrapped DEK, and fields required for recovery.

```text
                 KMS/HSM: KEK version v1
                         |
Random DEK ------------- wrap ---------> wrappedDEK(v1)
     |                                           |
AES-GCM(payload, IV, AAD)                        |
     |                                           |
     +---- store with record: ciphertext || tag -+
                                + IV + AAD + keyId/keyVersion

When reading:
  metadata + wrappedDEK -> KMS/HSM unwrap with KEK v1 -> DEK
  DEK + IV + AAD + ciphertext/tag -> AEAD decrypt + verify
```

Benefit: large datasets need not be re-encrypted merely because **the KEK rotates routinely**; `KEK-v2` can rewrap **the same DEK** and update metadata atomically. However, if the **DEK** itself leaked, or an attacker may have captured both **KEK-v1** and **wrappedDEK-v1** before rewrapping, changing the wrapping layer **does not remove the attacker's ability to decrypt old data**. In that case, evaluate re-encrypting payloads under a **new DEK** and containing past impact.

A successful `unwrap` only means usable key material exists; it does not prove the requester is authorized to read that tenant or record. Authorization, auditing, scoping policies, and tag checks remain mandatory.

## 5. What Must Be Backed Up to Recover the *Right Key*?

### 5.1. More Than Just a Keystore File

A useful **recovery bundle** may include:

1. **Key material permitted for backup:** keys or *wrapped/encrypted* copies per policy; never export non-exportable keys.
2. **Key inventory and mapping:** keyId, keyVersion, alias, owner/service, tenant, purpose, algorithm, size, creation/activation/expiration timestamps, and compromised/revoked status.
3. **Format and cryptographic parameters:** `AES/GCM/NoPadding`, IV/nonce, tag length, AAD, and serialization/schema. Losing IV/AAD/tag can make data undecryptable/unverifiable even with the key.
4. **Key-wrapping info:** wrappedDEK, wrappingKeyId/version, wrap algorithm, and KMS/HSM access policies.
5. **KDF info (if applicable):** salt, KDF name/version, iterations or work factor, output length, normalization/encoding. Salts are usually non-secret yet **must match** to re-derive keys.
6. **Certificates and trust metadata:** public certificate chains, trust anchors, CRL/OCSP/policy, or long-term signature validation evidence where required.
7. **Encrypted data with matching snapshot/version:** database/ciphertext backups, file objects, manifests/checksums, schema migrations, and logs needed to reconstruct state.
8. **Recovery runbook:** versioned docs, authorized personnel, backup locations, integrity checks, dual-approval rules, emergency stop points, rollback, auditing, and plans when a KMS region is down.

For example, backing up a `KeyStore` while forgetting the **entry password**, alias, or corresponding `iv` bytes in the database can still lead to *unrecoverable data*; conversely, backing up all data while keeping the KEK solely inside the same wiped system can create an unbootable dependency loop.

### 5.2. Break Bootstrap Dependency Cycles

**Anti-pattern:** a database backup is encrypted with key A; key A's backup lives inside that exact database, and the system can decrypt the database only after fetching key A. That is a dependency cycle with no recovery path.

Design an independent bootstrap path:

- KMS/HSM recoverable per policy outside the primary database.
- A valid key backup protected by an independent mechanism with enough authorized people/permissions to restore while prod is down.
- Credentials/approvals for recovery **do not** reside solely inside the application or accounts that could be lost in the same outage.
- Procedures executable inside a **clean environment** when production is suspected compromised.

### 5.3. Backups Must Match Data Versions

Key changes and rewraps alter metadata/wrappedDEKs. Backing up a database at time T while only holding a KEK from time T+1 or T−1 can leave part of the data unreadable.

Therefore:

- Retain KEK versions needed to **decrypt valid data** throughout the policy's access/retention window.
- Record exact `keyVersion`/`wrappingKeyVersion` on records.
- Update wrappedDEKs and metadata **atomically** or use idempotent migration/retry plans.
- Verify restoration **from real snapshots**, including older pre-rotation records, not just the newest record.

Never delete an old KEK while valid data still lacks a path to open under a new key, unless an intentional **crypto-shredding** policy accepts losing readability.

## 6. Securing Key Backups: Backups Are High-Value Assets

A key backup useful to operators **can be equally useful to attackers** if exposed. The goal is not “making lots of copies,” but maintaining **independent, protected, and tested copies**.

### 6.1. Protecting Confidentiality and Integrity

- **Encrypting key backups/wrapping:** use KMS/HSM or strong protection suited to the key type. For password-based keystores like PKCS#12, generate and protect strong passwords; never use demo passwords, short passwords, or hard-coded source credentials.
- **IAM controls:** separate permissions for creating backups, reading backups, restoring, importing keys, administering KEKs, and using keys in business workloads. Enforce **least privilege** and separation of duties.
- **Dual control/quorum:** recovering critical root keys may require two or more audited approvers, preventing any single account from unilaterally exporting everything.
- **Integrity assurance:** checksums catch accidental corruption; keyed authentication like MACs/digital signatures or built-in keystore/backup verification catches unauthorized tampering. **Unkeyed checksums are insufficient** against someone able to modify both the backup and checksum.
- **Transport security:** use authenticated, encrypted channels when moving backups over a network; never paste raw keys into chat, email, issue trackers, or logs.

### 6.2. Defending Against Ransomware, Accidental Deletion, and Disasters

- Maintain **versioned backups**, immutability/write-once controls during retention where appropriate, and deletion permissions isolated from primary system operations.
- Store copies in distinct fault domains: separate zones/regions or offline where risk models require.
- Common resilience patterns (such as the **3-2-1** rule for data) are helpful baselines, yet do not treat a number alone as a **key security guarantee**. Every secret copy also adds attack surface; evaluate key policies independently.
- Govern retention, access to old snapshots, storage vendors, and disposal/destruction of expired backups.

**Immutable copies only prevent certain edits/deletions**; they do not stop someone with snapshot read access from stealing raw keys or ciphertexts. Combine read restrictions with encryption.

### 6.3. Split Knowledge and Secret Sharing

For high-value root recovery material, you can use **secret sharing** or HSM/vendor-supported quorum mechanisms. For example, a k-of-n scheme permits recovery once enough protected shares assemble, reducing single-person dependency.

However:

- Never split an AES key by slicing byte chunks and calling it Shamir Secret Sharing; use standard mathematical schemes and vetted implementations with error handling.
- Shares remain secrets; protect, number, and track custodians, avoid placing two custodians in the same failure domain, and maintain share-leak procedures.
- Test actual recovery in a controlled environment. Quorum does not replace auditing or approvals.
- If enough shares are lost below the recovery threshold, data can be **lost permanently**.

### 6.4. Preventing Operational Leaks

Never print `SecretKey.getEncoded()`, private keys, plaintext recovery passwords, or key bytes into CI logs, APM, exception text, crash dumps, or support tickets. Restrict heap dumps/snapshots on key-handling hosts. Calling Java `Arrays.fill` on one array only clears **that array**, with no guarantee every copy disappeared from the JVM/provider/OS.

## 7. RTO, RPO, and Recovery Drills

- **RTO (Recovery Time Objective):** maximum acceptable downtime for encryption/decryption/verification capabilities.
- **RPO (Recovery Point Objective):** acceptable data/state loss, such as metadata records or key version mappings. For **non-reconstructible** key material, losing **one required key version** can render matching data permanently unrecoverable, even if data records were backed up.
- **Recovery rehearsal:** run periodic drills verifying not just “the backup file exists,” but that **the keystore opens and real sample data decrypts** under the right key version in an isolated environment.

A thorough recovery test measures milestones: fetching the backup, verifying integrity, obtaining approvals, initializing KMS/HSM, loading keys, restoring metadata/data, decrypting/verifying both old and new records, running limited traffic, and completing audits. Compare actual timings against RTO/RPO.

**Never copy production keys onto a developer laptop just to test backups.** Use an isolated DR environment, restricted roles, or test keys; for production keys, run only approved, controlled, audited recovery procedures.

## 8. Recovery Workflow When a Key Is Lost But Compromise Is NOT Suspected

### Step 1 — Classify and Scope the Incident

Determine whether this is **loss of access** (KMS down, accidentally revoked IAM), **keystore corruption**, **accidental key-version deletion**, or **loss of all copies**. Check telemetry, rotation logs, IAM changes, keyId/versions, and vendor status notices. **Never create a new key under the same alias expecting it to decrypt old ciphertexts.**

If signs of unauthorized access appear or trustworthiness is unclear, switch to the **suspected compromise** workflow instead of blindly restoring an old key into production.

### Step 2 — Validate a Trusted Backup Source

Fetch the signed/authenticated manifest and the snapshot matching the data version; check storage provenance, read permissions, and integrity. Identify the **exact secrets** needing recovery (DEK, KEK, private decryption key, metadata).

For non-exportable HSM/KMS keys, use only official supported backup/replication/restore features; **never try dumping raw keys** to bypass protection.

### Step 3 — Controlled Restoration

Restore inside a clean environment with policy-compliant approvals. Enforce strict secret handling, log zero key material, bind the exact alias/key version, prevent tenant mix-ups, and restore IAM controls. If the old key has passed its period for **creating** new protection, allow only authorized **read/decrypt** usage.

### Step 4 — Application Verification

Use known test records to verify the restored key works: AEAD decryption succeeds **and passes tag verification**, records from both before and after rotation open, no wrong algorithm/IV/AAD is used, and all key versions resolve. Review permissions and audits, then gradually restore traffic.

### Step 5 — Root-Cause Remediation

If failure stemmed from IAM/policy gaps, premature key-deletion automation, missing key-metadata snapshots, or insufficient DR regions, update procedures and re-test. Do not stop at fixing a single restore ticket.

**When no trusted copy remains:** if ciphertext was protected by a strong random key that was destroyed with no recovery path, no Java API can “guess the key back.” Look for *pre-existing* recovery paths like redundant wrappedDEKs or standby KMS regions; if none exist, report the impact and recover data from **other valid plaintext sources**, if available. Never downgrade cryptography or present corrupted data as recovered data.

## 9. When a Key Is Compromised or SUSPECTED Compromised: Incident Response Is Completely Different

**Principle:** when a private/secret key may have been copied by an attacker, changing the file password or disabling an alias **does not recall the exposed key bytes**. The attacker may already hold the key, ciphertexts, tags, or older backups. Assess impact across both current and historical data.

### 9.1. Detection, Activation, and Evidence Preservation

Indicators: anomalous key exports, keystore files in repos/public buckets, KMS decrypt/sign calls from unfamiliar origins, private keys in CI logs, compromised cloud credentials, unauthorized backup downloads, or certificates/signing tokens appearing externally.

When suspected:

1. Activate incident response, naming an **incident commander** alongside Security, SRE, application, compliance/legal, and data owner teams.
2. **Immediately restrict key usage**: pause non-essential sign/decrypt endpoints, revoke stolen credentials, isolate workloads, and tighten KMS permissions. Sequence steps carefully considering availability for critical systems.
3. Preserve logs, access trails, backup versions, KMS audits, and configs for investigation; never delay containment just to gather more evidence.
4. Document **suspected start and end timestamps**, affected services/tenants/key versions, and which parties could have read or modified data.

### 9.2. Create New Keys in a Clean Trust Domain

Generate **fresh, independent key material**, preferably in an uncompromised KMS/HSM/trust zone—never just rename a file or swap an `alias`. If the control plane, hosts, or IAM were compromised, remediate the root cause and credentials before or alongside introducing new keys; otherwise the attacker can steal the new keys immediately.

Update writers/services to **stop using the compromised key for new protection**. Maintain legacy read/decrypt access (only if genuinely needed for data recovery and approved) inside an isolated environment with a tight deadline, then downgrade/destroy on schedule.

### 9.3. Handling Assets Protected by the Compromised Key

| Compromised Key | Potential Impact | Typical Measures Needed |
| --- | --- | --- |
| Data-encrypting **DEK** | Attacker can read captured ciphertexts and forge ciphertexts/tags if parameters are known | Generate a **new DEK**, re-encrypt data requiring protection with fresh nonces, assess previously read/modified data |
| Wrapping **KEK** | Attacker can unwrap accessible wrappedDEKs, including in older backups | Rotate KEK; **rewrap** still-trusted DEKs; if old KEK + old wrappedDEKs may have been exposed, treat DEKs as compromised and **re-encrypt payloads** |
| **Private signing key** | Attacker can forge signatures on data/tokens/software | Stop signing, revoke certs/trust, issue new keys, audit and potentially re-issue artifacts, invalidate tokens/allowlists per policy |
| **HMAC/API shared secret** | Attacker can forge valid tags/tokens | Rotate/revoke shared secret, update all participants, reject old tokens/tags within the exposure window |
| **TLS private key** | Risk of endpoint impersonation and impact on certain sessions depending on protocol/cipher suite | Replace key pair/cert, revoke cert as appropriate, update trust/deployments; assess historical sessions based on forward secrecy |
| **Root/master key** | Multiple key hierarchy branches may be exposed | Trigger high-severity DR/IR, enumerate all child keys and data, replace along dependency graph, narrow blast radius, coordinate with vendor |

**You cannot “make already-read data secret again.”** Re-encrypting protects **new** copies once the old key is retired, yet does not erase old ciphertexts or plaintext the attacker already extracted. Retention and access to older snapshots are part of the impact assessment.

### 9.4. Rewrap Is NOT Always Equivalent to Re-Encrypt

Cases to distinguish:

- **Routine KEK rotation, no sign of leak:** a still-secret DEK can be rewrapped under the new KEK. Payload ciphertext stays unchanged; migration time is usually low.
- **KEK compromised, yet old DEKs and wrappedDEKs definitely never reached the attacker under the threat model:** rewrapping may form part of the response, though evidence and old backups must be audited—this is hard to assert with certainty.
- **DEK compromised, or KEK + wrappedDEKs that an attacker could hold:** replacing the KEK **does not restore confidentiality** of the old DEK. You need a **new DEK** and data re-encryption; historical copied data may still be readable with the old key.
- **Signing private key compromised:** there is no “rewrap signatures.” Issued signatures must be evaluated by timestamp, signing workflow, timestamp/evidence, and trust policy; issuing a new key does not erase forged signatures from the old period.

### 9.5. Revocation, Notification, and Closing Verification

- For certificates, publish/check revocation via CRL/OCSP per applicable PKI; note clients may cache, ignore, or enforce different policies. Merely “revoking the cert” does not guarantee all verifiers stop trusting the key instantly.
- For signed JWTs/tokens or HMACs, assess issued tokens, TTLs, `keyId`, sessions, caches, and verifiers still accepting the old key. Rotating `kid` or the signing key does not invalidate old tokens while verifiers still trust the old public key/secret.
- For data potentially read or altered, assess contractual, legal, and regulatory notification duties. Never declare a confirmed data breach from a single anomalous log; classify carefully and state confidence levels clearly.
- Re-test permissions, monitor anomalous activity after rotation, reconcile migrated record counts, AEAD tags, and readability, audit old snapshots, schedule old-key destruction, and archive audit evidence.
- Afterward, run a postmortem and update export/backup permissions, IAM, DR, key retention policies, logging, automation, and drills.

## 10. Java 17+: Example of PKCS#12 Backup and Restore of an AES `SecretKey`

Java provides `java.security.KeyStore` to manage key/certificate entries. With a JDK/provider supporting **PKCS#12** `SecretKeyEntry`, you can store an AES key inside a password-protected keystore, serialize it, and reload it.

**This is a technical demo, not a production backup solution:** the key is randomly generated, fixed passwords in code are **illustrative only**, the backup stays in process memory, and there are no immutable/offline backups, trust models, HSM/KMS, quorum, auditing, or DR. Never use these demo passwords or in-memory pattern verbatim in real applications.

The program runs four checks:

1. Generate an AES key and encrypt a simple string with AES-GCM.
2. Store the key in `KeyStore.SecretKeyEntry` under alias `dek-v1` with `KeyStore.PasswordProtection`, and serialize the PKCS#12 keystore to bytes.
3. Initialize a **new KeyStore from the backup bytes**, retrieve the key with the entry password, and decrypt the ciphertext. Recovery still requires the **IV**, ciphertext, and tag from the data record; the key alone is not enough.
4. Test a wrong entry password and a different AES key to verify restore/decrypt fail.

Create `KeyBackupRestoreDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.UnrecoverableKeyException;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyBackupRestoreDemo {
    private static byte[] encrypt(SecretKey key, byte[] iv, byte[] plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(SecretKey key, byte[] iv, byte[] encrypted)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        // Demo-only passwords; never hardcode actual recovery credentials.
        char[] storePassword = {'d','e','m','o','-','s','t','o','r','e','-','p','a','s','s'};
        char[] entryPassword = {'d','e','m','o','-','e','n','t','r','y','-','p','a','s','s'};
        byte[] backupBytes = null;
        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(128);
            SecretKey originalKey = generator.generateKey();
            byte[] iv = new byte[12];
            new SecureRandom().nextBytes(iv);
            byte[] plaintext = "ho-so-du-lieu-v1"
                    .getBytes(StandardCharsets.UTF_8);
            byte[] ciphertextAndTag = encrypt(originalKey, iv, plaintext);

            KeyStore backupStore = KeyStore.getInstance("PKCS12");
            backupStore.load(null, storePassword);
            KeyStore.PasswordProtection protection =
                    new KeyStore.PasswordProtection(entryPassword);
            try {
                backupStore.setEntry("dek-v1",
                        new KeyStore.SecretKeyEntry(originalKey), protection);
            } finally {
                protection.destroy();
            }

            ByteArrayOutputStream sink = new ByteArrayOutputStream();
            backupStore.store(sink, storePassword);
            backupBytes = sink.toByteArray();

            KeyStore restoredStore = KeyStore.getInstance("PKCS12");
            restoredStore.load(new ByteArrayInputStream(backupBytes), storePassword);
            SecretKey recoveredKey =
                    (SecretKey) restoredStore.getKey("dek-v1", entryPassword);
            if (recoveredKey == null) {
                throw new IllegalStateException("Missing key alias");
            }
            System.out.println("Recovered alias exists: " +
                    restoredStore.containsAlias("dek-v1"));
            System.out.println("Restored decrypts payload: " +
                    Arrays.equals(plaintext,
                            decrypt(recoveredKey, iv, ciphertextAndTag)));

            boolean rejectedWrongEntryPassword = false;
            char[] wrongPassword = {'w','r','o','n','g'};
            try {
                restoredStore.getKey("dek-v1", wrongPassword);
            } catch (UnrecoverableKeyException expected) {
                rejectedWrongEntryPassword = true;
            } finally {
                Arrays.fill(wrongPassword, '\0');
            }
            System.out.println("Wrong entry password rejected: " +
                    rejectedWrongEntryPassword);

            SecretKey unrelatedKey = generator.generateKey();
            boolean rejectedWrongKey = false;
            try {
                decrypt(unrelatedKey, iv, ciphertextAndTag);
            } catch (AEADBadTagException expected) {
                rejectedWrongKey = true;
            }
            System.out.println("Unrelated key decrypt rejected: " +
                    rejectedWrongKey);
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
            if (backupBytes != null) Arrays.fill(backupBytes, (byte) 0);
        }
    }
}
```

Compile and run (Java 17+ with a provider supporting PKCS#12 `SecretKeyEntry` and AES-GCM):

```bash
javac KeyBackupRestoreDemo.java
java KeyBackupRestoreDemo
```

Verified stdout on OpenJDK/test provider:

```text
Recovered alias exists: true
Restored decrypts payload: true
Wrong entry password rejected: true
Unrelated key decrypt rejected: true
```

### 10.1. Key Takeaways After the Example

- `KeyStore.getInstance("PKCS12")` selects the **keystore type**; `SecretKeyEntry` holds the key, and `PasswordProtection` represents entry protection credentials. `KeyStore.store` serializes the backup; `load` and `getKey` recover the key by alias.
- `storePassword` and `entryPassword` serve two **roles**: keystore integrity/loading and unlocking individual entries; providers may impose different password constraints and entry-type support. Never assume running on one provider guarantees identical behavior across all PKCS#12 providers.
- PKCS#12 is a **container format protecting key data**, not automatically a full DR process with IAM, auditing, anti-ransomware, retention, multi-region, and escrow. The demo passwords are very weak; **never use them in production**.
- `AES/GCM/NoPadding` authenticates ciphertext/tag: decrypting with an unrelated key fails with `AEADBadTagException` in the example. Never ignore tag verification errors during decryption.
- The 12-byte `IV` is for **one encryption in the demo**. Under GCM, every encryption with the same key needs a unique IV/nonce per policy; never reuse an IV for a new payload.
- `PasswordProtection.destroy()` clears the password copy inside that protection object. `Arrays.fill` in `finally` clears caller-owned arrays, yet **does not guarantee all copies are wiped from `KeyStore`, `ByteArrayOutputStream`, providers, JIT/GC, or RAM**.
- `restoredStore.getKey` requires alias and entry password; production also needs the right key version, authorization, and trust in the backup source. If an alias is missing or wrong, **never generate a random AES key as a replacement and call it a restore**.
- If your KMS/HSM forbids export, this PKCS#12 example **does not apply directly**. Use official vendor backup/DR mechanisms, and never weaken non-exportable policies just to run a demo.

### 10.2. What the Example Does NOT Prove

- No backup bytes are written outside the process, so it **does not** prove survival after host loss.
- It does not test multi-region restores, independent password escrow, compatible snapshots, IAM, or audit reconciliation.
- The program holds `originalKey` and `restoredStore` in the same process; it exercises the **serialize/load/getKey path**, not losing all original memory and restoring on a clean host.
- It does not claim a backup container resists brute force if the password is weak; never use demo passwords in real code.
- It does not authenticate who is allowed to restore, manage rotation, or run key-compromise incident response.
- It does not guarantee wiping key/backup bytes from every place in the JVM and OS.

## 11. Short Runbook for a Production Recovery Incident

Suppose a system stores `AES-GCM` data with DEKs wrapped by a KMS KEK:

### A. When the Service Loses Decryption Access But No Compromise Is Suspected

1. Open an incident, identify keyId/version, tenant, record counts, and exact errors; keep data and metadata intact.
2. Check whether a KMS replica, IAM permissions, or surviving key version can be used. **Never** generate a brand-new key under the old version label.
3. Obtain a valid integrity-checked backup with approvals, and restore into a clean zone using authorized procedures.
4. Test AEAD decryption across sample records from multiple rotation periods; verify tags, AAD, IVs, and expected plaintext/non-sensitive hashes.
5. Restore traffic under observation, record audits, fix root cause, and re-drill.

### B. When Key Compromise Is Suspected

1. Block unauthorized exports/usage, isolate the leak source, preserve evidence, and determine blast radius and all backup copies.
2. Create new keys inside a controlled trust domain; rotate related IAM/credentials.
3. Stop **new encrypt/sign** calls under the suspected key. Handle data currently protected by that key according to DEK/KEK/signing key classification.
4. For data at risk of being read from old ciphertexts, re-encrypt under a new DEK where feasible; for routine KEK replacement, rewrapping may suffice if DEKs remained secure per assessment.
5. Revoke/deprecate certificates/verification keys, API tokens, shared secrets, trust pins, and caches per real impact.
6. Test the new version, verify full migration, document historical data limitations and notification duties.
7. Retire/destroy the old key per retention/legacy-read needs **and** compromise policy; never keep an exposed key active by default just because “it might be needed later.”

### C. When Only Ciphertext Remains and All Required Keys Are Lost

1. Check pre-designed backup/escrow/wrappedDEK/re-derivation paths.
2. If no valid cryptographic recovery path exists, record that decryption **is impossible** with a new key; evaluate alternate authoritative plaintext sources (if any) and notification/business-continuity workflows.
3. Review DR design, redundancy, key-version lifecycles, and crypto-erasure policies to prevent recurrence.

## 12. Common Mistakes in Backup and Recovery

| Mistake | Why It Is Dangerous | Remedy |
| --- | --- | --- |
| Backing up only ciphertext with no KEK/DEK recovery path | You have data you cannot decrypt | Design full key hierarchy and DR bootstrap |
| Keeping only the “current key” and deleting all old versions | Data encrypted before rotation becomes unreadable | Retain key versions needed for recipient-use per policy |
| Backing up a keystore while losing password/alias/metadata | Cannot load/`getKey` or picks wrong key | Separate credential escrow, inventory, and restore drills |
| Storing key backups on the same host/cloud account as primary | One deletion or ransomware attack wipes both | Separate fault domains, deletion permissions, immutable/isolated copies |
| Putting raw private keys in repos/CI/logs | Uncontrolled secret sprawl | Forbid unnecessary exports; rotate/IR if exposed |
| Renaming an alias and thinking the key rotated | Underlying secret bytes did not change | Generate new **key material** and update writers/policies |
| KEK leaked, yet only rewrapping while ignoring old backups | Attackers may still unwrap old wrappedDEKs | Assess history; re-encrypt under new DEKs where needed |
| DEK leaked, yet only rotating the KEK | Data remains decryptable with the leaked DEK | Re-encrypt payloads under a new DEK |
| Losing a signing private key and restoring outside policy | Widens signature-forgery surface and may violate policy | Prefer generating a new key pair; keep old public cert for verification |
| Restoring from backup into a still-compromised prod environment | Attackers steal the freshly restored key too | Verify trust, clean environment, and fix permissions first |
| Checking only an unkeyed checksum of a backup file | Someone modifying both file and checksum still passes | Use keyed integrity/authenticity or equivalent controls |
| Generating a new AES key and overwriting the lost key's alias | Old ciphertexts fail to decrypt and mappings corrupt | Keep keyId/version immutable; create a proper new alias/version |
| Treating hardcoded demo passwords as safe | P12 file is easy to brute-force or leaked in code | Generate and store real credentials per policy |
| Never running recovery drills | Backups exist on paper yet fail under pressure | Test against real backups, measure RTO/RPO, audit periodically |
| Failing to update verifiers or token caches after compromise | Exposed key stays trusted for signing/auth | Revoke/distribute replacement trust and check every consumer |
| Reusing AES-GCM nonces after restore/counter rollback | Can break AEAD security on `(key, nonce)` reuse | Manage uniqueness across versions/replicas; if uncertain, rotate the key |

**Watch out during database rollbacks:** if the system allocates AES-GCM nonces via a counter, restoring an old snapshot can revert the counter to previously used values, causing **(key, nonce) reuse** on new data. Design rollback-safe/multi-writer nonce allocators, or **rotate the encryption key** before emitting new records per policy. Never treat backup restoration as solely “having the right key.”

## 13. Operations Checklist and Practice Exercises

### Before an Incident

- [ ] Inventory lists `keyId`/version, algorithm, key owner, usage (`encrypt`/`decrypt`/`sign`/`verify`/`wrap`), dependent data, and storage location.
- [ ] Policy clearly states which keys may be backed up, which are non-exportable, and which keep only public certificates; retention matches usage periods.
- [ ] Key backups are encrypted/authenticated, with independent restore permissions, proper dual control, auditing, and accidental-deletion/ransomware protection.
- [ ] Metadata covers IV/tag/AAD/KDF params/wrappedDEK/KEK version; database and key snapshots restore consistently together.
- [ ] Recovery plan covers KMS/HSM/region/account unavailability, including credential escrow and cycle-free bootstrap.
- [ ] RTO/RPO targets are defined and restore rehearsals run in an isolated DR environment.
- [ ] **Separate** playbooks exist for key loss, key unavailability, key compromise, and total key-backup loss.
- [ ] Strategies cover rotate/rewrap/re-encrypt, `keyId` migration, token/certificate revocation, and forensic audit logs.

### After Handling an Incident

- [ ] Verified AEAD tags/signatures across multiple key versions and tenants, not just one sample object.
- [ ] Verified writers no longer use the old key for new data if the key expired or was compromised.
- [ ] Identified remaining legacy copies (backups/snapshots/caches/replicas) and exposure risk of key material.
- [ ] Closed incident, audited restore actions, and recorded lessons on permissions, automation, and monitoring.

### Self-Check

1. If ciphertext and IV are intact but the **DEK is permanently lost**, why does generating a new AES key not help decrypt?
2. Why should backing up a **private signing key** not be treated the same as backing up a **DEK** for decrypting old data?
3. Distinguish **restore**, **rotate**, **rewrap**, **re-encrypt**, **revoke**, and **destroy** using an AES-GCM + KEK example.
4. When KEK-v1 leaks, is rotating to KEK-v2 and rewrapping all DEKs enough to stop an attacker who already holds `wrappedDEK-v1`? What else is needed?
5. If you only have `backup.p12` without store/entry passwords and key mappings, which recovery prerequisites are missing?
6. When keys are inaccessible due to a KMS outage with no signs of leak, why do you not necessarily have to re-encrypt the entire database?
7. Why can **restoring keys into production while malware persists** worsen the incident?
8. After restoring from an old snapshot, why must AES-GCM nonce counters be verified before encrypting new data?
9. Is a digital signature created before a private key was suspected compromised still trustworthy? Which evidence, timestamps, certificate revocations, and policies are needed?
10. How do you verify a backup succeeded in the sense of **being restorable and using the right key**, rather than merely “the file exists”?

**Exercise A:** run `KeyBackupRestoreDemo.java`, then try changing alias `dek-v1` in `getKey` or supplying a wrong entry password; diagnose from the thrown exception. Use **demo** keys and passwords only.

**Exercise B:** simulate records with `keyVersion=v1` and `v2`; write a mock migration reading/decrypting v1 data and writing new records under v2 without deleting v1 while valid dependent records remain.

**Exercise C:** create a tabletop drill table comparing “lost KEK, no leak suspected” vs. “compromised KEK + wrapped DEKs.” List trusted sources, blast radius, containment steps, objects needing rewrap/re-encrypt, verification tests, and return-to-service criteria.

**Exercise D:** rehearse a metadata backup missing `iv` or having the wrong `keyVersion`, plus a nonce-counter rollback. Document why restoring the secret key alone is insufficient and specify the strategy preventing `(key, nonce)` reuse.

## 14. Official References

- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key material lifecycle, backups, archives, recovery, compromised keys, and usage-period distinctions.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): `KeyStore.getInstance`, `load`, `setEntry`, `store`, `getKey`, and entry types.
- [Java SE 17 — KeyStore.SecretKeyEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.SecretKeyEntry.html): entry holding a `SecretKey`.
- [Java SE 17 — KeyStore.PasswordProtection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.PasswordProtection.html): entry protection credentials, password copying, and `destroy`.
- [Java SE 17 — KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): generating random AES keys via a provider.
- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): AEAD, `AES/GCM/NoPadding`, tag verification, and `AEADBadTagException`.
- [NIST SP 800-38D — GCM](https://csrc.nist.gov/pubs/sp/800/38/d/final): principles for IV/nonces and GCM encryption/authentication.
