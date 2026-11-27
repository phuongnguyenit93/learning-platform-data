# Server-Side Encryption, Client-Side Encryption, and Key Management

A Spring Boot application storing orders, customer profiles, or documents in managed services must answer three questions: **where is data encrypted**, **who controls the keys**, and **who can read the data after storage**. Simply enabling default encryption on object storage or a database does not necessarily protect data from every principal with service read permissions. Conversely, encrypting every byte inside the application adds responsibilities for key management, versioning, backup, and recovery.

Three common models are **server-side encryption (SSE)**, **client-side encryption (CSE)**, and **envelope encryption**. SSE lets the storage service encrypt data when writing to media; CSE encrypts data inside the application before sending; envelope encryption uses a short-lived data encryption key (DEK) to encrypt the payload and a managed key (KEK) in KMS to protect the DEK. Cloud providers offer their own key management services, yet the design principles and application responsibilities must still be thoroughly understood.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, covering identity/permissions, storage, messaging, data, secret protection, testing, and evaluating differences across cloud providers. The focus of this lesson is choosing an encryption model based on the threat model, integrating KMS/Key Vault/Cloud KMS, and designing a safe key lifecycle.

## 1. Learning Objectives and Running Scenario

After this lesson, you will be able to:

1. Distinguish between encryption in transit, encryption at rest, SSE, CSE, and envelope encryption.
2. Explain the differences among provider-managed keys, customer-managed keys (CMKs), customer-provided keys, and application-managed keys.
3. Choose between SSE and CSE based on data sensitivity, compliance requirements, access permissions, and searchability.
4. Design envelope encryption using AES-GCM, DEKs, KEKs, and authenticated additional data.
5. Use AWS KMS, Azure Key Vault Keys, or Google Cloud KMS to wrap/unwrap DEKs.
6. Grant least-privilege permissions to workloads and separate runtime permissions from key administration permissions.
7. Plan key rotation, rewrapping, disabling, recovery, and destruction.
8. Test ciphertext, integrity, key versions, decrypt permissions, and logs to prevent plaintext exposure.

Scenario: `document-service` stores PDF contracts and sensitive customer information. Files are stored in object storage, metadata is stored in a database, and the application runs on Kubernetes and may be deployed on AWS, Azure, or Google Cloud.

| Data | Protection goal |
| --- | --- |
| PDF contracts | Prevent anyone with bucket read access but no application permission from decrypting contents |
| Non-sensitive metadata | Use managed service SSE/TDE to protect underlying media |
| Customer identifiers | May require field-level CSE if DBAs/operators must not read plaintext |
| DEK | Never store plaintext alongside ciphertext; keep only the KMS-wrapped copy |
| KEK | Stored and managed in KMS/Key Vault; restrict unwrap/decrypt permissions |

~~~mermaid
flowchart TD
    A["Spring Boot document-service"] --> B["Generate DEK for an object"]
    B --> C["AES-256-GCM encrypts payload"]
    B --> D["KMS / Key Vault / Cloud KMS wraps DEK"]
    C --> E["Ciphertext + nonce + tag"]
    D --> F["Wrapped DEK + key reference"]
    E --> G["Object storage"]
    F --> G
    G --> H["On read: retrieve wrapped DEK"]
    H --> I["KMS unwraps DEK"]
    I --> J["AES-GCM verifies tag and decrypts"]
    J --> K["Plaintext only within authorized application scope"]
~~~

**Core principle:** KMS protects and controls the keys; the encryption algorithm protects the data; IAM/RBAC determines which workloads may request key operations. All three layers must be designed together.

## 2. Encryption in Transit and Encryption at Rest

### 2.1. Encryption in transit

Encryption in transit protects data over the network, typically using TLS 1.2/1.3. Examples:

- Spring Boot making HTTPS calls to S3, Azure Blob Storage, or Google Cloud Storage.
- SDKs fetching OAuth tokens from Microsoft Entra ID or calling KMS APIs.
- Service-to-service communication over mTLS when mutual verification is required.

TLS protects requests/responses on the wire, but once a request reaches the service and is processed, the service may see plaintext depending on the model. TLS does not replace encryption of data in storage.

### 2.2. Encryption at rest

Encryption at rest protects data on physical media, snapshots, or backups. Managed services can automatically encrypt data before writing to storage:

- Object storage encrypts objects and replicas.
- Databases use Transparent Data Encryption (TDE) or built-in encryption at rest.
- Disks/volumes are encrypted at the block storage layer.

SSE/TDE is usually **transparent to the application**: the application sends plaintext over TLS, the service encrypts on write, and decrypts when an authorized principal reads. This protects against stolen media or out-of-band backup access, but does not by itself stop a principal with API read permissions from reading the data.

### 2.3. Encryption at the application layer

CSE encrypts the payload **before sending it to storage or the database**. The storage service receives ciphertext, lacks the application's decryption key, and therefore cannot read plaintext.

CSE can mitigate risks such as:

- Operators who have object read permissions but lack DEK unwrap permissions.
- Snapshots/backups copied outside the system.
- Unauthorized access to a storage account or bucket where the attacker lacks KMS permissions.
- Specific data fields needing field-level encryption to narrow who can read them.

CSE does not hide all metadata: object names, sizes, timestamps, tenant identifiers, access patterns, and unencrypted metadata can still be exposed. Design object naming and metadata carefully if they are sensitive.

## 3. Server-Side Encryption (SSE)

### 3.1. Workflow

~~~text
Spring Boot
    |
    | plaintext over HTTPS/TLS
    v
Object storage / database service
    |
    | service encrypts on write
    v
Encrypted media / snapshot / backup
    |
    | service decrypts when an authorized principal reads
    v
Plaintext response over TLS
~~~

With SSE, the application does not need to generate a DEK per object. The storage or database service manages encryption/decryption and interacts with KMS if a customer-managed key is chosen.

### 3.2. Key options

| Option | Who manages the key material? | Level of control |
| --- | --- | --- |
| Provider-managed key | Cloud provider | Easy to operate; limited control over custom lifecycle and key auditing |
| Customer-managed key (CMK) | Customer manages the key resource/policy in KMS; provider still operates KMS infrastructure | Control over usage permissions, rotation, disabling, and auditing |
| Customer-provided key | Customer supplies the key in each request | Direct key control, but responsible for securely storing and transmitting the key |
| Application-managed key | Application or separate system manages it | Flexible, but high responsibility; typically combined with envelope encryption |

