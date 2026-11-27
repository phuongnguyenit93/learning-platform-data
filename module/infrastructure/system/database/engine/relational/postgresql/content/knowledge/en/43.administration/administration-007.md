# Managing Secrets and Changing Passwords

PostgreSQL authenticates users through database roles. A role with the `LOGIN` attribute can connect to a database; when password authentication is used, PostgreSQL validates the client-supplied password against a password verifier stored in the catalog. Credential management therefore encompasses multiple tasks: choosing an authentication mechanism, generating strong passwords, protecting secrets at rest and in transit, distributing them to applications, rotating them periodically or during incidents, and revoking old access.

In production, changing a password is never just running a single SQL statement. An application may have dozens of instances, connection pools, PgBouncer, background workers, replication standbys, migration jobs, and monitoring agents. A new password can cause new connections to fail if secrets are not updated in sync; conversely, already-authenticated sessions generally remain active after a password changes. Rotation requires a plan for both credentials and connections.

This lesson covers PostgreSQL's role/password model, SCRAM-SHA-256, `pg_hba.conf` configuration, safe password-change operations, secret files and secret managers, staged rotation, connection pool refreshes, replication credentials, expiration/revocation, auditing, and runbooks. Examples assume production PostgreSQL accessed over a network by applications; exact policies must fit your version, drivers, proxies, and operational platform.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish between database roles, login roles, group roles, and password credentials.
2. Explain password verifiers and how PostgreSQL stores authentication data.
3. Choose SCRAM-SHA-256 over legacy MD5.
4. Configure `password_encryption` and `pg_hba.conf`.
5. Change passwords safely using `psql`, avoiding secret exposure in histories or logs.
6. Protect credentials in `.pgpass`, service files, secret managers, and containers.
7. Design password rotation for multi-instance applications.
8. Use separate login roles and group roles for zero-disruption staged rotation.
9. Refresh connection pools, PgBouncer, and background workers after rotation.
10. Rotate replication credentials and verify WAL receivers.
11. Understand password expiry, `NOLOGIN`, revocation, and session termination.
12. Distinguish password rotation from TLS certificate rotation.
13. Audit role changes, restrict privileges, and safeguard break-glass accounts.
14. Build runbooks and test rotation procedures.

## 2. Roles and Passwords in PostgreSQL

PostgreSQL uses roles to manage identities and privileges. A role can:

- Have `LOGIN` to connect.
- Have `NOLOGIN` to act as a group role or privilege-holding role.
- Have `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, and other attributes.
- Be a member of one or more other roles.
- Have a password verifier if password authentication is used.

Inspect roles in `psql`:

```sql
\du
```

Or query the catalog:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolvaliduntil
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

### Login Roles and Group Roles

A sound design separates login identity from business privileges:

- Login roles represent services or users and hold credentials.
- `NOLOGIN` group roles hold required `SELECT`/`INSERT`/`UPDATE`/`EXECUTE` privileges.
- Login roles are granted membership in the group role.

This allows creating new credentials without re-granting every object privilege for each identity.

## 3. Password Verifiers Are Not Plaintext Passwords

PostgreSQL does not need to store plaintext passwords to authenticate password-based logins. The internal `pg_authid` catalog stores password verifiers, such as SCRAM-SHA-256 or legacy MD5 hashes/verifiers.

Verifiers remain sensitive data:

- Anyone holding a verifier can attempt offline password guessing.
- Weak passwords are vulnerable to brute-force or dictionary attacks if a verifier leaks.
- Backups and global-role dumps may contain verifiers.
- Read access to `pg_authid` must be strictly restricted.

The `pg_roles` view masks the password field so ordinary users cannot read verifiers. Never grant broad read access to `pg_authid` and never paste verifiers into logs, tickets, or chat.

### Inspecting Verifier Types

DBAs may need to inventory verifier algorithms without exposing hash values. Querying `pg_authid` requires elevated privileges; run only in controlled administrative sessions:

```sql
SELECT
    rolname,
    CASE
      WHEN rolpassword LIKE 'SCRAM-SHA-256$%' THEN 'scram-sha-256'
      WHEN rolpassword LIKE 'md5%' THEN 'md5'
      WHEN rolpassword IS NULL THEN 'no password'
      ELSE 'other'
    END AS verifier_type
FROM pg_catalog.pg_authid
ORDER BY rolname;
```

Never `SELECT rolpassword` directly for reports. Reports only need role names and verifier types.

## 4. Password Authentication and pg_hba.conf

`pg_hba.conf` specifies which clients may connect, to which databases and users, from which addresses, and using which authentication method. PostgreSQL reads the file sequentially; the first matching line for a connection request decides the method. If authentication fails, the server does not fall through to subsequent lines.

A line has the form:

```text
TYPE  DATABASE  USER  ADDRESS  METHOD
```

Example:

```conf
hostssl  appdb  app_login  10.20.0.0/16  scram-sha-256
```

This line requires TLS and SCRAM password authentication for the specified role, database, and address range.

### Common Authentication Methods

| Method | Overview of Operation | Common Use Case |
|---|---|---|
| scram-sha-256 | Challenge-response based on SCRAM verifier | Modern password authentication |
| md5 | Legacy password mechanism | Legacy compatibility during migration |
| peer | Local authentication via OS user mapping | Local Unix sockets |
| cert | Authentication via client TLS certificate | Certificate-based identity |
| trust | No password required | Strictly isolated/special test environments only |
| reject | Rejects connection | Blocking a specific client group |

Avoid `trust` for production network connections. `peer` authentication also requires proper mapping and policy; it does not mean every local user is authorized to log in.

## 5. SCRAM-SHA-256

SCRAM is a challenge-response mechanism. Client and server use password-derived material to prove both sides know the credential without sending the plaintext password as a SQL value over the wire.

Advantages over MD5:

- Uses salted password verifiers and a stronger key derivation function.
- Resists certain offline attacks far better than legacy MD5.
- Supports channel binding in compatible clients and servers, binding authentication to the TLS channel.
- Recommended password authentication choice for new deployments.

SCRAM does not replace TLS. TLS is still required to protect session traffic, query results, other credentials, and server identity verification.

### Client Compatibility

Older PostgreSQL drivers may lack SCRAM support. Before switching production, verify versions of drivers, poolers, proxies, migration tools, backup tools, and monitoring clients.

## 6. password_encryption

The `password_encryption` setting determines which algorithm PostgreSQL uses when creating new password verifiers:

```sql
SHOW password_encryption;
```

Set it for the administrative session before creating or changing passwords:

```sql
SET password_encryption = 'scram-sha-256';
```

Or configure it in `postgresql.conf`:

```ini
password_encryption = 'scram-sha-256'
```

This setting does not automatically convert existing MD5 verifiers to SCRAM. Each role's password must be reset to generate a new verifier.

### When It Applies

A verifier is generated using the `password_encryption` value active at the moment the password is set. Changing the setting later does not rewrite stored verifiers.

## 7. Configuring pg_hba.conf for SCRAM

Example:

```conf
# Require TLS and SCRAM for application network access
hostssl  appdb  app_login  10.20.0.0/16  scram-sha-256

