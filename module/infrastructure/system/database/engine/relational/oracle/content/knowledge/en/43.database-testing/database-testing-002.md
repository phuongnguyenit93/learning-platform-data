# Creating an Isolated Oracle Environment with Containers or Automated Virtual Machines

An isolated Oracle environment lets developers and DBAs test SQL, schema migrations, JDBC, backup/restore, Data Pump, PL/SQL, and failure scenarios without affecting shared databases. When environments are provisioned automatically, the team can reproduce the exact same database version, initialization configuration, and test data on local workstations, CI runners, or lab servers.

Two common deployment approaches:

- **Container:** running Oracle Database in Docker or Podman. Fast startup, lower resource overhead than VMs, and easy to integrate into pipelines.
- **Virtual Machine (VM):** creating a separate guest OS using VirtualBox, VMware, KVM, or a cloud platform. A VM has its own kernel and operating system, making it suitable when testing OS behavior, native libraries, networking, or stronger isolation than containers.

Both approaches can be combined: automate VM creation with Vagrant/Packer, then use Ansible to install a container runtime and run an Oracle Database container inside the VM. This hybrid approach creates a reproducible lab with relatively clear infrastructure control.

## 1. Goals and scope of an isolated environment

A good Oracle lab should satisfy:

- No accidental connections to production.
- Recorded database version and service name.
- Reproducible test data.
- Volumes storing datafiles separate from the container lifecycle.
- Schema and privilege initialization scripts following the principle of least privilege.
- Health/readiness checks before running tests.
- Ability to reset to a clean state or restore from a snapshot.
- Automated execution on developer machines and CI.
- Limits on CPU, RAM, storage, and network.
- No real data or production secrets.

The lab's objective determines the deployment approach. If you only need to test SQL/JDBC, an Oracle Database Free container is usually sufficient. If you need to test the kernel, systemd, native Oracle Client, ASM, multiple nodes, or complex network routing, a VM or dedicated lab is more appropriate.

## 2. How do Containers and VMs differ?

Both containers and VMs isolate application environments, but their technical boundaries differ.

~~~text
Container model

Host operating system and kernel
  |
  +-- Container runtime
        |
        +-- Oracle container
        |     +-- Oracle Database processes
        |     +-- Oracle data volume
        |
        +-- Test application container
              +-- JDBC driver
              +-- Integration tests

Virtual machine model

Physical host
  |
  +-- Hypervisor
        |
        +-- Guest OS
              +-- Oracle Database
              +-- Oracle data disks
              +-- Test tools
~~~

| Criterion | Container | VM |
|---|---|---|
| Kernel | Uses host kernel | Has its own guest kernel |
| Startup | Usually faster | Usually slower |
| Resources | Usually lighter | Usually requires more RAM/disk |
| Isolation | Namespace/cgroup and runtime boundary | Hypervisor boundary |
| OS testing | Limited by host kernel | Can run a different OS |
| Data | Named volume/bind mount | Virtual disk |
| Reproducibility | Image and Compose | Box/template and provisioning |
| Best suited for | SQL, JDBC, schema tests, CI | OS/native/network, multi-node lab |
| Portability | Good if image supports the platform | Depends on hypervisor/box |

A container is not a lightweight VM. Containers share the host kernel; do not rely on a container as the sole security boundary when running untrusted code. For untrusted workloads or OS isolation testing, use a VM or a managed sandbox environment.

## 3. Selecting an Oracle Database image

Choose an image appropriate for your purpose and usage rights:

- Oracle Database Free is suitable for learning, development, and testing within product limits.
- Oracle Database Enterprise Edition or Standard Edition must comply with the corresponding license rights and terms of use.
- Oracle Container Registry provides images published by Oracle; some images/tags require signing in and accepting terms before pulling.
- Oracle's GitHub `docker-images` repository contains scripts to help build certain images from Oracle software distributions; you must download the software and comply with the corresponding license.
- Community images can be convenient, but you must evaluate their origin, maintainer, tags, Dockerfile, security updates, and terms of use before adopting them.

Do not assume running a database inside a container changes database licensing. A container is merely a packaging and runtime mechanism; usage rights still depend on the edition, deployment, and contract.

### 3.1 Prioritize verifiable sources

Before using an image:

1. Identify the official publisher and repository.
2. Read the terms and accept the license if required by the registry.
3. Select a specific version tag.
4. Record the digest if the pipeline requires high reproducibility.
5. Review documentation on environment variables, volumes, and init scripts.
6. Verify supported CPU architectures.
7. Read security advisories and the image update schedule.

Avoid using the `latest` tag in critical pipelines because the tag's contents can change over time. In a personal lab, `latest` may be used for quick trials, but record the actual image ID and version.

### 3.2 Oracle Database Free

The example below uses the Oracle Database Free image from Oracle Container Registry. The tag name must be chosen according to registry documentation at deployment time:

~~~text
container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Some Oracle Database Free builds provide CDB service `FREE` and PDB service `FREEPDB1`. Service names, tags, volume paths, and lifecycle scripts must be verified against the documentation of the specific image.

