# Listener, Service Registration, and Oracle Net Connection Flow

## 1. The Big Picture

When a Java application, SQL*Plus, or an administration tool connects to Oracle Database over the network, it does not simply "open port 1521 and run SQL." **Oracle Net Services** must solve three distinct tasks:

1. **Locate the target**: the connection name provided by the client is resolved into a network address and a *database service* name.
2. **Find where it is served**: an **Oracle Net Listener** at that address receives the request, looks up service information, and chooses an appropriate *service handler*.
3. **Establish the session**: the connection is handed off or redirected to a database server process; authentication, session creation, and SQL exchange then follow.

On the database side, the background process **LREG (Listener Registration)** notifies the listener which instance provides which services and which handlers can accept connections. Therefore, even when the listener is running, a service may not yet be registered or ready.

```text
CLIENT MACHINE                                   DATABASE MACHINE
──────────────                                   ────────────────
Application / SQL*Plus / JDBC
  │
  ├─ "ORDER_APP" (alias in tnsnames.ora)
  │         or
  └─ "//db01.example.com:1521/orders_rw.example.com" (Easy Connect)
            │
            ▼
    Oracle Net naming resolution
    -> host, port, protocol, SERVICE_NAME
            │
            │ TCP/TCPS to endpoint
            └──────────────────────────────────► Listener :1521
                                                   ▲
                                                   │ service registration
                                              LREG │
                                                   │
                                            Oracle instance
                                           (services + handlers)
                                                   │
                                        select handler for service
                                                   │
                  ┌────────────────────────────────┘
                  ▼
    Handoff / redirect to dedicated server
    or shared server dispatcher
                  │
                  ▼
    Authenticate and establish database session
                  │
                  ▼
    Client ↔ server process / dispatcher ↔ Database
          (SQL, results; listener does not proxy every query)
```

**Key takeaway:** The listener is the intake and routing point for **initial connection requests**. Once the connection is established, database session traffic typically flows directly between the client and the selected server process/dispatcher; the listener is not a mandatory proxy for every SQL statement.

> Examples use Oracle Database 19c as the baseline for common concepts and syntax. Actual configurations may vary in 21c, 23ai/26ai, Oracle RAC, Exadata, Oracle Cloud, and across client versions. Host/service names below are illustrative placeholders, not live endpoints.

## 2. Distinguishing the Entities Correctly

| Term | What Is It? | Example | Do Not Confuse With |
| --- | --- | --- | --- |
| **Database** | Physical and logical data structures managed by Oracle | `ORCLCDB` | Instance or service |
| **Instance** | SGA and background processes used to access a database | `orcl1`, `orcl2` | CDB/PDB or service |
| **SID** | Identifier of an Oracle instance, especially in local connections and legacy configs | `orcl1` | Application service name |
| **CDB** | Container database that can hold multiple PDBs | `ORCLCDB` | A single PDB |
| **PDB** | Pluggable database inside a CDB | `ORDERPDB` | Listener or a separate instance |
| **Database service** | Logical name representing a database workload/access point; can bind to a PDB, multiple instances, and HA policies | `orders_rw.example.com` | SID and client alias |
| **Net service name / alias** | Arbitrary client-side name used to look up a *connect descriptor* | `ORDER_APP` | Actual database service name |
| **Listener** | Process listening for connections on one or more network endpoints | `LISTENER` on `db01:1521` | Database server process |
| **Service handler** | Process/address handling connections for a service: dedicated server or dispatcher | `DEDICATED`, `D000` | Listener |
| **Connect descriptor** | Structure specifying `ADDRESS` and `CONNECT_DATA` | `(DESCRIPTION=...)` | Just a hostname |

One instance can register **multiple services**, and one service in a RAC environment can be offered by **multiple instances**. That relationship is why applications should connect using the workload's service rather than pinning to a specific node's SID.

### 2.1. Why `SERVICE_NAME` Matters More Than `SID` for Applications

In a CDB, connecting to a **service with a PDB property** routes the session into the corresponding PDB. In RAC, a service can relocate across instances according to Clusterware policy. Neither case can be adequately described by a fixed `SID`.

Example:

```text
SERVICE_NAME = orders_rw.example.com   ← application needs access to ORDER workload
INSTANCE     = orcl1                   ← instance currently serving it
PDB          = ORDERPDB                ← container holding the application schema
CLIENT ALIAS = ORDER_APP               ← name chosen by the app team in tnsnames.ora
```