**Customer-managed key does not mean the application receives the private key or raw key material.** Typically, KMS retains the key material and workloads are only permitted to invoke encrypt/decrypt or generate-data-key operations.

### 3.3. SSE on AWS

Common options with Amazon S3:

| Mode | Meaning |
| --- | --- |
| SSE-S3 | S3 manages keys itself for object encryption |
| SSE-KMS | S3 uses an AWS KMS key; can use an AWS managed key or a customer managed KMS key |
| DSSE-KMS | Dual-layer server-side encryption with two layers of encryption managed by the service |
| SSE-C | Client supplies the key per request; S3 performs server-side encryption/decryption |

AWS SDK for Java 2.x example requesting SSE-KMS for an object:

~~~java
PutObjectRequest request = PutObjectRequest.builder()
        .bucket(bucketName)
        .key(objectKey)
        .serverSideEncryption(ServerSideEncryption.AWS_KMS)
        .ssekmsKeyId(kmsKeyArn)
        .build();

s3Client.putObject(request, RequestBody.fromFile(file));
~~~

This is a conceptual example for S3 `PutObject`; you must add the S3 SDK dependency and handle files/streams appropriately for your application. If a bucket already has default bucket encryption set to SSE-KMS, specifying headers per object may not be required; however, verify bucket policies and encryption configuration.

When using SSE-KMS, uploading principals typically need the corresponding KMS permissions for S3 to generate data keys; reading principals need decrypt permissions per the key policy/IAM and bucket policy. Actual policy evaluation also depends on S3 Bucket Keys, cross-account access, grants, and service integrations. Never grant only S3 `GetObject` and assume KMS permissions are automatically included.

**SSE-C is not CSE.** The client sends the key to S3 over HTTPS, yet S3 still encrypts/decrypts on the server side. If the storage service must only ever see ciphertext, you need CSE before uploading.

### 3.4. SSE on Azure Storage

Azure Storage encrypts data at rest by default using encryption at rest. You can choose:

- Microsoft-managed keys: the platform manages the keys.
- Customer-managed keys in Azure Key Vault or Managed HSM: the organization controls the key resource and policy.
- Customer-provided keys in certain supported services/flows: the client supplies the key for the service to perform server-side encryption.

For Blob Storage CMK, configure the identity that Storage uses to access Key Vault and grant appropriate key permissions. This may be the managed identity of the storage account/service, not necessarily Spring Boot's identity. Always distinguish the principal calling the Blob API from the principal Azure Storage uses to access Key Vault.

Spring Boot still calls the Blob SDK over HTTPS; the application does not need to encrypt content itself just because Storage uses CMK. If plaintext must be protected even from the storage service, use CSE.

### 3.5. SSE on Google Cloud Storage

Google Cloud Storage supports:

- Google-managed encryption keys by default.
- Customer-managed encryption keys (CMEK) via Cloud KMS.
- Customer-supplied encryption keys (CSEK) for supported use cases.

When using CMEK, the Cloud Storage service agent needs permission to use the appropriate CryptoKey. Spring Boot's service account still needs object storage permissions; the service agent's KMS permissions and the workload's IAM permissions belong to two separate principals.

Google Cloud Storage can use key versions according to CMEK configuration. When changing the primary version, newly written objects can use the new version; existing objects are not automatically re-encrypted simply because the primary version changed.

### 3.6. Databases and volumes

Encryption at the database/volume layer is suitable for protecting data files, logs, backups, and snapshots:

| Service | Common mechanism |
| --- | --- |
| Amazon RDS/Aurora | Storage encryption with AWS KMS |
| Azure SQL Database | Transparent Data Encryption; customer-managed key option available |
| Azure Database for PostgreSQL/MySQL | Encryption at rest depending on service capabilities and configuration |
| Google Cloud SQL | Encryption at rest; CMEK in supported configurations |
| Persistent disk/managed disk | Disk encryption and customer-managed keys depending on service |

TDE does not replace CSE for a sensitive column if DBAs or database principals are allowed to query plaintext. If the database engine itself must not read a field, encrypt at the application layer before writing.

## 4. Client-Side Encryption (CSE)

### 4.1. Workflow

~~~text
Spring Boot application
    |
    | 1. Generate/obtain DEK
    | 2. AES-GCM encrypt plaintext
    | 3. KMS wraps DEK with KEK
    v
Ciphertext + nonce + authentication tag
Wrapped DEK + key reference + metadata
    |
    | HTTPS
    v
Object storage / database
    |
    | Stores only ciphertext and wrapped DEK
    v
On read: app fetches envelope -> KMS unwraps DEK -> AES-GCM decrypts
~~~

With CSE, storage does not decrypt content. The application must have permission to unwrap the DEK and possess the matching metadata to decrypt.

### 4.2. When should CSE be used?

| Requirement | Is CSE appropriate? |
| --- | --- |
| Storage operators must not read plaintext | Yes |
| Only want disk/backup encryption while letting the service read objects | SSE is usually sufficient |
| Encrypt a few PII fields before writing to DB | Can be appropriate |
| Need direct server-side search/filtering on content | Harder; requires custom indexing/tokenization design |
| Need to handle large videos or streaming | Possible, but requires chunking/streaming format and per-chunk nonce/tag management |
| Need to share files across multiple tenants with distinct permissions | Possible, but requires a per-tenant/recipient key model and clear access control |
| No key retention/recovery process exists | Do not deploy CSE yet |

CSE increases security but also increases operational complexity. Losing the KEK or losing all wrapped DEK copies can render data unrecoverable even if object storage remains intact.

### 4.3. What CSE does not automatically protect

- **Metadata:** object names, tenants, timestamps, content length, tags, and access patterns may still be exposed.
- **Application runtime:** when the application decrypts, plaintext resides in memory and could appear in heap dumps, logs, or crash reports.
- **Credential compromise:** an attacker who compromises a workload identity with unwrap permission can ask KMS to decrypt.
- **Authorization:** encryption does not replace tenant/user access control; check permissions before unwrapping.
- **Integrity beyond payload:** AES-GCM authenticates ciphertext/AAD, but does not automatically protect all metadata unless that metadata is included in AAD.

