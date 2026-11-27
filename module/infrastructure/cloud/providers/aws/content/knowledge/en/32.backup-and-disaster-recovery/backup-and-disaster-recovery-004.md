# Cross-Region Backup Copies and AWS Backup Vault Lock

## Lesson Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, disaster recovery depends on having usable backups stored independently of the running environment. AWS Backup supports copying recovery points to another AWS Region either on a schedule or on demand. Copies in the destination Region are encrypted using the destination backup vault's key and can be used to restore when the source Region experiences an outage.

AWS Backup Vault Lock adds protection against premature deletion or out-of-policy lifecycle changes. Its two modes—Governance and Compliance—offer different levels of control. Combining cross-Region copies with Vault Lock enables organizations to maintain a secondary backup in another location that resists accidental deletion or account compromise.

After this lesson, you will be able to:

- Explain the purpose of cross-Region backup copies and the differences between backup, copy, replication, and restore.
- Design backup plans with copy actions to a destination Region and independent retention.
- Verify support by resource type and Region before deployment.
- Configure backup vaults, AWS KMS keys, and IAM roles for cross-Region copies.
- Distinguish between Vault Lock Governance mode and Compliance mode.
- Set min/max retention, grace periods, and inspect lock states.
- Combine cross-account copying, AWS Organizations, and vault access policies when isolating storage accounts.
- Monitor copy jobs, troubleshoot errors, and organize restore testing to verify recoverability.
- Estimate costs, RPO/RTO, and risks when applying immutable retention.

## 1. Why Keep Backups in Another Region?

Same-Region backups help recover from application errors, accidental deletions, or service-level disruptions. However, if a major incident impacts an entire Region, both the workload and its same-Region backups can become inaccessible. A copy in another Region provides an additional recovery option when the primary Region is unavailable.

For example, an e-commerce application runs in ap-southeast-1 (Singapore). Operations stores daily backups in a vault in that Region and copies recovery points to ap-southeast-2 (Sydney). If the primary Region suffers an outage, the team can restore resources from the Sydney copy per the DR plan.

Cross-Region copying helps achieve several goals:

- **Geographic resilience:** maintaining backups outside the primary operating Region.
- **Compliance and retention:** storing data in another location per internal or regulatory mandates.
- **Mitigating accidental deletion:** if a source backup is deleted, the independent copy in the destination Region can remain intact.
- **Separation of administration:** pairing with cross-account backup to restrict operational account permissions over archived copies.
- **Recovery flexibility:** choosing a Region suited to the DR plan, user locations, and service capacity.

Important distinctions:

| Concept | Meaning | Example |
|---|---|---|
| Backup | A recovery point created from a resource at a point in time or interval | Daily RDS snapshot |
| Cross-Region copy | AWS Backup creates another recovery point in a destination Region | Copying a snapshot from Singapore to Sydney |
| Replication | A service-level mechanism synchronizing data or changes | S3 Cross-Region Replication, RDS read replica |
| Restore | Recreating a resource or data from a recovery point | Restoring a database from a snapshot in the destination Region |

Cross-Region copying is not equivalent to active-active or automatic failover. It creates backups for recovery. Operations still needs to provision infrastructure, networking, DNS, secrets, access permissions, capacity, and verify applications in the DR Region.

## 2. RPO, RTO, and Choosing a Destination Region

Before configuring a backup plan, define each workload's recovery targets.

- **Recovery Point Objective (RPO):** the maximum amount of data loss acceptable to the business, typically measured from the latest usable backup to the time of incident.
- **Recovery Time Objective (RTO):** the maximum acceptable time to return a service to an agreed operational state.
- **Retention:** how long a recovery point is kept.
- **Copy lag:** the elapsed time from source backup completion until the copy in the destination Region completes and becomes usable.

For instance, for a 24-hour RPO, daily backups may be a starting point. For a 15-minute RPO, daily backups alone are insufficient; evaluate continuous backup/PITR or service-native replication. For a 2-hour RTO, merely having a snapshot in the destination Region may still fall short once you include infrastructure provisioning, data restore, app configuration, and traffic validation.

Example selection table:

| Workload Type | Illustrative Targets | Options to Evaluate |
|---|---|---|
| Infrequently changing content site | 24-hour RPO, 8-hour RTO | Daily backups, cross-Region copy, restore runbook |
| E-commerce API | 1-hour RPO, 2-hour RTO | More frequent backups, cross-Region copy, partially pre-provisioned DR infrastructure |
| Critical transactional database | Minutes RPO, under 1-hour RTO | PITR, native replication, or multi-Region database architecture; backup copies as an added safeguard |
| Long-term retention records | Policy-driven RPO, multi-year retention | Backup plan, copy to dedicated vault, Vault Lock Compliance after verification |

When selecting a destination Region, evaluate:

1. Geographic distance and data residency requirements.
2. Whether AWS services and resource types support cross-Region copy across both Regions.
3. Region opt-in availability and AWS partition boundaries.
4. Availability of instance classes, storage, quotas, and IP addressing at restore time.
5. Storage, data transfer, and KMS key costs.
6. Administrative isolation and blast radius between source and destination Regions.

Do not pick a Region solely because it is nearest or has the lowest storage rates. The DR Region must support all required services and capacity to run the workload after recovery.

## 3. How AWS Backup Cross-Region Copy Works

AWS Backup can copy recovery points to one or more other Regions in two ways:

- **On-demand copy:** an operator selects a recovery point and starts a copy job manually.
- **Scheduled copy:** a backup plan defines CopyActions to automatically copy whenever a backup rule creates a recovery point.

When copying to a new Region for the first time, AWS Backup typically performs a full copy. For resource types supporting incremental backups, subsequent copies to the same destination vault are typically incremental. Copies are re-encrypted using the destination backup vault's KMS key.

There is an important Amazon EBS exception: copying a snapshot to a vault with a different KMS key can turn the copy into a full copy rather than incremental. Repeatedly copying to the same vault with the same encryption key allows subsequent copies to remain incremental.

Cross-Region copy limitations:

- Not all resource types support copying. Check the Cross-Region backup column in the Feature availability by resource table.
- Not all Region pairs support copying. Check the Feature availability by AWS Region table and account opt-in status.
- AWS Backup does not support copying recovery points already stored in cold storage or archive tiers to another Region.
- Some services impose extra conditions. For example, RDS cross-Region copy may require pre-creating a matching option group in the destination Region if the source uses a custom option group with persistent options.
- AWS Backup does not guarantee an SLA on copy job completion time. Duration depends on data size, source service, system load, and operational conditions.

Some resource types support continuous backup/PITR. When copying a continuous recovery point to another Region, the copy becomes a periodic snapshot backup; point-in-time restore capability is not preserved on that copy. Therefore, do not assume a copy of a PITR backup permits restoring to arbitrary timestamps like the source.

Before deploying, build a matrix:

| Resource Type | Source Region | Destination Region | Cross-Region Support | Special Conditions |
|---|---|---|---|---|
| Amazon EBS | ap-southeast-1 | ap-southeast-2 | Check support matrix | Changing KMS key can force full copy |
| Amazon RDS | ap-southeast-1 | ap-southeast-2 | Check DB type and Region | Check option groups, engine/version |
| Amazon S3 | ap-southeast-1 | ap-southeast-2 | Check feature matrix | PITR/continuous copy becomes snapshot |
| Amazon EFS | ap-southeast-1 | ap-southeast-2 | Check file system type | Check lifecycle and restore support |
| Amazon Aurora | ap-southeast-1 | ap-southeast-2 | Check cluster and Region | Some copies are full backups |

This table is a planning example; confirm actual support status in the AWS Backup Feature availability documentation at implementation time.

## 4. Creating a Backup Vault and KMS Key in the Destination Region

A backup vault is where AWS Backup stores recovery points. Each vault belongs to a single AWS account and a single Region. When copying recovery points to a destination Region, create the destination vault beforehand and choose an appropriate encryption key.

Basic workflow:

1. Choose the DR Region.
2. Create a customer managed KMS key in the destination Region if the resource type and encryption requirements call for it.
3. Create the backup vault in the destination Region.
4. Assign the KMS key as the vault's encryption key.
5. Configure access policies, IAM roles, and Vault Lock as required.
6. Point the copy action to the destination vault ARN.

Example creating a vault in ap-southeast-2:

~~~bash
aws backup create-backup-vault \
  --backup-vault-name dr-vault \
  --encryption-key-arn arn:aws:kms:ap-southeast-2:111122223333:key/12345678-1234-1234-1234-123456789012 \
  --region ap-southeast-2
~~~

Replace the illustrative ARN with an actual KMS key in the destination Region. KMS keys are Regional resources; a key in ap-southeast-1 cannot be referenced as the key for a vault in ap-southeast-2.

### 4.1. Understanding Encryption During Copy

AWS Backup uses the destination vault's KMS key to encrypt copies for most resource types. However, key selection depends on the resource type and whether AWS Backup fully manages it.

| Scenario | Copy Encryption Key |
|---|---|
| Resource fully managed by AWS Backup | Can use customer managed key or AWS Backup managed key of the destination vault |
| Resource not fully managed by AWS Backup | Destination vault requires a customer managed key or the AWS service managed key of the resource-owning service, depending on resource type |
| Cross-account copy of a non-fully-managed resource | Requires a customer managed key whose key policy permits the destination account to use it |
| Cross-Region copy | Uses a key residing in the destination Region |

For example, when copying EC2/EBS backups, you cannot rely on the AWS Backup managed key aws/backup in every case. For non-fully-managed resources, a CMK or the source service's AWS managed key such as aws/ebs may be needed. Check the encryption support table for your exact resource type.

The IAM role running backup/copy jobs and the KMS key policy must allow required operations. Commonly involved permissions include kms:CreateGrant, kms:GenerateDataKey, and kms:Decrypt. If the key policy contains a Deny, inspect conditions and allowlist backup/restore roles. A job may report completion while a specific item fails to back up or restore as expected if KMS permissions are incomplete; always verify job details and actual data.

## 5. Automating Copies with a Backup Plan

A backup plan defines the creation schedule, source vault, and lifecycle for recovery points. Each rule can specify one or more CopyActions to send copies to destination vaults.

Example backup plan JSON for daily backups copied to a DR Region:

~~~json
{
  "BackupPlanName": "DailyBackupWithDRCopy",
  "Rules": [
    {
      "RuleName": "DailyDatabaseBackup",
      "TargetBackupVaultName": "primary-vault",
      "ScheduleExpression": "cron(0 18 ? * * *)",
      "StartWindowMinutes": 60,
      "CompletionWindowMinutes": 240,
      "Lifecycle": {
        "DeleteAfterDays": 35
      },
      "CopyActions": [
        {
          "DestinationBackupVaultArn": "arn:aws:backup:ap-southeast-2:111122223333:backup-vault:dr-vault",
          "Lifecycle": {
            "DeleteAfterDays": 120
          }
        }
      ]
    }
  ]
}
~~~

In this example:

- Source backups are stored in primary-vault in the Region where the plan is created.
- The cron schedule runs daily at 18:00 UTC.
- Source backups have a 35-day retention.
- Copies in dr-vault have a 120-day retention.
- The copy's lifecycle is declared independently of the source recovery point's lifecycle.

If the destination vault enforces a Vault Lock with min retention 90 days and max retention 365 days, a 120-day copy retention satisfies those bounds. If copy retention is shorter than min or longer than max, the copy job will fail.

Create the backup plan:

~~~bash
aws backup create-backup-plan \
  --backup-plan file://backup-plan.json \
  --region ap-southeast-1
~~~

After creating the plan, assign resources to it using resource assignments or tag-based selections. A backup plan does not automatically protect any resources in the account without an appropriate assignment.

### 5.1. On-Demand Recovery Point Copy

To copy an existing recovery point on demand, use StartCopyJob:

~~~bash
aws backup start-copy-job \
  --recovery-point-arn arn:aws:backup:ap-southeast-1:111122223333:recovery-point:EXAMPLE-RECOVERY-POINT \
  --source-backup-vault-name primary-vault \
  --destination-backup-vault-arn arn:aws:backup:ap-southeast-2:111122223333:backup-vault:dr-vault \
  --iam-role-arn arn:aws:iam::111122223333:role/AWSBackupDefaultServiceRole \
  --region ap-southeast-1
~~~

Provide the actual recovery point ARN and source vault name. The IAM role must trust AWS Backup and hold copy permissions. After calling the API, save CopyJobId to track progress.

