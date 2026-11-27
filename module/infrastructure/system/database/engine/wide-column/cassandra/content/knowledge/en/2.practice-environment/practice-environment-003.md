# Installing via OS Packages, Virtual Machines, or Containers

## 1. Objectives and Installation Choices

Apache Cassandra is a **distributed wide-column** database management system. A node can run on a Linux machine installed directly from OS packages, inside a virtual machine (VM), or inside a container. These installation methods expose the same **CQL native protocol** interface, while differing in configuration paths, data locations, process lifecycle, and networking. Understanding these differences helps you set up environments to practice partition keys, query-driven table design, replication, consistency levels, compaction, repair, failure handling, and Java applications.

After this lesson, you will be able to:

1. Choose among **APT/DEB, DNF/RPM, Linux VM, or Docker** based on your goals.
2. Install a Cassandra 5.0 node, confirm its version and `UN` state, and run verification CQL queries.
3. Locate `cassandra.yaml`, SSTable/commitlog data, logs, CQL port, and process management commands for each installation method.
4. Distinguish between **VM** and **container** isolation and preserve data when recreating an environment.
5. Identify errors involving JDK, repositories, firewalls/NAT, advertised addresses, volume permissions, and insufficient resources.
6. Prepare connection endpoints for continuing practice with the Apache Cassandra Java Driver.

> **Lab principle:** choose **one installation method** for your initial smoke test. The branches below are **mutually exclusive alternatives**. If you run multiple Cassandra nodes via different installation methods on the same host, isolate their ports, cluster names, and data directories; do not accidentally let a new node join an unrelated cluster.

## 2. Comparing the Options

| Option | Where Cassandra Runs | Advantages | Cost / Limitations | Best Suited For |
|---|---|---|---|---|
| **DEB/APT** on Debian, Ubuntu | Process and service on Linux host | Package integrates with service management, logs, and system directories | Requires admin privileges; installs directly onto host | Linux VM or dedicated Linux host for operations practice |
| **RPM/DNF** on RHEL/AlmaLinux and compatibles | Process and service on Linux host | Familiar service administration on RPM systems | Package support varies by distro; must verify repository and JDK | Operations lab on RPM systems |
| **Linux VM** | Guest OS with its own kernel, systemd, filesystem, and IP | Snapshots, OS/network fault testing, and multi-node topologies | Uses more RAM/CPU/disk than containers; requires guest network setup | Multi-node operations, node/VM failure labs |
| **Docker container** | Cassandra process in a Linux container / Docker Desktop VM | Fast startup, version pinned in image, easy recreation | Must manage volumes, networks, resources; Desktop VM differences | Learning CQL/Java, demos, CI, reproducible labs |
| **Binary tarball** (supplemental) | User-space process on Linux | No system package install required; easy to test an exact version | Self-managed process, logs, and config; no default OS service | Linux hosts without package install rights or quick testing |

**A VM is not a standalone Cassandra installation method.** First you provision a Linux VM, then you install **DEB/RPM** or a **tarball** *inside the guest*. Containers use an image that already packages Cassandra and its runtime; `docker run` launches the process instead of `systemctl`.

```text
Java application or cqlsh
        │ TCP 9042: native transport/CQL
        ▼
┌─────────────────────────────────────────────────────┐
│ Cassandra server + CQL + nodetool                   │
├──────────────────┬──────────────────┬───────────────┤
│ Linux host       │ Linux guest VM   │ Container     │
│ apt/dnf +        │ apt/dnf +        │ image +       │
│ systemd          │ systemd          │ Docker Engine │
│ /var/lib/...     │ guest disk       │ named volume  │
└──────────────────┴──────────────────┴───────────────┘
        Data must persist across restarts
```

## 3. General Preparation and Version Pinning

### 3.1. Reference Version Stack

