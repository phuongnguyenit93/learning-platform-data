# Secret management, password rotation, and avoiding logging sensitive data in Oracle

## 1. Why is secret management part of database security?

An Oracle system has many kinds of secrets beyond database user passwords:
- Passwords for application accounts, integration accounts, and administrative accounts.
- Credentials used for database links, scheduler jobs, external jobs, and backup tools.
- Passwords or keys to open TDE keystores.
- Private keys and certificates used for TLS.
- API keys, tokens, and cloud service credentials.
- Credentials used by connection pools, ETL pipelines, monitoring, and deployment systems.

If secrets are stored in source code, configuration files, scripts, tickets, or logs, anyone lacking database privileges can still extract credentials to log in. Changing a password is also not as simple as running `ALTER USER`: every application, connection pool, job, and integration using that credential must be updated at the right time.

This lesson belongs to the **Security** chapter of the **Database Engine Relational Oracle** module. It focuses on three capabilities:

1. **Secret management:** identifying, storing, authorizing, monitoring, and revoking credentials/keys.
2. **Password rotation:** replacing credentials through a controlled process, updating all consumers, and verifying operation.
3. **Log protection:** logging sufficient information for investigation without exposing passwords, tokens, keys, or sensitive data.

The goal is not to log everything for debugging convenience. The goal is being able to trace who did what, when, where, and with what outcome without storing secret values.

## 2. Distinguishing secrets, configuration, and business data

Not every configuration value is a secret.

| Category | Examples | Handling |
|---|---|---|
| Secret | Passwords, API tokens, private keys, TDE keystore passwords | Secret manager, wallet/keystore, least privilege |
| Configuration | Hostname, port, service name, schema name | Configuration management; still under change control |
| Identifier | Username, client ID, wallet alias | May require contextual protection, not necessarily secret |
| Sensitive data | ID numbers, financial details, personal data | Classify, minimize collection, mask, and control access |
| Public data | Public service names, release numbers | Can be logged if needed |

A connection string can contain both configuration and secrets. For example, `host`, `port`, and `service_name` are generally not passwords, whereas a username/password or token embedded in a URI is a secret. Never log full connection strings when unsure of their contents.

### 2.1. Secrets must be protected in every state

Secrets can appear:
- During creation or provisioning.
- In transit from a secret manager to an application.
- In process memory.
- In configuration files or caches.
- In SQL statements, bind variables, or command lines.
- In logs, traces, dumps, and backups.
- During rotation and revocation.

Encryption at rest protects only part of the lifecycle. If an application writes passwords to logs or sends them over an unencrypted connection, encryption at rest does not solve that exposure.

### 2.2. Classification by impact

A practical classification:
- **Critical:** `SYS`, `SYSDBA`, TDE master keys, CA private keys, credentials with system-wide administrative privileges.
- **High:** service accounts with read/write access to sensitive data, backup/replication credentials.
- **Moderate:** application accounts with restricted privileges within a single schema.
- **Low:** credentials used for lab environments or synthetic data.

Classification level determines who may access secrets, retention rules, approval workflows, review frequency, and compromise response.

## 3. Secret management principles

### 3.1. One identity per workload

Avoid sharing one database account across multiple applications or environments whenever possible.

Example:
- `ORDER_API_USER`: accesses only objects needed by the order API.
- `REPORTING_USER`: reads only granted views/tables.
- `ETL_LOADER`: write access to staging areas and required ETL tasks.
- `MONITOR_USER`: holds only approved monitoring privileges.

When each workload has its own identity, a credential can be revoked or rotated without disrupting unrelated systems.

### 3.2. Least privilege

Grant only necessary privileges:
- Never use `SYS`/`SYSTEM` for applications.
- Never grant `DBA` just to make an application run.
- Restrict `ANY` privileges.
- Separate read, write, operational, and key-management privileges.
- Use appropriate roles for interactive work; evaluate direct grants when applications need privileges inside stored procedures per Oracle semantics.
- Inspect inherited privileges and role-granted privileges.

Even a strong credential creates huge risk if paired with overly broad privileges.

### 3.3. Secrets must never enter source code

Never commit passwords, tokens, wallet passwords, private keys, or wallet files to Git.

Never use:
- Hardcoded password strings in Java, Python, or PL/SQL.
- `.env` files containing secrets committed to repositories.
- Passwords baked into Docker images or build artifacts.
- Secrets in command line arguments.
- Secrets inside SQL comments or object names.
- Real secret values in shared configuration templates.

Configuration templates should hold only variable names or aliases, e.g., `DB_CREDENTIAL_ALIAS=orders-prod`, never real passwords.

### 3.4. Prefer short-lived credentials where possible

For supported workloads, prefer short-lived tokens or credentials over long-lived static passwords. A secret manager can issue credentials tied to workload identity and revoke them when no longer needed.