Avoid blindly retrying on-demand commands. If retrying after a client timeout, use an appropriate idempotency token when invoking the StartCopyJob API directly to prevent duplicate requests.

## 6. Cross-Account Copy and Isolating Storage Accounts

A copy in another Region provides geographic isolation. To strengthen resilience against source account compromise, you can also copy into a dedicated backup account within AWS Organizations.

Example architecture:

~~~mermaid
flowchart LR
    subgraph PROD["Production account"]
      A[Application resources]
      B[Primary backup vault]
      A --> B
    end
    subgraph DR["Backup account"]
      C[DR backup vault]
      D[Vault Lock Compliance]
      C --> D
    end
    B -->|Cross-Region / cross-account copy| C
    C --> E[Restore in DR account and Region]
~~~

To set up cross-account copying:

1. Both accounts must belong to the same AWS Organizations organization.
2. The management account must enable cross-account backup.
3. Create the backup vault in the destination account and Region.
4. Configure an encryption key for the destination vault.
5. Attach a resource-based access policy to the destination vault allowing backup:CopyIntoBackupVault.
6. The source IAM role needs backup:CopyFromBackupVault and backup:CopyIntoBackupVault permissions.
7. If source resources are encrypted with a customer managed KMS key, share key usage permissions with the destination account per an appropriate policy.
8. Restrict which accounts and vaults may receive copies using IAM, vault access policies, and SCPs.

The default backup vault cannot serve as a cross-account copy destination because its default key cannot be shared across accounts. Create a dedicated vault with explicitly managed encryption keys.

For resources fully managed by AWS Backup, the destination vault can use either a customer managed key or an AWS Backup managed key per service support. For other resources, the destination vault requires a CMK because AWS managed keys cannot be shared cross-account. Check encryption documentation for each resource type.

AWS Backup supports cross-account copying within the same organization. If a destination account later leaves the organization, it retains the backups already received. Organizations should restrict organizations:LeaveOrganization via SCP if policy mandates archive accounts remain inside the organization. Also limit which accounts can copy into the destination vault so it cannot be flooded with unexpected backups.

## 7. What Is AWS Backup Vault Lock?

AWS Backup Vault Lock is a WORM (write once, read many) feature applied to a backup vault. Once recovery points reside in a locked vault, AWS Backup rejects deletions or lifecycle edits that violate the retention policy.

Vault Lock helps:

- Prevent users from deleting recovery points before their retention expires.
- Protect backups against human error or compromised privileged accounts.
- Enforce minimum and maximum retention on new backup/copy jobs.
- Add a safeguard for long-term retention and audit compliance.

Each backup vault can have at most one Vault Lock. Vault Lock is distinct from Amazon S3 Object Lock or Amazon Glacier Vault Lock; it is a mechanism specific to AWS Backup.

There are two modes:

| Characteristic | Governance mode | Compliance mode |
|---|---|---|
| Goal | Controlled administrative governance | Immutable policy-enforced retention |
| Who can remove the lock? | Principals with appropriate IAM permissions | Nobody after the grace period expires |
| Has a grace period? | No | Yes |
| Grace duration | Not applicable | Minimum 3 days (72 hours), maximum 36,500 days |
| After lock takes effect | Can be modified by sufficiently privileged principals | Vault lock becomes immutable |
| Best suited for | Backup workflows needing governed flexibility | Records requiring strict protection against deletion or tampering during retention |

### 7.1. Governance Mode

Governance mode restricts vault changes to principals holding specific IAM permissions. Highly privileged users can still remove or update the Vault Lock. This mode fits organizations that want approval gates and separation of duties while keeping the ability to adjust retention if policy changes.

Governance mode does not guarantee immutability against every administrator or root user. If an account is compromised and an attacker obtains sufficient IAM permissions, they can remove the lock. Pair it with IAM least privilege, SCPs, separate backup accounts, and CloudTrail monitoring.

### 7.2. Compliance Mode

Compliance mode targets strict WORM requirements. When creating the lock, specify ChangeableForDays as the grace period. During the grace period, the lock can be modified or deleted. Once the grace period expires, the vault lock becomes immutable and cannot be altered or removed by any user, including the root user or AWS.

If the vault contains recovery points, the vault cannot be deleted once Compliance mode is immutable. If the vault is empty, it can be deleted per AWS Backup rules.

