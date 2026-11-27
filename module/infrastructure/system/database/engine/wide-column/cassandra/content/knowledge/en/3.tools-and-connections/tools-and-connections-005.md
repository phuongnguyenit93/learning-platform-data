# Listen/Broadcast Addresses, Internode Connections, and Application Connections

## 1. Why Does Cassandra Have Multiple Network Addresses?

Apache Cassandra is a **distributed wide-column database**. A node communicates with other nodes in the cluster while also accepting CQL statements from Java applications or `cqlsh`. These two connection groups have different roles and network configurations:

- **Internode (node ↔ node):** gossip/membership discovery, exchanging read/write messages, replica coordination, data streaming during bootstrap/repair, and various cluster administrative operations.
- **Native client (application ↔ node):** the Java Driver and `cqlsh` send CQL over the **native binary protocol**; the receiving node acts as the coordinator and then communicates with replicas over the internode path when needed.

Therefore, a node can listen on one internal network address for **internode** traffic and a different address for **clients**. Parameters containing `listen`, `broadcast`, `rpc`, and port numbers cannot be interchanged arbitrarily.

In the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this topic connects directly to distributed architecture, partition keys, replication, read/write consistency, repair operations, and connections from Java applications.

After this lesson, you will be able to:

1. Distinguish **bind/listen** addresses from **advertise/broadcast** addresses.
2. Properly configure the `listen_address`–`broadcast_address` pair for internode traffic and `rpc_address`–`broadcast_rpc_address` for clients.
3. Explain the differences between ports `7000`, `7001`, `9042`, and `7199`.
4. Test connectivity from a node and from an application host, and identify issues caused by firewalls, NAT, DNS, TLS, or driver discovery.
5. Recognize how network configuration affects gossip, replication, bootstrap, repair, and the Java Driver.

## 2. Distinguishing Bind Addresses and Broadcast Addresses

A **bind/listen address** is the IP address or interface on which the Cassandra process opens a socket to **accept incoming connections**. A **broadcast/advertised address** is the address a node **announces to other parties so they can connect back to it**. They can be the same, but in multi-NIC, containerized, NAT, or multi-network-zone topologies, they often need to differ.

| Question | Bind/listen | Broadcast/advertise |
| --- | --- | --- |
| "Where does Cassandra open its socket?" | Answered by the bound address/interface. | Does not determine which socket is listening. |
| "Which address should peers or drivers call?" | Works only if the bind address is also routable by the other party. | Publishes the endpoint for the other party to use. |
| "Can `0.0.0.0` be used?" | Allowed for client `rpc_address` under conditions; **not** for internode `listen_address`. | Never use `0.0.0.0` as an advertised connection target. |
| "Does it automatically open the firewall?" | No. | No. |

For example, a node binds its CQL service on `0.0.0.0:9042`, meaning it can listen on all applicable IPv4 interfaces. A driver cannot connect to `0.0.0.0` as a real node address; it needs an IP or DNS name reachable from the application machine.

### 2.1. Diagram of the Two Network Groups

~~~mermaid
flowchart LR
    subgraph CLIENT["Application network"]
        APP["Java Driver"]
        CQL["cqlsh"]
    end
    subgraph CLUSTER["Internode network"]
        A["Node A"]
        B["Node B"]
        C["Node C"]
    end
    APP -->|"Native CQL / 9042"| A
    APP -->|"Native CQL / 9042"| B
    CQL -->|"Native CQL / 9042"| C
    A <-->|"Internode / 7000"| B
    B <-->|"Internode / 7000"| C
    C <-->|"Internode / 7000"| A
~~~

This diagram simplifies logical communication. In practice, each node may have **one or more network interfaces** and separate firewalls. The Java Driver typically uses multiple nodes after discovering topology rather than sending every query to a single contact point.

## 3. Network Parameters in `cassandra.yaml`