# Reject non-TLS connections from the application network
hostnossl  appdb  app_login  10.20.0.0/16  reject
```

Rule ordering matters. The `reject` rule must appear after matching `hostssl` rules; if placed earlier, it could block intended connections depending on match criteria.

### Inspecting Configuration

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_catalog.pg_hba_file_rules
ORDER BY line_number;
```

This view helps catch parse errors and inspect loaded rules. It does not prove which rule a specific client matches without evaluating all connection attributes and order.

After editing the file:

```sql
SELECT pg_catalog.pg_reload_conf();
```

Reloading HBA does not disconnect existing sessions. Check logs to confirm the configuration loaded without parse errors.

## 8. Changing Passwords Safely with psql

Never write real passwords directly inside SQL statements, shell commands, scripts saved to history, or CI logs. A safer interactive approach in `psql` is the meta-command:

```text
\password app_login
```

`psql` prompts for the new password twice and hashes/derives it before sending the change command. This avoids placing plaintext passwords into command histories or server statement logs as happens when typing directly in `ALTER ROLE`.

### Changing the Current Role's Password

```text
\password
```

### Changing Another Role's Password

The operator needs appropriate privileges. Never share terminal recordings or outputs containing secrets during operations.

## 9. ALTER ROLE and Password Exposure Risks

SQL syntax:

```sql
ALTER ROLE app_login PASSWORD 'new-secret';
```

Never use literal examples like this with production secrets. Passwords can leak into:

- Shell or `psql` history if entered interactively.
- SQL statement logs or error logs depending on logging configuration.
- Audit trails, query capture, and tracing.
- CI output, terminal transcripts, and screen recordings.
- Source code or migration files.

If automation must change passwords, use APIs/secret injection designed to suppress logging and transmit secrets securely. Never concatenate passwords into SQL strings inside scripts.

## 10. Creating Roles Following Least Privilege

Example creating a privilege-holding group role:

```sql
CREATE ROLE app_readwrite NOLOGIN;

GRANT CONNECT ON DATABASE appdb TO app_readwrite;
GRANT USAGE ON SCHEMA app TO app_readwrite;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO app_readwrite;
GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA app
TO app_readwrite;
```

Privileges for future objects require default privileges configured for the role that creates objects:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
TO app_readwrite;
```

Create a separate login role:

```sql
CREATE ROLE app_login_v1 LOGIN INHERIT;
GRANT app_readwrite TO app_login_v1;
```

Set the password interactively via `psql`:

```text
\password app_login_v1
```

Never grant `SUPERUSER` to application roles. Roles owning objects should be separated from runtime roles if the application does not need DDL.

## 11. Password Strength and Generation

Database passwords should be randomly generated by a password manager or secret manager with a cryptographic generator. Never use service names, hostnames, environments, dates, or predictable patterns.

Principles:

- Sufficient length and high entropy.
- Unique secrets per service and environment.
- Never reuse passwords across production, staging, and development.
- Never share passwords across unrelated applications.
- Never store passwords in source control.
- Restrict who can read or rotate secrets.
- Prefer secret managers that generate and store random secrets directly.

PostgreSQL core does not provide a full IAM password policy, password history, or approval workflow engine. Use an external policy/secret manager and do not assume the server enforces every strength rule automatically.

## 12. Managing Password Expiration

You can set a password expiration timestamp with `VALID UNTIL`:

```sql
ALTER ROLE app_login_v1
VALID UNTIL '2027-01-01 00:00:00+00';
```

Or remove the expiration:

```sql
ALTER ROLE app_login_v1 VALID UNTIL 'infinity';
```

### Meaning

`VALID UNTIL` limits how long password authentication remains valid. It does not terminate already-connected sessions, does not replace disabling a role, and is not an instant revocation mechanism across every authentication method.

### Choosing an Expiration Policy

Do not set expirations so short that they cause recurring outages unless reliable automated rotation is in place. For high-risk credentials or mandatory policies, coordinate expiration with secret distribution, pool refreshes, and owner notifications.

## 13. Checking Which Roles Have Password Expiration

```sql
SELECT
    rolname,
    rolcanlogin,
    rolvaliduntil
