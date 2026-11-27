# Installing via OS Packages, Virtual Machines, or Containers

To learn MySQL, you first need a database server that you can start, stop, configure, and recreate when needed. There are three common ways to set up an environment: installing MySQL directly using the operating system's package manager, installing it inside a virtual machine, or running it via a container. Each approach suits a different practice objective.

This lesson uses MySQL Community Server 8.4 as the example version. Align the version with the application or course content you are using; when you need reproducible environments, pin a specific version instead of using a mutable image tag like `latest`.

After this lesson, you will be able to:

- Choose a deployment method that suits your computer and practice goals.
- Install, start, and verify MySQL on Linux.
- Create a virtual machine to isolate the database server.
- Run MySQL with Docker Compose with persistent data storage.
- Connect to the server, verify the version, and troubleshoot several common startup errors.

## 1. Choosing a Deployment Method

| Deployment Method | When to Use | Considerations |
| --- | --- | --- |
| OS package | You want to learn system services, `systemd`, configuration files, and Linux server operations | MySQL is tied to the OS lifecycle; the version in default repositories may differ from the desired version |
| Virtual Machine (VM) | You want a dedicated Linux machine, to test network configuration, firewalls, upgrades, or simulate a server | Consumes more RAM, CPU, and disk space; requires managing the guest OS as well |
| Container | You want fast setup, easy environment recreation, and configuration stored as code | Requires understanding images, port mapping, volumes, and container lifecycle; containers do not replace backup procedures |

If your immediate goal is simply practicing SQL on a personal computer, a container is usually the cleanest option. If you want to understand how MySQL runs as a Linux service, install it using OS packages. If you need to test changes that could affect the entire OS or network, use a virtual machine to limit the blast radius.

All of these deployment methods produce a MySQL server. Subsequent topics such as table design, data types, keys, queries, indexes, transactions, access control, and backups can all be practiced on the same sample database.

## 2. Preparing Before Installation

Before choosing an installation method, check the following prerequisites:

1. **Version and platform:** identify the MySQL version to learn, the operating system, and the CPU architecture (x86-64 or ARM). Check the supported platform matrix for the MySQL release you plan to install.
2. **Resources:** allocate enough RAM and disk space for the OS, binaries, logs, and data. For a small learning VM, you can start with 2 vCPUs, 4 GB RAM, and a 25 GB disk, then adjust based on load.
3. **Installation privileges:** installing system packages requires administrative privileges; creating a VM requires permission to use virtualization software; running containers requires a working Docker Engine or compatible runtime.
4. **Connection port:** MySQL typically listens on TCP port `3306`. Check whether this port is already in use by another service. If mapping to the host machine, you can use another port, such as `3307`.
5. **Existing data:** if the machine already has MySQL or MariaDB, identify the service, data directory, and backups before making changes. Do not overwrite or delete the data directory just to work around a startup error.
6. **Network scope:** a learning environment on a personal machine should only allow connections from localhost or the required lab network. Do not expose the database port to the Internet.

### Distinguishing Between MySQL and MariaDB

Some Linux distributions provide MariaDB in their default repositories, even though package names or installation commands may lead beginners to think it is Oracle MySQL. The two DBMSs share related origins but are separate products with differences in versioning and features. If the lesson requires MySQL Community Server, verify the package vendor and version before installing. After installing, verify with the SQL statement in section 6 rather than relying solely on the `mysql` command name.

## 3. Installing MySQL via OS Packages

Direct installation is suitable when you have a dedicated Linux machine or want to learn how to manage services with OS tools. Package names, service names, and configuration paths may differ across distributions.

### 3.1. Ubuntu or Debian

First, update the package list and check where the `mysql-server` package will be fetched from:

```bash
sudo apt update
apt-cache policy mysql-server
```

Read the `Candidate` field and repository information. On some Debian releases or default repository configurations, the default server package may be MariaDB or may not provide the Oracle MySQL version you need. If MySQL Community Server is specifically required, configure the official MySQL APT repository according to the instructions for your distribution, then re-check the package candidate.

