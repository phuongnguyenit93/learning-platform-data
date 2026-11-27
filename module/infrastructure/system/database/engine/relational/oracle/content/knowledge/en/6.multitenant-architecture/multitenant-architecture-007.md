# Clone, Plug, Unplug, and Checking PDB Compatibility

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** CDB and PDB  
> **Objective:** Understand and practice the lifecycle of a **Pluggable Database (PDB)** in the Oracle Multitenant architecture: creating copies via **clone**, detaching a PDB via **unplug**, attaching a PDB via **plug**, checking compatibility with **DBMS_PDB**, and resolving warnings before putting the PDB into service.

## 1. Context: PDBs Can Be Cloned and Moved Between CDBs

In the Oracle Multitenant architecture, a **Container Database (CDB)** provides the shared infrastructure, while each **Pluggable Database (PDB)** holds the objects and data of logically isolated applications or user groups.

A typical CDB consists of:

```text
CDB_PROD
├── CDB$ROOT        : root container; instance management, shared metadata
├── PDB$SEED        : template for creating new PDBs
├── APP_PDB         : PDB actively running an application
└── REPORT_PDB      : PDB serving reporting
```

A PDB is not like a schema:

- **A schema** is a collection of objects belonging to a database user, such as `ORDERS`, `CUSTOMERS`, indexes, and sequences.
- **A PDB** has its own set of metadata, schemas, datafiles, and open state within the CDB scope.
- **A CDB** contains the PDBs and runs shared processes and management structures at the instance/root tier.

PDB portability is a major benefit of Multitenant: you can create test environments closely matching a source environment, move a PDB to another CDB, or re-attach a detached PDB without manually exporting every table.

However, these operations **are not equivalent** to an independent backup. Creating copies, moving, storing files, and recovering data must be clearly distinguished.

## 2. Distinguishing Clone, Unplug, and Plug

| Operation | Meaning | Source PDB After Operation | Data at Destination |
|---|---|---|---|
| **Clone** | Creates a **new PDB** from an existing PDB | Usually continues existing and can operate per clone conditions | Logical/physical copy per clone method |
| **Unplug** | Detaches a PDB from a CDB and generates a metadata description for plugging elsewhere | Enters **UNPLUGGED** state, cannot be used as an open PDB | Produces an XML manifest or PDB archive; not yet attached to target CDB |
| **Plug** | Creates a PDB in the target CDB from metadata and matching datafiles | Depends on transfer workflow; source may have been removed from old CDB | PDB is registered in target CDB; must be opened and verified |
| **Refreshable PDB clone** | Copy that can receive subsequent changes from the source via supported refresh mechanisms | Source remains active | Copy has a refresh relationship with source; differs from an independent clone |
| **Snapshot copy** | Copy utilizing storage snapshot/copy-on-write capabilities when supported | Source still exists; has specific dependencies depending on config | May save initial space, but is not identical to an independent datafile copy |

Mental diagram:

```text
                   ┌── Clone ────────────> New PDB_B
PDB_A in CDB_1 ────┤                         (source PDB_A remains)
                   │
                   └── Unplug ───> Manifest + datafiles
                                     │
                                     │ Plug
                                     v
                                  CDB_2
                                   └── PDB_A or a new name
```

**Choosing by objective:**

- Need a parallel lab/test environment: typically use **clone**.
- Need to move a PDB to another CDB: use **unplug → transfer metadata and datafiles → check compatibility → plug**.
- Need a read environment for reporting or DR updatable from source: look into **refreshable PDB** and version requirements.
- Need recovery from corruption or data loss: rely on **RMAN backup/recovery** and formal recovery strategy; cloning or unplugging does not replace backups.

## 3. Preparing the Oracle Multitenant Environment

The examples use hypothetical names:

| Parameter | Illustrative Value | Meaning |
|---|---|---|
| Source CDB | `CDB1` | Container Database currently holding the PDB |
| Source PDB | `LAB_SRC` | PDB to clone or move |
| Cloned PDB | `LAB_CLONE` | New PDB for testing |
| Target CDB | `CDB2` | Container Database that will receive the PDB |
| PDB after plug | `LAB_MOVED` | PDB name used in the target CDB |
| Unplug metadata | `/u03/pdbstage/lab_src.xml` | XML file written by Oracle on the **database server** filesystem |
| Source data area | `/u02/oradata/CDB1/lab_src/` | Example path holding datafiles of the source PDB |
| Target data area | `/u02/oradata/CDB2/lab_moved/` | Example path for datafiles of the target PDB |

These are sample names only. On Windows or systems using **ASM/OMF (Oracle Managed Files)**, paths can look very different, such as locations starting with `+DATA`. Always use actual paths provided by your DBA or system.

### 3.1. Required Tools and Privileges

To run PDB modification commands, you need an account with appropriate CDB administrative privileges, typically executed under `SYSDBA` in **`CDB$ROOT`**, or an administrative account granted `CREATE PLUGGABLE DATABASE` and related privileges. A PDB local user cannot move arbitrary PDBs across the CDB.

Illustrative commands for a lab environment on a Linux server:

```bash
sqlplus / as sysdba
```

Once inside SQL*Plus:

```sql
SHOW CON_NAME;
SHOW PDBS;
```

`SHOW CON_NAME` must return `CDB$ROOT` before CDB-level operations. If currently in another PDB, with appropriate privileges:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
```

Do not confuse `CDB$ROOT` with a PDB's service name. Normal application sessions should connect directly to the PDB service, whereas the administrative steps below execute in the root.

### 3.2. Checking CDB, PDBs, and Open Modes

```sql
SELECT name, open_mode, cdb
FROM v$database;

SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
```

Important states:

- **MOUNTED:** the PDB is recognized but not yet open for normal user queries.
- **READ ONLY:** the PDB is open for reading, disallowing data modifications as in read-write mode.
- **READ WRITE:** the PDB is open for read and write activity.
- **UNPLUGGED:** the PDB has been detached; cannot be used as an open PDB in the old CDB.
- **RESTRICTED:** a restricted-connection state that may appear when compatibility issues or maintenance require handling.

A PDB can have additional open options and states depending on Oracle version. Always observe actual values rather than assuming every newly created PDB is ready.

### 3.3. Checking File Paths and Resources

Inspect current datafiles (requires privileges to access dynamic performance views):

```sql
SELECT con_id, file#, name
FROM v$datafile
ORDER BY con_id, file#;
```

Paths in `FILE_NAME_CONVERT` syntax must match actual datafiles, avoiding overwriting the source directory.

Check other prerequisites before practicing:

1. Whether the target CDB has **enough space for datafiles and tempfiles** and allows adding a PDB.
2. Whether Oracle version/patch/options between source and target CDBs are compatible.
3. Whether automatic file-naming policy **OMF** is configured or `FILE_NAME_CONVERT` must be specified.
4. Whether **TDE encryption** or wallets/keystores are used.
5. Whether an independent copy is needed and rollback via backup is guaranteed.
6. Whether users/applications are connected to the source PDB and maintenance or downtime notification is required.

> **All `CLOSE`, `UNPLUG`, `DROP`, and `MOVE` commands in this lesson must only be executed against a lab PDB or following an approved change process.** These are structural database changes that can disconnect applications and affect physical data.

## 4. Cloning a PDB Within the Same CDB

### 4.1. How Does Cloning Work?

**Local PDB cloning** creates a new PDB from a source PDB in the same CDB. Oracle copies the required metadata and data from the source to create the target PDB; the normal result is an independent PDB that can operate separately from the source PDB.

Example:

```text
CDB1
├── CDB$ROOT
├── PDB$SEED
├── LAB_SRC    ─── clone ──┐
└── LAB_CLONE <────────────┘
```

The source keeps its name and data. The clone gets its **own PDB identity**, with data starting from the same state as the clone point in time, while subsequent changes on the clone do not propagate back to the source.

### 4.2. Choosing Cold Clone for Simplicity

With a standard workflow broadly supported across Oracle Multitenant releases, prepare the source PDB in **READ ONLY** mode before cloning. In the CDB root:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE lab_src OPEN READ ONLY;
```

Verify:

```sql
SELECT name, open_mode
FROM v$pdbs
WHERE name = 'LAB_SRC';
```

Expect `OPEN_MODE = READ ONLY`.

**Impact:** Sessions using `LAB_SRC` can be terminated when closing the PDB, and applications cannot write data while the PDB is `READ ONLY`. This operation is only appropriate during a maintenance window or in a lab environment.

### 4.3. Creating a Clone Using FILE_NAME_CONVERT

If the CDB **does not yet** have suitable OMF configured, specify how to rename/map file paths for the new PDB:

```sql
CREATE PLUGGABLE DATABASE lab_clone
FROM lab_src
FILE_NAME_CONVERT = (
    '/u02/oradata/CDB1/lab_src/',
    '/u02/oradata/CDB1/lab_clone/'
);
```

Meaning:

- `LAB_CLONE`: name of the new PDB.
- `FROM LAB_SRC`: clone from the source PDB.
- `FILE_NAME_CONVERT`: maps old paths to new file paths, avoiding reusing the source PDB's files.

**Note:** Paths are examples only. Do not run verbatim if your machine uses different paths. If datafiles are not in the same directory, multiple mapping pairs or OMF may be needed depending on the environment.

On systems configured with **Oracle Managed Files**, it may be as simple as:

```sql
CREATE PLUGGABLE DATABASE lab_clone FROM lab_src;
```

Oracle automatically manages filenames inside the configured OMF destination. The two PDB creation templates above are **alternatives**; do not run both to create the same `LAB_CLONE`.

### 4.4. Opening the New PDB and Returning Source to READ WRITE

```sql
ALTER PLUGGABLE DATABASE lab_clone OPEN READ WRITE;

ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE lab_src OPEN READ WRITE;

SELECT name, open_mode
FROM v$pdbs
WHERE name IN ('LAB_SRC', 'LAB_CLONE')
ORDER BY name;
```

After creation, the new PDB may require additional administrative steps depending on version and plug-in status. In a normal lab environment, `OPEN READ WRITE` is the target.

If you want the PDBs to auto-open on future CDB restarts, once they are open in the right state:

```sql
ALTER PLUGGABLE DATABASE lab_clone SAVE STATE;
ALTER PLUGGABLE DATABASE lab_src SAVE STATE;
```

Saving state does not replace configuring listeners/services or testing application connections.

### 4.5. Verifying the Clone Is Independent

Connect via the new PDB's service and check the container:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;
```

Example inside the new PDB, assuming a lab schema exists with appropriate privileges:

```sql
CREATE TABLE clone_marker (
    id NUMBER PRIMARY KEY,
    note_text VARCHAR2(100)
);

INSERT INTO clone_marker VALUES (1, 'Created only in LAB_CLONE');
COMMIT;
```

Switch to the source PDB via the source's own service and verify the marker table does not automatically appear from post-clone changes. The marker table is just an example; use a dedicated schema and never create it in `SYS`.

## 5. Cloning a READ WRITE PDB: Hot Clone

In Oracle versions supporting **hot cloning**, you can clone from a PDB open in **READ WRITE** mode without having to switch the source to `READ ONLY`. This reduces downtime when creating clones.

However, hot clone availability and requirements depend on **version, CDB type, local undo mode, ARCHIVELOG mode, and clone type (local/remote)**. For instance, modern Oracle versions support online PDB cloning when local undo and required redo retention conditions are met.

Conceptual flow:

```text
LAB_SRC is READ WRITE
    |
    | application continues generating changes
    |
    +---- hot clone ----> LAB_CLONE
                            |
                            +-- consistent data at an appropriate clone point
