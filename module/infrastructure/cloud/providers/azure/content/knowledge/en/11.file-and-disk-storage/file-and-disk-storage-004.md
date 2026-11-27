# Azure Files Snapshots, Backup, and Recovery

Imagine a company using **Azure Files** as a shared drive for its accounting department. At 14:00, an employee accidentally overwrites the payroll spreadsheet; the next morning, a folder is deleted; over the weekend, the operations team discovers the storage account is no longer accessible. All three incidents involve data loss, yet **they do not necessarily share the same recovery method**.

Azure Files provides **file share snapshots** to roll back to a file state from an earlier point in time. **Azure Backup** orchestrates backup policies, recovery point schedules, retention periods, and recovery workflows; in supported configurations, it can also back up into a vault tier. **Soft delete** helps recover an accidentally deleted file share within its protection window. Choosing the right mechanism depends on the incident type, recovery scope, RPO/RTO requirements, and protection against storage-account-level risks.

This lesson belongs to the **File and Disk Storage** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module introduces the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; and teaches how to deploy, monitor, protect, and control costs for application architectures on Azure. Here, we focus on **Azure Files data protection and recovery**, without equating file share snapshots with managed disk snapshots or Azure Blob snapshots.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **snapshot**, **backup**, **recovery point**, **soft delete**, and **replication**.
2. Explain how an **Azure Files share snapshot** captures point-in-time share state and why it is not an independent copy outside the storage account.
3. Build a protection policy using **Azure Backup**: frequency, retention, data scope, recovery points, and operational permissions.
4. Compare **snapshot-based backup** with **vaulted backup** when supported by file share type and region.
5. Choose how to recover **a single file**, **a folder**, **an entire file share**, or **an accidentally deleted file share**.
6. Define RPO/RTO, test restores, and configure alerts for backup failures.
7. Spot common misconceptions, such as treating GRS as a backup or treating snapshots as independent of the storage account.
8. Write incident response runbooks without overwriting additional data or losing valuable recovery points.

## 2. Recap of Azure Files and Protection Scope

**Azure Files** provides managed file shares on Azure Storage. Applications and servers can access them using protocols supported by the account/share type, such as **SMB** or **NFS**. Some systems use **Azure File Sync** to synchronize data from Windows Server to an Azure file share; others mount the share directly from VMs or office machines over an appropriate network connection.

Conceptual structure:

```text
Subscription / Resource group
└── Storage account: stcontosofiles01
    ├── File share: finance
    │   ├── reports/
    │   ├── invoices/
    │   └── payroll.xlsx
    └── File share: projects
        ├── designs/
        └── contracts/
```

When taking a snapshot of `finance`, you capture the state of **the `finance` file share**, not the entire storage account, and you do not automatically snapshot `projects`. When configuring backups, verify which **specific file shares** are included in the protection scope.

**Feature note:** snapshot, backup, snapshot-tier/vault-tier capabilities, and restore procedures may vary by **SMB/NFS**, **standard/premium or billing model**, storage account kind, region, and service availability over time. In real environments, verify features in the Azure Portal and service documentation applicable to the protected share before committing to RPO/RTO SLAs.

## 3. How Do Snapshots, Backups, Soft Delete, and Replication Differ?

| Mechanism | Nature | Solves well | Key limitation |
|---|---|---|---|
| **File share snapshot** | Read-only state of a file share at snapshot creation time; changed data is stored via the service's snapshot mechanism. | Recovering modified/deleted files or comparing a share's state across points in time. | Snapshots are tied to the source storage account/share and do not create an independent copy against full account loss. |
| **Azure Backup – snapshot tier** | Azure Backup orchestrates and manages recovery points based on share snapshots. | Scheduled backups, multi-day retention, restoring individual items or the entire share as supported. | Snapshot recovery point data remains within the source storage account's boundary. |
| **Azure Backup – vaulted tier** | Stores backup copies in a vault tier for supported Azure Files types and policies. | Increases recoverability during severe incidents affecting the source storage account. | Does not apply to every share type/SKU/region; has distinct schedules, retention, features, and pricing. |
| **File share soft delete** | Retains recovery capability for a deleted file share during a configured retention period. | Recovering when someone accidentally deletes **an entire share**. | Does not replace snapshots for restoring a single overwritten or deleted file inside an active share. |
| **Redundancy/replication** | Stores multiple data copies via LRS/ZRS/GRS/GZRS or supported options. | Data durability and infrastructure or regional fault tolerance per model. | Valid modifications or deletions can be replicated; does not provide historical version rollback by default. |

