# KMS Grants, Encryption Context, and Cross-Account Access

AWS Key Management Service (AWS KMS) controls key usage using key policies, IAM policies, and grants. When an application needs temporary permissions, needs to bind decryption operations to data context, or needs to use a key owned by another AWS account, designers must coordinate these mechanisms properly. A configuration missing permission on one side typically results in `AccessDeniedException`; an overly broad configuration can allow principals to use the key beyond its intended scope.

After this lesson, learners can:

- Explain grants, grantees, grant tokens, retiring principals, and how to terminate grants.
- Use encryption context to bind encrypted data to business context and restrict permissions.
- Design KMS key access across two AWS accounts using key policies and IAM policies.
- Inspect, troubleshoot permission errors, and manage access lifecycles according to the principle of least privilege.

## 1. The Permission Control Model in AWS KMS

Every KMS key always has a **key policy**. This is a resource-based policy attached directly to the key and is the foundation for determining who can use the key and which operations they can call. No principal automatically has access to a key, including the key creator or the root user of the key-owning account.

Three mechanisms commonly work together:

| Mechanism | Role | When to use |
|---|---|---|
| Key policy | Defines permissions on the KMS key side; can specify principals directly or allow the account to use IAM policies to delegate | Foundational permissions, key administration, cross-account key sharing |
| IAM policy | Attached to a user or role to allow or deny a principal from performing operations | Managing permissions by role group, application, or workload |
| Grant | Grants a specific set of operations to a grantee on a single key; can be created and terminated via API | Temporary permissions, permissions for KMS-integrated AWS services, permissions tied to resource lifecycles |

An `Allow` in an IAM policy does not by itself grant permission to use a KMS key if the key policy has not enabled the account to use IAM policies or granted appropriate permissions to the principal. Similarly, a grant cannot override an effective `Deny`. AWS KMS evaluates the policies and grants applicable to the request; the request succeeds only when an appropriate allowance exists and no denial applies.

Key policies are Region-scoped: a key's policy controls only that key in the Region where it resides. Therefore, when debugging errors, confirm the exact key ARN, account, and Region before analyzing statements.

## 2. KMS Grants: Narrowly Scoped Delegation

### 2.1. What Is a Grant?

A grant is a mechanism that gives a principal or an AWS service principal permission to perform a set of supported operations on a single KMS key. Each grant has one grantee and allows only the listed operations. Grants cannot deny permissions.

A grant typically includes the following components:

- `KeyId`: the key to which the grant applies.
- `GranteePrincipal` or `GranteeServicePrincipal`: the principal receiving permissions. Choose only one of these two fields.
- `Operations`: the allowed operations, such as `Decrypt`, `Encrypt`, `GenerateDataKey`, or `DescribeKey`.
- `Constraints`: conditions restricting the grant, such as encryption context or `SourceArn`.
- `RetiringPrincipal` or `RetiringServicePrincipal`: the principal designated to terminate the grant when permissions are no longer needed.
- `GrantId` and `GrantToken`: values returned by AWS KMS when creating the grant, used for grant management and immediate usage.

A grantee principal can be an IAM user, IAM role, assumed-role user, or account principal. The grantee may belong to the key-owning account or another account. IAM groups and AWS Organizations are not valid grantee principals. When granting permissions to workloads, prefer IAM roles with temporary credentials over IAM users with long-lived access keys. When using `GranteeServicePrincipal`, the grant creation request must include the `SourceArn` grant constraint and must specify `RetiringPrincipal` or `RetiringServicePrincipal`.

A grant accepts only grant operations supported by the key type. For example, a grant for a symmetric encryption key can allow `Encrypt`, `Decrypt`, and `GenerateDataKey`; operations like `Sign` or `Verify` do not apply to this key type. Requesting an operation unsupported by the key causes `CreateGrant` to fail.

### 2.2. Creating a Grant with an Encryption Context Constraint

Suppose role `InvoiceWorker` needs to decrypt invoice data using a symmetric KMS key. We only want this role to decrypt ciphertext carrying the encryption context `Application=Billing`. An administrator can create the grant as follows:

```bash
aws kms create-grant \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --grantee-principal arn:aws:iam::111122223333:role/InvoiceWorker \
  --operations Decrypt \
  --retiring-principal arn:aws:iam::111122223333:role/SecurityAdmin \
  --constraints EncryptionContextSubset={Application=Billing}
```