Do not rely on `ORACLE_SID=orcl1` on the server to determine the `SERVICE_NAME` that remote applications should use. `ORACLE_SID` usually selects an instance for local *bequeath* connections, not the service name in a network descriptor.

## 3. What Does Oracle Net Listener Actually Do?

The listener is a process that can run independently of the instance, accepting requests at protocol addresses (*protocol endpoints*) such as TCP or TCPS. One listener can accept connections for multiple databases/services; conversely, one instance can register with multiple listeners as configured.

Upon receiving a request containing `SERVICE_NAME`, the listener needs to know:

- Is that service dynamically registered or statically configured?
- Which instance(s) currently provide the service?
- Which handler is accepting connections: dedicated server or shared server dispatcher?
- Is the handler available, blocked from new connections, or overloaded?
- In a clustered environment, does the connection need to be forwarded or redirected to another node?

The listener may **hand off a socket**, **spawn a dedicated server process**, or **return another address for the client to reconnect to**. The exact mechanism depends on the OS, protocol, and handler type. Therefore, do not claim that on every connection the Oracle listener "proxies" data or always produces exactly one TCP connection.

### 3.1. Dedicated Server

Each client connection is served by a corresponding *dedicated server process*; this suits many traditional applications, though it requires enough process/session resources for concurrent connections.

```text
Client A ─► Listener ─► Dedicated server A ─► Instance
Client B ─► Listener ─► Dedicated server B ─► Instance
```

The client can request it explicitly in the descriptor:

```text
(CONNECT_DATA=
  (SERVICE_NAME=orders_rw.example.com)
  (SERVER=DEDICATED)
)
```

### 3.2. Shared Server

When a database is configured for shared server, a **dispatcher** handles network communication for multiple clients and places requests onto queues for *shared server processes* to execute. The listener registers and selects a dispatcher for the service. This configuration is completely different from an application using a **JDBC connection pool**: a connection pool reuses open sessions/connections on the application side, whereas shared server changes Oracle's server-side process architecture.

```text
Client A ──┐
Client B ──┼──► Dispatcher D000 ─► Queue ─► Shared servers ─► Instance
Client C ──┘
```

In the descriptor, you can request `(SERVER=SHARED)` if the system has appropriate dispatchers configured. Aside from dedicated/shared, Oracle also offers **Database Resident Connection Pooling (DRCP)** with server type `POOLED`; do not treat these three mechanisms as the same.

## 4. Dynamic Service Registration: What Does LREG Tell the Listener?

In modern Oracle versions, **LREG** is the background process responsible for dynamic service registration. Older documentation often attributed registration to **PMON**; when reading 19c+ documentation, use the process name **LREG**.

During dynamic registration, LREG sends the listener information such as:

- The service name (which may include a network domain).
- The name of the instance providing the service.
- Ready handlers, dispatcher addresses, and server types.
- Status and load information used for routing and load balancing.

The listener uses this information to maintain its list of services, instances, and handlers. **You do not need to manually declare every service in `listener.ora`** when dynamic registration works properly.

```text
Oracle instance startup / service start / state change
                         │
                         ▼
                  LREG detects it
                         │
                         ▼
    LOCAL_LISTENER / REMOTE_LISTENER determine registration targets
                         │
                         ▼
               Listener receives info
                         │
                         ▼
        lsnrctl services shows service
        and handler READY/BLOCKED/...
                         │
                         ▼
          Clients can find the right service
```

### 4.1. `LOCAL_LISTENER`

`LOCAL_LISTENER` specifies the local listener address with which the instance registers. In standard configurations on TCP port **1521**, Oracle has a default listener resolution mechanism; an empty parameter value is not necessarily an error.

If the listener listens on **port 1522** or another non-default endpoint, the DBA must ensure `LOCAL_LISTENER` points to that endpoint and that any alias used can be resolved **from the database host**, not merely from the client machine.

Illustrative example:

```sql
-- Read current configuration without modifying the system.
SELECT name, value
FROM   v$parameter
WHERE  name IN ('local_listener', 'remote_listener')
ORDER BY name;
```

If a custom listener is configured on `db01.example.com:1522`, the DBA can set `LOCAL_LISTENER` to the corresponding Oracle Net address through a controlled administrative procedure. Only change this parameter when you have genuinely verified an endpoint mismatch; **do not modify `SERVICE_NAMES` as a default workaround**.

### 4.2. `REMOTE_LISTENER`

