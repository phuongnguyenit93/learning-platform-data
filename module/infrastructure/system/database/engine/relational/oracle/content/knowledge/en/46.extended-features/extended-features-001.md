# Building a Feature Matrix by Release, COMPATIBLE, Edition, and Licensing in Oracle

## 1. Why Do You Need a Feature Matrix?

Oracle Database has multiple releases, editions, options, management packs, and licensing models. A feature may appear in the documentation for one release but not in another; it may be installed in the binaries but unavailable in the edition in use; it may work technically yet require a separate option or management pack; or it may only be enabled when the `COMPATIBLE` parameter reaches an appropriate level.

Therefore, asking "Does the database support this feature?" is not enough. Before designing, upgrading, or enabling a feature, you must simultaneously determine:

1. **Release and Release Update (RU):** the specific software version, including patch level.
2. **`COMPATIBLE`:** the configured database format/capability compatibility level.
3. **Edition:** the base product feature set, such as Enterprise Edition or Standard Edition 2 in supported releases.
4. **Option/management pack:** components that may need to be purchased and licensed separately.
5. **License entitlement and metric:** contracts, quantities, deployment scope, and license calculation rules.
6. **Architectural conditions:** platform, CDB/PDB, RAC, cloud service, topology, and deployment configuration.

This lesson belongs to the **Database Engine Relational Oracle** module, **Extended Features** chapter, focusing on **building a feature matrix by release, COMPATIBLE, edition, and licensing**.

The goal is to build an evidence-backed matrix used to make technical decisions and manage licensing. Database views help observe configuration or feature usage; they do not replace contracts and do not by themselves prove entitlement.

## 2. Five Layers to Distinguish

A good matrix does not lump all conditions into a single "Supported" column. Distinguish the following layers.

| Layer | Question to Answer | Primary Evidence Source |
|---|---|---|
| Release/RU | Does the feature exist and remain supported in this version? | Oracle documentation, release notes, upgrade guide |
| COMPATIBLE | Does the database compatibility level allow using the required structures/features? | `V$PARAMETER`, release parameter documentation |
| Edition | Does the installed edition include that base feature? | Licensing Information User Manual for the exact release |
| Option/pack | Is a separate option or management pack required? | Licensing manual, product price list, contract |
| Entitlement | Does the organization have the right to use it in this deployment and metric? | Ordering document, license agreement, cloud service terms, license inventory |

In addition to the five layers above, check the architecture: a feature may require a specific CDB/PDB setup, OS/platform, hardware, service configuration, or topology.

### 2.1. Present in Binaries Does Not Mean Entitled to Use

An option may be installed or shown as available in the database home even when the organization has no corresponding entitlement. Conversely, the fact that an option is unused in the current environment does not necessarily mean a license is unnecessary for another deployment.

**Technical availability** answers whether the software can provide the functionality. **License entitlement** answers whether the organization has the right to use the functionality under its contracts and deployment terms. These are two separate conclusions.

### 2.2. Usable Does Not Mean It Should Be Enabled

Even when a feature is supported and entitled, you must still evaluate:
- Performance and resources.
- Impact on backup/restore, replication, and DR.
- Application/driver compatibility.
- Operations, monitoring, and team skills.
- License and infrastructure costs.
- Rollback or data conversion risks.

The matrix must include both the technical status and the deployment decision.

## 3. Release, Release Update, and Feature Lifecycle Status

### 3.1. Release

Release identifies the Oracle Database version line, such as 19c, 21c, or 23ai. Do not just record "Oracle 19" in the inventory; record the full version and actual release family.

A feature can:
- Be introduced in one release.
- Be extended in a subsequent release.
- Have restrictions by edition or platform.
- Be deprecated.
- Be desupported in a newer release.
- Change configuration requirements or administration methods.

### 3.2. Release Update (RU)

An RU is a periodic update containing bug fixes and changes issued by Oracle for the corresponding release. Two environments both labeled "19c" may still differ in RU, one-off patches, and the SQL patch registry.

Record at minimum:
- Database release/version.
- RU or patch level.
- SQL patch registry.
- Oracle Home/JDBC client version if relevant.
- Applied date and change record.

Do not assume an RU only contains security fixes and has no behavioral impact. Read the RU README, known issues, and bug fix list relevant to your workload.

### 3.3. Feature Lifecycle

In the matrix, use statuses with clear meanings:

| Status | Meaning |
|---|---|
| Available | Present in the release and permitted by edition/architecture conditions |
| Available with restriction | Present but restricted by edition, platform, topology, or configuration |
| Requires option/pack | Requires a separately licensed component |
| Requires COMPATIBLE | Only available when `COMPATIBLE` meets the requirement |
| Deprecated | Still exists, but Oracle recommends against using it and it may be removed in a future release |
| Desupported | No longer supported in that release |
| Not available | Not present in the release/edition/architecture under review |
| Unknown / verify | Insufficient evidence to conclude |

Do not use a single "No" cell for not available, unlicensed, and unchecked. These statuses require different actions.

## 4. What Does `COMPATIBLE` Control?

The `COMPATIBLE` initialization parameter specifies the compatibility level that the database maintains for structures and behaviors allowed for use. It enables upgrading the database software first, and raising the data compatibility level later when ready.

Check the value:

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

You can view the configuration in the SPFILE:

```sql
SHOW PARAMETER compatible;
```

Columns and visibility depend on privileges and version.

### 4.1. Database Release Differs from COMPATIBLE

For example, a database may already be running a newer Oracle software release while `COMPATIBLE` is kept at a lower value during a transition period. Some new capabilities may not yet be allowed because the database still maintains the older compatibility level.

Therefore, do not infer feature availability solely from `V$VERSION`. Record all of the following:
- Software release.
- RU.
- `COMPATIBLE`.
- Edition.
- Option/pack.
- Database configuration.

### 4.2. Raising COMPATIBLE Requires a Separate Change Plan

Changing `COMPATIBLE` is typically a static change requiring an SPFILE configuration and restart following the release procedure. Illustrative example:

```sql
ALTER SYSTEM SET compatible = '19.0.0' SCOPE = SPFILE;
```

Do not run this statement merely because the database software was upgraded to 19c. Valid values and procedures must follow the upgrade guide for the exact release.

Before increasing it:
- Confirm the upgrade is complete.
- Complete application and workload testing.
- Verify backup/recovery.
- Check the downgrade path.
- Read the requirements of the feature to be enabled.
- Have approval and a change window.

### 4.3. Increasing COMPATIBLE Can Restrict Downgrade

After raising the compatibility level and once the database uses new structures, reverting to an older release may no longer be supported. Downgrade capability depends on the release, upgrade state, features used, and Oracle guidance.

Do not treat changing the parameter back as a full rollback. Check the downgrade guide or restore from a verified backup.

### 4.4. COMPATIBLE Is Not a License Switch

Setting `COMPATIBLE` high does not grant entitlement to use an option. Setting it low does not by itself prove that no feature was used or no license is required. It is a technical condition in the matrix, not a substitute for a contract.

## 5. Edition, Options, and Management Packs

### 5.1. Edition

The edition defines the set of base capabilities provided in the product. Edition names and feature matrices vary by release, platform, and distribution model.

When building the matrix, record the exact running edition and the purchased edition. Do not infer the edition solely from an option shown in `V$OPTION`.

### 5.2. Database Options

Some capabilities are packaged as separate options. Examples of groups that commonly require separate license verification by release and contract include:
- Partitioning.
- Advanced Compression.
- Advanced Security.
- Database In-Memory.
- Real Application Clusters.
- Active Data Guard.
- Multitenant in models/releases with corresponding licensing conditions.
- Other options listed in the Licensing Information User Manual.

This list is an example for building an inventory, not a claim that every option has the same terms across every release or cloud service.

### 5.3. Management Packs

Management packs are groups of administration/diagnostics/tuning tools with separate licensing conditions by product and release. Examples:
- Diagnostics Pack.
- Tuning Pack.
- Other management packs listed in the licensing documentation.

Features such as AWR, ASH, ADDM, SQL Tuning Advisor, or SQL Monitoring may relate to the corresponding pack. You must cross-check the exact feature, release, conditions, and contract; do not assume all diagnostic tools are free or that every dictionary query requires a pack.

### 5.4. Enterprise Edition Does Not Mean Every Option Is Licensed

A database running Enterprise Edition does not automatically have the right to use all database options and management packs. Record each entitlement separately and identify which deployments are covered.

### 5.5. Cloud Services and License Included/BYOL

Database services on the cloud may have models such as:
- License included.
- Bring Your Own License (BYOL).
- Service-specific entitlement.
- Limits by shape, OCPU/ECPU, region, or service tier.

