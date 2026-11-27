# Initializing a ZooKeeper Cluster and Configuring connect-string

## 1. What does ZooKeeper do in Service Discovery?

ZooKeeper is a distributed coordination service providing a data tree (znodes), synchronization mechanisms, and sessions. Spring Cloud Zookeeper Discovery uses ZooKeeper to store service registration data and look up instances by service name.

In production environments, applications typically connect to an **ensemble** consisting of multiple ZooKeeper servers. The servers coordinate leader election, replicate state, and keep serving when a node fails, as long as the remaining nodes maintain a quorum.

This lesson walks through setting up a three-node ensemble, configuring ports, identifying each server, checking quorum, and declaring `connect-string` for Spring Cloud applications.

## 2. Components and network ports

| Example port | Role | Who needs access? |
|---:|---|---|
| 2181 | Client port: accepts connections from applications and CLI | Applications and authorized admin hosts |
| 2888 | Peer communication between ensemble members | ZooKeeper servers |
| 3888 | Leader election between members | ZooKeeper servers |

These port numbers are common defaults and can be changed in zoo.cfg. Clients only connect to the client port; do not configure Spring Cloud to connect to the peer port or election port.

~~~mermaid
flowchart TB
    APP[Spring Cloud applications] -->|Client port 2181| Z1[ZooKeeper 1]
    APP -->|Client port 2181| Z2[ZooKeeper 2]
    APP -->|Client port 2181| Z3[ZooKeeper 3]
    Z1 <-->|Peer 2888 / Election 3888| Z2
    Z2 <-->|Peer 2888 / Election 3888| Z3
    Z3 <-->|Peer 2888 / Election 3888| Z1
~~~

Servers need stable hostnames and reachability over both peer and election ports. Applications only need network routing to the client ports of the servers listed in the connect string.

## 3. Choosing the node count and understanding quorum

ZooKeeper uses a quorum to commit changes. An ensemble needs a majority of members active to continue processing write operations and maintaining consistent state.

| Server count | Required quorum | Servers that can be lost while retaining quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 4 | 3 | 1 |

Production deployments typically choose 3 or 5 servers rather than 2 or 4. A 4-node ensemble still requires 3 nodes, offering the same fault tolerance as a 3-node ensemble at higher operational cost.

With three nodes, place them on separate hosts or failure domains. If all three servers run on the same physical host or within the same failure-prone network zone, running three processes provides no real fault tolerance.

When quorum is lost, clients may retain sessions or local data briefly, but the registry must not be treated as ready to accept new changes.

## 4. Preparing three ZooKeeper servers

Example using three machines or containers with stable hostnames:

| Server ID | Hostname | Client port | Peer port | Election port |
|---:|---|---:|---:|---:|
| 1 | zk1.internal | 2181 | 2888 | 3888 |
| 2 | zk2.internal | 2181 | 2888 | 3888 |
| 3 | zk3.internal | 2181 | 2888 | 3888 |

Before starting:

- Hostnames must resolve from every ZooKeeper server.
- Each server needs a persistent data directory with appropriate read/write permissions.
- Each server's dataDir must be separate; do not share the same data directory.
- Each server needs a myid file containing the exact ID declared in zoo.cfg.
- Firewalls must allow the peer port and election port between ZooKeeper servers.
- Open the client port only to authorized applications and administration hosts.

Do not use localhost in the server list of a distributed ensemble. Each node must identify its own hostname accurately and be able to connect to its peers.

## 5. Configuring zoo.cfg

ZooKeeper uses a configuration file commonly named zoo.cfg. Ensemble members must declare the same server list and the same quorum parameters.

Example configuration used for all three nodes:

~~~properties
tickTime=2000
initLimit=10
syncLimit=5
dataDir=/var/lib/zookeeper
clientPort=2181

server.1=zk1.internal:2888:3888
server.2=zk2.internal:2888:3888
server.3=zk3.internal:2888:3888
~~~

