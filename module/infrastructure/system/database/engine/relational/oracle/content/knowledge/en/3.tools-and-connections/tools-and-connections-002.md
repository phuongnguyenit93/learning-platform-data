# Distinguishing Local Connections, Network Connections, and OS Authentication in Oracle Database

When using SQL*Plus, SQLcl, SQL Developer, or a Java application to connect to Oracle Database, we often encounter three terms: **local connection**, **network connection**, and **OS authentication**. These three concepts do not lie on the same classification axis:

- **Local vs. network** answers the question: *Which connection path does the client take to reach Oracle Database?*
- **OS authentication vs. database password** answers the question: *What credentials or evidence does Oracle use to identify and authorize the user?*

For example, on the same database server, `sqlplus / as sysdba` typically creates a **local bequeath connection** and uses **OS authentication**. Meanwhile, `sqlplus app_user@//localhost:1521/salespdb` creates an **Oracle Net connection over TCP/IP**, even though the client and server may reside on the same physical machine, and typically uses a **database account password**.

This lesson explains the connection mechanics, common syntax, associated privileges, and how to diagnose connection errors in Oracle Database, particularly when working with SQL*Plus/SQLcl and CDB/PDB environments.

## 1. Two Independent Axes: Connection Path and Authentication Method

### 1.1. Classification by Connection Path

| Type | Where the Client Runs | Communication Path | Oracle Listener | Typical Routing Info |
| --- | --- | --- | --- | --- |
| **Direct local (local bequeath)** | On the **database server** | The client process communicates with the Oracle server process on the same machine via local IPC/process spawning | **Not required** for bequeath connections | `ORACLE_SID`, Oracle Home environment |
| **Oracle Net on the same machine** | On the database server | Connects via Oracle Net, e.g. TCP to `localhost:1521` | **Usually required** | Host, port, service name, or alias |
| **Oracle Net from another machine** | On a laptop, application server, or another admin host | TCP/IP network connection or configured Oracle Net protocol | **Usually required** (listener or equivalent service endpoint) | Host/IP, port, service name, or alias |

**"Local" does not mean "network-free."** A client connecting to `localhost` over TCP still uses Oracle Net. Conversely, a **bequeath** connection usually omits host/port/service from the connect string and does not require a listener.

### 1.2. Classification by Authentication Mechanism

| Authentication Method | Authentication Evidence | Conceptual Example | Key Requirements |
| --- | --- | --- | --- |
| **Database password** | Username and password verified by Oracle | `sqlplus app_user@//dbhost:1521/salespdb` | Account can log in and has the required privileges |
| **Operating system authentication (OS authentication)** | Identity/group membership of the OS account provided by a trusted OS | `sqlplus / as sysdba` or `sqlplus /` | Must belong to the admin OS group or be a properly configured `IDENTIFIED EXTERNALLY` user |
| **Network/integrated authentication** | Configured mechanisms such as Kerberos, Windows authentication, certificates, etc. | Depends on Oracle Net and environment setup | Does not work by default merely because a network or OS user exists |

A **local bequeath** connection can use either a **database password** or **OS authentication**. An **Oracle Net** connection usually uses a database password, though it can also use integrated authentication if the environment is configured to support it. Therefore, never infer the authentication method solely from the words "local" or "network."

### 1.3. Visual Diagram

```text
Axis 1 — CONNECTION PATH

[SQL*Plus on database server]
       |
       +-- No @connect_identifier
       |      |
       |      +-- local bequeath --> [Oracle instance]
       |               (usually via ORACLE_SID)
       |
       +-- @//localhost:1521/salespdb
              |
              +-- Oracle Net/TCP --> [Listener] --> [Database service/PDB]

[SQL*Plus on another machine]
       |
       +-- @//dbhost.example.com:1521/salespdb
              |
              +-- Oracle Net/TCP --> [Listener] --> [Database service/PDB]


Axis 2 — AUTHENTICATION (applied over the appropriate connection path)

[Database password]  [OS user / OSDBA group]  [Kerberos / integrated auth]
```

