# Separating Key Administration Permissions from Data Access Permissions

In a system running on Google Cloud, the security team may be responsible for creating and rotating encryption keys, while the application only needs to use keys to encrypt or decrypt data for business operations. If the same broad permissions are granted to both groups, an application bug or compromised account could lead to modifying key configurations, granting additional access permissions, or impacting more data than intended.

A secure design must separate three responsibilities: managing key lifecycles and policies, performing cryptographic operations with keys, and reading or writing application data. Google Cloud IAM allows granting these permissions to different identities. When permissions are scoped accurately, the key operations team can manage cryptographic resources, while the workload is limited to using only the specific keys it needs.

## 1. Three Permission Layers to Distinguish

Cloud Key Management Service (Cloud KMS) organizes resources into a hierarchy of project, key ring, CryptoKey, and key version. CryptoKey is the resource representing the logical key; its versions contain the corresponding key material. IAM policies can be attached at multiple levels, and permissions from parent levels inherit down to child resources. Therefore, the scope where a role is bound is just as important as the role name itself.

| Permission Layer | Responsibilities | Identities Typically Granted |
| --- | --- | --- |
| Key administration | Create key rings and CryptoKeys, configure rotation, manage key version states, view or modify IAM policies | Security team or platform team |
| Key usage | Call encrypt, decrypt, sign, or verify operations depending on key type | Application service account or Google Cloud service's service agent |
| Data access | Read, write, list, or manage objects, records, and business secrets | Users and service accounts performing business operations |

These three layers do not substitute for one another. An application with permission to read an object in Cloud Storage does not necessarily have permission to call Cloud KMS directly. Conversely, a service account permitted to use a CryptoKey does not automatically have permission to read objects in a bucket or access data in a database.

For example, the **security-prod** project stores shared keys, while the **orders-prod** project runs the orders service. The security team manages keys in **security-prod**; the orders service's service account is only allowed to use a specific CryptoKey; read and write permissions for order data are granted separately in the data project.

## 2. Selecting IAM Roles by Responsibility

Cloud KMS predefined roles help clarify the purpose of each identity:

| Role | Intended Purpose | Where to Grant |
| --- | --- | --- |
| **roles/cloudkms.admin** | Manage Cloud KMS resources and key access policies | Project or key ring within the admin team's scope |
| **roles/cloudkms.cryptoKeyEncrypterDecrypter** | Encrypt and decrypt using a CryptoKey | Specific CryptoKey the workload needs |
| **roles/cloudkms.cryptoKeyEncrypter** | Encrypt only using a CryptoKey | Specific CryptoKey, if the workload does not need decryption |
| **roles/cloudkms.cryptoKeyDecrypter** | Decrypt only using a CryptoKey | Specific CryptoKey, if the workload only processes encrypted data |
| **roles/cloudkms.viewer** | View Cloud KMS resource metadata | Teams needing to inspect metadata without managing keys |

Administrators typically need permissions to manage key rings, CryptoKeys, key versions, and IAM configurations. Applications typically need only key usage roles. If a workload only encrypts outbound data and does not decrypt data, consider the dedicated encrypter role to narrow permissions. Always inspect the actual permissions in a role and the inheritance scope in IAM policies before deployment.

Bind key usage roles directly on the specific CryptoKey needed. Granting roles at the project level may allow the service account to use many other keys in the project, increasing the blast radius if the application identity is compromised. If an application needs three keys for three different purposes, grant permissions on each corresponding key.

### Permissions to modify IAM policies must also be controlled

Separating administrative roles and usage roles is the first step. A principal with permission to modify the IAM policy of a key ring or CryptoKey can add new bindings, including a binding granting key usage permissions to that same principal. Therefore, if strict separation of duties is required, **setIamPolicy** permissions must also be controlled.

You can use a custom role for certain key lifecycle tasks that excludes IAM policy modification permissions, and then assign policy approval and updates to a separate IAM or security team. When using predefined roles that include policy management permissions, apply change approval workflows, periodic binding reviews, and audit log monitoring. Simply dividing two teams under different names is not sufficient evidence of separation of duties if one team can still grant permissions to itself.

