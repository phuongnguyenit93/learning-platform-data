# SCRAM Password Authentication and Secret Management

When a Java application connects to PostgreSQL, it normally proves its identity via a *login role* and an authentication method selected by the server. In password-based environments, **SCRAM-SHA-256** is PostgreSQL's modern authentication mechanism, designed to avoid transmitting the raw password directly over the wire during authentication while letting the server store a derived **password verifier** instead of the plaintext password.

However, switching from `md5` to `scram-sha-256` **does not automatically make a system secure**. A solid configuration must simultaneously account for **TLS**, server identity verification, `pg_hba.conf`, password strength, role privileges, how secrets are delivered to the application, credential rotation lifecycles, connection pooling, logs, backups, and secret-compromise response.

For example, a system might use SCRAM yet remain vulnerable if passwords are hard-coded in the repository, printed in logged JDBC URLs, or shared via one database superuser across every microservice. Conversely, an application with strong secret management can still be exposed by a misconfigured `pg_hba.conf` permitting unintended authentication methods.

This lesson belongs to the **Security** chapter of the *Database Engine Relational PostgreSQL* module. Its goal is to explain SCRAM accurately, configure password-based connections securely, establish secret-management workflows, and diagnose common deployment failures.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **authentication**, **authorization**, and **transport security**.
2. Explain the SCRAM-SHA-256 challenge–response mechanism conceptually.
3. Understand why PostgreSQL stores a verifier rather than needing the raw password to authenticate SCRAM.
4. Distinguish SCRAM-SHA-256 from SCRAM-SHA-256-PLUS and TLS channel binding.
5. Use `password_encryption` and `pg_hba.conf` within their proper scopes.
6. Create least-privilege login roles and set passwords using tools that avoid exposing secrets in SQL history.
7. Understand how `libpq`, `psql`, JDBC, and connection pools consume secrets.
8. Recognize common password-leak vectors: source code, command lines, connection URIs, environment variables, logs, and CI artifacts.
9. Design workflows for **secret rotation**, privilege updates, account disabling, and session revocation.
10. Inspect safe status metadata without printing password verifiers.
11. Troubleshoot SCRAM, TLS, role, database, and permission errors.
12. Decide when to use SCRAM versus other identity mechanisms.

## 2. Three Distinct Protection Layers

~~~text
Application / psql / JDBC
          |
          v
 [1] TRANSPORT SECURITY
      TLS, CA, hostname verification,
      optional channel binding
          |
          v
 [2] AUTHENTICATION
      Which PostgreSQL role is it?
      Which method does pg_hba.conf select?
      SCRAM/password/cert/...
          |
          v
 [3] AUTHORIZATION
      Does the role have DB CONNECT?
      Does it have schema USAGE?
      Does it have table SELECT/INSERT/UPDATE?
      Does RLS filter rows?
~~~

### 2.1. Authentication: Who Is Connecting?

PostgreSQL checks whether the client can authenticate as a login role such as `app_orders`. SCRAM belongs to the **authentication layer**.

### 2.2. Authorization: What Are They Allowed to Do?

Even after authenticating successfully, a role may lack access to tables or functions. Privileges are governed by `GRANT`, `REVOKE`, ownership, role membership, RLS, and related controls.

### 2.3. Transport Security: Is Traffic Protected Over the Network?

TLS encrypts and authenticates the transport channel when configured—especially when the client verifies the CA chain and server hostname. SCRAM **does not replace TLS** for SQL traffic and query results after login.

### 2.4. First Key Takeaway

Never conflate these three concepts:

- **Valid SCRAM** does not prove the TLS channel was verified.
- **Valid TLS** does not prove the role holds only necessary privileges.
- **A least-privilege role** does not fix a password leaked in CI logs.

Security is the combination of all three layers plus operational discipline.

## 3. What Is SCRAM?

**SCRAM** stands for *Salted Challenge Response Authentication Mechanism*. PostgreSQL supports **SCRAM-SHA-256** for password authentication.

Core idea:

- The client holds or fetches the password from secret storage.
- The server stores a password verifier derived from the password alongside parameters such as a salt and iteration count.
- On connect, both sides run challenge–response exchanges proving knowledge of the matching secret.
- The client **does not send the plaintext password directly** as a cleartext auth message.
- The server verifies the client, and the client can verify proof that the server holds matching authentication data.

### 3.1. Why Not Simply Send Passwords Over TLS?

TLS protects the transport channel, while SCRAM avoids transmitting plaintext passwords inside the authentication exchange and stores salted, work-factor-derived verifiers. The two layers complement each other; they are not mutually exclusive.

### 3.2. SHA-256 Here Is Not a Single Raw Hash

Do not imagine the database merely stores `SHA256(password)`. SCRAM runs a key-derivation process with a **salt** and iteration count, then computes verifier values used for challenge–response.

### 3.3. What Is the Salt For?

Salting prevents identical passwords from trivially yielding identical verifiers and defeats shared precomputed hash tables. Salting **does not replace strong passwords**.

### 3.4. What Are Iterations For?

Key derivation adds a work factor, raising the cost of guessing passwords offline from leaked data. Still, attackers with access to verifiers and compute resources can attempt offline guessing; strong passwords and protecting auth metadata remain vital.

## 4. Conceptual Challenge–Response Flow

~~~text
CLIENT                                   POSTGRESQL
  |                                           |
  |------ Connection request, user/db ------->|
  |                                           |
  |<----- Server picks SASL mechanisms -------|
  |        SCRAM-SHA-256 [+ PLUS]             |
  |                                           |
  |------ Client-first, nonce --------------->|
  |                                           |
  |<----- Server-first: nonce + salt + i -----|
  |                                           |
  |  Client derives keys from password        |
  |  Builds client proof                      |
  |                                           |
  |------ Client-final + proof -------------->|
  |                                           |
  |  Server validates proof against verifier  |
  |                                           |
  |<----- Server-final signature -------------|
  |                                           |
  | Client verifies server signature          |
  |                                           |
  |======= Authenticated SQL session =========|
~~~

This diagram illustrates the exchange of proofs, nonces, salts, and signatures; it is **not** a complete byte-level SASL specification.

### 4.1. Nonce

Per-session random values included in the handshake to protect against replay attacks per protocol design.

### 4.2. Client Proof

The client computes a proof from the password and exchange transcript; the server verifies it using the stored verifier without needing the plaintext password.

### 4.3. Server Signature

The client validates the server's authentication response under SCRAM. This does not automatically replace TLS certificate and hostname verification over the network.

### 4.4. Do Not Mistake the Handshake for Full Session Encryption

After authentication, SQL traffic still needs TLS to protect query text, results, personal data, and other application payloads.

## 5. Password Verifiers in PostgreSQL

PostgreSQL stores password authentication material for login roles in an appropriate verifier format. For SCRAM, conceptually:

~~~text
SCRAM-SHA-256$iterations:salt$StoredKey:ServerKey
~~~

This sample string shows only the structure; it is **not a valid password or usable verifier**.

### 5.1. Verifiers Differ from Plaintext Passwords

The server does not need to store user passwords in cleartext to validate SCRAM, reducing plaintext exposure risk from server-side auth storage.

### 5.2. Verifiers Are Still Sensitive Data

Anyone who obtains a verifier can mount offline password-guessing attacks or leverage it depending on the threat model. Never place verifiers in logs, dashboards, or support tickets.

### 5.3. Do Not Query pg_authid to "Prove Security"

The `pg_authid` catalog holds sensitive authentication data and has restricted access. Never print `rolpassword` to screens, reports, or screenshots sent to others.

### 5.4. Use pg_roles for Less Sensitive Metadata

The `pg_roles` view lets you inspect role names, `LOGIN` capability, and password expiration without exposing verifiers.

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolvaliduntil
FROM pg_roles
WHERE rolcanlogin
ORDER BY rolname;
~~~

### 5.5. Do Not Confuse a Verifier with Reversible Encryption

A SCRAM verifier is derived authentication material, not a symmetrically encrypted password that can be decrypted back to plaintext.

## 6. SCRAM-SHA-256 and SCRAM-SHA-256-PLUS

When TLS is active and both client and server support it, PostgreSQL can negotiate **SCRAM-SHA-256-PLUS** with **channel binding**.

### 6.1. Standard SCRAM-SHA-256

Challenge–response proving knowledge of the secret corresponding to the verifier.

### 6.2. SCRAM-SHA-256-PLUS

Binds TLS channel parameters into the SCRAM exchange. This helps detect certain *man-in-the-middle* interceptions or intermediate TLS termination where both sides do not share the exact same TLS channel.

### 6.3. Channel Binding Is Not a Decorative TLS Flag

If an app requires `PLUS` while traffic passes through a TLS-terminating proxy or lacks client/server support, authentication can fail. Inspect the actual TLS topology, proxies, and client capabilities.

### 6.4. Do Not Equate PLUS with mTLS

- **SCRAM-PLUS**: password-based authentication bound to the TLS channel.
- **mTLS / client certificate authentication**: the client proves identity with an X.509 certificate and private key under certificate-based authentication.

Both strengthen identity assurance, yet differ completely in credential management.

## 7. TLS Is Still Essential When Using SCRAM

SCRAM avoids sending raw passwords in cleartext during the handshake, but it does not encrypt ongoing application traffic. TLS remains a distinct, necessary layer.

### 7.1. libpq sslmode Levels

Common options include:

| `sslmode` | Concept | Suitable for sensitive production? |
|---|---|---|
| `disable` | No TLS | Generally unsuitable over untrusted networks |
| `allow` | May connect without TLS first | Not an enforced TLS policy |
| `prefer` | Prefers TLS, falls back to unencrypted | Insufficient when encryption is mandatory |
| `require` | Requires TLS | Encrypted; review server verification needs |
| `verify-ca` | TLS + verifies CA chain | Stronger than `require`, skips hostname match |
| `verify-full` | TLS + CA + hostname verification | Usually preferred when proper PKI exists |

### 7.2. Why Does verify-full Matter?

Encrypting traffic to **some arbitrary server** does not guarantee you reached your intended PostgreSQL server. Hostname verification binds the certificate to the expected endpoint.

### 7.3. Server Hostnames and Certificates

If a certificate is issued for `db.example.test`, clients should connect using that DNS name rather than switching to an IP absent from the certificate—unless your PKI and clients properly use IP SANs.

### 7.4. Never Switch to disable Just to "Fix a SCRAM Error"

When TLS verification fails, inspect CAs, SANs/hostnames, chains, and proxies. Disabling TLS hides deployment bugs and weakens security.

## 8. Client-Side Channel Binding

In `libpq`, the `channel_binding` connection parameter commonly accepts `disable`, `prefer`, and `require`, depending on version support.

~~~text
host=db.example.test
dbname=appdb
user=app_orders
sslmode=verify-full
channel_binding=prefer
~~~

### 8.1. prefer

The client uses channel binding whenever supported by negotiation and the TLS layer.

### 8.2. require

The client demands compatible channel binding; if unavailable, the connection fails. Use once the full client–proxy–server path is verified to support it.

### 8.3. disable

Does not request or use channel binding. Never choose it blindly just to bypass an error without investigating the root cause.

### 8.4. JDBC Can Differ from libpq

The PostgreSQL JDBC driver is not `libpq`. Support and parameter names for channel binding, TLS, and certificates vary by driver version. Never copy `libpq` options to JDBC assuming identical behavior.

## 9. pg_hba.conf Selects the Authentication Method

PostgreSQL uses the **Host-Based Authentication** file to define connection rules: connection type, database, user, source address, and authentication method.

Example HBA line:

~~~text
# TYPE    DATABASE     USER             ADDRESS             METHOD
hostssl   appdb        app_orders       10.20.0.0/16        scram-sha-256
~~~

This is a **configuration line in `pg_hba.conf`**, not SQL.

### 9.1. host

Matches TCP/IP connections where supported without requiring TLS.

### 9.2. hostssl

Matches only TCP/IP connections using SSL/TLS. Useful to ensure password rules never serve plaintext TCP connections.

### 9.3. local

Applies to Unix-domain socket connections on supported platforms. This differs from TCP to `127.0.0.1` or `::1`. `local` often uses `peer` authentication depending on policy.

### 9.4. user and database

An HBA rule must match both database and role per supported syntax. An app using multiple databases or roles can hit different rules.

### 9.5. ADDRESS

Represents the connection source as seen by the PostgreSQL server. Behind proxies, VPNs, or NAT, the IP seen by the server may be the proxy IP rather than the end workstation.

## 10. pg_hba.conf Rule: First Match Is Decisive

PostgreSQL evaluates HBA rules **in order**; the first line matching connection type, database, user, and address is chosen. If authentication fails on that rule, PostgreSQL **does not fall through to lower rules as a password fallback**.

~~~text
# Example illustrating dangerous ordering:
host    all     all         10.20.0.0/16     trust
hostssl appdb   app_orders  10.20.0.0/16     scram-sha-256
~~~

If the broad `trust` line matches first, the later SCRAM line never runs for that connection.

### 10.1. Evaluate Specific Rules in Full Context

Do not just append a `scram-sha-256` line and assume all logins use SCRAM. Inspect every rule above it, include files, and broader rules.

### 10.2. trust Is High Risk

`trust` lets matching connections authenticate without verifying a password. That suits only tightly isolated test labs—never broad production use.

### 10.3. reject Explicitly Closes Unwanted Paths

HBA supports `reject` to block specific connection groups explicitly. Ordered incorrectly, `reject` can lock out an entire application; production HBA edits require rollback plans and console access.

### 10.4. IPv4 and IPv6

`127.0.0.1/32` and `::1/128` are separate addresses. Connecting to `localhost` can resolve to IPv6 rather than IPv4, causing you to inspect the wrong rule.

## 11. How scram-sha-256 and md5 Differ in HBA

In PostgreSQL, `pg_hba.conf` can specify:

~~~text
hostssl appdb app_orders 10.20.0.0/16 scram-sha-256
~~~

requiring authentication via SCRAM.

Legacy systems may still contain:

~~~text
hostssl appdb legacy_user 10.20.0.0/16 md5
~~~

### 11.1. md5 Is a Legacy Method

Legacy MD5 password verifiers lack SCRAM's security properties. For modern PostgreSQL deployments, plan a migration to SCRAM rather than building new systems on MD5.

### 11.2. Important Transition Compatibility Behavior

In PostgreSQL versions supporting this behavior, **an HBA `md5` rule can automatically negotiate SCRAM authentication if the role's stored password is already a SCRAM verifier**. This eases migrations, not a reason to keep `md5` in HBA forever.

### 11.3. The Reverse Is Not Equivalent

If HBA requires `scram-sha-256` while the role still holds only an old MD5 verifier, the server cannot authenticate SCRAM against an MD5 verifier as if the formats were interchangeable. Reset the password with `password_encryption = 'scram-sha-256'`.

### 11.4. Check Server Version

PostgreSQL releases evolve support and deprecation for password methods over time. Always verify running server and client versions rather than assuming legacy methods stay supported forever.

## 12. What Does password_encryption Do?

The `password_encryption` parameter determines **how PostgreSQL hashes/derives password verifiers when passwords are set via supported commands**.

~~~sql
SHOW password_encryption;
~~~

Expected value for SCRAM deployments:

~~~text
scram-sha-256
~~~

### 12.1. Does Not Convert Old Passwords

Running:

~~~sql
SET password_encryption = 'scram-sha-256';
~~~

does not scan roles and convert old verifiers to SCRAM. Previously set passwords must be **reset/rotated** to generate new verifiers.

### 12.2. Not an HBA Method Setting

`password_encryption` controls the verifier stored when setting a password, while HBA controls **which authentication method** clients must use on connect. They are related yet independent.

### 12.3. Set It Before Changing Passwords

A normal migration verifies the setting first, resets role passwords, and finally validates HBA and client support.

### 12.4. Never Assume All Environments Match

Dev, CI, and production may differ. Inspect via `SHOW password_encryption` or `pg_settings` instead of guessing from repo config files.

## 13. Setting Passwords in psql Without Putting Plaintext in SQL History

In `psql`, use the meta-command:

~~~text
\password app_orders
~~~

It prompts interactively, avoiding plaintext passwords in literal SQL statements that end up in command history or SQL logs.

### 13.1. Why Avoid Literal PASSWORD?

Avoid using statements like this with real secrets in terminals or migration scripts:

~~~sql
-- NEVER EMBED REAL PASSWORDS IN SQL TEXT
ALTER ROLE app_orders PASSWORD 'production-secret-example';
~~~

The literal text can leak into shell/`psql` history, tooling logs, traces, audit systems, or committed scripts.

### 13.2. \password Requires Appropriate Privileges

A login role can change its own password where allowed; administrators can change other roles' passwords if privileged. Without permission, the command fails.

### 13.3. Never Use Documentation Examples as Real Passwords

Illustrative strings in documentation (like `production-secret-example`) are not secure passwords. In real practice, generate strong random secrets using approved tools—never copy literals.

### 13.4. \password Is Not a Secret Manager

It avoids SQL-literal leaks, but your organization still needs secure secret delivery to apps, safe storage, rotation, auditing, and revocation.

## 14. Creating Dedicated Login Roles Instead of Using postgres

An application should never connect as superuser `postgres` merely to bypass permission errors.

~~~sql
CREATE ROLE app_orders LOGIN;
~~~

Then run `\password app_orders` in `psql` as a suitably privileged role.

### 14.1. LOGIN Is Only Authentication Capability

A role needs `LOGIN` to sign in, which grants zero automatic read/write privileges on application tables.

### 14.2. Superuser Is Vast Authority

Using superuser for a microservice means a SQL injection bug or secret leak can compromise the entire cluster.

### 14.3. One Role per Workload

Split roles by service, environment, and function:

~~~text
app_orders_rw
app_reporting_ro
batch_importer
migration_admin
monitoring_ro
~~~

Separating roles lets you revoke one role with minimal disruption to others and improves auditability.

### 14.4. Not Every Instance Needs Its Own Password

Several models exist: shared role/secret per service pool, one role per service, per-tenant roles, or short-lived identities. Choose based on governance and threat model; avoid creating millions of login roles unnecessarily.

## 15. Least Privilege: A SQL Example

Suppose the application database has schema `sales` and table `sales.orders`.

~~~sql
GRANT CONNECT
ON DATABASE appdb
TO app_orders;

GRANT USAGE
ON SCHEMA sales
TO app_orders;

GRANT SELECT, INSERT, UPDATE
ON sales.orders
TO app_orders;
~~~

This example requires the database, schema, table, and role to exist, along with sufficient grantor privileges.

### 15.1. CONNECT