Oracle database authentication, wallets, Kerberos, TLS certificates, OCI IAM, or external authentication mechanisms each have specific deployment conditions. Select mechanisms matching your actual architecture and release.

## 4. Secure credential storage for Oracle applications

### 4.1. Oracle Wallet and Secure External Password Store

An Oracle Wallet can store credentials so clients connect to the database without putting username/password directly in commands or source code. Secure External Password Store (SEPS) allows clients to connect using a configured connect identifier/alias.

Once the wallet is properly configured, a client can connect using the external password store, for example:

```text
sqlplus /@orders_prod
```

`orders_prod` is a connect alias configured in Oracle Net. The command contains no username or password.

Key points to manage:
- Allow only the intended OS or service account to read the wallet directory.
- Prevent unrelated users from accessing via filesystem permissions.
- Protect wallet passwords and auto-login wallet files.
- Maintain protected backups and tested restore procedures.
- Have a procedure to rotate credentials inside the wallet.
- Never put wallets or `cwallet.sso` files in source control.
- Restrict copying wallets to other hosts or environments.

Auto-login wallets are convenient for unattended service startups, but a copied auto-login file can weaken protection if ACLs and host controls are lax. Consider local auto-login wallets where appropriate for the environment.

### 4.2. Oracle Net configuration

Client wallets must be configured per Oracle Net guidance for the exact version. Configuration can point to the wallet location and external password store options in `sqlnet.ora`.

Never put passwords in `tnsnames.ora` or connection URLs. Keep endpoint/service details in `tnsnames.ora`; keep credentials in the wallet.

### 4.3. Do not pass passwords via command line

A convenient command can inadvertently leave passwords in:
- Shell history.
- Process lists.
- Orchestration system logs.
- Build output.
- Terminal telemetry.

When using wallet management utilities, never put real passwords directly in saved or shared commands. Use interactive secure prompts, APIs/secret providers, or tool-supported input mechanisms. Never use documentation sample strings as deployment passwords.

### 4.4. Using the password prompt in SQL*Plus

For interactive use, SQL*Plus provides the `PASSWORD` command to prompt for passwords:

```sql
PASSWORD app_user
```

The client prompts for the input per command behavior. This is generally safer than typing passwords in `CONNECT user/password` or storing `ALTER USER` with real secrets in scripts.

For the current account, you can run:

```sql
PASSWORD
```

Exact prompt behavior depends on the client and authentication method. Disable terminal echo and avoid recording entered values in terminal transcripts.

## 5. User management and password policies in Oracle

### 5.1. Using profiles to enforce policies

Oracle Database profiles set password limits and certain resource limits for users. Common password parameters:

| Profile parameter | Purpose |
|---|---|
| `FAILED_LOGIN_ATTEMPTS` | Number of failed login attempts before locking the account per policy |
| `PASSWORD_LOCK_TIME` | Account lock duration |
| `PASSWORD_LIFE_TIME` | Password lifetime |
| `PASSWORD_GRACE_TIME` | Warning grace window after password expiration |
| `PASSWORD_REUSE_TIME` | Time interval before an old password can be reused |
| `PASSWORD_REUSE_MAX` | Number of password changes required before reuse |
| `PASSWORD_VERIFY_FUNCTION` | Password strength verification function |
| `INACTIVE_ACCOUNT_TIME` | Locks inactive accounts when supported by the version |

Do not apply one set of values to every user. Service accounts, human user accounts, and administrative accounts have different requirements. Values must match organizational security policy and Oracle release capabilities.

### 5.2. Profile creation example

Illustrative example—adjust per policy and confirm the verify function is installed:

```sql
CREATE PROFILE app_password_policy LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_MAX 10
    PASSWORD_REUSE_TIME 365
    PASSWORD_VERIFY_FUNCTION ORA12C_VERIFY_FUNCTION;
```

`ORA12C_VERIFY_FUNCTION` must exist in the database. Oracle provides sample scripts to install password verification functions; DBAs should review and adapt them before use. Never assume every database has this function pre-installed.

`PASSWORD_REUSE_TIME` and `PASSWORD_REUSE_MAX` must be configured as a pair to enforce reuse rules. Consult version-specific documentation on semantics when one value is `UNLIMITED`.

### 5.3. Assigning a profile to a user

```sql
ALTER USER app_user PROFILE app_password_policy;
```

Check profile and account status:

```sql
SELECT username,
       account_status,
       profile,
       expiry_date,
       authentication_type,
       password_versions
FROM dba_users
WHERE username = 'APP_USER';
```

Viewing `DBA_USERS` requires privileges; in restricted schemas, use an appropriate view like `USER_USERS`. Never query or export password hashes into logs/tickets. `PASSWORD_VERSIONS` is metadata about verifier versions, not plaintext passwords.

### 5.4. Checking active profile rules

```sql
SELECT profile,
       resource_name,
       limit
FROM dba_profiles
WHERE profile = 'APP_PASSWORD_POLICY'
  AND resource_type = 'PASSWORD'
ORDER BY resource_name;
```