Oracle Database Free has resource and feature limits under its product terms. Do not use Free lab results to conclude that all behavior/performance is identical to Enterprise Edition.

## 4. Preparing Docker or Podman

The container host requires:

- Docker Engine + Docker Compose plugin, or Podman with a Compose-compatible workflow.
- A CPU architecture supported by the image.
- Sufficient RAM and disk for database startup, workload, and datafiles.
- Unoccupied listener port.
- Permission to pull images from the registry.
- Persistent directory/volume for data storage.

Check:

~~~bash
docker version
docker compose version
docker info
~~~

With Podman:

~~~bash
podman version
podman info
~~~

Docker Desktop on Windows/macOS typically runs Linux containers through a backend VM. Distinguish between host ports and container ports when configuring connections.

## 5. Logging into the registry and pulling the image

If Oracle Container Registry requires authentication/term acceptance, perform this using an account authorized by your organization:

~~~bash
docker login container-registry.oracle.com
docker pull container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Do not store registry tokens in source code or Compose files. Use Docker's credential store, CI secrets, or an appropriate secret manager mechanism.

Inspect the image:

~~~bash
docker image inspect container-registry.oracle.com/database/free:<validated-version-tag>
docker image ls
~~~

Record the repository/tag, image digest/ID, database release, pull date, registry source, and accepted license/terms.

## 6. Running an Oracle container with docker run

Example starting Oracle Database Free:

~~~bash
docker volume create oracle-lab-data
docker run -d --name oracle-lab --publish 127.0.0.1:1521:1521 --env ORACLE_PWD --volume oracle-lab-data:/opt/oracle/oradata --shm-size=1g container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Before running, set the `ORACLE_PWD` environment variable in your terminal or secret manager. The command only passes the existing environment variable into the container without writing the password directly into the command text.

PowerShell example:

~~~powershell
$env:ORACLE_PWD = "Use-a-local-lab-secret"
docker run -d --name oracle-lab --publish 127.0.0.1:1521:1521 --env ORACLE_PWD --volume oracle-lab-data:/opt/oracle/oradata --shm-size=1g container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Bash example:

~~~bash
export ORACLE_PWD='Use-a-local-lab-secret'
docker run -d --name oracle-lab --publish 127.0.0.1:1521:1521 --env ORACLE_PWD --volume oracle-lab-data:/opt/oracle/oradata --shm-size=1g container-registry.oracle.com/database/free:<validated-version-tag>
~~~

The password in these examples is only a lab placeholder. Do not use production passwords, do not commit files containing secrets, and do not reuse this password in other environments.

### 6.1 Why publish the port on loopback?

Mapping `127.0.0.1:1521:1521` publishes the listener only on the host loopback interface. It restricts other machines on the LAN from directly accessing the lab database. If remote machine access is needed, design a specific private network/firewall instead of publishing the database on all interfaces.

### 6.2 Checking status and logs

~~~bash
docker ps
docker logs -f oracle-lab
~~~

The database needs time to initialize datafiles and open services. A container in the `running` state does not mean the database is ready to accept connections.

Wait for the ready/success message per the image documentation. Do not run integration tests immediately after `docker run` without checking readiness.

### 6.3 Connecting from the host

For images providing PDB service `FREEPDB1`, the Thin URL typically looks like:

~~~text
jdbc:oracle:thin:@//localhost:1521/FREEPDB1
~~~

Actual accounts and services must match the image configuration. Connect using the service name; do not infer a SID from the container name.

## 7. Using Docker Compose

Compose declares the image, ports, environment, volumes, and networks in one file so the team can spin up the same environment with a single command.

Example directory structure:

~~~text
oracle-lab/
  compose.yaml
  .env
  .gitignore
  oracle-init/
    01-create-lab-user.sql
  tests/
    ...
~~~

### 7.1 The .env file

~~~text
ORACLE_PWD=Use-a-local-lab-secret
~~~

Add `.env` to `.gitignore`:

~~~text
.env
*.wallet
*.p12
*.jks
~~~

Do not commit secrets or private keys. In CI, inject `ORACLE_PWD` from a secret store rather than storing it in the repository.

### 7.2 compose.yaml

~~~yaml
services:
  oracle:
    image: container-registry.oracle.com/database/free:<validated-version-tag>
    container_name: oracle-lab
    env_file:
      - .env
    ports:
      - "127.0.0.1:1521:1521"
    volumes:
      - oracle-data:/opt/oracle/oradata
      - ./oracle-init:/opt/oracle/scripts/setup:ro
    shm_size: 1g
    restart: unless-stopped

volumes:
  oracle-data:
~~~

The init script path in this example is a convention supported by certain Oracle database container images. Verify the exact setup/startup directory and script execution behavior in the documentation of the pinned image. Not all community Oracle images use the same path.

### 7.3 Starting up

~~~bash
docker compose config
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f oracle
~~~

