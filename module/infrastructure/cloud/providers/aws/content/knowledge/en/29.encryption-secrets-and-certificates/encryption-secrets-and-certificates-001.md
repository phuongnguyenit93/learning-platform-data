# Encryption at Rest, in Transit, and Envelope Encryption

Data in AWS systems needs protection across multiple states: while residing on disk, while moving across the network, and while being processed by an application. Encryption reduces the risk of exposing content when storage media, snapshots, backups, network traffic, or artifacts are accessed without authorization. However, the effectiveness of encryption depends on key management, decryption permissions, TLS configuration, and operational procedures.

AWS provides built-in encryption layers across services such as Amazon S3, EBS, RDS, and EFS; AWS Key Management Service (AWS KMS) manages key material and key usage permissions. For applications that need to encrypt data themselves before sending or storing it, **envelope encryption** uses a data key to encrypt the payload, and then uses a higher-level managed key to protect the data key. This approach handles large data volumes without sending all plaintext through KMS.

This lesson belongs to the **Encryption, Secrets, and Certificates** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects KMS, S3, EBS, RDS, EFS, TLS, AWS Certificate Manager, and Java/Spring Boot applications to help you choose appropriate protection layers, manage key lifecycles, and operate securely.

> **Principle:** Encryption protects confidentiality and integrity within the exact scope provided by the algorithm; authorization still determines who can read or decrypt. Without the proper key and `kms:Decrypt` permission, ciphertext does not turn into plaintext on its own. Never write plaintext data keys, secrets, or private keys into logs, source control, artifacts, or tickets.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish between encryption at rest, encryption in transit, and encryption in use.
2. Explain the roles of symmetric encryption, asymmetric encryption, hashing, and authenticated encryption.
3. Distinguish between a data key and a KMS key/wrapping key.
4. Describe envelope encryption and the `GenerateDataKey`/`Decrypt` flow.
5. Explain encryption context and why sensitive data must not be placed in the context.
6. Compare S3 SSE-S3, SSE-KMS, DSSE-KMS, SSE-C, and client-side encryption.
7. Configure default encryption for an S3 bucket and inspect object encryption.
8. Explain KMS key policies, IAM policies, grants, and cross-account key access.
9. Choose appropriate encryption approaches for EBS, RDS, EFS, and backups/snapshots.
10. Explain the TLS handshake, certificate chain, hostname validation, and HTTPS.
11. Use AWS Certificate Manager (ACM) to manage certificates for integrated services.
12. Enforce TLS for S3 and application endpoints.
13. Distinguish between automatic KMS key rotation and re-encryption/migration to a new key.
14. Design least-privilege decrypt permissions and separation of duties for key administration.
15. Troubleshoot access denied, invalid ciphertext, certificate, and TLS handshake errors.
16. Practice envelope encryption and encryption verification on an AWS sandbox.

## 2. Three States of Data Protection

| State | Where is the data? | Main risks | Controls |
|---|---|---|---|
| At rest | S3 objects, EBS volumes, RDS storage, EFS, snapshots, backups | Unauthorized storage/snapshot access, lost media, exposed copies | Server-side/client-side encryption, KMS, access control |
| In transit | Internet, VPC, service-to-service, client-to-API, replication | Eavesdropping, tampering, man-in-the-middle | TLS/HTTPS, certificate validation, private connectivity |
| In use | RAM, process memory, query results, application runtime | Memory dump, compromised process, debug/log exposure | Least privilege, isolation, memory hygiene, confidential computing when appropriate |

Encryption at rest does not automatically protect data after an application decrypts it in RAM. TLS protects the transport channel; it does not prevent an already compromised endpoint from reading plaintext. Encryption does not replace IAM, network segmentation, patching, monitoring, backup, or incident response.

### 2.1. Encryption at Rest

Storage services encrypt data before writing it to storage media and decrypt it when an authorized principal reads it. With managed services, AWS handles most cryptographic operations inside the service; applications still need to choose the appropriate key type, policy, and encryption settings.

Examples:

- S3 encrypts objects with SSE-S3 by default; SSE-KMS or DSSE-KMS can be selected.
- EBS encrypts volumes and snapshots using a KMS key.
- RDS encrypts database storage, automated backups, snapshots, and read replicas according to service limits.
- EFS encrypts file system data at rest using a KMS key; clients can use TLS when mounting.
- Backups and data copies must preserve their corresponding encryption boundaries.

### 2.2. Encryption in Transit

TLS creates an encrypted channel between client and server. Certificates allow the client to verify that it is connecting to the right server hostname and that the certificate chain is trusted. TLS also protects record integrity within the connection session.

In AWS, use HTTPS for public APIs, TLS for database connections, TLS between load balancers and targets when needed, and private connectivity/VPC endpoints to reduce exposure. A private network does not automatically mean traffic is encrypted.

### 2.3. Encryption in Use

When an application processes data, plaintext typically exists in process memory. Protecting this layer requires different controls such as workload isolation, IAM least privilege, avoiding memory dumps containing secrets, restricting debug/heap dumps, and considering Nitro Enclaves/confidential computing for specialized use cases. This is an additional layer, not an automatic feature enabled with KMS.

## 3. Cryptographic Foundations to Know

### 3.1. Symmetric and Asymmetric Encryption

| Characteristic | Symmetric encryption | Asymmetric encryption |
|---|---|---|
| Keys | Same secret key to encrypt/decrypt | Mathematically related public key and private key |
| Performance | Fast, suited for large data | Slower, typically used for key exchange, signatures, or protecting small keys |
| Examples | AES-256-GCM | RSA, elliptic-curve cryptography |
| Applications | Encrypting objects, volumes, files, databases | TLS certificates, digital signatures, key wrapping in some models |

AWS KMS symmetric encryption keys are generally suitable for data encryption and envelope encryption. KMS asymmetric keys can be used for encrypt/decrypt or sign/verify depending on key usage; do not use an asymmetric KMS key to call `GenerateDataKey` for a symmetric data key.

### 3.2. Authenticated Encryption

Modern encryption should provide both confidentiality and authentication/integrity. AES-GCM is an authenticated encryption with associated data (AEAD) mode: in addition to ciphertext, the algorithm produces an authentication tag to detect tampering with the ciphertext/AAD.

Key considerations:

