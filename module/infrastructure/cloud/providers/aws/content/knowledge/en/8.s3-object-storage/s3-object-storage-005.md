# S3 Encryption and KMS Key Permissions

## Learning Objectives

After completing this lesson, learners will be able to:

- Distinguish between **SSE-S3, SSE-KMS, DSSE-KMS, SSE-C**, and **client-side encryption**; choose a mode based on security, key control, operational, and cost requirements.
- Explain **envelope encryption** and the roles of **AWS Key Management Service (AWS KMS)**, **data keys**, **KMS keys**, and **encryption context** when Amazon S3 encrypts and decrypts objects.
- Identify the required permission layers: **IAM identity policies**, **S3 bucket/access point policies**, **KMS key policies/grants**, **SCP** constraints, VPC endpoint policies, and **explicit Denies**.
- Configure bucket default encryption, upload/read SSE-KMS objects using the AWS CLI, inspect metadata, monitor, and investigate errors.
- Analyze **cross-account access**, **AWS managed keys vs. customer managed keys**, **S3 Bucket Keys**, **replication/copy**, **multipart uploads**, key rotation, and scenarios that trigger `AccessDenied`.
- Propose an encryption design for applications on **EC2/ECS/Lambda**, where **IAM, VPC, Region/AZ, resilience, monitoring, and cost** must be evaluated together.

**Context:** This lesson is part of the **S3 Object Storage** chapter of the **CLOUD_PROVIDERS_AWS** module. In an AWS architecture, S3 commonly stores product images, invoice documents, logs, analytics datasets, and backups. Encrypting data at rest is one piece of designing a secure application; **encryption does not grant access permissions on its own and does not replace IAM, networking, versioning, backups, or monitoring**.

> **Assumptions:** Examples primarily use **S3 general purpose buckets** in the same Region as the KMS key. Specific characteristics of **directory buckets / S3 Express One Zone**, cross-account setups, or newer features have their own rules. Always verify AWS documentation for the exact bucket type, Region, and APIs in production.

## 1. Separating Three Questions: Is Data Encrypted, Who Can Read It, and Who Manages the Key?

For an S3 object, there are three distinct concerns:

1. **Encryption at rest:** How is the object's content protected while stored on S3 infrastructure?
2. **Authorization:** Which principals are allowed to call `PutObject`, `GetObject`, `ListBucket`, or `DeleteObject`?
3. **Key authorization/management:** When using SSE-KMS or DSSE-KMS, which principals are permitted to use the **KMS key** to generate data keys, decrypt, share, and audit?

Suppose a company stores `invoices/2026/order-1001.pdf` in S3:

- The bucket allows a Lambda role to read the file via `s3:GetObject`.
- The object uses **SSE-KMS** with a customer managed KMS key.
- The Lambda role lacks `kms:Decrypt` or the key policy does not permit the role to use the key.
- Result: calling `GetObject` **can fail with AccessDenied even though S3 permissions are valid**.

Conversely, granting `kms:Decrypt` does not mean the role automatically gains `s3:GetObject`. These two permission layers govern different actions.

~~~mermaid
flowchart LR
  A[Application with IAM role] --> B{Does S3 allow GetObject?}
  B -->|No| E[AccessDenied]
  B -->|Yes| C{Does object use SSE-KMS?}
  C -->|No| D[S3 returns object per valid permissions]
  C -->|Yes| K{Does KMS allow Decrypt on the key?}
  K -->|No| E
  K -->|Yes| D
~~~

This diagram is a simplified learning model; real-world evaluation also includes **bucket policy Denies, SCPs, permissions boundaries, session policies, key policies, grants, VPC endpoint policies**, and request conditions.

### Where Does Encryption Differ from Access Control?

| Mechanism | Purpose | Does Not Guarantee by Itself |
| --- | --- | --- |
| **SSE-S3/SSE-KMS/DSSE-KMS** | Protects data at rest per S3 encryption mode | Who holds S3 access, TLS, or application authentication |
| **IAM and bucket policies** | Allows or denies S3 API calls for principals | Permission to use the KMS key under SSE-KMS |
| **KMS key policy / IAM / grants** | Controls usage of the KMS key | That the caller has S3 access to the object |
| **TLS + HTTPS bucket policy** | Protects data in transit and enforces secure transport | That an object can still be recovered after deletion |
| **Versioning / Object Lock / backups** | Reduces accidental deletion/modification risk and aids recovery per config | Proper data access permissions or encryption |

## 2. S3 Object Encryption Modes

All **newly uploaded objects to S3** are encrypted server-side by default using **SSE-S3** unless another configuration or header is specified. This has been S3's default behavior since 2023. Users can choose stronger key-governance encryption modes as needed.

| Mode | Who Manages the Key Material? | When to Choose | Extra Client Permissions |
| --- | --- | --- | --- |
| **SSE-S3** | Amazon S3 manages service encryption keys | Most data needing standard encryption at rest with minimal ops | Appropriate S3 permissions; typically no separate AWS KMS permissions |
| **SSE-KMS** | AWS KMS manages the KMS key (**AWS managed key** or **customer managed key**) | Need key-usage access control, key audit trails, custom key policy/rotation, cross-account sharing | Needs both S3 permissions **and** appropriate KMS permissions |
| **DSSE-KMS** | Two layers of server-side encryption, one using AWS KMS | Compliance or policy mandates dual-layer encryption for supported objects/services | Appropriate S3/KMS permissions; check specific limits and separate pricing |
| **SSE-C** | Client supplies the encryption key on every request; S3 does not store the key | Specific compatibility/policy mandates requiring full client-side key control | Client must supply the exact key on read; does not use KMS keys as in SSE-KMS |
| **Client-side encryption** | Application encrypts before upload; client manages keys independently | Requirement that S3 stores only application-generated ciphertext | Client must decrypt after download; can be combined with server-side SSE |

**SSE** stands for *Server-Side Encryption*. In SSE modes, S3 handles encryption before writing data to storage and decrypts it upon authorized object retrieval.

### 2.1. SSE-S3: The Simple Default

With SSE-S3, S3 uses AWS-supported strong encryption (such as AES-256) and manages the keys and encryption workflow automatically; applications do not need to create a customer managed KMS key.

Appropriate when:

- Encryption at rest is required without custom KMS key policy/permission controls.
- Object/request volume is very high and you want to avoid KMS management overhead.
- Data is internal or not sensitive enough to require separate key policies.

SSE-S3 **does not mean objects are public**: reads and writes are still governed by IAM, bucket policies, Block Public Access, and S3 security controls.

### 2.2. SSE-KMS: Separating S3 Permissions and KMS Permissions

With SSE-KMS, you specify an **AWS KMS key** in the matching Region. AWS KMS offers:

- **AWS managed key** with an alias like `aws/s3`: AWS creates and manages its key policy for service integration; you cannot customize its key policy for arbitrary cross-account access.
- **Customer managed key**: you create and control its key policy, lifecycle, rotation settings, tags, and cross-account sharing.

**If principals in another AWS account need to read or write SSE-KMS objects, you generally must use a customer managed KMS key with an appropriate key policy.** Opening the bucket policy alone is insufficient when objects are encrypted with the AWS-managed `aws/s3` key.

Common scenario: an ECS role writes objects using SSE-KMS with a customer managed key; a Lambda role in another account needs to read those objects and must be granted permissions on both the **bucket/object** and the **KMS key**.

### 2.3. DSSE-KMS: Dual-Layer Server-Side Encryption

**Dual-Layer Server-Side Encryption with AWS KMS keys (DSSE-KMS)** applies two independent layers of server-side encryption managed by S3, with one layer integrated with AWS KMS. It is chosen when compliance or governance mandates dual-layer encryption for supported objects and services.

Key points to note:

- Enabling standard SSE-KMS does not automatically provide two-layer DSSE-KMS.
- **S3 Bucket Keys are not supported with DSSE-KMS**; if you rely on Bucket Keys to reduce KMS calls, re-evaluate costs.
- Certain S3 integrations/features have separate support constraints; verify compatibility before using replication, copy, or analytics.
- DSSE-KMS does not replace IAM authorization, key policies, TLS, or application-level controls.

### 2.4. SSE-C and Client-Side Encryption

With **SSE-C**, every request must provide a customer-supplied key to S3 using the supported protocol. To read the object, the client must present the exact key; losing the key means losing the ability to decrypt the data. Never expose keys in logs, URLs, captured headers, or insecure channels.

With **client-side encryption**, the application encrypts data **before** sending it to S3. S3 stores only ciphertext; reading the plaintext requires decrypting via the application's mechanism or an appropriate client such as the AWS Encryption SDK / S3 Encryption Client. This approach adds complexity around key management, metadata, re-encryption, and sharing.

**Practical decision:** if standard encryption suffices, start with SSE-S3. If you need **key policy governance, key-usage auditing, or cross-account KMS sharing**, choose SSE-KMS with a customer managed key. If policy mandates dual-layer encryption, evaluate DSSE-KMS. Avoid SSE-C or client-side encryption unless justified, as they shift heavy key-management responsibility onto the application.

## 3. Envelope Encryption: How Does S3 Use a KMS Key?

**Envelope encryption** encrypts large payloads using a **data key**, while a KMS key protects that data key. With SSE-KMS, S3 integrates with AWS KMS to generate and use data keys for object encryption.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant App as App IAM role
    participant S3 as Amazon S3
    participant KMS as AWS KMS
    participant Store as S3 encrypted object storage

    App->>S3: PutObject (SSE-KMS, KMS key)
    S3->>KMS: GenerateDataKey (per valid permissions/conditions)
    KMS-->>S3: Plaintext data key + encrypted data key
    Note over S3: Uses plaintext data key in memory to encrypt object
    S3->>Store: Stores ciphertext + wrapped key metadata
    S3-->>App: Success

    App->>S3: GetObject
    S3->>KMS: Decrypt data key per valid key and context
    KMS-->>S3: Data key for decryption
    S3->>Store: Reads ciphertext
    S3-->>App: Decrypted object content
~~~

The diagram illustrates the primary flow; **S3 Bucket Keys and KMS integration optimizations** can significantly reduce KMS calls and change how data keys are reused internally. Do not assume from this diagram that every single `PutObject` or `GetObject` translates one-for-one into a KMS API call.

### Key Components

| Component | Role |
| --- | --- |
| **KMS key** | Logical key in AWS KMS used to protect and govern key usage; has a key ID/ARN, policy, and lifecycle |
| **Data key** | Symmetric data key used by S3 to encrypt the object body |
| **Encrypted data key** | Copy of the data key wrapped by the KMS key and stored alongside the object metadata |
| **Encryption context** | Non-secret key-value pairs binding KMS cryptographic operations to an encryption context |
| **KMS key policy** | Resource-based policy defining which principals/permissions can use the key |
| **IAM identity policy / grant** | Additional authorization mechanisms enabling KMS actions within key policy and guardrail limits |

**Do not think that the entire object payload is sent to KMS for KMS to encrypt byte by byte.** AWS KMS protects the small data keys in this process; S3 performs the bulk encryption of the object body.

### KMS Key Region

The KMS key used for **SSE-KMS on an S3 object** must reside in the **same AWS Region** as the bucket where S3 encrypts the object. When **copying or replicating to another Region**, select an appropriate key in the destination Region if using SSE-KMS at the destination. Never pass a Region A key ARN to a bucket in Region B expecting S3 to translate it automatically.

## 4. Bucket Default Encryption vs. Per-Request Encryption

S3 supports a **default encryption configuration** at the bucket level. When an object is uploaded and the client **does not specify another mode**, the bucket's default configuration is applied.

Example:

~~~text
Bucket: invoice-data-demo
Region: ap-southeast-1
Default encryption: SSE-KMS
KMS key: arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab
Bucket Key: enabled
~~~

If a client uploads a new object without sending encryption headers, the bucket applies SSE-KMS as configured. However:

- **Default encryption does not automatically override explicit encryption headers sent by clients**; understand how requested modes interact with S3 and KMS permissions.
- **Changing default encryption does not re-encrypt pre-existing objects**. To change the encryption mode or key for existing data, plan a copy, S3 Batch Operations, or re-encryption workflow.
- **Default encryption is not a bucket policy.** It tells S3 how to encrypt on write, whereas a policy defines which principals can call APIs and under what conditions.
- When objects must strictly use **one specific key**, coordinate bucket configuration, key permissions, policies, and upload workflows using supported mechanisms.

### Inspecting Current Configuration via CLI

~~~bash
aws sts get-caller-identity --profile lab

aws s3api get-bucket-encryption \
  --bucket invoice-data-demo \
  --profile lab \
  --region ap-southeast-1
~~~

Sample output:

~~~json
{
  "ServerSideEncryptionConfiguration": {
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "aws:kms",
          "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
        },
        "BucketKeyEnabled": true
      }
    ]
  }
}
~~~

**Bucket names, account IDs, and key IDs are illustrative**; replace them with real, authorized resources before running CLI commands.

### Configuring Default SSE-KMS

In **S3 Console → Bucket → Properties → Default encryption**, choose **SSE-KMS**, the appropriate KMS key, and optionally **S3 Bucket Key** if supported and beneficial for your workload.

AWS CLI example, using a JSON file **created by the practitioner in a lab environment**:

~~~json
{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
      },
      "BucketKeyEnabled": true
    }
  ]
}
~~~

After saving the JSON above as `bucket-encryption.json`:

~~~bash
aws s3api put-bucket-encryption \
  --bucket invoice-data-demo \
  --server-side-encryption-configuration file://bucket-encryption.json \
  --region ap-southeast-1 \
  --profile lab
~~~

To apply this configuration, the administrative principal needs the corresponding S3 bucket configuration permissions and **KMS key permissions** as required. Verify permissions, key ARN, bucket Region, and account procedures before running.

**Note:** By baseline behavior, AWS S3 encrypts new objects with SSE-S3 by default since 2023 even if you have not configured a custom default rule. Do not misinterpret the absence of a custom SSE-KMS rule as plaintext storage.

## 5. SSE-KMS Authorization: Three Layers to Read Together

For SSE-KMS, a successful access path typically involves:

1. **S3 access:** IAM identity policy and/or bucket/access point policy permits `s3:PutObject` or `s3:GetObject` on the requested resource, without being blocked by Block Public Access, explicit Deny, SCPs, permissions boundaries, session policies, or VPC endpoint policies.
2. **KMS authorization:** The KMS key policy must allow key usage **directly** or **permit IAM policies in the account to grant permissions**; grants may also apply where used. For **cross-account** access, both the key owner's key policy and the caller's IAM policy generally must allow it.
3. **Request context:** The KMS key must be enabled/usable, in the right Region, of the right key type, and conditions such as `kms:ViaService` and encryption context must match. During S3 service calls, S3 invokes KMS on the caller's behalf using the caller's permissions and supported context.

~~~mermaid
flowchart TD
    A[Role/Principal calls S3 API] --> B{S3 authorization}
    B -->|Deny| X[AccessDenied]
    B -->|Allow| C{Does object need KMS ops?}
    C -->|No| Z[Perform S3 operation]
    C -->|Yes| D{KMS key policy + IAM/grant + conditions}
    D -->|Deny| X
    D -->|Allow| Z
~~~

### Common KMS Permissions

| S3 Operation | S3 Permission to Check | KMS Permission Typically Needed |
| --- | --- | --- |
| **PutObject with SSE-KMS** | `s3:PutObject` | `kms:GenerateDataKey` |
| **GetObject with SSE-KMS** | `s3:GetObject` | `kms:Decrypt` |
| **Multipart upload with SSE-KMS** | `s3:PutObject`, plus any upload-method permissions | `kms:GenerateDataKey` and in certain stages `kms:Decrypt` |
| **CopyObject: SSE-KMS source** | Read source and write destination per policies | `kms:Decrypt` on source key; matching permissions on destination key if encrypted |
| **Upload/Copy to SSE-KMS destination** | Write permission on destination object | `kms:GenerateDataKey` on destination key, plus extra permissions per workflow |
| **HeadObject (basic metadata)** | `s3:GetObject` or appropriate API permission | Typically does not decrypt body; **certain checksum/API options** may require KMS permission |
| **ListBucket** | `s3:ListBucket` | Does not require `kms:Decrypt` merely to list object keys |

This table lists **common permissions**, not an exhaustive replica of all API conditions. For **multipart uploads**, copies, replication, Bucket Keys, checksums, or specialized features, check the exact required permissions in the corresponding API docs.

### Why Adding IAM `kms:Decrypt` Still May Not Be Enough

A KMS key policy might **not permit** the role to use the key or might not delegate permission to the account's IAM policies; the key could also be disabled, pending deletion, or have a mismatched condition. This causes an `AccessDenied` at the KMS layer even when the IAM role has `kms:Decrypt` and the S3 bucket allows `GetObject`.

Likewise, an **IAM role trust policy** is a separate concern: it controls who can assume the role. Successfully assuming a role does not imply S3 or KMS API calls are permitted.

## 6. Complete Example: Same-Account Role Reading and Writing SSE-KMS Objects

**Problem:** Account `111122223333`, Region `ap-southeast-1`, bucket `invoice-data-demo`, illustrative customer managed KMS key ARN:

~~~text
arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab
~~~

A Lambda or ECS role `InvoiceWorkerRole` needs to:

- Upload new objects into `invoices/` using SSE-KMS.
- Read objects under `invoices/`.
- Not delete the bucket, modify bucket policies, or administer the key.

### 6.1. Identity-Based Policy Attached to the Role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteInvoiceObjects",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::invoice-data-demo/invoices/*"
    },
    {
      "Sid": "UseInvoiceKMSKey",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
    }
  ]
}
~~~

**Explanation:**

- `s3:GetObject` and `s3:PutObject` apply strictly to objects under the `invoices/` prefix.
- `kms:GenerateDataKey` allows the workflow to generate data keys when writing SSE-KMS objects.
- `kms:Decrypt` supports reading objects and workflows such as multipart uploads where needed.
- `kms:DescribeKey` does not replace encrypt/decrypt permissions; it helps with certain inspection/verification calls.
- The policy does not grant `s3:DeleteObject`, bucket management, or key policy administration.

If the application needs to **list the prefix**, you must also grant `s3:ListBucket` on the **bucket ARN**, typically scoped with a `s3:prefix` condition. Do not attach `ListBucket` to an object ARN expecting it to work.

### 6.2. KMS Key Policy Allowing the Role to Use the Key

Illustrative statement placed inside the **key policy** of that exact customer managed KMS key (not the bucket policy):

~~~json
{
  "Sid": "AllowInvoiceWorkerUseFromS3",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111122223333:role/InvoiceWorkerRole"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "s3.ap-southeast-1.amazonaws.com"
    }
  }
}
~~~

This is **a single statement** to integrate into a valid existing key policy, **not a complete standalone key policy**. A KMS key policy must retain key administration permissions and proper recovery controls. Inside a key policy, `Resource: "*"` refers to the key to which the policy is attached; it does not grant permissions across all KMS keys in the account.

**The `kms:ViaService` condition:** restricts use of the KMS key to calls routed through the S3 service in the specified Region per supported flows. Pairing this condition with the exact role ARN tightly scopes key usage. Do not apply it blindly to direct application KMS calls: if an application calls `kms:Decrypt` directly, the `kms:ViaService` condition for S3 will not match.

**Same-account nuance:** A key policy can grant access directly to a role or allow IAM identity policies within the account to grant key permissions via the standard delegation statement. Therefore, do not claim that **every** same-account KMS usage strictly requires both a direct role Allow in the key policy **and** an IAM Allow. The example deliberately shows both so learners clearly see both control layers.

### 6.3. Permission to Use a Role Does Not Imply Permission to Read Objects

If the workload runs on:

- **Lambda:** requires an execution role trusting `lambda.amazonaws.com`; attach the policy above.
- **ECS:** typically attach the policy to the **task role** used by the container, not the ECS task execution role used for pulling images and writing logs.
- **EC2:** use a role via an instance profile so the SDK retrieves temporary credentials.
- **CI/CD:** use a role assumed via supported authentication or federation; never hardcode access keys.

