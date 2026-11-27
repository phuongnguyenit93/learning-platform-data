# Managing systemd/Service or Container Lifecycles by Environment

MySQL requires an operational procedure suited to how each environment is deployed. On Linux servers, systemd typically manages the mysqld process as a service. On Windows, MySQL runs as a Windows Service. In container environments, Docker or an orchestration platform is responsible for creating, stopping, restarting, and monitoring containers.

Start, stop, and restart operations appear simple, yet they directly affect data integrity, recoverability, configuration, logs, access permissions, and downtime. In particular, container lifecycles are tied to persistent volumes: containers may be replaced frequently, while database data must persist independently of the container.

In the **DATABASE_MYSQL** module, this lesson covers managing the MySQL service on Linux and Windows, operating MySQL with Docker Compose, deploying environment-specific configuration, checking health/readiness, reading logs, protecting secrets, backing up, and upgrading safely.

## 1. Choosing an Operational Model by Environment

Common MySQL management models:

| Environment | How MySQL Runs | Lifecycle Manager |
|---|---|---|
| Linux host with package install | `mysqld` process on the host | systemd and package service unit |
| Windows host | Background `mysqld` process | Windows Service Manager |
| Personal development machine | Container or local package | Docker Compose or service manager |
| Ephemeral CI/test | Container used for a single test run | Pipeline/Compose runner |
| Staging | Service or container closely matching production | systemd, Compose, or orchestration platform |
| Production | Monitored service with backup and recovery | systemd or container/orchestrator platform |

No single management command fits everywhere. You must clearly determine:

- What is responsible for starting MySQL after a reboot?
- Which datadir or volume stores the data?
- Which configuration files are loaded?
- Are logs written to journald, files, or a container log driver?
- How does the application verify the database is ready?
- Who manages secrets and accounts?
- What are the backup, restore, upgrade, and rollback procedures?

A development environment may prioritize fast iteration. Production additionally requires change control, downtime planning, monitoring, backups, and a recovery plan.

## 2. MySQL Service Lifecycle on Linux with systemd

When installing MySQL from OS packages or the Oracle MySQL repository, the package usually provides a service unit. The service name can vary by distribution and package:

- Debian/Ubuntu commonly uses the name `mysql`.
- Some RPM distributions commonly use the name `mysqld`.

Check the actual service name before taking action:

```bash
systemctl list-unit-files | grep -E 'mysql|mysqld'
systemctl status mysql
```

In the example, `mysql` is used if that is the unit name of the installed package; if the system uses `mysqld`, replace the name in the status command with `mysqld`. Only one of these names may exist. If not found, check the unit name provided by the installed package rather than manually creating a conflicting service.

### 2.1. Distinguishing Running State from Auto-Start State

systemd manages at least two aspects that must be distinguished:

- Active state: whether the service is currently running, stopped, failed, or transitioning.
- Enablement state: whether the service is configured to start automatically with a target at boot.

A service can be running without being enabled. Conversely, a service can be enabled while currently stopped.

Check:

```bash
systemctl is-active mysql
systemctl is-enabled mysql
systemctl status mysql
```

Start immediately and enable auto-start at boot:

```bash
sudo systemctl enable --now mysql
```

Disable auto-start without stopping the running service:

```bash
sudo systemctl disable mysql
```

Stop the service and disable auto-start:

```bash
sudo systemctl disable --now mysql
```

Enable and disable control behavior on the next boot; start, stop, and restart affect the current state.

### 2.2. Start, Stop, and Restart

Basic commands:

```bash
sudo systemctl start mysql
sudo systemctl stop mysql
sudo systemctl restart mysql
sudo systemctl status mysql
```

Restart stops the service and then starts it again. With a package-provided MySQL unit, the service manager uses the stop/start mechanism defined by the package. MySQL executes a controlled shutdown to close connections, finish required work, and flush data durably.

Do not use `kill -9` as a routine stop action. SIGKILL gives mysqld no chance to shut down cleanly; InnoDB may have to run crash recovery at the next startup, and recovery time can be long. Only use forceful termination per an incident runbook when the consequences are understood.

You can request a MySQL shutdown using the administrative utility:

```bash
mysqladmin --defaults-extra-file=/path/to/client.cnf shutdown
```

The account needs the `SHUTDOWN` privilege. The client option file must be protected by read permissions, and passwords must not be placed directly in shell history.

