# Backing Up Configuration and Cleaning Up the Practice Environment Within Scope

While learning MySQL, you will repeatedly change configuration, create test databases, spin up containers or virtual machines, and then remove them to start fresh. Without proper documentation and backups of what needs to be kept, you risk losing data, forgetting a working configuration, or accidentally deleting another server on the same computer.

This lesson explains how to identify the components of a MySQL environment, back up configuration and data according to purpose, test restoring backups, and clean up the environment within a defined scope. Examples focus on MySQL Community Server on Linux, Docker Compose, and virtual machines. These principles apply to practice environments in the `DATABASE_MYSQL` module, covering table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query optimization, access control, and relational database operations.

After this lesson, you will be able to:

- Distinguish configuration backups, data backups, and VM snapshots.
- Record version, running configuration variables, accounts, and how MySQL is started.
- Save configuration files with appropriate permissions and know how to protect sensitive information.
- Create logical backups of a practice database and verify restorability.
- Clean up containers, virtual machines, or installed packages without accidentally impacting other environments.

## 1. Identifying the Exact Environment to Back Up or Clean Up

Before taking action, write an identification record. A single machine can simultaneously have a directly installed MySQL server, a MySQL container, and a VM running MySQL. Sharing a service name or port does not mean they share the same data.

Record at least the following details:

| Component | Information to Record | Example |
| --- | --- | --- |
| Server | Environment name, host or VM, connection address | `mysql-lab-local`, `127.0.0.1` |
| Version | Server version and distribution | MySQL Community Server 8.4 |
| Deployment | OS package, container, or VM | Docker Compose |
| Service/container | Service name, container name, or systemd unit | `mysql`, `mysql-lab`, `mysqld` |
| Connection | Host, port, socket, and network scope | `127.0.0.1:3307` |
| Data | Databases to keep and storage location | `labdb`, named volume `mysql_data` |
| Configuration | Config files, Compose file, systemd override | `/etc/mysql/`, `compose.yaml` |
| Dependencies | Applications, scripts, or lessons using the environment | demo app connecting to `labdb` |

Once logged in to MySQL, collect server details:

```sql
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    @@datadir AS data_directory,
    @@socket AS socket_path,
    @@log_error AS error_log;
```

Inspect key active configuration variables:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'bind_address',
    'character_set_server',
    'collation_server',
    'default_storage_engine',
    'innodb_buffer_pool_size',
    'log_error',
    'max_connections',
    'port',
    'sql_mode'
);
```

Save the results in your environment log. These are the values the server is actively using at query time; they serve as a baseline for comparison after restoring configuration. Some variables can be changed dynamically and do not necessarily reflect the configuration files on disk.

On Linux, identify the exact service unit before acting:

```bash
systemctl status mysql --no-pager
systemctl status mysqld --no-pager
```

Typically Ubuntu/Debian uses the `mysql` unit, while RHEL-compatible systems use `mysqld`. One of the two commands may report no unit found; that is not a reason to stop or delete a similarly named service. With Docker, identify the Compose project and service via `docker compose ps`; with a VM, verify the VM name in the virtualization software.

## 2. Distinguishing Types of Backups

No single backup artifact fits every purpose. Choose the backup type based on what needs to be recovered:

| Backup Type | Contents | When to Use | Limitations |
| --- | --- | --- | --- |
| MySQL configuration | Config files, service config, Compose files, version info, and runtime variables | Rebuilding how the server was configured | Does not contain database tables and rows |
| Logical backup | SQL statements creating schemas, data, and selected objects | Migrating databases, restoring exercises, or inspecting data | Requires compatible client and server to re-import; not a byte-for-byte copy of datadir |
| Physical backup | MySQL data files and metadata backed up via a consistent process | Recovering a server or large datasets | Must follow compatible tools, versions, and data-consistency procedures |
| VM/disk snapshot | Disk or full VM state at a point in time | Reverting a lab state or moving a VM | Not guaranteed to be a consistent database backup while MySQL is actively writing |

For routine practice exercises, back up the configuration and create a logical backup for databases you need to keep. VM snapshots are useful for reverting machine state, but they do not replace a database backup whose restore has been tested.

## 3. Backing Up MySQL Configuration

### 3.1. Identifying Configuration Files

Common locations include:

| Operating System | Common Locations |
| --- | --- |
| Ubuntu/Debian | `/etc/mysql/`, including `my.cnf` and included directories such as `conf.d/`, `mysql.conf.d/` |
| RHEL/Rocky/AlmaLinux | `/etc/my.cnf`, `/etc/my.cnf.d/` |
| Custom installation | Paths specified by startup flags or service configuration |

Do not assume there is only a single `my.cnf` file. One file can contain `!include` or `!includedir` directives to load configuration from other locations. Read these directives and inspect the service configuration before backing up.

On systemd, you can inspect the unit definition and overrides:

```bash
systemctl cat mysql
systemctl cat mysqld
```

Only save units or overrides that actually belong to the environment being backed up. Review the output carefully before sharing because some custom configurations may contain sensitive paths or environment variables.

`my_print_defaults mysqld` or `mysqld --print-defaults` can show options read from configuration files. Output may contain sensitive values if configuration files hold credentials; never post raw output to source repositories, forums, or public logs.

### 3.2. Creating a Configuration File Archive

On Ubuntu/Debian, if `/etc/mysql/` is the active configuration directory:

```bash
backup_dir="$HOME/mysql-lab-backups"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

