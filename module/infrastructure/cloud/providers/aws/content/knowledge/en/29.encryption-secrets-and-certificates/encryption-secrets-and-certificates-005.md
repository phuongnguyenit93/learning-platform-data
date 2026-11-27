# Rotation, Disabling, Scheduled Deletion, and Restoring Key Access

AWS Key Management Service (AWS KMS) manages the keys used to protect data across the AWS ecosystem. A KMS key is a logical resource with an identifier, policy, access permissions, and cryptographic key material. When rotating a key, KMS can replace the key material while keeping the logical resource intact. When disabling or scheduling deletion, KMS changes the resource's state and directly affects the ability to perform cryptographic operations.

In a Java or Spring Boot application, the application typically calls KMS to encrypt or decrypt data keys using envelope encryption. Services such as Amazon S3, Amazon EBS, Amazon RDS, and many other AWS services can also use a KMS key to protect data keys. Therefore, key lifecycle management requires coordinating AWS KMS with IAM, key policies, CloudTrail, CloudWatch, and each service's encryption configuration.

This lesson explains how to choose a rotation method, when to disable or schedule deletion, and how to recover a key after a mistaken operation or interrupted access.

## Learning Objectives

After this lesson, learners can:

- Distinguish between rotating key material and creating a new KMS key.
- Choose automatic rotation, on-demand rotation, or manual rotation based on key type.
- Predict the impact of `Disabled` and `PendingDeletion` states on applications, data, and AWS services.
- Schedule controlled key deletion and recognize special handling required for multi-Region keys.
- Restore key usability by correcting the state or appropriate access permissions.
- Monitor key lifecycle changes using AWS CloudTrail, Amazon EventBridge, and CloudWatch.

## 1. Understanding Key State Before Operating

A KMS key has a state (`KeyState`). The state indicates whether the key can perform cryptographic operations. An operation can be denied due to key state, access permissions, or both.

| State | Meaning | Common remediation |
|---|---|---|
| `Enabled` | The key can perform cryptographic operations if the principal has permission. | Check policies and permissions if operations still fail. |
| `Disabled` | The key still exists but cannot perform cryptographic operations. | Use `EnableKey` after confirming it is safe to re-enable. |
| `PendingDeletion` | The key is in the deletion waiting window and cannot perform cryptographic operations. | Use `CancelKeyDeletion` before the waiting window expires if the key must be kept. |
| `PendingReplicaDeletion` | A multi-Region primary key waiting for its replica keys to be deleted. | Inspect and handle the associated replicas. |
| `PendingImport` | A key with external key material origin currently has no valid material to use. | Re-import key material following the import procedure. |
| `Unavailable` | A key in a custom key store cannot reach its backing key store. | Restore connectivity to the AWS CloudHSM cluster or external key store. |

Most keys are created in the `Enabled` state. Keys using imported key material can remain in `PendingImport` until material is imported. `Creating`, `Updating`, and `PendingReplicaDeletion` are states related to multi-Region keys. Do not treat every KMS error by trying to enable the key: if the state is `PendingImport` or `Unavailable`, the root cause lies in the key material or backing key store.

Distinguish three layers of information:

1. **KMS key:** the logical resource referenced by key ID or key ARN. A key has policies, grants, description, aliases, and configuration.
2. **Key material:** the cryptographic secret performing encryption, decryption, signing, or verification. Rotation can replace key material without creating a new logical resource.
3. **Data keys and application data:** data keys typically encrypt actual data; KMS keys typically protect data keys. Rotating a KMS key does not automatically rotate data keys or re-encrypt existing data.

Understanding these three layers prevents confusion between rotation, disabling, and deletion.

## 2. Rotation: Controlled Replacement of Key Material

### 2.1. Automatic Rotation

Automatic rotation lets AWS KMS generate new key material on a schedule. This feature is supported for customer managed keys of symmetric encryption type with key material origin `AWS_KMS`.

By default, KMS rotates key material every 365 days. You can set a custom period from 90 to 2,560 days via `RotationPeriodInDays`. The period is calculated from the time rotation is enabled and repeats according to the configured number of days.

