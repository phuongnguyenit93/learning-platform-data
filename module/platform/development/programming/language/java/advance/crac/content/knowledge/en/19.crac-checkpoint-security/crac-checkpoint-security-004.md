# Encrypting images at rest and in transit

A Java application checkpoint can contain more sensitive data than a configuration file or a build artifact. In memory at checkpoint time, there may be access tokens, session credentials, private keys, user information, in-flight requests, cache data, SQL statements, message payloads, and internal library state. If a checkpoint image is read without authorization, whoever obtains the image may extract data or restore a process with pre-prepared state.

CRaC (Coordinated Restore at Checkpoint) saves and restores process state, yet it should not be assumed that every JDK or platform automatically encrypts checkpoint artifacts. Encryption mechanisms must be determined according to the runtime, operating system, storage, packaging pipeline, and image transport method. A checkpoint may consist of multiple files, metadata, and auxiliary files; all sensitive components need to fall within the protection scope.

Protecting checkpoint images requires addressing two distinct stages: **encryption at rest** so unauthorized parties cannot read artifacts on disk, object storage, or backups; and **encryption in transit** to prevent eavesdropping or tampering with data on the wire. At the same time, the application needs to manage keys, authenticate integrity, control restore permissions, and avoid leaving temporary plaintext copies behind.

## 1. Why do checkpoint artifacts need encryption?

A checkpoint can save the memory state of a running process. This is useful for shortening startup, yet it also expands the scope of data needing protection.

An image may contain:

- Access tokens, session tokens, refresh tokens, or temporary credentials loaded onto the heap.
- Private keys, certificate material, or data used for signing requests.
- User information, application sessions, and business data currently being processed.
- Cache contents, internal message queues, request bodies, or response buffers.
- Connection strings, endpoints, tenant IDs, and infrastructure metadata.
- Native library data or off-heap memory included in the checkpoint by the runtime.
- Thread state, executor state, transaction context, or resource handles depending on the runtime.

Not every checkpoint contains all of the above data. The exact scope depends on the application, runtime, excluded resources, and checkpoint mechanism. However, a safe assessment should start from the assumption that the artifact may contain sensitive process data.

If the artifact is stored in object storage, a registry, a shared filesystem, a backup repository, or a CI artifact store, anyone granted erroneous read permissions could access data in the image. If the artifact traverses an unencrypted internal network, anyone able to observe traffic could capture a copy. If the artifact is altered, the restored process could start from an untrusted state.

Encryption reduces risk when data is accessed in storage or in transit. It does not replace access permissions, authentication, auditing, key management, and target host controls.

## 2. Scope of protection: the entire checkpoint package

Do not encrypt only a single file and overlook the remaining components. Depending on the runtime and packaging approach, a checkpoint can be a directory containing multiple memory page files, metadata, file descriptor state, mapping information, or auxiliary data. A deployment pipeline may additionally generate archives, manifests, checksums, and logs.

Components to include in the inventory:

| Component | Potentially exposed data | Protection method |
|---|---|---|
| Memory/image files | Heap, native state, and application data | Encrypt the entire artifact or use encrypted storage |
| Metadata/manifest | Filenames, versions, paths, configuration, and identity | Encrypt or sign/authenticate; restrict read permissions |
| Archive/package | Checkpoint contents after bundling files | Encrypt the complete package |
| Temporary files | Extracted copies or intermediate plaintext copies | Use protected storage and clean up |
| Backup/version history | Older checkpoint versions | Apply the same encryption and retention policy |
| Transfer logs | URLs, object keys, credentials, or environment details | Do not record secrets; restrict permissions and retention duration |
| Checksum/signature files | Artifact verification metadata | Protect authenticity, avoid replacing alongside the artifact |

If the runtime creates a checkpoint as a directory, wait for the checkpoint operation to complete before packaging or encrypting. Do not read, compress, encrypt, or upload files while the runtime is still writing them. A package created from an incomplete set of files may fail to restore or be inconsistent.

Preserve the exact structure and metadata needed for restore: filenames, permissions, owners, symbolic links, ordering, or relationships between components as required by the runtime. Do not arbitrarily alter checkpoint contents or structure for encryption convenience without understanding the runtime's format.

## 3. Encryption at rest and encryption in transit

These two layers protect two different boundaries.

**Encryption at rest** protects data while the artifact resides on disk, volumes, object storage, backups, or storage media. Common options include volume/filesystem encryption, object storage server-side encryption, and client-side encryption prior to upload.

**Encryption in transit** protects data as the artifact moves from where the checkpoint is created to storage, or from storage to the restore machine. Common options include TLS/HTTPS, mutual TLS, SSH/SFTP, or a properly configured encrypted private channel.

~~~text
Checkpoint creation machine
  |
  | 1. Checkpoint completes
  v
Checkpoint package
  |
  | 2. Encrypt with data key
  v
Ciphertext + authenticated manifest
  |
  | 3. Transfer over TLS
  v