In this example:

- `InvoiceWorker` receives only `Decrypt` permission on the specified key.
- `EncryptionContextSubset` requires the decryption request to include the pair `Application=Billing`; the request may also include additional context pairs.
- `SecurityAdmin` can retire the grant when the job completes.
- The principal running the command must have `kms:CreateGrant` permission on the key.

The `CreateGrant` response returns `GrantId` and `GrantToken`. Store `GrantId` to look up or revoke the grant later. If the application needs to use the grant immediately after creation, pass `GrantToken` in the corresponding KMS request while the grant is still propagating.

Example calling decrypt with a grant token:

```bash
aws kms decrypt \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --ciphertext-blob fileb://ciphertext.bin \
  --encryption-context Application=Billing \
  --grant-tokens "$GRANT_TOKEN"
```

Here, `$GRANT_TOKEN` is the token saved from the `CreateGrant` response. You do not need to pass the token forever: once the grant has propagated across AWS KMS, the grantee can use the grant's permissions without passing the token.

### 2.3. Grant Tokens and Eventual Consistency

AWS KMS uses an eventual consistency model. After creating, retiring, or revoking a grant, the change can take a short period to take effect system-wide—usually a few seconds, though occasionally up to a few minutes. If a grantee calls KMS immediately after `CreateGrant`, the request may receive `AccessDeniedException` even though the grant was created successfully.

A grant token allows a request to reference a newly created grant immediately. The token is an opaque identifier that does not expose the grant's contents. Only the `CreateGrant` operation returns a grant token; `ListGrants` returns the grant ID, not the token. Applications should capture the token from the creation response if they need to use the permission immediately in the same workflow.

Do not resolve propagation errors by hastily widening policies. First check the `CreateGrant` response, key ARN, grantee, operations, constraints, and whether the request passed the grant token.

### 2.4. Terminating Grants: Retire and Revoke

Both retiring and revoking delete the grant, so permissions derived solely from that grant cease to apply once the change propagates.

- **Retire** is typically performed by the retiring principal designated in the grant—usually the workload or principal assigned responsibility for ending access.
- **Revoke** is typically performed by a key administrator or principal with grant administration permissions when access must be terminated from the key owner's side.

You can use `ListGrants` to find the grant ID before managing a grant. Example:

```bash
aws kms list-grants \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555

aws kms retire-grant \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --grant-id GRANT_ID
```

Retire or revoke only after verifying the exact key and grant. If a grant was created for an AWS service, follow that service's resource lifecycle and documentation; deleting a grant actively used by a service can cause operations on that resource to fail.

The `kms:CreateGrant` permission carries high security impact: a principal allowed to create grants can further delegate key access to other principals, including AWS services. Restrict who can create grants, which operations can be granted, and grant constraints. When granting permissions to AWS services, policies commonly constrain `kms:CreateGrant` with conditions such as `kms:GrantIsForAWSResource`; exact requirements depend on the integrated service.

## 3. Encryption Context: Binding Ciphertext to Data Context

### 3.1. How Does Encryption Context Work?

Encryption context is a set of string key-value pairs that an application passes into AWS KMS cryptographic operations when using a **symmetric encryption KMS key**. KMS uses the context as additional authenticated data (AAD): the context is cryptographically bound to the ciphertext, verifying that data is decrypted in the same context used during encryption.

For example, when encrypting invoice data, an application can pass:

```json
{
  "Application": "Billing",
  "Environment": "Production",
  "RecordType": "Invoice"
}
```

When decrypting, the application must pass the exact same set of key-value pairs. Values must match exactly and are case-sensitive; the order of pairs in the context does not matter. If a pair is missing, a value changes, or capitalization differs, decryption fails.

Keep three properties of encryption context in mind:

1. **Not secret.** The context is not encrypted and can appear in plaintext in AWS CloudTrail logs. Never put passwords, access tokens, card numbers, personal data, or sensitive data into the context.
2. **Integrity-bound.** The context is bound to the ciphertext as AAD. Ciphertext created for `Application=Billing` will not decrypt successfully if the request passes `Application=Analytics`.
3. **Usable for authorization.** Key policies, IAM policies, and grants can enforce conditions based on encryption context to restrict operations to a specific data type or application.

