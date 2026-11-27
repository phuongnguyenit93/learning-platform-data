# Name Resolution, Container Networking, Firewalls, and Connection Path Verification

## 1. The Problem: A Cassandra Address That Works Here May Fail Elsewhere

Apache Cassandra is a **distributed wide-column database**. Java applications or `cqlsh` send CQL to a node via the **native binary protocol**, typically on TCP port **9042**. The receiving node acts as the **coordinator** and communicates with replicas according to the partition key, replication, and operation consistency. Therefore, the connection path must work both from **client → coordinator** and, when needed, **node → node**.

In practice, issues often start from a seemingly simple situation:

- Running `cqlsh 127.0.0.1 9042` **inside the Cassandra container** succeeds, yet running it from the host machine returns `Connection refused`.
- A Java application running on the host connects via `localhost:9042`, yet when Java runs in another container the connection fails.
- The Java Driver connects to a contact point, then reports errors for peers with private IPs unreachable from the application.
- DNS resolves the hostname, yet a firewall or TLS prevents the native handshake from succeeding.

The key is always identifying **where the client process is running**, what IP the hostname resolves to **within that exact environment**, and whether TCP/TLS/CQL passes through each layer.

This lesson belongs to the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It helps establish a reliable connection path for practicing CQL, query-driven table design, read/write consistency control, observing replication/repair, and accessing Cassandra from Java.

**Objectives:**

1. Distinguish **hostname**, **DNS**, `localhost`, container IP, host OS, and Cassandra's advertised endpoint.
2. Choose the right address and port when the client runs on the host, in Docker Compose, in Kubernetes, or outside the cluster network.
3. Verify in order: **name resolution → TCP → TLS → native protocol → auth → topology → CQL**.
4. Distinguish firewall rules for **native 9042**, **internode 7000**, JMX, and optional TLS ports.
5. Diagnose errors where the Java Driver connects to a contact point successfully but cannot reach discovered nodes.

## 2. Connection Path Map

~~~mermaid
flowchart LR
    subgraph HOST["Host machine"]
        H["Java app on host"]
        P["Host port 127.0.0.1:9042"]
    end
    subgraph NET["Docker Compose network"]
        A["Java app in app container"]
        C["cassandra container / native 9042"]
    end
    H -->|"TCP to published port"| P
    P -->|"Docker port forwarding"| C
    A -->|"Service DNS: cassandra:9042"| C
    C -.->|"Internode 7000 with peers"| R["Other Cassandra node"]
~~~

This diagram illustrates **one Cassandra container** and can be extended with peers. Applications on the **host** and applications **inside a container** see different network namespaces. The client's network namespace determines what `localhost` means.

### 2.1. Easily Confused Addresses

| Address or Name | What Does It Mean? | Where Can It Be Used From? |
| --- | --- | --- |
| `127.0.0.1` / `localhost` | Loopback of **the exact network namespace where the client runs**. | Host to a service published on the host; a container only to itself; containers **within the same Kubernetes Pod** can share loopback. |
| `cassandra` | Service name provided by Docker Compose DNS within the Compose network. | Containers on the same Compose network; typically **does not** resolve directly from the host. |
| Container IP such as `172.18.0.5` | IP on the bridge/container network, which may change when recreated. | Containers/networks routed accordingly; should not be hard-coded in apps. |
| `host.docker.internal` | Special hostname typically pointing from a container to the host on **Docker Desktop**. | Containers needing to call a service on the host; on Linux it usually requires explicit configuration. |
| `db.example.internal` | Organization-managed DNS name that may point to a host, load balancer, or specific endpoint. | Only machines with DNS and network routing to the resolved address. |
| `cassandra.default.svc.cluster.local` | Illustrative Kubernetes Service DNS name. | Typically from Pods inside the cluster; has no meaning on the Internet or a personal laptop. |

**There is no single hostname that works for every client.** Always check where the **Java process** or **cqlsh process** runs rather than taking an address that worked in another terminal and assuming it is reusable.

### 2.2. Native Client and Internode Are Two Separate Paths