A profile takes effect only when assigned to users. Modifying a profile affects every account sharing it; check the list of assigned users before modifying.

### 5.5. Password expiration does not replace planned rotation

`PASSWORD_LIFE_TIME` is a profile-based expiration mechanism. For service accounts, if a password expires before consumers are updated, applications can suddenly lose connectivity. Coordinate expiration with automated rotation, expiry monitoring, and deployment plans for new credentials.

Rotation frequency should match your threat model and policy. Rotating too frequently without automation increases operational failures and pushes people toward weak passwords or unsafe storage. When credential compromise is suspected, rotate/revoke immediately per incident response rather than waiting for scheduled expiration.

## 6. Rotating database user passwords

Password rotation is the process of replacing an active credential with a new credential, updating every consumer, and revoking the old value at the proper time.

### 6.1. Inventory before changing

Identify every consumer of the account:
- Applications and connection pools.
- Batch/ETL processes and scheduler jobs.
- Database links.
- Monitoring, backup, and deployment tools.
- Operational scripts.
- Stored procedures or external integrations.
- Standby, DR, or other nodes if dependent credentials exist.

Never assume only the primary application uses an account. A shared account may be embedded in lesser-known jobs.

### 6.2. Controlled rotation workflow

A typical workflow:

1. **Identify owners:** who owns the credential and each consumer.
2. **Schedule window:** choose a change window and notify relevant teams.
3. **Prepare new credential:** generate a strong random value via a secret manager or approved tool.
4. **Check consumers:** confirm applications support secret reload or pool recreation.
5. **Change password in Oracle:** use a secure administrative channel.
6. **Update secret store:** publish the new credential to the wallet/secret manager with proper access controls.
7. **Open new connections:** test login from each consumer.
8. **Refresh pools/jobs:** drain old connections and ensure new connections use the new credential.
9. **Monitor errors:** watch for logon failures, invalid credentials, job failures, and retries.
10. **Revoke old value:** once confirmed no consumers still need the old value.
11. **Record outcome:** timestamp, owner, account, updated consumers, and verification evidence—without recording secrets.

### 6.3. Changing passwords via DBA command

General administrative syntax:

```sql
ALTER USER app_user IDENTIFIED BY "<NEW_SECRET>";
```

`<NEW_SECRET>` is only a placeholder, not a real password. The statement may appear in SQL history, audits, traces, or management tools depending on execution method and configuration. Never place real secrets in shared scripts, source control, tickets, or terminal command history.

For interactive operations, prefer SQL*Plus/client password prompts. For automation, fetch secrets directly from a secret manager using supported secure mechanisms; restrict read permissions on outputs and execution history.

### 6.4. Post-change verification

Do not stop after seeing `ALTER USER` succeed. Verify:
- Fresh login with the new credential.
- Connections through the intended service name.
- Applications successfully open new connections.
- Connection pools do not indefinitely hold old connections.
- Jobs and batches run successfully.
- No consumers remain on the old credential.
- Account is not unexpectedly locked or expired.

Sessions already connected before the password change generally are not automatically disconnected solely because the password changed. Proactively refresh pools/sessions as planned; if compromise is suspected, terminate active sessions or lock the account per incident response.

## 7. Gradual password rollover

Some Oracle releases support **gradual password rollover**, allowing a transition window so applications can change passwords without updating every consumer simultaneously.

The relevant profile parameter is `PASSWORD_ROLLOVER_TIME`. Example:

```sql
ALTER PROFILE app_password_policy
LIMIT PASSWORD_ROLLOVER_TIME 7;
```

During the configured rollover window, the database accepts both old and new passwords per feature semantics. This supports rolling out new credentials across application groups incrementally.

### 7.1. Conditions and limits

- Verify your release and Release Update support the feature.
- Check user/authentication types and eligibility rules.
- Verify the profile assigned to the account.
- Consult Oracle documentation on rollover duration and end-of-period behavior.
- Test in staging with real applications and connection pools.

Never assume all accounts, external authentication methods, or Oracle versions handle rollover identically.

### 7.2. Rollover workflow

A general sequence:
1. Assign a profile with an appropriate rollover duration.
2. Change the password per Oracle procedures.
3. Distribute the new credential via the secret manager.
4. Update each consumer and verify new connections.
5. Monitor consumers still using the old credential.
6. End the rollover period and confirm only the new credential remains valid.
7. Revoke and purge stored copies of the old credential per policy.

Rollover is a bounded transition window, not an excuse to keep old passwords indefinitely. Assign owners and deadlines for every consumer.

## 8. Rotating credentials in connection pools

Java or middleware applications commonly maintain connection pools. When a password changes, the pool may still hold previously opened connections. When connections close and the pool opens new ones, old credentials may be reused if secrets were not reloaded.

### 8.1. Pool update steps

