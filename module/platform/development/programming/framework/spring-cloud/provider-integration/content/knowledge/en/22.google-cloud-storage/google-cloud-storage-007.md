# Encryption, Versioning, Retention, and Object Lifecycle

## 1. Protecting Data Throughout Its Lifecycle

A Spring Boot application storing files in Google Cloud Storage (GCS) must answer more questions than just how to upload and download successfully. How must data be encrypted? Who manages the keys? If a user accidentally overwrites or deletes an object, can it be recovered? What is the minimum duration documents must be retained? When the business retention period ends, how can objects automatically move to a cheaper storage class or be deleted?

Cloud Storage provides several mechanisms to address these requirements:

- **Encryption:** encrypts data at rest using Google-managed keys, Cloud KMS customer-managed keys, customer-supplied keys, or application-side encryption.
- **Object Versioning:** preserves previous object versions when a live object is replaced or deleted.
- **Soft Delete:** retains deleted objects for a period so they can be restored.
- **Retention policies and holds:** prevent objects from being deleted or replaced before allowed.
- **Object Lifecycle Management:** automatically transitions storage classes or deletes objects when configured conditions are met.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. This lesson focuses on data protection, version management, retention periods, and automated object lifecycle management in Cloud Storage.

After this lesson, you will be able to:

- Distinguish Google-managed encryption, CMEK, CSEK, and client-side encryption.
- Configure a Cloud KMS key for a bucket or individual objects.
- Understand the role of the service agent, Cloud KMS permissions, and risks of disabling/destroying key versions.
- Explain Object Versioning, noncurrent versions, and generations.
- Restore soft-deleted objects and understand the limits of the restore process.
- Design bucket retention policies, Bucket Lock, Object Retention Lock, and object holds.
- Write lifecycle rules by age, prefix, storage class, noncurrent time, and number of newer versions.
- Configure these features using the Java Storage client and gcloud CLI.
- Account for IAM, costs, audit logs, and recovery testing in Spring Boot applications.

> **Version scope:** Examples use the Google Cloud Storage Java client (artifact com.google.cloud:google-cloud-storage) and gcloud CLI. Manage dependencies using a BOM matching your project's Java/Spring baseline and check the Javadoc for the actual resolved version. Buckets, projects, objects, and keys in examples are illustrative data. Operations that lock a retention policy or destroy a Cloud KMS key version may be irreversible; execute them only after reviewing related procedures and resources.

## 2. The Big Picture

Encryption, versioning, soft delete, retention, and lifecycle are not different names for the same feature. They protect against different risks.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> WRITE["Create / update object"]
    WRITE --> ENC["Encryption at rest"]
    ENC --> LIVE["Live object generation"]
    LIVE --> VERSION["Object Versioning"]
    LIVE --> RETENTION["Retention policy / holds"]
    LIVE --> LIFECYCLE["Lifecycle Management"]
    LIVE --> DELETE["Delete request"]
    DELETE --> SOFT["Soft Delete"]
    VERSION --> NONCURRENT["Noncurrent generations"]
    SOFT --> RESTORE["Restore as a new live generation"]
    NONCURRENT --> CLEAN["Lifecycle cleanup"]
    SOFT --> CLEAN
    KMS["Cloud KMS / key governance"] -. "CMEK key access" .-> ENC
    AUDIT["IAM + Audit Logs + monitoring"] -. "Governance" .-> WRITE
    AUDIT -. "Governance" .-> DELETE
~~~

| Mechanism | Question addressed | What it does not solve by itself |
| --- | --- | --- |
| Encryption | Who can decrypt stored data? | Does not stop an authorized reader from downloading the object |
| Object Versioning | Can an earlier byte version be retrieved? | Does not protect against deleting the entire bucket |
| Soft Delete | Can a recently deleted object/bucket be recovered? | Does not provide a readable version while soft-deleted |
| Retention policy | What is the minimum time an object must be kept? | Does not create an independent backup copy |
| Object hold | Can deletion/replacement of a specific object be paused? | Does not determine when business logic should release the hold |
| Lifecycle Management | When to transition storage class or delete objects? | Does not bypass retention or holds |

A design can combine multiple mechanisms. For example, a bucket storing contract records may use CMEK, a locked retention policy, soft delete, and lifecycle rules to manage costs. A bucket storing temporary files may use default encryption, a short or disabled soft delete per policy, no Object Versioning, and lifecycle cleanup rules.

## 3. Encryption Options in Cloud Storage

Cloud Storage always encrypts data server-side before writing it to disk. Default encryption is managed by Google and requires no key creation or extra encryption steps in application code.

Beyond default encryption, Cloud Storage offers three main options:

| Mechanism | Who manages the key? | Where is the key used? | Use case |
| --- | --- | --- | --- |
| Google-managed encryption (default) | Google | Cloud Storage encrypts/decrypts inside the service | Most applications needing encryption at rest |
| Customer-managed encryption key (CMEK) | Customer manages via Cloud KMS | Cloud Storage service agent uses keys in Cloud KMS | Compliance, key lifecycle control, auditing |
| Customer-supplied encryption key (CSEK) | Customer manages outside GCS | Client sends key in requests needing encryption/decryption | Systems with external key management workflows |
| Client-side encryption | Customer application or key system | Encrypted before sending bytes to GCS | Need data encrypted before leaving the application |

An object uses only one of these object encryption approaches at a time. CMEK and CSEK are server-side encryption: Cloud Storage receives data and encrypts it before storing. Client-side encryption encrypts data before sending; afterward Cloud Storage still encrypts the ciphertext with default server-side encryption.

### 3.1. Google-Managed Encryption

This is the default option. Cloud Storage manages key material, encryption/decryption, and internal key rotation automatically. Applications continue calling Storage.create, Storage.reader, and Blob.downloadTo as usual.

Advantages:

- No private keys or key rings to manage.
- No extra Cloud KMS permissions needed for the service agent.
- No upload/download code changes required.
- Fits the majority of applications requiring encryption at rest.

Default encryption does not make an object private in the IAM sense. Principals with storage.objects.get can still read objects via the API. Continue designing IAM, UBLA, Public Access Prevention, and business authorization.

### 3.2. When to Choose CMEK?

Choose CMEK when the organization needs to manage key lifecycles, control key usage permissions, audit encryption activity, or satisfy compliance policies requiring customer-controlled keys.

CMEK allows controlling:

- Key ring and key location.
- Key versions, rotation schedule, and primary version.
- Principals/service agents allowed to use the key.
- Audit logs of key usage.
- When key versions are disabled or destroyed.

CMEK does not mean all object metadata is encrypted with that key. Cloud Storage uses CMEK for object data and certain checksums/hashes; much of the remaining metadata is still protected by service-managed server-side keys. Therefore, do not put sensitive information into object names, bucket names, or custom metadata.