**Practical rule:** use snapshots for point-in-time recovery close to an error; use backup policies to manage schedules and retention; use independent vault-tier/off-account protection when recovery from major disasters is required; and enable soft delete to mitigate accidental file share deletion. These mechanisms complement one another—they are not different names for the same feature.

### Distinguishing examples

- An employee accidentally modifies `payroll.xlsx`: prioritize a **snapshot/recovery point** taken before the edit, then restore the single file.
- An administrator deletes the `finance` share: check **soft delete** and available backup mechanisms.
- The storage account becomes inaccessible or is deleted: **in-account share snapshots** may not suffice; rely on a supported independent recovery plan configured beforehand.
- Azure disk/infrastructure failure: **redundancy** supports availability, but cannot "rewind" contents overwritten by a valid operation.

## 4. How Azure Files Share Snapshots Work

A share snapshot is a **point-in-time, read-only** capture of an entire file share. The snapshot captures file, directory, and metadata states per service capabilities at creation time. Once created, applications can continue modifying/deleting files in the live share while the snapshot still references the prior state.

Progression example:

```text
09:00  finance/payroll.xlsx  = version A
        │
        ├── 09:05: create Snapshot S1
        │           S1 sees payroll.xlsx = A
        │
11:00  employee edits payroll.xlsx → version B
        │
        ├── 11:05: create Snapshot S2
        │           S2 sees payroll.xlsx = B
        │
13:00  payroll.xlsx is deleted from the live share
        │
        └── Restore from S1 or S2 depending on the target point in time
```

From a snapshot, you can **browse historical contents or copy/restore** to an allowed destination; **you cannot write directly into the snapshot itself**, because snapshots are read-only. Snapshots can be accessed through the Azure Portal, SMB/Windows "Previous Versions" clients in supported scenarios, or Storage APIs/CLI/SDKs.

### How are snapshots stored?

Share snapshots store **changed deltas** rather than physically duplicating all data on every capture. This makes creating recovery points faster and more economical than full copies in many situations.

However, costs can still rise when:

- Large volumes of data change between snapshots.
- Large files are rewritten frequently.
- Many snapshots are retained over long periods.
- Many shares take frequent snapshots.

**A snapshot is not an independent copy in another storage account.** If the team needs to recover from account loss, regional access loss, or mistakes by highly privileged operators, evaluate independent protection tiers and deletion controls over recovery points.

### Snapshots do not guarantee absolute application consistency

A snapshot captures file share state at creation time, yet **does not automatically guarantee applications have flushed caches, completed transactions, or synchronized multi-file state**. For example, accounting software might be writing two interdependent files; a snapshot could occur mid-write.

For data requiring application consistency:

1. Identify applications actively reading/writing and files with mutual dependencies.
2. If needed, put the application into a safe/quiesced state or use application-level quiescing support.
3. Take the snapshot or recovery point per runbook.
4. Resume the application and **test recovery** to confirm files can be opened cleanly.
5. For database systems, never assume file share snapshots replace database-layer consistent backups.

## 5. Creating and Using Manual Snapshots

Manual snapshots suit labs, upgrade testing, quick checkpoints before risky changes, or ad-hoc recovery points.

### Procedure in Azure Portal

