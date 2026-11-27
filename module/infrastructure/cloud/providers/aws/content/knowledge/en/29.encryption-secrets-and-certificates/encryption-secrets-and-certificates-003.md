# AWS Managed Keys, Customer Managed Keys, and Selection Strategy

In AWS, data encryption is typically implemented through AWS Key Management Service (AWS KMS). When a service such as Amazon EBS, Amazon RDS, Amazon S3, or AWS Secrets Manager needs to encrypt data, KMS can provide keys for the service to protect that data. An important design question is whether to use an **AWS managed key** managed by AWS or a **customer managed key** created and controlled by your organization.

This choice affects access permissions, auditability, key rotation, cross-account data sharing, cost, and operational responsibility. No single key type fits every workload. You should start from security requirements and how the AWS service integrates with KMS, then choose just enough control.

## Learning Objectives

After this lesson, you can:

- Distinguish between AWS owned keys, AWS managed keys, and customer managed keys.
- Explain who creates, who manages, and who can change the policy for each key type.
- Evaluate the impact of key type on rotation, access control, cross-account sharing, auditing, and cost.
- Select the appropriate key type for an AWS workload and establish a key lifecycle management process.

## 1. AWS KMS and the Role of Encryption Keys

AWS KMS is an encryption key management service. KMS controls the use of key material and provides cryptographic operations via APIs. For most AWS services, applications do not need to manage key material themselves: the service integrates with KMS to encrypt or decrypt data according to granted permissions.

A KMS key is a logical resource within an AWS account and Region. A key has metadata, a key policy, a state, a configuration, and corresponding key material. Key material is the component that performs cryptographic operations; for keys created and managed by KMS, the key material is protected inside the KMS system and is never returned to applications in plaintext.

When data exceeds the size limit for direct KMS encryption operations, systems typically use **envelope encryption**:

1. KMS generates a data key (DEK), returning a plaintext DEK and a copy of the DEK encrypted under the KMS key.
2. The application or service uses the plaintext DEK to encrypt data where it is processed.
3. The application stores the ciphertext together with the encrypted DEK; after encryption, the plaintext DEK is removed from memory when no longer needed.
4. When decryption is needed, the application sends the encrypted DEK to KMS to retrieve the plaintext DEK, then uses that DEK to decrypt the data.

In this way, KMS protects the data encryption key without having to receive large data payloads. AWS services typically abstract most of the envelope encryption workflow away from the user.

## 2. Three Key Types to Distinguish

AWS KMS has three common key categories. Among them, AWS managed keys and customer managed keys are the two primary options when designing how a workload uses KMS in your account.

### AWS Owned Keys

AWS owned keys are owned and managed by AWS. They do not reside in the customer's AWS account, so customers cannot view them in their KMS key list, modify their key policies, attach tags, configure rotation, or control the lifecycle of individual keys.

Some AWS services use AWS owned keys to protect data. The service is responsible for selecting and operating the key. Users typically only configure encryption at the service level, if the service offers that option.

### AWS Managed Keys

An AWS managed key is a KMS key located in the customer's AWS account that is created and managed by an AWS service on the customer's behalf. For example, Amazon EBS may use a key with the alias `aws/ebs`; Amazon S3 may use `aws/s3` when configuring SSE-KMS with an AWS managed key.

You can view metadata, key IDs, aliases, key policies, and key usage events in supported AWS tools. However, AWS manages the key policy and key material. Customers cannot edit the key policy, create or revoke grants at will, change the rotation schedule, disable the key, or schedule key deletion. An AWS managed key is usually created automatically the first time you select the corresponding service encryption option.

AWS managed keys follow the alias format `aws/<service>`. The key is scoped to an account and Region. Customers use the key through the AWS service that created it; it should not be treated as a general-purpose shared key for applications to call cryptographic operations on directly.

AWS manages rotation for AWS managed keys. Eligible symmetric keys are automatically rotated on a schedule set by AWS, typically annually; customers cannot set a custom period or trigger rotation on their own schedule. Rotating key material does not change the key ID and does not require users to re-encrypt data already protected by the key.

### Customer Managed Keys

A customer managed key (CMK) is a KMS key that the customer creates and manages in their AWS account. The customer controls the key policy, can use IAM policies to delegate permissions when the key policy allows it, creates grants, attaches tags, sets aliases, enables or disables the key, configures rotation, and schedules key deletion.

A customer managed key is appropriate when an organization needs clear control over who can use the key, which services can use it, which accounts can access it, or needs audit evidence per data boundary. A CMK can be used by KMS-integrated AWS services or by applications calling KMS APIs directly, depending on the key type and granted permissions.

