# Backup Vaults and Protecting Backups from Unauthorized Deletion

In the `CLOUD_PROVIDERS_GCP` module, learners progress from project management, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases, then apply that knowledge to protect resources, automate releases, and monitor reliability and cost. The **Backup and Disaster Recovery** chapter raises a vital question: if an operator clicks delete by mistake, a service account is compromised, or ransomware tries to destroy data, will backups still exist and remain recoverable?

This lesson introduces **Backup vaults** in **Google Cloud Backup and DR**, specifically **enforced retention**, **retention lock**, **project liens**, **IAM separation of duties**, and **access restrictions**. You will design an isolated backup repository, configure a backup plan for a test disk, verify protection status with read-only checks, and build a controlled recovery workflow.

> **Operational warning:** Enforced retention can retain data and continue incurring charges for the entire protection window. Once a retention lock takes effect, you cannot lower the retention period or remove the lock. Do not test destructive actions, multi-year retention locks, or real resource purchases in production without an approved change. The lab uses a staging project and only guides safe policy verification.

## 1. The threat: losing source data and losing backups too

Backups are useful only if they remain intact **when a restore is needed**. Consider at least four scenarios (and related controls):

| Threat | Example | What to prevent |
| --- | --- | --- |
| Accidental deletion | An administrator deletes a disk, backup, or project during cleanup. | Recovery points cannot be deleted before their protection expires. |
| Ransomware attack | A privileged account is compromised and the attacker deletes backups as well. | Isolate production operational permissions from vault management permissions; enforce retention. |
| Policy tampering | An attacker lowers retention to one day and waits for expiration. | Lock the ability to **decrease** enforced minimum retention after the effective date. |
| Deleting the vault project | Someone with Resource Manager permissions tries to delete the project to bypass retention. | Project liens, separate IAM, and multi-party approval for lien admin actions. |
| Unauthorized restore | An unauthorized user attempts to restore data to another project. | Restrict backup/restore scope, IAM, audit logs, and approvals. |
| Mismanaged encryption keys | CMEK is disabled or keys become inaccessible during restore. | Independent key lifecycle governance, restore testing, and KMS admin separation. |

**Do not confuse:** Backups, snapshots, replicas, and high availability solve different goals. Replicas can propagate deletion errors; HA reduces infrastructure downtime, but does not necessarily preserve valid data from before a human error occurred. Vaulted backups add recovery points with an independent lifecycle and protection policy.

## 2. What is a backup vault?

In Google Cloud Backup and DR, a **backup vault** is a Google-managed storage resource capable of **isolation, immutability during enforced retention, and protection against early deletion**. It is not an arbitrary Cloud Storage bucket named "vault." A backup vault has its own resource model and API:

- **Backup vault:** top-level container storing location, minimum enforced retention, retention inheritance, lock, encryption, and access restriction configuration.
- **Data source:** child resource representing a protected target, such as a Compute Engine disk or instance; Backup and DR creates it once a compatible backup runs.
- **Backup:** a specific recovery point linked to a data source with expiration/protection timestamps.
- **Backup plan:** policy defining **when to back up and how long to keep** for a supported workload type.
- **Backup plan association:** link between a specific resource and a backup plan for automated backups.
- **Backup vault service agent:** Google-managed identity used to perform necessary operations on resources in protected projects.

~~~mermaid
flowchart TB
  ORG[Google Cloud Organization]
  ORG --> HUB[Backup hub project]
  ORG --> SPOKE[Workload project]
  HUB --> VAULT[Backup vault]
  HUB --> PLAN[Backup plan / daily rule]
  VAULT --> SOURCE[Data source: disk-orders]
  SOURCE --> B1[Recovery point 1]
  SOURCE --> B2[Recovery point 2]
  PLAN --> ASSOCIATION[Backup plan association]
  ASSOCIATION --> DISK[Compute Engine disk]
  SPOKE --> DISK
  VAULT --> IAM[Vault IAM + access restriction]
  VAULT --> RETENTION[Minimum retention + lock]
  HUB --> LIEN[Project lien]
  RETENTION --> B1
  RETENTION --> B2
~~~

### 2.1. Workloads and management interfaces

Workloads supported by **Google Cloud console-based backup plans** include Compute Engine instances, Compute Engine disks, Cloud SQL instances, AlloyDB clusters, and Filestore instances, depending on type and location. Other workloads like Google Cloud VMware Engine, Oracle, or SQL Server use the **appliance management console** model with different limits. Do not assume identical configuration, locations, or CMEK support across all workloads.

Cloud SQL/AlloyDB transaction log backups used for PITR may be stored **outside the backup vault**. Therefore, claiming "all recovery data and all transaction logs are kept immutable inside the vault" is incorrect without checking each product and configuration. Identify precisely which components are protected by the vault.

### 2.2. Centralized hub/spoke or one vault per project?