```

Do not think of hot clone as "Oracle copies changing files with the OS `cp` command": Oracle handles metadata, redo, and consistency through database mechanisms.

The clone command can use the same form:

```sql
CREATE PLUGGABLE DATABASE lab_clone
FROM lab_src;
```

Yet **execute this only when the environment meets hot clone prerequisites**, such as OMF or file mapping and appropriate redo/undo configuration. If unsure about version/config, use the **READ ONLY** procedure in Section 4 or follow the cloning guide for your exact running version.

Source checks commonly run by DBAs include:

```sql
SELECT log_mode
FROM v$database;

SELECT property_name, property_value
FROM database_properties
WHERE property_name = 'LOCAL_UNDO_ENABLED';
```

Local undo status can also be checked using other views or properties appropriate to the version. Observing configuration alone is not enough to guarantee hot clone works; cross-check the exact version's requirements.

## 6. Cloning a PDB from Another CDB

**Remote PDB cloning** creates a PDB in the target CDB from a PDB in a source CDB. Oracle uses a **database link** from the target CDB to connect to the source database during the clone.

Diagram:

```text
CDB1                               CDB2
└── LAB_SRC  ─── Oracle Net ─────> └── LAB_REMOTE
                 / database link       (new PDB)
```

SQL template in the target CDB:

```sql
CREATE PLUGGABLE DATABASE lab_remote
FROM lab_src@cdb_source_link;
```

`cdb_source_link` must be created/configured **in advance** with appropriate privileges, and the target CDB must have a datafile placement strategy (OMF or valid file mapping). Do not assume any arbitrary database link to a PDB is sufficient; remote cloning requires accounts, privileges, and connectivity meeting the version's Multitenant rules.

To deploy, the DBA must verify:

- Oracle Net connectivity from **target CDB** to **source CDB**.
- Account privileges across the database link and PDB creation privileges at the target.
- Version/character set/compatibility.
- Source `READ ONLY` requirement or corresponding hot clone prerequisites.
- Network bandwidth and storage capacity, as data can be large.
- Database link security: credentials, network, and auditing.

**Remote clone differs from unplug/plug:** Cloning creates a new PDB in the target while keeping the source; unplug/plug is usually for **moving** a PDB detached from the old CDB.

## 7. Snapshot Copy and Refreshable Clone: Two Variants to Distinguish

### 7.1. Snapshot Copy

Oracle supports forms of **snapshot copy** in compatible environments/versions and storage technologies. Rather than immediately creating an independent copy of every block, a snapshot can rely on copy-on-write or base storage data.

Common advantages are initialization speed and low initial space usage. In return, the copy has **storage technology prerequisites** and may carry dependencies on the snapshot/source. Never treat a snapshot copy as a fully independent copy you can freely relocate by copying an arbitrary directory.

Syntax example depending on version support:

```sql
CREATE PLUGGABLE DATABASE lab_snapshot
FROM lab_src
SNAPSHOT COPY;
```

This example is only for feature recognition. Do not run without confirming storage and version support.

### 7.2. Refreshable PDB Clone

A refreshable clone can periodically pull changes from the source via the PDB refresh mechanism. This is not a static snapshot: the source continues changing while the copy retains link metadata to update later.

Constraints commonly considered:

- During refresh phases, the copy normally operates with **read-only** semantics compatible with refresh mode.
- Network/link configuration, redo retention, and refresh schedule.
- Version requirements, undo mode, and source/target compatibility.
- Procedure to convert to an independent PDB when refreshes are no longer needed.

`REFRESH MODE` and `REFRESH` options require consulting syntax for the deployed Oracle release. This lesson focuses primarily on **independent clones** and **unplug/plug**, the two foundational workflows.

## 8. Unplug: Detaching a PDB and Exporting Metadata

### 8.1. What Does Unplug Produce?

When **unplugging**, Oracle generates a descriptor file for the PDB to be used when **plugging** into a compatible CDB. The common manifest is an **XML** file; some versions also support a **PDB archive** format with the `.pdb` extension.

Example:

```text
CDB1
└── LAB_SRC
     |
     +-- UNPLUG INTO '/u03/pdbstage/lab_src.xml'
     |
     +--> lab_src.xml       (metadata/manifest)
     +--> datafiles         (still in storage location)
```

**The XML does not contain all table data.** The XML file contains descriptive/path information and details Oracle needs to recognize the PDB; **the datafiles must still be present and accessible** when plugging.

This is the most critical point when moving between servers: copying only `lab_src.xml` to a new server will **not be enough** to reopen the PDB with its data.

### 8.2. Procedure to Unplug a PDB Using XML

Assume `LAB_SRC` is a **lab PDB** you manage. First, ensure a valid backup exists and confirm no application sessions still need service. In the CDB root:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;
```

Once the PDB is closed, generate the XML manifest:

```sql
ALTER PLUGGABLE DATABASE lab_src
UNPLUG INTO '/u03/pdbstage/lab_src.xml';
```

The file is created on a **filesystem writable by the Oracle Database server process**; it does not appear on a laptop running SQL Developer. The directory must exist and the Oracle OS user must have write permissions.

Check state:

```sql
SELECT name, open_mode
FROM v$pdbs
WHERE name = 'LAB_SRC';
```

After unplugging, the PDB cannot be used like a normal open PDB. Metadata for the PDB may remain in the source CDB until removed from the CDB catalog.

### 8.3. DROP ... KEEP DATAFILES After Unplug

If the goal is to move the PDB to another CDB, clean up remaining metadata in the source CDB. After a successful unplug, for the **right lab PDB**:

```sql
DROP PLUGGABLE DATABASE lab_src KEEP DATAFILES;
```

This command removes the PDB's metadata from the source CDB while **retaining the datafiles** so they can be plugged elsewhere. This is the right option when the data still needs to be moved.

**Never replace `KEEP DATAFILES` with `INCLUDING DATAFILES`** in a PDB move workflow: `INCLUDING DATAFILES` can delete the physical datafiles, wiping out the dataset you intended to move. Before dropping, confirm the XML was created successfully and have a plan to preserve/transfer the datafiles.

