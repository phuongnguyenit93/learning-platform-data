# Choosing the Right Oracle Edition for Practice Labs and Resource Limits

An Oracle environment used for learning needs to **match the functionality required by the lab**, **run stably on available resources**, and **be reproducible when repeating exercises**. Choosing the edition with the most features is not always best: a personal machine running an IDE, browser, and database simultaneously can run out of RAM; conversely, a browser-based SQL service is lightweight but does not allow practicing instance administration.

This lesson guides you on how to choose the Oracle Database **release**, **edition**, and **deployment method** for labs covering SQL, PL/SQL, Java/JDBC, schema design, and basic administration. The goal is to arrive at a well-reasoned configuration before downloading software or creating a virtual machine.

## 1. Distinguishing Easily Confused Choices

When asking "which Oracle version should I use?", there are actually at least four decisions:

| Aspect | Question to Answer | Examples |
| --- | --- | --- |
| **Release** | Which Oracle generation's syntax and behavior does the lesson require? | 19c, 21c, 23ai, 26ai |
| **Edition / usage rights** | What features are needed, and what resource limits and licensing terms apply? | Oracle AI Database Free, Standard Edition 2 (SE2), Enterprise Edition (EE) |
| **Deployment form** | Where does the database run, and who is responsible for installing and administering it? | Direct installation, container, virtual machine, OCI service |
| **Connection tool** | How does the learner send SQL or application code to the database? | SQLcl, SQL Developer, SQL*Plus, JDBC |

**SQL Developer and SQLcl are client tools, not an Oracle Database server.** Installing SQL Developer alone will not automatically create a database on your machine. Similarly, an Oracle container is a way to *package and run* a specific edition/release, not a separate edition.

### Release and edition serve different roles

- **Release** determines feature versions, syntax, compatibility, and support lifecycle. A script using a new 26ai feature may not run on 19c.
- **Edition** determines the permitted feature set and usage limits. Within the same release, Free, SE2, and EE do not necessarily grant usage rights to the exact same features.
- **If a lesson explicitly specifies 19c**, do not automatically switch to 26ai just because 26ai is newer: output, screens, and support for a specific feature may differ. Check the release and edition documentation matching the lab requirements.

At the time of writing, **Oracle AI Database 26ai Free** is the current Free option recommended by Oracle for local development and practice; Oracle notes that 26ai has replaced 23ai in the current product line. **Oracle Database 21c XE** and older XE releases may still appear in older curricula, but you should not download them by default for new labs unless there is a specific compatibility requirement.

## 2. Options Suitable for a Practice Lab

| Option | Best suited when | What to plan ahead |
| --- | --- | --- |
| **Oracle AI Database 26ai Free on a personal machine** | Learning SQL, PL/SQL, schemas, indexes, transactions, Java app connectivity, and basic administration | Has CPU/RAM/data limits; the machine must have enough capacity for the OS, IDE, and database combined |
| **Oracle AI Database 26ai Free in a container** | Wanting environment isolation, easy recreation, and consistency across team members | Docker/Podman still consumes host RAM and disk space; a volume is needed to persist data |
| **Oracle AI Database 26ai Free installed directly or in a VM** | Wanting to observe OS services, listener, files, and administrative operations close to a server environment | Installation and system maintenance are more complex than a container; a VM also consumes its own resources |
| **Oracle Live SQL (web-based)** | Only needing to practice basic SQL/PL/SQL on a low-spec machine or where software installation is restricted | No permission to manage the instance, listener, file system, backups, or network configuration |
| **OCI Always Free Autonomous Database** | Wanting a remote database with cloud-provisioned resources, or learning how to access a managed service | Requires an account, network access, and adherence to current cloud quotas/policies; administration privileges differ from self-installed databases |
| **Oracle 19c / 21c or SE2 / EE in a provisioned environment** | The lab explicitly names an older release, commercial features, or enterprise system compatibility | Must verify the installation, usage rights, support, and access conditions; do not assume Free can substitute |

**Default recommendation:** if the lab does not lock a specific version, the learner has a capable machine, and real SQL/PLSQL/JDBC execution is needed, start with **26ai Free deployed in a container**. When the lab requires observing OS-level services or server-level recovery, consider direct installation or a VM. If the goal is solely writing queries and the machine is very weak, start on Live SQL.