Do not directly apply on-premises license tables to cloud services. Use the corresponding service description, cloud contract, and licensing terms.

## 6. Building the Feature Matrix

A row in the matrix represents a feature or a group of capabilities with the same conditions. Do not write a generic "Oracle advanced features" row because each feature has different release, edition, and entitlement rules.

### 6.1. Recommended Columns

| Column | Content |
|---|---|
| Feature ID | Stable identifier for reference |
| Feature name | Official name/business name |
| Business purpose | Why the application needs the feature |
| Introduced in | First supported release |
| Target release/RU | Release and patch level under review |
| Lifecycle | Available/deprecated/desupported |
| Edition | Required edition |
| Option/pack | Separate option or management pack |
| COMPATIBLE | Minimum compatibility level/condition |
| Architecture | CDB/PDB, RAC, OS, platform, cloud condition |
| License metric | Processor, NUP, or contract-defined metric |
| Entitlement evidence | Contract/order/approval |
| Technical evidence | Query, config, test, screenshot/log |
| Owner | DBA, application owner, license owner |
| Decision | Approved, blocked, not used, verify |
| Review date | Most recent review date |

### 6.2. Example Blank Matrix Template

| Feature | Release/RU | COMPATIBLE | Edition | Option/pack | Entitlement | Result |
|---|---|---|---|---|---|---|
| Partitioning | Enter target version | Check manual | Check manual | Check license | Cross-check contract | Verify |
| Advanced Compression | Enter target version | Check manual | Check manual | Check license | Cross-check contract | Verify |
| Database In-Memory | Enter target version | Check manual | Check manual | Check license | Cross-check contract | Verify |
| Diagnostics Pack | Enter target version | Per release | Suitable edition | Management pack | Cross-check contract | Verify |
| Active Data Guard | Enter target version | Per release | Suitable edition | Option | Cross-check contract | Verify |
| Multitenant/PDB | Enter target version | Per release | Per service | PDB/option conditions | Cross-check contract | Verify |

This is a process template, not an official feature entitlement matrix. Do not fill in "Yes" for a feature merely because its name appears in the dictionary or marketing documentation.

### 6.3. Separate Technical Status and License Status

There should be two separate decision columns:

- `technical_status`: supported, configured, tested, blocked, unknown.
- `license_status`: entitled, not entitled, contract review, not applicable, unknown.

A feature may have technical_status = supported while license_status = not entitled. In that case, the production decision must be blocked until an approved resolution is in place.

## 7. Documentation Sources and Order of Precedence

Use documentation matching the exact release and deployment model.

### 7.1. Oracle Database Licensing Information User Manual

This is an essential source to determine:
- Which features belong to which edition.
- Which options/packs have separate licensing conditions.
- Release-specific conditions and exceptions.
- Certain metrics/limits by product model.

You must select the manual corresponding to the release and platform in use. Do not take tables from 11g/12c and apply them verbatim to 19c/23ai or cloud services.

### 7.2. Oracle Database Licensing Guide / License Definitions

Cross-check:
- Ordered product/option.
- Processor or Named User Plus.
- Minimums and specialized metrics.
- Core factor if applicable.
- Virtualization/cloud terms.
- Term, territory, entity, and deployment scope.

The organization's contracts and ordering documents govern actual entitlement. Public documentation helps explain the product but cannot replace a specific contract.

### 7.3. Database New Features Guide

Used to determine which release introduced a feature, new behaviors, and technical requirements.

### 7.4. Upgrade Guide and Release Notes

Used to confirm:
- Supported upgrade paths.
- `COMPATIBLE` changes.
- Deprecated/desupported features.
- RU-specific known issues.
- Post-upgrade actions.
- Platform/architecture restrictions.

### 7.5. My Oracle Support and Patch README

When support access is available, check bugs, one-off patches, known issues, and corresponding driver/database requirements. The RU/one-off patch README is evidence to keep in the change record.

## 8. Collecting Technical Status from the Database

The SQL statements below help inventory configuration. They are not tools for confirming license entitlement.

### 8.1. Database Version

```sql
SELECT banner_full
FROM v$version
ORDER BY banner_full;
```

Or:

```sql
SELECT version,
       version_full
FROM v$instance;
```

Save the results along with Oracle Home, RU, and platform.

### 8.2. COMPATIBLE

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

Record both the configured value and the sampling timestamp.

### 8.3. Options Visible in the Instance

