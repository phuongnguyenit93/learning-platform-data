# Overview of ASM, Disk Groups, Redundancy, and Boundaries with Filesystems

In Oracle Database, a table like `SALES.ORDERS` is a logical object, while the table's data ultimately resides in **datafiles** on storage devices. Oracle must know how to allocate capacity, distribute files across multiple disks, handle disk failures, and open those files while the database runs. There are two familiar organization approaches:

- **Traditional filesystem:** Oracle stores datafiles, control files, redo logs, etc., under OS-managed paths such as `/u02/oradata/SALES/users01.dbf`.
- **Oracle Automatic Storage Management (ASM):** Oracle uses a specialized storage management layer to organize devices into **ASM disk groups** and store Oracle files using names like `+DATA/SALES/DATAFILE/users.257.123456789`.

**ASM is neither a new SQL database nor an ordinary Linux directory.** It is a storage management component built for Oracle, providing data distribution and redundancy at the disk group level. Understanding ASM helps you read `+`-prefixed filenames properly, plan capacity, distinguish disk failures from database failures, and decide when to use a filesystem or ASM.

## 1. Placing ASM in the Right Architectural Spot

An application does not need to know which disk holds each table block. It sends SQL to the **Oracle Database instance**; the instance uses storage metadata to read/write the database's files.

### When Using a Filesystem

```text
Application / SQL client
        |
        v
Oracle Database Instance (SGA + background processes)
        |
        v
Datafile /u02/oradata/SALES/users01.dbf
        |
        v
OS Filesystem (e.g., XFS/ext4)
        |
        v
Volume/LVM/RAID/SAN or block device
        |
        v
Physical disks or provisioned storage
```

The operating system and volume/filesystem layer manage file paths. The DBA must still place datafiles onto suitable filesystems/mount points, monitor space, and coordinate with storage admins when expanding.

### When Using ASM

```text
Application / SQL client
        |
        v
Oracle Database Instance
        |       (queries metadata, performs database I/O)
        |
        +---------> Oracle ASM Instance
        |            - manages ASM metadata
        |            - mounts disk groups
        |            - coordinates rebalancing
        |              (does not proxy all block I/O)
        v
ASM file: +DATA/SALES/DATAFILE/users.257....
        |
        v
ASM Disk Group +DATA
        |               |
        v               v
ASM disk A          ASM disk B ... (block devices / LUNs)
        \               /
         \--- physical storage ---/
```

**Common point of confusion:** an Oracle Database instance and an Oracle ASM instance are **two different types of instances**. The ASM instance manages metadata, disk group layout, and disk group operations; the database instance handles SQL, transactions, data caching, and database recovery. During normal data reads/writes, the database instance performs I/O **directly to the ASM devices**, using metadata obtained from ASM. There is no rule saying "every `SELECT` must pass all blocks through the ASM process."

ASM is typically deployed via **Oracle Grid Infrastructure** with its own configuration and administrative privileges. It works for single-instance databases and is the common storage choice for Oracle RAC; **using ASM does not mean you are automatically running RAC**.

## 2. From Storage Devices to ASM Disk Groups

Layers to distinguish:

| Concept | Meaning | Illustrative Example |
|---|---|---|
| **Physical disk / LUN / block device** | Capacity device visible to the OS; can be a physical drive or a LUN presented by SAN/RAID | `/dev/mapper/asm-data01` |
| **ASM disk** | Eligible device recognized by ASM and added to a disk group | `DATA_0001` |
| **Failure group** | Group of ASM disks treated as sharing a fault domain; ASM avoids placing mirror copies in the same fault domain when possible | `RACK_A`, `RACK_B` |
| **ASM disk group** | Set of ASM disks managed as one storage pool, with redundancy rules and dedicated attributes | `+DATA`, `+RECO` |
| **ASM file** | File managed by ASM inside a disk group; the database can use it as a datafile, redo log, control file... | `+DATA/SALES/DATAFILE/...` |
| **ASM allocation unit (AU)** | ASM's fundamental allocation unit on a device | e.g., a disk group configured with a 4 MiB AU |
| **ASM file extent** | Portion of a file mapped by ASM to allocated regions on ASM disks | Extents distributed across multiple disks |

**An ASM disk group is not a tablespace.** A tablespace is a logical structure inside Oracle Database made up of datafiles or tempfiles; a disk group is where **those files are physically placed by ASM**. One disk group can hold files from multiple databases or multiple tablespaces; one database can use multiple disk groups.

