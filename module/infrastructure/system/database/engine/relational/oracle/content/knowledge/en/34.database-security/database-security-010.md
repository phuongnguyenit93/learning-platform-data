# TDE, keystores, key backups, and feature/licensing requirements

Transparent Data Encryption (TDE) is Oracle Database's mechanism for encrypting data at rest. TDE encrypts data inside datafiles so that anyone obtaining physical files, backup media, or storage devices cannot read the contents without the proper keys. Applications continue querying data with SQL as usual; the database transparently decrypts when an authorized user accesses the data.

TDE is only effective when keys are managed properly. A database can contain encrypted datafiles and still be unrecoverable if the keystore is lost, corrupted, or missing the required master key. Therefore, a TDE design must cover:

- Scope of data to encrypt.
- TDE type: column encryption or tablespace encryption.
- Keystore/wallet and storage location.
- Master encryption keys and key lifecycle.
- Opening/closing the keystore, auto-login, and password management.
- Key backup, recovery, and restore testing.
- Key synchronization across primary/standby, RAC nodes, and PDBs.
- Verification of edition, feature support, and licensing requirements.

TDE is a data-at-rest protection layer; it does not replace access control, network encryption, secret management, auditing, or backup policies.

## 1. What problem does TDE solve?

If a database stores sensitive data in plaintext on storage media, someone with direct read access to datafiles or file copies could attempt to extract data outside normal SQL access paths.

TDE encrypts data at the database storage layer:

~~~text
Application
   |
   | SQL: SELECT / INSERT / UPDATE
   v
Oracle Database
   |
   | Encryption/decryption inside the database
   v
Datafiles on disk: encrypted data
   |
   v
Storage / backup media
~~~

When an authorized session reads data, Oracle decrypts it inside the database and returns results per the session's SQL privileges. When writing, the database encrypts data before writing to storage per TDE mechanisms.

### 1.1 Risks TDE helps mitigate

- An attacker obtains a copy of datafiles without the keystore/keys.
- Storage devices or backup media are lost or stolen.
- Database files are copied without authorization at the OS/storage layer.
- Backups containing encrypted tablespace data, when handled appropriately under the corresponding mechanisms and configurations.

### 1.2 Risks TDE does not solve by itself

- Users with SELECT privileges on sensitive data can still read plaintext via SQL.
- A compromised application account can still query whatever data that account is permitted to read.
- SQL injection can still retrieve decrypted data through the database.
- TDE does not encrypt data in transit; TLS/Oracle Net encryption is still needed per policy.
- TDE does not prevent authorized users from exporting data to CSV, logs, reports, or other systems.
- TDE does not replace Data Masking, Data Redaction, VPD, auditing, or authorization.
- TDE does not protect if an attacker gains access to both the database and the required keystore.

TDE primarily protects data at rest against unauthorized access at the file/media layer. Define the threat model accurately before deploying.

## 2. Key concepts in TDE

TDE uses a hierarchical key model. Exact phrasing can differ between column encryption and tablespace encryption, but the core concepts include:

- **TDE master encryption key:** the master key managed inside the keystore.
- **Data encryption key / table key / tablespace key:** keys used to encrypt actual data or data keys.
- **Keystore:** where Oracle stores master keys and key metadata.
- **Wallet:** a common term for a software keystore; may take PKCS#12 and auto-login file formats.

General model:

~~~text
Password-protected keystore
       |
       +-- TDE master key
                |
                +-- protects column encryption data keys
                |
                +-- protects tablespace encryption keys
                         |
                         v
                  Encrypted data blocks
~~~

The master key is not a single key directly encrypting every byte in every datafile. It protects the data keys. This hierarchy makes it possible to rotate the master key without necessarily re-encrypting every datafile from scratch.

### 2.1 Losing the keystore can mean losing the ability to decrypt

If datafiles remain intact while the keystore holding the master key is lost or cannot be opened, Oracle may be unable to decrypt TDE data. Backing up the database without backing up the corresponding keystore leaves an incomplete recovery plan.

### 2.2 Retaining key history

When rotating the master key, older keys are generally still required to decrypt previously created data or backups. Do not delete old key versions simply because a new key is active.

Consider retiring old keys only when:

- You know precisely which data still references those keys.
- Retained backups/archived backups have passed retention or been transitioned via a verified process.
- Full keystore backups exist.
- Restore and recovery have been tested.
- Approved by the DBA/security owner.

## 3. Column encryption vs. tablespace encryption

Oracle TDE offers two main deployment approaches: encrypting individual columns or encrypting entire tablespaces.

### 3.1 TDE column encryption

Column encryption encrypts designated columns in a table. Example for identifier data:

~~~sql
CREATE TABLE employees_secure (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    national_id VARCHAR2(30) ENCRYPT
);
~~~

Only the `NATIONAL_ID` column is marked `ENCRYPT` in this example. Other columns are not automatically encrypted by column encryption.

Advantages:

- Can scope encryption to specific sensitive columns.
- Useful when only a subset of table data requires protection.
- Can be applied without moving the entire tablespace to an encrypted tablespace.

Considerations:

- Restrictions exist on supported data types and operations.
- Indexes, constraints, equality predicates, and SALT follow specific rules.
- Copies of data at the application layer, exports, or logs still require separate protection.
- Column and schema management can become complex when many sensitive columns exist.

### 3.2 TDE tablespace encryption

Tablespace encryption encrypts data within a tablespace. Segments stored in that tablespace are protected at the tablespace layer, covering many data types that column encryption cannot target directly.

