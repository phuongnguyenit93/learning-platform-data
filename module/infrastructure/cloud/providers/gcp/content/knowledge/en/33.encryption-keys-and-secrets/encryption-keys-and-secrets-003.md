# CMEK and Customer-Managed Key Integration

When deploying workloads on Google Cloud, stored data is encrypted by default. For many systems, the default mechanism already meets data protection requirements. However, some organizations need to decide for themselves which key protects the data, where the key resides, who is allowed to use the key, the key rotation schedule, and when decryption access is revoked. **Customer-managed encryption keys (CMEK)** meet those control needs through Cloud Key Management Service (Cloud KMS) and Google Cloud services with CMEK integration.

In the CLOUD_PROVIDERS_GCP module, CMEK relates directly to how projects, IAM, storage, databases, and workload operations are organized. A sound design must combine resource location, service agent permissions, key lifecycle policies, recoverability, and cost. Simply enabling the CMEK option on a resource is not enough to ensure the system can operate safely over the long term.

After this lesson, you will be able to:

- Distinguish between Google Cloud default encryption, CMEK, customer-supplied keys, and application-side encryption.
- Describe how CMEK protects a data encryption key (DEK) using a key encryption key (KEK).
- Explain the roles of key ring, CryptoKey, key version, and service agent.
- Choose appropriate locations, protection levels, usage scopes, and IAM permissions for keys.
- Integrate CMEK into a Cloud Storage resource using the Google Cloud CLI.
- Plan key rotation, key replacement, monitoring, and incident handling without losing data access.

## 1. What Problem Does CMEK Solve?

### Default encryption remains the baseline protection layer

Google Cloud encrypts stored data by default. Services manage the underlying keys and perform most encryption and decryption operations on the customer's behalf. Users do not need to create key rings or grant Cloud KMS permissions to use default encryption.

With default encryption, customers still manage resource access using IAM, network configuration, organization policies, and other safeguards. However, customers do not directly manage each underlying encryption key, its rotation schedule, or usage logs for those keys.

CMEK adds a layer of control: customers create or select a key in Cloud KMS, manage permissions to use the key, and attach that key to a resource in a CMEK-supported service. The service still handles encryption and decryption during normal access flows; Cloud KMS performs the required operations with the customer-managed key.

### Comparing encryption options

| Mechanism | Who manages the key? | Integration method | When to consider? |
|---|---|---|---|
| Google Cloud default encryption | Google manages underlying keys | Service automatically encrypts data at rest | Suitable for most workloads needing encryption at rest without operating keys |
| CMEK | Customer manages keys in Cloud KMS | Integrated service calls Cloud KMS via service agent | When control over location, permissions, lifecycle, rotation, and key revocation is needed |
| Customer-supplied encryption key (CSEK) | Customer supplies the key on each request; support depends on the service | Application sends the key per request rather than referencing a configured CMEK | Specific scenarios, such as Cloud Storage requiring a customer-supplied key per operation |
| Application-side encryption (client-side encryption) | Customer manages all keys and the encryption process | Application encrypts before sending data to Google Cloud | When the application must keep data as ciphertext before the cloud service receives it |

CMEK does not replace IAM, VPC Service Controls, data classification, application secret management, or client-side encryption. CMEK focuses on controlling data-at-rest encryption keys in integrated services. You must verify the exact resource types and data types protected; a product may support CMEK for certain components but not for all data associated with that product.

## 2. How Does CMEK Work?

Services integrated with CMEK typically use **envelope encryption**. Large data is encrypted with a dedicated data key called a DEK. CMEK acts as the key encryption key (KEK) used to protect the DEK.

Overview workflow:

1. The service generates or uses a DEK to encrypt the data.
2. The service asks Cloud KMS to use the CMEK to encrypt (wrap) the DEK.
3. The service stores the encrypted data alongside the DEK in its protected form.
4. When data needs to be read, the service agent asks Cloud KMS to decrypt (unwrap) the DEK.
5. The service uses the DEK to decrypt the data and returns the result according to the caller's resource permissions.

