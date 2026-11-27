# Native Protocol, Application Access Ports, and Protocol Compatibility

## 1. What Role Does the Native Protocol Play in Apache Cassandra?

In the distributed wide-column architecture of **Apache Cassandra**, applications send CQL queries to a node acting as the **coordinator**; this node routes and coordinates replicas based on the partition key, replication factor, and consistency level. The **Cassandra native protocol**, also called the *CQL binary protocol*, is the network protocol used by clients such as `cqlsh` and the **Java Driver** to exchange commands and results with Cassandra.

The native protocol operates over **TCP** connections and transmits binary messages. It supports operations such as session initialization, authentication, CQL execution, prepared statements, batches, paging, and topology/schema change notifications. Clients do not need to implement the protocol themselves: the driver handles connections, message framing, data type conversion, coordinator selection, and many connection errors.

This topic belongs to the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Understanding the protocol layer helps connect CQL lab exercises with cluster architecture, read/write consistency levels, fault tolerance, and real-world Java deployments.

After this lesson, you will be able to:

1. Distinguish **native client-to-node** traffic from **internode communication** and administrative ports.
2. Identify the proper host, port, listening address, broadcast address, and TLS configuration for applications.
3. Describe how the driver connects, negotiates protocol versions, and discovers topology.
4. Practice connecting with cqlsh and the Java Driver, understanding why a query must include an appropriate partition key.
5. Diagnose issues involving network ports, authentication, certificates, routing, driver versions, and native protocol versions.

## 2. Distinguishing CQL, Native Protocol, and Internal Cluster Connections

The following three layers are not synonymous:

| Component | Example | Responsibility |
| --- | --- | --- |
| **CQL language** | `SELECT ... WHERE device_id = ?` | Expressing queries and schema/data changes. |
| **Native binary protocol** | `QUERY`, `PREPARE`, `EXECUTE`, `RESULT` | Carrying queries, parameters, results, errors, and events between the driver/cqlsh and Cassandra. |
| **Internode communication** | Nodes exchanging data with other replicas | Gossip, replication, streaming, and internal cluster coordination. |

In the model below, the application connects directly to the native port of the nodes; nodes communicate with each other over a separate channel. Depending on configuration, **each request may pick a different coordinator**.

~~~mermaid
flowchart LR
    A["Java Application / cqlsh"] -->|"Native TCP: 9042 default"| B["Node A<br/>coordinator for request 1"]
    A -->|"Native TCP: 9042 default"| C["Node B<br/>coordinator for request 2"]
    B <-->|"Internode: dedicated port"| C
    B <-->|"Internode: dedicated port"| D["Node C / replica"]
    C <-->|"Internode: dedicated port"| D
~~~

**Remember:** a client connecting to a node **does not mean the data resides only on that node**. The coordinator receives the request and routes it based on the token/partition key and the keyspace's replicas. The native protocol carries the operation's consistency requirement, while actual guarantees also depend on the replication factor, replica status, and query.

### 2.1. The Native Protocol Is Not HTTP/REST

An open TCP socket on port 9042 does not mean there is an HTTP server. Do not send URLs or JSON directly to port 9042 via a browser or `curl` expecting CQL results. A client must implement the native protocol or use an existing driver/tool.

Any HTTP proxies/APIs deployed internally by an organization (if present) are a **separate layer**; they do not make the Cassandra native protocol itself HTTP.

## 3. Related Ports and Usage Scope

| Default / Common Port | Function | Who Typically Connects? |
| --- | --- | --- |
| **9042/TCP** | **CQL native transport** | cqlsh, Java/Python/Node.js/C# drivers, and other CQL clients. |
| **9142/TCP** | Additional native TLS port **if configured** in supported versions | Clients using TLS on a separate port; not open by default. |
| **7000/TCP** | Standard internode communication | Cassandra nodes. |
| **7001/TCP** | Legacy-style internode TLS port | Nodes, depending on setup; modern versions can encrypt on port 7000. |
| **7199/TCP** | JMX for administrative tools, commonly used by `nodetool` | Authorized operators/operational processes. |
| **9160/TCP** | Historical Thrift API | Relevant only to very old Cassandra systems; **do not use** as a modern CQL endpoint. |