## 3. Granting Permissions to the Exact Identity Performing Cryptographic Operations

For applications calling the Cloud KMS API directly, the identity that needs permissions is the service account the application actually runs as. Do not grant roles to a developer's personal account and let the application share those credentials. Use dedicated service accounts for each workload or appropriate trust boundary.

For example, the orders service runs with the service account **orders-api@orders-prod.iam.gserviceaccount.com** and needs to encrypt and decrypt using CryptoKey **orders-data-key** in project **security-prod**. The administration team creates the key and establishes the policy; after the policy is approved, grant key usage permissions to the service account:

~~~bash
gcloud kms keys add-iam-policy-binding orders-data-key \
  --keyring=prod \
  --location=asia-southeast1 \
  --project=security-prod \
  --member="serviceAccount:orders-api@orders-prod.iam.gserviceaccount.com" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
~~~

This command binds the role on the exact CryptoKey in the key-owning project. Replace the project, key ring, location, CryptoKey, and service account names in the example with actual resources. The key location must be compatible with the location requirements of the service using it.

The application continues receiving data permissions where the data is stored. For instance, if the application needs to read and write objects, grant the appropriate Cloud Storage roles on the bucket or data project. Never grant **roles/cloudkms.admin** to an application service account merely to work around missing encrypt or decrypt permissions.

For large data, applications can use envelope encryption: the application encrypts data with a data encryption key (DEK), then uses Cloud KMS to protect the DEK with a key encryption key (KEK). Cloud KMS protects the data key; the application must still control permissions to read encrypted data, store the wrapped DEK, and handle plaintext in memory. This pattern does not eliminate the need to separate data permissions from key usage permissions.

## 4. Distinguishing Applications Calling Cloud KMS from Services Using CMEK

An application's service account does not always call Cloud KMS directly. When enabling customer-managed encryption keys (CMEK) for a managed service such as Cloud Storage, BigQuery, or Cloud SQL, the Google Cloud service typically performs encryption and decryption operations through that service's service agent.

In the CMEK case:

1. Identify the service agent used by the resource-managing service.
2. Grant **roles/cloudkms.cryptoKeyEncrypterDecrypter** to the service agent on the chosen CryptoKey.
3. Grant data permissions to users or application service accounts on the bucket, dataset, instance, or corresponding resource.
4. Keep CryptoKey administration permissions restricted to the security or platform team.

For example, with a bucket using CMEK, the Cloud Storage service agent needs permission to use the CryptoKey to encrypt and decrypt objects. The application's service account needs Cloud Storage permissions to read or write objects for business operations. The application does not necessarily need direct Cloud KMS permissions when Cloud Storage performs cryptographic operations on behalf of the resource.

Retrieve the exact service agent created or designated by the service according to that service's documentation; do not guess the service agent email address from the project name. When configuring cross-project CMEK, verify the key-owning project, the resource-containing project, the service agent identity, and the policy on the CryptoKey.

## 5. Secret Manager Has Its Own Permission Layer

Secret Manager is used to store and manage secret values such as passwords, tokens, or API keys. Cloud KMS is used to manage cryptographic keys and execute cryptographic operations. The two services can work together, but secret access remains a distinct permission layer.

For example:

- The secret administration team manages secret lifecycles and secret versions.
- The application's service account receives **roles/secretmanager.secretAccessor** on the specific secret it needs to read.
- If the secret is configured with CMEK, the Secret Manager service agent needs permission to use the corresponding CryptoKey.
- The application receives direct Cloud KMS permissions only when the application itself calls the Cloud KMS API.

Do not grant **roles/secretmanager.admin** to an application just to read secret values. Similarly, do not grant broad Cloud KMS permissions to an application just because the secret is encrypted with CMEK. Granting the exact permissions to the identity executing each operation limits the impact when a credential is exposed.

## 6. Permission Separation Flows in a System

The diagram below illustrates two ways keys are used. The left flow shows an application calling Cloud KMS directly; the right flow shows a Google Cloud service using CMEK through a service agent.