Compliance mode fits once retention is formally approved and no longer needs changes. Never enable this mode on a production vault before verifying lifecycles, restores, KMS, policies, and costs.

## 8. Min Retention, Max Retention, and Grace Period

Vault Lock supports two retention bounds:

- **MinRetentionDays:** minimum retention days. New backup or copy jobs with shorter retention fail.
- **MaxRetentionDays:** maximum retention days. New backup or copy jobs with longer retention fail.
- **ChangeableForDays:** grace period for Compliance mode. Specifying this parameter creates the Vault Lock in Compliance mode.

Allowed values:

| Attribute | Limit |
|---|---|
| MinRetentionDays | Minimum 1 day |
| MaxRetentionDays | Maximum 36,500 days |
| ChangeableForDays | Between 3 and 36,500 days |

MinRetentionDays and MaxRetentionDays are optional in the API, though MinRetentionDays is required in certain CloudFormation schemas. Without max retention, Vault Lock sets no upper bound; recovery points with Always retention may be kept indefinitely.

Important detail: Vault Lock min/max retention does not retroactively alter the retention of recovery points created before the lock was applied. Older recovery points continue following the lifecycle defined at creation. Min/max limits apply to new backup and copy jobs after Vault Lock is configured.

Policy example:

- The destination vault accepts only backups with retention between 90 and 365 days.
- The backup plan's copy action sets DeleteAfterDays to 120.
- A new backup job with 30-day retention is rejected when targeting this vault.
- A copy job with 400-day retention is also rejected.
- Recovery points already inside the vault before lock creation do not automatically change to 90 or 365 days.

When using Compliance mode, inspect all lifecycles across backup plans, copy actions, and Organizations-managed backup plans before starting the grace period. If any job uses Always retention or excessively long retention, recovery points may never expire and generate ongoing storage costs.

## 9. Creating Vault Lock with the AWS CLI

Example creating Governance mode with retention between 90 and 365 days:

~~~bash
aws backup put-backup-vault-lock-configuration \
  --backup-vault-name dr-vault \
  --min-retention-days 90 \
  --max-retention-days 365 \
  --region ap-southeast-2
~~~

Omitting ChangeableForDays creates the Vault Lock in Governance mode.

Example creating Compliance mode with a 7-day grace period:

~~~bash
aws backup put-backup-vault-lock-configuration \
  --backup-vault-name dr-vault \
  --changeable-for-days 7 \
  --min-retention-days 90 \
  --max-retention-days 365 \
  --region ap-southeast-2
~~~

In this example, after creating the lock, the organization has 7 days to validate and adjust configuration. Afterward, Vault Lock becomes immutable. The minimum grace period is 3 days; choosing 7 days is illustrative, not a mandatory default.

Inspect vault configuration:

~~~bash
aws backup describe-backup-vault \
  --backup-vault-name dr-vault \
  --region ap-southeast-2
~~~

Key fields include:

- Locked: indicates Vault Lock is applied.
- MinRetentionDays: minimum retention.
- MaxRetentionDays: maximum retention.
- LockDate: UTC timestamp when the grace period ends and the lock becomes immutable.
- NumberOfRecoveryPoints: count of recovery points in the vault.

During the grace period, misconfigurations can be updated via PutBackupVaultLockConfiguration or removed via DeleteBackupVaultLockConfiguration. After the grace period expires, a Compliance mode lock cannot be modified or removed.

Do not place these commands in automated pipelines without change-management approval. In particular, Compliance mode commands create irreversible constraints after the grace period.

## 10. Combining Cross-Region Copy with Vault Lock

A reference architecture:

1. Create a backup plan in the source Region.
2. Create backup vaults in both source and destination Regions.
3. Create suitable KMS keys in each Region.
4. Configure copy actions targeting the destination vault.
5. Verify copy jobs succeed and recovery points appear in the destination Region.
6. Test restores from the destination Region.
7. Start with Vault Lock in Governance mode if an initial trial phase is needed.
8. Verify retention, restores, costs, permissions, and operational procedures.
9. Once policy is approved, transition the destination vault to Compliance mode under change control.
10. Continuously monitor copy jobs and restore tests.

Diagram:

~~~mermaid
flowchart TD
    A[Production resources] --> B[Backup plan]
    B --> C[Primary backup vault]
    C --> D[Copy job]
    D --> E[Destination vault in another Region]
    E --> F[Vault Lock]
    F --> G[Immutable recovery points after grace period]
    G --> H[Restore test]
    H --> I[DR workload]
    D --> J[EventBridge copy job event]
    J --> K[Alarm, ticket and operations]
~~~

If a copy action specifies 120-day retention and the destination Vault Lock sets min 90 and max 365 days, the copy job satisfies the bounds. If the backup plan later lowers retention to 30 days, the copy action fails compliance and jobs may fail. Therefore, review backup plan edits together with destination vault retention policies.

Vault Lock governs actions performed through AWS Backup within its feature scope. However, for certain resource types, direct calls via source-service APIs may fall outside Vault Lock or vault access policies. For example, EBS snapshots can be shared or moved across storage tiers via EC2 APIs such as ModifySnapshotAttribute and ModifySnapshotTier. To block those actions, add IAM/SCP Deny rules with narrow exceptions for roles used by AWS Backup, since AWS Backup itself needs those actions for cross-account copies or cold storage transitions.

Additionally, a disabled AMI can disrupt restores even if recovery points remain inside a locked vault. Protect actions such as ec2:DisableImage through appropriate IAM/SCP policies.

## 11. Monitoring Backup and Copy Jobs

AWS Backup emits state-change events for backup, copy, and restore jobs to Amazon EventBridge. EventBridge receives these events on a best-effort basis, typically every 5 minutes. Do not rely solely on a single event to prove backup completion; cross-check against the AWS Backup API or console.

Common copy job states:

| State | Meaning |
|---|---|
| CREATED | Job has been created |
| RUNNING | Copy is in progress |
| COMPLETED | Copy finished |
| FAILED | Copy failed |

Filter copy job failures with an EventBridge event pattern:

~~~json
{
  "source": [
    "aws.backup"
  ],
  "detail-type": [
    "Copy Job State Change"
  ],
  "detail": {
    "state": [
      "FAILED"
    ]
  }
}
~~~

The rule can notify SNS, open a ticket, invoke Lambda, or route events to operations tooling. Include account, Region, resource ARN, source vault, destination vault, copy job ID, and status message in tickets.

Also track:

- Backup job and copy job success rates.
- Elapsed time from backup completion to copy completion.
- Age of the newest recovery point in the destination Region.
- Number of recovery points in the destination vault.
- Copy job failures broken down by resource type, Region, and KMS key.
- Restore test pass rates.
- Warm/cold storage and data transfer costs.

Inspect jobs via CLI:

~~~bash
aws backup list-copy-jobs \
  --by-state FAILED \
  --region ap-southeast-1
~~~

View details for a copy job:

~~~bash
aws backup describe-copy-job \
  --copy-job-id COPY_JOB_ID \
  --region ap-southeast-1
~~~

Copy jobs have no completion SLA. If a copy job runs longer than expected, inspect its status, resource type, data size, KMS permissions, service quotas, and status messages.

## 12. Restore Testing and DR Drills

A successful backup or copy job only proves a recovery point was created. It does not prove the application will work after restore.

AWS Backup Restore Testing lets you schedule automated restore tests from selected recovery points. You can specify the source vault, recovery point time range, test frequency, and resource selections. For DR readiness, test recovery points in the destination Region to prove the copy is genuinely usable.

A restore test workflow:

1. Select a recovery point in the destination vault.
2. Run a restore test into an isolated environment or test VPC.
3. Verify the resource is provisioned cleanly.
4. Inspect data, schema, encryption, IAM roles, security groups, and networking.
5. Start applications dependent on the restored resource.
6. Run smoke tests and data integrity checks.
7. Record restore time, errors, and actual RTO.
8. Clean up test resources per procedure and archive the report.

For example, restore an RDS database from a copy in the DR Region. After restoring, verify engine version, parameter group, option group, subnet group, security groups, secrets, application endpoint configuration, and access permissions. A snapshot can exist while the application fails to start if any of these dependencies are missing.

A restore testing plan can pick the newest recovery point or a random recovery point within a specified window. Random sampling helps validate recoverability across different points in time. To validate RTO, measure provisioning, restore, configuration, and business verification end-to-end—not merely the time until AWS Backup reports the restore job completed.