Grants database connection permission per the privilege model, though `PUBLIC` may already hold `CONNECT` by default on some databases; `GRANT` alone does not prove the DB is locked down.

### 15.2. Schema USAGE

Permission to enter the namespace does not grant access to tables inside it.

### 15.3. Table Privileges

`SELECT`/`INSERT`/`UPDATE`/`DELETE` must be granted per actual need. Read-only services receive no write grants.

### 15.4. Functions and Sequences

Applications may also need `EXECUTE` on functions or `USAGE` on sequences for ID generation depending on schema design. Never assume table privileges pull along unrelated object rights.

### 15.5. Default Privileges

Future objects do not automatically inherit old table `GRANT`s. Configure `ALTER DEFAULT PRIVILEGES` for the exact object-creating role and schema when needed.

## 16. Why Does HBA Succeed Yet SELECT Fails?

A common real-world symptom:

~~~text
SCRAM authentication: SUCCESS
Database connection: SUCCESS
SELECT * FROM sales.orders: ERROR permission denied
~~~

There is no contradiction: the client proved its identity, yet lacks authorization on the schema or table.

### 16.1. Troubleshooting Order

Check sequentially:

1. Does the login role exist and have `LOGIN`?
2. Did an HBA rule match the connection?
3. Do the password verifier and client negotiation align?
4. Is the TLS channel verified?
5. Does the database exist and does the role hold `CONNECT`?
6. Does the role hold schema `USAGE`?
7. Does the role hold the actual object privileges?
8. Do RLS policies or `SECURITY DEFINER`/`INVOKER` affect the outcome?

### 16.2. Never Fix with GRANT ALL ON EVERYTHING

Overly broad grants mask symptoms while expanding blast radius. Fix authentication bugs in authentication, and missing permissions with the exact missing object grants.

## 17. Safe Lab: Preparing the Database and Role

**Environment:** A test PostgreSQL instance/cluster, an authorized admin account, and a fresh database dedicated to the lab. Role/HBA changes affect the cluster, so never run them on production without an approved change.

### 17.1. Creating a Dedicated Database

~~~sql
CREATE DATABASE scram_demo_db;
~~~

Requires `CREATEDB` or superuser; run as a test admin role.

### 17.2. Creating a Login Role Without an Initial Password

~~~sql
CREATE ROLE scram_demo_login
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOREPLICATION;
~~~

The new role does not yet have a usable password for password auth.

### 17.3. Setting a Password Safely

In `psql`, verify:

~~~sql
SHOW password_encryption;
~~~

If controlling verifier generation in an authorized session:

~~~sql
SET password_encryption = 'scram-sha-256';
~~~

Then run the interactive `psql` command:

~~~text
\password scram_demo_login
~~~

Never paste real passwords into lessons, visible SQL statements, chat, or logs.

### 17.4. Granting Connection Privileges

~~~sql
GRANT CONNECT
ON DATABASE scram_demo_db
TO scram_demo_login;
~~~

To remove default `PUBLIC` `CONNECT` in an isolated lab, you may run `REVOKE CONNECT ON DATABASE scram_demo_db FROM PUBLIC` after verifying admin tooling won't break; this is a database privilege decision, not a SCRAM prerequisite.

## 18. Lab: Creating Read-Only Data in the Test Database

Connect `psql` to `scram_demo_db` as an admin role and run:

~~~sql
CREATE SCHEMA scram_lab;

CREATE TABLE scram_lab.healthcheck (
    id INTEGER PRIMARY KEY,
    marker TEXT NOT NULL
);

INSERT INTO scram_lab.healthcheck(id, marker)
VALUES (1, 'scram-demo-ok');

GRANT USAGE ON SCHEMA scram_lab
TO scram_demo_login;

GRANT SELECT ON scram_lab.healthcheck
TO scram_demo_login;
~~~

### 18.1. Why Build This Lab?

You can verify two independent goals:

- Connecting successfully using password/SCRAM.
- The role holds `SELECT` on one table while lacking permission to modify it.

### 18.2. No Write Privileges Granted

In the lab, omit `INSERT`/`UPDATE`/`DELETE` to test least privilege. If the client attempts `UPDATE`, PostgreSQL rejects it under active privileges.

### 18.3. Which Database Holds the Objects?

Roles are cluster-wide, while schemas and tables belong to a specific database. Make sure you are connected to `scram_demo_db` when creating tables.

## 19. Lab: Configuring a Specific HBA Rule

Illustrative configuration for a test PostgreSQL server with TLS enabled:

~~~text
# pg_hba.conf - illustrative, not SQL
hostssl scram_demo_db scram_demo_login 127.0.0.1/32 scram-sha-256
hostssl scram_demo_db scram_demo_login ::1/128      scram-sha-256
~~~

### 19.1. Prerequisites

- Server TLS/SSL enabled with valid certificate and key.
- PostgreSQL listening for TCP/IP connections on the needed interfaces.
- HBA rules placed in proper order.
- Client uses TLS and supports SCRAM.
- Test using a hostname matching the certificate when using `verify-full`.

### 19.2. Loopback Example Only

If PostgreSQL runs on a separate server, the source address must be a narrow CIDR for the allowed client or proxy. Never swap in `0.0.0.0/0` arbitrarily just to "make it work."

### 19.3. Never Edit HBA Directly Without Authorization

The file is managed by DBAs/infrastructure. On managed PostgreSQL, network and auth rules may be restricted or exposed through a provider interface.

### 19.4. Never Wipe Out Existing HBA Rules

Always preserve rescue admin access, file backups, and a rollback path. One ordering mistake can lock out remote access.

## 20. Reloading HBA Configuration and Verifying Rules

Most `pg_hba.conf` edits require a reload to apply to new connections.

~~~sql
SELECT pg_reload_conf();
~~~

This requires appropriate privileges and only sends the reload signal; it does not prove every rule parsed cleanly or that new connections will succeed.

### 20.1. Checking the HBA Parser

With sufficient view privileges:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

### 20.2. Watch the error Column

If the parser reports an error, fix the configuration file. A rule present on disk with a parse error is not active on the server.

### 20.3. Include Files May Exist

Some deployments use `include`/`include_dir` directives; inspect the **effective rule order** after expanding included files.

### 20.4. Existing Sessions Persist

Reloading HBA does not disconnect already-authenticated connections. Pooled connections can keep running, misleading you into thinking new passwords/HBA rules were tested when old sessions were simply reused.

## 21. Lab: Testing Real Connections with psql

Once the role, password, TLS, and HBA are ready, connect from an allowed environment.

Example `libpq` conninfo **without embedding a password**:

~~~text
psql "host=db.example.test port=5432 dbname=scram_demo_db user=scram_demo_login sslmode=verify-full"
~~~

In a loopback lab, replace `db.example.test` with the actual endpoint matching your certificate's hostname and HBA rules. This is a terminal command, not SQL.

### 21.1. Enter the Password via Prompt

Let `psql` prompt for the password or use a protected secrets file. Never pass passwords as command-line arguments.

### 21.2. Querying Identity

~~~sql
SELECT
    current_user,
    session_user,
    current_database();
~~~

Without `SET ROLE`, `current_user` and `session_user` reflect the login role.

### 21.3. Testing Read Privileges

~~~sql
SELECT *
FROM scram_lab.healthcheck;
~~~

Expected to return the marker row from the `SELECT`-granted table.

### 21.4. Testing Denied Operations

~~~sql
-- Run only in the lab; expected permission error
UPDATE scram_lab.healthcheck
SET marker = 'should-not-update'
WHERE id = 1;
~~~

Since the role holds only `SELECT`, this must be rejected. If it succeeds, audit `PUBLIC`, memberships, table ownership, and other grants.

### 21.5. Test with a Fresh Connection

Close the session and open a new connection when testing password or HBA changes; never rely on an existing pooled session.

## 22. Checking TLS on Active Connections

PostgreSQL provides `pg_stat_ssl` to inspect TLS state on backend connections.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version AS tls_version,
    s.cipher
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s
  ON s.pid = a.pid
WHERE a.datname = current_database()
ORDER BY a.pid;
~~~

### 22.1. What Does ssl=true Mean?

The connection uses TLS at the server. It **does not prove the client verified the hostname or CA**; inspect client/cert configuration for that.

### 22.2. ssl=false Can Be Normal on Local Sockets

Unix-domain socket connections do not use TLS and may authenticate via `peer` or another method. Do not confuse `ssl=false` local sockets with a SCRAM error.

### 22.3. pg_stat_ssl Does Not Show the Exact HBA Method

This view reports TLS state, not a complete log of whether "the client used `SCRAM-SHA-256-PLUS`." Combine HBA config, client settings, and server logs/monitoring.

### 22.4. Restrict Observability Privileges

Details of other users' sessions may be restricted by privileges. Never grant broad visibility over sensitive activity to application roles just for a dashboard.

## 23. .pgpass: Storing Passwords for libpq/psql

For `libpq` clients, a password file avoids embedding passwords in scripts or connection strings.

Format:

~~~text
hostname:port:database:username:password
~~~

Illustrative example—**never use this literal as a real secret**:

~~~text
db.example.test:5432:appdb:app_orders:<replace-with-generated-secret>
~~~

### 23.1. Common Locations

On Unix-like systems, the default file is `~/.pgpass`. On Windows, it is typically `%APPDATA%\postgresql\pgpass.conf`, or a custom path via `PGPASSFILE` where supported.