- The nonce/IV must be generated and used according to the algorithm's requirements.
- Never reuse a nonce with the same key in standard AES-GCM usage.
- The authentication tag must be verified before accepting plaintext.
- Additional authenticated data (AAD) is authenticated alongside the ciphertext but is not encrypted.

Do not design custom algorithms or encryption formats for production. Use maintained libraries such as the AWS Encryption SDK or native service encryption mechanisms, following the algorithm suites and commitment policies recommended in the documentation.

### 3.3. Hashes and Digital Signatures Do Not Replace Encryption

A one-way hash produces a digest to check whether data has changed; a hash does not allow recovering plaintext. A digital signature uses a private key to sign and a public key to verify origin/integrity; a signature does not hide the content. TLS typically combines certificates, signatures, key exchange, and symmetric session keys to authenticate peers and encrypt transmitted data.

## 4. Key Hierarchy: KMS Keys and Data Keys

An encryption system typically has multiple key tiers:

- **KMS key (wrapping key):** a key managed in AWS KMS, controlled via key policies/IAM/grants.
- **Data key (DEK):** a symmetric key used to encrypt the actual data.
- **Encrypted data key (EDK):** a copy of the data key encrypted by the KMS key; can be stored alongside the ciphertext.
- **Plaintext data key:** exists only in the memory of the process performing encryption/decryption; must be cleared from memory as soon as possible.

~~~mermaid
flowchart TD
    KMS["AWS KMS key<br/>Key policy + IAM"]
    KMS -->|"Encrypt / wrap"| EDK["Encrypted data key (EDK)"]
    KMS -->|"GenerateDataKey"| DEK["Plaintext data key (DEK)"]
    DEK -->|"AES-GCM"| CT["Encrypted application data"]
    EDK --> STORE["Store EDK + ciphertext + metadata"]
    CT --> STORE
    STORE -->|"Read"| APP["Authorized application"]
    APP -->|"Decrypt EDK through KMS"| KMS
    KMS -->|"Plaintext DEK over TLS"| APP
    APP -->|"Decrypt ciphertext"| DATA["Plaintext data in memory"]
~~~

The KMS key does not directly encrypt large files/objects in the `GenerateDataKey` workflow. The application uses the plaintext data key to encrypt data outside KMS, while KMS only protects the data key. For server-side encryption managed by S3/EBS/RDS, the service handles data keys and KMS integration on the application's behalf.

### 4.1. Why Use Envelope Encryption?

- **Performance:** large data is encrypted locally with a symmetric data key without sending every byte through KMS.
- **Reduced KMS calls:** KMS operations are only needed to generate or decrypt the data key per envelope.
- **Centralized management:** the KMS key policy controls who can wrap/unwrap data keys.
- **Portability:** the encrypted data key can be stored alongside the ciphertext for later decryption by an authorized principal.
- **Rotation:** data keys can be re-encrypted with a new KMS key without necessarily re-encrypting the entire payload, if the application format and workflow support it.

An encrypted data key alone is not enough to decrypt. You need the right KMS key, the exact encryption context (if used), decrypt permission, and the corresponding ciphertext.

## 5. Envelope Encryption with AWS KMS

### 5.1. Encryption Flow

1. The application calls `GenerateDataKey` on a symmetric KMS key, optionally passing `EncryptionContext`.
2. KMS returns a plaintext data key and an encrypted data key.
3. The application uses the plaintext data key with a vetted encryption library to encrypt plaintext into ciphertext.
4. The application stores the ciphertext, encrypted data key, nonce/IV, authentication tag, and required metadata.
5. The application clears/zeroizes the plaintext data key from memory after use.

### 5.2. Decryption Flow

1. The application reads the ciphertext, encrypted data key, and metadata.
2. The application calls KMS `Decrypt` with the encrypted data key and the exact encryption context.
3. KMS verifies authorization, key state, and context, then returns the plaintext data key.
4. The application verifies the authentication tag and decrypts the ciphertext.
5. The application clears the plaintext data key from memory.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as AWS KMS
    participant Store as Object/Database storage
    App->>KMS: GenerateDataKey(KMS key, context)
    KMS-->>App: Plaintext DEK + encrypted DEK
    App->>App: Encrypt payload with DEK (AEAD)
    App->>Store: Store ciphertext + EDK + nonce/tag/context metadata
    Store-->>App: Retrieve encrypted record
    App->>KMS: Decrypt(EDK, same context)
    KMS-->>App: Plaintext DEK
    App->>App: Verify tag and decrypt payload
    App->>App: Clear plaintext DEK from memory
~~~

### 5.3. Generating a Data Key with the AWS CLI

Example requesting KMS to generate an AES-256 data key:

~~~bash
aws kms generate-data-key \
  --key-id arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555 \
  --key-spec AES_256 \
  --encryption-context Application=orders,Environment=production \
  --region ap-southeast-1
~~~

The response contains `Plaintext` and `CiphertextBlob`. Do not run this command in a shared terminal or write the output to logs because the response contains the base64-encoded plaintext data key. In an application, read the response directly into memory, encrypt the payload, and release the plaintext key. Store `CiphertextBlob` alongside the ciphertext and non-secret metadata.

If a workflow only needs to generate an encrypted data key for storage without encrypting a payload in the same step, KMS provides the `GenerateDataKeyWithoutPlaintext` API, which returns the encrypted data key without returning the plaintext data key. When the data needs to be encrypted, the application must obtain the plaintext data key through a separately designed workflow. This API does not replace `GenerateDataKey` when the application needs the plaintext key immediately to encrypt.

### 5.4. Encryption Context

Encryption context is a set of non-secret key-value pairs used by KMS as additional authenticated data for symmetric cryptographic operations. Example:

~~~json
{
  "Application": "orders",
  "Environment": "production",
  "RecordType": "invoice"
}
~~~

When decrypting the encrypted data key, you must provide the exact same encryption context, which is case-sensitive. The context is logged in plaintext in CloudTrail and is not encrypted; do not put customer names, emails, account numbers, secrets, or sensitive data here.

Context can be used to:

- Distinguish the purpose of key usage.
- Improve auditability in CloudTrail.
- Constrain KMS grants/policies using condition keys.
- Prevent an encrypted data key from being used in the wrong context if the application verifies context consistently.

### 5.5. AWS Encryption SDK