- The secret manager supplies the new credential to the workload.
- Datasource configuration picks up the new value.
- Recreate the pool or reload configuration per framework capabilities.
- Health-check using a new connection.
- Shift traffic to the new pool.
- Drain and close the old pool.
- Monitor authentication errors and connection churn.
- Revoke the old password once all pools have switched over.

Do not just edit a config file on disk and assume running processes picked up the new value. Many applications read secrets only at startup.

### 8.2. Blue/green connection pools

Two pools can be used:
- Blue pool using the old credential.
- New pool using the new credential.

After the new pool passes health checks, shift requests to the new pool and drain the old pool. This minimizes downtime, though infrastructure and applications must temporarily support two datasources.

### 8.3. Retry limits

If credentials are wrong, relentless retries can increment `FAILED_LOGIN_ATTEMPTS` and lock the account. Use backoff, circuit breakers, and alerts on repeated authentication failures. Never retry indefinitely with an old password.

## 9. Special Oracle credentials requiring separate inventory

### 9.1. Database links

Database links use credentials to connect to remote databases. For fixed-user database links, authentication info is stored in database metadata per Oracle mechanisms; do not try to recover plaintext passwords from it.

When a remote user's password changes, update/recreate the database link following supported procedures and verify queries using the link. Link creation DDL can include passwords in statements, so protect SQL history, audits, and deployment tools.

If the architecture supports current-user database links or external authentication, evaluate them to reduce static credentials. Not every database link pattern supports the same mechanism.

### 9.2. DBMS_SCHEDULER credentials

External jobs and certain job types require credential objects. Oracle provides APIs in `DBMS_CREDENTIAL`/`DBMS_SCHEDULER` depending on version.

Job credentials need:
- Clear ownership.
- Restricted usage privileges.
- Rotation synchronized with OS accounts or target services.
- Post-change job testing.
- No passwords passed through public scripts/logs.

When rotating credentials, check running jobs, upcoming scheduled runs, and credential execute privileges.

### 9.3. Password files and administrative accounts

Privileges such as `SYSDBA`, `SYSOPER`, `SYSBACKUP`, `SYSDG`, or `SYSKM` can involve password files and dedicated administrative authentication mechanisms.

Password file management requires checking:
- Database version and password file format.
- RAC and storage location in ASM or filesystem.
- Data Guard primary/standby.
- Nodes and administrative tools using the file.
- Synchronization and verification procedures after rotation.

Do not treat administrative password files like ordinary application users. Follow `orapwd`, `ALTER USER`, and Data Guard/RAC guidance for your exact release. Protect file read permissions and never copy files to unmanaged locations.

### 9.4. External non-database accounts

OS accounts, cloud accounts, backup agents, monitoring, and middleware are not fully governed by Oracle profiles alone. They require owners, secret stores, rotation schedules, and revocation procedures. Inventories should identify the authoritative identity provider for each.

## 10. TDE keystores, TLS, and key rotation

Database passwords and encryption keys are two distinct types of secrets. Changing a user password does not rotate the TDE master key; rotating the master key does not change application passwords.

### 10.1. TDE keystore

Transparent Data Encryption (TDE) uses a keystore/wallet to protect master encryption keys. Operational procedures must:
- Protect the keystore password.
- Restrict who can open/administer the keystore.
- Back up the keystore per Oracle guidelines.
- Ensure backups and disaster recovery hold matching keys.
- Test restoring and opening encrypted data.
- Log key rotation history without logging secrets.

### 10.2. Rotating the TDE master key

TDE master key rotation is a distinct administrative operation. `ADMINISTER KEY MANAGEMENT` syntax varies by release, CDB/PDB, and keystore state. General command pattern:

```sql
ADMINISTER KEY MANAGEMENT SET KEY
IDENTIFIED BY "<KEYSTORE_PASSWORD>"
WITH BACKUP USING 'before_key_rotation';
```

The placeholder is not a real password. Before executing, verify:
- Keystore is in the proper state.
- Target container/PDB and key scope are right.
- A secure keystore backup exists.
- RAC/standby and backup synchronization plans are ready.
- Restore testing is in place.
- Operator holds TDE administrative privileges.

Never delete old keys or keystore backups while retained datafile backups still need those keys for recovery.

### 10.3. TLS certificates and private keys

TLS certificates expire and require renewal/rotation. Track:
- Certificate chains and CAs.
- Hostnames/SANs.
- Expiration dates.
- Client trust stores.
- Private key permissions.
- Listener/client wallet configurations.
- Deployment timing to avoid client trust mismatches.

Never email or paste private keys into tickets. Never log private keys or keystore passwords in application startup logs.

## 11. How can logs leak sensitive data?

### 11.1. SQL text

If applications concatenate passwords or tokens directly into SQL literals, those values can appear in SQL text, the shared pool, audits, or traces depending on collection mechanisms.

Never embed secrets in SQL statements. Use bind variables for business data; for passwords and credentials, use proper authentication/secret management mechanisms rather than passing them as ordinary SQL parameters.