FROM pg_catalog.pg_roles
WHERE rolcanlogin
ORDER BY rolvaliduntil NULLS LAST, rolname;
```

`NULL` or `infinity` means no expiration timestamp is recorded in the catalog. Distinguish a role with no password from a role with a non-expiring password; `pg_roles` does not expose verifiers.

## 14. Migrating from MD5 to SCRAM

Migration should proceed in client batches to avoid locking out the entire application.

Procedure:

1. Inventory roles using password authentication.
2. Inventory client drivers, PgBouncer, proxies, and automation tools.
3. Upgrade clients lacking SCRAM support.
4. Set `password_encryption` to `scram-sha-256`.
5. Reset passwords for each login role to generate SCRAM verifiers.
6. Review HBA rules and switch methods to `scram-sha-256`.
7. Reload HBA.
8. Test new connections from every client type.
9. Monitor authentication failures.
10. Remove MD5 rules once no dependencies remain.

PostgreSQL can negotiate SCRAM even when an HBA rule specifies `md5` if the role already holds a SCRAM verifier on versions supporting that behavior. Even so, the end state should explicitly specify `scram-sha-256` in HBA so policies stay readable and auditable.

## 15. Checking SCRAM Compatibility

Before migration, build an inventory:

| Client | Items to Verify |
|---|---|
| Java JDBC driver | Version supporting SCRAM and TLS |
| .NET Npgsql | Driver version and auth negotiation |
| Go pgx/libpq | Library version and connection mode |
| Python psycopg | `psycopg`/libpq version |
| PgBouncer | SCRAM frontend/backend compatibility and `auth_file` |
| Backup/restore tools | Connections after HBA changes |
| Monitoring/exporters | Credentials and driver versions |
| Replication standbys | `primary_conninfo`/passfile and HBA |

Do not test only the newest `psql` binary. An older client can keep running inside a background worker or job scheduler and fail only when it reconnects.

## 16. Protecting Passwords in .pgpass

`libpq` supports a password file so applications and CLIs do not embed passwords in connection strings. On Unix-like systems, the default file is `.pgpass` in the home directory; it can be overridden via `PGPASSFILE`.

Format:

```text
hostname:port:database:username:password
```

Illustrative example without real secrets:

```text
pg-primary.internal:5432:appdb:backup_user:REPLACE_WITH_SECRET
```

### File Permissions

On Unix, `.pgpass` must have restrictive permissions, typically `0600`; if permissions are too permissive, `libpq` ignores the file. On Windows, the default file lives under `%APPDATA%\postgresql\pgpass.conf`.

### Escaping

Colons and backslashes inside fields must be escaped according to `pgpass` rules. The first matching entry for the connection parameters is used; entry order matters.

Never commit `.pgpass` into repositories or place it in web-served directories.

## 17. PGPASSWORD and Environment Variables

`libpq` honors the `PGPASSWORD` environment variable, but it should not be used for long-lived secret storage in production. Environment variables can leak via process inspection, diagnostics, crash dumps, orchestration metadata, or debugging tools depending on OS and privileges.

Prefer:

- Secret managers or short-lived secret injection.
- Password files with strict permissions.
- Mounted secret files in containers.
- Driver secret providers integrated with a vault.

If an environment variable is unavoidable in short-lived CI or jobs, restrict scope and lifetime, mask logs, and ensure runners are not shared with untrusted workloads.

## 18. Service Connection Files

`libpq` supports service files such as `pg_service.conf` to store host, port, database, user, and connection options. Service files can pair with password files:

```ini
[app-write]
host=pg-primary.internal
port=5432
dbname=appdb
user=app_login_v1
sslmode=verify-full
passfile=/run/secrets/pgpass
application_name=orders-api-write
```

Connect:

```sh
psql "service=app-write"
```

Service files do not need to store passwords. Keep config files and secret files with separate permissions; never put secrets into URIs, which easily show up in process lists and logs.

## 19. Secret Managers

A secret manager stores, distributes, versions, and controls access to credentials. Examples include cloud secret managers, HashiCorp Vault, or internal secret platforms.

Desired capabilities:

- Encryption at rest and in transit.
- IAM/RBAC and least privilege.
- Audit logs of who read or rotated secrets.
- Controlled versioning and rollback.
- Cryptographically secure secret generation.
- TTLs/leases for dynamic credentials where supported.
- Rotation events or notifications.
- Access policies tied to service identity and environment.

### PostgreSQL Does Not Auto-Sync with Secret Managers

Saving a new password in a secret manager does not change the PostgreSQL role password. Conversely, changing a password with `ALTER ROLE` does not update the secret manager. Rotation workflows must update both sides in a controlled order.

## 20. Secrets in Docker and Kubernetes

Never bake database passwords into container images or Dockerfiles. Never place raw secrets directly inside Kubernetes manifests committed to source control.

### Kubernetes Secrets

Kubernetes Secrets are typically base64-encoded in manifests and APIs. Base64 is not encryption. You must:

- Enable encryption at rest for etcd per platform policy.
- Restrict RBAC for reading and updating secrets.
- Avoid mounting secrets into containers that do not need them.
- Never log environment or secret contents.
- Use external secret manager integrations where appropriate.
- Rotate and revoke service account access.

### Mounted Files vs. Environment Variables

Mounted secret volumes can update files when a Secret object changes per Kubernetes semantics, whereas container environment variables do not automatically update inside a running process. Applications must support re-reading/reloading or pod rollouts. Connection pools must still open new connections using the new credential.

## 21. Password Rotation vs. Connection Refresh

Once PostgreSQL authenticates a connection, that session does not re-check the password on every query. Therefore:

- Changing a password invalidates the old credential for new authentication attempts.
- Already-open sessions usually keep running.
- Pools can continue handing out idle connections authenticated earlier with the old password.
- When a pool opens a new connection, it must use the new password.
- Setting a role `NOLOGIN` or terminating sessions has a different impact than merely changing the password.

This is why rotation requires a pool refresh plan rather than only updating the secret value.

## 22. A Role Has Only One Password Verifier at a Time

A standard PostgreSQL role has a single active password verifier. Changing the password for that same role overwrites the old verifier; there is no native mechanism for one role to accept two independent passwords simultaneously during an overlap window.

This complicates rolling deployments when multiple application instances pick up new secrets at different times.

### Staged Rotation Solution

Use a new login role for the new credential while both login roles belong to a shared group role holding permissions:

```sql
CREATE ROLE app_login_v2 LOGIN INHERIT;
GRANT app_readwrite TO app_login_v2;
```

Set the new role's password using `psql`:

```text
\password app_login_v2
```

Applications gradually switch to `app_login_v2`. Once all clients use the new role, disable the old role and handle remaining sessions.

## 23. Staged Password Rotation for Applications

Reference zero/low-downtime procedure:

1. Confirm the group role and runtime privileges are separated from the login role.
2. Create a new versioned login role.
3. Grant membership of the group role to the new login role.
4. Set the new password via secure interactive or automated flow.
5. Store the new secret version in the secret manager.
6. Test login from a canary instance.
7. Roll out the new secret in batches.
8. Open new connections and confirm authentication succeeds.
9. Monitor connection distribution by `application_name` and user.
10. Once all clients have switched, disable the old login role.
11. Terminate old sessions per change plan if required.
12. Drop the old role after resolving grants, ownership, and dependencies.

### Why Use a Canary?

A canary validates password, HBA rules, TLS, role membership, database `CONNECT`, and object privileges before full rollout. One successful `psql` login is insufficient if the application uses a different driver or pooler.

## 24. Single-Role Rotation When Dual Roles Are Not Feasible

Some managed services or legacy applications do not easily support dual login roles. In that case, coordinate a cutover:

1. Prepare the new secret and confirm the rollout path.
2. Choose a change window or fast synchronization mechanism.
3. Change the role's password in PostgreSQL using a secure flow.
4. Immediately update the secret manager and configuration.
5. Reload, restart, or recreate pools per platform.
6. Verify every instance can establish new connections.
7. Maintain a bounded, audited rollback procedure.

Because the old verifier is replaced immediately, clients that have not received the new secret will fail on reconnect. Assess downtime risk before picking this approach.

## 25. Disabling the Old Role

After staged rotation:

```sql
ALTER ROLE app_login_v1 NOLOGIN;
```

`NOLOGIN` blocks new logins as that role. It does not terminate existing sessions.

Check active sessions:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    backend_start
FROM pg_catalog.pg_stat_activity
WHERE usename = 'app_login_v1'
ORDER BY backend_start;
```