Storage / backup repository
  |
  | 4. Read ciphertext over TLS
  v
Restore machine
  |
  | 5. Verify manifest, decrypt with granted permissions
  v
Plaintext checkpoint in protected region
  |
  v
CRaC restore
~~~

TLS does not replace encryption at rest because TLS terminates when data is written to storage. Volume encryption does not replace TLS because data can still be read in transit if sent over an insecure channel. A system typically needs both.

## 4. Encryption-at-rest models

### 4.1. Disk or volume encryption

The filesystem or block device is encrypted, for example using the operating system's or storage platform's volume encryption mechanism. Once the volume is mounted and the application has access permissions, data typically appears as plaintext to authorized processes.

Advantages:

- Can protect many files simultaneously without changing the checkpoint format.
- Integrates at the infrastructure layer with minimal application code changes.
- Can be applied to staging directories, checkpoint directories, and volumes holding decrypted copies.

Limitations:

- Does not protect against processes or administrators with permission to read data once the volume is unlocked.
- Does not automatically protect copies replicated to other storage if the destination is unencrypted.
- Backups, volume snapshots, and replica storage require separate policies.
- Volume unlock keys and mount permissions must be managed.

Volume encryption is appropriate when operations control the storage infrastructure and want to protect data if a device or volume is accessed unexpectedly. It is not end-to-end artifact encryption.

### 4.2. Server-side encryption

Object storage or a storage service can encrypt data as it is written to media. The provider manages encryption operations and may use platform-managed keys or customer-controlled keys in KMS.

Advantages:

- Easy integration with object storage.
- Can encrypt object versions and replicas as well if configured properly.
- KMS policies and audit logs support access control.
- The application does not necessarily have to handle ciphertext formatting itself.

Must verify:

- Does the bucket/container enforce encryption on every object?
- Are older objects or copies encrypted?
- Do backups, replication, and versioning preserve the same policy?
- Who is permitted to request decryption when reading objects?
- Does the key policy restrict by workload identity, environment, or artifact prefix?
- Does the service audit key usage events?

Server-side encryption protects storage media under the provider's trust model. Users or services with permission to read objects and permission to use the key can still receive plaintext. If protection is needed against the storage service itself or against principals permitted to read objects without decryption keys, consider client-side encryption.

### 4.3. Client-side encryption

Client-side encryption encrypts the artifact before sending it to storage. Storage receives only ciphertext; decryption keys are managed separately via KMS/HSM or a dedicated key system.

Advantages:

- Ciphertext is produced before leaving the application's trust boundary.
- Storage never needs to see plaintext.
- The same encryption format can be used across multiple storage types.
- Object read permission does not automatically imply decryption permission.

In return, the application or pipeline must manage formatting, data keys, nonces, authentication tags, manifests, rotation, and restore. If keys are lost, artifacts may become unusable. Both key backups and disaster recovery procedures need testing.

### 4.4. Combining multiple layers

A common configuration uses client-side encryption for the artifact, TLS in transit, and server-side encryption or volume encryption in storage. These layers protect different boundaries.

Do not confuse multiple layers of encryption with arbitrary multiple keys. Define the threat model and owner of each key. Using too many layers without clear rotation and recovery policies can make restores difficult to operate or leave data undecryptable when needed.

## 5. Encryption in transit with TLS

When uploading or downloading checkpoints over HTTP, HTTPS/TLS provides encryption and transport channel authentication. For new services, prefer TLS 1.3 when components support it; TLS 1.2 with a secure cipher suite configuration remains widely used. Follow the organization's and platform's security policies.

Ensure:

- Clients verify the server's certificate chain and hostname.
- Do not disable certificate validation to work around environment errors.
- Use an appropriate CA trust store and maintain a certificate update plan.
- Use mutual TLS when authenticating both client and server at the transport layer is required.
- Keep client credentials in a secret manager or identity provider, never embedded in the checkpoint package.
- Protect every hop if TLS terminates at a reverse proxy or gateway.
- Never send artifacts over plaintext HTTP.
- Never log Authorization headers, private keys, session tokens, or full signed URLs.

If uploads pass through a proxy, gateway, or service mesh, identify where TLS terminates. The channel from client to proxy may be encrypted while the hop from proxy to storage is not. Every hop needs to be part of the protection model.

TLS does not authenticate artifact contents after storage. Once an object is stored, an attacker could replace the object with another file if they have storage write permissions. Therefore, artifact integrity and provenance must be verified using authenticated encryption, digital signatures, or a MAC over the manifest.

## 6. Integrity verification: encryption alone is not enough

Unauthenticated encryption can leave open the possibility of modifying ciphertext or metadata without the system properly detecting it. With checkpoints, even a small change in a memory file or metadata can cause restore to fail or restore manipulated state.

Use authenticated encryption with associated data (AEAD), for example:

- AES-GCM.
- ChaCha20-Poly1305.