### 3.3. When to Choose CSEK?

CSEK fits when the organization operates an external key management system outside Google Cloud and wants to supply an AES-256 key on every request involving the object.

Cloud Storage does not store raw CSEKs. On upload, the application sends the key; when reading, downloading, or copying the object, the application must supply the exact key used earlier. If the key is lost, data encrypted with that key cannot be decrypted.

CSEK increases key management responsibility substantially. Use it only with proven backup, rotation, recovery, and key-material access control processes.

### 3.4. When Is Client-Side Encryption Needed?

Client-side encryption is useful when the application must ensure plaintext is never sent to Cloud Storage. The application encrypts bytes before uploading and decrypts after downloading. Cloud Storage receives only ciphertext.

In return, the application must manage:

- Algorithms, nonces/IVs, and ciphertext format.
- Key encryption keys and data encryption keys.
- Key rotation and re-encryption.
- Integrity/authentication tags.
- Encryption format versioning.
- Recovery capabilities if keys are lost or revoked.

Do not invent custom cryptographic algorithms. Use vetted cryptographic libraries and a dedicated key management system.

## 4. Configuring CMEK with Cloud KMS

### 4.1. Components and Access Flow

When a bucket uses CMEK, the project's Cloud Storage service agent performs encryption/decryption using the Cloud KMS key. The application still calls the Storage API using its normal workload identity and object IAM permissions.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant IAM as IAM
    participant GCS as Cloud Storage
    participant Agent as Storage service agent
    participant KMS as Cloud KMS

    App->>IAM: Authenticate workload
    App->>GCS: Upload object
    GCS->>Agent: Request CMEK encryption
    Agent->>KMS: Encrypt with current key version
    KMS-->>Agent: Wrapped data key
    Agent-->>GCS: Encryption complete
    GCS-->>App: Object metadata + generation
    App->>GCS: Download object
    GCS->>Agent: Request decryption
    Agent->>KMS: Decrypt data key
    KMS-->>Agent: Data key
    Agent-->>GCS: Decryption complete
    GCS-->>App: Object bytes
~~~

The Cloud Storage service agent has the form:

`service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com`

Retrieve the exact service agent for the project containing the bucket before granting permissions. Do not use the Spring Boot runtime service account in place of the service agent in CMEK configuration.

### 4.2. IAM Permissions for CMEK

Grant `roles/cloudkms.cryptoKeyEncrypterDecrypter` to the Cloud Storage service agent on the specific CryptoKey. This role allows the service agent to encrypt and decrypt with that key.

Important requirements:

- The Cloud KMS key ring must be in a location compatible with the bucket.
- Multi-region or dual-region buckets follow corresponding location rules; do not arbitrarily pick the nearest single region.
- Use only symmetric encryption keys for Cloud Storage CMEK.
- The Cloud KMS API and Cloud Storage API must be enabled.
- The runtime application still needs IAM permissions storage.objects.create/get/list/delete according to business operations.
- Key administrators and bucket operators can be two separate groups of principals.

Do not grant roles/cloudkms.admin to a runtime service just to upload files. The service agent needs encrypt/decrypt permission; the application does not need to read key material directly.

### 4.3. Creating a Key and Granting Permissions

Example creating a key ring and key in a location compatible with the bucket:

~~~bash
gcloud kms keyrings create document-keyring \
  --location=asia-southeast1 \
  --project=training-platform-security

gcloud kms keys create document-key \
  --keyring=document-keyring \
  --location=asia-southeast1 \
  --purpose=encryption \
  --project=training-platform-security
~~~

Retrieve the service agent of the project containing the bucket:

~~~bash
gcloud storage service-agent \
  --project=training-platform-dev
~~~

Grant encrypt/decrypt permission to the service agent on the CryptoKey:

~~~bash
gcloud kms keys add-iam-policy-binding document-key \
  --keyring=document-keyring \
  --location=asia-southeast1 \
  --project=training-platform-security \
  --member="serviceAccount:service-PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
~~~

Replace PROJECT_NUMBER with the actual project number of the project containing the bucket. Examples are illustrative only; verify key location, key-owning project, and service agent before applying.

### 4.4. Setting a Default CMEK on a Bucket

A bucket can configure a default KMS key so new objects use that key when a request does not specify another encryption method.

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --default-encryption-key=projects/training-platform-security/locations/asia-southeast1/keyRings/document-keyring/cryptoKeys/document-key
~~~

Changing the default key affects only objects created after the setting takes effect. Existing objects keep using the key version they were encrypted with until rewritten.

### 4.5. Specifying CMEK for a Single Object

The Java client supports Storage.BlobWriteOption.kmsKeyName:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadWithCmek(
        Storage storage,
        String bucket,
        String objectName,
        String kmsKeyName,
        String content) {

    BlobInfo info = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("text/plain; charset=utf-8")
            .build();

    return storage.create(
            info,
            content.getBytes(StandardCharsets.UTF_8),
            Storage.BlobWriteOption.kmsKeyName(kmsKeyName));
}
~~~

kmsKeyName is the full resource name of the CryptoKey. If the bucket has a default KMS key and the request specifies no other key, Cloud Storage uses the default key. If the request specifies a specific key, that key takes precedence for the object.

## 5. Rotation, Key Replacement, and Re-Encryption

### 5.1. Key Rotation Does Not Automatically Re-Encrypt Existing Objects

Cloud KMS can create new key versions and switch the primary version. New encryption operations use the new primary version. Existing objects continue to be decrypted using the key version used when the object was written; older key versions must remain enabled.

Example:

| Time | Primary key version | New object | Existing object |
| --- | --- | --- | --- |
| T1 | version 1 | A uses version 1 | A uses version 1 |
| T2 | version 2 | B uses version 2 | A still uses version 1 |
| T3 | version 3 | C uses version 3 | A/B still use older key versions |

Do not disable or destroy version 1 simply because the primary version moved to version 2. Objects encrypted with version 1 cannot be downloaded, copied, or rewritten if that version is disabled or destroyed.

### 5.2. Re-Encrypting Existing Objects

To move an object to a new key or key version, rewrite the object. This operation reads data using the current key and writes the object back using the target key. You can use gcloud storage objects update or the Storage rewrite/copy API.

~~~bash
gcloud storage objects update \
  gs://training-documents-archive/contracts/contract-001.pdf \
  --encryption-key=projects/training-platform-security/locations/asia-southeast1/keyRings/document-keyring/cryptoKeys/document-key
~~~

With millions of objects, consider Storage batch operations, manifests, prefixes, rate limits, and error monitoring. After re-encryption, verify the object's kmsKeyName metadata points to the target key.

