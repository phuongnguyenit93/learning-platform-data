# SYSDBA, SYSOPER, and specialized administrative privileges in Oracle

Oracle Database provides special administrative privileges that allow certain accounts to perform operations at the instance, database, backup, Data Guard, encryption key, or Oracle ASM level. The two most common are **SYSDBA** and **SYSOPER**. They are not ordinary roles like DBA; they are administrative privileges used when connecting to the database, for example `CONNECT / AS SYSDBA` or `CONNECT backup_user@service AS SYSBACKUP`.

SYSDBA allows performing almost all database administration tasks, including startup/shutdown, mount/open, recovery, and privileged access to the data dictionary. SYSOPER has a narrower scope, focusing on instance operational tasks such as startup/shutdown, mount/open database, and limited administrative operations. Specialized privileges such as SYSBACKUP, SYSDG, SYSKM, SYSASM, and SYSRAC support separation of duties: a backup operator does not necessarily need full SYSDBA privileges, a Data Guard administrator does not need access to all application data, and an ASM administrator does not need database administrator privileges.

Separating privileges limits blast radius if an account is compromised, restricts out-of-scope operations, and creates a clear audit trail. Granting privileges must go hand in hand with appropriate authentication: OS authentication for local connections, password file authentication for remote administrative connections, control of OS group memberships, and auditing of privileged sessions.

This lesson belongs to the **Security** topic of *Database Engine Relational Oracle*. It focuses on:

- How administrative privileges differ from ordinary roles and system privileges.
- Scope and use cases of SYSDBA and SYSOPER.
- SYSBACKUP, SYSDG, SYSKM, SYSASM, and SYSRAC.
- OS authentication, password files, and the REMOTE_LOGIN_PASSWORDFILE parameter.
- Granting/revoking privileges, checking V$PWFILE_USERS, and account management.
- SQL*Plus/SQLcl connections and startup/shutdown operations.
- Least privilege, separation of duties, auditing, and safe operations.
- Common errors and hands-on lab exercises to verify privileges in a lab environment.

## 1. What is an administrative privilege?

An administrative privilege is a special privilege that allows connecting and performing database/instance administrative operations beyond the scope of ordinary SQL privileges. Oracle supports privileges such as:

| Privilege | Primary purpose |
| --- | --- |
| SYSDBA | Comprehensive database administration, including startup/shutdown, mount/open, recovery, and privileged operations. |
| SYSOPER | Instance/database operations with a limited set of tasks. |
| SYSBACKUP | Database backup and recovery within a specialized scope. |
| SYSDG | Oracle Data Guard administration. |
| SYSKM | Encryption key/keystore management, especially for Transparent Data Encryption. |
| SYSASM | Oracle ASM instance and disk group administration. |
| SYSRAC | Performing specialized administrative operations for Oracle RAC. |

Exact names and specific capabilities of some privileges may vary by Oracle release, architecture, and tools. Always consult the documentation for the running version before granting or using them in production.

### Do not confuse administrative privileges with the DBA role

`DBA` is a database role containing many system privileges and standard administrative privileges. This role is not equivalent to SYSDBA:

- A user with the DBA role does not automatically have permission to connect `AS SYSDBA`.
- The DBA role does not substitute for startup/shutdown or recovery operations that require an administrative privilege.
- SYSDBA has special connection and execution semantics; it is not just a collection of ordinary grants.
- SYSDBA/SYSOPER and specialized administrative privileges are managed via administrative authentication/password files or OS authentication, and should not be checked only in DBA_SYS_PRIVS like ordinary system privileges.

### SYS is a schema, SYSDBA is a privilege

`SYS` is the special administrative schema/user that owns the data dictionary and core objects. `SYSDBA` is the administrative privilege that allows connecting with the corresponding administrative rights. The two concepts are related but not synonymous.

When connecting `AS SYSDBA`, Oracle executes the administrative session with the SYS identity under SYSDBA semantics. Therefore, DDL/DML statements run in this session can directly affect the dictionary and system objects. Do not use SYSDBA to run applications or manipulate day-to-day business data.

## 2. SYSDBA: comprehensive database administration privilege

SYSDBA is the highest privilege in the administrative privilege group for a database instance. An account with SYSDBA can perform broad administrative operations, such as:

- STARTUP and SHUTDOWN of the instance.
- MOUNT, OPEN, CLOSE of the database.
- Performing media recovery and restore/recovery operations.
- Creating, modifying, or managing database components at the administrative level.
- Accessing dictionary objects with special privileges.
- Managing users and granting administrative privileges.
- Performing maintenance operations requiring SYSDBA privileges.

SYSDBA has very broad power; a mistake or wrong statement in this session can affect the entire database. Grant it only to DBAs/operations personnel who genuinely need it and follow change control procedures.

### Local connection via OS authentication

