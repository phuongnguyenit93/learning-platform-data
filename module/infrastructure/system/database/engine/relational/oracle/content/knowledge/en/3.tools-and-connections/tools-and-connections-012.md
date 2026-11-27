# Reading ORA Error Codes and Distinguishing Connectivity Errors from Authentication Errors

When a Java application or a tool like SQL*Plus, SQLcl, or SQL Developer fails to reach **Oracle Database**, the message usually takes the form `ORA-xxxxx`, `TNS-xxxxx`, or an exception thrown by the JDBC driver. The same symptom—"cannot connect to the database"—can stem from two very different problem categories:

- **Connectivity errors:** the application has not reached the right Oracle listener/service, or failed to establish and maintain the required session. Causes may lie in hostname, DNS, network ports, routing, listener, service/PDB name, TLS, resource limits, or dropped connections.
- **Authentication errors:** the login request reached Oracle's identity-checking step, yet the username, password, account status, or authentication mechanism failed requirements. Network connectivity may be completely healthy.

A third category must also be kept separate: **authorization errors**, which occur after Oracle identifies the user, when that user lacks permission to open a session or perform an operation. Changing passwords or opening firewall ports will never fix missing table privileges.

The goal of this lesson is to read **error codes, failure points, and connection context** accurately so you choose the right diagnostic step instead of guessing or making unsupported production config changes.

## 1. What Is `ORA`? Why Do Error Messages Have Multiple Layers?

Oracle uses error codes consisting of a prefix and number, for example:

```text
ORA-01017: invalid username/password; logon denied
ORA-12514: TNS:listener does not currently know of service requested in connect descriptor
ORA-28000: the account is locked
```

Exact wording can vary across Oracle versions, drivers, and tools; the **numeric code** is usually a more reliable starting point for classification. In some tools, Oracle Net-layer errors also appear with the `TNS-` prefix, such as `TNS-12541`. `TNS` does not mean a password error: Oracle Net is responsible for locating and establishing the connection path to the database service.

On the Java application side, exceptions also wrap across multiple layers:

```text
Spring / Hibernate / connection pool
    |
    +-- CannotGetJdbcConnectionException / JDBCConnectionException
            |
            +-- java.sql.SQLException or SQLRecoverableException
                    |
                    +-- ORA-12514 / ORA-01017 / ORA-17002 / ...
                            |
                            +-- socket / DNS / TLS errors if present
```

This is an illustrative hierarchy: not every exception carries all of these layers. A generic message such as `Failed to obtain JDBC Connection` is **not enough** to conclude the network is broken. You must inspect **cause/next exceptions**, the vendor code from `SQLException.getErrorCode()`, `SQLState`, and driver messages.

Information to record during investigation includes timestamp, environment, application/release version, redacted hostname/port/service name, ORA or TNS code, JDBC error code/`SQLState`, whether other sources can connect, and recent changes. Never record passwords, tokens, wallets, or full URLs if a URL contains secrets.

## 2. Oracle Connection Flow: Where Can Errors Occur?

For an application connecting via Oracle JDBC Thin, the path looks like this:

```text
Application / SQL client
       |
       |  (1) Read connect descriptor: host, port, service, or TNS alias
       v
Name resolution and network path (DNS, routing, firewall, TCP)
       |
       |  (2) Reach listener or Oracle Net endpoint
       v
Oracle listener
       |
       |  (3) Identify service and route to matching instance/PDB
       v
Oracle database server/session
       |
       |  (4) Verify auth mechanism, username, password,
       |      account status; check session-creation privilege
       v
Session established
       |
       |  (5) Execute SQL/PLSQL with object privileges
       v
Queries, transactions, results
```

In systems using **TCPS/TLS**, certificate verification, wallets, and encryption configuration also participate during connection setup; failures here must not be mislabeled as "wrong database password." With Oracle RAC, Data Guard, redirected services, or cloud managed databases, routing is more complex, yet this phase-by-phase breakdown remains just as effective.

