# Profiles, password policies, and session resource limits

Oracle Database uses a **profile** to group rules applied to a database user. A profile can contain two groups of settings: password policies and resource limits. This allows DBAs to apply the same set of rules to a group of accounts such as application users, batch accounts, reporting accounts, or administrative accounts.

The password policy group controls failed login attempts, password lifetime, account lock duration, password history, password complexity, and rollover time when changing passwords for applications. The resource limits group controls concurrent sessions, CPU, logical reads, connection time, idle time, and several other resources.

These two groups have different enforcement mechanisms. **Password limits are always enforced by Oracle. Resource limits in a profile are only enforced when RESOURCE_LIMIT is enabled.** In addition, Oracle recommends using Database Resource Manager when more flexible resource management is needed. Therefore, profiles are an important tool for account administration, but not the only solution for workload management.

This lesson belongs to the **Security** group of Database Engine Relational Oracle. It focuses on the profile model, password policies, session/call-level resource limits, RESOURCE_LIMIT, Database Resource Manager, application account management, monitoring, and safe deployment procedures.

After this lesson, you will be able to:

- Explain profiles and how to assign a profile to a user.
- Distinguish password parameters from resource parameters.
- Use CREATE PROFILE, ALTER PROFILE, and DROP PROFILE.
- Understand DEFAULT, UNLIMITED, and how limits are inherited from the DEFAULT profile.
- Configure FAILED_LOGIN_ATTEMPTS and PASSWORD_LOCK_TIME.
- Configure PASSWORD_LIFE_TIME and PASSWORD_GRACE_TIME.
- Understand why PASSWORD_REUSE_TIME and PASSWORD_REUSE_MAX must work together.
- Apply PASSWORD_VERIFY_FUNCTION and check password complexity.
- Use INACTIVE_ACCOUNT_TIME and PASSWORD_ROLLOVER_TIME.
- Limit concurrent sessions, CPU, logical reads, CONNECT_TIME, and IDLE_TIME.
- Distinguish session-level limits from call-level limits.
- Enable RESOURCE_LIMIT and check its actual status.
- Distinguish profile resource limits from Database Resource Manager.
- Monitor DBA_PROFILES, DBA_USERS, DBA_USERS_WITH_DEFPWD, and V$SESSION.
- Design suitable profiles for applications, batch jobs, analysts, and service accounts.

> **Example scope:** Examples mainly follow Oracle Database 19c. Limit values in the examples are lab data for illustration, not production configurations for every system. You must check current profiles, actual workloads, release/RU, CDB/PDB architecture, and your organization's security policy before making changes.

## 1. What is a profile?

A profile is a set of attributes that Oracle assigns to a database user. A profile can contain:

- **Password parameters:** authentication rules and password lifecycle.
- **Resource parameters:** limits on resources that a user/session is allowed to consume.

Profiles help DBAs manage users by group. For example:

| Account group | Applicable profile |
| --- | --- |
| Transactional applications | Session count matching the connection pool, password lifecycle for service accounts |
| Reporting users | Session limits, CPU/call, or logical reads suited to the workload |
| Batch accounts | Limits suited to long-running jobs and execution windows |
| Developers | Session and resource limits in development environments |
| Administrative accounts | Strict authentication policies, managed separately under DBA procedures |

### 1.1. A user has only one profile

Each database user is assigned one profile at a time. A profile is assigned directly to a user, not to a role or another profile.

~~~sql
ALTER USER app_user PROFILE app_runtime_prof;
~~~

When changing a user's profile, the new profile applies to sessions created afterward. Already open sessions do not receive the new limits immediately.

### 1.2. Profiles do not replace roles

Roles are used to group object access privileges and system privileges. Profiles are used to group password/resource limits.

| Component | Purpose |
| --- | --- |
| User | Database login identity |
| Role | Group of access privileges |
| Profile | Group of password policies and resource limits |
| Database Resource Manager | Schedules and controls resource usage by workload |

For example, APP_RUNTIME_ROLE can grant SELECT/INSERT privileges on application tables, while APP_RUNTIME_PROF limits the session count and password lifecycle of APP_USER.

### 1.3. The DEFAULT profile

A user not assigned a specific profile uses the DEFAULT profile. If a specific profile omits a parameter or sets a parameter to DEFAULT, Oracle takes the corresponding value from the DEFAULT profile.

DEFAULT and UNLIMITED are different:

- DEFAULT: inherits the parameter value from the DEFAULT profile.
- UNLIMITED: sets no limit for that parameter.

Do not assume the database's DEFAULT profile always retains its initial values. A DBA may have modified it. Always query DBA_PROFILES before relying on default values.

## 2. Two parameter groups and enforcement mechanisms

| Group | Examples | Enforcement mechanism |
| --- | --- | --- |
| Password | FAILED_LOGIN_ATTEMPTS, PASSWORD_LIFE_TIME, PASSWORD_VERIFY_FUNCTION | Always managed by password management; independent of RESOURCE_LIMIT |
| Resource | SESSIONS_PER_USER, CPU_PER_CALL, IDLE_TIME, LOGICAL_READS_PER_SESSION | Enforced only when RESOURCE_LIMIT = TRUE |

### 2.1. RESOURCE_LIMIT

Check the current value:

~~~sql
SHOW PARAMETER resource_limit
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
~~~

On Oracle Database 19c, the documented default value is TRUE, but the actual configuration may have been changed by a DBA. Do not infer the status from the default value; check the running database.

If it needs to be enabled:

~~~sql
ALTER SYSTEM SET resource_limit = TRUE;
~~~

RESOURCE_LIMIT can be changed using ALTER SYSTEM. In a CDB/PDB environment, this must be executed in the permitted container and scope. If the change needs to persist across restarts, the DBA must determine how to configure the SPFILE appropriately for the environment.

### 2.2. Password parameters are not governed by RESOURCE_LIMIT

Even when RESOURCE_LIMIT = FALSE, rules such as failed login attempts, password lifetime, and password verification are still enforced by Oracle.

This is an important distinction when auditing a profile: resource limits may be declared but not enforced if RESOURCE_LIMIT is disabled; password limits remain in effect.

## 3. Creating, modifying, assigning, and dropping profiles

### 3.1. Required privileges

- CREATE PROFILE: create a profile.
- ALTER PROFILE: modify limits in a profile.
- DROP PROFILE: drop a profile.
- ALTER USER: assign a profile to a user.
- ALTER SYSTEM: change RESOURCE_LIMIT.
- ALTER RESOURCE COST: change the weights for COMPOSITE_LIMIT.

These privileges should be granted according to DBA/security administrator responsibilities, not broadly to application accounts.

### 3.2. Creating a profile

