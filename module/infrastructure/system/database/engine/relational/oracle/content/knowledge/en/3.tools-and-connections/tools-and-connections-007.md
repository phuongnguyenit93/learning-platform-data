# Layered Connection Troubleshooting: DNS, TCP, Listener, and Database Service

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Tools and Connections  
> **Objective:** Independently diagnose why an application or SQL tool cannot connect to Oracle Database by testing each layer in order: **hostname resolution → TCP transport → Oracle Net Listener → database service/PDB → authentication and query execution**.

## 1. Why Troubleshoot Layer by Layer?

A "cannot connect to database" message can stem from several independent causes:

- The hostname fails to resolve or resolves to the wrong IP address.
- The client cannot reach the server's TCP port due to routing, VPN, firewall, or the listener not listening.
- TCP reaches the Oracle Net Listener, but the listener does not recognize the requested service.
- The listener knows the service, but the database/PDB is not ready or has no handler to serve the connection.
- Network transport and the service work, but the account, password, or login privileges are incorrect.

If you immediately check the password when the actual issue is DNS, you waste time without solving the problem. Conversely, opening a firewall port will not fix a misspelled service name.

### Oracle Connection Path Diagram

```text
Java application / SQL Developer / SQLcl / SQL*Plus
        |
        | 1. "db.lab.example" -> IP address
        v
       DNS / OS name resolver
        |
        | 2. TCP to <IP>:1521
        v
      Network / routing / firewall / NAT
        |
        | 3. Oracle Net connect request
        v
      Oracle Net Listener (typically TCP 1521)
        |
        | 4. Request service, e.g., FREEPDB1
        v
      Database instance / service registration / PDB
        |
        | 5. Authenticate LAB_ORACLE, create session
        v
      SQL executes on the selected PDB
```

**Distinguish two commonly confused concepts:**

- **Listener:** the process that receives and dispatches Oracle Net connection requests. One listener can serve multiple services.
- **Database service:** the logical name used to select the target database/PDB or group of instances providing the service. A service is not a TCP port or a hostname.

A passing test at an earlier layer **does not prove** that the next layer works. For example, a successful test on port 1521 only proves TCP connectivity; it does not confirm that the `FREEPDB1` service exists or that login succeeds.

## 2. Preparing a Clear Set of Connection Parameters

Before running commands, confirm the actual values. This lesson uses an illustrative environment:

| Parameter | Example Value | What to Understand |
|---|---|---|
| Client | Laptop running SQL Developer or a Java application | The machine initiating the connection request |
| Database host | `db.lab.example` | DNS name or IP of the **Oracle server** |
| Port | `1521` | Listener port reachable from the client; may differ across Docker/NAT |
| Protocol | `TCP` | Environments using TCPS require separate configuration and testing |
| Service name | `FREEPDB1` | Practice PDB in Oracle Database Free |
| Username | `LAB_ORACLE` | Account that **exists inside the PDB** |
| Password | Actual account password | Never include in screenshots, logs, or tickets |
| Tool | SQL*Plus, SQLcl, SQL Developer, or JDBC | Different tools may read configuration differently |

**EZConnect connection string:**

```text
//db.lab.example:1521/FREEPDB1
```

In SQL*Plus:

```bash
sqlplus -L LAB_ORACLE@//db.lab.example:1521/FREEPDB1
```

The tool will prompt for the password. The `-L` flag makes SQL*Plus attempt to log in only once and return the error, which is ideal for determining the outcome of a single test.

In JDBC Thin, a connection using a service name takes the form:

```text
jdbc:oracle:thin:@//db.lab.example:1521/FREEPDB1
```

For comparison across other environments:

| Oracle Edition or Deployment | Example PDB Service |
|---|---|
| Oracle Database Free 23ai/26ai | `FREEPDB1` |
| Oracle Database XE 18c/21c | `XEPDB1` |
| Oracle 19c with CDB/PDB created via DBCA | For example `ORCLPDB1`, depending on installation |
| Organization-managed Oracle | Service name provided by the DBA; do not guess |