AEAD provides confidentiality and authentication for ciphertext. It also allows authenticating unencrypted metadata via Associated Authenticated Data (AAD), such as artifact ID, normalized file path, format version, or chunk index.

During decryption, if the ciphertext, tag, or AAD does not match, the operation must fail. Never ignore the authentication tag or proceed with restoring unverified data.

A checksum like SHA-256 is useful for detecting transmission errors or accidental corruption. However, if an attacker can replace both the file and the checksum, a checksum does not prove provenance. To authenticate against attackers, use AEAD, a MAC with a secret key, or a digital signature with a trusted public key.

## 7. Envelope encryption: encrypting data with a DEK and protecting the DEK with KMS

A common pattern is envelope encryption:

- **Data Encryption Key (DEK):** Data key used to encrypt the checkpoint.
- **Key Encryption Key (KEK):** Key managed in KMS/HSM, used to wrap or encrypt the DEK.
- **Wrapped DEK:** DEK encrypted with the KEK; can be stored alongside the ciphertext artifact.
- **KMS key reference:** Identifier of the key in KMS, not a decryption secret.

~~~text
                 KMS / HSM
              KEK (non-exportable)
                    |
                    | wrap DEK
                    v
Checkpoint --> random DEK --> encrypt artifact with AEAD
                    |
                    +---- Wrapped DEK stored in manifest
                    |
                    v
             Ciphertext artifact
~~~

Artifact creation workflow:

1. Authenticate the identity of the checkpoint creation pipeline.
2. Request KMS to generate a new DEK or generate a DEK on the client according to policy.
3. Use the plaintext DEK to encrypt the artifact.
4. Request KMS to wrap/encrypt the DEK with the KEK.
5. Store the wrapped DEK, key ID, algorithm, nonce, and required metadata in an authenticated manifest.
6. Clear references to the plaintext DEK when no longer needed; never write the DEK to logs or unencrypted files.

Restore workflow:

1. Authenticate the identity of the workload permitted to restore.
2. Read the manifest and verify its signature/MAC or authenticated metadata.
3. Request KMS to unwrap the DEK using appropriate decrypt permissions.
4. Authenticate and decrypt each file/chunk.
5. Place plaintext into the protected staging area only after verification succeeds.

KMS does not need to export the KEK. KMS holds the KEK and only performs wrap/unwrap operations according to policy. This allows storage access permissions and key usage permissions to be separated.

## 8. Selecting algorithms and managing nonces

Use standardized cryptographic algorithms and maintained cryptographic libraries. For Java applications, AES-GCM is a common AEAD choice if supported by the JDK/provider and organizational policy. ChaCha20-Poly1305 is also an appropriate AEAD choice on supported platforms.

Key points to remember:

- Use a sufficiently strong key, typically AES-256 per policy.
- With AES-GCM, the nonce is typically 96 bits long and the authentication tag is typically 128 bits.
- Never reuse the same nonce with the same key in AES-GCM.
- Each artifact should have its own DEK; each re-encryption of an artifact needs a new nonce or a new DEK by design.
- With chunked encryption, every chunk must have a unique nonce under the same DEK.
- Do not design your own algorithm, mode, or combination of encryption and checksums.
- Do not use ECB or homegrown encryption based on XOR.

A nonce does not need to be kept secret, but must be stored for decryption. For a single file encrypted with a dedicated DEK, a 96-bit random nonce can be generated using SecureRandom. For very large files split into many chunks, design non-repeating nonces, such as a unique artifact prefix combined with a monotonically increasing chunk counter. When retrying or re-encrypting, ensure nonces are never reused with the same DEK for different plaintext.

## 9. Java AES-GCM example for a small payload

The following snippet illustrates JCA/JCE APIs to encrypt and decrypt a small payload using AES-GCM. In a real system, the DEK must be issued or protected by KMS; the local key generation example is solely to illustrate the algorithm and is not how production keys should be stored.

~~~java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

public final class AesGcmExample {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public record EncryptedPayload(byte[] nonce, byte[] ciphertext) {}

    public static SecretKey newDemoKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        return generator.generateKey();
    }

    public static EncryptedPayload encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] authenticatedMetadata) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        new SecureRandom().nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(authenticatedMetadata);

        byte[] ciphertext = cipher.doFinal(plaintext);
        return new EncryptedPayload(nonce, ciphertext);
    }

    public static byte[] decrypt(
            SecretKey key,
            EncryptedPayload encrypted,
            byte[] authenticatedMetadata) throws Exception {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, encrypted.nonce()));
        cipher.updateAAD(authenticatedMetadata);

        try {
            return cipher.doFinal(encrypted.ciphertext());
        } catch (AEADBadTagException ex) {
            throw new SecurityException(
                    "Checkpoint payload authentication failed", ex);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newDemoKey();
        byte[] metadata = "artifact=demo;format=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "sample checkpoint payload"
                .getBytes(StandardCharsets.UTF_8);

        EncryptedPayload encrypted = encrypt(key, plaintext, metadata);
        byte[] restored = decrypt(key, encrypted, metadata);

        if (!Arrays.equals(plaintext, restored)) {
            throw new IllegalStateException("Plaintext mismatch");
        }
    }
}
~~~