### Free "Full" and "Lite" in containers

Oracle Container Registry provides **Full** (for example, tag `latest`) and **Lite** (tag `latest-lite`) Free images. Lite is convenient when prioritizing a smaller image size and very simple exercises, but it **lacks several components included in Full**; the image documentation notes Lite's limitations, such as Oracle Data Pump and RMAN.

Therefore:

- Exercises with `SELECT`, `JOIN`, `GROUP BY`, or simple JDBC communication: you may consider Lite after verifying every feature used in the lab.
- Exercises with `expdp`/`impdp`, backup/recovery with RMAN, certain diagnostic tools, and advanced features: choose **Full** or a verified Oracle environment that includes all required components.
- Do not switch an image from Full to Lite on the same data volume without a supported migration/restore plan.

"Lighter" here refers to the packaged component selection; it **does not mean** Oracle Lite is a different RDBMS or that it necessarily uses less RAM in every exercise.

## 3. Reading Resource Limits Correctly

For **Oracle AI Database 26ai Free**, Oracle publishes the following core limits:

| Free Limit | Practical Meaning |
| --- | --- |
| **Up to 2 CPU cores** for database processing | Having more host cores does not allow Free to exceed this processing limit for the database |
| **Up to 2 GB RAM for the database** | Database memory limit (SGA and PGA), **not** the total RAM needed for the host/container/IDE |
| **Up to 12 GB of user data** | Limit on user data inside Oracle; **not** the total disk space consumed by the image, redo, temporary files, logs, and backups |
| **One installation per logical environment** | A logical environment can be a physical machine, VM, or container; Free's specific rules must be respected |

Exceeding the user data size limit can trigger `ORA-12954`; attempting to run another Free installation in the same logical environment can trigger `ORA-00442`. Edition limits cannot be "unlocked" by allocating more RAM or CPU to the container.

**Distinguishing product limits from machine requirements:**

1. **Free limits** are the ceiling Oracle enforces on the engine, even on a powerful host.
2. **Minimum installation requirements** depend on the OS and distribution format. The Linux installation guide for 26ai Free states a minimum of 1 GB RAM, 2 GB RAM recommended, and at least 10 GB disk space on supported Linux platforms; the Windows documentation requires at least 2 GB RAM, roughly 8.5 GB for the software, plus at least 2 GB of temporary disk space.
3. **Resources for comfortable learning** must also account for the browser, SQL client, IntelliJ/VS Code, JVM, Docker Desktop/VM, data volumes, and downloaded installers/files.

The numbers in the table below are **recommended planning targets**, not minimum specs guaranteed by Oracle:

| Learning machine / environment | Reasonable approach | Reason |
| --- | --- | --- |
| **2–4 GB RAM, limited disk space** | Live SQL or OCI if Internet and a suitable account are available | Local database + OS + IDE easily contend for RAM |
| **Around 8 GB RAM, at least 25–40 GB free disk** | Free container or direct install; manage how many apps stay open simultaneously | Leaves buffer for the image, data, Java builds, logs, and multiple lab sessions |
| **16 GB RAM or more, ample disk space** | Free container/VM; can run Java apps and admin tools alongside | More host headroom, though **Free is still capped at 2 cores / 2 GB RAM** |
| **Shared lab machine / server** | A managed environment providing dedicated learner accounts/schemas, or isolated provisioned environments per learner | Prevents service/port collisions, accidental deletion of each other's data, and exposure of admin accounts |

**Disk note:** do not treat `12 GB user data` as meaning only 12 GB of free disk space is required. The Oracle software/image, database structures, temporary files, redo, logs, Docker layers, and backups can make actual disk usage significantly larger. If the machine only has a few GB free, choose a web/cloud lab first.

### Quick resource check before choosing

Write down four facts about your machine:

- **CPU architecture:** x86-64 or ARM64; the image/installer must support the actual architecture, especially on Apple Silicon Macs.
- **Physical RAM and currently free memory:** evaluate while the required practice applications are running.
- **Free space on the drive storing the image/volume or Oracle data:** not just the drive where downloads are saved.
- **Container/VM capability and installation permissions:** Docker Desktop, Podman, BIOS virtualization, OS admin rights, and lab-imposed restrictions.

