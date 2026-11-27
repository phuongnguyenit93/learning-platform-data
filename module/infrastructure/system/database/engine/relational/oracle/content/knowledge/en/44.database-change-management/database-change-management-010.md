# Release Updates, OPatch, datapatch, and Post-Patch Verification

Patching Oracle Database consists of two parts that must be managed as one unified process: updating software inside the Oracle Home and updating SQL objects inside the database. **OPatch** applies or rolls back patches at the Oracle Home layer; **datapatch** synchronizes the SQL changes required by a patch into the database. These two steps serve different purposes, and a successful OPatch run does not prove the database is completely patched.

A safe patching workflow requires selecting the right patch for the version/platform, reading the accompanying README, inspecting inventory and conflicts, preparing backups/rollback, applying the binary patch, running datapatch when the database is in the proper state, and verifying both inventory and the SQL patch registry. With RAC, Data Guard, and CDB/PDB, you must also account for each node's state, database role, and individual pluggable databases.

## 1. Release Updates and Oracle Patch Types

Oracle distributes several types of patches. Naming and release schedules vary across releases, though the categories below are common in database operations.

### 1.1. Release Update (RU)

A Release Update is a cumulative update bundle for an Oracle Database release line. RUs are released periodically, bundling selected bug fixes and security updates for that release.

An RU typically includes Oracle Home binary changes and may include SQL changes that must be applied to the database via datapatch. Newer RUs generally accumulate content from prior RUs within the same release line, though exact contents and applicability must be confirmed in the specific patch README.

RUs are the standard update unit for many modern Oracle Database environments. When planning, select the supported RU for the exact release, platform, architecture, and Oracle Home.

### 1.2. Release Update Revision (RUR) and Historical Terminology

Some releases previously used Release Update Revisions (RUR) or other update tracks. Policies and naming depend on the release line and release era. Never assume every current version follows the exact same RU/RUR model.

Consult Oracle documentation for the exact release you run. Do not choose a patch solely by similar naming or based on a guide written for a different release.

### 1.3. Security Patches and Critical Patch Updates

Oracle publishes scheduled security updates and delivers security content via RUs or corresponding patch bundles. Critical Patch Update (CPU) is the term used in Oracle's security update schedule; in many modern releases, customers apply security content through the appropriate RU.

Read advisories and patch READMEs to see which patches address specific vulnerabilities, which releases are affected, applicability conditions, and whether Java VM components or related middleware also need updating.

### 1.4. One-Off / Interim Patches

A one-off or interim patch addresses a specific bug or special requirement. It may depend on a particular base RU, platform, component, and previously installed patches.

Never install a one-off onto an Oracle Home running a different RU than the patch specifies. If a patch conflicts with an existing RU or one-off, request a merge patch or alternative guidance from Oracle Support. Never delete existing patches from inventory to force a new patch in.

### 1.5. Patches for OJVM, Grid Infrastructure, and Other Components

OJVM patches, Grid Infrastructure patches, client patches, and database RUs may carry distinct requirements. One Oracle Home can house multiple components and patch bundles. Procedures for a Database Home do not necessarily match Grid Infrastructure Homes.

In RAC or clustered environments, patches may require OPatchAuto or a specific node-patching order. Never guess and swap `opatch` for `opatchauto` or vice versa; follow the patch README and component-specific guides.

### 1.6. Quick Comparison

| Type | Purpose | Key Checks |
|---|---|---|
| Release Update | Cumulative update for a release line | Release/platform, RU level, prerequisites, SQL actions |
| Security update / CPU content | Remediate security vulnerabilities | Advisory, severity/impact, recommended RU or patch |
| One-off / interim | Fix a specific bug | Bug number, conflicts, merge patches, and RU prerequisites |
| OJVM patch | Patch Oracle Java VM component | OJVM component, sequencing, and dedicated requirements |
| Grid Infrastructure patch | Patch clusterware/ASM/GI | OPatchAuto, rolling capability, node ordering |
| Client patch | Patch Oracle client home | Target Home, apps using client, and driver compatibility |

## 2. Distinguishing OPatch and datapatch

The two tools operate at different layers:

- **OPatch** manages patches in Oracle Home: replacing/updating binaries, libraries, configuration files, or software components per patch contents.
- **datapatch** executes SQL patch actions included with patches to update the database dictionary, packages, component metadata, and related SQL objects.

High-level model:

    Patch archive / patch directory
                |
                v
       Read patch README
                |
                v
        OPatch apply
                |
                v
       Oracle Home binaries
                |
                v
       Start / open database
                |
                v
          datapatch
                |
                v
       SQL changes in database
                |
                v
       Post-patch verification

