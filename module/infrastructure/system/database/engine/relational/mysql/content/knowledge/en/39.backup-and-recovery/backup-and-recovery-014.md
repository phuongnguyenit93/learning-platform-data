# Backing Up Configuration, Accounts, Certificates, and Encryption Keys

## Objectives

A MySQL backup can only be fully restored when you preserve both the data and the components required for the server to start, authenticate users, establish secure connections, and decrypt data. Configuration files, account definitions, TLS certificates, and encryption keys usually sit outside table-data backup streams; if you miss them, recovery can stall even when all data files remain intact.

This lesson belongs to the **DATABASE_MYSQL** module, spanning table design, data types, keys, SQL, indexes, transactions, concurrency control, query tuning, and relational database operations. Within backup and recovery, this material focuses on identifying, protecting, versioning, and restoring MySQL's accompanying configuration and security components.

After this lesson, you will be able to:

- Inventory configuration files, runtime settings, and extensions that must be preserved.
- Export and restore account definitions, privileges, roles, and default role settings.
- Back up certificates, CA chains, private keys, and TLS credentials securely.
- Identify the keyring or KMS/HSM service protecting encrypted data and build the corresponding recovery workflow.
- Perform recovery checks to confirm the server starts, applications log in, and encrypted data is readable.

## 1. Viewing a Backup as a Bundle of Components

Schema data is only one piece of system state. A recovery may require the following groups of artifacts:

| Group | Example Components | Purpose During Recovery |
|---|---|---|
| Server configuration | `my.cnf`, `my.ini`, include directories, startup flags, service config | Start MySQL with the right paths, port, modes, and expected behavior |
| Persisted settings | `mysqld-auto.cnf` managed by `SET PERSIST` | Restore system variables persisted across restarts |
| Accounts and privileges | `user`/`host` accounts, auth plugins, roles, grants, default roles | Allow DBAs, applications, and operational tools to log in with proper privileges |
| Certificates and TLS | Server certificate, private key, CA, client certificates, CRL if used | Establish encrypted connections and certificate validation |
| Encryption keys | Keyring data, component/plugin config, KMS/HSM identifiers and access permissions | Open encrypted tablespaces, redo logs, or data |
| Operational info | MySQL version, plugins/components, paths, file ownership, ACLs, deployment topology | Recreate a compatible environment with proper access controls |

Clearly define the scope of every backup bundle. A data dump does not inherently include OS configuration, private keys, keyrings, or KMS access credentials. Conversely, a copy of a configuration directory does not replace the data backups and logs required for recovery objectives.

## 2. Inventorying MySQL Configuration

MySQL can read settings from multiple option files, included directories, command-line flags, and service-manager configs. Exact locations depend on the OS, package, and deployment method. Therefore, never copy a single `my.cnf` or `my.ini` without confirming which sources the server actually reads.

Before backing up, record the version and key variables:

```sql
SELECT VERSION() AS mysql_version;

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'basedir', 'datadir', 'port', 'socket', 'pid_file',
  'log_error', 'log_bin', 'relay_log', 'server_id',
  'lower_case_table_names', 'character_set_server',
  'collation_server', 'sql_mode', 'time_zone',
  'tls_version', 'ssl_ca', 'ssl_cert', 'ssl_key'
);

SHOW PLUGINS;

-- MySQL 8.0: inspect registered components when this table is available
SELECT component_urn FROM mysql.component;
```

The variables above are a starting inventory; add variables covering replication, binary logs, InnoDB, encryption, auditing, authentication, and active plugins. `SHOW PLUGINS` lists plugins; components must be inventoried separately by version, such as via `mysql.component` in MySQL 8.0. Variable values can be sensitive or reveal internal layout, so restrict access to the exported inventory.

On the host side, identify:

- All option files and included directories, including files managed by configuration management tools.
- Command-line flags and configurations for systemd, Windows Service, containers, or orchestrators.
- The OS account running `mysqld`, plus read/write permissions on data directories, logs, certificates, and keyrings.
- Plugin/component configurations, accompanying shared libraries, and environment variables required at startup.
- Runtime changes persisted via `SET PERSIST`.

The `my_print_defaults` utility helps inspect options read from option files, while `mysqld --verbose --help` can show options and default sources depending on version. Output from these commands can expose passwords or sensitive paths; store only in access-restricted areas and never paste verbatim into tickets or public logs.