`docker compose config` lets you inspect the resolved Compose configuration. Do not share its output if it contains secret values.

### 7.4 Stopping and removing

~~~bash
docker compose stop
docker compose start
docker compose down
~~~

`down` stops and removes containers/networks managed by Compose, while named volumes are normally preserved.

The following command also deletes volumes managed by Compose:

~~~bash
docker compose down -v
~~~

This operation deletes the lab database data. Use it only when you are sure you want to reset all datafiles. Do not run `down -v` inside a Compose directory pointing to data that must be kept.

## 8. Persistent volumes and data lifecycle

Containers can be removed and recreated. If datafiles reside only in the container's writable layer, data can be lost when the container is deleted.

A named volume allows data to live independently of the container:

~~~text
oracle-lab-data volume
        |
        v
/opt/oracle/oradata inside container
        |
        v
Oracle datafiles, control files, redo files
~~~

### 8.1 Named volumes

~~~bash
docker volume create oracle-lab-data
docker volume inspect oracle-lab-data
~~~

Named volumes are well-suited for local labs and CI workflows that need to preserve data across restarts.

### 8.2 Bind mounts

You can mount a host directory:

~~~yaml
volumes:
  - ./data/oradata:/opt/oracle/oradata
~~~

Bind mounts make files visible on the host, but require handling permissions, filesystem performance, SELinux labels, and Windows/macOS/Linux differences. For database files, named volumes usually cause fewer issues.

### 8.3 Restart vs. reset

- Restart container: stops and restarts processes, keeps the volume.
- Recreate container: creates a new container, keeps the named volume unless deleted.
- Reset database: deletes the volume or uses a database recreate procedure.
- Restore snapshot: restores the volume/backup to a previously saved state.

Do not use restart as a way to wipe test data.

### 8.4 Backing up volumes

A volume is not automatically a backup. You can back up the database using RMAN or consistent storage snapshots according to procedure. Directly copying open datafiles with a standard file copy does not guarantee a consistent backup.

## 9. Automated schema initialization

A lab can automatically create users/schemas and objects after the database is created for the first time. Use version-controlled init scripts, but never put real passwords in scripts.

SQL example:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE

ALTER SESSION SET CONTAINER = FREEPDB1;

CREATE USER lab_app IDENTIFIED BY "ReplaceWithLabSecret";

GRANT CREATE SESSION,
      CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE
TO lab_app;

ALTER USER lab_app QUOTA 500M ON USERS;

EXIT
~~~

This example assumes an image/service with PDB `FREEPDB1` and a script running with sufficient privileges. PDB name, tablespace, script execution context, and password syntax must match the image/release.

Do not grant `DBA`, `CREATE ANY TABLE`, or broad system privileges to an application user just to test CRUD.

### 9.1 Setup scripts and startup scripts

Some images support two types of directories:

- Setup scripts: run during initial database creation.
- Startup scripts: run every time the database container starts.

This behavior varies by image. If a setup script only runs on first database creation, editing the file later will not re-run the script against an existing volume.

Therefore:

- Use setup scripts for initial bootstrapping.
- Use a migration tool or dedicated automation for subsequent schema changes.
- Do not place non-idempotent `CREATE USER` statements in a startup script that runs on every boot.
- Log and check exit codes of init scripts.

### 9.2 Idempotent initialization

An idempotent script can be executed multiple times without causing errors or duplicate data. Not all Oracle SQL DDL statements support `IF NOT EXISTS` across all releases; you can use PL/SQL to check metadata before creating objects, or manage changes with a migration tool.

Do not catch and ignore all exceptions. Handle only specific expected errors, and ensure other errors fail the job so CI does not report a false green.

## 10. Readiness checks

A running container only indicates that the main process has not exited. Oracle may still be:

- Creating the database.
- Recovering the instance.
- Opening the PDB.
- Running init scripts.
- Registering services with the listener.

The application must wait until the database accepts connections and succeeds in running a query.

### 10.1 Checking logs

~~~bash
docker logs oracle-lab
~~~

Read the specific ready message for the image and version. Do not rely on a single log string if images change; readiness should verify an actual connection.

### 10.2 Probing with SQL

When SQL*Plus is present in the image:

~~~bash
docker exec -it oracle-lab bash
sqlplus -L system@//localhost:1521/FREEPDB1
~~~

After authenticating, run:

~~~sql
SELECT 1 FROM dual;
SELECT sys_context('USERENV', 'CON_NAME') AS con_name FROM dual;
~~~

Avoid passing passwords directly in shell commands whenever possible; use prompts or a secret mechanism.

### 10.3 Retrying in integration tests

The test runner should retry connecting within a bounded window:

~~~java
long deadline = System.nanoTime() + Duration.ofMinutes(5).toNanos();
SQLException lastError = null;

while (System.nanoTime() < deadline) {
    try (Connection connection = dataSource.getConnection();
         Statement statement = connection.createStatement();
         ResultSet result = statement.executeQuery("SELECT 1 FROM dual")) {
        if (result.next() && result.getInt(1) == 1) {
            return;
        }
    } catch (SQLException e) {
        lastError = e;
        Thread.sleep(2000);
    }
}