### 2.1. Disk Discovery and Disk Membership

Before ASM can use a device, storage/OS admins must provision block devices/LUNs with stable names and permissions. ASM discovers candidate devices via its configured *disk discovery* mechanism. Depending on platform, this may use udev, Oracle ASMLib, or disk filtering/labeling mechanisms compatible with the deployed release.

A device added to a disk group stores membership info in its **ASM disk header**. Never arbitrarily:

- Run `mkfs` to create a regular filesystem on a device belonging to an ASM disk group.
- Mount an ASM disk like a regular XFS/ext4 volume.
- Copy files directly onto the block device or edit disk headers with OS tools.
- Change device paths without coordinating ASM/cluster configuration.

Such actions can corrupt data. Creating, adding, removing, replacing, or formatting devices must follow storage administration procedures with ownership and cluster-state verification.

### 2.2. File Organization by Allocation Unit and Extent

ASM divides storage space into **allocation units** and uses them to allocate **ASM file extents**. An extent can comprise one or more AUs depending on allocation rules and file size. ASM manages metadata mapping a file's extents to specific disks.

```text
ASM file: +DATA/SALES/DATAFILE/users...
        |
        +-- File extent 1 ---> ASM disk A: AUs
        |
        +-- File extent 2 ---> ASM disk B: AUs
        |
        +-- File extent 3 ---> ASM disk C: AUs
        |
        +-- File extent 4 ---> ASM disk A/B/... per distribution
```

This is an illustrative model, not a guarantee of which extent sits on which disk. **Oracle data blocks** are logical units of Oracle Database; **ASM AUs and ASM file extents** are ASM's storage management units. Never confuse them with extents/segments inside tablespaces: the two layers serve different roles.

ASM can **stripe** extents across multiple disks to distribute I/O load and improve balance. Striping behavior (*fine/coarse*) and applied templates differ by ASM file type, release, and configuration. Never assume "one ASM file" equals "one physical disk."

## 3. What Does an ASM Instance Manage?

An ASM instance has its own memory area, background processes, and parameters. The ASM instance does not store business tables and does not execute application SQL transactions. Its primary responsibilities include:

1. **Discovering and mounting disk groups:** verifying the disk set in a group and providing required metadata to database instances.
2. **Space management:** allocating and mapping ASM file extents.
3. **Redundancy management:** determining mirror copies by failure group and disk group/file attributes.
4. **Rebalancing:** when disks are added, removed, resized, or replaced, redistributing extents to balance capacity and satisfy redundancy rules.
5. **Providing metadata to database instances:** helping locate files and updating mappings when storage topology changes.

The database instance continues handling DBWn, LGWR, SGA, transactions, undo, redo, and database-level data recovery. Using ASM **does not make redo logs, RMAN, or database backups unnecessary**.

### 3.1. ASM on a Single Host vs. in a RAC Cluster

```text
SINGLE INSTANCE
  Host A:
    Database Instance A
    ASM Instance A --------> Disk Group +DATA

RAC / CLUSTER (simplified diagram)
  Node A: Database Instance A ---+
                                  +---- shared +DATA
  Node B: Database Instance B ---+     ASM Disk Group
      ASM instances/ASM services manage
      metadata per Grid Infrastructure architecture
```

In RAC, database instances of the same database access shared storage with coordinated data access mechanisms. Details can vary with **Flex ASM**, where a database instance does not necessarily reside on the same node as the ASM instance serving it. Never try simulating RAC by letting two independent database instances on two hosts arbitrarily open the same datafile directory.

### 3.2. Which Files Can Reside in ASM?

Oracle file types commonly supported in ASM disk groups:

- **Datafiles** and **tempfiles** of tablespaces.
- **Control files** and **online redo log files**.
- **Archived redo logs**, backup pieces, image copies, and **Fast Recovery Area (FRA)** files per configuration.
- **SPFILE** and other administrative files supported in ASM by Oracle / Oracle Grid Infrastructure.

ASM paths are assigned and managed by Oracle according to file type. OS-level files such as Java source code, downloaded images, shell scripts, system binaries, and standard application logs still belong on filesystems, object storage, or other suitable storage platforms.

## 4. Disk Group: A Storage Pool with Its Own Policies

Disk groups are usually given short, purpose-descriptive names:

| Common Name | Purpose | Notes |
|---|---|---|
| `+DATA` | Datafiles, control files, and some redo files | Does not require a separate group per table/tablespace |
| `+RECO` or `+FRA` | Fast Recovery Area, archived redo, and backup/recovery files | FRA has its own quota/cleanup rules; does not automatically count as an off-system backup |
| `+OCR` / disk group used for Grid Infrastructure | Certain cluster-related files per Oracle-supported models | Has specific compatibility, quorum, and cluster admin requirements |

These names are **conventions**, not mandatory reserved names. A disk group also has a **redundancy type**, **AU size**, **compatibility attributes**, mount state, disk count, and capacity. Naming a disk group `+RECO` does not automatically cause the database to write archived redo there: recovery destinations/paths must be configured explicitly.

### 4.1. Oracle Managed Files (OMF) and ASM Are Two Different Concepts

**OMF (Oracle Managed Files)** is the mechanism by which Oracle Database names and manages file lifecycles under configured destinations, such as:

```text
db_create_file_dest    = +DATA
db_recovery_file_dest  = +RECO
```

When properly configured, Oracle can automatically generate ASM filenames like:

```text
+DATA/SALES/DATAFILE/users.257.123456789
+DATA/SALES/CONTROLFILE/current.258.123456790
+RECO/SALES/ARCHIVELOG/...
```

OMF **is not synonymous with ASM**: Oracle Managed Files can also be used on a regular filesystem, and ASM supports **aliases** alongside Oracle-managed fully qualified names. Never try renaming, moving, or deleting datafiles directly like text files in an OS directory; use supported database commands/procedures or ASM/Oracle tools for each operation type.

### 4.2. One Database Can Span Multiple Disk Groups

```text
Database SALES_CDB
  +-- Tablespace SYSTEM -> datafiles in +DATA
  +-- Tablespace APP    -> datafiles in +DATA
  +-- Online redo logs  -> can reside in +DATA and/or suitable destinations
  +-- Archived redo     -> +RECO if FRA is configured
  +-- RMAN backups      -> +RECO or another backup destination

Database REPORT_CDB
  +-- Datafiles         -> can also share +DATA
```

**Tenant/schema/PDB boundaries do not automatically equal disk group boundaries.** Two PDBs inside the same CDB can place datafiles in the same disk group; two different databases can also share an ASM pool depending on capacity and isolation design. SQL data access permissions remain controlled by Oracle Database, independent of whether two files share a disk group.

## 5. Redundancy: What Types of Failures Does ASM Protect Against?

**Redundancy** here refers to creating **physical mirror copies of ASM file extents** per policy to maintain data availability when a disk or failure group fails. Protection level depends on failure group design, redundancy type, placement, file templates, and remaining free space.

### 5.1. Common Redundancy Types

| Disk Group Type | Core Principle | Protection Level to Understand |
|---|---|---|
| **EXTERNAL redundancy** (views often display `EXTERN`) | ASM does not mirror normal extents itself; expects underlying storage such as RAID/SAN to protect if needed | Losing an unprotected block device/LUN can lose files |
| **NORMAL redundancy** | Typically uses **two-way mirroring**: two extent copies in different failure groups | Can tolerate losing one failure group under proper design; needs space to restore redundancy |
| **HIGH redundancy** | Typically uses **three-way mirroring** across different failure groups | Can tolerate losing two failure groups when topology and policies fit; consumes more capacity |
| **FLEX redundancy** | Granular redundancy managed per **file group** and supported release capabilities | Cannot assume every file has two or three copies from the group type name alone |
| **EXTENDED / EXTEND redundancy** | Extended model across sites/locations in supported configurations | Requires dedicated site/failure-group/quorum design and fault tolerance planning |

**NORMAL does not simply mean "having two disks," and HIGH is not just "having three disks."** It is the number and layout of failure groups that lets ASM isolate mirror copies outside a single fault domain. For instance, losing power to one disk enclosure can knock out many disks simultaneously even if total disk count is large.

Actual file protection can also differ from defaults in some configurations: **ASM file templates**, file group properties, special files, and release-specific rules apply. This table outlines general architectural principles for selection, not a substitute for detailed configuration documentation.

### 5.2. Failure Groups Determine How Copies Are Isolated

Picture a NORMAL disk group with two fault domains:

```text
                      ASM DISK GROUP +DATA

        FAILURE GROUP FG_A          FAILURE GROUP FG_B
        (rack/tray/power A)         (rack/tray/power B)
          Disk A1, A2                  Disk B1, B2
             |                            |
       extent X, copy 1             extent X, copy 2
       extent Y, copy 2             extent Y, copy 1

A failure confined to FG_A -> FG_B still holds copies of extents X/Y.
```