After each drill, update runbooks, dependency inventories, DR quotas, and actual RTO/RPO estimates.

## 13. Common Troubleshooting

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| Copy job not created | Unsupported resource type or Region | Check Feature availability by resource and by Region |
| Copy job FAILED with AccessDenied | IAM role lacks permissions or wrong trust policy | Check AWS Backup role and required actions |
| Copy job FAILED due to KMS | Key policy lacks CreateGrant/GenerateDataKey/Decrypt or has a Deny | Check IAM policy, KMS key policy, and grants |
| Destination vault does not receive copy | Wrong vault ARN, missing vault, or wrong Region/account | Check destination vault ARN and account/Region |
| Copy rejected due to retention | Lifecycle shorter than MinRetentionDays or longer than MaxRetentionDays | Align copy action retention with Vault Lock |
| Copy is not incremental | EBS copy uses a different KMS key or resource lacks incremental support | Check resource type and destination vault key |
| Cold-tier copy does not run | Source recovery point is already in cold/archive tier | Copy before cold transition or use appropriate native features |
| RDS copy fails with option group | Destination Region lacks required custom option group | Pre-create matching option group before copying |
| Restore job failed | Missing service-linked role, quota, subnet, or KMS access | Inspect restore metadata, roles, and destination Region config |
| Vault Lock cannot be removed | Compliance grace period has expired | Check LockDate and lock mode before attempting edits |
| Vault cannot be deleted | Compliance lock still holds recovery points | Verify retention and retention policies |
| Unexpected storage cost growth | Recovery point retention too long or Always | Inspect lifecycles, Min/Max retention, and recovery point counts |

When troubleshooting, record BackupJobId, CopyJobId, or RestoreJobId, recovery point ARN, account, Region, resource type, and status message. Do not attempt to delete backups or shorten retention to work around errors once a vault is under Compliance lock.

## 14. Security and Access Control

A secure backup architecture separates permissions for creating backups, copying, restoring, administering vaults, and altering retention.

Key principles:

- Use dedicated IAM roles for AWS Backup with a trust policy for backup.amazonaws.com.
- Grant least-privilege permissions scoped by resource type, vault, and Region.
- Separate backup creation permissions from recovery point deletion permissions.
- Restrict who can call PutBackupVaultLockConfiguration, DeleteBackupVaultLockConfiguration, and DeleteRecoveryPoint.
- Use a separate destination account when blast-radius isolation is needed.
- Protect KMS key policies and control grant creation permissions.
- Use SCPs or vault access policies to restrict destructive actions.
- Log changes via CloudTrail.
- Test restore permissions separately; permission to create backups does not automatically guarantee permission to restore.

Vault Lock governs operations performed through AWS Backup within its feature boundaries. Inspect direct APIs of the resource-owning services to confirm there are no unintended bypass paths. For EBS, review snapshot sharing and storage-tier transition permissions. For AMIs, block disable operations if they could impair restores.

## 15. Cost and Optimization

Cross-Region copying adds costs compared to keeping backups solely in the source Region. Line items to account for:

- Storage charges for recovery points in the source Region.
- Storage charges for copies in the destination Region.
- Data transfer or copy charges per service and Region pricing.
- KMS key usage and encryption/decryption API requests.
- Cold storage charges if the resource type supports it and lifecycle transitions tiers.
- Restore testing charges and temporary resources spun up during tests.
- Operating costs of the DR environment if compute, database, or network resources stay provisioned.

AWS Backup Vault Lock carries no separate surcharge, though storage charges still apply to recovery points inside a locked vault. Because recovery points cannot be deleted early, misconfigured retention can create sustained costs. Specifically, Always retention in Compliance mode can retain data indefinitely.

Optimization measures:

1. Classify workloads by RPO, RTO, and retention.
2. Copy only the resource types and datasets needed for DR or compliance.
3. Use distinct retention durations for operational backups versus long-term backups.
4. Check incremental copy support and KMS key effects on EBS.
5. Use cold storage when resource types support it and retention meets minimum requirements.
6. Align lifecycles with MinRetentionDays/MaxRetentionDays.
7. Track recovery point counts and costs by Region, account, and vault.
8. Schedule restore testing to avoid paying to store unusable backups.