### 2.3. Inspecting the Service Unit

Read the unit currently used by systemd:

```bash
systemctl cat mysql
systemctl show mysql -p FragmentPath -p DropInPaths
```

A package unit may declare:

- User and Group running the process.
- Executable path and startup arguments.
- How to stop the process.
- Restart policy.
- Resource limits and sandboxing.
- Dependencies on filesystems or networking.

Do not replace a package unit with a custom-written file without fully understanding how the package manages datadir, socket, PID file, runtime directory, and permissions. If overrides are needed, prefer a systemd drop-in:

```bash
sudo systemctl edit mysql
```

After modifying a unit or drop-in, tell systemd to reload its definitions:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mysql
```

`daemon-reload` only reloads unit definitions. It does not replace restarting mysqld when MySQL configuration files change. Nor do you need to run `daemon-reload` merely because you edited a `my.cnf` configuration file.

### 2.4. Reload vs. Restart

`systemctl reload mysql` only works if the unit defines a suitable reload action. Not every package or unit provides this operation.

MySQL has some configuration variables that can change at runtime and some that are read only at startup. For runtime variables, appropriate SQL statements can be used; for startup-only variables, edit configuration or persisted values and restart. Do not assume calling `systemctl reload` causes mysqld to reread all configuration files.

Before making changes, check the variable's attributes in the documentation for the exact version and verify the actual value with SHOW VARIABLES.

## 3. Configuring MySQL on the Server

MySQL can read configuration from multiple option files depending on the OS, installation method, and startup arguments. Common locations include:

| Environment | Common Locations |
|---|---|
| Linux package | `/etc/my.cnf`, `/etc/mysql/my.cnf` |
| Linux include directory | `/etc/mysql/conf.d/`, `/etc/mysql/mysql.conf.d/` |
| Windows | `my.ini` in the installation directory or ProgramData |
| Docker image | `/etc/mysql/conf.d/` or a mounted configuration path |

These are common locations, not a fixed list for every installation. Verify how the current instance is started and which option files are actually read.

### 3.1. Splitting Configuration by Purpose

Example configuration file:

```ini
[mysqld]
port = 3306
bind-address = 127.0.0.1
max_connections = 200
innodb_buffer_pool_size = 2G
slow_query_log = ON
long_query_time = 1
```

The parameters above are illustrative examples only. Do not copy resource values into production without measuring RAM, workload, connection counts, and hardware capacity.

Configuration can be split into smaller grouped files:

- `server.cnf`: general server parameters.
- `innodb.cnf`: InnoDB configuration.
- `logging.cnf`: general log, slow query log, and error log.
- `replication.cnf`: replication settings if applicable.

Only place files inside an include directory that the instance actually reads. Avoid declaring the same option in multiple places because load order may produce an unexpected final value.

### 3.2. Validating Configuration Before Restarting

Some MySQL versions support validating configuration with the `--validate-config` option. You can use the binary and option files matching the installed package:

```bash
mysqld --validate-config
```

Depending on the installation, you may need to pass the exact option file path or run as an account with read permissions on the configuration files. Syntax/configuration validation does not replace runtime testing and does not guarantee every change suits the workload.

You can inspect the default options parsed for the program with:

```bash
my_print_defaults mysqld
```

After the server starts, check the active values:

```sql
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
```

### 3.3. Runtime, Startup-Only, and Persisted Configuration

Not every MySQL variable can be changed while the server is running. Categorize them:

- Dynamic variable: can be changed at runtime in GLOBAL or SESSION scope if permitted by documentation.
- Read-only/startup-only variable: only takes effect when mysqld starts.
- Persisted variable: can be saved via the SET PERSIST mechanism to persist across subsequent restarts, if supported by the variable.

Example changing and persisting a supported variable:

```sql
SET PERSIST max_connections = 300;
```

SET PERSIST writes the value to `mysqld-auto.cnf`. This file is managed by MySQL; do not edit it directly with a text editor. Persisted values can take higher precedence than settings in option files at server startup, so configuration sources must be managed clearly.

If you only want to change the current run, use SET GLOBAL when the variable allows it. If you need to set a value for the next startup without changing current runtime, check SET PERSIST_ONLY and the variable's limits. Use RESET PERSIST to remove a persisted value for the exact variable name when rolling back.

Do not mix config files, SET GLOBAL, and SET PERSIST without documenting the source of truth. A runbook should record: desired value, management source, scope, application time, and rollback method.

## 4. Managing MySQL with Windows Service

On Windows, MySQL is typically installed as a service named by the installer or administrator, such as `MySQL80`. The service name does not necessarily match the display name or binary version.

Check the service:

```powershell
Get-Service -Name '*MySQL*'
Get-Service -Name 'MySQL80'
```

Start, stop, or restart:

```powershell
Start-Service -Name 'MySQL80'
Stop-Service -Name 'MySQL80'
Restart-Service -Name 'MySQL80'
Get-Service -Name 'MySQL80'
```

You can use `sc.exe query` to inspect service status:

```powershell
sc.exe query MySQL80
```

`MySQL80` in the example must be replaced with the actual service name. The service account must have access permissions for the datadir, configuration files, logs, certificates, and related directories.

### 4.1. my.ini File and Service Arguments

MySQL on Windows typically uses `my.ini`. Its path may be passed on the service command line or resolved via the installation's option-file search mechanism.

Inspect the service configuration using Windows administrative tools and verify the binary path, `defaults-file`, datadir, and logs. Do not move the datadir or change the service account without updating ACLs and checking read/write permissions.

After editing startup-only parameters, restart the service during an appropriate maintenance window. Afterward, confirm the server is operational and read the error log.

## 5. MySQL Lifecycle in Docker and Docker Compose

Containers package mysqld along with its runtime environment. Docker manages the container, while MySQL data must be stored on a persistent volume.

A container can be deleted and recreated when updating an image. If the datadir resides solely in the container's writable layer, data can be lost when the container is removed. Therefore, mount a volume at `/var/lib/mysql`.

### 5.1. Sample Compose Service

Example Compose configuration for development or staging:

```yaml
services:
  db:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: appdb
      MYSQL_USER: appuser
      MYSQL_PASSWORD_FILE: /run/secrets/db_app_password
      MYSQL_ROOT_PASSWORD_FILE: /run/secrets/db_root_password
    secrets:
      - db_app_password
      - db_root_password
    volumes:
      - mysql_data:/var/lib/mysql
      - ./mysql/conf.d:/etc/mysql/conf.d:ro
    ports:
      - "127.0.0.1:3306:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

