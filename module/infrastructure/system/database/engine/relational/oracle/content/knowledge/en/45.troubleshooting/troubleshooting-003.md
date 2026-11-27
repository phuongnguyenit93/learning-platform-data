# ORA-01017, ORA-28000, and Authentication or Account Lock Errors

When an application or DBA connects to Oracle Database, two common errors are **ORA-01017: invalid username/password; logon denied** and **ORA-28000: the account is locked**. Both occur during login, but their causes and remedies differ:

- ORA-01017 indicates that Oracle rejected the submitted credentials. It may be due to a wrong username, password, credential passing method, or connecting to a different database/PDB than expected.
- ORA-28000 indicates that the target account is currently locked. You need to determine why the account was locked, unlock it in the right container, and stop the source of bad logins so the account is not locked again immediately.

Do not repeatedly guess passwords or simply unlock the account while leaving an application running with old credentials. A service, connection pool, job, or health check may be sending the wrong password repeatedly and re-lock the account right after the DBA unlocks it.

## 1. Distinguishing Authentication Errors from Connectivity Errors

First, distinguish network/listener-layer errors from database authentication errors.

| Error Code | Common Meaning | Layer to Check |
|---|---|---|
| ORA-01017 | Username/password rejected | Credentials, account, service/PDB |
| ORA-28000 | Account is locked | Account status, profile, failed login source |
| ORA-28001 | Password has expired | Password lifecycle and rotation procedure |
| ORA-28002 | Password will expire soon, currently in grace period | Profile and password change plan |
| ORA-28003 | Password fails the password verification function | Password policy |
| ORA-28007 | Password cannot be reused per policy | Password reuse policy |
| ORA-01045 | User lacks CREATE SESSION privilege | Login privileges |
| ORA-28009 | SYS must connect AS SYSDBA or AS SYSOPER | SYS connection mode |
| ORA-28040 | No matching authentication protocol | JDBC/Oracle client version and server policy |
| ORA-12154 | Could not resolve connect identifier | Oracle Net naming/TNS |
| ORA-12514 | Listener does not know requested service | Service registration and connect string |
| ORA-12541 | No listener at endpoint | Host, port, listener, and network |

ORA-12154, ORA-12514, and ORA-12541 are not password errors. When encountering them, do not reset passwords or unlock accounts yet; resolve connectivity and service issues first.

## 2. What Is ORA-01017?

ORA-01017 occurs when Oracle rejects the credentials submitted during logon. Common message:

~~~text
ORA-01017: invalid username/password; logon denied
~~~

Possible causes include:

- Misspelled username or password.
- The application is still using an old secret after a password change.
- A password with special characters is misinterpreted by a shell, YAML, URL, or script.
- The username was created with a quoted identifier and is therefore case-sensitive.
- Connecting to the wrong service, database, or PDB.
- The account does not exist in the target container.
- The password was changed in a different PDB or on a different database.
- The Oracle client/JDBC driver is incompatible with the server's authentication protocol.
- An external authentication mechanism is misconfigured.

ORA-01017 does not prove that the password the operator just entered is wrong everywhere. It only proves that the credentials sent to that specific endpoint were rejected there.

## 3. Verifying the Right Database, Service, and PDB

An easily overlooked cause is an application connecting to the wrong database or PDB. The same username can exist across multiple PDBs with different passwords, statuses, and privileges.

Before investigating the account, verify the endpoint:

- Hostname or SCAN name.
- Listener port.
- Service name.
- PDB that the service routes to.
- Environment: development, test, staging, production, or DR.

Service-name JDBC URL format:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
~~~

Do not confuse SID with service name. In multitenant architectures, applications should connect via the service configured for the target PDB rather than connecting to CDB root and assuming a PDB local user can log in.

Once connected with an appropriate administrative account, check the container:

~~~sql
SHOW CON_NAME;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name
  FROM dual;
~~~

If the client does not support the `SHOW` command, the `SYS_CONTEXT` query still works in any SQL worksheet.

From CDB root, view users across containers:

~~~sql
SELECT con_id,
       username,
       common,
       account_status,
       profile,
       lock_date,
       expiry_date
  FROM cdb_users
 WHERE username = UPPER('APP_RUNTIME')
 ORDER BY con_id;
~~~

Querying `CDB_USERS` requires appropriate dictionary read privileges. If connected directly to a PDB, `DBA_USERS` is typically the right view:

~~~sql
SELECT username,
       account_status,
       profile,
       lock_date,
       expiry_date
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

If the account exists only in PDB SALES while the application connects to the service for PDB REPORTING, login will fail even though the username/password works in SALES. Verify the service before rotating credentials.

## 4. Case Sensitivity of Usernames and Passwords

Oracle normalizes unquoted usernames to uppercase. For example:

~~~sql
CREATE USER app_runtime IDENTIFIED BY "Example-Secret";
~~~

The normal username is stored as `APP_RUNTIME`. However, if a quoted username is created:

~~~sql
CREATE USER "appRuntime" IDENTIFIED BY "Example-Secret";
~~~

then the username is case-sensitive and must be referenced with exact casing.

Oracle passwords are case-sensitive under modern password case-sensitivity settings. The following strings are distinct passwords:

~~~text
Example-Secret
example-secret
EXAMPLE-SECRET
~~~

Do not disable password case sensitivity to work around ORA-01017. Fix the credentials sent by the client.

If you suspect a username was created with double quotes, the DBA can inspect the exact name in `DBA_USERS`/`CDB_USERS`. Do not guess from how the name appears in application configuration.

## 5. Passwords with Special Characters

Passwords containing quotes, `$`, `&`, `!`, `#`, `;`, `@`, `:`, or spaces can be interpreted differently by:

- Shell or PowerShell.
- YAML/properties files.
- Docker Compose or Kubernetes manifests.
- JDBC URLs.
- SQL*Plus scripts.
- CI/CD variable substitution.
- Secret injection tools.

Example Spring Boot configuration:

~~~yaml
spring:
  datasource:
    username: APP_RUNTIME
    password: DB_PASSWORD_FROM_SECRET
~~~

`DB_PASSWORD_FROM_SECRET` is a placeholder illustrating a value injected from an environment/property source or secret manager; never replace it with a real password in a repository.

Avoid embedding passwords in JDBC URLs when they can be passed separately via username/password properties. Use a secret manager or the platform's credential management mechanism. When troubleshooting, verify that the secret is injected accurately without printing its value to logs.

With SQL*Plus, a safer way to enter a password is to let the client prompt for it instead of placing the real password directly on the command line:

~~~text
sqlplus /nolog
SQL> CONNECT APP_RUNTIME@//dbhost.example.com:1521/APP_SERVICE
Enter password:
~~~

Never screenshot or share logs containing passwords. When illustrating passwords with special characters in SQL statements, use dummy values and check the quoting rules of your SQL client/version.

## 6. Verifying Account Existence and Status

After confirming the target database/PDB, the DBA inspects the account:

~~~sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile,
       authentication_type,
       common
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

Useful columns:

- USERNAME: account name.
- ACCOUNT_STATUS: account state.
- LOCK_DATE: timestamp when locked, if applicable.
- EXPIRY_DATE: password expiration date per metadata.
- PROFILE: profile assigned to the user.
- AUTHENTICATION_TYPE: authentication method, if exposed by the view/version.
- COMMON: whether this is a common or local user in multitenant, if applicable.

Common statuses:

| ACCOUNT_STATUS | Interpretation |
|---|---|
| OPEN | Account is open |
| LOCKED | Account is locked |
| LOCKED(TIMED) | Account is time-locked |
| EXPIRED | Password has expired |
| EXPIRED(GRACE) | Password is in the grace period |
| EXPIRED & LOCKED | Password expired and account is locked |
| EXPIRED(GRACE) & LOCKED | Combined status depending on version/policy |

Exact statuses and display strings may vary across versions. Do not judge from a single column alone; check the profile, lock time, and authentication history.

## 7. What Is ORA-28000?

ORA-28000 indicates the account is locked:

~~~text
ORA-28000: The account is locked
~~~