| Common Port | Protocol / Purpose | Which Side Needs Access? |
| --- | --- | --- |
| **9042/TCP** | Cassandra CQL native transport (can also use TLS directly on this port) | Java Driver/cqlsh → reachable native endpoints on nodes |
| **7000/TCP** | Internode exchange, gossip, replica requests, streaming per config | Cassandra node ↔ Cassandra node |
| **7001/TCP** | Legacy internode TLS port if configured by the version | Only nodes when this port is actually used |
| **7199/TCP** | JMX for `nodetool`/administration | Authorized administrative machines only |
| **9142/TCP** | Secondary native TLS port if supported by version/config | Only when explicitly enabled on nodes; not the default |

Port numbers can be customized in `cassandra.yaml`. A TCP connection to `7000` does not allow sending CQL; conversely, `9042` working does not prove internode gossip, bootstrap, or repair is healthy. In Cassandra 5.0, the separate native TLS port `native_transport_port_ssl` is marked deprecated; check documentation for your exact version.

## 3. Name Resolution: Test from Where the Application Runs

### 3.1. Layers That May Participate in Name Resolution

A hostname may be mapped via a `hosts` file, internal DNS, Compose/Kubernetes DNS, the OS resolver, or deployment-specific mechanisms. Each container/Pod can have a different `/etc/hosts` and `/etc/resolv.conf` from the host.

A command succeeding from a **personal laptop** does not prove the same hostname resolves properly from a **container or production server**. Conversely, a service name like `cassandra` may exist only inside a Docker Compose network.

Common checks on Linux:

~~~bash
# Check which IP a name resolves to, potentially including /etc/hosts.
getent hosts db.example.internal

# Query DNS when dig is available.
dig db.example.internal

# Resolve a service name from inside a container that has getent.
getent hosts cassandra
~~~

On Windows PowerShell:

~~~powershell
Resolve-DnsName db.example.internal
~~~

**Run from the exact source of the request.** For example, `getent hosts cassandra` on the host may fail to find the name, while inside a container on the same Compose network it returns Cassandra's IP. Additionally, `getent`/`dig` are not included in every minimal image; use a diagnostic container on the same network when needed.

### 3.2. DNS Success Is Not Enough

Suppose `db.example.internal` resolves to `10.30.5.20`. To conclude the application can connect to Cassandra, you still must answer:

1. Does the client machine have **routing** to `10.30.5.20`?
2. Is there a listener on `9042/TCP` and does the firewall permit it?
3. Does that port require **TLS**, and is the client configured accordingly?
4. Are the native protocol/driver compatible and are auth credentials correct?
5. When the driver discovers other peers, do **those peers** have addresses reachable from the client?

`ping` only tests ICMP if allowed; many environments block ICMP while TCP still works. Do not use `ping` success/failure as the final verdict for native CQL.

## 4. Docker Compose: Host Ports and Service DNS

### 4.1. A Single Cassandra Container for a Learning Environment

The **illustrative** `compose.yaml` below runs a single Cassandra node for connectivity testing. Choose an image/tag approved by your project when deploying; `cassandra:4.1` here is a specific version for the example.

~~~yaml
services:
  cassandra:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: local-network-lab
    ports:
      # Publish only on host loopback for the lab.
      - "127.0.0.1:9042:9042"
~~~

Start and inspect:

~~~bash
docker compose up -d
docker compose ps
docker compose port cassandra 9042
docker compose logs --tail=100 cassandra

# Run cqlsh directly inside the Cassandra container.
docker compose exec cassandra cqlsh 127.0.0.1 9042
~~~

Cassandra may still be initializing its schema and native transport when the container already appears in `docker compose ps`; confirm it is **ready to accept CQL** before diagnosing failures. `docker compose exec cassandra cqlsh ...` tests **from inside the Cassandra container**, not the path from the host.

Because `127.0.0.1:9042:9042` is published, from a **terminal on the host**:

~~~bash
cqlsh 127.0.0.1 9042
~~~

On a Windows host you can test TCP:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 9042
~~~

If `cqlsh` is not installed on the host, test TCP first, then use a client installed on the host or a diagnostic container with an appropriate route. `Test-NetConnection` only tests TCP, without verifying native protocol or authentication.