On the database server host, an OS user belonging to the OS group mapped to OSDBA can connect without entering a database username/password:

~~~sql
sqlplus / as sysdba
~~~

Or inside an open SQL*Plus session:

~~~sql
CONNECT / AS SYSDBA
~~~

This capability relies on the OS identity of the client process and group membership on the host. A user can connect as SYSDBA without a password file password if OS authentication is configured for that host.

### Remote connection via password file authentication

Administrative connections over Oracle Net generally require password file authentication:

~~~sql
sqlplus admin_dba@prod_service as sysdba
~~~

SQL*Plus prompts for the password if not supplied via a secure mechanism. Avoid putting passwords directly on the command line, in plain-text scripts, shell history, or logs.

The account must have been granted SYSDBA, and the password file/remote authentication must be properly configured. Remote SYSDBA connections require protecting the network, listener, password file, and secrets as top-tier credentials.

### Verifying an administrative session

~~~sql
SHOW USER;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_USER') AS current_user,
       sys_context('USERENV', 'ISDBA') AS isdba
FROM dual;
~~~

`ISDBA` can help verify that the session is using SYSDBA privilege depending on the version. Do not rely on a single variable for auditing; combine with the audit trail and connection metadata.

## 3. SYSOPER: limited operational privilege

SYSOPER is intended for instance/database operational duties without needing full SYSDBA privileges. This privilege permits operations such as:

- STARTUP and SHUTDOWN.
- MOUNT database and OPEN database.
- ALTER DATABASE within permitted operational scopes, such as certain backup/archive operations.
- Enabling restricted session within supported privilege bounds.

SYSOPER does not allow an operator to freely read/modify application data or perform every administrative task like SYSDBA. Exact permitted operations should be verified against the privilege table for the Oracle release in use.

### Connecting with SYSOPER

~~~sql
sqlplus ops_user@prod_service as sysoper
~~~

Or locally if the corresponding OS group is configured:

~~~sql
sqlplus / as sysoper
~~~

### Example operational commands

~~~sql
SHUTDOWN IMMEDIATE;
~~~

~~~sql
STARTUP MOUNT;
~~~

~~~sql
ALTER DATABASE OPEN;
~~~

These commands only run when the database/instance is in an appropriate state. SYSOPER can perform certain operational tasks but does not replace a DBA for complex recovery, structural changes, or privileged data access.

### SYSOPER is not an application data read privilege

An account with SYSOPER should not additionally be granted read access to business tables merely to monitor applications. Use a monitoring account with minimal SELECT privileges on required views. Instance operation and business data querying are two separate duties.

## 4. Comparing SYSDBA and SYSOPER

| Criterion | SYSDBA | SYSOPER |
| --- | --- | --- |
| Privilege level | Comprehensive, highest privilege for database administration | Limited to specific operational tasks |
| Startup/shutdown | Yes | Yes |
| Mount/open database | Yes | Yes, within permitted scope |
| Recovery | Authorized to perform administrative recovery operations | Does not have all SYSDBA recovery capabilities |
| Dictionary/data access | Broad special privileges | Not granted arbitrary data read/write access |
| User/privilege administration | Yes | Not the purpose of SYSOPER |
| Best suited for | DBAs, database recovery, configuration, and overall administration | Operators performing startup/shutdown and limited operational tasks |
| Risk if credential compromised | Very high | Lower than SYSDBA, yet can still cause database disruption |

### Choosing SYSOPER or SYSDBA?

If a task only requires starting/stopping the instance, mounting/opening the database, or limited operational actions, evaluate SYSOPER first. If it requires recovery, database configuration changes, user/privilege management, or full administration, an authorized DBA uses SYSDBA.

Do not grant SYSDBA just because a legacy script asks for it. Identify the exact statements that need to run and choose the smallest administrative privilege that satisfies the requirement.

## 5. SYSBACKUP: separating backup and recovery duties

SYSBACKUP was introduced so backup/recovery operators can perform their work with RMAN and related APIs without needing full SYSDBA privileges. This is part of the separation of duties model.

### Use cases

- Connecting with RMAN to perform database backups.
- Performing restore/recovery operations within the privilege scope.
- Managing certain backup/recovery tasks without granting full administrative privileges.

### Granting the privilege

~~~sql
GRANT SYSBACKUP TO backup_operator;
~~~

Connecting:

~~~sql
CONNECT backup_operator@prod_service AS SYSBACKUP
~~~

RMAN can use the corresponding administrative connection:

~~~text
rman target backup_operator@prod_service
~~~

When tools require an administrative privilege, use the authentication mechanism and syntax supported in your environment. Do not put passwords in scripts or on the command line.

### SYSBACKUP does not replace backup procedures

Having SYSBACKUP does not by itself guarantee backups are restorable. You still need:

- Retention policies and backup schedules.
- Backups of control files, SPFILE, and archived redo logs as required for recovery.
- Verification of backup pieces and catalog/control file metadata.
- Restore/recovery testing in an isolated environment.
- Protection of access to backup storage and encryption keys.

### SYSBACKUP and SYSDBA

SYSBACKUP reduces privileges compared to SYSDBA for personnel only doing backup/recovery. If a specific task requires operations outside SYSBACKUP scope, identify and approve the additional privilege separately; do not escalate to SYSDBA by default.

## 6. SYSDG: Data Guard administration

SYSDG is a specialized administrative privilege for Oracle Data Guard operations. It enables operators to manage primary/standby environments, the broker, and related operations without needing full SYSDBA.

### Use cases

- Performing Data Guard administrative operations via SQL*Plus or corresponding tools.
- Managing certain primary/standby database states.
- Performing Data Guard Broker tasks within supported privileges.

### Granting and connecting

~~~sql
GRANT SYSDG TO dataguard_operator;
~~~

~~~sql
CONNECT dataguard_operator@prod_service AS SYSDG
~~~

### Notes

SYSDG is not a full database administration privilege. It does not replace SYSDBA for all database activities, nor does it replace OS/Clusterware administrative accounts. Operators must follow switchover/failover procedures, check apply lag, transport lag, role transitions, and ensure a rollback plan exists.

## 7. SYSKM: encryption key and keystore management

SYSKM is an administrative privilege for key/keystore management operations, especially related to Transparent Data Encryption (TDE). Separating this privilege enables key managers to perform their duties without necessarily holding full DBA rights over data.

### Use cases

- Managing the TDE keystore/wallet.
- Performing Oracle-supported key management operations.
- Supporting open/close keystore, backup, or master encryption key rotation workflows per version/configuration.

### Granting and connecting

~~~sql
GRANT SYSKM TO key_operator;
~~~

~~~sql
CONNECT key_operator@prod_service AS SYSKM
~~~

### Protecting SYSKM

SYSKM credentials and the keystore password can determine the ability to decrypt data. Do not store them in the same secret store or with the same group that has access to backups if the separation of duties model requires independence. Keystore backup and restore/recovery testing are mandatory parts of TDE procedures.

SYSKM does not mean the operator can read all plaintext data. Key management privileges and table/data access privileges are two separate layers; follow the privilege model of your Oracle release.

## 8. SYSASM: Oracle ASM administration

SYSASM is the administrative privilege for Oracle Automatic Storage Management (ASM). ASM manages disk groups and storage used by databases. SYSASM is used to connect to the ASM instance and perform storage administration tasks.

### Use cases

- Creating, mounting, dismounting, or dropping ASM disk groups.
- Managing ASM disks, failure groups, and disk group attributes.
- Monitoring and operating the ASM instance.
- Performing administrative storage operations within supported privileges.

### Connecting to ASM

~~~sql
sqlplus / as sysasm
~~~

Or using a password file account granted SYSASM per configuration:

~~~sql
CONNECT asm_operator@asm_service AS SYSASM
~~~

### SYSASM differs from SYSDBA

SYSASM administers the ASM instance and storage; SYSDBA administers the database instance. The two scopes are related but not identical. In a separated architecture, do not grant SYSASM to application DBAs if they do not need to manage ASM; do not use SYSDBA to bypass dedicated ASM administration procedures.

### OS groups for ASM

On Unix/Linux, installations may use groups such as OSASM (often named asmadmin), OSDBA, and OSOPER. Actual group names depend on installation configuration and Oracle Grid Infrastructure. Do not assume group names; verify against host configuration and installation documentation.

## 9. SYSRAC: specialized administrative privilege for RAC

SYSRAC is an administrative privilege serving certain Oracle Real Application Clusters administrative tasks and related utilities/agents. It supports privilege separation for RAC operations without needing to grant full SYSDBA.

### Use cases

- Oracle-supported RAC administrative tasks with SYSRAC.
- Operations of Clusterware/agents or management tools requiring specialized privileges.
- Certain operations involving RAC instances/nodes/services depending on the version.

### Granting and connecting

~~~sql
GRANT SYSRAC TO rac_operator;
~~~

~~~sql
CONNECT rac_operator@prod_service AS SYSRAC
~~~

The exact scope of SYSRAC depends on the Oracle release and tools used. It is not a replacement for SYSDBA for database administration, nor does it automatically grant OS privileges to manage Grid Infrastructure. Clusterware/ASM still have separate OS privilege layers and accounts.

## 10. Comparison table of specialized administrative privileges