**A service name does not have to match the SID or database name.** For instance, `FREE` can be the CDB/SID name while `FREEPDB1` is the service to reach the PDB. When troubleshooting a real configuration, use the parameters from that exact environment instead of example values.

### Choosing Where to Run Commands

Distinguish measurements taken **on the client** from those taken **on the server**:

- DNS and TCP commands must run from the **exact machine experiencing the connection failure**; results from another machine may not be representative due to different networks, DNS, and firewalls.
- `lsnrctl` and database administration queries typically run on the **database server** or with appropriate administrative privileges.
- The final SQL connection test must be retried from the **failing client/application**.

In Docker, the "server" may be a container: the port inside the container and the port published to the host machine are two different test endpoints.

## 3. Layer 1 — Checking DNS and Hostname Resolution

### What Question Does DNS Answer?

When an application uses the hostname `db.lab.example`, the operating system must turn that hostname into an IP address. If it cannot resolve, the client does not yet know where to open a TCP socket.

Beyond DNS, the OS may use the `hosts` file, caches, local resolvers, or VPN configuration. Therefore, distinguish between:

- **DNS lookup:** which A/AAAA records does the DNS server return?
- **OS-level resolution:** which address can a program on the client machine actually use?

### Windows PowerShell

```powershell
Resolve-DnsName db.lab.example

Resolve-DnsName db.lab.example -Type A
Resolve-DnsName db.lab.example -Type AAAA

nslookup db.lab.example
```

How to read the output:

- An `A` record gives an IPv4 address; an `AAAA` record gives an IPv6 address.
- If it returns `NXDOMAIN` or reports that the name cannot be found, first check the **hostname, DNS, VPN, and DNS zone**.
- If multiple IPs are returned, the client may try a different address than the one you test manually.
- `nslookup` and DNS lookup tools do not necessarily reflect the application's full OS resolution path, especially when the machine uses `hosts`, caches, or custom resolvers.

Inspect the machine's DNS configuration:

```powershell
Get-DnsClientServerAddress

ipconfig /all
```

### Linux

```bash
getent ahosts db.lab.example

nslookup db.lab.example

dig +short db.lab.example A
dig +short db.lab.example AAAA
```

- `getent ahosts` uses the OS-configured name-resolution mechanism, making it useful to compare against what applications see.
- `dig` and `nslookup` query the DNS service directly, helping identify current DNS records.
- `dig` may not be installed; if missing, use `getent` or install the appropriate DNS tools for your OS.

Inspect related configuration when needed:

```bash
cat /etc/resolv.conf
grep '^hosts:' /etc/nsswitch.conf
```

The `/etc/hosts` file can also affect resolution on Linux; on Windows, the typical path is `C:\Windows\System32\drivers\etc\hosts`.

### Interpreting DNS Failures

| Result | Common Meaning | Next Step |
|---|---|---|
| Name fails to resolve | Typo, VPN disconnected, no access to internal DNS, or missing record | Verify hostname with DBA and check DNS/VPN |
| DNS returns unexpected IP | Stale record, split DNS between internal network/VPN, wrong environment | Compare real server IP against DNS record; do not unilaterally edit production DNS |
| IP is right yet error persists | DNS succeeded; the problem likely lies at TCP or beyond | Proceed to section 4 |
| Both IPv4 and IPv6 exist | Client may pick a different address family than your test | Test actual connectivity over both IPv4 and IPv6 paths |

> **Do not use `ping` as sole proof for Oracle.** Ping uses ICMP; a firewall may block ICMP while TCP 1521 still works. A successful ping also does not prove the Oracle port is open.

**Testing by IP to isolate the fault:** if you know the database server's IP with certainty, you can test TCP directly to that IP. If the IP works while the hostname fails, the logical branch to investigate is DNS/hosts. However, in environments with load balancers, SCAN, TLS certificates, or multiple IPs, connecting by IP may not reflect the designed connection path; use it only as a temporary diagnostic when appropriate.