Customer managed keys support more configurations than AWS managed keys, such as symmetric keys, asymmetric keys, HMAC keys, KMS-generated key material, or imported key material in supported cases. Customer managed keys also support multi-Region keys if a workload needs the same logical key material across multiple Regions.

## 3. Comparing AWS Managed Keys and Customer Managed Keys

| Criterion | AWS managed key | Customer managed key |
|---|---|---|
| Who creates it | Created by an AWS service when needed | Created by the customer (some flows assist creation in services) |
| Who manages key material | AWS | AWS KMS protects key material; customer controls configuration and usage permissions |
| Key policy | Managed by AWS; customer cannot edit | Controlled by the customer |
| IAM policies and grants | Cannot be customized by the customer | Can be used per key policy and KMS authorization model |
| Rotation | Managed by AWS; customer cannot customize schedule | Can enable automatic rotation for eligible key types or manage manual replacement workflows |
| Disable or schedule deletion | Customer cannot | Customer can; impact must be assessed before executing |
| Tags and custom aliases | Not managed like a CMK; alias set by service | Supports customer-managed tags and aliases |
| Cross-account access | Not an option for sharing key usage cross-account | Can be configured cross-account if supported by the service and use case |
| Multi-Region | No | Can create multi-Region customer managed keys |
| Operational effort | Low | Higher because the customer is responsible for policies, lifecycle, and monitoring |
| Cost | No monthly key storage fee | Monthly key fee and request charges per applicable KMS pricing |

Details may vary by key type, Region, and integrated service. Always verify the documentation for the service you are using before assuming it supports every KMS feature.

## 4. Access Control: Key Policies, IAM Policies, and Grants

KMS uses a **key policy** as the core access control mechanism for each KMS key. The key policy determines which principals are allowed to perform operations on the key. An IAM policy can grant permissions to principals in the account when the key policy enables that delegation mechanism. Therefore, merely attaching an IAM policy to a role may not be enough for the role to use a KMS key.

For a customer managed key, clearly define the permission groups:

- **Key administrators**: manage key configuration and policies. Administrative permissions do not necessarily include permission to use the key to decrypt data.
- **Key users**: perform required cryptographic operations such as `Encrypt`, `Decrypt`, or `GenerateDataKey`.
- **AWS services**: granted permissions in the integration mode supported by the service, typically via key policy or grants.
- **Auditors**: view key configuration and usage events without needing permission to decrypt data.

Grants provide a flexible delegation mechanism for certain cases, especially when an AWS service needs permission to use a key on a resource's behalf. Grants do not replace proper key policy design. When revoking a grant or modifying a policy, evaluate which workloads depend on that permission.

With an AWS managed key, AWS retains control of the key policy. If a workload needs a custom policy, cross-account permissions, or access conditions based on principal and encryption context, check whether the service supports a customer managed key.

### Encryption Context

Encryption context is a set of non-secret key-value pairs sent with certain KMS symmetric encryption operations. KMS uses the context as additional authenticated data (AAD); the context is not encrypted and must be supplied identically during decryption. Organizations can use encryption context in policy conditions to restrict key usage to a specific resource type or purpose.

For example, an application can send the context `{"App":"orders","Environment":"prod"}` when calling KMS operations. Do not put passwords, tokens, personal data, or secrets in encryption context because these values are not designed to be confidential and may appear in audit logs.

## 5. Rotation and Key Lifecycle

Rotation changes the key material used for new encryption operations within the same KMS key. When rotation is supported by KMS, KMS retains older versions of key material so ciphertext created earlier can still be decrypted. The key ID and alias remain unchanged. Applications continue referencing the same KMS key, so you normally do not need to re-encrypt all existing data solely because automatic rotation occurred.

For customer managed keys, automatic rotation is supported for symmetric encryption keys with AWS KMS-generated key material. You can configure a rotation period from 90 to 2,560 days; the common default period is 365 days. Asymmetric keys, HMAC keys, keys with imported key material, and certain custom key stores do not support automatic rotation via the same mechanism. Those cases require dedicated key material management procedures.

Distinguish between these two actions:

- **Rotate key material**: KMS keeps the same KMS key and manages key material versions to decrypt older data.
- **Replace a KMS key with another key**: create a new key resource, update workloads, and perform re-encryption or re-wrapping of data as needed. This is an architectural change and requires a migration plan.

For customer managed keys, lifecycle states and actions directly affect data accessibility:

- **Disable**: cryptographic operations using the key are blocked until the key is re-enabled. Services depending on the key may stop being able to read or write data.
- **Schedule deletion**: KMS sets a waiting period before permanent deletion, between 7 and 30 days. During the waiting period, deletion can be canceled. After deletion completes, data can only be decrypted if another valid key copy remains.
- **Policy or grant changes**: workloads can lose permission to call KMS even though the ciphertext remains intact.

