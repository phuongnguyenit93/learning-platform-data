# Cloud KMS Key Rings, Keys, and Key Versions

Cloud Key Management Service (Cloud KMS) manages the lifecycle of cryptographic keys in Google Cloud. When working with Cloud KMS, you must distinguish between three resource levels: a **key ring** used to group keys, a **CryptoKey** representing a logical key and its associated policies, and a **CryptoKeyVersion** containing the actual key material used for encryption, decryption, or signing operations.

Properly understanding these three levels helps you design IAM permissions, choose key storage locations, rotate keys, and keep older data decryptable after creating new versions.

## Learning Objectives

After this lesson, you will be able to:

- Explain the relationship between project, location, key ring, CryptoKey, and CryptoKeyVersion.
- Read the full resource ID of a key ring, key, and key version.
- Distinguish between purpose, protection level, and key version states.
- Create a key ring and symmetric key using the Google Cloud CLI.
- Explain primary versions, rotation, and why older versions must be retained while data still needs to be decrypted.
- Choose appropriate IAM scopes for administrators and applications.

## 1. Cloud KMS Resource Model

Cloud KMS resources reside within a Google Cloud project and are placed in a location. The hierarchy can be visualized as follows:

~~~text
Organization
└── Folder
    └── Project
        └── Location
            └── Key ring
                └── CryptoKey
                    ├── CryptoKeyVersion 1
                    ├── CryptoKeyVersion 2
                    └── CryptoKeyVersion 3
~~~

Organization and folder are Google Cloud governance levels surrounding a project. Within a project, the location determines the geographic region of the Cloud KMS resources. Key ring, CryptoKey, and CryptoKeyVersion are the cryptographic resource levels.

### Key ring: grouping keys by administrative scope

A key ring is a logical grouping containing CryptoKeys within the same location. Key rings help organize keys by environment, application, data group, or permission boundary. For example, a project may have separate key rings for **production**, **staging**, and **analytics**.

A key ring does not contain key material and does not directly perform encryption. It provides a level to manage groups of keys and assign IAM permissions for all keys within the group. Key ring names must be unique within a location; the same name can appear in a different location. A key ring itself incurs no Cloud KMS cost.

### CryptoKey: logical key definition

A CryptoKey is a named resource containing metadata and one or more key versions. When creating a CryptoKey, you define key attributes such as:

- **Purpose:** the type of cryptographic operation the key is allowed to perform, such as symmetric encryption/decryption, asymmetric encryption, asymmetric signing, or MAC.
- **Protection level:** the environment protecting the key material, such as software, HSM, or an external key management system.
- **Rotation schedule:** the schedule for automatically creating new versions, if supported by the key type.
- **IAM policy:** the principals permitted to administer the key or use the key for cryptographic operations.

Purpose and protection level cannot be changed after the CryptoKey is created. Versions belonging to the same CryptoKey share the same purpose.

CryptoKey is the stable identifier that applications and IAM policies typically reference. The actual key material resides in the CryptoKeyVersions beneath it.

### CryptoKeyVersion: actual key material

Each CryptoKeyVersion contains a set of key material used for cryptographic operations. Versions are numbered starting from **1**; when rotating a key, Cloud KMS creates a new version rather than overwriting the material of the old version.

When decrypting data or verifying a signature, the system must use the exact version that was used to encrypt the data or create that signature. Therefore, older versions may still be required even after a new version has become the primary version.

Cloud KMS does not allow principals to view or export raw key material. Applications send requests to Cloud KMS; the service performs operations using the key material on behalf of the application.

## 2. Reading Full Resource IDs

A resource ID indicates the project, location, and parent resource levels. For example:

~~~text
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME/cryptoKeyVersions/VERSION
~~~

| Resource | Trailing part of resource ID | Meaning |
|---|---|---|
| Key ring | keyRings/KEY_RING | Group of keys within a location |
| CryptoKey | cryptoKeys/KEY_NAME | Logical key and metadata |
| CryptoKeyVersion | cryptoKeyVersions/VERSION | A specific version of key material |

For example, the segment **cryptoKeyVersions/3** explicitly identifies version 3 of a CryptoKey. When troubleshooting incidents or inspecting logs, verify the full project, location, key ring, key, and version; looking only at the key name may not be enough to identify the exact resource.