Note: an environment can set a **default connect identifier** via `TWO_TASK` (Unix/Linux) or `LOCAL` (Windows), causing a SQL*Plus command **without `@...`** to still connect over Oracle Net. Thus, "no `@`" is a common indicator of local bequeath, **not absolute proof**.

## 2. Direct Local Connection: Local Bequeath

### 2.1. How It Works

On a database server, an Oracle client can connect directly to an **instance running on the same operating system**. On Unix/Linux, this is commonly called a **bequeath connection**; the Oracle client spawns or communicates with the corresponding server process without going through the standard TCP listener.

In Unix/Linux environments, selecting the target instance typically relies on:

- `ORACLE_HOME`: installation directory of the Oracle client/server software being used.
- `ORACLE_SID`: **system identifier (SID)** of the local instance to connect to.
- `PATH` and related environment variables to invoke the matching `sqlplus` binary.

Illustrative example on a Linux database server (assuming Oracle Home and executable paths are properly configured):

```bash
# Select the local instance to work with.
export ORACLE_SID=ORCL

# Connect as a database user; SQL*Plus will prompt for a password.
sqlplus app_user

# Connect using OS authentication with SYSDBA administrative privilege.
sqlplus / as sysdba
```

`sqlplus app_user` and `sqlplus / as sysdba` can use **the same local connection path** while using **different authentication methods**. Do not assume every local connection is a passwordless login.

**Conditions:** the examples above assume `TWO_TASK`/`LOCAL` is not set to redirect to an Oracle Net service. On Windows, selecting an instance, Oracle Home, and Windows services depends on the installation configuration.

### 2.2. Connecting Directly Without a Listener

With local bequeath, a TCP listener on port `1521` does not necessarily have to be running. This is useful during instance maintenance, for example when the listener is stopped or the service has not registered yet.

However, **not needing a listener does not mean the database is always accessible**: the instance must be in an appropriate state, software paths must match, the account must have privileges, and the OS must permit access. With a qualifying administrative account, `sqlplus / as sysdba` can connect even when the instance is shut down in order to start it or inspect its state, whereas a normal application user has no such privilege.

### 2.3. Local Bequeath and CDB/PDB

In a multitenant architecture, `ORACLE_SID` identifies the **instance**; it is **not a PDB name**. A local administrative connection such as `sqlplus / as sysdba` to a CDB instance typically lands in `CDB$ROOT`. To access a specific PDB, applications should connect via that PDB's **database service**.

Illustrative example after connecting with appropriate privileges:

```sql
SHOW CON_NAME;

-- Only an account granted appropriate administrative privileges can switch containers.
ALTER SESSION SET CONTAINER = SALESPDB;

SHOW CON_NAME;
```

Do not use `ORACLE_SID=SALESPDB` as a substitute for a PDB's service name: those are two distinct concepts.

## 3. Network Connection: Oracle Net

### 3.1. Host, Port, Listener, and Service

An Oracle network connection typically involves these components:

1. **Client**: SQL*Plus, SQLcl, SQL Developer, Java/JDBC application, etc.
2. **Host/IP**: server address or database service access endpoint.
3. **Port**: Oracle Listener port (commonly `1521`, though it can differ).
4. **Listener**: accepts incoming connection requests and routes them to the corresponding database service/server process.
5. **Service name**: logical name of a **database service**; commonly used to target a CDB or a specific PDB.

Example of an Oracle Net connection using **Easy Connect**:

```bash
sqlplus app_user@//dbhost.example.com:1521/salespdb.example.com
```

SQL*Plus prompts for `app_user`'s password as needed. The string `//dbhost.example.com:1521/salespdb.example.com` specifies the **host**, **port**, and **service name**. Port `1521` is a common default, not a mandatory rule.

A variant on the database server itself:

```bash
sqlplus app_user@//localhost:1521/salespdb.example.com
```

Even though it runs on the same database server, this is still an **Oracle Net/TCP connection**. The listener and service must be properly configured and registered.