Syntax:

~~~sql
CREATE PROFILE profile_name LIMIT
    parameter value
    parameter value;
~~~

Application profile example:

~~~sql
CREATE PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 8
    CPU_PER_SESSION UNLIMITED
    CPU_PER_CALL 6000
    CONNECT_TIME 480
    IDLE_TIME 30
    LOGICAL_READS_PER_SESSION UNLIMITED
    LOGICAL_READS_PER_CALL 500000
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7;
~~~

The values above are examples only. CPU_PER_CALL 6000 equals 60 seconds of CPU because the unit is hundredths of a second. CONNECT_TIME 480 is 480 minutes. IDLE_TIME 30 is 30 minutes without a call. You must benchmark and tune according to application behavior.

### 3.3. Assigning a profile to a user

~~~sql
ALTER USER app_user PROFILE app_runtime_prof;
~~~

When creating a new user:

~~~sql
CREATE USER app_user
IDENTIFIED BY "Replace_With_Secret"
PROFILE app_runtime_prof;
~~~

Do not write real production passwords into scripts, repositories, or deployment logs. Use a secret manager or a secure provisioning mechanism.

### 3.4. Modifying a profile

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 12
    IDLE_TIME 45
    CPU_PER_CALL 9000;
~~~

Profile changes apply to new sessions. Existing sessions continue using the attributes loaded at login.

### 3.5. Setting a parameter to DEFAULT or UNLIMITED

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    LOGICAL_READS_PER_SESSION DEFAULT
    CONNECT_TIME UNLIMITED;
~~~

DEFAULT inherits the value from the DEFAULT profile. UNLIMITED removes the limit on that parameter.

### 3.6. Dropping a profile

~~~sql
DROP PROFILE app_runtime_prof;
~~~

You cannot drop the DEFAULT profile. If the profile is currently assigned to users, CASCADE is required:

~~~sql
DROP PROFILE app_runtime_prof CASCADE;
~~~

When dropping a profile with CASCADE, users currently using that profile are reassigned to DEFAULT. Dropping a profile does not alter active sessions; new sessions use the profile after reassignment takes effect.

## 4. Password parameters

Oracle profiles include the following main parameters:

| Parameter | Meaning |
| --- | --- |
| FAILED_LOGIN_ATTEMPTS | Number of consecutive failed login attempts before locking the account |
| PASSWORD_LOCK_TIME | Lock duration after exceeding FAILED_LOGIN_ATTEMPTS |
| PASSWORD_LIFE_TIME | Number of days a password can be used before expiring |
| PASSWORD_GRACE_TIME | Warning/grace period allowing login to change the password before full expiration |
| PASSWORD_REUSE_TIME | Number of days to wait before an old password can be reused |
| PASSWORD_REUSE_MAX | Number of password changes required before an old password can be reused |
| PASSWORD_VERIFY_FUNCTION | Function to check password strength/complexity |
| INACTIVE_ACCOUNT_TIME | Number of days without a successful login before locking the account |
| PASSWORD_ROLLOVER_TIME | Period allowing both old and new passwords to log in during a rollover |

Time parameters are generally measured in days. Fractions of a day can be used, for example 1 hour is 1/24 day and 1 minute is 1/1440 day. FAILED_LOGIN_ATTEMPTS and PASSWORD_REUSE_MAX require integers.

## 5. FAILED_LOGIN_ATTEMPTS and PASSWORD_LOCK_TIME

These two parameters work together to limit failed login attempts.

### 5.1. FAILED_LOGIN_ATTEMPTS

FAILED_LOGIN_ATTEMPTS specifies the number of consecutive failed authentication attempts before the account is locked.

~~~sql
CREATE PROFILE login_guard_prof LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1;
~~~

In the example above, after five consecutive failed login attempts, the account is locked for the PASSWORD_LOCK_TIME duration.

### 5.2. PASSWORD_LOCK_TIME

PASSWORD_LOCK_TIME is measured in days:

- 1: lock for one day.
- 1/24: lock for one hour.
- UNLIMITED: lock until a DBA unlocks it manually.

Manual unlock:

~~~sql
ALTER USER app_user ACCOUNT UNLOCK;
~~~

Setting PASSWORD_LOCK_TIME too long can increase support overhead if an application is misconfigured with a wrong password and keeps retrying logins. Setting it too short can reduce brute-force protection effectiveness. Combine this with monitoring, connection-layer rate limiting, and account protection policies.

### 5.3. Failure counting and reset

After a user logs in successfully, Oracle resets the consecutive failed login counter. In proxy authentication or CONNECT THROUGH environments, you must understand which account is being counted for failed logins.

### 5.4. Checking account status

~~~sql
SELECT
    username,
    account_status,
    lock_date,
    expiry_date,
    profile
FROM dba_users
WHERE username = 'APP_USER';
~~~

ACCOUNT_STATUS can display OPEN, LOCKED, EXPIRED, EXPIRED(GRACE), or combined statuses depending on the situation. The status shown in the dictionary may be updated upon the next login attempt; cross-check with login events and lock timestamps.

## 6. PASSWORD_LIFE_TIME and PASSWORD_GRACE_TIME

### 6.1. PASSWORD_LIFE_TIME

PASSWORD_LIFE_TIME specifies the number of days a password can be used for authentication before expiring.

~~~sql
CREATE PROFILE human_user_prof LIMIT
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7;
~~~

The 90-day example is an illustrative policy. Choose the lifetime according to your security policy and account type. Oracle advises caution against setting PASSWORD_LIFE_TIME too low, because frequent password changes can create operational burden and encourage predictable password choices.

### 6.2. PASSWORD_GRACE_TIME

When a password reaches the end of PASSWORD_LIFE_TIME, the user enters the grace period:

1. Log in using the current password.
2. Oracle warns that the password will expire soon.
3. The user can still log in during the grace period to change the password.
4. If the grace period ends without changing the password, the password expires and the user must change it before continuing.

Common messages:

- ORA-28002: the password will expire within a number of days.
- ORA-28001: the password has expired.

### 6.3. Grace period is not a new lifetime to keep the password forever

PASSWORD_GRACE_TIME is a transition window. It gives applications/users time to change passwords without sudden disconnection on the expiration date.

### 6.4. Checking expiry

~~~sql
SELECT
    username,
    account_status,
    expiry_date,
    profile
FROM dba_users
WHERE username IN ('APP_USER', 'REPORT_USER');
~~~

Do not check only the profile definition. DBA_USERS shows the status and expiration date of each individual account.

## 7. PASSWORD_REUSE_TIME and PASSWORD_REUSE_MAX

These two parameters must be configured together to set password reuse conditions.