If the bucket enables Object Versioning, noncurrent generations may still use the old key. Re-encrypting the live generation does not automatically re-encrypt all noncurrent versions. Inventory and handle old versions per retention/lifecycle policies before disabling/destroying old keys.

### 5.3. Disabling and Destroying Key Versions

- **Disable:** objects using that key version temporarily cannot be decrypted. If the key version is re-enabled, data becomes accessible again.
- **Destroy:** key material is permanently destroyed; objects depending on that version can never be decrypted again.
- **Primary version disabled/destroyed:** the key cannot be used for new encryptions until a valid primary version exists.

Before disabling or destroying a version, list objects using that key version, re-encrypt them to another key or Google-managed encryption, check noncurrent versions, and monitor access errors. Destroying a key version still protecting objects can cause permanent data loss; storage charges for those objects continue until the objects themselves are deleted.

For objects in buckets with a locked retention policy or Object Retention Lock, Cloud KMS enforces additional constraints on destroying key versions. Do not treat locking retention as a reason to skip key management processes.

## 6. Customer-Supplied Encryption Keys (CSEK)

### 6.1. Key Model

CSEK uses an AES-256 key supplied by the application. The key must be Base64-encoded when passed to the Java API. Cloud Storage does not store the raw key; when reading an object, the client must supply the exact key used during upload.

CSEK fits when an organization operates an external key management system outside Google Cloud. In return, every component allowed to read the object must properly fetch the key from a key vault or Secret Manager. Never store CSEKs in source code, application.yml, container images, or logs.

### 6.2. Uploading with CSEK

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadWithCsek(
        Storage storage,
        String bucket,
        String objectName,
        String base64Aes256Key,
        String content) {

    BlobInfo info = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("text/plain; charset=utf-8")
            .build();

    return storage.create(
            info,
            content.getBytes(StandardCharsets.UTF_8),
            Storage.BlobWriteOption.encryptionKey(base64Aes256Key));
}
~~~

base64Aes256Key must be a properly formatted Base64-encoded AES-256 key. For example, do not derive keys directly from user passwords. Use a cryptographically secure random generator or a dedicated key management system.

### 6.3. Downloading with CSEK

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public void downloadWithCsek(
        Storage storage,
        String bucket,
        String objectName,
        String base64Aes256Key,
        Path destination) {

    Blob blob = storage.get(
            BlobId.of(bucket, objectName),
            Storage.BlobGetOption.decryptionKey(base64Aes256Key));

    if (blob == null) {
        throw new IllegalStateException("Object does not exist");
    }

    blob.downloadTo(
            destination,
            Blob.BlobSourceOption.decryptionKey(base64Aes256Key));
}
~~~

The example supplies the key for both the metadata GET and the download. Depending on the method called, the Java client may require BlobGetOption.decryptionKey or BlobSourceOption.decryptionKey. If the key is missing or incorrect, decryption fails.

### 6.4. Rotating CSEKs

To change a CSEK, Cloud Storage must read the object using the old key and rewrite it using the new key:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob rotateCsek(
        Storage storage,
        String bucket,
        String objectName,
        String oldBase64Key,
        String newBase64Key) {

    BlobId id = BlobId.of(bucket, objectName);

    Storage.CopyRequest request = Storage.CopyRequest.newBuilder()
            .setSource(id)
            .setSourceOptions(
                    Storage.BlobSourceOption.decryptionKey(oldBase64Key))
            .setTarget(
                    id,
                    Storage.BlobTargetOption.encryptionKey(newBase64Key))
            .build();

    return storage.copy(request).getResult();
}
~~~

For large objects, CopyWriter may require multiple RPCs; call copyChunk() until complete. Verify generation, checksum, and readability after rotation. If Object Versioning is enabled, noncurrent versions remain encrypted with the old key until handled separately.

### 6.5. CSEK Operational Rules

- Do not log raw keys or Base64 keys.
- Do not pass keys in URLs or query parameters.
- Store keys in Secret Manager or an appropriate HSM/key vault system.
- Restrict key retrieval permissions per workload and environment.
- Maintain a backup/recovery plan for key material.
- Associate an internal key version ID with object metadata in the database if lookup is needed.
- Test reading objects after application restarts and after key rotation.
- Do not destroy old keys while any object or noncurrent generation still depends on them.

## 7. Client-Side Encryption

With client-side encryption, the application encrypts bytes before sending them to GCS. Cloud Storage stores the ciphertext and still applies default server-side encryption or CMEK at the storage layer.

~~~mermaid
flowchart LR
    PLAIN["Plaintext"] --> APPENC["Application encryption"]
    APPENC --> CIPHER["Ciphertext"]
    CIPHER --> GCS["Cloud Storage"]
    GCS --> CIPHER2["Ciphertext download"]
    CIPHER2 --> APPDEC["Application decryption"]
    APPDEC --> PLAIN2["Plaintext"]
    KEY["Key management system"] -. "Encryption/decryption key" .-> APPENC
    KEY -. "Encryption/decryption key" .-> APPDEC
~~~

Client-side encryption can fit when security requirements forbid plaintext from ever appearing in the storage service. However, the application must design data format, key hierarchy, nonces/IVs, authenticated encryption, key rotation, and recovery itself.

A common design is envelope encryption:

1. Generate a Data Encryption Key (DEK) per object or group of objects.
2. Encrypt the file using authenticated encryption such as AES-GCM.
3. Use a Key Encryption Key (KEK) in Cloud KMS to wrap the DEK.
4. Store the ciphertext and wrapped DEK along with non-sensitive metadata.
5. When reading, unwrap the DEK, decrypt, and verify the authentication tag.

Do not store plaintext DEKs long-term. If object metadata stores the wrapped key or encryption format version, constrain that information and do not place secrets in object names.

## 8. Object Versioning

### 8.1. How Does Versioning Work?

Object Versioning is enabled at the bucket level. When a live object is replaced or deleted, the old version becomes a **noncurrent version** and remains in the bucket until explicitly deleted or removed by a lifecycle rule.

Each generation shares the same object name while having a distinct version identifier. Example:

| Time | Operation | Live generation | Noncurrent versions |
| --- | --- | --- | --- |
| T1 | Initial upload | 100 | None |
| T2 | Overwrite object | 101 | 100 |
| T3 | Overwrite again | 102 | 100, 101 |
| T4 | Delete live object | None | 100, 101, 102 |

A noncurrent version can be read if the request specifies its exact generation. When deleting a noncurrent version, if the bucket has Soft Delete enabled, that version can enter a soft-deleted state before permanent deletion.

### 8.2. Enabling Object Versioning

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --versioning
~~~

Disabling versioning:

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --no-versioning
~~~