### 23.2. Unix File Permissions

Lock down permissions:

~~~sh
chmod 0600 ~/.pgpass
~~~

`libpq` on Unix ignores password files with overly permissive modes as a built-in safeguard.

### 23.3. Windows Permissions

Manage ACLs per user/service account; never assume placing a file in a profile folder prevents other local accounts from reading it.

### 23.4. Colons and Backslashes in Passwords

Password files require escaping special characters like `:` and backslashes. If a secret contains them, format it strictly per `libpq` rules instead of truncating strings arbitrarily.

### 23.5. The File Still Holds a Secret

`.pgpass` avoids command-line leaks, yet remains a plaintext password file on disk. Protect the filesystem, backups, ownership, and rotation lifecycle.

## 24. PGPASSWORD and Environment Variables: Convenient but Risky

Some `libpq` tools read `PGPASSWORD`.

~~~text
PGPASSWORD = secret supplied by environment
~~~

### 24.1. Why Is It Not the First Choice?

Environment variables can leak through:

- Process introspection on some OS/container setups.
- Debug dumps, diagnostics, and support bundles.
- CI/CD job output from debug commands.
- Logs printing environment maps.
- Misconfigured orchestration or metadata services.
- Subprocesses inheriting the environment.

### 24.2. Not Universally Forbidden Either

Some platforms inject secrets via environment variables with strict controls. Know your threat model, operational policies, and exposure paths; never assume an env var is a secure vault merely because it is named `DB_PASSWORD`.

### 24.3. Never Print Env Vars to Debug

An `echo` or debug dump puts secrets into terminal logs. Verify presence and connectivity without printing values.

### 24.4. Never Put Secrets in Shell History

Setting literal passwords in terminal commands leaves traces in shell history, session recordings, or CI logs. Use controlled secret injection instead of copy-pasting secrets.

## 25. Connection URIs Can Also Leak Passwords

A URI can embed username and password:

~~~text
postgresql://user:password@db.example.test:5432/appdb
~~~

This illustrates syntax only—**not a recommended way to store real secrets**.

### 25.1. Why Is It Dangerous?

URIs frequently appear in:

- Application logs.
- Monitoring attributes.
- Stack traces.
- Command lines and process listings.
- Browser history or internal docs.
- Tickets and chat copy-pastes.
- Source or config repositories.

### 25.2. URL-Encoding Is Not Encryption

Special characters that are URL-encoded can be trivially decoded. Never treat encoding as secret protection.

### 25.3. Separate Endpoints from Secrets

Store hostnames, ports, database names, and TLS configs in non-secret configuration; fetch secrets via controlled mechanisms and pass them into password properties only where needed.

### 25.4. Careful Redaction

If logging connection configuration for diagnostics, strip passwords and tokens—do not only search for `password=` while missing credentials embedded in URI userinfo.

## 26. Secret Managers and Secret Delivery Models

Production systems typically use a secret manager or identity integration for credentials.

~~~text
Secret Manager / Credential Issuer
          |
          | authenticates via workload identity
          v
Application startup / rotation agent
          |
          | receives least-privilege credential
          v
Memory / protected file / platform secret mount
          |
          v
JDBC connection pool
          |
          v
PostgreSQL TLS + SCRAM
~~~

### 26.1. What Does a Secret Manager Store?

Typically username, password, endpoint metadata, secret version, expiration, or rotation metadata—keeping plaintext passwords out of repositories.

### 26.2. Workload Identity

Applications should authenticate to the secret manager using workload identity (host, service account, federated identity) rather than hard-coding "a password to fetch passwords."

### 26.3. Grant Minimal Secret Read Access

Service A should not be able to read Service B's DB password. Secret permissions form an authorization layer independent of PostgreSQL `GRANT`s.

### 26.4. Secret Caching and Rotation

Apps may cache secrets in memory to avoid calling the secret manager on every query. Define refresh rules, TTLs, invalidation, and error handling when secret versions rotate.

### 26.5. Secret Managers Do Not Automatically Update PostgreSQL Verifiers

Updating a value in a vault without updating the PostgreSQL role's password causes new connections to fail. Rotation must coordinate **both the database and client distribution**.

## 27. Java/JDBC: Connecting Without Hard-Coded Passwords

Conceptual Java example:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

public final class DbConnectionExample {
    public Connection open(String passwordFromSecretProvider)
            throws Exception {
        String url =
            "jdbc:postgresql://db.example.test:5432/appdb"
            + "?sslmode=verify-full";

        Properties props = new Properties();
        props.setProperty("user", "app_orders");
        props.setProperty("password", passwordFromSecretProvider);

        return DriverManager.getConnection(url, props);
    }
}
~~~

### 27.1. Where Does the Password Come From?

`passwordFromSecretProvider` must come from an authorized secret-fetching component. This snippet **neither illustrates** hard-coding secrets nor implements a secret manager.

### 27.2. Security Limits of Java Strings

JDBC APIs typically accept passwords as `String`, which cannot be explicitly zeroed in memory like mutable buffers. Minimize secret retention, never log or serialize them, and protect heap dumps and process access.

### 27.3. Match TLS Settings to the Driver

`sslmode=verify-full` illustrates modern PostgreSQL JDBC driver usage; trust store, certificate, and channel-binding configurations must match your driver version, runtime environment, and policy.

### 27.4. Never Enable Sensitive Debug Logging

Never log full `Properties` maps, JDBC URLs containing userinfo, exception payloads with secrets, or raw configuration objects.

### 27.5. Exception Handling

Connection failures can stem from passwords, TLS, HBA, networking, DNS, databases, or privileges. Never return full connection strings containing sensitive details to end users.

## 28. Connection Pools Complicate Rotation

Services typically use HikariCP or another pool to reuse sessions.

~~~text
Application
    |
    v
Connection Pool
  conn A ---- authenticated yesterday
  conn B ---- authenticated yesterday
  conn C ---- new connection now
    |
    v
PostgreSQL
~~~

### 28.1. SCRAM Runs at Connection Setup

Each new connection runs through authentication. An already-authenticated connection does not repeat the SCRAM handshake on every SQL query.

### 28.2. After Changing a Password

Already-authenticated sessions normally **are not logged out** when a role's password changes. Only new connections attempting to use the old password fail.

### 28.3. A Confusing Symptom

An application appears healthy for several minutes after rotation because old pooled connections remain open, then suddenly begins logging authentication failures as the pool opens new connections.

### 28.4. Updating Config Alone Is Not Enough

If the pool caches the old secret, updating the secret manager without reloading or cycling the pool makes new connections fail with the stale password.

### 28.5. Coordination Strategy

Update secrets, spin up new pools/connections with the new password, drain old connections cleanly, and monitor failures. Zero-downtime deployments often require rolling restarts or a two-role rotation strategy.

## 29. Single-Password Rotation for One Role

For a standard password-based PostgreSQL login role, basic configuration holds **one active password verifier** per role at a time; do not assume it natively supports two simultaneous passwords.

### 29.1. Basic Sequence

1. Generate a strong new secret.
2. Ensure applications can fetch the new secret.
3. Update the role password in PostgreSQL.
4. Update secret distribution to the new version.
5. Cycle pool connections as needed.
6. Monitor authentication failures.
7. Revoke/retire the old secret.
8. Verify a fresh connection succeeds using the new credential.

### 29.2. Potential Failure Window

If the DB switches before apps, new connections from old apps fail. If apps switch before the DB, new connections also fail. That is why timing coordination and rollback readiness matter.

### 29.3. Rotation Is More Than ALTER ROLE

Account for every consumer holding that secret: CI runners, maintenance scripts, reporting jobs, old pods, CronJobs, developer workstations, and DR automation.

### 29.4. Verify Without Exposing Secrets

Open a **fresh connection** over the expected TLS/SCRAM path; never print plaintext passwords or verifiers to prove an update succeeded.

## 30. Near-Zero-Downtime Rotation with Two Login Roles

A strategy for zero/low-downtime apps uses two separate login identities inheriting identical privileges from one **NOLOGIN privilege role**.

~~~text
           Privilege Role (NOLOGIN)
                  app_orders_access
                   /             \
                  /               \
         app_orders_a           app_orders_b
            LOGIN                  LOGIN
            secret A               secret B
~~~

### 30.1. Creating the Privilege Group Role

~~~sql
CREATE ROLE app_orders_access NOLOGIN;
~~~

Grant required object privileges to the group role:

~~~sql
GRANT CONNECT ON DATABASE appdb
TO app_orders_access;

GRANT USAGE ON SCHEMA sales
TO app_orders_access;

GRANT SELECT, INSERT, UPDATE ON sales.orders
TO app_orders_access;
~~~

### 30.2. Creating Two Login Roles

~~~sql
CREATE ROLE app_orders_a LOGIN;
CREATE ROLE app_orders_b LOGIN;
~~~

With matching PostgreSQL version and inheritance settings, grant membership:

~~~sql
GRANT app_orders_access TO app_orders_a;
GRANT app_orders_access TO app_orders_b;
~~~

Verify role inheritance semantics so both logins receive expected privileges.

### 30.3. Setting Two Separate Passwords in psql

~~~text
\password app_orders_a
\password app_orders_b
~~~

Never hard-code secrets in SQL.

### 30.4. Cutover

1. Apps initially use `app_orders_a`.
2. Prepare `app_orders_b` with the new password.
3. Verify B's privileges and fresh connections.
4. Perform a rolling deploy/pool replacement from A to B.
5. Monitor active sessions and errors.
6. Once certain A has no callers left, disable or revoke A per policy.

