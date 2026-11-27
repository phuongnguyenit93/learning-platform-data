# CREATE USER, Authentication, Account Locking, and Password Lifecycle Management

In Oracle Database, user management is a core part of security. DBAs need to define who can connect, how Oracle authenticates that identity, what an account is allowed to do, when an account is locked, and how credentials are changed throughout its lifecycle.

These concepts are closely related but distinct:

- **User:** an identity managed by Oracle for authentication and privilege assignment.
- **Schema:** a namespace containing objects owned by a user, such as tables, views, sequences, procedures, and packages. When a regular user is created, Oracle simultaneously creates a schema with the same name; a schema is not a separate login account.
- **Authentication:** verifying the identity of the person or application connecting.
- **Authorization:** determining what actions an authenticated identity is allowed to perform.
- **Account status:** indicating whether an account is open, locked, or requires a password change.

A user can exist without being allowed to create a session. An account can authenticate successfully yet still lack permission to read a specific table. Therefore, creating a user, granting login privileges, and granting data privileges are separate steps that must be managed deliberately.

## 1. Preparation Before Creating a User

Before running `CREATE USER`, determine the account's purpose:

| Account type | Purpose | Typical privileges needed |
|---|---|---|
| Schema owner | Owns and deploys application objects. | `CREATE SESSION` and a limited set of object creation privileges; quota on required tablespaces. |
| Application runtime | Used by the application to access data at runtime. | `CREATE SESSION` and specific object privileges such as `SELECT`, `INSERT`, `UPDATE`, `EXECUTE`. |
| Reporting user | Runs reports or read queries. | `CREATE SESSION` and read privileges on approved views or tables only. |
| DBA or operations account | Performs database administration by role. | Required administrative privileges, granted individually and strictly controlled. |

Do not share a single account across developers, runtime applications, and administrative tasks. When multiple components share an identity, auditing cannot easily determine who performed an action, and revoking privileges can impact multiple systems.

Before creating a user, verify:

1. You are connected to the right database and right pluggable database (PDB).
2. The username is not already in use and follows naming conventions.
3. Default tablespace, temporary tablespace, and quota have been prepared by the DBA.
4. The profile containing password policies already exists if the user needs a dedicated profile.
5. The executor has `CREATE USER` privilege in the appropriate container scope.

In Oracle multitenant environments, a user created in a PDB is normally a **local user**, existing only in that PDB. A common user is created in the CDB root and has a broader container scope; by default configuration, common user names usually require the `C##` prefix. Before creating an account, you can check the current container:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
```

In SQL*Plus, `SHOW CON_NAME` also displays the current container. Accidentally creating a user in the root instead of the application PDB alters account scope and administration, so confirm the container before executing DDL.

## 2. Creating a User with `CREATE USER`

### 2.1. Syntax and Key Attributes

A common syntax form when creating a password-authenticated user is:

```sql
CREATE USER username
    IDENTIFIED BY password
    DEFAULT TABLESPACE tablespace_name
    TEMPORARY TABLESPACE temp_tablespace_name
    QUOTA quota_size ON tablespace_name
    PROFILE profile_name
    PASSWORD EXPIRE;
