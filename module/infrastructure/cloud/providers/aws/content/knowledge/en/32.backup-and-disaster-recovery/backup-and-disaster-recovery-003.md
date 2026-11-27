# Centralized Backup Policies and Cross-Account Backups

In an AWS organization with multiple accounts, each application team may create its own backup plans, choose schedules, and manage backup vaults independently. That approach offers flexibility at small scale, yet becomes difficult to maintain as the number of accounts, Regions, and workloads grows. An account can be missed, retention policies can drift out of alignment, and backups stored in the same account as the workload can be exposed if that account is compromised.

AWS Backup combined with AWS Organizations enables organizations to manage backup policies at the organization, OU, or account level. A centralized backup policy defines schedules, retention rules, Regions, and resource selections; the policy is inherited down to member accounts. AWS Backup also supports copying recovery points to a backup vault in another account, adding a layer of protection when the source account suffers an incident.

This lesson falls within the CLOUD_PROVIDERS_AWS scope: designing and operating secure, resilient, and cost-controlled AWS infrastructure. The focus is on building shared backup policies, structuring administrative permissions, configuring cross-account copies, and validating recoverability. A sound policy must cover the right resources, meet RPO/RTO, protect copies, and be verified through actual restores.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between backup plans, backup rules, backup selections, backup vaults, and AWS Organizations backup policies.
- Explain how AWS Backup integrates with AWS Organizations for centralized backup policy management.
- Design policy hierarchies across root, OU, and account levels, and understand inheritance and attribute overrides.
- Identify the roles of the management account, delegated administrator, and member accounts.
- Set up recovery point replication flows to a backup vault in another account.
- Analyze the IAM permissions, vault access policies, and AWS KMS key policies required for cross-account copies.
- Build a strategy for retention, copy isolation, restore testing, and cost monitoring.

## 2. Foundational AWS Backup Concepts

### 2.1. Backup Plans and Backup Policies

A **backup plan** is a backup configuration within AWS Backup. A plan contains one or more rules, where each rule defines the execution schedule, target backup vault, and recovery point lifecycle. A rule can also specify copying recovery points to another vault.

A **backup policy** is an AWS Organizations policy type dedicated to AWS Backup. The policy describes backup plans and resource selections to apply to member accounts. When attached to the root, an OU, or an account, AWS Organizations computes an effective policy from inherited parent configurations and child-level overrides.

You can think of it this way:

- A backup plan is the configuration defining when a workload is backed up and where it is stored.
- A backup policy is the mechanism for distributing and governing backup plan configurations across multiple accounts in an organization.

Backup policies standardize how backups are taken. They do not automatically guarantee every resource is protected: resources must be of a supported resource type, match selection criteria, and reside in a Region specified by the policy.

### 2.2. Backup Rules and Backup Selections

A single backup plan can include multiple rules to meet different goals. For example:

- A daily rule retaining backups short-term for operational recovery.
- A weekly or monthly rule retaining backups longer to meet audit requirements.
- A rule creating copies in another Region or a dedicated archive account.

A backup selection determines which resources are included in the plan. You can select by resource type, ARN, or resource tags depending on support. Organizations commonly use tags to classify workloads—for example, **Backup=Daily**, **Backup=Critical**, or **Environment=Production**.

Tags only work if properly attached to resources and if the resource type supports tag-based selection. Define tag naming conventions, valid values, tag owners, and how untagged resources are handled.

### 2.3. Recovery Points and Backup Vaults

A recovery point is a backup captured from a resource at a point in time. AWS Backup stores recovery points inside a backup vault. A vault is a logical container used to organize, control access to, and apply protection controls over backups.

Each vault belongs to a single account and a single Region. A recovery point created in a source vault can be copied to another vault if the resource type and configuration support it. The destination vault can be in another Region, another account, or both.