For HIGH redundancy, the conceptual principle requires three independent fault domains to place three copies of each extent. NORMAL generally requires at least two failure groups; HIGH requires at least three, and exact disk/failure-group rules vary by version, group type, and deployment.

**A failure group represents "disks likely to fail together," not "disks guaranteed safe just because they sit next to each other."** If two failure groups share the same power supply, SAN controller, or storage array without true independence, a shared hardware failure can affect both. Designers must ground failure groups in actual hardware diagrams and fault domains.

### 5.3. EXTERNAL Redundancy Does Not Mean "Unsafe"

EXTERNAL lets ASM focus on striping/placement while underlying storage (such as managed RAID) handles protection by design. Conversely, if you present multiple unprotected LUNs from a single array and choose EXTERNAL, ASM will **not add mirror copies** to save data when a LUN fails.

You can run RAID beneath ASM and still choose ASM mirroring intentionally, though stacking multiple redundancy layers costs capacity, performance, and operational complexity. Define clearly **which layer protects against which failure**, avoiding the trap of assuming RAID is enough while blindly expecting ASM to protect further.

### 5.4. Redundancy Does Not Replace Backups

ASM mirroring maintains availability when storage components fail. It **cannot undo**:

- An accidental committed `DELETE`/`DROP TABLE`.
- Corrupted data caused by an application bug.
- Logical corruption legitimately written to all mirror copies.
- Site-wide disasters, lost accounts/access, or destruction of the entire storage system.
- Needs to restore the database to a **past point in time**.

Therefore, you still need **RMAN backups**, an archived redo/recovery strategy, restore testing, and independent copies matching RPO/RTO requirements. The FRA on `+RECO` centralizes recovery resources; **an FRA sitting on the same local infrastructure is not automatically an off-site backup**.

## 6. Reading Capacity Properly: RAW, FREE, and USABLE

One of the most common mistakes is seeing `FREE_MB` and assuming you can immediately add that exact number of MB of application data.

Columns DBAs commonly inspect in `V$ASM_DISKGROUP_STAT`:

| Column | Meaning |
|---|---|
| `TOTAL_MB` | Total capacity of ASM disks in the group (raw value), in view MB units |
| `FREE_MB` | Unallocated capacity at the ASM level; **before subtracting mirroring overhead and recovery reserve** |
| `REQUIRED_MIRROR_FREE_MB` | Estimated space needed to restore required mirroring after a failure group loss matching the redundancy type |
| `USABLE_FILE_MB` | Estimated remaining capacity usable for new files after accounting for redundancy and reserve requirements |
| `TYPE` | Redundancy type such as `EXTERN`, `NORMAL`, `HIGH`, `FLEX`, or `EXTEND` depending on release |
| `OFFLINE_DISKS` | Number of currently offline disks in the group |
| `STATE` | Mount/management state of the disk group |

In typical NORMAL or HIGH groups, the conceptual calculation is expressed as:

```text
NORMAL: usable ≈ (free - required_mirror_free) / 2
HIGH:   usable ≈ (free - required_mirror_free) / 3
EXTERNAL: typically no ASM-level mirror overhead
```

Example for reading meaning only: a NORMAL group with `FREE_MB = 200000` and `REQUIRED_MIRROR_FREE_MB = 40000` yields roughly **80,000 MB** of usable file space by the basic formula. You cannot conclude there is room for 200,000 MB of new files, because data requires two copies plus reserve capacity to restore redundancy.

**`REQUIRED_MIRROR_FREE_MB` is not necessarily a physically locked empty partition.** It is a management metric reflecting post-failure-group recovery capacity. In FLEX/EXTENDED disk groups, capacity interpretation is more complex due to per-file-group/site policies: consult views, formulas, and guides **for your exact release**. `USABLE_FILE_MB` can become negative if free headroom falls below the reserve target; negative does not automatically mean the database immediately halted.

Beyond ASM columns, also monitor actual tablespace/datafile capacity, FRA quotas, backup retention, and file autoextend limits. **Free space in a disk group** does not guarantee every tablespace can autoextend without hitting quotas, maxsize, or other policies.

## 7. Rebalance: When Adding, Replacing, or Dropping ASM Disks

ASM does not pin all files permanently to a single disk. When disk group resources change, ASM may need to **rebalance** to redistribute extents:

```text
Initially +DATA:     Disk A + Disk B
                       |       |
                       +-------+
                           |
       Add Disk C, ASM confirms membership
                           |
                      REBALANCE
                           |
       Redistribute some file extents across A/B/C
```