### 30.5. Trade-Offs

This adds extra roles, per-session audit identities, and membership maintenance—yet lets two secrets coexist cleanly without needing one role to hold two verifiers.

## 31. VALID UNTIL and NOLOGIN: Two Different Controls

PostgreSQL supports password expiration on roles:

~~~sql
ALTER ROLE app_orders_a
VALID UNTIL '2027-06-30 00:00:00+00';
~~~

And disabling `LOGIN`:

~~~sql
ALTER ROLE app_orders_a NOLOGIN;
~~~

### 31.1. VALID UNTIL

Limits password validity under password authentication rules. It is not a full account-expiration framework and does not necessarily block non-password authentication methods the same way.

### 31.2. NOLOGIN

Prevents the role from being used as a login identity for new connections, while allowing it to retain privileges or memberships for other patterns.

### 31.3. Neither Automatically Closes Live Sessions

Changing `VALID UNTIL`, `NOLOGIN`, or passwords **does not automatically terminate previously authenticated sessions**. Terminate existing sessions explicitly if immediate revocation is required.

### 31.4. Never Treat PASSWORD NULL as Equivalent to NOLOGIN

~~~sql
ALTER ROLE app_orders_a PASSWORD NULL;
~~~

This removes any usable password for password-based authentication, yet the role can still log in via other methods if HBA and privileges allow. To block new logins as a role, use `NOLOGIN`.

## 32. Revoking Existing Sessions After a Secret Leak

During credential compromise, merely rotating the password is insufficient because an attacker may still hold an open authenticated session.

### 32.1. Inspecting Active Sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    backend_start,
    state
FROM pg_stat_activity
WHERE usename = 'app_orders_a'
ORDER BY backend_start;
~~~

### 32.2. Terminating Sessions Requires Special Privileges

PostgreSQL provides `pg_terminate_backend` to terminate backend sessions with sufficient privileges.

~~~sql
-- Admin example: assess impact before running:
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = 'app_orders_a'
  AND pid <> pg_backend_pid();
~~~

### 32.3. Why Not Run Indiscriminately in Production?

It aborts in-flight transactions, causes application errors, rollbacks, and retry storms. During real incidents, weigh urgent revocation against blast radius under your incident response plan.

### 32.4. Do Not Check Only Role Name

If a secret was shared across jobs or services, inspect source IPs, `application_name`, timestamps, pool behavior, and authorized activity logs.

### 32.5. Multi-Layer Containment

You may need to simultaneously rotate passwords, set `NOLOGIN` on old roles, terminate sessions, revoke vault/CI secrets, rotate related tokens, audit logs, and scope accessed data.

## 33. Secret Management Lifecycle

Every production credential should be managed across its full lifecycle:

~~~text
Generate -> Approve/Issue -> Store -> Distribute
     ^                               |
     |                               v
   Revoke <- Retire <- Rotate <- Use/Monitor
~~~

### 33.1. Generate

Use a cryptographically secure generator for long, unpredictable passwords never reused across services or environments.

### 33.2. Issue/Approve

Record owner, purpose, privileges, expiration, environment, and approval workflow.

### 33.3. Store

Use a secret manager or protected vault; never store plaintext in source code, shared docs, or tickets.

### 33.4. Distribute

Grant minimal secret-read access to workload identities; protect secret retrieval channels and process injection.

### 33.5. Use

Connect using SCRAM over TLS per policy, under a least-privilege role.

### 33.6. Monitor

Alert on authentication failures, connection counts, privilege changes, and anomalous secret usage without logging secret values.

### 33.7. Rotate

Rotate secrets on schedule or on events, sync DB verifiers, cycle pools, and verify new connections.

### 33.8. Revoke/Retire

Disable roles/secrets, check remaining live sessions, purge stale copies, and update documentation/runbooks.

## 34. Generating Strong Passwords for SCRAM

SCRAM cannot rescue a short or common password.

### 34.1. Length and Entropy

For machine-generated credentials, prefer long, high-entropy random strings rather than relying solely on "one uppercase, one digit, one symbol" heuristics.

### 34.2. Never Reuse

Production, staging, dev, and separate services must use independent passwords. Compromising dev must never reveal production credentials.

### 34.3. Avoid Project Names and Dates

Patterns like `Project2026!` or `Company@123` are easily guessed even when meeting basic complexity rules.

### 34.4. Mind Input and Encoding

Unicode, special characters, or very long passwords must be handled consistently by clients and servers. Use generators and APIs that preserve exact bytes/encoding; never `trim()` or `lower()` secrets fetched from a vault.

### 34.5. Do Not Arbitrarily "Pre-Hash" on the Client

If an app computes `SHA-256(password)` itself and sends that digest as the password, that digest simply becomes a reusable plaintext equivalent without meaningfully improving security. SCRAM already handles key derivation in-protocol; protect the original secret properly.

## 35. Secrets in CI/CD and Infrastructure-as-Code

Common places DB passwords leak accidentally:

- Git commits containing `application.properties`.
- `.env` files pushed to a repository.
- CI jobs dumping all environment variables.
- Terraform plans/state storing secrets in sensitive attributes.
- Publicly readable Helm values or plain YAML manifests.
- Kubernetes Secrets mistaken for encrypted storage merely because of base64.
- Docker images baking secrets into layers.
- Build arguments or `Dockerfile` `ENV` containing passwords.
- Test fixtures embedding production credentials.
- Unrestricted support bundles or heap dumps.

### 35.1. IaC State Is Sensitive Data

Console masking in a plan does not stop state files or storage backends from retaining secret copies. Enforce encryption at rest, IAM, version history controls, logging, and retention limits.

### 35.2. Container Images Are No Place for Passwords

Baking secrets into Docker images creates hard-to-revoke copies distributed broadly. Inject secrets at runtime via controlled platform mechanisms.

### 35.3. Never Mistake Base64 for Encryption

Kubernetes Secret manifests base64-encode values; encoding offers zero protection against anyone reading the manifest or API. Enforce RBAC, encryption at rest, node isolation, and secret distribution policies.

### 35.4. Rotate After an Accidental Commit

Once a secret enters Git or CI logs, deleting the line in the latest branch **does not undo exposure**. Rotate/revoke the secret and audit artifact/backup history and access logs.

## 36. Logs and Observability: Visibility Without Printing Secrets

Systems need to know authentication failed without recording the password submitted.

### 36.1. Safe to Log

- Timestamps.
- Target role/username.
- Database name.
- `application_name` if present.
- Source IP.
- Auth/TLS/network error category.
- Connection counts, pool wait times, retry rates.
- Non-sensitive secret version IDs (not values).
- Certificate expiry and TLS policy compliance status.

### 36.2. Never Log

- Plaintext passwords.
- PostgreSQL SCRAM verifiers.
- Connection URIs containing passwords.
- Raw secret-manager responses.
- Tokens/API keys used to fetch secrets.
- Authorization headers.
- Full environment dumps.
- Sensitive private keys/certificates.
- Memory dumps containing credentials.

### 36.3. Failed Passwords Must Never Echo as Debug Data

Never log "client tried password xyz." PostgreSQL error/statement logging can capture connection details or statements depending on settings; design log redaction and log access controls carefully.

### 36.4. Watch Parameterized SQL Too

Even with prepared statements, diagnostics or middleware may log bind values. Avoid sending plaintext passwords in `ALTER ROLE ... PASSWORD '...'` SQL when safer admin paths exist.

## 37. Protecting Backups and Snapshots

PostgreSQL backups can contain sensitive data and configuration, including authentication material within applicable backup scopes.

### 37.1. Physical Backups

A copy of the cluster data directory includes system catalogs and auth verifiers. Protect backup access with the same rigor as sensitive production data.

### 37.2. Logical Backups

Dump tools vary in whether they include cluster-wide roles/verifiers. Never assume a dump excludes or includes password verifiers without knowing the exact command and flags used.

### 37.3. Encryption and Access Control

Encrypt backups at rest, enforce IAM and key management, audit downloads, and test restores per your threat model.

### 37.4. Retention After Rotation

Even after rotating live passwords, older backups may retain older verifiers or application secrets. Manage retention windows and access to archived backups.

### 37.5. Never Use Backups to Verify Passwords

Never extract verifiers from backups or paste them into tickets; verify updates via fresh logins and non-sensitive metadata.

## 38. Migrating Legacy Systems from MD5 to SCRAM

Plan migrations in **phases** to avoid locking out clients.

~~~text
Inventory clients + server versions
            |
            v
Verify driver/libpq SCRAM support
            |
            v
Enable SCRAM verifier generation
            |
            v
Rotate login role passwords
            |
            v
Test fresh connections
            |
            v
Switch HBA to scram-sha-256
            |
            v
Monitor errors, retire legacy paths
~~~

### 38.1. Inventory First

Catalog all services, DB users, driver versions, batch jobs, BI tools, migration runners, monitoring agents, and endpoints.

### 38.2. Upgrade Unsupported Clients

If an older app uses a driver lacking SCRAM support, switching verifiers or HBA before upgrading the driver will lock it out.

### 38.3. Switch Verifier Setting for New Passwords

~~~sql
SHOW password_encryption;
~~~

Ensure it targets SCRAM; then **reset** each role's password safely.

### 38.4. Leverage HBA md5 Transition Behavior Where Supported