```

These clauses are optional depending on needs; not every user requires specifying all of them.

| Clause | Meaning |
|---|---|
| `username` | Oracle identity name. Unquoted names are normally normalized to uppercase. |
| `IDENTIFIED BY` | Specifies the password used for database authentication. Passwords are case-sensitive in modern Oracle configurations. |
| `DEFAULT TABLESPACE` | Default tablespace for segments created by the user when no other tablespace is specified. |
| `TEMPORARY TABLESPACE` | Tablespace used for operations needing temporary space such as sorts or hashes when spilling to TEMP. |
| `QUOTA` | Storage limit the user is allowed to allocate in a tablespace. |
| `PROFILE` | Assigns a profile defining password policies and, if enabled, resource limits. |
| `PASSWORD EXPIRE` | Marks the password as expired so the user must change it upon login via supported client mechanisms. |

`DEFAULT TABLESPACE` does not automatically grant permission to create any object type, nor does it replace a quota. If a user needs to create tables, the user must have the appropriate system privilege and tablespace quota, or be granted `UNLIMITED TABLESPACE` when genuinely justified. Avoid granting unlimited quota just to bypass quota errors.

### 2.2. Example: Creating a Schema Owner

Suppose the database already has tablespace `APP_DATA`, temporary tablespace `TEMP`, and profile `APP_PASSWORD_POLICY`. An application schema owner account can be created as follows:

```sql
CREATE USER app_owner
    IDENTIFIED BY "ReplaceWithSecretFromVault"
    DEFAULT TABLESPACE app_data
    TEMPORARY TABLESPACE temp
    QUOTA 500M ON app_data
    PROFILE app_password_policy
    PASSWORD EXPIRE;

GRANT CREATE SESSION TO app_owner;
GRANT CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE TO app_owner;
```

The password string in the example is a placeholder for syntax illustration only, not a password to actually use. In real deployments, generate a unique random password and inject it through a secure secret provisioning workflow. Avoid storing real passwords in SQL files, Git, deployment logs, or commands that might appear in shell history.

`CREATE USER` creates the identity and schema, but **does not automatically grant `CREATE SESSION`**. Without this privilege, the user cannot open a standard database session. System privileges such as `CREATE TABLE` only permit creating the corresponding object types within the user's schema; quotas still limit allocated segment space.

### 2.3. Separating the Schema Owner from the Runtime Account

A running application normally does not need privileges to create or alter database structures. You can create a dedicated runtime user:

```sql
CREATE USER app_runtime
    IDENTIFIED BY "ReplaceWithAnotherSecretFromVault"
    DEFAULT TABLESPACE app_data
    TEMPORARY TABLESPACE temp
    PROFILE app_password_policy;

GRANT CREATE SESSION TO app_runtime;
GRANT SELECT, INSERT, UPDATE
    ON app_owner.orders TO app_runtime;
GRANT SELECT
    ON app_owner.customers TO app_runtime;
```

The user `APP_RUNTIME` does not need `CREATE TABLE`, `CREATE USER`, `ALTER SYSTEM`, or DBA privileges to perform the application operations shown above. Table privileges are granted directly in the example for clarity; in systems with multiple accounts, object privileges can be grouped into functional roles and those roles granted to runtime users.

Example:

```sql
CREATE ROLE app_order_reader;
GRANT SELECT ON app_owner.orders TO app_order_reader;
GRANT SELECT ON app_owner.customers TO app_order_reader;
GRANT app_order_reader TO app_reporting;
```

Roles help manage privilege sets by duty. Always inspect effective privileges received from roles, direct grants, and nested roles; do not grant `DBA`, `RESOURCE`, or broad roles just because an application hits a missing privilege error.

## 3. Authentication Methods

Oracle can authenticate users with a database password or rely on an external identity system. The chosen method affects where secrets are managed, password policies, and how access is revoked.

### 3.1. Database Password Authentication

This is the common approach for application users or direct login users:

```sql
CREATE USER app_user
    IDENTIFIED BY "ReplaceWithSecretFromVault";
```

Oracle verifies the password using database authentication. Oracle passwords are case-sensitive in modern configurations. Do not disable case sensitivity for legacy application compatibility; update the application to handle passwords properly.

Connections typically take the form:

```text
username/password@service_name
```

Do not put real passwords on the command line, in logged connection strings, or in unprotected configuration files. For applications, retrieve secrets from a secret manager or the deployment platform's credential management mechanism.

### 3.2. External Authentication

With external authentication, Oracle relies on a configured external authentication system instead of checking a database password for the user. An example user declaration is:

```sql
CREATE USER ops_user IDENTIFIED EXTERNALLY;
```

In some configurations, the external identity can be OS-based; Oracle Net configuration and related parameters determine how identities are mapped. Do not enable remote OS authentication casually, as the trust boundary depends on client hosts, OS accounts, and network configuration.

### 3.3. Global Authentication

In environments integrated with a directory service or enterprise identity provider, a user can be mapped to a global identity:

```sql
CREATE USER directory_user
    IDENTIFIED GLOBALLY AS 'CN=Directory User,OU=People,DC=example,DC=com';
