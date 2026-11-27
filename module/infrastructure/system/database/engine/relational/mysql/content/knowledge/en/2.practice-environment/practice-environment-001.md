# Choosing a MySQL Version and Resources for the Learning Environment

This lesson belongs to the **Practice Environment** chapter of the `DATABASE_MYSQL` module. The module aims to help you master MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, access privileges, backups, and troubleshooting relational database operations. Therefore, the learning environment needs to be stable enough for SQL examples to produce consistent results, yet flexible enough to create data, test configurations, and restore state after each practice exercise.

After this lesson, you will be able to choose an appropriate MySQL release track, decide between direct installation or running via containers, estimate machine resources, start a sample environment, and verify that the server is running the expected version.

## 1. Why Choose a Version Before Practicing?

MySQL Server is the program that stores and processes data. The MySQL client, MySQL Workbench, and connectors are tools that connect to the Server. Their versions do not have to be identical, but they need to be compatible with one another.

Differences between Server versions can affect SQL syntax, reserved keywords, data types, default values, authentication mechanisms, collations, the optimizer, and execution plans. A statement that runs on one machine may produce warnings or different performance results on another if the two machines use different configurations or versions.

During your studies, record at least the following:

- The MySQL Server version used by the exercise.
- The installation method: direct installation, container, or cloud managed service.
- The connection port, database name, and practice account.
- Charset, collation, and important configuration settings if the lesson depends on them.

Do not use the client program's version to infer the Server version. The `mysql --version` command shows the running client version; the `SELECT VERSION();` query is what reveals the Server version of the current connection.

## 2. Choosing a MySQL Release Track

MySQL currently has two main release tracks: **LTS (Long-Term Support)** and **Innovation**. Both receive bug fixes and security updates. The main difference lies in the stability of the feature set and the upgrade cadence.

| Criterion | LTS | Innovation |
|---|---|---|
| Goal | Environments needing a stable feature set over a long period | Trying out new features and changes |
| Behavior changes | Limited changes within the same LTS series | Behavior, syntax, or optimization methods may change between releases |
| Upgrade cadence | Maintenance upgrades within the same series; upgrading to the next LTS series on schedule | Supported until the next Innovation release |
| Suitable for | Structured learning, applications needing stable compatibility, long-term environments | Researching new features, testing with automated tests and regular upgrade plans |

### Recommended Choice as of 19-11-2026

For a new learning environment, choose **MySQL 9.7 LTS** as the default version. Docker Official Image currently lists the `9.7.4` tag for this track. If a specific project or document requires MySQL 8.4, use a corresponding 8.4.x patch version instead of arbitrarily switching to 9.7.

The Innovation track is currently listed by Docker Official Image as `26.10.0`. Only choose this track when the goal of the exercise is to experiment with new features or test compatibility with an Innovation release. Do not use it as the default for the entire introductory path unless specifically required.

MySQL 9.7 is the last series using the old sequential numbering scheme. Subsequent Innovation and LTS series use year-and-month numbering in the form YY.M.P (year, release month, and patch number). Therefore, when reading a version, clearly verify the release track rather than inferring solely from whether the number is larger or smaller.

### Pinning the Version for Reproducible Results

If using Docker, choose a specific tag, such as `mysql:9.7.4`, so that every environment creation starts from the exact same patch version. The `9.7` tag may be updated to a newer patch in the 9.7 series; the `latest` tag may switch to a different track. At the time of writing, Docker Official Image points `latest` to the Innovation 26.10.0 series, not LTS.

When you need to apply security patch updates, proactively check the release notes, update the tag, back up your data, and re-run your tests. Do not upgrade the Server midway through a practice exercise and compare results as if the environment had not changed.

Quick selection rules:

1. New lesson, no compatibility constraints: choose MySQL 9.7 LTS.
2. Project or exercise requires MySQL 8.4: choose the exact 8.4 LTS series.
3. Lesson testing new features: choose the Innovation track and explicitly record the version in your report.
4. Project with existing data or a running system: check the upgrade path and back up before changing versions.