| Model | Organization | Benefits | Trade-offs |
| --- | --- | --- | --- |
| **Centralized hub/spoke** | Backup vaults/plans in a backup-team-managed project; workloads in service projects. | Separates privileges from workload operations teams; centralized retention/audit governance. | Must grant service agent permissions across projects and clarify operational ownership. |
| **Decentralized** | Each workload project has its own vault and plans. | Self-managed by app teams, less cross-project IAM. | A compromised principal can control multiple components in the same project; policy drift is easier. |

To defend against ransomware and unauthorized deletion, consider a **dedicated backup hub project** with administrators, security policies, and lifecycles separate from source projects. Hub and spoke projects can still live in the same organization to apply appropriate access restrictions.

## 3. Two types of retention that must be distinguished

A backup is governed by **assigned retention** in the backup plan and **enforced retention** on the vault. They are not synonymous.

| Concept | Where defined | Meaning |
| --- | --- | --- |
| **Assigned retention** or `Delete backups after` | Backup rule in the backup plan | Intended duration to keep a backup; once expired, the system cleans it up automatically per policy. |
| **Minimum enforced retention** or `Prevent backup deletion` | Backup vault | Mandatory floor: nobody may manually delete a backup before this protection period elapses. |
| **Retention inheritance mode** | Chosen at vault creation | Determines whether each backup's deletion protection follows the vault minimum or the backup rule expiration. |
| **Retention lock** | Vault setting with an effective date | After the effective date, minimum enforced retention cannot be **reduced**; it can only be increased. |

A vault's minimum enforced retention can be configured from **0 days up to 99 years**, though individual resource types/backup rules have **specific limits**. A value of 0 provides no meaningful deletion protection for backups; for critical data, set a value greater than 0 per business and regulatory requirements.

A backup rule for a resource using a vault must specify retention **at least equal to the minimum enforced retention**. Invalid example: vault minimum of 30 days paired with a 7-day backup plan rule.

### 3.1. Two inheritance modes

When creating a vault, choose one of two modes:

1. `inherit-vault-retention` (default): the backup's **enforced retention** window inherits the vault minimum. The backup plan still manages the assigned expiration, though manual deletion prohibition may be shorter than assigned retention.
2. `match-backup-expire-time`: each backup's deletion protection extends until **backup expiration** per the backup plan's retention rule. This is stronger when you want to prevent manual deletion for the **entire lifecycle** of the backup, rather than only the initial days.

The inheritance mode **cannot be changed after vault creation**. Decide during vault design. Compliance environments often consider `match-backup-expire-time`, after reviewing costs and backup types used.

### 3.2. Example with 7 days and 30 days

Suppose:

- Vault minimum enforced retention: **7 days**.
- Backup rule: retain recovery points for **30 days**.
- Backup created on 01/11; normal expiration is 30 days later.

| Vault mode | Window blocking manual deletion | Interpretation |
| --- | --- | --- |
| `inherit-vault-retention` | At least the first 7 days | After the enforced minimum passes, policy may permit manual deletion before expiration subject to remaining permissions/rules. |
| `match-backup-expire-time` | Until the full 30-day backup retention ends | Cannot be manually deleted for all 30 days; system deletes upon backup expiration. |

**Security takeaway:** Never see "backup plan keeps 30 days" and conclude "30 days immutable." Inspect the **vault inheritance mode and each backup's actual enforced retention timestamp**.

### 3.3. Changing minimum retention

Per Backup and DR documentation:

- **Unlocked** vault: authorized users can increase or decrease minimum retention for **backups created after the change**.
- **Locked** vault: minimum retention can only be increased, never decreased.
- Changing the vault minimum **does not shorten or extend enforced retention already recorded on existing backups**.
- If the new minimum exceeds a backup plan's retention, **console-based plans** may block the change; check and update compatible plans through proper procedures.

Thus, lowering the minimum on an unlocked vault does not immediately release existing backups created under a longer enforced retention. However, it leaves **future backups** less protected. That is why locking policy matters against prolonged attacks.

## 4. Retention lock: preventing policy tampering to delete backups later

Enforced retention prevents early deletion of individual backups. **Retention lock** protects the **vault's minimum enforced retention** from being lowered after the lock effective date.

The lock lifecycle has three main states:

~~~mermaid
flowchart LR
  U[Unlocked] -->|Set lock effective date| P[Lock pending]
  P -->|Effective date reached| L[Locked]
  P -->|Authorized edit before effective date| U
  L -->|Can increase minimum only| L
  L -.->|Cannot remove lock or reduce minimum| X[Denied]
~~~

- **Unlocked:** minimum can be edited per permissions and conditions.
- **Pending lock:** an effective date is set; before that date, the lock can still be adjusted or removed via supported controls.
- **Locked:** once the effective date arrives, **neither the lock can be removed nor the minimum lowered**, even by a Project Owner. It can only be increased.