volumes:
  mysql_data:

secrets:
  db_root_password:
    file: ./secrets/db_root_password.txt
  db_app_password:
    file: ./secrets/db_app_password.txt
```

This is an illustrative example for the official MySQL image and Docker Compose file secrets support. Before using it, consult the documentation for your exact image tag, Compose version, and platform secrets mechanism.

Key points to note:

- Pin the image to a tested version; for production, consider a specific patch tag or digest for exact image reproducibility.
- The `mysql_data` volume preserves the datadir across container lifecycles.
- The configuration directory is mounted read-only so the container cannot write back to host config files.
- The port is bound only to loopback in this example; production typically does not need to publish the DB port to the host if the application shares the Docker network.
- Secret files must never be committed to Git or baked into images.
- The `unless-stopped` restart policy helps Docker restart the container after daemon or host restarts, according to the chosen policy.

If the application also runs in Compose, you can make the application wait for the database to become healthy:

```yaml
services:
  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
```

`depends_on` with `service_healthy` coordinates initial startup timing. The application must still handle reconnection and retries if the database later disconnects.

### 5.2. Starting, Stopping, and Inspecting Containers

Common commands:

```bash
docker compose up -d db
docker compose ps
docker compose logs --tail=100 db
docker compose logs -f db
docker compose stop db
docker compose start db
docker compose restart db
```

- `up -d` creates or updates the container and runs it in the background.
- `stop` stops the container while keeping both container and volumes.
- `start` starts a stopped container again.
- `restart` restarts an existing container.
- `logs` reads stdout/stderr collected by Docker.

Check MySQL inside the container:

```bash
docker compose exec db mysqladmin ping -h 127.0.0.1 --silent
```

`ping` confirms the server responds. For application-level readiness, also check SQL connectivity using the application account and a simple query, since the process may be running while privileges, schemas, or application dependencies are not yet ready.

### 5.3. Removing Containers Does Not Mean Deleting Data

An important distinction:

```bash
docker compose down
```

This command stops and removes containers and networks managed by Compose; named volumes are normally preserved.

The following command can also delete named volumes:

```bash
docker compose down --volumes
```

If the volume holds `/var/lib/mysql`, database data can be deleted. Only run commands with `--volumes` when the intent is to destroy that environment's data and you have confirmed backups or that the data is disposable. Never include this command in daily restart runbooks.

### 5.4. Initialization Variables Apply Only to a New Datadir

Variables such as MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD, and MYSQL_ROOT_PASSWORD in the official image are generally used when initializing an empty datadir.

Once a volume already contains an initialized database, changing environment values in Compose does not automatically change existing MySQL passwords or recreate the database. Update accounts with appropriate administrative SQL statements, then update the secrets used by the application and test connectivity.

Never delete a volume just to trigger initialization variables again if the volume holds data you need to keep.

## 6. Health Checks, Readiness, and Recoverability

A running process does not guarantee the database is ready to serve applications. Distinguish:

- Process/liveness: the `mysqld` process is running and responding.
- Readiness: the server accepts connections and executes required queries.
- Application health: the application connects with its own account, has proper privileges, and can access required schemas.

### 6.1. Liveness Checks

You can use:

```bash
mysqladmin ping --silent
```

Or inside a container:

```bash
docker compose exec db mysqladmin ping -h 127.0.0.1 --silent
```

Liveness is useful for detecting an unresponsive server. It does not prove that migrations have run, the application account has privileges, or all dependencies are ready.

### 6.2. SQL Readiness Checks

Use a connection with appropriate configuration and credentials:

```sql
SELECT 1;
SELECT CURRENT_TIMESTAMP;
SELECT DATABASE();
```

Applications should retry connections with bounded backoff when the database has just started or is failing over. Avoid rapid continuous retries that can overload the server during recovery.

### 6.3. Restart Policies Do Not Replace Monitoring

A Docker restart policy can automatically restart a container after the process exits or the Docker daemon restarts. It does not solve:

- Configuration errors causing mysqld to fail startup repeatedly.
- Corrupted datadir or missing permissions.
- Full disks.
- Incorrect secrets.
- A running server unable to process queries.
- Applications failing to reconnect.

Monitor restart loops, health status, error logs, disk usage, and live connections. Never configure infinite restarts without alerting and a runbook.

## 7. Logs and Diagnostics When the Service Fails to Start

Logs are the first source of truth when MySQL fails to start, crashes, or restarts repeatedly.

### 7.1. Linux systemd and journald

Check status:

```bash
systemctl status mysql --no-pager
```

Read recent logs:

```bash
journalctl -u mysql -n 200 --no-pager
journalctl -u mysql -f
```

If the service is named `mysqld`, substitute the corresponding unit name. Some packages write the error log to a separate file rather than sending everything to journald.

### 7.2. Container Logs

```bash
docker compose logs --tail=200 db
docker compose logs -f db
docker inspect <container_name>
```

Check exit code, restart count, health status, mounts, and networking when a container keeps exiting.

### 7.3. MySQL Error Log

You can check the error log location:

```sql
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'pid_file';
SHOW VARIABLES LIKE 'socket';
```

If mysqld fails to start, you cannot run SHOW VARIABLES; in that case, read the error log at the configured path or the logs collected by the service manager/container.

Do not share raw logs externally without checking for sensitive details such as internal hostnames, usernames, file paths, queries containing personal data, or connection details.

## 8. Privileges, Secrets, and Network Boundaries

Good service management restricts process privileges and database access paths.

### 8.1. Service Account

On Linux, packages usually create a dedicated system account such as `mysql`. mysqld should not run as root in normal operation. The service account needs least-privilege access to:

- Datadir.
- Error log and configured log files.
- Unix socket, PID file, and runtime directory.
- TLS certificates/keys if MySQL uses TLS.
- Configuration files it must read.

Do not grant write permissions across the entire filesystem just to resolve a permission error. Identify the exact file or directory being denied.

### 8.2. Password and Secret Management

Avoid placing passwords on the command line:

```bash
mysql -uroot -pMySecretPassword
```

This can expose secrets in shell history or process lists. Use `-p` for interactive prompting, an option file with restricted permissions, a secrets manager, or Docker/Kubernetes secrets appropriate for the environment.

In Compose, secret files must be protected on the host and excluded from source control. Provide each service only the secrets it requires. Do not mount the root password into an application if the application only needs a limited-privilege database account.

### 8.3. Network Boundaries

- Bind ports only to required interfaces.
- In container environments, prefer a private network between app and database.
- Do not publish port 3306 to the Internet.
- Use firewalls/security groups to restrict access sources.
- Enable TLS when connecting over untrusted networks.
- Use dedicated per-application accounts with appropriate host patterns.

If MySQL serves only applications on the same host, consider a Unix socket or binding to loopback. If the app runs in another container, use the service name on the internal network rather than hardcoding container IPs.

## 9. Backup, Restore, and Persistent Storage

Service/container lifecycles must be integrated with a data protection plan.

### 9.1. Datadir Lives Outside the Container Lifecycle

For containers, mount a persistent volume to the datadir:

```yaml
volumes:
  - mysql_data:/var/lib/mysql