`REMOTE_LISTENER` specifies remote listeners that should receive registration information, commonly seen in Oracle RAC when services register with **SCAN listeners**. In systems managed by Oracle Clusterware, parameters and listeners are usually configured automatically; do not manually apply single-instance changes without checking the topology first.

### 4.3. Why Is the Listener Running Yet the Service Is Still Missing?

If the listener starts **after** the instance, dynamic registration may be delayed until the next LREG discovery cycle. Oracle 19c documentation describes a default discovery interval of roughly **60 seconds**; a DBA can proactively trigger immediate re-registration:

```sql
-- Administrative command; requires appropriate privileges.
-- Execute only after verifying the listener and service are operating properly.
ALTER SYSTEM REGISTER;
```

This command tells LREG to re-register immediately; it **does not create a nonexistent service**, **does not open a closed PDB**, **does not fix DNS/firewalls**, and **does not replace starting the listener**. If registration packets fail to reach the listener due to a wrong endpoint or registration policy, running this command repeatedly will not fix the root cause.

## 5. How Do Dynamic Registration and Static Registration Differ?

| | **Dynamic** | **Static** |
| --- | --- | --- |
| Source of info | Instance/service via LREG | `SID_LIST_<listener_name>` entry in `listener.ora` |
| Runtime awareness | Knows registration and handler state | May not know the true state of the instance |
| Typical `lsnrctl services` output | `READY`, `BLOCKED`, etc. | `UNKNOWN` when only statically configured |
| Updates on service start/stop | Automatically updated via registration | Does not automatically reflect full dynamic state |
| When to use | Normal application connections | Special cases needing SID visibility before instance startup, e.g., certain Data Guard Broker or external procedure setups |

Example static declaration structure—**for recognition only**, not a configuration to copy verbatim into production:

```ini
# listener.ora — illustrating a static SID list for special administrative scenarios
SID_LIST_LISTENER =
  (SID_LIST =
    (SID_DESC =
      (GLOBAL_DBNAME = orcl_admin.example.com)
      (ORACLE_HOME = /u01/app/oracle/product/19c/dbhome_1)
      (SID_NAME = orcl1)
    )
  )
```

`ORACLE_HOME`, `SID_NAME`, and static names must match the real server. Do not add `SID_LIST` just to "cure" every `ORA-12514` error; if the needed service is supposed to be registered by LREG, fix the misconfiguration at the right layer instead of masking the problem with a static entry. `UNKNOWN` status means the listener does not know runtime state from a static entry—it **does not automatically mean the instance is broken**.

## 6. How Does the Client Find the Endpoint?

Before opening a connection, the client must translate a *connect identifier* into a *connect descriptor*. Two common methods are **Easy Connect** and **local naming (`tnsnames.ora`)**.

### 6.1. Easy Connect

Common syntax:

```text
//host[:port]/service_name
```

SQL*Plus example:

```bash
# Client prompts for password interactively; do not embed passwords in command lines.
sqlplus -L app_user@//db01.example.com:1521/orders_rw.example.com
```

JDBC Thin example:

```properties
spring.datasource.url=jdbc:oracle:thin:@//db01.example.com:1521/orders_rw.example.com
spring.datasource.username=app_user
# Retrieve password from a secrets manager or environment secret store.
```

In both examples, `db01.example.com:1521` is the **listener** address, and `orders_rw.example.com` is the **database service**. Never use the listener name (`LISTENER`) in place of the service name. Easy Connect Plus and newer client syntaxes support extra endpoints, security parameters, retries, and load balancing; verify the exact syntax supported by your deployed Oracle Client/JDBC driver.

### 6.2. `tnsnames.ora`: Client-Side Aliases

```ini
# tnsnames.ora on the client machine or the location pointed to by TNS_ADMIN
ORDER_APP =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db01.example.com)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = orders_rw.example.com)
      (SERVER = DEDICATED)
    )
  )
```

Client usage:

```bash
sqlplus -L app_user@ORDER_APP
```

The client resolves `ORDER_APP` to the descriptor first and then contacts the network address. `ORDER_APP` is a **client-chosen alias**, which may differ from `orders_rw.example.com`. Changing an alias on a laptop does not mean the listener or database service was renamed.

### 6.3. `sqlnet.ora` and `TNS_ADMIN`

`sqlnet.ora` configures Oracle Net behavior, including naming methods and their lookup order:

```ini
# sqlnet.ora — example client-side naming resolution order
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
```