This is only an example for an in-memory payload. Do not read an entire checkpoint into a byte array because checkpoints can be very large. A real format needs to support streaming or chunked encryption, storing nonces/tags, wrapped DEK, and manifest. If authentication fails, abort restore and treat the artifact as untrusted.

In production, replace the demo key generation function with a KMS generate-data-key workflow or an approved key service. Do not serialize a plaintext SecretKey into the manifest or checkpoint package.

## 10. Encrypting large checkpoints by chunks

Checkpoints can be hundreds of MB or multiple GB in size. Reading the entire artifact into the heap to encrypt increases memory pressure and can result in a larger checkpoint or cause OOM. Use streaming encryption or split files into bounded-size chunks.

A chunk format should store at minimum:

- Artifact ID and format version.
- File ID or normalized relative path.
- Chunk index and total chunk count or final marker information.
- Unique nonce for the chunk.
- Ciphertext and authentication tag.
- Plaintext length or ciphertext length.
- Metadata needed to verify ordering and completeness.

AAD can contain artifact ID, file path, chunk index, and format version. That way, a chunk cannot be swapped between two files or two artifacts without causing authentication to fail.

~~~text
Artifact
  |
  +-- File A
  |     +-- Chunk 0 -> nonce 0 -> AEAD -> ciphertext + tag
  |     +-- Chunk 1 -> nonce 1 -> AEAD -> ciphertext + tag
  |     +-- Chunk 2 -> nonce 2 -> AEAD -> ciphertext + tag
  |
  +-- File B
  |     +-- Chunk 0 -> nonce 3 -> AEAD -> ciphertext + tag
  |     +-- Chunk 1 -> nonce 4 -> AEAD -> ciphertext + tag
  |
  +-- Authenticated manifest
        +-- file list
        +-- chunk counts
        +-- wrapped DEK
        +-- algorithm and format version
~~~

Each chunk needs to be authenticated before that chunk's plaintext data is passed to the next step. During restore, verify the full chunk count, exact order, exact size, and exact file list in the manifest. A manifest with a signature/MAC or authenticated via AAD helps detect deletion, addition, renaming, or swapping of components.

If using multipart upload, do not treat successful upload of individual parts as a complete artifact. Publish a manifest/commit marker only after all files and chunks have been uploaded, verified, and finalized successfully.

## 11. Compressing before encrypting

Checkpoints may contain many compressible memory regions. If compression is needed to reduce size, a common order is:

1. Complete the checkpoint.
2. Package or compress files in the required format.
3. Encrypt the package or individual chunks.
4. Upload ciphertext.

Encryption makes data look nearly random, so compressing after encryption usually does not reduce size significantly. Compressing before encryption is usually more effective.

However, compression can increase CPU and memory usage, affecting checkpoint pipeline duration. Measure compression ratio, CPU time, I/O time, and total time from checkpoint completion until the artifact is ready.

If the threat model includes size side-channels, consider padding or bucket sizing. Ciphertext size can reveal approximate artifact size or changes between versions. Padding increases storage and bandwidth, so apply it only when necessary.

## 12. Protecting manifests and metadata

Manifests typically describe how to restore the artifact. They may contain:

- Artifact ID, build ID, and timestamp.
- JDK vendor/version/build and CRaC runtime metadata.
- File list, sizes, ordering, or checksums.
- Algorithm, nonce format, key ID, and wrapped DEK.
- OS/architecture or platform profile.
- Application version and compatibility configuration.
- Information supporting restore or verification.

Metadata can expose topology, internal paths, runtime versions, or service names. Encrypt the manifest if these fields are sensitive. If the manifest must be read before obtaining decryption keys, keep a minimal, non-sensitive header outside, while placing sensitive metadata inside an encrypted region.

The manifest must be authenticated. One approach is digital signing with a dedicated signing key; another is using a MAC or putting critical fields into the AEAD's AAD. Never arbitrarily reuse the same key for both encryption and signing. Use separate key purposes and separate policies.

The manifest needs to bind artifact ID, file list, chunk counts, sizes, algorithm, and wrapped DEK. If an attacker modifies the manifest to point to a different wrapped key or reorder chunks, the verification step must detect it.

## 13. Hashes, MACs, and digital signatures

These mechanisms serve different purposes:

| Mechanism | Protects | When to use |
|---|---|---|
| Hash (e.g., SHA-256) | Detects modification against a known digest | Checking corruption or comparing contents when the digest is protected separately |
| MAC (e.g., HMAC-SHA-256) | Integrity and authenticity using a shared secret key | Producer and restore service are both authorized to share a secret |
| Digital signature | Integrity and provenance using private/public keys | Producer signs; restore service only needs the public key to verify |
| AEAD tag | Integrity/authenticity of ciphertext and AAD | Authenticating each file/chunk during decryption |