~~~mermaid
flowchart TD
    U[User or application] --> S[Google Cloud service]
    S -->|Request to create or open data| A[Service's service agent]
    A -->|IAM permissions on key| K[Cloud KMS - CMEK]
    K -->|Wrap or unwrap DEK| A
    A --> S
    S -->|Use DEK to encrypt or decrypt| D[(Encrypted data)]
~~~

The diagram illustrates the logical relationship; internal call ordering and how DEKs are stored may vary across services.

An important point is that users reading a bucket, table, or disk typically do not need direct Cloud KMS CryptoKey Encrypter/Decrypter permissions. The service's service agent performs encryption and decryption operations behind the scenes. Users still must have appropriate IAM permissions on the resource. If the service agent loses permission to use the key, or the key version is disabled or destroyed, operations requiring decryption may fail even though the user still has read permissions on the resource.

Cloud KMS does not grant users the ability to view or export the raw key material of a key version. Cloud KMS performs cryptographic operations on behalf of an authorized principal.

## 3. Understanding the Cloud KMS Resource Structure

A CMEK key is organized according to the following hierarchy:

~~~text
Google Cloud project
└── Location
    └── Key ring
        └── CryptoKey
            ├── CryptoKeyVersion 1
            ├── CryptoKeyVersion 2
            └── CryptoKeyVersion 3 (primary)
~~~

| Component | Meaning | Operational decision |
|---|---|---|
| Project | Governance, IAM, billing, and API boundary | Can place keys in a dedicated project to separate key admin permissions from workload admin permissions |
| Location | Region where keys are stored and operations occur | Must be compatible with the resource's location and service-specific rules |
| Key ring | Logical grouping containing keys in the same location | Used to organize by environment, service, or administrative scope |
| CryptoKey | Logical identifier of the key referenced by resources | This is the CMEK resource services typically accept in configuration |
| CryptoKeyVersion | Version containing the key material used for cryptographic operations | Can be enabled, disabled, or scheduled for destruction per governance processes |

A CryptoKey can have multiple versions. The primary version is used for new encryption operations according to the service's behavior. Older versions generally need to be retained to decrypt data already protected by those versions. Therefore, creating a new version does not mean you can immediately delete older versions.

CMEK keys used for data encryption must have the symmetric purpose ENCRYPT_DECRYPT and the algorithm GOOGLE_SYMMETRIC_ENCRYPTION as required by Google Cloud CMEK integrations. When creating a key with gcloud, the corresponding purpose value is encryption.

### Choosing the key protection level

Cloud KMS supports the main protection levels:

- **Software:** cryptographic operations are performed by Cloud KMS software. This is suitable for many standard workloads.
- **HSM:** cryptographic operations take place inside Cloud HSM. Consider when hardware protection requirements or compliance policies mandate HSM.
- **External / External VPC:** keys are kept in an external key management system via Cloud External Key Manager (Cloud EKM). This option is useful when the organization must keep key material inside its own system or a supported partner's system.

Cloud HSM and Cloud EKM have different quota, cost, connectivity, and availability requirements compared to software keys. When using Cloud EKM, the ability to encrypt or decrypt also depends on the external key system and connectivity to it.

Additionally, Cloud KMS allows importing externally generated key material into a Cloud KMS key (BYOK). After import, the key material is managed within Cloud KMS according to the key configuration. This differs from Cloud EKM, where key material remains inside the external system. Generating and importing your own key material increases responsibility for protecting the original copy, automating new version imports, and controlling recovery workflows.

### Cloud KMS Autokey

Cloud KMS Autokey automatically provisions key rings and CMEKs when creating or updating resources belonging to supported services. Autokey can also automatically grant required permissions to the service agent. This mechanism reduces manual steps and helps enforce consistent key creation policies at the folder or project level.

Autokey is suitable when automatically generated key settings meet requirements for location, protection level, key granularity, and separation of duties. The organization still needs to govern who can request key provisioning, who can modify or destroy key versions, and monitor changes created by Autokey.

## 4. Designing CMEK Integration Before Deployment

### Verifying services and data scope

Do not assume every resource in a service supports CMEK. Check the list of CMEK-integrated services and the documentation for the exact resource type. For example:

| Service | Example protectable scope | Identity requiring permissions |
|---|---|---|
| Cloud Storage | Objects in a bucket, via bucket default key or per-object specified key | Cloud Storage service agent of the project containing the bucket |
| BigQuery | Dataset, table, or query results depending on configuration | BigQuery service account of the project running BigQuery |
| Compute Engine | Supported Persistent Disk, snapshot, and machine image | Compute Engine service agent of the project containing the resource |
| Google Kubernetes Engine (GKE) | Node boot disks and attached Persistent Disks; application-layer Kubernetes Secret encryption is a separate integration | Compute Engine service agent for disk CMEK |

The list above is only an example. Open the service's CMEK documentation to confirm supported resource types, locations, limitations, and current permission-granting procedures before deployment.

### Choosing projects and separation of duties

A common design places workloads in a data project and key rings in a separate key management project. This separation ensures the application operations team does not implicitly have permissions to modify or destroy the keys protecting the data.

At least three responsibility groups should be distinguished:

- **Key administrator:** creates key rings, creates keys, configures rotation, and manages key version states.
- **Resource administrator:** creates buckets, datasets, disks, or resources to be protected and selects the appropriate CMEK.
- **Service agent:** receives only permission to use the key for encryption and decryption as required by the service integration.

Do not grant Owner or Editor just to troubleshoot a CMEK error. Grant required permissions at the narrowest scope. The role commonly used for a service agent is Cloud KMS CryptoKey Encrypter/Decrypter, IAM role ID roles/cloudkms.cryptoKeyEncrypterDecrypter, assigned directly on the CryptoKey if the operating model allows.

### Choosing location and key granularity

The key ring location must be compatible with the resource location. For regional or zonal resources, the key typically must be in the same region or a location permitted by the service. For multi-region resources, the key ring location must correspond to that multi-region. Some services do not support the global location or have specific rules for dual-regions; check each service's documentation.

Google recommends designing keys with a manageable scope, typically per project, per location, per service, and where appropriate per resource. Sharing a key too broadly increases the blast radius if a version is disabled or destroyed. Conversely, creating too many keys increases administrative overhead. Choose granularity aligned with data boundaries, compliance requirements, and operational capacity.

## 5. Hands-On: Protecting a Cloud Storage Bucket with CMEK

This example creates a key in a separate key management project and uses that key as the default encryption key for new objects in a bucket. Replace the sample values with valid project IDs, bucket name, and location in your environment.

### Step 1: Prepare variables and enable the Cloud KMS API

~~~bash
export KEY_PROJECT_ID="security-keys-prod"
export DATA_PROJECT_ID="application-data-prod"
export LOCATION="asia-southeast1"
export KEY_RING="storage-ring"
export KEY_NAME="customer-data"
export BUCKET_NAME="example-customer-data-bucket"

gcloud services enable cloudkms.googleapis.com --project="$KEY_PROJECT_ID"
~~~

The project storing keys must have the Cloud KMS API enabled. The deployment account must have permissions to create key rings, CryptoKeys, and update the key's IAM policy. The account also needs permissions to create buckets in DATA_PROJECT_ID.

### Step 2: Create the key ring and CryptoKey

~~~bash
gcloud kms keyrings create "$KEY_RING" \
  --location="$LOCATION" \
  --project="$KEY_PROJECT_ID"

gcloud kms keys create "$KEY_NAME" \
  --location="$LOCATION" \
  --keyring="$KEY_RING" \
  --purpose=encryption \
  --protection-level=software \
  --project="$KEY_PROJECT_ID"
~~~

Construct the key's resource name for use in service configurations:

~~~bash
export KEY_RESOURCE="projects/$KEY_PROJECT_ID/locations/$LOCATION/keyRings/$KEY_RING/cryptoKeys/$KEY_NAME"
~~~

In this example, key material is generated and managed by Cloud KMS. If HSM or external keys are required, select the corresponding protection level and key creation workflow before attaching the key to resources.

You can configure an automatic rotation schedule for the CryptoKey. The NEXT_ROTATION_TIME value must be a future timestamp in ISO 8601 format; choose a timestamp aligned with your organization's policy:

~~~bash
export NEXT_ROTATION_TIME="2026-12-01T00:00:00Z"

gcloud kms keys set-rotation-schedule "$KEY_NAME" \
  --location="$LOCATION" \
  --keyring="$KEY_RING" \
  --rotation-period=90d \
  --next-rotation-time="$NEXT_ROTATION_TIME" \
  --project="$KEY_PROJECT_ID"
~~~

### Step 3: Grant permissions to the Cloud Storage service agent

Cloud Storage uses the service agent of the project containing the bucket to perform encryption and decryption. Use the following command to retrieve the service agent identity and grant permission to use the CMEK:

~~~bash
gcloud storage service-agent \
  --project="$DATA_PROJECT_ID" \
  --authorize-cmek="$KEY_RESOURCE"
~~~

This command grants permission to use the key to the Cloud Storage service agent of DATA_PROJECT_ID. If configuring IAM manually instead of running the command above, identify the exact service agent of the project containing the bucket and assign roles/cloudkms.cryptoKeyEncrypterDecrypter on the exact CryptoKey.

### Step 4: Create the bucket with the default key

~~~bash
gcloud storage buckets create "gs://$BUCKET_NAME" \
  --location="$LOCATION" \
  --default-encryption-key="$KEY_RESOURCE" \
  --project="$DATA_PROJECT_ID"
~~~

The bucket uses the CMEK as the default key for objects written after the configuration takes effect. You can also update an existing bucket using gcloud storage buckets update with the --default-encryption-key flag.

To inspect the default key configuration:

~~~bash
gcloud storage buckets describe "gs://$BUCKET_NAME" \
  --format="default(default_kms_key)"
~~~

If a separate key is needed for a specific object, Cloud Storage allows specifying a CMEK in the upload command via the --encryption-key flag. When a bucket has a default key and an object write request specifies a different key, the key specified in the request takes precedence for that object.

### Step 5: Verify data and scope of application

Upload a test object, read it back using an identity with bucket access permissions, and inspect metadata to confirm the object uses the expected key resource. User object reads still rely on Cloud Storage IAM; users do not need direct Cloud KMS decrypt permissions if the service agent has been granted the proper permissions.

Changing a bucket's default key does not automatically re-encrypt existing objects. Older objects continue to use the key that protected them. To move legacy data to a new key, perform an object rewrite or use Storage batch operations for large datasets.

## 6. Rotating, Replacing, and Revoking Keys

### Rotating key versions

When Cloud KMS rotates a CryptoKey, the system creates a new key version and sets that version as primary according to the configured schedule. Older versions may still be needed to decrypt DEKs that were protected previously.

Rotating a key version does not mean older data has been re-encrypted. Behavior depends on the service:

- With Cloud Storage, objects written after the new key version becomes primary will use the new version when the bucket or write request uses that CryptoKey. Older objects continue to depend on the version that protected them.
- With BigQuery, rotating a CryptoKey does not implicitly re-encrypt existing tables. Tables may continue using the key version bound to the table when it was created.
- Some integrations may automatically re-wrap or re-encrypt DEKs in their own ways. Check the exact service documentation for completion timing and conditions.

You can configure an automatic rotation schedule or create new versions manually. A rotation schedule creates new key versions regularly, but does not replace a plan for inventorying data that depends on older versions.

### Replacing one CryptoKey with another CryptoKey

Key replacement is the process of migrating resources from one CryptoKey to another CryptoKey. This is a different operation from creating a new version within the same CryptoKey. General workflow:

1. Create the target key in an appropriate location and verify the service agent has permission to use it.
2. Update default configurations or per-resource configurations so newly written data uses the target key.
3. List resources and data still using the old key.
4. Re-encrypt or rewrite legacy data following the service's guidelines.
5. Verify read permissions, backup jobs, recovery workflows, and data processing pipelines after migration.
6. Only disable the old key version once you have confirmed no data still needs that version for decryption.

Do not delete the old key merely because the default configuration has been changed. The new configuration may affect only newly written data, while historical data still depends on the old key.

### Disabling or destroying key versions

Disabling a key version blocks cryptographic operations that require that version. If needed, administrators can re-enable a disabled version. Destroying a key version is irreversible once the destruction process completes; data depending on that version may permanently lose decryption capability.

Before disabling or destroying, inventory all resources and data dependent on the version, including stored data, snapshots, backups, and infrequently used workloads. With Cloud Storage, object metadata includes the kmsKeyName field to help identify the key protecting an object. Only proceed with destruction when retention policies, recovery requirements, and data owners have been checked.

Revoking the service agent's IAM permissions can also prevent the service from decrypting data. Therefore, IAM changes on a CryptoKey must be treated as changes that affect application availability.

## 7. IAM, Monitoring, and Reliability

### Applying least privilege and separation of duties

- Only grant roles/cloudkms.cryptoKeyEncrypterDecrypter to the exact service agent and exact key needed.
- Restrict the number of people allowed to create, change IAM, disable, or destroy key versions.
- Separate the project holding keys from the project holding workloads when separation of duties is required.
- Do not grant broad KMS permissions to application users if they only need to read or write resources via service APIs.
- Check inherited permissions at the project, folder, and organization levels to avoid accidentally broadening key usage scope.

### Monitoring key activity and health

When operating CMEK, monitor:

- IAM policy changes on CryptoKeys and state changes on key versions.
- Encryption, decryption operations, and key access errors in Cloud Audit Logs under appropriate audit configurations.
- Resources currently using each CryptoKey and key version.
- Key versions approaching scheduled rotation, disabled, or pending destruction.
- Quota errors, latency, or connectivity loss with Cloud EKM if external keys are used.
- Data readability after key changes, permission updates, or workload redeployments.

Cloud KMS provides dashboards and inventory features to help track key usage and dependent resources. Combine this data with logs from storage services, databases, and workload monitoring systems.

### Ensuring data accessibility

CMEK puts key state in the critical data path. If the key or the service agent's permissions are unavailable, read or write operations may fail. With Cloud EKM, the external key system and the network path to it also become part of reliability.

An operational plan should include:

- Designated owners for key incident response and personnel authorized to restore key versions.
- A procedure to verify service agent permissions after creating projects or enabling new services.
- Alerts prior to scheduled destruction times and an approval workflow for key lifecycle changes.
- Data recovery testing in a representative environment, including scenarios where a key is disabled and re-enabled.
- Fallback plans for Cloud EKM connectivity, quotas, and dependencies if used.
- A list of resources and backups dependent on keys for auditing and incident response.

## 8. Common Errors and Troubleshooting

| Symptom | Common cause | Inspection steps |
|---|---|---|
| Resource creation returns Cloud KMS permission error | Service agent does not exist yet or lacks permissions on the CryptoKey | Identify the exact service agent of the resource's project; inspect the key's IAM policy |
| Reports incompatible location | Key ring is in a different location or violates multi-region/dual-region rules | Match the resource's location against the service's specific CMEK rules |
| Reading data fails even though user has bucket/table permissions | Service agent lost permissions, or key version is disabled or destroyed | Check KMS permissions, key version state, and service logs |
| Older data still shows the pre-rotation key | Rotation only creates a new version; older data has not been re-encrypted | Inspect per-resource metadata or encryption info; run rewrite if needed |
| Cloud EKM returns errors or slow operations | Issues with external key system, connectivity, quota, or EKM policy | Check EKM connection status, external service, network path, and quota |
| Part of a product's data does not use CMEK | CMEK supports only certain resource types or data layers | Check the integration matrix and specific documentation for the feature in use |

When troubleshooting, check in order: exact CryptoKey resource name, exact project and location, exact service agent, IAM policy on the key, key version state, and then expand to quotas or the EKM system. After granting permissions, you may need to wait for IAM changes to propagate before retrying.

## 9. Cost and Architectural Choices

Cloud KMS incurs costs related to the number of key versions and cryptographic operations. Cloud HSM and Cloud EKM also have separate quotas and operational costs. An overly granular key design can increase the number of key versions to manage; an overly shared key design can increase the blast radius during an incident.

When estimating cost and complexity, account for:

- Number of CryptoKeys, active key versions, and rotation schedules.
- Frequency of encryption and decryption operations and quota limits of the chosen protection level.
- Costs of Cloud HSM or external key management systems.
- Effort to re-encrypt historical data during key replacement.
- Retention duration for older key versions to ensure data readability and backup recovery.
- Operational staffing for on-call duties, IAM audits, log monitoring, and incident response.

Not every workload needs CMEK. If the goal is simply encryption at rest, Google Cloud's default encryption may already suffice. Choose CMEK when the benefits of lifecycle control, location, access control, or compliance requirements justify the added cost and operational responsibility.

## 10. Pre-Production Checklist for CMEK

- [ ] Confirmed the exact service, resource type, and data protected by CMEK.
- [ ] Selected the appropriate key management project, location, and protection level.
- [ ] Decided on shared versus dedicated scope for each key.
- [ ] Created CryptoKeys with the symmetric purpose and algorithm supported by the service.
- [ ] Identified the exact service agent and granted KMS permissions at the narrowest scope.
- [ ] Configured CMEK on resources and verified newly written data uses the right key.
- [ ] Checked whether existing data requires rewriting or re-encryption.
- [ ] Set up rotation schedules and determined how long older key versions must be retained.
- [ ] Set up alerts for IAM changes, key version states, and key usage errors.
- [ ] Tested data recovery and procedures for when a key becomes unavailable.
- [ ] Inventoried backups, snapshots, and workloads dependent on the key before destroying versions.

## 11. Conclusion

CMEK enables organizations to actively control the keys protecting data across integrated Google Cloud services. The effectiveness of CMEK depends on three tightly connected areas: proper key and location design, accurate IAM assignment for service agents, and controlled key lifecycle operations. When deploying, start from the data types to protect, verify service support, test read/write and recovery workflows, and then expand to production workloads.

## References

- [Customer-managed encryption keys (CMEK) – Cloud KMS](https://docs.cloud.google.com/kms/docs/cmek)
- [Recommended practices for using CMEKs – Cloud KMS](https://docs.cloud.google.com/kms/docs/cmek-recommended-practices)
- [Use Cloud KMS keys in Google Cloud](https://docs.cloud.google.com/kms/docs/use-keys-google-cloud)
- [CMEK key rotation – Cloud KMS](https://docs.cloud.google.com/kms/docs/cmek-rotation)
- [Use customer-managed encryption keys – Cloud Storage](https://docs.cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Customer-managed Cloud KMS keys – BigQuery](https://docs.cloud.google.com/bigquery/docs/customer-managed-encryption)
- [Protect resources with Cloud KMS keys – Compute Engine](https://docs.cloud.google.com/compute/docs/disks/customer-managed-encryption)
- [Use customer-managed encryption keys – GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/using-cmek)
