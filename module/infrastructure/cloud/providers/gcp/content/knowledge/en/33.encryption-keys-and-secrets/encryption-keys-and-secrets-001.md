# Default Encryption and Key Management Options on GCP

Google Cloud automatically encrypts customer data at rest. As a result, a new workload already has an at-rest protection layer without requiring you to create keys or add configuration. When requirements for key control, separation of duties, auditing, or compliance increase, an organization can move to Customer-Managed Encryption Keys (CMEK) with Cloud Key Management Service (Cloud KMS), use Autokey to provision keys automatically, or connect an external key management system.

This lesson explains the default encryption mechanism, the roles of different key types, and how to choose a key management model for GCP workloads. The hands-on example uses Cloud Storage; other services have their own CMEK integration workflows.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between encryption at rest and encryption in transit.
- Describe how Google Cloud uses DEKs, KEKs, and envelope encryption.
- Compare Google-managed keys, CMEK, CMEK with Autokey, Cloud EKM, and CSEK.
- Determine when CMEK is needed and what conditions to verify before enabling it.
- Configure a Cloud KMS key as the default encryption key for a Cloud Storage bucket.
- Assess the impact of rotating, disabling, and destroying key versions.

## 1. What does encryption at rest protect?

Encryption at rest protects data that has been written to storage devices or backup media. Examples on GCP include objects in Cloud Storage, Compute Engine volumes, snapshots, data stored in databases, and customer content stored by other services.

Encryption makes data difficult to read if an unauthorized party obtains a physical copy or backup. However, encryption at rest is only one layer in a data protection model:

| Protection Layer | When Applied | GCP Examples |
|---|---|---|
| Encryption at rest | When data is stored on storage | Encryption of objects in Cloud Storage or Persistent Disk |
| Encryption in transit | When data travels across a network | TLS between clients and APIs, or between services |
| Encryption in use | When data is being processed in memory | Confidential Computing, Confidential VMs, and appropriate memory protection mechanisms |
| Application-level encryption | Before the application sends data to a storage service | Application encrypts sensitive fields using a cryptographic library |

Default encryption at rest does not replace IAM, application-layer authorization, network controls, secret management, or end-to-end encryption performed by the application. For example, a user with valid object read permissions can still download the content; the fact that the object is encrypted at rest does not automatically deny that request.

It is also important to distinguish customer content from customer metadata. Content such as object bytes or disk data is the focus of encryption at rest. Certain metadata such as object names, labels, sizes, or operational information have their own protection mechanisms. You should not place secrets in resource names, object names, or metadata under the assumption that CMEK will encrypt all of those fields.

## 2. Google Cloud's Default Encryption Mechanism

Google Cloud encrypts customer content at rest by default. Users do not have to create keys, enable a configuration flag, or manage rotation schedules to receive this baseline protection layer. Google owns and operates the key system used for the default model.

Google Cloud documentation describes AES-256 as the encryption standard at the storage layer. Some very old Persistent Disk resources may be historical exceptions, so when evaluating a legacy resource, you should check the documentation for that specific service and resource creation time.

### Envelope encryption

At large scale, systems typically do not use a single root key to directly encrypt every byte of data. Instead, they use the envelope encryption model:

- Data Encryption Key (DEK) is the data key used to encrypt the content.
- Key Encryption Key (KEK) is the key-protecting key used to encrypt or wrap the DEK.
- Ciphertext is the encrypted content.
- Wrapped DEK is the DEK that has been encrypted with the KEK and stored alongside the information needed to decrypt the data.

Overview diagram:

~~~mermaid
flowchart LR
    A[Customer content] --> B[DEK]
    B --> C[Encrypt content]
    C --> D[Ciphertext at rest]
    B --> E[Wrap DEK with KEK]
    F[KEK] --> E
    E --> G[Wrapped DEK]
    D --> H[Storage]
    G --> H
~~~

When reading data, the service retrieves the wrapped DEK, requests the key management mechanism to unwrap the DEK, and then uses the DEK to decrypt the content. Separating the DEK and KEK makes it possible to change or control the key-protecting key without redesigning the entire data storage layout.

In the default model, Google manages the KEKs and related operational processes. Customers cannot view or set custom rotation schedules for those default keys, nor do they have key usage logs at the key-administration level as with CMEK. Multiple customers may share certain KEKs in Google's infrastructure; therefore, the default model does not establish a separate per-customer key boundary.