Disabling versioning only stops the bucket from creating additional noncurrent versions on future replacements/deletions. Existing versions remain and must be managed separately.

### 8.3. Configuring via Java

~~~java
import com.google.cloud.storage.BucketInfo;
import com.google.cloud.storage.Storage;

public void enableVersioning(
        Storage storage,
        String bucketName) {

    BucketInfo bucketInfo = BucketInfo.newBuilder(bucketName)
            .setVersioningEnabled(true)
            .build();

    storage.update(bucketInfo);
}
~~~

This is a bucket administration operation requiring IAM permission storage.buckets.update. Use a test bucket when practicing and inspect current settings before making changes.

### 8.4. Reading a Specific Generation

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob readVersion(
        Storage storage,
        String bucket,
        String objectName,
        long generation) {

    return storage.get(
            BlobId.of(bucket, objectName, generation));
}
~~~

To download that version's bytes, pass a BlobId containing the generation to storage.reader() or Blob.downloadTo(). Do not rely on the object name alone when you must guarantee reading the exact approved version.

### 8.5. Restoring a Noncurrent Version

You can copy a noncurrent generation to become a new live object. Restoring creates a new generation; it does not turn the old generation back into the live generation with the same ID.

~~~bash
gcloud storage cp \
  gs://training-documents-archive/reports/annual.pdf#OLD_GENERATION \
  gs://training-documents-archive/reports/annual.pdf
~~~

Before restoring, inspect the current object and decide whether overwriting is allowed. If versioning is enabled, the overwritten live version becomes a noncurrent version.

### 8.6. Costs and Limitations

- Each noncurrent version is billed for storage according to its storage class.
- There is no default cap on how many object versions can accumulate.
- Object Versioning does not protect data if the entire bucket is deleted.
- Deleting noncurrent versions may incur early deletion charges depending on storage class and retention age.
- Lifecycle Management should be used to bound the count or age of noncurrent versions.

Versioning fits data that requires change history. If the primary goal is recovering accidentally deleted objects/buckets, evaluate Soft Delete.

## 9. Soft Delete

### 9.1. Mechanism

Soft Delete retains deleted objects or buckets for a configured period. During this window, the resource is in a soft-deleted state: it cannot be read or written like a live object, but it can be listed and restored. Once the retention duration expires, the resource is permanently deleted.

For buckets supporting Soft Delete, the current default configuration is typically 7 days. The retention duration can be customized from 3 to 90 days; set duration to 0 to disable. Some bucket types/capabilities do not support Soft Delete.

Soft-deleted objects do not appear in standard listings. You must pass a dedicated flag/filter to view them.

### 9.2. Listing Soft-Deleted Objects

~~~bash
gcloud storage ls \
  gs://training-documents-archive/** \
  --soft-deleted
~~~

Listing soft-deleted versions of a specific object:

~~~bash
gcloud storage ls \
  gs://training-documents-archive/reports/annual.pdf \
  --soft-deleted
~~~

### 9.3. Restoring a Generation

~~~bash
gcloud storage restore \
  gs://training-documents-archive/reports/annual.pdf#DELETED_GENERATION
~~~

The Java Storage client also provides Storage.restore(BlobId); BlobId must include the generation:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob restoreSoftDeleted(
        Storage storage,
        String bucket,
        String objectName,
        long deletedGeneration) {

    BlobId deletedVersion = BlobId.of(
            bucket,
            objectName,
            deletedGeneration);

    return storage.restore(deletedVersion);
}
~~~

Restore permissions include storage.objects.restore and storage.objects.create. If restoring overwrites an existing live object with the same name, the principal also needs appropriate delete permission.

### 9.4. Restore Creates a New Generation

Restore creates a new live object in the same bucket:

- The object receives a new generation.
- Metageneration resets to 1.
- Create time becomes the restore timestamp.
- Soft delete time and hard delete time are cleared from the new live object.
- If the bucket uses Autoclass, the restored object is placed in the Standard storage class.
- If a live object with the same name already exists, the existing object can be overwritten; with versioning enabled, the previous live version becomes noncurrent.

Therefore, restore is a new object write operation based on deleted data. Inspect the current live object and generation before restoring.

### 9.5. Configuring Soft Delete

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --soft-delete-duration=14d
~~~

This example sets the soft-deleted object retention window to 14 days. For buckets containing temporary data or caches with high object churn, Soft Delete can significantly increase storage costs. Balance the retention duration against actual recovery needs.

### 9.6. Comparing Object Versioning and Soft Delete

| Criterion | Object Versioning | Soft Delete |
| --- | --- | --- |
| Purpose | Preserve previous object versions | Recover deleted resources |
| Data state | Noncurrent versions are readable | Soft-deleted objects are not readable |
| Recovery | Copy version into a new live object | Restore into a new live object |
| Bucket deletion | Does not protect against bucket deletion | Can retain a deleted bucket during soft-delete window |
| Cost | Stores multiple generations | Stores deleted objects during retention duration |
| Automated management | Lifecycle rules delete noncurrent versions | Hard deletion when soft-delete duration expires |

Both Object Versioning and Soft Delete can be enabled together. This provides layered protection, but requires lifecycle rules and budgets to avoid retaining data longer than intended.

## 10. Bucket Retention Policy and Bucket Lock

### 10.1. What Is a Retention Policy?

A bucket retention policy sets a minimum retention duration for objects in the bucket. Objects cannot be deleted or replaced before reaching the configured retention age. The policy applies to both existing objects and new objects once effective.

For example, with a 365-day retention period:

- An object that has existed for 30 days must be kept for 335 more days.
- An object that has existed for 400 days is eligible for deletion/replacement if no holds or other retention rules apply.
- A newly overwritten object receives a new creation time and starts a fresh retention period.

If a delete/replace operation violates the bucket retention policy, Cloud Storage rejects it with an unmet retention policy error. Lifecycle Delete must also wait until objects satisfy the retention period.

### 10.2. Configuring the Retention Period

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --retention-period=365d
~~~

Reading the configuration:

~~~bash
gcloud storage buckets describe \
  gs://training-documents-archive \
  --format="default(retention_policy)"
~~~

The retention period is represented in seconds in the API. The CLI accepts days, weeks, months, years, or seconds. The maximum duration per current documentation is 100 years.

### 10.3. Bucket Lock

While a retention policy is unlocked, administrators can increase, decrease, or remove the policy. Once **locked**:

- The retention period cannot be reduced.
- The retention policy cannot be removed.
- The retention period can still be increased.
- The bucket cannot be deleted while any object has not yet met the retention period.
- Cloud Storage places a lien on the project to prevent deleting the project while the bucket lock remains active.

Locking is irreversible. This mechanism is meant for immutable storage/compliance requirements; establish an approval process and verify the bucket, retention period, and retention plan before locking.

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --lock-retention-period
~~~