## 3. Choosing How to Run MySQL

There are three common ways to set up a practice environment. No single option fits every situation; choose based on the lesson's goal and the tools available on your machine.

| Run Method | When to Choose | Pros | Points to Note |
|---|---|---|---|
| Direct installation on Windows, Linux, or macOS | You want to learn installation, service configuration, log inspection, and OS process management | Direct access, fewer intermediate layers, easy integration with local tools | Can conflict with an existing MySQL, port 3306, or data directory; changing versions and cleaning up takes more effort |
| Docker / Docker Compose | You want an identical environment across multiple machines or to run multiple independent versions | Pinned image, service isolation, fast environment creation and teardown, data can be persisted in a volume | Requires Docker Engine or Docker Desktop; requires understanding port mapping and volumes |
| MySQL on a cloud service | You want to practice remote connections, networking, access control, backups, or operating a managed service | No need to manage a physical server yourself; can simulate how applications connect to a remote database | May incur costs, require an account and network configuration; must protect credentials and data |

**Recommendation for most practice exercises:** use Docker Compose if Docker is already installed on your machine. Each exercise can spin up an independent environment, use an explicit version tag, and store data in a volume. If you are not yet familiar with Docker or the lesson focuses on OS service management, installing MySQL directly is also a reasonable choice.

There is no need to use the cloud just to run basic SQL statements. Switch to the cloud when the lesson actually requires connecting over a network or working with a managed database service.

## 4. Preparing Connection Tools

A minimal learning environment consists of:

- **MySQL Server:** the database process that the exercises will operate against.
- **MySQL command-line client:** runs SQL directly, well-suited for getting comfortable with statements, recording outputs, and automation.
- **MySQL Workbench:** a graphical interface for managing connections, writing SQL, designing data models, and performing certain administrative tasks.
- **Terminal:** runs Docker Compose or service management commands.

You should install the latest MySQL Workbench version provided on the official download page and check compatibility with the Server you are using. At the time of writing, the official download page lists Workbench 26.10.0 and notes that the latest version is backward-compatible with supported MySQL Server versions.

When creating a Workbench connection to MySQL running on a personal machine, the commonly used details are:

| Field | Value in the Sample Environment |
|---|---|
| Connection Method | Standard TCP/IP |
| Hostname | `127.0.0.1` |
| Port | `3306` |
| Username | `learner` |
| Password | Enter the password for the learner account |
| Default Schema | `mysql_lab` |

Use a dedicated account for exercises. Only use `root` when administrative operations or account creation are required; do not use the administrative account for routine queries.

## 5. Estimating Machine Resources

Required resources depend on data size, concurrent connections, the number of services running simultaneously, and the type of exercise. The levels below are **recommended baselines for learning on a personal computer**, not official minimum specifications published by Oracle.

| Practice Scale | Recommended Host Machine | Reference Allocation for MySQL |
|---|---|---|
| Basic SQL exercises, single learner, small dataset | 2 CPU cores, 8 GB RAM, at least 10 GB free SSD space | 1–2 CPU cores, ~1–2 GB RAM, dedicated data volume |
| Exercises with many tables, indexes, transactions, EXPLAIN, and larger datasets | 4 CPU cores, 16 GB RAM, 20–30 GB free SSD space | 2–4 CPU cores, ~2–4 GB RAM, increase volume size according to data |
| Also running applications, cache, message broker, or multiple databases | 4+ CPU cores, 16+ GB RAM | Separate allocation per service; monitor CPU, RAM, I/O, and disk space |

A few allocation principles:

- **RAM:** MySQL uses memory for the buffer pool, connections, temporary memory, and internal operations. If your machine only has 8 GB of RAM, start with a small configuration and close unnecessary services. When learning query optimization on large datasets, adding RAM can help reduce disk reads, but it does not replace proper index design.
- **CPU:** 2 cores are enough to start with for a single learner and small datasets. More cores are helpful when running many concurrent queries or multiple services; adding CPU does not automatically make a single query faster.
- **SSD and storage:** place data on an SSD if possible. Reserve space for the database, binary logs if enabled, dump files, and sample datasets. Never let the volume fill up, as MySQL may stop writing data.
- **Resources for Docker:** the RAM and CPU allocated to Docker must be sufficient for MySQL while still leaving resources for the OS, IDE, browser, and study tools.
- **Data:** start with a small dataset to verify statements. Only scale up to millions of rows when the exercise needs to measure the impact of indexes, joins, or execution plans.