## 4. Layer 2 — Checking TCP Transport to Host and Port

Correct DNS does not guarantee TCP reachability. The TCP layer answers: **can the client establish a connection to host:port?**

### Windows PowerShell

From the machine running SQL Developer/JDBC:

```powershell
Test-NetConnection -ComputerName db.lab.example -Port 1521
```

You can request detailed output:

```powershell
Test-NetConnection db.lab.example -Port 1521 -InformationLevel Detailed
```

Check the `TcpTestSucceeded` line:

- `True`: the TCP handshake to the chosen address/port succeeded. A process is accepting connections, though this **does not yet prove it is the Oracle listener with the right service**.
- `False`: no connection could be established. Check the port, IP, firewall, VPN, network route, NAT, and service status on the server.

`PingSucceeded` may be `False` while `TcpTestSucceeded` is `True`; in that case, there is no TCP failure.

### Linux or macOS

From a client with Netcat:

```bash
nc -vz -w 3 db.lab.example 1521
```

- If `succeeded` / `open` appears, the TCP connection to host:port succeeded.
- If `Connection refused`, the target host or an intermediate device actively rejected the connection. A common cause is no listener on that port; also check firewall policies.
- If `timed out`, packets or replies may be dropped, misrouted, the host may be unresponsive, or the network disrupted.
- If `Name or service not known`, return to the name-resolution step.

Netcat implementations vary in syntax; if `-w` is unsupported, check `nc -h` and use the corresponding flag.

### Checking Directly on the Database Server

On Linux, identify the process listening on the port:

```bash
sudo ss -ltnp '( sport = :1521 )'
```

For example, look for a `LISTEN` line with `0.0.0.0:1521` or a server interface IP. If it listens only on `127.0.0.1:1521`, clients from other machines cannot reach the listener directly over an external network address.

On Windows Server:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 1521
```

Or:

```powershell
netstat -ano | findstr :1521
```

Checking the port on the server tells you whether the listener has an open socket there, but **does not replace testing from the client** because a firewall between the two machines may still block the connection.

### With Docker, NAT, or Port Forwarding

Suppose the Oracle container listens on **1521**, while the host machine publishes it as **1522**:

```bash
docker run ... -p 127.0.0.1:1522:1521 ...
```

In that case:

- **From the host itself:** connect to `localhost:1522/FREEPDB1`.
- **From inside the container:** the listener is usually still on port `1521`.
- **From another machine:** the `127.0.0.1:1522` mapping above cannot be used because the host binds only to loopback. Network access requires appropriate publish/network configuration in compliance with security policy.

Inspect port mappings with:

```bash
docker ps
docker port oracle-free
```

In Docker Desktop, `localhost` from your laptop refers to the host machine running Docker; inside another container, `localhost` refers to that container itself. This is a very common source of connection errors.

### When the Environment Requires TCPS

If the Oracle Net configuration uses **TCPS** (Oracle Net over TLS), test against the TCPS port provided by the administrator using a client configured with the appropriate wallet/certificates. A successful TCP handshake still does not prove that the TLS handshake or certificate verification succeeds. Do not assume the TCPS port is always 1522; the port depends on the actual configuration.

## 5. Layer 3 — Checking the Oracle Net Listener

Once TCP succeeds, the next step is confirming that the endpoint is genuinely an Oracle Listener and which services the listener knows about.

### How Does the Listener Receive Connection Requests?

A client sends an Oracle Net request containing a **service name**. The listener receives the request on its listening port, looks up the service/handler information, and hands off the connection to the appropriate database instance. In most modern deployments, the instance automatically registers its services with the listener (dynamic service registration); this mechanism is performed by the **LREG** background process.

Two distinct cases can occur:

1. The listener is **not running** or the client hits the **wrong listener/port** → TCP/listener-layer failure.
2. The listener **is running**, yet **does not know the requested service** → service registration or service name error; TCP may still succeed.

### Commands on the Database Server

Log into the server with an OS account configured for the Oracle environment and run:

```bash
lsnrctl status
```

For a listener not named `LISTENER`, specify the actual name:

```bash
lsnrctl status LISTENER
```

Key details to read in the output:

- `Alias` / listener name.
- `Listening Endpoints Summary`: addresses/protocols/ports the listener is listening on.
- `Services Summary`: services that have been registered or configured.
- Messages showing the listener is running, uptime, and log file location when displayed.

To view detailed service and handler information:

```bash
lsnrctl services
```

Example illustrating output meaning:

```text
Service "FREEPDB1" has 1 instance(s).
  Instance "FREE", status READY, has 1 handler(s) for this service...
    Handler(s):
      "DEDICATED" established:0 refused:0 state:ready
