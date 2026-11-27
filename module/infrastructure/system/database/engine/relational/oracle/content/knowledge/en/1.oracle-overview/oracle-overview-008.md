# Version, Release, Release Update, and the `COMPATIBLE` Parameter in Oracle Database

In Oracle Database operations, the question "Which version are we running?" can have several answers: **product release family** (19c, 21c, 26ai), **software update level** (such as RU 19.31), **applied patches**, and **on-disk data compatibility level** (`COMPATIBLE=19.0.0`). These pieces of information are related, yet not identical. Understanding the difference helps plan upgrades, security patching, and downgrade feasibility.

This lesson focuses on relational Oracle Database, particularly 19c systems and Oracle AI Database 26ai. Exact syntax and operational procedures may vary by platform, RAC/Data Guard topology, and Oracle Cloud services; when working on a live system, always verify against the documentation for that exact release.

## 1. Four Concepts to Keep Separate

| Concept | Example | Question It Answers | Operational Significance |
| --- | --- | --- | --- |
| **Release / release family** | Oracle Database **19c**, **21c**, Oracle AI Database **26ai** | Which product generation is in use? | Determines feature set, upgrade paths, and support policy. |
| **Release Update (RU)** | **19.31**, **23.26.4** | Up to which quarterly cycle is this release updated? | Delivers bug fixes, security patches, and select enhancements within the same release family. |
| **Specific patch** | RU, Monthly Recommended Patch (MRP), one-off patch | Which patches have been applied to the Oracle Home / database? | Requires verifying both software binaries and post-patch SQL steps. |
| **`COMPATIBLE`** | `19.0.0`, `21.0.0`, `23.9.0` | Up to which compatibility level may on-disk data formats be used? | Can gate certain features and directly governs downgrade capability. |

For example: a database can **run Oracle Database 19c RU 19.31 software** while still keeping **`COMPATIBLE=19.0.0`**. This is completely normal: the RU number is not a value to assign to `COMPATIBLE`.

### 1.1. Release Differs from Edition and Platform

A release name such as **19c** identifies a generation of Oracle Database. **Enterprise Edition**, **Standard Edition 2**, or Free tiers are product/licensing classifications; **Linux**, **Windows**, and deployment architectures are separate dimensions. Two systems both labeled "19c" may differ in edition, patch level, licensed options, and support schedule.

Never infer patch level or feature entitlement solely from the string "19c."

### 1.2. Long Term Support and Innovation Releases

Oracle distinguishes releases designed for extended support lifecycles (**Long Term Support Release**) from releases focused on delivering newer features earlier (**Innovation Release**).

- **19c**: Long Term Support release, widely deployed in enterprise systems.
- **21c**: Innovation Release.
- **23ai → 26ai**: Oracle AI Database **26ai** replaces the **23ai** name/branding starting with the October 2025 RU, serving as the next Long Term Support release. According to Oracle, transitioning from 23ai to 26ai at this milestone is performed via an RU and does not require a major database upgrade or application recertification merely due to the product rename.

Consequently, **26ai does not mean every internal version number starts with `26` everywhere**. Documentation and tools may continue displaying technical version numbers starting with `23`; interpret product names and version numbers in their proper context.

> Support policies and platform coverage change over time. When choosing a release for a new system, confirm current support schedules, application certifications, and official upgrade paths; never infer support status simply from a higher release number.

## 2. Reading Version Numbers and Display Formats

### 2.1. Example with Oracle Database 19c

You may encounter strings like these:

- `19c`: release family name.
- `19.3.0.0.0`: a base software release level of 19c.
- `19.31.0.0.0`: example of a 19c installation updated to **RU 19.31**.
- `19.0.0.0.0`: the **base version** returned in the `VERSION` column, even when `VERSION_FULL` reflects a higher RU.

In 19c, RUs are typically referred to as **19.x** (e.g., 19.30, 19.31). Never read "19.31" as "Oracle 31c" or set `COMPATIBLE=19.31.0` simply because an RU was applied.

Starting in Oracle Database 18c, views can expose both `VERSION` and `VERSION_FULL`. To determine the exact software level, inspect the right column and cross-check the patch inventory.

### 2.2. Special Behavior in Oracle AI Database 26ai