An account may be locked because:

1. Failed login attempts exceeded the `FAILED_LOGIN_ATTEMPTS` limit in the profile.
2. A DBA or administrative process executed `ALTER USER ... ACCOUNT LOCK`.
3. A security policy or automated process locked the account.
4. The account was locked alongside an expired password state.

Do not assume every ORA-28000 is caused by a bad password. Check audit records, change tickets, and profile settings to distinguish manual locks from failed-login locks.

## 8. FAILED_LOGIN_ATTEMPTS and PASSWORD_LOCK_TIME

An Oracle profile can limit failed login attempts before locking the account.

- FAILED_LOGIN_ATTEMPTS: number of consecutive failed logins allowed before locking the account per profile.
- PASSWORD_LOCK_TIME: duration the account remains locked after reaching the threshold; expressed in days in the profile.

Check the user's profile:

~~~sql
SELECT username,
       profile
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

Then inspect the profile limits:

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE profile = 'APP_PROFILE'
   AND resource_name IN (
     'FAILED_LOGIN_ATTEMPTS',
     'PASSWORD_LOCK_TIME',
     'PASSWORD_LIFE_TIME',
     'PASSWORD_GRACE_TIME',
     'PASSWORD_REUSE_TIME',
     'PASSWORD_REUSE_MAX'
   )
 ORDER BY resource_name;
~~~

Replace `APP_PROFILE` with the actual profile from `DBA_USERS`. Never assume a user always uses the `DEFAULT` profile.

### Meaning of the Limits

For example, if a profile specifies:

~~~text
FAILED_LOGIN_ATTEMPTS = 5
PASSWORD_LOCK_TIME    = 1/24
~~~

then after five consecutive failed login attempts, the account is locked for the configured duration; 1/24 of a day equals approximately one hour. This example only explains the calculation and is not a recommendation for a specific value.

If `PASSWORD_LOCK_TIME` is set to `UNLIMITED`, the account requires manual DBA unlock. If set to a finite duration, the account can unlock automatically once the lock period expires per policy. Inspect actual values and behavior for your version rather than relying on defaults.

Do not relax `FAILED_LOGIN_ATTEMPTS` to `UNLIMITED` just to avoid ORA-28000. Doing so weakens protection against password guessing. Any policy change requires security review and system-level approval.

## 9. Unlocking an Account Properly

Unlock only after confirming the right database/PDB, the right user, and identifying or resolving the source of bad logins.

In the PDB containing a local user, the DBA can run:

~~~sql
ALTER USER app_runtime ACCOUNT UNLOCK;
~~~

Verify again:

~~~sql
SELECT username,
       account_status,
       lock_date
  FROM dba_users
 WHERE username = 'APP_RUNTIME';
~~~

If an account is time-locked, the DBA can still manually unlock it when authorized. If the application continues sending the wrong password, the account will immediately lock again.

### Common Users in a CDB

Common users are managed in CDB root and span multiple containers depending on configuration. When modifying a common user, execute in the appropriate container and use `CONTAINER=ALL` only when you truly intend to apply the change across all applicable containers.

Illustrative example:

~~~sql
ALTER USER c##integration ACCOUNT UNLOCK CONTAINER=ALL;
~~~

Do not use this command for local users. Local users must be managed in their respective PDB. Verify syntax and container scope against your Oracle release and account type.

### Unlocking Is Not Resetting the Password

If the current password is still valid and the account was only locked, unlocking may suffice. If the application's secret is stale, update the password/secret per procedure and roll out the new credentials.

When changing passwords, follow secure procedures so secrets are never written into scripts, shell history, tickets, or logs. Afterward, confirm that applications, jobs, and integration clients all use the new credentials.

## 10. Changing Password and Unlocking in One Operation

When setting a new password and unlocking at the same time, the DBA can use:

~~~sql
ALTER USER app_runtime
  IDENTIFIED BY "New-Secret-Value"
  ACCOUNT UNLOCK;
~~~

The string in the example is a placeholder only. Never use sample passwords in production and never commit statements containing real secrets.