If policy demands immediate revocation, assess and terminate remaining sessions with appropriate administrative privileges.

## 26. Terminating Old Sessions

Use `pg_terminate_backend` after verifying exact target sessions:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_catalog.pg_stat_activity
WHERE usename = 'app_login_v1'
  AND pid <> pg_backend_pid();
```

Never run bulk termination without evaluating in-flight transactions. Termination can roll back transactions, fail jobs, or leave clients uncertain whether a transaction committed.

### Termination and Pool Behavior

Poolers and applications may auto-reconnect. If the old role is still allowed to log in, connections can reappear immediately. Disable login or change credentials before terminating to prevent reconnect loops using the old secret.

## 27. Revoking Passwords and Login Capability

You can:

- Set the role `NOLOGIN` to block new logins.
- Change the password to an undistributed random value.
- Set the password to `NULL` so no password verifier exists.
- Edit `pg_hba.conf` to `reject` a source or role.
- `REVOKE CONNECT` per database.
- Terminate existing sessions.

These mechanisms have distinct semantics. For instance, `REVOKE CONNECT` does not close open sessions; `NOLOGIN` does not terminate active backends. Pick the mechanism matching your revocation goal.

## 28. NULL Passwords and NOLOGIN Roles

Setting a NULL password:

```sql
ALTER ROLE app_login_v1 PASSWORD NULL;
```

This removes the password verifier for the role; password authentication cannot log in as that role. Other authentication methods such as `cert` or `peer` follow their own policies and HBA rules.

`NOLOGIN`:

```sql
ALTER ROLE app_login_v1 NOLOGIN;
```

`NOLOGIN` blocks the role from opening new connections regardless of authentication method. It is generally the clearer choice when disabling a role's entire login capability.

## 29. REVOKE CONNECT and Database Privileges

You can restrict `CONNECT`:

```sql
REVOKE CONNECT ON DATABASE appdb FROM app_login_v1;
```

Keep in mind:

- `CONNECT` may be granted via `PUBLIC` or another role membership.
- The role may hold `CONNECT` through a separate grant.
- `REVOKE` does not close existing sessions.
- HBA rules can block connections before privilege checks run.

Verify ACLs and role memberships before treating `REVOKE` as complete revocation.

## 30. Password Rotation for PgBouncer

PgBouncer authenticates clients and opens backend connections to PostgreSQL. Distinguish:

- Frontend authentication: applications logging into PgBouncer.
- Backend authentication: PgBouncer logging into PostgreSQL.

Credentials and verification data may come from `auth_file` or `auth_query` depending on configuration. When rotating passwords:

1. Identify which roles and secrets are used for client auth and backend auth.
2. Update the secret and auth source.
3. Verify SCRAM compatibility for your PgBouncer version.
4. Reload config or auth files if needed.
5. Open a new backend connection to verify.
6. Reconnect/drain old server connections per maintenance plan.
7. Inspect `SHOW CLIENTS`, `SHOW SERVERS`, and logs.

Reloading the auth file does not automatically replace existing server connections. Verify backend connections and client reconnect behavior separately.

## 31. PgBouncer auth_file and SCRAM

An auth file can store password verifiers instead of plaintext in supported configurations and versions. Supporting SCRAM verifiers for frontend or backend auth depends on PgBouncer version and `userlist`/`auth_query` setup.

### Protecting the Auth File

- Restrict file permissions to the service account only.
- Never commit the file to repositories.
- Never attach the file to tickets or logs.
- Maintain an owner, version, and rotation process.
- Reload in a controlled manner and verify.

If using `auth_query`, the lookup role must hold minimum privileges per PgBouncer guidance; never grant broad read access on `pg_authid` to application roles.

## 32. Rotation for Replication Users

Physical standbys use credentials in `primary_conninfo` to connect to the primary. An example configuration can reference a password file:

```text
primary_conninfo = 'host=pg-primary.internal port=5432 user=replicator application_name=standby_a passfile=/run/secrets/replication.pgpass'
```

Create a replication role with least privilege:

```sql
CREATE ROLE replicator LOGIN REPLICATION;
```

Set the password via `psql`:

```text
\password replicator
```

Rotation requires updating the secret on all standbys, verifying HBA rules for replication connections, and prompting WAL receivers to reconnect as appropriate. Changing the password on a single shared role causes un-updated standbys to fail on reconnect.

## 33. Rotating Replication Credentials with Staged Roles

To avoid changing a single credential shared across multiple standbys simultaneously:

1. Create a new replication role with `LOGIN REPLICATION`.
2. Set the new password via a secure flow.
3. Add matching HBA rules for standby addresses.
4. Update `primary_conninfo`/passfile on each standby.
5. Reload/reconnect WAL receivers and confirm streaming.
6. Monitor `pg_stat_replication` on the primary.
7. Once all standbys use the new role, disable the old role.
8. Revoke the old role after confirming no consumers remain.

The new role needs `REPLICATION` and required connection rights—never `SUPERUSER`. Restrict source addresses in `pg_hba.conf`.

## 34. Verifying Replication After Rotation

On the primary:

```sql
SELECT
    application_name,
    usename,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

On the standby:

```sql
SELECT
    status,
    sender_host,
    sender_port,
    slot_name,
    written_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_wal_receiver;
```

View names and columns can vary by PostgreSQL version. Confirm streaming state and lag after rotation.

## 35. Rotation for Logical Replication and CDC

Logical replication subscriptions store connection details in subscription catalogs. Subscription credentials must be treated as highly restricted secrets.