This is a security decision with long-term consequences. If a vault accidentally locks an overly long minimum retention, there may be no way to reduce it before the period expires. Use **multi-person change review** when setting or raising retention, with durations approved by Legal, Security, and Backup owners.

In a lab, you can create an **unlocked** test vault to inspect the configuration, then examine the lock screen read-only. **Do not confirm a permanent effective lock during this lesson.** If your organization must prove retention lock behavior, run it in a dedicated compliance test environment with designated approvers and awareness of irreversible costs.

## 5. Project liens prevent deleting the entire vault project

If someone with `resourcemanager.projects.delete` deletes the project hosting the vault, backup-level retention needs an extra safeguard. A **project lien** is a Resource Manager guardrail preventing project deletion while the lien remains active.

Starting **November 1, 2026**, Backup and DR automatically applies a **project-level lien** to projects containing backup vaults with **backups protected by enforced retention**. Verify the actual status on the hub project, as vaults without protected backups yet or special environments may not meet auto-lien conditions. For test projects without enforced retention, manual liens may be required per governance guidelines.

### 5.1. A lien is not invulnerable

An appropriately privileged principal can still attempt to **remove a lien**, so a lien is one defense layer among several. Security teams should restrict `roles/resourcemanager.lienModifier` and use **Privileged Access Manager (PAM)** to require **multi-party approval** before granting temporary elevated privileges.

| Component | Protects | Limitations |
| --- | --- | --- |
| Enforced retention | Blocks deletion of backups within their protection window. | Does not block all IAM changes or future backup policies. |
| Retention lock | Blocks reducing minimum retention later. | Does not replace timely backup creation; protection windows still expire. |
| Project lien | Blocks deleting the project holding the vault. | Can be removed by a sufficiently privileged principal; requires PAM/SoD. |
| Vault IAM | Restricts who administers vaults, restores, and views backups. | Overly broad roles/misconfiguration remain a risk. |
| Access restriction | Constrains valid backup/restore sources and targets. | Does not replace IAM and must be chosen at vault creation. |
| Restore drill | Verifies backups are actually usable. | Does not block destructive actions; requires independent procedures. |

Example read-only lien check with gcloud:

~~~bash
gcloud alpha resource-manager liens list
~~~

In environments using different CLI versions, check available syntax/flags to filter the target project accurately before drawing conclusions. Never remove a lien in production just to prove project deletion is possible. During drills, inspect lien metadata and audit who is authorized to modify it.

## 6. Vault access restrictions: limiting where backups and restores can occur

At vault creation, the **access restriction** setting controls which projects/organizations may use the backup vault as a source or destination for backups/restores. This value **cannot be changed after creation**.

| gcloud mode | Meaning | Best suited for |
| --- | --- | --- |
| `within-project` | Only back up and restore resources within the same project. | Standalone per-project vaults. |
| `within-org` | Restricts to resources within the current organization; default if unspecified. | Multi-project hub/spoke within one organization. |
| `within-org-but-unrestricted-for-ba` | Organization-scoped for console-managed resources; exception for backup-appliance-managed resources. | Organizations still using appliance management console with assessed risk. |
| `unrestricted` | Allows usage across other projects/organizations per capabilities and IAM. | Only when an explicit, approved cross-organization requirement exists. |

For a centralized backup project in the same organization as workload projects, `within-org` is usually the sensible starting point. Choosing `within-project` will block backups from other spoke projects even if the service agent has IAM permissions. Choosing `unrestricted` widens the boundary unnecessarily and demands stricter governance of restore destinations.

Access restriction is **not an automatic allow mechanism**. IAM is still required for principals, the vault service agent, backup plans, and target resource permissions.

## 7. Permissions and hub/spoke separation of duties

A tamper-resistant deployment must separate who can **administer vaults**, **create/maintain backups**, **perform restores**, and **alter project governance**.

### 7.1. Roles and least privilege

| Group/persona | Typical permissions needed | Scope |
| --- | --- | --- |
| Backup security administrator | `roles/backupdr.backupvaultAdmin` or scoped custom role | Project holding the vault. |
| Vault/backup viewer | `roles/backupdr.backupvaultViewer` | Project holding the vault. |
| Backup operator | Backup and DR roles for managing/applying backup plans and triggering resource backups | Plan management project and appropriate source projects. |
| Restore operator | `roles/backupdr.restoreUser` and target resource creation permissions | Approved restore project only. |
| Backup vault service agent | E.g., `roles/backupdr.diskOperator` or `roles/backupdr.computeEngineOperator` per resource type | Protected workload project. |
| Project lien administrator | `roles/resourcemanager.lienModifier` via PAM/JIT | Hub project. |
| Security auditor | Read access to IAM/audit logs and relevant backups, no delete rights | Hub/spoke projects. |