throw new IllegalStateException("Oracle did not become ready", lastError);
~~~

This is Java pseudocode that must be placed in an appropriate method with `InterruptedException`/exception handling declared. Production-grade tests should distinguish transient startup errors from configuration errors like wrong passwords or invalid services; never retry indefinitely.

## 11. Connecting from a test container vs. from the host

The two connection paths differ:

| Client location | Host in JDBC URL |
|---|---|
| Running on host | `localhost` or `127.0.0.1` |
| Running in same Compose network | Service name, e.g., `oracle` |
| Running inside VM | Private IP/hostname of the VM |
| Running from another machine | Private DNS/IP permitted by firewall |

Example from the host:

~~~text
jdbc:oracle:thin:@//localhost:1521/FREEPDB1
~~~

Example from an application container in the same Compose network:

~~~text
jdbc:oracle:thin:@//oracle:1521/FREEPDB1
~~~

Inside a container, `localhost` points to that container itself, not another Oracle container. Use the Compose network's service DNS.

## 12. Creating an environment with Podman

Podman provides a workflow similar to Docker for many use cases:

~~~bash
podman pull container-registry.oracle.com/database/free:<validated-version-tag>
podman volume create oracle-lab-data
podman run -d --name oracle-lab -p 127.0.0.1:1521:1521 --env ORACLE_PWD -v oracle-lab-data:/opt/oracle/oradata container-registry.oracle.com/database/free:<validated-version-tag>
~~~

Verify:

~~~bash
podman ps
podman logs -f oracle-lab
podman volume inspect oracle-lab-data
~~~

Rootless Podman may behave differently regarding port binding, volume permissions, cgroups, and networking. Verify host environment and image constraints. Do not assume every Docker Compose feature works identically across all Podman versions.

## 13. Automating VM creation with Vagrant

A VM is suitable when an independent guest OS is required. Vagrant defines VMs via configuration files and recreates them via commands.

Sample directory structure:

~~~text
oracle-vm-lab/
  Vagrantfile
  provision/
    site.yml
    files/
      compose.yaml
  inventory/
    ...
~~~

### 13.1 Vagrantfile

~~~ruby
Vagrant.configure("2") do |config|
  config.vm.box = ENV.fetch("ORACLE_LAB_BOX")
  config.vm.hostname = "oracle-lab"

  config.vm.network "private_network",
    ip: "192.168.56.20"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = 8192
    vb.cpus = 4
  end

  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "provision/site.yml"
  end
end
~~~

`ORACLE_LAB_BOX` is a box vetted and registered by the organization in Vagrant. Do not use boxes of unknown origin containing pre-installed databases or passwords.

8 GB RAM and 4 CPUs are only example values. Choose based on the Oracle release, memory target, host capacity, and workload.

### 13.2 Provisioning the VM

~~~bash
vagrant up
vagrant status
vagrant ssh
~~~

### 13.3 Stopping, snapshotting, and destroying the VM

~~~bash
vagrant halt
vagrant snapshot save clean-baseline
vagrant snapshot restore clean-baseline
vagrant destroy
~~~

A snapshot captures the VM state according to the hypervisor/Vagrant. Understand whether the snapshot includes disk and memory, and do not treat a running snapshot as a certified Oracle backup.

## 14. Provisioning a VM with Ansible

Ansible helps install packages, create directories, configure runtimes, copy Compose files, and launch containers. High-level playbook example:

~~~yaml
---
- name: Provision Oracle lab host
  hosts: all
  become: true

  vars:
    lab_dir: /opt/oracle-lab

  tasks:
    - name: Create lab directory
      ansible.builtin.file:
        path: "{{ lab_dir }}"
        state: directory
        owner: root
        group: root
        mode: "0750"

    - name: Copy Compose definition
      ansible.builtin.copy:
        src: files/compose.yaml
        dest: "{{ lab_dir }}/compose.yaml"
        owner: root
        group: root
        mode: "0640"

    - name: Start Oracle lab
      ansible.builtin.command:
        cmd: docker compose up -d
        chdir: "{{ lab_dir }}"
      register: compose_result
      changed_when: "'Started' in compose_result.stdout or 'Created' in compose_result.stdout"
~~~

This playbook only illustrates the Compose deployment step. Installing Docker/Podman, registry login, supplying `.env`, and managing secrets must be added according to your distro, collections, and organizational security standards.

### 14.1 Ansible Vault

Do not place plaintext database passwords in vars files or repositories. Use Ansible Vault or a secret manager to inject secrets. Enable `no_log` for tasks that might print credentials to stdout.

### 14.2 Idempotency

Dedicated Ansible modules are generally better than arbitrary `command` tasks because modules can determine before/after state. If using `command`, design `changed_when`, `creates`/`removes`, and state checks to avoid unnecessary re-execution.

## 15. Installing Oracle Database directly inside a VM