If using hashes, the digest must be protected by a MAC, signature, or trusted channel. A SHA-256 file placed next to ciphertext in the same storage does not defend against an attacker with permission to replace both.

Digital signatures are useful when multiple environments are allowed to restore but not allowed to create artifacts. Only the checkpoint creation pipeline holds the signing private key; restore services hold only the trusted public key. This separates artifact issuance permission from artifact usage permission.

## 14. Key management with KMS or HSM

KMS/HSM helps store and use key material within a dedicated management boundary. The application can ask KMS to generate data keys, wrap DEKs, unwrap DEKs, or sign manifests without exporting the KEK.

A key design should specify:

- Key owner and responsible team.
- Key purpose: encrypt checkpoints, sign manifests, or protect transport.
- Environment: development, staging, production.
- Tenant or application boundary.
- Region and disaster recovery.
- Rotation schedule and retention.
- Principals permitted to encrypt, decrypt, wrap, unwrap, or sign.
- Audit events and alerts for anomalous key usage.

Do not use a single key for all environments if policy requires isolation. Separating keys by environment or tenant reduces blast radius. A dedicated KEK can be used per environment and a fresh DEK for each artifact.

Never put KEKs or plaintext DEKs in source code, images, long-lived environment variables, manifests, or checkpoint files. A KMS key ID is not a secret, yet permission to use the key is an asset that requires control.

## 15. Separating checkpoint creation permissions from restore permissions

The checkpoint creation pipeline and restore workloads may require different permissions.

| Principal | Permissions typically needed | Permissions to restrict |
|---|---|---|
| Checkpoint builder | Generate DEK, encrypt, wrap DEK, upload artifact, sign manifest | Decrypt production artifacts if unnecessary |
| Artifact publisher | Publish encrypted objects and signed manifests | Access plaintext DEK |
| Restore workload | Read artifacts, verify signatures, unwrap DEK, decrypt | Create or overwrite production artifacts |
| Storage operator | Manage lifecycle/replication per policy | Not implicitly granted client-side decryption permission |
| KMS administrator | Manage key policies, rotation, and key state | Does not automatically need checkpoint read permission |
| Auditor | Read audit logs and permitted metadata | No decryption permission needed |

Separating permissions reduces the risk of a single compromised account being able to forge artifacts, overwrite artifacts, and decrypt every checkpoint. Use workload identities and short-lived credentials to grant permissions per job.

The restore role should only decrypt authorized artifacts, for example by key, prefix, environment, application, or tag. Avoid broad policies allowing any service account to unwrap any DEK.

## 16. Rotation and key lifecycle

Rotation needs to be designed before artifacts are stored long-term. A checkpoint created today might need to be restored months later. If the KEK is deleted or the key version is no longer available, the artifact may become undecryptable.

With envelope encryption, the KEK can be rotated by unwrapping the DEK with the old key version and re-wrapping it with the new key version, if KMS and policy support it. That avoids having to decrypt and re-encrypt the entire checkpoint ciphertext.

Principles:

- Record the required key ID and version in the authenticated manifest.
- Retain old key versions while artifacts needing restore still exist.
- Test rewrap and restore procedures after rotation.
- Do not delete keys simply because the application moved to a new version.
- Have an emergency revocation procedure if a key is compromised.
- Maintain key backups or recovery mechanisms according to KMS policy.
- Check whether artifact retention and key retention share the same lifecycle.

Deleting a KEK can render all artifacts protected by that key undecryptable. This can serve as cryptographic erasure, but only when no copies, key versions, backups, and wrapped DEKs have a recovery path. Understand KMS policy thoroughly before using key deletion as a data deletion mechanism.

## 17. Encryption in the upload pipeline

A secure upload pipeline can execute:

1. Wait for the runtime to report the checkpoint is complete.
2. Verify the expected file list and sizes.
3. Package or compress if the format requires.
4. Generate a dedicated DEK for the artifact.
5. Encrypt files/chunks using AEAD.
6. Create a manifest binding files, chunks, nonces, key ID, and version.
7. Sign or authenticate the manifest.
8. Upload ciphertext over TLS.
9. Verify object size, checksum, and upload completion.
10. Publish the manifest/commit marker last.
11. Record audit events and clean up staging plaintext.

Use a separate staging location for each artifact creation run. Avoid directly overwriting an object currently being restored or an already published artifact. If upload is interrupted, incomplete artifacts must be marked unused and cleaned up according to retention policy.

If using multipart upload, persist upload state in a secure location so it can resume by design. However, never reuse nonces under the same DEK for different plaintext when retrying encryption. The simple approach is using a fresh DEK for a new encryption run; if resuming upload of already encrypted ciphertext, keep the exact already generated ciphertext chunks and do not re-encrypt them with old nonces over different content.