```

This example shows the listener recognizes service `FREEPDB1` and has a handler in the ready state. Actual handler counts, instance names, and states depend on the system.

**`lsnrctl status`/`services` must be run in the right Oracle Home environment or target the right listener.** On hosts with multiple Oracle Homes or multiple listeners, a succeeding command might not be inspecting the listener the client actually reaches.

### Quick Client-Side Check with `tnsping`

If an Oracle Net client is installed, you can run:

```bash
tnsping DBLAB
```

Here `DBLAB` is an alias configured in `tnsnames.ora` or an equivalent naming method. `tnsping` usually shows how Oracle Net resolved the alias and whether it could reach the listener at the described address.

**Limitations of `tnsping`:** an `OK` response **does not confirm** that the PDB is open, the service accepts logins, the password is right, or SQL queries work. It tests Oracle Net resolution and listener reachability, not a full database session.

### Listener Does Not Show the Expected Service

If TCP works yet `lsnrctl services` lacks `FREEPDB1`, check in order:

1. Are you querying the **exact listener and port** the client uses?
2. Is the database instance running?
3. Is the target PDB open?
4. Is the database registering services with the **right listener** (`LOCAL_LISTENER`; RAC environments may involve `REMOTE_LISTENER`/SCAN)?
5. Are you requesting a different service name than the one the database actually exposes?

On the server, an account with `SYSDBA` privileges can trigger re-registration once configuration has been verified:

```sql
ALTER SYSTEM REGISTER;
```

This statement tells the instance to re-register with its configured listener; it **does not open a closed PDB**, create a new service, or fix an incorrect `LOCAL_LISTENER` address. Do not modify listener parameters on a shared environment before verifying the system's network configuration.

### Interpreting Listener-Layer Results

| Symptom | Interpretation |
|---|---|
| `TNS-12541: no listener` / `ORA-12541` | No listener reached at endpoint, or address/port/network path issue |
| `ORA-12514: listener does not currently know of service requested` | Listener was reached, but the service name is not currently known to the listener |
| `ORA-12505: listener does not currently know of SID given` | Connect descriptor requested a **SID**, which the listener does not know; consider using the PDB's service name |
| `ORA-12516` | Listener knows the service but found no available handler; check load/connection limits/handlers |
| `lsnrctl services` shows `READY` service | Listener has a registered handler; proceed to test SQL login to verify the database layer |

## 6. Layer 4 — Checking the Database Service and PDB State

The listener can run normally even while the database instance is down or the PDB is closed. In Oracle multitenant architecture, it is critical to connect to the **right service pointing to the target PDB**.

### CDB, PDB, SID, and Service Name

```text
Oracle database server
├── Instance: FREE               (example SID)
├── CDB: FREE
│   ├── CDB$ROOT                 (root administration)
│   ├── PDB$SEED                 (template PDB)
│   └── FREEPDB1                 (PDB used for the lab)
└── Listener: TCP 1521
    ├── Service: FREE            (typically routes to CDB/root)
    └── Service: FREEPDB1        (routes to the practice PDB)