If you need OS-level testing or native Oracle Client/server configurations, you can install Oracle Database directly in the guest OS instead of running a container.

General steps:

1. Select an Oracle Linux/OS supported by the Oracle Database release.
2. Allocate CPU, RAM, disk, and filesystems.
3. Install prerequisite packages per the installation guide.
4. Download Oracle Database software from an authorized source.
5. Create a validated response file.
6. Install software using the silent installer.
7. Run root scripts in the order required by Oracle.
8. Create the database/PDB using DBCA silent mode or a managed template.
9. Configure listener and services.
10. Configure startup/shutdown and monitoring.
11. Run smoke tests and save the baseline.

### 15.1 Silent installation

Oracle Universal Installer and DBCA support silent mode with response files or command-line parameters depending on the release. Response file names, parameters, and prerequisites differ across versions.

Do not copy a 19c response file to 23ai or another release without checking documentation. Store response files in a secure configuration store and do not commit passwords.

### 15.2 DBCA

DBCA can create databases and PDBs per configuration. When automating:

- Choose a unique DB name/SID within the lab.
- Choose a character set matching the application.
- Choose CDB/PDB topology.
- Size memory targets according to VM RAM.
- Choose filesystem/ASM according to test goals.
- Define clear listener/service names.
- Create a least-privilege lab user.
- Enable `ARCHIVELOG` if tests require backup/recovery.

### 15.3 When is a native database install in a VM unnecessary?

If you only need a database for integration tests, containers typically involve fewer steps. Native VM installs are better suited when tests depend on OS packages, kernel, ASM, service management, or native Oracle Client/Database setups.

## 16. Automating with Packer

Packer can build pre-configured machine images/boxes. A pipeline can:

1. Pull an approved base image.
2. Spin up a temporary builder VM.
3. Install OS updates and prerequisites.
4. Install a container runtime or Oracle software per license.
5. Configure monitoring and hardening.
6. Clean up caches and temporary secrets.
7. Run smoke tests.
8. Export the VM image artifact.

Do not bake passwords, private keys, registry tokens, or personal data into machine images. Use provisioning-time secrets and rotate temporary credentials after the build.

## 17. Creating reproducible database test schemas

A lab needs more than a running database process. It needs schemas and datasets that can be recreated with identical results.

Manage:

- Schema DDL.
- Reference data.
- Test fixtures.
- Stored procedures/packages.
- Grants and roles.
- Database parameters required for testing.
- Migration versions.

Popular migration tools such as Flyway or Liquibase can apply versioned DDL. Test setups should run migrations from scratch on an empty database to catch hidden dependencies.

### 17.1 Do not use production dumps as default fixtures

Production data may contain personal, financial, or trade secret information. Use synthetic data or data masked according to an approved process.

### 17.2 Deterministic test data

For repeatable tests:

- Use fixed seeds for random data.
- Use fixed dates/times or Clock injection.
- Never rely on `SELECT` ordering without an `ORDER BY`.
- Create clearly namespaced test keys.
- Clean up data after tests via transaction rollback or schema reset.
- Do not share a single schema across parallel tests if conflicts can occur.

## 18. Isolating tests and avoiding conflicts

Several isolation levels exist:

### 18.1 One database, multiple schemas

Pros: lightweight and fast. Cons: shared resources and instance parameters; schemas can affect each other via shared objects/locks.

### 18.2 One database container per test suite

Pros: easy full-database reset and reduced conflicts. Cons: higher RAM/CPU/disk usage when running multiple suites.

### 18.3 One container per CI job

Pros: independent jobs, clean teardown. Suitable for integration tests if the host has adequate resources.

### 18.4 One VM per test group

Pros: stronger OS/network isolation. Cons: slower startup and resource-heavy.

### 18.5 Choosing isolation by objective

| Need | Appropriate isolation level |
|---|---|
| Unit tests not requiring Oracle | Mock/fake repository or test double |
| Small SQL integration tests | One Oracle container per test suite |
| Independent migration tests | Fresh container for each CI job |
| Native Oracle Client testing | VM or runner with pinned client |
| RAC/Data Guard testing | Dedicated multi-node lab |
| Running untrusted code | Managed VM/sandbox |

## 19. Integrating Oracle containers into CI

Typical pipeline:

~~~text
Checkout source
     |
     v
Pull pinned Oracle image
     |
     v
Start isolated database
     |
     v
Wait for database readiness
     |
     v
Create test user and schema
     |
     v
Run migrations
     |
     v
Run integration tests
     |
     v
Collect logs and reports
     |
     v
Stop and remove container/volume
~~~

### 19.1 Pipeline steps

1. Pull the image by pinned tag/digest.
2. Supply passwords from CI secrets.
3. Create an isolated volume/job network.
4. Start Oracle.
5. Retry until the SQL query succeeds.
6. Create schema and load fixtures.
7. Run integration tests.
8. Save test reports and database logs on failure.
9. Stop the container.
10. Delete the job's ephemeral volume.

### 19.2 Unique resource names per job