| Phase | Question to Answer | Common Related Symptoms/Codes |
|---|---|---|
| Reading connection target | Was the TNS alias or connect descriptor resolved properly? | `ORA-12154` |
| Network and listener | Are host/port reachable and is the listener up? | `ORA-12541`, `ORA-12545`, timeouts like `ORA-12170` |
| Service/SID routing | Does the listener know the requested service/PDB or SID? | `ORA-12514`, `ORA-12505` |
| Session/resource allocation | Can the server allocate a handler/session? | `ORA-12516`, `ORA-12519`, occasionally session/process limit errors |
| Authentication | Are the account and login mechanism valid? | `ORA-01017`, `ORA-28000`, `ORA-28001`, `ORA-28040` |
| Authorization | Does the user have `CREATE SESSION` and object privileges? | `ORA-01045`, `ORA-01031`, sometimes `ORA-00942` |
| Post-connection | Was the session dropped mid-query or mid-transaction? | `ORA-03113`, `ORA-03114`, context-dependent network errors |

**An error code describes what Oracle or the driver observed, not necessarily one single root cause.** For example, a timeout may come from a firewall, overload, an unresponsive endpoint, or security checks; you still need logs and tests from where the application actually runs.

## 3. Connectivity Errors: Before Oracle Checks Username/Password

### 3.1. `ORA-12154` – Cannot Resolve Connect Identifier

Example:

```text
ORA-12154: TNS:could not resolve the connect identifier specified
```

Typically the Oracle Net client could not find or resolve the alias/connect string into a valid connect descriptor. Checks to run:

- Is the alias or `SERVICE_NAME` spelled properly? Was an alias name (`ORCL_DEV`) confused with a service name (`app_dev_service`)?
- Is the tool reading the intended `tnsnames.ora`, `sqlnet.ora`, `TNS_ADMIN` setting, or Oracle client configuration?
- Is there a syntax error in the connect descriptor or Oracle Net config path?
- If using Easy Connect, is `//host:port/service` formatted properly?

Do not start by resetting passwords: this failure happens before Oracle can authenticate the user. When using an alias, `tnsping <alias>` can test Oracle Net resolution and listener reachability, though it does not verify login or query execution.

### 3.2. `ORA-12541` – No Listener Found at Endpoint

Example:

```text
ORA-12541: TNS:no listener
```

Usually no listener is accepting connections at the requested address/port, or the network path produces an equivalent refusal. Verify host, port, environment, listener status, and bind endpoint configuration. For example, the app switched to a new port while network config still points to the old one.

On Windows, you can run a **basic TCP check**:

```powershell
Test-NetConnection -ComputerName oracle-dev.example.internal -Port 1521
```

`TcpTestSucceeded: True` proves only that a TCP connection could be established to that address/port at test time; it **does not prove the Oracle service is right, the account is valid, or the app can run queries**. If TCP fails, check DNS, routing, firewalls, the listener, and network segmentation. Use your actual assigned host/port rather than treating the example above as a real endpoint.

### 3.3. `ORA-12545`, `ORA-12170`, `ORA-12535` – Unreachable Target or Timeout

Common messages:

```text
ORA-12545: Connect failed because target host or object does not exist
ORA-12170: TNS:Connect timeout occurred
ORA-12535: TNS:operation timed out
```

`ORA-12545` suggests a problem with the target hostname/address or reaching it; check DNS, hostname, routing, descriptor settings, and reachability to the exact endpoint. `ORA-12170`/`ORA-12535` report that a wait limit expired, though the specific cause could be an unresponsive network hop, an overloaded listener/database, or slow/failing security negotiation.

You must test from **the exact host/container/pod running the application**, or somewhere sharing the same network and egress policy. A developer's laptop reaching the database does not prove an application in Kubernetes or a CI runner can reach it.

Never treat every timeout by cranking timeouts up drastically. If the endpoint is wrong or firewalled, longer timeouts only make users wait longer and exhaust connection pools.

### 3.4. `ORA-12514` – Listener Does Not Know Requested Service

Example:

```text
ORA-12514: TNS:listener does not currently know of service requested in connect descriptor
```

The client reached a listener, yet the listener did not recognize the declared **service name** at that moment. This is an **Oracle service-routing error**, not proof that the username/password is wrong. Common possibilities to check:

- The URL has a typo in the service name or points to the wrong environment/PDB.
- The PDB is closed or the application service has not been started/registered properly.
- Listener/service registration is out of sync after a restart, switchover, or config change.
- The client is reaching a different listener than expected due to DNS, routing, or a multi-address connect descriptor.

Example connecting by service name with JDBC Thin:

```text
jdbc:oracle:thin:@//oracle-dev.example.internal:1521/app_dev_service
```