Once you have confirmed the package source provides the exact MySQL version needed, install and start the service:

```bash
sudo apt install mysql-server
sudo systemctl enable --now mysql
sudo systemctl status mysql --no-pager
```

`enable` configures the service to start automatically with the OS; `--now` starts it immediately on this run. If `status` shows `active (running)`, the service process is running. This status does not yet prove that accounts, access privileges, or remote connections are configured properly.

On some Ubuntu installations, the MySQL `root` account uses system socket authentication. In that case, you can open the client with:

```bash
sudo mysql
```

If the `root` account is configured with a password, use `mysql -u root -p` and enter the password at the prompt. Never pass the password directly as a command-line argument because the command can be saved in shell history or exposed in the process list.

### 3.2. RHEL, Rocky Linux, or AlmaLinux

On RHEL-compatible systems, once the official MySQL Community repository is configured, install the server package and enable the service as follows:

```bash
sudo dnf install mysql-community-server
sudo systemctl enable --now mysqld
sudo systemctl status mysqld --no-pager
```

The service name is typically `mysqld` on this family of distributions. If the MySQL Community repository is not yet configured, follow the official repository setup guide for your OS version before running the package install command. Check package details with `dnf info mysql-community-server` to verify the provider.

On some fresh RPM installations, MySQL generates a temporary password for `root` and writes it to the log. You can find the relevant line with:

```bash
sudo grep 'temporary password' /var/log/mysqld.log
```

Log in with `mysql -u root -p`, use the temporary password found above, and change the password according to your environment's policy. Log paths or initialization behavior may vary by version and package configuration; if you do not find this line, check the service logs instead of guessing the password.

### 3.3. Completing Initial Configuration

On systems that provide this utility, run:

```bash
sudo mysql_secure_installation
```

Read each prompt carefully and choose settings appropriate for your learning environment. Common items to review include setting a strong administrative password, removing anonymous accounts, restricting remote `root` login, and removing the default test database if unused. Do not enable remote access for `root` just for convenience when connecting from another machine.

Configuration file paths depend on the distribution. Ubuntu/Debian typically place files under `/etc/mysql/`, whereas RPM-based distributions commonly use `/etc/my.cnf` and an included configuration directory. Before editing, identify which configuration file the service actually loads. After changing server configuration, validate syntax if supported by the tool, restart the service, and check logs if the service fails to start.

```bash
# Ubuntu/Debian
sudo systemctl restart mysql

# RHEL and compatible distributions
sudo systemctl restart mysqld
```

## 4. Installing MySQL in a Virtual Machine

A virtual machine emulates an independent computer with its own operating system, disk, and network interface. This approach is useful when you want to practice an installation workflow close to a real server while keeping the test environment isolated from your primary OS.

### 4.1. Creating a Virtual Machine

You can use VirtualBox, Hyper-V, VMware, or a virtualization platform suited to your machine. General steps:

1. Download the ISO of a supported Linux distribution compatible with the chosen MySQL version.
2. Create a VM with a suitable initial configuration, such as 2 vCPUs, 4 GB RAM, and a 25 GB virtual disk. Increase resources if your data or test workload is larger.
3. Choose NAT networking for the initial installation so the VM can access the Internet without appearing directly on the LAN.
4. Install the OS, create a standard administrative account, and update system packages.
5. Install MySQL inside the VM following the procedure in section 3, then verify the service and log in directly inside the VM.

Create a snapshot once the OS and MySQL are running smoothly. Snapshots are convenient for reverting to a test state, but they do not replace database backups: snapshots can depend on VM state and are not always a consistent backup for data actively being written.

### 4.2. Connecting from the Host Machine

To connect from the host machine, you need a network path to the VM. Two common methods are:

- **SSH tunnel:** keep MySQL listening only on the VM's loopback interface, then forward the port over SSH. For example, from the host machine run:

  ```bash
  ssh -L 3307:127.0.0.1:3306 username@vm_address
  ```

  Keep the SSH session open, then connect MySQL from the host machine to `127.0.0.1`, port `3307`. This method avoids exposing the MySQL port directly on the network.