Example creating an encrypted tablespace:

~~~sql
CREATE TABLESPACE secure_ts
DATAFILE '/u02/oradata/ORCL/secure_ts01.dbf'
SIZE 500M
ENCRYPTION USING 'AES256'
DEFAULT STORAGE (ENCRYPT);
~~~

This example illustrates syntax; file names, storage, algorithm, and availability must align with your version/edition and internal standards.

Advantages:

- Protects all segments residing in the encrypted tablespace.
- Suits applications/schemas with broad sensitive data.
- Eliminates specifying `ENCRYPT` column by column.
- Can cover LOB segments when LOBs are stored in the encrypted tablespace.

Considerations:

- Tablespace placement and migration must be managed.
- May incur CPU/I/O overhead depending on workload and hardware.
- Converting existing tablespaces to encryption requires capacity planning, time, and support verification.

### 3.3 Comparison

| Criterion | Column encryption | Tablespace encryption |
|---|---|---|
| Scope | Selected columns | Data inside the tablespace |
| Configuration | Declared on columns | Declared on the tablespace |
| LOBs | Support limitations; do not assume all LOB columns are encrypted directly | Protected if LOB segments reside in an encrypted tablespace |
| Indexes | Restrictions related to SALT and index types | Index segments are protected if stored in an encrypted tablespace |
| Administration | Per column/table | Per tablespace and placement |
| Best suited for | Selected sensitive fields | Storage areas or workloads requiring broad encryption |

Choose an approach based on storage architecture, data types, query patterns, compliance requirements, and Oracle version.

## 4. Encryption algorithms

Oracle TDE supports AES algorithms with varying key lengths depending on version and TDE type:

- AES128.
- AES192.
- AES256.

Example tablespace using AES256:

~~~sql
CREATE TABLESPACE secure_ts
DATAFILE '/u02/oradata/ORCL/secure_ts01.dbf'
SIZE 500M
ENCRYPTION USING 'AES256'
DEFAULT STORAGE (ENCRYPT);
~~~

For column encryption, you can specify the algorithm using version-supported syntax; if omitted, Oracle uses the feature/version default.

Do not pick an algorithm solely on the notion that "more bits is always better." Consider:

- Organizational security standards.
- Version and platform support.
- CPU performance and hardware acceleration capabilities.
- Compatibility across primary, standby, and restore environments.
- Licensing terms.

Do not assume the default algorithm is identical across all versions or encryption modes.

## 5. SALT in column encryption

Column encryption can use SALT so that identical plaintext values do not necessarily produce identical ciphertext across different rows.

Example:

~~~sql
CREATE TABLE customer_identity (
    customer_id NUMBER PRIMARY KEY,
    national_id VARCHAR2(30) ENCRYPT
);
~~~

Under default column encryption behavior, Oracle can apply SALT. SALT strengthens resistance to repetition/pattern analysis, but affects certain index/equality operations.

### 5.1 NO SALT

In some cases requiring an index on an encrypted column, Oracle allows declaring `NO SALT`:

~~~sql
CREATE TABLE customer_identity (
    customer_id NUMBER PRIMARY KEY,
    national_id VARCHAR2(30) ENCRYPT NO SALT
);
~~~

`NO SALT` produces more deterministic encryption for identical plaintext and can reveal repeated value patterns. This is a security trade-off; do not use it merely to enable indexing without evaluating the risk.

### 5.2 Do not assume all operations are supported

Operations on encrypted columns depend on data type, algorithm, SALT, indexes, and version. Before designing queries, consult the TDE documentation for your release regarding:

- Equality predicates.
- Range predicates.
- Joins.
- ORDER BY/GROUP BY.
- Index creation.
- Function-based indexes.
- Constraints.
- Export/import.

## 6. What is a keystore (wallet)?

A keystore is where Oracle stores TDE master encryption keys. For software keystores, Oracle commonly uses PKCS#12 format.

Common files:

- `ewallet.p12`: password-protected keystore.
- `cwallet.sso`: auto-login keystore.

Actual paths depend on `WALLET_ROOT` or version-specific wallet configuration.

### 6.1 Password-protected keystore

The keystore is protected by a password. When it needs to be opened, an administrator supplies the password through management mechanisms.

Advantages:

- Access to open the keystore is gated by a secret.
- Suits procedures requiring manual intervention or secret manager integration.
- Can serve as the source to generate an auto-login keystore.

Disadvantages:

- Requires managing the password and opening procedure after restarts.
- Without an operator/secret service opening the keystore, the database cannot access encrypted data after a restart.

### 6.2 Auto-login keystore

An auto-login keystore allows the database to open the keystore without interactive password entry in certain startup contexts.

The file is typically `cwallet.sso`. It enables automated operations, yet remains a critical secret artifact:

- Protect with filesystem permissions.
- Never place in source control.
- Never bake into shared container images.
- Never send via email/chat.
- Copy only over secure channels.

Auto-login does not mean the keystore is no longer sensitive. Anyone with access to the auto-login file and an appropriate environment may be able to use the keys.

### 6.3 Local auto-login keystore

A local auto-login keystore is bound to the host where it was created per Oracle mechanisms. This can be an option for environments needing to restrict copying auto-login files to other hosts.

When migrating hosts, cloning, or recovering a server, recreate/restore the keystore following version-specific guidance; do not assume a local auto-login file works on any host.

### 6.4 Password wallet and auto-login wallet must be managed together