### 3.2. Service Name vs. SID

This is one of the most frequent points of confusion:

| Component | Meaning | Example |
| --- | --- | --- |
| **SID** | Identifier of an **Oracle instance** | `ORCL` |
| **Service name** | Logical name clients use to connect to a database or workload; can point to a PDB, multiple instances, or service configs | `salespdb.example.com` |
| **TNS alias** | Client-side alias that maps to Oracle Net connection details | `SALES_DB` |

In RAC, one service can run across multiple instances. In a CDB, each PDB can have its own service so clients connect directly to the right container. Therefore, prefer **service name** in application connection strings; avoid casually substituting SID for service name.

### 3.3. Using `tnsnames.ora`

To avoid typing the full host/port/service on every command, the client can define an alias:

```text
SALES_DB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbhost.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = salespdb.example.com)
    )
  )
```

Then use:

```bash
sqlplus app_user@SALES_DB
```

The `tnsnames.ora` file is typically searched by the client in the directory pointed to by `TNS_ADMIN` or the Oracle Net configuration directory under Oracle Home, depending on the software used. **A TNS alias is merely a client-side configuration alias**, not a database account object and not a replacement for authentication.

The command:

```bash
tnsping SALES_DB
```

can verify how the client resolves the alias and whether the Oracle Net endpoint responds. **A successful `tnsping` does not mean database login will succeed**: it checks neither passwords, account privileges, nor the full readiness of the database service.

### 3.4. Does an Application Account Need Oracle Database Installed on a Laptop?

No. An application using **JDBC Thin** can connect over TCP/IP to Oracle Database without needing Oracle Database server or a full Oracle Client installed on the application machine. Example JDBC Thin URL using a service name:

```java
String url = "jdbc:oracle:thin:@//dbhost.example.com:1521/salespdb.example.com";
String user = "app_user";

// Illustrative example: retrieve the password from an appropriate secrets manager.
String password = System.getenv("DB_PASSWORD");

try (java.sql.Connection connection =
         java.sql.DriverManager.getConnection(url, user, password)) {
    System.out.println("Connected: " + !connection.isClosed());
}
```

This example assumes the Oracle JDBC driver is already in the dependencies and `DB_PASSWORD` is supplied securely. JDBC Thin here uses a **network connection path**; it does not automatically inherit `/ as sysdba` privileges from the host simply because an app runs on the same machine.

## 4. Operating System Authentication (OS Authentication)

### 4.1. Concept

With OS authentication, Oracle trusts identity information already verified by the operating system or an integrated authentication provider, according to configured policy. Users can connect using `/` syntax **without typing a database password** in certain cases.

There are **two distinct scenarios** to understand:

1. **Administrative login via OSDBA/OSOPER groups**: such as `sqlplus / as sysdba`. SYSDBA/SYSOPER privilege comes from membership in an Oracle-configured OS group and is evaluated at connection time.
2. **Regular user login authenticated externally**: such as `sqlplus /` for a properly mapped `IDENTIFIED EXTERNALLY` user with `CREATE SESSION` privilege.

These two scenarios are not equivalent: an OSDBA group member receives very powerful administrative privileges; a regular `IDENTIFIED EXTERNALLY` account only has the database privileges explicitly granted to it.

### 4.2. `sqlplus / as sysdba`: OS Authentication for Administration

On a Linux/Unix database server, an OS user belonging to the configured **OSDBA** group (commonly `dba`, though the actual name can vary) can run:

```bash
sqlplus / as sysdba
```

Meaning:

- `/`: provides no standard database username/password; requests external authentication.
- `AS SYSDBA`: requests connection with **SYSDBA administrative privilege**.
- The OS identity/group membership of the client process is verified by Oracle according to configuration; if authorized, an administrative session is established.
- On a `SYSDBA` administrative connection, `SHOW USER` typically displays `SYS`, **not necessarily the OS login name**.

Example in SQL*Plus:

```sql
SHOW USER;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user
FROM   dual;
```

