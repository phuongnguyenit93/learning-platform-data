# Installing and Initializing the Database with the Right Tool for Your Oracle Version

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Practice Environment  
> **Goal:** Install a connectable Oracle Database, identify the right container/PDB, create a dedicated schema, and run a first SQL query.

## 1. Distinguishing Software Installation from Database Initialization

In Oracle, **installing Oracle Database** and **creating a database** are related tasks, not synonyms:

1. **Installing server software (database software):** places Oracle binaries, libraries, and tools on the machine. The installation directory is typically called `ORACLE_HOME`.
2. **Initializing a database:** creates datafiles, control files, redo logs, instance configuration, admin accounts, and connection services.
3. **Starting and opening the database:** starts the instance, opens the database and PDB so they accept queries.
4. **Creating a practice schema:** creates a dedicated user with just enough privileges for exercises, instead of using `SYS`/`SYSTEM` for every operation.

Since Oracle Database 12c, the **multitenant** architecture uses:

- **CDB (Container Database):** the database holding the shared administrative layer, including the root container `CDB$ROOT`.
- **PDB (Pluggable Database):** a database plugged into a CDB, where application schemas, tables, and data typically reside.
- **Instance:** the set of processes and memory serving the database; `SID` identifies the instance on the server.
- **Listener:** the process accepting network connections, usually listening on TCP port `1521`.
- **Service name:** the service name clients use to reach the right database/PDB; distinct from `SID`.

Default setup example for Oracle AI Database 26ai Free:

```text
Computer / virtual machine / container
└── Oracle Database instance: SID = FREE
    └── CDB: FREE
        ├── CDB$ROOT        ← CDB administration
        ├── PDB$SEED        ← system template, do not store exercise data
        └── FREEPDB1        ← create users, tables, and practice data here

Client ── TCP localhost:1521 ── Listener ── service FREEPDB1
```

**Important consequence:** Connecting to service `FREE` usually places you in `CDB$ROOT`, whereas `FREEPDB1` places you in the practice PDB. Attempting to create an application user in the root container by mistake easily triggers error `ORA-65096`.

## 2. Choosing the Tool Based on Version and Environment

| Case | Suitable installation/initialization tool | Default or target database/PDB |
|---|---|---|
| **Oracle AI Database 26ai Free** (learning, development) | Windows installer; RPM package + `oracle-free-26ai configure` script on Linux; or Docker/Podman container | `FREE` / `FREEPDB1` |
| **Oracle Database 23ai Free** | OS installer, RPM + `oracle-free-23ai configure`, or matching container | `FREE` / `FREEPDB1` |
| **Oracle Database 21c XE**, **18c XE** | XE installer and bundled configuration tool; follow version-specific docs | `XE` / `XEPDB1` |
| **Oracle Database 19c**, 21c, 23ai/26ai Enterprise/Standard | Oracle Universal Installer (or documented deployment package), then **Database Configuration Assistant (DBCA)** to create CDB/PDB | Custom names, e.g., `ORCL` / `ORCLPDB1` |
| **Database on another server or Oracle Cloud** | No need to install a database server on your laptop; only need SQL Developer, SQLcl, SQL*Plus, or JDBC client and connection details | Use the **actual service name** provided by the administrator |

`SQL Developer` is a graphical tool for connecting and running SQL; `SQLcl` and `SQL*Plus` are command-line tools. They **do not replace the server installer or DBCA**. Conversely, DBCA is primarily used to create/manage databases; DBCA is not a daily SQL-authoring tool.

> **Recommended choice for new labs:** Oracle AI Database **26ai Free** on Docker/Podman if your machine already has a container runtime; or install **26ai Free** directly on supported Windows/Oracle Linux. If your course or project specifies 19c/21c, stick to that version and use its exact tooling. Do not mechanically replace `XE` with `FREE`.

### Prerequisites to prepare