Never run the lock command on a production bucket just to experiment. Use a dedicated test bucket, and lock only after thoroughly verifying long-term impacts.

### 10.4. Bucket Retention and Object Versioning

When Object Versioning is enabled, a live object can become a noncurrent version even before its retention period expires. However, that version must still be retained per the retention policy and cannot be deleted early. This preserves version history while preventing premature data deletion.

### 10.5. Retention Does Not Replace Backups

Bucket Lock prevents premature deletion of objects inside the bucket. It does not replace independent copies in another project/account, disaster recovery plans, or controls against project-wide issues. Design backup/replication based on your system's RPO/RTO requirements and failure domains.

## 11. Object Retention Lock and Object Holds

### 11.1. Object Retention Lock

A bucket retention policy applies the same minimum duration to all objects in the bucket. Object Retention Lock allows setting a specific retain-until timestamp and retention mode per individual object, provided object retention is enabled on the bucket.

Two modes to understand:

- **Unlocked:** the configuration can be modified or removed per service rules and appropriate permissions.
- **Locked:** the retain-until time cannot be shortened and the object's retention configuration cannot be removed; locking is irreversible.

Example updating retention configuration for a single object via CLI:

~~~bash
gcloud storage objects update \
  gs://training-documents-archive/contracts/contract-001.pdf \
  --retain-until=2028-02-15T05:30:00Z \
  --retention-mode=Unlocked
~~~

Before locking object retention, re-verify the retain-until date and the irreversible consequences. Do not apply retention lock to temporary objects, staging files, or component objects needing cleanup.

When modifying an existing Unlocked retention configuration to lock it or shorten retain-until, some gcloud commands require adding `--override-unlocked-retention`. Verify current state and administrative authorization before using this flag; it does not make the operation safe or reversible.

### 11.2. Temporary Hold

A temporary hold is a flag on an object. While enabled, the object cannot be deleted or replaced. When the hold is released, the bucket retention clock is not reset.

Use case: holding a file during an investigation or incident response, then releasing the hold once approved.

### 11.3. Event-Based Hold

An event-based hold retains an object until a business event occurs. When the event-based hold is released, the bucket retention policy duration begins counting from the time the hold is released.

Use case: a loan record must be retained until the loan is settled; after settlement, the system releases the hold and the policy retention period starts counting down.

### 11.4. Setting Holds in Java

The Java client provides BlobInfo.Builder.setTemporaryHold and setEventBasedHold. These APIs may carry Beta/Pre-GA status depending on library version; check the Javadoc and Pre-GA terms before using in production.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.BlobId;

BlobInfo heldObject = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName))
    .setContentType("application/pdf")
    .setTemporaryHold(true)
    .setEventBasedHold(true)
    .build();
~~~

When creating an object, pass BlobInfo to Storage.create. When updating holds on an existing object, read the Blob first, build BlobInfo via toBuilder(), update the hold flags, and update with generation/metageneration preconditions.

### 11.5. Impact Matrix

| Mechanism | Prevents deletion? | Prevents replacement? | Can metadata be edited? | How is time calculated? |
| --- | --- | --- | --- | --- |
| Bucket retention | Yes, before expiration | Yes, before expiration | Yes | From when the object was stored in the bucket |
| Object retention locked | Yes, before retain-until | Yes, before retain-until | Editable metadata may still be updated | According to the object's retain-until |
| Temporary hold | Yes | Yes | Yes | Does not reset bucket retention clock |
| Event-based hold | Yes | Yes | Yes | When released, bucket retention clock restarts |
| Soft Delete | After delete, retains soft-deleted copy | Not a pre-delete overwrite guard | Cannot edit soft-deleted objects | According to soft delete retention duration |

Object holds are not encryption or IAM. Principals still need appropriate permissions to set/release holds; releasing a hold should follow a business workflow with an audit trail.

## 12. Object Lifecycle Management

### 12.1. Rule Model

Lifecycle Management automatically performs an action when an object satisfies all conditions in a rule. Each rule has exactly one action:

- Delete: deletes matching objects or versions.
- SetStorageClass: transitions the object to another storage class.
- AbortIncompleteMultipartUpload: aborts incomplete multipart uploads matching conditions.

The outcome of a Delete action also depends on bucket settings. If Object Versioning is enabled, deleting a live object turns that generation into a noncurrent version. If versioning is disabled but Soft Delete is enabled, the deleted object enters a soft-deleted state. Deleting a noncurrent version in a bucket with Soft Delete can also move that version into a soft-deleted state. Therefore, a lifecycle rule does not guarantee bytes are permanently erased the instant the rule triggers.

Common conditions:

| Condition | Meaning |
| --- | --- |
| age | Number of days since object creation |
| createdBefore | Object created before a specified UTC date |
| customTimeBefore | Object Custom-Time before a specified date |
| daysSinceCustomTime | Days elapsed since Custom-Time |
| daysSinceNoncurrentTime | Days elapsed since the object became noncurrent |
| noncurrentTimeBefore | Noncurrent version older than a specified date |
| isLive | Applies only to live or noncurrent versions |
| numNewerVersions | At least N newer versions exist |
| matchesPrefix | Object name starts with prefix |
| matchesSuffix | Object name ends with suffix |
| matchesStorageClass | Object belongs to one or more storage classes |
| sizeAboveBytes / sizeBelowBytes | Byte size above or below threshold |

All conditions declared in a single rule must match simultaneously. For example, age=365 and matchesPrefix=["reports/"] applies only to objects under prefix reports/ that are at least 365 days old.

### 12.2. Deleting Temporary Objects After 30 Days

Lifecycle JSON example:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "age": 30,
        "matchesPrefix": [
          "tmp/"
        ]
      }
    }
  ]
}
~~~

This rule requires objects under prefix tmp/ to reach 30 days of age before becoming eligible for deletion. Lifecycle actions run asynchronously; applications must not assume objects vanish at the exact moment conditions are met.

### 12.3. Deleting Noncurrent Versions After 90 Days

When a bucket enables Object Versioning, manage noncurrent versions. Example:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "isLive": false,
        "daysSinceNoncurrentTime": 90
      }
    }
  ]
}
~~~

This rule applies only to noncurrent versions that became noncurrent at least 90 days ago. It does not delete the live version.

You can use numNewerVersions to keep a fixed number of recent versions. For example, delete versions when at least 5 newer versions exist:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "isLive": false,
        "numNewerVersions": 5
      }
    }
  ]
}
~~~

Real configurations must check retention requirements, soft delete, and retention policies. Lifecycle Delete does not override object holds or retention periods.

### 12.4. Transitioning Storage Class by Object Age