```

The distinguished name in the example must match the organization's directory structure and authentication configuration. Connectivity also depends on the directory service, Oracle Net, and corresponding security configuration.

Kerberos, RADIUS, or other network authentication mechanisms also require infrastructure-level setup. Running `CREATE USER` alone does not install or enable those authentication services.

### 3.4. Authentication and Authorization Are Two Separate Steps

A user who authenticates successfully may still receive errors when accessing data because privileges have not been granted. Example:

```sql
GRANT CREATE SESSION TO app_user;
GRANT SELECT ON app_owner.orders TO app_user;
```

`CREATE SESSION` allows opening a session; `SELECT` on `APP_OWNER.ORDERS` allows reading that specific table. The two privileges serve different purposes. When investigating login failures, check authentication and account status first; when investigating object access errors, check grants and roles.

## 4. Profiles and Password Policies

A profile centralizes a set of limits applied to users. A profile can specify failed login attempts, lock duration, password lifetime, grace time, and password reuse rules.

### 4.1. Commonly Used Password Limits

| Parameter | Effect |
|---|---|
| `FAILED_LOGIN_ATTEMPTS` | Consecutive failed login attempts before Oracle locks the account per the profile. |
| `PASSWORD_LOCK_TIME` | Duration the account remains locked after exceeding failed login attempts; unit is days. |
| `PASSWORD_LIFE_TIME` | Number of days a password remains valid before expiring. |
| `PASSWORD_GRACE_TIME` | Grace period days after password expiration; during this time the user may be warned and prompted to change the password. |
| `PASSWORD_REUSE_TIME` | Period that must elapse before reusing an old password. |
| `PASSWORD_REUSE_MAX` | Minimum number of password changes before an old password can be reused. |
| `PASSWORD_VERIFY_FUNCTION` | Function that validates new passwords, such as length and difference from the previous password. |
| `INACTIVE_ACCOUNT_TIME` | On supported versions, locks inactive users after a configured period. Confirm version support and activity calculation before applying. |

The `UNLIMITED` value has specific behavior per parameter. For `PASSWORD_REUSE_TIME` and `PASSWORD_REUSE_MAX`, configure them together according to the documentation for your Oracle version; when both have finite limits, both elapsed time and change count affect reuse eligibility. Do not set arbitrary values without understanding how they affect the password change process.

### 4.2. Creating a Sample Profile

The following example illustrates a policy with failed login threshold, lock duration, password lifetime, and grace time:

```sql
CREATE PROFILE app_password_policy LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_TIME 365
    PASSWORD_REUSE_MAX 10
    PASSWORD_VERIFY_FUNCTION ORA12C_STRONG_VERIFY_FUNCTION;
```

The numbers in the example are illustrative values, not mandatory standards for every organization. `PASSWORD_LOCK_TIME 1` corresponds to one day. Actual policies must fit security requirements, internal regulations, account types, and application operations.

`ORA12C_STRONG_VERIFY_FUNCTION` is a password verification function name provided in some Oracle installations via sample password management scripts. Verify that the function exists in the database and matches your version before assigning it. If an organization uses a custom function, the DBA must deploy it following Oracle's required interface and test valid passwords, invalid passwords, password changes, and execution errors.

Assign a profile to a user:

```sql
ALTER USER app_user PROFILE app_password_policy;
```

The `DEFAULT` profile applies to users without an explicit profile assignment. Do not assume the `DEFAULT` profile's parameters match organizational policy; DBAs should inspect actual values in the database.

### 4.3. Inspecting and Modifying Profiles

Profile limits can be viewed via data dictionary views:

```sql
SELECT profile, resource_name, limit
FROM dba_profiles
WHERE profile = 'APP_PASSWORD_POLICY'
ORDER BY resource_type, resource_name;
```

To modify limits, use `ALTER PROFILE`:

```sql
ALTER PROFILE app_password_policy LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1
    PASSWORD_GRACE_TIME 7;