Do not conclude that "Free database only uses 2 GB" means a 2 GB RAM laptop will run Windows, Docker Desktop, and an IDE stably together. The database's RAM cap and the **entire environment's** resource cost are two different calculations.

## 4. Decision Workflow from Lesson Requirements

### Step 1 — Identify what the lab strictly requires

First, confirm which category the lab belongs to:

- **Pure SQL:** DDL, DML, queries, joins, aggregates, constraints.
- **PL/SQL:** blocks, functions, procedures, packages, exceptions, triggers.
- **Application programming:** JDBC, Spring JDBC/JPA, transactions, connection pools.
- **Oracle architecture:** schemas, tablespaces, CDB/PDB, users/roles, service names, listener.
- **DBA / advanced:** Data Pump, RMAN, flashback, tuning, partitioning, replication, high availability.

Cross-check **each required feature** against the documentation for the release and edition. Administrative/advanced features may require `SYSDBA` privileges, components absent from Lite, a suitable cloud service, or a licensed edition. Do not assume all DBA features are supported just because basic SQL statements run.

### Step 2 — Identify compatibility requirements

If the assignment or project team explicitly specifies `Oracle 19c`, 19c syntax and behavior are the primary criteria. If the lab targets an existing enterprise system, ask for the target environment's release/patch level and schema management approach.

If there are no compatibility constraints, prefer the current Free release and its accompanying documentation to avoid investing effort in an outdated environment. Changing releases should be treated as a deliberate compatibility decision, especially when the lab involves advanced SQL, JDBC drivers, or DBA scripts.

### Step 3 — Check edition and licensing terms

For foundational labs, Free is usually sufficient for learning. For features requiring SE2/EE or specific privileges, verify the feature list and **usage rights** in the Oracle Licensing documentation for that release. Being "able to download an installer" does not mean permission to use every feature for every purpose.

Oracle states that **AI Database Free does not include Oracle Support and does not receive patches, including security patches**. Therefore, using Free for isolated labs, demos, and small-scale development is practical; environments with long-term operational or security requirements should use an appropriately supported service or edition.

### Step 4 — Choose the runtime mode based on machine and admin rights

`Need to run SQL without install rights` → Live SQL.  
`Need a dedicated, easily recreated database` → Free container.  
`Need OS/listener/Oracle file tasks` → Direct installation or a purposefully prepared VM.  
`Weak machine but need app connectivity` → Database on OCI/lab server, ensuring network and access permissions.  
`Need commercial features` → Pre-provisioned SE2/EE environment with verified usage rights.

### Step 5 — Verify a connectable output

Before concluding an environment is ready, you need to know:

1. Listener host and port.
2. **The PDB service name** used for the lab; do not just guess a SID.
3. Dedicated learner user/schema and required privileges.
4. How data persists across restarts, how to reset the lab, and how to export/import data when switching machines.

An environment where "the container is running" but the application cannot log into the PDB is not yet ready for practice.

## 5. Scenario-Based Selection Examples

### Scenario A — Learning SQL on a 4 GB RAM laptop

**Prompt:** write `CREATE TABLE`, `INSERT`, `SELECT`, `JOIN`, and `GROUP BY`. No Java server access or tablespace creation required.

**Choice:** Oracle Live SQL. The learner only needs a browser and a session; there is no need to run a local Oracle engine. Save scripts and results externally because storage capacity, sample data, and schema privileges depend on the service.

**Unsuitable for this lab:** turning a SQL exercise into a multi-GB VM installation or assuming `SYSDBA` privileges exist on Live SQL.

### Scenario B — Learning Java JDBC/Spring on an 8 GB RAM laptop

**Prompt:** CRUD application using Oracle, creating tables and transactions, repeatedly running integration tests. Docker/Podman can be installed.

**Choice:** Oracle AI Database 26ai Free **Full** in a container, with a persistent data volume, listener exposed on localhost, and a dedicated user/schema. Pick a JDBC driver version compatible with your JDK and Oracle server per driver documentation, then configure the URL pointing to the right PDB.

**Note:** evaluate total RAM when running the JVM, IDE, and container together; do not raise the JVM `-Xmx` or container limits without checking remaining host RAM.