## 5. Envelope Encryption: DEK and KEK

### 5.1. Two key tiers

- **DEK (Data Encryption Key):** the key that encrypts the actual data, e.g., AES-256.
- **KEK (Key Encryption Key):** a key in KMS used to wrap/unwrap DEKs; not used directly to encrypt large files.
- **Wrapped DEK:** a DEK encrypted by the KEK, which can be stored alongside the ciphertext.
- **Key reference:** identifier of the KMS key/Key Vault key/CryptoKey, optionally including version.

~~~mermaid
flowchart TD
    P["Plaintext payload"] --> E["AES-256-GCM"]
    D["DEK: AES-256"] --> E
    E --> C["Ciphertext + nonce + tag"]
    D --> W["KMS Wrap / Encrypt DEK"]
    K["KEK in KMS"] --> W
    W --> WD["Wrapped DEK"]
    C --> O["Encrypted object envelope"]
    WD --> O
    M["Key ID + algorithm + format version + AAD context"] --> O
~~~

### 5.2. Why not use the KEK to encrypt files directly?

KMS services typically limit the plaintext size that can be encrypted directly and are optimized for key management operations. Encrypting a large file via a KMS API:

- Increases latency and cost.
- Can exceed request size limits.
- Forces payloads to traverse KMS instead of being encrypted locally.
- Is difficult to stream and hard to bound in memory.

Envelope encryption only sends the **small DEK** to KMS for wrapping/unwrapping. The payload is encrypted locally with AES-GCM.

### 5.3. Encryption flow

1. The application authenticates the principal and verifies object write permissions.
2. Request KMS to generate a DEK or generate one locally using `SecureRandom`/`KeyGenerator`.
3. Obtain the plaintext DEK in memory and the wrapped DEK.
4. Generate a unique random nonce for this encryption operation with that DEK.
5. Encrypt plaintext using AES-256-GCM; include critical metadata in AAD.
6. Store ciphertext, nonce, wrapped DEK, key reference, algorithm, and format version.
7. Perform best-effort zeroing of plaintext DEK copies from controllable memory.

### 5.4. Decryption flow

1. Authenticate the user/tenant and verify object read permissions.
2. Read the envelope; validate format version, key reference, and metadata.
3. Call KMS to unwrap the DEK with the exact encryption context.
4. Use the DEK and nonce for AES-GCM decryption.
5. GCM verifies the authentication tag; if invalid, reject the plaintext.
6. Return plaintext within authorized scope and do not log it.
7. Perform best-effort zeroing of the DEK from memory once finished.

**Never return partial plaintext before GCM tag verification succeeds.** For streaming APIs, design buffering/chunk authentication so unverified data is never consumed as valid data.

## 6. Choosing Algorithms and Envelope Format

### 6.1. AES-256-GCM

AES-GCM is authenticated encryption with associated data (AEAD): it provides both encryption and integrity/authenticity checks.

| Parameter | Recommended value |
| --- | --- |
| Cipher | `AES/GCM/NoPadding` |
| Key size | 256 bits (32 bytes) |
| Nonce/IV | 96 bits (12 bytes) |
| Authentication tag | 128 bits (16 bytes) |
| AAD | Non-secret context that still requires authentication |
| Nonce rule | Never reuse a nonce with the same DEK |

Never use ECB. CBC only encrypts without authenticating; if a legacy mode must be used, implement encrypt-then-MAC properly. For new applications, prefer AEAD such as AES-GCM or ChaCha20-Poly1305 where supported by platform policy.

### 6.2. Nonce/IV

A GCM nonce does not need to be secret, but **it must be unique per key**. Reusing a nonce with the same DEK can leak information and break integrity guarantees.

Simple approach per object:

- Generate a fresh DEK for each object/envelope.
- Generate a 12-byte nonce from `SecureRandom`.
- Store the nonce alongside the ciphertext.
- Never reuse the DEK/nonce pair for another encryption.

When one DEK encrypts many records, you need a controlled nonce-uniqueness mechanism and usage limits. Avoid designing custom counters unless you can synchronize and prevent duplicates across multiple instances.

### 6.3. Authenticated Additional Data (AAD)

AAD is metadata authenticated alongside the ciphertext without being encrypted. It can contain:

- Tenant ID.
- Object ID.
- Logical record type.
- Schema/format version.
- Application namespace.

Example AAD binding an object to a tenant:

~~~text
tenant=tenant-42
object=contract-2026-001
purpose=contract-pdf
format=v1
~~~

On decryption, you must reconstruct the exact same AAD used during encryption. If an attacker alters the object ID or tenant ID in metadata, GCM tag verification fails. Never put secret data in AAD because AAD is stored/observable in plaintext.

With AWS KMS, encryption context is additional metadata authenticated by KMS during `Encrypt`/`Decrypt` operations; it is **not secret** and may appear in CloudTrail. Never place PII, tokens, or sensitive data in encryption context.

### 6.4. Stored envelope format

A record can be represented as follows:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyProvider": "aws-kms",
  "keyReference": "arn:aws:kms:region:account:key/key-id",
  "wrappedDek": "base64...",
  "nonce": "base64...",
  "ciphertext": "base64...",
  "context": {
    "tenantId": "tenant-42",
    "objectId": "contract-2026-001"
  }
}
~~~

This is an **illustrative data model**, not a universal format across all SDKs. Version the schema, bound metadata sizes, validate context, and define migrations. Never store plaintext DEKs or KEKs in the envelope.

For large payloads, you can store ciphertext in object storage and envelope metadata in headers/sidecars/a database. Ensure metadata cannot be detached from the object or swapped undetected; include critical fields in AAD.

## 7. Java Encryption Patterns in Spring Boot

This section illustrates a cloud-agnostic encryption layer. A specific KMS adapter supplies the DEK and wrapped DEK. The application never stores KEKs itself.

### 7.1. Key provider model and interface

~~~java
package com.example.protection;

public record DataKeyMaterial(byte[] plaintextKey, byte[] wrappedKey, String keyReference) {
}
~~~

~~~java
package com.example.protection;

import java.util.Map;

public interface DataKeyProvider {
    DataKeyMaterial generateDataKey(
            String keyReference,
            Map<String, String> kmsEncryptionContext);