### 7.1. PASSWORD_REUSE_TIME

Number of days that must pass before an old password can be reused.

### 7.2. PASSWORD_REUSE_MAX

Number of password changes that must occur before an old password can be reused.

### 7.3. Both conditions must be satisfied

~~~sql
CREATE PROFILE password_history_prof LIMIT
    PASSWORD_REUSE_TIME 365
    PASSWORD_REUSE_MAX 10;
~~~

With this example, an old password can only be reused when:

- 365 days have passed since that password was last used.
- The user has changed the password at least 10 times according to the rules.

### 7.4. UNLIMITED has easily misunderstood semantics

| PASSWORD_REUSE_TIME | PASSWORD_REUSE_MAX | Result |
| --- | --- | --- |
| Finite value | Finite value | Both the time condition and change count must be satisfied |
| UNLIMITED | Finite value | Old password can never be reused |
| Finite value | UNLIMITED | Old password can never be reused |
| UNLIMITED | UNLIMITED | Oracle ignores both restrictions; passwords can be reused |

This is a critical point: one UNLIMITED parameter combined with one finite parameter means the password can never be reused; when both are UNLIMITED, Oracle ignores both.

### 7.5. DEFAULT and password reuse

If one of the two parameters is set to DEFAULT, Oracle takes the corresponding value from the DEFAULT profile. If the DEFAULT profile still has UNLIMITED, that parameter is treated as UNLIMITED. Check DBA_PROFILES to avoid misconfiguration.

## 8. PASSWORD_VERIFY_FUNCTION

PASSWORD_VERIFY_FUNCTION attaches a PL/SQL function used to validate passwords when a user sets or changes a password.

### 8.1. Purpose

The verification function can enforce rules such as:

- Minimum length.
- Uppercase/lowercase characters.
- Digits or special characters.
- Not containing the username or predictable variants.
- Not being too similar to the old password.
- Not being on a list of common passwords.

Exact complexity rules depend on the implemented function.

### 8.2. Oracle-supplied verification functions

Oracle provides password verification scripts/functions for certain versions and policies. Common function names in Oracle 19c include ORA12C_VERIFY_FUNCTION or ORA12C_STRONG_VERIFY_FUNCTION, depending on the installed script and environment.

Before assigning, verify that the function exists in SYS and that the user assigning the profile has appropriate EXECUTE privileges.

~~~sql
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'SYS'
  AND object_name IN (
      'ORA12C_VERIFY_FUNCTION',
      'ORA12C_STRONG_VERIFY_FUNCTION'
  )
ORDER BY object_name;
~~~

If the function is installed and policy permits:

~~~sql
ALTER PROFILE human_user_prof LIMIT
    PASSWORD_VERIFY_FUNCTION ORA12C_VERIFY_FUNCTION;
~~~

Do not assume the function exists just because the database is 19c. The DBA must verify that the script has been installed in the Oracle Home/database and check the function status.

### 8.3. The function must belong to the SYS schema

Oracle requires the password verification function to reside in the SYS schema and the caller to have EXECUTE privilege on the function. You can use an Oracle-supplied script or a custom function written according to the documented interface.

### 8.4. Resetting to no verification

~~~sql
ALTER PROFILE human_user_prof LIMIT
    PASSWORD_VERIFY_FUNCTION NULL;
~~~

NULL means no password verification function is run for that profile. Do not use this configuration if policy requires password complexity.

### 8.5. Password complexity does not replace MFA

Password verification only validates passwords against the function. It does not replace:

- Multi-factor authentication.
- Network encryption.
- Account lifecycle management.
- Secret vaults and rotation automation.
- Auditing and monitoring.
- Privilege separation.

## 9. INACTIVE_ACCOUNT_TIME

INACTIVE_ACCOUNT_TIME automatically locks an account if the user does not log in successfully within a consecutive period of time.

~~~sql
CREATE PROFILE dormant_user_prof LIMIT
    INACTIVE_ACCOUNT_TIME 60;
~~~

For example, the account will be locked if there is no successful login within 60 days.

### 9.1. Value limits

In Oracle 19c:

- Unit is whole days.
- Minimum value is 15 days.
- Maximum value is 24855 days.
- UNLIMITED disables the inactivity limit.

### 9.2. Which accounts are affected?

This parameter applies to database-authenticated users; password parameters have no effect on external/global authenticated users. In a read-only database environment, the database cannot perform account locking operations as on a primary database in the normal manner.

### 9.3. Inactivity differs from account lock due to failed logins

INACTIVE_ACCOUNT_TIME tracks the time of the most recent successful login. FAILED_LOGIN_ATTEMPTS tracks consecutive failed authentication attempts. The two mechanisms have different purposes.

## 10. PASSWORD_ROLLOVER_TIME

PASSWORD_ROLLOVER_TIME supports changing passwords for application service accounts without needing to update all clients simultaneously.

### 10.1. The service account problem

An application may run across multiple nodes, containers, or servers. All connect to the database using a single service account. When a DBA changes the password, each client must be updated with the new secret. If the database rejects the old password immediately, nodes that have not yet received the new secret may lose connectivity.

### 10.2. Rollover period

When a profile has a non-zero PASSWORD_ROLLOVER_TIME and the DBA changes the password, Oracle allows both the old password and the new password to log in during the configured rollover window.

~~~sql
CREATE PROFILE app_service_prof LIMIT
    PASSWORD_ROLLOVER_TIME 1;
~~~

A value of 1 means one day. During this window, the application can be updated node by node to the new password.

### 10.3. Rollover limits

- Value 0 or NULL: disables rollover.
- Positive value: enables rollover.
- Minimum duration: 1 hour.
- Maximum duration: 60 days or the lesser of PASSWORD_LIFE_TIME and PASSWORD_GRACE_TIME according to Oracle rules.
- Unit is days; 1 hour is represented as 1/24.

Six-hour example:

~~~sql
ALTER PROFILE app_service_prof LIMIT
    PASSWORD_ROLLOVER_TIME 6/24;
~~~

### 10.4. Zero-downtime password rotation procedure

1. Create/modify a profile with a non-zero PASSWORD_ROLLOVER_TIME.
2. Assign the profile to the service account.
3. The DBA changes the database account password.
4. During the rollover period, both old and new passwords can log in.
5. Update the secret on each application node.
6. Verify that all nodes use the new password.
7. End the rollover early once completed.

Ending early:

~~~sql
ALTER USER app_service_user
EXPIRE PASSWORD ROLLOVER PERIOD;
~~~

After the rollover ends, only the new password is accepted.

### 10.5. Checking status

~~~sql
SELECT username, account_status, profile
FROM dba_users
WHERE username = 'APP_SERVICE_USER';
~~~