Role names are examples from Backup and DR IAM documentation; verify exact permissions for **each resource type and operation** in the official permissions table. Do not grant `roles/backupdr.admin` to an entire application team if they only need to trigger backups or view status. **Service agent** roles must not be assigned to human users or ordinary service accounts.

### 7.2. Vault service agent and cross-project permissions

Each backup vault has a Google-managed service agent. When the vault lives in a hub project and the source disk lives in a spoke project, the service agent requires the appropriate role **on the spoke project**.

Example for a **Compute Engine disk**, after retrieving the exact service agent email from the vault details page:

~~~bash
gcloud projects add-iam-policy-binding WORKLOAD_PROJECT_ID \
  --member="serviceAccount:BACKUP_VAULT_SERVICE_AGENT_EMAIL" \
  --role="roles/backupdr.diskOperator"
~~~

For a **Compute Engine VM instance** instead of a disk, the documented role may be `roles/backupdr.computeEngineOperator`. Do not apply a VM role blindly to disks or Cloud SQL. When a disk/VM sits in the **same project as the vault**, granting conditions may differ; consult resource-type-specific docs.

If backup or restore fails with `PERMISSION_DENIED`, verify the exact service agent email, project, backup plan association, role, and restore destination permissions. Never fix it by granting organization-wide Owner and forgetting to revoke it.

### 7.3. Attack paths via management plane instead of deleting individual backups

A compromised account may attempt to:

- Delete existing backups (blocked by enforced retention).
- Lower retention for future backups (blocked by retention lock if locked).
- Detach the backup plan association from a workload to **stop creating new backups**.
- Remove the project lien or delete the project if privileged.
- Disable CMEK keys to make data hard or impossible to restore.
- Exfiltrate data by restoring to another project.
- Disable alerts, log sinks, or alter log retention.

Therefore, an anti-ransomware program cannot merely count existing backups; it must monitor **backup schedule compliance**, **security configuration changes**, **IAM drift**, **service agents**, **key lifecycle**, and **restore readiness**.

## 8. Choosing location, encryption, and retention by workload

Backup vaults can be created in supported locations, including regional, cross-regional, or multi-regional. Location support depends on workload type:

| Workload | Regional/cross-regional | Multi-region | Notes |
| --- | --- | --- | --- |
| Compute Engine VM instances | Yes, per location compatibility | Yes in supported multi-regions | Evaluate in-VM application consistency. |
| Compute Engine disks | Yes | Yes | Disk backup differs from full-VM backup. |
| Cloud SQL instances | Yes | Yes | PITR transaction logs have separate storage behavior outside the vault. |
| AlloyDB clusters | Yes with specific location conditions | No per current list | Check source/vault region and retention range. |
| Filestore instances | Yes | No per current list | Restrictions by resource and location. |

Regional/cross-regional vaults protect against single-zone failures via redundant storage; multi-region vaults help defend against full-region outages for supported workloads. Choosing multi-region does not mean RTO=0 or automatic app recovery; restoration still needs tooling, permissions, and runbooks.

### 8.1. Protecting with CMEK

By default, backup data is encrypted at rest using Google-managed keys. If customer-controlled keys are required, **CMEK** can be used where supported by the workload/vault location. However:

- Depending on resource type, backup vault CMEK support has limitations; check dedicated docs and source encryption compatibility.
- **Select CMEK only at vault creation**; do not treat it as an attribute you can toggle freely later.
- Key location must be compatible with the vault.
- Disabling/destroying the key can render backups un-restorable even while retention remains active.
- Separate Cloud KMS admins from Backup and DR admins and monitor key rotation/destruction schedules.

**Immutability does not equal recoverability**: if backups are untouched yet the decryption key is lost, restore still fails.

### 8.2. Choosing retention and estimating cost

Hypothetical example based on data requirements:

| Environment | Backup frequency | Assigned retention | Minimum enforced retention | Lock decision |
| --- | --- | --- | --- | --- |
| Lab staging | Daily | 30 days | 7 days | Do not lock permanently; inspect status UI only. |
| Production orders | Daily + weekly/monthly per policy | 35–90 days or regulatory | Depends on RPO/compliance; may match full expiration | Review with Security/Legal; lock after approval. |
| Legal/forensics | Per specific retention mandate | Potentially long | Per legal hold policy | Requires dedicated decision and sign-off. |

Numbers here are **design examples**, not substitutes for actual retention policy. Backup plan retention has its own hourly/daily/weekly/monthly and resource-type limits. Do not enter 99 years for a daily rule just because the vault maximum is 99 years.

Retention length drives storage and data transfer fees; data protected by enforced retention cannot be deleted early to save money. Calculate storage consumption, daily churn, retention, storage location, restore operations, and network fees in the Pricing Calculator before locking.

## 9. Safe lab practice: creating an early-deletion-resistant vault