A vault can carry a resource-based access policy controlling which principals may perform actions on the vault. AWS Backup Vault Lock can enforce minimum/maximum retention durations and protect recovery points from deletions or lifecycle modifications that violate the lock configuration. This is a valuable control when guarding against accidental or malicious backup tampering and deletion.

### 2.4. RPO and RTO Driving Policy Design

Before choosing backup schedules, determine:

- **RPO (Recovery Point Objective):** the maximum acceptable data loss, measured in time. A 24-hour RPO usually requires at least a daily backup, though it also depends on run timing, completion duration, and backup type.
- **RTO (Recovery Time Objective):** the maximum acceptable time to restore a service. RTO depends on data size, restore procedures, target infrastructure, application validation, and cutover actions.

Backup frequency directly affects RPO. Copy placement, accessibility, resource provisioning time, and operational procedures affect RTO. A dense backup schedule does not automatically yield a low RTO if the organization has never tested a restore.

## 3. Managing Centralized Backup Policies with AWS Organizations

### 3.1. Governance Architecture

In AWS Organizations, accounts are organized under a root, OUs, and accounts. Backup policies can be attached at each level:

- Attach at the root when rules must apply broadly across the entire organization.
- Attach at an OU when a group of accounts shares requirements, such as Production, Development, or Shared Services.
- Attach at an account when a specific workload or approved exception requires custom settings.

A common architecture consists of:

1. The management account administers AWS Organizations and enables the required integration with AWS Backup.
2. A dedicated account is registered as the delegated administrator so the backup team manages operations centrally.
3. Backup policies are attached to the root or appropriate OUs.
4. Member accounts receive the effective policy, and AWS Backup deploys the backup plans within those accounts.
5. Recovery points are created in the workload account's vault and then copied to a vault in a separate archive account.

Using a delegated administrator separates service administration from the management account. Delegation does not mean everyone in that account automatically gains access to all resources; you still need proper IAM, service permissions, and governance boundaries.

### 3.2. Prerequisites Before Deployment

Before creating policies, confirm:

- AWS Organizations is configured in a mode supporting AWS Backup integration.
- Trusted access between AWS Organizations and AWS Backup is enabled per service guidance.
- A delegated administrator is registered if the organization uses a separate service administration account.
- Member accounts requiring protection sit in the intended OUs.
- Target Regions are identified and source services support AWS Backup in those Regions.
- The IAM role referenced by the backup selection already exists or is provisioned consistently across member accounts.
- The source backup vault named in the rule already exists in each member account and corresponding Region; a policy only references the vault name and does not replace vault provisioning.
- The destination backup vault, vault access policy, and KMS keys are prepared before enabling copy actions.

Never roll out a broad policy before testing on an OU or non-critical account. Testing reveals role, KMS permission, resource selection, and Region issues without generating a flood of failed backup jobs.

### 3.3. Attaching Policies and Checking Effective Policies

Basic workflow:

1. Open AWS Backup in the service administration account or management account according to your chosen model.
2. Verify AWS Organizations integration and administrative permissions.
3. Author the backup policy with the necessary plans, rules, selections, and Regions.
4. Attach the policy to the target root, OU, or account.
5. Inspect the effective policy of a member account to confirm inheritance behaves as intended.
6. Verify that the backup plan and backup selection appear in the member account.
7. Monitor the first backup job and verify recovery points in the vault.

The effective policy is critical when multiple policy layers exist. Content attached at the root can supply defaults to an OU; an OU-level policy can append or override permitted sections; an account-level policy can fine-tune for one account. Always check the final effective result in the target account rather than looking only at the parent policy.

## 4. Inheritance and Policy Structure Design

### 4.1. Inheritance Rules

AWS Organizations backup policies use a policy inheritance engine. Operators such as **@@assign**, **@@append**, and **@@remove** control how child-level values interact with parent values:

- **@@assign** assigns a value to an attribute at the current policy level; depending on placement, it can replace inherited values.
- **@@append** adds values to an inherited list, suitable for expanding Region lists or resource scopes.
- **@@remove** removes inherited values from a list, if the attribute and policy context support that operation.