### 8.4. Unplugging into a PDB Archive

In Oracle versions supporting PDB archives, you can use:

```sql
ALTER PLUGGABLE DATABASE lab_src
UNPLUG INTO '/u03/pdbstage/lab_src.pdb';
```

The archive format packages metadata together with related files into a bundle for easier transport, though it requires sufficient disk space, filesystem permissions, and may have restrictions for certain datafile types or features. Cross-check version details before using. XML and archive are **alternatives** for a single unplug; do not run both commands on an already unplugged PDB.

Even when using an archive, you still need to check compatibility with the target CDB, TDE state, and post-plug requirements.

## 9. Transferring the PDB Dataset to the Target Machine/CDB

In an XML unplug scenario, moving a PDB typically involves:

1. **Closing the source and creating the manifest** via `UNPLUG INTO`.
2. Ensuring the associated **datafiles** are preserved; identify files by metadata and actual locations.
3. Copying or moving the manifest **and** required datafiles to a location accessible by the target CDB.
4. Setting filesystem/ASM permissions and ensuring no other process has the files open or is modifying them.
5. On the target CDB, running `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` and reviewing violations.
6. If compatible, executing `CREATE PLUGGABLE DATABASE ... USING` with the appropriate file option.
7. Opening the PDB, checking status/violations, and testing application connectivity.

If the XML references `/u02/oradata/CDB1/lab_src/system01.dbf` while on the target server the datafile sits at `/u04/incoming/lab_src/system01.dbf`, you need a mechanism to map **source paths** using the version's syntax (such as `SOURCE_FILE_NAME_CONVERT` where appropriate, plus `FILE_NAME_CONVERT` for target files) or standardize staging paths so Oracle locates the files.

**Do not hand-edit the XML to "quickly rename things"** outside supported procedures/documentation, because the manifest holds internal metadata and validation details.

With ASM, RAC, ACFS, TDE, or multi-node storage, transferring datafiles can have special requirements. Do not apply regular filesystem copy commands verbatim to ASM diskgroups.

### Only XML or Also Datafiles?

| Case | What Is Needed at Target? | Meaning |
|---|---|---|
| `UNPLUG INTO ...xml` | XML manifest **and** all required datafiles accessible from target DB server | XML only describes the PDB |
| `UNPLUG INTO ...pdb` | Valid PDB archive, supported version, and enough space to extract/plug | Archive can package metadata/files |
| **Clone over database link** | Link and remote clone prerequisites; Oracle copies data via SQL clone mechanics | Does not require manual XML unplug first |
| **Snapshot copy** | Supported storage/snapshot backend and copy dependencies | Not equivalent to a full standalone copy of all datafiles |

## 10. Checking Compatibility Before Plugging

Not every PDB from one CDB can be plugged into any arbitrary CDB. Oracle checks multiple metadata attributes and system states to ensure the PDB can function properly at the destination.

### 10.1. Categories of Conditions to Cross-Check

| Category | What to Inspect | Example Impact |
|---|---|---|
| **Database version** | Release/patch level of source PDB and target CDB | A PDB from a newer release cannot arbitrarily plug down into an older release; moving up may require an upgrade |
| **COMPATIBLE** | Data format compatibility level and used features | Target CDB does not support the source PDB's compatibility level |
| **Character set** | Database character set and national character set; version-specific Multitenant rules | PDB and target CDB must meet character-set compatibility requirements |
| **Installed components/options** | Components, options, and SQL patch installation status | PDB uses a component missing or incompatible in the target CDB |
| **Time zone file/version** | Timezone data version compatibility | May produce warnings or require timezone upgrade |
| **Platform and physical data** | Platform, endian/format, block size, transportability | Datafiles cannot be used directly at target if conditions mismatch |
| **TDE** | Encryption keys, wallet/keystore, and key transfer mechanism | A PDB with encrypted data lacking valid keys cannot be used normally |
| **Datafile paths/space** | File read/write permissions, mapping, insufficient space, or name collisions | `CREATE ... USING` fails or collides with another PDB's files |
| **CDB limits** | Allowed PDB count, resources, edition policies | Cannot create new PDB or open the desired number of PDBs |
| **Metadata/conflicts** | PDB name, GUID/DBID, internal metadata, and dependencies | Requires recreating/renaming or resolving constraints before plugging |

This table is a checklist guide. **Exact compatibility rules depend on the release, RU, and actual configuration.** Never assume two sides are fully compatible simply because both carry the label "Oracle 19c."

### 10.2. DBMS_PDB.CHECK_PLUG_COMPATIBILITY

Oracle provides the `DBMS_PDB` package to read a PDB's metadata and test whether it can be plugged into the **target CDB**.

First, place the XML manifest on a path accessible to the **target database server**. Log into **`CDB$ROOT`** of the target CDB with appropriate privileges:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
SET SERVEROUTPUT ON SIZE UNLIMITED
```

Run the compatibility check:

```sql
DECLARE
    l_compatible BOOLEAN;