Example transitioning objects under prefix archive/ to Coldline after 90 days:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesPrefix": [
          "archive/"
        ],
        "matchesStorageClass": [
          "STANDARD"
        ]
      }
    }
  ]
}
~~~

Common storage classes:

| Storage class | Minimum storage duration | Retrieval fee |
| --- | ---: | --- |
| Standard | None | No |
| Nearline | 30 days | Yes |
| Coldline | 90 days | Yes |
| Archive | 365 days | Yes |

Choose classes based on read frequency, retention length, and retrieval cost. If an object is deleted before its minimum storage duration, early deletion charges may apply. Time spent in live, noncurrent, and soft-deleted states may count toward minimum duration depending on the mechanism. Lifecycle SetStorageClass is cost-advantageous over manual rewrites in many cases; still evaluate storage, operation, and retrieval costs under current pricing.

### 12.5. Autoclass

Autoclass lets Cloud Storage automatically transition storage classes based on access patterns. When a bucket enables Autoclass, do not use the matchesStorageClass condition in lifecycle rules. Choose either Autoclass or explicit lifecycle transition rules as your management model; avoid conflicting configurations that make storage class predictions difficult.

### 12.6. Applying Lifecycle Config to a Bucket

Using gcloud:

~~~bash
gcloud storage buckets update gs://training-documents-archive \
  --lifecycle-file=lifecycle.json
~~~

Read back the bucket configuration using:

~~~bash
gcloud storage buckets describe \
  gs://training-documents-archive
~~~

Do not apply lifecycle Delete across an entire bucket without verifying prefix, age, versioning, retention, holds, and soft delete. Test on a test bucket with sample objects and observe the outcome.

## 13. Configuring Lifecycle Management in Java

The Java client supports BucketInfo.LifecycleRule, LifecycleAction, and LifecycleCondition.

Example deleting objects under prefix tmp/ after 30 days:

~~~java
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.BucketInfo.LifecycleRule;
import com.google.cloud.storage.BucketInfo.LifecycleRule.LifecycleAction;
import com.google.cloud.storage.BucketInfo.LifecycleRule.LifecycleCondition;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageClass;
import java.util.List;

public void configureTempCleanup(
        Storage storage,
        String bucketName) {

    Bucket bucket = storage.get(bucketName);

    LifecycleRule cleanupRule = new LifecycleRule(
            LifecycleAction.newDeleteAction(),
            LifecycleCondition.newBuilder()
                    .setAge(30)
                    .setMatchesPrefix(List.of("tmp/"))
                    .build());

    bucket.toBuilder()
            .setLifecycleRules(List.of(cleanupRule))
            .build()
            .update();
}
~~~

The example replaces the bucket's lifecycle configuration. If the bucket already has rules, read the existing configuration and merge the new rule; do not accidentally wipe out the existing rule list.

Example transitioning storage class:

~~~java
LifecycleRule coldlineRule = new LifecycleRule(
        LifecycleAction.newSetStorageClassAction(StorageClass.COLDLINE),
        LifecycleCondition.newBuilder()
                .setAge(90)
                .setMatchesPrefix(List.of("archive/"))
                .setMatchesStorageClass(List.of(StorageClass.STANDARD))
                .build());
~~~

Some newer lifecycle conditions are supported only in newer Java client versions. Check the Javadoc and BOM; do not use an older library version assuming every service-side condition is supported by the SDK.

## 14. Spring Boot Design for Bucket Policies and Lifecycles

### 14.1. Separating Runtime Permissions and Provisioning Permissions

Runtime applications usually only need to read/write objects for business operations. Administrative actions such as changing the default KMS key, enabling versioning, setting retention policies, locking buckets, or modifying lifecycle configs should be handled by provisioning pipelines or dedicated admin principals.

| Workload | Typical permissions |
| --- | --- |
| Document API upload/download | storage.objects.create/get |
| Document API list | storage.objects.list |
| Cleanup worker | storage.objects.delete within appropriate scope |
| Restore operator | storage.objects.restore, storage.objects.create, and overwrite permissions if needed |
| Bucket provisioning | storage.buckets.create/update/get |
| CMEK service agent | cloudkms.cryptoKeyEncrypterDecrypter on the key |
| Key administrator | Cloud KMS administration via a separate role |

Do not grant roles/storage.admin to every service just because a worker needs to upload. Use bucket scope and custom roles when narrowing permissions.

### 14.2. Storage Bean

If the application already uses the Spring Framework on Google Cloud starter and it auto-configures Storage, inject that bean. If configuring manually:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcsConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Use ADC or workload identity. Never put service account JSON private keys or CSEKs in source code.

### 14.3. Environment-Specific Configuration

~~~yaml
app:
  gcs:
    bucket: training-documents-dev
    default-kms-key: projects/training-platform-security/locations/asia-southeast1/keyRings/document-keyring/cryptoKeys/document-key
    lifecycle-policy-managed-by: infrastructure
~~~

Properties are illustrative. Dev, staging, and production buckets should have policies matching data sensitivity and environment. Do not let clients pass arbitrary buckets or KMS key names in upload APIs.

### 14.4. Separating Business Services and Administrative Services

An application can organize components as:

- DocumentStorageService: upload/download/list/delete for business operations.
- ObjectVersionService: persist generation, query versions, and restore older copies.
- RetentionPolicyService: check when objects are eligible for deletion and hold status.
- LifecycleProvisioning: update lifecycle configs in deployment pipelines.
- EncryptionPolicyService: verify KMS key names, bucket default encryption, and key status.

Never let a user-facing controller directly call APIs to lock retention or destroy keys. These are high-impact administrative operations requiring dedicated approval controls.

## 15. Monitoring, Auditing, and Object Inventory

A policy is effective only when it can be observed and verified.

Useful metadata fields:

- Bucket/object name or internal document ID.
- Generation and metageneration.
- KMS key name if the object uses CMEK.
- Storage class and class transition timestamps.
- Retention expiration time or retain-until time.
- Temporary hold / event-based hold status.
- Soft delete time / hard delete time if soft-deleted.
- Create/update timestamps and size.

Never log raw CSEKs, access tokens, or file contents. Object names and custom metadata can be read by authorized principals; avoid placing sensitive data in these fields.

Signals to monitor:

- 403 errors from missing IAM or Cloud KMS permissions.
- Decryption failures after a key version is disabled.
- Ratio of noncurrent and soft-deleted objects.
- Count of objects past lifecycle eligibility that have not been cleaned up.
- Total bytes by storage class and generation count.
- Count of objects under holds or retention.
- Restore failures and restore frequency.
- Cloud KMS HSM/EKM costs if using those key types.

Use Cloud Audit Logs to trace IAM, key, bucket, and object operations. Use Storage Insights/inventory reports or BigQuery to inventory large object counts by kmsKeyName, storage class, generation, create time, and metadata.