The auto-login file is typically generated from the password-protected keystore. Keep secure backups of the password wallet and master keys. Never keep only `cwallet.sso` and delete the original `ewallet.p12`.

## 7. Configuring WALLET_ROOT and TDE_CONFIGURATION

In Oracle versions supporting modern configuration, `WALLET_ROOT` defines the root directory holding wallets/keystores. `TDE_CONFIGURATION` specifies the keystore configuration type.

Example:

~~~sql
ALTER SYSTEM SET WALLET_ROOT =
    '/u01/app/oracle/admin/ORCL/wallet'
    SCOPE = SPFILE;
~~~

`WALLET_ROOT` is a static parameter in typical configurations, so an instance restart may be required for the new value to take effect.

After configuring `WALLET_ROOT` and restarting:

~~~sql
ALTER SYSTEM SET TDE_CONFIGURATION =
    'KEYSTORE_CONFIGURATION=FILE'
    SCOPE = BOTH;
~~~

This is an example for a software file keystore. Syntax, parameters, and restart requirements depend on Oracle version and keystore type (`FILE`/`OKV` or other supported configurations).

### 7.1 Keystore location under WALLET_ROOT

In typical configurations, Oracle uses a TDE-related subdirectory under `WALLET_ROOT` to store the keystore. Do not guess the path during deployment; verify via `V$ENCRYPTION_WALLET` and release documentation.

### 7.2 Older versions using sqlnet.ora

Older Oracle releases may configure wallet locations using `ENCRYPTION_WALLET_LOCATION` in `sqlnet.ora`. Do not mix both configuration methods without understanding precedence and migration rules.

When upgrading a database, review:

- Source/target versions.
- Whether `WALLET_ROOT` is configured.
- The value of `TDE_CONFIGURATION`.
- Whether `sqlnet.ora` still holds legacy wallet settings.
- The actual path from which the running instance opens the wallet.

## 8. Creating a password-protected keystore

Example creating a software keystore:

~~~sql
ADMINISTER KEY MANAGEMENT CREATE KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

The password in the example is a placeholder only. Never use it verbatim in production and never commit real secrets into repository scripts.

The keystore password should be:

- Randomly generated per policy.
- Stored in an approved secret manager/password vault.
- Granted access by role.
- Covered by rotation and emergency access procedures.
- Never hard-coded in application configuration files.

### 8.1 Opening the keystore

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "StrongKeystorePassword";
~~~

In a multitenant environment, the `CONTAINER` scope must be clearly specified. Do not open or modify keystores for all PDBs when only one container needs action.

### 8.2 Checking status

~~~sql
SELECT con_id,
       wrl_type,
       wrl_parameter,
       status,
       wallet_type,
       keystore_mode,
       fully_backed_up
FROM v$encryption_wallet
ORDER BY con_id;
~~~

Common fields:

- `WRL_TYPE`: keystore location type.
- `WRL_PARAMETER`: wallet path/parameter.
- `STATUS`: keystore status.
- `WALLET_TYPE`: `PASSWORD`, `AUTOLOGIN`, or corresponding type.
- `KEYSTORE_MODE`: `UNITED` or `ISOLATED` in multitenant.
- `FULLY_BACKED_UP`: backup status per Oracle-reported metadata.

Columns may vary by release. Inspect the view structure before using it on older versions.

Common statuses can include `OPEN`, `CLOSED`, `OPEN_NO_MASTER_KEY`, `OPEN_UNKNOWN_MASTER_KEY_STATUS`, or `NOT_AVAILABLE` depending on version and context. Check exact meanings in the release reference.

## 9. Creating and activating the TDE master key

After the keystore is created and opened, a master key must be set for TDE to use.

Example:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'initial_tde_master_key';
~~~

`SET KEY` creates/sets the current master key per TDE mechanisms and triggers a keystore backup in this example. The backup identifier helps label the created backup.

### 9.1 Checking key metadata

~~~sql
SELECT con_id,
       key_id,
       tag,
       creation_time,
       activation_time,
       creator,
       user_name
FROM v$encryption_keys
ORDER BY activation_time DESC;
~~~

Available views and columns depend on version/privileges. Never expose or share secret contents; key ID metadata is not the master key itself.

### 9.2 Key ID is not key material

`KEY_ID` is a key identifier. You cannot recover a master key from `KEY_ID` alone. You must retain the keystore and its backups.

### 9.3 Do not run SET KEY repeatedly by mistake

`SET KEY` is a key lifecycle operation, not a status check command. Execute it only during initial setup, rotation, or approved administrative procedures. Every change must be logged, backed up, and synchronized to dependent environments.

## 10. Creating an auto-login keystore

Once a password-protected keystore exists, an auto-login keystore can be created:

~~~sql
ADMINISTER KEY MANAGEMENT CREATE AUTO_LOGIN KEYSTORE
    FROM KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Oracle creates the corresponding auto-login file in the keystore location per release rules.

### 10.1 Creating local auto-login

In supported environments:

~~~sql
ADMINISTER KEY MANAGEMENT CREATE LOCAL AUTO_LOGIN KEYSTORE
    FROM KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Local auto-login is host-bound. Verify support and behavior during copy/restore on your running release.

### 10.2 Auto-login does not replace password backups

When you need to:

- Restore on a new host.
- Open the keystore manually.
- Change the password.
- Import/export keys.
- Recreate auto-login.

the password-protected keystore and original password may be required. Back up both the original keystore and required artifacts per procedure.

## 11. Closing the keystore and restarting the database