```

Modifying a profile can affect many users assigned to that profile. Before editing, list all users assigned the profile, assess application impact, and notify stakeholders per operational procedures. Password management parameters are enforced by Oracle's profile mechanism; certain other resource limits in a profile may also depend on `RESOURCE_LIMIT` configuration and version.

### 4.4. Balancing Password Policies with Operations

Passwords should be sufficiently long, unique per account, and randomly generated using a secret management tool. Password verification functions can block passwords that are too short, too common, or too similar to the username. Forcing password changes on overly short cycles can push users toward predictable patterns or minor variations of old passwords.

Organizations should select password lifetimes according to compliance requirements and risk models. For service accounts, combine a secret manager, least privilege, monitoring, and controlled rotation workflows. Do not set `PASSWORD_LIFE_TIME UNLIMITED` simply to avoid application outages; if an exception exists, require justification, compensating controls, and a clear review expiration date.

## 5. Locking and Unlocking Accounts

Oracle can lock accounts automatically after repeated failed logins or manually by a DBA. These two cases must be distinguished when troubleshooting incidents.

### 5.1. Manual Locking

When a user leaves, an application is decommissioned, credentials show signs of compromise, or access must be temporarily suspended, a DBA can lock the account:

```sql
ALTER USER app_user ACCOUNT LOCK;
```

This command prevents the user from opening new sessions. Locking an account does not immediately terminate all already-connected sessions. If ongoing activity must be stopped, the DBA must inspect current sessions and handle them according to operational procedures, taking active transactions and application impact into account.

### 5.2. Unlocking

After verifying the root cause and obtaining approval, the DBA can unlock the account:

```sql
ALTER USER app_user ACCOUNT UNLOCK;
```

If an account was locked due to exceeding failed login attempts, identify the source of failed logins before unlocking. An application still holding an old password in its connection pool may keep failing authentication and lock the account again.

### 5.3. Automatic Profile-Based Locking

For example, a profile with:

```sql
FAILED_LOGIN_ATTEMPTS 5
PASSWORD_LOCK_TIME 1
```

When failed login attempts exceed the limit, Oracle locks the user for the configured duration. With a finite lock time, the account can unlock automatically once the lock period ends. With an unlimited lock setting, a DBA may need to unlock it manually. Specific behavior and status should be verified against the active profile and database version.

### 5.4. Distinguishing Account Lock from Password Expiration

Account locking prevents login. Password expiration requires changing the password per policy. A user can simultaneously be locked and expired; unlocking does not necessarily clear the password expiration requirement.

Common statuses in `DBA_USERS.ACCOUNT_STATUS` include:

| Status | General meaning |
|---|---|
| `OPEN` | The account is open with no expired or locked status. |
| `LOCKED` | The account is manually locked or in a lock state that does not auto-expire. |
| `LOCKED(TIMED)` | The account is locked for a timed period, typically due to failed login attempts. |
| `EXPIRED` | The password has expired and must be changed. |
| `EXPIRED(GRACE)` | The password has expired, but the user is within the grace period. |

Oracle can display combined statuses when a user is both locked and expired. Read the actual status rather than relying solely on a single date column.

## 6. Password Changes and Credential Lifecycle Management

### 6.1. On-Demand Password Changes

A DBA can set a new password for a user with:

```sql
ALTER USER app_user IDENTIFIED BY "NewUniqueSecretFromVault";
```

Users can change their own passwords using supported client tools. In SQL*Plus, the `PASSWORD` command prompts for old and new passwords, avoiding writing passwords directly in SQL statements:

```text
SQL> PASSWORD
Changing password for CURRENT_USER
Old password:
New password:
Retype new password:
```

This is a SQL*Plus command, not a SQL statement supported in every client. With other tools, use their corresponding secure password-change feature. Never send real passwords in tickets, chat, email, or logs.

### 6.2. Forcing a Password Change at Next Login

When provisioning a new account or after a DBA resets a password, you can require the user to change it on their next login:

```sql
ALTER USER app_user PASSWORD EXPIRE;
```

Depending on the client and application, the user receives a password-expired notification and is prompted to change it before continuing. Non-interactive service accounts may not be able to handle this password-change flow; plan credential rotation through a secret manager and application deployment workflow.

### 6.3. Lifecycle for Human Accounts

An individual user management lifecycle may include:

1. **Provisioning:** create an individual user, determine authentication method, assign a profile, and grant only necessary roles.
2. **Activation:** grant login privilege, deliver initial credentials over a secure channel, and require changing the initial password.
3. **Active use:** monitor status, failed logins, granted privileges, and anomalous activity.
4. **Change or reset:** rotate passwords when due per policy, when a user forgets a password, or on signs of credential exposure.
5. **Suspension:** lock the account when required for investigation or temporary access suspension.
6. **Revocation:** when a user leaves the organization or no longer has duties, lock the account, revoke grants/roles, and handle active sessions per procedure.
7. **Retention or removal:** drop a user only after verifying object ownership, application dependencies, retention requirements, and approvals.

### 6.4. Lifecycle for Service Accounts

Application accounts have a different lifecycle from human accounts because credentials are typically stored in a secret manager or deployment configuration and used by connection pools.

- Create a separate runtime account per application or per required trust boundary.
- Grant privileges on the exact tables, views, sequences, or packages used by the application.
- Store credentials in a secret manager; avoid hard-coding in source code, container images, or public config files.
- During rotation, update the secret and connection configuration in a controlled sequence; verify new instances use the new credential before revoking the old credential if the platform supports a transition workflow.
- Check connection pools, job schedulers, batch processes, and standby/failover systems so no component retains the old password.
- When an application is decommissioned, lock the account, confirm no connections or dependent jobs remain, then revoke privileges and handle the user per procedure.

Do not share one service account across unrelated applications. Separating identities improves traceability, limits blast radius on credential exposure, and enables independent rotation.

## 7. Inspecting Users, Statuses, and Granted Privileges

Data dictionary views allow DBAs to inspect actual configuration. `DBA_` views usually require administrative privileges or appropriate dictionary read privileges; regular users can use `USER_` and `ALL_` views within their permitted scope.

### 7.1. Checking Account Status

```sql
SELECT
    username,
    account_status,
    authentication_type,
    profile,
    default_tablespace,
    temporary_tablespace,
    expiry_date,
    lock_date