```

Depending on version/configuration, services may carry different names, belong to a cluster, or be created specifically for an application. **Do not substitute a SID for a service name when the client needs a PDB service.**

### Inspecting Instance/Database State on the Server

On the **database server**, using an OS account authorized for Oracle administration with the proper `ORACLE_SID`:

```bash
sqlplus / as sysdba
```

Then run:

```sql
SELECT instance_name, status
FROM v$instance;

SELECT name, open_mode
FROM v$database;

SELECT name, open_mode
FROM v$pdbs
ORDER BY name;

SHOW CON_NAME;
```

Interpretation:

- `v$instance` shows the current state of the instance.
- `v$database.open_mode` is typically `READ WRITE` when the database is open for normal operations.
- `v$pdbs` shows each PDB. The PDB the application needs should generally be in `READ WRITE`; `PDB$SEED` is normally read-only.
- `SHOW CON_NAME` prints the container of the **current session**, helping avoid confusion between `CDB$ROOT` and a PDB.

From the root container, query active services:

```sql
SELECT name, network_name, pdb
FROM v$active_services
ORDER BY name;
```

To inspect configured services, a DBA can also check `DBA_SERVICES` (or `CDB_SERVICES` depending on privileges/version). **Defined services** and **active/listener-registered services** are not always identical.

### What If the PDB Is Closed?

Suppose `FREEPDB1` is in `MOUNTED` state. If you hold database administration privileges and opening the PDB is appropriate for the environment, from `CDB$ROOT`:

```sql
ALTER PLUGGABLE DATABASE FREEPDB1 OPEN;

ALTER PLUGGABLE DATABASE FREEPDB1 SAVE STATE;
```

- `OPEN` opens the PDB for user access. Run it only when the PDB is actually closed; there is no need to reopen an already open PDB.
- `SAVE STATE` preserves the open state so Oracle automatically restores it after a CDB restart, where supported by the version/configuration.

Afterward, recheck `v$pdbs` and `lsnrctl services`. If the listener still does not show the service after the PDB opens, revisit service registration.

In production systems or shared multi-user environments, **administrators** are responsible for opening/closing PDBs, managing resources, and service registration. Learners should gather evidence without altering shared database state.

### Testing an SQL Session from the Target Client

On the machine experiencing the connection failure:

```bash
sqlplus -L LAB_ORACLE@//db.lab.example:1521/FREEPDB1
```

Enter the password when prompted. If login succeeds, run:

```sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS connected_service
FROM dual;

SELECT 1 AS connection_ok
FROM dual;