Closing the keystore:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE CLOSE
    IDENTIFIED BY "StrongKeystorePassword";
~~~

In some contexts it may close without supplying a password or use different syntax depending on wallet type; follow release documentation.

If the database uses encrypted tablespaces/columns, closing the keystore can cause operations needing decryption to fail or render TDE data inaccessible until the keystore is reopened.

### 11.1 After a restart

Verify:

1. The instance opens the intended keystore path.
2. Wallet status is in the expected state.
3. The master key is available.
4. Required PDBs have opened keystores.
5. Queries against encrypted objects succeed.
6. Standby/RAC nodes have the same required key material.

Do not check only whether the database is OPEN. A database can be OPEN while the keystore is still CLOSED or lacks the appropriate master key.

## 12. Rotating the master key

Key rotation creates a new master key and switches the active key to the new version per Oracle procedures. Older keys are normally retained to decrypt data/backups protected by earlier versions.

Example:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'rotate_tde_key_2026';
~~~

This is the typical command form to set/rotate a master key and create a backup. Exact syntax may differ by CDB/PDB context or release.

### 12.1 Rotation does not mean re-encrypting every datafile

In the hierarchical key model, the master key protects data keys. Changing the master key generally updates the protection layer on data keys rather than reading and re-encrypting every datafile block in a full rewrite. However, impact and steps depend on TDE type, rekey operations, and version.

### 12.2 When is rotation needed?

- According to organizational rotation schedules.
- After suspected exposure of a master key or keystore password.
- After major personnel/administrative privilege changes.
- When required by security policy.
- When migrating keystore architectures.

Rotation does not remove the need to protect older key versions.

### 12.3 Back up immediately after rotation

Every key change requires:

1. Verifying the keystore is properly open.
2. Executing rotation during an approved window.
3. Creating a keystore backup.
4. Copying the backup to separate secure storage.
5. Synchronizing to required standbys/RAC nodes/PDBs.
6. Recording key ID, tag, timestamp, and operator.
7. Testing keystore opening and data access.

## 13. Backing up the keystore and master keys

Database backups and keystore backups are two separate parts of a data protection plan. A database backup alone may be insufficient to recover TDE data without the corresponding key material.

### 13.1 Creating a backup with ADMINISTER KEY MANAGEMENT

Example:

~~~sql
ADMINISTER KEY MANAGEMENT BACKUP KEYSTORE
    USING 'before_maintenance'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

The backup command creates a keystore backup per Oracle mechanisms. Syntax may support `TO file_name` or variations by release. Verify where the backup file is written and its filesystem permissions.

### 13.2 WITH BACKUP when creating/rotating keys

When running `SET KEY`, use `WITH BACKUP` to instruct Oracle to create a keystore backup:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'before_key_change';
~~~

Do not treat this automatic backup as the sole backup copy. Move artifacts to a secure backup repository separated from the host/database.

### 13.3 Off-host backups

Backup procedures should:

- Copy the password-protected keystore.
- Retain auto-login artifacts if architecture requires and policy allows.
- Store passwords/secrets in a separate secret manager.
- Encrypt transport and backup storage.
- Restrict read permissions.
- Maintain off-host/offline or immutable copies per policy.
- Include checksums and version-identifying manifests.
- Periodically test restore capability.

Never store the only backup on the same filesystem as datafiles. If the host/storage is lost, both the database and keys could be lost together.

### 13.4 Back up the keystore after every key change

The following changes must be logged and backed up:

- Creating the initial master key.
- Rotating the master key.
- Importing keys from another system.
- Changing the keystore password.
- Changing keystore configuration.
- Creating/updating an auto-login wallet.

Backups must be correlated with timestamps and their corresponding database/PDB/keystore.

## 14. Recovering a TDE database during restore

Restoring an encrypted database requires all of:

- Valid database/datafile/control file/redo backups.
- The keystore holding the required master keys.
- Passwords or mechanisms to open the keystore.
- Wallet path/`TDE_CONFIGURATION` settings.
- Filesystem permissions.
- A compatible Oracle environment.

General workflow:

~~~text
Prepare host/database
       |
       v
Restore the matching keystore version
       |
       v
Set file permissions and wallet config
       |
       v
Open the keystore
       |
       v
Restore/recover the database
       |
       v
Verify encrypted tablespaces/columns
       |
       v
Test queries and applications
~~~

Exact sequencing depends on database state and restore type. Some scenarios require opening the keystore before mount/open or before reading encrypted datafiles. Follow a tested runbook for your actual version and architecture.

### 14.1 Old backups need old keys

If a backup was taken before a key rotation, ensure the current keystore still retains the key versions needed to decrypt data from that backup.

Never delete old keys simply because the current live database queries succeed. Older backups may need to be restored in the future.

### 14.2 Restore testing is mandatory

A backup file existing on disk does not prove the backup can be restored. Rehearse regularly:

1. Use an isolated environment.
2. Restore the database backup.
3. Restore the matching keystore/password.
4. Open the keystore.
5. Recover the database.
6. Query encrypted tables/columns.
7. Confirm applications can read the data.
8. Record recovery time and manual steps.

Never run destructive recovery drills on production.

## 15. Exporting/importing encryption keys

In certain migration, clone, PDB move, or cross-environment recovery scenarios, encryption keys must be exported/imported following Oracle procedures.

Export framework example:

~~~sql
ADMINISTER KEY MANAGEMENT EXPORT ENCRYPTION KEYS
    WITH SECRET "TransferSecret"
    TO '/secure/transfer/tde_keys.exp'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Import framework example:

~~~sql
ADMINISTER KEY MANAGEMENT IMPORT ENCRYPTION KEYS
    WITH SECRET "TransferSecret"
    FROM '/secure/transfer/tde_keys.exp'
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP;
~~~

These examples illustrate common syntax. Depending on release, container, and keystore mode, additional scope or clauses may be required. Consult the Oracle SQL Language Reference for your exact version before executing.

### 15.1 Export files are sensitive artifacts

A key export file is not an ordinary configuration file. You must:

- Protect `TransferSecret` separately.
- Restrict file read permissions.
- Use secure transfer channels.
- Verify checksums.
- Purge temporary copies per retention policy.
- Never commit to Git.
- Log source, destination, and operator.

### 15.2 Importing does not replace backups

After importing, back up the target keystore and verify key metadata. Do not delete the export file or source keystore before the migration is verified and a recovery backup exists.

## 16. Multitenant: CDB, PDB, and keystore modes

In Oracle Multitenant, a CDB contains a root container and pluggable databases (PDBs). TDE keystores can be managed in two modes:

- `UNITED`: PDBs share a common keystore managed by the CDB.
- `ISOLATED`: a PDB maintains its own dedicated keystore per supported configuration.

Actual mode values can be viewed in `V$ENCRYPTION_WALLET.KEYSTORE_MODE` on releases providing that column.

### 16.1 United mode

In united mode, root manages a shared keystore for PDBs. Opening the keystore and setting keys can apply by container scope.

Example operation in a CDB:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "StrongKeystorePassword"
    CONTAINER = ALL;
~~~

`CONTAINER=ALL` should be used intentionally. In some cases, operating only on `CONTAINER=CURRENT` is appropriate. Connect to the intended container before executing.

### 16.2 Isolated mode

In isolated mode, a PDB has its own keystore. This separates key administration between PDBs, but increases operational responsibility:

- Each PDB must have its own keystore and master key.
- Backups/restores must match the right PDB and key material.
- PDB unplug/plug must handle keystores per procedure.
- DBAs must monitor wallet status for each container.

### 16.3 Checking status per container

~~~sql
SELECT con_id,
       status,
       wallet_type,
       keystore_mode,
       fully_backed_up,
       wrl_parameter
FROM v$encryption_wallet
ORDER BY con_id;
~~~

Do not conclude TDE is ready for every PDB just because `CDB$ROOT`'s wallet is `OPEN`.

### 16.4 PDB unplug/plug and cloning

When moving or cloning a PDB containing encrypted data, ensure the target has the required master keys. With isolated keystores, export/import or transfer the keystore per procedure. With united mode, verify the PDB's keys exist in the shared keystore and container scope is compatible.

Never copy a PDB's datafiles alone and assume it can open in the target database.

## 17. RAC and Data Guard

### 17.1 Oracle RAC

Instances in a RAC cluster need access to the same key material for the database. Keystore paths and artifacts must be deployed consistently across nodes per the chosen storage architecture.

Verify:

- Each instance sees the right keystore.
- Wallet status on every instance.
- Auto-login files work per host policy.
- After rotation, new keys are shared/synchronized.
- Restarting individual instances does not break wallet opening.

### 17.2 Data Guard standby

Standby databases need corresponding key material to read/apply encrypted data. After creating or rotating a master key on the primary, synchronize the keystore to the standby using supported procedures and verify status.

If the standby lacks the new key:

- Redo apply or encrypted data access operations may fail.
- Switchover/failover may not work as expected.
- Restoring backups at the standby may fail.

### 17.3 Post-rotation runbook

A synchronization checklist:

1. Rotate the key on primary during an approved window.
2. Back up the new keystore.
3. Transfer the keystore/key material over a secure channel.
4. Update all relevant standby and RAC nodes.
5. Open the keystore in required environments.
6. Verify `V$ENCRYPTION_WALLET` and key metadata.
7. Confirm redo apply and test queries.
8. Update inventory/backup manifests.

Never perform switchover/failover without verifying key readiness at the target.

## 18. TDE and RMAN backups

TDE and RMAN backup encryption are related but distinct concepts.

### 18.1 TDE protects database data at rest

TDE column/tablespace encryption encrypts data within database storage. With tablespace encryption, data in encrypted tablespaces is stored encrypted on disk.

### 18.2 RMAN backup encryption is a separate configuration

RMAN has its own backup encryption modes, such as transparent, password, or dual mode depending on version. RMAN backup encryption can encrypt backup sets according to its configuration and corresponding keys/secrets.

Do not infer that all backups, exports, or file copies are automatically protected merely because the database uses TDE.

### 18.3 Datafile backups and backup sets

Whether a backup is encrypted depends on:

- TDE type (column/tablespace).
- Backup type (image copy vs. backup set).
- RMAN encryption configuration.
- Version and options.
- How data is processed in the backup pipeline.

Consult RMAN/TDE documentation for your release and verify through restore testing. For sensitive data, RMAN backup encryption or storage-level encryption may also be required by policy.

### 18.4 Back up the keystore separately

Even when RMAN backups are encrypted, the keystore must still be managed separately. If backups are encrypted using TDE master keys or RMAN transparent mode relying on a wallet, the appropriate keys/keystore are required to restore.

## 19. TDE does not replace network encryption

TDE protects data stored on disk. When clients connect to the database, data returned over the network requires separate protection.

Options include:

- TLS with Oracle Net.
- Oracle Native Network Encryption if configured and supported.
- VPN or private network as an additional layer.