Certain PostgreSQL versions let HBA `md5` authenticate via SCRAM when the role already holds a SCRAM verifier. This provides a useful migration bridge—verify against your actual compatibility matrix.

### 38.5. Tighten HBA Last

Once all clients and passwords are ready, switch target rules to `scram-sha-256`, reload, and test fresh connections across every path.

### 38.6. Monitor Production

Watch login failures, pool reconnects, deployment waves, and infrequent batch jobs. Never declare victory just because the web app ran cleanly for an hour.

## 39. Checklist When Changing password_encryption

A common mistake is running:

~~~sql
SET password_encryption = 'scram-sha-256';
~~~

and assuming every role has migrated off MD5.

### 39.1. What Changes

The setting affects how newly set passwords generate verifiers going forward.

### 39.2. What Does NOT Change Automatically

- Existing stored verifiers for roles.
- HBA rules/methods.
- TLS certificates.
- Passwords in secret managers.
- Passwords cached by apps/pools.
- Driver/JDBC versions.
- Existing sessions.
- Role privileges.

### 39.3. Completion Criteria

Every role must be verified via a **fresh connection** matching the HBA SCRAM rule and new secret from its actual client—never relying solely on `SHOW password_encryption`.

## 40. Common SCRAM Authentication Errors

| Symptom | Likely areas to inspect |
|---|---|
| `password authentication failed` | Wrong password, verifier/role/HBA mismatch, stale secret |
| `no pg_hba.conf entry` | No rule matching host/db/user/SSL |
| `role does not exist` | Misspelled role or not created in cluster |
| `database does not exist` | Wrong DB name or not created |
| `permission denied for schema` | Auth OK, missing schema `USAGE` |
| `permission denied for table` | Auth OK, missing table privileges |
| `certificate verify failed` | CA/chain/hostname/trust store mismatch |
| `channel binding required` or similar | TLS/PLUS/client incompatibility |
| Only new app instances fail | Old pool still alive; new connections use stale secret |
| CI succeeds, production fails | Different HBA IP/proxy/TLS/driver/secret |
| TCP fails while local socket works | Different HBA rules / `local` vs. `host` |
| Old sessions remain after rotation | Changing password does not kill existing backends |

### 40.1. Never Conclude from a Single Generic Message

Some errors are intentionally generic to avoid leaking information or cover multiple root causes. Cross-check server logs, HBA config, role metadata, and client settings with authorized access.

### 40.2. Never Test Passwords by Printing Them

Copying secrets into SQL queries or logs causes secondary incidents. Test using fresh connections with secure secret injection.

### 40.3. Never Lower Security Just to Get Connected

Disabling TLS, switching to `trust`, or logging in as superuser just to bypass errors hides root causes and creates production exposure. Fix the exact failing layer.

## 41. Diagnostic Flow for a Failing New Connection

~~~text
Connection fails
         |
         v
 DNS / network / port reaches server?
         |
         +-- No -> check endpoint, firewall, listen_addresses
         |
         v
 TLS handshake/certificate OK?
         |
         +-- No -> check CA, hostname, certificate, TLS proxy
         |
         v
 pg_hba.conf first matching rule?
         |
         +-- No -> check type, db, user, source CIDR, SSL, ordering
         |
         v
 Role LOGIN and verifier/password valid?
         |
         +-- No -> check secret version, rotation, SCRAM support
         |
         v
 SCRAM/channel binding negotiation OK?
         |
         +-- No -> check client version, TLS/PLUS capability
         |
         v
 Database CONNECT / schema/table rights?
         |
         +-- No -> check GRANT/RLS/ownership
         |
         v
 Query works; print zero secrets
~~~

### 41.1. Identify the First-Match HBA Rule

A broad rule higher up may intercept the connection before your SCRAM rule. Inspect the entire ordered list, not just lines matching the username.

### 41.2. Identify the Actual Client

JDBC drivers, `psql`/`libpq`, ODBC, BI connectors, and proxies have distinct compatibility quirks. If CLI `psql` works while Java fails, suspect driver/TLS settings rather than the server password.

### 41.3. Distinguish New vs. Reused Connections

A pool holding old sessions does not validate a new password. Force a fresh connection using an app-equivalent client.

### 41.4. Verify Credential Version

The secret manager may issue v2 while the app caches v1. Use non-secret version IDs/metadata to diagnose without displaying passwords.

## 42. pg_hba_file_rules Is Not a Complete Attack-Surface Map

`pg_hba_file_rules` validates file syntax and rule ordering on disk, yet cannot answer everything:

- Is a firewall blocking or exposing the port?
- Which interfaces does the server listen on?
- Does a proxy rewrite source IPs?
- Did the client enforce `verify-full` on the TLS certificate?
- Did the client negotiate SCRAM-PLUS?
- Do old sessions remain open for the role?
- Are secrets leaking into logs?

### 42.1. Evaluate Configuration Along the Real Traffic Path

Strict HBA on the DB server paired with an intermediate proxy allowing public traffic changes your threat model. Always evaluate the full production topology.

### 42.2. HBA Is Not a Secret Distribution System

HBA only selects auth methods and IP/user/database scopes; it neither delivers passwords to apps nor manages secret lifecycles.

### 42.3. IP Allowlists Do Not Replace Credentials

A service inside an allowed CIDR with a leaked secret remains a risk; conversely, a valid password from a disallowed IP is still rejected if HBA/network policy blocks it.

## 43. Why Does Connection Pooling Affect SCRAM Performance?

SCRAM performs key derivation and verification during each handshake, incurring CPU cost. Opening a brand-new connection per SQL statement multiplies network, TLS, and SCRAM handshake overhead while straining backend limits.

### 43.1. Use Right-Sized Pools

Reusing connections cuts handshake overhead, though oversized pools waste RAM and PostgreSQL backend slots.

### 43.2. Pools Must Not Cache Secrets Forever

Pools holding credentials indefinitely slow rotation and prolong exposure. Support clean secret refresh/draining and verify new connections.

### 43.3. Auth/TLS Is Not Total Request Latency

If a query takes 100 ms because an index is missing, optimizing SCRAM handshakes will not speed up queries on already-open connections. Measure connection-setup latency separately from query execution latency.

### 43.4. Connection Storms

When secrets rotate all at once or PostgreSQL fails over, many app instances reconnecting simultaneously can spike auth/TLS CPU. Use backoff, jitter, bounded pools, and staged rollouts.

### 43.5. Never Arbitrary-Lower SCRAM Work Factors

Security cost and performance must follow supported version defaults and security guidance. Dropping cryptographic work factors without security review is not how to fix a connection storm—fix pooling and retry backoff instead.

## 44. Managed PostgreSQL and Non-Traditional Password Auth

Some environments provide:

- Client certificate authentication.
- Kerberos/GSSAPI or SSPI in integrated directories.
- `peer` authentication for local system accounts.
- Cloud-provider token/IAM-based database authentication.
- Connection proxies or identity-aware gateways.

### 44.1. When Does SCRAM Fit?

When services use traditional PostgreSQL password credentials and clients support SCRAM. It is a strong choice when secrets are properly managed.

### 44.2. When to Consider Alternatives?

If an organization already runs a trusted identity platform supporting short-lived tokens or client certificates, those can reduce long-lived password management overhead in suitable use cases.

### 44.3. Do Not Assume Cloud IAM Tokens Are Standard SCRAM

Tokens passed in the password field under provider mechanisms may not be processed by PostgreSQL like ordinary SCRAM verifiers. Follow the provider's authentication documentation.

### 44.4. Migration Plans Must Respect Platform Bounds

Managed services may prohibit editing `pg_hba.conf` directly or reading `pg_authid`. Use the provider's management interfaces and supported roles rather than trying to bypass platform limits.

## 45. Separating Environments and Role Identities

Operational rule:

~~~text
Development:
  db-dev.example.test
  role app_orders_dev
  secret ref /dev/orders/db

Staging:
  db-stage.example.test
  role app_orders_stage
  secret ref /stage/orders/db

Production:
  db-prod.example.test
  role app_orders_prod
  secret ref /prod/orders/db
~~~

### 45.1. Never Reuse Production Passwords in Dev

If a dev laptop or CI runner is compromised, separate credentials stop lateral movement.

### 45.2. Never Share Admin Roles

An app running `SELECT`/`INSERT`/`UPDATE` needs neither `CREATEROLE`, `CREATEDB`, nor `SUPERUSER`.

### 45.3. Never Restore Production Secrets into Test Environments

Restoring a production backup to test requires scrubbing/rotating roles and passwords and hardening access per policy. Never place real production credentials in lower-security test environments just for test data.

### 45.4. Naming and Ownership

Role names should map cleanly to services/workloads; document owner, permissions, rotation cadence, revocation steps, and emergency access.

## 46. Incident Response When a Password Leak Is Suspected

An incident may surface via a repo leak, log leak, vault alert, anomalous logins, or unexpected queries.

### 46.1. Scope First

Identify which secret, role, database, privilege scope, and environments are affected, and whether an attacker obtained a verifier or plaintext.

### 46.2. Contain and Revoke

Depending on severity, rotate passwords, revoke secrets, set `NOLOGIN` on affected roles, terminate suspicious sessions, tighten network exposure, and block reuse.

### 46.3. Inspect History

Review PostgreSQL logs/connection records, application traces, and audit logs within authorized scope. Note that logs may not capture every query—never assume "no log entry means no access."