~~~mermaid
flowchart LR
  subgraph Security["Security project"]
    Admin["Key administration team"]
    KMS["Cloud KMS CryptoKey"]
    Admin -->|"Manage lifecycle and policy"| KMS
  end

  subgraph Workload["Workload project"]
    App["Application service account"]
    Data["Bucket / database"]
    App -->|"Data permissions"| Data
  end

  App -->|"Encrypt / decrypt when calling API directly"| KMS
  Agent["Service's service agent"] -->|"Use key for CMEK"| KMS
  Agent -->|"Operate on data per service configuration"| Data
~~~

Both flows may coexist in an architecture, but you must clearly determine which identity actually calls Cloud KMS. Avoid granting duplicate permissions to both the application and the service agent when only one identity needs to execute cryptographic operations.

## 7. Implementation and Verification Process

You can apply the following sequence for a new workload:

1. **Identify the encryption flow.** Choose between direct application calls to Cloud KMS, envelope encryption, or service-managed CMEK. Clearly identify the principal executing encrypt/decrypt operations.
2. **Choose resource boundaries.** Place keys in the appropriate project and location. Organize key rings by environment or administrative domain; avoid grouping keys with different owners and sensitivity levels under an overly broad IAM scope.
3. **Assign administration.** Grant key lifecycle management permissions to the responsible team. Separate who can modify IAM policies from the workload using the key when controls require strong separation.
4. **Grant minimum usage permissions.** Bind the encrypt/decrypt role or a narrower role to the service account or service agent on the exact CryptoKey.
5. **Grant data permissions independently.** Grant Storage, BigQuery, Cloud SQL, or Secret Manager permissions according to business operations. Independently test both data access permissions and key usage permissions.
6. **Test with real identities.** Verify the workload can perform required operations; at the same time, verify the workload cannot create keys, modify policies, disable key versions, or access out-of-scope data.
7. **Monitor and review.** Enable appropriate Cloud Audit Logs configurations for Admin Activity and Data Access, monitor IAM policy changes alongside cryptographic operations, and periodically remove bindings that are no longer needed.

When rotating keys, understand the impact of key versions. Setting a rotation schedule creates a new key version as the primary version for subsequent encryption operations; Cloud KMS itself does not automatically re-encrypt all older data. The system still needs valid older versions to decrypt data previously encrypted with them, unless the data has been migrated per the service's procedures. Do not disable or schedule destruction of a key version before verifying that data, backups, and workloads no longer depend on that version.

## 8. Common Authorization Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Granting **roles/cloudkms.admin** to an application service account | Application has a wider administrative scope than business needs require | Grant only the key usage role on the required CryptoKey |
| Granting key usage permissions at the project level | Workload can use many keys outside its required scope | Narrow the binding down to the CryptoKey |
| Granting object read permissions while forgetting CMEK permissions for the service agent | Service cannot read or write data encrypted with a customer-managed key | Verify the service agent identity and the CryptoKey's policy |
| Granting direct Cloud KMS permissions to an application when the service already uses a service agent | Increases the number of principals able to use the key | Identify the principal performing cryptographic operations and remove redundant bindings |
| Letting the key administration team modify policies without controls | A principal could grant itself key usage permissions | Separate **setIamPolicy** permission, require approvals, and review audit logs |
| Disabling or destroying a key version while data still depends on it | Applications or services may lose the ability to decrypt data | Check dependencies, backups, and recovery plans before changing version state |

## 9. Design Verification Criteria

Before putting a workload into operation, check the following questions:

- Does each CryptoKey have a clear administrative owner and intended purpose?
- Is the granted service account or service agent the exact identity performing cryptographic operations?
- Is the key usage role bound at the required CryptoKey scope?
- Have data read/write permissions and key usage permissions been granted and tested independently?
- Can administrative identities modify policies to grant permissions to themselves? If so, are approval and monitoring mechanisms sufficiently strict?
- Can administration, policy change, and key usage operations be traced through audit logs?
- Do rotation, disabling, and key version destruction plans account for older data and backups?

A sound design allows the security team to control key lifecycles, limits applications to only the cryptographic capabilities they need, and ensures users access data strictly according to business permissions. When the three permission layers are granted separately and tested independently, a compromised credential has a smaller blast radius, and investigating or revoking access is also much clearer.