In all cases, the **key policy must still authorize the actual calling principal context**. Verify with `aws sts get-caller-identity` from the exact environment encountering errors.

## 7. Bucket Policies and Mandating SSE-KMS

There are two very different goals:

- **Goal A:** "Every newly stored object uses SSE-KMS" → set **default encryption to SSE-KMS** and govern configuration/permissions.
- **Goal B:** "Clients must explicitly send the SSE-KMS header in upload requests" → use a **bucket policy Deny** conditioned on the request header.

Example **denying `PutObject` requests that do not declare SSE-KMS**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUploadsWithoutExplicitSSEKMS",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::invoice-data-demo/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    }
  ]
}
~~~

**Behavior warning:** The statement above rejects any request **missing the SSE-KMS header**, even if the bucket **already has default encryption set to SSE-KMS**. Because the policy inspects the **incoming request condition**, it does not factor in that S3 would apply default SSE-KMS afterward. This breaks upload clients that rely on bucket defaults. Only enforce this when your design explicitly requires **clients to declare** the encryption mode and all clients have been updated.

### Want to Enforce a Specific Customer Managed Key?

Beyond `s3:x-amz-server-side-encryption`, you can use the related condition key:

~~~text
s3:x-amz-server-side-encryption-aws-kms-key-id
~~~

When authoring the bucket policy, account for **missing headers**, **other key ARNs**, aliases, key ID formats, and interaction with default encryption. Never take a sample policy that blocks uploads and then loosen `Principal` or open the KMS key unconditionally to make errors go away.

A simpler governance approach is often **default SSE-KMS with the official key + restricting who can modify bucket encryption configuration + compliance monitoring**, reserving header-based Deny rules for verified design mandates.

### Enforcing HTTPS

Data in S3 is encrypted at rest, yet requests also need protection **in transit**. Consider a bucket policy Deny when `aws:SecureTransport=false`:

~~~json
{
  "Sid": "DenyInsecureTransport",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::invoice-data-demo",
    "arn:aws:s3:::invoice-data-demo/*"
  ],
  "Condition": {
    "Bool": {
      "aws:SecureTransport": "false"
    }
  }
}
~~~

Before deploying in production, evaluate **AWS services calling on your behalf**: certain network context keys are omitted for service principals, so an organization may need an `aws:PrincipalIsAWSService` exception following AWS patterns to avoid accidentally blocking valid service-to-service workflows. Never add broad exceptions without verified justification.

## 8. Cross-Account Access: Why Opening the Bucket Alone Fails

Suppose:

- **Account A:** `111122223333`, bucket `invoice-data-demo` and a customer managed KMS key.
- **Account B:** `444455556666`, role `ReportConsumerRole` needs to **read** `reports/` in A's bucket.
- Cross-account access is granted to a **specific role**, without sharing static keys.

### 8.1. Three Authorizations Must Align Simultaneously

| Location | Configuration | Role |
| --- | --- | --- |
| **Bucket in A** | Bucket policy allowing role B to read `reports/*` | Grants access on the S3 resource side |
| **Role in B** | IAM identity policy granting `s3:GetObject` on the object ARN | Grants permission on the caller side for standard cross-account access |
| **KMS key in A** | Key policy allowing role/account B to use `kms:Decrypt` under appropriate conditions | Allows decrypting the object's data key in the key-owning account |
| **Role in B (KMS)** | IAM identity policy granting `kms:Decrypt` for A's key ARN | Completes cross-account KMS permission on the caller side |

**AWS KMS differs from S3 cross-account rules:** for a KMS key in account A, an IAM policy in account B alone is **never sufficient**; A's key policy must permit cross-account access, and B's IAM policy must also grant the corresponding actions. The key must support custom policies and sharing—typically a **customer managed key**.

### 8.2. Bucket Policy in Account A

Example statement scoped to a prefix:

~~~json
{
  "Sid": "AllowReadReportsFromAccountB",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/ReportConsumerRole"
  },
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::invoice-data-demo/reports/*"
}
~~~

Depending on the context, the bucket owner must also review Object Ownership, Block Public Access, explicit Denies, and organizational policies. If `ListBucket` is required, grant it on the bucket ARN with a matching `s3:prefix` condition.

### 8.3. KMS Key Policy in Account A

Illustrative statement inside the customer managed key policy:

~~~json
{
  "Sid": "AllowAccountBReportConsumerDecryptViaS3",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/ReportConsumerRole"
  },
  "Action": [
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "s3.ap-southeast-1.amazonaws.com"
    }
  }
}
~~~

### 8.4. IAM Policy for `ReportConsumerRole` in Account B

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::invoice-data-demo/reports/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab"
    }
  ]
}
~~~

After configuring, test `GetObject` from the real role and verify CloudTrail/S3 responses. **Never change `Principal` to `"*"` or open key permissions to all accounts** unnecessarily.

### The AWS Managed Key `aws/s3` Is an Important Boundary

With the AWS managed key for S3, you cannot edit its key policy to grant access to a role in account B like you can with a customer managed key. When cross-account reads of SSE-KMS objects are needed:

1. Choose a **customer managed KMS key** in the target Region.
2. Configure the bucket/objects to use that key.
3. Configure matching **bucket policy, KMS key policy, and caller IAM policy**.
4. For older objects still encrypted with `aws/s3`, plan to **copy/re-encrypt** them to the customer managed key before shifting cross-account consumers.

## 9. AWS CLI Hands-On: Uploading, Checking Metadata, and Reading Objects

**Environment:** A lab account already has a bucket and customer managed KMS key in the right Region. IDs below are illustrative only. The test role has appropriate S3/KMS permissions; use no real secrets and never log temporary credentials in terminal output.

### 9.1. Verify Active AWS Caller Identity

~~~bash
aws sts get-caller-identity --profile lab
aws s3api get-bucket-location --bucket invoice-data-demo --profile lab
aws s3api get-bucket-encryption --bucket invoice-data-demo --profile lab
~~~

Verify the account/role, bucket Region, and default encryption rule before uploading. In some environments, `GetBucketEncryption` is denied by IAM; **AccessDenied on reading bucket configuration does not prove objects are unencrypted**.

### 9.2. Create a Local Test File

~~~bash
printf "hello s3 sse-kms lab\n" > invoice-lab.txt
~~~

This creates a simple file on the learner's machine. Do not use personal information or sensitive data for testing.

### 9.3. Upload with SSE-KMS Using a Specific Key ARN

~~~bash
aws s3api put-object \
  --bucket invoice-data-demo \
  --key invoices/lab/invoice-lab.txt \
  --body invoice-lab.txt \
  --server-side-encryption aws:kms \
  --ssekms-key-id arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab \
  --profile lab \
  --region ap-southeast-1
~~~

The S3 CLI initiates the upload and S3 integrates with KMS as configured. If `kms:GenerateDataKey` is missing, the key policy rejects it, or S3 permissions are blocked, the operation fails. Explicitly specify the KMS key ARN especially when accounts, roles, or buckets involve cross-account contexts.

### 9.4. Inspect Encryption Metadata

~~~bash
aws s3api head-object \
  --bucket invoice-data-demo \
  --key invoices/lab/invoice-lab.txt \
  --query '{SSE:ServerSideEncryption,KMSKey:SSEKMSKeyId,BucketKey:BucketKeyEnabled,Size:ContentLength}' \
  --profile lab \
  --region ap-southeast-1
~~~

Illustrative response:

~~~json
{
  "SSE": "aws:kms",
  "KMSKey": "arn:aws:kms:ap-southeast-1:111122223333:key/12345678-1234-1234-1234-1234567890ab",
  "BucketKey": true,
  "Size": 21
}
~~~

With SSE-S3, metadata typically shows `ServerSideEncryption: AES256`; with DSSE-KMS, the value can appear as `aws:kms:dsse`. Do not assume **every** response attribute is always populated across every object/bucket type.

### 9.5. Download and Read

~~~bash
aws s3api get-object \
  --bucket invoice-data-demo \
  --key invoices/lab/invoice-lab.txt \
  ./downloaded-invoice-lab.txt \
  --profile lab \
  --region ap-southeast-1
~~~

If the object uses SSE-KMS, the role needs the appropriate key decryption permission for the workflow. **Do not pass `--server-side-encryption` to `GetObject`** to tell S3 to "decrypt": S3 automatically handles server-side decryption according to object metadata and valid permissions.

### 9.6. Verify a Denied Path as Well

In a lab, you can test a **role that has S3 permissions but lacks KMS permissions** against an SSE-KMS object. Record the error and CloudTrail event, then restore the valid configuration. Never modify production bucket or key policies to stage a demo failure.

**Expected outcome:** Learners confirm that **encryption is recorded in object metadata** and **valid S3 permissions are insufficient when KMS denies access**.

## 10. S3 Bucket Keys: Reducing KMS Requests and Changing Encryption Context

For buckets with many SSE-KMS objects, S3 can generate high volumes of KMS calls. **Amazon S3 Bucket Keys** is a feature that dramatically reduces S3 → KMS requests during SSE-KMS encryption, cutting KMS request costs and quota pressure. Depending on the workload, AWS documents reductions of **up to roughly 99%** in related KMS request volume.

### When Is It a Good Fit?

- Buckets with **many objects** frequently uploaded/read using SSE-KMS.
- **KMS request** cost or API rate quotas are an active concern.
- The workload uses standard **SSE-KMS**, not requiring DSSE-KMS.
- Key policies and encryption context conditions have been reviewed for Bucket Key compatibility.

### Why Must You Understand Encryption Context?

The KMS encryption context is a set of key-value pairs attached to KMS requests to support validation and policy conditions. With standard SSE-KMS, one context key S3 passes is:

~~~text
kms:EncryptionContext:aws:s3:arn
~~~

In many cases **without Bucket Keys**, the value is the **object ARN**, for example:

~~~text
arn:aws:s3:::invoice-data-demo/invoices/2026/order-1001.pdf
~~~

When **using S3 Bucket Keys**, the context can change to the **bucket ARN**:

~~~text
arn:aws:s3:::invoice-data-demo
~~~

If a KMS key policy or IAM policy includes a `kms:EncryptionContext:aws:s3:arn` condition requiring `arn:aws:s3:::invoice-data-demo/invoices/*`, enabling Bucket Keys can cause KMS requests to **fail the condition check**. Evaluate and update policy conditions and test permissions whenever toggling this feature.

**Never put secrets into encryption context**: context values can appear in KMS/CloudTrail audit logs.

### Do Bucket Keys Change IAM/S3 Permissions?

No. Bucket Keys reduce KMS call frequency and alter encryption context granularity; **they do not grant `s3:GetObject`**, replace bucket policies, or remove the need for proper key governance. For cross-account sharing and constrained key policies, test requests from each real principal.

### SSE-KMS Costs

When using a **customer managed key**, costs can include:

- Key maintenance fees (and key version/feature fees where applicable).
- **AWS KMS API request** fees tied to uploads, downloads, copies, multipart uploads, or other workflows.
- S3 storage, requests, data transfer, replication, logging, and supporting infrastructure fees.

**AWS managed keys** have a different key-management fee structure than customer managed keys, though **KMS requests can still incur charges**. Standard SSE-S3 does not incur these KMS API charges for the application.

Never choose between SSE-KMS and SSE-S3 solely on a single fee figure; first meet key-governance and auditing requirements, then optimize with Bucket Keys and request patterns.

## 11. KMS Key Policies, Grants, Rotation, and Key Lifecycle

### 11.1. Key Policies Are the Primary Access Control for KMS Keys

AWS KMS differs from many services in that **every key has a key policy**. A key policy can:

- Allow specific principals to use the key;
- Allow **IAM identity policies in the same account** to grant key permissions per the policy structure;
- Enforce conditions such as `kms:ViaService` or encryption context;
- Separate **key administration** permissions from **encrypt/decrypt** permissions.

**Key administration permissions do not automatically grant permission to decrypt data**; designs should separate key administrators from applications using the key unless a workflow genuinely requires combining them.

A key policy that accidentally **removes administrative/recovery permissions** can leave a key unmanageable. During practice, preserve mandatory organizational admin statements and only add tightly scoped usage statements.

### 11.2. KMS Grants

A **KMS grant** is a mechanism giving a grantee permission to use a KMS key for allowed operations, commonly used by AWS service integrations. Grants do not fully replace key policies; creating grants relies on appropriate key policy/IAM permissions and supported constraints.

In some systems, troubleshooting requires inspecting all of:

- The principal's IAM policy;
- The KMS key policy;
- Active grants and grant constraints;
- Explicit Denies from guardrail layers.

Do not broadly grant `kms:CreateGrant` just to silence `AccessDenied`; it carries administrative impact and must be tightly scoped to the use case.

### 11.3. Rotation Does Not Re-Encrypt Existing Data

**KMS automatic rotation** for customer managed keys allows AWS KMS to generate new cryptographic key material on a configured schedule. The logical key ID/ARN remains unchanged, and AWS KMS retains prior key material needed to decrypt older ciphertexts.

**Important:** Enabling automatic key rotation **does not rewrite existing S3 objects or change their SSE mode**. If your goal is to **migrate all objects to a new KMS key with a different ARN**, you need an explicit re-encryption/copy workflow.

### 11.4. How Disabling or Deleting a KMS Key Affects Data

- When a key is **disabled** or lacks permissions, SSE-KMS objects relying on that key **cannot be read or written** along KMS-dependent flows.
- **Scheduled deletion** culminating in permanent key deletion can result in **permanent inability to decrypt** data encrypted solely under that key.
- Backups, copies, or replicas encrypted with other keys must be verified for accessibility before changing key lifecycle state.
- Configure alerts via CloudTrail/EventBridge/CloudWatch for state and policy changes on critical keys.

When rotating to a new key ARN or responding to a suspected key compromise, **inventory dependent objects**, retain decryption capability for historical data during migration, and run restore drills. Operational risk here is far greater than toggling a typical bucket property.

## 12. Copy, Multipart Upload, Replication, and Legacy Objects

### 12.1. `CopyObject` Between Two Keys

Suppose a source object uses `KMS-Key-A`, and the destination object is copied with `KMS-Key-B`. The workflow may require:

- `s3:GetObject` on the source and `s3:PutObject` on the destination;
- `kms:Decrypt` on key A;
- `kms:GenerateDataKey` and required KMS permissions on key B;
- Matching bucket/object policies and KMS constraints.

If copying an object within the same bucket solely to change its key, **re-copying** can create a **new version** if versioning is enabled, alter ETag/metadata per API behavior, and increase request costs. For millions of objects, consider **S3 Batch Operations** with controlled tracking and error handling.

### 12.2. Multipart Upload and SSE-KMS

Large file uploads via multipart upload split data into parts. With SSE-KMS, beyond `s3:PutObject`, verify the KMS permissions required at each stage—specifically `kms:GenerateDataKey` and `kms:Decrypt` per S3 multipart documentation. A role that uploads small files fine yet hits **AccessDenied on multipart uploads** may be missing KMS permissions needed for multipart workflows.

### 12.3. Replication for SSE-KMS Objects

Common goals:

- Replicate objects from a source bucket to a destination bucket in the same or another Region.
- Maintain copies in a dedicated backup account.
- Encrypt replicas with a **KMS key in the destination Region**.

For SSE-KMS, replication requires explicitly **opting in** to replicate SSE-KMS encrypted objects and specifying the destination KMS key in the replication rule; the replication IAM role needs both S3 and KMS permissions. It may need permission to decrypt with the source key and encrypt with the destination key, plus matching key policies. **Never assume enabling a replication rule automatically replicates SSE-KMS objects.**

Enable versioning as required by replication, verify Object Ownership, cross-account KMS policies, bucket policies, role permissions, request/data-transfer costs, and monitor replication status.

### 12.4. New Default Encryption Does Not Convert Historical Data

Suppose a bucket previously used SSE-S3 and today switches its default to SSE-KMS. New uploads will use the new default as applicable. **Existing objects do not automatically convert to SSE-KMS.**

Migration workflow:

1. **Inventory** current encryption states and key ARNs across objects.
2. Identify the object scope and check versioning, Object Lock, and replication dependencies.
3. Prepare KMS keys, IAM roles, key/bucket policies, and quotas.
4. Pilot copy/re-encrypt on a representative sample; verify metadata and read/restore behavior.
5. Migrate in batches with retries, error tracking, and budget monitoring.
6. Validate applications, presigned URLs, metadata, and versioning/dedup side effects.
7. Clean up old versions or legacy keys only after verifying new data is readable and backed up.

## 13. Combining S3 SSE-KMS with EC2, ECS, Lambda, VPC, and Data Services

A sample architecture storing invoices for an e-commerce application:

~~~mermaid
flowchart TB
    U[User] --> API[API Gateway / ALB]
    API --> App[Lambda or ECS: create invoice]
    App -->|PutObject SSE-KMS| S3[(S3 invoice bucket)]
    App -. IAM role .-> IAM[IAM permissions]
    S3 -->|GenerateDataKey / Decrypt per workflow| KMS[AWS KMS key]
    IAM -. KMS permissions .-> KMS
    S3 --> Log[CloudTrail / S3 access logs]
    KMS --> Audit[CloudTrail key events]
    App --> Obs[CloudWatch alarms]
    S3 --> Backup[Versioning / backup / replication]
~~~

**Each layer has a distinct responsibility:**

- **IAM role** for Lambda/ECS/EC2 grants `s3:PutObject`, `s3:GetObject`, and scoped KMS permissions for exact keys/actions, attached using each compute service's role mechanism.
- **VPC and networking** determine whether the runtime has a network path to S3 endpoints; private workloads can use an **S3 gateway endpoint** or appropriate endpoint. A valid network path does not replace IAM or KMS permissions.
- **S3 default encryption** enforces SSE-KMS; roles and bucket policies constrain prefixes, TLS, and access rules.
- **KMS key** carries an appropriate key policy, audit logging, and rotation/recovery procedures.
- **CloudTrail** enables S3/KMS API auditing; capturing full object-level S3 data events generally requires explicit configuration.
- **Versioning/replication/backups** enable recovery from accidental deletion or overwrites to meet RPO/RTO targets.
- **AWS Budgets / Cost Explorer** monitor storage, KMS requests, API requests, replication, transfer, and logs.

### Does Object Encryption Depend on Availability Zone (AZ)?

An S3 general purpose bucket is a **Regional** resource, not pinned to a single AZ like an EBS volume. The KMS key for SSE-KMS must be in the same Region as the bucket, while EC2/Lambda workloads can run across multiple AZs. Even with S3's service-level durability, **losing a KMS key or losing permission to it can render objects unreadable**, so treat key policies and key lifecycle as critical availability dependencies.

### Permissions for Presigned URLs

An application can generate a **presigned URL** allowing end users to upload or download an S3 object using the permissions of the signing principal. This avoids distributing long-term AWS credentials to end users, but a presigned URL is a time-bounded bearer capability; protect the URL and enforce expected content-type/headers, key prefixes, expirations, and allowed actions.

With SSE-KMS, **the signing principal** and S3/KMS workflow must hold appropriate permissions. End users do not receive KMS credentials directly; however, an upload using a presigned URL must send **headers matching the signature** if SSE-KMS headers were signed. Never embed KMS key material or application secrets in the URL.

## 14. Encryption Monitoring, Auditing, and Cost Control

### 14.1. Verifying Encryption Status

Combine multiple sources:

- **Bucket default encryption configuration:** shows how S3 encrypts new uploads by default.
- **Object metadata from `HeadObject`:** shows the object's SSE mode and key ID/ARN when returned.
- **S3 Inventory / Storage Lens and supported inventory tools:** essential when auditing millions of objects.
- **AWS Config / Security Hub** with relevant rules/controls: detects configuration drift or non-compliance.
- **CloudTrail:** tracks who changed bucket encryption policies, modified key policies, disabled/scheduled key deletion, plus S3 data events when enabled.

**Never rely solely on the bucket's default encryption setting to claim 100% of historical objects use the new key.** Verify via object metadata or inventory reports.

### 14.2. CloudTrail: Do Not Confuse the Log Sources

| Source | Helps Identify | Limitations |
| --- | --- | --- |
| **CloudTrail S3 management events** | Who modified bucket encryption, policies, public access, or replication rules | Does not automatically log every client `GetObject` |
| **CloudTrail S3 data events** | Object-level actions such as `GetObject` and `PutObject` when properly scoped | Separate configuration and cost; must scope buckets/prefixes |
| **CloudTrail AWS KMS events** | Key operations such as `GenerateDataKey`, `Decrypt`, and key policy/state changes | Call counts are not strictly 1:1 with objects due to Bucket Keys and caching |
| **CloudWatch** | Application metrics/alarms, errors, latency, API behavior | Must configure metrics, alarms, and log retention explicitly |

KMS encryption context values can appear in CloudTrail; never store passwords, tokens, or secret data inside them.

### 14.3. Cost Modeling

For SSE-KMS, separate the cost components:

\[
C_{\text{total}}
\approx C_{\text{S3 storage}}
+ C_{\text{S3 requests/transfer}}
+ C_{\text{KMS keys}}
+ C_{\text{KMS requests}}
+ C_{\text{replication/logs/backup}}
\]

A workload with many small objects and heavy read/write traffic can incur **substantial KMS request costs** relative to storage costs. **Bucket Keys** are a primary optimization lever, provided you account for encryption context impacts and unsupported features.

### Example Request-Volume Comparison

Suppose a service creates 2 million objects/month and reads 10 million times/month. With SSE-KMS **without Bucket Keys**, billable KMS API calls can scale up alongside S3 operations; however, **do not blindly assume exactly 12 million KMS requests** without checking caching, multipart uploads, copies, and S3-KMS integration behavior.

Workflow:

1. Measure actual KMS request metrics/billing and CloudTrail activity.
2. Group buckets/prefixes/workloads with high request counts.
3. Evaluate Bucket Keys compatibility with existing key policies.
4. Use **AWS Pricing Calculator / Cost Explorer** with the exact Region, key type, and current pricing.
5. Compare actual post-enablement metrics against baseline measurements.

## 15. Troubleshooting: When Does S3 Return AccessDenied Because of KMS?

| Symptom | Common Causes | Primary Checks |
| --- | --- | --- |
| **`PutObject` SSE-KMS returns `AccessDenied`** | Missing `s3:PutObject`, `kms:GenerateDataKey`, key policy excludes role, or bucket policy rejects header | Caller ARN, bucket policy, KMS key policy, exact KMS ARN/Region |
| **`GetObject` SSE-KMS returns `AccessDenied`** | S3 allows read, but missing `kms:Decrypt`; key policy/SCP/boundary Deny | Check encryption metadata, actual role, and KMS key state |
| **Cross-account read of SSE-KMS object fails** | Bucket allows it, but `aws/s3` key cannot be shared, or missing caller IAM / KMS key policy | Use a customer managed key; grant role B in A's key policy and KMS actions in B's IAM |
| **Only multipart uploads fail** | Missing KMS permissions required for multipart workflow | Check `GenerateDataKey`/`Decrypt`, failing API stage, and CloudTrail |
| **Client omits SSE header and `PutObject` is Denied** | Bucket policy mandates the header, even though default SSE-KMS is enabled | Compare `s3:x-amz-server-side-encryption` policy condition with actual headers |
| **Enabling S3 Bucket Keys triggers `AccessDenied`** | Policy condition on `kms:EncryptionContext:aws:s3:arn` expects an object ARN | Check bucket ARN context and update condition carefully |
| **Changed default encryption, but old objects remain SSE-S3** | Default encryption affects new uploads only | Inventory historical objects and plan re-encryption |
| **Key disabled / pending deletion** | KMS key is unusable or locked by lifecycle | `kms:DescribeKey`, CloudTrail, key owner, key recovery process |
| **SSE-KMS upload to bucket in another Region fails** | KMS key is in a different Region than the bucket | Verify bucket Region and key ARN |
| **Copy/replication fails with KMS `AccessDenied`** | Missing source decrypt / destination encrypt, cross-account key policies, or replication role gaps | Review source/destination, versions, key ARNs/Regions, replication status |
| **`HeadObject` works, `GetObject` fails** | Metadata does not require decrypting body, whereas reading does | Compare `s3:GetObject`, `kms:Decrypt`, and explicit Denies |
| **KMS `Throttling` / `RequestLimitExceeded`** | Excessive KMS calls or key/API rate limits | Measure KMS requests, retry with backoff, enable Bucket Keys, check quotas/cost |
| **Role has IAM KMS Allow yet still fails** | Key policy does not delegate to account IAM or allow role, explicit Deny, or condition mismatch | Compare key policy, grants, context, `kms:ViaService`, SCPs |

### Seven-Step Investigation Workflow

~~~text
1. Identify the actual caller: aws sts get-caller-identity (exact role/profile/workload).
2. Identify the bucket, object key, Region, and failing action (Put/Get/Copy/Multipart).
3. Inspect object encryption metadata (if permitted) and bucket default encryption config.
4. Check IAM + bucket policy: Allow/Deny, prefix, endpoint, SecureTransport.
5. If SSE-KMS: verify key ARN/Region/state, KMS key policy, caller IAM,
   grants, boundaries/SCPs, kms:ViaService, and encryption context.
6. Review CloudTrail S3/KMS events at the time of failure, including request IDs if present;
   check Bucket Keys, replication, and request headers.
7. Apply minimal permission/condition fixes in a lab, retest upload/download,
   and confirm out-of-scope operations remain denied.
~~~

**Never resolve errors by opening** `s3:*`, `kms:*`, or `Principal: "*"` across all resources. Doing so masks the true root cause and creates overly broad access paths—especially dangerous with customer managed KMS keys.

## 16. Common Misconceptions When Designing S3 Encryption

| Misconception | Accurate Understanding |
| --- | --- |
| "S3 has no default encryption unless I turn on a rule." | S3 applies SSE-S3 by default to new objects; custom rules are for SSE-KMS/DSSE-KMS or specific configs. |
| "SSE-KMS only requires S3 permissions." | Operations can also require explicit AWS KMS permissions on the corresponding key. |
| "I have `kms:Decrypt`, so I can definitely read the S3 object." | You still need `s3:GetObject` and no blocking Denies or failed conditions. |
| "Key policy doesn't matter if the IAM policy has Allow." | Key policies are a foundational part of AWS KMS authorization. |
| "The AWS managed key `aws/s3` is easy to share cross-account." | Cross-account access generally requires a customer managed KMS key for controlled sharing. |
| "Enabling default SSE-KMS re-encrypts all old objects." | Default configuration primarily affects new uploads; historical data requires explicit re-encryption. |
| "Requiring clients to send an SSE-KMS header won't affect default uploads." | A bucket policy denying based on request headers blocks clients relying on default encryption. |
| "S3 Bucket Keys only cut costs without affecting policies." | Encryption context can switch to the bucket ARN instead of the object ARN, affecting KMS conditions. |
| "KMS key rotation automatically rewrites every S3 object." | Automatic rotation of the same logical key does not change object encryption mode or ARN. |
| "S3 encryption is a backup." | Encryption does not protect against accidental deletion, overwrites, or data loss from key deletion. |
| "SSE-KMS automatically routes network traffic privately." | Encryption at rest does not control VPC routing, endpoints, or TLS. |
| "CloudTrail automatically logs every S3 `GetObject`." | Object-level data events typically require explicit configuration per requirements. |

## 17. AWS Implementation Checklist

- [ ] Identified which data needs SSE-S3, SSE-KMS, DSSE-KMS, or client-side encryption based on real requirements.
- [ ] Verified **bucket Region, bucket type**, and matching KMS key ARN/Region.
- [ ] If using SSE-KMS: documented choice of AWS managed vs. customer managed key, especially for cross-account use.
- [ ] Bucket default encryption configured properly; team understands it **does not convert old objects**.
- [ ] Actual EC2/ECS/Lambda/CI principal verified; no long-lived static credentials used to bypass KMS controls.
- [ ] Identity policies, bucket policies, key policies/grants, SCPs/boundaries/session/endpoint policies reviewed together.
- [ ] Uploads have `kms:GenerateDataKey` and reads have `kms:Decrypt` per workflow; multipart/copy/replication permissions verified separately.
- [ ] Any `kms:ViaService` or encryption context conditions verified for Region, bucket/object ARN, and Bucket Key interaction.
- [ ] If enforcing SSE-KMS headers, all clients send headers compatible with the bucket policy.
- [ ] HTTPS/TLS, Block Public Access, and S3 access restrictions in place; encryption is not mistaken for authorization.
- [ ] Safe KMS key lifecycle/rotation/disable/delete plan and recovery procedures established if a key becomes unusable.
- [ ] Versioning/backups/replication and **restore tests** meet data RTO/RPO targets.
- [ ] CloudTrail S3/KMS, CloudWatch alarms, log retention, and config/key-change auditing configured.
- [ ] Estimated storage, requests, KMS keys/requests, Bucket Keys, copy/replication, and logging costs per Region.
- [ ] Verified successful upload/download and confirmed an **out-of-scope request is Denied** in a lab environment.

## 18. Scenario Exercises

### Scenario A — Lambda Can Upload but Cannot Read

A Lambda function using `InvoiceWorkerRole` has `s3:PutObject`, `s3:GetObject`, and `kms:GenerateDataKey`. The bucket defaults to SSE-KMS with a customer managed key. Uploads succeed, yet reading the object back returns `AccessDenied`.

**Tasks:**

1. Identify which KMS permission may be missing.
2. Explain why `GetObject` and `PutObject` invoke different KMS actions.
3. Cross-check the key policy, IAM policy, Region, active role, and CloudTrail.
4. Propose the minimal fix, retest, and verify that deleting objects remains denied.

**Hint:** `kms:Decrypt` is typically needed when reading SSE-KMS objects; also check for explicit Denies and key policy restrictions.

### Scenario B — Sharing Report Data with Another Account

Account A has a bucket encrypted with the AWS managed key `aws/s3`; Account B was granted `s3:GetObject` in the bucket policy, yet still cannot decrypt objects.

**Task:** Propose a migration path using a customer managed KMS key in the same Region, configuring both accounts, re-encrypting legacy objects, and verifying via CloudTrail.

**Hint:** Cross-account KMS requires authorization from both the key owner and the caller account, whereas the key policy of an AWS managed key cannot be customized like a customer managed key.

### Scenario C — Requests Start Failing After Enabling Bucket Keys

An IAM/KMS policy previously included the condition:

~~~json
{
  "StringLike": {
    "kms:EncryptionContext:aws:s3:arn": "arn:aws:s3:::invoice-data-demo/invoices/*"
  }
}
~~~

After enabling S3 Bucket Keys, some SSE-KMS operations fail.

**Tasks:** Explain the difference between object ARN and bucket ARN in encryption context; propose how to adjust the condition and enforce prefix isolation via S3 IAM/bucket policies; design before/after verification tests.

**Hint:** Bucket Keys can pass the bucket ARN in encryption context; object-prefix authorization should be enforced in S3 policies rather than relying solely on KMS context conditions.

### Scenario D — Cost Estimation for 50 Million Objects

An application stores tens of millions of small objects with heavy `GetObject` traffic and mandates a customer managed KMS key.

**Tasks:** Build a table of input variables to measure: storage, uploads, downloads, multipart uploads, KMS requests, key count, replication, CloudTrail/logs, and Region; compare with Bucket Keys enabled vs. disabled, and describe how to confirm KMS permissions remain intact.

**Hint:** Never assume a 1:1 ratio of S3 requests to KMS requests without measuring; Bucket Keys dramatically reduce KMS request frequency under supported conditions.

## 19. Conclusion

**S3 encrypts new objects server-side by default using SSE-S3**. When systems require independent key-usage permissions, KMS governance, and secure cross-account sharing, **SSE-KMS with a customer managed key** is usually worth evaluating; **DSSE-KMS** addresses specialized dual-layer encryption mandates. Access outcomes depend simultaneously on **S3 permissions, AWS KMS permissions, key state, request conditions, and Deny layers**.

A reliable design workflow is: **define requirements → select encryption mode/key → configure bucket/role/key policies → test upload and download → monitor, back up, recover → optimize costs**. Within the AWS ecosystem, IAM, VPC, Region/AZ, Lambda/ECS/EC2, S3, CloudWatch, and AWS Budgets must be evaluated together so applications remain **secure, observable, recoverable, and within budget**.

### Official AWS Documentation for Deployment Reference

- [Protecting data with server-side encryption — Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/serv-side-encryption.html)
- [Using SSE-KMS encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html)
- [S3 Bucket Keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html)
- [Using server-side encryption with dual-layer encryption keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/dual-layer-server-side-encryption.html)
- [Setting default server-side encryption behavior for S3 buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html)
- [Replicating objects created with server-side encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-config-for-kms-objects.html)
- [AWS KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [AWS KMS cross-account access](https://docs.aws.amazon.com/kms/latest/developerguide/key-policy-modifying-external-accounts.html)
- [AWS KMS encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
- [AWS KMS permissions](https://docs.aws.amazon.com/kms/latest/developerguide/kms-api-permissions-reference.html)
- [AWS CLI S3 API command reference](https://docs.aws.amazon.com/cli/latest/reference/s3api/)
- [AWS KMS pricing](https://aws.amazon.com/kms/pricing/) and [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)

API permissions, pricing, encryption modes, and feature support can vary by Region, bucket type, and over time. Always verify the latest documentation and active policies before deploying to production.
