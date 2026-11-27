# Configuring `ORACLE_SID`, `PATH`, and `TNS_ADMIN` in an Oracle Practice Environment

When practicing Oracle Database, a single machine may hold multiple Oracle Homes, multiple database instances, or multiple client tools. The three environment variables `ORACLE_SID`, `PATH`, and `TNS_ADMIN` specify **which local instance to work with**, **which Oracle executable will run**, and **which directory holds Oracle Net network configuration**. Setting these variables properly makes SQL*Plus behave consistently, yet each variable has a distinct role and they do not substitute for one another.

After this lesson, you will be able to:

- Distinguish **SID**, **service name**, **Oracle Home**, and **TNS alias**, especially in CDB/PDB architecture.
- Set and verify all three variables on Linux, Windows Command Prompt, and PowerShell.
- Create `tnsnames.ora`, connect via an alias or Easy Connect, and pinpoint whether an error lies in executable paths, name resolution, the listener, or the database.
- Pick the right configuration when using **Oracle Database Server** on a practice machine versus **Oracle Instant Client** on a client-only machine.

> **Example context:** A practice machine runs Oracle AI Database Free with instance `FREE`, PDB `FREEPDB1`, and a TCP listener on port `1521`. These are defaults for the current Free release; if using Oracle XE, Oracle 19c, or a custom database, use your **system's actual SID, service name, and paths**. Paths in this lesson are illustrative only.

## 1. Understanding the Three Environment Variables Correctly

| Variable | What is it for? | Directly affects | Not used to |
| --- | --- | --- | --- |
| `ORACLE_SID` | Selects the **database instance name on the local machine** | Local connections like `sqlplus / as sysdba` when Oracle Database Server and OSDBA privileges exist | Select a PDB or route TCP connections to a remote host |
| `PATH` | Lists directories where the OS searches for executables | Commands like `sqlplus`, `lsnrctl`, `tnsping` (if installed), and on Windows, DLL lookup as well | Choose a database or define a connection alias |
| `TNS_ADMIN` | Specifies the **directory** where Oracle Net looks for config files like `tnsnames.ora` and `sqlnet.ora` | Alias connections like `user@ALIAS_NAME` and other Oracle Net settings | Point directly to the `tnsnames.ora` file or automatically start a listener |

A closely related variable is `ORACLE_HOME`: the directory containing a **full Oracle Database Home** installation (housing `bin/sqlplus`, libraries, admin tools, etc.). On a Database Server machine, `ORACLE_HOME` and `ORACLE_SID` must correspond to the same environment. With **Instant Client**, you normally **do not need `ORACLE_HOME`**, and network clients **do not need `ORACLE_SID`**.

### 1.1. SID is not service name

Oracle uses multiple names across different scopes:

| Concept | Example | Meaning |
| --- | --- | --- |
| Instance SID | `FREE` | Name of the Oracle instance running on the server; local connections use this name |
| CDB | `FREE` | Container database holding the root and PDBs |
| PDB | `FREEPDB1` | Pluggable database where practice schemas and tables usually reside |
| Service name | `FREEPDB1` | Service advertised by the listener for clients connecting to the PDB |
| Net service name / TNS alias | `FREE_LAB` | Alias defined by the **client** inside `tnsnames.ora` |

For example, when practicing directly on the server:

~~~bash
export ORACLE_SID=FREE
sqlplus / as sysdba
~~~

This command relies on the **local** instance and OS authentication. Once logged in, an administrative session normally starts in `CDB$ROOT`. Setting `ORACLE_SID=FREEPDB1` to "select the PDB" is wrong: `FREEPDB1` is the PDB/service name in this example, not the SID of a separate instance.

Conversely:

~~~bash
sqlplus lab_user@//127.0.0.1:1521/FREEPDB1
~~~

goes through the **Oracle Net listener** to locate service `FREEPDB1`; it does not pick its target from the shell's `ORACLE_SID`. SQL*Plus will prompt for `lab_user`'s password. Replace `127.0.0.1` with the server hostname/IP if running the client from another machine.

### 1.2. Two connection flows to visualize

~~~text
LOCAL CONNECTION (machine with Database Server)
Shell → PATH finds sqlplus → ORACLE_HOME + ORACLE_SID
      → local Oracle instance (requires appropriate auth privileges)