**Lab architecture:** one `BACKUP_HUB_PROJECT_ID` holding vaults/plans; one `WORKLOAD_PROJECT_ID` with a simulated Compute Engine disk. Both projects sit in the same organization; illustrative region `asia-southeast1`. Use only an approved project with budgets/alerts; resource creation commands **will incur costs** if executed.

### 9.1. Prepare APIs and permissions

In the hub project, enable the Backup and DR API using an authorized admin principal:

~~~bash
gcloud services enable backupdr.googleapis.com \
  --project=BACKUP_HUB_PROJECT_ID
~~~

Enable required Compute Engine APIs and services in the workload project per organizational workflow. The vault creator needs `roles/backupdr.backupvaultAdmin` on the hub project; plan/association creators and disk accessors need their respective permissions, not necessarily all held by the same person.

### 9.2. Create vault: 7-day minimum, lock aligned to 30-day rule

CLI example strictly for a lab environment permitted to create backups:

~~~bash
gcloud backup-dr backup-vaults create orders-lab-vault \
  --project=BACKUP_HUB_PROJECT_ID \
  --location=asia-southeast1 \
  --backup-min-enforced-retention=7 \
  --backup-retention-inheritance=match-backup-expire-time \
  --access-restriction=within-org
~~~

Parameter explanation:

- `--backup-min-enforced-retention=7` sets a 7-day floor against early deletion.
- `--backup-retention-inheritance=match-backup-expire-time` protects each backup **until rule expiration**, such as 30 days.
- `--access-restriction=within-org` allows cross-project usage within the same organization while still enforcing IAM.
- This example **does not set a permanent retention lock**. To lock the minimum with an effective date, do so after security review via the vault details/Console and formal approval.

Upon vault creation, Backup and DR returns an operation ID. Check asynchronous status with:

~~~bash
gcloud backup-dr operations describe FULL_OPERATION_ID
~~~

Once the operation completes, inspect the vault configuration and status:

~~~bash
gcloud backup-dr backup-vaults describe orders-lab-vault \
  --project=BACKUP_HUB_PROJECT_ID \
  --location=asia-southeast1
~~~

Verify name, location, minimum enforced retention, inheritance mode, access restriction, lock status, and service agent. If `match-backup-expire-time` was misconfigured, **the mode cannot be changed on the existing vault**; create a new vault per approved design without deleting a vault holding protected backups.

### 9.3. Create a backup plan for the sample disk

Example creating a daily plan retaining **30 days**; the backup rule sits in the source disk's region:

~~~bash
gcloud backup-dr backup-plans create disk-daily-30d \
  --project=BACKUP_HUB_PROJECT_ID \
  --location=asia-southeast1 \
  --backup-vault=orders-lab-vault \
  --resource-type=compute.googleapis.com/Disk \
  --backup-rule='rule-id=daily,retention-days=30,recurrence=DAILY,time-zone=UTC,backup-window-start=0,backup-window-end=4' \
  --max-custom-on-demand-retention-days=30
~~~

The rule runs within the 00:00–04:00 UTC window per backup plan time, not guaranteed at exactly 00:00. Ensure the disk is in a region supported by the backup plan, and the 30-day policy exceeds the 7-day vault minimum. With `match-backup-expire-time`, backups under this rule cannot be manually deleted before roughly 30 days elapse.

If your CLI version uses updated `--backup-rule` syntax, check `gcloud backup-dr backup-plans create --help` and latest docs; never alter production policies just to make a lab command run.

### 9.4. Associate the disk with the plan

Retrieve the **numeric ID** of the test disk:

~~~bash
gcloud compute disks describe TEST_DISK_NAME \
  --zone=asia-southeast1-a \
  --project=WORKLOAD_PROJECT_ID \
  --format="value(id)"
~~~

Then an authorized user creates the association in the **workload project**:

~~~bash
gcloud backup-dr backup-plan-associations create orders-disk-assoc \
  --project=WORKLOAD_PROJECT_ID \
  --location=asia-southeast1 \
  --resource=projects/WORKLOAD_PROJECT_ID/zones/asia-southeast1-a/disks/DISK_NUMERIC_ID \
  --resource-type=compute.googleapis.com/Disk \
  --backup-plan=projects/BACKUP_HUB_PROJECT_ID/locations/asia-southeast1/backupPlans/disk-daily-30d
~~~

Replace `DISK_NUMERIC_ID` with the value returned by describe. In centralized hub/spoke setups, grant `roles/backupdr.diskOperator` to the exact vault service agent on the workload project **before** running if required by the disk type. One association protects one disk; backing up an entire VM instance and its attached disks requires a Compute Engine Instance plan or multiple disk associations as designed.

### 9.5. Verify results using read-only operations

After the backup job completes:

1. Open **Backup and DR → Vaulted backups** in the Console.
2. Select the sample disk data source and inspect the backup list, creation time, assigned expiration, enforced retention, and backup state.
3. Cross-check the backup rule, vault mode, and earliest eligible deletion timestamp.
4. Open vault details and verify minimum, inheritance, lock status, and access restriction.
5. Check whether the hub project has a lien (if protected backups qualify for auto-lien).
6. Record status/metadata evidence; **no need to call the delete API**.

Example command to list backups:

~~~bash
gcloud backup-dr backups list \
  --backup-vault=orders-lab-vault \
  --data-source=DATA_SOURCE_ID \
  --location=asia-southeast1 \
  --project=BACKUP_HUB_PROJECT_ID
~~~

`DATA_SOURCE_ID` is retrieved from Vaulted backups/data sources after the first backup appears. If no backups exist yet, do not treat an empty `list` output as working protection: check job status, association, schedule, API/IAM, and backup window timing.

## 10. Designing non-destructive tests against unauthorized deletion

Tests should verify **security properties** in a controlled manner:

| Test ID | What to verify | Safe method | Expected result |
| --- | --- | --- | --- |
| BV-01 | Vault enforces retention | `backup-vaults describe` + Vaulted backups metadata | Minimum > 0; new backups carry appropriate enforced periods. |
| BV-02 | Correct inheritance mode | Inspect inheritance field and backup expiration | Mode is `match-backup-expire-time` if full-lifecycle protection is required. |
| BV-03 | Lock status | Inspect vault details | `Locked` once effective date passed, or `Unlocked` if lab lock unapproved. |
| BV-04 | IAM separates operators | Review IAM policies on hub/spoke, principals, and roles | Workload users cannot modify vault/retention. |
| BV-05 | Cross-project access not overly broad | Inspect `within-org` restriction and service agent bindings | External organizations are not permitted. |
| BV-06 | Project lien protects hub | List liens, review Lien Modifier permissions and PAM | Lien present when eligible; nobody can remove unilaterally. |
| BV-07 | Backups unmodified after creation | Read backup metadata and audit logs | No out-of-policy modification/deletion actions on backups. |
| BV-08 | Restore is feasible | Create new restored resource in isolated staging, verify checksums | Data readable; RTO/RPO recorded. |
| BV-09 | Stopping protection does not erase old backups | Review association and existing backups | Removing association affects future backups only; existing points retain their own retention. |

If a **negative delete test** is required, use a separate test vault/backup with approval, short retention, and budget; never test `gcloud backup-dr backups delete` on real data. Returned error codes on denied attempts may hit IAM before reaching retention policy (e.g., `PERMISSION_DENIED` vs. precondition error), so do not hard-code a single HTTP status code as proof.

### 10.1. Does editing retention affect existing backups?

If an administrator lowers the minimum from 7 to 3 days **before locking**, backups already created with a 7-day enforced retention **are not shortened**. Tests should compare metadata of backups created before vs. after, rather than checking only the current vault minimum. Only backups created afterward follow the new setting under applicable rules.

Once a lock is effective, attempts to lower the minimum must be rejected by the system. However, missing IAM permissions might reject the request upfront; to prove **retention lock** enforcement rather than insufficient IAM, coordinate testing with the security owner and inspect the exact rejection reason.

## 11. Recovery drills: immutable backups must still be usable

A backup protected from deletion that cannot be restored **fails DR objectives**. Track two metrics:

- **RPO:** acceptable data loss target, e.g., 24 hours with daily backups if no supplementary mechanism exists.
- **RTO:** time to restore workload operations, including restore permissions, resource provisioning, networking, data verification, and traffic cutover.

Minimum staging disk drill:

1. Pick a successful recovery point inside the vault.
2. Create a **new disk** in an authorized staging project/zone—never overwrite the source disk.
3. Ensure the vault service agent / restore operator has permissions in the restore project.
4. Attach the new disk to an isolated test VM; mount **read-only** if forensic evidence preservation is needed.
5. Verify filesystem, checksums, or marker files; for database apps, verify application consistency rather than mere file existence.
6. Record duration from restore request to successful validation; update the runbook and clean up staging resources per approval.

For Cloud SQL/AlloyDB, restore workflows differ from disks and may involve PITR logs outside the vault. Drill specifically for the database engine, credentials, CMEK, and networking. Never extrapolate a disk restore test to claim similar RPO/RTO for the entire database tier.

## 12. Monitoring, auditing, and early warning

To detect tampering attempts **before data loss occurs**, combine backup job tracking, configuration changes, and IAM activity.