The AWS Encryption SDK implements envelope encryption and manages message formats, data keys, algorithm suites, authentication, and key commitment. For applications that encrypt files/messages themselves, prefer using the SDK rather than building a custom encryption format. The SDK can use a KMS keyring to wrap data keys and allows storing encrypted messages in S3, databases, or other systems.

The SDK does not automatically manage IAM permissions, KMS key lifecycles, application authorization, or plaintext memory across all languages/runtimes. Applications must still control keyrings, encryption context, commitment policy, dependency versions, and decrypt permissions.


## 6. Encrypting Data in Amazon S3

Amazon S3 supports server-side encryption (SSE) and client-side encryption. Since January 5, 2023, S3 automatically applies SSE-S3 to all newly uploaded objects; every bucket has a default encryption configuration. If you require key policy control, decrypt auditing, or dual-layer encryption, choose SSE-KMS/DSSE-KMS. Default encryption does not automatically re-encrypt older objects that existed before the configuration was applied.

### 6.1. S3 Encryption Options

| Mechanism | Who manages the key? | Characteristics | Use cases |
|---|---|---|---|
| SSE-S3 | Amazon S3 | AES-256, S3 manages keys and rotation; default for new objects | Most workloads needing baseline at-rest encryption |
| SSE-KMS | AWS KMS key | Key policy/IAM control, KMS usage auditing, customer-managed key | Sensitive data, separation of duties, cross-account access |
| DSSE-KMS | Two encryption layers managed by S3 and KMS | Dual-layer server-side encryption; extra protection layer for compliance | Dual-layer encryption requirements |
| SSE-C | Customer-provided key in each request | S3 does not store the key; caller must supply the exact key on every related request | Specialized key custody use cases; higher operational burden |
| Client-side encryption | Application/customer | Encrypted before sending to S3; S3 only receives ciphertext | Plaintext must not appear at the service, or full control over crypto format is needed |

SSE-S3, SSE-KMS, and DSSE-KMS all encrypt object data on the server side before writing to disk; do not assume object keys, user metadata, or information outside the object body are ciphertext by default. Do not put PII/secrets in object keys or metadata unless separate protection controls apply. SSE-C requires the client to send the key over HTTPS; S3 does not store the key, so losing the key means losing the ability to decrypt. Client-side encryption protects data before upload, but the application must manage keys, metadata, the decrypt path, and format compatibility.

### 6.2. Configuring Default Encryption with SSE-S3

Example setting a bucket's default encryption to SSE-S3:

~~~json
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }
  ]
}
~~~

Apply it:

~~~bash
aws s3api put-bucket-encryption \
  --bucket company-private-data \
  --server-side-encryption-configuration file://s3-encryption.json
~~~

S3 currently defaults to SSE-S3 for all new buckets/objects; this command illustrates how to declare the configuration explicitly in IaC or runbooks. Bucket configuration does not automatically re-encrypt existing objects. To change encryption on existing objects, you must perform a planned copy/rewrite or batch operation.

### 6.3. Configuring SSE-KMS and S3 Bucket Key

Example default encryption using a customer-managed KMS key:

~~~json
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555"
      },
      "BucketKeyEnabled": true
    }
  ]
}
~~~

Apply it:

~~~bash
aws s3api put-bucket-encryption \
  --bucket company-private-data \
  --server-side-encryption-configuration file://s3-kms-encryption.json
~~~

S3 Bucket Keys can reduce KMS request volume and SSE-KMS costs by using a bucket-level key to reduce the frequency of KMS calls per object. It does not change the object's encryption boundary and does not replace KMS authorization. When Bucket Keys are enabled, the encryption context that S3 sends to KMS may be scoped to the bucket ARN rather than the object ARN; evaluate the impact on policy conditions, audit context, and traceability before enabling it.

### 6.4. Required Permissions for SSE-KMS

To upload objects using SSE-KMS, a principal typically needs:

- S3 permissions such as `s3:PutObject` on the bucket/object.
- KMS `kms:GenerateDataKey` permission on the appropriate key.
- A KMS key policy or grant allowing the principal to use the key.

To download and decrypt objects, a principal typically needs:

- S3 `s3:GetObject` permission.
- KMS `kms:Decrypt` permission.
- A key policy/grant allowing the principal to decrypt.

Multipart uploads and some other operations may require additional KMS permissions such as `kms:Decrypt`. Verify API/service-specific permissions; do not copy a sample policy into production without verifying it. If the key is in another account, both an identity policy in the caller account and a key policy in the key-owning account are required; use the key ARN for cross-account references.

### 6.5. DSSE-KMS and SSE-C

DSSE-KMS provides two layers of server-side encryption, one managed by S3 and one using AWS KMS. Choose it when compliance/security requirements mandate dual-layer encryption; evaluate cost, service compatibility, and feature limitations before adopting it.

SSE-C requires the client to send a customer-provided key over TLS on every request that needs the key. S3 does not store the key and cannot recover it if lost. Never pass the key on a command line, in shell history, in logs, or in monitoring labels. For most modern systems, SSE-KMS or client-side encryption is much easier to operate than SSE-C.

### 6.6. Checking Object Encryption

Check default bucket encryption:

~~~bash
aws s3api get-bucket-encryption \
  --bucket company-private-data
~~~

Check object metadata:

~~~bash
aws s3api head-object \
  --bucket company-private-data \
  --key reports/annual-report.pdf
~~~

Inspect fields such as `ServerSideEncryption`, `SSEKMSKeyId`, and `BucketKeyEnabled` if returned in the response. S3 Inventory can also export encryption status for bulk auditing. Never assume older objects have been re-encrypted based solely on the default encryption config.

### 6.7. Enforcing Encryption Policies