During rollover, ACCOUNT_STATUS may show IN ROLLOVER.

### 10.6. For service accounts only

Oracle designed gradual password rollover for database application clients/service accounts, not administrative users. Administrative users are restricted from using this feature; do not grant administrative privileges to a user whose profile enables rollover.

If a password is suspected of being compromised, change/revoke it immediately under incident response; do not extend rollover merely for deployment convenience.

## 11. Session-level and call-level resource parameters

Profiles can limit resources at two levels:

- **Session level:** total resources consumed over the lifetime of a session.
- **Call level:** resources consumed by a single SQL processing call, such as parse, execute, or fetch.

### 11.1. Resource parameters table

| Parameter | Level | Unit/Meaning |
| --- | --- | --- |
| SESSIONS_PER_USER | Concurrent sessions | Maximum concurrent sessions for a user |
| CPU_PER_SESSION | Session | Cumulative CPU time, in 1/100 seconds |
| CPU_PER_CALL | Call | CPU time for one call, in 1/100 seconds |
| CONNECT_TIME | Session | Total connection elapsed time, in minutes |
| IDLE_TIME | Session | Continuous time without a call, in minutes |
| LOGICAL_READS_PER_SESSION | Session | Data blocks read from memory and disk within a session |
| LOGICAL_READS_PER_CALL | Call | Data blocks read within one call |
| PRIVATE_SGA | Session | Private SGA memory; only useful with Shared Server |
| COMPOSITE_LIMIT | Session | Total resource cost in weighted service units |

### 11.2. SESSIONS_PER_USER

Limits the number of concurrent sessions for a user:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 8;
~~~

If an application uses a connection pool, the value must be compatible with:

- Number of application instances.
- Maximum pool size per instance.
- Batch/monitoring connections using the same user.
- Administrative or support connections, if any.

Setting it lower than the total valid connections can cause the application to receive errors when opening additional sessions. Setting it too high can allow a service account to open more sessions than the system can handle.

### 11.3. CPU_PER_SESSION

Limits total CPU time for a session. The unit is 1/100 second.

~~~sql
ALTER PROFILE analyst_prof LIMIT
    CPU_PER_SESSION 360000;
~~~

360000 centiseconds equals 3600 CPU seconds. This is CPU time, not wall-clock time.

### 11.4. CPU_PER_CALL

Limits CPU time for a single call:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    CPU_PER_CALL 6000;
~~~

6000 centiseconds equals 60 CPU seconds for one call. A query may involve multiple calls during parse/execute/fetch; do not equate CPU_PER_CALL with total CPU for the entire session.

### 11.5. LOGICAL_READS_PER_SESSION

Limits total logical block reads within a session. Logical reads include blocks read from the buffer cache and blocks read from disk into the cache.

### 11.6. LOGICAL_READS_PER_CALL

Limits logical reads for a single call:

~~~sql
ALTER PROFILE analyst_prof LIMIT
    LOGICAL_READS_PER_CALL 500000;
~~~

This is a block count limit, not a row count limit. A query returning few rows can still read many blocks if predicates are not selective or the execution plan is suboptimal.

### 11.7. CONNECT_TIME

CONNECT_TIME limits the total elapsed time of a session, in minutes:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    CONNECT_TIME 480;
~~~

A value of 480 equals eight hours. When exceeded, Oracle rolls back the current transaction and terminates the session. Time is checked periodically, so a session may remain open slightly longer than the limit.

CONNECT_TIME differs from IDLE_TIME: CONNECT_TIME counts total session existence time, including active working time.

### 11.8. IDLE_TIME

IDLE_TIME limits continuous time a session makes no database calls:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    IDLE_TIME 30;
~~~

After about 30 minutes of idle time, Oracle can terminate the session. Time is checked periodically, so it is not necessarily disconnected at the exact 30-minute mark to the second.

**A long-running query is not counted as idle just because it takes a long time.** IDLE_TIME measures the duration with no calls between client calls to the database.

With connection pools, synchronize IDLE_TIME with the pool idle timeout and connection validation mechanism. If the database terminates a session before the pool evicts the connection, the application may borrow a dead connection and fail on the next use.

### 11.9. PRIVATE_SGA

PRIVATE_SGA limits a session's private memory area in the SGA. This parameter is only meaningful when using Shared Server architecture; with Dedicated Server, private SQL/PLSQL areas typically reside in the PGA.

### 11.10. COMPOSITE_LIMIT

COMPOSITE_LIMIT limits the total resource cost of a session in service units. Oracle calculates a weighted sum from:

- CPU_PER_SESSION.
- CONNECT_TIME.
- LOGICAL_READS_PER_SESSION.
- PRIVATE_SGA.

Weights are configured via ALTER RESOURCE COST. If no weight is set for a resource, its default weight is 0.

Example:

~~~sql
ALTER RESOURCE COST
    CPU_PER_SESSION 100
    CONNECT_TIME 1
    LOGICAL_READS_PER_SESSION 2;
~~~

With the formula above, the session cost is:

~~~text
cost =
    100 * CPU_PER_SESSION
  +   1 * CONNECT_TIME
  +   2 * LOGICAL_READS_PER_SESSION
~~~

Then the profile can limit COMPOSITE_LIMIT:

~~~sql
ALTER PROFILE analyst_prof LIMIT
    COMPOSITE_LIMIT 5000000;
~~~

COMPOSITE_LIMIT is harder to design than individual limits because the DBA must understand the workload and choose weights. Do not use an arbitrary number without measuring usage first.

## 12. What happens when a resource limit is exceeded?

Oracle handles limit violations differently depending on the type of limit.

### 12.1. Exceeding CONNECT_TIME or IDLE_TIME

Oracle:

1. Rolls back the current transaction.
2. Terminates the session.
3. Reclaims session resources.
4. The client usually receives an error on the session's next call.

PMON may need additional time to clean up the session after termination.

### 12.2. Exceeding other session-level limits

When a session-level limit such as CPU_PER_SESSION or LOGICAL_READS_PER_SESSION is exceeded, Oracle aborts the current operation/statement and rolls back the statement. Previous statements in the transaction remain intact. The user can only COMMIT, ROLLBACK, or disconnect; normal work cannot continue in that session.

### 12.3. Exceeding call-level limits

When CPU_PER_CALL or LOGICAL_READS_PER_CALL is exceeded:

- The current statement is aborted and rolled back.
- Previous statements in the transaction remain intact.
- The session stays connected.
- The client can handle the error and continue the session per application logic.

### 12.4. Do not confuse statement rollback with transaction rollback