On a server with admin privileges, a DBA can inspect registration via `lsnrctl services`, check PDB status, and inspect Oracle services. In managed database services, equivalent details must usually be obtained through provider tooling/support; never assume applications have permission to run `lsnrctl`.

### 3.5. `ORA-12505` – Listener Does Not Know Requested SID

Example:

```text
ORA-12505: TNS:listener does not currently know of SID given in connect descriptor
```

This error involves a connection requesting a **SID** unknown to the listener. Distinguish the two identifier styles:

```text
# JDBC Thin using service name (common with PDBs)
jdbc:oracle:thin:@//db.example.internal:1521/app_service

# Legacy JDBC Thin identifying by SID
jdbc:oracle:thin:@db.example.internal:1521:ORCL
```

In multitenant architecture, applications normally connect using the **PDB's service name**, never substituting an instance SID for a service name. Obtain the exact connect descriptor from the DBA; never swap `/` for `:` as a quick guess.

### 3.6. `ORA-12516`, `ORA-12519` – Listener Knows Target, No Suitable Handler Available

Example:

```text
ORA-12516: TNS:listener could not find available handler with matching protocol stack
ORA-12519: TNS:no appropriate service handler found
```

This group involves the listener's ability to hand the request off to a matching handler/server process. Common scenarios to analyze include traffic spikes, process/session limits, instance state, service registration, or requested server mode. `ORA-00018`/`ORA-00020` may also appear when hitting database session/process limits depending on context.

Developers check pool connection counts, app replica counts, connection leaks, and retry storms; DBAs check instance state, resource limits, and handlers; operations correlates scale/release timestamps. Never assume "raising `PROCESSES`" is the sole fix; if an app leaks or opens unbounded connections, the failure will return.

### 3.7. `ORA-17002` and JDBC I/O Errors

In JDBC Thin, you may encounter messages like:

```text
java.sql.SQLRecoverableException: IO Error: The Network Adapter could not establish the connection
... Error Code: 17002
```

`17002` is an Oracle JDBC error code indicating a driver-level I/O failure. It **does not by itself distinguish** DNS, firewalls, wrong host, stopped listener, closed socket, or TLS errors. Read the nested cause exception—such as `UnknownHostException`, `ConnectException`, `SocketTimeoutException`, or an SSL error—and check the endpoint and network.

Even when seeing `SQLRecoverableException`, never retry endlessly: the connection may remain unrecoverable until config or the database is fixed. For in-flight write transactions, verify whether the server committed before the link broke; retrying writes requires idempotency or reconciliation.

## 4. Authentication Errors: Reached Login, Identity Rejected

### 4.1. `ORA-01017` – Username/Password Rejected

Example:

```text
ORA-01017: invalid username/password; logon denied
```

This is the classic symptom of an **authentication error**, distinct from `ORA-12514` or `ORA-12541`. However, "invalid username/password" does not always mean someone mistyped a character. Check:

- Were the username, password, and secret version injected into the right environment?
- Is the application reaching **the right PDB/service** containing that account? A valid DEV user might not exist in TEST/PROD.
- Was the password recently rotated while some replicas, CI secrets, or connection pools still hold old credentials?
- Was the account created as a case-sensitive quoted identifier, or does the client transform username casing unexpectedly?
- Does the password contain special characters mangled by a shell, config file, URL, or secret template? Never print passwords to logs to verify.
- Is authentication password-based, external, wallet, proxy, or another mechanism? Do client and server configs agree?

To isolate, keep the endpoint unchanged and test with **an authorized Oracle tool** using the same identity (entering the password via secure prompt) from an equivalent network source. Never spam password guesses: profile policies can lock the account after repeated failures.

### 4.2. `ORA-28000` – Account Is Locked

```text
ORA-28000: the account is locked
```

Oracle rejects the login because the account is locked. Causes include exceeding failed-login limits in the password profile, manual locking by a DBA, or other security policies. The DBA/admin checks `ACCOUNT_STATUS`, root cause, and unlock procedures. **Never repeatedly unlock the account** while the app is still sending the old password: it will simply lock again until you stop the bad-login source or retry loop.

### 4.3. `ORA-28001` – Password Has Expired

```text
ORA-28001: the password has expired
```