### 4.2. When the Java Application Also Runs in Docker Compose

If there is an `app` service on the **same Compose network**, Java should connect to `cassandra:9042`:

~~~text
Client running on host:
    127.0.0.1:9042  -> Docker published port -> Cassandra container:9042

Client running in app container:
    cassandra:9042  -> Compose DNS -> Cassandra container:9042

App-container client using 127.0.0.1:9042:
    127.0.0.1 is the app container ITSELF -> usually Connection refused
~~~

Docker Compose provides service names and a default network for services in the same project unless network configuration is changed. Normally **`ports` is not needed** for the `app` container to call `cassandra:9042` on the same network. `ports` is for **publishing ports to the host**; `expose` (if present) also does not publish to the host.

When the Cassandra container is recreated, its internal IP may change. Use the **service name** so Docker DNS resolves the current endpoint rather than hard-coding a bridge IP address.

### 4.3. Published Ports and the Risk of Over-Exposure

~~~yaml
# Example of binding the port on the host:
ports:
  - "127.0.0.1:9042:9042"  # host loopback only, suitable for a local lab
~~~

Contrast with:

~~~yaml
ports:
  - "9042:9042"  # typically publishes across host interfaces
~~~

Values like `9042:9042` can make the port reachable from outside the host depending on Docker, the OS, and the firewall. Do not publish Cassandra native transport to untrusted networks; when remote access is needed, use a private network/VPN, source-restricted firewalls, TLS, and proper auth.

A container **does not become reachable from the host merely because the Cassandra process inside the container opens 9042**: the host needs a path to the container (such as port mapping). At the same time, publishing a port cannot fix a bind/advertise error if Cassandra itself has not opened its native listener.

### 4.4. If a Containerized App Needs to Call Cassandra on the Host

This is the **reverse** of the Compose scenario above. On Docker Desktop, the hostname `host.docker.internal` typically lets containers reach the host:

~~~text
App container -> host.docker.internal:9042 -> Cassandra on host
~~~

On Docker Engine for Linux, this name does not work by default in every configuration; you may need to configure a host gateway/network per Docker documentation. Furthermore, Cassandra on the host must bind an interface reachable from the container; if it listens only on `127.0.0.1` on the host, the container generally cannot reach it via the host gateway. This pattern is unnecessary when **Cassandra is already another service on the same Docker network**.

## 5. Kubernetes Environments: Pods, Services, and DNS

Kubernetes adds a DNS/Service layer and differs from Docker Compose in several ways:

- Containers **inside the same Pod** share a network namespace and can reach each other on `localhost` when the service listens on that port.
- **Different Pods** have separate IPs. An app Pod calling `localhost:9042` targets **itself**, not a separate Cassandra Pod.
- Pods typically access a Service by a name such as `cassandra` within the namespace or the FQDN `cassandra.default.svc.cluster.local`.
- Clustered Cassandra is usually deployed via a **StatefulSet/operator, stable DNS, and sometimes a headless Service** so each node has its own identity/endpoint. A single ClusterIP/load balancer does not guarantee the Java Driver can discover and connect to every node Cassandra advertises.
- From outside Kubernetes, `*.svc.cluster.local` hostnames and Pod IPs usually lack external DNS/routing. Any supported NodePort/LoadBalancer or TCP ingress must be paired with accurate native endpoints, topology, firewalls, and security configuration.

The reference diagnostic commands below assume namespace `dev` and read permissions:

~~~bash
# View Pod IPs, status, and Kubernetes nodes.
kubectl get pods -n dev -o wide

# View Services, Service types, and ports.
kubectl get svc -n dev

# EndpointSlices behind the cassandra Service (name depends on deployment).
kubectl get endpointslice -n dev -l kubernetes.io/service-name=cassandra

# Check NetworkPolicies that may affect TCP traffic.
kubectl get networkpolicy -n dev

# Test cqlsh in a Cassandra Pod if the image includes cqlsh.
kubectl exec -n dev cassandra-0 -- cqlsh 127.0.0.1 9042
~~~

Substitute the namespace, Pod, and Service names for your deployment. When investigating why **an app Pod cannot reach Cassandra**, the key test must run **from the app Pod or a debug Pod with the same network policy**. Testing inside the Cassandra Pod only confirms the native listener locally inside Cassandra.