| Parameter | Connection Layer | Role and Notes |
| --- | --- | --- |
| `listen_address` | Internode | Address used for node-to-node communication. **Do not set `0.0.0.0`.** |
| `listen_interface` | Internode | Selects an interface instead of an IP; **do not set simultaneously** with `listen_address`. |
| `broadcast_address` | Internode | Address advertised to other nodes. If unset, typically defaults to `listen_address`. |
| `listen_on_broadcast_address` | Internode | Option to additionally listen on the broadcast address in certain multi-interface networks; not needed in every topology. |
| `storage_port` | Internode | Port for message exchange between nodes; default **7000/TCP**. |
| `ssl_storage_port` | Internode (legacy) | Legacy SSL port, typically **7001/TCP**; used only per corresponding version configuration. |
| `rpc_address` | Native client | Native server bind address for Java Driver/cqlsh; `0.0.0.0` may be used under proper conditions. |
| `rpc_interface` | Native client | Selects an interface instead of `rpc_address`; **do not set simultaneously**. |
| `broadcast_rpc_address` | Native client | Address advertised to drivers; must be reachable from clients and must not be `0.0.0.0`. |
| `start_native_transport` | Native client | Enables/disables native transport. |
| `native_transport_port` | Native client | Native CQL port; default **9042/TCP**. |
| `server_encryption_options` | Internode | TLS/encryption configuration for node-to-node traffic. |
| `client_encryption_options` | Native client | TLS configuration for application-to-node traffic. |

These settings describe the **Cassandra server** and are normally placed in each node's `cassandra.yaml`. Parameter names and deprecation status for some options can vary by Cassandra version. Read the configuration and documentation for your exact version before editing a live cluster.

### 3.1. Internode: `listen_address` and `broadcast_address`

Minimal **illustrative** configuration example:

~~~yaml
# Cassandra Node A; IPs are documentation examples only.
listen_address: 192.0.2.11
broadcast_address: 192.0.2.11
storage_port: 7000
~~~

- `listen_address` must be a **valid address on the node** that can be bound by the operating system. Cassandra documentation warns against setting `listen_address: 0.0.0.0`.
- If `listen_interface` is available, choose **one** of `listen_address` or `listen_interface`; do not configure both. When an interface has multiple addresses, check the corresponding IPv4/IPv6 preference option.
- `broadcast_address` is the address peers use to communicate with the node. If left blank, Cassandra typically defaults to `listen_address`. The advertised address must be routable from other nodes on the internode port.
- `listen_on_broadcast_address` can be helpful in certain **dual physical interface** setups where a node must listen on both the broadcast and listen addresses. Do not enable it mechanically if routers/NAT already handle the corresponding route.

The IP ranges `192.0.2.x`, `198.51.100.x`, and `203.0.113.x` in this lesson belong to **documentation example ranges**; they are not real addresses to copy verbatim into a live cluster.

If running Cassandra only on a laptop, `listen_address: localhost` may suffice. When adding a second node on another machine, the loopback address `127.0.0.1` is no longer suitable because **127.0.0.1 on each machine points only to itself**.

### 3.2. Native Client: `rpc_address` and `broadcast_rpc_address`

~~~yaml
# Assume Node A has an interface for the application network.
start_native_transport: true
native_transport_port: 9042
rpc_address: 198.51.100.11
broadcast_rpc_address: 198.51.100.11
~~~

The name `rpc_address` is historical; in modern Cassandra, it controls the **bind address of the native CQL transport**. The port receiving CQL is normally `native_transport_port`, not `storage_port`. If using `rpc_interface` to select a NIC, do not simultaneously set `rpc_address`.

When listening on multiple interfaces:

~~~yaml
# Example of a deployment with firewall controls.
rpc_address: 0.0.0.0
broadcast_rpc_address: 198.51.100.11
start_native_transport: true
native_transport_port: 9042
~~~

Here is the critical distinction:

- `rpc_address: 0.0.0.0` is **allowed** in Cassandra, but `broadcast_rpc_address` must be set to a **concrete address**, not `0.0.0.0`.
- `broadcast_rpc_address` does not automatically enable the listener, TLS, or open ports. The driver must actually be able to connect to the advertised endpoint.
- Binding on all interfaces expands the reachable network surface; restrict **security groups/firewalls** and configure TLS, authentication, and authorization as needed.

**Do not substitute `broadcast_rpc_address` for `broadcast_address`:** one is for **Cassandra peers**, and the other is for **clients/drivers**.

### 3.3. Default Ports to Know

| Port | Connecting Parties | Who Should Have Access? | Notes |
| --- | --- | --- | --- |
| `7000/TCP` | Node ↔ node | Authorized Cassandra nodes only | Internode messages and streaming; governed by internode encryption settings. |
| `7001/TCP` | Legacy internode TLS | Nodes only, when the deployment actually uses it | `ssl_storage_port` has been deprecated since Cassandra 4.0; many modern TLS setups use port 7000. |
| `9042/TCP` | Driver/cqlsh ↔ node | Authorized application hosts/services | Native CQL; TLS encryption can run directly on 9042. |
| `9142/TCP` | Native TLS on a secondary port, if configured | Necessary clients only | `native_transport_port_ssl` is not enabled by default and is deprecated as of Cassandra 5.0. |
| `7199/TCP` | JMX/administration | Authorized administrative hosts | `nodetool` uses JMX, not native CQL. |