OPatch records patches in the Oracle Home inventory. datapatch records SQL patch actions in the database registry. Both sources of truth must be reconciled.

### 2.1. Why OPatch Succeeding Is Not Enough

An RU can include both binary fixes and SQL changes. Running only OPatch without running datapatch when required leaves the Oracle Home on the new RU while the database dictionary remains unpatched.

Consequences may include:

- The SQL patch registry lacks the new patch.
- Database components or packages remain outdated.
- Version mismatch warnings on startup or when running admin tools.
- Bugs surfacing only when exercising features tied to the patch's SQL actions.

Conversely, running datapatch when the Oracle Home lacks the corresponding binary patch does not produce a complete patch either. datapatch must run from the patched Oracle Home targeting the right database/Oracle Home to synchronize.

### 2.2. Inventory and SQL Registry Are Two Separate Sources

| Verification Point | Tool / View | Shows |
|---|---|---|
| Oracle Home inventory | `opatch lsinventory` | Binary patches recorded in the Home |
| SQL patch registry | `DBA_REGISTRY_SQLPATCH` | SQL patch actions applied/rolled back in the database |
| Component registry | `DBA_REGISTRY` | Status and versions of database components |
| Database version banner | `V$VERSION` | Running Oracle Database version |
| CDB/PDB state | `V$PDBS`, `CDB_*` views | Status and details per container |

Never substitute one source for the other. Post-patch checks must confirm both that Oracle Home inventory matches and that the SQL patch registry in the right containers shows success.

## 3. Pre-Patch Preparation

Production patching heavily affects database availability and compatibility. Before running commands, prepare a reviewed change plan and a suitable maintenance window.

### 3.1. Identify the Exact Oracle Home and Database

Record:

- Current Oracle Database release and RU.
- Platform, architecture, and edition.
- Oracle Home path of the instance to patch.
- SID, database name, DBID, and `DB_UNIQUE_NAME`.
- CDB/PDB vs. non-CDB.
- RAC vs. single instance.
- Data Guard primary/standby roles if present.
- Grid Infrastructure Home and other Oracle Homes on the host.
- Whether OJVM or specialized components are installed.

Do not rely solely on shell `ORACLE_HOME` variables on hosts with multiple Oracle Homes. Inspect the environment and running processes to verify the exact Home. A classic mistake is running OPatch against a client or Grid Infrastructure Home instead of the Database Home.

Verify from SQL:

    SELECT
        name,
        dbid,
        db_unique_name,
        open_mode,
        database_role,
        cdb
    FROM v$database;

Check instance:

    SELECT
        instance_name,
        host_name,
        version,
        status
    FROM v$instance;

### 3.2. Read the Patch README

The patch README is the primary instruction source for that patch. Read every section:

- Supported products/releases/platforms.
- Prerequisites and required OPatch version.
- Conflicting patches and superseded patches.
- Required component or one-off patches.
- Apply/rollback procedures.
- Shutdown/startup requirements.
- Rolling vs. non-rolling instructions.
- Datapatch instructions.
- Post-installation steps.
- Known issues and special notes.

Never reuse commands from an older patch README for a newer patch just because the tool names match. Syntax, sequencing, and prerequisites can change.

### 3.3. Verify Patch Download and Checksum

Download patches from authorized Oracle channels, verifying patch number, platform, and checksum per Oracle instructions. Never use patch files from untrusted sources.

Preserve the extracted patch directory structure. Do not rename or move internal files when the README expects a specific layout.

### 3.4. Backups and Rollback Readiness

Before patching:

- Confirm the latest RMAN backup completed and is accessible.
- Verify control file, SPFILE, and archived redo log backups per policy.
- Confirm an Oracle Home copy or snapshot exists per organizational support procedures.
- Save pre-patch `opatch lsinventory` output.
- Back up listener, `tnsnames`, `sqlnet`, password files, and critical configuration files.
- Record states of database, PDBs, services, ASM, cluster, and Data Guard.
- Define how to roll back binary patches and handle SQL patches.
- Define go/no-go criteria and responsible owners.

Patch rollback is not equivalent to an RMAN database restore. OPatch rollback reverts the Oracle Home via patch mechanisms; datapatch aligns the SQL registry with binary state; RMAN restore/recovery is a database-level recovery path with broader impact.

### 3.5. Check Space and Permissions

Verify free space on filesystems holding Oracle Home, patch staging directory, temp directory, logs, and FRA if database steps apply. Confirm the patching user has read/write permissions on relevant directories and required operational privileges.