The configuration directory depends on how Oracle Client, Oracle Home, Instant Client, the application, the **`TNS_ADMIN`** environment variable, and individual drivers are installed. If `tnsping ORDER_APP` resolves the wrong descriptor, determine **which exact file the client is reading**; do not assume a single `tnsnames.ora` serves every tool on the machine. Some JDBC Thin applications use Easy Connect URLs without needing `tnsnames.ora` at all.

### 6.4. Why Port and Service Name Belong to Two Different Layers

```text
db01.example.com:1521               → DNS + TCP + Listener endpoint
orders_rw.example.com                → Oracle Net database service
app_user                             → Oracle database account
ORDERPDB                             → Container receiving the session
```

**A successful TCP handshake** only proves an endpoint is listening on that port; it does not prove the service is registered, a handler is ready, the user is authenticated, or the PDB is open.

## 7. A Typical Single-Instance Configuration

Suppose we have:

- Database host: `db01.example.com`.
- Listener: `LISTENER`, TCP port `1521`.
- CDB: `ORCLCDB`, instance: `orcl1`.
- PDB: `ORDERPDB`.
- DBA-managed application service: `orders_rw.example.com`, bound to `ORDERPDB`.
- Clients connecting via alias `ORDER_APP` or Easy Connect.

### 7.1. Listener Side

A minimal TCP listener configuration looks like:

```ini
# listener.ora on the database server — illustrative example
LISTENER =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS = (PROTOCOL = TCP)(HOST = db01.example.com)(PORT = 1521))
    )
  )
```

The listener may be created and configured automatically by installation tools. **Adding `SID_LIST_LISTENER` is not required** for normal application database services because LREG registers them dynamically. If the database runs behind NAT, a container, or a VM, the listener address advertised to clients must also be properly routable. Do not copy hosts, ports, or paths verbatim from examples without verifying your real network topology.

### 7.2. Database Service Side

Oracle creates a default service for each PDB, but the **Oracle 19c Multitenant Administrator's Guide** recommends using **user-defined services** for applications so you can manage custom attributes and operational policies instead of coupling to the default PDB service.

For databases managed by **Oracle Restart/Clusterware**, use **SRVCTL** to create, configure, start, and set policies for services. For single-instance setups not managed by Clusterware, DBAs can use **`DBMS_SERVICE`**. In Oracle 19c, managing services directly via the **`SERVICE_NAMES`** parameter is **deprecated**; do not use it as the default path for creating new services.

Read-only inspection commands when using Oracle Restart/Clusterware (replace `db_unique_name` with the actual value):

```bash
srvctl config service -db db_unique_name
srvctl status service -db db_unique_name
```

Creating, starting, stopping, or relocating services with SRVCTL/DBMS_SERVICE alters database operations and requires proper DBA procedures. If `ORDERPDB` is closed or the service has not been started, the listener may show no usable service even though the listener itself is alive.

### 7.3. Verifying from the Listener

On a machine with Oracle Net Listener Control and the proper Oracle Home:

```bash
lsnrctl status LISTENER
lsnrctl services LISTENER
```

`STATUS` shows which config file the listener uses, which endpoints are open, and a summary list of services. `SERVICES` shows instance/handler details, making it ideal for verifying whether a service is truly registered.

Illustrative output (abbreviated, not a live system capture):

```text
Service "orders_rw.example.com" has 1 instance(s).
  Instance "orcl1", status READY, has 1 handler(s) for this service...
    Handler(s):
      "DEDICATED" established:0 refused:0 state:ready
```

| Status | How to Read It |
| --- | --- |
| `READY` | Instance/handler can accept connections at the time the listener reported |
| `BLOCKED` | Temporarily refusing new connections; inspect database state and resources |
| `RESTRICTED` | Instance restricts connections due to restricted mode |
| `UNKNOWN` | Static registration entry; listener has no dynamic runtime state from registration |
| Service missing | Check service name, PDB/service status, LREG, registration endpoint, or which listener you queried |

`lsnrctl status` returning success **does not guarantee** every listed service is connectable. Read `services` and test a valid application connection.

## 8. Step-by-Step Connection Establishment Flow

Suppose an application connects using:

```text
jdbc:oracle:thin:@//db01.example.com:1521/orders_rw.example.com
```

**Step 1 — Resolve the connect identifier.** Oracle JDBC Thin parses Easy Connect, extracting protocol TCP, host `db01.example.com`, port `1521`, and service `orders_rw.example.com`. With an alias, the client first checks `tnsnames.ora` or its configured naming method.