- **NAT port forwarding:** configure host port `3307` to forward to guest port `3306` in the VM network settings. Ensure MySQL listens on the appropriate interface and the guest firewall permits the connection flow. Use this only in a trusted lab network; never create forwarding rules from an Internet router to the database server.

When a connection fails, check in order: the VM's IP address, forwarding rules, service status, `bind-address`, and the firewall. Opening a port in the firewall has no effect if MySQL is only listening on a different address.

## 5. Running MySQL with Docker Compose

Containers package MySQL together with its required runtime environment. Docker Compose lets you describe the image, environment variables, ports, and volumes in a single file so you can rebuild the environment with the exact same configuration.

### 5.1. Preparing Credentials

Install Docker Engine and the Docker Compose plugin following the instructions for your operating system. Verify Docker works:

```bash
docker version
docker compose version
```

Create a dedicated directory for the practice exercise, then create an `.env` file inside that directory:

```dotenv
MYSQL_ROOT_PASSWORD=replace-with-a-long-random-admin-password
MYSQL_PASSWORD=replace-with-a-learner-user-password
```

Replace the example values with sufficiently strong random strings. Do not commit `.env` to Git and do not reuse real passwords. You can add `.env` to the project's `.gitignore`. Restrict read permissions on this file on shared systems.

### 5.2. Creating the compose.yaml File

Create `compose.yaml` in the same directory as `.env`:

```yaml
services:
  mysql:
    image: mysql:8.4
    container_name: mysql-lab
    environment:
      MYSQL_ROOT_PASSWORD: "${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD in .env}"
      MYSQL_DATABASE: labdb
      MYSQL_USER: labuser
      MYSQL_PASSWORD: "${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env}"
    ports:
      - "127.0.0.1:3307:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    restart: unless-stopped

volumes:
  mysql_data:
```

Meaning of the configuration:

- `image` selects MySQL 8.4. When stricter reproducibility across machines or over time is needed, pin a verified patch version or image digest.
- `MYSQL_ROOT_PASSWORD` sets the initial password for the `root` account.
- `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` instruct the image to create a database and an application account when initializing the data directory for the first time.
- `127.0.0.1:3307:3306` maps port `3306` inside the container to port `3307` on the host machine's loopback interface. Other machines on the network cannot connect via this loopback mapping.
- `mysql_data` is a named volume that persists data beyond the container lifecycle. Removing or recreating the container does not delete this volume.

Initialization variables are only applied when the data directory is empty. If the `mysql_data` volume has already been initialized, changing the password in `.env` does not automatically change the password of the existing account; log in and change it using the appropriate SQL statement.

### 5.3. Starting and Connecting