## 16. Costs and Trade-Offs

| Mechanism | Benefit | Operational cost/risk |
| --- | --- | --- |
| Google-managed encryption | Simple, default | Less key lifecycle control than CMEK |
| CMEK software key | Key control, auditing, and permissions | Cloud KMS/IAM management; HSM/EKM has separate quotas/costs |
| CSEK | Customer-controlled keys | Complex key distribution, backup, rotation, and recovery |
| Client-side encryption | Plaintext encrypted before upload | Application owns cryptography and key lifecycle |
| Object Versioning | Recover old versions | Stores multiple generations and increases storage cost |
| Soft Delete | Recover recently deleted objects/buckets | Stores deleted objects during retention duration |
| Bucket Lock | Strong immutable retention | Cannot shorten/remove policy; bucket hard to clean/delete |
| Lifecycle | Automates age and storage class management | Misconfigured rules can delete wrong objects; actions are asynchronous |

Early deletion charges may apply when objects in Nearline, Coldline, or Archive are deleted/replaced before their minimum storage duration. Time spent in live, noncurrent, and soft-deleted states may count toward minimum storage duration depending on the mechanism. When using lifecycle or versioning, account for both object counts and actual retention duration.

For buckets holding temporary data, enabling versioning + long soft delete + retention lock can inflate costs sharply. For buckets holding legal records, higher cost and operational complexity may be necessary to satisfy retention mandates.

## 17. Testing Encryption, Versioning, and Retention

### 17.1. Unit Tests

Verify business logic and adapters:

- Bucket is selected by environment, never taken from client requests.
- Uploads use the KMS key required by policy.
- CSEKs or key material are never logged.
- Object records store generation, size, and storage class.
- Documents are not marked READY before upload and metadata verification succeed.
- Cleanup workers do not delete objects still under retention or holds.
- Lifecycle configurations are generated from approved configuration.

Mocking Storage tests only application logic; it does not prove Cloud KMS permissions, bucket retention, or soft delete actually work.

### 17.2. Integration Tests on a Dedicated GCP Project

1. Create a test bucket in a location compatible with the KMS key.
2. Grant the Cloud Storage service agent encrypt/decrypt permissions on the key.
3. Upload an object using default CMEK and verify kmsKeyName.
4. Upload with a different explicit key and verify metadata.
5. Attempt download when the service agent lacks key permissions; confirm the request fails.
6. Rotate the KMS primary version, upload a new object, and verify the key version.
7. Re-encrypt a sample object and verify it remains readable.
8. Enable Object Versioning, overwrite an object, and check the noncurrent generation.
9. Enable Soft Delete, delete an object, list soft-deleted objects, and restore by generation.
10. Set an unlocked retention policy, attempt early deletion, and confirm rejection.
11. Set temporary/event-based holds and test delete/overwrite blocks.
12. Configure lifecycle on a test prefix and verify actions once rule conditions are met.
13. Clean up resources per test policy, checking remaining object versions and soft-deleted objects.

Do not lock retention policies or destroy key versions in routine integration tests. If irreversible behaviors must be tested, use dedicated test projects/buckets/keys and an explicit approval process.

### 17.3. Fault Injection

Simulate:

- Cloud KMS key version disabled.
- KMS permission revoked from the Storage service agent.
- Runtime service account missing storage.objects.create.
- New object uploaded, but database update fails.
- Object overwritten while Object Versioning is enabled.
- Deleting an object that currently has a hold.
- Restoring a soft-deleted object when a live object with the same name already exists.
- Lifecycle Delete running on an object still under retention.
- Noncurrent versions persisting longer than expected due to missing lifecycle rules.
- KMS rotation completed, while some noncurrent versions still use the old key.

Expected outcomes: the system never falsely marks a file ready, never deletes data violating retention, can identify which key version protects each object, and has tested recovery procedures.

## 18. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| CMEK upload returns 403 | Storage service agent lacks Cloud KMS permissions | Grant roles/cloudkms.cryptoKeyEncrypterDecrypter on the exact key |
| CMEK key cannot be used | Key location incompatible with bucket | Verify bucket/key ring locations |
| CMEK object download fails | Key version disabled/destroyed or service agent lost permissions | Check KMS key version and IAM |
| After rotation, old objects still use old key | Rotation does not auto-re-encrypt objects | Rewrite objects and check noncurrent versions |
| CSEK download returns decryption error | Missing/wrong AES-256 key | Look up key version in key vault and pass the exact decryption key |
| Lost ability to read CSEK object | Key material lost | Restore from key backup; if gone, data cannot be decrypted |
| Version count grows continuously | Missing lifecycle cleanup for noncurrent versions | Add daysSinceNoncurrentTime or numNewerVersions |
| Object deletion rejected | Retention policy, object retention, or hold | Check retention expiration and hold state |
| Lifecycle does not delete object | Conditions not yet met, active hold, or retention still active | Check all conditions and policy timestamps |
| Restore creates a different live object | Restore generates a new generation | Update database with the new generation |
| Restore overwrites current file | Live object already exists with same object name | Check live generation before restoring |
| Costs spike after enabling versioning | Many noncurrent versions retained | Add lifecycle rules and review retention requirements |
| Soft-deleted object missing from listing | Standard listing hides soft-deleted resources | Use `--soft-deleted` or API filter |
| Locking retention fails | Missing bucket update permission or metageneration mismatch | Re-read bucket metadata and verify IAM |

## 19. Policy Examples by Data Category

### 19.1. Transaction Documents

Requirements: controlled encryption, policy-mandated minimum retention, and auditing.

- Use CMEK with a key ring in a bucket-compatible location.
- Separate runtime identity, Storage service agent, and key administrator.
- Apply retention policy matching legal duration.
- Lock the bucket only after compliance/legal and operations sign-off.
- Use Soft Delete for a recovery window if appropriate.
- Audit restore, delete, key rotation, and IAM change operations.

### 19.2. User-Updatable Files

Requirements: allow users to replace files while supporting rollback to previous versions.

- Use Google-managed encryption or CMEK as required.
- Enable Object Versioning.
- Persist the current generation in the database.
- Use generation preconditions on replace/delete.
- Use lifecycle rules to delete noncurrent versions after an approved period.
- Use Soft Delete if an extra recovery window is needed after version deletion.

### 19.3. Temporary Files and Caches

Requirements: short lifetime, high volume, and low cost.

- Use default encryption.
- Do not enable Bucket Lock.
- Do not enable Object Versioning if history is unneeded.
- Choose a short Soft Delete duration or disable if policy permits.
- Use lifecycle rules to delete the tmp/ prefix after TTL.
- Enforce size limits and quotas on upload.
- Monitor object counts and total bytes to prevent unexpected accumulation.