### 11.2. Bind values

Bind variables keep literals out of SQL text, yet bind capture or SQL tracing can record bind values. If binds hold account numbers, tokens, or personal data, logs/traces can still expose sensitive information.

Do not enable broad bind capture/tracing in production without assessing what data may be captured. Restrict target sessions, duration, access permissions, and retention.

### 11.3. Connection strings and exceptions

Common places credentials accidentally leak:
- JDBC URLs with embedded passwords.
- Serialized datasource configuration objects.
- Exceptions printing entire connection properties.
- HTTP Authorization headers or bearer tokens.
- Request bodies containing credentials.
- Environment dumps and diagnostic bundles.
- Startup scripts echoing environment variables.
- Command lines containing passwords.
- SQL Developer/SQLcl history or terminal transcripts.

Log only error codes and necessary context; never log full authentication configurations.

### 11.4. Traces and performance repositories

SQL Trace, TKPROF, `V$SQL`, bind capture, AWR/ASH, or SQL Monitor can contain SQL text, bind metadata, or sensitive data depending on configuration and statement type.

Trace files and repositories must be access-controlled, encrypted per policy, subject to retention, and purged systematically. Never attach raw trace files to public tickets or repositories.

## 12. Designing secure logs

### 12.1. Log metadata instead of secrets

A useful log entry typically includes:
- Timestamp with timezone or consistent system time standard.
- Application/service/module/action.
- Request ID or correlation ID.
- Database username or service identity per policy.
- `SQL_ID` or operation code.
- Relevant object/function.
- Success/failure outcome.
- Error code.
- Duration and row count if appropriate.
- Client/service context needed for investigation.

You do not need to log passwords, tokens, private keys, wallet contents, or full request bodies to troubleshoot a login failure.

### 12.2. Field allowlisting

Design loggers using allowlists: emit only pre-approved fields. Never automatically serialize entire request objects, datasource properties, environments, or exception contexts.

### 12.3. Masking and redaction

If an identifier must be logged, record only the minimum necessary portion, such as the last four characters when business rules allow. For tokens, avoid logging prefixes/suffixes if they still aid recovery or guessing. For passwords and private keys, log zero characters.

Redaction must happen before writing logs. Deleting logs after distribution does not guarantee all copies are purged.

### 12.4. Authorization and retention

Logs are assets needing protection too:
- Allow only authorized operations/security teams to read them.
- Separate log-writing permissions from log-modification/deletion permissions.
- Use centralized logging with TLS and access control.
- Protect archives and backups.
- Set retention per legal/business requirements.
- Monitor log access.
- Maintain an incident procedure for unintended secret exposure in logs.

Never retain logs indefinitely without a clear purpose.

## 13. Auditing in Oracle: traceability without collecting secrets

Auditing helps answer who performed which action, on which object, when, and with what outcome. Audit policies must align with security objectives and data volume.

### 13.1. Unified Auditing

Unified Auditing provides a central place to inspect configured audit records. Illustrative query:

```sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       client_program_name,
       module,
       action
FROM unified_audit_trail
WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER BY event_timestamp DESC;
```

Views and columns must be verified by version, privileges, and auditing configuration. This query selects investigative metadata without retrieving `SQL_TEXT` or `SQL_BINDS`.

### 13.2. Auditing critical events

Per policy, consider auditing:
- Successful and failed logons.
- Creating, altering, locking, unlocking, or dropping users.
- Role and system privilege changes.
- Profile changes.
- DDL on sensitive objects.
- Access to sensitive data tables.
- TDE/keystore administrative activities.
- Audit policy modifications.
- Operations on database links or credential objects if monitoring is required.

Scope policies on a need-to-know basis. Overly broad auditing spikes volume, complicates investigations, and collects unnecessary SQL text/binds.

### 13.3. Unified Audit and SQL text/binds

Some audit records may store SQL text or bind information depending on policy type, version, and configuration. Before enabling broad auditing, inspect which fields are captured and whether they could hold secrets or personal data.

When auditing password changes, prioritize capturing principal, timestamp, outcome, and source; never record old or new password values.

### 13.4. Fine-Grained Auditing

Fine-Grained Auditing (FGA) tracks specific accesses on objects/columns meeting conditions. FGA fits when narrow conditional auditing on sensitive data is needed.

FGA is not a secure password vault or a way to scrub secrets from application logs. Design audit conditions, handlers, and retention so sensitive values do not enter audit messages.

## 14. Safe SQL Trace and bind capture

SQL Trace helps analyze performance, but decide deliberately whether bind values are needed.

Example enabling trace for a session with waits while disabling bind capture:

```sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => 123,
        serial_num => 456,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
```

Disable trace after collection:

```sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => 123,
        serial_num => 456
    );
END;
/
```

SID and serial number are examples only. DBAs must target the exact session and hold proper privileges.