In the directory containing `compose.yaml` and `.env`, run:

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 mysql
```

The first startup may take extra time to create the data directory and initialize the system. Wait until the container is running stably, then log in:

```bash
docker compose exec mysql mysql -u root -p
```

Enter `MYSQL_ROOT_PASSWORD` at the prompt. Or from the host machine, if the MySQL client is installed:

```bash
mysql -h 127.0.0.1 -P 3307 -u labuser -p labdb
```

To stop the container while preserving data:

```bash
docker compose stop
```

To remove the container and network created by Compose while preserving the named volume:

```bash
docker compose down
```

The `docker compose down -v` command also deletes the named volume and the data inside it. Run it only when you intend to delete all practice data and have confirmed nothing needs to be kept. Do not use this command as a default cleanup step.

## 6. Verifying the Server After Installation

Once logged in with the MySQL client, run the following statements:

```sql
SELECT VERSION(), @@version_comment, @@port, @@datadir;
SHOW DATABASES;
```

The output confirms the server version, listening port, data directory, and existing databases. Check `VERSION()` and `version_comment` to make sure you are running Oracle MySQL as required, rather than another compatible server.

Next, verify the learning account created in the container:

```sql
SELECT CURRENT_USER();
USE labdb;
CREATE TABLE environment_check (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    note VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO environment_check (note) VALUES ('MySQL lab is ready');
SELECT id, note, created_at FROM environment_check;
```

If all statements succeed, you have verified connectivity, table creation privileges, data insertion, and data retrieval. In an environment installed via OS packages or a VM, create a dedicated database and account for the lesson following the same principle of least privilege; do not use `root` for applications or daily practice exercises.

## 7. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Check and Resolve |
| --- | --- | --- |
| Service fails to start | Misconfiguration, inaccessible data directory, insufficient disk space, or port already in use | Check `systemctl status` and logs via `journalctl -u mysql -n 100 --no-pager` or `journalctl -u mysqld -n 100 --no-pager`; fix the cause logged there and restart |
| `Address already in use` or cannot bind port | Another process is occupying port `3306` | On Linux, run `sudo ss -ltnp | grep ':3306'`; identify the service holding the port before stopping it or choose a different mapped port |
| `Access denied` | Wrong password, wrong account, or account not permitted to connect from the current host | Verify username, password, account host, and authentication method; enter the password at the prompt instead of passing it on the command line |
| `Can't connect` or connection refused | Service not ready, wrong host/port, `bind-address`, firewall, or wrong port mapping | Check service status, logs, listening address, and network rules; with Compose, inspect `docker compose ps` and `docker compose logs mysql` |
| Container is running, but the application cannot connect immediately | MySQL is still initializing data | Wait for logs to indicate the server is ready and retry; a container status of `running` does not guarantee MySQL is ready to accept connections |
| Changed `.env` but MySQL password did not change | The volume already contains data from a previous initialization | Change the password inside MySQL using an administrative account; environment variables only set accounts on the very first initialization |
| MySQL cannot open the data directory after changing versions | Data was created by a different version or permissions are incorrect | Check the previous and new versions, logs, and directory ownership; back up data before attempting an upgrade or recovery |

On Linux, service logs are usually the most helpful place to find the root cause:

```bash
# Ubuntu/Debian
sudo journalctl -u mysql -n 100 --no-pager

# RHEL and compatible distributions
sudo journalctl -u mysqld -n 100 --no-pager
```

For containers:

```bash
docker compose ps
docker compose logs --tail=100 mysql
```

Do not delete the data directory or volume to "retry" before determining whether that data needs to be kept. If you must recreate the environment, back up necessary data, record the current MySQL version and configuration, and only then perform the deletion.

## 8. Safety Principles for the Learning Environment

- Only open the MySQL port to machines that actually need to connect. When learning on a personal computer, prefer loopback or an SSH tunnel.
- Use separate passwords for administrative accounts and application accounts; grant exact privileges on the exact database.
- Do not allow `root` to log in remotely unless the lesson has a specific administrative requirement.
- Store data in a volume or persistent disk. Containers can be recreated, but data must have its own lifecycle and backups.
- Before upgrading versions or changing storage configuration, back up and verify restore capability.
- Do not put passwords, `.env` files, or real data into Git, screenshots, or shared logs.

## 9. Practice Exercises

1. Set up a MySQL server using one of the three methods above. Record the operating system, MySQL version, installation method, and connection port.
2. Restart the machine or runtime environment. Verify that MySQL starts automatically (for OS package installation) or can be restarted via Compose/VM.
3. Connect with a client and run `SELECT VERSION(), @@port, @@datadir;`. Explain each value.
4. Create a `practice_db` database, a `practice_user` account with the required privileges on that database, and then log in with the new account.
5. For containers, run `docker compose down` followed by `docker compose up -d`; confirm the table and data are still present. Then explain why `docker compose down -v` produces a different result.
6. Intentionally misconfigure the connection port in the client, read the error message, and identify the exact cause. Restore the correct port and reconnect.

## 10. Completion Criteria

You have completed this lesson when you can independently set up a MySQL server, start and stop it, log in via a client, confirm the exact version, create and query a table, explain where data is stored, and locate logs when connection or startup fails. Keep your version and environment setup details recorded so upcoming exercises on SQL, indexes, transactions, access control, and backups can reuse the same setup.
