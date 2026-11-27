# Checking Editions, Features, Options, and Management Packs Before Using Oracle Database

## 1. Why Must You Verify Before Deploying?

Oracle Database includes many capabilities that are **pre-installed, visible in administrative interfaces, or report `TRUE`**, yet permission to use them depends on **edition**, **version/release**, **deployment model**, **licensed options/management packs**, and **contractual terms**. A statement executing successfully does not prove that using that feature is licensed.

For example, two servers both running Oracle Database Enterprise Edition (EE) can have different usage entitlements:

- Server A is licensed only for base EE and has not purchased Oracle Partitioning or Diagnostics Pack.
- Server B is licensed for EE, Oracle Partitioning, and Diagnostics Pack within the appropriate scope.

A partitioned table or AWR report may run technically on both servers, yet you **must not infer** that both servers are entitled to use them. Moreover, a feature included in a specific Oracle Cloud service is not necessarily included when bringing an on-premises license under Bring Your Own License (BYOL).

**Learning objective:** After this lesson, you will be able to accurately identify the target Oracle environment, distinguish *features* from *options* and *management packs*, read entitlement tables in official documentation, safely inspect technical indicators, and produce an **approved / hold / not permitted** decision before deployment.

> **Scope:** This is a technical guide for decision-making and evidence gathering. Final usage rights must be verified against contracts, ordering documents, licensing policies applicable to your system, and the **Licensing Information User Manual for your exact release**. Do not treat this lesson as a license certification or price list.

## 2. Five Layers of Information to Separate

| Layer | Question to Answer | Examples |
| --- | --- | --- |
| **Database offering / edition** | Which product is running? | Standard Edition 2 (SE2), Enterprise Edition (EE), Oracle AI Database Free, EE on engineered systems |
| **Release and environment** | Which version, deployed where? | Oracle Database 19c on-premises, Oracle AI Database 26ai on OCI Base Database Service, OCI BYOL |
| **Feature** | Which specific capability is desired? | Creating partitions, opening a standby read-only while applying redo, generating AWR reports |
| **Option** | Does this feature belong to a separately licensed option? | Oracle Partitioning, Active Data Guard, Advanced Security, Advanced Compression, Real Application Clusters (RAC) |
| **Management pack** | Does the admin/monitoring task require a separate pack? | Oracle Diagnostics Pack, Oracle Tuning Pack, other Enterprise Manager management packs |

**Edition** is the baseline product scope. **Feature** is a specific behavior. **Option** extends capability sets often purchased separately on EE on-premises. **Management pack** grants rights to a suite of admin tools, reports, APIs, or screens. Invoking an API directly can still fall under the same pack as clicking the corresponding button in Enterprise Manager.

The reasoning chain to follow is:

```text
Business need
    │
    ▼
Specific feature / operation
    │
    ▼
Licensing Information manual for the exact release
    │
    ├── Included in offering/edition? ──► Check limits & conditions
    │
    ├── Belongs to an option? ────────────► Verify option entitlement
    │
    └── Belongs to a management pack? ────► Verify pack entitlement & prerequisites
    │
    ▼
Contract + deployment model + server/processor/user scope
    │
    ▼
Document decision and evidence before enabling/using
```

Never skip the middle verification steps under the assumption that "EE includes everything" or "if the UI shows it, it is permitted."

## 3. Identifying the Exact Offering Before Reading Feature Tables

### 3.1. Common Offering Categories

| Offering | Practical Meaning | What to Check |
| --- | --- | --- |
| **SE2** | Edition for applications fitting SE2 scale and feature limits | Technical limits, licensing metrics, EE-only features; does not automatically carry EE options |
| **EE on-premises** | Expanded edition serving higher workloads and requirements | EE **does not mean** every extra-cost option and pack is purchased |
| **EE on engineered systems** | EE running on Exadata/Oracle Database Appliance or Oracle-defined combinations | Capabilities and licensing differ per system; check the **EE-ES** column and footnotes |
| **Oracle AI Database Free / Free, XE editions per release** | Free products with distinct terms, resource caps, and feature lists | Read the exact Free/XE terms for that release; do not apply EE/SE2 policies loosely |
| **OCI Database Service** | Managed service with tiers such as Base Database Service SE, EE, EE-HP, EE-EP; Exadata Database Service | Each tier has a different list of **included** options/packs; distinguish license-included from BYOL |
| **Other cloud deployments / BYOL** | Software and licenses deployed onto another environment | Verify cloud policies and eligible BYOL scope; do not apply OCI service columns mechanically |