BEGIN
    l_compatible := DBMS_PDB.CHECK_PLUG_COMPATIBILITY(
        pdb_descr_file => '/u03/pdbstage/lab_src.xml',
        pdb_name       => 'LAB_MOVED'
    );

    IF l_compatible THEN
        DBMS_OUTPUT.PUT_LINE('COMPATIBLE: proceed to review violations.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('INCOMPATIBLE: resolve violations first.');
    END IF;
END;
/
```

Two primary parameters:

- `PDB_DESCR_FILE`: path to the PDB's XML manifest.
- `PDB_NAME`: intended PDB name when plugged into the target CDB.

The `BOOLEAN` return indicates overall compatibility. However, `TRUE` **does not mean there are zero warnings or post-plug tasks**. Always query the violations view.

### 10.3. PDB_PLUG_IN_VIOLATIONS

On the target CDB, after running the check, query:

```sql
SELECT time,
       name,
       cause,
       type,
       message,
       status,
       action
FROM pdb_plug_in_violations
WHERE name = 'LAB_MOVED'
ORDER BY time;
```

Depending on version and check timing, the columns typically help identify:

- `NAME`: affected PDB or intended name.
- `CAUSE`: compatibility category.
- `TYPE`: severity, such as `ERROR` or `WARNING`.
- `MESSAGE`: explanation of the issue detected by Oracle.
- `STATUS`: resolution state, such as `PENDING` or `RESOLVED`, depending on report type.
- `ACTION`: remediation guidance when provided by Oracle.

**Prioritize unresolved `TYPE='ERROR'` entries.** Some warnings may allow plugging, yet the PDB requires remediation, upgrades, or verification before application use.

Example filtering entries requiring attention:

```sql
SELECT type, cause, message, status, action
FROM pdb_plug_in_violations
WHERE name = 'LAB_MOVED'
  AND status <> 'RESOLVED'
ORDER BY type, cause;
```

Do not manually edit datafile/metadata contents to bypass checks; follow Oracle's prescribed actions and your environment's operational policies.

### 10.4. If CHECK_PLUG_COMPATIBILITY Returns FALSE

If `FALSE`, the right procedure is:

1. Read `PDB_PLUG_IN_VIOLATIONS` completely and classify errors vs. warnings.
2. Cross-check version/RU/`COMPATIBLE`, components, character set, timezone, TDE, and file paths.
3. If needed, prepare a more suitable target CDB or perform upgrade/patch/keystore migration using supported procedures.
4. After addressing conditions, **re-run the compatibility check**.
5. Plug only once compatibility has been verified.

Renaming the PDB or moving file locations **cannot** fix version, component, or encryption key mismatches.

## 11. Plugging a PDB from XML into the Target CDB

### 11.1. NOCOPY: Using Existing Datafiles

When the manifest and datafiles are already in their final locations, and paths in metadata match actual files, one option is **`NOCOPY`**:

```sql
CREATE PLUGGABLE DATABASE lab_moved
USING '/u03/pdbstage/lab_src.xml'
NOCOPY
TEMPFILE REUSE;
```

Meaning:

- `USING`: reads the PDB description from XML.
- `NOCOPY`: uses datafiles in place; Oracle does not copy datafile contents elsewhere.
- `TEMPFILE REUSE`: permits reusing tempfiles when compatible with the configuration.

**Critical precondition:** Because `NOCOPY` reuses the datafiles, those files **must not simultaneously belong to another active PDB**. Never use NOCOPY as a way to "make two PDBs point to the same set of datafiles"; that is not a valid clone and risks data destruction.

If datafiles were moved to a path different from the manifest, a matching mapping mechanism is needed; this example assumes files are already at the matching path.

### 11.2. COPY: Creating File Copies at the Target

When source datafiles remain in a readable location yet you want the target PDB to own its **own copy**, use `COPY` along with prepared mapping:

```sql
CREATE PLUGGABLE DATABASE lab_moved
USING '/u03/pdbstage/lab_src.xml'
COPY
FILE_NAME_CONVERT = (
    '/u02/oradata/CDB1/lab_src/',
    '/u02/oradata/CDB2/lab_moved/'
);
```

This syntax assumes:

- Source files referenced by the XML are still accessible at the source path.
- The mapping pairs accurately reflect the file paths Oracle needs.
- The target CDB has permission to create files in the target directory without dangerous name collisions.

`COPY` and `NOCOPY` have distinct semantics. When using `COPY`, ensure enough storage space for copying datafiles. Depending on version, `MOVE`, OMF, or other clauses may exist; consult `CREATE PLUGGABLE DATABASE ... USING` for your exact Oracle release.

### 11.3. If Using OMF

If the target CDB has Oracle Managed Files configured, Oracle can automatically generate target file paths using `DB_CREATE_FILE_DEST` and related settings. Do not arbitrarily combine `FILE_NAME_CONVERT` with OMF if the system's file-naming rules can resolve destinations automatically.

Check on the target CDB:

```sql
SHOW PARAMETER db_create_file_dest
SHOW PARAMETER pdb_file_name_convert
```

The specific option depends on source–target conditions and Oracle version. **Never change CDB-wide parameters** just to run an example without evaluating the impact on other PDBs.

### 11.4. Plugging from a PDB Archive

If supported, a `.pdb` archive file can serve as the source:

```sql
CREATE PLUGGABLE DATABASE lab_moved
USING '/u03/pdbstage/lab_src.pdb';
```

File location, extract/copy options, and accessibility can differ from `USING ...xml` depending on version. Apply this only when the target CDB supports the archive format and after reviewing the corresponding PDB archive guide; the check in Section 10 using an XML manifest is the primary illustrative workflow.

## 12. Opening the PDB After Plugging and Resolving Warnings

After `CREATE PLUGGABLE DATABASE ... USING` succeeds, the PDB may be in `MOUNTED` state. Check state:

```sql
SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LAB_MOVED';
```

Re-check violations:

```sql
SELECT type, cause, message, status, action
FROM pdb_plug_in_violations
WHERE name = 'LAB_MOVED'
ORDER BY time;
```

If there are no unresolved errors and the environment is ready, open the PDB:

```sql
ALTER PLUGGABLE DATABASE lab_moved OPEN READ WRITE;
```

Verify:

```sql
SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LAB_MOVED';
```

The goal for a normally functioning lab environment is:

```text
NAME        OPEN_MODE      RESTRICTED
----------- -------------- ----------
LAB_MOVED   READ WRITE     NO
```

The example shows expected output, not proof that a real PDB is guaranteed to open. If the PDB opens **RESTRICTED** or encounters errors, read the messages and `PDB_PLUG_IN_VIOLATIONS`; some cases require running upgrades, SQL patch updates, or fixing specific components before allowing application access.

When you need the open state to persist across CDB restarts:

```sql
ALTER PLUGGABLE DATABASE lab_moved SAVE STATE;
```

### 12.1. Checking Services and Application Connections

A PDB named `LAB_MOVED` typically gets a matching default service per Multitenant configuration, yet applications may use a **custom service name** managed by the DBA. Verify which service is published in the real environment.

In the CDB root, check services:

```sql
SELECT name, network_name, pdb
FROM v$active_services
WHERE UPPER(pdb) = 'LAB_MOVED'
ORDER BY name;
```

On the listener host:

```bash
lsnrctl services
```

From a client (replace host, port, service name, and username with real values):

```bash
sqlplus app_user@//db-target.example:1521/LAB_MOVED
```

Inside the session, run:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS current_service,
       USER AS connected_user
FROM dual;

SELECT 1 AS connection_ok FROM dual;
```

The SQL connection confirms the path to the PDB works. For production systems, continue verifying application objects, users, jobs, scheduler, directory objects, database links, external integrations, and privileges in the target environment.

### 12.2. Post-Plug Upgrade Steps May Be Needed

If the source PDB is on a different version/patch level than the target CDB, the PDB may require **upgrade/dictionary patching** using Oracle-supported workflows and tools. Common examples include running the appropriate upgrade tool or `datapatch` to synchronize SQL patch metadata; older releases converting a non-CDB to a PDB also have their own conversion script.

**Do not blindly run `noncdb_to_pdb.sql` for every PDB-to-PDB plug**: that script belongs to converting a **non-CDB** into a PDB, which differs from detaching an existing PDB from a source CDB. Only run procedures required by your Oracle release documentation and compatibility warnings.

### 12.3. TDE Keystore and Encryption Keys

If the source contains data encrypted with **Transparent Data Encryption (TDE)**, moving datafiles and XML does not automatically guarantee the target CDB has the needed keys.

Account for:

- Keystore/wallet in source and target CDBs.
- Managing TDE master keys and exporting/importing keys per version and isolated/united keystore mode.
- Keystore access permissions, keystore open state, and key backups.
- Restrictions when cloning/plugging across Free/different editions or configurations.

Never put keystore passwords or key copies in public manifests, source code, or logs. If the compatibility check returns encryption-related warnings, resolve them through TDE security administration procedures before serving users.

## 13. Comprehensive Hands-On Example: Unplugging and Re-Plugging a Lab PDB

This section simulates the workflow **on the same host or an environment with access to the exact original datafiles**, to clarify metadata changes. The example targets **LAB_SRC**, a lab PDB permitted to be stopped and detached from the CDB; never apply it to a production PDB.

### Prerequisites

- A lab CDB containing PDB `LAB_SRC` with a small amount of test data.
- No critical applications depending on `LAB_SRC`.
- An administrative account authorized to manage PDBs.
- Directory `/u03/pdbstage` exists on the database server and the Oracle OS user has write permission.
- A backup or recoverable copy of data taken before operating.
- Original datafiles will remain at the same paths after dropping metadata.

### Step 1 — Confirm Initial State

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

SELECT name, open_mode
FROM v$pdbs
WHERE name = 'LAB_SRC';

SELECT con_id, name
FROM v$datafile
WHERE con_id = (
    SELECT con_id FROM v$pdbs WHERE name = 'LAB_SRC'
)
ORDER BY name;
```

Record the datafile paths. This lets you verify the files remain intact after unplugging.

### Step 2 — Close and Unplug

```sql
ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;

ALTER PLUGGABLE DATABASE lab_src
UNPLUG INTO '/u03/pdbstage/lab_src.xml';
```

Confirm the command succeeded, the XML file exists on the server, and storage reported no errors. Do not reopen the unplugged PDB.

### Step 3 — Remove Source Metadata While Keeping Files

```sql
DROP PLUGGABLE DATABASE lab_src KEEP DATAFILES;
```

This command is a high-impact step; do not run it for any other PDB. Afterward, the original datafiles must remain intact if you intend to re-plug with NOCOPY.

### Step 4 — Check Compatibility in the Receiving CDB

In this lab, the receiving CDB is the original CDB. If the target is another CDB, transfer the XML and datafiles first, then run the steps below in the **target** CDB.

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
    l_ok BOOLEAN;
BEGIN
    l_ok := DBMS_PDB.CHECK_PLUG_COMPATIBILITY(
        pdb_descr_file => '/u03/pdbstage/lab_src.xml',
        pdb_name       => 'LAB_SRC'
    );

    IF l_ok THEN
        DBMS_OUTPUT.PUT_LINE('COMPATIBLE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('INCOMPATIBLE');
    END IF;
END;
/
```

Check violations:

```sql
SELECT type, cause, message, status, action
FROM pdb_plug_in_violations
WHERE name = 'LAB_SRC'
ORDER BY type, cause;
```

If the check fails or unresolved errors exist, **stop here** to resolve compatibility. Never attempt to plug by ignoring errors.

### Step 5 — Re-Plug Existing Datafiles

Because the old PDB was removed from the CDB with `KEEP DATAFILES` and the files remain at the paths recorded in the manifest, NOCOPY can be used:

```sql
CREATE PLUGGABLE DATABASE lab_src
USING '/u03/pdbstage/lab_src.xml'
NOCOPY
TEMPFILE REUSE;
```

Never run this command if the old PDB is still in the CDB or the datafiles are already opened by another database.

### Step 6 — Open and Verify Data

```sql
ALTER PLUGGABLE DATABASE lab_src OPEN READ WRITE;

SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LAB_SRC';

ALTER PLUGGABLE DATABASE lab_src SAVE STATE;
```

Connect to the PDB service as a lab user and confirm:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
       USER AS connected_user
FROM dual;
```

Query an application table that existed before unplugging and compare row counts/check keys recorded prior to the operation. If the data matches, the unplug/plug succeeded for the lab objective.

### Step 7 — If Performing Across Two CDBs

The workflow from Step 2 to Step 6 keeps the same structure, with these differences:

- Must transfer the XML **and datafiles** or PDB archive to the target server/storage.
- Use the name `LAB_MOVED` if renaming the PDB in the target CDB.
- Check compatibility **on CDB2**, not CDB1.
- Use appropriate file mapping and choose `COPY` or `NOCOPY` based on file locations.
- Handle listener/service, TDE keys, and post-plug warnings in CDB2.
- Only cut applications over to the target PDB after all verification steps pass.

## 14. Troubleshooting Common Issues

| Symptom/Error | Cause to Investigate | Resolution Path |
|---|---|---|
| Cannot clone because source is open READ WRITE | Version/clone method does not support hot clone with current config | Use read-only clone workflow or configure hot clone support per docs |
| `FILE_NAME_CONVERT` fails to create files | Wrong source mapping path, missing target directory, OS permissions, or file collision | Check `V$DATAFILE`, filesystem/ASM, permissions, and choose OMF if appropriate |
| `UNPLUG INTO` fails to write XML | Wrong server path, missing write permission, insufficient space | Create proper staging dir on DB server; check Oracle OS user |
| After unplug, only XML was copied to new server | Actual datafiles are missing | Transfer all datafiles or use a supported PDB archive |
| `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` returns `FALSE` | Version, component, charset, timezone, TDE, or other incompatibility | Query `PDB_PLUG_IN_VIOLATIONS` and resolve root causes |
| Plug succeeds yet PDB opens `RESTRICTED` | Remaining violations or SQL component upgrade/patch work needed | Check violations and alert log; run required post-plug procedures |
| Cannot open encrypted PDB | Incorrect key/wallet/keystore or keys not transferred | Perform TDE migration per security administration procedures |
| Service missing from listener | PDB not open or service not registered/configured | Check `V$PDBS`, `V$ACTIVE_SERVICES`, `lsnrctl services` |
| ORA-01017 when connecting to plugged PDB | Wrong credentials, service, or PDB | Verify user exists in the right PDB, auth settings, and service |
| New PDB has name conflict | PDB name already exists in target CDB | Choose a new name and verify metadata/filenames |
| Target datafile collides with file in use | Wrong mapping, or used NOCOPY while files belong to another database | Stop immediately; check physical file ownership and use COPY/separate paths |
| Clone runs slowly and disk usage spikes | Large PDB, slow I/O, full copy instead of snapshot | Estimate size, inspect storage, and pick appropriate method |

Oracle messages may appear with codes such as `ORA-650xx`, `ORA-651xx`, or filesystem errors, though exact codes vary by scenario and version. Save the **full error message**, the exact SQL executed, timestamp, and environment rather than relying on a single code without context.

## 15. Data Protection Principles When Working with PDBs

### 15.1. Unplug Is Not a Backup

Unplugging creates a manifest and detaches a PDB from a CDB, but **it does not create an independent, restore-tested backup**. The XML and datafiles might sit on the same failing storage device; in that case, unplugging cannot help you recover.

For critical data, maintain an RMAN backup strategy and test restores before structural changes. Align backups with retention policies, encryption, and off-source storage.

### 15.2. Avoid Having Two CDBs Manage the Same Set of Datafiles

`NOCOPY` is valid only when existing files are handed over exclusively to the PDB in the target CDB. Pointing two concurrently active PDBs/CDBs at the same set of datafiles is not cloning and can cause severe corruption.

To run two environments in parallel, use **clone**, `COPY`, valid RMAN duplication, or an Oracle-supported snapshot method.

### 15.3. Metadata Also Needs Security

An XML manifest can expose structure, metadata, and internal paths. Archive files can hold datafiles containing sensitive data. You should:

- Restrict read/write permissions on staging files.
- Transfer files over secure channels.
- Protect TDE keystores/keys with dedicated procedures.
- Clean up staging files per policy once verification completes.
- Avoid committing XML manifests or datafiles into public repositories.

### 15.4. Account for Identities and Integrations Outside the PDB

A PDB holds schemas and data, yet applications also rely on components outside the data itself:

- Service names and listener/SCAN routing.
- Scheduler jobs, database links, directory objects, external tables.
- Hostnames/paths, network ACLs, and filesystem permissions.
- Secret management, TDE keystores, and external authentication systems.
- Connection pool configs such as service names or ports in JDBC.
- Data Guard, backup/monitoring, and operational runbooks post-move.

Thus, "PDB is OPEN READ WRITE" is an important technical milestone, yet **does not by itself prove the entire application migrated successfully**.

## 16. Quick Post-Operation Status and Configuration Checks

In the CDB root, with appropriate privileges, a useful inspection query set is:

```sql
SELECT name, open_mode, cdb
FROM v$database;

SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;

SELECT name, network_name, pdb
FROM v$active_services
WHERE UPPER(pdb) IN ('LAB_SRC', 'LAB_CLONE', 'LAB_MOVED')
ORDER BY pdb, name;

SELECT time, name, type, cause, status, message
FROM pdb_plug_in_violations
WHERE name IN ('LAB_CLONE', 'LAB_MOVED', 'LAB_SRC')
ORDER BY time;
```

When cross-checking files:

```sql
SELECT con_id, file#, name
FROM v$datafile
ORDER BY con_id, file#;
```

And inside the PDB itself, confirm:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       USER AS username
FROM dual;
```

Include real application names and queries in the final verification rather than relying solely on the PDB opening successfully.

## 17. Decision Tree: Which Method to Use?

```text
What do you want to do with the PDB?
|
+-- Create a copy for parallel testing?
|      |
|      +--> CLONE
|            |-- READ ONLY source: simple, easy-to-control workflow
|            |-- READ WRITE source: only when hot clone is supported
|            +-- Need minimal copied data: check snapshot copy prerequisites
|
+-- Want a copy periodically updated from the source?
|      |
|      +--> REFRESHABLE PDB CLONE (if supported)
|
+-- Want to move a PDB to another CDB?
|      |
|      +--> UNPLUG
|             |
|             +--> XML + DATAFILES, or PDB ARCHIVE
|             |
|             +--> Transfer files/staging to target environment
|             |
|             +--> DBMS_PDB.CHECK_PLUG_COMPATIBILITY
|             |       |
|             |       +-- FALSE/ERROR: resolve compatibility
|             |       +-- TRUE: still inspect violations
|             |
|             +--> CREATE PLUGGABLE DATABASE ... USING
|             |
|             +--> OPEN + check violations + service + SQL
|
+-- Need to recover data after an incident?
       |
       +--> RMAN BACKUP/RECOVERY and appropriate DR strategy
```

Looking at this tree, remember **clone creates a copy**, whereas **unplug/plug detaches/attaches a PDB along with its metadata and appropriate physical data**. The compatibility check is an independent step that must never be skipped when moving a PDB across CDBs or versions.

## 18. Practice Exercises and Review Questions

### Exercise 1 — Creating an Independent Clone

**Context:** You have a lab PDB named `LAB_SRC` in a CDB and need to create `LAB_CLONE` for testing without altering the source's data.

Requirements:

1. Verify the CDB root and `LAB_SRC` status.
2. Prepare the source as `READ ONLY` if not using hot clone.
3. Clone `LAB_SRC` into `LAB_CLONE` using OMF or appropriate `FILE_NAME_CONVERT`.
4. Open the clone `READ WRITE`, and return the source to `READ WRITE`.
5. Create a test object inside the clone and demonstrate it does not appear in the source from post-clone changes.
6. Record all file paths and service names used.

**Question:** Why is copying the datafile directory with an OS command while the PDB is open not equivalent to `CREATE PLUGGABLE DATABASE ... FROM`?

**Hint:** Oracle must guarantee metadata, PDB identity, consistency, redo, and file-management requirements; arbitrary filesystem copies provide none of these guarantees.

### Exercise 2 — Unplug and Re-Plug in the Same CDB

**Context:** Use only a test PDB `LAB_SRC` that has a backup and is permitted to stop.

Requirements:

1. Record datafile names prior to the operation.
2. Close the PDB and unplug it to XML.
3. Only once XML/datafiles are safe, drop metadata with `KEEP DATAFILES`.
4. Run `DBMS_PDB.CHECK_PLUG_COMPATIBILITY`.
5. Query `PDB_PLUG_IN_VIOLATIONS`.
6. If compatible, re-plug using `NOCOPY`.
7. Open the PDB, verify data, and test SQL connectivity.

**Question:** If you only save the XML manifest and lose the datafiles, why cannot it be treated as a backup?

**Hint:** Metadata describes structure/identity and files; the actual data lives in the datafiles.

### Exercise 3 — Analyzing Compatibility Check Results

Suppose `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` returns `FALSE` and `PDB_PLUG_IN_VIOLATIONS` contains:

```text
TYPE    CAUSE             MESSAGE (illustrative)
ERROR   OPTION            Component version mismatch
WARNING TIMEZONE_VERSION  Timezone version differs
```

Answer:

1. Should you proceed immediately with `CREATE ... USING`?
2. What kind of details does the DBA need to verify?
3. Will renaming `LAB_MOVED` to another PDB name fix the component mismatch error?

**Guidance:** Do not proceed while severe errors remain; inspect versions, patches/components, and Oracle guidance; renaming does not resolve version/component conflicts.

### Exercise 4 — Choosing COPY vs. NOCOPY

Consider two scenarios:

- **A:** Moving a PDB to another CDB on the same storage; original datafiles have been released from the source CDB and can be used in place.
- **B:** Keeping a staging set of files and wanting to create an independent copy of datafiles in the target CDB's directory.

**Guided answer:** A can consider `NOCOPY` if exclusive file ownership and mapping are satisfied; B can choose `COPY` and appropriate `FILE_NAME_CONVERT`/OMF.

### Exercise 5 — Post-Plug Issue

PDB `LAB_MOVED` appears in `V$PDBS`, yet SQL Developer reports the service does not exist. Outline the inspection order.

**Hint:** Check `OPEN_MODE`/`RESTRICTED`, `PDB_PLUG_IN_VIOLATIONS`, service in `V$ACTIVE_SERVICES`, listener `lsnrctl services`, hostname/port, and exact service name in the client connection. Do not create new users or open firewalls before identifying the failing layer.

## 19. Conclusion on PDB Portability

Oracle Multitenant enables managing PDBs as relatively independent units within a CDB:

- **Clone** to create parallel environments from source data.
- **Unplug** to package descriptive metadata and detach a PDB from a CDB.
- **Plug** to attach a valid PDB package into a target CDB.
- **DBMS_PDB.CHECK_PLUG_COMPATIBILITY** together with **PDB_PLUG_IN_VIOLATIONS** help identify and resolve discrepancies before/after attaching a PDB.

To operate safely, simultaneously account for **PDB open mode, identity and datafiles, database version, storage configuration, TDE, listener/services, and administrative privileges**. Even though the SQL statements are short, a complete PDB move always requires verifying data, connectivity, and application dependencies.

### Official Documentation for Version Cross-Reference

- [Oracle Database Multitenant Administrator's Guide](https://docs.oracle.com/en/database/) — Creating, cloning, unplugging, plugging and managing PDBs.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Syntax for `CREATE PLUGGABLE DATABASE`, `ALTER PLUGGABLE DATABASE`, and `DROP PLUGGABLE DATABASE`.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_PDB` package and `CHECK_PLUG_COMPATIBILITY`.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — `V$PDBS`, `V$ACTIVE_SERVICES`, and `PDB_PLUG_IN_VIOLATIONS`.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/) — TDE, keystores, and key transfer requirements in Multitenant.

When using Oracle 19c, 21c, 23ai, or 26ai, consult the exact documentation set for your **deployed version and patch level**, as hot clone, snapshot copy, archive, compatibility, and post-plug step capabilities can differ.