| Privilege | Scope | Recommended role/team |
| --- | --- | --- |
| SYSDBA | Comprehensive database/instance | Senior DBA, recovery, and overall administration |
| SYSOPER | Limited database operations | Operator for startup/shutdown, mount/open |
| SYSBACKUP | Backup/recovery | Backup operator, RMAN |
| SYSDG | Data Guard | Data Guard operator |
| SYSKM | Encryption key/keystore | Key management officer |
| SYSASM | ASM storage/instance | ASM administrator |
| SYSRAC | RAC-specific operations | RAC/Clusterware operations per supported privileges |

### Separation of duties

A separation model may include:

- DBAs administering the database and holding SYSDBA when needed.
- Operators performing startup/shutdown using SYSOPER.
- Backup team using SYSBACKUP.
- Data Guard team using SYSDG.
- Key management team using SYSKM.
- Storage/ASM team using SYSASM.
- RAC operations using SYSRAC along with required OS/Clusterware privileges.

The exact model depends on scale, architecture, and organizational policy. One person may hold multiple roles in smaller environments, but each privilege must be granted purposefully and audited.

## 11. OS authentication and OS groups

Oracle supports operating system authentication for administrative connections on the database host. An OS user belonging to the appropriate administrative group can connect using slash syntax without entering a database username/password:

~~~sql
sqlplus / as sysdba
sqlplus / as sysoper
sqlplus / as sysasm
~~~

The Oracle installer/configuration maps OS groups to administrative privileges. On Unix/Linux, common names include:

| OS group category | Typical corresponding privilege |
| --- | --- |
| OSDBA (often named dba) | SYSDBA |
| OSOPER (often named oper) | SYSOPER |
| OSBACKUPDBA (often named backupdba) | SYSBACKUP |
| OSDGDBA (often named dgdba) | SYSDG |
| OSKMDBA (often named kmdba) | SYSKM |
| OSRACDBA (often named racdba) | SYSRAC |
| OSASM (often named asmadmin) | SYSASM |

Actual group names depend on the installation owner, Oracle Grid Infrastructure, Oracle Home, and platform. On Windows, Oracle uses local groups named along the lines of ORA_DBA, ORA_OPER, and corresponding groups per home/role. Do not mechanically apply the Linux naming table to Windows.

### Why are OS groups so sensitive?

Members of OSDBA can usually obtain local SYSDBA privileges. If a regular OS account is mistakenly added to this group, that user can administer the database without knowing any database password. Therefore:

- Restrict membership in OSDBA/OSOPER and specialized groups.
- Do not add application users, developers, or CI/CD accounts to OSDBA just to run one command.
- Review group membership periodically and whenever personnel changes occur.
- Protect host access, sudo, SSH, and the Oracle software owner account.
- Separate operator accounts from accounts running applications.

### Checking OS groups

On Linux/Unix, DBAs/administrators can check group membership using OS tools such as id or getent. On Windows, check Local Users and Groups or domain administration tools. These checks occur outside SQL and must comply with host administrative rights.

### OS authentication is not password file authentication

OS authentication authenticates via user/group on the database host. Password file authentication authenticates database accounts granted administrative privileges via a password file, typically used for remote connections. Both mechanisms can coexist, but each must be configured and protected separately.

## 12. Password file authentication

A password file is a special file Oracle uses to authenticate accounts granted administrative privileges when making administrative connections over Oracle Net. It allows a database account to authenticate to connect AS SYSDBA, SYSOPER, or specialized privileges depending on the version.

### When is a password file needed?

- A DBA connects from a remote administrative workstation via service/listener.
- RMAN or management tools connect to the database from another host.
- RAC instances need to use a shared password file per configuration.
- Separate administrative accounts need to be managed rather than relying on OS accounts on the database host.

### REMOTE_LOGIN_PASSWORDFILE

The initialization parameter REMOTE_LOGIN_PASSWORDFILE controls password file usage. Common values:

| Value | General meaning |
| --- | --- |
| NONE | Password file authentication is not used for administrative connections. |
| EXCLUSIVE | Password file dedicated to one database; supports managing granted administrative users. |
| SHARED | Password file can be shared subject to Oracle restrictions; user/admin privilege management capabilities are more restricted than EXCLUSIVE. |

Checking:

~~~sql
SHOW PARAMETER remote_login_passwordfile;

SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name = 'remote_login_passwordfile';
~~~

Default values and modifiability depend on release/platform. Some configurations require an instance restart for changes to take effect; consult version documentation before modifying.

### Creating a password file

Oracle provides the orapwd utility to create a password file. Syntax depends on version and deployment method (filesystem or ASM):

~~~text
orapwd file=orapwORCL password=<secure-password> entries=20
~~~

This is illustrative syntax; do not place real passwords in shell history or logs. With Oracle RAC/ASM and newer releases, the password file may be managed inside ASM and shared by multiple instances. Use Oracle-supported tools/configurations for production environments rather than manually copying files while the cluster is running.

### Protecting the password file