Use container, volume, and network names containing the build ID or job ID to prevent two pipelines from hitting the same database:

~~~text
oracle-ci-<job-id>
oracle-data-<job-id>
oracle-net-<job-id>
~~~

These names are illustrative conventions. CI runners must also clean up when jobs time out or are canceled.

### 19.3 Do not share volumes across parallel jobs

Two jobs must not mount the same datafile directory of a standalone database instance. Concurrent access to Oracle datafiles from multiple containers/instances is not a supported way to share a database.

Each instance needs its own storage, except in properly configured cluster architectures supported by Oracle.

### 19.4 Collecting logs before cleanup

If a test fails:

- Collect application test reports.
- Collect relevant Oracle alert/diagnostic logs.
- Collect container logs.
- Record the image tag/digest.
- Record the JDBC driver version.
- Record the database version and service.

Only then clean up ephemeral resources. Do not store passwords or sensitive data in CI artifacts.

## 20. Resetting the database between tests

Several strategies exist:

- Create a new container and volume for each suite.
- Create a new schema for each suite.
- Use migration rollback/cleanup.
- Restore a consistently created baseline snapshot.

### 20.1 Deleting volumes and recreating

~~~bash
docker compose down -v
docker compose up -d
~~~

This initializes a fresh database from scratch using the image and setup scripts. It deletes data inside the project's named volumes.

### 20.2 Resetting the schema

You can drop/recreate the test schema using automation with appropriate privileges. Ensure it never targets a shared schema or database by mistake.

### 20.3 Baseline snapshots

VM snapshots or storage snapshots can shorten reset times. However, the database must be in a supported state for snapshotting; crash-consistent snapshots are not always equivalent to application-consistent Oracle backups.

If guarantees are needed, use RMAN duplicate/restore or snapshot mechanisms supported by Oracle/storage vendors and test the restore.

## 21. Resource management

Oracle Database requires substantial RAM and shared memory. If under-provisioned, the database may start slowly, fail to open services, or get OOM-killed.

Monitor:

- Host and container RAM.
- CPU utilization.
- Free disk space.
- Volume growth.
- Shared memory.
- Container restart count.
- Database alert log.

### 21.1 Memory

Set memory limits appropriate for database SGA/PGA and OS overhead. Never set the container memory limit lower than total database demand.

### 21.2 CPU

Too low a CPU quota can slow down startup and tests. Use appropriate limits so one lab does not starve the entire host.

### 21.3 Storage

Monitor volumes and filesystems. Oracle datafiles can autoextend, so enforce capacity limits and alerts before the host runs out of disk space.

### 21.4 Shared memory

Some Oracle containers require a sufficiently large `shm-size`. Values must follow image/database release guidelines and memory configuration.

## 22. Lab security

A lab is still a database server with a listener and credentials. Principles:

- Publish the listener only to loopback if used solely locally.
- Never use production passwords.
- Never expose database ports to the Internet.
- Use a least-privilege lab user.
- Do not run applications as `SYS`/`SYSTEM`.
- Do not mount the Docker socket into application containers unless necessary.
- Do not run images from untrusted sources.
- Pin image versions/digests.
- Keep images and host runtimes updated.
- Never store unmasked production data.
- Restrict read permissions on volumes and wallets.
- Clean up secrets after tests.

Containers can be configured as privileged or with broad host path mounts; avoid these privileges for standard labs.

## 23. Multi-database/service environments

Multiple containers can be run for different objectives:

- Oracle Database Free for SQL/PLSQL labs.
- Another database release for compatibility checks.
- One container as source and one as target for migrations.
- One database dedicated to integration tests and another for performance tests.

Each instance needs:

- Its own container name.
- Its own host port if published.
- Its own volume.
- A documented service name.
- A CPU/RAM budget.
- Network isolation.

Never run two standalone database instances mounting the same Oracle data directory.

## 24. Testing JDBC in the lab

Once Oracle is ready, run a smoke test:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps =
         connection.prepareStatement("SELECT sys_context('USERENV','SERVICE_NAME') FROM dual");
     ResultSet rs = ps.executeQuery()) {

    if (!rs.next()) {
        throw new IllegalStateException("Oracle returned no row");
    }

    System.out.println("Connected service: " + rs.getString(1));
}
~~~

The smoke test should verify:

- Connection to the right database/service.
- User mapped to the right schema.
- Ability to execute `SELECT`.
- Ability to `INSERT`/`UPDATE`/`ROLLBACK` on fixtures.
- Character sets and data types.
- Migration execution.
- Proper connection pool handling.

Do not merely ping port 1521; an open port does not prove the database is ready.

## 25. Testing migrations and version compatibility

An isolated environment is useful for verifying:

- Flyway/Liquibase migrations.
- DDL on fresh schemas.
- Newer JDBC drivers.
- Database upgrade compatibility.
- Data Pump import/export.
- RMAN backup/restore in an appropriate lab.
- Flashback features by edition/version.
- Stored procedure/package compilation.
- Constraint and index rebuilds.