EXIT;
```

This single test simultaneously confirms:

1. The client traversed the Oracle Net network path.
2. The listener routed to the right service.
3. The database accepted the account and created a session.
4. The session can execute SQL.
5. `current_container` points to the **intended PDB**.

If using Oracle 21c XE, change service `FREEPDB1` to `XEPDB1`; for a custom 19c environment, use the actual PDB service provided by your DBA.

## 7. Quick Layer-by-Layer Error Reference

Oracle Net error messages vary across drivers, versions, and where the failure occurs. The table below lists the **priority investigation path**; do not treat any single error code as absolute proof of a single root cause.

| Symptom / Error Code | Priority Layer | What to Check |
|---|---|---|
| `UnknownHostException`, hostname not found | DNS/hostname | `Resolve-DnsName`, `getent ahosts`, internal DNS, VPN, spelling |
| `ORA-12154: TNS:could not resolve the connect identifier specified` | Client-side Oracle Net naming | Alias in `tnsnames.ora`, `TNS_ADMIN`, `sqlnet.ora`, `NAMES.DIRECTORY_PATH`, EZConnect syntax |
| `ORA-12545: Connect failed because target host or object does not exist` | Host/address or Oracle Net | Listener address, hostname, resolved IP, connect descriptor |
| `ORA-12541: No listener` | TCP/listener | Correct host/port, listener running/accepting connections, NAT/firewall |
| `ORA-12170` / `ORA-12535` or TCP timeout | Network path and timeouts | TCP test from client, firewall, routing, overloaded listener/DB |
| `ORA-12514` | Listener → service | Correct service name, PDB open state, `lsnrctl services`, service registration |
| `ORA-12505` | Listener → SID | Check if a SID is used instead of a service name, connect descriptor config |
| `ORA-12516` | Listener → handler | Handler state, process/session limits, server load |
| `ORA-01033` / `ORA-01034` | Instance/database | Startup state, database open mode, DBA notices |
| `ORA-01017` | Authentication | Username/password typo, case sensitivity, right PDB/service |
| `ORA-28000` / `ORA-28001` | Account state | Account locked or password expired; requires authorized admin action |
| JDBC `IO Error: The Network Adapter could not establish the connection` | Inconclusive | Check DNS/TCP/listener and the underlying root `cause` in order |
| Connection succeeds yet shows `CDB$ROOT` | Database service selection | Switch to the **PDB service**; verify `SYS_CONTEXT('USERENV', 'CON_NAME')` |
| Connects fine yet queries fail with `ORA-01031` | Post-session SQL privileges | Connection layer passed; check schema privileges rather than firewall rules |

**Note on `ORA-12154`:** This is usually an **Oracle Net connect-identifier resolution error**, such as failing to find alias `DBLAB`. It does not necessarily mean DNS failed to resolve a hostname. To tell them apart, test full EZConnect syntax and inspect alias configuration in the next section.

## 8. When the Fault Is in Oracle Net Naming: `tnsnames.ora` and EZConnect

An application may know only an alias like `DBLAB` instead of the hostname, port, and service. This alias is mapped via Oracle Net naming, commonly `tnsnames.ora`.

Example `tnsnames.ora` entry:

```ini
DBLAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)
               (HOST = db.lab.example)
               (PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = FREEPDB1)
    )
  )
```

Corresponding connection command:

```bash
sqlplus -L LAB_ORACLE@DBLAB
```

If this command fails while EZConnect `LAB_ORACLE@//db.lab.example:1521/FREEPDB1` succeeds, the issue most likely lies in the **alias name, configuration file, or client configuration lookup path**.

### Identifying Where the Client Reads Oracle Net Configuration

On systems with Oracle Client/Oracle Home, the default directory is usually under:

```text
$ORACLE_HOME/network/admin
```

The `TNS_ADMIN` environment variable can point to a different directory containing `tnsnames.ora` and `sqlnet.ora`.

In Windows PowerShell:

```powershell
$env:TNS_ADMIN
$env:ORACLE_HOME
```

On Linux:

```bash
printf 'TNS_ADMIN=%s\n' "$TNS_ADMIN"
printf 'ORACLE_HOME=%s\n' "$ORACLE_HOME"
```

Depending on the tool, a client may bundle its own Oracle Net libraries or use JDBC Thin whose configuration differs from SQL*Plus. Therefore, inspect the **actual failing application runtime**, not just an administrator's shell environment.

In `sqlnet.ora`, `NAMES.DIRECTORY_PATH` can specify naming methods such as `TNSNAMES` and `EZCONNECT`. If an organization intentionally restricts allowed methods, your use of aliases or EZConnect must match that policy.

### Service Name and SID Are Not Interchangeable

Connect descriptor using a service name:

```ini
(CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
```

Legacy connect descriptor using a SID:

```ini
(CONNECT_DATA = (SID = FREE))
```

In multitenant environments, application clients normally must use the **PDB service name**. If a Java app uses a legacy SID-style URL while SQL Developer uses a service name, the two tools can receive different errors even when connecting to the same server.

## 9. Practical Troubleshooting Workflow

Suppose SQL Developer reports it cannot connect to `LAB_ORACLE@db.lab.example:1521/FREEPDB1`.

### Step 1: Confirm the Parameters

Record the hostname, port, service name, protocol, client/driver, error timestamp, and active network (LAN/VPN). Never put passwords in logs, screenshots, or support emails.