```sql
SELECT parameter,
       value
FROM v$option
ORDER BY parameter;
```

`V$OPTION` indicates whether certain options are installed/enabled in the software/database environment according to the release's semantics. A `TRUE` value does not prove the organization purchased a license; `FALSE` also does not replace reading the contract.

### 8.4. Component Registry

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

This view reflects the status of components registered in the database. Not every database option is represented as a component in `DBA_REGISTRY`.

### 8.5. SQL Patch Registry

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Use the results to cross-check RUs/SQL patches. Combine with the Oracle Home inventory and patch README; the registry is not the complete patch history across every layer.

### 8.6. Feature Usage Statistics

```sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date,
       version
FROM dba_feature_usage_statistics
ORDER BY name;
```

`DBA_FEATURE_USAGE_STATISTICS` assists in observing certain feature usage detected by the database. You must understand its limitations:
- False positives or false negatives can occur depending on the feature and release.
- Detected feature usage does not by itself prove entitlement.
- No detected usage does not by itself prove a feature was never used.
- You must read the feature usage documentation and confirm how Oracle records each feature.
- Do not use a single snapshot as a substitute for long-term auditing.

In a CDB, inspect the corresponding CDB view if the release provides it and privileges allow; clearly record the container/PDB and sampling scope.

### 8.7. Management Pack Access Configuration

You can inspect the related parameter:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'control_management_pack_access';
```

This parameter controls certain management pack access capabilities depending on the release. It is not a license key and does not grant entitlement. Setting a value that allows access does not mean the contract includes the pack; setting a restrictive value also does not replace usage and entitlement inventorying.

### 8.8. Checking CDB/PDB

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Record the PDBs, services, status, and entitlement rules applicable to the multitenant model of the release/contract. Do not infer licensing conditions solely from the number of OPEN PDBs.

## 9. Why Views Do Not Prove Licensing

There are several common misconceptions:

| Observation | What Can Be Concluded | What Cannot Be Concluded |
|---|---|---|
| `V$OPTION` = TRUE | The option has a technical status displayed as available | The organization has purchased the option |
| `DBA_REGISTRY` has component | The component is registered/installed | Entitlement exists for all uses |
| Feature usage has `DETECTED_USAGES` | The database recorded a usage type per its detector | The contract definitely requires or permits a specific legal conclusion |
| `CONTROL_MANAGEMENT_PACK_ACCESS` allows | Certain pack functions can be accessed | The pack license has been purchased |
| SQL executes successfully | The database can execute the statement | The statement is licensed in that environment |
| DBA sees no usage | The snapshot did not record usage | There was no usage at another time or via another access path |

Separate technical evidence, usage evidence, and contractual evidence in your reports.

## 10. Determining Actual Edition and Entitlement

### 10.1. Determining Technical Edition

Use the version banner, Oracle Home inventory, and deployment documentation to confirm the edition. Do not rely solely on `V$OPTION`, because many options can display statuses independently of the edition.

Example to retrieve the banner:

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

Combine information from:
- Oracle Home inventory.
- Database creation/deployment record.
- Container image or cloud service details.
- Contracts/ordering documents.

### 10.2. Organization's License Inventory

The license owner/asset management team should provide:
- Product SKU and edition.
- Ordered options/management packs.
- License quantities.
- Metric.
- Processor/core factor if applicable.
- Named User Plus and minimums if applicable.
- Deployment scope and legal entity.
- Term/expiry/renewal.
- ULA/PULA or special terms if any.
- Cloud service entitlement or BYOL conditions.
- Amendments/contract changes.

Do not store sensitive contract details in technical files with broad access permissions. The matrix can reference a contract ID or a controlled document repository.

### 10.3. The Metric Is Not Always Session Count

Some licenses use Processor, some use Named User Plus, or custom metrics. Do not take the connection pool size, database user count, or visible CPU count inside a VM and infer the number of licenses to purchase on your own.

Virtualization, hard partitioning, soft partitioning, cloud infrastructure, and core factors have their own rules. Cross-check licensing policies/contracts and confirm with a license specialist.

## 11. Examples of Feature Groups to Include in the Matrix

The list below is an inventory suggestion. Specific conditions must be verified in the manual for the exact release and in the contract.

### 11.1. Partitioning

Check:
- Whether the release supports the partitioning type in use.
- Edition/option requirement.
- `COMPATIBLE` if conditional.
- Table/index partitioning, interval, reference, composite, or related features.
- Existing DDL and objects actually using it.
- License entitlement.

Object inventory:

```sql
SELECT owner,
       table_name,
       partitioning_type,
       subpartitioning_type,
       partition_count