```

Never store a database solely in the container's writable layer. Never accidentally mount an empty host directory over an existing datadir, as this can cause mysqld to start with a different directory or fail with permission/initialization errors.

For services installed directly on the host, clearly identify the datadir and ensure backups cover data, required logs, configuration, and key material according to policy.

### 9.2. Logical Backups

You can use `mysqldump` for logical data exports:

```bash
mysqldump --single-transaction --routines --triggers --events appdb > appdb.sql
```

`--single-transaction` creates a consistent snapshot for transactional tables such as InnoDB under appropriate conditions. If non-transactional tables or concurrent DDL exist, a separate locking/backup plan is required. Evaluate size, duration, character sets, privileges, and full-instance backup needs.

Do not write passwords directly on the command line. Use a client option file or secret mechanism.

### 9.3. Physical Backups and Volume Snapshots

Physical backups or volume snapshots must coordinate with MySQL state and supported backup tools. Do not raw-copy a running datadir as though it were a consistent backup. Use an appropriate physical backup tool, a controlled snapshot procedure, or a clean shutdown before copying when appropriate.

A backup is only valuable once restore has been tested. Periodically rehearse recovery in an isolated environment, verifying data, privileges, configuration, and recovery time.

### 9.4. Stop/Restart Is Not a Backup

A clean shutdown lets InnoDB flush required state and close files properly. However, it does not create an independent backup copy. A failed disk or accidental volume deletion can still cause data loss.

Maintain backups outside the datadir/volume with retention, encryption, restricted access, and regular restore verification.

## 10. Upgrading the MySQL Service or Container

Upgrading the server can change the data dictionary, data formats, optimizer behavior, or configuration requirements. Do not treat changing an image tag or replacing a binary as a routine restart.

General procedure:

1. Identify the current version, target version, and supported upgrade path.
2. Read release notes and upgrade notes for the relevant versions.
3. Check plugins, components, replication, backup tools, and application drivers.
4. Check configuration so removed or behavior-changed options are not used.
5. Take a backup and verify it can be restored.
6. Test the upgrade on a copy of the data in staging.
7. Schedule a maintenance window or cutover/failover strategy.
8. Pin the image/package version and perform the upgrade.
9. Monitor the error log, service status, and SQL verification results.
10. Run smoke tests and test workloads.
11. Monitor latency, replication lag, error rates, and resource usage.
12. Execute the tested rollback plan if acceptance criteria fail.

Do not downgrade the binary and directly open an upgraded datadir if MySQL procedures do not support it. Rollback usually requires restoring a backup or failing back to an older instance with compatible data, rather than merely swapping image tags.

### 10.1. Updating a Container Image

You can pull the pinned image and recreate the service:

```bash
docker compose pull db
docker compose up -d --no-deps db
docker compose ps
docker compose logs --tail=200 db
```

The sample commands do not automatically provide backups, compatibility checks, or rollback. Before running in production, complete the upgrade steps and confirm the volume is preserved.

### 10.2. Updating Packages on the Host

For MySQL installed via a package manager, follow the supported upgrade workflow for your OS and repository. Do not manually swap binaries while the service is running. After package updates, verify the service unit, configuration files, error log, version, and database state.

## 11. Deployment Workflow by Environment

| Environment | Configuration and Lifecycle | Required Controls |
|---|---|---|
| Local development | Docker Compose or package; reproducible data | Dedicated volume, test secrets, loopback port |
| CI/test | Ephemeral container, schema/fixture initialization | Pinned version, health check, clean teardown |
| Staging | Matches production in version, config, and topology | Migration rehearsal, backup/restore test, smoke test |
| Production | systemd or orchestrator, persistent datadir | Change window, monitoring, backup, access control, rollback |

Configuration across environments should differ only in intentional values such as resources, endpoints, secrets, TLS, and log retention. Avoid running local/staging on a MySQL version far removed from production, as SQL behavior, optimizer plans, or plugins may differ.

Do not bring production data into development environments without masking procedures and access controls.

## 12. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| systemd reports failed | Bad config, datadir permissions, port in use, disk full | status, journalctl, error log, filesystem |
| Container restarts continuously | mysqld exited, wrong secret, config error, volume permissions | compose logs, inspect, health status, mounts |
| Service runs yet app cannot connect | Network, bind-address, firewall, user/host grant, TLS | Connect from the right network, check account and endpoint |
| MySQL takes long to start | InnoDB crash recovery, large redo log, slow storage | Error log, disk I/O, recovery progress |
| Changed environment yet password unchanged | Datadir was already initialized previously | Change password via SQL and update secret |
| Data lost after recreate | Datadir was in container layer or volume was deleted | Check mounts and backups; never run `down --volumes` |
| `systemctl reload` has no effect | Unit does not support reload or variable requires restart | Check unit and variable scope |
| Service starts yet health check fails | Server not ready yet, wrong host/socket, or privilege issue | Check logs and test SQL connection with the right account |
| Fails to start after upgrade | Removed option, incompatible plugin, data dictionary error | Upgrade log, error log, release notes, and restore plan |

When investigating, capture state before restarting repeatedly. Restart loops can obscure the timestamp of the initial failure and add extra load on storage.

## 13. Controlled MySQL Restart Runbook

A production restart procedure should have clear steps:

**Before restart:**

1. Confirm instance, service name, environment, and responsible owner.
2. Identify the reason for restart: configuration, patching, incident, or maintenance.
3. Check replicas/failover if applicable; confirm which node is permitted to restart.
4. Notify applications or drain traffic per procedure.
5. Verify the latest backup and restore-test status.
6. Confirm sufficient disk space and no ongoing recovery or critical DDL.
7. Record version, uptime, error log, and connection status.

**During restart:**

1. Stop the service via systemd/Windows Service or container orchestration command.
2. Wait for shutdown to complete; do not `kill -9` unless handling an emergency.
3. Apply approved changes.
4. Start the service/container again.
5. Monitor error logs and health status.

**After restart:**

1. Confirm the process/service is active.
2. Confirm MySQL accepts connections.
3. Run `SELECT 1` with the application account.
4. Verify schemas, privileges, TLS, and connectivity from the application network.
5. Check replication, event scheduler, or plugins if used by the instance.
6. Run smoke tests and monitor latency/error rates.
7. Record results, downtime duration, and configuration changes.

If health/readiness fails, halt the rollout and switch to the incident handling or prepared rollback procedure. Do not restart in an endless loop hoping the error disappears on its own.

## 14. Operational Mistakes to Avoid

| Mistake | Risk | Proper Practice |
|---|---|---|
| Using `kill -9` for routine stops | Skips clean shutdown, can prolong crash recovery | Use service manager or `mysqladmin shutdown` |
| Confusing `enable` with `start` | Service fails to auto-start after reboot or runs unexpectedly | Check active and enabled states separately |
| Running `daemon-reload` after every `my.cnf` edit | Does not make mysqld reload config | Restart when startup variables change; `daemon-reload` is for units only |
| Assuming `systemctl reload` is always supported | New configuration is not applied | Check unit and variable scope |
| Storing datadir only in the container layer | Data lost when container is removed | Attach a persistent volume |
| Running `docker compose down --volumes` as routine cleanup | Deletes the database volume | Use `stop`/`down` without `--volumes` when preserving data |
| Changing `MYSQL_ROOT_PASSWORD` in Compose to rotate password | Init env vars do not modify already-created accounts | Change password inside MySQL and update secret |
| Putting passwords on the command line or in Git | Credential exposure | Secrets manager, ACL-protected option file, or Docker secrets |
| Publishing 3306 on all interfaces | Expands attack surface | Private network, loopback, firewall, and TLS |
| Using the `latest` tag in production | Unplanned upgrades | Pin version/digest and test first |
| Copying a running datadir as a backup | Copy may be inconsistent | Appropriate backup tool or clean shutdown |
| Rolling back solely by swapping image tags | Older binary may fail to read upgraded datadir | Restore backup or follow supported downgrade procedure |

## 15. Operational Checklist

**Service and configuration:**

- Confirm exact service name or Compose project/service.
- Distinguish active state from enablement/restart policy.
- Identify exact option files and include directories.
- Record configuration source: file, SET GLOBAL, or SET PERSIST.
- Check dynamic/startup-only variables before restarting.
- Use `daemon-reload` when changing units; do not confuse with reloading MySQL.
- Run the service under a least-privilege account.

**Containers and data:**

- Pin tested image versions.
- Mount a persistent volume to the datadir.
- Do not delete volumes during restart procedures.
- Understand that init variables apply only to a fresh datadir.
- Restrict port publishing and use private networks.
- Protect secret files and never commit secrets.

**Health, logs, and recovery:**

- Implement proper liveness and readiness checks.
- Monitor error logs, journald, or container logs.
- Alert on restart loops, full disks, and health failures.
- Maintain backups independent of the datadir/volume.
- Test restores and measure recovery time.
- Maintain restart, upgrade, and rollback runbooks.

**Deployment:**

- Keep local, CI, staging, and production on compatible versions.
- Test configuration changes and upgrades on staging.
- Establish a change window and clear ownership.
- Verify application behavior after restarts/upgrades.
- Document changes and operational outcomes.

## 16. Key Takeaways

- Linux packages typically manage MySQL via a systemd service; the unit name may be `mysql` or `mysqld`.
- Windows can run MySQL as a Windows Service with a service name set by the installer.
- Distinguish active state from enablement; enabling does not mean starting.
- Use the service manager or `mysqladmin shutdown` for controlled stops; avoid `kill -9` in routine operations.
- `daemon-reload` reloads unit definitions; it does not make mysqld reread `my.cnf`.
- `systemctl reload` only works if supported by the unit and never replaces restarts for startup-only variables.
- MySQL can receive configuration from option files, persisted variables, and startup arguments; manage configuration sources consistently.
- Containers are ephemeral; the datadir must reside on a persistent volume.
- Regular `docker compose down` preserves named volumes; `docker compose down --volumes` can delete data.
- MySQL container initialization variables do not automatically update accounts in an already-initialized datadir.
- Health checks must distinguish process liveness from SQL readiness.
- Secrets, service accounts, ports, and networks must follow least-privilege principles.
- Backups must be independent of the datadir and must be restore-tested.
- Upgrading MySQL must follow a supported upgrade path with backups, staging, smoke tests, and a rollback plan.

Reliable MySQL operations require consistent management of both process and data. Service managers and container orchestrators only manage the process lifecycle; persistent storage, configuration, secrets, health checks, backups, and upgrade procedures determine database resilience in every environment.

## References

- MySQL 8.4 Reference Manual — Starting and Stopping MySQL: https://dev.mysql.com/doc/refman/8.4/en/starting-stopping.html
- MySQL 8.4 Reference Manual — Using Systemd: https://dev.mysql.com/doc/refman/8.4/en/using-systemd.html
- MySQL 8.4 Reference Manual — Windows Service: https://dev.mysql.com/doc/refman/8.4/en/windows-start-service.html
- MySQL 8.4 Reference Manual — Using Option Files: https://dev.mysql.com/doc/refman/8.4/en/option-files.html
- MySQL 8.4 Reference Manual — Persisted System Variables: https://dev.mysql.com/doc/refman/8.4/en/persisted-system-variables.html
- MySQL 8.4 Reference Manual — mysqldump: https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html
- Docker Docs — Start containers automatically: https://docs.docker.com/engine/containers/start-containers-automatically/
- Docker Compose Docs — Services: https://docs.docker.com/reference/compose-file/services/
- Docker Compose Docs — Volumes: https://docs.docker.com/reference/compose-file/volumes/
- Docker Docs — Manage sensitive data with Docker secrets: https://docs.docker.com/compose/how-tos/use-secrets/
- Docker Hub — Official MySQL image: https://hub.docker.com/_/mysql