### 14.1. Tracing rules

- Trace only the specific session/request under investigation.
- Keep collection windows brief.
- Disable tracing immediately once enough data is gathered.
- Avoid bind capture if binds may hold secrets or sensitive data.
- Protect trace files and TKPROF reports.
- Delete/retire files per retention rules.
- Never send raw traces over unprotected channels.

Even with `binds => FALSE`, SQL text can still contain literals if the application concatenates values into SQL. Design SQL to keep secrets out of statement text from the start.

## 15. Protecting logs at the application tier

### 15.1. Java/JDBC

Java applications may log SQL, bind parameters, or datasource configs via framework/driver loggers. Examples:
- ORM SQL loggers.
- Bind parameter loggers.
- Connection pool debug logs.
- HTTP client request/response loggers.
- Exception handlers.

In production:
- Never enable debug bind logging by default.
- Never log datasource passwords.
- Never print `Properties` containing credentials.
- Never log Authorization headers.
- Never serialize full request objects.
- Keep time-bounded debug logs separate from audit logs.
- Add automated tests verifying synthetic secret markers never appear in logs.

### 15.2. PL/SQL

Never put secrets into:
- `DBMS_OUTPUT.PUT_LINE`.
- `RAISE_APPLICATION_ERROR` messages.
- Unprotected custom audit tables.
- Dynamic SQL text.
- Exception wrappers.
- Debug tables.

If a procedure accepts a secret parameter, never log its value. Log only operation name, caller, outcome, and correlation ID.

### 15.3. Shell and CI/CD

Disable command echo when scripts handle secrets. Never put secrets in argument lists or commands printed to build logs. Use CI/CD secret stores, protected variables, or short-lived credential issuance; restrict which jobs and runners can read them.

Never store secrets in build artifacts, caches, crash dumps, or `set -x`/verbose output.

### 15.4. Testing logs with dummy secret markers

In test environments, use a non-real marker such as `TEST_SECRET_467_DO_NOT_LOG`. Run controlled login successes/failures and search for the marker in:
- Application logs.
- SQL traces.
- Audit outputs.
- CI build logs.
- Shell transcripts.
- Error reports.

If the marker appears, fix the logger and retest. Never use real passwords as test data.

## 16. Finding and auditing at-risk accounts

### 16.1. Expired or locked accounts

```sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile,
       authentication_type
FROM dba_users
ORDER BY account_status, username;
```

Requires DBA privileges. Distinguish policy-locked accounts, expired passwords, and external/global authenticated accounts.

### 16.2. Finding accounts using the DEFAULT profile

```sql
SELECT username, profile, account_status
FROM dba_users
WHERE profile = 'DEFAULT'
ORDER BY username;
```

This is a review list, not proof every account on `DEFAULT` is wrong. Evaluate the actual profile settings and organizational policy.

### 16.3. Reviewing password profiles

```sql
SELECT profile,
       resource_name,
       limit
FROM dba_profiles
WHERE resource_type = 'PASSWORD'
ORDER BY profile, resource_name;
```

Do not export secret information. Review reports should focus on policy posture and exceptions needing remediation.

### 16.4. Auditing service user privileges

Review:
- System privileges.
- Object privileges.
- Roles.
- Proxy authentication.
- Grants containing `ANY`.
- Unnecessary administrative privileges.
- Accounts without active owners or workloads.

Views such as `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS`, and `DBA_TAB_PRIVS` support reviews when authorized. Revoking privileges requires checking dependencies and change management processes.

## 17. When a secret is exposed: incident response

Suppose a password appears in a log or Git commit. Deleting the log line is insufficient because copies may exist in archives, SIEMs, backups, tickets, or Git history.

Response procedure:
1. **Determine scope:** secret type, account, privileges, environment, and exposure locations.
2. **Assess severity:** whether the secret is still active, what privileges it holds, and signs of unauthorized use.
3. **Contain:** restrict access to logs/repositories or temporarily lock the account if needed.
4. **Rotate/revoke:** change passwords, revoke tokens, replace certificates/keys per corresponding procedures.
5. **Update consumers:** ensure legitimate workloads use the new secret.
6. **Investigate:** check audits, logon successes/failures, source IPs, module/action, and activity post-exposure.
7. **Clean up copies:** scrub secrets from logs/archives/tickets and Git history per policy; control backups.
8. **Restore service:** verify connectivity and business operations.
9. **Postmortem:** fix log sources, CI rules, secret scanning, and rotation workflows.

If a secret was committed, treat it as compromised even in a private repository. Deleting a commit or rewriting history does not make the old secret safe again; rotate/revoke first, then remediate history and copies.

## 18. Secret lifecycle workflow

A secret has an explicit owner and lifecycle:

```text
Create / provision
        |
        v
Store in wallet or secret manager
        |
        v
Grant access to one workload identity
        |
        v
Use without logging the value
        |
        v
Monitor usage and expiry
        |
        v
Rotate or renew
        |
        v
Verify consumers and revoke old value
        |
        v
Retire secret and protected backups by policy
```