- Restrict OS read/write permissions on the file.
- Do not place the file in source control or application images.
- Use secret management and rotation per policy.
- Monitor changes to administrative privileges and the password file.
- Synchronize the file using supported procedures in RAC/Data Guard.
- Do not share SYSDBA credentials among multiple people when individual accounts can be provisioned.

### Password file and granted users

When SYSDBA/SYSOPER or a specialized privilege is granted to a database user, Oracle records the corresponding administrative entry in the password file when configuration allows. V$PWFILE_USERS is the key view to inspect users granted administrative privileges.

## 13. Granting and revoking administrative privileges

Administrative privileges are granted to database users with GRANT and revoked with REVOKE. These operations require the executor to hold appropriate administrative privileges, typically a SYSDBA connection.

### Creating a dedicated administrative user

~~~sql
CREATE USER ops_user IDENTIFIED BY "<secret-managed-password>";
GRANT SYSOPER TO ops_user;
~~~

Depending on the release and authentication setup, granting an administrative privilege may require the user to exist and the password file to be in the appropriate mode. Do not also grant the DBA role if the duty only requires SYSOPER.

### Granting SYSDBA

~~~sql
GRANT SYSDBA TO dba_operator;
~~~

### Granting specialized privileges

~~~sql
GRANT SYSBACKUP TO backup_operator;
GRANT SYSDG TO dataguard_operator;
GRANT SYSKM TO key_operator;
GRANT SYSRAC TO rac_operator;
~~~

SYSASM is usually managed in the context of the ASM instance and ASM's password file/OS group configuration. Grant privileges to the right user on the right instance; do not run commands on the database instance just because the syntax looks similar.

### Revoking privileges

~~~sql
REVOKE SYSDBA FROM dba_operator;
REVOKE SYSOPER FROM ops_user;
REVOKE SYSBACKUP FROM backup_operator;
REVOKE SYSDG FROM dataguard_operator;
REVOKE SYSKM FROM key_operator;
REVOKE SYSRAC FROM rac_operator;
~~~

After revoking, re-check V$PWFILE_USERS and confirm the user no longer holds the administrative privilege. If credentials were compromised, in addition to revoking, rotate passwords, review OS groups, active sessions, and audit records.

### Do not use the SYS account as a personal account

SYS is a system account used for privileged work. Do not change/share the SYS password across multiple DBAs when the model allows dedicated administrative accounts. Individual accounts help audits identify who performed an action and allow revoking one person without affecting others.

## 14. Checking administrative privileges in the database

V$PWFILE_USERS is the primary view to inspect users granted administrative privileges via the password file. Querying this view may require catalog privileges or appropriate SELECT privileges.

~~~sql
SELECT *
FROM v$pwfile_users
ORDER BY username;
~~~

Common columns include USERNAME, SYSDBA, SYSOPER, SYSASM, SYSBACKUP, SYSDG, SYSKM, and CON_ID. Specific columns depend on the Oracle release; use DESC V$PWFILE_USERS before writing fixed monitoring queries.

Example checking common privileges if the version includes these columns:

~~~sql
SELECT username,
       sysdba,
       sysoper,
       sysasm,
       sysbackup,
       sysdg,
       syskm
FROM v$pwfile_users
ORDER BY username;
~~~

### Comparing with DBA_SYS_PRIVS

~~~sql
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE grantee IN ('OPS_USER', 'DBA_OPERATOR');
~~~

DBA_SYS_PRIVS lists ordinary system privileges. Do not rely solely on this view to check SYSDBA/SYSOPER; administrative privileges are managed via the password file/OS authentication mechanism and reflected in V$PWFILE_USERS.

### Viewing the DBA role

~~~sql
SELECT grantee, granted_role, admin_option
FROM dba_role_privs
WHERE granted_role = 'DBA'
ORDER BY grantee;
~~~

This query helps distinguish users holding the DBA role from users holding administrative privileges. The two lists may not overlap.

### Viewing password file configuration

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'remote_login_passwordfile';
~~~

### Checking the container

In a multitenant environment:

~~~sql
SHOW CON_NAME;

SELECT sys_context('USERENV', 'CON_NAME') AS container_name,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'ISDBA') AS isdba
FROM dual;
~~~

Administrative privileges, common/local users, and connection services may have different container scopes. When operating in a CDB/PDB, verify that you are in the right container/service and that privileges are granted at the right scope. Do not assume a grant in root automatically means all local users in PDBs have the same privileges.

## 15. Auditing administrative connections and SYS operations

SYSDBA/SYSOPER sessions and administrative connections must be audited because they can alter database state or access sensitive data.

### AUDIT_SYS_OPERATIONS

The AUDIT_SYS_OPERATIONS parameter controls auditing of operations by users with administrative privileges such as SYSDBA/SYSOPER under your Oracle release's audit mechanism. Check:

~~~sql
SHOW PARAMETER audit_sys_operations;