### Notes on `mysqld-auto.cnf`

When using `SET PERSIST`, MySQL writes system variable values into `mysqld-auto.cnf` inside the data directory. This file participates in server configuration at startup. Include it in your protection inventory and archive it alongside the timestamp of the corresponding data backup.

Do not hand-edit `mysqld-auto.cnf` while the server manages it. Use `SET PERSIST`, `SET PERSIST_ONLY`, or `RESET PERSIST` according to your needs and MySQL version. When restoring to another environment, review every value before applying because paths, devices, ports, and resource limits may differ.

## 3. Backing Up Accounts, Roles, and Privileges

In MySQL, an account is identified by a username and host pair, such as `'orders_app'@'10.20.30.15'`. An account record can include authentication plugins, lock state, password policies, TLS requirements, resource limits, and other attributes. Privileges may be granted directly or through roles; roles may also be configured as default roles upon login.

For every account and role to retain, export definitions and grants via administrative statements:

```sql
SHOW CREATE USER 'orders_app'@'10.20.30.15';
SHOW GRANTS FOR 'orders_app'@'10.20.30.15';

SHOW CREATE USER 'orders_report'@'10.20.30.25';
SHOW GRANTS FOR 'orders_report'@'10.20.30.25';
```

`SHOW CREATE USER` provides the statement to recreate the account and any authentication attributes the caller is privileged to view. `SHOW GRANTS` shows direct privileges and granted roles. Do the same for admin accounts, service accounts, roles, and internal accounts required by applications or operational tooling.

For roles, record privileges inside the role, role-to-account grants, and default roles. For example:

```sql
CREATE ROLE 'orders_readonly';
GRANT SELECT ON orders.* TO 'orders_readonly';
GRANT 'orders_readonly' TO 'analyst'@'10.20.30.25';
SET DEFAULT ROLE 'orders_readonly' TO 'analyst'@'10.20.30.25';
```

During export, preserve role creation, role assignment, and default-role statements alongside their grants. If an account receives multiple roles or nested roles, record the full hierarchy so recovery does not leave missing privileges.

Account definitions and grants are sensitive data. `SHOW CREATE USER` output can contain hashed authentication strings or plugin attributes; protect exported files as secrets, encrypt at rest, and restrict who can read them. Never push these contents into public Git repositories, unencrypted emails, or CI/CD logs.

### Choosing an Appropriate Export Method

You can use an account-export utility supported by your exact MySQL version or export `SHOW CREATE USER` and `SHOW GRANTS` statements across your account inventory. Before choosing a tool, check documentation for your running version and confirm whether it preserves roles, dynamic privileges, default roles, authentication attributes, and TLS requirements.

Never copy raw grant-table files or system privilege tables from a data directory onto a server running a different version. Data dictionary and grant table structures change across versions; use administrative and upgrade mechanisms supported by MySQL. Nor should you blindly restore accounts of departed staff or revoked secrets.

## 4. Backing Up Certificates and TLS Configuration

MySQL can use TLS to encrypt client/server connections and, depending on configuration, verify client certificates. A TLS bundle typically includes:

- Server certificate and its corresponding private key.
- CA certificate or CA chain used by clients to verify the server.
- Client certificates and private keys if client certificate authentication is enabled.
- CRL or certificate revocation check settings if used in the environment.
- File paths, formats, key passphrases (if any), file ownership, and file permissions.

Variables such as `ssl_ca`, `ssl_cert`, `ssl_key`, and `tls_version` identify active settings. Inspect them with:

```sql
SHOW GLOBAL VARIABLES LIKE 'ssl_%';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
```

Back up certificates along with the required CA chain and private keys in encrypted storage with strict access controls. Copies must preserve file permissions suitable for the OS account running MySQL. A leaked private key can compromise authentication across the whole system, so never place keys in broadly shared folders or source repositories.