## 3. Choosing a Location Before Creating a Key Ring

Location is a critical architectural decision. Cloud KMS supports regional locations, multi-regional locations, and the **global** location. Location affects where key material is stored, data residency requirements, and latency when applications call Cloud KMS.

- **Regional:** suitable when applications and data are concentrated in a single region, or when regional data residency is required.
- **Multi-regional:** suitable when data needs to be stored across multiple regions within a Google-defined multi-region.
- **Global:** a special multi-region with data centers worldwide; it does not allow you to choose individual data centers inside it.

Choose a location close to the resources using the key and verify whether that location supports the desired protection level. For CMEK, the key location typically needs to be compatible with the location of the protected resource. For Cloud EKM, you must consider the location of the external key management system.

**You cannot move a key ring or key to another location after creation.** If the wrong location is chosen, the typical remedy is to create new resources in the appropriate location and migrate applications and data to the new key under a controlled migration plan.

Operations that create or update resources and metadata in a multi-region may be slower than in a single-region due to consensus requirements across data centers. Evaluate latency, availability, and data residency requirements instead of assuming multi-region is always better.

## 4. Purpose and Protection Level

These two attributes answer two different questions: **what the key is used for** and **where the key material is protected**.

### Purpose

| Common Purpose | Usage |
|---|---|
| Symmetric encrypt/decrypt | The same key is used for both encryption and decryption |
| Asymmetric encrypt/decrypt | Uses the public key to encrypt and the private key to decrypt |
| Asymmetric signing | Uses the private key to sign and the public key to verify |
| MAC signing/verification | Generates and verifies message authentication codes |

Choose the purpose based on the protocol and application needs. The purpose of a CryptoKey cannot be changed after creation; if the wrong purpose is chosen, you must create another key and migrate the application to the new key.

### Protection level

| Value | Description |
|---|---|
| SOFTWARE | Key material is protected by Cloud KMS software mechanisms |
| HSM | Key material is protected by multi-tenant Cloud HSM |
| HSM_SINGLE_TENANT | Key material is protected by single-tenant HSM infrastructure dedicated to one customer |
| EXTERNAL | Cloud KMS integrates with an External Key Manager (EKM) system over the internet |
| EXTERNAL_VPC | Cloud KMS connects to EKM via VPC |

HSM and EKM availability varies by location. Protection level cannot be changed after creating a key. Therefore, verify compliance requirements, operational models, and location before creating the key.

## 5. Primary Version and How Versions Are Used

A CryptoKey can have multiple versions in the enabled state.

- For **symmetric encryption keys**, one version is selected as the **primary version**. If an encryption request does not specify a version, Cloud KMS uses the primary version.
- For **asymmetric keys**, there is no primary version. Applications must explicitly specify the version to use in each operation.
- Enabled versions can still be specified directly when the operation matches the key's purpose.

For example, the key **payments-data-key** has two versions:

| Version | Role | State |
|---|---|---|
| 1 | Encrypted data prior to the rotation | Enabled |
| 2 | Primary version for new data | Enabled |

The application can continue decrypting older data using version **1**, while new encryption requests default to using version **2**. Changing the primary version does not automatically migrate old data to the new version.

## 6. Key Version Lifecycle and States

Cloud KMS manages state at the CryptoKeyVersion level. Key rings and CryptoKeys do not have a state field following the key version state model.

| State | Meaning | Usable for cryptographic operations? |
|---|---|---|
| PENDING_GENERATION | Asymmetric version is being generated | No |
| PENDING_IMPORT | Version is being imported from external key material | No |
| ENABLED | Version is ready for use | Yes |
| DISABLED | Key material still exists but is temporarily unusable | No |
| DESTROY_SCHEDULED | Waiting for the scheduled time to destroy key material | No |
| DESTROYED | Key material has been destroyed | No |
| IMPORT_FAILED | Key import process failed | No |

Key points to remember:

- New symmetric versions typically start in the **ENABLED** state; asymmetric versions start in **PENDING_GENERATION** and transition to **ENABLED** once generation completes.
- A **DISABLED** version can be re-enabled if the key material still exists.
- A version in **DESTROY_SCHEDULED** cannot be used. During the waiting period prior to destruction, the version can be restored to the disabled state following Cloud KMS procedures.
- Once in **DESTROYED**, the key material is no longer stored in Cloud KMS. Data encrypted with that version cannot be decrypted unless a valid copy of the key material exists elsewhere. For signing keys, new signatures cannot be created with a destroyed private key; verifying old signatures depends on retaining the public key.