| Property | Meaning |
|---|---|
| tickTime | ZooKeeper's basic time unit, in milliseconds |
| initLimit | Maximum ticks allowed for a follower to initialize and sync with the leader |
| syncLimit | Maximum ticks a follower can lag behind the leader during synchronization |
| dataDir | Directory storing snapshots and transaction logs according to the version's storage config |
| clientPort | Port accepting client connections |
| server.X | Declares an ensemble member with server ID, peer port, and election port |

With tickTime=2000, one tick equals 2 seconds. initLimit=10 and syncLimit=5 are measured in ticks, not directly in seconds. The values in the example are common starting points; tune them according to network latency, disk speed, and real-world load.

### 5.1. Identifying each server with myid

Inside dataDir, ZooKeeper requires a myid file containing the node's ID. With the configuration above:

On zk1.internal:

~~~bash
mkdir -p /var/lib/zookeeper
echo 1 > /var/lib/zookeeper/myid
~~~

On zk2.internal:

~~~bash
mkdir -p /var/lib/zookeeper
echo 2 > /var/lib/zookeeper/myid
~~~

On zk3.internal:

~~~bash
mkdir -p /var/lib/zookeeper
echo 3 > /var/lib/zookeeper/myid
~~~

Each node has a single myid and that ID must match the suffix in server.X. Do not copy the myid file from one node to another. If two servers share the same ID, startup or member election can fail.

### 5.2. Per-node configuration differences

The list of server.1, server.2, server.3 must match across all three servers. Machine-specific settings include:

- dataDir points to that node's local data directory.
- myid contains the node's distinct ID.
- clientPort can be the same when each server runs on its own machine/container; if multiple processes run on the same host, they must use different ports.
- If binding the client port to a specific interface, the bind address must match the deployment network.

Do not share a single dataDir across multiple servers and do not place myid in a shared directory.

## 6. Starting and verifying the ensemble

Start ZooKeeper using the script bundled with the distribution. Script names and paths may vary depending on the installation method:

~~~bash
bin/zkServer.sh start
~~~

Check the status on each node:

~~~bash
bin/zkServer.sh status
~~~

In a healthy ensemble, one node is elected **leader** and the remaining nodes become **followers**. Depending on the version and configuration mode, the status command may display additional details about the node or running mode.

Connect using the CLI to each server:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

Inside the CLI, you can inspect the root znode:

~~~text
ls /
~~~

If the CLI connects successfully, it proves the client port accepts connections and a session can be created. To verify the ensemble, also check leader/follower status across nodes and quorum logs; reaching one client port alone does not prove the entire ensemble has quorum.

### 6.1. Checking Four Letter Words commands

Some ZooKeeper versions support four-letter administration commands such as ruok, srvr, and mntr. On modern versions, these commands must be explicitly enabled via configuration, for example:

~~~properties
4lw.commands.whitelist=ruok,srvr,mntr
~~~

After configuring and restarting per operational procedures, you can check:

~~~bash
echo ruok | nc zk1.internal 2181
echo srvr | nc zk1.internal 2181
~~~

ruok returns imok to indicate the process is responding to commands. It does not by itself prove the node has quorum or can commit writes. Use srvr, mntr, zkServer.sh status, and logs to verify node roles and sync status.

Enable only the required administration commands and restrict access to the client port. Never expose diagnostic commands to public networks.

## 7. Understanding connect-string

A connect string is the list of ZooKeeper client endpoints an application can try connecting to. Basic syntax:

~~~text
zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
~~~

Endpoints are separated by commas. The client uses this list to establish a session and can try another server if the current connection fails or a node stops serving. The list should include multiple ensemble members so the application has alternatives when one node goes down.

A connect string is not a list of peer ports. Applications always use the **client port** (2181 in the example), whereas peer and election ports are strictly for server-to-server communication.

### 7.1. Connect string with a chroot path

ZooKeeper allows clients to append a chroot path to the end of the connect string:

~~~text
zk1.internal:2181,zk2.internal:2181,zk3.internal:2181/spring-cloud
~~~