    byte[] unwrapDataKey(
            String keyReference,
            byte[] wrappedKey,
            Map<String, String> kmsEncryptionContext);
}
~~~

Implementations call AWS KMS, Azure Key Vault, or Google Cloud KMS. Only the adapter holds the necessary permissions to wrap/unwrap; business services need not know SDK specifics.

**Separate the two context types:** byte-array AAD is authenticated by AES-GCM with the payload; KMS encryption context is provider-specific metadata (AWS KMS uses a key/value map, whereas Azure Key Vault wrap has no equivalent parameter). Never assume these two values share the same format. Only put non-sensitive metadata into KMS context; reconstruct the exact context when unwrapping.

### 7.2. Envelope model

~~~java
package com.example.protection;

public record EncryptedEnvelope(
        int formatVersion,
        String algorithm,
        String keyReference,
        byte[] wrappedKey,
        byte[] nonce,
        byte[] ciphertext) {
}
~~~

In production, records holding byte arrays should defensively copy on construction and access to prevent callers from mutating contents after verification. Use immutable value objects and versioned serializers.

### 7.3. AES-GCM service

~~~java
package com.example.protection;

import java.util.Map;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.stereotype.Service;

@Service
public class EnvelopeEncryptionService {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int KEY_BYTES = 32;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final DataKeyProvider keyProvider;
    private final SecureRandom secureRandom = new SecureRandom();

    public EnvelopeEncryptionService(DataKeyProvider keyProvider) {
        this.keyProvider = keyProvider;
    }

    public EncryptedEnvelope encrypt(
            byte[] plaintext,
            byte[] aad,
            String keyReference,
            Map<String, String> kmsEncryptionContext) throws Exception {

        DataKeyMaterial material =
                keyProvider.generateDataKey(keyReference, kmsEncryptionContext);

        byte[] dek = material.plaintextKey();
        byte[] nonce = new byte[NONCE_BYTES];
        secureRandom.nextBytes(nonce);

        try {
            if (dek.length != KEY_BYTES) {
                throw new IllegalStateException("Expected a 256-bit DEK");
            }

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad);

            byte[] ciphertext = cipher.doFinal(plaintext);

            return new EncryptedEnvelope(
                    1,
                    "AES-256-GCM",
                    material.keyReference(),
                    material.wrappedKey(),
                    nonce,
                    ciphertext);
        } finally {
            // Best-effort cleanup; JVM/provider may retain internal copies.
            Arrays.fill(dek, (byte) 0);
        }
    }

    public byte[] decrypt(
            EncryptedEnvelope envelope,
            byte[] aad,
            Map<String, String> kmsEncryptionContext) throws Exception {

        if (envelope.formatVersion() != 1
                || !"AES-256-GCM".equals(envelope.algorithm())) {
            throw new IllegalArgumentException("Unsupported envelope format");
        }

        byte[] dek = keyProvider.unwrapDataKey(
                envelope.keyReference(),
                envelope.wrappedKey(),
                kmsEncryptionContext);

        try {
            if (dek.length != KEY_BYTES) {
                throw new IllegalStateException("Invalid DEK length");
            }

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, envelope.nonce()));
            cipher.updateAAD(aad);

            // doFinal verifies the GCM authentication tag before returning plaintext.
            return cipher.doFinal(envelope.ciphertext());
        } finally {
            Arrays.fill(dek, (byte) 0);
        }
    }
}
~~~

The sample above focuses on AEAD logic. Production code should additionally include:

- Defensive copies and size validation for all fields.
- Tenant/object authorization checks **before** calling unwrap.
- Binding AAD to object/tenant IDs sourced from a trusted request context.
- Error mapping that does not leak ciphertext, keys, or plaintext.
- Bounded timeouts/retries for KMS calls.
- Metrics on key references/versions without recording secrets.
- Streaming/chunked encryption for large files.
- Tests for tampering, wrong AAD, wrong keys, and version migration.

Do not declare broad `throws Exception` in production services; translate KMS errors, format errors, and authentication tag failures into dedicated domain/service exceptions.

### 7.4. Generating DEKs locally instead of KMS GenerateDataKey

A provider adapter can generate an AES key locally via JCA and then call KMS to wrap it:

~~~java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey dek = generator.generateKey();

byte[] plaintextDek = dek.getEncoded();
// Call KMS wrap/encrypt with plaintextDek.
// Persist wrapped DEK; never persist plaintextDek.
~~~

This is a common pattern with Key Vault RSA wrapping and Cloud KMS `encrypt`. With AWS KMS, you can use `GenerateDataKey` so KMS creates both the plaintext DEK and ciphertext blob in a single call, avoiding separate generation and wrapping steps.

## 8. Integrating AWS KMS

### 8.1. GenerateDataKey

AWS KMS provides the `GenerateDataKey` API, which returns:

- `Plaintext`: the DEK for the application to encrypt data.
- `CiphertextBlob`: the DEK encrypted by the KMS key.
- Key ID and related metadata.

AWS SDK for Java 2.x example:

~~~java
GenerateDataKeyResponse response = kmsClient.generateDataKey(
        GenerateDataKeyRequest.builder()
                .keyId(kmsKeyArn)
                .keySpec(DataKeySpec.AES_256)
                .encryptionContext(Map.of(
                        "tenant", tenantId,
                        "purpose", "contract"))
                .build());

byte[] plaintextDek = response.plaintext().asByteArray();
byte[] wrappedDek = response.ciphertextBlob().asByteArray();
~~~

The application uses `plaintextDek` for AES-GCM and stores `wrappedDek` in the envelope. After use, perform best-effort zeroing of the plaintext key from memory. The encryption context must be supplied identically on decrypt; do not accept unvalidated caller-supplied data.

### 8.2. Decrypting the DEK

~~~java
DecryptResponse response = kmsClient.decrypt(
        DecryptRequest.builder()
                .ciphertextBlob(SdkBytes.fromByteArray(wrappedDek))
                .encryptionContext(Map.of(
                        "tenant", tenantId,
                        "purpose", "contract"))
                .build());

byte[] plaintextDek = response.plaintext().asByteArray();
~~~

AWS KMS uses metadata inside the ciphertext blob to identify the decryption key; in certain API scenarios, you can also specify a key ID. For cross-account envelopes or multi-key setups, store the key ARN/resource reference for auditing and migration support.