Oracle transitioned from the 23ai label to **Oracle AI Database 26ai** via the October 2025 RU, reflected in versions such as **23.26.0**. Subsequent RUs in 2026 follow forms like **23.26.1**, **23.26.2**, **23.26.3**, and **23.26.4** for quarterly cycles.

Under 26ai's `VERSION_FULL` convention, the five numeric fields carry a different meaning from traditional 19c numbering:

```text
23 . 26 . 4 . 0 . 0
│    │    │   │   └─ recut
│    │    │   └───── Monthly Recommended Patch (MRP) level
│    │    └───────── quarterly RU within the year
│    └────────────── RU year (2026)
└─────────────────── technical base release
```

This illustrates the structure rather than guaranteeing every patch matches a five-field string exactly. With 26ai, the product name can read "26ai" while `VERSION` or `VERSION_FULL` begins with "23." **Do not mechanically apply the exact same positional interpretation to every Oracle generation.**

### 2.3. SQL Queries to Inspect a Running System

Connect with an account authorized to read dynamic performance views and run:

```sql
-- Base version and full version string of the instance (18c and later).
SELECT instance_name, version, version_full
FROM   v$instance;

-- Banner showing product name and release.
SELECT banner_full
FROM   v$version;

-- Currently active on-disk data format compatibility level.
SELECT name, value
FROM   v$parameter
WHERE  name = 'compatible';
```

In SQL*Plus or SQLcl, you can also run:

```sql
SHOW PARAMETER compatible;
```

**Illustrative** output for a 19c system:

```text
VERSION          VERSION_FULL
---------------  -----------------
19.0.0.0.0       19.31.0.0.0

NAME             VALUE
---------------  -------
compatible       19.0.0
```

Correct reading: the software belongs to the 19c release family, is patched to RU 19.31, and uses on-disk data format compatibility 19.0.0.

## 3. Release Update (RU) and the Patch Ecosystem

### 3.1. What Is an RU?

A **Release Update** is a periodic update bundle within an Oracle Database release family, delivering bug fixes, security patches, stability improvements, and occasionally new or expanded features. Oracle releases RUs quarterly, typically in **January, April, July, and October**. RUs are **cumulative**: a newer RU includes fixes from prior RUs on the same branch per Oracle's rules.

Visualize a 19c system:

```text
Oracle Database 19c
     │
     ├── RU 19.29 (10/2025)
     ├── RU 19.30 (01/2026)
     ├── RU 19.31 (04/2026)
     └── RU 19.32 (07/2026)
```

Moving **19.30 → 19.31** is a **patch/update within the same 19c release**. Moving **19c → 26ai** is an **upgrade to a different release family**, requiring compatibility evaluation and a full database upgrade procedure.

Never equate an **RU** with a **major upgrade**: the two operations differ in prerequisites, scope of change, and rollback mechanisms.

### 3.2. RU, MRP, and One-Off Patches

| Update Type | Characteristics | Operational Mindset |
| --- | --- | --- |
| **RU** | Quarterly update bundle, cumulative within a release family. | Primary foundation of a regular patching strategy. |
| **MRP (Monthly Recommended Patch)** | Monthly recommended fix bundle, cumulative on top of **one specific RU**; does not change the RU number. | Can be layered on top of an RU when platform and RU prerequisites match. |
| **One-off / interim patch** | Fixes one specific bug or small bug group, subject to dependencies/conflicts. | Must be checked against the running RU and Oracle Support guidance. |
| **RUR (Release Update Revision)** | Older mechanism; Oracle moved to MRP for current update policy. | May still appear in older documentation or patch histories. |

MRP availability is not identical across all operating systems; Oracle documents the MRP program for **Linux**. Never assume a Linux patch applies to Windows or other platforms.

### 3.3. Software Patching and SQL Patching Are Two Sides of Patching

For many self-managed Oracle Database patches, applying a patch has two layers:

1. **Oracle Home (binaries/inventory):** software files are updated using the appropriate tool (such as OPatch or OPatchAuto depending on environment).
2. **Database SQL registry:** required SQL changes are applied via **`datapatch`** or an equivalent automated step and recorded in **`DBA_REGISTRY_SQLPATCH`**.

Checking only `V$VERSION` or only the installation directory is **insufficient** to conclude all components were patched successfully. If binaries reach the new RU while SQL patching did not complete, the system can remain in a half-updated state.

To inspect software binaries on a self-managed Unix/Linux host:

```bash
$ORACLE_HOME/OPatch/opatch lsinventory
```