These numbers are common defaults or historical conventions, **not guarantees for every deployment**. Ports can be changed. Cassandra 5.0 marks the separate native TLS port setting `native_transport_port_ssl` as **deprecated**; prioritize checking the running version's configuration and TLS plan on the primary native port.

**Network rule:** applications typically need connectivity to the **native endpoint of every node the driver might choose**, not just the single initial contact point. Internode and JMX ports serve different purposes and should not be exposed indiscriminately to application clients or the Internet.

## 4. Configuring Listening and Broadcast Addresses

Important Cassandra parameters live in `cassandra.yaml`. The snippet below **illustrates property names and relationships**, not a complete deployment configuration:

~~~yaml
# Conceptual example: replace addresses and security settings for your real environment.
start_native_transport: true
native_transport_port: 9042
rpc_address: 0.0.0.0
broadcast_rpc_address: 192.0.2.10
~~~

In this example, `192.0.2.10` is an **illustrative documentation address**, not a deployable node IP. Meaning of the parameters:

- `start_native_transport`: enables or disables the native transport service on the node.
- `native_transport_port`: the port on which native transport accepts TCP connections, default **9042**.
- `rpc_address`: the address/interface to **bind** for the native server listener. Despite "rpc" in the name, this parameter applies to native transport in modern Cassandra.
- `broadcast_rpc_address`: the address the node **advertises to drivers and the cluster** so clients know which endpoint they can connect to. It must be an address clients can actually route to.

If `rpc_address: 0.0.0.0` is set (listening on all IPv4 interfaces), `broadcast_rpc_address` must be configured to a concrete address and **must not** be `0.0.0.0`. A bind address cannot stand in for a broadcast address: `0.0.0.0` is not a destination remote clients can use.

Do not confuse `rpc_address`/`broadcast_rpc_address` with `listen_address`/`broadcast_address` for **internode communication**. A cluster may use a private network for nodes to talk to one another and a separate network for applications to send native requests.

### 4.1. Why Can cqlsh Connect While the Java Driver Still Fails?

Drivers typically start with one or more **contact points**, then read cluster metadata and discover other nodes to manage connections and requests. If a node broadcasts a private address unreachable from the client machine (such as a container IP, pod IP, NAT, or another internal network), initial session creation may succeed while connections to discovered peers fail.

Example:

1. The application connects to `db-gateway.example.internal:9042`.
2. The node returns metadata indicating a peer has native endpoint `10.40.0.12:9042`.
3. The application on an external network has no route to `10.40.0.12`, so logs report failing to connect to the peer even though the gateway remains reachable.

The fix is to inspect the **actual addresses the driver discovers**, network routing between clients and nodes, broadcast address configuration, and proxy/address translation mechanisms if the environment requires them. Do not assume placing a TCP load balancer in front of a single node automatically solves full topology discovery for every driver.

## 5. Initial Connection and Native Message Exchange

A native session typically goes through the following stages:

~~~mermaid
sequenceDiagram
    participant App as Java Driver / cqlsh
    participant Node as Cassandra native endpoint
    App->>Node: Open TCP connection (+ TLS if configured)
    opt Query server capabilities
        App->>Node: OPTIONS
        Node-->>App: SUPPORTED
    end
    App->>Node: STARTUP (CQL_VERSION, options)
    alt Authentication required
        Node-->>App: AUTHENTICATE
        App->>Node: AUTH_RESPONSE / auth exchange
        Node-->>App: AUTH_SUCCESS
    else No authentication required
        Node-->>App: READY
    end
    App->>Node: PREPARE or QUERY
    Node-->>App: RESULT (or ERROR)
    App->>Node: EXECUTE with bind values
    Node-->>App: RESULT (or ERROR)
~~~

This diagram shows a **typical flow**; drivers are not required to always send `OPTIONS` before `STARTUP` or always `PREPARE` before `QUERY`. During an active session, the driver can also receive `EVENT` notifications about node/schema changes, send `BATCH`, fetch result pages, and manage multiple connections.