### 8.3. IAM and key policies

Workloads calling AWS KMS `GenerateDataKey` need the `kms:GenerateDataKey` permission; reading envelopes and unwrapping DEKs requires `kms:Decrypt`. If an adapter calls KMS `Encrypt`/`Decrypt` directly to wrap DEKs, grant those corresponding actions. Both the key policy and IAM policies can participate in authorization decisions.

Encryption context:

- Is not secret; it may be logged in CloudTrail.
- Must match between `GenerateDataKey`/`Encrypt` and `Decrypt`.
- Can be used in IAM conditions to constrain key usage context.
- Must not contain emails, account numbers, tokens, or PII.

### 8.4. SSE-KMS and CSE with AWS KMS are two different things

| SSE-KMS | CSE envelope |
| --- | --- |
| S3 calls KMS per bucket/object encryption configuration | Application calls KMS to generate/wrap DEKs |
| S3 receives plaintext and encrypts on the server | S3 only receives ciphertext |
| S3 decrypts when an authorized principal reads | Application unwraps the DEK and decrypts |
| Requires S3 permissions and KMS permissions along the SSE flow | Requires S3 permissions and application KMS permissions |
| Less crypto code | Application owns format, nonce, AAD, and migration |

Do not confuse enabling default SSE-KMS on a bucket with having the application encrypt payloads before upload.

## 9. Integrating Azure Key Vault Keys

### 9.1. Key Vault keys vs. secrets

- **Key Vault Secret:** stores a sensitive value such as a password or token.
- **Key Vault Key:** a cryptographic key object supporting operations such as wrap/unwrap, encrypt/decrypt, or sign/verify depending on key type.
- **Key Vault Certificate:** manages certificates and links to corresponding keys/secrets per the service model.

Envelope encryption should use a **Key Vault Key** for the KEK—never store plaintext DEKs in a Secret. You can use Azure Key Vault or Managed HSM depending on key material protection and isolation requirements.

### 9.2. Wrap/unwrap DEK with RSA-OAEP-256

Example using the Azure SDK for Java:

~~~java
CryptographyClient cryptoClient = new CryptographyClientBuilder()
        .keyIdentifier(keyIdentifier)
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

WrapResult wrapped = cryptoClient.wrapKey(
        KeyWrapAlgorithm.RSA_OAEP_256,
        plaintextDek);

byte[] wrappedDek = wrapped.getEncryptedKey();

UnwrapResult unwrapped = cryptoClient.unwrapKey(
        KeyWrapAlgorithm.RSA_OAEP_256,
        wrappedDek);

byte[] plaintextDek = unwrapped.getKey();
~~~

Import and package names may vary by `azure-security-keyvault-keys` version; check your Azure SDK BOM. The key must be an RSA key with a size and attributes compatible with the wrapping algorithm. `RSA-OAEP-256` is suitable for wrapping a 32-byte DEK; never use RSA to encrypt PDFs or large objects directly.

### 9.3. Permissions and identity

The workload needs a Microsoft Entra ID token and permission for cryptographic operations on the key. With Azure RBAC, a role like **Key Vault Crypto User** is suitable for applications performing allowed cryptographic operations; exact permissions also depend on key type, operation, and scope. Do not use **Key Vault Secrets User** in place of Key Vault Key permissions.

If Azure Storage uses CMK, the principal granted Key Vault permissions may be the **Storage account's managed identity** or the service principal required by the service, not necessarily Spring Boot's identity. Keep roles distinct:

- Spring Boot identity: permissions to call Blob/Key Vault APIs if the application wraps/unwraps directly.
- Storage service identity: permissions to use the key for SSE-CMK.
- Key administrator: permissions to create/rotate/disable keys and manage policies.

### 9.4. Key versions

A Key Vault key identifier can include a version. The envelope should store the key ID/version that wrapped the DEK. When a new key becomes the current version, older DEKs must still be unwrappable using the old version until rewrapping completes or retention ends. Never delete/disable an old version merely because a new version was created.

## 10. Integrating Google Cloud KMS

### 10.1. Encrypting DEKs with Cloud KMS

Google Cloud KMS offers `Encrypt`/`Decrypt` APIs suitable for protecting small DEKs. Application payloads are encrypted locally with AES-GCM; only the DEK is sent to KMS.

Java client example:

~~~java
CryptoKeyName keyName = CryptoKeyName.of(
        projectId, locationId, keyRingId, cryptoKeyId);

EncryptResponse response = kmsClient.encrypt(
        EncryptRequest.newBuilder()
                .setName(keyName.toString())
                .setPlaintext(ByteString.copyFrom(plaintextDek))
                .setAdditionalAuthenticatedData(ByteString.copyFrom(contextBytes))
                .build());

byte[] wrappedDek = response.getCiphertext().toByteArray();
~~~

When decrypting the DEK:

~~~java
DecryptResponse response = kmsClient.decrypt(
        DecryptRequest.newBuilder()
                .setName(keyName.toString())
                .setCiphertext(ByteString.copyFrom(wrappedDek))
                .setAdditionalAuthenticatedData(ByteString.copyFrom(contextBytes))
                .build());

byte[] plaintextDek = response.getPlaintext().toByteArray();
~~~

The Cloud KMS `Encrypt` API has a plaintext size limit (64 KiB for symmetric encrypt); therefore only send small DEKs, not large files/objects. AAD must match identically on decrypt. For key versions, the API uses the primary version on encrypt, and the ciphertext carries metadata so KMS identifies the matching version for decryption.

### 10.2. IAM and service accounts

The principal calling Cloud KMS needs appropriate permissions, such as the `roles/cloudkms.cryptoKeyEncrypterDecrypter` role on the CryptoKey or an appropriate scope. Use Workload Identity Federation/Workload Identity in cloud environments instead of loading long-lived service account JSON keys into containers.

If using CMEK for Cloud Storage, the **Cloud Storage service agent** needs encrypt/decrypt permissions on the CryptoKey; this permission is separate from the Spring Boot service account's permissions to call Storage APIs.

### 10.3. Cloud KMS and envelope encryption

Google Cloud KMS also supports application-level client-side encryption libraries in several languages/products. If building your own format, manage versioning, nonces, AAD, wrapped DEKs, and serialization as described earlier. Never mix a custom envelope format with a cloud library's format without a migration/compatibility plan.