NETWORK CONNECTION (server or client machine)
Shell → PATH finds sqlplus → connect string
      → TNS_ADMIN/tnsnames.ora (if using an alias)
      → host:port → listener → SERVICE_NAME → CDB/PDB
~~~

**The listener is not needed for local OS-authenticated connections** (`sqlplus / as sysdba`), but it is required for TCP connections such as `user@//host:1521/service`. Setting environment variables does not mean the database or listener is already running.

## 2. Preparing Before Configuration

Identify the environment you are practicing in:

1. **Database server machine:** Has an Oracle Database Home and a local running instance. You need the actual SID, actual Oracle Home, and an OS account allowed to administer it (typically `oracle` on Linux).
2. **Client machine:** Has SQL*Plus / Instant Client while the database runs on another machine. You need `host`, `port`, `service name`, and database credentials. You do not need to guess or set the server's SID.
3. **Container / VM environment:** Distinguish the shell on the host from the shell **inside** the container/VM. Environment variables set on the host do not automatically appear in processes inside the other environment.

If you do not know the values yet, check the installation config or ask the administrator. **Never copy example paths verbatim** because Oracle Home varies by version, OS, and installation method.

## 3. Configuration on Linux

The commands below target `bash` or compatible shells. `export` sets variables for the current shell and child processes launched from it.

### 3.1. Machine with Oracle Database Server

Log in as the proper OS account managing the database (the account name may differ from `oracle`):

~~~bash
sudo -iu oracle
~~~

Set up the practice session, **replacing `ORACLE_HOME` with where Oracle is actually installed**:

~~~bash
export ORACLE_SID=FREE
export ORACLE_HOME=/opt/oracle/product/26ai/dbhomeFree
export PATH="$ORACLE_HOME/bin:$PATH"

# Set TNS_ADMIN only when pointing to a dedicated Oracle Net config directory.
export TNS_ADMIN="$HOME/oracle-net"
mkdir -p "$TNS_ADMIN"
~~~

Here:

- `ORACLE_SID=FREE` selects the local instance used for local connections.
- `ORACLE_HOME/bin` is placed **before** the remaining `PATH` entries so the shell prioritizes tools from this Oracle Home; this is especially important if multiple Oracle installations exist on the machine.
- `TNS_ADMIN` is a **directory**. Later you will place `$TNS_ADMIN/tnsnames.ora` inside it. Merely creating the directory does not create connection aliases.

Verify the shell state:

~~~bash
printf 'SID=%s\nHOME=%s\nTNS_ADMIN=%s\n' \
  "$ORACLE_SID" "$ORACLE_HOME" "$TNS_ADMIN"
command -v sqlplus
sqlplus -v
~~~

`command -v sqlplus` should resolve to the intended executable, such as `/opt/oracle/product/26ai/dbhomeFree/bin/sqlplus`. `sqlplus -v` only confirms the client executable runs; it **does not verify that the database is running**.

If your OS user belongs to a group granted SYSDBA privileges, test a local connection:

~~~bash
sqlplus / as sysdba
~~~

At the `SQL>` prompt:

~~~sql
SELECT instance_name, host_name, status
FROM v$instance;

SHOW CON_NAME;
EXIT;
~~~

The expected instance name in this example is `FREE`. `SHOW CON_NAME` shows the current session's container, usually `CDB$ROOT` for an initial local SYSDBA connection.

> Only use `SYSDBA` for administrative tasks. When creating tables, running queries, and practicing SQL, connect with an application account in the PDB; do not use `SYS` as an exercise account.

### 3.2. Using `oraenv` to switch between Oracle Homes

On installations with a valid `oraenv` script and `oratab` configuration file, running this script updates `ORACLE_HOME`, `ORACLE_SID`, and `PATH` together:

~~~bash
export ORACLE_SID=FREE
export ORAENV_ASK=NO
. /usr/local/bin/oraenv
unset ORAENV_ASK

command -v sqlplus
printf '%s\n' "$ORACLE_HOME"
~~~

