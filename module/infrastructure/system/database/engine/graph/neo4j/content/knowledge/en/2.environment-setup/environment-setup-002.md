# Installing Neo4j and Verifying Version-Specific System Requirements

## 1. Lesson Objectives

**Neo4j** is a graph database management system based on the **property graph** model: information resides in **nodes**, directed **relationships** connecting nodes, and **properties** describing them. The **Cypher** language lets you query relationships, connection patterns, and paths. Before moving on to indexes, constraints, data import, query tuning, or connecting via the Java Driver and Spring Data Neo4j, you first need to **install the right Neo4j version in a compatible environment**.

By the end of this lesson, you will be able to:

1. Distinguish between the **Neo4j DBMS** version, the **Cypher** version, the **JVM running the server**, and the **Java Driver running in the application**.
2. Cross-check the Neo4j version against operating system, CPU architecture, Java, RAM, and storage capacity.
3. Choose an official download package, verify the version/edition, and start Neo4j via Desktop, server package, or Docker.
4. Verify the service via Browser, Cypher, and logs; identify root causes when startup fails.
5. Create a repeatable installation checklist for Java/Spring Boot practice.

> **Documentation baseline:** Specific examples in this lesson reference Neo4j **2026.10.2** documentation (released November 2026). This is an **intentional illustrative version**, not a requirement to always use the latest release. When running real projects, consult the documentation for the exact version chosen, especially when OS/JVM support policies change.

## 2. Understanding "Neo4j Version" Correctly Before Installing

### 2.1. Neo4j Server uses two numbering schemes

- Older branches use forms like **4.4**, **5.x**, for example **5.26 LTS**.
- Starting with **2025.01**, Neo4j Server uses a **CalVer** release schedule of the form **YYYY.MM.Patch**, such as `2026.10.2`. This denotes the release date and patch level; do not interpret `2026.10` as "Java 26" or "Cypher 26".
- Certain releases are designated as **LTS (Long-Term Support)**; review the support lifecycle and upgrade guide when choosing between an LTS release and a newer release.
- **Community Edition** and **Enterprise Edition** differ in features and licensing terms. Do not assume a command runs on every edition just because the server version is the same.

### 2.2. Neo4j Server ↔ Java Matrix for Native Installations

According to [Neo4j Operations Manual – System requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/):

| Neo4j Server version | Supported JVM by branch | Notes |
| --- | --- | --- |
| **2025.10 and later**, including **2026.10.2** | **Java 21 or Java 25** | Choose a Java version supported by Neo4j on the exact OS |
| **2025.01 to before 2025.10** | **Java 21** | Java 17 does not meet the requirement |
| **5.14 to 5.26 LTS** | **Java 17 or Java 21** | Also check the specific release and OS |
| **5.x before 5.14** | **Java 17** | Newer Java milestones must be confirmed in that release's docs |
| **4.x** | **Java 11** | Legacy branch; do not choose for new projects without compatibility reasons |
| **3.x** | **Java 8** | Mentioned only for identifying legacy environments |

**Comparison examples:**

- Machine has **Java 17**, wanting to install **Neo4j 2026.10.2** from ZIP/TAR: **does not meet requirements**. Install Java 21/25 appropriate for the OS, or pick a Neo4j version compatible with your project requirements.
- Machine has **Java 21**, wanting to run **Neo4j 5.26 LTS** or **2026.10.2**: the **major Java** requirement is satisfied for both; still check OS, CPU architecture, and JDK vendor.
- Java project where the application runs on **Java 17** and Neo4j 2026 DBMS runs on another host/process using **Java 21**: **can be valid** if the application's Java Driver version supports the Neo4j Server. Both processes are not forced to use the same JVM.

> **Three separate components:** `java -version` on the host shows Java in the terminal; the Neo4j DBMS uses the JVM configured for the **server process**; the Java application uses its own JVM and its own **Java Driver**. Neo4j Desktop includes a mechanism to supply the JDK for DBMSs it manages; Docker images also bundle their runtime, so installing Java 21 on the host is not strictly required to run a container.

### 2.3. Do not confuse Cypher version and DBMS version

Since **Neo4j 2025.06**, Neo4j provides **Cypher 5** and **Cypher 25** language versions. Configuration can set the default version for the DBMS/database, and queries can also specify it explicitly:

~~~cypher
CYPHER 5
RETURN 'Running with Cypher 5' AS result;
~~~

Starting from **2026.02**, the distributed default `neo4j.conf` sets `db.query.default_language=CYPHER_25` for new databases. Existing databases may retain their own language configuration. When learning syntax or importing queries from older projects, record **both the DBMS version and the Cypher version** to explain syntax/behavior differences. See [Neo4j Operations Manual – Introduction](https://neo4j.com/docs/operations-manual/current/introduction/) and [Configure Cypher version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/).

## 3. Checking System Requirements Before Downloading

### 3.1. Preflight workflow in the proper order

~~~mermaid
flowchart TD
  A["Determine Neo4j version / edition"] --> B["Choose deployment method"]
  B --> C{"Desktop or Docker?"}
  C -- "Yes" --> D["Check Desktop/Docker requirements and host resources"]
  C -- "No (Native server)" --> E["Check OS, CPU, JDK per version"]
  D --> F["Check RAM, disk, ports, and write permissions"]
  E --> F
  F --> G{"All checks pass?"}
  G -- "No" --> H["Update environment or choose compatible version"]
  H --> B
  G -- "Yes" --> I["Download package for right edition and arch, install and verify"]
~~~

First write down four items: **intended version**, **Community/Enterprise**, **runtime method (Desktop/native/Docker)**, and **OS + CPU**. Only then check Java, because Java requirements for a self-installed native server differ from Desktop/Docker.

### 3.2. CPU, RAM, and storage requirements

According to the [System requirements table](https://neo4j.com/docs/operations-manual/current/installation/requirements/), Neo4j supports **x86_64** and **ARM** platforms in the listed configurations:

| Environment type | Reference CPU, RAM, storage | Practical meaning |
| --- | --- | --- |
| **Personal/development** | Reference minimum **2 GB RAM**, **10 GB storage**; **16 GB RAM or more** recommended | Leave RAM headroom for the OS, Docker/IDE, application, and page cache |
| **Self-managed server** | Reference minimum **8 GB RAM**; actual sizing depends on data volume and workload | Must account for heap, page cache, file descriptors, I/O, and backups |
| **Self-managed cloud VM** | Reference minimum **2 vCPU, 2 GB RAM, 10 GB storage** | Only a starting point, not production sizing |

Neo4j generally benefits from **SSD/NVMe**, since many workloads perform random reads. "Having 10 GB of disk" does not guarantee enough space for data, transaction logs, imports, and backups. On machines running Docker Desktop, remember to account for RAM allocated to the Docker VM/engine.

### 3.3. Supported operating systems and JVMs

In the **2026.10.2** documentation, listed development operating systems include **Windows 11**, **macOS 13/14/15/26**, **Ubuntu Desktop 22.04/24.04/26.04 LTS**, and **Debian 11/12/13**. Server operating systems have a **separate** support list (such as Windows Server 2022/2025 and corresponding Linux distributions). Some older OS versions are marked **deprecated** and may be dropped in future releases.

**Key point:** Do not just see `21` or `25` in `java -version` and conclude it passes. Check the **combination of OS + JDK vendor (Oracle, OpenJDK, Zulu, Temurin, ...)** in the corresponding table for your Neo4j version. For example, the Windows 11 table for 2026.10.2 lists **OracleJDK/ZuluJDK 21/25**, whereas many Linux distributions also list OpenJDK/Temurin.

### 3.4. Commands to gather machine information

**Linux (Ubuntu/Debian/RHEL):**

~~~bash
cat /etc/os-release     # OS name and version
uname -m                # x86_64, aarch64, ...
java -version           # If installing Neo4j Server natively
free -h                 # RAM
df -h .                 # Available space on current filesystem
~~~

**macOS (Terminal):**

~~~bash
sw_vers                 # macOS version
uname -m                # arm64 or x86_64
java -version           # Current JVM, if present
sysctl -n hw.memsize    # RAM in bytes
df -h .                 # Disk capacity
~~~

**Windows (PowerShell):**

~~~powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
java -version
Get-PSDrive -PSProvider FileSystem
~~~

If Java is not installed yet, seeing `java -version` report an unrecognized command is normal for Desktop/Docker; for a **native server**, you must install a compatible JVM before starting. To see **which** Java is used when multiple JDKs are installed, also check `where.exe java` (Windows) or `which java` (Linux/macOS), and verify `JAVA_HOME` or the service's environment variables.

### 3.5. Checking ports, filesystem, and permissions

Neo4j typically serves the HTTP UI on `localhost:7474` and Driver connections over **Bolt on `localhost:7687`**. These ports can be changed in configuration. Before starting a second instance, check whether the ports are already occupied:

~~~bash
# Linux: list listening TCP ports
ss -lnt
~~~

~~~powershell
# Windows PowerShell
Get-NetTCPConnection -State Listen -LocalPort 7474,7687 -ErrorAction SilentlyContinue
~~~

For native installations, the user running Neo4j needs read permissions for configuration and write permissions for **data, logs, and transaction logs**. On Linux, documentation supports **EXT4/XFS** for relevant configurations, requiring proper flush semantics to guarantee ACID; do not place databases on arbitrary network shares. On Windows, use a supported default filesystem and **do not use FAT**. With Docker, permissions on the bind-mounted directory/volume must allow the container process to write data.

## 4. Choosing a Download Source and Managing Versions

Download **Neo4j DBMS** from the [Neo4j Deployment Center](https://neo4j.com/deployment-center/) or official Neo4j package/container repositories. Select the exact **edition**, **OS package**, **CPU architecture**, and **version**. Before deploying:

1. Record the full version, e.g., `2026.10.2` or `5.26.x`; avoid letting `latest` silently shift your learning/test environment.
2. Check the support matrix and release notes for **that version**; a newer DBMS does not guarantee automatically opening an older data store if upgrade procedures are skipped.
3. If downloading ZIP/TAR/DEB/RPM, verify **SHA-256** against the checksum published on the download page before installing.
4. Respect edition licensing. **Enterprise Edition** requires appropriate license compliance; the Developer edition bundled with Desktop is for development use under its applicable terms.

Checksum verification examples:

~~~bash
# Linux (replace filename with the downloaded archive)
sha256sum neo4j-package.tar.gz
~~~

On **macOS**, you can run `shasum -a 256 neo4j-package.tar.gz` to compute the same hash.

~~~powershell
# Windows PowerShell
Get-FileHash .\neo4j-package.zip -Algorithm SHA256
~~~

Compare the entire hash string against the official value; this verifies the download integrity, and **does not** by itself prove an arbitrary package carries a valid digital signature.

## 5. Installing with Neo4j Desktop (Suitable for Beginners)

Neo4j Desktop 2.x supports managing multiple local DBMSs across different versions as well as remote connections. Desktop supplies the appropriate JDK for the DBMSs it manages; you do not need to configure a host JVM like a native server. However, you must still verify OS and resource compatibility **for both Desktop and the DBMS you intend to run**.

### Steps

1. Download Desktop from [Neo4j Desktop installation](https://neo4j.com/docs/desktop/current/installation/) or Deployment Center, and run the OS installer.
2. Open Desktop, create a **local DBMS instance**, and **explicitly select the Neo4j version** (e.g., `2026.10.2` if distributed).
3. Record the selected version and edition. Set a strong password for the `neo4j` admin user.
4. Click **Start** and wait for the ready state. If it fails, inspect the instance's **Logs/Settings**.
5. Open **Query/Neo4j Browser** from Desktop and run the verification queries in Section 9.

**Important distinction:** The **Desktop** version is not the same as the **DBMS** version running inside it. When checking compatibility with a Java application, record the instance's **Neo4j Server version**. If creating two instances on the same host, each instance needs separate ports or appropriate connection management.

## 6. Installing Neo4j Server Directly on the OS

This option helps you learn about processes, services, configuration files, filesystems, and resources. Choose it only when you have machine administration access and have verified OS/JVM in Section 3.

### 6.1. Ubuntu/Debian via the official APT repository

Neo4j publishes an APT repository at **debian.neo4j.com**. Per the [current .deb installation guide](https://neo4j.com/docs/operations-manual/current/installation/linux/debian/), you can add the repository using a **GPG keyring**, then install a specific version.

Example commands on a **Neo4j-supported** Ubuntu/Debian host with `sudo` privileges:

~~~bash
# 1. Create directory for GPG keyrings
sudo mkdir -p /etc/apt/keyrings

# 2. Fetch public key from Neo4j repo and convert to keyring format
wget -O - https://debian.neo4j.com/neotechnology.gpg.key |
  sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg
sudo chmod a+r /etc/apt/keyrings/neotechnology.gpg

# 3. Declare repository
echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable latest' |
  sudo tee /etc/apt/sources.list.d/neo4j.list
sudo apt-get update

# 4. List available versions and install the exact version for this lesson
apt list -a neo4j
sudo apt-get install neo4j=1:2026.10.2
~~~

The `1:` prefix in `neo4j=1:2026.10.2` is a Debian package **epoch**, not part of the DBMS version. The `stable latest` repository entry still exposes newer releases over time; pinning the exact package helps prevent unintended upgrades. For long-term host management, also consider package pin/hold policies and backup-backed upgrade procedures.

The Enterprise package is named `neo4j-enterprise` and requires separate license acceptance. On some Ubuntu Server installations, the `universe` repository must be enabled for dependencies. For tighter manual control, download the Linux TAR from Deployment Center following [Linux executable (.tar)](https://neo4j.com/docs/operations-manual/current/installation/linux/tarball/).

After installation, Neo4j is typically managed with `systemd`:

~~~bash
# Set initial password BEFORE the DBMS starts for the first time
sudo -u neo4j neo4j-admin dbms set-initial-password 'REPLACE_WITH_STRONG_PASSWORD'

# Start service and verify
sudo systemctl start neo4j
sudo systemctl status neo4j
sudo journalctl -u neo4j -n 100 --no-pager
~~~

The `set-initial-password` command is only for **initialization**, not for resetting the password of a database that already has accounts. Passwords passed on the command line may appear in shell history or process listings: on shared hosts, follow your organization's secret/credential workflow and never place real passwords in scripts or Git.

> **Permission note:** The example uses the `neo4j` service user created by the APT package. Depending on installation method and system policy, permissions to run `neo4j-admin` may vary; follow the [systemd guide](https://neo4j.com/docs/operations-manual/current/installation/linux/systemd/) for your chosen version. In an isolated fresh lab you may leave the default `neo4j` password and change it immediately upon first login, but never do this in a network-accessible environment.

### 6.2. Windows via ZIP

1. Verify a supported OS, installed Java, and `java -version` in the terminal Neo4j will use.
2. Download the matching **Windows Executable ZIP** from Deployment Center and verify SHA-256.
3. Extract to a fixed path (for example `C:\neo4j\neo4j-2026.10.2`). Avoid placing important data directories in locations that will be wiped during upgrades.
4. In **Command Prompt** at the extracted root directory, start the server:

~~~bat
bin\neo4j console
~~~

5. Wait for the service/connector ready message, then open `http://localhost:7474` and log in.

On Windows you can also install it as a **Windows Service**, though service configuration, execution privileges, and service Java setup must follow [Neo4j Windows installation](https://neo4j.com/docs/operations-manual/current/installation/windows/) for the exact version. If the server runs cleanly in console mode but fails as a service, start by comparing the **service account, Java environment variables, and read/write permissions**.

### 6.3. macOS via TAR or Homebrew

- Check macOS/CPU and Java version first; Apple Silicon uses `arm64`, Intel machines are typically `x86_64`.
- With a TAR package from Deployment Center, extract it and run `bin/neo4j console` inside the install directory (after following configuration setup instructions).
- Homebrew supports installing **Community Edition**; per documentation:

~~~bash
brew install neo4j
brew services start neo4j
brew services list
~~~

Homebrew may provide a newer release depending on when the command is run. If you need an **exact version** across a study/test team, verify the actual installed version afterward, check version-pinning options, or use TAR/Docker. See [Neo4j macOS installation](https://neo4j.com/docs/operations-manual/current/installation/osx/).

### 6.4. Directories and configuration files

| Component | Typical location | Purpose |
| --- | --- | --- |
| `neo4j.conf` | `<NEO4J_HOME>/conf` for ZIP/TAR; `/etc/neo4j` on Linux packages | Connectors, memory, and DBMS configuration |
| `data` | Configured via `server.directories.data` | Stores databases; **do not delete when preserving data** |
| `logs` | Configured via `server.directories.logs` | Startup logs, config errors, and operational logs |
| `plugins` | Plugin directory per installation | Only install plugins compatible with the server version |
| `bin` | Inside `NEO4J_HOME` or `/usr/bin` depending on package | `neo4j`, `neo4j-admin`, `cypher-shell` |

Actual paths vary by package and OS; consult [Default file locations](https://neo4j.com/docs/operations-manual/current/configuration/file-locations/) rather than copying paths from another machine.

## 7. Installing via Docker with a Pinned Version Tag

Docker is suitable when you need the exact same image across multiple machines or CI. **Neo4j 2026.10.2 Community Edition** has the tag `neo4j:2026.10.2`; Enterprise has a matching tag with the `-enterprise` suffix and requires license acceptance. Verify tag details in [Docker introduction](https://neo4j.com/docs/operations-manual/current/docker/introduction/).

Check Docker:

~~~bash
docker version
docker info
~~~

Pull the official image and start **a local practice container**:

~~~bash
docker pull neo4j:2026.10.2

docker run --detach --name neo4j-lab \
  --publish 127.0.0.1:7474:7474 \
  --publish 127.0.0.1:7687:7687 \
  --env NEO4J_AUTH=neo4j/REPLACE_WITH_STRONG_PASSWORD \
  --volume neo4j_lab_data:/data \
  neo4j:2026.10.2

docker ps --filter name=neo4j-lab
docker logs --tail 100 neo4j-lab
~~~

The snippet above uses **Linux/macOS shell (Bash)** syntax; PowerShell has different line-continuation rules—either put the `docker run` command on **one line** or use Docker Compose. Replace the placeholder password before running; passing a password as an argument is only a brief lab illustration and is unsuitable for production secret management.

Open `http://localhost:7474` and log in with `neo4j` and the configured password. Both ports are bound to **127.0.0.1** so only the host machine can access them during the lesson. The named volume `neo4j_lab_data` retains data when the container is replaced.

~~~bash
# Stop container without removing volume
docker stop neo4j-lab
docker start neo4j-lab

# Inspect the image/version the container is running
docker inspect neo4j-lab --format '{{.Config.Image}}'
~~~

**Do not** run `docker rm -v` or delete the volume if you still need the practice data. Changing `NEO4J_AUTH` after the volume already contains a user/password **does not** change the credentials stored in the database. To connect from Spring Boot running in another container, configure a shared network and address by service/container name; `localhost` inside the app container does not point to the Neo4j container.

**Difference in JVM checks:** The Neo4j container's JVM lives inside the image, so `java -version` on the host does not represent the server JVM. When needed, run the check inside the container (if the image includes the tool):

~~~bash
docker exec neo4j-lab java -version
~~~

## 8. Where Does "Installation" Happen When Using AuraDB?

**Neo4j AuraDB** is a managed service, so **you do not download/install Neo4j Server or configure server Java** on your development machine. You create an instance in [Aura Console](https://console.neo4j.io/), obtain the `neo4j+s://...` URI, username, and password, and run Cypher from the Query UI or an application. Hardware sizing, JVM allocation, and Neo4j Server upgrade timing are handled by the service.

You still must verify **Driver version**, network/TLS connectivity, and AuraDB tier resource limits. Your development machine does not need the server installed, though it still needs a compatible Java/JDK if running a Java application.

## 9. Post-Install Checks: How to Know You Have the Right Version

### 9.1. Checking service, ports, and connectivity

1. Confirm the process/service/container is running and not crash-looping.
2. Open `http://localhost:7474` for local setups (or the actual HTTP endpoint); log in with the account of the **instance** you just installed.
3. For the Java Driver, the local URI is typically `bolt://localhost:7687`, not the Browser HTTP URI.
4. Run a read-only Cypher check:

~~~cypher
RETURN 1 + 1 AS result, datetime() AS serverTime;
~~~

The expected output has one row with `result = 2` and a timestamp. If Browser opens but Cypher execution fails, inspect **Bolt, authentication, and the target database**—do not conclude installation is complete yet.

### 9.2. Verifying exact server version and edition

Once logged in, run:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

The result returns DBMS component details, the **versions list**, and the **edition**. Record the actual DBMS value and compare it against your chosen version. This is more reliable than guessing from a download filename or the Desktop UI version.

You can check active databases with:

~~~cypher
SHOW DATABASES;
~~~

Administrative commands may show different information depending on **account privileges and edition**; if you lack permission to view all databases, use an appropriate administrative account for admin labs.

### 9.3. Testing a small property graph

~~~cypher
MERGE (u:User {userId: 'lab-001'})
  ON CREATE SET u.name = 'An'
MERGE (p:Project {projectId: 'neo4j-lab'})
  ON CREATE SET p.title = 'Install Neo4j'
MERGE (u)-[:MEMBER_OF]->(p)
RETURN u.name AS user, p.title AS project;
~~~

Read it back:

~~~cypher
MATCH path = (:User {userId: 'lab-001'})-[:MEMBER_OF]->(:Project {projectId: 'neo4j-lab'})
RETURN path;
~~~

This confirms the DBMS can persist **nodes**, **properties**, and **relationships** and read back paths rather than merely responding to constant expressions. `MERGE` allows re-running the sample while avoiding duplicates in a simple lab; under concurrent access, real data still requires designing **uniqueness constraints**.

### 9.4. Checking persistence

For a local server or a container **with an attached volume**, stop the service cleanly, restart it, and re-run the `MATCH` query. If the graph remains, you have verified data survives beyond a session lifecycle. With AuraDB, log out and reconnect to verify at the service level.

If the database is empty after recreating a container, inspect the volume mounted at `/data`, the volume name, and whether the volume was removed beforehand.

## 10. Connecting with Java Driver and Spring Data Neo4j

When moving on to the Java Driver or Spring Data Neo4j, verify **two independent compatibility ranges**:

| Component | Requirements to verify | Example |
| --- | --- | --- |
| **Self-hosted Neo4j 2026.10.2 Server** | Server OS + JVM per 2026.10 docs | Choose supported Java 21 or Java 25 |
| **Java Driver** | **Application** JDK and supported **Neo4j Server** versions | Java Driver **6.x** supports servers **4.4, 5.x, 2025.x, 2026.x** and requires Java **17+** per current docs |
| **Spring Data Neo4j** | Compatibility matrix across Spring Boot, Spring Data, and Driver | Choose dependencies via Spring Boot BOM and check release notes |
| **Plugins (APOC, GDS, ...)** | Plugin version matches edition and Neo4j Server | Do not copy plugin JARs from an older install to a newer one |

Source: [Neo4j Java Driver – Installation](https://neo4j.com/docs/java-manual/current/install/). This is why you must not apply the server's **Java 21/25** requirement to conclude that every Java application must compile with Java 21/25.

When moving an application from local to Docker or AuraDB, swap the **connection URI** and credentials per environment:

~~~properties
# application.properties (read values from environment variables)
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Typical URI values: `bolt://localhost:7687` for Java on the host; `bolt://neo4j:7687` for apps on the same Docker Compose network; `neo4j+s://...` for AuraDB with TLS. Never store real credentials in source code, repositories, or logs.

## 11. Layered Troubleshooting

| Symptom | Likely cause | Verification / fix |
| --- | --- | --- |
| `UnsupportedClassVersionError` or JVM fails to start | Java version lower than server requirement | Compare `java -version` and the **service's** Java against the matrix in Section 2 |
| Desktop starts but local DBMS won't start | Instance DBMS/JDK, file permissions, insufficient resources, or port conflict | Inspect **instance Logs**, verify DBMS version and ports |
| Linux package install reports missing `daemon` dependency | `universe` repo not enabled on Ubuntu Server or broken repo | Read `.deb` docs, check `apt-cache policy` and sources list |
| `Connection refused` on `localhost:7687` | DBMS not ready, wrong port, Bolt not listening | Check logs/ports and URI; wait for server startup |
| `Address already in use` | HTTP/Bolt port taken by another instance | Change port in config or stop the old instance |
| `Authentication failed` | Wrong password, wrong instance, or volume retains old credentials | Confirm instance/credentials; change password via proper admin mechanism |
| Docker runs but data disappears after recreate | `/data` not mounted to volume or volume deleted | Inspect mounts and Docker command history; preserve volume on recreate |
| `OutOfMemoryError` or container killed | Insufficient RAM/page cache/heap, Docker resource limits | Check logs and memory limits; size for workload rather than guessing |
| Plugin fails to load | Plugin does not match Neo4j edition/version | Check the plugin's own compatibility matrix |
| New server runs but Cypher syntax differs from old docs | Different default Cypher version or feature changes across releases | Record DBMS/Cypher versions; check changelog or specify `CYPHER 5` when appropriate |
| TLS error connecting to AuraDB | Wrong URI scheme, hostname, certificate, or network restriction | Use the exact `neo4j+s://` URI from Aura Console; do not disable TLS verification |

Diagnose in order: **OS/JVM → process → logs → ports → URI → credentials → database/edition → Cypher**. This prevents confusing a server installation error with a Java Driver issue or query syntax error.

## 12. Hands-on Exercise: Creating a Reproducible Setup Record

Choose **one** deployment method (Desktop, native, or Docker) and complete this record template:

| Field to record | Illustrative example |
| --- | --- |
| Deployment method | Docker on laptop |
| OS and architecture | Ubuntu 24.04 LTS, x86_64 |
| Edition and Server version | Community, 2026.10.2 |
| **Server** Java | Runtime inside Docker image; verified inside container |
| **Application** Java | Java 17 (if applicable) |
| Available RAM and storage | Record actual measurements from preflight step |
| Source and checksum | Official Docker image tag/digest or downloaded SHA-256 |
| Browser URI | `http://localhost:7474` |
| Driver URI | `bolt://localhost:7687` |
| Database and user | `neo4j`, `neo4j` (example; do not record password) |
| `dbms.components()` result | Record actual observed version and edition |
| Cypher check result | `RETURN 2` and `User → Project` graph sample succeeded |
| Restart check result | Sample data persisted |

**Exercise 1:** A teammate runs Neo4j **2026.10.2** from a TAR archive and only has **JDK 17**. Identify the failing preflight check and propose a fix without modifying the existing data directory.

**Exercise 2:** A Spring Boot application uses **Java 17** and Java Driver 6.x to connect to Neo4j **2026.10.2**. Explain why the server JVM does not have to match the application JVM, and list the three minimum connection details required.

**Exercise 3:** Two users run the same `neo4j:2026.10.2` Docker image tag, yet one can open Browser while the other gets port `7474` already in use. Write three specific diagnostic steps without deleting any data.

**Exercise 4:** You are asked to upgrade from Neo4j 5.26 LTS to the 2026 branch. Before installing, list what must be verified: whether the OS is still supported, JVM, edition/plugins, backups, migration guide, and default Cypher version changes.

### Completion Checklist

- [ ] Chosen and recorded server version, edition, and deployment method.
- [ ] Verified OS, CPU, JVM, RAM, disk, and system requirements for the **exact version**.
- [ ] Verified download source, checksum, or image tag/digest.
- [ ] Logged into the DBMS, verified `dbms.components()`, and executed Cypher.
- [ ] Distinguished HTTP/Browser URI from Bolt/Driver URI.
- [ ] Tested saving and reading back nodes/relationships across reconnect or restart.
- [ ] Recorded the installation checklist without storing passwords in docs/repository.

## 13. Official Documentation for Version Verification

- [Neo4j Deployment Center](https://neo4j.com/deployment-center/) — packages, versions, editions, checksums.
- [Operations Manual – System requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/) — OS, JVM, and hardware resources.
- [Operations Manual – Introduction/versioning](https://neo4j.com/docs/operations-manual/current/introduction/) — CalVer and Cypher 5/Cypher 25.
- [Neo4j Desktop – Installation](https://neo4j.com/docs/desktop/current/installation/) — Desktop installation and supported environments.
- [Neo4j Linux – Debian packages](https://neo4j.com/docs/operations-manual/current/installation/linux/debian/) — APT setup and specific package versions.
- [Neo4j Windows](https://neo4j.com/docs/operations-manual/current/installation/windows/) and [Neo4j macOS](https://neo4j.com/docs/operations-manual/current/installation/osx/) — native startup.
- [Neo4j Docker – Getting started](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — image tags, ports, persistence, and authentication.
- [Neo4j Java Driver – Installation](https://neo4j.com/docs/java-manual/current/install/) — Driver version, application JDK, Neo4j Server compatibility.
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/) — review before upgrading versions or migrating data.

> **Practice reminder:** **Successful installation** means the server starts, returns Cypher results, reports the **exact expected version/edition**, and persists data reliably. This is the foundation before studying property graph modeling, indexes/constraints, tuning, and Java integration.