Changing default port numbers is possible, but requires updating network configuration, firewalls, client settings, and verifying compatibility. Do not treat `7000` or `7199` as ports for sending CQL from Java.

## 4. Scenario: Three-Node Cluster Separating Internode and Client Networks

Suppose an environment has three nodes, each with two interfaces:

| Node | Internode address (`listen`/`broadcast`) | Native client address (`rpc`/`broadcast_rpc`) |
| --- | --- | --- |
| A | `192.0.2.11` | `198.51.100.11` |
| B | `192.0.2.12` | `198.51.100.12` |
| C | `192.0.2.13` | `198.51.100.13` |

The addresses in this table are for explanation, **not real production IPs**. Corresponding interfaces and routes must actually exist before using an equivalent configuration.

On **Node A**:

~~~yaml
# Example cluster: each node must use its own dedicated IPs.
listen_address: 192.0.2.11
broadcast_address: 192.0.2.11
storage_port: 7000

start_native_transport: true
native_transport_port: 9042
rpc_address: 198.51.100.11
broadcast_rpc_address: 198.51.100.11
~~~

On Node B and Node C, substitute each node's respective addresses from the table above. This is a **network configuration excerpt**, not a complete `cassandra.yaml` file; a real cluster also requires cluster name, seed provider, snitch, datacenter/rack, token allocation, auth/TLS, resource settings, and many other options.

### 4.1. Which Connections Does a Request Traverse?

Suppose a Java application sends:

~~~sql
SELECT reading_time, value
FROM sensor_readings.readings_by_device_day
WHERE device_id = 'device-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

A typical flow is:

1. The Java Driver opens a **native** connection to Node B at `198.51.100.12:9042`.
2. Node B acts as the **coordinator**, computes the token from partition key `(device_id, reading_day)`, and identifies replicas using ring metadata and the replication strategy.
3. If it needs to communicate with Node A or Node C, the coordinator uses the **internode** path toward `192.0.2.11:7000`, `192.0.2.13:7000`, or existing connections.
4. The coordinator aggregates responses according to the query's **consistency level** and returns data to the driver over the native connection.

Node B may be both coordinator and a replica, depending on the partition's token. There is no rule saying "if the client connects to Node B, data resides only on Node B." Replication factor and consistency determine how many replicas store data and how many responses an operation needs; network addresses determine **whether communication can occur**.

### 4.2. What Are Seed Nodes?

`seed_provider` declares the **initial internode contact points** so a new node can locate the cluster and learn topology. Seed is a **discovery** role, not a master node or the place where all data is stored.

In many Cassandra versions, `SimpleSeedProvider` configures a list of seed hosts/addresses and, depending on the version, may include internode ports. Follow the exact syntax in the documentation for your deployed version.

Seeds must be **routable over the internode network**; do not mistakenly enter `broadcast_rpc_address`, which is only for Java clients. Do not turn every node into a seed; pick stable seeds and plan them appropriately across datacenters.

## 5. NAT, Containers, and Reachable Addresses

### 5.1. Why Does the Contact Point Work While the Driver Still Reports Errors?

Applications typically start with one or a few **contact points**, after which the Java Driver **discovers topology** to connect to multiple nodes. If nodes advertise native addresses on a network unreachable by the application, the driver may establish the initial connection yet fail when connecting to peers.

Example:

~~~text
Application host
  |-- connects to contact point via DNS:9042 --> succeeds
  |-- driver receives peer native endpoint: 10.0.8.22:9042
  |-- connects to 10.0.8.22:9042             --> times out
~~~

The cause may be that `broadcast_rpc_address` advertises a container/pod IP or private network unreachable by external clients, or that NAT/proxy address/port translation is misconfigured. The right fix is to check the **endpoints the driver actually discovers**, routes/firewalls to **each node**, and appropriate address translation if the system sits behind NAT.

A TCP load balancer in front of a contact point **does not automatically guarantee** that the driver can reach every discovered peer. With Kubernetes, rely on the platform's networking/operator/driver strategy rather than altering individual pod broadcast IPs in ways that break node communication.

### 5.2. Client-Side NAT Example Only

A node with a private internode network that needs to advertise its client endpoint through NAT might need a configuration equivalent to:

~~~yaml
listen_address: 10.20.0.11
broadcast_address: 10.20.0.11

rpc_address: 0.0.0.0
broadcast_rpc_address: 198.51.100.11
native_transport_port: 9042
~~~

This is an **explanatory model**, not a runnable complete configuration: `198.51.100.11` is a documentation IP, and a real deployment requires **NAT/routing/port forwarding** from the advertised IP to the node's listener, firewall/TLS policies, and stable endpoints for all nodes. Configuring client NAT does not automatically solve NAT between **internode peers**.

If nodes across multiple sites/datacenters need to advertise different addresses, verify connectivity from **every node to every relevant internode endpoint**. When using asymmetric IP networks, rely on the capabilities supported by your Cassandra version, cluster management tooling, and actual network layer.

### 5.3. Why Should You Not Arbitrarily Change a Ring Member's Address?

Internode addresses are tied to cluster identity/gossip and topology metadata. Changing `listen_address` or `broadcast_address` on a production node and restarting without a plan can cause peers to treat the new address as a different endpoint, hindering the node from rejoining the ring or disrupting routing/replication.

If you need to move a node to another machine/IP, follow the **replace/decommission/bootstrap procedure** appropriate for your Cassandra version and cluster state, while verifying host ID, tokens, seeds, firewalls, and replication. Do not treat changing an internode IP as a routine single-line YAML edit.

## 6. How Internode Connections Affect Data and Consistency

Internode addresses do not determine the **partition key** or **replication factor**, but a broken internode network can prevent the cluster from satisfying the application's consistency requirements.

Hypothetical example of one datacenter with **RF = 3**:

| Condition | Write/Read at `ONE` | Write/Read at `LOCAL_QUORUM` |
| --- | --- | --- |
| Three replicas available | Can be satisfied | Can be satisfied if 2 replicas respond. |
| One replica unavailable | Can be satisfied by 1 of the remaining 2 replicas | Can be satisfied if both remaining replicas respond. |
| Only one replica available | Can be satisfied under suitable conditions | Not enough for 2 responses to achieve quorum. |

This is a **replica-counting** example and does not cover every timeout, failure, or multi-datacenter topology scenario. A node showing `UN` in `nodetool status` does not guarantee all internode and CQL connections/latencies are healthy. If the network between some nodes is partitioned, the coordinator may report `Unavailable`, `ReadTimeout`, or `WriteTimeout` depending on the operation and CL.

During bootstrap, repair, or SSTable streaming, data moves over **internode** connections. Therefore, port 9042 working does not mean repair/streaming will succeed. Conversely, healthy internode links do not prove external applications can reach port 9042.

### 6.1. TLS and Security on Both Paths

~~~text
Application ---- native CQL/TLS ----> Cassandra node
                 client_encryption_options

Cassandra node ---- internode/TLS ----> Cassandra node
                    server_encryption_options
~~~

**`client_encryption_options`** protects **client ↔ server** connections; **`server_encryption_options`** protects **server ↔ server** connections. Enabling one does not automatically enable the other. Modern internode TLS can use `storage_port` 7000; `ssl_storage_port` 7001 is a legacy mechanism in many 4.x/5.x releases. Distinguish TLS from application-level CQL authentication/authorization.

Production networks need firewalls restricting `7000` to trusted nodes, `9042` to authorized application hosts, and `7199` strictly to administration. Never expose internode/JMX ports to the Internet to "fix timeouts."

## 7. Layer-by-Layer Connection Diagnostics

Working from the network layer up to Cassandra helps pinpoint whether the fault lies in the **bind address**, **broadcast address**, **firewall**, **TLS**, **topology**, or **CQL query**.

### 7.1. From the Application Host: DNS, TCP, and cqlsh

On Linux/macOS:

~~~bash
# Checks whether a TCP connection opens; does not prove CQL works.
nc -vz db-a.example.internal 9042

# Tests native CQL using a real client.
cqlsh db-a.example.internal 9042
~~~

On Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName db-a.example.internal -Port 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;
SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

If TCP connects but `cqlsh` fails to enter, inspect **TLS**, **auth**, cqlsh/native protocol compatibility, and server logs. When the server requires TLS, provide the corresponding options and truststore/certificate configuration, for example:

~~~bash
cqlsh db-a.example.internal 9042 --ssl -u student
~~~

Do not embed passwords in shell commands or shared files. `--ssl` does not replace verifying the CA, hostname, and certificate according to actual configuration.

### 7.2. On the Cassandra Node: Listeners and Ring Status