When using chroot /spring-cloud, the client views the data tree rooted at that path as if it were its own root. Other applications can use different chroots to separate logical namespaces on the same ensemble.

The chroot path must be created before clients connect. For example, connect via CLI without a chroot and create the path:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

~~~text
create /spring-cloud "service-discovery-root"
~~~

Only then should applications use the connect string with the /spring-cloud suffix. If the path does not yet exist, clients may encounter NoNode errors when using that namespace.

Chroot only isolates the namespace observed by a client; it does not create a separate ensemble, does not replace ACLs, and is not an independent security boundary.

## 8. Configuring connect-string in Spring Cloud Zookeeper

A Spring Boot application using Spring Cloud Zookeeper Discovery typically declares the appropriate starter and ZooKeeper endpoints in application.yml.

With Maven, the common dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

The starter version should be managed by a Spring Cloud BOM compatible with the Spring Boot version in use. Do not mix starter versions from a different release train.

Client configuration connecting to the ensemble:

~~~yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
      discovery:
        enabled: true
~~~

The spring.cloud.zookeeper.connect-string property specifies the list of ZooKeeper servers used by Spring Cloud Zookeeper. spring.cloud.zookeeper.discovery.enabled enables service discovery integration; defaults may depend on the version and starter, so declaring it explicitly makes configuration easier to read.

If using a dedicated namespace:

~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181/spring-cloud
~~~

Ensure /spring-cloud already exists before starting the application. When multiple services share an ensemble, agree on a consistent chroot path so they all view the same registry namespace.

### 8.1. Externalizing the connect string to environment variables

Do not hardcode environment-specific infrastructure addresses in source code. Spring Boot supports mapping environment variables to properties; you can set:

~~~bash
export SPRING_CLOUD_ZOOKEEPER_CONNECTSTRING=zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
~~~

On Windows PowerShell:

~~~powershell
$env:SPRING_CLOUD_ZOOKEEPER_CONNECTSTRING = "zk1.internal:2181,zk2.internal:2181,zk3.internal:2181"
~~~

This value maps to spring.cloud.zookeeper.connect-string. Each environment can supply its own endpoint list via deployment manifests or a configuration store. If the variable is missing in production, validate configuration at startup to catch missing endpoints early; do not let the application silently connect to localhost.

## 9. Connections, sessions, and resilience

A ZooKeeper client establishes a session with the ensemble. Sessions have a timeout; if a client stays disconnected too long and the session expires, ephemeral znodes bound to that session can be deleted. Spring Cloud Zookeeper Discovery uses this mechanism to manage instance registration lifecycles.

A connect string with multiple servers helps the client try another endpoint in the ensemble, but does not make a session last forever. When connectivity drops:

- The client can fail over to another server in the same ensemble.
- If the interruption is brief and the session remains valid, the client can resume the session.
- If the session expires, the client needs to create a new session and discovery can re-register the instance.
- If the ensemble loses quorum, registry writes and updates cannot be guaranteed to function normally.

Therefore, the connect string should list multiple nodes, the session timeout must match network conditions and JVM pause durations, and the application needs to handle reconnection states properly.

Do not confuse connect-string with timeout. The connect string only supplies addresses to find servers; session timeout controls how long a session can remain out of contact before expiring.

## 10. Verifying the application has connected and registered

After starting the ZooKeeper ensemble, start a Spring Cloud service configured with the connect string. Verify in order:

1. Confirm application logs show the client connected to ZooKeeper.
2. Check that there are no DNS, connection refused, timeout, or authentication errors.
3. Connect with the ZooKeeper CLI to the exact ensemble and chroot namespace.
4. Inspect the discovery tree used by Spring Cloud Zookeeper. A common default is /services, though it can vary depending on the discovery root configuration of the version in use.
5. Confirm the service ID and instance node appear after the application registers.
6. Stop the application gracefully, then observe the registration node being removed via lifecycle hooks.
7. Stop one ZooKeeper server as a test to verify the client stays connected to the remaining ensemble with quorum.

Example checking the root and namespace:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