Do not extract patches inside an active Oracle Home if the README specifies staging elsewhere. Prevent patch archives, logs, and backups from exhausting filesystem space during maintenance.

## 4. Inspecting Oracle Home Inventory with OPatch

OPatch is a utility bundled with Oracle Home, typically located at:

    $ORACLE_HOME/OPatch/opatch

On Windows, the executable is typically `opatch.bat` inside the `OPatch` directory. Exact paths and filenames depend on platform.

### 4.1. Check OPatch Version

    $ORACLE_HOME/OPatch/opatch version

Compare against the minimum OPatch version required by the patch README. If OPatch must be upgraded, obtain the matching OPatch package from Oracle Support, back up the current `OPatch` directory per procedure, and update the target Oracle Home.

Never assume the absolute latest OPatch always supports every release/platform. Use the Oracle-supported version for your specific patch and Oracle Home.

### 4.2. List Inventory

    $ORACLE_HOME/OPatch/opatch lsinventory

For more detail:

    $ORACLE_HOME/OPatch/opatch lsinventory -detail

This prints Oracle Home details and inventory-recorded patches. Save pre-patch output as a baseline to compare post-patch.

If inventory reports errors, do not proceed with applying patches. First resolve inventory pointers, permissions, Oracle Home paths, and `oraInventory` consistency per Oracle guidance.

### 4.3. Inventory Is Not the Database SQL Patch List

`lsinventory` reads Oracle Home inventory. It does not prove every PDB has run datapatch. Query `DBA_REGISTRY_SQLPATCH` after running datapatch.

### 4.4. Querying Inventory via SQL When Needed

Some releases support the `DBMS_QOPATCH` package/view to query inventory from inside the database. Privileges and usage vary by release. It is a supplementary tool and does not replace running OPatch on Oracle Home when verifying binary patches.

## 5. Checking Prerequisites and Conflicts

Before applying, confirm the patch fits the Oracle Home and has no unresolved conflicts.

### 5.1. Check Prerequisites

A patch README may require:

- A specific base RU or patch level.
- A minimum OPatch version.
- Oracle Home in a specific state.
- Particular components or options installed.
- Rolling back older patches first.
- Replacing specific one-offs with a merge patch.
- Dedicated preparation steps for RAC/Data Guard/OJVM.

Never skip prerequisites simply because `apply` appears to start.

### 5.2. Check Conflicts with OPatch

OPatch provides a prerequisite check for conflicts between a new patch and current inventory. Example syntax common across many releases:

    $ORACLE_HOME/OPatch/opatch prereq CheckConflictAgainstOHWithDetail \
      -phBaseDir /stage/patch_directory

The patch directory path must point to the directory containing valid patch metadata. Verify exact syntax and prerequisites against the README and OPatch version.

If conflicts appear:

1. Identify the conflicting patch IDs.
2. Check which patches are superseded or whether a merge patch exists.
3. Consult the README and Oracle Support notes for that conflict.
4. Determine whether an old one-off can be rolled back or requires a replacement patch.
5. Test on a cloned Oracle Home or staging environment.
6. Apply only after resolving conflicts per official guidance.

Never delete inventory records, hand-edit XML inventory files, or remove patch files to bypass conflicts.

### 5.3. Check Already-Installed Patches

If a patch already appears in inventory, verify it is the exact patch ID, version, and Oracle Home. Avoid re-running `apply` without understanding state. If a prior apply stopped partway, read OPatch logs and follow Oracle recovery instructions.

## 6. Applying Patches with OPatch

Application procedures depend on patch type. The example below illustrates a patch applied manually via OPatch per README; do not copy it verbatim if the patch requires OPatchAuto or another rolling method.

### 6.1. Stop Required Components

For in-place patching, the README may require shutting down database instances, listeners, application connections, or processes holding Oracle Home open. In RAC, node and instance shutdown order depends on rolling capability and patch instructions.

Verify no process still locks binaries slated for replacement. Never kill processes blindly by name without verifying owner and impact.

### 6.2. Run OPatch apply

Example:

    cd /stage/patch_directory
    $ORACLE_HOME/OPatch/opatch apply

OPatch verifies inventory and prerequisites, then updates files in Oracle Home. Review stdout and logs to confirm completion status.

Never treat a shell exit code of `0` as sufficient if output contains warnings or mandates post-installation steps. Archive logs and patch IDs.

### 6.3. Silent Mode

Automated workflows may use silent mode if supported by the README:

    $ORACLE_HOME/OPatch/opatch apply -silent

Silent mode does not bypass prerequisites or replace review. Automation must inspect exit codes, logs, and post-run inventory state.