### Step 2: Query DNS from the Failing Machine

Windows:

```powershell
Resolve-DnsName db.lab.example
```

Linux:

```bash
getent ahosts db.lab.example
```

If the name does not resolve to the expected IP, fix naming/VPN/DNS before moving on.

### Step 3: Test TCP to the Target Port

Windows:

```powershell
Test-NetConnection db.lab.example -Port 1521
```

Linux:

```bash
nc -vz -w 3 db.lab.example 1521
```

If TCP fails, check server listener status, firewall, NAT, and routing. If TCP succeeds, continue.

### Step 4: Inspect the Listener and Services on the Server

```bash
lsnrctl status
lsnrctl services
```

Verify the listener is listening on the right endpoint and that service `FREEPDB1` appears. If the service is missing, check the database/PDB and service registration settings.

### Step 5: Check the PDB and Active Services

With appropriate admin privileges on the server:

```sql
SELECT name, open_mode FROM v$pdbs;
SELECT name, network_name, pdb FROM v$active_services;
```

If the PDB is closed, notify the DBA or perform authorized administrative steps. If both the PDB and service look good, continue.

### Step 6: Test SQL Using the Specific Service Name

```bash
sqlplus -L LAB_ORACLE@//db.lab.example:1521/FREEPDB1
```

Once inside SQL*Plus:

```sql
SELECT USER,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service
FROM dual;
```

If this succeeds, network–listener–service–authentication–SQL is proven for this tool. If the Java application still fails, inspect the **application's own configuration**: JDBC URL, environment variables, connection pool, proxy, wallet/TCPS, driver, container networking, credentials, and the root cause in the stack trace.

### Step 7: Record Findings Layer by Layer

Use a compact summary table:

| Layer | Question | Evidence to Record |
|---|---|---|
| DNS | Did the hostname resolve to the right IP? | Command, timestamp, returned IP |
| TCP | Could the client open a socket to the port? | `TcpTestSucceeded` or `nc` output |
| Listener | Is a listener active on the target endpoint? | Listener name, listening address, port |
| Database service | Does the listener know the service and is the PDB open? | Service name, handler, `open_mode` |
| SQL session | Right user, right PDB, query executes? | `USER`, `CON_NAME`, `SELECT 1 FROM dual` output |

This table lets support teams immediately pinpoint which layer is failing without asking you to repeat already-proven checks.

## 10. Illustrative Scenarios

### Scenario A — Wrong DNS While Listener Works Normally

- `Resolve-DnsName db.lab.example` returns `10.40.1.25`.
- The DBA confirms the database is actually reachable at `10.40.2.25`.
- TCP test by hostname fails; TCP test against the DBA-confirmed IP succeeds.

**Investigation conclusion:** the DNS record may point to the wrong address or the client is on the wrong network/VPN. Fix name resolution or network configuration through your environment's standard process—no Oracle password reset is needed.

### Scenario B — TCP Succeeds but `ORA-12514` Occurs

- `Test-NetConnection ... -Port 1521` reports `TcpTestSucceeded: True`.
- SQL*Plus reports `ORA-12514`.
- `lsnrctl services` lists service `FREE`, without `FREEPDB1`.
- Querying `v$pdbs` shows `FREEPDB1` is `MOUNTED`.

**Investigation conclusion:** the listener is running, but the PDB service is unavailable. If authorized, an administrator opens the PDB and verifies service re-registration. Opening firewall ports would not solve this issue.

### Scenario C — TCP, Listener, and Service Work, but `ORA-01017` Occurs

- DNS resolves properly and TCP connects.
- The listener shows service `FREEPDB1` with a `READY` handler.
- Using `LAB_ORACLE`, SQL*Plus reports `ORA-01017`.

**Investigation conclusion:** most of the network path is already working. Check the username, password, target PDB, and client authentication configuration. Do not alter network settings without further evidence.

### Scenario D — Host Connection Succeeds While Java Container Fails