With a call-level limit, the statement exceeding the threshold is rolled back, but earlier work in the transaction is not automatically lost. With CONNECT_TIME/IDLE_TIME, Oracle rolls back the current transaction and terminates the session. Understand this when designing applications with multiple DML statements in the same transaction.

## 13. Enabling and verifying resource enforcement

### 13.1. Checking RESOURCE_LIMIT

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
~~~

If it is FALSE, profile resource limits are not enforced. Password parameters remain active.

### 13.2. Enabling enforcement

~~~sql
ALTER SYSTEM SET resource_limit = TRUE;
~~~

This change affects the entire database or container scope depending on where it is executed. The DBA must assess the impact on all accounts using resource profiles.

### 13.3. Checking assigned profiles

~~~sql
SELECT username, profile, account_status
FROM dba_users
ORDER BY username;
~~~

### 13.4. Checking resource limits in profiles

~~~sql
SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
WHERE profile IN (
    'APP_RUNTIME_PROF',
    'ANALYST_PROF',
    'DEFAULT'
)
ORDER BY profile, resource_type, resource_name;
~~~

DBA_PROFILES shows the configured parameters and values. If a profile uses DEFAULT, inspect the corresponding row in the DEFAULT profile to find the effective value.

## 14. Password defaults in the DEFAULT profile

Oracle Database 19c documents several common values for the DEFAULT profile:

| Password parameter | Documented default value |
| --- | --- |
| FAILED_LOGIN_ATTEMPTS | 10 |
| PASSWORD_LIFE_TIME | 180 days |
| PASSWORD_GRACE_TIME | 7 days |
| PASSWORD_LOCK_TIME | 1 day |
| PASSWORD_REUSE_TIME | UNLIMITED |
| PASSWORD_REUSE_MAX | UNLIMITED |
| PASSWORD_VERIFY_FUNCTION | NULL |
| INACTIVE_ACCOUNT_TIME | UNLIMITED |
| PASSWORD_ROLLOVER_TIME | 0 |

Resource parameters in the DEFAULT profile initially default to UNLIMITED. However, a DBA may modify the DEFAULT profile, and databases created via different methods may have different settings. Therefore, query DBA_PROFILES instead of hard-coding assumptions into runbooks.

### 14.1. Viewing the DEFAULT profile

~~~sql
SELECT resource_name, resource_type, limit
FROM dba_profiles
WHERE profile = 'DEFAULT'
ORDER BY resource_type, resource_name;
~~~

### 14.2. DEFAULT password verify function is NULL

If PASSWORD_VERIFY_FUNCTION is NULL, the profile does not invoke a password complexity function. Setting PASSWORD_LIFE_TIME alone does not ensure strong passwords or prevent reuse of old passwords.

## 15. Creating a profile combining password policy and resource limits

The example below creates a profile for a transactional application. Values are for practice only.

~~~sql
CREATE PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 12
    CPU_PER_SESSION UNLIMITED
    CPU_PER_CALL 6000
    CONNECT_TIME 480
    IDLE_TIME 30
    LOGICAL_READS_PER_SESSION UNLIMITED
    LOGICAL_READS_PER_CALL 500000
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_TIME 365
    PASSWORD_REUSE_MAX 10
    PASSWORD_ROLLOVER_TIME 0;
~~~

If the organization requires password complexity, assign PASSWORD_VERIFY_FUNCTION after confirming the function is available:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    PASSWORD_VERIFY_FUNCTION ORA12C_VERIFY_FUNCTION;
~~~

Assign the profile:

~~~sql
ALTER USER app_service_user PROFILE app_runtime_prof;
~~~

Verify:

~~~sql
SELECT username, profile, account_status
FROM dba_users
WHERE username = 'APP_SERVICE_USER';

SELECT resource_name, resource_type, limit
FROM dba_profiles
WHERE profile = 'APP_RUNTIME_PROF'
ORDER BY resource_type, resource_name;
~~~

After making changes, open a new session with the account to test. Previously open sessions do not automatically reload the profile.

## 16. Dedicated profile for service accounts and gradual rollover

Application accounts often have passwords stored in a secret manager and distributed across multiple application nodes. A dedicated profile can be used:

~~~sql
CREATE PROFILE app_service_rollover_prof LIMIT
    SESSIONS_PER_USER 20
    IDLE_TIME 60
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 180
    PASSWORD_GRACE_TIME 7
    PASSWORD_ROLLOVER_TIME 1;
~~~

Assign to the service user:

~~~sql
ALTER USER app_service_user
PROFILE app_service_rollover_prof;
~~~

When a password change is needed:

~~~sql
ALTER USER app_service_user
IDENTIFIED BY "New_Secret_From_Vault";
~~~

During the rollover period, both old and new passwords can be accepted. Update all application nodes, then expire rollover early:

~~~sql
ALTER USER app_service_user
EXPIRE PASSWORD ROLLOVER PERIOD;
~~~

Check the account:

~~~sql
SELECT username, account_status, profile
FROM dba_users
WHERE username = 'APP_SERVICE_USER';
~~~

Do not grant administrative privileges to a service account just for deployment convenience. Password rollover is designed for application accounts and does not apply to administrative users under Oracle restrictions.

## 17. Profiles for analyst and batch workloads

Not all user groups need the same limits.

### 17.1. Analyst profile

~~~sql
CREATE PROFILE analyst_prof LIMIT
    SESSIONS_PER_USER 3
    CPU_PER_CALL 12000
    CONNECT_TIME 720
    IDLE_TIME 20
    LOGICAL_READS_PER_CALL 1000000
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7;
~~~

This profile illustrates limits on session count, call CPU, connection time, and idle time. For large analytical queries, setting CPU/logical reads limits too low may cause legitimate queries to fail.

### 17.2. Batch profile

~~~sql
CREATE PROFILE batch_prof LIMIT
    SESSIONS_PER_USER 2
    CPU_PER_SESSION UNLIMITED
    CPU_PER_CALL UNLIMITED
    CONNECT_TIME 1440
    IDLE_TIME 60
    LOGICAL_READS_PER_SESSION UNLIMITED
    LOGICAL_READS_PER_CALL UNLIMITED
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24;
~~~

Batch jobs may require long sessions and read many blocks. This profile illustrates separating batch workloads from interactive users. If you need to schedule CPU, parallelism, I/O, or workload priority, consider Database Resource Manager.

### 17.3. Do not use profiles to mask a runaway SQL query

If a query runs too long due to plan regression, profile CPU_PER_CALL can abort the query but does not fix the root cause. Inspect the execution plan, statistics, SQL tuning, and Resource Manager directives instead of simply lowering thresholds.

## 18. Profiles and Database Resource Manager