Rebalancing evens out disk utilization per ASM mechanics, and when a disk is dropped/removed, Oracle must relocate remaining data. In mirrored configurations, copies must still obey failure group rules.

Common administrative operations:

- Adding eligible new disks to a group.
- Replacing a failed disk or dropping a disk from a group via supported procedures.
- Increasing LUN capacity / resizing disks and signaling ASM to recognize the change.
- Monitoring rebalance progress and the priority/resources allocated to it.

**Rebalancing incurs I/O cost.** The database can stay operational during many supported online operations, yet workload throughput and latency can be impacted. Never assume adding/dropping disks always incurs zero downtime regardless of failure state, storage type, or remaining capacity.

Parameters/controls for **rebalance power** let administrators trade off migration speed against resources left for live workloads. Views such as `V$ASM_OPERATION` reflect active rebalance work, though exact column names, states, and controls depend on release. **Never run `ALTER DISKGROUP ... DROP DISK` "to test" on a live system**: it directly alters storage membership.

## 8. Boundaries Between ASM, Filesystems, RAID, and ACFS

### 8.1. An ASM Disk Group Is Not a Normal Mount Point

Compare two paths:

```text
Filesystem:
  /u02/oradata/SALES/users01.dbf

ASM:
  +DATA/SALES/DATAFILE/users.257.123456789
```

For a filesystem, `ls`, `df`, `mount`, and OS permissions inspect paths and capacity. For ASM, `+DATA` identifies a **disk group** in the ASM namespace, not a normally mounted `/DATA` directory. To inspect ASM file structures, use **ASMCMD** or Oracle views/tools matching administrative privileges.

An ASM file can have extents spread across multiple disks. You cannot treat `+DATA/SALES/...` as a shell pathname to copy with a regular `cp` command. Moving Oracle files between ASM and a filesystem requires tools and sequences suited to the file type, such as Oracle-supported database/RMAN/ASMCMD methods.

### 8.2. Filesystems Still Coexist Alongside ASM

ASM does not replace every filesystem on a server. The operating system and Oracle Grid/Database software still sit on appropriate filesystems, along with config files, scripts, Java programs, audit/trace logs, and other deployment files.

One server can simultaneously have:

```text
/u01/app/oracle/...    -> Oracle software, tools, some logs
/var/log/...           -> OS logs
+DATA                  -> datafiles/online redo managed by ASM
+RECO                  -> recovery/backup files managed by ASM
```

Do not run `df -h` to measure `USABLE_FILE_MB` of `+DATA`, and do not query `V$ASM_DISKGROUP` to find how much space remains on the drive holding Java source code.

### 8.3. Where Do RAID/LVM/SAN Sit?

RAID, volume managers, SANs, and cloud block storage belong to the layers providing or protecting **block devices**. ASM sits on the Oracle side, consuming devices presented by the OS/infrastructure and managing them into pools for Oracle files.

```text
Physical disks / cloud volumes
          |
       RAID / SAN / LUN (by design)
          |
 OS sees block device(s)
       /                 \
    Filesystem       ASM disk group
        |                 |
    /u02/...         +DATA/...
        \                 /
          Oracle Database
```

Multiple layers can work together; the diagram does not mandate RAID or LVM on every system. Choosing ASM EXTERNAL redundancy based on underlying protection must be **verified** via storage configuration and failure-scenario testing—never guess from LUN names.

### 8.4. Is Oracle ACFS the Same as ASM?

**Oracle ACFS (ASM Cluster File System)** is a **filesystem** built atop Oracle ASM Dynamic Volume Manager (ADVM) components in supported configurations. It can be mounted by the OS as a standard path to store eligible file types. Thus:

| Form | Visible Namespace | Primary Mechanism |
|---|---|---|
| Oracle files directly in ASM | `+DATA/...` | ASM manages file extents, not a standard OS path |
| Files in XFS/ext4 or another OS filesystem | `/u02/...` | OS filesystem manages files on volumes/block devices |
| Files in ACFS | Mount point like `/acfs/...` | ACFS/ADVM runs atop ASM infrastructure in supported setups |

**ACFS does not mean mounting a disk group directly like XFS.** ACFS is an additional filesystem layer with its own support matrix for OS, Oracle version, and file types. Never assume every Oracle Free/container or cloud service permits creating ACFS.

## 9. Read-Only Inspection in an ASM Environment