**Warning:** destroying a version still used by applications or services can cause permanent data loss or service outages. Before destroying, identify all data, backups, applications, and recovery procedures that still depend on that version.

## 7. IAM: Granting Permissions at the Right Resource Level

You can manage permissions at the project, key ring, or CryptoKey level. You cannot attach an independent IAM policy to an individual CryptoKeyVersion.

| Permission Level | Scope of Impact |
|---|---|
| Project | Keys within the project |
| Key ring | Keys belonging to the key ring |
| CryptoKey | Only the selected key and its enabled versions |
| CryptoKeyVersion | Independent IAM permissions are not supported |

For example, granting permissions on the **payments-prod** key ring allows the principal to use the keys in that key ring according to the granted permissions. If an application only needs to encrypt/decrypt using a single key, consider granting permissions at the CryptoKey level to narrow the scope.

Common roles:

- **roles/cloudkms.admin:** administers Cloud KMS resources, including maintenance and sensitive version management permissions such as destroying versions. Grant only to the team responsible for key administration.
- **roles/cloudkms.cryptoKeyEncrypter:** allows encrypting using keys within the granted scope.
- **roles/cloudkms.cryptoKeyDecrypter:** allows decrypting using keys within the granted scope.
- **roles/cloudkms.cryptoKeyEncrypterDecrypter:** allows both encryption and decryption.

Separate key administration roles from the identity running the application. Applications should receive only the cryptographic permissions they need; the key administration team receives permissions to create, modify configurations, or destroy versions. When different permission controls are needed between two applications, consider creating two separate CryptoKeys rather than sharing a key ring and attempting to restrict permissions per version.

## 8. Creating a Key Ring and Symmetric Key with gcloud

The following example creates a key ring and CryptoKey for symmetric encryption/decryption. Replace the placeholder values with your actual environment's project, location, and resource names.

### Step 1: select the project

~~~bash
gcloud config set project PROJECT_ID
~~~

### Step 2: create the key ring

~~~bash
gcloud kms keyrings create payments-prod \
  --location LOCATION
~~~

### Step 3: create the CryptoKey

~~~bash
gcloud kms keys create payments-data-key \
  --keyring payments-prod \
  --location LOCATION \
  --purpose encryption \
  --protection-level software
~~~

The command above creates a software key with the encryption purpose. If HSM or EKM is required, select the corresponding protection level and confirm that the location supports that key type.

### Step 4: inspect key details and versions

~~~bash
gcloud kms keys describe payments-data-key \
  --keyring payments-prod \
  --location LOCATION

gcloud kms keys versions list \
  --key payments-data-key \
  --keyring payments-prod \
  --location LOCATION
~~~

Check the initial version, state, and primary state before configuring the application. To view the full resource ID, use an appropriate output format in gcloud or the Cloud KMS API.

### Step 5: create a new version and set it as primary

For symmetric encryption keys, you can create a new version and set it as primary in the same command:

~~~bash
gcloud kms keys versions create \
  --key payments-data-key \
  --keyring payments-prod \
  --location LOCATION \
  --primary
~~~

Only use the **--primary** flag for keys with purpose **encryption**. For asymmetric keys, create a version and then update the application to explicitly reference the new version according to the application's key rollout process.

### Step 6: configure automatic rotation

Example setting a 90-day rotation period:

~~~bash
gcloud kms keys update payments-data-key \
  --keyring payments-prod \
  --location LOCATION \
  --rotation-period 90d
~~~

The 90-day period is for illustration only. Choose the period based on security policy, compliance requirements, data sensitivity, and the application's ability to handle older versions. Cloud KMS does not support automatic rotation for asymmetric signing or asymmetric encryption keys.

## 9. Rotation Does Not Mean Re-Encrypting Data

Rotation creates a new version to protect new data. For data that an application directly encrypts using Cloud KMS, rotation **does not automatically decrypt and re-encrypt old ciphertext**. Older versions still need to exist to decrypt data created with them.

A safe rotation workflow typically includes:

1. Create a new version and confirm it is in the **ENABLED** state.
2. For symmetric keys, switch primary to the new version or let the automatic rotation schedule perform this step.
3. Monitor the application and confirm new encryption operations use the new version.
4. Continue retaining older versions to decrypt existing data.
5. If dependencies on older versions must be removed, execute a decrypt and re-encrypt workflow for the data, then verify the data, backups, and recovery procedures.
6. Only disable or schedule destruction of older versions after confirming no dependencies remain.

For CMEK, integrated Google Cloud services may handle rotation in different ways. Some services automatically re-encrypt data encryption keys (DEKs), while others only use the new version for new data. Check the documentation for the service you use before scheduling destruction of older versions.

For asymmetric signing keys, you must distribute the public key of the new version and update verifiers. For asymmetric encryption keys, senders must use the new public key; receivers still need the private keys of older versions to decrypt legacy data.

## 10. Real-World Scenario: Managing Keys for Payment Data

A payment system stores sensitive data in a Google Cloud service that supports CMEK. The platform team creates the **payments-prod** key ring and the **payments-data-key** CryptoKey in a location compatible with the storage service.

Initially, version **1** is primary. After a rotation cycle, Cloud KMS creates version **2** and version **2** becomes primary. New data is protected by the new version, while older data may still depend on version **1**.

The operations team needs to verify how the storage service handles DEKs after rotation. If the service has not re-encrypted legacy DEKs, version **1** must remain enabled to read data. The team only considers destroying version **1** after obtaining evidence that data, backups, and recovery workflows no longer require this version.

Permissions are also divided by responsibility: the application's service account only has permission to use the CryptoKey for required operations; the key administration team has permissions to manage rotation and versions. Thus, a bug in the workload does not automatically grant the workload permission to change configurations or destroy key material.

## 11. Common Design Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Choosing a location without checking residency or HSM/EKM support | Fails to meet data requirements or cannot create the required key type | Verify location and protection level before creation |
| Thinking a key ring holds key material | Confusion about each resource's responsibility | Treat the key ring as a grouping; key material resides in CryptoKeyVersion |
| Trying to grant IAM on a single version | Permissions cannot be expressed that way in Cloud KMS | Split into separate CryptoKeys if distinct permission boundaries are needed |
| Immediately deleting the old version after rotation | Older data may become undecryptable | Keep older versions until migration and verification are complete |
| Using automatic rotation for asymmetric keys | Configuration is not supported | Design a manual version creation and public key distribution workflow |
| Granting Cloud KMS Admin to an application service account | Workload may receive overly broad administrative permissions | Grant encrypt/decrypt roles at the key level following least privilege |

## 12. Pre-Production Checklist for Keys

- [ ] Project and location satisfy organizational, data residency, and latency requirements.
- [ ] Location supports the chosen protection level.
- [ ] Purpose and algorithm match the application's operations.
- [ ] Identified which CryptoKeys can be shared and which must be separated.
- [ ] IAM is granted at the narrowest possible scope; service accounts do not have key administration permissions unless required.
- [ ] Rotation schedule and an owner responsible for handling new versions are established.
- [ ] Applications can identify the required version when decrypting or verifying signatures.
- [ ] Backups and recovery workflows still function when an older version is disabled.
- [ ] Verification step exists before placing a version into scheduled for destruction state.

## Conclusion

Key rings help organize and assign permissions by group; CryptoKeys represent logical keys and policies; CryptoKeyVersions contain the actual key material. Location, purpose, and protection level are decisions that must be finalized before creating a key. During rotation, remember that the new version serves new data, while older versions may still be necessary to read existing data. The process is only complete when applications, data, backups, and IAM have all been verified.

## References

- [Cloud KMS resources and resource hierarchy](https://docs.cloud.google.com/kms/docs/resource-hierarchy)
- [Cloud KMS locations](https://docs.cloud.google.com/kms/docs/locations)
- [Key version states](https://docs.cloud.google.com/kms/docs/key-states)
- [Cloud KMS permissions and roles](https://docs.cloud.google.com/kms/docs/reference/permissions-and-roles)
- [Create a key ring](https://docs.cloud.google.com/kms/docs/create-key-ring)
- [Create a key](https://docs.cloud.google.com/kms/docs/create-key)
- [Key rotation](https://docs.cloud.google.com/kms/docs/key-rotation)
- [CMEK key rotation](https://docs.cloud.google.com/kms/docs/cmek-rotation)