Oracle SQL Language Reference recommends Database Resource Manager rather than using only profiles to set resource limits when flexible management mechanisms are needed.

### 18.1. Profile resource limits

Profiles provide hard limits such as:

- Maximum session count.
- CPU time per call/session.
- Logical reads per call/session.
- Connect time and idle time.
- Certain memory/session limits.

When a threshold is exceeded, the operation/session may be aborted or terminated.

### 18.2. Database Resource Manager

Database Resource Manager allows DBAs to define resource plans, consumer groups, and directives to allocate resources among workload classes.

Capabilities may include:

- Allocating CPU by ratio/priority.
- Limiting or governing parallel execution.
- Managing active sessions and queueing.
- Prioritizing critical workloads.
- Managing I/O and supported resources.
- Switching consumer groups based on mapping rules.

### 18.3. Comparison

| Criterion | Profile | Database Resource Manager |
| --- | --- | --- |
| Attached to | Database user | Consumer group/workload |
| Session count | Has SESSIONS_PER_USER | Can manage active sessions via directives |
| Password policy | Yes | Not its purpose |
| CPU | Hard limits per session/call | Flexible workload allocation/governance |
| Workload priority | Limited | Has resource plans/directives |
| Query queueing | Not the primary mechanism | Can manage queueing via configuration |
| Manage by service/module | Limited | Can map workloads to consumer groups |

### 18.4. Both can be used together

A design can:

- Use profiles for password policies and maximum session counts.
- Use Resource Manager to prioritize OLTP over batch/reporting.
- Use network/application pool limits to control external connections.
- Use SQL tuning and plan management to handle query regressions.

Do not view profiles and Resource Manager as mutually exclusive choices.

## 19. Monitoring profiles and sessions

### 19.1. DBA_PROFILES

~~~sql
SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
ORDER BY profile, resource_type, resource_name;
~~~

USER_PROFILES can be used to view profile settings within the current user's scope according to privileges.

### 19.2. DBA_USERS

~~~sql
SELECT
    username,
    profile,
    account_status,
    lock_date,
    expiry_date,
    authentication_type
FROM dba_users
ORDER BY username;
~~~

Dictionary columns may differ across releases. If querying a column that does not exist, consult the DBA_USERS reference for your database version.

### 19.3. Finding users on a profile

~~~sql
SELECT username, account_status
FROM dba_users
WHERE profile = 'APP_RUNTIME_PROF'
ORDER BY username;
~~~

### 19.4. Monitoring current sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    profile,
    last_call_et,
    machine,
    program,
    module
FROM v$session
WHERE username = 'APP_SERVICE_USER'
ORDER BY sid;
~~~

LAST_CALL_ET depends on session status: when INACTIVE, it is the number of seconds since the session became inactive; when ACTIVE, it is the number of seconds since the session became active. It is useful for cross-checking IDLE_TIME but does not replace the enforcement mechanism.

### 19.5. Monitoring session statistics

~~~sql
SELECT
    s.sid,
    s.serial#,
    n.name,
    st.value
FROM v$session s
JOIN v$sesstat st
  ON st.sid = s.sid
JOIN v$statname n
  ON n.statistic# = st.statistic#
WHERE s.username = 'APP_SERVICE_USER'
  AND n.name IN (
      'CPU used by this session',
      'session logical reads'
  )
ORDER BY s.sid, n.name;
~~~

These are cumulative figures per session. Use deltas between two points in time or combine with monitoring to understand consumption rates; do not compare cumulative totals between sessions of different lifetimes.

### 19.6. Finding users with default passwords

~~~sql
SELECT
    d.username,
    u.account_status,
    u.profile
FROM dba_users_with_defpwd d
JOIN dba_users u
  ON u.username = d.username
ORDER BY d.username;
~~~

DBA_USERS_WITH_DEFPWD helps locate accounts still using default passwords. Address these accounts according to system security policy and ownership.

## 20. CDB and PDB: common profiles and local profiles

In a multitenant database, a profile can be common or local:

- A common profile is created in the CDB root and spans containers according to common object rules.
- A local profile is created in a PDB and applies only within that PDB.

### 20.1. Common profile naming

Common profiles generally require the prefix specified by COMMON_USER_PREFIX, which defaults to C##. Example:

~~~sql
CREATE PROFILE c##common_app_prof LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1;
~~~

Execute in the CDB root with appropriate privileges.

### 20.2. Password/resource profile of a common user

In a CDB, when a common user is assigned one profile in the root and another profile in a PDB, Oracle applies password-related settings from the root profile; session resource-related settings in the PDB are taken from the profile assigned in that PDB according to multitenant rules.

This is an important detail when the same common user logs into multiple PDBs. Do not assume password policies and resource limits both come from the same profile.

### 20.3. Checking the current container

~~~sql
SHOW CON_NAME
~~~

Or:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Before CREATE/ALTER PROFILE, confirm whether you are in the root or a PDB and verify the intended scope of the change.

## 21. Do profile changes affect existing sessions?

No. Profile changes apply to sessions created after the change.

Example:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    IDLE_TIME 15;
~~~

Sessions that logged in before the ALTER PROFILE statement still keep the limits loaded at connection time. New sessions will use IDLE_TIME 15.

Therefore, the deployment workflow should be:

1. Check the current profile.
2. Modify the profile.
3. Verify the user is assigned the correct profile.
4. Open a new session using a test account.
5. Verify behavior.
6. Only then apply to production account groups.

If enforcement verification is needed, test in a lab environment with small thresholds and a controlled workload. Do not intentionally trigger CPU/IO runaways in production.

## 22. Impact on connection pools and applications

Profile resource limits can directly impact applications using connection pools.

### 22.1. SESSIONS_PER_USER and pool size

If a service account is shared across multiple application instances, total pool capacity may exceed SESSIONS_PER_USER:

~~~text
Node A pool max = 10
Node B pool max = 10
Node C pool max = 10
Total potential sessions = 30
~~~

If the profile limits sessions to 20, the last node may not be able to open enough connections. Calculate the total number of connections that can be open concurrently, including monitoring and batch jobs.

### 22.2. IDLE_TIME and pool validation

The database can terminate idle sessions after timeout. The connection pool needs to:

- Use an idle timeout lower than or coordinated with the database timeout.
- Validate connections before handing them to requests.
- Evict connections closed by the database.
- Retry connections according to a safe policy.

Do not simply set IDLE_TIME to unlimited to avoid stale connection errors; evaluate session leaks and connection counts as well.

### 22.3. CONNECT_TIME and connection lifetime

CONNECT_TIME limits total session age. The pool must account for the database terminating sessions by age and recreate connections. If the profile has a CONNECT_TIME shorter than the pool's connection lifetime, the application may encounter connection errors when sessions are terminated.