Before disabling or deleting a key, identify which resources, snapshots, backups, logs, secrets, and stored data depend on that key. Testing data restoration from backups is part of key management operations.

## 6. Cross-Account and Multi-Region

If data is encrypted with a customer managed key and needs to be used by another AWS account, cross-account access can be configured. Both sides are typically required: the key policy in the key-owning account allows the external principal, and the IAM policy in the external account allows the principal to call KMS operations. The storage or consuming service must also support that sharing model.

AWS managed keys are not suitable for cross-account use cases because customers do not control their key policies. When sharing EBS snapshots, data copies, resources, or workloads across accounts, confirm the service requirements and consider a customer managed key.

A standard KMS key is tied to a single Region. If an application needs to process ciphertext across multiple Regions, a customer managed multi-Region key enables related keys with the same key material and key ID. Each primary or replica key still has its own Region-scoped policy, grants, aliases, and management state. Not every AWS service supports multi-Region keys; verify before choosing this architecture.

## 7. Cost and Operational Responsibility

AWS managed keys reduce administrative overhead and have no monthly key storage fee. Customer managed keys incur a monthly key fee; KMS requests and related features may incur charges depending on pricing, key type, and Region. Services using KMS may also have separate charges.

When evaluating cost, do not count only the number of keys. Consider the number of encrypt/decrypt requests, frequency of data key generation, number of Regions, number of accounts, audit requirements, and operational effort. Splitting keys per small resource can increase cost and complexity. Sharing one key across too many applications increases blast radius if a policy or key is misconfigured.

## 8. Selection Strategy

Answer the following questions before choosing a key type:

1. Does the AWS service support AWS managed keys, customer managed keys, or both for the feature being used?
2. Are there requirements to control the key policy, usage permissions, or custom encryption context?
3. Does data need to be shared across AWS accounts or processed in multiple Regions?
4. Are there requirements for auditing, separation of duties, cost-allocation tags, or key lifecycle evidence?
5. Does the organization have processes and owners responsible for rotation, policies, alerts, backups, and deletion?

### When to Choose an AWS Managed Key

Choose an AWS managed key when the service supports it and these conditions fit:

- The service's default encryption already meets security and compliance requirements.
- You do not need to edit the key policy or share key usage permissions with other accounts.
- You do not need a custom rotation schedule, administrative tags, or permission to disable/delete the key.
- You want to minimize key-related decisions and operational overhead.

Example: a development environment using EBS encryption with `aws/ebs`, or a simple workload using the AWS managed key option provided by a service. This is a reasonable choice when internal requirements do not demand extra control.

### When to Choose a Customer Managed Key

Choose a customer managed key when one or more of the following requirements apply:

- You need to control which principals and services are allowed to use the key.
- You need cross-account permissions or custom security boundaries.
- You need rotation on an organizational schedule, tags, aliases, or custom lifecycle processes.
- You need to separate key administration permissions from application operational permissions.
- You need detailed auditing and proof of key access per workload or data group.
- You need a multi-Region key in an architecture supported by the service.

Example: a production payment system requires a key policy restricting decryption to specific roles; the security team administers the key while the application team can only call required operations; data is shared cross-account under an approved process. A customer managed key establishes the appropriate control boundary here.

### Quick Decision Matrix

| Need | Typically suitable choice | Reason |
|---|---|---|
| Simple encryption using built-in service configuration | AWS managed key | Low ops overhead; AWS manages policy and rotation |
| Custom access permission policy | Customer managed key | Customer controls key policy and grants |
| Using a key for workloads in another account | Customer managed key | Can configure cross-account access when supported by the service |
| Separating keys by application or data classification | Customer managed key | Manage permissions, tags, and audits per boundary |
| No additional control requirements | AWS managed key | Avoids unnecessary complexity |
| Multi-Region key required | Customer managed key | Supports primary and replica keys across Regions |

This matrix is a starting point. AWS service documentation and internal control requirements remain the final basis for decision-making.

## 9. Example: Creating and Configuring a Customer Managed Key

The following example creates a symmetric KMS key to protect production order application data. The commands only create the key and alias; before placing it into a real workload, review the key policy, IAM policies, service permissions, and operational procedures.

```bash
# Create a symmetric customer managed key with KMS-generated key material.
aws kms create-key \
  --description "KMS key for orders production" \
  --key-spec SYMMETRIC_DEFAULT \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS

# Replace <key-id> with the KeyId from the create-key output.
aws kms create-alias \
  --alias-name alias/orders-prod \
  --target-key-id <key-id>

# Enable automatic rotation for an eligible key.
aws kms enable-key-rotation --key-id <key-id>

# Check rotation status.
aws kms get-key-rotation-status --key-id <key-id>
```