The **Oracle AI Database 26ai** manual currently lists columns such as `Free`, `SE2`, `EE`, `EE-ES`, `BaseDB SE`, `BaseDB EE`, `BaseDB EE-HP`, `BaseDB EE-EP`, and `ExaDB`. For instance, an option may be *extra cost* for EE on-premises while *included* in an OCI tier. The **19c** manual lists a different set of offerings (reflecting offerings as of that release); always open the matching manual instead of mixing tables across two versions.

### 3.2. Pinpointing Release Timing and Licensing Scope

Before checking features, record at least:

1. **Running version:** release and update level, e.g., `19c` with its Release Update, or `26ai`.
2. **Offering:** SE2, EE, EE-ES, Free, or the specific OCI service/tier name.
3. **Where it runs:** bare metal, VM, cluster, engineered system, or cloud; production, DR, test, or dev environment.
4. **Purchased/granted entitlements:** ordering documents, contracts, SKU/entitlements, BYOL terms, or service-included items.
5. **Entitlement scope:** hosts, processors/cores, users, standby/DR environments, and contract term.

Metrics like **Processor** and **Named User Plus**, as well as partitioning/virtualization policies, can alter how required licensing scope is calculated. You cannot verify license sufficiency merely by counting CPUs in `V$OSSTAT` or reading the edition name. Apply the Oracle terms and policies effective for your exact deployment.

## 4. How to Read Oracle's Entitlement Matrix

In the *Licensing Information User Manual*, locate the section **Permitted Features, Options, and Management Packs by ... Offering**. The 26ai manual explains:

- **`Y`**: capability is listed as available for that offering, **not necessarily free**; read the `Notes` column to see if an option/pack or other condition applies.
- **`N`**: not available in the corresponding offering.
- **`N/A`**: not applicable in that column's context.
- **`Extra cost option/pack`**: requires purchasing entitlement to the corresponding add-on product.
- **`Included option/pack`**: included in the specified offering, still subject to limits, service terms, and BYOL rules.

A summary table helps you know *which entry to check*; it never replaces the manual. The table below uses **EE/SE2 on-premises** as a common illustration and states only baseline status for representative items per current manuals; always verify against your exact release:

| Need / Feature | EE on-premises | SE2 on-premises | What to Recognize |
| --- | --- | --- | --- |
| Standard `CREATE TABLE`, transactions, B-tree indexes | Base capability | Base capability | Still check advanced clauses in DDL, configs, or drivers used |
| **Table partitioning** | Typically requires **Oracle Partitioning** extra-cost option | No corresponding Oracle Partitioning option | Partitioning a table/index differs from simply having a date column and index |
| **Multi-instance RAC** | Typically requires **Oracle RAC** extra-cost option | No EE RAC | RAC differs from Data Guard and is not equivalent to all HA forms |
| **Data Guard Redo Apply** | Base Data Guard capability in EE | Not available | Distinguish basic standby from **Active Data Guard** extended features |
| **Active Data Guard** | Typically requires **Active Data Guard** extra-cost option | Not available | Example: querying a physical standby while redo is actively applied |
| **Column/tablespace TDE** | Typically requires **Advanced Security** extra-cost option | Not available as an SE2 on-premises option | Distinct from TLS/native network encryption |
| **Advanced Row/LOB Compression** | Typically requires **Advanced Compression** extra-cost option | Not available | Do not lump Basic Table Compression or certain RMAN/Data Pump modes under the same rule |
| **In-Memory Column Store** | Typically requires **Database In-Memory** option; special rules exist for **In-Memory Base Level** | Not available | Check `INMEMORY_SIZE` caps, compression modes, and release rules |
| **AWR/ADDM/ASH** | Typically requires **Diagnostics Pack** | Packs not available as in EE | Some view exceptions exist; check the management packs section |
| **SQL Tuning Advisor, SQL Profiles, Real-Time SQL Monitoring** | Typically requires **Tuning Pack**, with **Diagnostics Pack** as a prerequisite | Packs not available as in EE | Accessing via SQL, PL/SQL APIs, or UI still requires license verification |