### 18.1. Inventory

Every inventory record should track:
- Secret ID or alias (never the secret value).
- Secret type.
- Technical owner and business owner.
- Workload/consumer.
- Environment.
- Storage location.
- Creation date and expiry/rotation due date.
- Privilege tier.
- Dependencies and recovery procedures.

### 18.2. Access review

Periodically review:
- Who can read the secret?
- Which workloads use it?
- Are stale accounts present?
- Are any secrets ownerless?
- Are wallet read permissions overly broad?
- Are copies sitting in backups or personal machines?
- Have credentials expired or fallen out of use?

### 18.3. Automated rotation

Automated rotation requires:
- API to issue new credentials.
- Mechanism to update passwords in Oracle.
- Secret store update.
- Application/pool reload.
- Health checks.
- Controlled rollback or retry.
- Auditing without logging secret values.

Automation does not remove dependencies. If the database password rotates while the secret manager fails to update or the connection pool does not reload, services can still lose connectivity.

## 19. Checklist for a password rotation cycle

| Phase | Verification item |
|---|---|
| Pre-rotation | Owner, account, privileges, all consumers, and timing are clear |
| Preparation | New secret generated and stored in secret manager |
| Database | Password changed over a secure administrative channel |
| Secret store | New secret version published |
| Application | Pools/processes reloaded and opening new connections |
| Integrations | Jobs, DB links, ETL, backups, and monitoring verified |
| Security | Logs contain no passwords/tokens; audits hold required metadata |
| Completion | Old credential revoked once no consumers remain |
| Monitoring | Authentication failures, locks, timeouts, and service health normal |
| Documentation | Operator, timestamp, outcome recorded; zero secrets logged |

## 20. Scenario example: rotating ORDER_API_USER's password

Suppose the `ORDER_API` application connects to Oracle using account `ORDER_API_USER`.

### Step 1. Inventory

Record all consumers:
- Two API instances.
- One reconciliation batch job.
- Monitoring dashboard.
- Secret alias `orders-prod-db`.

Never write the current password into the inventory.

### Step 2. Inspect the account

```sql
SELECT username,
       account_status,
       profile,
       expiry_date,
       authentication_type
FROM dba_users
WHERE username = 'ORDER_API_USER';
```

Confirm profile and account status.

### Step 3. Prepare the new secret

Generate a random password per policy in the secret manager. Grant secret read access only to the intended service identity. Never copy the value into tickets or chat.

### Step 4. Execute rotation

The DBA changes the password over a secure admin client, using a password prompt or approved automation. Never record real passwords in illustrative scripts.

If the release/profile supports gradual password rollover, evaluate the transition window so both API instances and the batch job switch sequentially.

### Step 5. Update the secret store

Publish the new version for the alias. Verify each instance retrieves the right version without logging secret contents.

### Step 6. Reload pools

Create new pools or refresh datasources per application mechanism. Health-check new connections, shift traffic, and drain old pools.

### Step 7. Verify batch and monitoring

Run connection/health checks for batch jobs, dashboards, and other integrations. Watch for authentication failures and account locks.

### Step 8. Conclude

Once all consumers use the new secret and no old dependencies remain, end rollover or revoke the old credential per feature/policy. Update inventory and record rotation results without secrets.

## 21. Common misconceptions

| Misconception | Reality |
|---|---|
| Encrypting a password inside a config file is enough | Applications must still decrypt it; read permissions and key management determine real security |
| A private Git repo is safe for storing secrets | Anyone with repo access, backups, or forks can still extract secrets |
| Changing the password in the database finishes the job | Consumers, pools, jobs, DB links, and integrations all require updating |
| Old connections drop immediately on password change | Already authenticated sessions may persist; pools/sessions must be refreshed |
| Bind variables guarantee values stay out of logs | Bind capture and SQL traces can capture bind values |
| Disabling bind logging makes logs completely safe | SQL text, exceptions, connection strings, or request bodies can still leak |
| Audits must store passwords to prove rotation | Audits only need principal, action, time, outcome, and proper context |
| TDE replaces a secret manager | TDE protects data at rest; it does not manage application passwords |
| Wallets can be copied freely | Wallets and auto-login files require strict ACLs, backups, and ownership |
| Password expiration auto-updates applications | Expiration can cause outages if consumers have not rotated |
| Removing a secret from Git history is sufficient | Compromised credentials must be rotated/revoked; history rewrites only clean up copies |
| Sharing accounts simplifies operations | Complicates traceability, rotation, and per-workload revocation |
| Raising log levels always helps investigation | Debug logs can expose binds, tokens, and connection properties |
| Data Redaction hides secrets in all logs | Data Redaction controls query results from the database, not log sanitization |

## 22. Final security checklist