## 11. Comparing Key Management Services

| Criterion | AWS KMS | Azure Key Vault / Managed HSM | Google Cloud KMS |
| --- | --- | --- | --- |
| Key resource | KMS key | Key Vault key / HSM key | CryptoKey and CryptoKeyVersion |
| DEK creation | `GenerateDataKey` | Generate DEK locally then `WrapKey` | Generate DEK locally then `Encrypt` |
| Wrap/unwrap | `Encrypt`/`Decrypt` or `GenerateDataKey`/`Decrypt` | `WrapKey`/`UnwrapKey` | `Encrypt`/`Decrypt` |
| Workload identity | IAM role, STS, workload identity | Microsoft Entra ID, Managed Identity | Service account, Workload Identity Federation |
| Operation permissions | IAM + key policy/grants | Azure RBAC or access policies | IAM roles on the key |
| Key rotation | Automatic/on-demand rotation depending on key type | Create new version/rotation policy depending on key type | Create new CryptoKeyVersion and switch primary |
| Auditing | CloudTrail/KMS events | Azure Monitor/Key Vault audit logs | Cloud Audit Logs |
| Service-side encryption | S3, RDS, and KMS-integrated services | Storage, SQL, and CMK-integrated services | Cloud Storage, BigQuery, Cloud SQL, and CMEK-enabled services |

Each provider represents key versions, policies, and principals differently. Adapters should abstract specific SDK APIs, but **must not hide differences in authorization, key versioning, or auditing**.

## 12. Key Lifecycle Management

Keys are assets with a lifecycle. Creating a new key is only the beginning.

### 12.1. Operational states

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Enabled
    Enabled --> Rotating
    Rotating --> Enabled: New writes use new version
    Enabled --> Disabled: Suspend use
    Disabled --> Enabled: Restore if safe
    Disabled --> ScheduledForDestruction
    ScheduledForDestruction --> Disabled: Cancel if supported
    ScheduledForDestruction --> Destroyed
    Destroyed --> [*]
~~~

Stages:

1. **Create:** create the key with appropriate type/attributes/region.
2. **Enable:** grant least-privilege access to required workloads.
3. **Use:** record key references/versions and audit operations.
4. **Rotate:** move new encryption operations to a new version.
5. **Rewrap/Re-encrypt:** process DEKs or encrypted data per policy.
6. **Disable:** suspend use of old versions after verifying no dependencies remain.
7. **Destroy:** execute only after retention, backup, and recovery validation.

### 12.2. Rotation does not mean re-encryption

During KMS key rotation, distinguish between:

| Action | What changes? |
| --- | --- |
| KMS automatic rotation | New key material version is generated/used for new encrypt operations; KMS typically still decrypts older ciphertexts with the needed version |
| Creating a new key version | Primary/current version may change; already encrypted objects retain their old envelopes |
| Rewrapping DEKs | Plaintext DEK is unwrapped with the old KEK and re-wrapped with the new KEK; payload ciphertext does not change |
| Re-encrypting payloads | Data is decrypted and re-encrypted with a new DEK; I/O intensive and may require downtime/streaming |
| Disabling/destroying old keys | Can make older envelopes/objects undecryptable if they still depend on that key |

**Key rotation does not automatically re-encrypt all objects or databases.** With SSE, the service manages how keys are used for new data and how old data is decrypted according to service behavior. With CSE, the application manages wrapped DEKs and may need to rewrap them.

### 12.3. Rewrapping DEKs

When you only want to change the KEK while keeping the payload ciphertext:

1. Read the envelope and wrapped DEK.
2. Use the old KEK to unwrap the DEK in memory.
3. Use the new KEK to wrap the same DEK.
4. Write the updated envelope metadata with the new key reference/version.
5. Verify decryption works with the new key.
6. Only consider disabling the old key after all objects/backups/replicas have been transitioned.

Payload ciphertext does not change because the DEK remains the same. Rewrapping reduces cost compared to decrypting/re-encrypting large payloads. However, if a DEK has been compromised or its algorithm is weak, rewrapping is not enough; generate a new DEK and re-encrypt the payload.

### 12.4. Backup, retention, and recovery

Before disabling/destroying a key, verify:

- How many objects/rows/backups/snapshots still depend on this key version?
- Are there replicas or archives in other regions/accounts/projects?
- Can old backups still be restored using available keys?
- Are Key Vault soft-delete/purge protection or deletion protection mechanisms enabled per policy?
- Who is authorized to schedule deletion/purge?
- Is there a procedure to recover keys/identities/permissions after an incident?

Losing a key can mean permanent data loss. Never delete a key just because live object storage no longer references it; backups, archives, and offline copies may still need the old key.

## 13. Access Permissions and Separation of Duties

### 13.1. Minimal runtime permissions

| Principal | Recommended permissions |
| --- | --- |
| Spring Boot workload | Storage API calls and only the KMS operations needed for business logic |
| Storage service identity | CMK access as required by the SSE service |
| Key administrator | Create, rotate, disable, and manage policies |
| Security auditor | Read audit/config metadata; no default decrypt permission |
| Backup/recovery operator | Recovery permissions under controlled procedures with auditing |

Separate **encrypt** and **decrypt** permissions if the threat model requires it. A write-only archiving workload may be allowed to generate/encrypt DEKs without read/unwrap permissions. An analytics service may be granted decrypt access only for a specific dataset/tenant.

### 13.2. Scope and policy

- Create separate keys for production and non-production.
- Consider separate keys per tenant or data classification if isolation is required.
- Scope permissions to specific key resources; avoid wildcards across entire accounts/subscriptions/projects.
- Use conditions/context to constrain encryption context when supported by KMS.
- Never share a single KMS key across all applications merely for convenience.
- Monitor changes to key policies, grants, IAM bindings, and access policies.
- Strictly govern unwrap/decrypt permissions because they turn ciphertext back into plaintext.

### 13.3. Authorization before unwrapping

A file download API must not call KMS decrypt before verifying the caller has permission to read the object. Proper sequence:

1. Authenticate the calling user/service.
2. Check tenant/object ownership and business authorization.
3. Read envelope metadata.
4. Verify the key reference and context belong to the authorized object.
5. Call KMS unwrap.
6. Decrypt with AES-GCM and return the data.