Run in an environment with administrative privileges:

~~~bash
# Is native transport enabled on the node?
nodetool statusbinary

# How are nodes seen by Cassandra?
nodetool status

# Gossip/endpoint information (output depends on version).
nodetool gossipinfo

# Monitor streaming status during bootstrap/repair.
nodetool netstats
~~~

On Linux, you can inspect listening sockets with:

~~~bash
ss -lnt
~~~

Check the addresses/ports in the `ss` output against `rpc_address`, `native_transport_port`, `listen_address`, and `storage_port`. `nodetool statusbinary` relies on JMX and reports native transport status on the queried node; `nodetool status` reports ring status and is not a TCP test from the application host.

### 7.3. Checking Internode Paths Between Nodes

From **Node B**, test TCP to **Node A's internode broadcast address**:

~~~bash
# Documentation example IP; replace with the actual address.
nc -vz 192.0.2.11 7000
~~~

Test in reverse from A to B and across relevant node pairs. If TCP opens but gossip/streaming still fails, inspect server-to-server TLS, certificates, internode authentication, cluster configuration, and logs. A single TCP connection test does not prove all bidirectional data streams are open.

On Cassandra 4.x+ with suitable metadata tables, you can inspect via cqlsh:

~~~sql
-- Structure and access permissions of system tables depend on version.
DESCRIBE TABLE system.local;
DESCRIBE TABLE system.peers_v2;
~~~

`system.peers_v2` exists in newer versions; on older Cassandra releases, check `system.peers` and the documentation for your running version. Never write directly to system tables to "fix an IP."

### 7.4. Which Error to Inspect at Which Layer?

| Symptom | Primary Diagnosis | Resolution |
| --- | --- | --- |
| `Connection refused` on 9042 | Native listener not running, bound to wrong IP/port, firewall rejecting | Check `start_native_transport`, `rpc_address`, `native_transport_port`, listener status. |
| TCP 9042 timeout from application | Routing, DNS, firewall, security group, NAT | Test from the application host itself and toward every advertised endpoint, not just the contact point. |
| `cqlsh` works on the node but not remotely | `rpc_address: localhost`, firewall, or client address | Check whether the listener is bound to the application network interface. |
| Driver reaches contact point then loses peers | `broadcast_rpc_address` unreachable or local DC mismatch | Inspect peers discovered by the driver, routing to each native endpoint, and driver policy. |
| Node B does not see Node A even though cqlsh works | Internode `listen/broadcast`, `7000`, seed/gossip | Check node-to-node connectivity and gossip logs; native 9042 is a separate layer. |
| `listen_address: 0.0.0.0` prevents valid node startup | Wildcards are disallowed for internode addresses | Configure a concrete internode IP or interface. |
| `rpc_address: 0.0.0.0` without `broadcast_rpc_address` | Node has no concrete endpoint to advertise to clients | Set an actually routable broadcast address. |
| TLS handshake fails | Sides disagree on TLS usage, CA/hostname mismatch | Inspect `client_encryption_options` or `server_encryption_options` separately depending on the failing path. |
| `Unauthorized` once CQL is connected | Missing CQL permissions on role/keyspace/table | Check authentication/authorization; do not change ports to fix permission errors. |
| `Unavailable` or timeout under quorum | Insufficient replicas or slow responses | Check `nodetool status`, internode network, RF, CL, logs, and system load. |
| Repair/streaming fails while regular queries still run | Internode connectivity/throughput or disk/resource limits | Check `nodetool netstats`, firewall, TLS, logs, and disk/network load. |
| Inconsistent endpoints/host IDs after changing node IP | Changed ring member address without proper procedure | Stop ad-hoc changes; follow the version-appropriate node replacement/migration procedure. |

## 8. CQL Practice: Check the Data Model After the Network Works

Once the endpoint and cqlsh connect successfully, proceed to CQL checks. The lab below is suitable only for a **single-node practice environment**, so it uses `SimpleStrategy` and RF = 1:

~~~sql
CREATE KEYSPACE IF NOT EXISTS network_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS network_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  reading_time timestamp,
  reading_id uuid,
  value double,
  PRIMARY KEY ((device_id, reading_day), reading_time, reading_id)
) WITH CLUSTERING ORDER BY (reading_time DESC, reading_id ASC);