## 18. Encryption in the restore pipeline

A controlled restore workflow:

1. Authenticate the workload identity of the restoring instance.
2. Verify whether artifact ID, environment, version, and policy allow restore.
3. Download the manifest over TLS and verify its signature/MAC.
4. Retrieve the wrapped DEK and ask KMS to unwrap it using restricted permissions.
5. Download ciphertext over TLS.
6. Verify each chunk using its AEAD tag and AAD.
7. Verify completeness of files, chunks, sizes, and metadata in the manifest.
8. Decrypt into a protected staging directory.
9. Check file permissions, ownership, structure, and compatibility metadata.
10. Move the artifact to the restore location only after the entire package is verified.
11. Invoke the restore mechanism according to JDK/runtime documentation.
12. Keep readiness in a not-ready state until the application and dependencies recover.

Do not decrypt and restore piecemeal in a way that allows the process to start from an incomplete package. If the runtime requires an entire consistent checkpoint directory, finish verifying everything before handing that directory to the runtime.

If an AEAD tag is invalid, the manifest signature is wrong, chunks are missing, or the file list does not match, abort restore. Do not skip failing files or attempt decryption with an arbitrary key.

## 19. Avoiding temporary plaintext and leftover files

A common weakness is encrypting the final object while leaving a plaintext copy in a temporary directory. For example, a pipeline creates an unencrypted archive, then encrypts the archive and uploads it. If the original archive remains, the encryption-at-rest objective is not met.

Check:

- Is the original checkpoint directory on an encrypted volume?
- Are plaintext archives deleted after encryption?
- Are temporary files created with owner-only read/write permissions?
- Does a crash or process kill leave plaintext files behind?
- Are temporary directories automatically backed up or synced?
- Can swap, core dumps, or diagnostic dumps contain plaintext?
- Does restore write decrypted files onto a protected volume?
- Does cleanup run if the pipeline fails mid-way?

Secure deletion on SSDs, copy-on-write filesystems, or object-storage versioning is not simply overwriting a file and deleting it. If strong deletion is needed, use encrypted storage and destroy keys under a cryptographic erasure policy, while also managing all backups/key versions.

Tmpfs avoids writing temporary files to disk in some configurations, but does not automatically eliminate all risks. Contents still reside in memory and may be swapped or appear in dumps depending on configuration. Review the entire host policy.

## 20. Access controls on storage and artifact repositories

Encryption does not replace storage access controls. Restrict who can list, read, write, delete, copy, or modify retention on checkpoint artifacts.

Common measures:

- Separate buckets/containers per environment or application.
- IAM policies restricted by prefix, tag, or resource.
- Allow only the pipeline to publish official artifacts.
- Versioning or immutable retention when protection against modification/deletion is needed.
- Audit logs for read, write, delete, and key usage.
- No public objects or broad ACLs.
- Restrict permissions to download checkpoints to personal machines.
- Separate permissions for backup and restore operators.
- Set retention according to recovery needs and data policy.

If using pre-signed URLs, limit duration, HTTP method, object, and permissions. Do not log full URLs because the query string can act as a bearer credential. TLS must still be enabled and certificates must be verified.

## 21. Transferring over TLS, mTLS, and SFTP

Common methods:

| Channel | When appropriate | Notes |
|---|---|---|
| HTTPS/TLS | Upload/download via object storage or artifact API | Verify certificates and hostname |
| mTLS | Service-to-service requiring mutual authentication | Manage client certificates and rotation |
| SFTP/SSH | File transfer across controlled hosts | Verify host keys; restrict users and directories |
| Private network/VPN | Reduce endpoint exposure | Does not replace application encryption or TLS if policy requires |
| Service mesh TLS | Protect hops between workloads | Identify TLS termination and all remaining hops |

Do not build custom encryption protocols over TCP. Use TLS or proven protocols. With SFTP, verify host keys rather than accepting any server key; otherwise, the client could send artifacts to an imposter server.

## 22. Verifying provenance and preventing artifact rollback

Encryption and signatures can prove an artifact was not altered after issuance, yet do not necessarily prevent replacing it with an older, still-valid artifact.

For example, an attacker could replace a newer checkpoint with an older, properly signed checkpoint. The signature remains valid, yet the application could start from an outdated state.

If rollback is a risk, the manifest should include:

- Monotonically increasing artifact generation or sequence.
- Permitted build/version and deployment release.
- Environment and application identity.
- Creation timestamp from a trusted source.
- Expiration or usage window policy.
- Checkpoint lineage or parent ID if needed.

The restore service needs to compare the generation against policy or durable metadata outside the artifact. Do not trust only self-declared timestamps inside the artifact. Maintaining an allowlist or minimum generation in a control plane with integrity protection may be necessary.

## 23. Performance and capacity