### 6.4. Post-OPatch Verification

After applying:

    $ORACLE_HOME/OPatch/opatch lsinventory

Confirm the patch ID and version appear in the right Oracle Home. Inspect OPatch logs to verify zero failed steps or partial rollbacks.

When multiple Oracle Homes exist, run `lsinventory` on every Home per plan. Never assume patching a Database Home patched Grid Infrastructure Home or client homes.

## 7. datapatch: Updating SQL Inside the Database

`datapatch` executes SQL patch actions to synchronize the database with patches installed in Oracle Home. It typically resides in Oracle Home under `OPatch/datapatch` per release layout.

Example:

    $ORACLE_HOME/OPatch/datapatch -verbose

Run it from the patched Oracle Home environment connected to the target database. Connection privileges and database state must satisfy the patch README.

### 7.1. Preconditions Before Running

Before running datapatch:

- Binary patches succeeded in Oracle Home.
- The database is started from the patched Oracle Home.
- The database is open in the mode required by datapatch/README.
- CDB root and target PDBs are open appropriately, typically `READ WRITE`.
- Listeners/services and local connectivity work.
- No conflicting DDL or other patch runs are active.
- Sufficient space exists in the data dictionary, system tablespaces, and logs.

In a CDB, datapatch applies SQL patches to root and open eligible PDBs. Closed or unavailable PDBs may remain unpatched in that run; open those PDBs and re-run datapatch per release instructions to finish.

Never assume running once against CDB root automatically patched every PDB. Check the registry in each container.

### 7.2. Running datapatch

Example:

    $ORACLE_HOME/OPatch/datapatch -verbose

`-verbose` prints detailed progress. Save stdout and the log file path printed by datapatch. If it fails, inspect the log to pinpoint the failing PDB, SQL action, or component.

Never run datapatch from an old Oracle Home or a Home different from the patched instance. Verify `ORACLE_HOME`, `PATH`, `ORACLE_SID`, and connections before running.

### 7.3. Can datapatch Be Re-Run?

If a previous run was interrupted or a PDB was closed, you can re-run datapatch after fixing the root cause. The tool reads the SQL patch registry state and executes required actions against current inventory/state; re-running per Oracle guidance is the standard way to complete patching.

Never delete registry rows or edit internal tables to trick datapatch into thinking a patch never ran. If the registry shows errors, inspect logs and follow guidance for that exact patch/release.

### 7.4. datapatch Does Not Replace OPatch

datapatch does not install binary patches. If Oracle Home is unpatched, datapatch cannot substitute for OPatch. Likewise, OPatch does not execute all SQL actions needed by the database dictionary.

## 8. CDB/PDB: Checking and Patching All Required Containers

In multitenant architectures, root and each PDB maintain container-scoped registries. A patch may require SQL actions in CDB root, seed, and one or more PDBs.

### 8.1. List PDBs and Status

    SELECT
        con_id,
        name,
        open_mode,
        restricted
    FROM v$pdbs
    ORDER BY con_id;

Note which PDBs need patching and which are closed for maintenance or operational policy.

### 8.2. Open Target PDBs

Example:

    ALTER PLUGGABLE DATABASE ALL OPEN;

This opens all PDBs permitted by account privileges and environment. In production, do not blindly run `ALL` if certain PDBs must remain closed; open specific PDBs per change plan.

A PDB must be in the proper state for datapatch to apply SQL changes. If a PDB was closed during the first pass, open it and re-run datapatch per Oracle documentation.

### 8.3. Check the SQL Patch Registry in Every Container

Switch containers and query:

    ALTER SESSION SET CONTAINER = CDB$ROOT;

    SELECT
        patch_id,
        patch_uid,
        action,
        status,
        action_time,
        description,
        logfile
    FROM dba_registry_sqlpatch
    ORDER BY action_time DESC;

Then check each PDB:

    ALTER SESSION SET CONTAINER = APP_PDB;

    SELECT
        patch_id,
        patch_uid,
        action,
        status,
        action_time,
        description,
        logfile
    FROM dba_registry_sqlpatch
    ORDER BY action_time DESC;

`APP_PDB` is illustrative. Connect with a user holding dictionary read privileges in each container. You can use `CDB_*` views if supported by your release and the user has appropriate container data privileges.

### 8.4. Newly Created or Cloned PDBs After Patching

PDBs created, cloned, or plugged in after Oracle Home already received an RU must have their registry and SQL patch status verified per Oracle guidelines. Never assume a new PDB automatically has all SQL patches just because Oracle Home is patched.

In automated PDB provisioning pipelines, include datapatch/registry checks in provisioning and validation steps.