| Signal | Detection | Action |
| --- | --- | --- |
| Backup schedule compliance | Missed backups, failed jobs, missing new recovery points. | Investigate policy, service agent permissions, quotas, workload health. |
| Vault minimum/lock/access change | Attempt to alter retention or vault governance. | Alert Security/Backup owner; cross-check change ticket. |
| Backup plan association deleted | Workload stops producing new backups. | Restore protection with approval and inspect existing backups. |
| Service agent IAM drift | Backup/restore fails with 403 or overly broad roles granted. | Fix bindings per resource type; perform periodic access reviews. |
| Project lien removed or new lienModifier IAM | Risk of deleting the hub project. | Inspect PAM approvals; trigger high-priority alert. |
| CMEK disable/destroy scheduled | Backups may become undecryptable on restore. | Escalate to KMS owner; block unauthorized destruction. |
| Abnormal backup bytes/retention growth | Rising cost or misconfigured retention rule. | Review backup expiration, data source count, cost/billing reports. |
| Failed restore drill or RTO breach | Backups fail recovery requirements. | Fix runbook, permissions, location, dependency recovery. |

In Cloud Logging, filter **Admin Activity audit logs** for the Backup and DR API; illustrative example:

~~~text
protoPayload.serviceName="backupdr.googleapis.com"
protoPayload.methodName:("backupVaults" OR "backupPlans" OR "backupPlanAssociations")
~~~

Actual syntax and `methodName` values may vary by API version; start from a real log entry and build a matching field filter. Read/restore operations may require Data Access audit logs enabled and corresponding Logs Viewer/Private Logs Viewer roles. Never label "no logs found" as "no access occurred" if that Audit Log category was not enabled.

Route alerts for backup failures, protection removal, IAM changes, and lien changes to an on-call channel independent of the production workload. If an attacker compromises the production project, dashboards stored solely inside that project cannot be trusted as the sole source of truth.

## 13. Cost, enforced retention commitments, and decommissioning lifecycle

Enforced retention is a **data storage commitment**, not a free security rule. If backups must be kept for 30 days, you cannot delete them on day three to trim bills or tidy up a test environment.

Cost drivers include:

1. Actual stored backup volume, daily churn, and service-level storage optimizations.
2. Number of recovery points, retention length, and daily/weekly/monthly cycles.
3. Location (regional, cross-regional, multi-region), data transfer, and restore transfers.
4. Backup and DR management/storage charges plus compute/disk costs during restore drills.
5. Longer retention mandates from compliance, litigation holds, or retention locks.

Illustrative example (**not a price quote**): if a dataset starts at 200 GiB with 5 GiB of daily changes to retain, after 30 days total stored data can grow well beyond 200 GiB. Actual billing depends on backup format, incremental behavior, compression/deduplication, and pricing; use the Google Cloud Pricing Calculator and workload Billing data.

When decommissioning:

- Stop new backups through the proper **unprotect** workflow.
- Wait for existing backups to pass enforced retention and expiration.
- Confirm no data sources/backups remain blocking vault deletion.
- Manage project liens and removal permissions via PAM/approvals per governance policy.
- Delete the vault only when service and compliance conditions permit; never try to bypass retention for "quick cleanup."

A vault **cannot be deleted** while backups remain under enforced retention or pending expiration cleanup. This protective property must be factored into budgets and project shutdown plans.

## 14. Ransomware response scenario

Suppose a production project service account is leaked. The attacker deletes the ordering system's disks, attempts to delete the backup plan association, and probes the backup vault in the hub project.

Recommended runbook:

1. **Contain the incident:** revoke tokens, disable or restrict the compromised principal per procedure, block unusual IAM changes, collect audit logs.
2. **Assess scope:** which workloads were deleted/encrypted, which backup plan associations are missing, which vaults hold recovery points, and are project liens intact?
3. **Verify immutability:** inspect vault minimum, inheritance, retention lock status, and enforced end times of **existing** backups.
4. **Protect the restore path:** use a separate restore operator, enforce target IAM, isolated networking, and KMS keys; avoid restoring directly into the compromised environment.
5. **Select a clean recovery point:** correlate compromise time with backups taken beforehand; immutable backups can still contain malware-encrypted data if taken after the intrusion began.
6. **Test restore:** restore into a staging/forensic project; verify checksums, application integrity, network access, and credentials.
7. **Restore service:** deploy clean infrastructure, patch vulnerabilities, rotate secrets, restore verified data, and cut over traffic only after Security approval.
8. **Measure RPO/RTO and postmortem:** document gaps in IAM, retention, alerts, backup schedules, vault placement, and remediation steps.

An immutable backup alone is **not enough** to prevent data leakage or sustain business continuity if the latest backup is already tainted, decryption keys are missing, or operators lack restore permissions. Cyber resilience requires **prevention, detection, response, and recovery**.

## 15. Common misconfigurations