Encryption, authentication, compression, and transport all consume CPU or I/O. For large checkpoints, pipeline duration can become a significant part of deployment time.

Factors to measure:

- Checkpoint size before and after compression.
- Encryption/decryption throughput under actual CPU quota.
- Chunk size and number of parallel encryption workers.
- KMS generate/wrap/unwrap latency.
- Upload/download throughput and retries.
- Storage request count and cost.
- Buffer memory usage in the pipeline.
- Manifest/signature verification time.
- Time from checkpoint completion to artifact publication.
- Time from restore request until plaintext is ready.

Do not spawn too many encryption workers based solely on host CPU count. Inside containers, account for CPU quotas and cgroup throttling. Chunks that are too small increase metadata and tag overhead; chunks that are too large increase memory requirements and make retries expensive. Choose chunk size by benchmarking on realistic workloads.

Compressing before encrypting usually reduces storage and network costs, yet can increase CPU usage. Under low CPU quotas, a compression pipeline can slow down publishing or restoring. Measure both latency and resource consumption.

## 24. KMS availability and disaster recovery

Client-side encryption creates a dependency on KMS or the key service during restore. If KMS in a region becomes unavailable, the application may be unable to decrypt checkpoints even while object storage continues working.

Design for:

- KMS key replication or multi-region keys if supported by the platform.
- Restore policies in standby regions.
- Identities with unwrap permissions in the disaster recovery environment.
- Backups and retention of key metadata.
- Recovery procedures when keys are disabled or rotated.
- Testing restore when the primary region is lost.
- Alerts when keys are nearing expiration or disabled.
- Runbooks for KMS quota or throttling situations.

Do not copy plaintext DEKs to a less secure location merely as a KMS fallback. Use KMS/HSM-supported backup/recovery mechanisms and test with a real artifact.

## 25. Limitations of encryption

Artifact encryption is critical, yet does not protect against every scenario.

Encryption at rest does not protect plaintext once a volume is mounted and a process has read permissions. TLS does not protect data after TLS termination. Client-side encryption does not defend against a checkpoint creation machine compromised prior to encryption or a restore machine compromised after decryption.

Encryption also does not by itself prevent:

- Authorized principals with decrypt permission accessing data.
- Malware or malicious processes on the restore machine reading plaintext.
- Credentials leaking via logs, environment, debuggers, or core dumps.
- Attackers deleting artifacts causing denial of service.
- Rollback to older checkpoints if anti-rollback policies are absent.
- Exposure of metadata or artifact size if not encrypted/padded.
- KMS administrators or misconfigured key policies granting overly broad permissions.

Therefore, combine encryption with endpoint security, IAM, auditing, secret management, integrity verification, retention, and operational procedures.

## 26. Example manifest for an encrypted checkpoint

A manifest may have a logical structure like this:

~~~json
{
  "formatVersion": 1,
  "artifactId": "service-a-2026-11-13-build-42",
  "application": "service-a",
  "environment": "production",
  "runtime": {
    "jdkVendor": "approved-vendor",
    "jdkVersion": "approved-build",
    "architecture": "linux-x86_64"
  },
  "encryption": {
    "algorithm": "AES-256-GCM",
    "keyManagement": "envelope",
    "kmsKeyId": "kms-key-reference",
    "wrappedDataKey": "base64-ciphertext",
    "nonceFormat": "artifact-prefix-plus-chunk-counter"
  },
  "files": [
    {
      "id": "memory-0",
      "path": "checkpoint/memory.img",
      "plaintextSize": 123456789,
      "chunkCount": 12
    }
  ],
  "generation": 42
}
~~~

This is an illustrative structural example, not a standard CRaC schema. Plaintext keys or secrets should not be placed in the manifest. If filenames or runtime metadata are sensitive, encrypt that portion of the manifest or expose only a minimal header externally.

A real manifest needs to be authenticated via signature/MAC or bound via AAD. Fields like `artifactId`, `formatVersion`, file paths, sizes, chunk counts, `generation`, and key reference must be protected so an attacker cannot tamper with metadata and still pass verification.

## 27. Testing encryption and restore

Do not merely test that upload/download returns HTTP 200. Prove that artifacts are unreadable without permission, tampering is detected, and valid restores still succeed.

Scenarios:

1. Create a checkpoint in a test environment with synthetic sensitive data.
2. Package and encrypt the artifact.
3. Verify storage contains only ciphertext by design; no plaintext archive remains in staging.
4. Download the artifact using a principal with object-read permission only and no decrypt permission.
5. Confirm that principal cannot obtain plaintext.
6. Restore using an authorized principal; verify KMS unwrap and AEAD authentication succeed.
7. Modify one byte of ciphertext and confirm decryption fails.
8. Modify the manifest, file list, chunk order, or wrapped DEK and confirm signature/MAC/AAD validation fails.
9. Replace the artifact with an older generation and confirm rollback policy rejects it if policy requires.
10. Interrupt upload mid-chunks and confirm the artifact is not published.
11. Interrupt download/restore and confirm plaintext staging is cleaned up according to policy.
12. Rotate the KEK, rewrap the DEK, and restore the older artifact again.
13. Test restore in a standby region or while primary KMS is temporarily unavailable.
14. Measure CPU, memory, I/O, and duration for large artifacts under realistic resource limits.