Unwrapping before checking permissions records unnecessary decryptions in KMS audit logs and can create side channels. Apply rate limiting and monitor anomalous decrypt operations.

## 14. Protecting Data in Spring Boot

### 14.1. Configure key references, never raw KEKs

Example application configuration:

~~~yaml
app:
  encryption:
    provider: azure-key-vault
    key-reference: "${APP_ENCRYPTION_KEY_ID}"
    algorithm: AES-256-GCM
    envelope-version: 1
~~~

`APP_ENCRYPTION_KEY_ID` is only the key's resource identifier, not key material or a password. Credentials to call KMS come from Managed Identity, an AWS IAM role, or Google Workload Identity.

Never place plaintext DEKs/KEKs in `application.yml`, Config Server, environment variables, Docker images, or databases.

### 14.2. Separate adapters by provider

A package structure might look like:

~~~text
com.example.protection
  DataKeyProvider.java
  DataKeyMaterial.java
  EncryptedEnvelope.java
  EnvelopeEncryptionService.java
  aws/
    AwsKmsDataKeyProvider.java
  azure/
    AzureKeyVaultDataKeyProvider.java
  gcp/
    GoogleCloudKmsDataKeyProvider.java
~~~

Business services depend on `DataKeyProvider` and `EnvelopeEncryptionService`. Adapters contain SDK and identity details. This lets you unit-test AES-GCM without real cloud calls while integration-testing each adapter separately.

### 14.3. Never reuse one key for every purpose

Separate keys by purpose:

- DEKs for payloads/objects.
- KEKs for wrapping DEKs.
- Keys for signing tokens or JWTs.
- Keys for signing webhooks.
- Keys for database field encryption.

Never reuse the same key for encryption, signing, TLS, and password hashing. User passwords should use dedicated password hashing (Argon2id/bcrypt/PBKDF2 per policy), not reversible AES/KMS encryption like an ordinary secret.

### 14.4. Limit plaintext lifetime

- Decrypt only when business logic requires it.
- Avoid caching plaintext long-term.
- Never log requests/responses containing sensitive data.
- Restrict heap dumps, core dumps, and crash reports.
- Perform best-effort zeroing of byte arrays holding DEKs/plaintext once no longer needed.
- Use streaming to avoid holding entire large files on the heap.
- Protect temporary files and swap per environment policy.
- Never send plaintext to tracing/metrics/error reporting.

Zeroing byte arrays in Java is best-effort; the JVM, JIT, or crypto provider may retain internal copies. For stringent key-memory control requirements, evaluate HSMs, process isolation, or specialized crypto providers.

## 15. Testing Encryption and Key Management

### 15.1. Unit tests for AES-GCM

Test round-trip behavior:

~~~java
@Test
void encryptThenDecryptReturnsOriginal() throws Exception {
    byte[] plaintext = "contract-data".getBytes(StandardCharsets.UTF_8);
    byte[] aad = "tenant=tenant-42;object=contract-1"
            .getBytes(StandardCharsets.UTF_8);

    EncryptedEnvelope envelope = service.encrypt(
            plaintext, aad, "test-key-reference", java.util.Map.of());

    byte[] restored = service.decrypt(envelope, aad, java.util.Map.of());

    assertThat(restored).isEqualTo(plaintext);
}
~~~

Unit tests use a fake `DataKeyProvider` without calling KMS. Also add tamper tests:

- Modify a single ciphertext byte.
- Modify the nonce.
- Modify the wrapped DEK.
- Change tenant/object AAD.
- Use a nonexistent key reference.
- Change format version/algorithm.
- Pass an envelope missing fields or exceeding size limits.

Modifying ciphertext, nonce, or AAD must cause GCM authentication to fail; never return plaintext.

### 15.2. Testing permissions and provider adapters

Using a dev key in KMS/Key Vault/Cloud KMS:

1. Workload has `GenerateDataKey`/`WrapKey`/`Encrypt` permissions.
2. Workload has `Decrypt`/`Unwrap` permissions.
3. A principal lacking decrypt permission must be denied.
4. A disabled key or unusable version must produce a clear error.
5. Wrong encryption context/AAD must fail decryption.
6. Cross-tenant object access must be blocked by business authorization before unwrapping.
7. Logs/audit trails must not contain plaintext DEKs, payloads, or secrets.

### 15.3. Testing rotation

| Scenario | Expected result |
| --- | --- |
| Create new KEK version | New writes use version per policy |
| Old envelope using old KEK version | Remains decryptable throughout retention period |
| Rewrap DEK to new KEK | Payload ciphertext unchanged, envelope decrypts cleanly |
| Disable old key prematurely | Tests detect objects/backups still depending on it |
| Re-encrypt with new DEK | Plaintext before/after identical, new metadata valid |
| KMS timeout/429 | Bounded retries, no infinite loop |
| KMS unavailable | Fail closed for data needing decryption; no raw-key fallback |

### 15.4. Testing backup recovery

A backup process is only complete once decryption is proven:

1. Create an object and envelope in a dev environment.
2. Back up the object, metadata, and wrapped DEK.
3. Restore to a test bucket/account/project.
4. Grant KMS permissions per recovery procedure.
5. Decrypt and compare plaintext checksums.
6. Verify old key versions remain usable.
7. Record recovery time and operator.

Never test key destruction on a production key to prove backups. Use a dedicated key for destructive lifecycle tests.

## 16. Choosing a Model Based on Requirements

| Requirement | Suitable model | Rationale |
| --- | --- | --- |
| Protect disks/backups; service may read plaintext | SSE/TDE with provider-managed or CMK | Transparent, minimal crypto code |
| Control keys and audit service decrypt actions | SSE with CMK | Dedicated KMS policy and audit trail |
| Storage operators must not read object contents | CSE envelope encryption | Storage holds only ciphertext |
| Encrypt only a few PII fields in a database | Field-level CSE | Limits plaintext scope |
| Large files requiring streaming | Envelope + chunked AEAD | Avoids loading entire file into memory |
| Multiple services/tenants with distinct permissions | Separate DEK per object/tenant and scoped KEK policies | Isolates blast radius and decrypt permissions |
| Need to search encrypted contents | Requires custom index/token design | Standard ciphertext cannot be searched/filtered directly |