## 9. RAC and Data Guard

RAC and Data Guard alter how patching is organized. A workflow valid on single instance may be insufficient for a cluster or standby topology.

### 9.1. Oracle RAC

In RAC, each node has its own Oracle Home or a shared Home layout depending on architecture. Patches must be applied in a supported sequence.

Some patches support rolling patching, updating one node at a time while services keep running on remaining nodes. Others require non-rolling patching and full cluster downtime. Never infer rolling capability merely because a patch is an RU; inspect the README and RAC patching docs.

Determine:

- Whether the patch supports rolling mode.
- Whether OPatch or OPatchAuto is required.
- Node and instance order.
- Service relocation and session draining.
- ASM/Grid Infrastructure dependencies.
- When and on which node datapatch runs per instructions.
- Inventory verification across every node/Home.
- SQL registry checks after database services come online.

For Grid Infrastructure, OPatchAuto is commonly used per GI patching workflows. For Database Homes, tools and sequences may differ. Follow the exact commands and README for each component.

### 9.2. Data Guard

Data Guard environments may support standby-first patching for verified compatible patches. The general idea is updating standby software first, testing, performing a controlled switchover, and then updating the remaining database. However, applicability depends on the patch, release, Data Guard setup, and Oracle documentation.

Never manually run SQL patches/datapatch against a mounted standby unless explicitly instructed by a patch procedure. Datapatch normally requires an appropriately open database to run SQL actions. Primary/standby sequencing must follow patch-specific instructions.

Before and after patching, check:

- Transport lag and apply lag.
- Redo transport/apply status.
- Database role and open mode.
- Broker configuration if using Data Guard Broker.
- Services and client connect descriptors.
- Switchover/failback procedures.
- SQL patch registry on each database after patching finishes.

Never treat normal redo apply on a standby as proof that the standby's Oracle Home holds the right binary patches.

## 10. Checking the SQL Patch Registry

The primary view is `DBA_REGISTRY_SQLPATCH`, recording SQL patch actions executed by datapatch.

### 10.1. Query Patch History

    SELECT
        patch_id,
        patch_uid,
        action,
        status,
        action_time,
        description,
        source_version,
        target_version,
        logfile
    FROM dba_registry_sqlpatch
    ORDER BY action_time DESC;

Common columns:

- `PATCH_ID`/`PATCH_UID`: patch identifiers.
- `ACTION`: `APPLY` or `ROLLBACK`.
- `STATUS`: `SUCCESS` or `WITH ERRORS`.
- `ACTION_TIME`: timestamp when the action ran.
- `DESCRIPTION`: patch description.
- `SOURCE_VERSION`/`TARGET_VERSION`: versions involved in the action.
- `LOGFILE`: path to datapatch log.

Column names/availability can differ across releases; inspect the data dictionary on your running version.

### 10.2. Check Latest Status of a Specific Patch

Example filtering for a specific patch ID:

    SELECT
        patch_id,
        action,
        status,
        action_time,
        description,
        logfile
    FROM dba_registry_sqlpatch
    WHERE patch_id = 12345678
    ORDER BY action_time DESC;

Replace `12345678` with the actual patch ID. When multiple `APPLY`/`ROLLBACK` actions exist, read history chronologically to identify the latest action. Never conclude a patch is active solely because a row with `patch_id` appears.

### 10.3. Investigate WITH ERRORS

If `STATUS` is `WITH ERRORS`, SQL patch actions did not complete cleanly. Open the datapatch log referenced in `LOGFILE` and identify the failing SQL statement, component, or PDB.

Failures can stem from invalid components, object dependencies, tablespace space, privileges, or a PDB not in the right mode. Fix the cause per logs and Oracle documentation, then re-run datapatch when ready. Never edit the registry directly to flip `WITH ERRORS` to `SUCCESS`.

### 10.4. Check Component Registry

    SELECT
        comp_id,
        comp_name,
        version,
        status
    FROM dba_registry
    ORDER BY comp_id;

Verify relevant components have valid status and expected versions. An `INVALID` or `LOADING` component may need dedicated pre/post-patch steps per README.

### 10.5. Check Registry Across PDBs

In a CDB, query `DBA_REGISTRY_SQLPATCH` inside each container to confirm SQL patches. You can query `CDB_REGISTRY_SQLPATCH` if supported by your release and privileges allow, for example:

    SELECT
        con_id,
        patch_id,
        action,
        status,
        action_time,
        description
    FROM cdb_registry_sqlpatch
    ORDER BY con_id, action_time DESC;