The following examples require an environment **where an admin has already set up Oracle Grid Infrastructure/ASM**, plus appropriate observation privileges. They do not create, format, add, or drop disks. If your lab uses Oracle Free on a regular filesystem, there may be **no ASM instance/disk group**; that is a normal deployment difference, not a flaw in the lesson.

### 9.1. Viewing Disk Groups via ASMCMD

On the ASM admin host with Oracle Grid Infrastructure environment and proper privileges:

```bash
asmcmd lsdg
asmcmd ls +DATA/
```

`lsdg` displays mounted groups, type, total/free/usable space, and related metrics depending on version. `ls +DATA/` browses the namespace of disk group `DATA` if it exists and the account has access. Disk group names must come from your real environment; never assume every lab has `+DATA`.

### 9.2. Viewing Capacity from the ASM Instance

Log into the **ASM instance** with an account granted appropriate ASM privileges (full administration typically uses `SYSASM`), then run **read-only** queries:

```sql
SELECT
    name,
    state,
    type,
    total_mb,
    free_mb,
    required_mirror_free_mb,
    usable_file_mb,
    offline_disks
FROM v$asm_diskgroup_stat
ORDER BY name;
```

`V$ASM_DISKGROUP_STAT` provides statistics already maintained by ASM, usually better suited for repeated monitoring queries than operations triggering disk discovery. Example output structure:

```text
NAME   STATE    TYPE     TOTAL_MB FREE_MB REQ_MIR_FREE_MB USABLE_FILE_MB
DATA   MOUNTED  NORMAL     ...      ...         ...             ...
RECO   MOUNTED  EXTERN     ...      ...         ...             ...
```

This is a **structural illustration**, not assumed capacity numbers for a live environment. `EXTERN` in the view indicates **EXTERNAL redundancy**.

### 9.3. Viewing Disks and Failure Groups

```sql
SELECT
    g.name AS diskgroup_name,
    d.name AS asm_disk_name,
    d.failgroup,
    d.path,
    d.mount_status,
    d.header_status,
    d.state,
    d.total_mb,
    d.free_mb
FROM v$asm_disk_stat d
JOIN v$asm_diskgroup_stat g
  ON g.group_number = d.group_number
ORDER BY g.name, d.failgroup, d.name;
```

From this, learners should distinguish:

- `PATH` is the identifying name/path of the **block device/LUN** seen by ASM, not a SQL table path.
- `FAILGROUP` shows the fault domain group assigned to the disk.
- `HEADER_STATUS` and `MOUNT_STATUS` help observe disk state per ASM, yet **are not a standalone green light to pull a disk out of a group**.
- Per-disk `TOTAL_MB`/`FREE_MB` show space distribution; evaluate alongside the overall group and rebalance activity.

For RAC/Flex ASM, verify which ASM instance you are connected to and the scope returned by views. Never interpret one node's state as the absolute state of the entire cluster.

### 9.4. Is the Database Instance Using ASM or Filesystem Files?

On the **Oracle Database instance**, an account authorized to read dictionary/dynamic views can query:

```sql
-- Datafiles of the current database/container per granted privileges
SELECT tablespace_name, file_name
FROM dba_data_files
ORDER BY tablespace_name, file_name;

-- Online redo log members
SELECT group#, member
FROM v$logfile
ORDER BY group#, member;

-- OMF/FRA destination settings
SELECT name, value
FROM v$parameter
WHERE name IN ('db_create_file_dest', 'db_recovery_file_dest')
ORDER BY name;
```

If `FILE_NAME` starts with `+DATA/...`, it is an **ASM-managed file**. Seeing `/u02/oradata/...` means the file sits on a filesystem path. One database can also use **both styles** during a transition or in supported setups; do not conclude from a single file.

In CDB/PDB, `DBA_DATA_FILES` is scoped to the **current container**; a DBA may need `CDB_*` views and matching privileges to inspect across PDBs. Never confuse `TABLESPACE_NAME` with an ASM disk group name.

### 9.5. Observing Rebalance During Storage Changes

For authorized admins while an actual rebalance operation is running:

```sql
SELECT group_number, operation, state, power, actual, sofar, est_work
FROM v$asm_operation;
```

Columns and contents depend on version/rebalance mechanics. If the view returns no rows, it may simply mean **no active operation is currently tracked**. This exercise is strictly observational—do not trigger disk changes just to generate output.

## 10. Choosing ASM vs. Filesystem by Scenario