| Symptom | Possible cause | Check and remediation |
| --- | --- | --- |
| Backup plan cannot use vault | Minimum enforced retention exceeds rule retention, or incompatible location/resource type. | Compare rule duration, backup plan region, and vault location/support matrix. |
| Vault created but no backups appear | Resource not associated yet, backup window not reached, or job failed. | Check plan association, job logs, and service agent. |
| Cross-project backup returns 403 | Vault service agent lacks operator role on workload project. | Retrieve exact service agent email and grant disk/VM/SQL role accordingly. |
| Cannot lower retention | Vault is locked or rule/backup compatibility forbids it. | Check lock status; if already effective, lowering is impossible. |
| 30-day rule backup deletable after 7 days | Vault used `inherit-vault-retention` with a 7-day minimum. | Check inheritance mode; create a new vault with `match-backup-expire-time` if full-lifecycle protection is needed. |
| Missing restore permissions from target project | Missing restore/operator role or access restriction block. | Inspect IAM on hub/restore projects and restriction mode. |
| Hub project cannot be deleted | Active project lien. | Expected behavior while protected backups exist; follow decommission workflow. |
| Project Owner cannot delete backup | Enforced retention protects the backup. | Do not bypass; wait until enforced expiration. |
| Backup intact yet restore fails CMEK | Key disabled/destroyed or missing KMS permissions. | Investigate key lifecycle and KMS permissions per policy. |
| Cannot change vault location | Location is fixed to vault identity/design. | Create a new vault in a supported location and migrate protection systematically. |
| Backup bills spike unexpectedly | Long assigned/enforced retention, many recovery points, or multi-region. | Analyze billing, storage footprint, and backup rules; never weaken locks improperly. |
| Audit logs missing restore or backup reads | Required log type not enabled or filter wrong. | Check Cloud Audit Logs and enable Data Access logs where appropriate. |

## 16. Lesson completion checklist

- [ ] Can explain vault → data source → backup, backup plan, and association.
- [ ] Distinguish backup rule assigned retention from vault enforced retention.
- [ ] Know minimum enforced retention can reach 99 years, subject to per-resource-type limits.
- [ ] Distinguish `inherit-vault-retention` from `match-backup-expire-time`.
- [ ] Understand inheritance mode cannot be changed after vault creation.
- [ ] Understand retention lock cannot be removed or lowered once effective.
- [ ] Know editing the vault minimum later does not alter enforced retention on existing backups.
- [ ] Know that from 01/11/2026, projects with vaults holding protected backups receive automatic liens.
- [ ] Have PAM/multi-party approval protecting lien removal permissions.
- [ ] Separate hub project and spoke/workload projects where appropriate.
- [ ] Grant least-privilege roles to backup vault admins, viewers, restore operators, and service agents.
- [ ] Choose the right access restriction before vault creation; prefer `within-org` for same-org hub/spoke.
- [ ] Verify CMEK/location/resource-type compatibility and key lifecycle ownership.
- [ ] Create backup plans with retention >= vault minimum and valid resource associations.
- [ ] Inspect backup metadata, enforced retention timestamps, and lock status using read-only operations.
- [ ] Configure backup schedule compliance alerts and vault/IAM/lien change alerts.
- [ ] Test restores into isolated staging resources, verify data, and measure RPO/RTO.
- [ ] Maintain plans for cost, decommissioning, IAM reviews, and incident response.
- [ ] Never test deletion/lowering retention on production as test evidence.

## References

- [Overview of backup vaults — Google Cloud Backup and DR](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault) — vault model, locations, enforced retention, lock, and access restrictions.
- [Create and manage a backup vault](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-vault-create) — Console, gcloud, Terraform, minimum retention, CMEK, service agent, and delete constraints.
- [Backup plans overview](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-plan) — assigned retention, backup plan rules, resource types, and compatibility.
- [Back up disks to a backup vault](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/compute/disk-backup) — backup plan associations, disk IAM, on-demand backups, restore.
- [Protect and recover disks — Quickstart](https://docs.cloud.google.com/backup-disaster-recovery/docs/quickstarts/disk-backup-vault) — creating plans and backing up disks via vault.
- [Manage backups in the Google Cloud console](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/bv-backup-manage) — listing, viewing recovery points, and expiration timestamps.
- [Protect projects with liens](https://docs.cloud.google.com/backup-disaster-recovery/docs/configuration/project-liens) — automatic lien application, project protection, and removal conditions.
- [Protect project liens with Privileged Access Manager](https://docs.cloud.google.com/backup-disaster-recovery/docs/configuration/project-liens-multi-party-approval) — multi-party approval before lien removal.
- [Configure cyber resilience for Backup and DR](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/best-practices-cyber-resilience) — hub/spoke architecture, separation of duties, IAM, KMS, and monitoring.
- [Best practices against ransomware](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/best-practices-ransomware) — ransomware defense and backup immutability.
- [Backup and Disaster Recovery IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/backupdr) — roles/permissions by resource and principal.
- [Backup and DR overview](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-dr) — Backup and DR scope, workload management, and backup models.