A parent-level policy can restrict which operators child policies are allowed to use. This preserves mandatory guardrails—such as preventing a child OU from removing a storage Region or lowering minimum retention.

Do not treat inheritance as simple text concatenation. JSON structure and supported operators have specific semantics per attribute. After every edit, inspect the effective policy and resulting backup plans.

### 4.2. Example Backup Policy Structure

The JSON snippet below illustrates a simplified policy: taking daily backups of EBS volumes in the Singapore Region and storing recovery points in the **OrgDailyVault** vault. This is an educational example for identifying components; before deploying, verify resource types, IAM roles, vault names, and policy schema against your real environment.

~~~json
{
  "plans": {
    "daily-ebs": {
      "regions": {
        "@@assign": ["ap-southeast-1"]
      },
      "rules": {
        "daily": {
          "schedule_expression": {
            "@@assign": "cron(0 17 ? * * *)"
          },
          "start_backup_window_minutes": {
            "@@assign": "60"
          },
          "complete_backup_window_minutes": {
            "@@assign": "180"
          },
          "target_backup_vault_name": {
            "@@assign": "OrgDailyVault"
          },
          "lifecycle": {
            "delete_after_days": {
              "@@assign": "35"
            }
          }
        }
      },
      "selections": {
        "ebs-volumes": {
          "iam_role_arn": {
            "@@assign": "arn:aws:iam::$account:role/AWSBackupDefaultServiceRole"
          },
          "resources": {
            "@@assign": [
              "arn:aws:ec2:*:*:volume/*"
            ]
          }
        }
      }
    }
  }
}
~~~

In this example:

- **plans** holds the centrally managed backup plans.
- **regions** restricts the Regions where the plan is deployed.
- **rules** defines the schedule, backup windows, vault, and retention duration.
- **selections** specifies protected resources and the IAM role used by AWS Backup.
- **$account** is a variable substituted by AWS Organizations with each member account ID during policy application.

The expression **cron(0 17 ? * * *)** runs in UTC. In Vietnam time (UTC+7), that corresponds to 00:00 the next day. When choosing schedules, convert timezones carefully and avoid piling too many workload backups onto the exact same timestamp.

### 4.3. Organizing Policies by Tier

An operationally maintainable structure is:

| Tier | What to Manage | Examples |
|---|---|---|
| Root | Organization-wide baseline requirements | Mandatory Regions, backup copy protection rules, naming standards |
| Production OU | Schedules and retention for critical systems | Daily backups, 35-day retention, copies to vault account |
| Development OU | Cost-efficient schedules for test environments | Weekly backups, 14-day retention |
| Account | Approved exceptions | Workloads with low RPO targets or custom retention periods |

Keep the root policy simple and stable. Express operational differences at the OU level by workload classification. Create account-level exceptions only with clear justification, an approver, and a review expiration date.

### 4.4. Tag Governance and Resource Selection

Tag-based selection applies a uniform policy across many resources without listing every ARN. For instance, a platform team may require workloads to carry **Backup=Daily** or **Backup=Critical**. The backup selection then matches resources bearing the appropriate tags.

To avoid coverage gaps:

- Standardize tag spelling, casing, and allowed values.
- Enforce tagging during resource creation via Infrastructure as Code.
- Use AWS Config or internal compliance checks to detect untagged resources.
- Define clear handling for mistagged or untagged resources.
- Audit the actual list of resources matched by selections into backup plans.

Do not assume every resource type supports tag selection or behaves identically. Check the AWS Backup feature matrix per resource type and Region.

## 5. Cross-Account Backups

### 5.1. Why Use a Dedicated Backup Account?

If a backup vault resides in the same account as the workload, a compromised high-privilege principal could attempt to delete both resources and recovery points within that same administrative boundary. Copying to a separate archive account reduces the risk that a single source-account incident destroys backup copies as well.

A reference model:

- **Workload account:** runs the application and creates initial recovery points.
- **Backup administrator account:** manages policies and monitors backup jobs across accounts.
- **Backup vault account:** owns destination vaults, KMS keys, and strict access policies.

Depending on organization size, the backup administrator and backup vault accounts can be two separate accounts to decouple policy administration from copy ownership. The archive account should allow interactive login and configuration changes to very few individuals.

### 5.2. Recovery Point Copy Flow

The basic flow includes:

1. The backup plan runs in the source account and creates a recovery point in the source vault.
2. The rule's copy action targets the destination backup vault by ARN.
3. AWS Backup validates copy permissions and the destination vault's access policy.
4. The recovery point is copied to the vault in the destination account.
5. The destination copy follows the lifecycle and lock protections applied to that vault.

A copy action can replicate within the same Region to another account, to another Region, or both if the resource type and feature support it. Check limits for each specific resource type before designing copy chains.

Copying is a separate task from the initial backup job. Therefore, monitor copy job statuses, completion times, and recovery points in the destination vault. A successful backup job at the source does not prove the cross-account copy succeeded.

### 5.3. Preparing the Destination Vault

Before enabling copy actions:

- Create the backup vault in the exact destination account and Region.
- Select a KMS key suited to encryption and cross-account sharing requirements.
- Set a vault access policy allowing only designated source accounts or roles to copy into the vault.
- Enable required cross-account backup settings in AWS Backup per service documentation.
- Confirm both source and destination accounts belong to the same AWS Organization, per cross-account backup prerequisites.
- Verify the resource type and Region support cross-account copying.

Vault names may match across accounts, but the ARN must point to the exact destination Region and account ID. Never use the source vault ARN in a copy action when targeting a separate archive account.

### 5.4. Vault Access Policies

A vault access policy is a resource-based policy attached directly to the destination backup vault. It governs which actions principals outside the vault account can perform on the vault.

The simplified example below illustrates allowing a specified source account to copy recovery points into the destination vault:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:root"
      },
      "Action": "backup:CopyIntoBackupVault",
      "Resource": "*"
    }
  ]
}
~~~

**111122223333** is an illustrative source account ID. In production, replace it with the actual account ID or specific principal matching your governance model. You can scope permissions down to a dedicated AWS Backup role rather than granting access to all principals in the source account, provided your IAM design and service flow support it.

The resource-based policy on the destination vault is only one piece of access control. The principal initiating the copy also needs an appropriate identity policy in the source account; the AWS Backup service role needs permissions on the resources; and KMS key policies must allow required encryption/decryption operations. A policy allowing **backup:CopyIntoBackupVault** does not implicitly grant permission to use KMS keys.

### 5.5. KMS and Copy Encryption

AWS Backup encrypts recovery points according to resource-type mechanisms and vault configuration. When copying cross-account, account for both the source recovery point's KMS key and the KMS key used for the destination copy.

Key principles:

- Prefer a customer managed KMS key in the archive account when you need control over key policies and cross-account access.
- Configure key policies and IAM policies so AWS Backup and designated roles have key usage permissions required for copy/restore flows.
- Verify keys exist in the right Region; KMS keys are Regional resources.
- Monitor key state, rotation schedules, key administrators, and recovery procedures if a key is disabled.
- Never delete KMS keys still needed to decrypt recovery points. Backups may exist yet remain unrecoverable if the required key or permission is lost.

Some resource types have specific encryption and copy rules. Do not generalize that every recovery point can be re-keyed in the same manner. Check encryption documentation for that resource type and test restoring from the destination copy.

## 6. Protecting Backups from Deletion or Tampering

### 6.1. Separation of Duties

A workload account should be able to create backups per policy without having administrative rights over the archive vault in another account. The vault account should restrict permissions to delete recovery points, alter vault policies, manage KMS keys, and disable protections.

Roles can be separated as follows:

- Backup operator monitors jobs and resolves routine errors.
- Backup administrator manages policies and account scope.
- Security administrator manages permissions, access controls, and change monitoring.
- Recovery operator executes restores following approved procedures.

Separation of duties reduces the risk that a single compromised credential deletes both the workload and all backup copies.

### 6.2. AWS Backup Vault Lock

AWS Backup Vault Lock enforces retention bounds on recovery points inside a vault. When configuring it, define:

- Minimum retention period.
- Maximum retention period if the organization requires an upper bound.
- Lock mode suited to governance requirements.
- Verification steps before engaging strict lock mode.

Vault Lock helps protect recovery points against deletion or retention shortening that violates configured rules. In Compliance mode, once the configuration grace period ends and the lock takes effect, modifying or removing the lock is strictly prevented. Therefore, test retention periods, review legal requirements, and assess cost before enabling this mode on production vaults.

### 6.3. Logically Air-Gapped Vaults

For critical workloads, organizations can evaluate AWS Backup logically air-gapped vaults as an isolated storage option. This feature adds an extra protection layer for recovery points and can support sharing or recovery through service-supported mechanisms.

Do not adopt this feature simply because of its name. Verify supported resource types, Regions, sharing models, encryption requirements, recovery times, and costs. Perform test restores to ensure isolated copies still meet RTO.

### 6.4. Protecting the Archive Account

The vault account should be secured like core infrastructure:

- Enforce MFA for users with interactive access.
- Use temporary roles and minimize long-lived credentials.
- Restrict principals allowed to modify vault policies or KMS key policies.
- Log changes via CloudTrail and deliver logs to storage with independent administrative control.
- Detect unusual vault deletions, recovery point deletions, key changes, or permission modifications.
- Maintain a controlled break-glass procedure and test it periodically.

## 7. Design Example: Backing Up a Production Workload to a Vault Account

### 7.1. Scenario

A company operates multiple AWS accounts organized into OUs. A Production application runs in **ap-southeast-1** using EC2 and EBS. The platform team wants to enforce a unified backup schedule, keep copies in the application account for 35 days, and retain a copy in a separate vault account.

Illustrative accounts:

| Account | Role |
|---|---|
| **111122223333** | Production Workload |
| **444455556666** | Backup Vault Account |
| **777788889999** | Backup Administrator Account |

These IDs are placeholders. Real architectures must use actual account IDs from your organization's AWS Organizations setup.

### 7.2. Policy Design

The platform team targets the Production OU and attaches a backup policy with these attributes:

- Region: **ap-southeast-1**.
- Selection: Production-scoped EBS volumes or volumes carrying standard backup tags.
- Schedule: daily.
- Source vault: **OrgDailyVault** in the workload account.
- Source retention: 35 days.
- Copy action: copy recovery points to the destination vault in account **444455556666**.
- Destination retention: aligned with recovery needs and organizational retention policy.

The policy is deployed first to a test account. The team checks the effective policy, resulting backup plan, selected EBS volumes, and first backup job. Only after validation is the policy rolled out to the entire Production OU.

### 7.3. Vault Account Configuration

In account **444455556666**, the security team:

1. Creates vault **ProductionArchiveVault** in **ap-southeast-1**.
2. Creates or selects a customer managed KMS key meeting encryption requirements.
3. Attaches a vault access policy permitting designated source account principals to copy into the vault.
4. Configures required IAM and KMS permissions for AWS Backup.
5. Applies Vault Lock if immutable retention has been approved.
6. Enables monitoring on changes to the vault, key, and recovery points.

The copy action inside the backup rule points to an ARN like:

~~~text
arn:aws:backup:ap-southeast-1:444455556666:backup-vault:ProductionArchiveVault
~~~

This ARN merely illustrates the format: service, Region, account ID, resource type, and vault name. Verify the exact ARN in the destination account before placing it in the policy.

### 7.4. Monitoring and Verification

After execution:

1. Verify the backup job in the source account reaches completed status.
2. Verify the copy job completes independently.
3. Check the vault account and confirm the recovery point appears in the right vault, Region, and timestamp.
4. Inspect the encryption key and lifecycle of the recovery point.
5. Execute a test restore from the copy inside the vault account.
6. Record recovery duration, manual steps, and any errors to compare against RTO.

Only when the destination copy can be restored and the application operates properly after restore does the organization have proof that its cross-account backup chain meets recovery objectives.

## 8. Recovery Testing and Ongoing Operations

### 8.1. Successful Backups Are Not Enough

A successful backup job only indicates the service finished creating a backup according to job status. It does not prove the application can boot, data is consistent, or operators have the permissions required to restore during an emergency.

A testing plan should verify:

- Recovery points exist in the right account, Region, and vault.
- Recovery roles can access both recovery points and KMS keys.
- Restored resources receive required network, IAM, and dependency configurations.
- Application data is readable and passes consistency checks.
- Restore time and cutover steps meet RTO.
- Procedures remain executable when the source account is unavailable.

### 8.2. Testing by Resource Type

Not all resource types share the same restore procedure. EBS volumes may need attaching to an EC2 instance; RDS requires checking endpoints, parameter groups, and application connectivity; DynamoDB requires verifying tables, permissions, and items; EFS requires verifying mount targets and access permissions.

Maintain dedicated runbooks for each workload group. Runbooks should specify the executing account, Region, vault, recovery point, KMS key, role, target infrastructure, validation steps, and exit criteria.

### 8.3. AWS Backup Restore Testing

For supported resource types, AWS Backup restore testing can schedule automated recovery checks. A restore testing plan specifies testing frequency, recovery point scope, and validation criteria. Verify supported resource types, Regions, and configurations before operationalizing.

Restore testing should run inside a controlled test account or VPC. Set resource limits and automated cleanup procedures to avoid unexpected costs. Do not expose sensitive production data in test environments without equivalent security controls.

### 8.4. Monitoring Backup and Copy Jobs

Monitor at a minimum:

- Failed, aborted, or overdue backup jobs.
- Failed copy jobs or missing recovery points in the destination vault.
- Resources falling outside backup selections.
- Modifications to backup policies, backup plans, selections, or vault policies.
- Changes to KMS keys, key policies, or key states.
- Recovery points nearing expiration without meeting retention requirements.
- Failed restore tests or RTO breaches.

AWS Backup exposes job statuses and integrates with AWS monitoring and event services. EventBridge can route job events to SNS, Lambda, or incident management platforms. CloudTrail audits administrative activity and permission changes. Test alerting pipelines with a simulated failure rather than trusting rule creation alone.

## 9. Cost and Optimization

### 9.1. Cost Components

Backup architecture costs can include:

- Backup storage consumed in source and destination vaults.
- Cross-Region or cross-account copy storage and transfer.
- Tiered storage or service-specific recovery point charges.
- Retrieval, restore, or data transfer charges where applicable.
- KMS and supporting service charges.
- Temporary resources provisioned during restore testing.

Copying a recovery point creates additional stored data at the destination. Keeping copies across multiple accounts and Regions improves resilience while increasing cost. Model costs based on resource counts, frequency, retention duration, data churn rate, and copy count.

### 9.2. Retention Policies by Criticality

Avoid applying the longest retention to all resources. Group workloads as follows:

| Workload Group | Example Schedule | Retention Goal |
|---|---|---|
| Critical Production | Daily plus periodic copies | Meet recovery and audit requirements |
| Standard Production | Daily | Recover from routine operational errors |
| Development/Test | Weekly or pre-change milestones | Reduce cost while still supporting needed recovery |
| Long-term Archival | Custom schedule and regulatory mandate | Meet approved retention periods |

These schedules are design examples. Frequencies and durations must be driven by RPO/RTO, data regulations, resource-type capabilities, and current AWS pricing.

### 9.3. Controlling Data Growth

To manage costs:

- Remove obsolete selections after workloads are decommissioned.
- Audit overlapping backup plans between organizational policies and local plans.
- Set explicit lifecycles for both source recovery points and destination copies.
- Evaluate cold storage when supported by the resource type and retention duration.
- Track storage usage by account, Region, and vault.
- Use AWS Cost Explorer, AWS Budgets, and cost reports to detect anomalies.

Never shorten retention solely to fix a budget overrun without first assessing impacts on recovery and compliance obligations.

## 10. Common Pitfalls

| Pitfall | Consequence | Remediation |
|---|---|---|
| Attaching a policy at root without checking effective policy | Child accounts may receive unintended configurations | Inspect effective policy and backup plans in member accounts |
| Using tags when resources lack tags or have wrong values | Resources are omitted from selections | Standardize tags and audit the selected resource list |
| Backup role missing or lacking permissions | Backup jobs fail | Create role with proper trust policy and least-privilege permissions for resource types |
| Destination vault does not permit copies | Copy jobs fail despite successful source backups | Check vault access policy and source principal IAM policies |
| KMS key denies required actions | Cannot copy or restore recovery points | Inspect key policy, IAM policy, Region, and key state |
| Confusing backup jobs with copy jobs | Missing off-account copies go unnoticed | Track both job types and verify recovery points in the destination vault |
| Allowing source account to administer destination vault | Compromised source account can affect copies | Separate accounts, restrict permissions, and consider Vault Lock |
| Enabling strict Vault Lock without testing | Difficult to fix retention mistakes | Test, complete legal review, and approve before locking |
| Never running a restore | Unknown restore duration and data consistency | Schedule restore tests and record actual RTO |
| Picking schedules in local time while forgetting UTC | Backups run off-schedule or collide | Convert cron to UTC and stagger run schedules |

## 11. Checklist for Implementing Centralized and Cross-Account Backup Policies

### Before Implementation

1. Classify workloads by criticality, RPO, and RTO.
2. Identify accounts, OUs, and Regions requiring protection.
3. Verify resource types are supported by AWS Backup in target Regions.
4. Standardize tags and selections.
5. Designate management account, delegated administrator, and backup vault account.
6. Design schedules, lifecycles, vaults, and copy actions.
7. Prepare IAM roles, vault access policies, and KMS key policies.
8. Evaluate Vault Lock and retention requirements.

### During Implementation

1. Enable trusted access and configure the delegated administrator if used.
2. Pilot the policy on a limited OU or test account.
3. Inspect the effective policy and generated backup plans.
4. Verify backup selections match intended resources.
5. Run backup jobs and confirm recovery points in the source vault.
6. Run copy jobs and confirm recovery points in the destination vault.
7. Verify encryption, access controls, and lifecycles on both sides.

### After Implementation

1. Schedule restore tests according to workload criticality.
2. Monitor backup jobs, copy jobs, and policy changes.
3. Audit unprotected resources or resources dropped from selections.
4. Periodically review vault and KMS key access permissions.
5. Reconcile actual costs against budgets and retention terms.
6. Update runbooks when accounts, Regions, resource types, or recovery targets change.

## 12. Conclusion

Centralized backup policies allow an organization to enforce consistent backup rules across many AWS accounts via AWS Organizations. By structuring policies across root, OU, and account tiers, platform teams can standardize schedules, Regions, selections, and retention while using effective policies to verify final configurations per account.

Cross-account backups provide an extra defense layer if a workload account is compromised or suffers a severe incident. For copies to succeed, prepare destination vaults, vault access policies, IAM roles, and KMS keys carefully, and monitor copy jobs independently of source backup jobs. Separating administrative privileges and locking down vaults minimizes the chance that a source-account incident destroys backup copies.

A backup strategy is reliable only when the organization can restore data and applications within target timelines. Combine centralized policies, isolated off-account copies, retention controls, continuous monitoring, and regular restore testing to turn backups into verifiable recovery capability.