**Step 2 — DNS and network transport.** The client resolves the hostname to an IP and opens a TCP connection (or performs a TLS handshake for TCPS) to the listener. If DNS, firewalls, routing, or NAT are wrong, the request may never reach the listener.

**Step 3 — Listener receives connect data.** The listener reads `SERVICE_NAME` (along with attributes such as server type or instance name if specified), checks the table registered by LREG, and chooses a matching instance/handler.

**Step 4 — Handoff or redirect.** Depending on architecture, the listener spawns/hands off the connection to a dedicated server, assigns a dispatcher, or returns an address for the client to connect to another handler. If no service or handler is ready, the client receives an Oracle Net error at this stage.

**Step 5 — Authentication and session creation.** The server process communicates with the client, authenticates the account using the configured mechanism, checks access privileges, and completes session setup. `ORA-01017` typically occurs during authentication—a completely different failure layer from `ORA-12514`.

**Step 6 — SQL execution.** The application sends SQL and fetches results over the session; the listener returns to waiting for new incoming connections. If a connection pool is used, the application borrows an already open session, so **not every SQL query repeats all six steps**.

**Step 7 — Cleanup.** When the connection closes, the server process/dispatcher and associated resources are handled according to handler type; a connection pool may retain valid connections for reuse.

### Testing from the Client and Confirming the Actual Container

```bash
# Tests naming resolution and Oracle Net reachability only; does not log into the DB.
tnsping ORDER_APP

# Log in with a provisioned account; password is entered at the prompt.
sqlplus -L app_user@ORDER_APP
```

After logging in successfully:

```sql
SELECT SYS_CONTEXT('USERENV', 'SERVICE_NAME')  AS service_name,
       SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name
FROM   dual;
```

The output confirms **which service, container, and instance the client actually landed on**. This is especially helpful when multiple PDBs exist or when a service moves across instances in RAC. A successful `tnsping` tests only part of Oracle Net; it **does not authenticate the user and does not prove a specific PDB/service can accept sessions**.

## 9. Oracle RAC: SCAN and Two Listener Layers

In Oracle Real Application Clusters, applications should not hardcode the hostname of an individual node when the goal is a service with failover and connection load balancing. **SCAN (Single Client Access Name)** provides a stable DNS name for clients to reach the cluster; a SCAN listener receives the initial request and redirects it to the local listener on a node hosting an instance that serves that service.

```text
                         +------------------------+
Client ─► DNS: scan.example.com ─► SCAN listener  +──────────────┐
                         +------------------------+              │
                 picks instance offering service, load/policy    │ redirect
                                                                 ▼
                    ┌───────────────────────────────┬───────────────────────────────┐
                    │ Node 1                        │ Node 2                        │
                    │ Local Listener :1521          │ Local Listener :1521          │
                    │ Instance orcl1                │ Instance orcl2                │
                    └───────────────────────────────┴───────────────────────────────┘
```

Typical flow: client resolves SCAN → connects to a SCAN listener → SCAN listener selects an eligible instance offering the service → returns that node's local listener address → client contacts that node/handler to finish connecting.

```text
# JDBC Thin via a RAC service — illustrative
jdbc:oracle:thin:@//scan.example.com:1521/orders_rw.example.com
```

Common points to check when troubleshooting RAC errors:

- Does the SCAN name resolve properly, and can the client reach the SCAN listener?
- Is the Clusterware-managed service **online** on at least one instance?
- Is `REMOTE_LISTENER`/SCAN registration aligned with Clusterware configuration?
- Can the client reach the **redirected local listener address**, or only the SCAN VIP? This is a frequent failure when networks/firewalls are segmented.
- Are the driver and connection pool configured for failover, retries, timeouts, and service notifications required by the SLA? Using SCAN/services alone **does not automatically guarantee** in-flight transactions continue seamlessly after a failure.

**Never blindly apply single-instance listener commands to a Clusterware/RAC environment.** In RAC, listeners, SCAN, and services typically have lifecycles managed by Grid Infrastructure and SRVCTL.

## 10. Related Network and Security Configuration

### 10.1. TCP vs. TCPS

- **TCP**: transports Oracle Net connections over plain TCP. TCP listeners often use port `1521`, though another port can be configured.
- **TCPS**: Oracle Net over TLS, involving certificates, wallets/trust stores, and matching client/server configs. Opening a TCP port **does not prove** TLS is configured properly.

A descriptor may specify `(PROTOCOL=TCPS)`, yet simply changing `TCP` to `TCPS` in a URL is not enough; you need valid certificates, trust chains, hostname-verification policies, and wallet configuration matching your client/driver version.