Do not treat TDE as an end-to-end transport encryption solution. Configure and test TLS/network encryption independently.

## 20. TDE and Data Pump/export

Data Pump export creates dump files containing logical data. Data in dump files can be in decrypted form depending on how export processes it; therefore, never assume dump files are always encrypted merely because source tables reside in an encrypted tablespace.

When exporting sensitive data:

- Know where dump files are written.
- Protect `DIRECTORY` objects and OS permissions.
- Use appropriate Data Pump encryption options if licensed and permitted.
- Protect encryption passwords.
- Encrypt storage/transit.
- Set retention and securely delete temporary files.

Verify Data Pump encryption feature availability and licensing for your version/edition. Never use Data Pump access to bypass data classification policies.

## 21. TDE and temp, redo, undo, and LOB data

TDE column encryption and tablespace encryption have different scopes. Track which segments data gets written to:

- Table segments.
- Index segments.
- LOB segments.
- Undo.
- Temporary tablespaces.
- Redo/archived logs.
- Exports/dumps.

An encrypted tablespace protects segments within that tablespace per TDE tablespace mechanisms. However, data copied to other tablespaces, dump files, or external logs must be evaluated separately.

Do not assume every data copy created across the system is automatically encrypted the same way. Build a data flow inventory and test each path.

## 22. Monitoring TDE status

### 22.1 Keystore status

~~~sql
SELECT con_id,
       status,
       wallet_type,
       keystore_mode,
       fully_backed_up,
       wrl_type,
       wrl_parameter
FROM v$encryption_wallet;
~~~

### 22.2 Keys known to the database

~~~sql
SELECT con_id,
       key_id,
       tag,
       creation_time,
       activation_time
FROM v$encryption_keys
ORDER BY con_id, activation_time DESC;
~~~

### 22.3 Column encryption metadata

~~~sql
SELECT owner,
       table_name,
       column_name,
       encryption_alg,
       salt
FROM dba_encrypted_columns
ORDER BY owner, table_name, column_name;
~~~

### 22.4 Tablespace encryption metadata

~~~sql
SELECT tablespace_name,
       encrypted
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Depending on the version, `V$ENCRYPTED_TABLESPACES` can also be used to check encryption status and algorithms. Check available dictionary views in your release.

### 22.5 Operational checks

- Is the keystore `OPEN` in required containers?
- Is the master key active?
- Does `FULLY_BACKED_UP` reflect the expected backup state?
- Have keystore backups been copied off-host?
- Do all standby/RAC nodes have the new key version?
- Do auto-login wallets have strict filesystem permissions?
- Are alerts configured for closed keystores or unavailable keys?

`FULLY_BACKED_UP` is useful metadata, but does not prove an off-host backup can be restored. Perform actual recovery testing.

## 23. Feature availability and licensing requirements

TDE is subject to edition, version, platform, and licensing conditions. For on-premises Oracle Database deployments, TDE generally falls under the Oracle Advanced Security Option (ASO). Never infer from being able to run TDE commands or seeing TDE status views that your organization holds the required license.

### 23.1 What must be confirmed

Before enabling TDE, the DBA/license owner must confirm:

1. Oracle Database version and release update.
2. Edition and deployment type.
3. Platform (on-premises, engineered system, cloud service).
4. Whether Advanced Security Option is covered by contract/entitlement.
5. Specific TDE features permitted in that environment.
6. Any additional cloud service terms or licensing metrics.
7. Licensing terms for DR, test, development, and standby environments.

### 23.2 On-premises

In many on-premises Oracle Database Enterprise Edition models, TDE is part of the Advanced Security Option. Having Enterprise Edition does not automatically imply ASO is licensed.

Check the Oracle Licensing Information manual for your exact release and your organization's contract. Terms can change across releases and license programs.

### 23.3 Cloud services

Some Oracle Cloud Database services may include usage rights for security features within the service or have separate commercial terms. Do not mechanically apply on-premises licensing conclusions to cloud services.

Read the service description, ordering documents, and specific cloud terms. Do not assume all Oracle Cloud services share identical entitlements.

### 23.4 Editions and technical availability

Some features may:

- Be unavailable in certain editions.
- Have platform-specific restrictions.
- Require additional configuration.
- Change between releases.

Verify feature support against release documentation. Avoid relying on old blog posts or commands succeeding in another environment.

### 23.5 Views and parameters do not confirm licensing

The following are not sufficient evidence to conclude a feature is licensed:

- Querying `V$OPTION` and seeing an option `TRUE`.
- Seeing `V$ENCRYPTION_WALLET`.
- Successfully creating a keystore.
- `ADMINISTER KEY MANAGEMENT` SQL succeeding.
- Feature binaries present in the edition.

Technical capability and contractual entitlement are two different matters. The license owner/Oracle account team must confirm applicable entitlements.

## 24. Distinguishing TDE from other security features

| Feature | Primary goal | Replaces TDE? |
|---|---|---|
| TDE | Encrypting database data at rest | It is the at-rest encryption layer |
| TLS/Oracle Net encryption | Protecting data in transit | No |
| RMAN backup encryption | Encrypting backup sets per RMAN config | No; complementary |
| Storage encryption | Block/device encryption at storage layer | Not entirely; different management layer |
| Data Redaction | Masking query results at runtime per policy | No |
| Data Masking | Replacing sensitive data in non-production environments | No |
| VPD/Row-Level Security | Restricting rows visible to users | No |
| Database Vault | Controlling privileged access per policy | No |
| Auditing | Recording database activity | No |