Do not use real production data to test encryption without an approved protection procedure. Use synthetic secrets and check that they do not appear in logs or plaintext artifacts.

## 28. Common mistakes

**Encrypting only in transit.** After being written to storage, the artifact may still be plaintext. Encryption at rest is required.

**Enabling only server-side encryption and ignoring object read permissions.** Principals with permission to read objects and use the key can obtain plaintext. Control IAM and consider client-side encryption based on the threat model.

**Encrypting only one file in the checkpoint directory.** Metadata or auxiliary files can still leak data. Inventory and protect the entire package.

**Using checksums as authentication proof.** Attackers can replace both the file and the checksum. Use AEAD, MAC, or digital signatures.

**Reusing nonces with the same AES-GCM key.** This can break confidentiality and authenticity. Ensure unique nonces per DEK, especially during chunked encryption and retries.

**Storing plaintext DEKs or KEKs next to ciphertext.** Anyone with the artifact can decrypt it. Use envelope encryption and KMS/HSM.

**Deleting old keys too early.** Backup artifacts may become unrestorable. Align key retention with artifact retention and test rotation.

**Leaving plaintext archives in temporary directories.** Encrypting the final object does not remove plaintext copies. Protect staging and clean up even on errors.

**Trusting TLS to protect contents after storage.** TLS only protects the transport session. Storage needs encryption at rest and integrity.

**Not verifying certificates or host keys.** Artifacts could be sent to an imposter endpoint. Enable server authentication and manage trust material.

**Publishing the artifact before upload finishes.** Restores may read a package missing files/chunks. Publish the manifest/commit marker only after verification completes.

**Not binding the manifest to the artifact.** Attackers can swap files, chunks, or metadata. Sign/authenticate the manifest and use AAD per chunk.

**Setting overly broad decrypt permissions.** One service account could decrypt across all environments. Separate keys, roles, and policies by application/environment.

**Not testing restore after rotation or DR.** Artifacts may exist while keys are no longer usable. Test recovery using real artifacts in a controlled environment.

## 29. Checkpoint artifact protection checklist

- [ ] Have sensitive data items that may appear in checkpoints been identified?
- [ ] Have all files, metadata, manifests, backups, and temporary files been inventoried?
- [ ] Are checkpoints packaged/encrypted only after the runtime confirms completion?
- [ ] Is encryption at rest enabled for disks, volumes, object storage, and backups?
- [ ] Is the artifact client-side encrypted if required by the threat model?
- [ ] Do uploads/downloads use TLS with certificate/hostname verification?
- [ ] Is every hop after TLS termination protected?
- [ ] Has AEAD been chosen with unique nonces per key guaranteed?
- [ ] Are large artifacts encrypted by chunks without loading the whole artifact into the heap?
- [ ] Are the manifest, file list, chunk counts, sizes, and generation authenticated?
- [ ] Is envelope encryption used with dedicated DEKs and KEKs managed in KMS/HSM?
- [ ] Are encrypt, decrypt, sign, publish, and storage-read permissions separated?
- [ ] Have key rotation, key retention, and disaster recovery been tested?
- [ ] Are there no plaintext DEKs, KEKs, or credentials in artifacts/manifests/logs?
- [ ] Are temporary plaintext and staging directories protected and cleaned up on failures?
- [ ] Does storage policy restrict list/read/write/delete and enable auditing?
- [ ] Is anti-rollback enforced if the latest generation must be guaranteed?
- [ ] Does restore run only after signature/MAC/AEAD and file completeness are verified?
- [ ] Does readiness succeed only after decryption and dependency restoration complete?
- [ ] Have ciphertext tampering, manifest tampering, chunk tampering, upload interruption, and key rotation been tested?

## Conclusion

Checkpoint artifacts can contain sensitive data from the entire process, so they need to be protected as security assets. Encryption at rest protects data on disks, volumes, object storage, and backups; TLS protects data during upload/download. For stronger protection requirements at the storage boundary, client-side envelope encryption allows encrypting artifacts with dedicated DEKs and protecting DEKs with KMS/HSM.

A secure workflow needs to authenticate manifests, use AEAD with unique nonces, verify file/chunk completeness, separate creation and restore permissions, manage key rotation/retention, and avoid leaving temporary plaintext behind. After restore, decrypt only with authorized identities, verify the complete artifact, and only then hand it over to the runtime. Encryption does not replace endpoint protection or access controls, yet when combined with TLS, IAM, auditing, and recovery testing, it significantly reduces the risk of checkpoint exposure or tampering at rest and in transit.