### 19.4. Investigation Records or Legal Holds

Requirements: retain objects until a specific event or release decision.

- Use temporary holds or event-based holds matching business semantics.
- Record who placed the hold, reason, timestamp, and approver.
- Release holds via an audited workflow.
- If a bucket retention policy exists, remember event-based holds reset the retention clock upon release.
- Do not expect lifecycle rules to delete objects currently on hold.

## 20. Comparison with AWS S3 and Azure Blob Storage

| Aspect | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Default encryption | Google-managed server-side encryption | Default SSE-S3 for new objects | Default Storage Service Encryption |
| Customer-managed keys | CMEK via Cloud KMS | SSE-KMS via AWS KMS | Customer-managed key via Azure Key Vault |
| Customer-supplied keys | CSEK in request | SSE-C | Customer-provided keys |
| Client-side encryption | Application encrypts bytes itself | S3 Encryption Client | Client-side encryption SDK |
| Versioning | Object Versioning, generation | S3 Versioning, Version ID | Blob versioning |
| Soft delete/recovery | Soft Delete and restore | Delete markers/versioning, object recovery by feature | Soft delete for blobs/containers |
| Retention/immutability | Bucket Lock, Object Retention Lock, holds | S3 Object Lock governance/compliance | Immutable Blob Storage policies/legal holds |
| Lifecycle | Delete, SetStorageClass, and multipart cleanup | Expiration, transition, abort multipart | Delete, tiering, and version management |

Providers share similar feature names, but semantics differ. GCS generation is not equivalent to S3 Version ID or Azure Version ID. CMEK does not equal all KMS configurations on other providers. Multi-cloud adapters should standardize business behaviors such as encrypt, retain, restore, listVersions, and applyLifecycle, while each adapter encapsulates key references, version tokens, holds, and retention APIs.

## 21. Comprehensive Hands-On Exercise

**Context:** Build the Spring Boot `document-api` application managing contract records and temporary files in two separate buckets. Contract records require CMEK encryption, a 7-year minimum retention, and version recovery. Temporary files only need to persist for 30 days.

### Task A — Encryption

1. Create a Cloud KMS key ring and symmetric key in a bucket-compatible location.
2. Retrieve the project's Storage service agent.
3. Grant roles/cloudkms.cryptoKeyEncrypterDecrypter on the CryptoKey.
4. Configure default CMEK on the contracts bucket.
5. Upload an object and verify kmsKeyName.
6. Rotate the primary key version and explain why old objects still require the old key version.
7. Re-encrypt a test object and verify readability.

### Task B — Versioning and Soft Delete

1. Enable Object Versioning on the contracts bucket.
2. Upload an object and record its generation in the database.
3. Overwrite the object and confirm the old generation becomes noncurrent.
4. Delete the live object in a test bucket with Soft Delete enabled.
5. List soft-deleted generations and restore.
6. Update the document record with the new generation after restoring.

### Task C — Retention and Holds

1. Set a bucket retention period for testing requirements.
2. Attempt early deletion and handle the error.
3. Place a temporary hold on an object.
4. Release the temporary hold via an audited workflow.
5. Place an event-based hold and observe when the retention clock restarts after release.
6. On a dedicated test bucket, simulate Bucket Lock and explain why the policy cannot be shortened or removed once locked.

### Task D — Lifecycle

1. Create a rule deleting objects under prefix tmp/ after 30 days.
2. Create a rule deleting noncurrent versions after 90 days.
3. Create a rule transitioning archive/ objects to Coldline once old enough.
4. Explain why lifecycle does not delete objects under holds or active retention.
5. Review storage classes and minimum duration charges.

### Task E — Spring Boot and Testing

- Create a Storage bean via ADC/workload identity.
- Separate runtime roles and provisioning roles.
- Store generation, kmsKeyName, and required retention metadata in the document record.
- Never store CSEKs or private keys in source code.
- Test CMEK upload/download, restore, versioning, holds, and lifecycle on a dedicated project.
- Inspect audit logs, key versions, and object generations.
- Compare the design with AWS S3 and Azure Blob Storage.

**Pass criteria:** The application uses the proper encryption mode; can identify which key protects an object; manages versions and restores objects; avoids premature deletion under retention/holds; cleans up via lifecycle by prefix/age; and includes integration tests verifying real Cloud Storage behavior.

## 22. Key Takeaways

- Cloud Storage always encrypts server-side by default; choose CMEK/CSEK/client-side encryption only when key control mandates require it.
- CMEK requires the Cloud Storage service agent to have encrypt/decrypt permissions on the Cloud KMS key; key location must be compatible with the bucket.
- Rotating CMEK does not auto-re-encrypt existing objects; rewrite objects and check noncurrent versions before disabling/destroying old keys.
- CSEK requires the client to supply the exact key on reads; losing the key renders data unrecoverable.
- Object Versioning preserves noncurrent generations but does not protect against bucket deletion.
- Soft Delete retains deleted objects/buckets for a configured duration, and restore creates a new generation.
- Retention policies block deletion/replacement before expiration; Bucket Lock is irreversible.
- Temporary holds and event-based holds both block delete/overwrite; event-based holds have distinct semantics that restart the retention clock on release.
- A lifecycle rule has one action and all conditions must match; Delete does not override retention or holds.
- Control costs with lifecycle rules, suitable storage classes, Soft Delete duration, and limits on noncurrent versions.
- In Spring Boot, separate runtime permissions from bucket/key provisioning and audit restore, rotation, and retention operations.

### References

- [Data encryption options — Cloud Storage](https://docs.cloud.google.com/storage/docs/encryption)
- [Customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Use customer-managed encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Customer-supplied encryption keys](https://docs.cloud.google.com/storage/docs/encryption/customer-supplied-keys)
- [Use customer-supplied encryption keys](https://docs.cloud.google.com/storage/docs/encryption/using-customer-supplied-keys)
- [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Soft Delete overview](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Use soft-deleted objects](https://docs.cloud.google.com/storage/docs/use-soft-deleted-objects)
- [Request preconditions and object generations](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Bucket Lock and retention policies](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Object Retention Lock](https://docs.cloud.google.com/storage/docs/object-lock)
- [Object holds](https://docs.cloud.google.com/storage/docs/object-holds)
- [Object Lifecycle Management](https://docs.cloud.google.com/storage/docs/lifecycle)
- [Storage classes](https://docs.cloud.google.com/storage/docs/storage-classes)
- [Java Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Java BlobInfo](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.BlobInfo)
- [Java BucketInfo](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.BucketInfo)
- [Java BlobWriteOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobWriteOption)
- [Java BlobSourceOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobSourceOption)