This does not mean default data is stored in plaintext. Data is still encrypted and protected by Google's key management system, access controls, and internal auditing. The main differences lie in ownership, observability, and customer control over the keys.

## 3. Components in Cloud KMS

Cloud KMS is Google Cloud's cryptographic key management service. When a service supports CMEK, a customer-managed Cloud KMS key can act as the KEK protecting the resource's DEKs.

Common concepts:

| Component | Meaning |
|---|---|
| Project | Scope for managing IAM, APIs, quotas, and resources |
| Location | Geographic location of the key ring and keys; must match the location requirements of the service using the key |
| Key ring | Logical grouping containing CryptoKeys within a location |
| CryptoKey | Resource representing a logical key, containing configuration and key versions |
| CryptoKeyVersion | Version containing the actual cryptographic key material |
| Key rotation | Creating a new key version and switching the primary version to the new one |
| Service agent | Google Cloud service identity used to perform encrypt/decrypt operations on behalf of the service |

The resource structure has the form:

~~~text
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME/cryptoKeyVersions/VERSION
~~~

A CryptoKey can have multiple versions. A new version is created when the key is rotated; older versions must generally be retained to decrypt data that was protected by them. IAM permissions granted on a CryptoKey apply to the versions of that key.

### Protection level

When creating a key, you choose an appropriate protection level:

- **SOFTWARE:** Cloud KMS protects and uses the key material via the service's software mechanisms. This is a common choice for many workloads.
- **HSM:** Key material is generated and used within Cloud HSM security hardware. Choose this level when hardware control requirements or compliance standards mandate an HSM.
- **EXTERNAL** or **EXTERNAL_VPC:** Cloud KMS uses a key residing in a supported External Key Manager (EKM) system. The key resides outside the standard Cloud KMS key storage boundary; connectivity and availability of the external system become part of the data access path.

Not every GCP service supports every protection level. You must check the service compatibility matrix before designing your architecture.

## 4. Key Management Options on GCP

### 4.1. Google-owned and Google-managed keys

This is the default option:

- Google owns and manages the keys.
- Automatically applied to customer content stored in Google Cloud services.
- Requires no configuration or key lifecycle operations.
- Default encryption is included with the storage service.
- Customers do not directly manage key versions, rotation schedules, or usage permissions on default KEKs.

Use this when standard data protection requirements are already met by default encryption and the organization does not need independent key control.

### 4.2. Customer-Managed Encryption Keys (CMEK)

CMEK refers to keys that customers create and manage in Cloud KMS, which an integrated GCP service uses to protect data. CMEK typically acts as the KEK in envelope encryption; the service still handles data encryption and users access resources in much the same way as in the default model.

CMEK adds the following capabilities:

- Customers control key creation, location, protection level, and IAM permissions.
- Can set rotation schedules, create versions, disable, or schedule destruction of versions.
- Can view key metadata, track resources using the key in services that support key tracking, and inspect related audit logs.
- Can establish an isolated cryptographic boundary per customer or workload.
- Can use intentional key destruction to make data protected by that key unreadable (crypto-shredding), after assessing the full impact.

CMEK only works with services that have CMEK integration or compliance. The list of supported services and the scope of protected data may vary. A single product may have multiple separate CMEK integrations for different data types, so you should not assume that enabling CMEK on one resource will protect all data associated with that product.

CMEK also does not mean end users must be granted direct permissions on the key. Typically, the service's service agent receives the Cloud KMS CryptoKey Encrypter/Decrypter permission; the service uses this identity to encrypt or decrypt while processing requests.

### 4.3. CMEK with Cloud KMS Autokey

Autokey automatically creates key rings and CryptoKeys on demand when users create integrated resources. Autokey also helps create service agents and assign the required IAM permissions according to supported workflows.

Autokey is useful when an organization wants to:

- Standardize key configurations across multiple projects or workloads.
- Reduce manual key provisioning and assignment operations.
- Apply recommended practices for location, HSM protection level, separation of duties, and rotation schedules.
- Retain management control and observability over the created CMEKs.

Autokey does not turn every service into a CMEK-supported service. Only use it for resource types and services that integrate with Autokey. If you need custom protection levels or rotation schedules outside Autokey's configuration, evaluate creating CMEK manually.

### 4.4. Cloud External Key Manager (Cloud EKM)