FROM dba_part_tables
ORDER BY owner, table_name;
```

This view shows partitioned tables; it does not prove license entitlement. Combine it with DDL, usage, and the licensing manual.

### 11.2. Advanced Compression

Review:
- Compression type.
- Table/index/LOB usage.
- Backup compression and other compression features that may fall under different conditions.
- Edition, option, and release.
- CPU/I/O workload and storage savings.
- Feature usage and contract.

Do not lump all compression types into a single feature. Basic compression, advanced row compression, hybrid columnar compression, and backup compression have different technical/licensing conditions depending on product and release.

### 11.3. Database In-Memory

Inventory:
- Edition/release.
- Option entitlement.
- `INMEMORY_SIZE` and instance configuration.
- Objects with the `INMEMORY` attribute.
- In-memory population and memory consumption.
- Actual analytic workload.
- Platform/service restrictions.

An object declared `INMEMORY` does not automatically prove the segment has been populated or the workload is accelerated. Check the runtime views appropriate to the release and measure actual queries.

### 11.4. Real Application Clusters

Check:
- Edition/release and option entitlement.
- Clusterware/Grid Infrastructure.
- Instance count and node topology.
- Service configuration.
- FAN/FCF/UCP client support.
- Failover behavior and workload placement.

You can inspect instances:

```sql
SELECT inst_id,
       instance_name,
       host_name,
       status
FROM gv$instance
ORDER BY inst_id;
```

`GV$INSTANCE` shows instances visible in the cluster; it does not prove RAC entitlement.

### 11.5. Active Data Guard and Data Guard

Distinguish basic Data Guard capabilities from additional capabilities such as real-time query on standby or other features with separate option/license conditions.

Check:
- Database role.
- Open mode.
- Transport/apply lag.
- Standby topology.
- Read-only workload.
- Features actually used.
- Licensing manual and contract.

Example:

```sql
SELECT database_role,
       open_mode,
       protection_mode,
       switchover_status