- Verify **OS, CPU architecture, RAM, disk space, and admin privileges** in the documentation for your exact version. Oracle AI Database 26ai Free has Free edition resource/usage caps; the machine must also have headroom for the OS and learning tools.
- Download the installer from [Oracle AI Database Free](https://www.oracle.com/database/free/) and consult [Oracle Database 26ai — Install](https://docs.oracle.com/en/database/oracle/oracle-database/26/install.html). Never use an RPM/installer built for a different OS or architecture.
- Check port `1521` (or pick a different host port), ensure enough space for **datafiles** and **logs**, and have stable network access when pulling the image/installer.
- Prepare a strong, lab-specific password. Examples use admin accounts only during configuration; daily SQL work will use `LAB_ORACLE`.
- If the machine already has an older XE/Free install, Oracle services, or old data, **back up first** and check for `SID`, port, and service name conflicts. Do not overwrite or delete an existing installation just to run an example.

## 3. Method A — Running Oracle AI Database 26ai Free with Docker

This path fits Windows with Docker Desktop, Linux with Docker Engine, or macOS with a compatible container runtime. The commands below use **Bash** (Linux, macOS, or WSL). With Podman, replace `docker` with `podman` where your environment supports the equivalent syntax.

### 3.1. Creating a volume and running the official image

Check that Docker is running:

```bash
docker version
```

Place the admin password in an environment variable without typing it directly into the `docker run` command line:

```bash
read -r -s -p "New password for SYS/SYSTEM/PDBADMIN: " ORACLE_PWD
echo
export ORACLE_PWD
```

Then run:

```bash
docker volume create oracle-free-data
docker pull container-registry.oracle.com/database/free:latest

docker run -d \
  --name oracle-free \
  -p 127.0.0.1:1521:1521 \
  -e ORACLE_PWD \
  -v oracle-free-data:/opt/oracle/oradata \
  container-registry.oracle.com/database/free:latest

unset ORACLE_PWD
```

Meaning:

- `--name oracle-free`: container name used in subsequent commands.
- `-p 127.0.0.1:1521:1521`: maps port 1521 to the **host's localhost**, limiting access from external networks.
- `-e ORACLE_PWD`: passes the previously set environment variable to initialization; the password is applied to default admin accounts. For long-lived environments, prefer your runtime's **secret** mechanism over environment variables.
- `-v oracle-free-data:/opt/oracle/oradata`: preserves data in a named volume when the container stops or is properly recreated.
- `:latest`: pulls the current Free image; use a **specific version tag** when pinning a version for reproducibility or following an older curriculum.

**The first run** creates the database and can take some time depending on the machine. Follow the logs:

```bash
docker logs -f oracle-free
```

When you see a message along the lines of `DATABASE IS READY TO USE!`, the database is ready. Exit log tailing with `Ctrl+C`; this does not stop the database.

> If host port 1521 is already occupied, change the flag to `-p 127.0.0.1:1522:1521` and use port **1522** in all connection strings from the host. The port inside the container remains 1521.

### 3.2. Testing login to the PDB

You can use SQL*Plus included inside the container:

```bash
docker exec -it oracle-free sqlplus system@//localhost:1521/FREEPDB1
```

Enter the `SYSTEM` password set when creating the container; do not embed the password directly in a connect string saved in shell history. At the `SQL>` prompt, run:

```sql
SHOW CON_NAME;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;

EXIT;
```

The output of `SHOW CON_NAME` or `CURRENT_PDB` must be `FREEPDB1`. If not, check the **service name** used to connect.

### 3.3. Stopping and restarting

```bash
docker stop oracle-free
docker start oracle-free
docker ps --filter name=oracle-free
```

Stopping the container does not delete the named volume. **Do not delete the volume** if you need to keep your data. To connect from a client on the host, use `localhost:1521/FREEPDB1`.

## 4. Method B — Installing Oracle AI Database 26ai Free Directly on Windows

This path is suitable when you want the Oracle server to run as a Windows service.

1. Read the [26ai Free Installation Guide for Windows](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinw/). Verify a 64-bit OS and **Administrator** privileges; check `ORACLE_HOME`, `TNS_ADMIN`, and any previously installed Oracle versions to avoid conflicts.
2. Download the **Oracle AI Database 26ai Free for Windows** package from the official site, extract it, and run `setup.exe` with an administrator account.
3. Follow the wizard steps: choose the installation directory, confirm prerequisites, and set the admin password as prompted. Use the directory suggested by the wizard or a path whose permissions meet Oracle's requirements.
4. Wait for the installer to complete. For this Free edition, setup automatically creates CDB `FREE`, PDB `FREEPDB1`, and the listener with default settings. Note the connection details shown on the completion screen.
5. Open `services.msc` and check the **`OracleServiceFREE`** service. The listener service is named after the Oracle Home, e.g., `OracleOraDB26Home<n>TNSListener`; the number `<n>` varies by machine.
6. Use SQL Developer or SQL*Plus to connect to `localhost:1521/FREEPDB1` as `SYSTEM`, then switch to a dedicated practice account in section 7.

If the database is stopped, open `services.msc` to start `OracleServiceFREE` and the corresponding listener. If the database starts but the PDB is not yet open, use the `ALTER PLUGGABLE DATABASE` command in section 8.

**Note:** The **Free** installer creates the default database automatically; do not run DBCA to create an extra database just because you see the DBCA tool on the system.

## 5. Method C — Installing 26ai Free Directly on Oracle Linux

This example is for **Oracle Linux 9 x86-64** using Bash and `dnf`. Other Oracle Linux/RHEL versions, operating systems, and architectures must use the exact RPM/preinstall matching their version guide.

### 5.1. Installing the software

On Oracle Linux with the appropriate RPM repository enabled:

```bash
sudo dnf install -y oracle-ai-database-preinstall-26ai
```

Download the **Oracle AI Database Free 26ai RPM for Oracle Linux 9 x86-64** from Oracle, place it in the current directory, and install:

```bash
sudo dnf install -y ./oracle-ai-database-free-26ai-*.el9.x86_64.rpm
```

The exact version string in the filename changes with each release. Before installing, confirm only **one matching RPM** fits the pattern above. On RHEL, installing the preinstall package may differ from Oracle Linux.

### 5.2. Initializing the database after installing the RPM

Review the initialization configuration first:

```bash
sudo cat /etc/sysconfig/oracle-free-26ai.conf
```

Run the **configuration script for the exact version**:

```bash
sudo /etc/init.d/oracle-free-26ai configure
```

The script prompts for the admin password and creates:

- CDB / `SID`: `FREE`.
- PDB: `FREEPDB1`.
- Listener: defaults to port `1521`.

Service checks and operations:

```bash
sudo /etc/init.d/oracle-free-26ai status
sudo systemctl start oracle-free-26ai
sudo systemctl enable oracle-free-26ai
```

`start` starts the service; `enable` configures it to start at OS boot. To intentionally stop it, run `sudo systemctl stop oracle-free-26ai`.

### 5.3. Setting up the environment and connecting locally as admin

Switch to the `oracle` OS user, then set Oracle Home:

```bash
sudo su - oracle
export ORACLE_SID=FREE
export ORACLE_HOME=/opt/oracle/product/26ai/dbhomeFree
export ORAENV_ASK=NO
. "$ORACLE_HOME/bin/oraenv"
sqlplus / as sysdba
```

`sqlplus / as sysdba` relies on OS authentication on the server; it typically connects to `CDB$ROOT`. **Do not** use this syntax as a normal connection from a laptop to a database on another machine.

In SQL*Plus:

```sql
SELECT name, open_mode FROM v$pdbs;
SHOW CON_NAME;
EXIT;
```

If studying on Oracle **23ai Free**, substitute the corresponding **`23ai`** paths, RPM, and script names, e.g., `/etc/init.d/oracle-free-23ai configure`. Never mix a 23ai RPM with a 26ai script.

## 6. Method D — Oracle Database 19c/21c Enterprise or Standard with DBCA

For Oracle server editions installed via **Oracle Universal Installer (OUI)**, installing program files and creating a database can be split into two phases. DBCA is the right tool for step-by-step database creation.

1. Prepare the server according to the OS/hardware support matrix and installation permissions. Install Oracle Database software using the official installer, choosing "Install database software only" if you plan to create the database afterward.
2. Launch **Database Configuration Assistant** (e.g., run `dbca` from Oracle Home in a GUI environment) and select **Create a database**.
3. Choose **Typical** or **Advanced** configuration. For Oracle multitenant lessons, create a **CDB containing at least one PDB** if that option is available in your release/configuration.
4. Pick a global database name and `SID`, such as `ORCL`; give the PDB a clear name, such as `ORCLPDB1`. Configure datafile storage location, character set (usually `AL32UTF8` for new labs), memory, and listener appropriately.
5. Set administrative passwords, review the **Summary** page, select **Create database**, and wait for DBCA to finish. Record the `SID`, PDB name, listener port, and reported log paths.
6. Use SQL*Plus / SQL Developer to log into the **created PDB's** service, such as `localhost:1521/ORCLPDB1`, then create the exercise schema.

In DBCA, names like `ORCL` and `ORCLPDB1` are just **examples**, not fixed Oracle 19c names. Real configurations vary. Licensing and usage rights for Enterprise/Standard must match the deployment environment.

**Specifically for XE 18c/21c:** the Express Edition installer normally pre-creates `XE`/`XEPDB1`. Follow the exact XE documentation and connect via service `XEPDB1` for labs; do not assume they expose `FREEPDB1`.

## 7. Creating a Dedicated Schema for Practice

After successful installation, create a dedicated user inside the **PDB**. The example below assumes service `FREEPDB1` from 26ai/23ai Free and access from a machine with the database or Oracle client.

First log in with the `SYSTEM` admin account:

```bash
sqlplus system@//localhost:1521/FREEPDB1
```

If the client runs on another machine, replace `localhost` with the server's hostname/IP; if the host port was changed to 1522, update the port number accordingly. Enter the password at the prompt.

Verify you are in the right PDB:

```sql
SHOW CON_NAME;
```

Proceed only when the output is `FREEPDB1` (or the actual PDB assigned to you). Create the user and grant minimal privileges:

```sql
CREATE USER LAB_ORACLE
  IDENTIFIED BY "ReplaceWithStrongPassword_2026"
  DEFAULT TABLESPACE USERS
  QUOTA 100M ON USERS;

GRANT CREATE SESSION, CREATE TABLE TO LAB_ORACLE;
```

**You must replace the example password** with your own password. Run the user creation command on a PDB you control; on a class server, verify first that you have permission to create users. If the lab tablespace is not named `USERS`, select the tablespace assigned by your administrator. Never grant `DBA` or `SYSDBA` to a lab user.

Exit and log in with the newly created account:

```bash
sqlplus lab_oracle@//localhost:1521/FREEPDB1
```

Run a test set of statements:

```sql
SELECT USER AS current_user FROM dual;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;

CREATE TABLE bai_hoc (
    id       NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY,
    ten      VARCHAR2(100 CHAR) NOT NULL,
    ngay_tao DATE DEFAULT SYSDATE NOT NULL
);

INSERT INTO bai_hoc (ten) VALUES ('Oracle Database lab');
COMMIT;

SELECT id, ten, ngay_tao
FROM bai_hoc
ORDER BY id;
```

If you get back the inserted row, you have verified **PDB connection → user authentication → table creation privilege → writing and reading data**.

> `CREATE USER` creates a **schema inside an existing PDB**; it does not create a new Oracle database/CDB. This is an important distinction in a "database initialization" lesson.

## 8. Connecting with SQL Developer, SQLcl, SQL*Plus, and JDBC

A single database server can be accessed by many client tools. With a default Oracle 26ai Free initialization, parameters for **schema `LAB_ORACLE`** are:

| Attribute | Example value | Notes |
|---|---|---|
| Username | `LAB_ORACLE` | User just created in `FREEPDB1` |
| Password | Password set for `LAB_ORACLE` | Do not use the `SYS`/`SYSTEM` password |
| Hostname | `localhost` | If client is on the same host; from another machine use the actual server address |
| Port | `1521` | Or `1522` if mapped on container as in the example |
| Connection type | `Basic` in SQL Developer | Direct connection via host/port |
| Connection identifier | **Service name: `FREEPDB1`** | Do not choose SID `FREE` instead of the PDB service |
| Role | `Default` | Practice users do not use `SYSDBA` |

In **SQL Developer**, create a *New Database Connection*, fill in the fields above, click **Test**, then **Connect**. If connecting from a laptop to a server running in Docker, use the address/port **mapped on the host**.

In **SQLcl**:

```bash
sql lab_oracle@localhost:1521/FREEPDB1
```

In **SQL*Plus**:

```bash
sqlplus lab_oracle@//localhost:1521/FREEPDB1
```

In a **Java JDBC Thin** application, the service-style URL is typically:

```text
jdbc:oracle:thin:@//localhost:1521/FREEPDB1
```

Java setup example:

```java
String url = "jdbc:oracle:thin:@//localhost:1521/FREEPDB1";
String username = "LAB_ORACLE";
// Read password from secure config/environment variable; do not hard-code in source.
String password = System.getenv("ORACLE_LAB_PASSWORD");

try (java.sql.Connection conn =
         java.sql.DriverManager.getConnection(url, username, password);
     java.sql.PreparedStatement ps =
         conn.prepareStatement("SELECT COUNT(*) FROM bai_hoc");
     java.sql.ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        System.out.println("Lesson count: " + rs.getInt(1));
    }
}
```

The application needs an Oracle JDBC driver matching both your Java version and the server. If the service is `XEPDB1` or `ORCLPDB1`, update the **service name** in all connections above.

## 9. Verifying Database Status After Initialization

Log in with an appropriately privileged admin account on the server, such as `sqlplus / as sysdba` as OS user `oracle` on Linux. Inspect:

```sql
SELECT instance_name, status FROM v$instance;

SELECT name, open_mode FROM v$database;

SELECT name, open_mode FROM v$pdbs;

SHOW CON_NAME;
```

Understand the results:

- `v$instance.status` is normally `OPEN` when the instance/database is operating normally.
- `v$database.open_mode` is `READ WRITE` for an open read/write database.
- The practice PDB must have `OPEN_MODE = READ WRITE`; `PDB$SEED` is normally `READ ONLY`.
- When verifying schema/privileges, switch back to connecting as **LAB_ORACLE to the right PDB** and run `SELECT USER FROM dual;`.

If the PDB needs to be opened after a restart, from `CDB$ROOT` with `SYSDBA` privileges:

```sql
ALTER PLUGGABLE DATABASE FREEPDB1 OPEN;
ALTER PLUGGABLE DATABASE FREEPDB1 SAVE STATE;
```

Run `OPEN` only when the PDB is closed (e.g., `MOUNTED`); if the PDB is already open, no extra open is needed. `SAVE STATE` preserves the open state so the PDB opens automatically on subsequent CDB startups, on supported versions. Replace `FREEPDB1` with your actual PDB name if using a different version.

Check the listener on the server:

```bash
lsnrctl status
```

With Docker, also check `docker ps` and `docker logs oracle-free`. A container status of "running" only confirms the process is alive; it is **not enough** to prove the PDB is open and ready for connections.

## 10. Common Errors and Root-Cause Identification

| Symptom | Causes to check | Resolution path |
|---|---|---|
| Cannot connect, `ORA-12541` | Listener not running; wrong host/port; host port not mapped | Check `lsnrctl status`, `docker ps`, Oracle service, and actual port |
| `ORA-12514` | Wrong `FREEPDB1`/`XEPDB1` service, not yet registered, or PDB not open | Check `lsnrctl status`, `SELECT name, open_mode FROM v$pdbs`; open PDB if needed |
| `ORA-01017` | Wrong username/password, wrong CDB/PDB, wrong environment | Use exact service, re-enter credentials, and confirm user exists inside the PDB |
| `ORA-65096` on `CREATE USER` | Creating a local user inside `CDB$ROOT` | Connect to the PDB service before running `CREATE USER` |
| `ORA-01950` on table creation/insert | User has no quota on tablespace | Grant appropriate quota in the PDB, e.g., `ALTER USER LAB_ORACLE QUOTA 100M ON USERS` |
| `ORA-01031` | User lacks privilege for operation | Grant only the needed privilege; avoid granting `DBA` for learning |
| Docker reports `port is already allocated` | Host port 1521 is taken | Change host port, e.g., `127.0.0.1:1522:1521`; update client config |
| SQL Developer test fails while local SQL*Plus works | Different machine, network/firewall, service name, or client configured with SID | Check host address, port mapping, network rules, and **Service name** |
| Data disappears after container restart | Created container without persistent volume or connected to wrong container | Check volume mounted at `/opt/oracle/oradata` and container name before acting |

**Diagnostic principle:** Check in order: **server/container running → listener running → service registered → PDB open → username/password → schema privileges**. This ordering prevents tweaking SQL permissions when the root problem is network connectivity.

## 11. Expected Output of the Lab

By the end, the learner should be able to describe and demonstrate the following:

1. Specify **Oracle version/edition**, OS, installation method (Docker, Windows installer, Linux RPM, or DBCA), **SID/CDB/PDB** names, hostname, and port.
2. Connect via the **PDB service**, not CDB root by mistake; verify with `SHOW CON_NAME`.
3. Create `LAB_ORACLE` inside the PDB with `CREATE SESSION`, `CREATE TABLE`, and a bounded quota.
4. Create table `BAI_HOC`, insert a row, `COMMIT`, and successfully query it back.
5. Know how to start/stop the database with the appropriate tool and where to inspect logs when connections fail.

This outcome serves as the baseline environment for learning tables, keys, constraints, JOINs, transactions, indexes, the optimizer, and basic Oracle administration.

## Official Documentation to Cross-Check

- [Oracle AI Database 26ai Free — download and get started](https://www.oracle.com/database/free/get-started/)
- [Oracle AI Database 26ai Free — Linux guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/)
- [Oracle AI Database 26ai Free — Windows guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinw/)
- [Oracle AI Database Free — connecting via FREE/FREEPDB1 services](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/connecting-to-oracle-ai-database-free.html)
- [Oracle Database 19c — creating a database with DBCA](https://docs.oracle.com/en/database/oracle/oracle-database/19/admqs/installing-oracle-database-creating-database.html)
- [Oracle Database Free — container image on Oracle Container Registry](https://container-registry.oracle.com/)

Script names, Windows service names, `ORACLE_HOME` paths, and image/RPM versions depend on the **Oracle release and operating system**. When the documentation for your installed version differs from examples in this lesson, prioritize your exact version's guide.