On Windows, OS administrative authentication usually involves groups like `ORA_DBA` or an Oracle Home-specific OSDBA group and configured Windows authentication mechanisms. Do not assume Linux and Windows group names are identical.

**SYSDBA privilege is not the regular DBA role.** A database user granted the `DBA` role is not thereby automatically allowed to run `sqlplus / as sysdba`; conversely, an OS user in the OSDBA group can connect as SYSDBA without even knowing `SYS`'s database password.

### 4.3. `sqlplus /`: OS Authentication for Regular Users

The following command does **not** include `AS SYSDBA`:

```bash
sqlplus /
```

In an environment configured for OS authentication of regular users, Oracle maps the OS login to a **database user defined as `IDENTIFIED EXTERNALLY`**.

A *conceptual* example on a system with `OS_AUTHENT_PREFIX='OPS$'` and OS login `labuser`:

```sql
-- Executed by an administrative account, in the appropriate database/container.
CREATE USER "OPS$LABUSER" IDENTIFIED EXTERNALLY;
GRANT CREATE SESSION TO "OPS$LABUSER";
```

Then on the server, under that matching OS login and supported configuration:

```bash
sqlplus /
```

Oracle can recognize the database user `OPS$LABUSER` according to the configured mapping rules. This example **does not apply verbatim** across every OS or every CDB/PDB: prefixes, username formatting, current container, and OS authentication settings all affect the outcome. In particular, local bequeath connections to a CDB usually bind to the root container, so you cannot assume `sqlplus /` will connect directly to a local PDB user.

Key takeaway: logging in with `/` **does not grant privileges automatically**. The user must exist in the right place, map properly, and hold `CREATE SESSION` along with the required business privileges.

### 4.4. Can OS Authentication Work Remotely?

Make this distinction carefully:

- **Local bequeath OS authentication** trusts the identity of a process running directly on the database server and its local OS group memberships. This is the most common case when practicing `/ as sysdba`.
- **Integrated network authentication** such as Kerberos, Oracle Net-supported Windows authentication, or certificate-based authentication can enable database-passwordless login over the network in a different way, provided both server and client are configured accordingly.
- **You cannot assume an OS user on a laptop will automatically be trusted by the database server** just by running `sqlplus /@SALES_DB`. That command does not make the database blindly accept an OS account from an arbitrary client machine.

The legacy parameter `REMOTE_OS_AUTHENT` once existed in Oracle Database, but **must not be enabled just to allow remote OS login**; legacy network OS-identity trust carries spoofing risks and has been deprecated/discouraged by Oracle. For centralized or passwordless authentication, choose a supported, properly configured network authentication mechanism.

### 4.5. Remote SYSDBA vs. Local SYSDBA

Example administrative connection over Oracle Net:

```bash
sqlplus 'sys@//dbhost.example.com:1521/orcl.example.com as sysdba'
```

SQL*Plus prompts for the appropriate password. For password-based remote administrative connections, the database typically requires a **password file** and SYSDBA privilege granted to the relevant account; network, service, and security policies still apply.

Comparison:

| | Local `/ as sysdba` | Remote `sys@... as sysdba` |
| --- | --- | --- |
| Common connection path | Bequeath | Oracle Net |
| Common auth credential | OSDBA group on database server | Admin password via password file |
| Is a TCP Listener required? | No for bequeath path | Usually yes |
| Can it administer the instance? | Yes, if OS user has privileges | Yes, if configuration and privileges allow |

Never pass the `SYS` password directly in a command that could be saved in shell history or process listings. In production environments, use protected administrative channels, least privilege, and proper credential management.

## 5. Reading Common Commands Accurately

The examples below assume the SQL*Plus/SQLcl client has an appropriate environment; the database user exists, is unlocked, and the listener/service are configured where required.