FROM v$database;
```

Do not conclude licensing solely from a standby being MOUNT or OPEN READ ONLY. Identify the exact capabilities and use cases.

### 11.6. Diagnostics Pack and Tuning Pack

Inventory tools/workflows:
- AWR reports/snapshots.
- ASH.
- ADDM.
- SQL Tuning Advisor.
- SQL Monitoring.
- Other functions listed by the licensing manual.

Do not assume every `V$` view belongs to a pack. Also do not assume a function without a UI is exempt from license terms. Verify each feature against the manual for the exact release.

### 11.7. Multitenant

Check:
- Release and edition.
- Number of PDBs and how they are used.
- How PDBs are created, cloned, refreshed, or relocated.
- Application root/seed if present.
- Entitlement conditions by release/contract.
- Cloud service terms if running in the cloud.

Do not apply a fixed PDB count rule across all releases. Multitenant conditions have changed across versions and licensing models.

## 12. Example Matrix for a System

Suppose a system needs the following capabilities. This illustrates the structure, not a license conclusion for a specific release.

| Feature | Purpose | Release/RU | COMPATIBLE | Edition/option | License evidence | Decision |
|---|---|---|---|---|---|---|
| Partitioning | Split large transaction tables | Verify | Verify | Verify | Not yet cross-checked | Blocked |
| Advanced Compression | Reduce storage | Verify | Verify | Verify | Not yet cross-checked | Blocked |
| RAC | Instance HA | Verify | Verify | Verify | Not yet cross-checked | Blocked |
| Active Data Guard capability | Read-only standby workload | Verify | Verify | Verify | Not yet cross-checked | Blocked |
| Diagnostics Pack | AWR/ADDM | Verify | Verify | Verify | Not yet cross-checked | Blocked |
| Tuning Pack | SQL tuning/monitoring | Verify | Verify | Verify | Not yet cross-checked | Blocked |
| Multitenant | Isolate workloads with PDBs | Verify | Verify | Verify | Not yet cross-checked | Blocked |

The `Blocked` status here means there is not yet enough evidence to approve usage. It does not mean the feature is definitely unlicensed.

### 12.1. Adding Evidence to Each Row

For example, a complete row should record:
- Oracle documentation and release cross-checked.
- Database inventory results.
- DDL/configuration showing the feature in use.
- Test and workload results.
- Contract/order reference.
- Technical approver.
- License approver.
- Review date.

## 13. Classifying Necessity and Deciding to Enable Features

Not every feature in the matrix needs to be enabled. Add fields for:
- Business criticality.
- Expected benefit.
- Alternative without option.
- Operational complexity.
- License cost/impact.
- Rollback method.
- Owner.
- Decision date.

A feature should only be put into production when:
1. There is a clear business need.
2. The release and architecture support it.
3. `COMPATIBLE` meets the condition.
4. Edition and option are appropriate.
5. License entitlement is confirmed.
6. Testing and operational readiness are in place.
7. An approved rollback/mitigation exists.

## 14. End-to-End Feature Verification Workflow

### Step 1. Write the Business Requirement

Describe the desired outcome; do not start with an option name. For example: need to reduce reporting time, need instance failover, or need to store multi-tenant data.

### Step 2. Select Candidate Features

Identify Oracle capabilities that can meet the need. Note alternatives that do not require the corresponding option if available.

### Step 3. Lock the Target Environment

Record:
- Database release/RU.
- Edition.
- Platform.
- CDB/PDB topology.
- `COMPATIBLE`.
- RAC/Data Guard/cloud configuration.
- JDBC/driver/application version if impacted.

### Step 4. Consult Exact-Release Documentation

Read the corresponding Licensing Information User Manual, New Features Guide, Upgrade Guide, and Release Notes. Save the URL/document version and lookup date.

### Step 5. Perform Technical Verification

Use dictionary/dynamic views, parameters, DDL, and tests to confirm the feature is available, configured, and behaves as required.

### Step 6. Check Usage

Cross-check `DBA_FEATURE_USAGE_STATISTICS` and runtime evidence. Identify what limitations the detector has; do not interpret the numbers into legal conclusions on your own.

### Step 7. Confirm Entitlement

The license owner cross-checks the contract, SKU, metric, deployment scope, and cloud terms. If evidence is missing, the status must be `Unknown` or `Contract review`.

### Step 8. Approve and Record Decision

Save the technical approver, license owner, date, scope, and conditions. Do not enable a production feature before completing the required gates.

### Step 9. Test and Monitor

Test functionality, performance, backup/restore, HA/DR, monitoring, and applications. Monitor usage and resources after deployment.

### Step 10. Periodic Review

Re-review when:
- Upgrading release/RU.
- Changing edition or platform.
- Migrating on-premises to cloud.
- Adding nodes/CPUs/PDBs.
- Enabling an option or management pack.
- Changing contracts/ULA.
- Changing workloads or features actually used.

## 15. Controlling `COMPATIBLE` in the Upgrade Lifecycle

### 15.1. Before Upgrade

- Record the current `COMPATIBLE`.
- Read the compatibility requirements of the target release.
- Confirm the upgrade path and downgrade window.
- Identify features requiring the new compatibility level.
- Do not raise the parameter earlier than required by the upgrade guide.

### 15.2. After Upgrade but Before Raising COMPATIBLE

- Confirm database stability.
- Compile and check invalid objects.
- Run smoke/regression tests.
- Verify backup/recovery.
- Confirm application and client compatibility.
- Evaluate whether downgrade capability is still needed.

### 15.3. When Deciding to Raise COMPATIBLE

- Have change approval.
- Backup/restore point has been verified.
- Understand downgrade restrictions.
- Set a value supported by Oracle for the release.
- Restart if required by the parameter.
- Confirm the new value.
- Re-run regression tests.
- Record the change record and update the matrix.

### 15.4. Do Not Use COMPATIBLE to Mask Errors

If a feature does not work, do not arbitrarily increase `COMPATIBLE`. The root cause may be edition, option, grants, other parameters, RU, platform, or misconfiguration. Identify the right gate before making changes.

## 16. Managing License Usage and Audit Evidence

### 16.1. Minimum Evidence

Each feature should have:
- Feature name and definition.
- Database/host/cluster/cloud service scope.
- Release/RU and edition.
- COMPATIBLE.
- Option/pack requirement.
- Contract/order reference.
- License metric and quantity as verified by the responsible owner.
- Technical configuration/usage evidence.
- Technical owner and license owner.
- Verification date.
- Decision and exceptions.

### 16.2. Usage Monitoring Is Not a License Calculator

`DBA_FEATURE_USAGE_STATISTICS` is a data source for investigating feature usage. It does not replace:
- Oracle license audit process.
- License agreement.
- Ordering document.
- Metric calculation.
- Contract amendment.
- Advice from a license specialist.

Do not calculate license counts yourself from `DETECTED_USAGES` or `AUX_COUNT`. These fields are not the number of licenses to purchase.

### 16.3. Store Evidence with Access Control

Store SQL outputs, reports, and contract references in a repository with appropriate permissions. Mask sensitive information:
- Hostname/IP if classified.
- Username/service accounts.
- Contract pricing and commercial terms.
- Serial/asset identifiers.
- Customer data.

Technical reports should point to protected contract documents rather than copying commercial terms into shared logs.

## 17. Common Mistakes When Building a Matrix

| Mistake | Consequence | How to Handle |
|---|---|---|
| Recording only database release | Misses RU and COMPATIBLE | Record full release/RU/COMPATIBLE |
| Treating V$OPTION TRUE as licensed | Uses options without entitlement | Cross-check contract and licensing manual |
| Treating feature usage = license count | Incorrect metric calculation | License owner calculates per contract |
| Assuming Enterprise Edition includes all options | Enables unentitled options | Verify each option/pack |
| Using an older release's manual | Applies wrong conditions | Choose exact manual for release/platform |
| Applying on-prem rules to cloud | Wrong metric/entitlement | Check service terms and BYOL |
| Omitting CDB/PDB | Misses multitenant scope | Inventory exact containers and contract |
| Treating `COMPATIBLE` as a license switch | Confuses technical with legal | Separate compatibility and entitlement |
| Enabling features before approval | Creates unplanned usage | Enforce technical/license gates |
| Checking only enabled features | Misses features invoked by another workload | Combine configuration, usage, and application inventory |
| Skipping review on upgrade | Features may be deprecated/desupported | Update matrix on every upgrade |
| Treating no usage seen as unused | Misses detector limitations | Review DDL, SQL, applications, and audits |
| No owner assigned | Nobody responsible for updates | Assign technical and license owners |
| Not saving evidence | Hard to justify decisions | Save source, date, results, and approvals |

## 18. Hands-On Exercise: Building a Matrix for an Oracle Environment

This lab uses a test database or a clone. Do not enable options, change `COMPATIBLE`, or run licensed features on production just to test.

### Step 1. Record the Environment

Collect:
- `V$VERSION`.
- `V$INSTANCE`.
- `V$DATABASE`.
- `V$PARAMETER` for `COMPATIBLE`.
- PDBs/services.
- Oracle Home inventory and RU.

### Step 2. Inventory Options/Components

Run:
- `V$OPTION`.
- `DBA_REGISTRY`.
- `DBA_REGISTRY_SQLPATCH`.

Save output, recording timestamp and container.

### Step 3. Inventory Feature Usage

Read `DBA_FEATURE_USAGE_STATISTICS` per release. Clearly note this is usage evidence, not entitlement.

### Step 4. Select Five Business Features

Examples:
- Partitioning.
- Advanced Compression.
- RAC.
- Diagnostics Pack.
- Multitenant.

Do not enable new features in the lab without confirming entitlement. Only create inventory rows and mark them `Verify`.

### Step 5. Consult the Exact-Release Manual

For each feature, look up:
- Availability.
- Edition.
- Option/pack.
- `COMPATIBLE`.
- Platform/architecture restrictions.
- Deprecated/desupported status.

Record document title, release, and lookup date.

### Step 6. Cross-Check License Inventory

The license owner confirms:
- Product SKU.
- Metric.
- Quantity.
- Deployment scope.
- Contract/ordering document.
- Cloud/BYOL terms if applicable.

If data is missing, leave it as `Unknown`; do not guess.

### Step 7. Populate the Matrix

Each row has technical status, license status, evidence, and owner. Unconfirmed features must remain in `Blocked` or `Contract review` status.

### Step 8. Check COMPATIBLE

Cross-check compatibility requirements and the downgrade plan. Do not change parameters in the lab just to make the matrix show `Yes`.

### Step 9. Approve

DBA/architect confirms technical readiness; license owner/legal procurement confirms entitlement. Record the date and approval scope.

### Step 10. Save and Schedule Review

Store the matrix in a governance repository with version history. Schedule reviews upon upgrades, contract changes, or topology changes.

## 19. Checklist Before Enabling a Feature

### Technical
- Exact release/RU verified.
- Feature is still supported.
- Edition satisfies requirements.
- `COMPATIBLE` satisfies requirements.
- Technical option/pack is properly configured.
- Platform/topology is suitable.
- Application/drivers are compatible.
- Tests and rollback/mitigation exist.

### License
- Licensing manual for exact release cross-checked.
- Product SKU/contract confirmed.
- Metric and deployment scope confirmed.
- Option/management pack entitlement confirmed.
- Cloud/BYOL conditions confirmed if applicable.
- License owner approved.
- Evidence saved.

### Operations
- Owner assigned.
- Monitoring and usage evidence enabled appropriately.
- Backup/restore and DR evaluated.
- Resources and performance benchmarked.
- Change record clearly logs enablement time.
- Matrix updated.

## 20. Self-Check Questions

**Question 1.** Why do you need a feature matrix instead of just checking the release?

**Answer:** Because usability depends simultaneously on release/RU, `COMPATIBLE`, edition, option/pack, entitlement, and architecture.

**Question 2.** Is `COMPATIBLE` a license switch?

**Answer:** No. It is a database technical compatibility level and does not grant rights to use options.

**Question 3.** What does `V$OPTION` indicate?

**Answer:** The technical status of certain options in the database environment; it does not prove license entitlement.

**Question 4.** Is `DBA_FEATURE_USAGE_STATISTICS` a license calculator?

**Answer:** No. It records certain detected usage and has limitations; it does not replace contracts or metric calculations.

**Question 5.** Does Enterprise Edition include every option?

**Answer:** No. Many database options and management packs have separate licensing conditions.

**Question 6.** Why must RU be recorded?

**Answer:** The same release can differ in patch level, bug fixes, and behavior; the RU is part of the environment that must be verified.

**Question 7.** Why should you not raise COMPATIBLE immediately after an upgrade?

**Answer:** Raising it may restrict downgrades; testing, backups, and change approval must be completed first.

**Question 8.** Where does license entitlement come from?

**Answer:** From contracts, ordering documents, license agreements, and cloud service terms in effect for the organization/deployment.

**Question 9.** How should Diagnostics Pack and Tuning Pack be verified?

**Answer:** Inventory actual workflows and cross-check specific features against the Licensing Information User Manual for the exact release and contract.

**Question 10.** Why can't multitenant rules from one release be applied to another?

**Answer:** Feature conditions and licensing may change by release and service model.

**Question 11.** How should technical status and license status be separated?

**Answer:** One column records whether the feature is supported/configured/testable; another records whether entitlement is confirmed.

**Question 12.** When must a feature be Blocked?

**Answer:** When there is insufficient technical, compatibility, or entitlement evidence to approve production use.

**Question 13.** Why is an owner needed for each row?

**Answer:** So someone is accountable for updating the feature, evidence, contract, and decisions when the environment changes.

**Question 14.** Should a feature be enabled just because SQL executes successfully?

**Answer:** No. Successful SQL execution only proves technical capability, not right of use.

**Question 15.** When should the matrix be updated?

**Answer:** Upon release/RU upgrades, edition/platform changes, adding PDBs/nodes, enabling options, contract changes, or cloud migrations.

## 21. Conclusion

An Oracle feature matrix must separate technical capability from right of use. Release/RU identifies the software version and feature lifecycle; `COMPATIBLE` controls database compatibility level; edition defines the base feature set; options and management packs may require separate entitlement; contracts and metrics govern what scope the organization is entitled to deploy. CDB/PDB, RAC, platform, and cloud service architectures add further conditions.

Use `V$VERSION`, `V$PARAMETER`, `V$OPTION`, `DBA_REGISTRY`, `DBA_REGISTRY_SQLPATCH`, and `DBA_FEATURE_USAGE_STATISTICS` to gather technical/usage evidence. These views do not prove licensing. Cross-check the Licensing Information User Manual for the exact release against ordering documents, license agreements, and cloud terms; assign a license owner to confirm metrics and deployment scope. When evidence is insufficient, record `Unknown` or `Blocked` instead of guessing.

Each feature enablement must pass through gates: business need, release and architecture support, suitable `COMPATIBLE`, proper edition/option, approved entitlement, testing, and operational readiness. Update the matrix on every upgrade, topology change, or contract change. This governance helps technical teams choose the right capabilities, avoid confusing technical availability with license entitlement, and maintain evidence for deployment decisions.