Do not apply a large production server configuration to a study laptop. Measure actual usage, scale resources incrementally, and record the configuration when comparing performance.

## 6. Creating a MySQL 9.7 LTS Environment with Docker Compose

The following example creates a `mysql_lab` database, a `learner` practice account, exposes the port only on the machine's loopback interface, and persists data using a named volume. This configuration is intended for learning on a personal machine.

Create a dedicated directory for the environment, then save the following content as `compose.yaml`:

~~~yaml
services:
  db:
    image: mysql:9.7.4
    container_name: mysql-lab
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: mysql_lab
      MYSQL_USER: learner
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "127.0.0.1:3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_0900_ai_ci

volumes:
  mysql_data:
~~~

Create an `.env` file in the same directory:

~~~dotenv
MYSQL_ROOT_PASSWORD=replace_with_a_local_root_password
MYSQL_PASSWORD=replace_with_a_local_learner_password
~~~

Replace the two placeholder values with your own passwords for the practice machine. Do not commit the `.env` file to Git and do not reuse passwords from real accounts. For shared projects or environments containing important data, use an appropriate secret management mechanism instead of storing plaintext passwords in the repository.

Run the following commands from the directory containing `compose.yaml`:

~~~bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f db
~~~

On the first startup, the image needs to initialize the data directory and database. Wait for the logs to indicate that MySQL is ready for connections before opening Workbench or running the client. A container status of running does not necessarily mean database initialization has finished.

Connect using the client inside the container:

~~~bash
docker compose exec db mysql -u learner -p mysql_lab
~~~

Enter the learner password when prompted. Then run the verification query:

~~~sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@port AS server_port,
    @@character_set_server AS character_set_server,
    @@collation_server AS collation_server;
~~~

The result should show the Server running version 9.7.x, internal port 3306, and the configured character set/collation. When connecting from Workbench on the host machine, use host `127.0.0.1`, port `3306`, and user `learner`.

### Understanding Port Mapping and Volumes

In the configuration:

- `127.0.0.1:3306:3306` maps port 3306 on the host machine to port 3306 inside the container. Binding to `127.0.0.1` restricts connections to the local machine, which is suitable for a personal lab.
- `mysql_data:/var/lib/mysql` stores database files in a named volume. When the container is removed and recreated, the data remains in the volume.
- `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` are used by the image when initializing a new data directory. If the volume already contains a database, changing the variables in `.env` does not automatically change passwords or recreate users.

If port 3306 is already in use by another MySQL instance, change the left side to port 3307:

~~~yaml
ports:
  - "127.0.0.1:3307:3306"
~~~

In that case, clients on the host must connect to `127.0.0.1:3307`; the port inside the container remains 3306.

### Stopping and Recreating the Environment

Stop the container while keeping the data:

~~~bash
docker compose down
~~~

Start it again with the existing data:

~~~bash
docker compose up -d
~~~

Only run the following when you intentionally want to delete all practice data and create a fresh database from scratch:

~~~bash
docker compose down -v
~~~

The `-v` option deletes the named volume managed by Compose. All databases in that volume will be lost. Before running this command, export any data you want to keep using `mysqldump` or an appropriate backup tool.

## 7. Installing MySQL Directly on Your Machine

Direct installation is suitable when you want to understand how MySQL runs as an OS service or do not want to install Docker.

- **Windows:** download the 64-bit MSI package from the MySQL Community Server page and follow the MySQL Configurator instructions. Verify that the service is running and remember the administrative password you set.
- **Linux:** use the official repository or the package appropriate for your distribution. Select the right LTS branch in the repository configuration if you want to receive updates within that branch.
- **macOS:** use the native installer package matching your machine's architecture. Check the instructions for starting and stopping MySQL after installation.