sudo tar --acls --xattrs -czf "$backup_dir/mysql-config-$(date +%F).tar.gz" -C / etc/mysql
sudo chown "$(id -u):$(id -g)" "$backup_dir/mysql-config-$(date +%F).tar.gz"
chmod 600 "$backup_dir/mysql-config-$(date +%F).tar.gz"
```

On RHEL/Rocky/AlmaLinux, if the machine uses `/etc/my.cnf` and `/etc/my.cnf.d/`:

```bash
backup_dir="$HOME/mysql-lab-backups"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

sudo tar --acls --xattrs -czf "$backup_dir/mysql-config-$(date +%F).tar.gz" -C / etc/my.cnf etc/my.cnf.d
sudo chown "$(id -u):$(id -g)" "$backup_dir/mysql-config-$(date +%F).tar.gz"
chmod 600 "$backup_dir/mysql-config-$(date +%F).tar.gz"
```

The commands above are examples for common paths. Before running them, confirm the paths exist and include any custom config files, systemd overrides, or TLS certificates actually used by the environment. If a path in the command does not exist, adjust the source list for your machine; do not create empty placeholder files just to make the backup command succeed.

Verify the archive:

```bash
tar -tzf "$backup_dir/mysql-config-$(date +%F).tar.gz"
sha256sum "$backup_dir/mysql-config-$(date +%F).tar.gz"
```

Record the checksum alongside your backup log to detect file tampering or corruption during transfer. If the archive contains configs with passwords, private keys, or credentials, encrypt it before transferring to another storage location and restrict access to authorized personnel. Permission `600` protects the file on the local machine, but it does not replace encryption at rest or in transit.

### 3.3. Backing Up Container Configuration

With Docker Compose, configuration artifacts typically worth preserving include:

- `compose.yaml` or `docker-compose.yml`.
- MySQL configuration files mounted into the container.
- Custom Dockerfiles or initialization scripts if any.
- The image version or digest used.
- Project name, port mappings, and volume details.

The `.env` file may contain passwords. Never commit this file to Git and never copy it into an unencrypted archive. For recovery, store secrets in a secret manager or an encrypted, access-controlled backup. Document required variable names and how to supply them without recording secret values.

To record Compose state, use `docker compose ps` and `docker image inspect` on the active image. `docker compose config` is helpful for inspecting interpolated configuration, but its output can expose values from `.env`; inspect it only in a trusted environment and do not save or share unreviewed output.

Example recording image ID and service state:

```bash
docker compose ps
docker compose images
docker image inspect mysql:8.4 --format '{{.Id}} {{.RepoDigests}}'
```

Replace `mysql:8.4` with the actual image if the Compose file uses a different name. A tag like `8.4` may point to newer patches over time; saving the digest precisely identifies the image that ran.

## 4. Backing Up Practice Databases

Configuration backups do not protect tables and rows. If you need to preserve exercise results, create a separate database backup.

### 4.1. Logical Backup with mysqldump

Example backing up InnoDB database `labdb`:

```bash
mkdir -p "$HOME/mysql-lab-backups"
chmod 700 "$HOME/mysql-lab-backups"

mysqldump -u root -p \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --databases labdb \
  --result-file="$HOME/mysql-lab-backups/labdb-$(date +%F).sql"