If a password verification function is attached to the profile, the new password must satisfy the policy. Otherwise, Oracle returns ORA-28003 or a related error. Check the policy rather than bypassing the verification function just to make the statement succeed.

For application accounts, coordinate the sequence:

1. Identify the service/PDB and account.
2. Identify all sources using old credentials.
3. Generate/set the new secret per security procedures.
4. Update the secret store and deployment configuration.
5. Unlock the account in the right container.
6. Roll out the application so pools create connections using the new secret.
7. Verify login and monitor to ensure the account does not re-lock.

The exact order may vary with your secret management system and deployment model, but you must avoid a window where multiple clients continue sending the old password.

## 11. How ORA-01017 Leads to ORA-28000

A common scenario:

1. The DBA changes the password of `APP_RUNTIME`.
2. The secret store is updated, but some pods are still running with the old configuration.
3. HikariCP/UCP or the application opens new connections using the old password.
4. Failed login attempts accumulate.
5. `FAILED_LOGIN_ATTEMPTS` reaches the limit.
6. Oracle locks the account.
7. Other pods begin receiving ORA-28000.
8. The DBA unlocks the account, but the old pods continue retrying with the wrong password.
9. The account locks again.

Therefore, resolving ORA-28000 requires investigating both client sources and credential rollout. Running `ALTER USER ACCOUNT UNLOCK` without stopping the misconfigured client creates an incident loop.

## 12. Finding the Source of Failed Logins

The goal is to identify the host, program, timestamp, and account generating failed logins. Not all audit sources are enabled by default; query availability depends on Unified Auditing, traditional auditing, listener setup, and DBA privileges.

### Check Unified Audit Trail

If the system uses Unified Auditing and a policy captures logon failures, query:

~~~sql
SELECT event_timestamp,
       dbusername,
       userhost,
       client_program_name,
       action_name,
       return_code
  FROM unified_audit_trail
 WHERE dbusername = 'APP_RUNTIME'
   AND action_name = 'LOGON'
   AND return_code <> 0
 ORDER BY event_timestamp DESC;
~~~

Column names and contents can vary by release/audit configuration. Some fields may be null if the client did not send the corresponding metadata. Check your version's data dictionary and active policies.

### Traditional Audit

In environments using traditional auditing, DBAs can inspect `DBA_AUDIT_SESSION`:

~~~sql
SELECT username,
       userhost,
       terminal,
       timestamp,
       returncode,
       action_name
  FROM dba_audit_session
 WHERE username = 'APP_RUNTIME'
 ORDER BY timestamp DESC;
~~~

This view contains data only if the corresponding audit option is configured and retained per policy. Do not enable broad auditing in production arbitrarily, as it can increase storage usage and capture sensitive metadata.

### Listener Log and Application Logs

When database auditing lacks enough detail, correlate:

- The listener log on the Oracle host to inspect timestamps and client endpoints.
- Application logs to identify the pod, hostname, module, and retry timestamps.
- Kubernetes/VM/service manager logs to spot rollouts or secret rotations.
- Scheduler/job logs to locate batch jobs or scripts using old credentials.
- Secret manager audit logs to identify secret change timestamps and versions.

Do not log passwords to identify clients. Use username, source host, client program, connection ID, and timestamp.

## 13. Checking Whether an Account Was Locked Manually or by Failed Logins

`DBA_USERS` shows the current status and `LOCK_DATE`, but does not always fully explain why it happened. Combine:

1. Logon failure audit records if available.
2. Audit/DDL history for `ALTER USER ACCOUNT LOCK`.
3. Change tickets and automation logs.
4. Scheduler, batch, and application deployments.
5. The user's profile.

If an account was intentionally locked per policy, do not unlock it simply because an application reports an error. Confirm the owner, reason for locking, and approval before reopening.

## 14. Expired Passwords vs. Locked Accounts

ORA-28001 indicates the password has expired. ORA-28002 warns that the password will expire soon and the user is in the grace period. This is distinct from ORA-28000.

Check:

~~~sql
SELECT username,
       account_status,
       expiry_date,
       profile
  FROM dba_users
 WHERE username = 'APP_RUNTIME';