This is a credential-lifecycle issue. Resolution typically involves rotating/updating the password per policy, updating the secrets manager, and ensuring all workloads pick up the new version. `ORA-28002` warns that **the password will expire soon**; in many contexts connections still succeed, yet it is an urgent warning to rotate early—not a TCP connection error.

### 4.4. `ORA-28040` – No Matching Authentication Protocol

```text
ORA-28040: No matching authentication protocol
```

This code typically indicates an **authentication protocol/mechanism mismatch** between the client and Oracle server or configured security policy. DBAs and developers should check JDBC/Oracle client version, database authentication policies, account definitions, and security settings. Do not misread this as "wrong password" and reset passwords indiscriminately; avoid downgrading security settings just to force a connection without evaluating risks and client upgrade options.

### 4.5. Authorization: `ORA-01045`, `ORA-01031`, `ORA-00942`

```text
ORA-01045: user ... lacks CREATE SESSION privilege; logon denied
ORA-01031: insufficient privileges
ORA-00942: table or view does not exist
```

- `ORA-01045` occurs at the **session-creation privilege** boundary, when the user identity is recognized yet lacks `CREATE SESSION`.
- `ORA-01031` occurs when Oracle denies an operation for lack of privileges; it can involve SQL, DDL, or procedures.
- `ORA-00942` can mean the object truly does not exist, the schema/synonym is wrong, or the user lacks privileges to see/access it. Never assume the user entered a wrong password.

For example, suppose an application logs in cleanly and runs `SELECT * FROM orders`, yet Oracle returns `ORA-00942`. Investigate **the schema owning `ORDERS`, the SQL statement, synonyms, and required grants**—stop checking the listener. For cross-schema access, direct schema grants or appropriate privileges must be approved by the DBA/data owner; granting `DBA` to fix it is excessive.

## 5. Transport Security Errors Differ from Oracle Password Errors

Some environments mandate **TCPS/TLS**, certificate verification, Oracle wallets, or mTLS. When transport security settings mismatch, the Oracle client can fail **before** password login even happens.

| Error Code / Area | Diagnostic Direction | What to Check |
|---|---|---|
| `ORA-29024` | Certificate validation failed | Trust chain, server hostname, cert expiration, CA, and approved TLS config |
| `ORA-28759` | Could not open required wallet file/source | Path, file permissions, wallet distribution, and client configuration |
| `ORA-12638` | Credential retrieval failed in an auth mechanism | Credential provider/external auth, client config, and runtime environment |
| `SSLHandshakeException` in JDBC | TLS handshake failed | Truststore/wallet, certificate, protocol version, involved proxy/load balancer |

Exact codes depend on Oracle Net and JDBC configuration. Avoid disabling certificate checks, turning off encryption, or falling back to plain TCP as a "quick fix" in security-mandated systems. Fix the root cause in line with approved configuration and policy.

## 6. Quick Lookup Table: Which Code Calls Which Team?

| Code / Symptom | Priority Area | First Thing to Check | Teams Usually Involved |
|---|---|---|---|
| `ORA-12154` | Client/identifier config | Alias, `tnsnames.ora`, `TNS_ADMIN`, Easy Connect | Developer / operations |
| `ORA-12541` | Listener / network | Host, port, TCP, listener endpoint | Operations / DBA |
| `ORA-12545` | Host / route | DNS, target address, connectivity from runtime | Operations |
| `ORA-12170`, `ORA-12535` | Timeouts | Timeout thresholds, routing, firewall, load, and server response | Operations / DBA |
| `ORA-12514` | Service routing | Service name, PDB status, listener registration | DBA / operations |
| `ORA-12505` | SID routing | Whether connection uses SID vs. service; whether SID/service exists | DBA / developer |
| `ORA-12516`, `ORA-12519` | Handler / resources | Session/process/handler limits, pool, and load | DBA / developer |
| JDBC `17002` | Client-side I/O | Nested exception and TCP/TLS target | Developer / operations |
| `ORA-01017` | User/password auth | Secret, user, target PDB/service, credential changes | Developer / DBA |
| `ORA-28000` | Account locked | Account status, source of failed logins, retries | DBA / app owner |
| `ORA-28001` | Password expired | Expiry policy and secret-rotation pipeline | DBA / app owner |
| `ORA-28040` | Auth protocol | Client/driver version and auth policies | DBA / developer |
| `ORA-01045` | Session privilege | User's `CREATE SESSION` grant | DBA |
| `ORA-01031`, `ORA-00942` | Post-login grants or schema | Object owner, grants, SQL text, current schema | Developer / DBA |
| `ORA-29024`, wallet/TLS errors | Transport security | Certificate/wallet/trust config | Operations / DBA |
| `ORA-03113`, `ORA-03114` | Session/communication during or after connect | Disconnect timestamp, database/network logs, transaction | DBA / operations / developer |