FROM dba_users
WHERE username = UPPER(:username);
```

Useful columns include `ACCOUNT_STATUS`, `PROFILE`, `DEFAULT_TABLESPACE`, `TEMPORARY_TABLESPACE`, `EXPIRY_DATE`, and `LOCK_DATE`. `AUTHENTICATION_TYPE` helps identify the authentication type recorded by Oracle. Columns and values may vary by version; refer to the data dictionary of your running version.

### 7.2. Checking Assigned Profiles

```sql
SELECT username, profile, account_status
FROM dba_users
WHERE profile = 'APP_PASSWORD_POLICY'
ORDER BY username;
```

This query helps identify which users are affected if a DBA changes a profile. Before editing a shared profile, check the entire list rather than looking only at the user currently being handled.

### 7.3. Checking System Privileges, Roles, and Object Privileges

```sql
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE grantee = UPPER(:username)
ORDER BY privilege;

SELECT grantee, granted_role, default_role
FROM dba_role_privs
WHERE grantee = UPPER(:username)
ORDER BY granted_role;

SELECT grantee, owner, table_name, privilege, grantable
FROM dba_tab_privs
WHERE grantee = UPPER(:username)
ORDER BY owner, table_name, privilege;
```

These three queries show the system privileges, roles, and object privileges granted directly to a user. To evaluate effective privileges, also consider privileges received via roles, nested roles, `PUBLIC` grants, privileges granted through definer-rights programs, and other database security mechanisms.

## 8. Troubleshooting Common Errors

| Error code | Common cause | Investigation approach |
|---|---|---|
| `ORA-01017` | Invalid username or password; sometimes caused by connecting to the wrong service or differences in how passwords are sent. | Verify username, service name, password casing, and the application's credential source. |
| `ORA-28000` | Account is locked. | Check `DBA_USERS.ACCOUNT_STATUS`, `LOCK_DATE`, profile, and the source of failed logins before unlocking. |
| `ORA-28001` | Password has expired. | Change the password per procedure; inspect `PASSWORD_LIFE_TIME` and profile. |
| `ORA-28002` | Password is about to expire or is in the profile's grace period. | Change the password before the grace period ends; inspect `PASSWORD_GRACE_TIME`. |
| `ORA-28003` | New password fails the verification function. | Check `PASSWORD_VERIFY_FUNCTION` requirements and choose a unique, sufficiently strong password. |
| `ORA-28007` | New password cannot be reused per policy. | Check `PASSWORD_REUSE_TIME`, `PASSWORD_REUSE_MAX`, and choose a new password. |
| `ORA-01045` | User lacks `CREATE SESSION` privilege. | Verify and grant `CREATE SESSION` only if the user is permitted to log in. |
| `ORA-01950` | User lacks sufficient tablespace quota when segment allocation is required. | Check quota and grant the required space limit on the right tablespace. |

Do not hastily resolve errors by granting the DBA role or `UNLIMITED TABLESPACE`. Identify the specific least privilege or missing configuration instead.

## 9. Revoking Privileges and Ending the User Lifecycle

When an account no longer needs access, the first step is usually locking the user:

```sql
ALTER USER app_user ACCOUNT LOCK;
```

Then check sessions, jobs, application connections, object ownership, and dependencies. If active sessions must be terminated, the DBA must identify the exact sessions and use the system's administrative session termination procedure. Do not assume locking a user automatically disconnects all existing connections.

Privileges can be revoked individually:

```sql
REVOKE app_order_reader FROM app_user;
REVOKE SELECT ON app_owner.orders FROM app_user;
```

If a user holds multiple grants, review both direct privileges and role-based privileges. For a schema-owning user, dropping the account can delete owned objects if `CASCADE` is used:

```sql
DROP USER app_user CASCADE;
```

`DROP USER ... CASCADE` is a destructive operation on objects in the schema. Perform it only after verifying backups, retention requirements, dependencies, ownership, and approvals. In many cases, locking the user and retaining the schema during a retention period is a safer choice than dropping it immediately.

## 10. Safe Operational Principles

- Use separate accounts for each person, application, and duty; avoid shared accounts.
- Grant `CREATE SESSION` only to users that need to log in and grant data privileges with the smallest scope.
- Separate the schema owner from the runtime user so the application holds no unnecessary DDL privileges.
- Use appropriate profiles per account group; review exceptions, especially for service accounts.
- Use long, random, unique passwords; store them in a secret manager and never write them into source code or logs.
- Monitor failed logins, locked accounts, expired passwords, and privilege changes.
- When rotating service credentials, update all consumers and connection pools according to a verifiable plan.
- When a user or application leaves the system, lock the account first, revoke privileges, and drop the schema only after assessing dependencies.
- In CDB/PDB environments, always verify the container before creating, altering, or locking a user.

## Conclusion

`CREATE USER` creates the identity and schema; `CREATE SESSION` allows opening connections; system privileges, roles, and object privileges determine what a user can do once connected. The authentication method defines where identity is verified, while profiles govern many password rules and account locking. Lifecycle management must cover provisioning, activation, password changes, temporary locking, privilege revocation, and decommissioning when accounts are no longer used. Combining these steps with least privilege, a secret manager, status checks, and clear operational procedures helps DBAs control Oracle access securely and with full traceability.