If OpenSSL is available, check certificate expiration and subject details:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates
```

This command reads only public certificate info; never run commands that print private key contents just to inspect them. Record expiration dates and schedule renewals before certificates expire. When rotating certificates, verify SAN/hostname, CA chain, TLS versions supported by clients, and MySQL restart/reload capability.

### Restoring TLS

Before starting MySQL, place certificate and key files in the right locations, restore ownership and permissions, and verify paths in configuration. Once the server is running, test TLS connections from a real client and verify accounts enforcing SSL/X509 behave as designed.

Never assume old certificates remain valid after recovery. Certificates may have expired, been revoked, or no longer match the new hostname. If hostname, address, or CA changes, issue and distribute fresh certificates following your lifecycle process.

## 5. Protecting Keyrings and Data Encryption Keys

If MySQL uses encryption for tablespaces, redo logs, undo logs, or binary logs, the server needs access to the corresponding keys. In many setups, MySQL uses a keyring component or plugin to manage keys; other environments integrate with an external KMS or HSM.

Inventory at least:

- Name and version of the keyring component/plugin or KMS/HSM mechanism in use.
- Configuration files used to load the component/plugin and keyring data path.
- File permissions, service identity, and parameters needed to connect to the KMS/HSM.
- Key identifiers, key versions, access policies, and rotation workflows.
- Active encryption features and which objects depend on keys.

The critical point is that **encrypted data copies and key backups must belong to the same recovery plan**. If tablespaces are encrypted and the keyring is lost, MySQL may be unable to decrypt data even though all tablespace files are present. When using KMS/HSM, retain key identifiers and access permissions so the recovery host can request decryption.

Never casually copy, edit, or replace keyring files while the server is running. Creating a consistent backup depends on the specific component/plugin and version; follow the backup procedure documented for that mechanism. A maintenance window, synchronized step, or dedicated backup mechanism may be required. Always test restoring the keyring in an isolated environment before relying on it in a real incident.

### Distinguishing MySQL Keys from Backup Encryption Keys

Keys in the MySQL keyring protect data encrypted by MySQL itself. Keys used to encrypt dump files, snapshots, archives, or backups at the storage layer may be completely separate keys. Clearly document which key protects which layer, where it is managed, and who is authorized to recover it.

Keep key backups or KMS access independent of where data backups are stored. If backups and decryption keys sit in the same account or storage zone that can be wiped at once, a single incident can destroy both. For KMS/HSM, protect service identities, IAM policies, credentials, and access-recovery procedures.

## 6. Organizing and Protecting the Backup Bundle

Classify artifacts before storing them:

| Artifact Type | Examples | Recommended Protection |
|---|---|---|
| Standard configuration | InnoDB parameters, port, paths, SQL mode | Version control in private repo; scan for secrets before committing |
| Sensitive configuration | Client passwords, tokens, external service credentials | Secret manager or dedicated secrets vault |
| Accounts and grants | User/role definitions, authentication metadata | Encryption, restricted read permissions, access auditing |
| Public certificates | CA certificate, server certificate | Store alongside expiration metadata and trust chain |
| Private keys and keyrings | Private keys, keyring data, authorized key exports | Separate security vault, encryption, and strict access control |
| KMS/HSM metadata | Key ID, policy, service identity, recovery instructions | Secure operational docs and periodic access permission audits |

Every backup bundle should carry an identifier, creation timestamp, MySQL version, source host, account/configuration scope, certificate version, key identifier, and appropriate checksums. Record links to the data backups and binary logs needed to recover to the desired point in time.

Apply separation of duties: someone permitted to read data backups should not automatically be able to read private keys or administrative secrets. Use encryption in transit and at rest, cap retention windows, audit access, and keep offline or independent-storage copies for ransomware scenarios.

## 7. Restoring in Dependency Order

Restoring components in order prevents starting the server while missing required keys or certificates:

1. **Prepare environment:** install the compatible MySQL version, plugins/components, libraries, and OS packages. Note any differences between source and target hosts.
2. **Restore OS identities and permissions:** create service accounts, directories, ownership, and ACLs for data directories, logs, certificates, and keyrings.
3. **Restore configuration:** apply option files, service configs, and startup flags; review paths, ports, system variables, and `SET PERSIST` values.
4. **Restore key mechanism:** configure the keyring or KMS/HSM access before MySQL opens encrypted data.
5. **Restore TLS:** place CA, certificates, and private keys in their exact locations; verify file permissions and hostname.
6. **Start and inspect server:** check error logs, plugin/component status, TLS variables, encryption status, and data readability.
7. **Restore data:** load data backups and apply binary logs if recovering to a specific point in time.
8. **Restore accounts and privileges:** recreate accounts/roles, grants, and default roles using exported statements; test privileges with real accounts.
9. **Verify application:** test TLS connections, authentication, critical queries, and writes in a test environment before opening traffic.

If restoring onto a new server, do not mechanically copy old server identity files. Specifically, inspect `auto.cnf` containing `server_uuid`; standalone instances or replicas require valid, unique identities. Follow the clone/replication procedure for your MySQL version.

Do not open application traffic immediately once `mysqld` reports it is running. The server must pass log, plugin, TLS, keyring, privilege, and data checks before returning to service.

## 8. Post-Restore Verification

Recovery is only considered passing once required functions work. Use this verification checklist:

- [ ] MySQL version and plugins/components match the recovery plan.
- [ ] MySQL starts with no configuration, file-permission, or component-loading errors.
- [ ] Key system variables match expected values; persisted values have been reviewed.
- [ ] Keyring/KMS/HSM is ready and can open encrypted data.
- [ ] Certificates are unexpired, hostnames and CA chains are valid, and clients connect over TLS cleanly.
- [ ] Accounts, authentication plugins, roles, grants, and default roles have been restored.
- [ ] `CURRENT_USER()` returns the expected account on login; `SHOW GRANTS` matches designed privileges.
- [ ] Application reads/writes intended objects properly and unauthorized operations are rejected.
- [ ] Fresh backups can be taken from the recovered host and shipped to an independent location.

Record actual durations per step and compare against RTO. Identify the final recovered data checkpoint and compare against RPO. One successful recovery validates the process, yet it must be repeated periodically and after major changes to versions, certificates, plugins, keyrings, or KMS.

## 9. Common Mistakes

- **Backing up only schemas and tables:** server has data but lacks configuration, accounts, certificates, or keys to run. Maintain an inventory of non-data components.
- **Overlooking included option files:** critical configuration pieces go unrecovered. Inventory actual config sources and service flags.
- **Omitting `mysqld-auto.cnf`:** variables set via `SET PERSIST` are lost or differ from source. Include this file in the plan and review it on restore.
- **Exporting accounts but forgetting default roles:** users can log in yet lack expected privileges. Record grants, role memberships, and default roles.
- **Copying raw system schemas across versions:** grant table or data dictionary structures are incompatible. Use supported account migration methods.
- **Losing private keys or keyrings:** encrypted data cannot be decrypted. Test key recovery alongside data backups.
- **Storing backups and decryption keys together:** a single incident can destroy both data and recoverability. Separate storage domains and access permissions.
- **Failing to preserve file permissions:** MySQL cannot read certificates or keyrings after restore. Restore file ownership and ACLs.
- **Not monitoring certificate expiration:** servers or clients stop connecting when certificates expire. Schedule expiration checks and renewals.
- **Not testing KMS/HSM permissions:** config files exist, yet the recovery host lacks the identity or policy to fetch keys. Test access using the real runtime identity.

## 10. Practice Exercise

In a test MySQL environment, build a recovery bundle for a hypothetical application schema:

1. Record MySQL version, relevant configuration variables, plugins/components, and option file sources.
2. Create two application accounts with distinct privileges, one shared role, and one default role; export `SHOW CREATE USER` and `SHOW GRANTS`.
3. Record TLS paths, CA, server certificate, certificate expiration, and file permissions. Do not include private keys in the lab report.
4. If InnoDB encryption is enabled in the environment, identify the keyring/KMS/HSM, supported backup procedure, and permissions needed for recovery.
5. Store metadata and required copies in an access-controlled test storage location; record checksums and timestamps.
6. Stand up a fresh test MySQL host and restore configuration, key mechanism, TLS, data, and accounts in dependency order.
7. Verify connectivity, `CURRENT_USER()`, `SHOW GRANTS`, encrypted data reads, and a valid application operation.

**Completion criteria:** configuration, accounts, and TLS connections are reproducible; encrypted data is readable; accounts receive exact privileges; and the operations team can point to the secure location of every copy and its recovery procedure.

## Conclusion

For reliable MySQL recovery, manage configuration, accounts, certificates, and encryption keys as mandatory components of the backup plan. Document versions and dependencies thoroughly, protect secrets with proper access controls, use supported export/backup mechanisms, and test recovery regularly. Only when the server can boot, decrypt data, authenticate users accurately, and serve the application over TLS do you have evidence that the backup bundle meets operational objectives.