Cloud EKM allows Cloud KMS to use keys stored in a key management system external to Google Cloud. This model is suitable when an organization needs to keep key material in a system operated by itself or a specialized vendor.

In return, the data access path depends on connectivity to the EKM, quotas, latency, and the availability of the external system. If the service cannot use the external key, operations requiring data decryption may fail. Redundancy, monitoring, and incident response procedures must be designed for both sides. Not every service that supports Cloud KMS keys supports Cloud EKM keys.

### 4.5. Customer-Supplied Encryption Keys (CSEK)

CSEK is a model where certain services allow customers to send a key along with an API request so the service uses that key to protect data. CSEK differs from CMEK: keys are provided per request, and the customer is responsible for storing and re-supplying the exact same key when data access is needed.

Cloud Storage still provides documentation for CSEK within the service's supported scope. For Compute Engine, CSEK is deprecated for Persistent Disk, image, machine image, and snapshot resources as of 2026-07-20, and is scheduled for complete removal on 2027-07-20. For new Compute Engine resources, evaluate CMEK as the replacement. Do not apply a single conclusion about CSEK across all services; you must check the support status of each service individually.

### Quick Comparison

| Option | Who controls the key? | Customer control capability | When to consider |
|---|---|---|---|
| Google default encryption | Google | Low at the KEK level; automatic and zero-ops | Standard workloads |
| Manual CMEK | Customer via Cloud KMS | High: IAM, location, protection level, rotation, key state, and auditing | Need key control or an isolated cryptographic boundary |
| CMEK with Autokey | Customer; Autokey provisions automatically | High, reduces manual key creation and assignment | Need to standardize CMEK at scale across many workloads |
| Cloud EKM | External organization/EKM provider | Keys are kept outside Google Cloud | Requirement to control key material externally |
| CSEK | Customer | Customer supplies and retains the keys | Only when the specific service still supports it and this model meets requirements |

## 5. Key Model Selection Process

You can use the following questions to select an option:

1. **Does the service support CMEK?** If not, you must use default encryption or an application-layer encryption approach permitted by the service.
2. **Is there a requirement for independent key ownership or control?** If not, default encryption is usually the appropriate starting point.
3. **Do you need to audit key usage or separate key administrators from workload operators?** If yes, evaluate CMEK.
4. **Do you need to automate key creation and assignment across multiple projects?** If yes, check Autokey.
5. **Must the key material reside outside Google Cloud?** If yes, evaluate Cloud EKM and service compatibility.
6. **Are there specific data residency or HSM protection level requirements?** Verify location, protection level, and organization policies before creating keys.
7. **Can the operations team maintain key access throughout the entire data lifecycle?** If not, CMEK can introduce risks of outage or data loss if a key is disabled or destroyed.

For example: an application storing public images with no special key-control requirements can use default encryption. A data repository containing customer records that requires separation of key administration, auditing of key usage, and lifecycle control can choose CMEK. If regulations require key material to reside in an HSM system outside Google Cloud, evaluate Cloud EKM and verify whether the service supports it.

## 6. Hands-On: Protecting a Cloud Storage Bucket with CMEK

This example creates a Cloud KMS key in a key management project, grants permissions to the Cloud Storage service agent of the data project, and sets the key as the default encryption key for the bucket.

Assume:

- **KMS_PROJECT_ID:** key management project.
- **DATA_PROJECT_ID:** project containing the bucket.
- **LOCATION:** location of the bucket and key ring, for example **asia-southeast1** if that is the chosen workload location.
- **KEY_RING:** key ring name.
- **KEY_NAME:** CryptoKey name.
- **BUCKET_NAME:** globally unique bucket name.

### Step 1: Enable the API and create a key ring

Enable the Cloud KMS API in the key management project:

~~~bash
gcloud services enable cloudkms.googleapis.com \
  --project=KMS_PROJECT_ID
~~~

Create a key ring in a location compatible with the bucket:

~~~bash
gcloud kms keyrings create KEY_RING \
  --location=LOCATION \
  --project=KMS_PROJECT_ID
~~~

A key ring is bound to a location upon creation. For Cloud Storage, the key ring used for a bucket must be in a location compatible with the bucket. For other services, read that service's specific location requirements.

### Step 2: Create a CryptoKey

Create a symmetric key with purpose set to encryption:

~~~bash
gcloud kms keys create KEY_NAME \
  --keyring=KEY_RING \
  --location=LOCATION \
  --purpose=encryption \
  --protection-level=software \
  --project=KMS_PROJECT_ID
~~~

The full resource name of the key has the form:

~~~text
projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME
~~~

In environments requiring HSM, evaluate **--protection-level=hsm** and confirm that the location supports Cloud HSM. Choose the protection level based on security requirements and compatibility, not merely the highest selectable option.

### Step 3: Grant permissions to the Cloud Storage service agent

Cloud Storage uses the service agent of the project containing the bucket to call Cloud KMS. Grant the CryptoKey Encrypter/Decrypter permission to the right service agent on the right key:

~~~bash
gcloud storage service-agent \
  --project=DATA_PROJECT_ID \
  --authorize-cmek=projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME
~~~

The command above retrieves or creates the required service agent and grants permission to use the CMEK. If the organization performs permission assignment manually, the required role is **roles/cloudkms.cryptoKeyEncrypterDecrypter**. When the key resides in a separate project, permissions on the key must be granted to the data project's service agent.

Users or workloads accessing objects do not need direct Cloud KMS permissions just to read objects. The Cloud Storage service agent performs key operations on behalf of the service; IAM on the bucket still determines whether the caller is allowed to read the object.

### Step 4: Create a bucket with CMEK

~~~bash
gcloud storage buckets create gs://BUCKET_NAME \
  --location=LOCATION \
  --default-encryption-key=projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME \
  --project=DATA_PROJECT_ID
~~~

For an existing bucket, you can set or change the default key:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --default-encryption-key=projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME \
  --project=DATA_PROJECT_ID
~~~

The bucket's default key is used for newly written objects after configuration. Changing the default key does not automatically re-encrypt previously existing objects.

### Step 5: Verify the configuration

View the bucket's default key:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(default_kms_key)" \
  --project=DATA_PROJECT_ID
~~~

When verifying a specific object, inspect the object's metadata, including the **kmsKeyName** field if present. With Cloud Storage, CMEK protects object content and certain checksums such as CRC32C and MD5; much of the remaining metadata is still protected by Google's server-side keys. Therefore, do not use CMEK as a reason to place sensitive information in object names or metadata.

## 7. Key Lifecycle: Rotation, Disabling, and Destruction

Key management does not end when a CryptoKey is created. Each key version may be protecting long-lived data, so lifecycle operations must be tied to resource inventories and recovery procedures.

### Rotation does not mean re-encrypting data

When rotating a symmetric key in Cloud KMS, the system creates a new CryptoKeyVersion and sets it as the primary version. Services can use the new version to protect new DEKs. Old versions still need to exist to decrypt previously encrypted data.

How a service adopts a new version depends on the service's integration:

- Some services automatically re-wrap DEKs with the new version.
- Some services only use the new version for data or objects created after rotation.
- Some services require a migration, rewrite, or resource recreation operation.

With Cloud Storage, objects written before a version change may still depend on the old key version. If you need to move data to a new key or version, you must perform an object rewrite according to Cloud Storage documentation and verify the result. Do not delete old versions immediately after rotation.

### Disabling a key version

When a key version is disabled, the service cannot use that version for cryptographic operations once the state takes effect. Data depending on that version may become unreadable. Disabling is reversible by re-enabling the version if it has not been destroyed.

This is a useful incident-response measure when key compromise is suspected, but it can also cause an outage. Before executing it, you must know which resources depend on the key and identify who has permission to restore it.

### Destroying a key version

Destroy is a high-consequence operation. Once a version's key material is destroyed, data that can only be decrypted by that version cannot be recovered by re-enabling the key. Key destruction can be used for crypto-shredding or data lifecycle handling, but only after confirming:

- No resources still need that version for reading or recovery.
- Data that must be retained has been migrated or re-encrypted with an active key.
- Snapshots, backups, older objects, and disaster recovery environments have been inventoried.
- Retention policies, legal holds, and compliance requirements permit destruction.
- Approval workflows and the destruction waiting period have been completed.

Do not use the destroy operation as a routine cleanup step without verifying the usage of each version.

## 8. IAM, Auditing, and Safe Operations

CMEK provides greater control but also introduces an operational dependency. If the service agent loses permission to use the key, the key is disabled, or the key project experiences an issue, the storage service may fail to decrypt data.

Recommended practices:

1. **Separation of duties:** Cloud KMS administrators do not necessarily have to be workload administrators. Grant key management roles to the security team and key usage permissions to the required service agents.
2. **Least privilege:** Grant **roles/cloudkms.cryptoKeyEncrypterDecrypter** on the specific CryptoKey when possible; avoid granting broad permissions at the project or organization level unless necessary.
3. **Location management:** Place key rings in locations compatible with resources and residency requirements. For services with special location requirements, follow the service's integration documentation.
4. **Audit log monitoring:** Monitor key administration operations and cryptographic activity. Define which logs to enable, where to store them, retention periods, and alerts for sensitive actions.
5. **Recovery testing:** Test key re-enabling, version switching, and data recovery procedures in a test environment.
6. **Dependency management:** Maintain an inventory mapping keys, key versions, projects, service agents, and protected resources.
7. **Cost and quota planning:** Cloud KMS incurs costs per key version and operation; HSM and EKM have their own quotas, limits, and pricing structures. Check current pricing and quotas before deploying at scale.
8. **Organization policies:** In multi-project environments, consider Organization Policies to restrict which projects can be used as CMEK sources, which services require CMEK, or which protection levels are permitted.

## 9. Common Design Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Assuming every service supports CMEK | Resources cannot use the key as intended in the design | Check CMEK integrations and the scope of protected data |
| Creating a key ring in the wrong location | Service rejects the key configuration or fails location requirements | Match the resource location with the service's requirements |
| Forgetting to grant permissions to the service agent | Creating or reading resources with CMEK fails | Grant the right role on the right CryptoKey to the service agent |
| Granting KMS permissions to all developers | Over-privileging key management or key usage | Separate key administration permissions, key usage permissions, and data access permissions |
| Rotating and immediately destroying the old version | Older data may become undecryptable | Check how the service handles rotation and inventory dependencies before destroying |
| Assuming changing the default key re-encrypts old data | Older objects or resources still use the previous key | Perform rewrite/migration per the service's documentation |
| Having no fallback/redundancy plan for Cloud EKM | An EKM outage can disrupt data access | Verify SLAs, connectivity, quotas, monitoring, and runbooks |
| Using Compute Engine CSEK for new resources | Cannot create resources with a deprecated feature | Choose CMEK and plan migration for legacy resources |

## 10. Pre-Production Checklist for CMEK

- [ ] Accurately identified the types of data and resources to protect.
- [ ] Confirmed that the service and resource type support CMEK.
- [ ] Selected Google default, manual CMEK, Autokey, or Cloud EKM based on requirements.
- [ ] Selected the appropriate project, location, and protection level.
- [ ] Separated key administration roles from workload operations roles.
- [ ] Service agent has least-privilege permissions on the CryptoKey.
- [ ] Reviewed costs, quotas, and integration limits.
- [ ] Configured audit logs, monitoring, and alerts for sensitive operations.
- [ ] Defined the rotation approach and legacy data migration strategy.
- [ ] Tested disabling/enabling, recovery, and key incident response.
- [ ] Maintained an inventory of resources dependent on each CryptoKeyVersion.
- [ ] Established an approval workflow prior to destroying key versions.

## Conclusion

Google Cloud default encryption provides automatic encryption at rest for customer content and is a suitable foundation for many workloads. CMEK adds key control, auditing, and cryptographic boundaries for supported services. Autokey reduces the operational effort of provisioning CMEK; Cloud EKM addresses the need to keep keys in external systems but adds connectivity and availability dependencies.

The most important decision is choosing a level of control that matches data requirements and the ability to operate keys throughout the resource lifecycle. A CMEK key only strengthens protection when IAM is properly configured, the service agent continuously retains valid permissions, old versions are retained long enough, and recovery procedures are verified.

## References

- [Default encryption at rest](https://cloud.google.com/docs/security/encryption/default-encryption)
- [Customer-managed encryption keys (CMEK)](https://cloud.google.com/kms/docs/cmek)
- [Cloud KMS with Autokey](https://cloud.google.com/kms/docs/kms-autokey)
- [Cloud KMS key rotation](https://cloud.google.com/kms/docs/key-rotation)
- [Use customer-managed encryption keys with Cloud Storage](https://cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Cloud Storage customer-managed encryption keys](https://cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Deprecation of CSEK in Compute Engine](https://cloud.google.com/compute/docs/deprecations/csek-deprecation-in-compute-engine)