```

The client will prompt for the password. Never write the password directly after `-p`, in connection URLs, or in scripts committed to Git. `--single-transaction` creates a consistent logical snapshot for transactional tables like InnoDB without locking entire tables throughout the dump. Avoid running DDL operations such as `ALTER TABLE`, `DROP TABLE`, or `RENAME TABLE` on the database during the dump; for non-transactional tables, separate locking or backup procedures are required.

Verify the file after dumping:

```bash
test -s "$HOME/mysql-lab-backups/labdb-$(date +%F).sql"
sha256sum "$HOME/mysql-lab-backups/labdb-$(date +%F).sql"
```

An existing SQL file does not prove restorability. The critical verification step is importing it into a separate MySQL instance or a differently named test database, then verifying schema and data.

### 4.2. Recording Account Privileges

If the exercise created dedicated accounts, record usernames, hosts, and granted privileges. For example:

```sql
SHOW GRANTS FOR 'labuser'@'localhost';
```

Save the output alongside your configuration record if you need to rebuild privileges. Do not directly copy system tables in the `mysql` schema as an ad-hoc way to migrate accounts across versions. `SHOW CREATE USER` may display credential hashes; if you genuinely need to save that output, protect it as a secret. When restoring, create accounts with authentication plugins and new passwords compliant with policy, then re-grant least-privilege permissions.

### 4.3. When Physical Backups Are Needed

Never use `cp` or `tar` to copy the datadir of a running server directly and treat it as a complete backup. MySQL may be modifying multiple data files and logs concurrently. Such a copy can be inconsistent.

For small lab exercises, `mysqldump` is usually easy to understand and verify. When physical backups are needed, use a tool supported for your specific version and configuration, such as MySQL Enterprise Backup or Percona XtraBackup within their compatibility scope. A file-level cold backup requires stopping the server cleanly before copying and must preserve ownership, permissions, and all required files. Storage snapshots must follow procedures that guarantee data consistency.

## 5. Testing Restore Before Cleaning Up the Environment

A backup only has operational value when you know how to restore it. Test on a separate instance or VM to avoid overwriting an active database.

### 5.1. Verifying and Restoring Configuration

First list the archive contents:

```bash
tar -tzf "$HOME/mysql-lab-backups/mysql-config-YYYY-MM-DD.tar.gz"
```

Replace the date with the actual filename. Inspect the listing to make sure the archive contains the expected configuration directory. When restoring configuration on an active server, schedule maintenance and stop the right service before replacing files. Never extract an unverified archive directly into `/`.

With MySQL 8.0 or later, you can validate configuration before restarting using:

```bash
sudo mysqld --validate-config
```

This checks the configuration that `mysqld` reads under its startup environment. If the configuration uses custom paths or option files, ensure the validation command reads the exact target file. Once validated, restart the right unit and inspect the logs:

```bash
sudo systemctl restart mysql
sudo systemctl status mysql --no-pager
sudo journalctl -u mysql -n 100 --no-pager
```

On systems using the `mysqld` unit, substitute the corresponding unit name. After the server starts, re-run the `SELECT VERSION()` and `SHOW GLOBAL VARIABLES` statements from section 1 to compare against your pre-backup record.

### 5.2. Restoring an SQL Dump

On a test instance, prepare a clean target environment and import the dump:

```bash
mysql -u root -p < "$HOME/mysql-lab-backups/labdb-YYYY-MM-DD.sql"
```

Because the example dump used `--databases labdb`, the file contains statements to create/select the database. Only import into an explicitly verified target instance; if a database with the same name already exists, understand the exact impact of statements in the dump before running it.

After importing, verify:

```sql
SHOW DATABASES;
USE labdb;
SHOW TABLES;
SELECT COUNT(*) FROM environment_check;
```

Replace `environment_check` with an actual table present in the backup. Cross-check table counts, sample row counts, views, triggers, routines, and required events. If a demo application can connect, run a test read and write using the application account.

### 5.3. Restore Verification Log

Record the test date, source and target MySQL versions, backup filename, checksum, import result, and verified objects. If the restore fails, record the error message and fix the root cause before cleaning up the source environment. Never delete the only working environment merely because a backup file was created.

## 6. Cleaning Up a Docker Environment Within Scope

Docker Compose can manage multiple projects on the same machine. Before cleaning up, change into the exact directory containing the Compose file and verify the project/services:

```bash
docker compose ps
docker compose config --services
docker compose images
```

If using `-p` or `COMPOSE_PROJECT_NAME`, note the active project name. Volume names are typically generated by Compose from the project name and logical volume name; never guess a name and delete it.

### 6.1. Stopping Containers While Keeping Data

To stop the lab environment:

```bash
docker compose stop
```

To remove containers and networks created by the project while preserving named volumes:

```bash
docker compose down
```

This is the right choice when you want to recreate containers while preserving the database. Afterward, you can run `docker compose up -d` to bring the service back up from configuration.

### 6.2. Intentionally Deleting Lab Data

The named volume contains the MySQL datadir. Before deleting, identify the volume belonging to the right project and inspect it:

```bash
docker volume ls
docker volume inspect verified_volume_name
```

Once you have confirmed the backup restores cleanly and truly want to delete the current project's data, run from the exact Compose directory:

```bash
docker compose down -v
```

This command deletes named volumes declared in Compose and anonymous volumes attached to the project's containers. Data inside those volumes is deleted and cannot be recovered by running `up` again. Volumes declared as external have their own lifecycle and are not deleted by Compose this way.

Never run `docker system prune --all --volumes` to clean up a single lab exercise. Prune can affect images, containers, networks, and volumes outside the project you are working on. If you need to remove a specific volume, verify its name and contents with `docker volume inspect`, confirm no other container uses it, and only then delete that exact volume.

## 7. Cleaning Up a Virtual Machine Environment Within Scope

Before deleting a VM, verify the VM name, virtual disk directory, snapshots, shared folders, and whether any other service depends on the VM.

Safe procedure:

1. Log in to the VM and check whether MySQL is running; finish dumping any data you need to keep.
2. Stop MySQL cleanly or shut down the guest OS normally.
3. If needed for reuse, export the VM or copy the virtual disk and save version, network, RAM, CPU, and checksum details alongside it.
4. Confirm the export can be recognized or imported on the target environment if migrating.
5. Delete the exact selected VM in your virtualization software. Only choose to delete its virtual disks and snapshots once you have confirmed they are no longer needed.
6. Review NAT, port forwarding, and shared folder settings. Remove only rules dedicated to this VM; do not delete virtual networks used by other VMs.

Snapshots are useful for reverting to a previous state, but snapshots are not always independent of the base disk. If you want to keep a VM long-term, export or back up the full disk/snapshot chain according to your virtualization platform's instructions rather than taking a snapshot and deleting the VM.

## 8. Uninstalling MySQL Installed via OS Packages

Removing MySQL packages can impact running services and applications sharing the server. Perform this only on lab machines you administer after verifying the exact packages, units, datadir, and databases to keep.

Before removing, record the list of related packages and verify the service name:

```bash
# Ubuntu/Debian
dpkg -l | grep -E 'mysql|mariadb'
systemctl status mysql --no-pager