SELECT name, value
FROM v$parameter
WHERE name = 'audit_sys_operations';
~~~

In many configurations, audit records for privileged operations are written to the OS audit destination. Exact location and storage depend on platform, AUDIT_TRAIL, unified auditing, and database configuration. Check release documentation and organizational audit policy.

### Unified Auditing

Oracle versions supporting Unified Auditing provide audit policies and a unified audit trail. DBAs must determine which policies record administrative actions, login/logout, privilege usage, and privilege changes. Audit policy syntax and SYS operations behavior may depend on release/mode.

You can query the trail when authorized:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies
FROM unified_audit_trail
ORDER BY event_timestamp DESC;
~~~

The view and columns may vary by release; use DESC UNIFIED_AUDIT_TRAIL. Restrict read access on the audit trail to authorized audit teams.

### Auditing privilege changes

Monitor:

- GRANT/REVOKE of SYSDBA, SYSOPER, and specialized privileges.
- Changes to the password file or remote login configuration.
- Changes to OS group memberships.
- Remote administrative logins and logins from unfamiliar hosts.
- Startup/shutdown, mount/open, recovery, role transitions, and ASM operations.
- Changes to audit policies, keystores, or backup destinations.

In-database auditing does not fully capture OS group membership changes. Integrate OS logs, IAM, PAM, or corresponding access management systems.

### Audits must be protected

An account with SYSDBA can modify many database components; therefore, the audit trail must be forwarded/stored where the same operator cannot arbitrarily alter or delete it. Use separated duties for audit review and log retention.

## 16. Safe operational procedures

Before a privileged operation:

1. Identify the exact task: startup/shutdown, backup, Data Guard, key management, ASM, or RAC.
2. Choose the smallest appropriate administrative privilege.
3. Use an individual account or dedicated operational account, not shared SYS.
4. Authenticate via OS group or managed password file.
5. Verify the target database, service, instance, and container.
6. Check current status and command impact.
7. Execute within an approved change window/procedure if in production.
8. Log the command, timestamp, operator, SQLCODE, and outcome.
9. Verify the database/service returns to the expected state.
10. Close the session and revoke temporary privileges if granted for a short-term task.

### Separating accounts by duty

A backup user does not need the DBA role; an operator does not need read access to application tables; a key manager does not need to modify business data. If multiple duties are needed, grant multiple privileges intentionally and audit the use of each privilege.

### Credential management

- Do not store passwords in plain-text scripts.
- Use a wallet/secure external password store or secret manager per organizational standards.
- Do not send passwords via chat, tickets, or command line arguments.
- Rotate the password file following supported procedures and verify all dependent clients/instances.
- Protect password files and wallets at the OS/ASM level.
- Use TLS/network controls for remote administrative connections.
- Limit listener exposure and allow only necessary administrative hosts.

### Temporary privileges

If an engineer needs SYSDBA during a deployment, grant it with a time limit/procedure, record the approver, and revoke upon completion. Removal must be confirmed in V$PWFILE_USERS and IAM/OS group systems.

## 17. Common operational commands

The following examples illustrate syntax. Execute startup/shutdown or mount/open commands only on instances approved for maintenance, with a change plan and verified application dependencies.

### Shutdown

~~~sql
SHUTDOWN IMMEDIATE;
~~~

IMMEDIATE blocks new logins, terminates current sessions per Oracle procedures, rolls back uncommitted transactions, and closes the database/instance. This is a service-disrupting operation; do not run it in a lab on a shared database.

### Startup in NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

NOMOUNT starts the instance and reads initialization parameters, without mounting the control file or opening datafiles.

### Mount database

~~~sql
ALTER DATABASE MOUNT;
~~~

MOUNT opens the control file and associates the database with the instance; datafiles are not yet open for normal operations.

### Open database

~~~sql
ALTER DATABASE OPEN;
~~~

OPEN brings the database into normal operational state according to its current role/mode. In some recovery scenarios, recovery steps are required before opening.

### Restricted session

Restricted session limits logins to users with appropriate privileges. Exact syntax and required privileges depend on database state and version:

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Do not treat restricted session as a substitute for firewalls, account locking, or maintenance windows. Already connected sessions may persist; explicitly identify which sessions are allowed to remain active.

### RMAN with SYSBACKUP

Example connecting to target with an account granted SYSBACKUP:

~~~text
rman target backup_operator@prod_service
~~~

RMAN may prompt for a password or use Oracle Secure External Password Store. Use the right privilege and authentication setup for your version. Do not use SYSDBA if the backup task can be completed with SYSBACKUP.

### Data Guard and ASM

Tools such as DGMGRL and SQL*Plus can use the corresponding administrative privileges for Data Guard/ASM operations. Exact syntax depends on the tool and release. Do not execute ASM commands against a database service or vice versa; verify the service/instance before acting.

## 18. CDB/PDB and privilege scope