If the view does not exist or privileges are missing, switch containers and query `DBA_REGISTRY_SQLPATCH`. Reconcile results against the list of PDBs within patch scope.

## 11. Post-Patch Verification at the Oracle Home Layer

After OPatch finishes, verify binary inventory and versions.

### 11.1. Re-Run lsinventory

    $ORACLE_HOME/OPatch/opatch lsinventory -detail

Compare against pre-patch output:

- Patch ID is right.
- RU level is right.
- Oracle Home is right.
- No partial applies or inventory errors exist.
- Required one-off patches remain present or were replaced by planned merge patches.
- All RAC nodes/Homes show consistent state.

Archive post-patch output alongside the change record.

### 11.2. Check Binary Version from the Database

    SELECT banner_full
    FROM v$version;

`BANNER_FULL` is present in supported releases; otherwise use version columns/views appropriate for your release. `V$VERSION` displays the database software banner, but does not replace `lsinventory` for verifying patch IDs.

### 11.3. Inspect Alert Log and Startup

After starting the database from the patched Oracle Home, check the alert log for:

- Shared library or binary load errors.
- Startup/mount/open errors.
- Unloaded components.
- Patch/SQL registry warnings.
- Dictionary or background process errors.
- PDB open errors.

Never ignore warnings just because the database opened. Cross-check against known issues and the patch README.

## 12. Post-Patch Verification at the Database Layer

After datapatch, confirm the database operates normally and the SQL patch registry is accurate.

### 12.1. Check Database and Instance

    SELECT name, open_mode, database_role, cdb
    FROM v$database;

    SELECT instance_name, status, version
    FROM v$instance;

Confirm expected database name, role, `OPEN` mode, and version. In RAC, inspect every instance and service.

### 12.2. Check PDBs

    SELECT name, open_mode, restricted
    FROM v$pdbs
    ORDER BY name;

Verify required PDBs opened in the right mode without unexpected restricted mode. Check the SQL registry inside each PDB.

### 12.3. Check Invalid Objects

    SELECT
        owner,
        object_type,
        COUNT(*) AS invalid_count
    FROM dba_objects
    WHERE status = 'INVALID'
    GROUP BY owner, object_type
    ORDER BY owner, object_type;

Compare against the pre-patch baseline. Some invalid objects may have pre-existed or require recompilation per release procedures; do not automatically blame every `INVALID` object on the patch.

If invalid objects must be recompiled, follow Oracle-prescribed procedures such as `utlrp.sql` when instructed by the README/Oracle docs. Avoid running compile scripts out of habit while the database is in an unsuitable state or pending post-patch steps.

### 12.4. Check Component Status

    SELECT comp_id, comp_name, version, status
    FROM dba_registry
    ORDER BY comp_id;

Component statuses should match the baseline and patch documentation. If a component is `INVALID` or `LOADING`, inspect logs and relevant post-patch steps.

### 12.5. Application Smoke Tests

Once the database is open:

- Applications connect cleanly with service accounts.
- Critical read queries succeed.
- Stored procedures/packages execute cleanly.
- Transaction commits/rollbacks work.
- Key jobs/schedulers run.
- Connection pools establish and reuse connections normally.
- Critical batches, reporting, replication, and integrations operate normally.
- Latency, CPU, I/O, and wait events show no abnormal regressions.

Smoke tests should exercise representative business queries and flows, not just `SELECT 1 FROM dual`.

## 13. Sample Patching Workflow for a Single-Instance Database

The example below outlines a general sequence for an RU applied with OPatch and requiring datapatch. The patch README always takes precedence if its sequence differs.

### Phase A: Discovery

1. Record Oracle release, platform, Oracle Home, SID, and database role.
2. Save `opatch version` and `opatch lsinventory`.
3. Identify current RU and one-off patches.
4. Read the README and verify prerequisites.
5. Check conflicts.
6. Confirm backups, rollback plan, and maintenance window.
7. Prepare patch staging and verify disk space.

### Phase B: Apply Binary Patch

1. Shut down database/listener/processes per README.
2. Set `ORACLE_HOME` and `PATH` accurately.
3. Change into the patch directory.
4. Run OPatch apply.
5. Inspect output and logs.
6. Run `lsinventory` to verify the binary patch.

Example:

    export ORACLE_HOME=/u01/app/oracle/product/db_home
    export PATH=$ORACLE_HOME/OPatch:$ORACLE_HOME/bin:$PATH

    cd /stage/patch_directory
    opatch apply

This uses Unix/Linux shell syntax. On Windows, use the equivalent environment variables and executables.

### Phase C: Startup and datapatch