AWS managed keys are automatically rotated by AWS KMS annually; users cannot enable or disable their rotation schedule. AWS owned keys are owned and managed by the AWS service according to that service's policies. For customer managed keys, automatic rotation is optional and must be explicitly enabled.

Example enabling rotation with a 180-day period:

~~~bash
aws kms enable-key-rotation \
  --key-id <KEY_ID_OR_ARN> \
  --rotation-period-in-days 180

aws kms get-key-rotation-status \
  --key-id <KEY_ID_OR_ARN>
~~~

The second command checks `KeyRotationEnabled`, `RotationPeriodInDays`, and `NextRotationDate`. To enable rotation, the principal needs `kms:EnableKeyRotation`; checking status requires `kms:GetKeyRotationStatus`. Effective permissions also depend on the key policy and how the account configures IAM delegation.

Automatic rotation has important properties:

- The key ID, key ARN, Region, key policy, and permissions of the KMS key remain unchanged.
- Applications and AWS services continue referencing the same KMS key.
- When encrypting, KMS uses the current key material.
- When decrypting older ciphertext, KMS automatically selects the version of key material that was used to encrypt that ciphertext.
- KMS retains older key material so data encrypted before rotation can still be decrypted.
- Rotation does not automatically re-encrypt data or replace previously generated data keys.

Therefore, automatic rotation typically causes minimal disruption for applications using a KMS key as a wrapping key. However, it does not resolve every data exposure incident. If a data key has been compromised, merely rotating the KMS key does not make the exposed data key safe; you must evaluate generating new data keys and re-encrypting affected data.

When a customer managed key is disabled, KMS pauses key material rotation. Once the key is re-enabled, if the scheduled rotation date has already passed, KMS rotates immediately; otherwise, the existing schedule resumes. While a key is in `PendingDeletion`, rotation is paused. If deletion is canceled, the prior rotation state is restored and KMS performs rotation if overdue.

### 2.2. On-Demand Rotation

On-demand rotation initiates replacing key material immediately when requested, without waiting for the automatic rotation schedule. You can use this feature even if automatic rotation is not enabled. Performing an on-demand rotation does not alter any configured automatic rotation schedule.

On-demand rotation supports customer managed symmetric encryption keys with origin `AWS_KMS` or `EXTERNAL`. For keys with imported key material, you must import new material first; the new material must be in the pending rotation state (`Pending rotation`) before it can become the current material. KMS allows up to 25 on-demand rotations per KMS key.

Example:

~~~bash
aws kms rotate-key-on-demand \
  --key-id <KEY_ID_OR_ARN>

aws kms get-key-rotation-status \
  --key-id <KEY_ID_OR_ARN>
~~~

This operation requires `kms:RotateKeyOnDemand`; checking progress requires `kms:GetKeyRotationStatus`. Rotation runs asynchronously in the background so there can be a brief delay before completion. Use `ListKeyRotations` to inspect completed rotation history.

On-demand rotation does not apply to asymmetric keys, HMAC keys, or keys in custom key stores. For these types, consider manual rotation. For a set of multi-Region keys, initiate rotation only on the primary key. For imported key material in multi-Region keys, import the same new material into each related Region before rotating the primary key.

### 2.3. Manual Rotation

Manual rotation creates a new KMS key and switches applications or services to the new key. This approach is required when the key type does not support automatic or on-demand rotation, or when an organization needs to change algorithm, key usage, account, Region, or administrative boundaries.

General workflow:

1. Create a new KMS key with the appropriate key spec, key usage, Region, and policy.
2. Grant permissions to workloads that need to use the new key.
3. Update aliases or application configuration so new encryption operations use the new key.
4. Test encryption and decryption through the real application code paths.
5. Plan migration of older ciphertext, wrapped data keys, and backups. Older data may still need the old key to decrypt.
6. Only disable or schedule deletion of the old key after verifying no data, backups, or workloads still depend on it.

If applications reference an alias, you can repoint the alias to the new key to route new operations. Changing an alias does not automatically convert ciphertext encrypted with the old key. Keep the old key available until old data is decrypted, re-encrypted, or reaches end of retention.

### 2.4. Monitoring Rotation

You can verify rotation through multiple sources:

- `GetKeyRotationStatus` reports automatic rotation status and on-demand rotation progress.
- `ListKeyRotations` reports completed rotation history.
- AWS CloudTrail logs `RotateKey` events and key administration actions.
- Amazon EventBridge emits `KMS CMK Rotation` events when key material rotates.

With multi-Region keys, KMS synchronizes new key material across the primary and replicas before using the new material for cryptographic operations. Monitor status on the primary key and verify related Regions have synchronized.

## 3. Disabling a Key to Pause Usage

`DisableKey` transitions a customer managed key from `Enabled` to `Disabled`. In this state, KMS does not allow the key to be used in cryptographic operations. The key still exists, retaining its key material, policy, and metadata; an authorized principal can re-enable it.

Example:

~~~bash
aws kms disable-key --key-id <KEY_ID_OR_ARN>

aws kms describe-key \
  --key-id <KEY_ID_OR_ARN> \
  --query "KeyMetadata.{State:KeyState,Enabled:Enabled}"
~~~

Once confirmed safe to resume usage:

~~~bash
aws kms enable-key --key-id <KEY_ID_OR_ARN>
~~~

Only customer managed keys can be disabled or enabled this way. AWS managed keys and AWS owned keys cannot be directly disabled or enabled by users.

Disabling is appropriate when you need to:

- Pause a key during an incident investigation or dependency check.
- Prevent workloads from continuing to use the key while reviewing configuration.
- Test impact before deciding to delete a key.
- Temporarily block cryptographic operations while keeping recovery possible.

Understand the impact on services using envelope encryption. Already-decrypted data or data keys cached in memory by a service may not fail immediately. Failures typically surface when the service needs to call KMS to decrypt a data key or perform subsequent cryptographic operations. Thus, a workload may continue running briefly before failing when it next calls KMS.

While a key is disabled, KMS also pauses automatic rotation. After re-enabling, KMS resumes the rotation schedule or rotates immediately if overdue. Do not disable a production key for testing without first identifying dependent workloads, backups, and services.

## 4. Scheduled Deletion: Scheduling Key Removal

Deleting a KMS key is irreversible once the waiting window expires. AWS KMS allows scheduling deletion only for customer managed keys. AWS managed keys and AWS owned keys cannot be scheduled for deletion by users.

KMS requires a waiting window between 7 and 30 days; the default is 30 days. Once accepted, the key transitions to `PendingDeletion` and cannot perform cryptographic operations. When the waiting window expires, KMS deletes the key material, key metadata, and associated aliases. Actual deletion time may lag the scheduled time by up to 24 hours; use `DescribeKey` to view the scheduled deletion date.

Example scheduling deletion after 30 days:

~~~bash
aws kms schedule-key-deletion \
  --key-id <KEY_ID_OR_ARN> \
  --pending-window-in-days 30
~~~

KMS logs both scheduling deletion and actual deletion in AWS CloudTrail. During the waiting window, monitor failed KMS calls to detect any workloads still relying on the key.

### 4.1. Checks Before Scheduling Deletion

Before running `ScheduleKeyDeletion`, perform these steps:

1. Identify whether the key is used by AWS services, applications, other accounts, or external systems.
2. Check CloudTrail and resource configurations for recent activity; KMS does not store ciphertext and does not provide a complete inventory of data encrypted by a key.
3. Check backups, snapshots, long-term logs, archived data, and data retention requirements.
4. Verify disaster recovery plans and the ability to decrypt data across relevant Regions.
5. Consider disabling the key first, setting CloudWatch alarms, and observing errors over a sufficiently long window to confirm no dependencies remain.
6. Restrict `kms:ScheduleKeyDeletion`; you can use the `kms:ScheduleKeyDeletionPendingWindowInDays` condition key in key policies or IAM policies to enforce a minimum waiting period.

If uncertain whether data still depends on the key, keep the key `Disabled` and continue investigating. A disabled key can still be re-enabled; a permanently deleted key cannot be recovered through normal procedures.

### 4.2. Multi-Region Key Cases