~~~

Check the profile:

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE profile = 'APP_PROFILE'
   AND resource_name IN (
     'PASSWORD_LIFE_TIME',
     'PASSWORD_GRACE_TIME',
     'PASSWORD_REUSE_TIME',
     'PASSWORD_REUSE_MAX',
     'PASSWORD_VERIFY_FUNCTION'
   )
 ORDER BY resource_name;
~~~

If the password is expired, rotate the password through an approved procedure. Unlocking the account does not automatically make an expired password valid. If the account is both expired and locked, address both conditions in the proper sequence.

For service accounts, plan rotation before expiration. Do not set `PASSWORD_LIFE_TIME` to `UNLIMITED` solely to avoid outages if security policy prohibits it.

## 15. Password Verification Function

A profile may attach a `PASSWORD_VERIFY_FUNCTION` to validate new passwords. The function can enforce:

- Minimum length.
- Uppercase/lowercase characters.
- Digits and special characters.
- Excluding the username.
- Not reusing previous passwords per policy.
- Not being overly similar to the previous password.

Check:

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE resource_name = 'PASSWORD_VERIFY_FUNCTION'
 ORDER BY profile;
~~~

If `ALTER USER` returns ORA-28003, inspect the function attached to that profile and the specific policy. Do not remove the verification function just to set a weak password or reuse an old one.

## 16. ORA-28040 and Authentication Protocols

ORA-28040 typically occurs when the Oracle client and server share no mutually acceptable authentication protocol. It can appear after a database upgrade, changes to `sqlnet.ora`, or when using an outdated JDBC driver/client.

Investigation steps:

- Determine the Oracle Database release and patch level.
- Determine the actual JDBC driver version used by the application.
- Determine the Oracle Client/SQL*Plus version if using a thick client.
- Check `SQLNET.ALLOWED_LOGON_VERSION_SERVER` and related settings for your release.
- Consult Oracle's upgrade and authentication compatibility documentation.
- Upgrade the driver/client to a supported version before relaxing server security policy.

Do not downgrade the authentication protocol to a weak level just to let an old client connect. The proper fix is usually upgrading the client/driver and testing dependent applications.

## 17. ORA-01045 and the CREATE SESSION Privilege

If the username/password are valid but the user lacks login privilege, Oracle returns:

~~~text
ORA-01045: user APP_RUNTIME lacks CREATE SESSION privilege; logon denied
~~~

Check privileges:

~~~sql
SELECT grantee,
       privilege
  FROM dba_sys_privs
 WHERE grantee = 'APP_RUNTIME'
   AND privilege = 'CREATE SESSION';
~~~

If policy allows, the DBA can grant:

~~~sql
GRANT CREATE SESSION TO app_runtime;
~~~

Do not grant `DBA` just to fix ORA-01045. A runtime user typically only needs `CREATE SESSION` and required business object privileges.

## 18. ORA-28009 When Connecting as SYS

`SYS` is a special administrative account. When connecting as `SYS`, the client must specify an appropriate privilege such as `AS SYSDBA` or `AS SYSOPER`:

~~~text
sqlplus sys@//dbhost.example.com:1521/APP_SERVICE AS SYSDBA
~~~

Then let the client prompt for the password. Never use `SYS` in an application datasource. Create dedicated application users with least privilege.

## 19. Checking Credentials from JDBC and Spring Boot

When SQL*Plus logs in successfully but Spring Boot receives ORA-01017, focus on checking:

- Is the application using the expected Spring profile?
- Are environment variables/secrets injected into the process?
- Are any pods still using an older secret version?
- Does the JDBC URL specify the exact host, port, and service?
- Did extra whitespace or newlines slip into the username?
- Was the password altered by YAML, shell, or CI variable substitution?
- Are there multiple DataSources where one still holds old credentials?
- Is a pool creating new connections from stale configuration?

Do not print passwords to compare them. Compare secret versions, secret references, update timestamps, and one-way checksums generated via an approved internal process if policy permits.

### Verify Database Product/Service on Successful Connection