In a multitenant architecture, distinguish between CDB root, application root, and PDBs. Administrative connections can be established to a CDB or PDB service; users and privileges can have common or local scope.

### Verifying container before acting

~~~sql
SHOW CON_NAME;

SELECT name, cdb
FROM v$database;

SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM dual;
~~~

### Common users and local users

- Common users are defined in root and can exist across containers according to common user rules.
- Local users exist only within a single PDB.
- Administrative privileges have specific grant/container scope rules; CONTAINER=CURRENT/ALL syntax and permitted targets depend on the release.
- Connecting to a different service can place a session in a different container even with the same username.

Do not copy GRANT SYSDBA/SYSBACKUP statements from CDB root to a PDB without checking Oracle documentation for the exact release. Verify the user type, current container, password file, and service the tool will use.

### PDB lifecycle differs from instance lifecycle

STARTUP/SHUTDOWN control the instance/container database, whereas opening/closing a PDB uses ALTER PLUGGABLE DATABASE:

~~~sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
~~~

PDB operations require appropriate privileges and CDB state. Do not confuse instance administration privileges with PDB administration privileges or user management privileges within a PDB.

## 19. Common errors when connecting administratively

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-01017 invalid username/password | Wrong credentials, user not properly added to password file, or authenticating against wrong service | Check account, password file, privilege, and target service. |
| ORA-01031 insufficient privileges | Missing administrative privilege, wrong OS group, or insufficient privileges in stored/tool context | Verify AS privilege, OS group, V$PWFILE_USERS, and effective privileges. |
| ORA-28009 connection as SYS should be as SYSDBA or SYSOPER | Connecting as SYS without specifying an appropriate administrative privilege | Use CONNECT / AS SYSDBA or connect with an admin account using its granted privilege. |
| ORA-01994 GRANT failed: password file missing or disabled | Password file missing/disabled or REMOTE_LOGIN_PASSWORDFILE misconfigured | Check password file, parameter, and release configuration. |
| ORA-01031 when running admin command with SYSOPER | Command exceeds SYSOPER scope | Use the appropriate specialized privilege or hand off to an authorized DBA. |
| ORA-12514/ORA-12505 | Listener does not recognize requested service/SID | Check connect descriptor, service registration, and listener. |
| Local / AS SYSDBA connection denied on host | OS user not in appropriate OSDBA/OSASM group or wrong Oracle Home environment | Check OS group, ORACLE_HOME, ORACLE_SID, and authentication configuration. |
| Remote SYSDBA connection fails even though local works | Incorrect password file auth/network configuration | Check REMOTE_LOGIN_PASSWORDFILE, password file, grants, and listener/service. |
| User does not appear in V$PWFILE_USERS | Admin privilege not granted or password file out of sync | Grant the proper privilege via admin account and verify the file across instances/cluster. |
| SYSBACKUP cannot run a SYSDBA command | Task exceeds specialized backup/recovery privileges | Determine minimum required privilege; do not escalate to SYSDBA out of habit. |
| ASM connection fails | Using database service instead of ASM instance or missing OSASM/SYSASM | Connect to the proper ASM instance and verify group/password file. |
| Admin session lands in wrong PDB | Wrong service or container used | Check SHOW CON_NAME, CON_ID, and service name before acting. |

### Diagnostic checklist

1. Is the connection local or remote?
2. Is it using OS authentication or password file authentication?
3. Does the user hold the proper administrative privilege?
4. Is OS group membership correct?
5. Does REMOTE_LOGIN_PASSWORDFILE allow password file authentication?
6. Does the password file have the right path, OS permissions, and match the instance/database?
7. Does the listener/service point to the right CDB/PDB/ASM instance?
8. Is the command within the privilege scope?
9. Does the Oracle version support that privilege/syntax?
10. Does the audit trail record the denial reason or change?

## 20. Hands-on lab: creating and verifying a SYSOPER account

This lab requires a dedicated Oracle database for learning and an authorized DBA to grant privileges. Do not run shutdown/startup on a shared or production database.

### Step 1: verify configuration

Connect as SYSDBA in the lab:

~~~sql
SHOW USER;
SHOW PARAMETER remote_login_passwordfile;

SELECT name, value
FROM v$parameter
WHERE name = 'remote_login_passwordfile';
~~~

Confirm appropriate password file authentication if testing remote connections. For local OS authentication, check host group mappings.

### Step 2: create a test operator account

~~~sql
CREATE USER lab_operator IDENTIFIED BY "<password-from-secret-manager>";
GRANT SYSOPER TO lab_operator;
~~~

This is a lab account; replace the placeholder with a securely managed secret. Do not use example passwords or real passwords in stored scripts.

### Step 3: check password-file privileges

~~~sql
SELECT *
FROM v$pwfile_users
WHERE username = 'LAB_OPERATOR';
~~~