### 46.4. Check Backups and Copies

If the verifier or secret entered backups, CI artifacts, telemetry, or Git history, assess whether unauthorized parties could access those copies.

### 46.5. Safe Recovery

Issue fresh credentials, verify least-privilege grants, update secret distribution, roll out fresh pools, test TLS/SCRAM, and monitor post-cutover.

### 46.6. Postmortem Without Further Leaks

Document root cause, impact, timeline, remediation, and control improvements—never include plaintext passwords or verifiers in the report.

## 47. Common Misconceptions

### 47.1. "SCRAM means passwords cannot be guessed if verifiers leak"

False. Salting and work factors raise guessing cost, but weak passwords remain vulnerable.

### 47.2. "SCRAM encrypts all SQL traffic automatically"

False. TLS is required to protect the channel and application payloads.

### 47.3. "sslmode=require equals verify-full"

Not guaranteed in general. `verify-full` verifies both the hostname and CA per PKI rules.

### 47.4. "SCRAM-SHA-256-PLUS just means a longer password"

False. `PLUS` refers to TLS channel binding, not password length.

### 47.5. "channel_binding=require always works through every proxy"

False. Verify proxy support and how TLS is terminated along the path.

### 47.6. "Changing password_encryption converts all old verifiers"

False. Existing passwords must be reset/rotated.

### 47.7. "Having one SCRAM line in pg_hba.conf means all logins use SCRAM"

False. First-match ordering, type, database, user, address, and SSL determine which rule runs.

### 47.8. "When HBA auth fails, PostgreSQL tries the next rule"

False. There is no fallback across rules once a rule matches.

### 47.9. "hostssl automatically verifies client certificates"

False. `hostssl` requires TLS on the connection; it does not mean mTLS/client certificate authentication.

### 47.10. "HBA md5 always means the server runs MD5"

Not true in versions where HBA `md5` upgrades to SCRAM when the role stores a SCRAM verifier.

### 47.11. "HBA scram-sha-256 works with old MD5 verifiers"

False in standard setups; a SCRAM verifier is required.

### 47.12. "Password verifiers aren't sensitive because they aren't plaintext"

False. They must be protected as sensitive authentication material.

### 47.13. "Having LOGIN grants SELECT on all tables"

False. Authentication and authorization are separate layers.

### 47.14. "GRANT SELECT on a table implies schema USAGE"

Not by default; verify schema privileges.

### 47.15. "Using the postgres superuser for services is simplest"

Convenient initially, yet creates an unacceptable blast radius.

### 47.16. "\password is just different syntax for hard-coded SQL passwords"

No. It prompts interactively and keeps plaintext out of SQL statement history.

### 47.17. "Environment variables are automatically safer than files"

Not always. Both have distinct threat models and leak paths.

### 47.18. "Base64-encoded Kubernetes Secrets are encrypted"

False. Base64 is encoding, not encryption.

### 47.19. "URL-encoding a PostgreSQL URI makes it secure"

False. It merely escapes characters.

### 47.20. "Putting passwords in source code is fine if the repo is private"

False. Clone access, Git history, backups, and CI logs remain risks.

### 47.21. "A secret manager automatically updates passwords inside PostgreSQL"

Not automatically. Orchestration or an explicit rotation integration is required.

### 47.22. "Changing a password disconnects all old connections"

False. Existing authenticated sessions continue until closed or terminated.

### 47.23. "The pool still runs queries, so the new password must be right"

False. The pool may simply be reusing old sessions.

### 47.24. "VALID UNTIL disables every auth method and live session"

False. It governs password expiration primarily, not `NOLOGIN` or active session termination.

### 47.25. "PASSWORD NULL is the same as NOLOGIN"

False. The role could still authenticate via other HBA-allowed methods.

### 47.26. "Terminating a backend has no effect on transactions"

False. It aborts active transactions and causes application errors.

### 47.27. "One role works fine for every service and environment"

Never recommended; least privilege and rotation isolation require separate roles.

### 47.28. "Java JDBC supports every libpq property identically"

Not guaranteed. Driver versions and TLS/channel-binding configuration differ.

### 47.29. "pg_stat_ssl shows the exact SCRAM method used"

No. It reports TLS state, not auth negotiation history.

### 47.30. "Removing a secret from the latest branch stops the leak"

False. It can persist in Git history, CI artifacts, or cloned copies.

## 48. Hands-On Exercises

### Exercise 1 — Three Layers

Distinguish authentication, authorization, and TLS transport security using a PostgreSQL connection example.

**Hint:** SCRAM verifies identity, `GRANT` allows table reads, and TLS protects data in transit.

### Exercise 2 — Verifier

Is a SCRAM verifier a plaintext password?

**Answer:** No; it is derived data used for authentication.

### Exercise 3 — Salt

Why does SCRAM use a salt?

**Hint:** Limits shared precomputed hash tables and prevents identical passwords from yielding identical verifiers.

### Exercise 4 — Work Factor

What does the iteration count help with?

**Hint:** Increases the cost of offline password-guessing attacks.

### Exercise 5 — Weak Passwords

Is a short, common password safe merely because SCRAM is enabled?

**Answer:** No.

### Exercise 6 — TLS

Does SCRAM automatically encrypt returned query results?

**Answer:** No; TLS is required per security policy.

### Exercise 7 — verify-full

Why is `verify-full` preferable to encryption-only TLS?

**Hint:** Verifies server endpoint identity via CA and hostname.

### Exercise 8 — PLUS

What layer does `SCRAM-SHA-256-PLUS` add?

**Answer:** TLS channel binding.

### Exercise 9 — Proxies

Can a TLS-terminating proxy affect `channel_binding=require`?

**Answer:** Yes; verify topology and proxy capabilities.

### Exercise 10 — HBA

Which key fields in `pg_hba.conf` determine rule matching?

**Hint:** Type, database, user, address, and method.

### Exercise 11 — First-Match

A broad `trust` line sits above a `scram` line for the same connection. Which rule gets selected?

**Answer:** The earlier `trust` line if it matches.

### Exercise 12 — No Fallback

If the first matching rule fails due to a wrong password, does PostgreSQL try later rules?

**Answer:** No.

### Exercise 13 — hostssl

What does `hostssl` require?

**Hint:** TCP/IP connections encrypted with TLS/SSL.

### Exercise 14 — Local

Why do Unix socket connections behave differently from `127.0.0.1` connections?

**Hint:** They match different HBA connection types.

### Exercise 15 — md5 Migration

Why must you check client versions before switching all HBA rules to SCRAM?

**Hint:** Older clients may lack SCRAM support.

### Exercise 16 — password_encryption

After changing the setting to SCRAM, do all roles automatically have SCRAM verifiers?

**Answer:** Not yet.

### Exercise 17 — \password

Which `psql` command resets a password interactively?

**Answer:** `\password role_name`.

### Exercise 18 — pg_authid

Should `rolpassword` from `pg_authid` ever be pasted into support tickets?

**Answer:** No.

### Exercise 19 — pg_roles

Write a query checking a role's `LOGIN` capability and password expiration without exposing verifiers.

~~~sql
SELECT rolname, rolcanlogin, rolvaliduntil
FROM pg_roles
WHERE rolname = 'scram_demo_login';
~~~

### Exercise 20 — Least Privilege

Which privileges does a service reading only the `healthcheck` table need?

**Hint:** Database `CONNECT`, schema `USAGE`, and table `SELECT` per active configuration.

### Exercise 21 — Permission Error

SCRAM succeeds, yet `SELECT` raises permission denied. Which layer failed?

**Answer:** Authorization.

### Exercise 22 — HBA Debug

Which view displays HBA rules and parse errors?

**Answer:** `pg_hba_file_rules` (when permitted).

### Exercise 23 — Reload

Does `pg_reload_conf()` by itself prove HBA parsed cleanly and logins work?

**Answer:** No.

### Exercise 24 — New Connection

Why must you open a fresh connection after rotating a password?

**Hint:** Existing sessions authenticated earlier.

### Exercise 25 — .pgpass

What are the five fields in `.pgpass`?

**Hint:** `host:port:database:user:password`.

### Exercise 26 — File Permissions

On Unix, what is the standard minimum permission mode for `~/.pgpass`?

**Answer:** `0600`.

### Exercise 27 — PGPASSWORD

Name two ways environment secrets can leak.

**Hint:** Process inspection, debug logs, CI output.

### Exercise 28 — URI

Why are passwords in PostgreSQL URIs dangerous even when URL-encoded?

**Hint:** URIs get logged and URL encoding is trivially reversible.

### Exercise 29 — Java

How should JDBC receive passwords without hard-coding them in source code?

**Hint:** Fetch from a secret manager and pass via in-memory `Properties` using supported APIs.

### Exercise 30 — Connection Pooling

Why can an app start failing after rotation only when the pool opens new connections?

**Hint:** The pool cached the old secret while reusing old sessions.

### Exercise 31 — Single Role

Does a password-based role natively support two independent active passwords at once?

**Answer:** Not in standard usage.

### Exercise 32 — Two Login Roles

How do two roles A/B inheriting one `NOLOGIN` privilege role help?

**Hint:** Enables low-disruption secret cutover.

### Exercise 33 — VALID UNTIL

Does `VALID UNTIL` automatically close active sessions?

**Answer:** No.

### Exercise 34 — NOLOGIN

How does `NOLOGIN` differ from `PASSWORD NULL`?