A health check endpoint can confirm the database/service:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       USER AS connected_user
  FROM dual;
~~~

Do not allow a health check to repeatedly attempt logins with a bad password. Health checks must share the same secret lifecycle as the primary datasource or check only process/network health without database authentication.

## 20. Connection Pools After a Password Change

HikariCP and UCP retain established physical JDBC connections. After a database user's password changes:

- Already-authenticated physical connections may continue working until closed or invalidated.
- When the pool needs to open a new connection, it uses the credentials currently configured in the pool.
- If the pool has not picked up the new secret, new connections fail with ORA-01017.
- If multiple instances still hold old credentials, the account can lock again.

Therefore, after password rotation:

1. Update the secret store.
2. Update deployment/configuration references.
3. Roll out or refresh the DataSource/pool in a supported manner.
4. Confirm all replicas are using the new secret.
5. Monitor failed logins and account status.

Do not blindly restart the entire system before identifying which client is causing failures. Controlled rollouts and log monitoring prevent creating a login storm.

## 21. Procedure for Handling ORA-01017

### Step 1: Record Context

Collect:

- Timestamp and timezone.
- Username (do not collect the password).
- Host/port/service.
- Target PDB/database.
- Client: SQL*Plus, SQLcl, JDBC, Spring Boot, job, or tool.
- Hostname/pod/program name.
- First failure and retry count.

### Step 2: Verify Endpoint

Check DNS, listener, service name, and PDB. If the error is ORA-12154/12514/12541, resolve connectivity first.

### Step 3: Check User in the Right Container

Use `DBA_USERS` or `CDB_USERS` to verify the account exists, check common vs. local user type, and check status.

### Step 4: Verify Credentials Safely

Use SQL*Plus/SQLcl or an approved tool and let the client prompt for the password. Never paste passwords into tickets/chat or pass them on the command line.

### Step 5: Check Casing, Special Characters, and Secret Version

Compare username, secret reference, secret version, and client configuration. Do not print passwords.

### Step 6: Check Driver/Authentication Protocol

If credentials and endpoint are correct, inspect JDBC/client versions and ORA-28040 or related authentication errors.

### Step 7: Check Audits and Login Sources

If the error repeats, identify the pod, job, or host generating failed logins before changing passwords or unlocking.

## 22. Procedure for Handling ORA-28000

### Step 1: Stop Further Login Attempts

Pause retries or jobs suspected of using bad credentials per runbook. Continuing retries makes the situation harder to control.

### Step 2: Confirm the Right Account/Container

Check `DB_NAME`, `CON_NAME`, `SERVICE_NAME`, and `DBA_USERS`/`CDB_USERS`. Avoid unlocking a same-named user in the wrong PDB.

### Step 3: Inspect Status and Profile

Inspect `ACCOUNT_STATUS`, `LOCK_DATE`, `EXPIRY_DATE`, `PROFILE`, `FAILED_LOGIN_ATTEMPTS`, and `PASSWORD_LOCK_TIME`.

### Step 4: Find the Source of Failed Logins

Correlate Unified Audit Trail/traditional audit, listener logs, application logs, schedulers, and secret rotation history.

### Step 5: Fix the Cause

Examples:

- Update stale secrets on pods.
- Fix a service name pointing to the wrong PDB.
- Fix username casing.
- Fix quoting for passwords containing special characters.
- Upgrade the JDBC driver if the authentication protocol is incompatible.
- Stop old jobs still using revoked credentials.

### Step 6: Unlock or Change Password

Execute only after the source of bad logins is resolved and approved. Run `ALTER USER` in the right PDB or CDB scope.

### Step 7: Verify and Monitor

Confirm the account is `OPEN`, login succeeds, application pools create new connections, and no further failed logins occur.

## 23. Useful DBA Queries

### Account and Status

~~~sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