## 16. Hands-On Exercise: Protecting a Database with Cross-Region Copies

An e-commerce system runs RDS in ap-southeast-1. The organization requires keeping backups for 35 days in the primary Region, retaining a 120-day copy in ap-southeast-2, and protecting the copy against premature deletion.

Proposed design:

| Component | Illustrative Configuration |
|---|---|
| Source Region | ap-southeast-1 |
| DR Region | ap-southeast-2 |
| Source vault | primary-vault |
| Destination vault | dr-vault |
| Source retention | 35 days |
| Copy retention | 120 days |
| Vault Lock min retention | 90 days |
| Vault Lock max retention | 365 days |
| Vault Lock mode | Compliance after trial phase |
| Grace period | 7 days |
| Restore test | Monthly |

Steps:

1. Confirm the RDS engine, version, and destination Region are supported by AWS Backup for copying.
2. Create the KMS key and dr-vault in ap-southeast-2.
3. Configure IAM/KMS permissions for backups and copies.
4. Create a backup plan with a daily rule and CopyActions setting DeleteAfterDays to 120.
5. Run test backup and copy jobs; verify recovery points appear in dr-vault.
6. Test-restore the database in the destination Region and validate the application.
7. Enable Vault Lock Governance mode initially or validate retention on a sandbox vault.
8. Confirm no backup/copy jobs violate retention bounds.
9. Once policy is approved, create a Compliance mode lock with a 7-day grace period.
10. During the grace period, monitor LockDate, job statuses, and costs.
11. After the lock becomes immutable, continue monitoring copy jobs and restore testing.

Test scenarios:

- Source backup completes, but copy job FAILS due to KMS key policy.
- Copy action specifies 60-day retention while destination vault requires at least 90 days.
- Operations attempts to delete a recovery point before expiration.
- RDS restore succeeds, yet the application cannot connect due to security groups.
- A copy job takes longer than expected and lacks a completion SLA.
- Destination Region lacks an option group or DB instance quota.

Trainees should identify investigation steps, diagnostic data to collect, responsible roles, and safe recovery actions for each scenario.

## Conclusion

AWS Backup cross-Region copy creates recovery points in another Region to support recovery when the source Region experiences an outage. Copies can run on demand or automatically via CopyActions in a backup plan. Feature support, encryption, incremental behavior, and lifecycle rules depend on resource type, Region, and the destination vault's KMS key.

AWS Backup Vault Lock protects recovery points against early deletion and enforces min/max retention on new backup/copy jobs. Governance mode lets sufficiently privileged principals modify the lock; Compliance mode becomes immutable after a minimum 72-hour grace period. Before enabling Compliance mode, verify retention, lifecycles, restores, permissions, and costs.

A dependable DR design combines cross-Region copies, hardened vaults, KMS encryption, IAM least privilege, copy job monitoring, and scheduled restore testing. Only when restore tests pass and the application meets RPO/RTO do backups prove their recovery value.

## References

- [Creating backup copies across AWS Regions](https://docs.aws.amazon.com/aws-backup/latest/devguide/cross-region-backup.html)
- [Backup and tag copy](https://docs.aws.amazon.com/aws-backup/latest/devguide/recov-point-create-a-copy.html)
- [AWS Backup feature availability](https://docs.aws.amazon.com/aws-backup/latest/devguide/backup-feature-availability.html)
- [Encryption for backups in AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/encryption.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- [Creating backup copies across AWS accounts](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-cross-account-backup.html)
- [Managing AWS Backup resources across multiple AWS accounts](https://docs.aws.amazon.com/aws-backup/latest/devguide/manage-cross-account.html)
- [Vault access policies](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-vault-access-policy.html)
- [CreateBackupPlan API and CopyActions](https://docs.aws.amazon.com/aws-backup/latest/devguide/API_CreateBackupPlan.html)
- [StartCopyJob API](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_StartCopyJob.html)
- [Monitoring AWS Backup events using Amazon EventBridge](https://docs.aws.amazon.com/aws-backup/latest/devguide/eventbridge.html)
- [AWS Backup monitoring](https://docs.aws.amazon.com/aws-backup/latest/devguide/monitoring.html)
- [AWS Backup Restore Testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
- [AWS Backup pricing](https://aws.amazon.com/backup/pricing/)