NetworkPolicy enforcement depends on the CNI network plugin and active policies; `kubectl get networkpolicy` listing objects does not by itself prove packets are being dropped. Inspect both **ingress on Cassandra**, **egress on the app**, ports, labels, and namespace selectors if present.

## 6. Cassandra Bind/Advertise: Why One Contact Point Is Not Enough

Cassandra has two separate address pairs in `cassandra.yaml`:

| Setting | Traffic | Meaning |
| --- | --- | --- |
| `listen_address` | Internode | IP/interface Cassandra binds for node ↔ node. **Do not use `0.0.0.0`.** |
| `broadcast_address` | Internode | Endpoint other nodes use to contact this node. |
| `rpc_address` | Native client | IP/interface Cassandra binds for CQL native transport. May be `0.0.0.0` with a valid accompanying config. |
| `broadcast_rpc_address` | Native client | Endpoint drivers discover and connect to. Must be a **concrete, reachable** address for relevant clients. |

A **conceptual** configuration excerpt for a node with a real client IP:

~~~yaml
start_native_transport: true
native_transport_port: 9042

# Can listen on all IPv4 interfaces of the node/container itself.
rpc_address: 0.0.0.0

# Example IP; real deployments must have a routable endpoint to the node.
broadcast_rpc_address: 192.0.2.20
~~~

`192.0.2.20` is an **illustrative documentation IP**, not an IP to copy into a real system. If `rpc_address` is `0.0.0.0`, `broadcast_rpc_address` must declare a concrete address and cannot be `0.0.0.0`. **Do not assign the host's IP as a bind address inside a container** if the container does not own that IP.

### 6.1. Case: Java Driver Discovers an Unreachable Peer

Suppose:

~~~text
Java running outside the container network
  |
  | -> db-gateway.example.internal:9042       [TCP succeeds]
  |
  | <- metadata: Cassandra peer = 172.18.0.5:9042
  |
  | -> 172.18.0.5:9042                       [times out]
~~~

The Java Driver uses a **contact point** to initialize, then discovers topology and opens connections to other nodes. If Cassandra advertises a bridge/container IP that cannot be routed from outside, some requests or session discovery/initialization itself will fail.

How to investigate:

1. Identify which network namespace the Java Driver runs in and log the **actual peer addresses** the driver attempts to connect to.
2. Compare those addresses with `broadcast_rpc_address` and the node's cluster metadata.
3. Test DNS/TCP **from the Java host to every native endpoint** the driver may select.
4. When using NAT, proxies, Kubernetes, or load balancers, use an **address translation/gateway mechanism supported by the driver/cluster**; design stable per-node endpoints.
5. Do not assume port-mapping a **single** node suffices for a multi-node or multi-datacenter cluster.

**Separate internode path:** Cassandra nodes use `listen_address`/`broadcast_address` and `storage_port` 7000 for gossip/streaming. The Java Driver does not send CQL to 7000. Internode network errors can surface as `Unavailable`, read/write timeouts, or bootstrap/repair failures even while native 9042 still connects.

## 7. Firewalls: Opening the Right Path, Source, and Destination

A complete network path involves the server listener, routing, and allow rules. In many environments, TCP packets must also pass **host firewalls, cloud security groups/ACLs, container forwarding, Kubernetes NetworkPolicies**, or proxies.

| Flow | Typical Port | Recommended Scope | If Blocked |
| --- | --- | --- | --- |
| App/cqlsh → Cassandra native | 9042/TCP | Trusted application networks only; enforce TLS/auth | `Connection timed out` / refused / driver no node |
| Cassandra node ↔ node | 7000/TCP | Cluster nodes and internode network only | Gossip, replica requests, streaming, bootstrap/repair failures |
| Legacy internode TLS | 7001/TCP if configured | Relevant nodes only | Internode TLS fails to complete |
| Admin → JMX | 7199/TCP common | Authorized admin sources only | `nodetool` cannot connect to JMX |
| App → separate native TLS port | 9142/TCP if configured | Required apps only | Secondary-port native TLS fails |