### 22.4. Password expiration and secret rotation

When a service account's password expires, the application may lose the ability to create new connections. Therefore:

- Synchronize password lifecycle with the secret manager.
- Alert before expiration.
- Test rotation in a staging environment.
- Use PASSWORD_ROLLOVER_TIME if appropriate to update multiple clients gradually.
- Prevent the service account from being locked by failed logins due to stale secrets.

## 23. Common errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-02391 | Exceeded SESSIONS_PER_USER | Check pool size, session leaks, and profile |
| ORA-02393 | Exceeded CPU_PER_CALL | Check query plan, workload, and call threshold |
| ORA-02394 | Exceeded CPU_PER_SESSION | Check session workload and total CPU |
| ORA-02395 | Exceeded LOGICAL_READS_PER_SESSION | Check logical reads, plan, and limit |
| ORA-02396 | Exceeded IDLE_TIME | Idle session terminated; check pool timeout |
| ORA-02399 | Exceeded CONNECT_TIME | Session exceeded max time; adjust connection lifecycle |
| ORA-28000 | Account is locked | Check failed attempts, lock time, and unlock policy |
| ORA-28001 | Password has expired | Change password per password lifecycle |
| ORA-28002 | Password will expire soon | Change password during grace period |
| ORA-28003 | Password verification function rejected password | Review verify function rules and choose a compliant password |
| Resource limit declared but has no effect | RESOURCE_LIMIT is FALSE | Check V$PARAMETER and enable enforcement if approved |
| ALTER PROFILE does not affect open sessions | Profile changes apply to new sessions | Open a new session to verify |
| Password verify function invalid | Function not installed or compile error | Check SYS objects, grants, and function status |
| User locked due to inactivity | INACTIVE_ACCOUNT_TIME exceeded | Confirm owner then unlock per procedure |
| Application loses connections after idle | IDLE_TIME lower than pool timeout | Synchronize timeouts and connection validation |

Error codes may depend on the resource type and when Oracle raises the error. When investigating, read the full error stack and consult the SQL Language Reference for the release.

## 24. Common misconceptions

| Misconception | Reality |
| --- | --- |
| A profile is a role | Roles manage privileges; profiles manage password/resource limits |
| A user can have multiple profiles simultaneously | A user can only be assigned one profile at a time |
| Profiles are assigned to roles | Profiles are assigned only to users |
| RESOURCE_LIMIT controls password policies too | It only controls resource limits; password limits are always enforced |
| Setting IDLE_TIME kills long-running queries | Running queries are not counted as idle between calls |
| CONNECT_TIME is the same as IDLE_TIME | CONNECT_TIME counts total session time; IDLE_TIME counts time without calls |
| CPU_PER_CALL is a wall-clock timeout | It measures CPU time for a call, not elapsed time |
| LOGICAL_READS is the number of rows returned | It is the number of data blocks read |
| PRIVATE_SGA applies equally to Dedicated Server | This limit only matters for Shared Server |
| A finite PASSWORD_REUSE_TIME is enough | Must be paired with PASSWORD_REUSE_MAX |
| One UNLIMITED reuse parameter always allows reuse | One UNLIMITED combined with one finite prohibits reuse |
| Both reuse parameters UNLIMITED means no reuse | Oracle ignores both; passwords can be reused |
| Lower PASSWORD_LIFE_TIME is always safer | Too low can create burden and weak password habits |
| Password rollover is for admin accounts | Designed for application service accounts; admin users are restricted |
| ALTER PROFILE modifies current sessions | Only new sessions receive profile changes |
| Profiles replace Database Resource Manager | Resource Manager is more flexible for workload governance |
| DEFAULT is the same as UNLIMITED | DEFAULT inherits the value from the DEFAULT profile |

## 25. Profile design checklist

**Accounts and scope**

- Does the user belong to application, analyst, batch, or admin?
- Is a dedicated profile needed?
- Is the user in the CDB root or a PDB?
- Is the profile common or local?
- How many application nodes and connection pools exist?

**Password policy**

- What is the maximum failed login attempts limit?
- Does lock time match support procedures?
- Do password lifetime and grace period fit the account type?
- Are reuse time and reuse max configured together?
- Does the password verify function exist and work properly?
- Is the inactive account policy appropriate?
- Does the service account need gradual rollover?

**Resource limits**

- Is RESOURCE_LIMIT set to TRUE?
- Is SESSIONS_PER_USER sufficient for total pool capacity?
- Are CPU_PER_CALL and CPU_PER_SESSION based on measured workloads?
- Do logical read limits match actual queries?
- Does IDLE_TIME conflict with the connection pool?
- Does CONNECT_TIME cut off long sessions unexpectedly?
- Is Database Resource Manager needed instead of hard limits?

**Deployment**

- Has the current profile been documented?
- Has it been tested in staging/lab?
- Has it been tested with a new session?
- Are rollback profile values prepared?
- Are alerts configured for account lock/password expiry?
- Is post-deployment monitoring in place?

## 26. Comprehensive lab exercise

This lab creates a dedicated profile for an application account, assigns the profile, inspects the dictionary, and tests password/resource parameters. Use a lab schema and an account without administrative privileges.

### Step 1 — Create the profile

~~~sql
CREATE PROFILE profile_lab LIMIT
    SESSIONS_PER_USER 3
    CPU_PER_CALL 3000
    CONNECT_TIME 120
    IDLE_TIME 10
    LOGICAL_READS_PER_CALL 100000
    FAILED_LOGIN_ATTEMPTS 4
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_TIME 180
    PASSWORD_REUSE_MAX 5;
~~~

### Step 2 — Assign to the lab user

~~~sql
ALTER USER lab_user PROFILE profile_lab;
~~~

If LAB_USER does not exist yet, the DBA creates the user in the lab schema with secure password provisioning and then assigns the profile.

### Step 3 — Check the profile

~~~sql
SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
WHERE profile = 'PROFILE_LAB'
ORDER BY resource_type, resource_name;
~~~

### Step 4 — Check user assignment

~~~sql
SELECT username, profile, account_status
FROM dba_users
WHERE username = 'LAB_USER';
~~~

### Step 5 — Check RESOURCE_LIMIT

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
~~~

Only enable with ALTER SYSTEM when authorized and approved:

~~~sql
ALTER SYSTEM SET resource_limit = TRUE;
~~~

### Step 6 — Check password status

~~~sql
SELECT
    username,
    account_status,
    lock_date,
    expiry_date,
    profile
FROM dba_users
WHERE username = 'LAB_USER';
~~~

### Step 7 — Check sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    profile,
    last_call_et