Encryption context is not supported in cryptographic operations with asymmetric KMS keys or HMAC KMS keys. Do not pass context for those key types.

### 3.2. Encrypting and Decrypting with Context

The following example generates a data key for an invoice processing application. AWS KMS returns a plaintext data key and an encrypted copy of the data key; the application uses the plaintext data key to encrypt data in memory and then discards the plaintext key according to its key management lifecycle.

```bash
aws kms generate-data-key \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --key-spec AES_256 \
  --encryption-context Application=Billing,RecordType=Invoice
```

When decrypting the encrypted data key, the application must supply the same context:

```bash
aws kms decrypt \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555 \
  --ciphertext-blob fileb://encrypted-data-key.bin \
  --encryption-context Application=Billing,RecordType=Invoice
```

For data encrypted with envelope encryption, store or reconstruct the context using a stable convention alongside the ciphertext metadata. If an application changes field names or context values between versions, older data may become undecryptable. Therefore, version the context schema and test data recovery procedures before deploying changes.

### 3.3. Encryption Context Constraints in Grants

Grants support two types of encryption context constraints. Both apply only to symmetric encryption KMS keys:

| Constraint | Rule | Use case |
|---|---|---|
| `EncryptionContextEquals` | Request must contain the exact declared set of key-value pairs; case-sensitive matching | Allow operations only with a fixed context |
| `EncryptionContextSubset` | Request must contain every declared pair; additional pairs may be present | Require a business label while permitting extra metadata |

For example, `EncryptionContextEquals={Application=Billing,Environment=Production}` accepts only a context with those exact two pairs. If a request adds `RecordType=Invoice`, this grant does not match. With `EncryptionContextSubset={Application=Billing}`, both a context with only `Application=Billing` and a context with an extra `Environment=Production` pair are accepted.

Context constraints are ignored for operations that do not accept an encryption context, such as `DescribeKey` and `RetireGrant`. If a grant allows `CreateGrant`, any subsequent grant created must have encryption context constraints that are equally strict or stricter so delegated permissions cannot be widened.

### 3.4. Context Constraints in Policies

You can use the `kms:EncryptionContext:context-key` condition key in key policies or IAM policies to require a specific context pair. The statement below allows the role to decrypt only when the request includes `Application=Billing`:

```json
{
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111122223333:role/InvoiceWorker"
  },
  "Action": "kms:Decrypt",
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:EncryptionContext:Application": "Billing"
    }
  }
}
```

This condition requires the `Application=Billing` pair, while still allowing requests with additional context pairs. If you need to control the full set of allowed keys, you can combine `kms:EncryptionContextKeys` with appropriate conditions. `kms:EncryptionContextKeys` is a multivalued condition key; `kms:EncryptionContext:context-key` is a single-valued condition key. Do not use `ForAllValues` or `ForAnyValue` with the single-valued `kms:EncryptionContext:context-key` condition key, as that can create policies that unexpectedly allow requests missing context.

Distinguish matching during decryption from matching in policies. Context passed to a decryption operation must always match the original context exactly and case-sensitively. In policies, condition key names are case-insensitive; value case sensitivity depends on the condition operator—for example, `StringEquals` is case-sensitive.

## 4. Granting Cross-Account KMS Key Access

### 4.1. Both Sides Must Allow Access

Suppose account `111122223333` owns a KMS key in Region `ap-southeast-1`, while account `444455556666` runs an application that needs to encrypt and decrypt data using that key.

With key policy sharing, cross-account access requires two parts:

1. **The key policy in the key-owning account** allows the external account or specific role to use the key with selected operations.
2. **An IAM policy in the calling account** attached to the user or role allows that principal to call the operations on the owning account's key ARN.

The key policy defines the scope of permissions the external account can receive. The IAM policy in the external account determines which users or roles actually get those permissions. Updating only one side is not sufficient.

For customer managed keys, the owning account can also share keys via AWS Resource Access Manager (AWS RAM). AWS RAM creates and manages an additional key policy named `AWS_RAM`; the receiving account still needs an IAM policy for principals using the key and can only perform operations included in the shared permissions.

When `Principal` in a key policy is `arn:aws:iam::444455556666:root`, this is the **account principal** representing account `444455556666`, not solely the root user. This statement allows IAM administrators of that account to use IAM policies to further delegate permissions within the operations permitted by the key policy.