### Secret management
- Every credential has an owner and consumer inventory.
- Zero secrets in source code or Git.
- Wallets/secret managers protected by ACLs.
- Accounts hold least privilege.
- Keystore backups and restore tests exist.
- Rotation schedules and revocation procedures exist.

### Password rotation
- All consumers identified.
- Connection pool reload plan ready.
- Gradual rollover evaluated if supported by release.
- DB links, Scheduler jobs, password files, and related integrations checked.
- New connections verified.
- Old credentials revoked on schedule.

### Logging and auditing
- Never log passwords, tokens, private keys, or wallet contents.
- Never log connection strings containing credentials.
- Bind capture/tracing restricted and reviewed.
- Audits record actor, action, object, time, and outcome.
- Logs have ACLs, retention, and access monitoring.
- Tests using dummy markers check for secret leakage.

### Incident response
- Procedure ready to rotate/revoke exposed secrets.
- Ability to identify everywhere a secret appeared.
- Assigned owners and escalation channels.
- Procedures to clean Git history, archives, backups, and tickets.
- Post-rotation monitoring for anomalous activity.

## 23. Self-check questions

**Question 1.** How does a secret differ from configuration?

**Answer:** A secret is a value enabling authentication or decryption, such as a password, token, or private key. Configuration typically covers endpoints, ports, or service names; a config file can still hold secrets needing protection.

**Question 2.** Why avoid sharing one database account across multiple applications?

**Answer:** Separate identities enable traceability, privilege scoping, rotation, and credential revocation per workload.

**Question 3.** How do Oracle Wallet/SEPS help?

**Answer:** They store credentials outside source code/commands so clients connect using an alias without putting username/password directly in connection commands.

**Question 4.** Why avoid passing passwords via command line?

**Answer:** Values can appear in shell history, process lists, build logs, or telemetry.

**Question 5.** What do Oracle profiles manage?

**Answer:** Profiles can enforce failed login limits, account locking, password lifetime, grace periods, reuse rules, and password verification functions.

**Question 6.** Why inventory consumers before rotation?

**Answer:** One account can serve multiple applications, pools, jobs, and integrations; missing a consumer can cause outages after password changes.

**Question 7.** Does changing a password disconnect active sessions?

**Answer:** Do not assume so. Already authenticated sessions can remain active; pools/sessions must be refreshed as planned.

**Question 8.** What is gradual password rollover used for?

**Answer:** Provides a transition window for consumers to roll over to new passwords incrementally on supported releases and accounts.

**Question 9.** Can plaintext passwords be read back from database links?

**Answer:** Operational workflows should not rely on recovering plaintext; rotate/recreate links using Oracle-supported mechanisms.

**Question 10.** How do password files differ from regular database users?

**Answer:** Password files support administrative authentication privileges such as `SYSDBA`/`SYSOPER` and require dedicated RAC/standby management procedures.

**Question 11.** Is TDE master key rotation the same as user password rotation?

**Answer:** No. It is a distinct encryption key management workflow requiring keystore backup/restore and synchronization.

**Question 12.** Why can bind variables still leak data?

**Answer:** Certain bind capture, tracing, or auditing mechanisms can record bind values.

**Question 13.** What should secure logs record?

**Answer:** Timestamps, principals, actions, objects, request IDs, outcomes, and appropriate error codes—never secret values.

**Question 14.** Does Unified Auditing replace application logs?

**Answer:** No. Database audits record database activity; application logs provide request and business context. Both complement each other.

**Question 15.** If a password enters Git, is deleting the commit enough?

**Answer:** No. Treat the credential as compromised and rotate/revoke it; then clean history and copies per policy.

**Question 16.** Does Data Redaction replace log sanitization?

**Answer:** No. Data Redaction governs selected data returned from the database and does not prevent other loggers from writing secrets.

## 24. Conclusion

Secret management in Oracle spans the entire lifecycle of credentials and keys: identifying owners, inventorying consumers, storing in wallets or secret managers, granting least privilege, monitoring, rotating, and revoking. Oracle Wallet/Secure External Password Store separates credentials from commands and source code; profiles enforce password policies; gradual password rollover supports phased transitions when releases and accounts qualify. Database links, Scheduler credentials, password files, TDE keystores, and TLS private keys require separate inventories because each follows distinct operational procedures.

Password rotation is complete only when the password has changed, the secret store is updated, connection pools/jobs/integrations have switched to the new credential, new connections succeed, and the old value is revoked on time. Changing a database password while overlooking a consumer can cause service outages.

Logs must support investigations without containing secrets. Record principal, action, timestamp, object, request ID, and outcome; tightly control SQL text, bind capture, traces, connection strings, exceptions, and debug output. Unified Auditing and application logging complement each other, yet captured fields, access permissions, and retention must be bounded. If a secret is exposed, rotate/revoke immediately per incident response and then remediate copies. A secure system enables full action traceability without letting logs or operational tools become credential leak vectors.