A bucket policy can deny uploads if a request does not use SSE-KMS or uses the wrong KMS key ARN. The example below is an illustrative policy requiring every `PutObject` to use one specific KMS key:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUploadsWithoutApprovedKmsKey",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-private-data/*",
      "Condition": {
        "StringNotEqualsIfExists": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    },
    {
      "Sid": "DenyUploadsWithUnapprovedKmsKey",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-private-data/*",
      "Condition": {
        "StringNotEqualsIfExists": {
          "s3:x-amz-server-side-encryption-aws-kms-key-id": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555"
        }
      }
    }
  ]
}
~~~

Both statements use `StringNotEqualsIfExists` to deny if the client omits the header or sends a different value. Therefore, this policy intentionally requires clients to explicitly specify SSE-KMS and the exact key ARN; requests without the header will be denied even if the bucket has default encryption. If you want to rely on default encryption for requests that omit the header, design a different policy and verify object encryption after upload. Test uploads, multipart uploads, replication, and service integrations in a sandbox before enforcing.

## 7. Encrypting EBS, RDS, EFS, and Backups

### 7.1. Amazon EBS

EBS encryption uses AWS KMS to encrypt data at rest for volumes and snapshots. When creating an encrypted volume, data written to the volume, snapshots created from the volume, and data in transit between the instance and the volume are encrypted through the service's mechanism.

- You can enable EBS encryption by default per Region.
- You can select a default KMS key for new volumes.
- Snapshots of an encrypted volume remain encrypted.
- Copying a snapshot allows selecting a different KMS key to change the encryption key.
- You cannot directly convert an existing unencrypted volume to encrypted by toggling a flag; you typically need to create a snapshot/copy or create a new encrypted volume and migrate the data.
- When attaching a volume, the principal needs appropriate KMS permissions; EC2/EBS have related service integrations and grants.

Check account/Region configuration:

~~~bash
aws ec2 get-ebs-encryption-by-default \
  --region ap-southeast-1

aws ec2 get-ebs-default-kms-key-id \
  --region ap-southeast-1
~~~

Enable encryption by default:

~~~bash
aws ec2 enable-ebs-encryption-by-default \
  --region ap-southeast-1
~~~

Enabling the default applies only to new volumes created after the setting takes effect; it does not automatically encrypt existing volumes.

### 7.2. Amazon RDS

RDS encryption at rest uses a KMS key for underlying storage, automated backups, snapshots, and read replicas according to engine/feature support. Important rules:

- Select the KMS key when creating the DB instance/cluster; you cannot enable encryption in place for an unencrypted DB instance.
- To encrypt an unencrypted database, create a snapshot, copy the snapshot with a KMS key, and restore it as a new encrypted DB instance.
- When copying a snapshot to another Region, you need a key in the destination Region and permission to use the corresponding keys.
- Automated backups and snapshots inherit the database's encryption according to service behavior.
- TLS must be configured separately for database client connections; at-rest encryption does not encrypt SQL traffic.

### 7.3. Amazon EFS

EFS encrypts file system data at rest using a KMS key when creating the file system. You can use an AWS managed key or a customer managed key depending on control requirements. For encryption in transit, use the EFS mount helper with TLS when mounting the file system. Do not confuse EFS encryption at rest with the TLS mount option.

### 7.4. AWS Backup and Copies

Backup encryption depends on the resource type and how the backup is created. Some resource backups inherit the encryption key from the source resource; an AWS Backup vault also has an encryption key for backup copies depending on service support. When copying backups cross-account/cross-Region, check:

- Source key and destination key are in the proper Region/account.
- Key policies/grants for AWS Backup/service roles.
- Destination vault policy and IAM role.
- Restore permissions and decrypt permissions.
- Key retention/deletion procedures do not render backups unrestorable.

Perform restore tests periodically. A well-encrypted backup that cannot be decrypted or restored because the key was disabled or deleted is still a failed backup.

## 8. AWS KMS: Key Types, Policies, and Usage Permissions

### 8.1. AWS Owned, AWS Managed, and Customer Managed Keys

| Key type | Who manages it? | Policy/rotation | When to use? |
|---|---|---|---|
| AWS owned key | Owned by an AWS service | Not viewable/manageable directly in the account; service-controlled | Default internal service encryption |
| AWS managed key | Created/managed by an AWS service in your account | Key policy managed by AWS; automatic annual rotation | Quick KMS integration with limited management permissions |
| Customer managed key | Created/managed by the customer | Self-managed key policy, grants, aliases, rotation, disable/delete | Need auditing, separation of duties, cross-account, or custom access control |

Customer managed keys allow clear separation between who can administer the key and who can perform cryptographic operations. Key management permissions (`kms:EnableKey`, `kms:PutKeyPolicy`, `kms:ScheduleKeyDeletion`) should be separated from key usage permissions (`kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey`).

### 8.2. Key Policies and IAM Policies

The KMS key policy is the primary resource policy determining who can use and manage a KMS key. An IAM policy can grant KMS permissions only when the key policy allows IAM policies in the account to participate in authorization, or via grants. You cannot assume that attaching an IAM `kms:Decrypt` policy is enough for every KMS key.

Components:

- **Key policy:** root permissions on the KMS key.
- **IAM identity policy:** permissions for a user/role if the key policy enables IAM authorization.
- **Grant:** delegates cryptographic operation permissions to a principal/service within a defined scope.
- **Permissions boundary/SCP:** sets the maximum permissions ceiling; does not grant permissions.
- **Encryption context conditions:** constrains operations based on context where supported by the use case.

Example key policy statement allowing an application role to use a key via S3 in a specific Region:

~~~json
{
  "Sid": "AllowOrdersRoleThroughS3",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::123456789012:role/OrdersApplicationRole"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "s3.ap-southeast-1.amazonaws.com"
    }
  }
}
~~~

This is an illustrative statement for a key policy; you must also include a key administration statement and appropriate resource/encryption context conditions for the bucket/object. `kms:ViaService` restricts operations to calls made through S3 in the specified Region. When using S3 Bucket Keys or cross-account access, verify the actual encryption context and principal behavior before adding conditions.

### 8.3. Least Privilege for Decrypt

Do not grant `kms:*` to all application roles. Separate by behavior:

- Upload/encrypt role: `kms:GenerateDataKey` or `kms:Encrypt` as needed.
- Download/decrypt role: `kms:Decrypt`.
- Key administrator: manages policies, rotation, disabling, and deletion schedules; does not necessarily need to decrypt data.
- Audit role: reads metadata/CloudTrail; does not necessarily need decrypt permissions.
- Backup/restore role: KMS and service actions matching the restore workflow.

With resource policies and cross-account use, a principal in another account typically needs both an identity policy in their own account and a key policy in the key-owning account allowing access. Avoid `Principal: "*"` or overly broad wildcard resources/conditions.


## 9. Encryption in Transit with TLS and Certificates

TLS (Transport Layer Security) protects data transmitted between two endpoints. HTTPS is HTTP running over TLS. TLS provides confidentiality, integrity, and certificate-based server authentication; mutual TLS (mTLS) can authenticate both client and server when an application requires transport-layer identity.

### 9.1. Conceptual TLS Handshake

1. The client sends `ClientHello` with supported TLS versions, cipher suites, and handshake parameters.
2. The server returns `ServerHello` and the certificate chain.
3. The client verifies the certificate chain, hostname, validity period, and trust anchor.
4. Both parties complete key exchange to establish session keys.
5. Application data is transmitted using symmetric authenticated encryption.

TLS 1.2 and TLS 1.3 are both widely used. Prefer TLS 1.2 or higher, disable weak protocols/ciphers based on compatibility requirements, and keep TLS libraries updated. Never bypass hostname validation or accept self-signed certificates outside an approved trust model.

### 9.2. AWS Certificate Manager

AWS Certificate Manager (ACM) issues and manages TLS certificates for integrated AWS services such as Application Load Balancer, CloudFront, API Gateway, and other supported endpoints. ACM supports public certificates and private certificates via ACM Private CA.

- Public certificates are used for public hostnames; they require domain ownership validation via DNS or email using a supported method.
- ACM automatically renews eligible public certificates when they are still in use by an integrated service and validation conditions remain satisfied.
- Imported certificates are not automatically renewed by ACM; the owner must track expiry and import a new certificate.
- Private CA is suitable for internal PKI, private services, and mTLS; it requires managing the CA hierarchy, issuance policy, revocation, and costs.
- ACM certificates are Region-scoped for most regional services; CloudFront certificates must be created or imported in the Region CloudFront requires (`us-east-1`).

Do not treat a certificate like a secret API key. Public certificates are public; private keys must be protected. Never commit private keys or keystore passwords to source control.

### 9.3. TLS for AWS Services

| Connection | Control |
|---|---|
| Browser → CloudFront/ALB/API Gateway | HTTPS listener/custom domain with an ACM certificate |
| Service → S3 | HTTPS/TLS, bucket policy denying HTTP |
| Application → RDS/Aurora | TLS database connection, verifying server certificate/hostname per driver |
| EC2/ECS/EKS → internal service | HTTPS/TLS or mTLS per trust model |
| Client → EFS | EFS mount helper with TLS |
| Service → AWS API | AWS SDK/CLI HTTPS endpoint; keep certificate validation enabled |

VPCs, private subnets, security groups, and VPC endpoints control network reachability. They do not replace TLS when transport confidentiality/integrity is required.

### 9.4. Enforcing HTTPS on S3

A bucket policy can deny all requests not using HTTPS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-private-data",
        "arn:aws:s3:::company-private-data/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

You can restrict the minimum TLS version using the `s3:TlsVersion` condition key. The following example denies TLS lower than 1.2:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOldTls",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-private-data",
        "arn:aws:s3:::company-private-data/*"
      ],
      "Condition": {
        "NumericLessThan": {
          "s3:TlsVersion": "1.2"
        }
      }
    }
  ]
}
~~~

Test policies with clients, replication, logging, AWS service integrations, and VPC endpoints before applying to production. TLS enforcement can cause older clients or non-compliant integrations to be denied.

### 9.5. TLS for RDS

RDS/Aurora provides certificate authority bundles so clients can verify the server certificate. Configure the driver/JDBC connection string to require TLS and verify server identity; for PostgreSQL/MySQL, exact parameters depend on the engine and driver. Do not just enable TLS on the server while skipping certificate validation on the client.

For Java, use an updated JDBC driver, a trust store containing the appropriate CA bundle, and SSL mode/`verify-full` settings corresponding to the engine. When AWS rotates RDS server certificates, update the CA bundle and test connectivity prior to the cutover date.

## 10. KMS Key Rotation and Key Lifecycle

Rotation reduces the time a given version of cryptographic key material is in use, but it does not replace key access reviews, incident response, or data re-encryption. Distinguish between rotating key material inside the same logical KMS key and migrating to a new KMS key.

### 10.1. Automatic Rotation

AWS KMS supports automatic rotation for customer managed symmetric encryption keys whose key material is generated by AWS KMS (`Origin = AWS_KMS`). When rotation is enabled:

- By default, KMS generates new key material every 365 days.
- You can choose a rotation period from 90 to 2,560 days.
- The key ID, ARN, policy, alias, and permissions of the logical KMS key do not change.
- When decrypting older ciphertext, KMS automatically selects the appropriate older key material.
- AWS managed keys are rotated automatically by AWS every year; customer managed keys require enabling rotation if desired.
- AWS owned keys are owned by the service, which decides their rotation schedule.

Automatic rotation does not support asymmetric keys, HMAC keys, imported key material, or custom key stores; these cases require appropriate manual rotation workflows.

AWS KMS also supports on-demand rotation for symmetric encryption keys with AWS KMS-generated or imported key material. On-demand rotation does not change the configured automatic rotation schedule. Asymmetric/HMAC keys and custom key stores require manual rotation or migration workflows depending on the key type.

Enable rotation:

~~~bash
aws kms enable-key-rotation \
  --key-id alias/app-data-key \
  --rotation-period-in-days 365 \
  --region ap-southeast-1
~~~

Check status:

~~~bash
aws kms get-key-rotation-status \
  --key-id alias/app-data-key \
  --region ap-southeast-1
~~~

### 10.2. Rotation vs. Migration to a New Key

| Scenario | Logical key ARN | Existing data | Action |
|---|---|---|---|
| KMS automatic rotation | Unchanged | KMS retains old key material to decrypt | No need to modify ciphertext solely due to rotation |
| On-demand rotation | Unchanged | Still decrypted with appropriate material | Monitor CloudTrail/rotation status |
| Migration to a new KMS key | Changes | Ciphertext still requires the old key until re-encrypted | `ReEncrypt` data keys or copy/rewrite resources |
| Key exposure/compromise | May require replacing key/policy and re-encrypting | Assess data exposure and key access | Incident response, containment, migration |

When migrating to a new KMS key, do not delete the old key until confirming that all ciphertext, snapshots, backups, replicas, and archives have been re-encrypted or are no longer needed. `ReEncrypt` can re-encrypt ciphertext/key material from a source KMS key to a destination key without returning plaintext to the caller; with envelope encryption, you may only need to re-wrap the encrypted data key if the application format supports it.

### 10.3. Disabling, Scheduling Deletion, and Recovery

- `DisableKey` prevents new cryptographic operations from using the key but does not delete key material.
- `ScheduleKeyDeletion` sets a pending deletion waiting period; during the waiting period, deletion can be canceled.
- Once a key is permanently deleted, data whose only remaining form is ciphertext protected by that key may become unrecoverable.
- An alias is only a reference name; changing an alias does not automatically re-encrypt data.
- Rotation does not resolve a key compromise if an attacker has already obtained plaintext data keys or plaintext data.

Never schedule deletion for a key in use by resources, backups, log archives, or applications without an inventory and restore test.

## 11. Choosing an Encryption Model Based on Requirements

| Need | Typically suitable option | Points to verify |
|---|---|---|
| S3 objects needing default encryption, low ops overhead | SSE-S3 | Bucket/object encryption status |
| S3 sensitive data needing key usage auditing | SSE-KMS with customer managed key | Key policy, KMS cost, decrypt role |
| S3 needing dual-layer encryption | DSSE-KMS | Service compatibility, cost, compliance |
| Application encrypting before storage | AWS Encryption SDK + KMS keyring | Data key lifecycle, message format, context |
| EBS volumes/snapshots | EBS encryption with KMS | Default encryption, snapshot copy, restore |
| RDS database | RDS encryption at creation + TLS client | Snapshot migration, CA bundle, DB engine |
| EFS file system | KMS at rest + TLS mount | Key access and mount helper |
| Public API endpoint | ACM certificate + HTTPS/TLS | DNS validation, renewal, TLS policy |
| Internal service mTLS | Private CA + client/server certificates | Trust distribution, rotation, revocation |
| Data requiring long-term archiving | SSE-KMS/S3 + retention/restore plan | Do not delete keys before archive lifecycle ends |

Do not choose an encryption mechanism solely by the label "AES-256". Determine the threat model, who holds the keys, who can decrypt, where ciphertext resides, whether keys can be rotated/disabled, and how long data must remain recoverable.


## 12. Troubleshooting Encryption and KMS

| Symptom | Possible cause | Where to check |
|---|---|---|
| S3 `AccessDenied` on SSE-KMS upload | Missing `s3:PutObject`, `kms:GenerateDataKey`, or key policy disallows | IAM policy, KMS key policy/grant, bucket policy |
| S3 `AccessDenied` on download | Missing `s3:GetObject` or `kms:Decrypt` | Object key ARN, key state, key policy, and cross-account permissions |
| `KMSInvalidStateException` | Key disabled, pending deletion, or state does not support operation | `DescribeKey`, key state, deletion schedule |
| `InvalidCiphertextException` | Corrupt/invalid EDK, wrong KMS key, or mismatched encryption context | Ciphertext blob, key ARN, exact/case-sensitive context |
| Application fails to decrypt after key rotation | Confused material rotation with key migration, or old key deleted | Key ID/ARN, key material retention, ciphertext metadata |
| Older S3 objects still use old encryption | Default encryption applies only to new objects | `HeadObject`, S3 Inventory, copy/rewrite plan |
| EBS volume fails to attach | Principal/service lacks KMS grant/permission or key is disabled | KMS key state, grants, CloudTrail, EC2 events |
| RDS snapshot copy fails | Missing decrypt/encrypt permissions or key in wrong Region | Source/destination key policy, snapshot Region, IAM role |
| TLS handshake failure | Incompatible TLS version/cipher, broken trust chain, or wrong hostname | Client/server TLS logs, CA bundle, certificate SAN/expiry |
| ACM certificate fails to renew | Domain validation record missing or certificate no longer used properly | ACM renewal status, DNS validation, integrated service |
| Client connecting to S3 is denied | HTTP denied by bucket policy or TLS below minimum | `aws:SecureTransport`, `s3:TlsVersion`, client TLS version |

### 12.1. Checking KMS Key Metadata

~~~bash
aws kms describe-key \
  --key-id alias/app-data-key \
  --region ap-southeast-1

aws kms get-key-policy \
  --key-id alias/app-data-key \
  --policy-name default \
  --region ap-southeast-1

aws kms list-grants \
  --key-id alias/app-data-key \
  --region ap-southeast-1
~~~

Verify the key ARN, key state, key usage, origin, multi-Region property, and key policy. For service integrations, check grants created for the service principal/resource.

### 12.2. Checking Rotation

~~~bash
aws kms get-key-rotation-status \
  --key-id alias/app-data-key \
  --region ap-southeast-1

aws kms list-key-rotations \
  --key-id alias/app-data-key \
  --region ap-southeast-1
~~~

`GetKeyRotationStatus` shows the automatic rotation status; `ListKeyRotations` shows completed rotation history if the key supports this API. Never conclude a key has rotated just because a policy requires rotation; verify the actual status.

### 12.3. Investigating with CloudTrail

CloudTrail logs KMS API calls such as `GenerateDataKey`, `Decrypt`, `Encrypt`, `ReEncrypt`, `DisableKey`, `PutKeyPolicy`, and rotation operations. When investigating:

1. Identify `eventTime`, `eventSource = kms.amazonaws.com`, and `eventName`.
2. Read `userIdentity` to identify the role/user/service.
3. Inspect the key ID/ARN and encryption context if present.
4. Check `errorCode`/`errorMessage` to distinguish authorization, invalid state, and ciphertext/context errors.
5. Correlate with S3/EBS/RDS/Secrets Manager events and application logs.
6. Never log plaintext keys or secrets while debugging.

## 13. Common Design Mistakes

### 13.1. Assuming Default Encryption Solves All Risks

S3 SSE-S3 protects objects at rest but does not stop a principal with `s3:GetObject` from downloading plaintext. KMS encryption does not replace authorization either. You still need bucket policies, IAM least privilege, access point policies, logging, and data classification.

### 13.2. Keeping Plaintext Data Keys Too Long

Plaintext data keys only need to exist during encryption/decryption. Do not cache them indefinitely, write them to logs, or pass them through queues/outputs. If an application must cache keys, set a TTL, restrict scope, protect memory, and assess the risk.

### 13.3. Putting Sensitive Data in Encryption Context

Encryption context appears in plaintext in CloudTrail. Only use non-secret identifiers such as Application, Environment, RecordType, or an evaluated opaque resource ID; never include PII or credentials.

### 13.4. Using One KMS Key for All Workloads

A single shared key can create a large blast radius and hinder separation of duties. Separate keys by data classification, account, environment, or workload when needed; avoid creating too many keys without clear owners or lifecycles.

### 13.5. Deleting a Key Before Checking Backups

Permanently deleting a KMS key can make snapshots, objects, and backups unrecoverable. Before disabling or scheduling deletion, inventory all resources using the key, test restores, and verify retention periods.

### 13.6. Treating a Private Subnet as Encryption in Transit

Traffic inside a private VPC can still be observed or tampered with by a compromised endpoint or workload. Use TLS/mTLS according to your threat model and verify certificates on the client.

### 13.7. Building Custom Cryptographic Formats

Manually choosing nonces, key derivation, serialization, authentication tags, or rotation formats easily introduces subtle bugs. Use the AWS Encryption SDK or native service encryption; if custom implementation is unavoidable, require specialized cryptographic design review and interoperability testing.

## 14. Hands-on Practice in an AWS Sandbox

### 14.1. Lab A — S3 SSE-S3 and SSE-KMS

1. Create a dedicated sandbox bucket.
2. Check current default encryption using `get-bucket-encryption`.
3. Upload a test object and inspect it with `head-object`.
4. Create a customer managed symmetric KMS key in the same Region.
5. Configure bucket default encryption to SSE-KMS and enable Bucket Keys.
6. Upload another object; check `ServerSideEncryption`, `SSEKMSKeyId`, and `BucketKeyEnabled`.
7. Use a role lacking `kms:Decrypt` to try downloading the object; observe `AccessDenied`.
8. Grant proper permissions in the sandbox and verify the download succeeds.

### 14.2. Lab B — Envelope Encryption with KMS

1. Create a symmetric customer managed KMS key and alias.
2. Create a test application using the AWS SDK or AWS Encryption SDK.
3. Call `GenerateDataKey` with `AES_256` and a non-sensitive encryption context.
4. Use the SDK to encrypt test plaintext and store the ciphertext along with the encrypted data key.
5. Clear the plaintext data key from memory after encryption.
6. Read the record, call `Decrypt` with the exact context, and decrypt the payload.
7. Try modifying one field in the context; confirm decryption fails.
8. Try a role without `kms:Decrypt`; confirm authorization is denied.

### 14.3. Lab C — TLS Enforcement for S3

1. Create a sandbox bucket and upload a test object.
2. Add a bucket policy denying requests when `aws:SecureTransport = false`.
3. Access the object using an HTTPS client and verify success.
4. Try HTTP if the endpoint/client permits; confirm it is denied.
5. Check the CloudTrail event `tlsDetails` if available.
6. Test a minimum TLS version policy in the sandbox after verifying client compatibility.

### 14.4. Lab D — EBS Encryption by Default

1. Choose a sandbox Region and check EBS encryption by default.
2. Enable default encryption and specify a KMS key if required by the lab.
3. Create a test EBS volume.
4. Check `Encrypted` and `KmsKeyId` using `describe-volumes`.
5. Create a snapshot and verify its encryption.
6. Copy the snapshot to another key if needed to demonstrate key migration.
7. Do not disable/delete keys protecting resources you need to keep.

### 14.5. Lab E — KMS Rotation

1. Create a customer managed symmetric KMS key with origin `AWS_KMS`.
2. Enable automatic rotation with the default period or a sandbox-appropriate period.
3. Use `get-key-rotation-status` to confirm the status.
4. Note that the key ARN does not change when key material rotates.
5. Decrypt ciphertext created before rotation to verify KMS still uses the appropriate material.
6. Compare with migrating to a new KMS key: re-encrypt/re-wrap the data key and verify the ciphertext.
7. Do not schedule key deletion until restore testing is complete.

### 14.6. Lab F — ACM and TLS Endpoints

1. Have a test domain and permission to create DNS validation records.
2. Request a public certificate with ACM in the appropriate Region for the service.
3. Validate domain ownership.
4. Attach the certificate to an ALB listener or API Gateway custom domain.
5. Verify HTTPS, hostname, and certificate chain using a browser/`openssl s_client`.
6. Check the TLS version and expiry; inspect ACM renewal status.
7. Never use production private keys/certificates for labs.

## 15. Pre-Production Encryption Review Checklist

### Data Classification and Architecture

- [ ] Is data classified and are confidentiality/integrity requirements defined?
- [ ] Have data at rest, in transit, and in use been identified?
- [ ] Is the choice between server-side and client-side encryption justified?
- [ ] Is it clear who needs to decrypt and in which account/Region?
- [ ] Are snapshots, replicas, backups, exports, and archives accounted for?

### Key Management

- [ ] Do the key type, origin, and Region match the use case?
- [ ] Have the key policy, IAM policies, and grants been reviewed?
- [ ] Are encrypt/decrypt/admin roles separated according to least privilege?
- [ ] Does encryption context contain only non-secret metadata?
- [ ] Does the rotation policy fit the key type?
- [ ] Is an inventory taken before disabling/scheduling deletion?
- [ ] Have cross-account/cross-Region permissions been verified?

### At Rest

- [ ] Is S3 default encryption properly set to SSE-S3/SSE-KMS/DSSE-KMS?
- [ ] Have older objects been inventoried and re-encrypted if required?
- [ ] Does the SSE-KMS key policy allow the proper services/principals?
- [ ] Is EBS/RDS/EFS encryption enabled at resource creation?
- [ ] Do snapshot/backup copies maintain proper encryption?
- [ ] Are restore tests and a key recovery plan in place?

### In Transit

- [ ] Is HTTPS/TLS enforced on required public/internal endpoints?
- [ ] Are the TLS minimum version/cipher policies appropriate?
- [ ] Are certificate hostnames, chains, and expiries verified?
- [ ] Are ACM renewal status and DNS validation monitored?
- [ ] Do database clients verify certificates rather than only enabling TLS?
- [ ] Is plain HTTP avoided and is certificate validation never bypassed?

### Operations

- [ ] Are plaintext data keys/secrets/private keys kept out of logs/artifacts?
- [ ] Does CloudTrail monitor KMS/key policy/rotation operations?
- [ ] Are there alerts for key disabling, deletion schedules, and policy changes?
- [ ] Are runbooks available for `AccessDenied`, invalid ciphertext, and TLS errors?
- [ ] Is there a review schedule for key owners, grants, rotation, and restore readiness?

## 16. Self-Assessment Questions

1. How do encryption at rest, in transit, and in use differ?
2. Does encryption replace IAM authorization?
3. How do symmetric and asymmetric encryption differ?
4. What properties does AES-GCM provide?
5. How do hashes and digital signatures differ from encryption?
6. How does a KMS key differ from a data key?
7. What problem does envelope encryption solve?
8. What values does `GenerateDataKey` return?
9. Why must an application clear the plaintext data key from memory?
10. Why is the encrypted data key stored alongside the ciphertext?
11. What is encryption context and is it secret?
12. Why must encryption context match exactly during decryption?
13. Why should PII/secrets not be placed in encryption context?
14. How does the AWS Encryption SDK support envelope encryption?
15. How do SSE-S3, SSE-KMS, and DSSE-KMS differ?
16. Since when has S3 applied SSE-S3 by default to new objects?
17. Does default bucket encryption automatically encrypt older objects?
18. What operational risk does SSE-C carry if the customer key is lost?
19. Which KMS permissions are typically required for S3 SSE-KMS uploads and downloads?
20. Which cost does S3 Bucket Keys help reduce?
21. Does EBS encryption by default encrypt existing volumes?
22. Why does an unencrypted RDS database require snapshot/copy/restore to enable encryption?
23. How does EFS at-rest encryption differ from TLS mounting?
24. How do AWS owned, AWS managed, and customer managed KMS keys differ?
25. Why is the key policy a critical component in KMS authorization?
26. When are both a cross-account key policy and an IAM identity policy required?
27. Which key types does automatic KMS key rotation support?
28. What is the default KMS automatic rotation period and what is the current custom range?
29. How does automatic rotation differ from migrating to a new key?
30. Why can deleting a KMS key make backups impossible to restore?
31. What does a TLS handshake verify?
32. Which services does ACM support for certificate management?
33. Why are imported certificates not automatically renewed by ACM?
34. What do `aws:SecureTransport` and `s3:TlsVersion` enforce?
35. Why does a private subnet not automatically guarantee encryption in transit?
36. What should you check when a TLS handshake or certificate validation fails?

### Answer Guidelines

- **At rest/in transit/in use:** storage encryption, TLS transport, and memory/workload isolation protect different states.
- **Envelope:** KMS protects the data key; the data key encrypts the payload; the encrypted data key is stored with the ciphertext; the plaintext key exists only briefly in memory.
- **S3:** SSE-S3 is the default for new objects; SSE-KMS provides KMS authorization/auditing; DSSE-KMS provides dual-layer encryption; SSE-C requires the caller to safeguard the key.
- **KMS authorization:** key policy is foundational; IAM/grants supplement permissions per key policy configuration; apply least privilege and separation of duties.
- **Rotation:** automatic rotation replaces key material within the same logical key; migrating to a new key requires re-encrypting/re-wrapping and keeping the old key until data no longer depends on it.
- **TLS/ACM:** HTTPS protects the channel; clients must validate certificates/hostnames; ACM renews eligible integrated certificates, while imported certificates require owner management.

## 17. Official AWS Documentation

1. [AWS KMS key concepts](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html) — KMS keys, data keys, key material, and key hierarchy.
2. [Generate data keys](https://docs.aws.amazon.com/kms/latest/developerguide/data-keys.html) — `GenerateDataKey`, plaintext/encrypted data key, and decrypt flow.
3. [GenerateDataKey API](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html) — Request, key spec, and encryption context.
4. [Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html) — AAD, CloudTrail visibility, and policy constraints.
5. [AWS Encryption SDK concepts](https://docs.aws.amazon.com/encryption-sdk/latest/developer-guide/concepts.html) — Envelope encryption, keyrings, and algorithm suites.
6. [AWS Encryption SDK supported algorithm suites](https://docs.aws.amazon.com/encryption-sdk/latest/developer-guide/supported-algorithms.html) — AES-GCM, key derivation, signatures, and key commitment.
7. [Protecting data with encryption in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html) — SSE-S3, SSE-KMS, DSSE-KMS, SSE-C, and client-side options.
8. [Configuring default S3 bucket encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html) — Default encryption behavior and bucket configuration.
9. [S3 server-side encryption with AWS KMS](https://docs.aws.amazon.com/AmazonS3/latest/userguide/specifying-kms-encryption.html) — SSE-KMS permissions and configuration.
10. [S3 Bucket Keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html) — Reducing KMS request volume/cost for SSE-KMS.
11. [Protecting data in transit with Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryptionInTransit.html) — TLS 1.2/1.3, `aws:SecureTransport`, and `s3:TlsVersion`.
12. [Amazon EBS encryption](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-encryption.html) — Volume/snapshot encryption and KMS integration.
13. [Amazon RDS encrypted DB instances](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html) — RDS storage, snapshot, and migration encryption.
14. [Amazon EFS encryption](https://docs.aws.amazon.com/efs/latest/ug/encryption.html) — At-rest encryption and KMS key.
15. [Rotate AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html) — Automatic/on-demand/manual rotation and key material.
16. [Enable automatic KMS key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotating-keys-enable.html) — Rotation period and supported key types.
17. [KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html) — Key policy, IAM authorization, and grants.
18. [AWS Certificate Manager User Guide](https://docs.aws.amazon.com/acm/latest/userguide/acm-overview.html) — Public/private certificates, integrations, and renewal.
19. [ACM managed renewal](https://docs.aws.amazon.com/acm/latest/userguide/managed-renewal.html) — Conditions and process for automatic renewal.
20. [Amazon RDS SSL/TLS connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html) — TLS, CA certificates, and client configuration.

> **Key Takeaway:** Encryption at rest protects data on storage; TLS protects data in transit; envelope encryption uses a data key to encrypt the payload and a KMS key to protect the data key. Decryption permissions, encryption context, key rotation, certificate validation, backup restores, and key lifecycle management determine whether a system is both secure and recoverable.