### Profile Limits

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE profile = 'APP_PROFILE'
   AND resource_name IN (
     'FAILED_LOGIN_ATTEMPTS',
     'PASSWORD_LOCK_TIME',
     'PASSWORD_LIFE_TIME',
     'PASSWORD_GRACE_TIME',
     'PASSWORD_REUSE_TIME',
     'PASSWORD_REUSE_MAX',
     'PASSWORD_VERIFY_FUNCTION'
   )
 ORDER BY resource_name;
~~~

### Users Across PDBs

~~~sql
SELECT con_id,
       username,
       common,
       account_status,
       profile,
       lock_date,
       expiry_date
  FROM cdb_users
 WHERE username = UPPER('APP_RUNTIME')
 ORDER BY con_id;
~~~

### Login Privileges

~~~sql
SELECT grantee,
       privilege
  FROM dba_sys_privs
 WHERE grantee = 'APP_RUNTIME'
 ORDER BY privilege;
~~~

### Audit Logon Failures

~~~sql
SELECT event_timestamp,
       dbusername,
       userhost,
       client_program_name,
       action_name,
       return_code
  FROM unified_audit_trail
 WHERE dbusername = 'APP_RUNTIME'
   AND action_name = 'LOGON'
   AND return_code <> 0
 ORDER BY event_timestamp DESC;
~~~

`DBA_`/`CDB_` views and Unified Audit Trail require appropriate read privileges. Grant audit/diagnostic access only to DBAs or approved monitoring roles; do not grant `SELECT ANY DICTIONARY` to runtime applications for troubleshooting convenience.

## 24. Protecting Application Accounts

An application account should have:

- A business owner and a technical owner.
- `CREATE SESSION` and least-privilege object grants.
- A profile aligned with password policy.
- Centrally managed credentials.
- A rotation and rollout process.
- Monitoring for failed logins and account locks.
- An incident response plan if secrets are exposed.
- Dedicated accounts per environment or service when needed.

Do not share one DBA account across multiple applications. If a shared credential locks or rotates, it impacts multiple systems and makes source attribution difficult.

### Runtime Accounts vs. Migration Accounts

Consider separating:

- Schema owner owning the objects.
- Migration user running DDL during deployments.
- Runtime user running DML/EXECUTE.
- Read-only user for reporting/integrations.

The runtime user should not have `CREATE USER`, `ALTER USER`, `DROP ANY TABLE`, or the `DBA` role. This separation limits blast radius if runtime credentials are compromised.

## 25. Reducing Risk of Repeated Account Locks

Practical measures:

1. Use a secret manager and a single authoritative credential source.
2. Perform synchronized rollouts when passwords change.
3. Check all replicas, batch jobs, and scheduled tasks.
4. Avoid health checks that continuously retry logins.
5. Use exponential backoff and circuit breakers for authentication errors.
6. Alert on abnormal spikes in failed logins.
7. Distinguish password errors from network/service errors.
8. Do not share one account across too many unrelated clients.
9. Maintain clear unlock and rotation runbooks.
10. Record timestamp, owner, and scope for every account change.

Do not raise `FAILED_LOGIN_ATTEMPTS` excessively high to mask a stale secret. Fix credential lifecycle and retry behavior instead.

## 26. Auditing, Monitoring, and Alerting

Monitoring should detect early:

- Rising logon failures by user or host.
- Accounts transitioning to `LOCKED` or `LOCKED(TIMED)`.
- Passwords approaching expiration.
- Multiple pods simultaneously receiving ORA-01017.
- An old client still attempting connections after rotation.
- Failed logins originating from unexpected hosts.

Alerts should map to owners:

| Signal | Action |
|---|---|
| A few ORA-01017 errors from DBA workstation | Verify input and endpoint |
| Repeated ORA-01017 from a pod | Check pod's secret/config/pool |
| Multiple hosts failing together | Check rotation, service, or auth protocol |
| ORA-28000 | Stop failing retry source, inspect profile/audit, and unlock with approval |
| ORA-28001/28002 | Schedule password change and secret update |
| ORA-28040 after upgrade | Check client/JDBC compatibility |

Audit logs may contain hostnames, usernames, program names, and operational metadata. Apply retention, access control, and data handling policies accordingly.

## 27. Pitfalls to Avoid