### 5.1. What Data Does the Protocol Carry?

Common message groups:

| Message | Role |
| --- | --- |
| `OPTIONS` / `SUPPORTED` | Discover supported capabilities and connection options. |
| `STARTUP` / `READY` | Start the session with the appropriate CQL version and options. |
| `AUTHENTICATE` / `AUTH_RESPONSE` / `AUTH_SUCCESS` | Perform authentication when requested by the server. |
| `QUERY` | Execute a CQL statement sent directly. |
| `PREPARE` / `EXECUTE` | Prepare a query, then execute it with bind values. |
| `BATCH` | Send a group of CQL operations under Cassandra batch semantics. |
| `RESULT` / `ERROR` | Return data, metadata, statement results, or errors. |
| `REGISTER` / `EVENT` | Client registers for and receives topology/schema/status change notifications. |

The native protocol allows multiple concurrent in-flight requests via stream/request identifiers. **It is not a strictly sequential connection that can only send one SQL statement and wait.** The driver manages connections, backpressure, timeouts, and concurrency according to its own version and configuration.

### 5.2. Prepared Statements and Protocol-Dependent Paging

When using prepared statements, the driver sends `PREPARE` so the server returns metadata/an ID, then sends `EXECUTE` with bind values. This is the standard approach for repeated parameterized queries; avoid concatenating user input directly into CQL strings.

For large results, the native protocol can return individual **pages** and a **paging state**. Paging state is an opaque binary token tied to the query and protocol details; do not modify it, infer its contents, or reuse it for another query. Specifically, the native protocol specification notes that **v3 and v4 paging states are incompatible with each other**. When switching protocol versions during an upgrade, test pagination continuation/cursor resumption logic carefully.

## 6. Native Protocol Versions and Practical Compatibility Matrix

At least **four "versions"** must be distinguished:

| Version Type | Example | Reflects |
| --- | --- | --- |
| **Cassandra server version** | A Cassandra 4.x or 5.x release | Node/cluster behavior and features. |
| **CQL language version** | CQL 3.x | Query language grammar and semantics. |
| **Native protocol version** | v3, v4, v5 | Binary packet structure and client–server exchange capabilities. |
| **Driver/client version** | Java Driver 4.x, bundled cqlsh | Protocols and features supported by the client library/tool. |

**Do not infer** "Cassandra 5.x ⇒ Java Driver 5.x" or "CQL 3.x ⇒ native protocol v3". They have independent lifecycles. A compatible driver can select a native version supported by both client and server; exact capabilities depend on the driver release, Cassandra release, and cluster configuration.

### 6.1. What Changes Between Native Protocol Versions?

Versions v3, v4, and v5 share the same purpose but differ in capabilities and encodings:

- **v3** is a protocol widely used in older Cassandra systems.
- **v4** adds certain metadata/data types/warnings and changes the encoding of some results, including **a paging state incompatible with v3**.
- **v5** changes framing/negotiation mechanisms and adds features such as prepared result metadata. In some Cassandra releases, v5 may be marked **beta**; verify actual support rather than forcing it on by default.

Do not force a driver to use v5 based solely on the Cassandra version number. When unsure, let a **supported driver negotiate** a common version, then inspect logs/metadata to see which native protocol is in use.

### 6.2. Compatibility Checks Before Upgrading

1. Record the **server version**, **Java Driver version**, and **selected native protocol**, not just CQL syntax.
2. Check the compatibility matrix of your exact driver version against the target Cassandra version.
3. In staging, test session initialization, auth/TLS, metadata discovery, prepared statements, paging, consistency, LWT, and the data types in use.
4. During rolling upgrades where multiple node versions coexist, use a driver configuration supported for the **common protocol version set**; monitor connections to each node.
5. Re-verify prepared statements after schema changes/node restarts as well as previously persisted paging states; applications need appropriate retry and checkpoint policies.