### 4.2. Example Key Policy in the Key-Owning Account

Add the following statement to the key policy of the key belonging to account `111122223333`:

```json
{
  "Sid": "AllowBillingAccountUseOfKey",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:root"
  },
  "Action": [
    "kms:Encrypt",
    "kms:Decrypt",
    "kms:ReEncrypt*",
    "kms:GenerateDataKey*",
    "kms:DescribeKey"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "kms:EncryptionContext:Application": "Billing"
    }
  }
}
```

This statement allows account `444455556666` to use the listed operations when the request includes `Application=Billing`. `Resource` in the key policy is `*` because the policy is already attached to a specific key. This example illustrates a symmetric encryption key; select operations based on key type and actual requirements.

If you want to grant access to only one external role, you can put that role's ARN in `Principal` instead of the account principal. This narrows delegation scope more tightly, but when adding or replacing roles, you must update the key policy in the key-owning account.

### 4.3. Example IAM Policy in the Key-Using Account

Attach the following IAM policy to the application role in account `444455556666`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UseBillingKeyInOwnerAccount",
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555"
    }
  ]
}
```

The IAM policy uses the full key ARN to target the exact key in the owning account and Region. The application role must still send an encryption context satisfying the condition in the key policy. Allowing `kms:Decrypt` in the IAM policy cannot bypass the `Application=Billing` condition in the key policy.

### 4.4. Limits of Cross-Account Permissions

Cross-account permissions on a KMS key apply only to operation groups supported by AWS KMS, including:

- Cryptographic operations such as `Encrypt`, `Decrypt`, `ReEncrypt`, and `GenerateDataKey` appropriate to the key type.
- `CreateGrant`, `DescribeKey`, `GetKeyRotationStatus`, `GetPublicKey`, `ListGrants`, `RetireGrant`, and `RevokeGrant`.

Granting `kms:ListKeys` or `kms:ScheduleKeyDeletion` to a principal in another account does not make those operations valid on the owning account's key. Check the Cross-account use column in the AWS KMS permissions reference before adding operations to policies.

The external account must also have the Region containing the key enabled. When making cross-account calls, use the key ARN to identify the key. If the application uses the KMS key via an AWS service such as Amazon S3 or AWS Secrets Manager, grant additional permissions for the service and principal per that service's encryption documentation. The generic policy examples above do not replace service-specific permission lists.

### 4.5. Using Grants for Principals in Another Account

A grant's grantee can belong to a different account from the key-owning account. This is useful when permissions are time-bounded or change with a workload's lifecycle. However, a grant does not remove the IAM permission requirement in the calling account: the external principal still needs an identity-based policy allowing the operations on the key ARN. The grant must be created by a principal with `kms:CreateGrant`, and the grant should list only the required operations and constraints.

For long-term key sharing, key policy plus IAM policy is usually easier to audit and administer. If using grants, clearly define who creates grants, who the grantee is, who can retire them, which constraints are mandatory, and the revocation process when the workload finishes. Avoid granting broad `kms:CreateGrant` to an application role if that role does not need to delegate further.

## 5. Design and Operations Workflow

You can apply the following workflow when an application needs to use a KMS key:

1. **Identify owner and caller.** Record the account IDs, role ARNs, Region, and key ARN. Confirm which account owns the key and which account sends requests.
2. **Select minimal operations.** An application that only encrypts should not automatically get `Decrypt`; an application that only reads data does not need `ScheduleKeyDeletion` or key administration permissions.
3. **Choose the permission mechanism.** Use key policies and IAM policies for steady-state access; use grants for lifecycle-bound access or service integrations requiring grants.
4. **Design the encryption context.** Choose stable, non-sensitive names and values reflecting purpose or data type. Ensure all encryption and decryption paths use the same convention.
5. **Add conditions and constraints.** Use grant constraints or policy conditions to bind context. For service principals, restrict request sources with `SourceArn` as required by KMS.
6. **Test with real roles.** Test valid requests, requests missing context, requests with wrong context, and requests from unauthorized roles. Verify only valid requests succeed.
7. **Monitor and terminate access.** Use CloudTrail to inspect KMS activity; inspect grants with `ListGrants`; retire or revoke grants when no longer needed. Cross-account key operations may be logged in CloudTrail in both the calling account and the key-owning account.

When granting `kms:CreateGrant` to AWS services, allow only required cases. A common condition pattern is `kms:GrantIsForAWSResource=true`, though you must verify which operations the specific service needs and whether additional conditions are required.

## 6. Common Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| `AccessDeniedException` using key in same account | Key policy does not enable IAM policies or principal; missing IAM `Allow`; explicit `Deny` | Check key policy, IAM policy, permissions boundary, SCP, and applicable conditions |
| `AccessDeniedException` using key from another account | Missing permission in owner's key policy or missing IAM policy on caller side | Verify account principal/role in key policy and IAM policy attached to the right role in calling account |
| Decryption fails despite having `kms:Decrypt` | Encryption context missing, wrong value, or wrong case | Compare context of encryption and decryption calls; check grant constraints and policy conditions |
| Newly created grant is rejected on immediate request | Grant has not propagated yet; request did not pass grant token | Capture token from `CreateGrant` response, pass it in the request, and retest after grant propagation |
| `CreateGrant` returns validation error | Operation unsupported by key or invalid grantee/constraint parameters | Check key type, grant operation list, and `SourceArn`/retiring principal requirements for service principals |
| AWS service cannot use the key | Policy lacks permissions or grants required by the service; missing source conditions | Read the service's encryption guide; verify `kms:CreateGrant`, `kms:GrantIsForAWSResource`, and `SourceArn` if needed |
| External principal can call some APIs but not administrative APIs | API does not support cross-account access | Check the Cross-account use column for the operation in the AWS KMS permissions reference |

Never resolve errors by setting `Principal` to `*`, granting `kms:*`, or removing context conditions. Identify the exact missing permission layer and fix only the relevant statement.

## 7. Scenario Exercise

A company has two accounts:

- Account `111122223333` owns the symmetric KMS key `BillingKey` in `ap-southeast-1`.
- Account `444455556666` runs role `InvoiceWorker` to decrypt invoice data keys.
- Invoice data always uses encryption context `Application=Billing` and `RecordType=Invoice`.
- The security team wants the role to have permission only to decrypt invoice data and wants to be able to terminate access when the workload is decommissioned.

**Task:** Propose how to grant permissions, appropriate constraints, and how to terminate access.

**Solution Guidance:**

1. In the key-owning account, allow account `444455556666` or directly role `InvoiceWorker` to use `kms:Decrypt` on the key. You can add conditions requiring `Application=Billing` and `RecordType=Invoice`.
2. In account `444455556666`, attach an IAM policy to role `InvoiceWorker` with action `kms:Decrypt` and resource set to the full key ARN from account `111122223333`.
3. If time-bounded permissions are desired, create a grant for `InvoiceWorker` with operation `Decrypt`, specify a retiring principal, and use `EncryptionContextEquals` to enforce those exact two context pairs. If the workload has other valid context pairs, consider `EncryptionContextSubset` and evaluate the expanded scope.
4. While a newly created grant has not propagated, pass the `GrantToken` returned from `CreateGrant` in initial decryption requests.
5. When the workload finishes, the retiring principal calls `RetireGrant`; a key administrator can call `RevokeGrant` if access must be terminated administratively. Verify the grant is deleted and retry a request to confirm permissions are no longer active.

**Self-Check Questions:**

1. Why is an IAM policy `Allow kms:Decrypt` in the calling account insufficient on its own to use a key in another account?
2. How does `EncryptionContextEquals` differ from `EncryptionContextSubset`?
3. What problem does a grant token solve, and when can a grantee stop passing the token?
4. Why should customer IDs or personal information not be placed in encryption context?

## 8. References

- [Grants in AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/grants.html)
- [Creating grants and using grant constraints](https://docs.aws.amazon.com/kms/latest/developerguide/create-grant-overview.html)
- [Encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html)
- [AWS KMS condition keys](https://docs.aws.amazon.com/kms/latest/developerguide/conditions-kms.html)
- [Allowing users in other accounts to use a KMS key](https://docs.aws.amazon.com/kms/latest/developerguide/key-policy-modifying-external-accounts.html)
- [Troubleshooting AWS KMS permissions](https://docs.aws.amazon.com/kms/latest/developerguide/policy-evaluation.html)