For most learners, a binary distribution is the right choice; there is no need to compile from source. Before installing, check whether your operating system and CPU architecture are in the list of supported platforms.

If MySQL is already installed on the machine, check the service and port 3306 before installing another instance. Two Servers using the same TCP port on the same address will conflict. If you must maintain multiple versions, Docker is usually easier to isolate.

After installation, open a terminal and run:

~~~bash
mysql --version
~~~

This command checks the client. Log in to the Server and run:

~~~sql
SELECT VERSION();
SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

Record the output to know which version the Server is actually running and which port it is listening on.

## 8. Common Issues When Setting Up the Environment

| Symptom | Common Cause | How to Check and Resolve |
|---|---|---|
| Cannot connect to `127.0.0.1:3306` | Container is not ready, Server is not running, or port mapping is wrong | Check `docker compose ps`, inspect `docker compose logs db`, verify host and port |
| Port 3306 is already in use | Another MySQL instance or another application is occupying the port | Use host port 3307 or stop the unnecessary service |
| `Access denied` error after changing the password in `.env` | The old volume retains the account and password created during the previous initialization | Log in with the current password and change it via SQL; only delete the volume if data loss is acceptable |
| Container is running, but the client cannot connect immediately | MySQL is initializing the data directory or loading sample data | Wait for the logs to report readiness; do not send repeated queries during initialization |
| Data persists after recreating the container | The named volume was preserved | This is expected behavior; use `docker compose down -v` only when you want to delete the data |
| Data lost after deleting the volume or using a temporary directory | The database was not stored in a persistent location or the volume was deleted | Mount a named volume to `/var/lib/mysql`, and create regular backups for data you need to keep |
| Workbench connects, but some administrative operations fail | The Workbench version or feature is incompatible with the Server | Update Workbench and check compatibility documentation; use the mysql client to verify directly |

## 9. Checking the Environment Before Starting SQL Lessons

Before doing lessons on table design, keys, indexes, transactions, or query optimization, complete this checklist:

- [ ] Explicitly selected a MySQL LTS or Innovation track and recorded the full version.
- [ ] Both Server and client start properly; distinguished between the client version and the Server version.
- [ ] Selected an appropriate run method: direct installation, Docker Compose, or cloud.
- [ ] The machine has enough RAM, CPU, and SSD space for practice data.
- [ ] Created a dedicated database and learning account; not using root for routine queries.
- [ ] Confirmed host, port, charset, and collation.
- [ ] If using Docker, data is stored in a volume and you know which commands can delete the volume.
- [ ] Know how to view logs, stop, restart, and back up data.

A well-prepared environment ensures exercise results are reproducible. When encountering differences in syntax or performance, check the Server version, configuration, and data before concluding that a statement or design is wrong.

## Official References

The versions and tags in this lesson were verified as of **19-11-2026**. Before setting up a new environment, re-check the download page and release notes for the latest patch versions.

1. [MySQL 9.7 Reference Manual — MySQL Releases: Innovation and LTS](https://dev.mysql.com/doc/refman/9.7/en/mysql-releases.html): differences between LTS and Innovation, support lifecycle, and version numbering.
2. [MySQL 9.7 Reference Manual — Which MySQL Version and Distribution to Install](https://dev.mysql.com/doc/refman/9.7/en/which-version.html): choosing a release track and installation package.
3. [MySQL 9.7 Reference Manual — Installing MySQL](https://dev.mysql.com/doc/refman/9.7/en/installing.html): installation instructions by operating system and supported platforms.
4. [MySQL Community Server Downloads](https://dev.mysql.com/downloads/mysql/): download the Server and check currently distributed versions.
5. [Docker Official Image — mysql](https://hub.docker.com/_/mysql): image tags, environment variables, database initialization, data persistence, and Docker Compose examples.
6. [MySQL Workbench Downloads](https://dev.mysql.com/downloads/workbench/): download the graphical tool and view compatibility information.