Inspect subscription metadata using version-appropriate views/catalogs; never print connection strings containing passwords into outputs or tickets.

When rotating:

1. Identify the publisher role and every subscription consumer.
2. Create a new login role with required replication/select privileges.
3. Update subscription credentials securely via mechanisms supported by your PostgreSQL version.
4. Verify connections and apply workers.
5. Disable the old role after all subscribers switch.
6. Monitor replication lag and worker errors.

Never copy connection strings containing passwords into shell command history or logs.

## 36. Credentials for Backups, Monitoring, and Migrations

Never share an application superuser or a single password across all automation. Create separate task-specific roles:

| Role | Required Privileges |
|---|---|
| backup role | Backup privileges matching tool and version |
| monitoring role | Read required metrics and catalogs |
| migration role | DDL scoped to managed schemas |
| application role | Minimal runtime DML |
| replication role | `REPLICATION` and replication connections |
| break-glass role | Tightly controlled emergency administrative rights |

Each role needs an owner, purpose, secret location, rotation cadence/trigger, and consumer inventory.

## 37. Credential Inventory

An inventory should record:

- Role name and owner.
- Purpose, service, and environment.
- Database/cluster scope.
- Authentication method.
- Secret manager path/version reference—never the secret value.
- Consumer instances and jobs.
- Rotation date and expiry.
- Last successful rotation.
- Revocation procedure.
- Break-glass dependencies if any.

Never store plaintext passwords in an inventory. Store only references to secret objects and operational metadata.

## 38. Secret Rotation Triggers

Rotation can be triggered by:

- Policy rotation schedules.
- Personnel departures or access changes.
- Suspected secret exposure in source, logs, or tickets.
- Compromise or suspicious login activity.
- Vendor or secret manager rotation mandates.
- Certificate or identity policy changes.
- Service ownership or environment transfers.

If a secret leaks, treat it as an incident: revoke/rotate immediately per containment plan, inspect audit logs, and determine exposure scope. Never wait for the next scheduled rotation window.

## 39. Rotation Cadence and Password Expiry

No single cadence suits every credential. Pick cadence based on:

- Privilege level.
- Exposure surface.
- Secret lifetime or lease.
- Ability to automate rotation.
- Blast radius if compromised.
- Ability to synchronize all consumers.

High-privilege or externally exposed credentials require tighter controls. Dynamic short-lived credentials reduce secret lifespan, provided applications and poolers renew and reconnect properly.

## 40. Dynamic Credentials

Some secret managers issue temporary credentials by creating PostgreSQL roles with TTLs and revoking them when leases expire.

Benefits:

- Reduces long-lived static passwords.
- Gives each service or instance its own identity.
- Simplifies tracing consumers in audits.
- Enforces lease-based revocation.

Risks:

- Systems must renew leases before expiration.
- Pools must open new connections using fresh credentials.
- Role lifecycles and grants must be safely automated.
- Secret manager outages can disrupt reconnects.
- Existing sessions may survive lease revocation depending on the mechanism; understand termination policy.

Dynamic credentials do not automatically solve connection lifecycle or authorization design.

## 41. TLS and Passwords Are Two Distinct Protection Layers

Passwords authenticate the user/role. TLS protects the channel and can verify server identity. A strong password does not prevent MITM attacks if the client does not verify the server certificate.

Illustrative connection string:

```text
host=pg-primary.internal
dbname=appdb
user=app_login_v2
sslmode=verify-full
```

`verify-full` requires TLS and verifies the certificate chain and hostname against client trust stores. `sslmode=require` encrypts the channel without the same hostname verification.

### hostssl in HBA

Use `hostssl` for network connections requiring TLS. Combine with strict server certificate/private key permissions and client trust stores. Never disable certificate verification just to make a connection succeed.

## 42. Client Certificate Authentication

PostgreSQL supports certificate authentication via the HBA `cert` method. It authenticates clients using TLS certificates mapped to database roles.

Example:

```conf
hostssl  appdb  app_cert_user  10.20.0.0/16  cert
```

Certificate auth requires a client certificate, private key, CA trust, and certificate-to-role mapping if certificate names differ from role names. Protect private keys like password secrets; certificate expiration and revocation require rotation workflows.

### Certificates Do Not Grant Object Privileges

Authentication establishes identity as a role. Authorization still depends on PostgreSQL privileges, ownership, and role memberships.

## 43. Role Membership and Privileges After Rotation

The new login role must receive the exact group role memberships. Verify:

```sql
SELECT
    member.rolname AS member_role,
    parent.rolname AS granted_role
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member
  ON member.oid = m.member
JOIN pg_catalog.pg_roles AS parent
  ON parent.oid = m.roleid
ORDER BY member_role, granted_role;
```

Newer PostgreSQL versions include membership options such as `INHERIT`, `SET`, and `ADMIN` per grant. Verify behavior for your version and confirm the new role has required privileges without over-privileging.

## 44. Ownership and Cleaning Up Old Login Roles

Avoid letting application login roles own databases, schemas, or tables when a separate owner role can be used. When dropping an old role, PostgreSQL refuses if the role still owns objects or holds grants/dependencies.

Inspect ownership and privileges before dropping. In environments with legacy ownership, you may need:

```sql
REASSIGN OWNED BY app_login_v1 TO app_owner;
DROP OWNED BY app_login_v1;
```

These commands have wide impact inside the current database and can revoke or drop grants. Run only after reviewing dependencies in the exact target database; never treat them as default cleanup for every rotation.

## 45. Auditing Role and Password Changes

You need visibility into:

- Who created, altered, or disabled a role?
- When did the change occur?
- Which change ticket or approval authorized it?
- Which role received memberships?
- Which HBA rules changed?
- Which secret manager version was rolled out?
- Which consumers reconnected?

PostgreSQL logs, configuration management, audit extensions, and secret manager audit logs complement one another. Never record plaintext passwords or verifiers in audit events.

### log_connections and log_disconnections

Enable connection/disconnection logging to aid investigations. Weigh log volume, privacy, and retention. These logs do not replace auditing role DDL or secret manager audit trails.

## 46. Detecting Suspicious Logins

Monitor for:

- Sudden spikes in authentication failures.
- Roles logging in from unusual source IPs or regions.
- Unplanned `SUPERUSER` or `CREATEROLE` usage.
- Old login roles continuing to open sessions post-cutover.
- Service accounts active outside expected schedules.
- Unusual secret manager reads.