This is an **investigation routing table**, not a claim that each code has only one cause or that one team is authorized to perform every action.

## 7. Step-by-Step Diagnostic Workflow for "Cannot Connect to Oracle"

### Step 1 – Capture the Root Error Code and Scope

Record a few useful fields:

```text
Environment: TEST
Application: order-api
Release: 2026.11.x
Time: 14:25 +07
Error: ORA-12514
Database target: test-db.internal:1521 / order_test_service
Impact: all pods after rollout; other apps unknown
Recent change: service name configuration updated
```

This is an illustrative example containing no credentials. Answer: does the error hit **every replica** or only one node? One environment or all? During startup, borrowing from the pool, running a specific query, or mid-transaction? Intermittent failures on a few connections require a different investigation path from every connection being rejected.

### Step 2 – Check the Connect Descriptor; Don't Confuse SID with Service

With JDBC Thin, the common syntax is:

```text
jdbc:oracle:thin:@//<host>:<port>/<service_name>
```

Example:

```text
jdbc:oracle:thin:@//oracle-test.example.internal:1521/order_test_service
```

Cross-check host/port/service provided by the DBA, the actual configuration after secrets/configs are injected, application profiles, and recent deployment diffs. Two places sharing a hostname do not automatically land in the same PDB; two different URLs can also reach the same database if mapped wrongly. Never screenshot or share configs containing passwords.

### Step 3 – Check Hostname, Network, and Listener from the Application's Location

If the code points to network/listener, start with DNS/routing/port from the machine running the app. On Windows, test TCP with `Test-NetConnection`; on Linux or containers, use approved network tools. On the DBA side, inspect listener service registration and PDB/instance status with authorized admin tools.

**Interpret results carefully:**

- Hostname fails to resolve: check DNS and runtime config.
- TCP fails to open: check firewall, routing, port/listener, server state.
- TCP opens yet `ORA-12514`: service/PDB/registration is wrong or not ready.
- Reaches database yet `ORA-01017`: move to authentication and target PDB/user.

A passing network check does not bypass authentication; an auth message does not mean every other endpoint is healthy.

### Step 4 – Test Login Using a Trusted Client

From a host permitted to reach Oracle, you can use SQL*Plus to verify connectivity in **the matching environment**:

```text
sqlplus -L app_reader@//oracle-test.example.internal:1521/order_test_service
```

When prompted, enter the password interactively or via an approved secure mechanism. **Never** embed passwords on the command line or paste secret-containing output into chats/tickets. Depending on environment policy, repeated failed logins can lock the account; test only with permission and limit attempts.

Compare client test results against the application:

| Observation | Diagnostic Direction |
|---|---|
| Both SQL*Plus and app hit `ORA-12514` on same target | Prioritize checking service/listener/PDB |
| SQL*Plus connects, app hits `ORA-12541` | Check differing network paths, configured host/port, DNS, or runtime env |
| Both client and app hit `ORA-01017` on same account/PDB | Check secret, user status, and auth method |
| Client succeeds, app hits `ORA-01017` | Compare injected secret, username, service/PDB, client/driver auth, rotation |
| Same user logs in yet query hits `ORA-00942` | Connectivity/auth succeeded; move to schema/privileges/object |

### Step 5 – Once Logged In, Verify the Exact Database/PDB

Run this read-only query from a standard-privilege session:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

`SESSION_USER` confirms the authenticated login identity; `CURRENT_SCHEMA` is the schema used to resolve unqualified object names and can be changed for a session. It **grants no extra privileges** and need not match `SESSION_USER`. In Oracle multitenant, `CON_NAME` confirms the active PDB. Compare against expected environment values rather than trusting an alias name on a laptop.

### Step 6 – For Authentication Errors, Check Account Status via Admin Channels

A DBA or authorized administrator can inspect account status, e.g.:

```sql
-- Only for accounts authorized to view DBA_USERS.
SELECT username, account_status, lock_date, expiry_date
FROM dba_users
WHERE username = 'APP_RUNTIME';
```