| Command | Default Connection Path | Typical Authentication | Common Misconception |
| --- | --- | --- | --- |
| `sqlplus app_user` | Bequeath on database server, if no default connect identifier is set | Database password | Omitting `@` does not mean OS authentication |
| `sqlplus /` | Bequeath on database server, per configuration | OS external user | Not equivalent to `SYSDBA` |
| `sqlplus / as sysdba` | Bequeath on database server, per configuration | OSDBA / OS admin privilege | Needs no DB password, but requires OS privilege |
| `sqlplus app_user@//localhost:1521/salespdb` | Oracle Net to loopback | Database password | Still goes through TCP/listener despite same host |
| `sqlplus app_user@//dbhost:1521/salespdb` | Oracle Net from client host | Database password | Service name is not the same as SID |
| `sqlplus app_user@SALES_DB` | Via alias in Oracle Net config | Database password | `SALES_DB` is a client-side alias |
| `sqlplus 'sys@//dbhost:1521/orcl as sysdba'` | Oracle Net | SYSDBA via password file in typical setups | SYSDBA privilege differs from DBA role |

Note: if `TWO_TASK`/`LOCAL` is set, SQL*Plus may route over Oracle Net even when the command contains no `@`; always check the actual environment configuration when analyzing a connection.

### 5.1. Why `/` Does Not Mean "Security Disabled"

In `sqlplus / as sysdba`, `/` means **delegating authentication** to an external mechanism, most commonly the OS user/group on the database server. Oracle still checks identity and privileges. If any OS login can run that command successfully, the issue lies in over-broad OSDBA group grants or security misconfiguration—not that the syntax itself bypasses authentication.

### 5.2. Why `localhost` Is Not Equivalent to Local Bequeath

`localhost` is simply the loopback address of **the machine running the client**. On your laptop, `localhost:1521` points to your laptop, **not the database server in the data center**. On the database server, `localhost:1521` points to that server's listener, yet still uses TCP. Local bequeath selects a local instance via Oracle environment variables without using a TCP address at all.

## 6. Hands-On Verification Through Three Tests

### Test A — Directly on the Database Server

Assume you are in a shell as an OS user belonging to OSDBA, on a server with SID `ORCL`:

```bash
export ORACLE_SID=ORCL
sqlplus / as sysdba
```

In SQL*Plus:

```sql
SHOW USER;
SHOW CON_NAME;

SELECT instance_name, host_name, status
FROM   v$instance;
```

What to observe: the client runs on the database server; no host/port/service is needed; the OS user holds SYSDBA privileges so it logs in and can query instance views. `SHOW CON_NAME` distinguishes the CDB root from a PDB.

### Test B — From the Same Server, via Oracle Net

On the same database server:

```bash
sqlplus app_user@//localhost:1521/salespdb.example.com
```

The `@//localhost:1521/...` syntax forces the client through Oracle Net/TCP. To succeed, the listener must accept connections, the service must exist/be registered, and the user must have access to the target container/database. You can check the listener right on the database server:

```bash
lsnrctl status
```

This reflects the listener being inspected; it **does not authenticate `app_user` for you** and does not guarantee every PDB is ready for application traffic.

### Test C — From Another Machine

From a laptop or application server with SQL*Plus/SQLcl installed:

```bash
sqlplus app_user@//dbhost.example.com:1521/salespdb.example.com
```

Here, there must be network connectivity from the client to the database endpoint, the correct service name, a valid account, and configurations permitting access. You do **not** need to set `ORACLE_SID` to the server's SID to use Easy Connect. A client cannot make a local bequeath connection to an instance on another host simply by setting `ORACLE_SID`.

### 6.1. Inspecting the Logged-In Session Identity

After connecting, run this read-only query:

```sql
SELECT sys_context('USERENV', 'SESSION_USER')           AS database_user,
       sys_context('USERENV', 'AUTHENTICATION_METHOD') AS auth_method,
       sys_context('USERENV', 'HOST')                  AS client_host,
       sys_context('USERENV', 'SERVICE_NAME')          AS service_name,
       sys_context('USERENV', 'CON_NAME')              AS container_name
FROM   dual;
```