For version compatibility testing, run both the exact database version production uses and the target version. Do not rely solely on `latest` images.

## 26. Troubleshooting containers

### Container exits immediately after starting

Check:

- Did the image pull succeed?
- Were registry terms accepted?
- Is the CPU architecture supported?
- Does `ORACLE_PWD` meet requirements?
- Are RAM/shared memory sufficient?
- Are volume permissions correct?
- Do logs show initialization errors?

### Container is running but unreachable

Check:

- Has database startup completed?
- Is the listener running?
- Is the PDB/service open?
- Is host port mapping correct?
- Is a firewall or local security software blocking it?
- Does the URL use the right service?

### Data lost after recreate

Check:

- Was the named volume mounted?
- Was `docker compose down -v` accidentally run?
- Did the image change its mount path?
- Is the datafile directory correct?

### Permission denied on volume

Check the UID/GID of the Oracle user in the image, filesystem, and SELinux. Do not use `chmod 777` as a default fix.

### Out of disk

Check Docker volumes, filesystems, autoextend, logs, and dump files. Delete lab data properly per procedure; never delete open database files with OS commands.

## 27. Troubleshooting VMs

### VM fails to boot

Check:

- Is virtualization support enabled in the hypervisor?
- Is nested virtualization needed?
- Are host RAM/CPU sufficient?
- Does the box match the provider?
- Is disk space available?

### Provisioning fails

Check Ansible inventory, SSH, become privileges, package repositories, network, and task logs. Re-run the playbook after fixing idempotency errors.

### Database fails to start

Check the alert log, filesystem, listener, environment variables, ownership, and database service. Do not delete datafiles to force DBCA to run again.

### VM snapshot cannot be restored

Check hypervisor version, snapshot chain, and disk capacity. Maintain independent backups if data is important; snapshots are not a sole backup strategy.

## 28. Choosing between Containers and VMs

| Decision criterion | Container | VM |
|---|---|---|
| Fast startup for SQL labs | Very suitable | Can be too heavy |
| Integration tests in CI | Very suitable | Suitable but slower |
| Testing Oracle JDBC Thin | Suitable | Suitable |
| Testing JDBC OCI native client | Possible, requires native libs | Suitable |
| Testing OS packages/systemd | Limited | Suitable |
| Multi-subnet network testing | More limited | More flexible |
| Multi-node RAC/Data Guard | Requires specialized design | Dedicated VM lab |
| Running untrusted code | Do not use as sole boundary | More suitable if hardened properly |
| Limited host resources | Usually lighter | Usually heavier |
| Infrastructure reproducibility | Compose/image | Packer/Vagrant/Ansible |

Recommendations:

- Learning SQL, PL/SQL, JDBC, and schema migrations: Oracle Database Free container.
- Testing native Oracle Client/OCI: VM or controlled container image with native client.
- Testing OS and networking: VM.
- CI integration tests: ephemeral container.
- RAC/Data Guard: dedicated multi-node lab, never simulated with a single container.

## 29. Complete automated workflow templates

A local workflow:

~~~text
1. Clone lab repository
2. Check Docker/Podman
3. Pull pinned image
4. Load secret from local secret store
5. docker compose up -d
6. Wait for SQL readiness
7. Run setup/migrations
8. Run tests
9. Save logs/reports
10. Stop container
11. Keep or remove volume according to objective
~~~

A CI workflow:

~~~text
1. Allocate isolated runner/job ID
2. Authenticate to approved registry
3. Start Oracle container with ephemeral volume
4. Wait for service and PDB
5. Create least-privilege test schema
6. Run migration and integration tests
7. Collect logs on failure
8. Publish test reports
9. Remove container, network and ephemeral volume
10. Verify cleanup
~~~

A VM workflow:

~~~text
1. Select approved base box
2. vagrant up
3. Ansible provision OS and runtime
4. Deploy Oracle container or install database
5. Wait for readiness
6. Run test suite
7. Capture diagnostics
8. Snapshot clean baseline or destroy VM
~~~

## 30. Common mistakes

| Mistake | Consequence | Correct practice |
|---|---|---|
| Using the `latest` tag in CI | Results change on image updates | Pin version tag/digest |
| Using images from unknown sources | Supply chain and license risks | Use approved publishers/repositories |
| Thinking containers mean free license | Terms violation | Check edition and entitlement |
| Not mounting a persistent volume | Data lost when container is deleted | Use named volumes |
| Running tests right after `docker run` | Database not ready yet | SQL readiness probe and bounded retries |
| Publishing 1521 on all interfaces | Exposes lab database to LAN | Bind loopback or private network |
| Using `localhost` from an app container | Connects to the app container itself | Use service DNS |
| Sharing a volume across multiple instances | Corrupts database files | Separate storage per instance |
| Committing `.env`/passwords | Credential leakage | Secret manager and `.gitignore` |
| Using `SYS` for test applications | Overly broad privileges | Create a dedicated schema user |
| Assuming setup scripts run on every restart | Schema is not updated | Understand image lifecycle, use migrations |
| Resetting via restart | Old data persists | Intentionally recreate volume/schema |
| Running `down -v` without checking | Deletes database volume | Verify project/volume first |
| Using containers as a boundary for untrusted code | Host kernel/runtime risk | Use VMs/sandboxes |
| Not limiting RAM/disk | Host runs out of resources | Budgets and monitoring |
| Using unmasked production dumps | Data leakage | Synthetic/masked fixtures |
| Testing only one version | Misses compatibility issues | Pin and run version matrix |
| Not cleaning up CI jobs | Accumulation of volumes/containers | Clean up even on failure/cancel |