When scheduling deletion of a multi-Region primary key that still has replicas, the primary key transitions to `PendingReplicaDeletion`. All replica keys must be scheduled for deletion and awaited until deleted. The primary key's waiting window begins only after the last replica is deleted.

A replica key can be recreated by replicating an existing primary key into that Region. However, deleting the primary key affects the entire related key set; review recovery plans and consuming Regions beforehand.

## 5. Restoring Key Usability

Recovery depends on `KeyState` and the reason for denial. The first step is identifying the right key by key ID or ARN and checking its state:

~~~bash
aws kms describe-key \
  --key-id <KEY_ID_OR_ARN> \
  --query "KeyMetadata.{KeyId:KeyId,State:KeyState,Enabled:Enabled,Origin:Origin,Manager:KeyManager,MultiRegion:MultiRegion}"
~~~

### 5.1. Key Is Disabled

If the state is `Disabled`, verify that re-enabling the key aligns with incident response and that workloads are permitted to use it. Then run:

~~~bash
aws kms enable-key --key-id <KEY_ID_OR_ARN>
~~~

Re-check with `DescribeKey`. After the key returns to `Enabled`, test a controlled encryption or decryption operation using the application principal. If the key enforces a required encryption context, the test must supply the exact context.

### 5.2. Key Is PendingDeletion

You can cancel deletion while the key is still in `PendingDeletion` and the waiting window has not expired:

~~~bash
aws kms cancel-key-deletion --key-id <KEY_ID_OR_ARN>
~~~

After cancellation, the key state transitions to `Disabled`. Therefore, an additional enable step is required:

~~~bash
aws kms enable-key --key-id <KEY_ID_OR_ARN>
~~~

Next, check the state with `DescribeKey`, check rotation with `GetKeyRotationStatus`, and test application operations. KMS restores prior rotation configuration after deletion cancellation; if a rotation was overdue, KMS may rotate immediately once the key is re-enabled.

If the waiting window has already expired and KMS has deleted the key, `CancelKeyDeletion` has no effect. For standard symmetric KMS keys, ciphertext encrypted under a deleted key cannot be decrypted again.

### 5.3. Key Is PendingImport or Unavailable

If the key has `Origin=EXTERNAL` and state `PendingImport`, check key material expiration, import tokens, and the key material import procedure. When material has expired or been deleted, merely calling enable cannot restore cryptographic capability; valid material must be re-imported per KMS documentation.

If the key is `Unavailable`, inspect the custom key store. For an AWS CloudHSM key store, verify the cluster and connectivity. For an external key store, verify the external key manager, proxy, and connectivity. Once the backing key store is ready, re-check state and run a test operation.

### 5.4. Key Is Enabled but Applications Still Receive AccessDenied

`Enabled` only indicates the key can perform cryptographic operations; it does not mean every principal is allowed to use it. If an application receives `AccessDeniedException`, check in order:

- Whether the key policy allows the principal or account to use the key.
- Whether the role's or user's IAM policy grants required actions such as `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey`, or `kms:ReEncrypt`.
- Whether a KMS grant was revoked, expired, or misconstrained.
- Whether an SCP, permissions boundary, session policy, or VPC endpoint policy is blocking the action.
- Whether policy conditions require a specific encryption context, `ViaService`, Region, or principal ARN.
- Whether the application is referencing the right key ID, ARN, or alias in the right Region and account.

Grant only the actions and resources required by the workload. Never open up the key policy to all principals as a quick fix for access errors.

## 6. Operational Workflows and Monitoring

A sound operational workflow separates replacing key material, pausing usage, and deleting keys into deliberate, distinct changes.

~~~mermaid
flowchart TD
    A["KMS key is Enabled"] --> B{"Operational goal?"}
    B -->|"Periodic rotation"| C["Automatic rotation"]
    B -->|"Immediate rotation"| D["On-demand rotation"]
    B -->|"Pause usage"| E["DisableKey"]
    B -->|"Retire permanently"| F["ScheduleKeyDeletion"]
    E --> G{"Need to use again?"}
    G -->|"Yes"| H["EnableKey"]
    G -->|"No, continue evaluating"| I["Keep Disabled and monitor"]
    F --> J{"Still within waiting window?"}
    J -->|"Yes, need to keep key"| K["CancelKeyDeletion"]
    K --> L["EnableKey"]
    J -->|"No"| M["Key is permanently deleted"]