This illustrative query targets a standard unquoted username; match real casing/names accurately. Output distinguishes `OPEN`, `LOCKED`, `EXPIRED`, and combined states. Developers normally do not need `SELECT` on `DBA_USERS`; ask the DBA to check without granting admin rights to application accounts.

If the account is locked, find whatever is sending the old password or retry loop; if the password expired, execute rotation; if `ORA-28040`, verify driver protocol compatibility. Never grant `SYSDBA`, disable password policies, or hand out broad privileges just to test connectivity.

### Step 7 – Re-Verify After Fixing and Save Evidence

After applying a valid config fix, verify **the exact issue is resolved**: new sessions connect to the target service/PDB, the app executes a safe read-only query or smoke test, the connection pool stops throwing errors, and error rates/latencies return to normal. Record timestamp, change made, results, and owner. If a network fix changes the error into `ORA-01017`, that is evidence traffic now passes connectivity and reached authentication—not that the network fix failed.

## 8. Java Example: Extracting Vendor Code and Cause from `SQLException`

Oracle JDBC exposes **numeric vendor error codes**, `SQLState`, and exception chains. Outer Spring/Hibernate wrappers can hide `SQLException`, so logging must preserve the underlying cause securely.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class OracleConnectionProbe {
    public static void main(String[] args) {
        String url = System.getenv("ORACLE_JDBC_URL");
        String user = System.getenv("ORACLE_DB_USER");
        String password = System.getenv("ORACLE_DB_PASSWORD");

        if (url == null || user == null || password == null) {
            System.err.println("Missing Oracle connection configuration");
            return;
        }

        try (Connection connection = DriverManager.getConnection(url, user, password)) {
            System.out.println("Oracle connection established");
        } catch (SQLException error) {
            SQLException current = error;
            while (current != null) {
                int code = current.getErrorCode();
                System.err.printf(
                    "SQL vendor code=%d, SQLState=%s, category=%s%n",
                    code,
                    current.getSQLState(),
                    classify(code)
                );
                current = current.getNextException();
            }
            // In production systems, log the cause chain through controlled logging
            // to avoid exposing secrets or sensitive details.
        }
    }

    private static String classify(int code) {
        return switch (code) {
            case 12154, 12541, 12545, 12170, 12535, 12514, 12505 -> "CONNECTIVITY";
            case 1017, 28000, 28001, 28040 -> "AUTHENTICATION";
            case 1045, 1031, 942 -> "AUTHORIZATION_OR_SCHEMA";
            case 17002 -> "JDBC_IO_NEEDS_CAUSE";
            default -> "CHECK_FULL_CONTEXT";
        };
    }
}
```

This illustrative snippet requires the Oracle JDBC driver on the classpath and valid environment settings. It **classifies errors for diagnostics**, without fixing failures automatically or claiming to cover every case. In real systems, Spring pools, Hibernate, and application code can wrap errors across multiple `Throwable` layers; capture the cause chain and relevant metadata without logging full configs, passwords, credentials, wallets, or queries containing sensitive data.

For `ORA-17002` or a `SQLRecoverableException` lacking a clear Oracle code, `getCause()` may contain `UnknownHostException`, `ConnectException`, timeouts, or SSL exceptions. Therefore, **never inspect only a couple of numbers while ignoring the stack trace**. `SQLState` also helps group errors, yet `SQLState` mappings can differ across driver versions and failure paths; avoid building business logic solely on `SQLState`.

### 8.1. Java/Spring Boot Application Config Example

```yaml
spring:
  datasource:
    url: ${ORACLE_JDBC_URL}
    username: ${ORACLE_DB_USER}
    password: ${ORACLE_DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
```

DEV, TEST, and PROD each require dedicated URLs, users, and secrets. Configuring via environment variables is illustrative; production apps should use the platform's secrets management and proper secret-read permissions. When debugging, log only **environment name, sanitized service/host, and error code**; never print password-bearing variables or sensitive truststore/wallet values.

## 9. Three Real-World Investigation Scenarios

### Scenario A – After Deployment, Every Pod Reports `ORA-12514`

The app connected reliably beforehand. After a release updating `ORACLE_JDBC_URL`, all replicas report `ORA-12514`. From the same network, TCP to the listener port succeeds; no invalid-password error appears.

1. Developers compare the deployed URL against documented service details to spot typos or wrong-environment targets.
2. Operations checks config injection, DNS/routing, and deployment diffs.
3. DBAs confirm the PDB/service is running and registered with the listener.
4. After correcting the target, run connection and read-only smoke tests and monitor error rates.

Classification conclusion: **connectivity / service-routing error**. Rotating passwords or granting extra privileges will not fix the root cause.

### Scenario B – Network Works, Then `ORA-01017` Followed by `ORA-28000`

Following password rotation, one old replica still uses the previous secret version. That replica repeatedly opens new sessions and hits `ORA-01017`; after several failures, the account locks so healthy replicas now hit `ORA-28000` as well.

1. Operations identifies which replica/deployment generates failed logins and pauses retry loops per runbook.
2. Developers verify injected configs match the newly rotated secret version without printing passwords.
3. DBAs check account status and relevant audits, unlocking only after the bad-login source is stopped.
4. Roll all replicas onto the valid credential, verify fresh connections, and monitor for errors.

Classification conclusion: **authentication / credential lifecycle**. Listener and TCP may be completely healthy. Simply unlocking the account without stopping the stale-credential sender makes the lockout recur.

### Scenario C – Login Succeeds, Query Fails with `ORA-00942`

The application connects to the right PDB and user. `SELECT 1 FROM dual` succeeds, yet querying a business table raises `ORA-00942`.

1. Developers check table name, schema owner, release migrations, and whether the query qualifies the owner.
2. DBAs/schema owners verify the object exists and required grants are in place; check if a synonym is expected.
3. Re-test the exact SQL using the runtime account—never using a DBA account that masks permission differences.

Classification conclusion: **post-authentication schema/privileges**. Changing ports, listeners, or passwords will not address the cause.

## 10. When Connection Succeeds Yet the Session Drops

"Connection error" can also refer to an active session closing abruptly. Example:

```text
ORA-03113: end-of-file on communication channel
ORA-03114: not connected to ORACLE
```

These codes do not directly indicate right or wrong passwords; the session may have been severed by a server-process crash, network drop, infrastructure config, restart/failover, timeout, or client/server fault. Collect application logs, request timestamps, Oracle alert/trace logs with DBA support, restart/failover events, and network metrics together. With connection pools, check validation/eviction and how the app handles invalidated connections.

**Especially for write transactions:** losing the connection after sending `COMMIT` can leave the client unsure whether the transaction committed on the server. Never auto-retry a payment/transfer merely because of a transport drop. You need business-level identifiers, idempotency, reconciliation, or transaction-recovery patterns suited to your architecture.

## 11. Controlled Error-Classification Practice

Exercises should run in **authorized DEV/TEST environments**, never intentionally inducing errors in production or on accounts with strict lockout rules. Never alter listeners, PDBs, firewalls, or system passwords just to reproduce failures without authorization and a plan.

### Exercise 1 – Predict the Phase of Failure

Given a valid JDBC URL to `dev-db.example.internal:1521/dev_service`, for each change below identify **which phase is likely affected**, without needing to predict one single exact code:

| Hypothetical Change | Phase to Investigate |
|---|---|
| Wrong alias name in `tnsnames.ora` | Connect identifier resolution |
| Pointing to a port with no listener | Network / listener |
| Right host/port, wrong service name | Service routing |
| Right service, stale secret injected into app | Authentication |
| User recognized yet lacks `CREATE SESSION` | Session-creation authorization |
| User logs in yet lacks read grant on `ORDERS` | SQL execution privileges / schema |

### Exercise 2 – Using the Same Post-Login Check

If you have two Oracle environments (DEV/TEST) and read-only accounts, connect to each and run:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

Record **environment, expected target, and actual output** (without capturing secrets), then explain why merely seeing an app declare a `test` profile does not guarantee it connects to TEST. If environments reside in separate PDBs, compare `CON_NAME`; if standalone databases, also verify endpoints/database identifiers provided by the DBA.

### Exercise 3 – From Logs to First Action

No real errors need to be induced. Classify these four hypothetical messages yourself:

```text
A. ORA-12541: TNS:no listener
B. ORA-01017: invalid username/password; logon denied
C. ORA-12514: listener does not currently know of service requested
D. ORA-01031: insufficient privileges
```

- **A:** verify host/port and listener from the application's network source.
- **B:** verify account, secret version, service/PDB, and auth mechanism; limit login retries.
- **C:** check service name, listener registration, and PDB status; do not reflexively rotate passwords.
- **D:** identify the rejected operation and required privilege; inspect using the runtime user, not a DBA account.

Your exercise notes should capture at least three facts: original error code, **connection phase**, and **evidence-backed diagnostic step**. Any subsequent production remediation follows organizational access policies and runbooks.

## 12. Common Mistakes When Reading ORA Errors

| Faulty Reasoning | Why It Is Wrong | Better Approach |
|---|---|---|
| "Can't log in, so the password must be wrong." | Alias resolution failure, wrong service, or down listener all block before authentication. | Read the error code and pinpoint the exact phase. |
| "TCP port 1521 is open, so Oracle is fine." | TCP checks neither service/PDB, credentials, nor SQL privileges. | Verify service, login, and a read-only query step by step. |
| "`ORA-12514` means the user doesn't exist." | Listener does not know the service; user check wasn't reached yet. | Verify service, registration, and PDB state. |
| "`ORA-01017` always means a mistyped password." | Could be wrong PDB, stale secret, different username, or different auth config. | Verify identity, target, and secret lifecycle. |
| "Granting `DBA` to the app will fix errors." | High privileges don't fix network/service/auth and create severe risk. | Grant least privilege for the exact operation after finding root cause. |
| "`ORA-00942` means Oracle isn't connected." | Error occurs when a SQL query fails to find/access an object. | Check schema, migrations, and grants. |
| "Driver reports `17002`, so change the password." | An I/O error does not imply auth failure. | Read the nested exception and check socket/DNS/TLS. |
| "Just keep retrying until it works." | Can lock accounts, overload the DB, or duplicate writes. | Use bounded retries, classify errors, and enforce idempotency. |
| "It works from my laptop, so the pod will work too." | Each source has different networking, DNS, secrets, and policies. | Test from an environment sharing the workload's network path and config. |
| "Turning off TLS is the fast way to fix cert errors." | Destroys server identity verification and transport protection. | Fix trust, wallet, or certificates per policy. |

## 13. Collaborative Troubleshooting and Handoff Information

Connection failures often require **developers, DBAs, and operations** working together because each observes different layers:

| Team | Key Evidence / Responsibilities |
|---|---|
| Developer | Sanitized JDBC URL, driver version, stack/cause chain, connection pool state, error timestamps, retry behavior, recent code and migrations |
| DBA | PDB/service/listener state, session/handler/resource usage, user/privilege status, Oracle alert/trace logs, and auth policies |
| Operations | DNS, routing, firewalls, ports, secret injection, deployment changes, TLS/certificates, metrics/alerts, blast radius, and incident coordination |

A helpful ticket can be written like this:

```text
Environment: TEST
Component: inventory-api / build 47
When: 2026-11-14 10:20 +07
Observed error: ORA-01017 (JDBC vendor code 1017)
Target (sanitized): test-db.internal:1521 / inventory_test_service
Scope: 2/4 pods after secret rotation
Network: port reachable from affected pods
Recent changes: credentials rotated; deployment still rolling
Requested action: verify injected secret versions and account status
Do not include: password, token, wallet, unredacted connection URL
```

This directs troubleshooting immediately to credentials/deployment instead of blaming the listener. If the code turns into `ORA-28000`, flag potential account lockout right away and consider pausing retries to avoid worsening the incident.

## 14. Remembering How to Read ORA Codes

When encountering an Oracle error, follow this order: **read the root code → identify the failing phase → verify connection target → test from the app's source → move to credentials/privileges once connectivity is proven → re-verify with a session and safe query**.

Core distinctions:

- **`ORA-12154`, `ORA-12541`, `ORA-12514`, timeouts:** prioritize investigating Oracle Net config, network paths, listener/services, and connection resources.
- **`ORA-01017`, `ORA-28000`, `ORA-28001`:** prioritize investigating identity, secrets, account status, and password lifecycle.
- **`ORA-01045`, `ORA-01031`, `ORA-00942`:** investigate session-creation grants or SQL execution privileges/schemas.
- **`ORA-17002`, TLS errors, `ORA-03113`, and generic driver errors:** read the full exception/cause chain and context before concluding root cause.

Recognizing the exact failure layer guides you toward high-value checks, eliminates guesswork configuration edits, and protects production Oracle systems from unfounded fixes.