The dot and space in `. /usr/local/bin/oraenv` **source the script into the current shell**. The path to `oraenv` may differ across machines; do not run the command if that file does not exist. `oraenv` reads installation config such as `/etc/oratab` and has no knowledge of your custom `TNS_ADMIN` folder. If you need custom aliases, set `TNS_ADMIN` after running `oraenv`.

### 3.3. Machine with only Oracle Instant Client installed

Instant Client does not manage a local instance; it uses `PATH` to locate `sqlplus`, `TNS_ADMIN` to locate aliases, and a connect string to choose the service. For example, when the Instant Client SQL*Plus package is installed:

~~~bash
# Replace with your actual Instant Client directory.
export IC_DIR=/opt/oracle/instantclient_23_8
export PATH="$IC_DIR:$PATH"
export TNS_ADMIN="$HOME/oracle-net"

command -v sqlplus
sqlplus -v
~~~

If Instant Client libraries are not yet registered with the Linux dynamic linker, you may need to configure system `ldconfig` or `LD_LIBRARY_PATH` per the installation guide. Adding to `PATH` alone will not fix missing shared library errors. **Do not point `ORACLE_HOME` at an Instant Client directory as if it were a full Database Home**; it is unnecessary for normal Oracle Net connections and can cause confusion.

### 3.4. Persisting settings on Linux

On a lab machine consistently using one Oracle Home, you can add the appropriate `export` lines to `~/.bashrc` for interactive Bash shells; then open a new terminal or run:

~~~bash
source ~/.bashrc
~~~

For login shells, verify whether `~/.bash_profile` or `~/.profile` sources `~/.bashrc`. If you frequently switch among multiple SIDs/Homes, prefer running `oraenv` per session rather than hard-coding one set of values for every session.

Variables set in a shell **do not automatically apply to systemd services, already-open IDEs, processes of other users, or other containers**. You must configure them in the launch environment of the target process itself.

## 4. Configuration on Windows

Windows has two common shells with different syntax. The commands below affect **only the current terminal window and its child processes**. Oracle Home paths are examples and must be adjusted to match your installation.

### 4.1. Command Prompt (`cmd.exe`)

~~~bat
set "ORACLE_SID=FREE"
set "ORACLE_HOME=C:\app\oracle\product\26ai\dbhomeFree"
set "PATH=%ORACLE_HOME%\bin;%PATH%"
set "TNS_ADMIN=C:\oracle\net-admin"

echo %ORACLE_SID%
echo %TNS_ADMIN%
where sqlplus
sqlplus -v
~~~

Create the config directory (if it does not exist yet):

~~~bat
if not exist "C:\oracle\net-admin" mkdir "C:\oracle\net-admin"
~~~

The `set "NAME=value"` syntax avoids accidentally adding trailing spaces to values. Windows separates directories in `PATH` with semicolons `;`, whereas Linux uses colons `:`.

### 4.2. PowerShell

~~~powershell
$env:ORACLE_SID = 'FREE'
$env:ORACLE_HOME = 'C:\app\oracle\product\26ai\dbhomeFree'
$env:Path = "$($env:ORACLE_HOME)\bin;$env:Path"
$env:TNS_ADMIN = 'C:\oracle\net-admin'

New-Item -ItemType Directory -Force -Path $env:TNS_ADMIN
$env:ORACLE_SID
$env:TNS_ADMIN
where.exe sqlplus
sqlplus -v
~~~

If only **Instant Client on Windows** is installed, add the folder containing `sqlplus.exe` and Instant Client DLLs to `Path`; skip the `ORACLE_HOME` and `ORACLE_SID` steps because the target database is specified in the Oracle Net connect string. Never mistakenly use Linux's `:` PATH separator on Windows.

### 4.3. Persisting environment variables after closing the terminal

Open Windows **System Properties → Advanced → Environment Variables**, and configure variables at the appropriate User or System scope:

- `ORACLE_SID`: only needed when working with a local instance and when an application genuinely requires SID.
- `Path`: add the `bin` folder of the Oracle Home **or** the active Instant Client folder; watch ordering if multiple client packages exist.
- `TNS_ADMIN`: enter the **directory path**, not `...\tnsnames.ora`.