If you encounter errors such as `Unsupported protocol version`, `ProtocolError`, or the server closing the socket immediately during startup, inspect logs on both client and server. Causes may include no shared native version, wrong TLS/port settings, or an outdated driver.

## 7. TLS, Authentication, and Access Control

Native transport can be protected by **TLS** (encrypting client–node connections), **authentication** (identity verification), and **authorization** (CQL permission control). They solve different problems:

| Mechanism | Question Answered |
| --- | --- |
| TLS server authentication | Is the client connecting to the right server, and is data encrypted in transit? |
| Mutual TLS, if configured | Does the server require the client to present a valid certificate? |
| Cassandra authentication | Who is the login account/identity? |
| Authorization | Which keyspaces/tables can that identity `SELECT`, `MODIFY`, or manage schemas on? |

TLS configuration on the Cassandra side lives under `client_encryption_options` and requires actual certificates/keystores/truststores. A deployment may:

- Run TLS on **port 9042 itself**.
- In supported versions/configurations, enable an additional dedicated native TLS port, commonly illustrated as **9142**.
- During a migration window, allow both encrypted and unencrypted connections via the corresponding `optional` setting; this setting must be controlled and removed once migration completes.

**Do not conclude "9042 = no TLS" or "9142 = always TLS".** Only inspecting the configuration and testing the handshake confirms it. Never use "trust all certificates" in production applications; validate the trust chain and host identity according to applicable TLS policy.

Example of connecting cqlsh to a TLS-enabled server (depending on cqlsh version and environment certificate configuration):

~~~bash
# The server must have native TLS enabled on the right port.
cqlsh db.example.internal 9042 --ssl -u student
~~~

The account may need to enter a password via prompt or configure a credentials file protected with proper file permissions. **Avoid placing passwords directly in command-line arguments** or committed scripts. `--ssl` only requests TLS mode; CA/hostname verification follows the active cqlsh configuration.

## 8. Hands-On Port and Endpoint Verification

### 8.1. Check Networking Before Checking CQL

From the **application host**, verify DNS/IP resolution and TCP connectivity:

~~~bash
# Linux/macOS: tests TCP connectivity only, does not send CQL.
nc -vz db.example.internal 9042

# If the endpoint requires TLS: observe the certificate/handshake.
openssl s_client -connect db.example.internal:9042 -servername db.example.internal
~~~

From PowerShell on Windows:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

These tests **confirm only part of the picture**: an open TCP port does not prove that native handshake, auth, schema access, or CQL queries work. `openssl s_client` is valid only when the endpoint actually speaks TLS; against a non-TLS port, a handshake error is expected.

### 8.2. Check Native Transport and the Cluster Itself

From the node or an authorized operations machine:

~~~bash
# Status of the node's native transport service via nodetool/JMX.
nodetool statusbinary

# Status of nodes in the cluster; does not replace statusbinary.
nodetool status
~~~

`nodetool statusbinary` indicates the state of the native transport service on the node; `nodetool status` reports cluster/ring health and does not by itself prove port 9042 is open to the client network. To verify external reachability, always test from the actual application network.

In cqlsh:

~~~bash
cqlsh 127.0.0.1 9042
~~~

~~~sql
SHOW HOST;
SHOW VERSION;

-- Confirm metadata of the connected node.
SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

The `data_center` value will be used to configure the Java Driver's **local datacenter**. A common lab name may be `datacenter1`, but **never assume** this name in a real environment.

### 8.3. CQL Lab over the Native Protocol

The following example is for a **single-node lab only**, to create data for the Java section. Run these CQL statements in cqlsh:

~~~sql
CREATE KEYSPACE IF NOT EXISTS native_protocol_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS native_protocol_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  read_at timestamp,
  temp_c double,
  PRIMARY KEY ((device_id, reading_day), read_at)
) WITH CLUSTERING ORDER BY (read_at DESC);