## 31. Self-check exercises

Perform on a personal machine or authorized runner using dummy data.

### Exercise 1 — Pull Oracle Database Free

Log in to the registry if needed, pick a specific tag, and record the image digest.

### Exercise 2 — Run the container

Create a named volume, publish the loopback port, supply `ORACLE_PWD` from a secret, and start the database.

### Exercise 3 — Verify readiness

Follow logs and run `SELECT 1 FROM dual` through the PDB service.

### Exercise 4 — JDBC connection

Use the Thin driver, PDB service name, and lab user. Record driver/database versions.

### Exercise 5 — Initialize schema

Mount a SQL setup script to create a user and schema fixture. Verify the script runs only according to the image's supported lifecycle.

### Exercise 6 — Persistent volume

Restart and recreate the container, verifying data remains. Then in a separate lab run `down -v` and verify the database is recreated fresh.

### Exercise 7 — Compose network

Run a test app container on the same network and connect via the `oracle` service hostname.

### Exercise 8 — Vagrant

Create a VM from an approved box, allocating RAM/CPU and a private network.

### Exercise 9 — Ansible

Provision the runtime and deploy the Compose file with an idempotent playbook.

### Exercise 10 — CI cleanup

Simulate both passing and failing tests; verify logs are captured before ephemeral containers/volumes are removed.

### Exercise 11 — Resource limits

Measure RAM/CPU/disk during database startup and test execution. Experiment with limits in the lab and observe the impact.

### Exercise 12 — Compare Container vs. VM

Run the same integration suite on a container and a VM. Compare startup time, test duration, resource usage, and operational complexity.

## 32. Checklist before sharing a lab with the team

**Source and version**

- Do images/boxes come from approved sources?
- Are tags/digests pinned?
- Are edition and license terms clear?
- Are Oracle release and service names documented?

**Isolation**

- Does the database avoid pointing to production?
- Are ports opened only as narrowly as needed?
- Are volumes and networks isolated?
- Do CI jobs have unique resource names?

**Data and secrets**

- Is only synthetic/masked data used?
- Are passwords retrieved from a secret store?
- Are `.env`, wallets, and private keys excluded from commits?
- Do application users have least privileges?

**Reproducibility**

- Are Compose/Vagrant/Ansible files in the repository?
- Are init scripts and migrations versioned?
- Does a readiness check run before tests?
- Can the environment be reset to a clean state?

**Operations**

- Are RAM/CPU/disk limits configured?
- Are logs collected?
- Does CI clean up even on failure?
- Are there instructions on when to keep or delete volumes?
- Is there an owner for updating images and dependencies?

## 33. Key takeaways

| Concept | What to remember |
|---|---|
| Container | Isolates processes while sharing the host kernel |
| VM | Separate guest OS/kernel running on a hypervisor |
| Oracle Database Free | Suitable for labs within product limits |
| Oracle Container Registry | Oracle image source; may require login/term acceptance |
| Image tag/digest | Identifies the exact image version to reproduce |
| Docker Compose | Declares services, ports, volumes, and networks |
| Named volume | Keeps data independent of the container |
| Bind mount | Attaches a host directory; requires permission management |
| Init/setup script | Bootstraps the database per the image lifecycle |
| Readiness check | Verifies SQL/service availability |
| `FREEPDB1` | Example PDB service on some Oracle Free images |
| Vagrant | Creates/manages VMs via configuration |
| Ansible | Provisions OS and deploys repeatable configurations |
| Packer | Builds automated machine images/boxes |
| Secret manager | Supplies credentials without committing secrets |
| Ephemeral CI volume | Data storage lasting only for a single job |
| Snapshot | Point-in-time state; does not replace database backups |
| Synthetic data | Safe dummy data for testing |
| Cleanup | Properly removes containers/networks/volumes after tests |

To build a reproducible Oracle lab, pin images or VM boxes, manage configurations with Compose/Vagrant/Ansible, keep datafiles in separate volumes, supply secrets securely, and wait for SQL readiness before running tests. Containers fit SQL/JDBC integration tests and CI; VMs fit OS, native client, or stronger isolation needs. Use Oracle Database Free where product terms allow, verify licenses for all images/editions, never use unmasked production data, and always distinguish restarts, recreates, and volume resets from backup/restore. A good environment must be reproducible, verifiable, and cleanly torn down after each test run.