INSERT INTO network_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('device-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

INSERT INTO network_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('device-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 25.3);

SELECT reading_time, value
FROM network_lab.readings_by_device_day
WHERE device_id = 'device-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Expected result: two rows, with timestamp `01:05` before `01:00`. The `WHERE` clause specifies the **composite partition key** `(device_id, reading_day)`, allowing Cassandra to route directly to the partition. `listen/broadcast` addresses and the native port make the **connection path work**, but they do not replace the requirement for query-driven table design.

For multi-datacenter systems, use an appropriate replication strategy such as `NetworkTopologyStrategy` and replica counts matching actual datacenters. `RF = 1` in the lab does not demonstrate quorum behavior or multi-node fault tolerance. When evaluating consistency, examine both topology and required acknowledgment levels together.

## 9. Connecting from the Java Driver and Inspecting Topology

This example uses the **Apache Cassandra Java Driver 4.x** API. In a real deployment, replace contact points with **native addresses actually reachable from the application machine** and replace the local datacenter name with the value queried from `system.local`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;

public class CassandraNetworkExample {
    public static void main(String[] args) {
        // Actual IP addresses must be reachable from the application.
        // "datacenter1" is only an example; verify via SELECT from system.local.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT reading_time, value " +
                "FROM network_lab.readings_by_device_day " +
                "WHERE device_id = ? AND reading_day = ?");

            ResultSet result = session.execute(
                prepared.bind("device-01", LocalDate.of(2026, 11, 21)));

            for (Row row : result) {
                System.out.println(
                    row.getInstant("reading_time") + " => " +
                    row.getDouble("value"));
            }
        }
    }
}
~~~

This snippet is for a local machine lab. When moving to a cluster, provide contact points using real native hosts/ports—for example, multiple nodes in the **same datacenter** preferred by the application. The driver connects to a contact point to discover topology and can then establish connections to peers whose native addresses are advertised. Supplying three contact points does not mean the driver will use only those three nodes.

**Notes:**

- `withLocalDatacenter(...)` must match the datacenter name actually reported by the cluster. A mismatch can cause the driver to ignore the intended nodes.
- The Java Driver operates over **9042/native CQL**, not by connecting to internode `listen_address:7000`.
- `CqlSession` should be long-lived in an application and reused across many queries; `try-with-resources` here demonstrates closing the session when the program exits.
- Use prepared statements/bind parameters rather than concatenating input values into CQL strings.
- If the application reports timeouts after connecting successfully, evaluate the **partition key**, RF, consistency, replica status, and internode health before concluding it is an `rpc_address` bug.

## 10. Self-Practice Exercises

1. Explain in words the two paths "Java Driver → coordinator" and "coordinator → replica." Specify the ports and address groups used on each path.
2. In a two-network-interface configuration, identify the roles of `listen_address`, `broadcast_address`, `rpc_address`, and `broadcast_rpc_address`. Why can't the two pairs be arbitrarily swapped?
3. A node sets `listen_address: 127.0.0.1` when joining a two-machine cluster. Predict the failure and propose a valid replacement address.
4. Explain why `rpc_address: 0.0.0.0` requires a concrete `broadcast_rpc_address` and why `listen_address: 0.0.0.0` is disallowed.
5. Describe the verification workflow from application host to node: DNS → TCP 9042 → cqlsh/TLS/auth → peer discovery → CQL. When should you switch to checking port 7000?
6. In an RF = 3 scenario, one replica cannot receive internode messages. Calculate the required responses for `ONE` and `LOCAL_QUORUM`, then describe the conditions under which operations still succeed.
7. The Java Driver connects to a contact point successfully but reports timeouts for a peer at `10.0.8.22:9042`. Which configurations should you inspect and from where should you test connectivity?
8. Suppose you are preparing to change the IP of a production node. Explain why you should not simply edit `broadcast_address` and restart; what topology management steps are needed?
9. Run the CQL lab in Section 8 after verifying the endpoint. Explain why the query must filter on the full `(device_id, reading_day)` even though the native connection succeeded.

**Completion criteria:** distinguish and properly configure both listen/broadcast address pairs, identify the ports for each connection type, test networking from the right source, explain peer discovery errors, and connect network failures to Cassandra replication and consistency.

## References

- [Apache Cassandra — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `listen_address`, `broadcast_address`, `rpc_address`, `broadcast_rpc_address`, `storage_port`, native transport, and TLS options.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): node/cluster structure, replication, and client coordinators.
- [Apache Cassandra — Gossip](https://cassandra.apache.org/doc/stable/cassandra/architecture/gossip.html): how nodes learn cluster membership state.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): node status, native transport, gossip, and streaming.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): contact points, local datacenter, metadata/topology, and sessions.