INSERT INTO native_protocol_lab.readings_by_device_day
  (device_id, reading_day, read_at, temp_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z', 25.1);

INSERT INTO native_protocol_lab.readings_by_device_day
  (device_id, reading_day, read_at, temp_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z', 25.3);

SELECT read_at, temp_c
FROM native_protocol_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Expected result: **2 rows**, with the 01:05 record appearing before 01:00. Here, `(device_id, reading_day)` is the composite partition key; you cannot change the query to `WHERE temp_c > 25` and expect Cassandra to automatically have a matching index. Query-driven table design and partition keys remain central even after the client connects successfully.

`SimpleStrategy` + RF = 1 fits single-node illustration. For multi-node/multi-datacenter clusters, typically use `NetworkTopologyStrategy` and declare RF using the actual datacenter names.

## 9. Java Driver: Connecting and Executing Prepared Queries

The Java example below uses the `CqlSession` API of **Java Driver 4.x**, compatible with driver versions under the `com.datastax.oss.driver.api` package. Add the driver dependency matching your project's Java/Cassandra versions; replace contact points and datacenter with verified environment details.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;

public class CassandraNativeDemo {
    public static void main(String[] args) {
        // datacenter1 is only an example: read data_center from system.local.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT read_at, temp_c " +
                "FROM native_protocol_lab.readings_by_device_day " +
                "WHERE device_id = ? AND reading_day = ?");

            ResultSet rs = session.execute(
                ps.bind("sensor-01", LocalDate.of(2026, 11, 21)));

            for (Row row : rs) {
                System.out.println(
                    row.getInstant("read_at") + " -> " +
                    row.getDouble("temp_c"));
            }
        }
    }
}
~~~

**Path walkthrough:** when `session.execute(...)` is called, the driver encodes the prepared statement and bind values into a native protocol message, chooses a coordinator according to driver policy, receives the result, and converts data into Java types. The driver maintains multiple connections across nodes, so `CqlSession` is a long-lived object typically shared across the application and closed on shutdown.

### 9.1. Multiple Contact Points and Node Discovery

In multi-node systems, provide more than one **contact point** on endpoints reachable by the application and belonging to the right datacenter:

~~~java
CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("db-node-1.internal", 9042))
    .addContactPoint(new InetSocketAddress("db-node-2.internal", 9042))
    .withLocalDatacenter("dc1")
    .build();
~~~

`dc1` here is an example. Contact points are **initial entry points for cluster discovery**, not the exclusive list of nodes the driver can use. The driver fetches metadata and builds its connection pool according to its load-balancing policy, local DC, and topology. Ensure the client can route to the advertised native endpoints.

The snippet above only illustrates session creation; the application must close the session at the appropriate time, typically via `try-with-resources` for short-lived tools or a service shutdown hook.

### 9.2. Security and Session Control

If the server requires authentication, configure an auth provider or credentials via the application's secrets management mechanism. If the server requires TLS, configure an `SSLContext` that trusts the actual CA/certificate in the Java Driver; changing to port 9142 **is not enough** to enable client-side TLS automatically. Avoid hard-coding passwords in source code and avoid disabling hostname/certificate verification just to "make it connect."

In applications handling many requests, configure appropriate request timeouts, consistency, retry policies, and paging, and use prepared statements. These settings live in the driver/statement and **do not depend** on `CONSISTENCY`, `PAGING`, or `TRACING` commands in an external cqlsh session.

## 10. Layer-by-Layer Troubleshooting

When Java or cqlsh cannot connect, do not start by changing the consistency level. Determine whether the failure occurs at **DNS/TCP**, **TLS**, **native handshake**, **authentication**, **metadata discovery**, or **CQL execution**.