- Oracle Database and the Java app run in **two separate containers**.
- The app's JDBC URL uses `localhost:1521/FREEPDB1`.
- On the host, connecting to `localhost:1521` succeeds; inside the app, connections fail.

**Investigation conclusion:** `localhost` inside the Java container refers to the **Java container itself**, not the Oracle container. Use the Oracle container/service name on the shared Docker network and the container port (for example `oracle-free:1521`), then test DNS/TCP from **inside the app container**.

### Scenario E — Alias Fails While EZConnect Works

- `sqlplus LAB_ORACLE@DBLAB` reports `ORA-12154`.
- `sqlplus LAB_ORACLE@//db.lab.example:1521/FREEPDB1` succeeds.

**Investigation conclusion:** network routing and the service work under EZConnect. Check `tnsnames.ora`, `TNS_ADMIN`, `sqlnet.ora`, and SQL*Plus naming methods.

## 11. Concise Decision Flowchart

```text
Cannot connect to Oracle
    |
    v
Does hostname resolve to the right IP?
    |-- No --> DNS / hosts / VPN / hostname
    |
    v
Does TCP to host:port succeed?
    |-- No --> routing / firewall / NAT / listener not listening
    |
    v
Does listener receive requests and know the service?
    |-- No --> check endpoint, service name, service registration
    |
    v
Is DB/PDB open and handler ready?
    |-- No --> DB/PDB state, load, registration, service configuration
    |
    v
Can SQL*Plus/SQLcl log in?
    |-- No --> account / password / authentication / PDB
    |
    v
Does SELECT 1 FROM dual run?
    |-- No --> privileges / session state / database / application
    |
    v
End-to-end connectivity confirmed
```

This diagram organizes **evidence collection**. In practice, failures can affect multiple layers simultaneously; after fixing one issue, retest from the client to uncover the next.

## 12. Operational and Security Principles During Troubleshooting

1. **Test from the exact failing location.** A working connection from the server does not guarantee access from a laptop or application container.
2. **Never extrapolate from a single test.** `ping`, `nc`, `tnsping`, `lsnrctl`, and `sqlplus` answer different questions.
3. **Never expose passwords.** Let SQL*Plus prompt interactively; scrub secrets before sharing commands, logs, and screenshots.
4. **Never open database ports to the public Internet.** Test over approved network paths; adhere to VPN, firewall, TLS/wallet, and organizational access policies.
5. **Never arbitrarily restart production listeners or databases.** Inspect status and logs first; a restart can disrupt other applications while the real fault may just be a service name.
6. **Record actual environment parameters.** Oracle Free, XE, DBCA-created CDB/PDBs, RAC/SCAN, and Autonomous Database use different naming and connection conventions; `FREEPDB1` only applies when it is genuinely the system's service.
7. **Perform final verification with SQL.** Reliable proof of resolution is the target client itself logging into the **right PDB** and executing a simple query.

## 13. Self-Check Exercise

**Prompt:** Against an Oracle database you have permission to access, perform a verification pass without changing system configuration:

1. Record the hostname, TCP port, service name, and username (do not store the password).
2. Test DNS resolution from the client machine and note the returned IP.
3. Test TCP connectivity from the client to host:port.
4. If you have server access, record the listener endpoint and service list from `lsnrctl services`; otherwise, request this output from the DBA.
5. Connect using the service name via SQL*Plus/SQLcl/SQL Developer and run `SELECT USER, SYS_CONTEXT('USERENV','CON_NAME') FROM dual;`.
6. Present your findings using the table in section 9, stating the first failing layer and supporting evidence.

**Expected outcome:** Based on concrete test results, you can state precisely "DNS is not resolving properly", "TCP is not reaching the listener", "the listener has not registered the service", "the PDB is not open", or "reached the database but authentication failed"—rather than simply reporting "Oracle won't connect".

This is a foundational skill when working with Oracle SQL Developer, SQLcl, SQL*Plus, Java JDBC applications, containers, and multi-PDB Oracle Database environments.