Correlate PostgreSQL logs, network identity, cloud IAM, and application telemetry. Never rely on `client_addr` alone if traffic traverses NAT or proxies.

## 47. Break-Glass Credentials

A break-glass account is an emergency administrative credential used when primary IAM or secret manager systems fail.

Policies should enforce:

- Never used in daily operations.
- Tightly controlled storage and retrieval access.
- MFA and administrative approval where available.
- Auditing of every retrieval and use.
- Periodic usability testing.
- Mandatory rotation after every use.
- At least one recovery path during secret manager outages.

Never paste break-glass passwords in runbook documents or chat.

## 48. Managed PostgreSQL Services

Managed database services may restrict `SUPERUSER`, filesystem access, HBA editing, or role attributes. Master/admin password and certificate rotation may be governed by the provider's control plane.

Before running SQL:

- Check the service's role restrictions.
- Identify the secret source of truth.
- Check how the provider updates connection endpoints and certificates.
- Confirm behavior when rotating admin passwords.
- Check maintenance and restart implications.

Do not assume every self-managed Linux filesystem path or system command exists in a managed service.

## 49. Connection Pools After Password Rotation

After rolling out a new secret:

- Already-authenticated idle connections may still work.
- Active connections do not automatically switch credentials.
- Pools opening new connections must read the new secret.
- Some pools read environment/config only at startup.
- Some pools support secret providers or reload callbacks.

Design a clear pool lifecycle:

1. Update the secret reference.
2. Reload/recreate the pool or soft-evict idle connections.
3. Open a canary connection.
4. Verify authentication and database role.
5. Drain old connections.
6. Count sessions still using the old login role.

## 50. Kubernetes Secret Updates and Application Reloads

Mounted secret files can update via projected volume mechanics, but the application process must re-read the file. Environment variables injected at container startup generally do not change inside running processes.

Therefore:

- Use file watchers or reload hooks if supported by the application.
- Or execute a controlled rolling restart.
- Configure readiness probes so traffic routes only when new pools are healthy.
- Cap surge replicas so connection budgets are not exceeded.
- Verify every pod uses the new secret version.

Never delete the old secret from the secret manager before confirming all consumers have switched.

## 51. Rotation in CI/CD and Migration Jobs

CI/CD credentials often live in runners, pipeline variables, deployment agents, and migration tools.

Safeguards:

- Use short-lived credentials if supported by the platform.
- Mask secret output.
- Disable shell tracing while handling secrets.
- Never pass passwords as command-line arguments.
- Separate migration roles from runtime application roles.
- Restrict runner network access.
- Securely delete temporary files and lock down permissions.
- Audit pipeline identities and secret reads.

Migration jobs may run hours after deployment; inventory all scheduled jobs before revoking an old login role.

## 52. Rotation and Failover

Avoid performing password rotation concurrently with failover whenever possible, as simultaneous changes make it hard to separate authentication failures from topology failures.

If unavoidable:

1. Confirm the current primary via the HA control plane.
2. Confirm standby and replication state.
3. Pick one role/credential path and test on the new primary.
4. Update all consumers and standbys.
5. Verify reconnects and replication.
6. Revoke the old credential only once topology stabilizes.

Credentials must work on the promoted node and must not depend on a stale host or IP.

## 53. Handling Compromised Credentials

When a password is found in source code, logs, tickets, or terminal transcripts:

1. Identify the role, cluster, scope, and exposure duration.
2. Restrict access to the artifact containing the secret.
3. Rotate or disable the credential per containment plan.
4. Migrate consumers to the new credential.
5. Terminate old sessions if required.
6. Inspect login/audit logs and suspicious activity.
7. Check whether the secret was reused in other systems.
8. Scrub copies from repos, logs, and tickets per retention policy.
9. Document the incident timeline and evidence.
10. Fix the process that caused the secret leak.

Do not merely remove the secret from the current file; Git history, CI artifacts, backups, and logs may still retain old copies.

## 54. Troubleshooting: Password Authentication Failed

Authentication failure errors can stem from:

- Wrong username or password.
- New password not yet rolled out to the instance.
- Role set to `NOLOGIN` or expired.
- HBA rule selecting a different method, address, or database than expected.
- Client lacking SCRAM support.
- Pooler using mismatched frontend and backend credentials.
- Secret file permissions/format error or non-matching entry.
- Connecting to the wrong cluster or endpoint.

Procedure:

1. Record client, host, database, role, and timestamp.
2. Verify the actual target server and cluster.
3. Check HBA rule matching and server logs.
4. Check role `LOGIN` and `VALID UNTIL`.
5. Check verifier type without printing hashes.
6. Check secret version and file permissions.
7. Test a fresh connection from the same client runtime.
8. Verify driver SCRAM support.

Never ask users to paste passwords into tickets or chats for debugging.

## 55. Troubleshooting: SCRAM Migration Breaks Clients

1. Identify client type and driver version.
2. Check SCRAM negotiation errors in client and server logs.
3. Verify whether the role already has a SCRAM verifier.
4. Check `password_encryption` prior to the latest password reset.
5. Check HBA rules and rule ordering.
6. Upgrade drivers, poolers, or tools lacking SCRAM support.
7. Reset passwords using a secure flow to generate SCRAM verifiers.
8. Test a canary before full rollout.
9. Monitor authentication failure rates.

Never fall back to `trust` or disable password auth to work around compatibility errors.

## 56. Troubleshooting: Application Still Uses Old Credentials

1. Check the secret manager version on each instance.
2. Check whether environment variables or file mounts updated.
3. Check whether the process reloaded the secret.
4. Check application pools for stale idle connections.
5. Check PgBouncer auth sources and backend connections.
6. Check jobs, workers, and scheduled tasks outside the API fleet.
7. Recreate or soft-evict pools per rollout plan.
8. Disable the old role and watch reconnect attempts.

## 57. Troubleshooting: Standby Stops Streaming After Rotation

1. Identify the standby and when the WAL receiver stopped.
2. Inspect PostgreSQL standby logs.
3. Verify the current primary endpoint and role.
4. Check `primary_conninfo` and passfile path/permissions.
5. Check `pg_hba` replication rules and source addresses.
6. Confirm the role has `LOGIN` and `REPLICATION`.
7. Test authentication using an appropriate client.
8. Update secrets, reload, and reconnect per procedure.
9. Verify `pg_stat_wal_receiver` is streaming.
10. Monitor replay lag and retained WAL.