Run this at the OS level with `ORACLE_HOME` set to the target instance's home. For Grid Infrastructure, RAC, or multiple Oracle Homes, verify every relevant component per the patch package instructions.

To inspect SQL patch history:

```sql
SELECT action_time,
       patch_id,
       patch_type,
       action,
       status,
       description
FROM   dba_registry_sqlpatch
ORDER  BY action_time DESC;
```

What to look for:

- `PATCH_TYPE='RU'` indicates a Release Update record.
- `ACTION` is `APPLY` or `ROLLBACK`; `STATUS='SUCCESS'` indicates that specific execution succeeded.
- A single patch can have multiple rows due to apply, rollback, or retry attempts. **Never treat a single newest row as the complete current patch state**.
- `DBA_REGISTRY_SQLPATCH` reflects SQL patches; `opatch lsinventory` reflects the Oracle Home. Both sources complement each other.

> On managed Oracle Cloud services, users may not have privileges to run OS-level commands directly. In that case, use the corresponding cloud console/tooling and service maintenance documentation.

### 3.4. Mental Checklist When Scheduling an RU

A sound workflow includes: confirming release, edition, OS, and Oracle Home; downloading the exact RU package and README; checking prerequisites and patch conflicts; testing in a comparable non-production environment; preparing a backup/recovery plan; applying according to instructions for single-instance, RAC, or Data Guard; verifying both binary and SQL patch states, PDB status, and application health; and finally recording the updated version level.

Never rely on one generic OPatch command for every topology. Execution order with RAC, Grid Infrastructure, standby databases, or Autonomous Database differs from a standalone host and must follow the exact README of the package being applied.

## 4. What Does the `COMPATIBLE` Parameter Control?

### 4.1. Actual Effect

`COMPATIBLE` is an **initialization parameter** specifying the Oracle version level with which **on-disk data formats and structures** must remain compatible. When kept at an older level after a software upgrade, Oracle restricts on-disk changes or features incompatible with that level. Some new capabilities still work if they do not introduce incompatible format changes; other features require raising `COMPATIBLE` before they can be used.

Think of these two independent dimensions:

```text
Oracle Database software:   19c RU 19.31
Format compatibility:       COMPATIBLE = 19.0.0
                             ↑
                        Not the RU number
```

`COMPATIBLE` is **not** the Oracle JDBC version, an application SQL compatibility mode, a security patch level, or a guarantee that arbitrary legacy clients will work. Those aspects must be checked via interoperability matrices, driver docs, and application certifications.

### 4.2. Values Worth Remembering

The following values are indicative for common releases; exact allowed ranges depend on the specific release and whether the database is newly created or upgraded.

| Oracle Release | Typical Default `COMPATIBLE` | Minimum Allowed per Upgrade Guide |
| --- | --- | --- |
| Oracle Database **19c** | `19.0.0` | `11.2.0` |
| Oracle Database **21c** | `21.0.0` | `12.2.0` |
| Oracle AI Database **26ai** | `23.9.0` for fresh installs in corresponding RUs from 23.9 onward | `19.0.0` |

**Important note for 26ai:** earlier releases had different defaults, including `23.4.0`, `23.5.0`, and `23.6.0`; starting from RU 23.9, upgrade documentation specifies `23.9.0` as the default for new installations. If **upgrading from an older database**, `COMPATIBLE` may **stay at its existing value** after the database upgrade rather than jumping to the default of a fresh installation. Always **query the actual parameter** rather than guessing from the release name.

Another key distinction: **the minimum `COMPATIBLE` of the target release** does not mean "every source release can directly upgrade." For 26ai, Oracle documents **direct upgrade paths from 19c or 21c**; older versions require an appropriate intermediate upgrade path. Verify direct-upgrade eligibility separately from `COMPATIBLE` eligibility.

### 4.3. Why Raising `COMPATIBLE` Is a Major Decision

Suppose an enterprise upgrades a database from 19c to 26ai. It can perform the database upgrade first while temporarily **keeping `COMPATIBLE=19.0.0`**, if supported by documentation for that path, to allow time to validate applications and preserve a downgrade option.

When `COMPATIBLE` is later raised to a higher value such as `23.9.0`, the system may allow newer on-disk data structures. **You cannot simply change the parameter back to `19.0.0` to return to the old state.** Oracle warns that once `COMPATIBLE` is increased, downgrading the database to a prior release is no longer supported. Returning to an earlier point requires relying on backup/restore strategies or recovery plans prepared **before raising** the parameter, taking into account any data written after the recovery point.