1. Start the database from the patched Oracle Home.
2. Open the database per patch instructions.
3. For CDBs, open all in-scope PDBs.
4. Run datapatch from the exact patched Oracle Home.
5. Inspect logs and confirm zero SQL actions `WITH ERRORS`.

Example:

    $ORACLE_HOME/OPatch/datapatch -verbose

### Phase D: Verification

1. Run `lsinventory`.
2. Query `DBA_REGISTRY_SQLPATCH`.
3. Verify CDB/PDB registries.
4. Check `DBA_REGISTRY` and invalid objects.
5. Review alert log and datapatch log.
6. Run application smoke tests.
7. Archive evidence and close the change record.

## 14. Rolling Back Patches

Rollback must be planned before applying. Not every patch rolls back identically; some patches impose special steps or restrictions.

### 14.1. Binary Rollback with OPatch

For patches supporting rollback, for example:

    cd /stage/patch_directory
    $ORACLE_HOME/OPatch/opatch rollback -id 12345678

Substitute the patch ID and directory per the README. Some patches require running rollback from the patch directory or in a specific order. Never roll back an RU or one-off without checking dependencies against other installed patches.

After rollback, run `lsinventory` to confirm the patch is removed from Oracle Home.

### 14.2. SQL Synchronization After Rollback

If datapatch was run for the patch, follow README instructions for corresponding SQL rollback steps after binary rollback. In supported workflows, running datapatch from the rolled-back Oracle Home executes SQL rollback actions based on current inventory and registry state.

General example:

    $ORACLE_HOME/OPatch/datapatch -verbose

Never assume every patch has a SQL rollback action or that all rollbacks behave identically. Read logs and the README to confirm `ROLLBACK` actions succeeded. Never delete registry rows manually.

### 14.3. Rollback Is Not Database Restore

OPatch rollback modifies the Oracle Home. It does not restore application data changed after patching, nor does it rewind the database to a pre-patch SCN.

RMAN restore/recovery or Flashback Database are separate procedures that can discard changes after the recovery point. Use them only after evaluating RPO/RTO and obtaining explicit approval.

### 14.4. Out-of-Place Patching

Some environments create a new Oracle Home, patch the new Home, test it, and switch databases/services to that Home. This out-of-place patching keeps the old Home available as a software-level fallback if architecture and procedures support it.

However, the database dictionary may already have been updated by datapatch when run from the new Home. Switching back to the old Home does not automatically roll back SQL changes; ensure compatibility and follow Oracle rollback guidance. Never treat keeping the old Home as a complete rollback plan on its own.

## 15. Common Errors

### 15.1. Insufficient OPatch Version

Prerequisite or OPatch version errors indicate OPatch is outdated. Upgrade OPatch per README matching platform/release/Home, then re-verify `opatch version` and inventory before re-applying.

### 15.2. Patch Conflicts

The new patch conflicts with an existing one-off or installed patch. Identify conflicting patch IDs, inspect conflict details, and obtain a merge patch or guidance from Oracle Support. Never hand-edit inventory.

### 15.3. Insufficient Staging or Oracle Home Space

Free or allocate space per procedure while keeping logs and patch archives safe. Never delete arbitrary files inside Oracle Home to free space.

### 15.4. OPatch Apply Succeeds, datapatch Fails

Check database open mode, PDB states, `ORACLE_HOME`, service connections, privileges, component statuses, and the datapatch log. Fix the root cause and re-run datapatch per guidance. Do not immediately roll back binaries before diagnosing the SQL error and remediation path.

### 15.5. Missed PDBs

PDBs closed during datapatch will not receive SQL patches. Open the relevant PDBs and re-run datapatch, then inspect the registry inside those PDBs. Never check only CDB root.

### 15.6. SQL Patch Registry Shows WITH ERRORS

Open the log file listed in `LOGFILE` and the datapatch logs. Pinpoint the failing SQL statement, component, container, and prerequisites. Follow patch docs or Oracle Support guidance to fix. Never update registry tables directly.

### 15.7. Divergent Binary Inventory Across RAC Nodes

Check each Oracle Home/node, patch ID, and patch level. An unpatched node can cause errors when services run on or fail over to it. Complete the cluster sequence before returning all services to normal operation.

### 15.8. Database Opens, Yet Applications Fail

Causes include invalid objects, missing privileges, SQL plan shifts, driver/client compatibility, behavior changes, or application bugs. Inspect alert logs, application logs, SQL patch registry, component status, and smoke tests. Never declare patching successful merely because the database is `OPEN`.

## 16. Patch Planning for RAC and Data Guard

In HA architectures, change plans must spell out sequencing and continuation criteria.