A sound security architecture uses defense in depth. TDE protects data at rest, yet authorization, auditing, network encryption, backup security, and secret management are still required.

## 25. Performance and operations

TDE can add CPU overhead and affect I/O depending on encryption type, hardware, workload, and hardware crypto acceleration.

Before broad rollout:

- Benchmark OLTP read/write workloads.
- Benchmark batch and analytical workloads.
- Measure CPU, latency, and throughput.
- Measure backup/restore durations.
- Test indexes/queries on encrypted columns.
- Measure impact when the database lacks hardware crypto acceleration.
- Test LOB and TEMP workloads.

Do not extrapolate a small-table benchmark to the entire database.

### 25.1 Tablespace migration

Converting an existing tablespace to encryption may require online/offline operations depending on version and conversion method. Some releases support `ALTER TABLESPACE ENCRYPTION ONLINE`; other releases have different constraints.

Never run migration commands in production before:

- Verifying exact release syntax and feature behavior.
- Sizing datafile and TEMP capacity.
- Establishing a backup/recovery point.
- Estimating duration and locking behavior.
- Checking standby and replication impact.
- Having a rollback/recovery plan.

### 25.2 Column encryption migration

Adding or altering a column to `ENCRYPT` can require table rewrites/DDL operations and affect indexes/constraints. Check table size, data types, SALT, dependent objects, and applications before modifying.

## 26. Keystore incident response plan

### 26.1 Wallet CLOSED

Symptoms can include errors accessing encrypted data or performing operations requiring the master key.

Investigation:

1. Query `V$ENCRYPTION_WALLET`.
2. Identify the exact container and instance.
3. Verify the keystore path.
4. Verify the password/auto-login file.
5. Open the keystore following approved procedures.
6. Test querying encrypted data.

Never create a new master key just to fix a `CLOSED` wallet.

### 26.2 OPEN_NO_MASTER_KEY

The keystore may be open, yet no master key is activated for the current container or database context.

Check:

- Was a key previously set?
- Are you in CDB root or a PDB?
- Is united/isolated mode configured properly?
- Is this the right keystore for the database?
- Were keys imported completely?

Never arbitrarily create a new key if the database already holds data encrypted with an older key.

### 26.3 Wrong keystore path or unreadable file

Check:

- `WALLET_ROOT`.
- `TDE_CONFIGURATION`.
- `WRL_PARAMETER`.
- OS permissions/ownership.
- Mount points/network filesystems.
- Whether `ewallet.p12`/`cwallet.sso` exist and are intact.

Never `chmod 777` a wallet directory. Grant minimal permissions to the Oracle software owner and appropriate operations group.

### 26.4 Master key missing on standby

Check key ID/version on primary and standby, the latest keystore backup, and synchronization steps. Do not arbitrarily copy a single file if multiple keystores/PDBs or key versions exist.

## 27. Controlled TDE deployment workflow

A production workflow:

1. Classify data and define the threat model.
2. Choose column encryption or tablespace encryption.
3. Confirm version, edition, platform, and licensing.
4. Design `WALLET_ROOT`/`TDE_CONFIGURATION`.
5. Choose password keystore, auto-login, or isolated keystores per requirements.
6. Create the keystore and open it in the intended containers.
7. Set the master key and back up immediately.
8. Create encrypted tablespaces or encrypt columns.
9. Verify metadata and actual queries.
10. Synchronize keystores to relevant RAC/standby/PDB environments.
11. Test restarts, backup/restore, and disaster recovery.
12. Move key backups off-host and store secrets separately.
13. Monitor wallet status, key lifecycle, and backup status.
14. Document rotation/recovery runbooks and assign responsibilities.

## 28. Example runbook: creating a new TDE tablespace

The steps below are lab examples, not scripts to run verbatim on every database.

### Step 1: Verify configuration

~~~sql
SHOW PARAMETER wallet_root
SHOW PARAMETER tde_configuration
~~~

### Step 2: Create the keystore if it does not exist

~~~sql
ADMINISTER KEY MANAGEMENT CREATE KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

### Step 3: Open the keystore

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "StrongKeystorePassword";
~~~

### Step 4: Set the master key and back up

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'initial_key';
~~~

### Step 5: Verify wallet/key

~~~sql
SELECT status, wallet_type, fully_backed_up
FROM v$encryption_wallet;

SELECT key_id, tag, activation_time
FROM v$encryption_keys
ORDER BY activation_time DESC;
~~~

### Step 6: Create the encrypted tablespace

~~~sql
CREATE TABLESPACE secure_ts
DATAFILE '/u02/oradata/ORCL/secure_ts01.dbf'
SIZE 500M
ENCRYPTION USING 'AES256'
DEFAULT STORAGE (ENCRYPT);
~~~

### Step 7: Create a table and test

~~~sql
CREATE TABLE secure_ts_test (
    id NUMBER PRIMARY KEY,
    secret_value VARCHAR2(100)
)
TABLESPACE secure_ts;

INSERT INTO secure_ts_test VALUES (1, 'sample');
COMMIT;

SELECT * FROM secure_ts_test;
~~~

### Step 8: Back up the keystore off-host

The DBA creates a backup per procedure, locates the generated file, copies it over a secure channel, and verifies checksums. Store the password in a separate secret manager.

### Step 9: Restore rehearsal

Restore the database and keystore into a lab environment, open the wallet, query `SECURE_TS_TEST`, and record the outcome.