After saving, **open a new terminal/application** to pick up the updated values. If the system has multiple Oracle Homes, check `where.exe sqlplus` because an earlier entry in `Path` might not be the version you intend to use. Avoid running `setx PATH ...` casually due to the risk of truncating a long PATH or losing/altering existing entries. On Windows machines with Database Server, Oracle may also store Home settings in the Registry; verify the actual executable path being run rather than assuming from a single variable.

## 5. Configuring `TNS_ADMIN` and `tnsnames.ora`

### 5.1. Directory where Oracle Net searches for configuration

Example:

~~~text
Linux:   TNS_ADMIN=/home/oracle/oracle-net
         /home/oracle/oracle-net/tnsnames.ora

Windows: TNS_ADMIN=C:\oracle\net-admin
         C:\oracle\net-admin\tnsnames.ora
~~~

`TNS_ADMIN` must point to the **parent directory** containing the file. When this variable is unset, Oracle Net searches default locations depending on installation type and platform, such as `ORACLE_HOME/network/admin` or the Oracle Base Home path for a read-only Oracle Home; Instant Client also has its own default search path. Setting `TNS_ADMIN` lets you explicitly point to the exact configuration set for your lab.

In addition to `tnsnames.ora`, this directory may hold `sqlnet.ora` and other Oracle Net files. Using `TNS_ADMIN` on a client does not mean the listener is running with that new configuration; the listener is a **server-side** process with its own launch environment.

### 5.2. Creating the `FREE_LAB` alias

Create a plain-text file named exactly `tnsnames.ora` inside the `TNS_ADMIN` directory:

~~~text
FREE_LAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 127.0.0.1)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = FREEPDB1)
    )
  )
~~~

Explanation:

| Component | Role |
| --- | --- |
| `FREE_LAB` | Custom alias chosen by you, used in `sqlplus user@FREE_LAB` |
| `HOST` | Address of the **Oracle server**; `127.0.0.1` is valid only when client and listener share the same host/network context |
| `PORT` | Listener port, e.g., `1521`; not necessarily always the default port |
| `SERVICE_NAME` | Target service known to the listener; in this example `FREEPDB1` routes to the practice PDB |

**Example from another client machine:** change `HOST = 127.0.0.1` to the reachable hostname/IP of the Oracle server (for example `db-server.example.com`). Inside Docker, `localhost` inside a container refers only to **that container itself**, not automatically to the database container or the host; use the hostname/service matching the Docker network and actual port.

If a custom `sqlnet.ora` specifies `NAMES.DIRECTORY_PATH`, make sure `TNSNAMES` is not omitted when you want to use aliases. An example setting is:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
~~~

You do not need to create `sqlnet.ora` just to run basic examples if default name resolution already works.

### 5.3. Connecting via alias or Easy Connect

Once you have a database account for the exercise:

~~~bash
# Using the alias defined in tnsnames.ora:
sqlplus lab_user@FREE_LAB

# Direct connection without an alias:
sqlplus lab_user@//127.0.0.1:1521/FREEPDB1
~~~

Both commands prompt for `lab_user`'s password. With Easy Connect in this example, `TNS_ADMIN` is not needed to specify `host:port/service`; however, other Oracle Net settings may still depend on client configuration.

At `SQL>`, verify you are in the right container/service:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`CONTAINER_NAME` is expected to be `FREEPDB1` in this example. `SERVICE_NAME` will display the actual service name used by the database. Succeeding with `sqlplus -v` or `tnsping` alone does not prove login succeeded or that you entered the right PDB.

## 6. Layer-by-Layer Verification Workflow

When an issue occurs, check in order: **environment variables → executable → alias resolution → listener/service → authentication → PDB**. This narrows down the cause without changing multiple settings at once.

| Verification layer | Linux | Windows CMD / PowerShell | What to confirm |
| --- | --- | --- | --- |
| SID value | `echo "$ORACLE_SID"` | `echo %ORACLE_SID%` / `$env:ORACLE_SID` | SID matches the intended local instance |
| TNS_ADMIN value | `echo "$TNS_ADMIN"` | `echo %TNS_ADMIN%` / `$env:TNS_ADMIN` | Points to the **right directory** |
| SQL*Plus path | `command -v sqlplus` | `where.exe sqlplus` | Right executable and right PATH order |
| Does the client run? | `sqlplus -v` | `sqlplus -v` | No missing executable/DLL/library errors |
| TNS alias | `tnsping FREE_LAB` | `tnsping FREE_LAB` | Alias resolves and listener responds, if `tnsping` is installed |
| Actual login | `sqlplus lab_user@FREE_LAB` | `sqlplus lab_user@FREE_LAB` | Login succeeds; query confirms container |