In production, avoid hardcoding key IDs or ARNs in many places if an appropriate alias can be referenced. Manage permissions with least privilege; separate key administration from key usage; record owner, purpose, environment, and review date in tags or an asset management system. Grant `Decrypt` only to principals that genuinely need to decrypt.

## 10. Practical Scenarios

### Scenario A: Encrypting Volumes for a Development Environment

A development team creates EC2 instances and enables EBS encryption. They have no cross-account snapshot sharing requirements, need no custom key policy, and want minimal operational overhead. If organizational policy permits, the AWS managed key `aws/ebs` is an appropriate choice. The team still needs to check account and Region default encryption settings.

### Scenario B: Production Data Requiring Custom Access Control

An application stores order information in a service supporting SSE-KMS. The security team needs to control which roles can decrypt data and wants to inspect key usage along application boundaries. A customer managed key allows defining a suitable key policy, tags, and auditing workflow. Operations must monitor policies, rotation, and key state to prevent disruptions.

### Scenario C: Sharing Snapshots Between Two Accounts

A source account creates a snapshot encrypted with a customer managed key. A destination account needs to copy the snapshot and create a volume from the copy. The team must configure key permissions in the source account, IAM permissions in the destination account, and follow EBS snapshot sharing requirements. If the snapshot used an AWS managed key, the customer cannot edit its key policy for cross-account sharing this way; it must be redesigned using a customer managed key and an appropriate copy workflow.

### Scenario D: Application Running Across Multiple Regions

An application needs to read ciphertext in two Regions for a disaster recovery scenario. If the service and application workflow support it, a multi-Region customer managed key can reduce key material synchronization effort. The team must still manage policies, grants, aliases, and key state in each Region, and test failover and recovery procedures.

## 11. Common Design Mistakes

- **Choosing a customer managed key for every resource without a clear requirement**: increases key count, cost, and operational work. Define the needed security boundary before splitting keys.
- **Assuming an IAM policy is always enough for KMS access**: the key policy remains the core control mechanism. Check both key policy and IAM policy when troubleshooting `AccessDenied`.
- **Using an AWS managed key for cross-account use cases**: customers do not control its key policy. Choose a customer managed key if the service requires key sharing permissions.
- **Disabling or scheduling deletion without checking dependencies**: this can break an application's ability to decrypt. Check snapshots, backups, logs, secrets, and stored data before making changes.
- **Confusing rotation with key replacement**: rotation preserves the KMS key and key material versions needed for decryption; replacing a KMS key is a separate migration project.
- **Putting secret data in encryption context**: encryption context is not a secret store. Use only non-sensitive identifying values.
- **Assuming every service supports every KMS feature**: verify service documentation regarding key types, cross-account access, multi-Region support, and permission models before deploying.

## 12. Customer Managed Key Operations Checklist

Before promoting a key to production, confirm:

- [ ] An accountable owner and intended purpose are documented.
- [ ] Key policy and IAM policies follow the principle of least privilege.
- [ ] Administrative, usage, and audit permissions are properly separated.
- [ ] AWS services are granted permissions according to official integration guidance.
- [ ] Rotation is configured if supported by the key type; otherwise, a manual key material replacement or key migration procedure exists.
- [ ] CloudTrail and required alerts are configured to monitor key administration and usage activity.
- [ ] Incident procedures exist for disabled keys, policy changes, or revoked grants.
- [ ] A dependency review procedure is in place before scheduling deletion.
- [ ] Data and backup restoration have been tested in an appropriate environment.
- [ ] Cross-account and multi-Region workflows have been tested if used by the workload.

## Conclusion

AWS managed keys are suitable when service-provided encryption meets requirements and the organization wants to reduce key administration work. Customer managed keys are suitable when you need control over policies, usage permissions, cross-account sharing, rotation, tags, auditing, or lifecycle. AWS owned keys are fully managed by AWS in certain services and provide no direct customer control.

Choose keys based on data and workload requirements, verify AWS service support, and design permissions and key lifecycles alongside operational procedures. A well-managed key must remain available for legitimate workloads while allowing only the right principals to perform the right operations.

## References

- [AWS KMS concepts](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html)
- [AWS managed keys](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html#aws-managed-key)
- [Customer managed keys](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html#customer-mgn-key)
- [Rotating AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)
- [Key policies in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Grants in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/grants.html)
- [Multi-Region keys](https://docs.aws.amazon.com/kms/latest/developerguide/multi-region-keys-overview.html)
- [Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
- [AWS Key Management Service pricing](https://aws.amazon.com/kms/pricing/)