**Distinguishing network failure types:**

- `Connection refused` typically indicates **no listener** at that IP/port or an active rejection by a network device (TCP RST/REJECT).
- `Connection timed out` typically stems from **DROP/firewall, routing, network partition**, or the destination failing to respond in time.
- `SSLHandshakeException` indicates TCP reached the TLS stage but negotiation/certificate validation failed; it is not evidence that the port is closed.
- `Unauthorized` in CQL means connection and authentication went far enough for the server to **deny CQL permissions**.
- `ReadTimeout`/`WriteTimeout` after CQL is sent usually warrants checking replicas, consistency, internode networking, load, compaction, or server logs.

Never troubleshoot by disabling firewalls system-wide or exposing `7000`/`7199` to the Internet. Inspect and refine rules with **minimal source/destination/port** scope per environment policy.

## 8. Layer-by-Layer Connection Verification Workflow

A consistent checklist prevents mistaking DNS issues for native protocol errors:

~~~mermaid
flowchart TD
    A["Identify which host/container/Pod the client runs on"] --> B{"Does target name resolve to the right IP?"}
    B -->|"No"| C["Check DNS, hosts, network namespace"]
    B -->|"Yes"| D{"Can TCP reach the right IP:port?"}
    D -->|"No"| E["Check listener, ports, routing, firewall"]
    D -->|"Yes"| F{"Does TLS match if required?"}
    F -->|"No"| G["Check TLS mode, CA, hostname, certificates"]
    F -->|"Yes"| H{"Do native handshake and auth succeed?"}
    H -->|"No"| I["Check cqlsh/driver, protocol, credentials"]
    H -->|"Yes"| J{"Can driver reach discovered peers?"}
    J -->|"No"| K["Check broadcast RPC, NAT, topology, local DC"]
    J -->|"Yes"| L["Run CQL by partition key and check CL/replicas"]
~~~

### 8.1. Step 1: Identify Exact Source and Destination

Record: whether the client runs on the **host**, which container, which Pod/namespace, or another VM; the hostname/IP and port being connected to; and whether the node enables TLS/auth. If there are multiple endpoints, record the full list.

### 8.2. Step 2: Name Resolution

~~~bash
# Linux inside client environment; name may come from hosts or DNS.
getent hosts db.example.internal
~~~

~~~powershell
# Windows host or Windows machine running the application.
Resolve-DnsName db.example.internal
~~~

If the name only resolves inside Docker Compose, run the test **inside the application container**, not on the host.

### 8.3. Step 3: Check TCP

~~~bash
# Linux/macOS: test opening a connection to the native port.
nc -vz db.example.internal 9042
~~~

~~~powershell
# Windows PowerShell: succeeds when TcpTestSucceeded=True.
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

Note: `nc` and `Test-NetConnection` test only the **TCP socket**; they do not send CQL. If they fail, confirm the Cassandra service has native transport enabled and is listening on the right IP:

~~~bash
# Run in a Cassandra environment with JMX access.
nodetool statusbinary

# On a Linux node/container when tools and permissions are available:
ss -lnt
~~~

With Docker, also check `docker compose ps` and `docker compose port cassandra 9042`. With Kubernetes, check Service, EndpointSlice, Pod readiness, and NetworkPolicy.

### 8.4. Step 4: Verify TLS, Then Native Protocol

If the endpoint **is configured for TLS**, test the handshake from the client:

~~~bash
openssl s_client -connect db.example.internal:9042 -servername db.example.internal
~~~

This command makes sense only if the **port actually speaks TLS**; a non-TLS native port will not return the expected handshake. A valid certificate requires verifying the CA chain, hostname/SAN, and client TLS policy; opening an SSL connection alone is not enough.

Next, use **actual `cqlsh`**:

~~~bash
# If the server does not require TLS/auth (e.g., local lab).
cqlsh db.example.internal 9042

# If the server requires TLS and a username.
cqlsh db.example.internal 9042 --ssl -u student
~~~

Do not enter passwords directly into command history. If cqlsh works while Java does not, compare **TLS config, credentials, native protocol version, local datacenter, and the nodes the Java Driver discovers**.

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