**Do not apply this table to Oracle AI Database Free or an OCI tier.** For example, the 26ai manual lists **Oracle Partitioning, Advanced Compression, Advanced Security, Diagnostics Pack, and Tuning Pack** among items included in `Free`, yet Oracle AI Database Free has separate usage terms and resource limits. Likewise, a higher OCI tier may include options that another tier omits; BYOL carries specific provisions detailed under *Special License Rights*.

### Example: `Y` May Still Require an Add-On Purchase

In the 26ai feature matrix, Oracle Partitioning can show `Y` in the `EE` column while the notes column states **EE and EE-ES: Extra cost option**. `Y` indicates the capability exists for that edition, **not** that every EE customer has paid for the option.

## 5. Option Groups Commonly Confused

### 5.1. Partitioning: Table Design vs. Partitioning Entitlement

Technically, partitioning splits data by range, list, hash, or composite rules; it is commonly used to manage large datasets, data lifecycles, and certain query patterns. However, **DDL using `PARTITION BY` on EE on-premises** requires checking Oracle Partitioning entitlement before running.

```sql
-- Syntax illustration; DO NOT run on a system without verified Partitioning entitlement.
CREATE TABLE sales_events (
    event_id     NUMBER NOT NULL,
    event_date   DATE   NOT NULL,
    total_amount NUMBER(12, 2)
)
PARTITION BY RANGE (event_date) (
    PARTITION p_2026_h1 VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Without Oracle Partitioning entitlement, use ordinary table design, well-chosen indexes, application-level archiving, or evaluate changing offerings. The fact that "creating a partitioned table runs fine" does not alter licensing terms.

### 5.2. Data Guard vs. Active Data Guard

- **Oracle Data Guard** (such as Redo Apply on a physical standby) is a set of standby and redo-synchronization capabilities. It is included in EE according to the release's licensing table.
- **Oracle Active Data Guard** adds capabilities listed under the option—most notably **physical standby with real-time query** while receiving/applying redo. Using that capability on EE on-premises typically requires the extra-cost option.
- Licensing conditions may apply to **both the primary and the standbys using Active Data Guard features**. Do not inspect just one server; verify the entire topology.

Therefore, saying "we want a standby server" is not enough to choose between Data Guard and Active Data Guard: specify **whether the standby is opened for reads during apply**, the topology, and the exact SLA.

### 5.3. Advanced Security vs. Connection Encryption

**Transparent Data Encryption (TDE)** for columns/tablespaces, **Data Pump file encryption**, **RMAN disk backup encryption**, and **Data Redaction** fall under Oracle Advanced Security per the 26ai/19c manuals. Conversely, Oracle explicitly notes that **network encryption, network integrity, TLS/SSL, and certain strong authentication mechanisms are no longer part of the Advanced Security option** in licensed editions of supported releases.

This has two practical consequences:

1. Do not reject enabling TLS merely for lacking Advanced Security when the release documentation permits it.
2. Do not infer from "TLS is enabled" that TDE is also licensed; they are separate features.

TDE rights may be included or specially granted in certain OCI/BYOL offerings. Verify the exact row and notes rather than carrying EE on-premises conclusions over to OCI.

### 5.4. Advanced Compression: Identify the Exact Mode

Oracle Advanced Compression covers capabilities such as Advanced Row Compression, Advanced LOB Compression/Deduplication, certain RMAN compression modes, Data Pump compression, Advanced Index Compression, and related features. **Not every occurrence of `COMPRESS` in Oracle shares the same license rule.**

For example, the 26ai manual documents specific exceptions: `RMAN DEFAULT COMPRESS` does not require the Advanced Compression option, and `COMPRESSION=METADATA_ONLY` in Data Pump does not require that option. That does **not** mean all other backup/export compression modes are free. Always match the exact command, parameter, algorithm, and release footnotes.

### 5.5. Multitenant: Counting PDBs and Reading Offering Limits

A **CDB** (container database) can hold multiple **PDBs** (pluggable databases). The permitted PDB count cannot be inferred from `MAX_PDBS` or from Oracle allowing PDB creation via SQL.

Examples from the **26ai** manual:

- Without the Oracle Multitenant add-on, applicable offerings allow up to **3 user-created PDBs** per CDB under manual conditions.
- On EE on-premises, Oracle Multitenant is an **extra-cost option** when exceeding the option-free limit. Option limits and system caps can differ between EE and EE-ES.
- `Free` is documented as an **included option** for up to **16 PDBs**, though practical PDB count remains bounded by Free resource limits.
- `BaseDB EE-HP`, `EE-EP`, and `ExaDB` carry separate notes; **BYOL** may be capped at 3 PDBs without the Oracle Multitenant option.

Keep **user-created PDBs** separate from system containers like `PDB$SEED` rather than lumping them together arbitrarily. For 19c or other releases, read that release's matrix and any relevant version/patch conditions.

### 5.6. Database In-Memory and Capped Exceptions

Oracle Database In-Memory is normally a separately licensed option on EE on-premises. However, the 26ai manual also describes **Database In-Memory Base Level** for evaluation with constraints such as a maximum **16 GB in-memory area per CDB** (per instance in RAC), fixed compression settings, and certain disabled capabilities. Never treat every `INMEMORY_SIZE > 0` case as identical; verify the exact mode and permitted limits.

## 6. Management Packs: Risks Coming from Admin Tools

An application developer might never partition a table or enable RAC, yet a DBA or monitoring suite can still inadvertently trigger features belonging to a management pack. That is why license checks must include **dashboards, scheduled scripts, third-party tools, and APIs**.

| Pack | Representative Capabilities | Notes |
| --- | --- | --- |
| **Diagnostics Pack** | Automatic Workload Repository (**AWR**) reports, Automatic Database Diagnostic Monitor (**ADDM**), Active Session History (**ASH**), and corresponding APIs/views | Typically an extra-cost pack on EE on-premises; not all historical performance data is free to use |
| **Tuning Pack** | SQL Tuning Advisor, SQL Access Advisor, SQL Profiles, Real-Time SQL Monitoring, and related APIs | Typically an extra-cost pack on EE on-premises; **requires Diagnostics Pack** first |
| **Other Enterprise Manager packs** | Database Lifecycle Management, Data Masking and Subsetting, pack-specific admin features | Must check each pack's table, offering, GUI/API functions, and license conditions separately |

### 6.1. What Does `CONTROL_MANAGEMENT_PACK_ACCESS` Control?

The parameter `CONTROL_MANAGEMENT_PACK_ACCESS` has three values:

| Value | Pack Capabilities Technically Enabled |
| --- | --- |
| `NONE` | Disables Diagnostics/Tuning capabilities governed by this parameter |
| `DIAGNOSTIC` | Enables Diagnostics group, disables Tuning |
| `DIAGNOSTIC+TUNING` | Enables both groups |

According to the **Oracle Database 19c Database Reference**, the default for EE is `DIAGNOSTIC+TUNING`, while other editions default to `NONE`. In the **26ai** documentation, `Free` also defaults to `DIAGNOSTIC+TUNING`. **A default parameter value is a technical setting, not proof that the pack was purchased.**

Read the current configuration (query-only):

```sql
SELECT name, value
FROM   v$parameter
WHERE  name = 'control_management_pack_access';
```

If the organization lacks pack rights, DBAs must review system parameters and admin tool usage paths. Changing this parameter is a system change that affects monitoring/diagnostics and should follow approved change procedures. Conversely, **setting `NONE` does not erase past usage history** and does not replace entitlement verification.

### 6.2. Not Just the GUI: Packages, Views, and Scripts Are Also in Scope

The 26ai manual lists within Diagnostics Pack scope APIs and objects such as `DBMS_WORKLOAD_REPOSITORY`, `DBMS_ADDM`, `V$ACTIVE_SESSION_HISTORY`, many `DBA_HIST_*` views, and corresponding AWR/ASH/ADDM scripts. Tuning Pack can include `DBMS_SQLTUNE`, `DBMS_SQL_MONITOR`, `V$SQL_MONITOR`, and `V$SQL_PLAN_MONITOR`, subject to documented rules and exceptions.

**Distinction example:**

```text
Request: "I want to see which SQL is running slowly"