FROM v$session
WHERE username = 'LAB_USER';
~~~

### Step 8 — Test ALTER PROFILE

~~~sql
ALTER PROFILE profile_lab LIMIT
    IDLE_TIME 15
    SESSIONS_PER_USER 4;
~~~

Open a new session as LAB_USER to verify the new profile. Sessions opened prior to the change do not automatically pick up the new values.

### Step 9 — Clean up the lab (optional)

~~~sql
ALTER USER lab_user PROFILE DEFAULT;
DROP PROFILE profile_lab;
~~~

If the profile is still assigned to other users, resolve assignments first or use CASCADE per the change process. Only drop lab objects.

## 27. Self-check questions

1. What is a profile in Oracle?
2. How does a profile differ from a role in purpose?
3. How many profiles can be assigned to a user at one time?
4. How do password parameters differ from resource parameters?
5. What does RESOURCE_LIMIT control?
6. Are password parameters disabled by RESOURCE_LIMIT?
7. How does DEFAULT differ from UNLIMITED?
8. How do FAILED_LOGIN_ATTEMPTS and PASSWORD_LOCK_TIME work together?
9. How do PASSWORD_LIFE_TIME and PASSWORD_GRACE_TIME differ?
10. When do ORA-28002 and ORA-28001 occur?
11. How must PASSWORD_REUSE_TIME and PASSWORD_REUSE_MAX be configured?
12. What happens if one reuse parameter is UNLIMITED and the other is finite?
13. What happens if both reuse parameters are UNLIMITED?
14. What is PASSWORD_VERIFY_FUNCTION used for?
15. Which schema must the password verification function reside in?
16. What duration does INACTIVE_ACCOUNT_TIME measure?
17. What problem does PASSWORD_ROLLOVER_TIME solve?
18. During the rollover period, which passwords can log in?
19. Is PASSWORD_ROLLOVER_TIME used for administrative users?
20. What does SESSIONS_PER_USER limit?
21. How does CPU_PER_SESSION differ from CPU_PER_CALL?
22. What does LOGICAL_READS_PER_CALL measure?
23. Does IDLE_TIME kill long-running queries?
24. How does CONNECT_TIME differ from IDLE_TIME?
25. Which architecture does PRIVATE_SGA matter for?
26. Which resources are used to compute COMPOSITE_LIMIT?
27. How does exceeding a call-level limit differ from exceeding a session-level limit?
28. Do profile changes apply to already open sessions?
29. Why must profiles be coordinated with connection pools?
30. When should Database Resource Manager be used?

**Suggested answers:**

1. A set of password/resource limits assigned to a database user.
2. Roles group privileges; profiles group password/resource policies.
3. One.
4. Password parameters are always enforced; resource limits require RESOURCE_LIMIT TRUE.
5. Enables/disables enforcement of resource limits in profiles.
6. No; password management always operates.
7. DEFAULT inherits from the DEFAULT profile; UNLIMITED sets no limit.
8. After consecutive failed login attempts, the account is locked for PASSWORD_LOCK_TIME.
9. LIFE_TIME is the password lifetime; GRACE_TIME is the warning/change window before full expiration.
10. ORA-28002 is the upcoming expiration warning; ORA-28001 means already expired.
11. Both need appropriate values to require both wait time and change count simultaneously.
12. The old password can never be reused.
13. Oracle ignores both limits and passwords can be reused.
14. Checking password complexity/quality.
15. SYS.
16. Consecutive days without a successful login.
17. Allows applications to transition gradually from an old password to a new password.
18. Both old and new passwords during the rollover window.
19. No; it is designed for application service accounts.
20. The number of concurrent sessions for a user.
21. One measures total CPU in a session; the other measures CPU for a single call.
22. The number of data blocks read in a single call.
23. No; long-running queries are not counted as idle between calls.
24. CONNECT_TIME measures total session time; IDLE_TIME measures time without calls.
25. Shared Server.
26. CPU_PER_SESSION, CONNECT_TIME, LOGICAL_READS_PER_SESSION, and PRIVATE_SGA according to weights.
27. Call-level rolls back the statement and keeps the session; session-level limits may prevent the session from continuing work.
28. No; new sessions receive the changes.
29. The database can terminate idle/old sessions, causing the pool to hold stale connections or run out of connections.
30. When flexible priority allocation and workload management beyond profile hard limits are needed.

## Oracle reference documentation

- [Oracle Database 19c SQL Language Reference — CREATE PROFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-PROFILE.html): syntax and semantics of password/resource parameters.
- [Oracle Database 19c SQL Language Reference — ALTER PROFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PROFILE.html): modifying profiles and scope of application.
- [Oracle Database 19c SQL Language Reference — ALTER RESOURCE COST](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-RESOURCE-COST.html): weights for COMPOSITE_LIMIT.
- [Oracle Database 19c Database Security Guide — Configuring User Resource Limits](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-user-resource-limits.html): profile resource limits, RESOURCE_LIMIT, and enforcement.
- [Oracle Database 19c Database Security Guide — Using a Password Management Policy](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/using-password-management-policy.html): password lifetime, lock, reuse, verify function, and inactive accounts.
- [Oracle Database 19c Database Security Guide — Managing Gradual Database Password Rollover for Applications](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-gradual-database-password-rollover-applications.html): password rollover for service accounts.
- [Oracle Database 19c Database Reference — RESOURCE_LIMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/RESOURCE_LIMIT.html): parameter to enable/disable resource enforcement.
- [Oracle Database 19c Database Reference — DBA_PROFILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_PROFILES.html): current profile parameters.
- [Oracle Database 19c Database Reference — DBA_USERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_USERS.html): profile assignment, account status, and password expiry.
- [Oracle Database 19c Administrator's Guide — Managing Resources with Oracle Database Resource Manager](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-resources-with-oracle-database-resource-manager.html): advanced workload and resource management.

**Key takeaway:** Profiles bind password policies and resource limits to database users. Password parameters are always enforced; resource parameters require RESOURCE_LIMIT = TRUE. FAILED_LOGIN_ATTEMPTS, PASSWORD_LOCK_TIME, PASSWORD_LIFE_TIME, PASSWORD_GRACE_TIME, PASSWORD_REUSE_TIME, PASSWORD_REUSE_MAX, and PASSWORD_VERIFY_FUNCTION form the password lifecycle. SESSIONS_PER_USER, CPU, logical reads, CONNECT_TIME, and IDLE_TIME limit resource usage by session/call. PASSWORD_ROLLOVER_TIME enables phased service account password changes. Measure workloads before setting thresholds, coordinate profiles with connection pools, and use Database Resource Manager when flexible workload governance is needed.