These fields help identify the database user, the authentication method reported by Oracle, the client host, service, and container. Actual values depend on release and configuration; some fields may be empty or reflect session defaults, so **never rely on a single field alone to prove definitively whether a connection is bequeath or TCP**. For deeper verification, combine client configuration, listener logs, and dynamic performance views you are authorized to read.

## 7. Diagnosing Issues at the Right Layer

When a connection fails, determine whether the error belongs to **routing/connectivity**, **authentication**, **privileges**, or **database state**.

| Common Symptom | Layer to Check | Remediation Direction |
| --- | --- | --- |
| `ORA-12154: TNS:could not resolve the connect identifier specified` | Alias / connect-string resolution | Check alias, `tnsnames.ora`, `TNS_ADMIN`, Easy Connect syntax, and naming methods |
| `ORA-12541: TNS:no listener` | Unresponsive Oracle Net endpoint | Check hostname, port, listener status, and network/firewall |
| `ORA-12514: TNS:listener does not currently know of service requested` | Listener does not recognize requested service | Check service name, PDB/database state, and service registration with the listener |
| `ORA-01017: invalid username/password; logon denied` | Account authentication | Check username/password, target container, login syntax, and configured authentication method |
| `ORA-01031: insufficient privileges` | Insufficient privileges | If using `AS SYSDBA`, check OSDBA/password file; for regular users, verify required grants |
| `ORA-01034: ORACLE not available` or related local instance error | Local instance / environment | Check `ORACLE_SID`, Oracle Home, instance status, and OS permissions |
| `ORA-28000: the account is locked` | Database account policy | Contact the DBA to check status/unlock per procedure; do not bypass policy |

### 7.1. A Practical Troubleshooting Sequence

**If local `/ as sysdba` fails:**

1. Confirm you are on the **database server** and logged in as the intended OS user.
2. Check `ORACLE_SID`, Oracle Home, and which client binary is being invoked.
3. Check whether `TWO_TASK`/`LOCAL` is inadvertently redirecting the connection over the network.
4. Check whether the OS user belongs to the appropriate OSDBA group and whether OS authentication is properly configured.
5. Check instance status, OS services, and relevant logs.

**If `app_user@//host:port/service` fails:**

1. Verify network reachability to the target host and port.
2. Confirm the listener and service name using server-side info.
3. Use the PDB's proper service name; avoid confusing SID with service name.
4. Check username/password, account lock status, and `CREATE SESSION` privilege in the target container.
5. If the environment uses TLS, wallets, Kerberos, or custom network policies, cross-check client and server configurations.

Do not try to fix `ORA-12514` by changing passwords, and do not try to fix `ORA-01017` by opening listener ports when network traffic is already reaching the database. Each error code points to a prioritized set of causes rather than replacing full log inspection.

## 8. Access Privileges and Safe Practices

**Restrict OSDBA membership.** Any account allowed to log in via `/ as sysdba` can perform sensitive administrative operations, even without knowing `SYS`'s password. Protect OS groups, `sudo`/server login privileges, and corresponding audit trails.

**Use least-privilege application users.** Applications should use dedicated users/schemas on the appropriate database service/PDB; never run day-to-day business traffic as `SYS` or `SYSDBA`.

**Never embed passwords in shell commands or source code.** Syntax like `sqlplus user/password@service` can expose secrets in terminal history, scripts, or process-monitoring tools. For applications, use a secrets store or properly managed authentication mechanism.

**Secure network connections.** An Oracle Net connection over TCP is not automatically encrypted end-to-end according to every policy you might expect. When data-in-transit confidentiality is required, configure and verify Oracle Net encryption or TLS for your supported release and infrastructure.

**Do not enable legacy remote OS trust.** Never set `REMOTE_OS_AUTHENT=TRUE` just to make `/@service` work. For single sign-on, identity federation, or certificate login, use an Oracle-supported network authentication solution with explicit client/server configuration and access controls.

**Do not equate "can connect" with "allowed to do anything."** Passing the connection step is only the beginning. After authentication, Oracle checks system privileges, object privileges, roles, policies, and the current container.