~~~

Establish the following controls:

- **Authorization:** separate key administration roles from key usage roles; restrict who holds `kms:ScheduleKeyDeletion` and `kms:DisableKey`.
- **Waiting window:** use `kms:ScheduleKeyDeletionPendingWindowInDays` to enforce a minimum waiting period per organizational policy.
- **Auditing:** retain CloudTrail logs and review `DisableKey`, `EnableKey`, `ScheduleKeyDeletion`, `CancelKeyDeletion`, and rotation events.
- **Alerting:** create CloudWatch alarms or EventBridge rules to detect key lifecycle changes and attempts to use keys pending deletion.
- **Recovery drills:** periodically rehearse canceling scheduled deletion, re-enabling keys, and decrypting sample data using the actual workload role.
- **Dependency tracking:** maintain an inventory of services, applications, snapshots, backups, and archived data depending on each key.

For Java/Spring Boot applications, manage key ARN or alias configuration per deployment environment. When switching to a new key, test both encrypting new data and decrypting older data. If the application uses envelope encryption, store the encrypted data key alongside the ciphertext and ensure the key needed to decrypt the encrypted data key remains available.

## 7. Choosing the Right Operation

| Need | Operation to choose | Points to verify |
|---|---|---|
| Meet periodic rotation policy | Automatic rotation | Key type, origin, period, and rotation status. |
| Replace key material immediately | On-demand rotation | Key is symmetric; if using imported material, new material is already imported. |
| Key does not support automatic rotation | Manual rotation | Update consumers and retain old key to decrypt older data. |
| Pause cryptographic operations | Disable key | Workloads identified and re-enable procedure ready. |
| Evaluating whether a key can be deleted | Disable and monitor | No remaining services, backups, or ciphertext needing the key. |
| Confirmed no dependencies remain and ready to delete | Schedule deletion | Exact key, waiting window, replicas, and approvals. |
| Scheduled deletion by mistake, still in waiting window | Cancel deletion then enable | Verify state and access permissions after recovery. |
| Key Enabled but application denied | Fix key policy, IAM, or grant | Principal, action, Region, encryption context, and policy conditions. |

## 8. Practical Scenario

A Spring Boot application stores documents in Amazon S3 and uses a customer managed symmetric KMS key to protect the data. The operations team receives a request to enable annual rotation, and later notices an older key that appears unused and wants to delete it.

Recommended handling:

1. Use `DescribeKey` to confirm the key is customer managed, symmetric encryption, `Origin=AWS_KMS`, and currently `Enabled`.
2. Enable automatic rotation with a 365-day period, then verify the configuration with `GetKeyRotationStatus`.
3. Review CloudTrail, bucket configurations, backups, replication, and applications to identify resources depending on the key.
4. To verify dependencies further, disable the key during a monitored maintenance window. Watch for S3 and KMS access errors; if any legitimate workload is affected, re-enable the key immediately.
5. Only after confirming no data or backups still require the key, schedule deletion with an appropriate waiting window, such as 30 days.
6. During the waiting window, monitor CloudTrail and alerts. If a backup or workload still needs the key, run `CancelKeyDeletion`, then `EnableKey`, and test decryption.
7. Once the waiting window expires, the key is permanently deleted. Any symmetric ciphertext still relying on that key will be impossible to decrypt.

This scenario illustrates that rotation, disabling, and scheduled deletion serve three distinct purposes. Rotation replaces key material per policy; disabling pauses usage; scheduled deletion ends the key lifecycle after a mandatory waiting window.

## References

- [Rotate AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)
- [Enable automatic key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotating-keys-enable.html)
- [Perform on-demand key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotating-keys-on-demand.html)
- [Enable and disable keys](https://docs.aws.amazon.com/kms/latest/developerguide/enabling-keys.html)
- [Key states of AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/key-state.html)
- [Schedule key deletion](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys-scheduling-key-deletion.html)
- [Cancel key deletion](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys-cancelling-key-deletion.html)
- [Delete an AWS KMS key](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html)