**Retrying passwords repeatedly:** increases failed logins and locks the account. Stop retrying and verify the credential source.

**Unlocking immediately without finding the failing client:** the application may re-lock the account within seconds.

**Resetting password in the wrong PDB:** a same-named account in another PDB is not the account the application uses.

**Disabling password case sensitivity:** weakens authentication policy without fixing bad secrets.

**Setting FAILED_LOGIN_ATTEMPTS to UNLIMITED:** reduces protection against password guessing.

**Setting PASSWORD_LIFE_TIME to UNLIMITED to avoid expiration:** must follow organizational security and compliance policy, not an ad-hoc workaround.

**Granting DBA to runtime users:** unnecessary for logging in or running normal business logic.

**Writing passwords into logs/tickets/chat:** creates additional exposure points for sensitive credentials.

**Using SYS in application datasources:** increases risk and violates privilege boundaries.

**Restarting all applications before fixing secrets:** can trigger a login storm with bad credentials.

**Assuming ORA-01017 is always a wrong password:** it may be username, quoted identifier, service/PDB, or protocol mismatch.

**Using tnsping to verify passwords:** tnsping checks Oracle Net naming/listener reachability, not database user authentication.

## 28. Incident Handling Checklist

- [ ] Record exact error code and timestamp.
- [ ] Identify host, port, service name, and PDB.
- [ ] Identify the client, pod, job, or program logging in.
- [ ] Confirm username and account existence in the right container.
- [ ] Check `ACCOUNT_STATUS`, `LOCK_DATE`, `EXPIRY_DATE`, and `PROFILE`.
- [ ] Check `FAILED_LOGIN_ATTEMPTS` and `PASSWORD_LOCK_TIME`.
- [ ] Verify the secret version used by the client without printing the password.
- [ ] Check username casing and special-character password handling.
- [ ] Check JDBC/Oracle client version if ORA-28040 occurs.
- [ ] Inspect audit/listener/application logs to locate the failed login source.
- [ ] Stop failing retries before unlocking.
- [ ] Change password if needed and update all clients.
- [ ] Unlock the right local/common user in the right container.
- [ ] Roll out connection pools to establish connections with new credentials.
- [ ] Confirm the account does not re-lock.
- [ ] Document root cause and preventive actions.

## 29. Real-World Incident Example: Account Locked After Password Rotation

Suppose a DBA changes the `APP_RUNTIME` password at 10:00. A new deployment picks up the new secret version, but an old batch worker is still running with the old secret.

Symptoms:

- The new API connects successfully.
- The batch worker receives ORA-01017.
- After multiple retries, the account receives ORA-28000.
- The new API also begins failing because the account is now locked.

Handling procedure:

1. Pause the old batch worker or stop login retries.
2. Check audit/listener logs to confirm the host and program causing failed logins.
3. Verify the `APP_RUNTIME` account in the right PDB.
4. Verify secret versions in both the API and the batch worker.
5. Update the batch worker to use the new secret.
6. Unlock the account with approval.
7. Restart/refresh the batch worker's pool in a controlled rollout.
8. Confirm both the API and batch worker establish new connections successfully.
9. Monitor audit logs to ensure no further failed logins occur.
10. Document the root cause and add secret-version verification to the deployment process.

If you only unlock at step 6 while ignoring the old worker, the account will lock again immediately.

## 30. Conclusion

ORA-01017 indicates Oracle rejected the submitted credentials; ORA-28000 indicates the account is locked. When troubleshooting, first confirm the right database, service, and PDB, then inspect username, password case sensitivity, secret handling, account status, and profile limits. Expired passwords or incompatible authentication protocols are distinct conditions from account locks.

For ORA-28000, locate the failed login source using audit, listener, and application logs before unlocking. If a pod, batch job, or connection pool still holds an old secret, the account will re-lock after being opened. After password rotation, update all clients, roll out pools in a controlled manner, and monitor account status.

Keep runtime privileges minimal, protect credentials, monitor failed logins, and maintain clear rotation/unlock procedures. Never disable password policies, allow unlimited failed login attempts, or grant DBA to mask a root cause.