SELECT cluster_name, data_center, release_version
FROM system.local;

DESCRIBE KEYSPACES;
~~~

`system.local` shows the cluster/datacenter of the node handling the request. This datacenter name is critical for the Java Driver's `withLocalDatacenter` setting.

### 8.5. Step 5: Check Peers and Internode Paths

On a node with administrative access:

~~~bash
nodetool status
nodetool gossipinfo
nodetool netstats
~~~

From **Node B**, test TCP to **Node A's internode broadcast address** (assuming port 7000):

~~~bash
nc -vz 192.0.2.11 7000
~~~

`192.0.2.11` is an illustrative address. Replace it with the peer's real address. Node-to-node paths normally need bidirectional connectivity and consistent internode TLS. `nodetool status` displays ring status, but does not replace detailed TCP/TLS checks from each node or inspecting server logs.

## 9. CQL Lab: Verifying the Connection Reached the Right Cluster

Once cqlsh enters the **lab cluster**, create data to verify the full CQL path. The example below uses a **single-node Cassandra instance, RF = 1**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS connection_path_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS connection_path_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO connection_path_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature');

INSERT INTO connection_path_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'humidity');

SELECT event_time, event_type
FROM connection_path_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

**Expected:** two rows, with `01:05:00Z` before `01:00:00Z`. The partition key `(device_id, event_day)` routes the query to the corresponding partition; success at the TCP/TLS layer does not replace query-driven table design. If you hit `Unavailable` or timeouts when raising consistency, also inspect **replication factor, responding replicas, and internode networking**.

`SimpleStrategy`/RF = 1 is only for a single-node lab. For multi-node/multi-datacenter clusters, typically use `NetworkTopologyStrategy` and replica counts appropriate for actual datacenters.

## 10. Java Driver: Configuring Hostname Based on Where the Application Runs

The following example uses **Apache Cassandra Java Driver 4.x**. The hostname is read from an environment variable so the same program can run on the host or inside a Compose network.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;

public final class CassandraNetworkDemo {
    public static void main(String[] args) {
        // Java on host: CASSANDRA_HOST=127.0.0.1 if local port is published.
        // App container: CASSANDRA_HOST=cassandra if on the same Compose network.
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        // Replace with actual data_center obtained from system.local.
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT event_time, event_type " +
                "FROM connection_path_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            for (Row row : session.execute(
                    ps.bind("sensor-01", LocalDate.of(2026, 11, 21)))) {
                System.out.println(
                    row.getInstant("event_time") + " -> " +
                    row.getString("event_type"));
            }
        }
    }
}
~~~

**Takeaways:**

- On the **host**, if Compose publishes `127.0.0.1:9042:9042`, choose `CASSANDRA_HOST=127.0.0.1`.
- In an **app container on the same Compose network**, choose `CASSANDRA_HOST=cassandra`; do not use `127.0.0.1`, which refers to the app container itself.
- On a **machine outside the cluster**, choose a native endpoint DNS/IP **with a real network route** and configure TLS/auth if required by the server.
- On **Kubernetes**, choose an endpoint supported by the deployment/operator/driver; confirm the driver can reach peers after discovery.
- The value `datacenter1` is an example, not an immutable default DC name. Get the real name from `SELECT data_center FROM system.local;`.

`CqlSession` should be reused and long-lived within a service. The driver can connect to peers beyond the contact point, so the addresses advertised by Cassandra must also match the application network. When encountering `AllNodesFailedException` or no-node-available errors, inspect the **per-node cause** in the exception/logs, then check hostname/IP, port, TLS, authentication, and local DC.

If the environment requires TLS/auth, configure the SSL context and auth provider properly in the driver (with proper secrets management). Never bypass certificate verification or hard-code passwords in source code to work around errors.

## 11. Common Error Reference Table