**Hint:** Blocks the role from logging in on new connections vs. merely removing password authentication capability.

### Exercise 35 — Terminate

Why must you be cautious with `pg_terminate_backend` in production?

**Hint:** Aborts transactions and triggers errors/retries.

### Exercise 36 — Secret Manager

When an app fetches secrets from a vault, does PostgreSQL's stored password update automatically?

**Answer:** Not necessarily.

### Exercise 37 — Workload Identity

Why is workload identity better than hard-coding a token to read the vault?

**Hint:** Eliminates another static secret and bounds workload permissions.

### Exercise 38 — Kubernetes

Is base64-encoded data in a Kubernetes Secret automatically strongly encrypted?

**Answer:** No.

### Exercise 39 — Git Leak

If a password was committed accidentally, is amending/deleting the latest commit enough?

**Answer:** No; rotate/revoke immediately and audit history.

### Exercise 40 — Backups

Why do PostgreSQL backups need the same sensitivity protection?

**Hint:** They can contain both data and authentication material.

### Exercise 41 — pg_stat_ssl

What does `pg_stat_ssl` tell you, and what does it not tell you?

**Hint:** Reports TLS status, not whether the client used `verify-full` or `SCRAM-PLUS`.

### Exercise 42 — Managed Services

Why do not all cloud PostgreSQL offerings permit editing `pg_hba.conf` directly?

**Hint:** Providers manage network and auth policies through dedicated layers.

### Exercise 43 — Endpoint Certificate

Why can `verify-full` fail when connecting by IP while the certificate contains only a hostname?

**Hint:** Hostname/SAN mismatch.

### Exercise 44 — Zero-Trust

If an IP allowlist exists, do we still need passwords and TLS?

**Answer:** Yes, per threat modeling; defense layers complement one another.

### Exercise 45 — Log Redaction

List five kinds of data that must never appear in connection logs.

**Hint:** Passwords, SCRAM verifiers, secret-bearing URIs, tokens, private keys.

### Exercise 46 — Rotation Checklist

List at least six steps of a rotation workflow.

**Hint:** Generate new secret, prepare clients, update verifier, distribute, refresh pools, test new connections, monitor, revoke old secret.

### Exercise 47 — Credential Incident

If a password leaked and an attacker holds an active session, is rotating the password enough?

**Answer:** No; terminate sessions and investigate.

### Exercise 48 — Passwordless Auth

Name two alternative authentication options suitable depending on environment.

**Hint:** Client certificates, GSS/SSPI, `peer`, provider IAM tokens.

### Exercise 49 — Migrating MD5

Why must you inventory batch jobs and BI clients before switching HBA?

**Hint:** Infrequent clients may fail long after the migration appeared finished.

### Exercise 50 — Holistic Design

A Java system has three services using PostgreSQL on Kubernetes, all sharing one superuser password hard-coded in `application.yml`. Propose a controlled remediation plan.

**Hint:** Separate roles per service and environment, enforce least privilege, SCRAM verifiers, TLS `verify-full`, narrow source-CIDR HBA rules, secret manager/workload identity, purge secrets from Git/CI, rotate using dual login roles or phased rollout, refresh connection pools, run audit/fresh-connection tests, and revoke the misused superuser credential.

## 49. Safe SCRAM Implementation Checklist

### 49.1. Server and HBA

- [ ] PostgreSQL version supports SCRAM for the target architecture.
- [ ] `password_encryption` set appropriately for new passwords.
- [ ] Passwords reset for all login roles requiring SCRAM.
- [ ] HBA rules select `scram-sha-256` per exact database/user/address.
- [ ] HBA order is not shadowed by an earlier broad `trust`/`md5` rule.
- [ ] Remote production access requires TLS per policy.
- [ ] CIDRs are no wider than necessary.
- [ ] HBA parser reports zero errors.
- [ ] Tested with **fresh connections** across real traffic paths.

### 49.2. TLS and Clients

- [ ] Clients use TLS and verify CA/hostname where appropriate.
- [ ] Certificate SAN/hostname and CA chain are valid.
- [ ] `libpq`/JDBC/ODBC/BI driver versions support SCRAM.
- [ ] Channel-binding policy verified end-to-end.
- [ ] Proxies/load balancers do not break TLS assumptions.
- [ ] Retry/backoff protects against connection storms.
- [ ] Pools are configured to refresh credentials on rotation.

### 49.3. Roles and Authorization

- [ ] Applications never use superuser.
- [ ] Roles separated by workload and environment.
- [ ] Only required `CONNECT`/`USAGE`/`SELECT`/`INSERT`/... privileges granted.
- [ ] RLS and role inheritance checked if used.
- [ ] `CREATEROLE`/`CREATEDB`/`REPLICATION` omitted unless justified.
- [ ] Clear policies for `VALID UNTIL`/`NOLOGIN`.
- [ ] Tested as the real application role, not just admin.

### 49.4. Secrets and Operations

- [ ] Passwords generated randomly with high strength.
- [ ] Never reused across services or environments.
- [ ] Secrets stored in a vault or approved protected mechanism.
- [ ] Zero hard-coded secrets in source/IaC/logs.
- [ ] CI/CD and container secrets protected by IAM/RBAC.
- [ ] Never print verifiers or plaintext passwords while debugging.
- [ ] Clear owner, rotation schedule, and revocation plan.
- [ ] Backups, telemetry, and heap dumps protected by policy.
- [ ] Session-revocation procedure ready for compromises.
- [ ] Incident playbook and post-rotation reconnect checks in place.

## 50. Quick Reference Table

| Concept | Key takeaway |
|---|---|
| SCRAM-SHA-256 | Challenge–response password authentication |
| SCRAM verifier | Salt/work-factor-derived auth data; still sensitive |
| SCRAM-SHA-256-PLUS | SCRAM with TLS channel binding |
| TLS | Transport encryption and protection |
| `sslmode=verify-full` | Verifies CA and hostname |
| `channel_binding=require` | Demands channel binding when supported by client/server |
| `pg_hba.conf` | Rules selecting auth method per connection |
| `hostssl` | Matches only TLS-encrypted TCP/IP connections |
| HBA first-match | First matching rule picks the method; no fallback |
| `trust` | Skips password check on matching connections; dangerous if broad |
| `scram-sha-256` | HBA method requiring SCRAM |
| `md5` | Legacy method; plan deprecation |
| `password_encryption` | Controls verifier format for newly set passwords |
| `\password` | `psql` prompt avoiding plaintext SQL literals |
| `pg_roles` | Role metadata safer than `pg_authid` |
| `pg_authid` | Catalog holding auth secrets; tightly restricted |
| `pg_hba_file_rules` | Inspects HBA parsing and rule order |
| `pg_reload_conf()` | Signals config reload; does not verify logins |
| `pg_stat_ssl` | TLS status of active sessions |
| `LOGIN` | Role can log in |
| `CONNECT` | Database connection privilege |
| Schema `USAGE` | Namespace access privilege |
| Table `GRANT` | Data access privileges |
| Least privilege | Grant only permissions the job needs |
| `~/.pgpass` | `libpq` password file on Unix |
| `PGPASSFILE` | Custom password file path |
| `PGPASSWORD` | Env password; carries exposure risks |
| JDBC `Properties` | Passes password separately from URI/source |
| Secret manager | Stores and distributes secrets by identity |
| Workload identity | Service identity used to fetch secrets |
| Connection pool | Reuses sessions; impacts rotation |
| Rotation | Coordinates DB verifier and client secret updates |
| Dual login roles | Enables low-disruption A/B credential cutover |
| `NOLOGIN` | Disables new direct logins |
| `VALID UNTIL` | Bounds password validity per semantics |
| Existing session | Not automatically killed on password change |
| `pg_terminate_backend` | Terminates backends when authorized/evaluated |
| Secret leak | Requires rotate/revoke, not just deleting lines |
| CI logs/IaC state | May hold secrets; must be secured |
| TLS proxy | Can alter source IP and channel binding |

---

## Conclusion

**SCRAM-SHA-256 is PostgreSQL's modern password authentication mechanism** built on challenge–response and salted, work-factor-derived verifiers, avoiding plaintext password transmission during the handshake. **SCRAM-SHA-256-PLUS** adds TLS channel binding. Yet SCRAM alone neither encrypts SQL traffic, guarantees the client verified the server certificate, nor governs data authorization; combine it with **TLS `verify-full`**, **properly ordered HBA**, and **least-privilege roles**.

Two frequently confused settings are `password_encryption` and `pg_hba.conf`. The first governs how **verifiers for newly set passwords** are generated; the second selects the **authentication method for incoming connections**. Changing `password_encryption` does not convert existing passwords, and placing an HBA SCRAM rule below a broad rule never ensures it will be used. Every change must be verified with a **fresh connection** from the actual client/endpoint rather than pooled sessions.

**Secret management is a lifecycle process**, not a `password=...` line in app configuration. Generate strong, unique secrets, store them in controlled vaults, keep them out of source code/CI/logs/URIs, authorize access via workload identity, plan rotations, and manage pool reconnects. Where minimal cutover disruption is required, two login roles inheriting one privilege role enable phased secret transitions. Whenever credentials leak, remember **changing a password does not automatically terminate active authenticated sessions**.

Final principle: **authenticate properly with SCRAM, protect traffic with TLS, bound actions with PostgreSQL privileges, and govern secrets as sensitive assets with owners, rotation, revocation, monitoring, and incident response**.