| Symptom | Layer to Inspect | Appropriate Resolution |
| --- | --- | --- |
| `Connection refused` to host:9042 | TCP/native listener | Check address, port, `start_native_transport`, `rpc_address`, service status, and firewall. |
| Connection timed out | Network/DNS/routing | Test from the application host itself; check routing to the node and port. |
| `SSLHandshakeException` or handshake failure | TLS | Confirm TLS is enabled on the port, CA/truststore, SAN/hostname, and client config. |
| `AuthenticationException` | Authentication | Check credentials, auth provider, and server configuration. |
| `Unauthorized` on SELECT/CREATE | CQL authorization | Check roles and permissions on keyspaces/tables; this is not a port error. |
| `Unsupported protocol version` / `ProtocolError` | Native protocol | Check protocol support between server and driver; check for wrong port/TLS before forcing a version. |
| Java connects to contact point but misses peers | Discovery/topology | Check `broadcast_rpc_address`, routing to each peer, local DC, NAT/container/proxy. |
| Driver reports no suitable node found | Driver policy/local datacenter | Verify actual `data_center` and ensure contact points belong to the right DC. |
| `Unprepared` or errors after schema change | Prepared statement/schema metadata | Check schema agreement and driver re-prepare handling; do not assume the server always retains its prepared cache. |
| `ReadTimeout` / `WriteTimeout` | Replicas/consistency/processing time | Check RF, CL, node health, network, load, compaction, and logs; errors can happen after a successful handshake. |
| CQL returns missing partition key error | Query design | Check `PRIMARY KEY` and query-driven table model; do not try to fix by changing ports/protocols. |

### 10.1. Minimum Verification Checklist

1. **From the application host:** does the hostname resolve properly and can TCP reach the configured port?
2. **On the node:** does `nodetool statusbinary` report native transport as active, and is the listener bound to the right address and port?
3. **TLS/auth:** do server and client agree on encryption, CA, hostname, and credentials?
4. **CQL:** can `cqlsh` run `SHOW VERSION` and `SELECT ... FROM system.local`?
5. **Driver:** what protocol version do logs show, which addresses are peers discovered at, and what is the local datacenter?
6. **Query:** does the statement include the full partition key, target keyspace, appropriate consistency, and sufficient permissions?

In production environments, avoid enabling logs that dump full bind values or credentials. When investigating latency, combine application metrics, driver metrics, server logs, and selective tracing. **An open TCP port 9042 does not prove Cassandra is ready to serve valid queries.**

## 11. Practice Exercises and Self-Check Questions

1. List the purpose of **9042**, **7000**, and **7199**. Explain why typical Java applications do not need JMX open.
2. Use `Test-NetConnection` or `nc` to test the native port from the client machine. Use cqlsh to check `SHOW HOST` and `SHOW VERSION`. State the difference between "TCP open" and "CQL query succeeds."
3. Run the `native_protocol_lab`, then use the Java Driver to read both results with a prepared statement. Check `data_center` before filling in `withLocalDatacenter`.
4. Suppose a node uses `rpc_address: 0.0.0.0` without setting a valid `broadcast_rpc_address`. Explain why driver topology discovery may fail and how to verify the advertised address.
5. Suppose the server requires TLS on 9042, but cqlsh is run without `--ssl`. Which layer fails and what parameters should be checked?
6. Distinguish **Cassandra server version**, **CQL language version**, **native protocol version**, and **Java Driver version**. Why can't one version be deduced from another?
7. During a rolling upgrade, why can't a paging state obtained over native v3 be arbitrarily reused with v4? Propose how an application should handle older cursors.
8. Suppose the contact point is a public hostname while peers advertise unroutable private addresses. Name at least three checks to pinpoint why connections work intermittently or fail for peers.

**Completion criteria:** you can trace the path application → native endpoint → coordinator/replicas, distinguish the port groups, connect via cqlsh and Java, explain the role of bind/broadcast addresses, and select the right diagnostic layer when encountering protocol or query errors.

## 12. References

- [Apache Cassandra — Cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `start_native_transport`, `native_transport_port`, `rpc_address`, `broadcast_rpc_address`, and `client_encryption_options`.
- [Apache Cassandra — Native Protocol Versions](https://cassandra.apache.org/doc/stable/cassandra/reference/native-protocol.html): messages, negotiation, changes across v3/v4/v5, paging, and error codes.
- [Apache Cassandra — nodetool statusbinary](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/statusbinary.html): checking native transport status.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): query language, schemas, and primary keys.
- [Apache Cassandra Java Driver — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): configuring contact points and local datacenter.
- [Apache Cassandra Java Driver — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html): result paging, paging state, and reuse limitations.