`tnsping` **does not authenticate credentials** and **does not prove the service/PDB is ready for SQL**. Some Instant Client packages do not include `tnsping`; in that case, use `sqlplus` to test the actual connection.

On the **database server**, an administrator can inspect the listener and registered services:

~~~bash
lsnrctl status
~~~

Look for the listening port and the `Services Summary` section. If `FREEPDB1` does not appear or the PDB is not open, modifying `TNS_ADMIN` on the client will not fix the server state.

## 7. Common Errors and Fault Isolation

| Symptom | Common cause category | Checks / next steps |
| --- | --- | --- |
| `sqlplus: command not found` or `'sqlplus' is not recognized` | Wrong `PATH` or SQL*Plus not installed | Locate the folder containing `sqlplus`/`sqlplus.exe`, update PATH, and open a new shell |
| Running SQL*Plus from the wrong Oracle version | Multiple Oracle Homes / Instant Clients in PATH | Run `command -v sqlplus` / `where.exe sqlplus`; check which path takes precedence |
| Missing `libclntsh.so` / DLL error | Library loader cannot find client library | Check install directory, library dependencies, and OS loader/Path configuration |
| `ORA-12154` or `TNS-03505` | Cannot resolve net service name | Check `TNS_ADMIN` points to a directory, filename `tnsnames.ora`, alias, parentheses, and `sqlnet.ora` |
| `ORA-12541` | Cannot reach listener at chosen host/port | Check hostname, port, listener, firewall, and container port mapping |
| `ORA-12514` | Listener does not know requested service | Check `SERVICE_NAME`, service list in `lsnrctl status`, and instance/PDB state |
| `ORA-12505` | Descriptor requests a SID unknown to listener | Check `SID` in descriptor; prefer `SERVICE_NAME` for PDB connections |
| `ORA-01034` / `ORA-27101` on local connect | SID/HOME mismatch or instance not ready | Check `ORACLE_SID`, `ORACLE_HOME`, permissions, and actual instance status |
| `ORA-01031` with `/ as sysdba` | OS account lacks required admin privilege | Check OS user and OSDBA group membership; do not grant SYSDBA carelessly to mask errors |
| `ORA-01017` | Invalid credentials, or account/policy mismatch | Verify username/password, target service/PDB, and account status with the administrator |
| Terminal works but IDE/service fails to connect | Process did not inherit variables edited in terminal | Identify the IDE/service launch environment, update config there, and restart the process |

**Avoid randomly editing all three variables at once.** For example, if `sqlplus -v` runs fine but `sqlplus user@FREE_LAB` reports `ORA-12154`, inspect `TNS_ADMIN` and `tnsnames.ora` first; changing `ORACLE_SID` is normally unrelated to network alias resolution errors.

## 8. Complete End-to-End Practice Exercise

Assume Oracle Free is running on Linux and schema `LAB_USER` exists in PDB `FREEPDB1`. Execute sequentially:

**Step 1 — Select the right instance and Oracle binaries (on the database host):**

~~~bash
export ORACLE_SID=FREE
export ORACLE_HOME=/opt/oracle/product/26ai/dbhomeFree
export PATH="$ORACLE_HOME/bin:$PATH"

command -v sqlplus
sqlplus -v
~~~

**Step 2 — Point to an Oracle Net directory and create the alias file:**

~~~bash
export TNS_ADMIN="$HOME/oracle-net"
mkdir -p "$TNS_ADMIN"
cat > "$TNS_ADMIN/tnsnames.ora" <<'EOF'
FREE_LAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 127.0.0.1)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
  )
EOF
~~~

Note: writing the file in this step is intended for **a practice directory you own**. If the machine already has a `tnsnames.ora` holding active aliases, **append/edit the alias into the existing file** rather than overwriting the entire file. Adjust `HOST` if the listener is not on the same host/network context.