Path A: EXPLAIN PLAN / DBMS_XPLAN.DISPLAY for a SQL statement
        → Check basic plan-explanation capabilities in the manual.

Path B: AWR report / ASH analytics / ADDM
        → Verify Diagnostics Pack first.

Path C: SQL Tuning Advisor / Real-Time SQL Monitoring
        → Verify Tuning Pack and Diagnostics Pack prerequisite first.
```

Do not claim "every `DBA_HIST_*` view requires a paid pack": **the manual explicitly lists exceptions**, such as `DBA_HIST_SNAPSHOT`, `DBA_HIST_DATABASE_INSTANCE`, `DBA_HIST_SNAP_ERROR`, `DBA_HIST_SEG_STAT`, `DBA_HIST_SEG_STAT_OBJ`, and `DBA_HIST_UNDOSTAT`. Conversely, having `SELECT` on a view or `EXECUTE` on a package **does not** mean you are licensed to use all of its functions. Check the exact exception list and conditions for your release.

## 7. Inspecting the Environment with SQL: Gathering Signals, Not Certifying Licenses

The queries below are strictly **read-only informational checks**. They do not create options, enable packs, or trigger paid operations. Run them with an account granted appropriate metadata read privileges; in a multitenant CDB, understand the container scope of your query session.

### 7.1. Identify Release and Edition

```sql
-- Product banner; content format varies across releases.
SELECT banner
FROM   v$version;