### 10.2. Listeners Accepting Connections and Network Registration

Exposed endpoints should be restricted, with firewalls, listener admin privileges, and registration policies properly controlled. In multi-node systems, *service registration* security policies can restrict remote LREG registration; consult version-specific documentation for `VALID_NODE_CHECKING_REGISTRATION_...` and related mechanisms rather than opening registration unconditionally whenever `ORA-12514` appears.

Never pass passwords on command lines, commit secrets into `tnsnames.ora`, or disable TLS verification to "get it working." `tnsnames.ora` typically only needs addresses and service names—no passwords.

### 10.3. NAT, Containers, VPNs, and Firewalls

The network path from client → listener **can differ** from the path from client → server process/dispatcher after redirect. In Docker, VMs, VPNs, or multi-homed hosts, verify:

1. Can the client resolve the hostname inside the connect descriptor properly?
2. Is the actual TCP/TCPS port published/forwarded and permitted through firewalls?
3. Does the listener or dispatcher return a private/container IP that the client cannot route to?
4. In RAC, are node VIPs, SCAN VIPs, and local listeners reachable from the application's network zone?

Depending on deployment, network routing, listener endpoints, and container networking must be designed deliberately; never assume opening port `1521` alone covers every redirect scenario.

## 11. Outside-In Troubleshooting Workflow

When a client reports an inability to reach Oracle, work in order: network layer → listener → registration → service handler → database authentication.

### 11.1. Step A: Verify the Exact Connect String

Record the **exact host, port, protocol, service name**, driver version, and naming method in use; never ask users to send passwords. If an alias is used, verify what descriptor it resolves to in **the actual application environment** (IDEs, containers, and app servers may differ from a personal terminal).

```bash
# When using a TNSNAMES alias, verify client-side resolution.
tnsping ORDER_APP
```

For Easy Connect, compare the hostname/service against what the DBA published. Test DNS and TCP connectivity with OS-appropriate network tools (`nslookup`, `Test-NetConnection` on Windows, `nc -vz` on Linux if available). These network checks test endpoint reachability only; they do not replace Oracle login.

### 11.2. Step B: Check Where the Listener Is Listening

```bash
lsnrctl status LISTENER
lsnrctl services LISTENER
```

Read **Listening Endpoints Summary** to verify host/port/protocol; read **Services Summary** and handler sections to see if the service is present and whether an instance is `READY`. If the host has multiple Oracle Homes or listeners, specify the exact listener name and use the binary from the home managing the instance.

### 11.3. Step C: Inspect Services and PDBs from the Database

The following queries read metadata only; run them from an administrative account with appropriate privileges:

```sql
-- Services defined/registered in the database metadata view.
SELECT name, network_name, pdb, con_id
FROM   v$services
ORDER BY name;

-- Services currently active on the current instance.
SELECT name, con_id
FROM   v$active_services
ORDER BY name;

-- Check PDB open states when querying from CDB root.
SELECT con_id, name, open_mode
FROM   v$pdbs
ORDER BY con_id;

-- Listener targets configured for instance registration.
SELECT name, value
FROM   v$parameter
WHERE  name IN ('local_listener', 'remote_listener', 'service_names')
ORDER BY name;
```

Note: `V$SERVICES` and `V$ACTIVE_SERVICES` reflect different aspects of service metadata and status; they are **not an instant mirror** of `lsnrctl services`. In RAC, inspect **each instance** (e.g., via the appropriate `GV$...` views) and Clusterware service policies. `SERVICE_NAMES` should only be checked to understand legacy setups, not actively modified, as it is deprecated for customer use in 19c.

### 11.4. Step D: Determine Whether Registration Is Misaligned

If the database and service are running yet the listener does not know the service:

1. Identify the actual listener that should receive registration (host/port/protocol).
2. Compare `LOCAL_LISTENER` and `REMOTE_LISTENER` against that address, including alias and DNS resolution **on the database host**.
3. Check whether the listener blocks registration by network policy.
4. If the listener was just restarted, wait for the LREG cycle or have an administrator run `ALTER SYSTEM REGISTER` after verifying conditions.
5. Check the listener log and database alert/trace logs around the error timestamp if the mismatch persists.

If the PDB/service is closed, fix the PDB/service state via DBA procedures first; `ALTER SYSTEM REGISTER` cannot make a stopped service ready.

### 11.5. Step E: Test Authentication at the End of the Path