# RHEL/Rocky/AlmaLinux
rpm -qa | grep -Ei 'mysql|mariadb'
systemctl status mysqld --no-pager
```

After backing up and verifying the exact server, stop the service and instruct the package manager to remove the specific server package. For example:

```bash
# Ubuntu/Debian: review the list of packages to be removed before confirming
sudo apt remove mysql-server

# RHEL/Rocky/AlmaLinux: replace with the exact verified package name
sudo dnf remove mysql-community-server
```

Package names can vary by repository and version. Read the list of changes displayed by the package manager carefully; abort if the action intends to remove components outside the lab environment. Removing a package generally does not delete all configuration and data.

Only purge or delete data when the goal is completely removing the lab environment and backups have already been verified. Configuration usually resides under `/etc/mysql/` or `/etc/my.cnf*`; data usually resides under the datadir returned by `@@datadir`, commonly `/var/lib/mysql`. Logs may reside elsewhere. Never run `rm -rf` with guessed paths or wildcards to clean up MySQL. Verify every path, owner, and content before deleting; when in doubt, keep it for later inspection.

## 9. Checklist Before Confirming Cleanup Is Complete

Check off each item after verifying:

- [ ] Identified the exact server, Compose project, or VM to handle.
- [ ] Recorded MySQL version, deployment method, port, datadir, and key settings.
- [ ] Backed up configuration files and protected any archive containing secrets.
- [ ] Backed up databases to keep using an appropriate method.
- [ ] Verified checksums and test-restored the backup in a target environment.
- [ ] Identified volumes, virtual disks, snapshots, packages, and data directories belonging to the exact environment.
- [ ] Stopped or removed only the selected resources.
- [ ] Verified other MySQL environments remain running and unaffected.
- [ ] Documented what was kept, what was removed, and where backups are stored.

## 10. Practice Exercises

1. Set up a MySQL lab environment and record `VERSION()`, `@@port`, `@@datadir`, and key configuration variables.
2. Locate MySQL configuration files and included files. Create a configuration archive, set restricted permissions, and generate a checksum.
3. Create a `labdb` database with at least one InnoDB table, insert sample data, and back it up using `mysqldump`.
4. Spin up another test MySQL instance, restore the dump into it, and verify tables, data, and practice account privileges.
5. If using Docker Compose, run `docker compose down` followed by `up -d`; verify data remains intact thanks to the volume. Then identify which volume would be deleted if you ran `down -v`.
6. Create an identification record for a VM or package installation. List resources to keep and resources to remove; explain how to verify no other MySQL instance on the same machine is affected.
7. Upon completion, write a short log containing version, backup date, checksum, restore result, and cleanup scope.

## 11. Completion Criteria

You have completed this lesson when you can pinpoint exactly which MySQL environment is being managed, back up configuration and data through two separate procedures, prove that backups are restorable, and clean up containers, VMs, or installed packages within the chosen scope. You should also be able to explain why deleting a container does not necessarily delete a volume, why snapshots do not always replace database backups, and why resources must be verified before deletion.