| Scenario | Reasonable Choice | Reason |
|---|---|---|
| Learning SQL/JDBC on a laptop, Oracle Free container with a volume | **Environment-provided filesystem/volume** | Sufficient for SQL goals, avoids Grid Infrastructure deployment complexity |
| Dedicated lab on ASM disk groups, mirroring, and rebalancing | **ASM environment provisioned by DBA/instructor** | Requires devices, storage admin privileges, and controlled fault topology |
| Single-instance Oracle with well-managed SAN/RAID storage | **ASM or filesystem** per operational needs | Weigh toolchain, redundancy, backups, and admin team skills |
| Oracle RAC with shared storage | **ASM in an Oracle-supported architecture**, typically via Grid Infrastructure | Manages shared database storage and integrates with clusterware |
| Autonomous Database / managed cloud service | **Follow storage interface provided by the service** | Provider may abstract away ASM and withhold SYSASM privileges |
| Storing source code, deployment scripts, arbitrary OS files | **Appropriate filesystem/object storage** | Direct ASM disk groups are not general-purpose filesystems |
| Need an OS-mounted filesystem backed by Oracle ASM | **Evaluate ACFS/ADVM if platform supports it** | ACFS is a separate filesystem with deployment and licensing/support checks |

### Four Questions Before Deciding

1. **What must the workload store?** Oracle datafiles/redo/backups or arbitrary OS/application files?
2. **Who manages fault domains?** ASM failure groups, RAID/SAN, cloud block storage, or an intentional combination?
3. **Which capabilities are required?** Shared storage across RAC instances, online rebalancing, DATA/RECO separation, OMF auto-naming, or simple filesystem mounts?
4. **Does the environment support it and have admin expertise?** Grid Infrastructure, release/edition, OS, disk discovery, SYSASM, disk replacement workflows, and backup policies?

Choosing ASM solely because someone heard "it is faster than a filesystem" lacks grounding. Performance depends on I/O workload, device count/quality, cache, network/storage fabric, striping/mirroring layout, latency, and operations; no universal benchmark result applies to every system.

## 11. Common Cognitive Pitfalls

| Misconception | Accurate Understanding |
|---|---|
| "`+DATA` is a directory inside `/` on Linux." | `+DATA` is an ASM disk group namespace, not a normal filesystem mount point. |
| "An ASM disk group equals an Oracle tablespace." | Disk groups hold files; tablespaces are logical database objects using datafiles/tempfiles. |
| "The ASM instance executes application SQL." | The ASM instance manages storage metadata; the database instance handles SQL, transactions, and database recovery. |
| "Every database must have its own ASM disk group." | Multiple databases can share disk groups by design; one database can use multiple groups. |
| "NORMAL has two copies, so any two disks are enough." | Mirrors must reside in proper **failure groups**; hardware fault domains govern fault tolerance. |
| "ASM EXTERNAL redundancy means there are definitely no copies." | ASM does not mirror itself, yet underlying storage may provide RAID/mirroring or other protection. |
| "`FREE_MB` is the exact user data capacity you can still write." | Account for mirroring, `REQUIRED_MIRROR_FREE_MB`, `USABLE_FILE_MB`, and separate quota/file limits. |
| "ASM mirroring replaces backups." | Backups/recovery are still required for logical errors, corruption, point-in-time recovery, and full-system disasters. |
| "During ASM rebalance, the database is never affected." | Rebalancing uses I/O and resources; duration, latency, and risk depend on workload, topology, and change size. |
| "ACFS is how you directly mount `+DATA` like XFS." | ACFS is a filesystem layer atop ADVM/ASM in supported setups; it does not turn ASM disk groups into normal OS folders. |
| "Oracle Database Free always includes ASM for labs." | Many Free/container installs use filesystems; ASM needs a dedicated supported environment and privileges. |

## 12. Hands-On Practice and Thought Exercises

### Exercise 1 — Classify Components

Given the following items:

```text
/u02/oradata/SALES/system01.dbf
+DATA
+DATA/SALES/DATAFILE/system.257.123456789
ASM instance
Oracle Database instance
ASM disk DATA_0001
Failure group RACK_B
Tablespace USERS
RMAN backup
ACFS mount /acfs/reports
```

Classify each as **filesystem path**, **ASM disk group**, **ASM file**, **ASM disk**, **fault domain**, **database logical layer**, **instance**, or **backup/filesystem layer**. Explain why `Tablespace USERS` does not immediately identify a specific disk or OS path.

### Exercise 2 — Designing Failure Groups