## 58. Runbook: Staged Rotation for Application Logins

1. Inventory every consumer of the old login role.
2. Confirm the group role holds all required runtime privileges.
3. Create the new login role with least privilege.
4. Grant the group role to the new login role.
5. Set the new password via `psql` or secure automation.
6. Create the new secret version.
7. Test a canary connection with the production driver.
8. Roll out in batches while monitoring auth errors.
9. Confirm all app instances, workers, and jobs use the new role.
10. Disable the old login role.
11. Terminate old sessions per change plan.
12. Revoke/drop the old role after resolving dependencies.
13. Audit the rotation and update the inventory.

## 59. Runbook: Emergency Credential Compromise

1. Declare an incident and designate an owner/commander.
2. Identify the role, privileges, consumers, and exposure scope.
3. Decide between immediate disablement or staged replacement based on impact.
4. Provision replacement credentials/roles in the secret manager.
5. Update PostgreSQL auth and consumers.
6. Block new logins using the exposed credential.
7. Terminate remaining sessions if containment requires it.
8. Inspect logs, source IPs, and privileged actions.
9. Scrub artifact copies and check for secret reuse.
10. Verify services operate cleanly with the new credential.
11. Preserve evidence and post-incident follow-ups.

## 60. Runbook: SCRAM Migration

1. Inventory roles using password authentication.
2. Inventory all client libraries and tools.
3. Upgrade clients lacking SCRAM support.
4. Set `password_encryption=scram-sha-256`.
5. Reset passwords per role using a secure method.
6. Verify verifier algorithms without exposing hashes.
7. Update HBA methods to `scram-sha-256` by group.
8. Reload HBA and inspect `pg_hba_file_rules`.
9. Test fresh connections from every client class.
10. Remove MD5 rules once complete.
11. Monitor auth failures and update documentation.

## 61. Runbook: Rotating Replication Credentials

1. Inventory all physical and logical replication consumers.
2. Create a new replication login role and password.
3. Update HBA rules restricting exact source addresses.
4. Update passfiles, `primary_conninfo`, and subscription credentials.
5. Reload/reconnect each consumer in sequence.
6. Verify WAL receivers and `pg_stat_replication`.
7. Monitor lag and apply errors.
8. Confirm no consumers still use the old role.
9. Set the old role to `NOLOGIN`.
10. Revoke the old role once topology is stable.

## 62. Secrets and Password Management Checklist

### Identity and Privileges

- Every service has its own login role.
- Runtime privileges live in `NOLOGIN` group roles.
- Never grant `SUPERUSER` to applications.
- Replication, backup, monitoring, and migration roles are separated.
- Roles have clear owners and purposes.

### Passwords and Authentication

- Use `SCRAM-SHA-256` for password auth.
- Client drivers and poolers support SCRAM.
- Passwords are randomly generated and unique per service.
- Never record plaintext passwords in SQL history, logs, or source.
- `pg_hba.conf` restricts databases, users, and addresses, preferring TLS.
- Password verifiers and catalog backups are protected.

### Secret Distribution

- Secret manager is the source of truth.
- RBAC, auditing, and versioning are enabled.
- Never bake secrets into images or manifests.
- `.pgpass`/passfiles have strict permissions.
- Never log environment variables or connection URIs with secrets.
- Containers/pods mount only required secrets.

### Rotation and Revocation

- Complete inventory of consumers exists.
- Staged rotation or cutover plan is defined.
- Connection pools and PgBouncer are refreshed.
- Replication, backup, and monitoring jobs are tested.
- Old roles are disabled after cutover.
- Existing sessions are handled per policy.
- Expiry, revocation, and rollbacks are documented.

### Auditing and Incident Response

- Role changes and secret reads are audited.
- Break-glass accounts are tightly controlled.
- Credential compromise runbooks exist.
- Auth failures are monitored after rotation.
- Never send passwords via chat or tickets.

## 63. Common Mistakes

**Sharing one role/password across all services.** Impossible to revoke one consumer without breaking the rest.

**Putting plaintext passwords in ALTER ROLE commands.** Secrets can land in command histories or logs.

**Assuming changing a password disconnects old sessions.** Existing sessions normally keep running until closed or terminated.

**Updating the secret manager without refreshing pools.** Pools may continue serving old idle connections and fail only when opening new ones.

**Rotating a single role during a rolling deployment without overlap.** Un-updated instances fail when opening new connections.

**Granting SUPERUSER to application roles.** A leaked credential compromises the entire cluster.

**Treating Kubernetes Secret base64 as encryption.** Encryption at rest, RBAC, and secret lifecycle controls are still required.

**Using PGPASSWORD long-term.** Environment variables can leak through process and debugging surfaces.

**Rotating passwords while forgetting replication, PgBouncer, backups, and scheduled jobs.** Infrequently running consumers may fail days later.

**Using trust to work around SCRAM compatibility.** Weakens the authentication posture.

**Dropping the old role immediately after the first rollout.** Confirm all consumers, sessions, and dependencies are cleared first.

## 64. Practice Exercises

### Exercise 1 — PostgreSQL Roles

Distinguish between a `LOGIN` role, a `NOLOGIN` group role, and an owner role. Design roles for an orders service.

### Exercise 2 — Password Verifiers

Why is a password verifier still sensitive even though it is not plaintext? Where might verifiers be stored?

### Exercise 3 — SCRAM

Explain SCRAM-SHA-256 challenge-response and why TLS is still required.

### Exercise 4 — password_encryption

Set `password_encryption` to `scram-sha-256`. Why do roles with MD5 verifiers not convert automatically?

### Exercise 5 — pg_hba.conf

Write a `hostssl` rule for `appdb`/`app_login` from subnet `10.20.0.0/16` using `scram-sha-256`. Explain rule ordering.

### Exercise 6 — psql Password Change

Use `psql` `\password` to change a password. Why is this safer than writing a literal `ALTER ROLE ... PASSWORD` in a terminal?

### Exercise 7 — Least Privilege

Create a `NOLOGIN` group role with DML privileges in schema `app` and a separate login role granted membership.

### Exercise 8 — Default Privileges

Design default privileges so new tables created by `app_owner` automatically grant appropriate rights to `app_readwrite`.