### 16.1. RAC Runbook

A RAC runbook should state:

- Whether the patch is rolling or non-rolling.
- Whether OPatch or OPatchAuto is required.
- Which node is patched first.
- Which services are relocated/drained.
- Criteria for rejoining a node to the cluster.
- How to verify Oracle Home inventory on every node.
- When datapatch runs per README.
- Registry, instance, and service checks after each phase.
- Rollback scenario if one node fails.

Never split an RU into rolling steps on your own if the patch does not support rolling mode. Some patches require full-cluster non-rolling patching.

### 16.2. Data Guard Runbook

A Data Guard runbook should state:

- Whether the patch supports standby-first.
- Oracle Homes and database roles at each site.
- Transport/apply lag before and after patching.
- Order for patching standby, switching over, and patching the remaining site.
- When datapatch is required.
- Broker, redo transport, and redo apply checks.
- Failback/rollback scenarios.
- Reconciling SQL registry and inventory across primary and standby.

Never initiate a switchover solely because binary patching on the standby finished. Verify database roles, redo apply, patch compatibility, and Oracle's exact procedure for that patch.

## 17. Change Records and Post-Patch Evidence

A change record should preserve evidence allowing DBAs or auditors to verify before/after states:

| Evidence | Pre-Patch | Post-Patch |
|---|---|---|
| Oracle Home path | Yes | Yes |
| `opatch version` | Yes | Yes |
| `opatch lsinventory` | Yes | Yes |
| Patch ID / RU level | Yes | Yes |
| Database version/banner | Yes | Yes |
| `DBA_REGISTRY_SQLPATCH` | Baseline | `APPLY`/`ROLLBACK` status |
| PDB open state | Yes | Yes |
| Component registry | Yes | Yes |
| Invalid objects | Baseline | Post-patch delta |
| Alert/datapatch/OPatch logs | — | Archive logs |
| Application smoke test | Baseline | Results |
| Performance baseline | Yes | Comparison |

Evidence must clearly record timestamps, database identity, Oracle Home, node, and container. Output missing Home or PDB context creates confusion when auditing multiple databases.

## 18. Pre-, During-, and Post-Patch Checklists

### Pre-Patch

- Verify release, platform, Oracle Home, and database identity.
- Select the right RU/patch and read the full README.
- Check OPatch version, inventory, and patch conflicts.
- Identify prerequisites, superseded/one-off patches, and affected components.
- Verify backups, rollback, and out-of-place options.
- Check storage, permissions, staging, and log locations.
- Verify RAC/Data Guard/CDB/PDB state and rolling capability.
- Finalize runbook, downtime window, owners, and go/no-go criteria.

### During Patch

- Stop/relocate services in the proper sequence.
- Run OPatch/OPatchAuto per README.
- Inspect stdout and logs at every step.
- Confirm binary inventory after applying.
- Start the database from the patched Home.
- Open all required containers.
- Run datapatch from the exact patched Oracle Home.
- Monitor SQL actions and logs for every PDB.

### Post-Patch

- Verify `opatch lsinventory` on every Home/node.
- Confirm `DBA_REGISTRY_SQLPATCH` shows expected actions and statuses.
- Check every PDB, not just CDB root.
- Check `DBA_REGISTRY`, invalid objects, and alert logs.
- Verify database roles, services, listeners, and cluster health.
- Run application smoke tests and verify transactions.
- Monitor error rates, latency, CPU, I/O, and wait events.
- Archive logs/baselines and update the change record.

## 19. Key Principles to Remember

- RUs are cumulative update bundles; match exact release, platform, and patch README.
- OPatch modifies Oracle Home inventory and binaries; datapatch applies SQL changes inside the database.
- OPatch succeeding does not prove datapatch completed.
- `opatch lsinventory` and `DBA_REGISTRY_SQLPATCH` are two distinct state sources that must be reconciled.
- In a CDB, verify the SQL patch registry in root and every in-scope PDB.
- PDBs closed while datapatch runs must be opened and patched subsequently per guidance.
- RAC rolling capability and Data Guard standby-first support must be verified per specific patch.
- Never alter inventory or the SQL patch registry manually with DML.
- Binary rollback and SQL rollback are two coordinated parts; database restore is a separate procedure.
- Verify alert logs, component registry, invalid objects, services, and application smoke tests post-patch.
- The patch README and release-specific Oracle documentation are the authoritative references.

Oracle patch management spans end-to-end from Oracle Home through the database dictionary and every container. Only when inventory, datapatch registry, logs, and smoke tests are all verified does operations hold complete proof that a patch is fully deployed and the database is ready to serve applications.