Once the listener and service show a `READY` handler, test login with a valid account. Receiving `ORA-01017`, `ORA-28000`, `ORA-01045`, or session privilege errors means network/routing already passed the `ORA-12514` stage; at that point inspect credentials, account status, `CREATE SESSION`, and database policies instead of only tweaking the listener.

A command on the database server like `sqlplus / as sysdba` may use a **local connection bypassing the listener**. It proves the database is accessible locally, **not that remote Oracle Net is configured properly**.

## 12. Common Errors Table: Symptoms and Layers to Check

| Error Code / Symptom | Likely Area Involved | First Thing to Check |
| --- | --- | --- |
| `ORA-12154` | Client cannot resolve the connect identifier | `tnsnames.ora`, `TNS_ADMIN`, `NAMES.DIRECTORY_PATH`, alias or Easy Connect syntax |
| `ORA-12541` / `TNS-12541` | No listener found at requested endpoint | Correct host/port, listener process running, firewall/routing, and protocol |
| `ORA-12514` | Listener is up but does not know the requested service | `SERVICE_NAME`, `lsnrctl services`, service/PDB state, LREG registration |
| `ORA-12505` | Listener does not know the requested SID | Descriptor using old/wrong `(SID=...)`, instance name, or static registration; prefer proper service |
| `ORA-12516` / `ORA-12520` | No matching handler found, or handler unavailable | Dedicated/shared handlers, load, `PROCESSES`/`SESSIONS` limits, instance state |
| `ORA-12528` | Listener sees instance blocking new connections | Instance/PDB starting up, restricted/blocking state |
| `ORA-01017` | Invalid credentials or authentication mechanism | Username/password, PDB name, proxy/external auth, account policies |
| `ORA-28000` | Account is locked | Account status and security policy; authorized DBA action |
| JDBC `IO Error`, `ORA-17002` | I/O error with multiple possible causes | Root cause in exception chain, DNS, port, TLS, timeouts, redirects |
| `tnsping` OK but login fails | Naming/endpoint responds; deeper layers not necessarily OK | Service registration, handlers, authentication, PDB state |

**Avoid reacting mechanically to error codes.** For instance, `ORA-12514` right after a listener restart may simply mean LREG hasn't re-registered yet; the same error in a long-running system could mean the client called the wrong service, the PDB is closed, or registration went to another listener. Capture timestamps, listener addresses, and connect identifiers (when provided) to inspect logs accurately.

## 13. Four Practical Scenarios

### Scenario 1 — Listener `READY` but Wrong Service Called

Client config:

```text
//db01.example.com:1521/ORCLCDB
```

Meanwhile `lsnrctl services` only lists `orders_rw.example.com` (the app needs `ORDERPDB`). TCP 1521 is open and the listener is alive, yet the client may get `ORA-12514` for `ORCLCDB` if that name isn't registered. Proper fix: obtain the **DBA-published application service name** and update the descriptor; do not invent a static SID entry just to keep a wrong connection string working.

### Scenario 2 — Listener Moved to Port 1522, Database Still Registers on 1521

The DBA moved the listener endpoint to `db01:1522`. The client updated its URL to `:1522`, yet `lsnrctl services` on the new listener shows no service. If the instance keeps registering with the old default port, update `LOCAL_LISTENER` to the new endpoint (or its alias), verify name resolution **on the database server**, and re-register. Updating `tnsnames.ora` on the client alone does not tell LREG about the new port.

### Scenario 3 — Local SQL*Plus Connects, Remote Application Cannot

On the server, `sqlplus / as sysdba` succeeds, while the application hits `ORA-12541`. A local `/ as sysdba` connection can **bypass the listener**, so it does not rule out a stopped listener, wrong port, or firewall block. Start by testing host/port/protocol from the client host and running `lsnrctl status` on the server.

### Scenario 4 — RAC Reaches SCAN but Fails After Redirect

The client reaches the SCAN VIP and SCAN listener normally; the listener picks `orcl2` and redirects the client to Node 2's local listener. If the client's network zone cannot reach that node VIP, connection completion fails. Check **post-redirect network reachability**, along with local listener/service status on Node 2; do not stop testing after a TCP check to SCAN alone.

## 14. Self-Check Practice (Read-Only, Without Changing Config)

Assuming access to a lab database, work through these steps:

1. Record the exact connection string used by SQL*Plus/JDBC; identify the host/port, alias, and service.
2. Read `lsnrctl status` and `lsnrctl services` to identify endpoints, service names, instances, and handlers.
3. Run read-only queries against `V$SERVICES`, `V$ACTIVE_SERVICES`, `V$PDBS` (if CDB), and `V$PARAMETER`.
4. Connect using the **actual service** via Easy Connect or an alias; after login, use `SYS_CONTEXT` to verify the service/container/instance.
5. Explain in your own words why `tnsping` can succeed while `ORA-12514` still occurs, and why `sqlplus / as sysdba` does not prove the listener works.

**Reasoning Questions:**

**A.** `lsnrctl status` shows `LISTENER` listening on `:1521`, but `lsnrctl services` does not list `inventory_rw.example.com`. Should the client immediately change its password?

**B.** `lsnrctl services` shows an instance with `status UNKNOWN`. Is the database definitely shut down?

**C.** After restarting the listener, services disappear from output for tens of seconds and then reappear. Which component explains this?

**D.** An application uses Oracle RAC, yet its connection string is hardcoded to `node01` and SID `orcl1`. What are the operational drawbacks?

<details>
<summary>Answer Hints</summary>

**A.** No. `ORA-12514`/unregistered service happens before authentication; check the service name, active PDB/service state, and LREG first.

**B.** No. `UNKNOWN` typically appears on static registration entries, where the listener does not know live runtime state.

**C.** LREG performs dynamic registration periodically. You can wait for the next cycle or have a DBA run `ALTER SYSTEM REGISTER` if needed.

**D.** The application is coupled to a single node/instance, losing SCAN routing, service relocation, load-based routing, and HA policies; design around services and SCAN appropriately.

</details>

## 15. Operational Principles to Maintain

- **A service is the logical contract** between workload and database; prefer DBA-managed services for applications, especially with PDBs and RAC.
- **The listener is only the first connection-routing layer**; verify service/handlers and authentication before concluding connectivity is complete.
- **LREG registers dynamically**, with `LOCAL_LISTENER` and `REMOTE_LISTENER` determining which listeners receive registration; `SID_LIST` is not required for every service.
- **A running listener does not guarantee a ready service**; `lsnrctl services` is far more informative than a raw port check.
- **Client alias, service name, SID, and hostname are distinct**; inspect each layer during troubleshooting.
- **RAC/Clusterware has its own management workflow**; respect SCAN, local listeners, SRVCTL, and cluster service policies.
- **Local connections do not substitute for remote checks**; likewise, `tnsping` does not replace real queries and authentication.

## 16. Official Oracle Documentation for Further Reading

1. [Oracle Database 19c Net Services Administrator's Guide — Identifying and Accessing the Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/identifying-and-accessing-database.html): service names, listeners, handlers, dedicated/shared server, and practical connectivity.
2. [Oracle Database 19c — Configuring and Administering Oracle Net Listener](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-and-administering-oracle-net-listener.html): listener config, LREG, `lsnrctl STATUS/SERVICES`, handler states, and static registration.
3. [Oracle Database 19c RAC Installation Guide — Database Initialization Parameters for Service Registration](https://docs.oracle.com/en/database/oracle/oracle-database/19/rilin/database-initialization-parameters-for-database-service-registration.html): `LOCAL_LISTENER`, `REMOTE_LISTENER`, LREG, and `ALTER SYSTEM REGISTER`.
4. [Oracle Database 19c — Configuring Naming Methods](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-naming-methods.html): Easy Connect, `tnsnames.ora`, `sqlnet.ora`, and lookup ordering.
5. [Oracle Database 19c — Managing Services for PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/administering-pdbs-with-sql-plus.html): default vs. user-defined services, `PDB` property, SRVCTL/DBMS_SERVICE.
6. [Oracle Database 19c — Creating Database Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/creating-and-configuring-an-oracle-database.html): service management methods and `SERVICE_NAMES` deprecation notice.
7. [Oracle Database 19c RAC — Connecting Using SCANs](https://docs.oracle.com/en/database/oracle/oracle-database/19/riwin/about-connecting-to-an-oracle-rac-database-using-scans.html): SCAN listener → local listener flow and RAC service routing.
8. [Oracle Database 19c — Troubleshooting Oracle Net Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/troubleshooting-oracle-net-services.html) and [Oracle Error Help — ORA-12514](https://docs.oracle.com/en/error-help/db/ora-12514/): error causes at each layer.

**Mental checklist:** client identifier **→** naming resolution **→** listener endpoint **→** LREG-registered service **→** handler **→** authentication/session. When an error occurs, pinpoint which link in the chain stopped and inspect evidence at that exact layer.