A team is given 6 disks from two physical storage enclosures. Each enclosure shares one power feed and one controller; each holds 3 disks.

1. For ASM NORMAL redundancy, how should failure groups be defined by **enclosure/controller**?
2. If each disk were placed in its own failure group without accounting for whole-enclosure power loss, which mirroring assumption would break?
3. If HIGH redundancy is required, do **two independent enclosures** satisfy the three-fault-domain principle?
4. Where should backups be placed so they are not lost if both enclosures and the host fail completely?

**Hint:** failure groups must reflect shared failure scopes, not raw disk counts. HIGH redundancy requires three suitable fault domains in principle. Location/access-independent backups are a separate requirement from mirroring.

### Exercise 3 — Reading a Capacity Report

An administrator sees an ASM NORMAL group with **illustrative** metrics:

```text
FREE_MB                 = 200000
REQUIRED_MIRROR_FREE_MB = 40000
```

By the basic formula for NORMAL, approximate usable space for new files is:

```text
(200000 - 40000) / 2 = 80000 MB
```

Answer:

- Why can you not immediately write 200,000 MB of application data based on `FREE_MB` alone?
- Why must admins still monitor warning thresholds and recovery readiness when approaching full utilization of `USABLE_FILE_MB`?
- When data sits in a tablespace with its own `MAXSIZE` or user quota, does ASM usable space alone guarantee writes will succeed?

**Hint:** ASM capacity, file/tablespace limits, and user permissions are distinct boundaries.

### Exercise 4 — Read-Only Observation Lab

On an instructor-provided system with ASM and appropriate accounts:

1. Run `asmcmd lsdg` and record **NAME**, **TYPE**, **FREE_MB**, and **USABLE_FILE_MB** for a disk group.
2. Use `V$ASM_DISKGROUP_STAT` to cross-check mount state, offline disk count, and redundancy.
3. Use `V$ASM_DISK_STAT` to list failure groups. Sketch a diagram of each failure group and its member ASM disks.
4. From the database instance, inspect `DBA_DATA_FILES.FILE_NAME` and note which files use the `+GROUP/...` namespace vs. filesystem paths.
5. Write a short explanation: when an application updates a table, what role does the database instance play versus the ASM instance?

**Expected output:** an observation table and diagram using real environment names; no need to add/drop disks or alter settings.

### Exercise 5 — Choosing Storage for a Project

Project A is a JDBC CRUD exercise on a personal laptop with Docker and limited disk space. Project B is a three-node RAC system needing massive capacity, online administration, and a dedicated storage team. Project C is a PDF-export application needing a directory shared across a Java service and multiple OS processes.

For each project, propose **filesystem, ASM, or ACFS per platform support**, specify data storage boundaries, and explain backup management. In your explanation, distinguish storage redundancy from transaction durability and restore capability.

## 13. Architectural Conclusion

**Oracle ASM** organizes **ASM disks** into **disk groups**, distributes **ASM file extents** across devices, and depending on configuration performs **striping, mirroring, and rebalancing**. **Failure groups** model fault domains so mirror copies do not depend on a single physical component. **EXTERNAL**, **NORMAL**, **HIGH**, and extended redundancy types dictate protection/capacity strategies; capacity evaluation must examine **`USABLE_FILE_MB`** alongside other limits rather than `FREE_MB` alone.

At the software boundary, the **database instance** handles SQL and database I/O, the **ASM instance** manages storage metadata and disk groups, and the **OS filesystem** continues handling appropriate OS/application files. The `+DATA` prefix is a logical ASM path, not an ordinary folder. Understanding these layers clearly enables fault-tolerant storage design, accurate administrative interpretation, and never confusing ASM mirroring with backups.

## References

- [Oracle Automatic Storage Management Administrator's Guide — Oracle Database 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/ostmg/) — ASM instance concepts, disk groups, failure groups, redundancy, files, and rebalancing.
- [Oracle Database Concepts — Oracle Database Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — distinguishing database files, tablespaces/segments, and logical storage.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — descriptions of `V$ASM_DISKGROUP_STAT`, `V$ASM_DISK_STAT`, `V$ASM_OPERATION`, and capacity metrics.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — why backup, restore, and archived redo strategies remain essential even with mirroring.

Disk group admin procedures, ACFS/ADVM supportability, Flex/Extended redundancy, and usage rights depend on **Oracle release, edition, Grid Infrastructure, OS, and cloud platform**. In live deployments, consult exact environment documentation and follow approved storage change procedures.