~~~text
ls /
ls /spring-cloud
ls /spring-cloud/services
~~~

If not using a chroot, check the corresponding discovery root path, such as /services. Exact paths depend on configuration and version; verify against the running Spring Cloud Zookeeper configuration rather than creating multiple arbitrary trees.

## 11. Security and operating connections

ZooKeeper stores coordination data and service registration details. In production, protect both the client port and peer channels:

- Allow only authorized workloads and administration hosts to access the client port.
- Allow only ensemble members to communicate over the peer port and election port.
- Enable appropriate authentication and ACLs; restrict read/write access by namespace and application.
- Consider TLS and connection security mechanisms supported by your ZooKeeper and client library versions.
- Use durable storage for dataDir, and monitor disk usage and I/O latency.
- Track leader elections, synced follower count, session expirations, request latency, and quorum health.
- Back up according to proper procedures and test recovery; never directly copy a live data directory across nodes.

A chroot path does not replace ACLs. If two applications use two different chroots but both hold broad root permissions, separating namespaces is not enough to prevent unauthorized access.

## 12. Common configuration errors

| Symptom | Possible cause | Where to check |
|---|---|---|
| Server fails to start | Missing myid or mismatch with server.X | Check dataDir/myid and the server list |
| Node does not join quorum | Peer port/election port blocked or wrong DNS | Check hostnames, firewalls, and quorum logs |
| Client reports connection refused | Wrong port or server not listening on client port | Check clientPort, process status, and endpoint |
| Client connects to only one node | Connect string missing nodes or network allows only one endpoint | Check host list and firewalls from the workload |
| Chroot reports NoNode | Chroot path has not been created yet | Create the path before using a connect string with chroot |
| Application cannot see services | Inconsistent namespace or discovery root | Check chroot, discovery root, and znode tree |
| Instance disappears after network blip | Session expired and ephemeral node deleted | Check session timeout, reconnection, and re-registration |
| Ensemble cannot write | Quorum lost | Check leader/follower status and peer reachability |

When investigating, distinguish client connection errors from quorum errors. A client may open a TCP connection to one server while the ensemble has lost quorum and cannot process registry updates.

## 13. Sample deployment workflow

A three-node deployment workflow can follow these steps:

1. Prepare three hosts/containers with stable DNS and appropriate failure domains.
2. Open the client port for applications; open peer/election ports between ZooKeeper servers.
3. Install the same compatible ZooKeeper version across the nodes.
4. Create zoo.cfg with identical server.X lists and quorum parameters.
5. Create a dedicated dataDir and myid file with the matching ID on each node.
6. Start the servers and confirm one leader and the followers.
7. Test the client port with the ZooKeeper CLI and verify quorum via server status.
8. Create the chroot path if needed.
9. Configure spring.cloud.zookeeper.connect-string with multiple client endpoints.
10. Start the Spring Cloud service, verify the registration znode, and stop one node to test resilience.

~~~mermaid
flowchart TD
    A[Prepare hosts, DNS, and firewall] --> B[Configure identical zoo.cfg]
    B --> C[Create separate dataDir and myid]
    C --> D[Start ensemble]
    D --> E{Leader and quorum present?}
    E -->|No| F[Check peer, election, DNS, and myid]
    F --> D
    E -->|Yes| G[Create chroot if needed]
    G --> H[Configure Spring connect-string]
    H --> I[Start service and verify znode]
~~~

## 14. Summary

A production ZooKeeper ensemble typically uses 3 or 5 servers to preserve quorum when one or more nodes fail. Servers share the same server.X list, each node has its own myid and dataDir, and they communicate over peer and election ports. Applications connect via the client port.

The connect-string is a list of multiple host:clientPort pairs, optionally followed by a chroot path to separate logical namespaces. Spring Cloud Zookeeper configures this list via spring.cloud.zookeeper.connect-string; the discovery starter uses the ensemble to register and look up services. For reliable operation, verify DNS, network ports, quorum, sessions, chroot, ACLs, and reconnection behavior rather than only checking that a single TCP connection succeeds.