If the view does not display the user, check granted privileges, password file mode, and database configuration. Some releases have different columns; use DESC to inspect the structure.

### Step 4: connect as SYSOPER

From SQL*Plus/SQLcl:

~~~text
sqlplus lab_operator@lab_service as sysoper
~~~

Enter the password via prompt or Oracle Secure External Password Store. Confirm successful connection:

~~~sql
SELECT sys_context('USERENV', 'ISDBA') AS isdba
FROM dual;
~~~

ISDBA reflects SYSDBA status; it is not the sole check for SYSOPER. Use the connection result and V$PWFILE_USERS to verify the privilege.

### Step 5: understand the limits

In an isolated lab, test an operational task supported for SYSOPER per release documentation. Do not run SHUTDOWN/STARTUP if the instance serves other users. Try querying application data for which the user has no separate grant to observe privilege boundaries; the expected result may be missing object privileges or inability to access the schema.

### Step 6: revoke privileges

Reconnect with an authorized administrative account:

~~~sql
REVOKE SYSOPER FROM lab_operator;
DROP USER lab_operator;
~~~

Confirm the user no longer appears in V$PWFILE_USERS. Only use DROP USER after confirming this is a lab account and owns no objects that must be kept.

### Step 7: extend the lab with SYSBACKUP

In a dedicated lab environment, you can create a second account and grant SYSBACKUP:

~~~sql
CREATE USER lab_backup IDENTIFIED BY "<password-from-secret-manager>";
GRANT SYSBACKUP TO lab_backup;
~~~

Check V$PWFILE_USERS and connect using AS SYSBACKUP. Test appropriate RMAN operations on the lab database, then revoke and drop the account. Learners do not need SYSDBA to practice backup exercises.

## 21. Self-check questions

1. **What is SYSDBA?** An administrative privilege allowing database/instance administration with the broadest privilege scope.
2. **How does SYSOPER differ from SYSDBA?** SYSOPER permits only a limited set of operational tasks; SYSDBA has full database administration rights.
3. **Is SYSDBA the DBA role?** No; SYSDBA is an administrative privilege, while DBA is a database role.
4. **What is SYS?** The special schema/user that owns the data dictionary and system objects.
5. **What are the semantics of connecting AS SYSDBA?** The session connects with SYSDBA privilege and operates in the SYS context according to Oracle semantics.
6. **What is OS authentication?** Authenticating an administrative connection based on the database host's OS user/group.
7. **What is a password file used for?** Authenticating accounts with administrative privileges, especially for remote admin connections.
8. **What does REMOTE_LOGIN_PASSWORDFILE control?** Whether and how the database uses password file authentication.
9. **What is V$PWFILE_USERS used for?** Viewing users and administrative privileges recorded in the password file.
10. **Is DBA_SYS_PRIVS sufficient to check SYSDBA?** No; check V$PWFILE_USERS and OS authentication configuration.
11. **Who is SYSBACKUP suitable for?** Operators performing backup/recovery within a specialized privilege scope.
12. **What is SYSDG used for?** Oracle Data Guard operations.
13. **What is SYSKM used for?** Managing encryption keys/keystores.
14. **What is SYSASM used for?** Administering ASM instances and disk groups.
15. **What is SYSRAC used for?** Specialized Oracle RAC administrative tasks.
16. **Why not grant SYSDBA to a backup operator?** SYSBACKUP fulfills the duty with a smaller privilege scope.
17. **Why not share the SYS user?** It makes individual accountability difficult and prevents revoking access per person.
18. **Is OSDBA membership sensitive?** Yes; members can typically authenticate as SYSDBA locally.
19. **Does SYSOPER grant permission to read all application tables?** No; operational privileges do not equate to arbitrary data access.
20. **What needs to be verified in CDB/PDB?** Container/service, common/local user, and privilege scope.
21. **Why must administrative operations be audited?** Because they can alter database state, privileges, and sensitive data.
22. **If SYSOPER encounters an out-of-scope command, how should it be handled?** Identify the minimum required privilege and escalate to an appropriate operator/DBA; do not automatically grant SYSDBA.
23. **How should the password file be protected?** Restrict OS permissions, manage secrets/rotation, never put in source control, and synchronize following procedures.

SYSDBA and SYSOPER are administrative privileges, not ordinary roles. SYSDBA is for comprehensive database administration; SYSOPER is limited to operational tasks. SYSBACKUP, SYSDG, SYSKM, SYSASM, and SYSRAC separate privileges across backup, Data Guard, encryption keys, ASM, and RAC. Authenticate via protected OS groups or password files, verify privileges using V$PWFILE_USERS, audit all privileged sessions, and grant the smallest necessary privilege for each duty. In CDB/PDB or RAC environments, always confirm the right container, service, instance, and scope before running administrative commands.