| Symptom | Where to Check First | Resolution |
| --- | --- | --- |
| Host `cqlsh 127.0.0.1 9042` fails, while `docker compose exec cassandra cqlsh` succeeds | Port mapping from container to host, host loopback, and firewall | Check `docker compose ps`, `docker compose port`, native listener, and TCP from host. |
| Java in app container using `localhost:9042` fails | App container's network namespace | Use the service name `cassandra:9042` when sharing a Compose network. |
| Host cannot resolve `cassandra` while container can | Docker Compose service DNS only works inside the appropriate network | Host uses the published port or host DNS endpoint; do not use Compose service names outside the network. |
| DNS resolves accurately yet TCP times out | Routing, firewall/ACL, security group, NAT, or unresponsive listener | Test TCP directly from the client to IP:port; cross-check network policies. |
| TCP `9042` opens yet cqlsh cannot connect | TLS, native protocol, auth, server readiness | Compare client/server configs and logs; test cqlsh with matching TLS/credentials. |
| `SSLHandshakeException` | TLS port, CA, truststore, SAN/hostname, TLS protocol | Check the endpoint and encryption configuration on both sides. |
| Java reaches contact point then fails on other nodes | Advertised peer native endpoints are unroutable | Check `broadcast_rpc_address`, metadata/driver logs, NAT, and TCP reachability to each peer. |
| App Pod cannot reach Cassandra Service | Service namespace/DNS, EndpointSlices, Pod readiness, NetworkPolicy | Test DNS and TCP from the app Pod; compare ingress/egress policies and labels. |
| `nodetool status` shows a node down while cqlsh works on one node | Internode/gossip issue | Check port 7000 between nodes, internode TLS, gossip/logs, and replication. |
| `SELECT` query returns `Unauthorized` | CQL roles/grants | Check keyspace/table permissions; this is not a DNS error. |
| `ReadTimeout` / `WriteTimeout` after connecting successfully | Replicas, CL, load, internode network, compaction | Check RF/consistency and logs/metrics; do not immediately blame DNS or 9042. |
| CQL rejected due to unsupported filter condition | Table/partition key design | Run `DESCRIBE TABLE`, pick a query-aligned table; do not fix via firewall. |

## 12. Self-Practice Exercises

1. Trace the path when `cqlsh` runs on the **host** to Cassandra in Docker Compose with `ports: ["127.0.0.1:9042:9042"]`. Specify both the host port and the container port.
2. When Java runs in the `app` service on the same Compose network, explain why `127.0.0.1:9042` is wrong and `cassandra:9042` is right.
3. Run `getent hosts` or `Resolve-DnsName` from the exact client environment. State which IP the hostname returns and why a test on the host can differ from a container.
4. Use `nc -vz` or `Test-NetConnection` to test TCP 9042. Explain why TCP success is insufficient to conclude TLS, auth, and CQL work properly.
5. A Java Driver connects to `db-gateway.example.internal:9042` but cannot reach peer `172.18.0.5:9042`. Identify the cause, how to verify advertised peers, and an appropriate networking solution.
6. Compare firewall requirements for application → Cassandra native (`9042`) and Cassandra node ↔ node (`7000`). Why should `7199` not be opened to applications?
7. On Kubernetes, explain the difference between `localhost` across two Pods, a Service DNS name, and a Pod IP. List three Kubernetes objects to inspect when an app Pod cannot connect.
8. Run the CQL lab in Section 9, then read via the Java Driver. Set `CASSANDRA_HOST` according to where it runs and confirm the real datacenter name.
9. Suppose TCP 9042 from Java succeeds but `LOCAL_QUORUM` hits `ReadTimeout`: outline the inspection order for RF, replica health, internode, load, and consistency.

**Completion criteria:** accurately identify connection source/destination, choose valid hostnames per network namespace, distinguish service DNS from host published ports, verify DNS/TCP/TLS/CQL sequentially, understand peer discovery, and separate client network faults from internode/replication errors.

## References

- [Apache Cassandra — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): native transport, `rpc_address`, `broadcast_rpc_address`, `listen_address`, ports, and TLS.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): coordinator, nodes, cluster, replicas, and gossip.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): CQL connection via native protocol and session checks.
- [Docker Docs — Networking in Compose](https://docs.docker.com/compose/how-tos/networking/): service DNS, container networking, host ports, and container ports.
- [Kubernetes — DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/): Service names and cluster resolution.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): ingress/egress policies between Pods and Services.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): contact points, local datacenter, topology, and sessions.