Do not apply CSE mechanically to every piece of data. CSE carries higher KMS cost, latency, key lifecycle overhead, and recovery risk than SSE. Choose based on data classification and threat model.

## 17. Common Errors and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Upload succeeds but app cannot decrypt | Missing wrapped DEK, wrong key reference, or AAD mismatch | Inspect envelope metadata and context |
| KMS returns `AccessDenied`/403 | Principal lacks key operation permissions or key policy denies access | Check actual runtime identity, scope, and policies |
| AES-GCM throws `AEADBadTagException` | Wrong ciphertext/nonce/AAD, tampered data, or wrong DEK | Reject plaintext; investigate integrity and metadata |
| KMS decrypt succeeds but AES fails | DEK does not match ciphertext or format mismatch | Check version/algorithm/serialization |
| Old objects unreadable after rotation | Old key version disabled/destroyed or metadata lost | Restore permissions/key per procedure; verify backups |
| SSE-KMS upload rejected | Missing KMS `GenerateDataKey` or key policy blocks S3 service/request | Inspect bucket policy, IAM, key policy, and encryption settings |
| Azure Storage CMK not working | Storage identity lacks Key Vault key permissions or key unavailable | Check Storage account identity, Key Vault networking, and roles |
| GCS CMEK returns permission error | Cloud Storage service agent lacks permissions on CryptoKey | Grant role to the service agent on the right project/key |
| Latency increases when reading files | KMS unwrap on every object or retries | Safely cache metadata, optimize batching/streaming, check quotas |
| Rotation does not change keys on old data | Rotation only affects new encryption operations | Plan rewrap/re-encrypt according to policy |
| Heap dump contains plaintext/DEKs | Plaintext resides in JVM memory | Shorten lifetime, restrict dumps, stream data, harden process access |

## 18. Comprehensive Hands-On Exercise

`document-service` must store PDF contracts and metadata for multiple tenants:

- Object storage has SSE enabled with a customer-managed key.
- PDF contents must use CSE so storage operators cannot read plaintext.
- Each object has its own AES-256-GCM DEK.
- DEKs are wrapped by an environment-specific KMS key.
- Tenant/object metadata is bound via AAD.
- A KEK rotation process exists without re-encrypting payloads when only the KEK changes.

**Tasks:**

1. Choose SSE-KMS/CMEK for the storage layer and explain the value of the additional SSE layer.
2. Design an envelope format with `formatVersion`, `algorithm`, `keyReference`, `wrappedDek`, `nonce`, and `ciphertext`.
3. Generate a separate DEK per object using AES-GCM and a 12-byte nonce.
4. Bind tenant ID/object ID into AAD without placing PII in AWS KMS encryption context.
5. Grant decrypt permissions only to the contract-reading service; give the upload service only permissions needed to generate/wrap DEKs if design permits.
6. Write unit tests for ciphertext tampering and mismatched AAD.
7. Write integration tests for KMS permissions, key versions, and backup restoration.
8. Rewrap DEKs from the old KEK to the new KEK and verify payload ciphertext does not change.
9. Disable the old key only after inventorying all objects, backups, and replicas.

**Self-assessment questions:**

- Why does SSE-KMS not stop a storage service from returning plaintext to an authorized reading principal?
- How does SSE-C differ from CSE?
- Why does KMS only wrap the DEK instead of encrypting the PDF file directly?
- Why must a GCM nonce be unique per DEK?
- Is AAD encrypted? Where should tenant/object IDs be placed?
- When changing a KEK, when is rewrapping the DEK sufficient?
- Why does rotation not imply automatic re-encryption?
- Which principal needs KMS permissions when using Azure Storage CMK or GCS CMEK?
- What happens if an old key is destroyed while backups still require it for decryption?

**Guided answers:** SSE services decrypt when an authorized principal reads; SSE-C still encrypts server-side whereas CSE encrypts before sending; small DEKs avoid KMS size limits and latency; nonce reuse breaks GCM security; AAD is authenticated but not encrypted; rewrapping preserves the DEK so payload ciphertext stays unchanged; key rotation generally does not rewrite existing ciphertexts; the Storage service agent uses the CMK per service rules; losing an old key can cause permanent data loss.

## 19. Official References

- [AWS KMS – GenerateDataKey](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html): generating plaintext data keys and encrypted data keys for envelope encryption.
- [AWS KMS – Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html): KMS AAD, decrypt matching requirements, and non-secret metadata notes.
- [AWS S3 – Using server-side encryption with AWS KMS keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html): SSE-KMS, permissions, and key behavior.
- [AWS S3 – Client-side encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingClientSideEncryption.html): client-side encryption and envelope concepts.
- [Microsoft Learn – Azure Storage encryption for data at rest](https://learn.microsoft.com/en-us/azure/storage/common/storage-service-encryption): encryption at rest and customer-managed keys.
- [Microsoft Learn – Customer-managed keys for Azure Storage](https://learn.microsoft.com/en-us/azure/storage/common/customer-managed-keys-overview): Key Vault/Managed HSM and Storage identity.
- [Microsoft Learn – Key Vault cryptography](https://learn.microsoft.com/en-us/azure/key-vault/keys/about-keys-details): key types, cryptographic operations, wrap/unwrap, and versions.
- [Google Cloud – Cloud Storage encryption](https://cloud.google.com/storage/docs/encryption): Google-managed, CMEK, and customer-supplied keys.
- [Google Cloud – Use customer-managed encryption keys](https://cloud.google.com/kms/docs/cmek): CMEK integration, service agents, and KMS permissions.
- [Google Cloud KMS – Encrypt and decrypt data](https://cloud.google.com/kms/docs/encrypt-decrypt): Encrypt/Decrypt APIs and payload limits.
- [Google Cloud – Envelope encryption](https://cloud.google.com/kms/docs/envelope-encryption): DEK/KEK and large-data encryption model.
- [Java Cryptography Architecture – Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): AES-GCM, authenticated encryption, and JCA APIs.

**Remember:** SSE protects data in storage and is generally transparent to applications; CSE keeps plaintext within the authorized application scope; envelope encryption uses DEKs to encrypt payloads and KMS/Key Vault to protect DEKs. A solid design keeps **ciphertext, metadata, key references, unwrap permissions, rotation, and backups** aligned throughout the data lifecycle.