### Scenario C — Backup administration lab using RMAN

**Prompt:** back up the database, restore it, and observe files/database processes.

**Choice:** Free **Full** in a VM or container with an appropriate strategy for managing files and backups, after verifying every RMAN operation required by the lab. **Do not choose Lite** for an RMAN lab because the image documentation lists RMAN as unsupported.

**Note:** you need significantly more disk space than user data alone, adding room for backups and restores. Labs covering Oracle RAC, Data Guard, or specific EE features must be verified separately; never assume Free is enough just because it shares the Oracle name.

### Scenario D — Team must fix an application running on Oracle 19c

**Prompt:** troubleshoot SQL/PLSQL statements for an existing system running on 19c.

**Choice:** a team-provisioned 19c test environment with a schema and patch level representative of the target system. You may use 26ai Free to test ideas independently, but **results on 26ai do not replace 19c compatibility testing**.

## 6. Quick Trial of a Local Setup: Oracle 26ai Free Full

The example below illustrates a lab configuration using **Podman in a Bash environment**. Podman must already be installed with sufficient resources; if using Docker or another OS, follow Oracle's corresponding image instructions. The aim is to highlight the components you must specify when choosing an Oracle setup: **image, persistent storage, password, port, and service**.

### 6.1. Initializing the container

```bash
# Run on a machine with Bash + Podman; choose a strong password for the lab.
read -r -s -p "Oracle admin password: " DB_PASSWORD
printf '\n'
printf '%s' "$DB_PASSWORD" | podman secret create oracle_pwd -
unset DB_PASSWORD

podman run -d \
  --name oracle-lab \
  --publish 127.0.0.1:1521:1521 \
  --secret oracle_pwd \
  --volume oracle-lab-data:/opt/oracle/oradata \
  container-registry.oracle.com/database/free:latest

# Watch logs until the database is ready to accept connections.
podman logs -f oracle-lab
```

- `container-registry.oracle.com/database/free:latest`: the **Full** image per current Oracle Container Registry documentation. For projects requiring repeated reproducibility, **pin a specific tag/digest** instead of letting `latest` silently change.
- `--publish 127.0.0.1:1521:1521`: maps Oracle port 1521 to localhost for local labs; avoids unintentionally exposing the database to the Internet.
- `--volume oracle-lab-data:/opt/oracle/oradata`: data does not disappear merely by stopping or removing the container (though removing the volume deletes the data inside it).
- `--secret oracle_pwd`: passes the admin password via a Podman secret; avoids writing the password directly into commands and shell history.

If port 1521 on the host is already in use, you can change the **host port** to `1522` in the mapping `127.0.0.1:1522:1521`. Clients will then connect to `localhost:1522`, while the listener inside the container remains on 1521.

### 6.2. Connecting to the right PDB service

With default Oracle AI Database 26ai Free settings:

| Component | Common Value |
| --- | --- |
| CDB service | `FREE` |
| First PDB service | `FREEPDB1` |
| Listener port inside container | `1521` |
| JDBC URL to PDB from host | `jdbc:oracle:thin:@//localhost:1521/FREEPDB1` |

In SQLcl, an example interactive login using the admin account for the **learning schema creation** step:

```text
sql system@localhost:1521/FREEPDB1
```

SQLcl will prompt for the password. Once logged in, you can create a dedicated user for the lab (replace `<CUSTOM_PASSWORD>` with an appropriate password):

```sql
CREATE USER lab_student IDENTIFIED BY "<CUSTOM_PASSWORD>"
  QUOTA 200M ON USERS;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW,
      CREATE SEQUENCE, CREATE PROCEDURE TO lab_student;
```

Log back in as `lab_student` and run a verification query:

```sql
SELECT USER AS current_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
```

The expected result is user `LAB_STUDENT` and PDB `FREEPDB1` (if defaults were not changed). For Java, configure this URL and user credentials; do not use `SYS` or `SYSTEM` accounts for routine CRUD operations.

> **Why must you select a PDB?** Modern Oracle releases typically use a multitenant architecture. `FREE` is the service of the container database (CDB), whereas `FREEPDB1` is the pluggable database (PDB) where application schemas are created for lessons. Connecting to the CDB root by mistake can lead to user creation errors, missing tables, or operating in the wrong administrative scope. Always verify the actual service name from your installed environment.