-- Version information of the current instance.
SELECT instance_name, version, status
FROM   v$instance;
```

Record these outputs alongside Oracle Home, RU/patch inventory, and offering details from deployment records. Never infer licensing entitlement from the banner.

### 7.2. Check Options Reported Available by Oracle

```sql
SELECT parameter, value
FROM   v$option
WHERE  parameter IN (
           'Partitioning',
           'Real Application Clusters',
           'Advanced Compression'
       )
ORDER BY parameter;
```

`V$OPTION` reflects **binary or environment capabilities/characteristics**, depending on option and release. `TRUE` **does not mean** "purchased," "permitted," or "used." `FALSE` must likewise be interpreted in context of configuration and version. Never use this view as a licensing certificate.

### 7.3. Observe PDBs and Related Parameters

```sql
-- When sufficiently privileged, prefer querying from CDB root to inventory PDBs.
SELECT con_id, name, open_mode
FROM   v$pdbs
ORDER BY con_id;

SELECT name, value
FROM   v$parameter
WHERE  name IN (
           'control_management_pack_access',
           'inmemory_size',
           'max_pdbs'
       )
ORDER BY name;
```

With Multitenant, distinguish `PDB$SEED` from user-created PDBs; with RAC, inspect per-instance settings as needed. Parameters show configuration state and are insufficient to conclude licensing status.

### 7.4. Review Feature Usage Detection History

```sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date
FROM   dba_feature_usage_statistics
WHERE  detected_usages > 0
ORDER BY name;
```

`DBA_FEATURE_USAGE_STATISTICS` is **one signal source** for investigation, not an invoice or proof of entitlement. Rows may reflect historical usage, sampling, internal mechanisms, or version-specific exceptions. `CURRENTLY_USED = 'FALSE'` does not prove a feature was never used; `TRUE` alone does not confirm a licensing obligation until the feature and exceptions are classified.

**Oracle-documented audit script:** The 26ai manual references `options_packs_usage_statistics.sql` (My Oracle Support, document **KB143588**) to summarize option/pack usage and related features. Oracle explicitly notes this report is **advisory** and does not directly represent entitlements or licensing obligations. Organizations should verify script execution, scope, and permissions through internal DBA procedures, reviewing outputs alongside contracts and licensing specialists when needed.

### 7.5. Do Not Confuse Five Distinct States

| State | Accurate Meaning |
| --- | --- |
| **Installed** | Component is present in the Oracle Home or data dictionary |
| **Available / `TRUE`** | Binary/edition marks the technology or option as technically available |
| **Enabled / configured** | Parameter, component, or feature is turned on, including by default |
| **Used / detected** | Technical observation associated with the feature occurred within a time window |
| **Licensed / entitled** | Authorized for use under contract, offering, conditions, and deployment scope |

These five states can differ. Deployment decisions require **entitled** status, cross-checked against technical capabilities and the exact feature to be used.

## 8. Approval Workflow Before Using a Feature

### Step 1: Describe the Actual Behavior, Not Just the Technology Name

For example, instead of writing only "Data Guard," write: "One physical standby; need to run reporting queries on the standby while redo continues applying." That specific behavior separates basic Data Guard from Active Data Guard. Instead of "compression," specify Advanced Row Compression, the exact Data Pump `COMPRESSION` value, or the exact RMAN backup compression type.

### Step 2: Lock In Release and Offering Column

Obtain the edition from metadata and verify against procurement/deployment records. Open the exact 19c, 26ai, or target release manual; locate the exact `EE`, `SE2`, `Free`, or OCI service column. Also read `Notes`, **Options ... and Their Permitted Features**, **Management Packs ... and Their Permitted Features**, **Special License Rights**, and **Restricted Use Licenses** where applicable.

### Step 3: Separate Entitlements from Technical Evidence

Collect SQL observations (`V$VERSION`, `V$OPTION`, `DBA_FEATURE_USAGE_STATISTICS`, parameters), configuration records, scripts/jobs, and tools. Use this evidence to spot configs/usage needing review while obtaining entitlement records from contracts or license management.

### Step 4: Check Prerequisites and Blast Radius

For instance, Tuning Pack requires Diagnostics Pack; Active Data Guard can implicate both primary and standby; RAC/multitenant/virtualization change verification scope compared to a single instance. Separately check development, staging, disaster recovery, cloud environments, and hosts added later if they use the feature.

### Step 5: Record One of Three Evidence-Backed Decisions

| Decision | Condition | Action |
| --- | --- | --- |
| **APPROVED** | Release documentation permits it, matching entitlement is verified, all conditions are met | Record approver, timestamp, and scope, then proceed |
| **HOLD / VERIFY** | Missing contract, unclear SKU, unconfirmed option/pack, or conflicting evidence | Do not use feature yet; consult license owner / DBA / Oracle licensing as needed |
| **NOT PERMITTED** | Offering does not support it or required entitlement is absent | Redesign using permitted features, change offering, or acquire entitlement before use |

### Step 6: Bind the Decision to Change Management

Whenever creating DDL, upgrading releases, enabling monitoring jobs, switching cloud tiers, adding standbys, changing virtualization, or adding PDBs, re-verify because prior approval may apply only within the original scope.

## 9. Real-World Decision Examples

### Scenario A — An App on SE2 Wants Monthly Partitioning

**Need:** large `orders` table; team wants `PARTITION BY RANGE (created_at)` to manage monthly data.

**Check:** Oracle Partitioning is not available as an SE2 option in the offering matrix. The SQL engine accepting syntax or having installed components does not override this restriction.

**Decision:** `NOT PERMITTED` for this design on SE2; consider indexing, application-driven archiving, data model adjustments, or migrating to EE with Partitioning entitlement if genuinely required.

### Scenario B — EE Has AWR Enabled by Default Without Diagnostics Pack

**Need:** run `awrrpt.sql` daily and email reports to operations.

**Observation:** `CONTROL_MANAGEMENT_PACK_ACCESS` may default to `DIAGNOSTIC+TUNING` on EE even when the contract covers only base EE.

**Check:** `awrrpt.sql` and AWR/ADDM/ASH features belong to Diagnostics Pack (save for object-specific exceptions explicitly listed in the manual). Default configuration is not entitlement proof.

**Decision:** `HOLD / VERIFY`; do not enable new AWR jobs yet. DBA and license owner must verify Diagnostics entitlement, audit existing jobs/scripts, and align monitoring with existing rights.

### Scenario C — EE Needs a Standby That Applies Redo and Serves Dashboards

**Need:** open the standby so dashboards query near-real-time data while redo continues applying.

**Check:** this is **Active Data Guard** *physical standby real-time query*, distinct from basic Data Guard Redo Apply. On-premises EE typically requires the Active Data Guard option, and scope covers both primary and standbys using that capability.

**Decision:** `APPROVED` only after verifying option entitlement, involved system count, and valid contract terms; otherwise evaluate standby architectures without that add-on feature or alternative reporting paths.

### Scenario D — Lab Using Oracle AI Database 26ai Free

**Need:** test partitioning, TDE, or AWR in a lab using Free.

**Check:** the 26ai manual lists many options/packs as **included** in `Free`; however, Free carries strict resource caps and separate terms. Never extrapolate `Free` entitlements to assume EE on-premises production gets those options free of charge.

**Decision:** verify Free terms and lab-appropriate limits before experimenting; when moving from lab to commercial environments, re-evaluate from scratch.

### Scenario E — Same "EE" Label Across Two OCI Tiers

**Need:** Team A runs BaseDB EE, Team B runs BaseDB EE-HP; both want to enable Advanced Compression.

**Check:** per the 26ai manual, Advanced Compression is **not included** in base `BaseDB EE`, yet is listed as **included** in `BaseDB EE-HP` (and certain higher offerings). Changing tiers or BYOL status alters corresponding rights.

**Decision:** do not apply a single blanket policy to both teams; check the exact service/tier and license model of each deployment.

## 10. Pre-Deployment Verification Checklist Template

Copy this template into change requests, design reviews, or internal governance records:

| Field | Example Value to Fill In |
| --- | --- |
| System / environment | `order-db-prod`, production, primary + standby |
| Oracle version and RU | `19c`, specific RU |
| Edition / offering | `EE on-premises` or full OCI service name |
| Requirement | "7-day SQL performance report" |
| Planned feature/API/screen/script | `awrrpt.sql`; associated jobs and users |
| Relevant option/management pack | `Diagnostics Pack` |
| Manual page/table reference | Link to release and exact feature/pack row |
| Contractual entitlement | Entitlement/document ID, processor/user scope, and systems |
| Technical evidence | Banner, parameters, job list, usage under review |
| Additional conditions | Primary/standby, cloud/BYOL, PDB caps, pack prerequisites |
| Decision / approver / date | `APPROVED`, `HOLD / VERIFY`, `NOT PERMITTED` |
| Re-verification triggers | Release/tier change, added nodes/PDBs, enabling tools, architecture change |

**A complete record** explicitly states *which feature will be used*, *where the corresponding entitlement resides*, and *the scope of applicability*. Writing "Oracle EE → OK" or attaching a screenshot of `V$OPTION = TRUE` is insufficient.

## 11. Common Mistakes That Cause Licensing Issues

1. **"Enterprise Edition includes every feature."** False: many Oracle options/packs remain separately licensed depending on the offering.
2. **"`V$OPTION.VALUE = TRUE` means we are licensed."** False: it is a technical indicator, not proof of usage rights.
3. **"Oracle pre-installed the package, so running it is allowed."** False: GUI, SQL, PL/SQL, scripts, and third-party tools can all fall under the same pack.
4. **"Having Tuning Pack means we don't need Diagnostics Pack."** False: Tuning Pack has Diagnostics Pack as a manual prerequisite.
5. **"`DIAGNOSTIC+TUNING` is the default, so it's free."** False: a default is merely a technical parameter state.
6. **"Data Guard and Active Data Guard differ only in name."** False: real-time query on a standby actively applying redo is a classic case requiring the Active Data Guard option.
7. **"Every form of compression requires Advanced Compression."** False: specific modes and exceptions exist; match the exact operation.
8. **"Free and OCI include it, so EE on-premises does too."** False: rights are tied to the specific offering, release, and licensing model.
9. **"No usage rows means it was definitely never used."** False: feature usage statistics are subject to sampling, timing, and detection logic.
10. **"Dev, test, and standby are automatically license-free."** There is no such blanket rule; review contractual terms for each situation.

## 12. Matrix-Reading Practice Exercises

No state-changing commands are required. Answer each on your own before checking the hints:

**Exercise 1.** An EE on-premises database returns `Partitioning = TRUE` in `V$OPTION`. The dev team wants to create partitioned tables. What additional evidence is needed?

**Exercise 2.** On EE, `CONTROL_MANAGEMENT_PACK_ACCESS` displays `DIAGNOSTIC+TUNING`, yet procurement has not provided an entitlement record. Can you run SQL Tuning Advisor?

**Exercise 3.** Both `BaseDB EE` and `BaseDB EE-HP` environments in OCI want Advanced Compression. Can you make one shared conclusion just because both names include "EE"?

**Exercise 4.** A CDB plans to grow from 3 to 10 user PDBs. What additional factors must be checked?

<details>
<summary>Answer Hints</summary>

1. You need the manual for the exact release/edition, the Oracle Partitioning row, and proof of purchased/included option entitlement with appropriate scope. `TRUE` alone is not enough.
2. Not approved. Tuning Pack requires both Tuning **and** Diagnostics entitlement; a default parameter is not an entitlement. Place in `HOLD / VERIFY`.
3. No. Compare the exact service/tier columns; the 26ai documentation distinguishes the two tiers. Also check license-included vs. BYOL.
4. Release, offering, option-free PDB limit, Oracle Multitenant entitlement, EE/EE-ES/cloud system type, BYOL rules, and current technical/contractual limits.

</details>

## 13. Official Documentation References

The links below are starting points; when opening them, select the documentation matching the **release actually running** and check Oracle's published updates and notes:

1. [Oracle AI Database 26ai — Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html): offering tables, permitted features, options, management packs, usage tracking, and special license rights.
2. [Oracle Database 19c — Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): reference manual for 19c systems; do not substitute 26ai tables.
3. [Oracle Database 19c — `CONTROL_MANAGEMENT_PACK_ACCESS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/CONTROL_MANAGEMENT_PACK_ACCESS.html): values, defaults, and relationship with Diagnostics/Tuning Packs.
4. [Oracle AI Database 26ai — `CONTROL_MANAGEMENT_PACK_ACCESS`](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/CONTROL_MANAGEMENT_PACK_ACCESS.html): note default differences with Free.
5. [My Oracle Support](https://support.oracle.com/) — search **KB143588**, the `options_packs_usage_statistics.sql` script referenced in the 26ai manual; outputs assist usage investigation only and do not certify entitlements.
6. [Oracle Software Investment Guide / Licensing](https://www.oracle.com/corporate/pricing/): use alongside your organization's contracts and licensing records to verify metrics, scope, and terms.

**Final working rule:** verify **exact feature → exact release → exact offering → option/pack and limits → entitlement/contract → usage scope**; deploy only after every link in that chain is confirmed and recorded as evidence.