### Exercise 9 — Password Strength

Propose a random password generation policy for service accounts. Why must secrets not be reused between staging and production?

### Exercise 10 — VALID UNTIL

Set a password expiration on a role and explain why existing sessions are not disconnected when the password expires.

### Exercise 11 — MD5 Migration

Design an MD5-to-SCRAM migration for 20 application services and 5 automation clients.

### Exercise 12 — Client Compatibility

An older Java driver lacks SCRAM support. Build an inventory and upgrade rollout plan before switching HBA.

### Exercise 13 — .pgpass

Explain `.pgpass` format, file permissions, and escaping for colons and backslashes.

### Exercise 14 — PGPASSWORD

Why can the `PGPASSWORD` environment variable leak? Propose safer alternatives.

### Exercise 15 — Service Files

Write a `pg_service.conf` entry using `sslmode=verify-full` and a separate passfile.

### Exercise 16 — Secret Managers

List required capabilities for a secret manager storing PostgreSQL production credentials.

### Exercise 17 — Kubernetes Secrets

Why is base64 not encryption? Specify needed RBAC, encryption at rest, and mount policies.

### Exercise 18 — Existing Sessions

A role's password changed yet queries on old sessions keep running. Explain this behavior and its impact on connection pools.

### Exercise 19 — Dual Login Roles

Design `app_login_v1` and `app_login_v2` both inheriting `app_readwrite` for zero-disruption rotation.

### Exercise 20 — Single-Role Rotation

A legacy application does not support dual login roles. Design a cutover plan and assess downtime risk.

### Exercise 21 — NOLOGIN

Set an old role to `NOLOGIN`. Why must existing sessions still be checked and handled separately?

### Exercise 22 — pg_terminate_backend

Write a query listing sessions by `usename`/`application_name` and describe the risks of terminating active transactions.

### Exercise 23 — PASSWORD NULL

Compare `PASSWORD NULL` with `NOLOGIN`. When should all login capability be disabled?

### Exercise 24 — REVOKE CONNECT

Why is `REVOKE CONNECT` insufficient to close active sessions? Which grant sources must be checked?

### Exercise 25 — PgBouncer

Distinguish frontend authentication from backend authentication. Design rotation for both sides.

### Exercise 26 — SCRAM auth_file

Why do PgBouncer version and `auth_query`/`auth_file` configuration affect verifier storage? How should the file be protected?

### Exercise 27 — Physical Replication

Create a dedicated `REPLICATION` role and design rotation for `primary_conninfo`/passfiles across three standbys.

### Exercise 28 — Replication Verification

Write queries checking `pg_stat_replication` and `pg_stat_wal_receiver` after rotating replication passwords.

### Exercise 29 — Logical Replication

Design credential rotation for a publisher role and multiple subscriptions without exposing connection strings.

### Exercise 30 — Backup/Monitoring Roles

Design separate roles for backups, monitoring, migrations, and runtime. Explain least privilege for each.

### Exercise 31 — Credential Inventory

Design an inventory containing no plaintext secrets while still tracking owners, consumers, secret references, expiry, and revocation procedures.

### Exercise 32 — Rotation Triggers

A production password was pasted into a ticket. Build the incident response and containment steps.

### Exercise 33 — Dynamic Credentials

Explain benefits and risks of short-lived PostgreSQL credentials and how pools renew and reconnect.

### Exercise 34 — TLS

Distinguish password authentication from TLS server verification. Why does `sslmode=require` differ from `verify-full`?

### Exercise 35 — Certificate Auth

Design client certificate authentication using HBA `cert`. Which private keys and CA materials require rotation?

### Exercise 36 — Role Memberships

Write a query listing member roles and granted roles. Why must membership options be verified against your PostgreSQL version?

### Exercise 37 — Ownership Cleanup

An old login role owns objects. Why is `DROP ROLE` refused, and why do `REASSIGN OWNED`/`DROP OWNED` require careful review?

### Exercise 38 — Auditing

Design an audit trail covering role changes, secret manager reads, pool refreshes, and successful cutover without logging passwords or verifiers.

### Exercise 39 — SCRAM Failure

After switching HBA to SCRAM, an exporter fails to connect. Write a troubleshooting procedure isolating driver, verifier, HBA, and secret file issues.

### Exercise 40 — End-to-End Rotation

A system has:

- A PostgreSQL primary and two physical standbys.
- 30 instances of an orders API behind PgBouncer.
- One logical replication subscriber for analytics.
- Backup jobs running every 6 hours.
- A monitoring exporter and migration runner.
- All currently sharing a single login role with an old password.
- A policy requiring immediate rotation upon suspected secret exposure.
- Applications supporting rolling deployments, alongside daily batch jobs.

Design:

1. A new role model with separate group roles and login roles.
2. A SCRAM migration and client compatibility plan.
3. A secret manager inventory per consumer.
4. Staged rotation using new login roles.
5. PgBouncer frontend/backend authentication refresh.
6. Physical and logical replication credential updates.
7. Backup, monitoring, and migration job cutover.
8. Session draining, `NOLOGIN`, and old-role cleanup.
9. Auditing, emergency revocation, and rollback plans.
10. Tests and metrics proving no consumer still uses old credentials.

## Conclusion

**Managing PostgreSQL passwords means managing identities, verifiers, privileges, secret distribution, and connection lifecycles.** Use SCRAM-SHA-256 for password authentication, protect verifiers and catalog backups, enforce TLS for network connections, and keep plaintext secrets out of SQL histories, source code, command lines, and logs. Separate login roles from group roles so runtime privileges remain reusable while credentials stay isolated.

Rotating a single role overwrites its active password verifier; PostgreSQL does not support two parallel passwords on one role. For rolling deployments, staged rotation via a new login role inheriting a group role minimizes risk. After cutover, disable the old role, drain or handle remaining sessions, and drop the role only once dependencies and ownership are resolved.

Never overlook PgBouncer, connection pools, physical/logical replication, backups, monitoring, and scheduled jobs. Password changes do not disconnect old sessions; secret manager updates do not refresh pools; `NOLOGIN` does not terminate active backends. Verify every consumer with fresh connections, audit every rotation, and keep runbooks ready for compromises and revocations.

**A reliable rotation workflow maintains a complete inventory, protects secrets, rolls out under control, verifies connection refreshes, and cleanly revokes old credentials.**