### 6.3. Lifecycle management

```bash
podman stop oracle-lab
podman start oracle-lab
podman ps --filter name=oracle-lab
```

For multi-day labs, establish an export/backup approach suited to your learning goals. **Volumes preserve data across container replacements, but a volume by itself does not replace a backup.** In particular, labs involving data deletion or recovery should keep an independent copy to restore the initial state.

## 7. Common Mistakes When Choosing an Oracle Edition

| Misconception | Correct Understanding |
| --- | --- |
| "Free only uses 2 GB RAM, so a 2 GB machine is enough." | 2 GB is the database memory cap; the OS, container, SQL client, and IDE still need their own RAM. |
| "12 GB of data means only a 12 GB drive is needed." | You also need space for software/images, system data, temporary files, redo, logs, backups, and build artifacts. |
| "Using SQL Developer means I already have an Oracle server." | SQL Developer is a client; it must connect to an already-running database somewhere. |
| "A newer version always behaves just like 19c." | Compatibility and syntax depend on the release; always test on the required version. |
| "If the container has port 1521, any app can connect." | You also need proper network mapping, a ready database, the right service name, user, password, and privileges. |
| "Full and Lite are identical since both are Free." | Lite omits certain components; check the supported features list before choosing. |
| "Allocating 8 CPUs / 8 GB to the container bypasses Free limits." | The 2-core, 2 GB database RAM, and 12 GB user data caps are enforced by the edition. |
| "Free environments fit every production system." | Oracle does not provide patches/support as with supported editions; evaluate security and SLA requirements. |
| "OCI Always Free and local Free are administered the same way." | Cloud services have their own operational model, permissions, and quotas; local DBA labs do not necessarily translate directly. |

## 8. Decision Exercise

For each planned lab, fill out the following **environment selection sheet**:

```yaml
lesson_name: "Example: JDBC transactions with Oracle"
required:
  release: "Not version-locked"
  features: ["SQL", "transaction", "JDBC"]
  dba_privileges: false
lab_machine:
  cpu_arch: "x86-64"
  host_ram: "8 GB"
  free_disk: "35 GB"
  can_run_container: true
choice:
  release: "26ai"
  edition: "Oracle AI Database Free"
  deploy: "Podman container, Full image"
  database_service: "FREEPDB1"
  data_persistence: "Named volume"
reason: "Sufficient for SQL/JDBC; environment isolation; no advanced DBA tasks required"
risks_to_check:
  - "Total RAM when opening the IDE and database together"
  - "Image tag, network permissions, and compatible JDBC driver"
```

Then explain these three questions to yourself:

1. Why does this chosen release/edition satisfy the lab's **mandatory features**?
2. Why are the machine's **RAM, CPU, disk, and install permissions** sufficient for the entire environment, not just the engine alone?
3. If the machine is too weak or the lab demands features missing from Free/Lite, what is the alternative and what are the trade-offs?

A good decision typically records **release + edition + runtime method + host resources + service name + rationale**. This information also helps an instructor or teammate reproduce the exact same environment when troubleshooting errors.

## Oracle Documentation to Cross-Check Before Installing

- [Oracle AI Database Free – overview and Free resources](https://www.oracle.com/database/free/) — current Free release and resources.
- [Oracle AI Database Free – Get Started](https://www.oracle.com/database/free/get-started/) — installation methods, container images, and `FREE`/`FREEPDB1` connection patterns.
- [Oracle Database Free FAQ](https://www.oracle.com/database/free/faq/) — limits, patching/support, migration, and included tools.
- [Oracle AI Database 26ai Free – Licensing Restrictions](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/licensing-restrictions.html) — CPU, RAM, user data size, and logical environment limits.
- [Oracle AI Database 26ai Free – Linux system requirements](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/requirements.html) and [Windows](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinw/requirements.html) — platform-specific installation prerequisites.
- [Oracle Database Docker images](https://github.com/oracle/docker-images/blob/main/OracleDatabase/SingleInstance/README.md) — configuration variables, volumes, secrets, and container run instructions.

Links and feature support may change across releases or image tags. Before locking in an environment for a long-term course, re-verify the documentation for the specific release, edition, machine architecture, and features used by the labs.