## 29. Self-check practice labs

Run exercises only on a lab database or an environment approved by the DBA.

### Exercise 1 — Inspect wallet status

Query `V$ENCRYPTION_WALLET`. Record `WRL_PARAMETER`, `STATUS`, `WALLET_TYPE`, `KEYSTORE_MODE`, and `FULLY_BACKED_UP`.

### Exercise 2 — Create a password keystore

In a lab database, create a software keystore using `ADMINISTER KEY MANAGEMENT`. Verify generated files and filesystem permissions.

### Exercise 3 — Set the master key

Open the keystore, create a master key with `WITH BACKUP`. Query `V$ENCRYPTION_KEYS` and record the key ID/tag.

### Exercise 4 — Auto-login wallet

Create an auto-login keystore in the lab. Restart the instance per runbook and confirm wallet status. Then verify the standalone procedure for opening the password wallet.

### Exercise 5 — Column encryption

Create a table with an `ENCRYPT` column. Insert test data, query `DBA_ENCRYPTED_COLUMNS` metadata, and test SQL access.

### Exercise 6 — SALT and NO SALT

Create two test tables using column encryption with `SALT` and `NO SALT`. Check index/query support for your release and note the trade-offs.

### Exercise 7 — Tablespace encryption

Create an `AES256` encrypted tablespace, create a table, and verify `DBA_TABLESPACES`/`V$ENCRYPTED_TABLESPACES`.

### Exercise 8 — Key rotation

In the lab, create a new key version with `WITH BACKUP`. Check key metadata and confirm older data remains readable.

### Exercise 9 — Keystore backup

Back up the keystore, copy it to secure storage, and verify checksums. Never store the secret in the same directory.

### Exercise 10 — Restore test

Restore the lab database along with the keystore to an isolated host/instance. Verify queries on encrypted tables succeed.

### Exercise 11 — Multitenant

Check `KEYSTORE_MODE` in CDB/PDB. Compare `UNITED` and `ISOLATED` against version documentation without altering mode on live environments.

### Exercise 12 — Licensing review

Build a table listing version, edition, deployment type, TDE feature, Advanced Security entitlement, and approver. Cross-check ordering documents/licensing manuals before enabling TDE in production.

## 30. Production checklist

**Design**

- Have data scope and threat model been defined?
- Is the choice between column and tablespace encryption justified?
- Have LOBs, indexes, TEMP, undo, redo, exports, and backups been accounted for?
- Does the algorithm align with policy and version?

**Keystore**

- Are `WALLET_ROOT`/`TDE_CONFIGURATION` correct?
- Is the keystore password stored in a secret manager?
- Is auto-login genuinely needed?
- Are filesystem permissions tight enough?
- Is the CDB/PDB keystore mode defined?

**Keys**

- Is the master key active?
- Are key IDs/versions inventoried?
- Does rotation include a backup?
- Are old keys retained per retention rules?
- Do standby/RAC/PDB nodes have all required keys?

**Backup/restore**

- Is the keystore backed up after every key change?
- Are off-host/offline copies maintained?
- Are passwords stored separately?
- Are database backups and key backups correlated by timestamp?
- Has database + keystore restore been rehearsed?

**Licensing**

- Have version/edition/platform been verified?
- Has Advanced Security Option or cloud entitlement been confirmed by the license owner?
- Are specific features covered by entitlements?
- Are DR/test/dev licensing terms addressed?
- Are `V$OPTION` or runnable commands not being used as license proof?

**Operations**

- Is wallet status monitored?
- Are alerts configured for `CLOSED` wallet/unavailable key?
- Is a post-restart runbook ready?
- Are rotation/recovery runbooks ready?
- Are Data Guard/RAC checks run after rotation?
- Are traces/logs/exports protected for sensitive data?

## 31. Key takeaways

| Concept | Key takeaway |
|---|---|
| TDE | Encrypting database data at rest |
| Column encryption | Encrypting selected columns |
| Tablespace encryption | Encrypting data inside a tablespace |
| Master key | Top-level key managed in the keystore |
| Data encryption key | Key protecting the actual data |
| Keystore/wallet | Storage for TDE master keys and metadata |
| `ewallet.p12` | Common password-protected keystore |
| `cwallet.sso` | Common auto-login keystore |
| `WALLET_ROOT` | Root wallet directory in modern configurations |
| `TDE_CONFIGURATION` | Keystore type configuration |
| `V$ENCRYPTION_WALLET` | Keystore status and location |
| `V$ENCRYPTION_KEYS` | Master key metadata |
| `WITH BACKUP` | Requests a keystore backup during supported key-change commands |
| Key rotation | Activating a new master key version; retaining old keys per retention |
| `UNITED` | PDBs share a CDB-managed keystore |
| `ISOLATED` | PDB has its own keystore per configuration |
| RMAN encryption | Separate backup encryption mechanism; evaluate alongside TDE |
| Network encryption | Protects data in transit, independent of TDE |
| Advanced Security Option | License option typically tied to on-premises TDE |
| License entitlement | Must be verified by version, edition, platform, and contract |

TDE protects data at rest only when the keystore and master keys are properly managed. Choose the right encryption scope, safeguard password-protected keystores and key backups, synchronize keys across standby/RAC/PDBs, and rehearse real restores. Keep TDE distinct from RMAN backup encryption and network encryption. Finally, confirm edition, deployment model, and Advanced Security or cloud entitlements with the license owner before enabling the feature; a database supporting the command does not by itself prove the organization is licensed to use it.