As of **2026-11-21**, Apache lists Cassandra **5.0.9** as the latest GA release of the 5.0 branch. This lesson uses that version as the lab baseline. Before installing, check the [official Cassandra download page](https://cassandra.apache.org/_/download.html) to confirm the exact release you are using.

| Component | Chosen for This Lesson | Notes |
|---|---|---|
| Cassandra | **5.0.9**, `5.0` branch | Containers/tarballs can pin an exact patch; the `50x` repository may serve a newer patch |
| JDK running Cassandra on Linux/VM | **OpenJDK 17**, or Java 11 per Cassandra 5.0 docs | Check `java -version` on the **exact host/guest** running Cassandra |
| Python for `cqlsh` outside container | Python 3 compatible with the installed Cassandra release | Per Cassandra 5.0 installation docs, Python 3.8–3.13 is supported for `cqlsh` |
| Docker | Docker Engine or Docker Desktop using Linux containers; Compose v2 if using Compose files | Docker Desktop on Windows/macOS runs containers inside a Linux VM |
| Java client | JDK 17 and Apache Cassandra Java Driver 4.x | Application JDK can differ from server JVM; test driver separately |

With APT/DNF, the `50x` repo branch **does not guarantee pinning 5.0.9**. After installing, record the **actual package version**. If bit-for-bit reproducibility is required, use an image with a recorded digest, a checksum/signature-verified tarball, or a version-pinned package in a private repository. Never use `latest` as a baseline.

### 3.2. Resources, Ports, and Common Requirements

- A single-node lab should start on a **host with roughly 8 GiB RAM or more**, sufficient CPU, and SSD space; the VM/container needs separate memory headroom for OS, off-heap, page cache, logs, and compaction. This is a learning guideline, **not production sizing**.
- Check networking and firewalls. **9042/TCP** serves CQL/Java drivers; **7000/TCP** typically serves internode communication, **7001/TCP** may be used for internode TLS depending on configuration, and **7199/TCP** is normally JMX for `nodetool`. Do not expose 7199 to external networks casually.
- Synchronize clocks on hosts and VMs using NTP/chrony or an equivalent service; Cassandra's mutation timestamps affect **last-write-wins**.
- The server requires a Java version supported by the **Cassandra branch**. `cqlsh` requires a compatible Python version, though **the CQL server itself does not run on Python**.
- Many lab environments default to connections **without authentication/TLS**. Only allow access from loopback or an isolated lab network; before using shared networks or production, configure authentication, encryption, firewalls, backups, monitoring, and topology.

On Linux/guest, run initial checks:

```bash
uname -a
java -version
python3 --version
free -h
df -h .
date -u
```

On Windows/macOS running Docker Desktop, check **RAM/disk allocated to the Linux VM** alongside physical hardware. Having JDK 17 installed on Windows **does not indicate** which JVM version is inside the Cassandra image.

## 4. Option A: Installing DEB/APT Packages on Debian or Ubuntu

Run **inside the Linux shell** of your Debian/Ubuntu machine or VM with a `sudo`-capable account. This section demonstrates the Apache repository for Cassandra 5.0; if older Cassandra repos exist, inspect them to avoid mixing branches.

### 4.1. Installing Dependencies and Registering the Apache Repository

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jre-headless python3 curl ca-certificates

java -version
python3 --version

sudo install -d -m 0755 /etc/apt/keyrings
sudo curl -fsSL https://downloads.apache.org/cassandra/KEYS \
  -o /etc/apt/keyrings/apache-cassandra.asc

echo "deb [signed-by=/etc/apt/keyrings/apache-cassandra.asc] https://debian.cassandra.apache.org 50x main" \
  | sudo tee /etc/apt/sources.list.d/cassandra.sources.list

sudo apt-get update
apt-cache policy cassandra
```

Notes on this step:

- `50x` denotes the **Cassandra 5.0 branch**, not a specific patch number.
- `/etc/apt/keyrings/apache-cassandra.asc` holds the signing keys used to verify packages from the Apache repository; do not disable signature verification to bypass key errors.
- `apt-cache policy cassandra` shows the **Candidate** version APT plans to install and its source. If you must pin exactly 5.0.9, list available versions and select the exact version string in the package manager; do not assume the string is `5.0.9` without inspecting metadata.
- The official repository currently uses `debian.cassandra.apache.org`, replacing older URLs found in legacy guides.

### 4.2. Installing, Starting, and Verifying

```bash
sudo apt-get install -y cassandra
dpkg-query -W cassandra

# Depending on the distribution, the service may start automatically upon installation:
sudo systemctl status cassandra --no-pager
sudo systemctl start cassandra

nodetool status
nodetool version
cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

If `systemctl status` shows the service is not running, inspect logs before retrying a start. Cassandra needs time to initialize system keyspaces and join the ring; `systemctl start` exiting cleanly does not guarantee CQL is ready yet. When healthy, `nodetool status` displays **`UN`** (*Up/Normal*) for the node.

Key paths to remember for the DEB package:

| Component | Typical Path |
|---|---|
| Configuration | `/etc/cassandra/cassandra.yaml` |
| Data / commitlog | Directories under `/var/lib/cassandra` |
| Logs | `/var/log/cassandra/system.log`, plus sibling logs in that directory |
| Startup options | `/etc/default/cassandra` and package-provided config files |
| Service | `systemctl start/stop/status cassandra` |

If you want to change `cluster_name`, topology, listen addresses, or data directories, stop the node and edit configuration **before writing business data**. Changing `cluster_name` on a node already holding data requires metadata handling and a defined procedure; in a fresh lab, it is simplest to configure it properly before first launch.

### 4.3. Logs and Package Lifecycle

```bash
sudo journalctl -u cassandra -n 100 --no-pager
sudo tail -n 100 /var/log/cassandra/system.log
sudo systemctl stop cassandra
sudo systemctl start cassandra
```

**Never delete** `/var/lib/cassandra` just to "reinstall cleanly" if you have data to keep. Uninstalling a package and deleting the data directory are separate actions. In real deployments, use backups/snapshots and a proper upgrade workflow before changing packages; never allow unattended auto-upgrades to change versions between reproducible lab sessions.

## 5. Option B: Installing RPM Packages with DNF on RHEL-Family Linux

This example applies to RPM-based distributions with `dnf` and `systemd` (such as RHEL/AlmaLinux). The OS version must match repository and JDK support; since Cassandra RPM packaging can vary across distributions, inspect package metadata before installing.

### 5.1. Defining the Repository

```bash
sudo dnf install -y java-17-openjdk-headless python3 curl ca-certificates
java -version

sudo tee /etc/yum.repos.d/cassandra.repo >/dev/null <<'EOF'
[cassandra]
name=Apache Cassandra
baseurl=https://redhat.cassandra.apache.org/50x/
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://downloads.apache.org/cassandra/KEYS
EOF

sudo dnf makecache
dnf --showduplicates list cassandra
```

If your environment uses `yum`, run the equivalent OS-appropriate commands. The URL `redhat.cassandra.apache.org/50x/` serves the 5.0 branch repository. Older distributions may require different repo settings; **do not copy CentOS 7 options** onto modern systems unless specifically required for compatibility.

### 5.2. Installing the Package and Managing the Service

```bash
sudo dnf install -y cassandra
rpm -q cassandra

sudo systemctl daemon-reload
sudo systemctl enable --now cassandra
sudo systemctl status cassandra --no-pager

nodetool status
nodetool version
cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

On RPM systems, configuration, logs, and data usually follow conventions similar to DEB packages, but verify the **actual paths inside the package** and `cassandra.yaml` rather than assuming every RPM build is identical:

```bash
rpm -ql cassandra
sudo journalctl -u cassandra -n 100 --no-pager
```

Apache's download page notes that RPM packages have not been tested on all platforms. When troubleshooting service errors, collect `rpm -q cassandra`, `java -version`, the active repo, logs, and OS details before reporting issues or switching installation methods.

## 6. Option C: Creating a Linux VM and Installing Cassandra in the Guest

A VM is ideal when simulating a standalone server's operations: OS tuning, system services, firewalls, hostnames, networking, snapshots, and node failures. VMs also let you practice multi-node clusters on a virtual network, though **three VMs on one physical host are not three independent failure domains**.

### 6.1. Provisioning a Lab VM

You can use VirtualBox, VMware, Hyper-V, KVM, or any available hypervisor. Example starting specifications:

| VM Resource | Reference Lab Value |
|---|---|
| Guest OS | A supported Ubuntu Server/Debian or AlmaLinux/RHEL release |
| vCPU | 2 vCPUs |
| RAM | Around 4 GiB for the guest while leaving RAM for the host |
| Disk | SSD-backed virtual disk from 20 GiB for small datasets, larger when practicing compaction/repair |
| Network | NAT for internet access, or bridged/host-only as needed; ensure SSH and DNS work |
| Time | Enable time sync inside the guest; verify UTC/NTP |

This is a **small practice** specification, not a production operating target.

After installing the guest OS:

```bash
hostnamectl
ip addr
ip route
df -h
free -h
timedatectl status
```

Next, follow **Option A** if the guest is Debian/Ubuntu, or **Option B** if the guest is RPM-based. Run `apt`/`dnf` commands **inside the guest terminal**, not on a Windows/macOS host.

### 6.2. Distinguishing VM Network Modes

```text
Laptop/host                       Linux VM
┌─────────────────┐               ┌───────────────────┐
│ IDE + Java      │               │ Cassandra :9042   │
│ cqlsh           │── SSH/VM NIC ─│ SSH :22           │
└─────────────────┘               └───────────────────┘
         NAT: guest reaches internet, host needs forwarding/tunnel
         Bridged: guest gets its own LAN IP, firewall must allow traffic
         Host-only: host and guest communicate on a private virtual network
```

When Cassandra on the guest listens only on `127.0.0.1:9042`, `cqlsh` **inside the guest** works while the host cannot connect directly. You can keep CQL bound locally and open an **SSH tunnel** from the host for `cqlsh` testing:

```bash
# Run on host terminal; replace VM_IP and user with actual SSH details.
ssh -N -L 9242:127.0.0.1:9042 student@VM_IP
```

This SSH command requires the host to **actually reach SSH on the guest**; if the hypervisor uses isolated NAT, configure SSH port forwarding or attach a suitable host-only/bridged NIC first. In a second host terminal, assuming `cqlsh` is installed on the host:

```bash
cqlsh 127.0.0.1 9242
```

That tunnel only handles TCP forwarding for **a single node**. The Java Driver discovers topology and connects to node addresses **advertised** in metadata; to run a Java app outside the VM reliably, endpoints discovered by the driver must be routable from the application host. For multi-node labs, the network must allow the application to reach **all required nodes**, not just one arbitrarily forwarded port.

If you explicitly configure remote CQL over a trusted lab network, distinguish:

- `listen_address`: address the node uses for **internode/gossip communication**; must not be `0.0.0.0`.
- `rpc_address`: bind address for **native CQL**; can be a guest interface or `0.0.0.0`.
- `broadcast_rpc_address`: address Cassandra advertises to **drivers**; must be reachable from clients and must not be `0.0.0.0`.
- `native_transport_port`: default `9042`; must be permitted by firewalls and access policies.

For instance, on a private network, `listen_address: 192.168.56.10`, `rpc_address: 0.0.0.0`, and `broadcast_rpc_address: 192.168.56.10` are valid only if that is **genuinely the guest's IP**, the host/app can route to it, and firewall rules are configured. Do not copy example IPs verbatim. In multi-node environments holding data, changing listen/broadcast addresses requires a topology procedure rather than ad-hoc edits and cluster-wide restarts.

### 6.3. VM Snapshots and Their Limitations

VM snapshots are very convenient for reverting to a **clean OS state** before an exercise. However, taking a VM snapshot while Cassandra is actively writing does not guarantee database consistency in real scenarios; storage/hypervisor snapshots do not replace a backup/restore plan or `nodetool snapshot`. In an empty lab, shutting down Cassandra/the VM before taking a snapshot simplifies recovery.

## 7. Option D: Installing via Docker Container

This is the fastest choice for learning CQL and Java connectivity on Windows/macOS/Linux. Docker Engine must be able to run Linux containers; on Windows/macOS, Docker Desktop uses a Linux VM. Containers **do not** automatically persist data if it lives only in the writable container layer, which is discarded when the container is removed.

### 7.1. Starting a Node with the Docker CLI

Run on a host with the Docker CLI:

```bash
docker version
docker pull cassandra:5.0.9
docker volume create cassandra_install_data

docker run -d --name cassandra-install-lab \
  -p 127.0.0.1:9042:9042 \
  -e CASSANDRA_CLUSTER_NAME=install-lab \
  -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch \
  -e CASSANDRA_DC=datacenter1 \
  -e CASSANDRA_RACK=rack1 \
  -v cassandra_install_data:/var/lib/cassandra \
  cassandra:5.0.9
```

**Shell note:** multi-line examples use `\` for **Bash/Linux/macOS**. If running in **Windows PowerShell**, place the entire `docker run ...` command on a single line or use PowerShell's line continuation syntax; do not paste `\` directly and expect PowerShell to parse it like Bash.

| Component | Meaning |
|---|---|
| `cassandra:5.0.9` | Pins the image version for this lesson |
| `127.0.0.1:9042:9042` | Maps host CQL port 9042 to container CQL port 9042 on localhost only |
| `CASSANDRA_CLUSTER_NAME` | Lab cluster name, distinct from container name |
| `CASSANDRA_ENDPOINT_SNITCH` + `CASSANDRA_DC/RACK` | Topology settings for a single-datacenter environment |
| `cassandra_install_data:/var/lib/cassandra` | Named volume persisting data across container removals/recreations |

If another Cassandra instance on the host already uses port 9042, stop the old service/container or pick another host port, e.g., `-p 127.0.0.1:9242:9042`. When changing the host port, `cqlsh` run **on the host** connects to `9242`, while `cqlsh` **inside the container** still uses `9042`. With the Java Driver, also verify the endpoint Cassandra advertises via metadata when crossing NAT.

### 7.2. Verifying Actual Status

```bash
docker ps --filter name=cassandra-install-lab
docker logs cassandra-install-lab
docker exec cassandra-install-lab nodetool status
docker exec cassandra-install-lab nodetool version
docker exec cassandra-install-lab java -version
docker exec cassandra-install-lab cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

Wait until `nodetool status` shows the node as `UN`. A container showing `Up` **does not mean** Cassandra is accepting CQL yet. If `cqlsh` reports connection refused during startup, check `docker logs` and retry once the node is ready.

Disk and volume status:

```bash
docker stats --no-stream cassandra-install-lab
docker exec cassandra-install-lab sh -c "df -h /var/lib/cassandra"
docker volume inspect cassandra_install_data
```

On Docker Desktop, the volume may reside inside the Linux VM rather than appearing as a regular host folder. Using a volume keeps Cassandra data persistent; it is **not** an independent backup.

### 7.3. Docker Compose for Configuration as Code

If you need to recreate the lab repeatedly, save the following into a **`compose.yaml` file in your own practice directory** (the snippet below is an illustration for the learner, not a file shipped with this lesson):

```yaml
services:
  cassandra:
    image: cassandra:5.0.9
    container_name: cassandra-compose-lab
    environment:
      CASSANDRA_CLUSTER_NAME: compose-lab
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_DC: datacenter1
      CASSANDRA_RACK: rack1
    ports:
      - "127.0.0.1:9042:9042"
    volumes:
      - cassandra_compose_data:/var/lib/cassandra

volumes:
  cassandra_compose_data:
```

In the directory containing `compose.yaml`, run:

```bash
docker compose up -d
docker compose ps
docker compose logs cassandra
docker compose exec cassandra nodetool status
docker compose exec cassandra cqlsh -e "SELECT release_version FROM system.local;"
docker compose down
```

`docker compose down` removes containers/networks created by Compose while **preserving named volumes** by default. `docker compose down -v` **also deletes volumes** and all lab data inside them. Do not pass `-v` when keeping data for the next session.

The Docker CLI steps in section 7.1 and Compose in section 7.3 are **two alternative ways** to build the lab. Use one at a time, since both request host port 9042 and will conflict if run together. When switching, verify container and volume names; Docker Compose prepends a project prefix to volume names unless explicitly overridden.

### 7.4. Docker Networking and Connecting from a Java Application

```text
App running on host                 Cassandra container
127.0.0.1:9042  ─────────────────►  9042 (CQL)

App running in Docker network       Cassandra container
Service/container DNS :9042 ─────►  9042 (CQL)
```

- A Java application running on the host uses the endpoint **published on the host** (e.g., `127.0.0.1:9042`).
- A Java application running in a separate container on the **same Docker network** typically uses service name `cassandra` and port `9042`. `127.0.0.1` inside the Java container refers to the **Java container itself**, not Cassandra.
- Driver 4.x discovers nodes via metadata. Addresses **advertised** by Cassandra must be reachable within the network scope of the application, especially under multi-node, NAT, or multi-host setups. Published ports may let the client reach the initial contact point, yet **do not guarantee** every routed node connection succeeds.
- For production or multi-node clusters, design seeds, listen/broadcast RPC, DNS, firewalls, and replication around real topology. Never use a single-node container prototype to evaluate distributed fault tolerance.

## 8. Option E (Supplemental): Binary Tarball Without a Package Manager

A tarball is convenient on Linux/guests when you want to run **an exact Cassandra version** under a user account without registering repositories. It does not create an OS service or manage upgrades/backups automatically.

Example using Linux Bash:

```bash
java -version
python3 --version

curl -fLO https://dlcdn.apache.org/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz
curl -fLO https://dlcdn.apache.org/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz.sha512
curl -fLO https://dlcdn.apache.org/cassandra/5.0.9/apache-cassandra-5.0.9-bin.tar.gz.asc
curl -fLO https://downloads.apache.org/cassandra/KEYS

# Compare output with the string in the .sha512 file:
sha512sum apache-cassandra-5.0.9-bin.tar.gz
cat apache-cassandra-5.0.9-bin.tar.gz.sha512

# Verify signature using public keys published on the Apache website:
gpg --import KEYS
gpg --verify apache-cassandra-5.0.9-bin.tar.gz.asc apache-cassandra-5.0.9-bin.tar.gz

tar -xzf apache-cassandra-5.0.9-bin.tar.gz
cd apache-cassandra-5.0.9
bin/cassandra -f
```

The `-f` flag runs Cassandra in the **foreground** for immediate log visibility; in a second terminal inside the tarball directory:

```bash
bin/nodetool status
bin/nodetool version
bin/cqlsh -e "SELECT release_version, cluster_name, data_center FROM system.local;"
```

If 5.0.9 is no longer on active mirrors, fetch the exact release from the [Apache Archive](https://archive.apache.org/dist/cassandra/5.0.9/) and still verify checksums/signatures. Never ignore checksum mismatches. With a tarball:

- `conf/cassandra.yaml`: configuration file.
- `bin/cassandra`, `bin/nodetool`, `bin/cqlsh`: runtime and admin binaries.
- `data/`, `logs/`: data and log directories in the tarball layout.
- Because no service manager is included, if the process must survive logout/reboot you need to design a proper OS service rather than relying on `nohup` as a production solution.

Never install both a tarball and a package pointing to the **same data directory**. Two Cassandra processes accessing the same SSTables/commitlog can corrupt data.

## 9. Common Post-Install Smoke Test

The prerequisite is a node reporting `UN` and accepting `cqlsh`, regardless of installation method.

### 9.1. Confirming Cluster and Datacenter

In `cqlsh`, run:

```sql
SELECT release_version, cluster_name, data_center, host_id
FROM system.local;
```

Record the actual `release_version` and `data_center`; do not assume the datacenter is always named `datacenter1`. You can also check `nodetool describecluster` to verify cluster name, snitch, and schema versions.

### 9.2. Creating a Keyspace and Partition-Key Table

The example below assumes `data_center` returned **`datacenter1`**. If it differs, substitute the actual datacenter name in the replication map:

```sql
CREATE KEYSPACE IF NOT EXISTS installation_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 1
};

CREATE TABLE IF NOT EXISTS installation_lab.events_by_device (
  device_id text,
  event_id timeuuid,
  event_type text,
  PRIMARY KEY ((device_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);

INSERT INTO installation_lab.events_by_device
  (device_id, event_id, event_type)
VALUES ('device-001', now(), 'installed');

SELECT device_id, event_id, event_type
FROM installation_lab.events_by_device
WHERE device_id = 'device-001'
LIMIT 10;
```

Here `device_id` is the **partition key**, determining which partition stores the device's events; `event_id` is the **clustering key**, ordering rows within that partition. Filtering by partition key aligns with Cassandra's data model.

`NetworkTopologyStrategy` with RF=1 here is strictly for a **single-node lab**. It provides **no replica redundancy** and cannot demonstrate read/write consistency when a node fails. To meaningfully practice `LOCAL_QUORUM`, failure handling, and repair, you need a multi-node cluster with an appropriate replication factor.

### 9.3. Testing Java Application Connectivity

With Apache Cassandra Java Driver 4.x, basic setup looks like:

```java
import java.net.InetSocketAddress;
import com.datastax.oss.driver.api.core.CqlSession;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("datacenter1")
        .build()) {
    System.out.println(
        session.execute("SELECT release_version FROM system.local")
               .one().getString("release_version"));
}
```

This snippet is a **Java method body**, not a complete `.java` file. Add the `org.apache.cassandra:java-driver-core` dependency compatible with JDK 17 and wrap it in a class/method to execute. Adjust contact point, port, and local datacenter according to where the app runs:

| Application Location | Reference Endpoint | Condition |
|---|---|---|
| Same Linux host as package/tarball | `127.0.0.1:9042` | Cassandra binds native transport on loopback |
| Inside the same VM as Cassandra | `127.0.0.1:9042` | CQL server inside the guest is active |
| Host connecting to Docker with published 9042 | `127.0.0.1:9042` | Port mapping is valid and node advertises reachable address |
| App on the same Docker Compose network | `cassandra:9042` | Service DNS resolves and metadata endpoint matches |
| Host connecting to VM via NAT or bridged | Actual IP/port or SSH tunnel | Firewall, listener, and broadcast address match driver access |

**A TCP connection to 9042 alone is not enough:** `nodetool status=UN`, `cqlsh` success, Java driver reading `system.local`, and querying a real keyspace are distinct verification layers.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| APT cannot find package or `NO_PUBKEY` error | Wrong `50x` repo URL, missing key, or outdated tutorial instructions | Check `/etc/apt/sources.list.d/cassandra.sources.list`, `apt-cache policy`, official KEYS; never disable GPG |
| DNF repo or GPG error | Stale/wrong branch `baseurl`, incompatible distro release, network blocked from repo | Inspect `dnf repolist`, `dnf --showduplicates list cassandra`, `cassandra.repo`, and logs |
| Cassandra fails to start due to Java | JVM unsupported by 5.0 branch, wrong `JAVA_HOME` | Run `java -version` in the **exact target environment**, check service logs and Java config |
| `cqlsh` Python module/version error | Missing or incompatible Python for `cqlsh` | Use a Python version supported by that Cassandra release; verify how `cqlsh` was packaged |
| `systemctl status` shows running, but `cqlsh` is refused | Cassandra still initializing or listener not open yet | Check `system.log`, run `nodetool status`, inspect `ss -lntp` on Linux |
| Docker container starts then exits | Insufficient RAM, OOM, volume permissions, JVM/config error | Check `docker logs`, `docker inspect`, host/VM RAM, volume permissions |
| `Bind for 0.0.0.0:9042 failed` | Host port 9042 already used by another process/container | Check `docker ps`, `ss -lntp` (Linux), change host port mapping or stop old lab |
| VM guest runs CQL, host cannot reach port | VM on NAT, firewall blocking, Cassandra bound only to loopback | Check network mode, guest IP, `rpc_address`, and port; use SSH tunnel or proper network config |
| Java driver `NoNodeAvailableException` after handshake | Contact point reachable via NAT, but node broadcast IP is unroutable | Check `broadcast_rpc_address`, topology endpoints, DNS, and firewall from the **app host** |
| Driver reports wrong local datacenter | String passed to `withLocalDatacenter` mismatches `system.local.data_center` | Query actual DC and match exact casing; never guess |
| CQL works but data vanishes after container removal | No volume attached or `docker compose down -v` used | Use a named volume and verified backups; never treat container writable layers as durable storage |
| Disk full, compaction/repair fails | Insufficient space for new SSTables, commitlog, or snapshots | Check `df -h` on data dir/volume and expand disk; never delete SSTables manually |
| Attaching old data dir to different server version fails | Invalid upgrade/downgrade path, incompatible data/system tables | Follow the official upgrade guide and backups; never downgrade data arbitrarily |

Diagnostic evidence varies by installation method:

```text
APT/RPM    → systemctl status cassandra; journalctl -u cassandra;
             /var/log/cassandra/system.log; nodetool status
Tarball    → logs/system.log; bin/nodetool status; bin/cqlsh
VM         → guest logs + ip/route/firewall on guest + host/guest network
Docker     → docker logs; docker stats; docker exec ... nodetool status
Compose    → docker compose logs cassandra; docker compose ps
```

Always collect **Cassandra version, Java version, OS, node status, logs, and app→node network path** before altering configuration. A port error has nothing to do with partition keys; conversely, a query failing due to a missing partition key can happen even when installation is completely correct.

## 11. Preserving Data, Cleaning Up, and Switching Installation Methods

| Method | Where Data Typically Lives | Stop Action | What to Avoid |
|---|---|---|---|
| DEB/RPM | `/var/lib/cassandra` or path in `cassandra.yaml` | `sudo systemctl stop cassandra` | Never delete data just to fix a package error |
| VM | Inside the guest virtual disk | Stop Cassandra then shut down guest | Never treat a live-write VM snapshot as a tested CQL backup |
| Docker CLI | Named volume `cassandra_install_data` | `docker stop cassandra-install-lab` | Never run `docker volume rm` if you need the data |
| Docker Compose | Compose project's named volume | `docker compose down` | Never run `docker compose down -v` if preserving data |
| Tarball | `data/` directory or custom configured path | Stop process via its control mechanism | Never run two processes against the same data directory |

With the Docker CLI container from section 7.1, you can stop and recreate it using the same named volume:

```bash
docker stop cassandra-install-lab
docker rm cassandra-install-lab
docker volume ls --filter name=cassandra_install_data
```

Removing a **container** does not remove its **volume**. When recreating, keep the exact image version, cluster identity, and required configuration. If migrating from package/VM to container, **do not copy the raw data directory** and expect a new node with a different topology to work cleanly. Data migration must follow a valid plan such as verified backup/restore, `sstableloader` where appropriate, or streaming/migration tooling compatible with the version and schema.

## 12. Self-Check Exercises and Completion Criteria

1. A learner runs `cqlsh` successfully inside Docker, while the Java app on the host fails. List the check sequence across port mapping, listener, local datacenter, and advertised node address.
2. Given a requirement to keep strictly Cassandra 5.0.9, why is `apt install cassandra` from the `50x` repo insufficient to guarantee the exact version? How can you pin the lab version?
3. On Windows, `java -version` prints Java 17, while Cassandra runs in a container. Which command confirms the JVM **actually inside the Cassandra container**?
4. You use Docker Compose and run `down -v`. On the next container creation, does the lab keyspace data remain? How does this differ from `down`?
5. In a NAT VM, `cqlsh` inside the guest succeeds, but the host cannot connect to `VM_IP:9042`. Contrast NAT/SSH tunneling with configuring Cassandra's bind/broadcast settings.
6. Why must you check `nodetool status` in addition to `systemctl status` or `docker ps`? Does `UN` alone prove replication and repair are healthy?
7. Someone runs three Cassandra VMs on the same laptop and unplugs the laptop power. Has that tested the fault tolerance of three independent physical hosts? Explain the test's limitations.
8. A table uses `PRIMARY KEY ((device_id), event_id)`. Why must queries filter by `device_id`, and how does that relate to data distribution across nodes?

**Completion criteria:** learners choose **one** installation method, record the exact package/image/tarball version, read `system.local`, observe `UN`, run table-creation/write/read queries, identify data and log locations, and accurately describe the endpoints for `cqlsh` and Java applications. This provides the foundation before moving to multi-node labs on replication, consistency levels, compaction, repair, and incident handling.

## 13. Official References

- [Apache Cassandra — Download](https://cassandra.apache.org/_/download.html): releases, `50x` DEB/RPM repositories, signing keys, and package instructions.
- [Apache Cassandra 5.0 — Installing Cassandra](https://cassandra.apache.org/doc/latest/cassandra/installing/installing.html): Java/Python requirements, Docker, tarball, and package installs.
- [Apache Cassandra — Configuration reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `listen_address`, `rpc_address`, `broadcast_rpc_address`, `native_transport_port`.
- [Apache Cassandra — Quickstart](https://cassandra.apache.org/doc/stable/cassandra/getting-started/cassandra-quickstart.html): nodes, CQL, and quickstart guide.
- [Docker Hub — Official Cassandra image](https://hub.docker.com/_/cassandra): environment variables and container usage.
- [Docker Docs — Compose file reference](https://docs.docker.com/reference/compose-file/): `compose.yaml` syntax and volumes.
- [Docker Docs — Storage volumes](https://docs.docker.com/engine/storage/volumes/): lifecycle and persistence guarantees of named volumes.
- [Apache Cassandra Java Driver](https://github.com/apache/cassandra-java-driver): session configuration and local datacenter for Java clients.