That is why raising `COMPATIBLE` should never be treated as a routine step in every RU installation.

### 4.4. When Should You Change It?

**In Oracle Database 19c/21c:**

- When applying an RU, **keep `COMPATIBLE` unchanged**; e.g., moving from `19.30` to `19.31` does not mean setting `COMPATIBLE=19.31.0`.
- When upgrading to a new release family, consider keeping the old level during a validation window and only raise it once you accept giving up the downgrade path or need a feature that requires the higher level.

**In Oracle AI Database 26ai:**

- The general rule remains not raising `COMPATIBLE` merely for an RU.
- Feature-level exceptions exist. For example, certain **AI Vector Search** capabilities in 23.x RUs require `COMPATIBLE` to be at least **`23.6.0`**. Here, raising the parameter **unlocks a specific required capability**, not "to match the RU number."
- On eligible 26ai RUs, Oracle supports dynamically increasing `COMPATIBLE` under specific constraints; do not extrapolate that mechanism back to 19c.

### 4.5. How to View and Change It: Distinguishing Releases

Read-only query:

```sql
SELECT value
FROM   v$parameter
WHERE  name = 'compatible';
```

In releases like **19c**, once ready to raise it to a supported level, an administrator can update the **SPFILE** and restart the database:

```sql
-- SYNTAX EXAMPLE FOR 19c ENVIRONMENTS ONLY
-- Suppose the current value is lower and you intend to raise it to 19.0.0.
ALTER SYSTEM SET compatible = '19.0.0' SCOPE=SPFILE;

-- The change takes effect after a controlled database restart.
```