**Step 3 — Test from network connectivity through SQL execution:**

~~~bash
tnsping FREE_LAB
sqlplus lab_user@FREE_LAB
~~~

SQL*Plus prompts for the password. Once at `SQL>`:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name
FROM dual;

SELECT USER FROM dual;

EXIT;
~~~

Expect `CON_NAME = FREEPDB1` and `USER = LAB_USER`. If `tnsping` is absent but `sqlplus` is installed, you can still test directly with `sqlplus`.

**Step 4 — Cross-check using Easy Connect (without an alias):**

~~~bash
sqlplus lab_user@//127.0.0.1:1521/FREEPDB1
~~~

If **Easy Connect succeeds while `FREE_LAB` fails**, check `TNS_ADMIN`, the `tnsnames.ora` path, and alias syntax first. If **both fail**, check host/port, listener, service, credentials, and PDB state per the error message.

**Step 5 — Observe variable scoping:**

Open a new terminal and check `echo "$ORACLE_SID"` and `echo "$TNS_ADMIN"`. If the values are empty, that is normal behavior for variables set only in the previous session; set them again or place the needed settings in your shell startup file. Do not touch the database to fix uninherited shell variables.

## 9. Notes for Keeping Your Practice Environment Stable

- **Keep login credentials confidential.** Put only host, port, and service name in `tnsnames.ora`; never store plaintext passwords in config files or in commands saved to shell history.
- **Configure the right layer.** `ORACLE_SID` is a property for local instance connections; when a client connects over TCP, the target database is determined by the connect string and the service advertised by the listener.
- **Handle multiple Oracle versions carefully.** The shell `PATH` determines which binary runs. When switching Homes, use `oraenv` or verify that SID, Home, and executable all match.
- **Understand Java/JDBC Thin.** With a URL such as `jdbc:oracle:thin:@//db-server:1521/FREEPDB1`, Java applications typically do not need `ORACLE_SID` or `ORACLE_HOME` because connections rely on network address and service name. If using a TNS alias in JDBC, configure the driver's Oracle Net properties per its version; do not assume terminal shell variables are inherited by an IDE or Java process.
- **Diagnose errors by layer.** Wrong PATH prevents the program from launching; wrong TNS alias breaks name resolution; wrong listener/service breaks network connection; wrong credentials cause authentication errors. Each layer requires a different check.

### Self-check questions

1. Why is `ORACLE_SID=FREEPDB1` usually not the right way to connect to PDB `FREEPDB1`?
2. If `where.exe sqlplus` returns two paths, which path is used when you type `sqlplus`, and how would you change it?
3. Why is `TNS_ADMIN=C:\oracle\net-admin\tnsnames.ora` wrong?
4. Does a successful `tnsping FREE_LAB` prove that `LAB_USER` can log into the PDB?
5. If `sqlplus user@//host:1521/FREEPDB1` succeeds while `sqlplus user@FREE_LAB` reports `ORA-12154`, what should you check first?

**Guided answers:** (1) SID identifies an instance, whereas a PDB is selected via service/container; (2) the executable appearing first in PATH takes precedence; (3) `TNS_ADMIN` expects a directory path; (4) no, you must log in and query; (5) the `TNS_ADMIN` directory, `tnsnames.ora` contents, and the alias entry.

## Official References

- [Oracle SQL*Plus — Configuring SQL*Plus](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqpug/configuring-SQL-Plus.html): roles of environment variables.
- [Oracle Net Services — Local Naming Parameters in `tnsnames.ora`](https://docs.oracle.com/en/database/oracle/oracle-database/21/netrf/local-naming-parameters-in-tns-ora-file.html): file placement and Oracle Net syntax.
- [Oracle AI Database Free — Connecting to Oracle AI Database Free](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/connecting-to-oracle-ai-database-free.html): `FREE`/`FREEPDB1` services, local connections, Easy Connect, and listener.
- [Oracle Database 19c — Administering Oracle Database on Linux/UNIX](https://docs.oracle.com/en/database/oracle/oracle-database/19/unxar/administering-oracle-database.html): using `oraenv` when working with Oracle Homes.