## 9. Misconceptions to Avoid

**Misconception 1: "Running SQL*Plus on the database server means OS authentication."**  
False. `sqlplus app_user` (with no `@` and no redirect) can connect via local bequeath while still requiring a database password.

**Misconception 2: "Using `localhost` is a local connection that needs no listener."**  
False. `@//localhost:1521/service` requires Oracle Net/TCP and a matching listener/service; local bequeath is what bypasses the TCP listener.

**Misconception 3: "Having a Linux user named `oracle` means that user is `SYS` by default."**  
False. When an OS user holds OSDBA privileges and connects `/ as sysdba`, Oracle grants an administrative session with SYSDBA privilege, typically under the database identity `SYS`. That is a privilege mechanism, not simple username mapping.

**Misconception 4: "Changing `ORACLE_SID` lets you connect directly to a PDB."**  
False. `ORACLE_SID` selects an instance. A PDB is normally selected via a service name, or via an authorized container-switch operation inside an administrative session.

**Misconception 5: "`sqlplus /@SALES_DB` will automatically use my Windows/Linux account on the server."**  
False in default configurations. Integrated network authentication requires an explicitly configured mechanism and trust policy on both client and server.

**Misconception 6: "Logging in as `SYSDBA` proves the app user can also log in."**  
False. SYSDBA uses special privilege and authentication paths; applications must verify logins using the actual application database user, service/PDB, and granted privileges.

## 10. Self-Check Exercises

1. On an Oracle server, both `sqlplus / as sysdba` and `sqlplus app_user` omit `@...`. How are they similar, and how do they differ?
2. A developer sits on a laptop and runs `sqlplus app_user@//localhost:1521/SALES`. Will this command attempt to connect to the database server in the data center or to the laptop?
3. A database server's listener on port `1521` is stopped. Which connection method can a DBA in the OSDBA group try to inspect the local instance?
4. On the same database server, why might `sqlplus app_user@//localhost:1521/salespdb` fail with `ORA-12514` while `sqlplus / as sysdba` still succeeds?
5. A client-machine OS user wants to log in over the network without typing a database password. Is simply running `sqlplus /@SALES_DB` enough? What else must be considered?
6. A Java application uses the URL `jdbc:oracle:thin:@//dbhost:1521/salespdb`. Which connection path does it use? Does it automatically inherit SYSDBA privileges from the OS user running the application?

**Answer Hints:**

1. Both can use local bequeath (assuming no default connect identifier is set). The first uses OS authentication with SYSDBA privilege; the second typically uses database-user password authentication.
2. `localhost` refers to the laptop itself. You must use the database server's address/hostname or appropriate endpoint.
3. Try `sqlplus / as sysdba` from the database server itself, after verifying the proper Oracle environment and OSDBA membership.
4. The network command requires the listener to recognize the service; the bequeath command does not rely on the TCP listener and connects by instance.
5. No. You must configure a supported integrated network authentication mechanism, trust relationships, and corresponding identity/privilege mappings.
6. JDBC Thin goes over Oracle Net/TCP in this example. It does not automatically inherit SYSDBA privileges from the OS account; database privileges depend on the authentication method and actual grants.

## 11. Oracle Reference Documentation

- [Oracle Database Net Services Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/): Oracle Net, naming methods, listener, services, and connection management.
- [Oracle Database Net Services Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/): network files/parameters, protocols, and connection configuration.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): external authentication, SYSDBA, password files, and authentication mechanisms.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): instances, administrative environments, multitenant, and database management.
- [SQL*Plus User's Guide and Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqpug/): login syntax and SQL*Plus commands.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): initialization parameters such as `OS_AUTHENT_PREFIX`, `REMOTE_OS_AUTHENT`, and connection monitoring views.

When describing an Oracle session, always specify **where the client is running**, **whether the connection path is bequeath or Oracle Net**, **which service/SID selects the database**, **the authentication mechanism**, and **the user's privileges after login**. Recording these details makes connection behavior clear and prevents confusing OS privileges with database privileges.