Never run this statement without verifying current state, downgrade requirements, recovery strategy, and system runbooks. In RAC environments, all instances must share the same `COMPATIBLE` setting; in CDB/PDB setups, do not set arbitrary per-PDB values (a PDB's value must align with `CDB$ROOT`).

**Advanced note specific to 26ai:** starting in RU 23.9, Oracle documents a way to raise `COMPATIBLE` dynamically (under specific conditions) using this syntax:

```sql
-- Example from the 26ai guide: raising from 23.4.0 to 23.6.0 only.
ALTER DATABASE SET DOWNGRADE COMPATIBILITY TO '23.6.0';
```

Although the keyword contains `DOWNGRADE`, the operation illustrated **raises the `COMPATIBLE` level**. After the dynamic change, the new value must still be persisted in the parameter file/SPFILE to prevent errors on restart. In Data Guard, Oracle requires running it on the standby before the primary; the same level must be maintained across primary and standby. This is **not** a universal replacement for `ALTER SYSTEM ... SCOPE=SPFILE` across all Oracle releases.

## 5. Common Operational Scenarios

### Scenario A — Security Patching Without Changing On-Disk Formats

Current system:

```text
Release:             Oracle Database 19c
RU:                  19.30
COMPATIBLE:          19.0.0
Goal:                apply RU 19.31
```

After updating the RU successfully, the expected state is:

```text
Release:             Oracle Database 19c
RU:                  19.31
COMPATIBLE:          19.0.0
```

What changes is the **software patch level** and potentially SQL patches; `COMPATIBLE` stays the same. Verify via inventory, SQL patch registry, and application checks.

### Scenario B — Upgrading 19c to Oracle AI Database 26ai

A conceptual decision sequence:

1. Verify supported direct-upgrade paths, minimum RU levels, database type, OS platform, drivers, and applications.
2. Record the current `COMPATIBLE` setting and test the upgrade workflow in a test environment.
3. Perform the database upgrade per Oracle's guide; afterward query actual `VERSION_FULL` and `COMPATIBLE` rather than assuming they match.
4. Run regression, performance, backup/restore, and critical business tests; determine how long a downgrade option is still needed.
5. Only after formal approval, **raise `COMPATIBLE`** to the level required by target features, accepting the loss of the prior downgrade path.

If a requirement needs a feature requiring `COMPATIBLE ≥ 23.6.0`, plan the timing of enabling that feature explicitly instead of deciding based solely on the "26ai" name.

### Scenario C — Name Says "26ai", SQL Returns "23.x"

Suppose the banner reads **Oracle AI Database 26ai** while `VERSION_FULL` shows `23.26.4.0.0`. This is an expected numbering pattern in 26ai and does not automatically mean the database is "stuck on 23ai." Confirm against Oracle's version-numbering documentation and `DBA_REGISTRY_SQLPATCH` rather than concluding from the first two digits alone.

### Scenario D — Post-Patch State Looks Contradictory

`opatch lsinventory` shows the Oracle Home has the new RU, yet `DBA_REGISTRY_SQLPATCH` lacks a matching `APPLY/SUCCESS` entry in the database. Inspect the patch logs and `datapatch` execution; never declare completion based solely on binaries. Conversely, a `SUCCESS` row in the SQL patch history does not guarantee every related Oracle Home/instance is at the required level.

## 6. Frequently Asked Questions and Self-Check

**"Does applying an RU automatically change `COMPATIBLE`?"**  
Do not assume so. In 19c/21c, ordinary RUs do not require changing `COMPATIBLE`. In 26ai, the default for **fresh installs** and prerequisites for certain features can depend on the RU; an **upgraded** database may continue retaining its prior value.

**"Can I lower `COMPATIBLE` if I hit an error?"**  
You cannot treat that as a rollback mechanism. Once compatibility is raised, Oracle does not support lowering it back on the same database files in normal operation; rely on a recovery strategy prepared beforehand.

**"Does `COMPATIBLE=19.0.0` mean the database lacks recent RU patches?"**  
False. `COMPATIBLE` governs on-disk format compatibility; the installed RU and patch level are determined via version views, inventory, and the SQL patch registry.

**"Should I set `COMPATIBLE` to match the latest RU number?"**  
No. Always use a value supported by the specific release according to Oracle documentation, and change it only with clear justification.

**"Are all new features locked out if `COMPATIBLE` is kept lower?"**  
No. The parameter primarily gates features requiring incompatible on-disk formats/structures; check each feature's specific prerequisites.

### State-Reading Exercises

1. A database reports `VERSION=19.0.0.0.0`, `VERSION_FULL=19.31.0.0.0`, `COMPATIBLE=19.0.0`. What are its release, RU, and current compatibility level?
2. After installing RU 19.32, an administrator proposes raising `COMPATIBLE` to `19.32.0` "to keep them in sync." Is that reasoning sound?
3. An application has been tested on Oracle AI Database 26ai, yet the business still requires a downgrade option back to the prior release for a period of time. Should `COMPATIBLE` be raised immediately?
4. A system shows a successful SQL patch registry entry, but Grid Infrastructure and RAC node inventories have not been checked yet. Can the whole cluster be declared updated?

**Answer hints:** (1) 19c, RU 19.31, compatibility 19.0.0; (2) no—the RU number does not dictate `COMPATIBLE`; (3) consider keeping the prior level until the downgrade window ends; (4) not yet—every relevant component must be verified.

## 7. Oracle Documentation for Further Reference

- [Oracle AI Database — About Oracle Database Release Numbers](https://docs.oracle.com/en/database/oracle/oracle-database/26/upgrd/oracle-database-release-numbers.html): `VERSION`/`VERSION_FULL` structure, RUs, and MRPs.
- [Oracle Database — Patch Maintenance, 19c and Later Releases](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbptc/index.html): patching methods, inventory, and maintenance workflows.
- [Oracle AI Database — What Is Oracle Database Compatibility?](https://docs.oracle.com/en/database/oracle/oracle-database/26/upgrd/what-is-oracle-database-compatibility.html): upgrade paths, default/minimum `COMPATIBLE`, and downgrade risks.
- [Oracle AI Database — COMPATIBLE Initialization Parameter](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/COMPATIBLE.html): allowed values, constraints, and dynamic update syntax in 26ai.
- [Oracle Database 19c — DBA_REGISTRY_SQLPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_REGISTRY_SQLPATCH.html): meanings of SQL patch history columns.
- [Oracle Database 19c — V$INSTANCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INSTANCE.html): `VERSION` and `VERSION_FULL`.
- [Oracle AI Database FAQ](https://www.oracle.com/database/faq/): relationship between 23ai, 26ai, and upgrade options.

In operations, always track **release**, **RU level**, **patch inventory/SQL patch state**, **`COMPATIBLE` value**, and **recovery path** separately. Together, those five facts describe the complete state and maintenance options of an Oracle Database.