1. Sign in to the [Azure Portal](https://portal.azure.com/) under the right **tenant/subscription**.
2. Open **Storage accounts** and select the account containing the Azure file share.
3. Navigate to **File shares** and pick the target share, e.g., `finance`.
4. Locate **Snapshots** or the share snapshot creation action in the current UI.
5. Create the snapshot and record the **snapshot timestamp/identifier**, operator, and reason.
6. Open the snapshots list to confirm the recovery point exists.
7. If a restore is needed, inspect snapshot contents first before overwriting live data.

A successful snapshot creation **only verifies a recovery point exists**—it does not prove application data restores cleanly. Always test opening files and verify integrity separately.

### Azure CLI examples

Azure CLI offers command groups for **Azure Files data-plane** (`az storage share`, `az storage file`) and **Azure Resource Manager/control-plane** (`az storage share-rm`). Parameter names and authentication methods can vary by Azure CLI version and share type, so check `--help` in your working environment.

First verify subscription and account with read-only commands:

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table

az storage account show \
  --name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{Name:name,Kind:kind,Location:location}" \
  --output table
```

When calling data-plane commands, supply an authentication method supported by the command/share type (such as account key/connection string/SAS within permitted bounds). **Never paste account keys or connection strings into shell history, tickets, or repositories.** Signing into Azure CLI for resource management does not mean every Azure Files data-plane command automatically uses Microsoft Entra OAuth without extra configuration.

Illustration of creating a share snapshot:

```bash
az storage share snapshot \
  --name "<SHARE_NAME>" \
  --account-name "<STORAGE_ACCOUNT>"
```

If the command requests data-plane auth, prepare an authorized mechanism per organizational policy; never embed secrets in examples. Creating a snapshot **modifies resource state and may incur costs**, so run it only in labs or authorized environments.

List shares and snapshots:

```bash
az storage share list \
  --account-name "<STORAGE_ACCOUNT>" \
  --include-snapshots \
  --output json
```

When reading the output, note the share name and **snapshot timestamp**: multiple snapshots can share the same share name with different timestamps. Keep the exact timestamp string to target the right recovery point.

### When manual, when policy-driven?

Manual snapshots help right before a controlled change. For business data requiring continuous protection, relying on administrators remembering to click snapshot is usually insufficient. Use **Azure Backup** or an approved solution for automated schedules, retention, and monitoring.

## 6. Azure Backup for Azure Files

**Azure Backup** centrally manages scheduled backups and restores via policy rather than relying solely on manual snapshots. For supported share types and features, you configure Azure file share protection in a **Recovery Services vault**, register/discover the storage account, select file shares, and assign a **backup policy**.

Some deployments support multiple recovery point tiers:

- **Snapshot tier (operational):** fast recovery from snapshots managed by Backup on the source storage account.
- **Vaulted tier:** backs up into a vault tier more independent from the source account to broaden protection scenarios. Features, restore workflows, and limits vary by Azure Files type and supported policies.

Not every Azure Files share has the identical feature set. Before committing to protect **premium, NFS, or specialized workloads**, verify support for **each backup tier** in your target account/region, along with retention limits, schedules, restore targets, and service prerequisites.

### What does Azure Backup manage?

| Capability | Meaning for operators |
|---|---|
| **Backup policy** | Defines backup schedules and retention per organizational needs. |
| **Recovery point** | Selectable data point for restoration per supported policy/feature. |
| **Protected item** | File share currently managed under Azure Backup scope. |
| **Backup job** | Individual backup execution with status and error details if any. |
| **Restore job** | Monitored file/share restoration workflow with verifiable results. |
| **Alerts and monitoring** | Helps detect failed jobs or protection state changes. |
| **Retention** | Number/duration of recovery points retained per configuration. |

**A Recovery Services vault does not automatically hold an independent data copy merely because a protected item appears.** If configured for snapshot tier only, snapshot data remains in the source account. To assess resilience against account destruction, verify whether **vaulted backup is genuinely enabled and supported**.

### Azure Backup-managed snapshots vs. manual snapshots

Both recovery point types can coexist yet have **different lifecycle ownership**:

- Manual snapshots: created/deleted and retention-managed by the operations team.
- Azure Backup snapshots: managed by backup policies and the service to satisfy schedules, retention, and restores.

Do not manually delete or alter snapshots managed by Azure Backup simply to reclaim capacity; doing so can break recoverability or leave backup state inconsistent. Adjust retention through policies/protected items and supported procedures.

## 7. RPO, RTO, and Retention: Turning Business Needs into Policy

A system with "daily backups" can still fail requirements if the business tolerates at most one hour of data loss.

- **RPO (Recovery Point Objective):** maximum tolerable data loss, measured by how far back an eligible recovery point sits.
- **RTO (Recovery Time Objective):** maximum acceptable time until the system/data is operational again.
- **Retention:** how long recovery points are kept so older states remain reachable.
- **Backup frequency:** how often recovery points are captured; directly governs RPO when backups succeed.

Examples:

| Data | Target RPO | Target RTO | Reference retention | What to check |
|---|---|---|---|---|
| Team working files | 24 hours | 4 hours | 30 days | Scheduled snapshots, file-level restore capability. |
| Sensitive invoices | 4 hours | 2 hours | Per compliance | Check whether policy supports enough frequency and independent protection needs. |
| Project document folders | 24 hours | 8 hours | 90 days | Need to restore older versions weeks later. |
| Files used as continuous app data | Minutes or very low | Short | Per application | May require application-consistent/dedicated protection beyond standard snapshots. |

These figures **illustrate requirements**, not a guarantee that Azure Backup for Azure Files supports every frequency and RPO shown. Real policy selection must rely on **service-supported schedules and retention**, reliable recovery point creation, and tested restores. If required RPO is shorter than supported backup schedules, add complementary mechanisms or redesign the workload.

### Real-world RPO calculation example

If the last successful backup ran at 01:00 and a file is corrupted at 08:30, choosing the 01:00 recovery point loses valid changes between 01:00 and 08:30. The actual incident RPO is **7 hours 30 minutes**, not a generic "daily backup" target.

If another verified safe point exists at 08:00, lost data may be only around **30 minutes**. The newest point is not always the **right** point: with ransomware, the latest snapshot might already hold encrypted files. Choose a recovery point taken before the incident began.

## 8. Configuring Backup Policy and Protection via Azure Portal

The general workflow below applies to environments **eligible for Azure Backup for Azure Files**; UI labels may vary with Portal/feature updates.

### Phase A: Preparation

1. Confirm the subscription, tenant, resource group, and storage account hosting the file share.
2. Check the share protocol (SMB/NFS), account type, tier, region, and service backup support.
3. Document RPO, RTO, retention, and data classification requirements.
4. Verify Azure RBAC and data permissions needed to configure protection; avoid broad privileges unless required.
5. Review soft delete, redundancy, network restrictions, private endpoints, and related security policies.

### Phase B: Create or select a vault

1. Open the [Azure Portal](https://portal.azure.com/).
2. Search for **Recovery Services vaults** and select a vault meeting region/service conditions, or create a new one if permitted.
3. Open **Backup**, and select the workload corresponding to **Azure FileShare/Azure Files** in the UI.
4. Select the storage account and specific file shares to protect.
5. Create or select a **backup policy**, setting schedule and retention within service-supported options.
6. If snapshot/vault tier options appear, enable only features confirmed supported and aligned with recovery requirements.

### Phase C: Post-protection verification

1. Verify the file share appears as a **protected item**.
2. Wait for a scheduled backup or trigger **Backup now** if permitted.
3. Monitor **Backup Jobs** until completion succeeds.
4. Open **Recovery points** and verify selectable restore timestamps exist.
5. Record the policy, vault, protected item, schedule, retention, and owner.
6. Run a **restore test** into a separate folder before declaring protection complete.

**Key distinction:** a successfully created policy does not prove data has ever been backed up successfully. You need **actual recovery points** and a verified restore test.

## 9. Restoring a Single File or Folder from a Share Snapshot

This is the most common scenario: a file is deleted, overwritten, or corrupted while the file share and storage account remain healthy.

Suppose `finance/reports/summary.xlsx` was overwritten at 10:20, and a snapshot exists from 10:00.

### Safe approach: restore to a different name first

1. Identify the affected **share and file path**.
2. Record the incident timestamp and prior available recovery points.
3. Open the 10:00 snapshot and verify the target file exists with expected size/contents.
4. **Copy or download** the snapshot version to another name/location, such as `restored/summary-1000.xlsx`.
5. Have the business owner validate the restored version.
6. Only once approved, replace the live file or deliver the older version to users.
7. Document the snapshot ID, file path, verifier, and final action.

Benefit: avoids overwriting newer live versions that may still hold valid edits made after the snapshot. If needed, compare differences before merging data.

### Accessing via Windows "Previous Versions"

In compatible **SMB/Windows** environments, Windows Explorer can display **Previous Versions** of files or folders from share snapshots. Typical steps:

1. Mount the Azure file share or browse the UNC path with granted permissions.
2. Right-click the file/folder and open **Properties → Previous Versions**.
3. Select the snapshot with the desired timestamp.
4. Use **Open/Copy** to inspect first; avoid clicking **Restore** directly without verifying overwrite impact.

Visibility and actions depend on Windows version, SMB, mount method, data permissions, and snapshot support. For NFS or environments lacking Previous Versions support, use the Portal/API or appropriate tools.

### CLI illustration: downloading a file from a snapshot

Once you know the exact snapshot timestamp, one way to retrieve the older copy is downloading and inspecting it before writing back:

```bash
az storage file download \
  --account-name "<STORAGE_ACCOUNT>" \
  --share-name "<SHARE_NAME>" \
  --path "reports/summary.xlsx" \
  --snapshot "<SNAPSHOT_TIMESTAMP>" \
  --dest "./summary-recovered.xlsx"
```

Verify `az storage file download --help` syntax in your Azure CLI version and prepare an authorized data-plane authentication method. The `--dest` path is a **local file**, not an overwrite on the share. This reads from the snapshot; avoid downloading sensitive data onto unmanaged personal laptops.

To place the file back into the share, use supported tools and an approved change process; prefer uploading to a separate recovery path for verification before replacing the live file.

## 10. Restoring an Entire File Share from a Recovery Point

When large numbers of files are modified/deleted or an entire directory tree is damaged, restoring files individually may be too slow. **Azure Backup** can provide **full share** or selected-item restoration depending on the backup tier and share type.

General workflow:

1. Determine the data scope to roll back and when the incident started.
2. Open Recovery Services vault → Protected items/Backup items → select the Azure file share.
3. Choose **Restore** and the appropriate recovery point.
4. Evaluate **Original location** vs. **Alternate location** options if permitted.
5. If overwriting live data, assess valid changes made since the recovery point and stop/quiesce writing applications per runbook.
6. Test restoring to an **alternate location** when feasible to inspect folder structure, permissions, and metadata.
7. Monitor the Restore Job, inspect logs, and confirm recovery with the application owner.
8. Re-enable write permissions or services after verifying data and access rights.

### Original location vs. alternate location

| Option | Benefit | Risks/conditions |
|---|---|---|
| **Original location** | Returns data directly where applications expect it. | Can overwrite or interact with newer data; requires change control. |
| **Alternate location** | Easy to compare and validate before replacement; reduces further data loss risk. | Requires capacity, permissions, networking, and a supported restore target. |

Do not assume every backup tier allows direct restoration to **any storage account, region, or protocol**. Valid targets depend on the backup mechanism and service constraints. Check target capabilities in the restore wizard before writing runbooks around them.

### Application data and share permissions

Restoring file contents alone is insufficient if applications also rely on:

- NTFS ACLs or file/share permissions per protocol.
- SMB share-level permissions and matching Azure RBAC.
- File locks/active open sessions.
- Path names, DNS/UNC paths, and client mount configurations.
- Application state, indexes, databases, or sync jobs.

Restore testing must include **opening files with actual business accounts** and reading/writing per expected permissions—not just seeing files exist in the Portal.

## 11. Recovering an Accidentally Deleted File Share with Soft Delete

**Azure Files share soft delete** protects a deleted file share for a configured retention window on the storage account. During this window, the system can allow **undelete/restore** of the file share per supported capabilities.

Key points:

- Soft delete primarily handles **deletion of the file share itself**.
- It is **not** a recycle bin for individual files deleted or overwritten inside an existing share.
- It has a **retention period**; once expired, soft-delete recovery is no longer available by default.
- It does not replace vault backups for account-wide incidents or elevated-privilege compromises.

### Procedure when a share disappears

1. Confirm the storage account still exists and the share is not merely unreachable due to DNS/networking.
2. Check **deleted file shares** in the Portal if soft delete was enabled.
3. Verify the share name and deletion timestamp.
4. Use **Undelete/Restore** on the target share using authorized admin privileges.
5. Verify the share reappears and mounts/applications can access it.
6. If soft delete has no recoverable copy, evaluate available independent backup recovery points.
7. Log the deletion/restoration and review restricting share-deletion permissions going forward.

**Never delete a share to "test soft delete" on production data.** Use a lab share and authorized procedures, as deletion disrupts users and active mounts.

## 12. Ransomware, Mass Deletion, and Account-Level Risks

A strong backup strategy optimizes for more than "one accidentally deleted file." Consider what **an attacker or compromised privileged account** could alter or delete among both live data and recovery points.

### Three risk levels

| Incident | In-account snapshots | Independent vaulted backup (if supported) | Action required |
|---|---|---|---|
| Single file overwritten | Usually the fastest recovery option. | Can serve as an extra option. | Choose a copy prior to the file edit. |
| Many files encrypted by ransomware | Useful if clean snapshots remain and privileges were not abused to delete them. | Increases odds of an isolated clean copy when properly configured. | Determine intrusion time, isolate the source, inspect recovery points. |
| Storage account deleted/corrupted or inaccessible | Not a sufficiently reliable independent layer. | Can help if backup data truly resides in a vault and restores under supported conditions. | Follow account/region-level runbooks and verify recovery permissions. |

**Snapshots do not stop ransomware by themselves**: someone with sufficient administrative privileges can still tamper with data, policies, or recovery points depending on permissions and enabled protections. Combine:

- **Least privilege** and strong authentication for administrative accounts.
- Separation between file share operators and backup/vault administrators.
- Soft delete, retention, and supported backup protection features.
- Logging, alerting, and incident response procedures.
- Testing restores from recovery points taken **before compromise**.
- Independent/immutable backup storage where required and supported, with appropriate protection policies.

Do not claim that enabling any single "immutable" toggle renders all Azure Files backups un-deletable; verify the exact **backup tier, vault, immutability features, and admin permissions** in your deployment.

### Finding a clean recovery point

If ransomware began encrypting at 09:00 but was detected at 14:00, a 13:00 snapshot may contain many damaged files. An 08:00 recovery point is safer, yet still requires **scanning/inspection** since the malicious actor may have been present before encryption became visible.

When recovering after an attack:

1. Isolate the threat actor and secure compromised accounts/devices.
2. Identify trusted recovery points.
3. Restore into an isolated environment or alternate location whenever feasible.
4. Verify contents, permissions, applications, and dependent data.
5. Return to production only after security sign-off.

## 13. Azure File Sync and Snapshot/Backup Considerations

**Azure File Sync** synchronizes Windows Server with an Azure file share, optionally using cloud tiering. When using File Sync, distinguish between **cloud share data** and **unsynced local changes** on server endpoints.

Example:

```text
Windows Server (server endpoint)
       │
       │ Azure File Sync
       ▼
Azure file share (cloud endpoint)
       │
       ├── Share snapshot / Azure Backup
       └── Cloud share data at recovery point time
```

A snapshot on the Azure file share reflects what had reached the **cloud share at that moment**. If Windows Server holds unsynced local changes, do not assume the cloud snapshot contains them.

Verification steps:

- Check sync status, sync errors, and backlogs in Azure File Sync monitoring tools.
- Assess open data, file-using apps, and consistency plans.
- Understand how restoring in the cloud share impacts server endpoints and subsequent synchronization.
- To recover a file that existed only on a server before syncing, local server backup/restore may be needed.
- Never operate directly on a snapshot expecting File Sync to sync it like a live folder; snapshots are read-only.

A complete recovery strategy for File Sync may need both **Azure file share protection** and **Windows Server local data/configuration protection**, depending on business goals.

## 14. Monitoring Backup Jobs, Snapshots, and Recoverability

**Configured backups** do not equal **successful backups**. Establish a baseline monitoring workflow:

| Signal | Why it matters | Required response |
|---|---|---|
| **Backup job failed/warning** | New recovery points are not created as expected. | Investigate errors, permissions, service health, and retry per procedure. |
| **Last successful backup time** | Tolerable RPO may already be exceeded. | Alert when recovery point age crosses threshold. |
| **Recovery point count/retention** | Available restore copies and timestamps change with policies. | Verify retention and required historical restore points. |
| **Restore job duration/result** | Evaluates real-world RTO. | Record completion duration and ability to open data. |
| **Storage capacity/transactions** | Snapshots and backups affect capacity usage and cost. | Forecast growth and tune schedules/retention. |
| **Protected items state** | A share could accidentally be unprotected or have its policy altered. | Audit config changes and protection scope. |
| **Soft delete policy** | Accidentally deleted shares might fall outside retention. | Confirm retention window and restore procedure. |
| **Identity/permission changes** | Backup/restore permissions might be revoked or overly broadened. | Audit admin actions and enforce least privilege. |

Use **Azure Backup Center/Backup reports**, **Azure Monitor**, **Recovery Services vault**, Log Analytics, and Azure Activity Log per available integrations. Azure Activity Log typically tracks **control-plane** changes, whereas detailed job/recovery point telemetry lives in the backup service.

### Periodic restore testing

A test schedule might include:

1. Monthly: restore a random file to an alternate folder.
2. Quarterly: restore an entire test folder/file share to measure RTO.
3. Periodically per DR requirements: test account-loss or region-loss scenarios using configured backup mechanisms.
4. After policy, network, identity, or application changes: re-verify recovery point creation and restoration.

This is only an **illustrative cadence**, not an Azure requirement. Frequency must reflect criticality, compliance, and organizational budget.

Acceptance requires proof that **data is readable, permissions are intact, and applications can use it**, not merely a "Restore completed" status.

## 15. Security and Authorization for Recovery Operations

Different administrative tasks require different permissions:

- **Storage account/file share management:** create, modify, delete shares, and configure soft delete.
- **Azure Files data plane:** read/write file contents, view snapshots, or manipulate files per supported authentication.
- **Backup management:** create policies, enable/stop protection, trigger on-demand backups.
- **Performing restores:** select recovery points, restore targets, and monitor jobs.
- **Auditing:** view configurations, job history, and change logs without necessarily modifying data.

Never grant full Storage and vault administration rights to the same everyday operator account. Assign Azure RBAC roles by duty, use Microsoft Entra ID with PIM/MFA where configured, and log data-impacting operations.

### Principles when restoring sensitive data

- Restore into a location with **equal or stricter permissions** than the source.
- Do not download sensitive files to personal laptops or unmanaged hosts.
- When using an alternate location, control retention and cleanup of restored copies after verification.
- Record approver, timestamp, file scope, justification, recovery point, and checksum/verification method where appropriate.
- Do not delete older snapshots/backups until the new restore is proven successful and retention needs have ended.

## 16. Snapshot, Backup, and Restore Costs

Data protection carries costs; never pick retention purely for the lowest fee.

| Component | Cost impacts to evaluate |
|---|---|
| Share snapshots | Changed data volume retained across snapshots, retention length, and share type. |
| Azure Backup snapshot tier | Snapshot storage and related items per supported pricing model. |
| Azure Backup vaulted tier | Vaulted backup data, retention policies, features, and related transactions. |
| Storage redundancy | LRS/ZRS/GRS/GZRS depending on selection and region. |
| Restore | Target capacity, transactions, and egress/cross-region charges if incurred in supported models. |
| Monitoring | Log ingestion/retention, alerts, and monitoring tools. |
| Operations | Testing effort, data reconciliation, approvals, and DR drills. |

**Qualitative example:** two shares both hold 1 TB of data, yet Share A rarely changes while Share B rewrites large files daily. Snapshot storage growth on Share B can be vastly higher despite identical live capacity. Always budget using **change rate**, not just current size.

Before deploying, use the **Azure Pricing Calculator** and current pricing for your region/SKU/backup tier. Example figures are not price quotes.

## 17. Incident Response Workflow: Choosing the Recovery Mechanism

A solid runbook starts by asking **what was lost and since when?**

```text
Missing/corrupted Azure Files data detected
                 |
                 v
       Is the Storage account accessible?
           /                       \
         Yes                        No
         |                           |
         v                           v
      Does the Share still exist?   Assess account/region
       /              \             incident scope
     Yes               No                  |
     |                  |                  v
     v                  v           Evaluate configured
 File/folder        Share soft      vaulted/off-account
 edited/deleted?     delete?        backup & restore options
     |                  |
     v                  v
 Choose snapshot    Undelete share
 /recovery point    if within retention
     |
     v
 Restore to alternate location
     |
     v
 Verify accuracy, permissions, app
     |
     v
 Approve replacing live data
```

### First-15-minute action checklist

1. **Record symptoms:** storage account/share name, path, UTC timestamp, reporter.
2. **Prevent further data loss:** pause overwriting jobs/apps and isolate suspected compromised devices per procedure.
3. **Do not delete recovery points:** preserve relevant snapshots and backups, check retention policies.
4. **Classify the incident:** single-file loss, entire share loss, account loss, permission/network error, or ransomware.
5. **Select a safe recovery point:** recent, yet strictly prior to the incident.
6. **Prioritize restoring to a staging location:** do not immediately overwrite live files.
7. **Notify owners:** state potential data loss window and expected recovery time per runbook—never promise untested RTOs.
8. **Maintain an audit log:** record actions and decisions by each team.

### When a restore fails

Check step by step:

- Does the recovery point exist and **belong to the right file share**?
- Are you using snapshot tier or vaulted tier, and is the restore target supported?
- Do the share/storage account/vault have required permissions and healthy status?
- Can clients reach Storage via SMB/NFS/REST, DNS, and firewalls/private endpoints?
- Does the destination have sufficient quota/capacity, valid path names, and write permissions?
- With File Sync, had the expected data finished syncing to the cloud?
- Did the job fail due to networking, permissions, timeouts, data types, or protected item state?

If unclear, **do not repeatedly run overwrites against the same production target**. Capture errors and retry against a controlled lab target.

## 18. Hands-On Exercise: Restoring Accounting Data

**Context:** The `finance` share on Azure Files stores invoices and payroll. Policy-based backups create recovery points at 01:00 and 13:00. At 14:15, an employee reports `reports/payroll.xlsx` was accidentally overwritten around 13:40.

**Assumed details:**

| Item | Value |
|---|---|
| Storage account | `stcontosofiles01` |
| Share | `finance` |
| File | `reports/payroll.xlsx` |
| Recovery points | 01:00 and 13:00 |
| Time of error | 13:40 |
| Time detected | 14:15 |
| Objective | Recover the pre-edit file without overwriting newer data prior to verification |

### Tasks

1. Select the more appropriate recovery point and explain why.
2. Explain the difference between retrieving a file from a snapshot vs. restoring the entire share.
3. Outline a safe recovery plan with business-owner content verification.
4. Explain which mechanism to check if the `finance` share itself is later deleted.
5. Evaluate protection coverage if the entire storage account becomes inaccessible.
6. List at least three alerts or metrics to monitor.
7. Describe how to verify that an Azure File Sync deployment sees the restored data.

### Reference Solution

**Choose the 13:00 recovery point:** because it is the latest point **prior to the 13:40 overwrite**. The recovered file may omit valid edits made between 13:00 and 13:40, so confirm with the business owner.

**Steps:**

1. Inspect the 13:00 snapshot/recovery point for `reports/payroll.xlsx`.
2. Download or copy the file to a separate path such as `restored/payroll-1300.xlsx`.
3. Verify opening the file, sheets, formulas, and critical values.
4. Obtain sign-off from accounting before replacing the live copy.
5. After replacement, confirm dependent programs read the file cleanly and access permissions remain intact.
6. Archive evidence of the recovery point, timestamp, approver, and outcome.

**If the share is deleted:** inspect file share soft delete and its retention period; then evaluate recoverable backups. **If the account is lost:** snapshots in the same account are not independent copies; verify whether vaulted backups or off-account storage were actually configured.

**Monitoring:** last successful backup timestamp, failed job count, available recovery points, test restore duration, soft delete status, and snapshot capacity.

**Azure File Sync:** verify sync health, server endpoints, and synced updates; test reading the file on user workstations and monitor post-restore sync per runbook.

### Completion Criteria

The exercise passes when it includes:

- Recovery point selection based on **incident timestamp**.
- Recovery workflow that prevents additional loss of valid data.
- Evidence the file opens and permissions are accurate.
- Distinct plans for file deletion, share deletion, and account-level disaster.
- Monitoring plan and RPO/RTO testing strategy.

## 19. Knowledge Self-Check

**Question 1.** Is an Azure Files share snapshot an independent copy in a different storage account?

A. Yes, all snapshots automatically save into a Recovery Services vault.  
B. No, snapshots are tied to the source file share/storage account.  
C. Yes, because snapshots are read-only.

**Answer: B.** "Read-only" does not mean "independent copy." Snapshots must be paired with an appropriate backup policy when protecting against account-level incidents.

**Question 2.** An employee deletes one file inside an active share. Is file share soft delete the primary recovery mechanism?

**Answer:** No. Share soft delete focuses on **deleting the entire file share**. To recover an individual file, use share snapshots, recovery points, or appropriate versioning/backup mechanisms.

**Question 3.** Azure Backup shows a protected item created, yet no successful recovery point exists. Is that sufficient proof the data is protected?

**Answer:** No. You need successful backup jobs, selectable recovery points, and a verified restore test.

**Question 4.** A company has recovery points at 01:00 and 07:00; ransomware is detected at 14:00. Should you automatically pick 07:00 because it is closest?

**Answer:** No. Determine when compromise/encryption began, select a **clean** recovery point, and inspect data before restoring to production.

**Question 5.** Why does Azure Storage GRS/GZRS not automatically replace historical version backups?

**Answer:** Redundancy improves data durability and infrastructure resilience, yet valid edits or deletions still replicate. Backups/snapshots provide historical recovery points.

**Question 6.** Does "daily backup" guarantee a 30-minute RPO?

**Answer:** No. RPO depends on the last successful recovery point relative to the failure timestamp. You need protection frequent enough to match service capabilities and requirements.

**Question 7.** When restoring a critical file, why restore to a different filename first?

**Answer:** To inspect contents, avoid overwriting newer valid changes, and minimize impact if the wrong snapshot was selected.

**Question 8.** For Windows SMB clients, where can share snapshots sometimes be viewed in supported environments?

**Answer:** Under file/folder **Previous Versions**; availability depends on OS, SMB, mount method, permissions, and service support.

**Question 9.** With Azure File Sync, does a cloud share snapshot guarantee inclusion of all unsynced data recently written on Windows Server?

**Answer:** No. Snapshots capture cloud share state at creation time; unsynced local changes may not yet appear.

**Question 10.** Why should you avoid manually deleting snapshots managed by Azure Backup?

**Answer:** It can corrupt recovery points, retention tracking, or protection health. Manage retention via backup service policies and procedures.

**Question 11.** What must be verified before adopting vaulted backup for a premium or NFS file share?

**Answer:** Support across protocol, share type/tier, region, backup policy, recovery target, retention, permissions, and actual costs.

**Question 12.** Once a restore job reports completed, can you conclude RTO and application integrity are met?

**Answer:** No. Measure total time until **users/applications can actively use the data**, and verify files, permissions, mounts/DNS, and app dependencies.

**In summary**, file share snapshots roll back to a past point in time, Azure Backup organizes recovery points and retention, soft delete helps rescue deleted shares, and supported vaulted backup options expand resilience against wider failures. An Azure Files protection plan is trustworthy only when **appropriate recovery points exist, restores are tested, restoration permissions are clear, and RPO/RTO are measured in practice**.
