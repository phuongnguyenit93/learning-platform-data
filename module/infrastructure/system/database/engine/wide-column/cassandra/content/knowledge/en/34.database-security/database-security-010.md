# Network Binding, Firewalls, and Separating Application vs. Sync Traffic

## Objectives and Context

Apache Cassandra is a distributed **wide-column** database. An application sends a CQL statement to a **coordinator**; the coordinator communicates with **replicas** determined by partition key, token, and replication strategy. Nodes also exchange gossip, mutations, read requests, streaming, and repair. Consequently, a bad network configuration can prevent applications from connecting, mark nodes `DN`, stall cross-datacenter convergence, or expose an administrative service to the Internet.

This lesson belongs to the **Security** chapter of module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Its focus is **network binding**, **firewall/segmentation**, and **separating application access paths from inter-node communication paths**. It connects partition keys, CQL, read/write consistency levels, per-DC replication, compaction, repair, troubleshooting, and the Java Driver.

After this lesson, you will be able to:

1. Distinguish **listening addresses** (`listen_address`, `rpc_address`) from **advertised addresses** (`broadcast_address`, `broadcast_rpc_address`) and identify the risks of misusing either.
2. Separate the **client → CQL native transport** path, the **node ↔ node** path for gossip/replication/streaming, and the **management/observability** path.
3. Design an **allowlist matrix by source, destination, port, and purpose**, instead of opening all Cassandra ports to all networks.
4. Understand the protection boundaries of **firewalls**, **TLS**, **authentication/authorization**, and privilege separation, rather than treating any single layer as sufficient.
5. Diagnose scenarios where clients can connect yet replicas cannot sync, or where nodes are `UN` yet apps cannot reach CQL.
6. Practice inspecting ports, topology, CQL, and the Java Driver in a lab, recording results safely and maintaining a rollback plan when altering network policies.

> **Warning:** changing `listen_address`, `broadcast_address`, or blocking internode ports can partition the cluster and cause unavailability. Perform intentional firewall fault drills only in **labs/staging authorized for fault injection**. In production, apply changes through an approved process, keep an independent management path open, and roll out by node/rack/DC—never flush firewall rules or lock out SSH on a host you are administering remotely.

## 1. Cassandra's Three Communication Planes

Not all traffic reaching a Cassandra node is a single "database port."

| Plane | Who Connects to Whom? | Purpose | Common TCP Ports |
| --- | --- | --- | --- |
| **Application / CQL native transport** | Java Driver, `cqlsh`, authorized services → Cassandra coordinator | Authentication, CQL requests/responses, client routing | `9042` default; custom port if configured |
| **Internode / replication** | Cassandra node ↔ Cassandra node | Gossip, messaging, mutation/read requests, streaming/repair across replicas | `7000` common; `7001` may appear in legacy TLS configs or migrations |
| **Management / monitoring** | Authorized bastion/automation → JMX or admin agent | `nodetool`, health checks, metrics, troubleshooting | JMX commonly `7199`; exporters/agents may use separate ports |

**This is an orientation table, not a mandatory port list for every release.** Cassandra 4.x/5.x, internode TLS configurations, vendor distributions, containers/Kubernetes, and custom ports can all vary. Always observe **actual listeners**, `cassandra.yaml`, and version-specific docs before writing firewall rules.

Specifically:

- `9042` is the **CQL native transport** path, **not a gossip or streaming port**.
- `7000` typically serves **node-to-node** traffic; there is no reason to open it to all Java applications.
- `7001` **should not be opened blindly by default**. Whether a separate internode TLS port is used depends on config and version; newer versions can handle TLS differently from the old "7000 plaintext / 7001 TLS" model in legacy docs.
- `7199` belongs to **JMX/management**, not application ports. In some setups it listens only locally; enabling remote JMX requires dedicated authentication/TLS/tunneling policies and may require additional RMI ports.
- Port `9160` belongs to **legacy Thrift**, not modern Cassandra's CQL port; do not open it based on outdated checklists.

### Two-Datacenter Example Model

Suppose `dc_a` and `dc_b` belong to **one cluster**, with three nodes per DC; applications A and B sit in separate subnets.

~~~mermaid
flowchart LR
    A["Apps in dc_a"] -->|"CQL TLS :9042"| CA["Cassandra nodes dc_a"]
    B["Apps in dc_b"] -->|"CQL TLS :9042"| CB["Cassandra nodes dc_b"]
    CA <-->|"Internode messaging / streaming"| CB
    OPS["Admin bastion"] -. "JMX / ops over restricted channel" .-> CA
    OPS -.-> CB
    MON["Authorized monitoring"] -. "Metrics over appropriate channel" .-> CA
    MON -.-> CB
~~~

This diagram shows **logical flows only**: in reality, every node in the cluster needs appropriate internode connectivity to peers per topology, not just a single pair A/B. If a firewall allows A1 ↔ B1 while blocking remaining nodes, gossip/streaming may malfunction.

## 2. Bind Addresses vs. Advertised Addresses

**Bind/listen addresses** determine which network interfaces on **that machine** the Cassandra process opens sockets on. **Broadcast/advertised addresses** are the addresses a node announces to peers or clients to reach it. The two may match on simple hosts, yet often differ in multi-NIC, NAT, or container environments.

### Common Fields in `cassandra.yaml`

| Setting | Role | Common Mistake |
| --- | --- | --- |
| `listen_address` | Node IP to listen for **internode** traffic | Binding an IP not on a host NIC or confusing public/LB IPs |
| `listen_interface` | Interface selector for internode in supporting configs | Conflicting with simultaneous `listen_address` |
| `broadcast_address` | **Advertised internode** address for other nodes to reach | Advertising `127.0.0.1`, unroutable IPs, or one-way NAT IPs |
| `rpc_address` | Bind address for **client/native CQL** service (`rpc` name is historical) | Thinking `rpc_address` only controls Thrift, or binding `0.0.0.0` without firewalls |
| `rpc_interface` | Client interface selector in supporting versions/configs | Confusing it with the internode path |
| `broadcast_rpc_address` | **Advertised client** address in topology metadata | Advertising an address the Java Driver cannot route to |
| `native_transport_port` | CQL native transport port, typically 9042 | Opening the port without TLS/auth or firewalling the wrong subnet |

In many Cassandra releases, **`listen_address` cannot be set to `0.0.0.0`**: a node needs a routable internode endpoint identity. Conversely, `rpc_address: 0.0.0.0` can bind all interfaces when necessary, provided **`broadcast_rpc_address` is set to a specific, reachable address** alongside strict firewalls; never assume it is a safe default.

### Single-Node Lab Configuration Example

~~~yaml
# cassandra.yaml - ILLUSTRATIVE SNIPPET, NOT A COMPLETE FILE
# Node cass-a1 has private IP 10.20.10.11; apps arrive on the private network.
listen_address: 10.20.10.11
broadcast_address: 10.20.10.11
rpc_address: 10.20.10.11
broadcast_rpc_address: 10.20.10.11
native_transport_port: 9042
~~~

When using **two network interfaces**, such as internode `10.20.10.11` and CQL `10.30.10.11`, bind/advertise appropriately per network design and version:

~~~yaml
# NETWORK MODEL ONLY WHEN BOTH IPS BELONG TO THE NODE AND ARE ROUTABLE.
listen_address: 10.20.10.11
broadcast_address: 10.20.10.11
rpc_address: 10.30.10.11
broadcast_rpc_address: 10.30.10.11
native_transport_port: 9042
~~~

**Never copy IPs verbatim.** Both `listen_address` and `rpc_address` must match real interfaces and container/host architecture. `broadcast_*` must be endpoints **consumers can actually connect to**, not merely IPs pingable from localhost.

### Why Wrong Broadcast Addresses Cause Confusing Failures

The Java Driver may connect to an initial contact point and then discover other nodes through metadata. If the cluster advertises a `broadcast_rpc_address` unreachable from the application subnet, the driver can report nodes unavailable, uneven routing, or slow connections even while the contact point answers.

Likewise, if an internode `broadcast_address` points to an IP unreachable from another DC, peers cannot gossip/stream/repair. When nodes sit behind NAT, overlay networks, or L4 proxies, **design bind/broadcast settings around real bidirectional paths**—never "fix" it by throwing all ports open publicly.

## 3. Zone-Based Separation of App, Internode, and Admin Flows

Traffic separation means **defining precisely who needs to talk to which service**, then enforcing it at security groups/firewalls/network policies and on the host itself.

Example network zones in a **lab**:

- **Cassandra `dc_a`:** `10.20.10.0/24`.
- **Cassandra `dc_b`:** `10.20.20.0/24`.
- **Application `dc_a`:** `10.30.10.0/24`.
- **Application `dc_b`:** `10.30.20.0/24`.
- **Bastion/automation:** `10.40.0.0/24`.

These CIDRs are **fictional addresses for this lesson only**, not pre-allocated organizational designs.

### Baseline Policy Matrix

| Source | Destination | Port / Service | Action |
| --- | --- | --- | --- |
| App `dc_a` | Cassandra nodes `dc_a` | CQL TCP 9042 | **ALLOW** per subnet/service identity; require TLS/auth |
| App `dc_b` | Cassandra nodes `dc_b` | CQL TCP 9042 | **ALLOW** similarly, matching local DC |
| Cassandra node `dc_a` | Peers in `dc_a` and `dc_b` | Configured internode TCP port (e.g., 7000) | **Scoped ALLOW** bidirectionally, including cross-DC |
| Cassandra node `dc_b` | Peers in `dc_a` and `dc_b` | Configured internode port | **Scoped ALLOW** bidirectionally |
| Cassandra peer | Cassandra peer | Separate internode TLS port, **if actually used** | Allow only per verified config/version; never blindly open 7001 |
| Trusted bastion/automation | Node management listener | Configured JMX/agent | **Narrow ALLOW**; prefer tunnel, auth, and encryption |
| Authorized monitoring | Exporter/metrics endpoint | Actual exporter port | **Narrow ALLOW**; never expose dashboards/metrics publicly |
| Regular applications | Internode/JMX | 7000/7001/7199 | **DENY** without approved justification |
| Public Internet | CQL/internode/JMX | 9042/7000/7001/7199 | **DENY** by default |

**Stateful firewalls** typically allow return traffic for established connections automatically; **stateless ACLs** may also need return rules and ephemeral ports. Verify platform behavior rather than assuming all firewalls behave alike.

### Pseudopolicy for Discussion—DO NOT Run as Firewall Commands

~~~text
# PSEUDOPOLICY, not nftables/iptables/Cloud SG syntax
ALLOW app_dc_a -> cassandra_dc_a TCP/9042
ALLOW app_dc_b -> cassandra_dc_b TCP/9042
ALLOW cassandra_dc_a <-> cassandra_dc_a TCP/<internode_configured>
ALLOW cassandra_dc_b <-> cassandra_dc_b TCP/<internode_configured>
ALLOW cassandra_dc_a <-> cassandra_dc_b TCP/<internode_configured>
ALLOW ops_bastion -> management_endpoints TCP/<restricted_management_ports>
ALLOW authorized_monitoring -> metric_exporters TCP/<configured_exporter_ports>
DENY  internet -> cassandra_nodes TCP/<all_database_and_management_ports>
DENY  ordinary_app -> internode_or_JMX
~~~

**Crucial:** in a multi-DC design, both internode groups must communicate as required **for one cluster**. Just because applications read/write only in their local DC **does not mean** you can block cross-DC internode traffic and still expect replication.

## 4. Gossip, Streaming, Repair, and Why "Sync Flows" Cannot Be Blocked

Cassandra uses internode communication for many functions:

- **Gossip/membership:** exchanging node states, topology, failure detection, and routing metadata.
- **Read/write messaging:** coordinators sending mutations or read/digest requests to target replicas per RF/CL.
- **Streaming:** transferring SSTables/ranges during bootstrap, replace, decommission, or repair.
- **Hints/repair:** mechanisms helping replicas that missed mutations catch up, depending on version and data state.

Streaming cannot be dismissed as an "optional background service" and blocked arbitrarily. A rule blocking internode links breaks gossip, severs streaming, fails repairs, and stops replicas from receiving mutations. Application-level symptoms sometimes **appear later** than the network fault because `LOCAL_QUORUM` can still gather ACKs within the local DC.

### Example: Losing Connectivity Between Two DCs

Suppose `NetworkTopologyStrategy` sets `dc_a:3` and `dc_b:3`. An application writes in `dc_a` at `LOCAL_QUORUM`:

~~~text
dc_a: A1 ACK + A2 ACK -> write can succeed at LOCAL_QUORUM
dc_b: inter-DC blocked -> may not have received the mutation yet
~~~

Write success **only confirms enough local replicas** per CL; it **does not guarantee** the write reached `dc_b`. If traffic fails over to `dc_b` immediately afterward, reads may return stale versions. If a replica misses a `DELETE` for too long, evaluate tombstones and `gc_grace_seconds` before reconnecting to avoid **zombie data**.

~~~mermaid
sequenceDiagram
    participant App as Client dc_a
    participant A as Coordinator dc_a
    participant LA as Local replica dc_a
    participant B as Remote replica dc_b
    App->>A: WRITE LOCAL_QUORUM
    A->>LA: Mutation to local replicas
    A--xB: Mutation/replication blocked on WAN
    LA-->>A: 2/3 local ACKs met
    A-->>App: WRITE success
    Note over B: May miss data until sync path recovers
~~~

**Never check "is cross-DC connectivity healthy" with a single `SELECT` at local quorum.** Inspect internode links, per-DC node states, streaming/hints/repairs, and reconcile ACKed markers when appropriate.

### Dedicated Networks and Isolation Levels

A dedicated internode network can shrink the attack surface and manage bandwidth, provided you verify:

- Bidirectional routing exists between every pair of communicating nodes/replicas?
- Advertised DNS/IPs resolve and route from **all relevant DCs**?
- Internode TLS matches version, cert trust, and rotation?
- QoS/bandwidth caps do not choke streaming/repair during peak load?
- Ingress/egress rules apply symmetrically, even across node reboots and IP changes?
- A separate admin path exists to investigate if CQL or internode connectivity breaks?

## 5. Firewalls Do Not Replace TLS, Authentication, and Authorization

A rule `ALLOW app_subnet → TCP/9042` only checks network location/identity where supported; it **has no idea whether that CQL account should read sensitive data**. Defense in depth:

| Layer | Responsibility | What It Cannot Replace |
| --- | --- | --- |
| Network segmentation/firewalls | Reduce which hosts can reach TCP endpoints | Does not encrypt bytes; does not grant CQL permissions |
| **Client-to-node TLS** | Secures CQL transit, validates server certificates | Does not decide which tables a role may `SELECT` |
| **Internode TLS** | Protects communication between nodes/replicas | Does not validate node legitimacy if certs are over-issued |
| Authentication | Identifies connecting services/users | Does not enforce per-keyspace/table permissions |
| Authorization | Allows or denies operations by role/permission | Does not protect payloads in transit if TLS is off |
| Host/secret security | Protects config files, private keys, credentials, filesystems | Does not replace retention/backups or incident response |
| Auditing/monitoring | Detects anomalous requests, policy changes, or TLS errors | Does not block an already-permitted connection by itself |

### TLS for CQL Clients

In Cassandra versions with `client_encryption_options`, TLS must be configured consistently on both server and driver. When policy mandates **strict TLS**, never let clients fall back to plaintext if handshakes fail.

~~~yaml
# cassandra.yaml - REFERENCE SNIPPET ONLY
# Subkey names/formats may vary across versions.
client_encryption_options:
    enabled: true
    optional: false
    # keystore / truststore / client_auth per PKI and version
~~~

`optional: false` illustrates disallowing plaintext fallback in versions supporting that flag. Never put keystore/truststore passwords in public docs or commit them to Git. Servers need matching certificates/keys, and clients need trust anchors, hostname/SAN validation, and rotation policies.

### TLS Between Nodes

~~~yaml
# cassandra.yaml - CONCEPTUAL EXAMPLE, does not replace a TLS migration workflow
server_encryption_options:
    internode_encryption: all
    # keystore/truststore, client_auth, cipher protocols per version
~~~

Options for `internode_encryption` (such as `none`, `dc`, `rack`, `all`) and certificate-validation mechanics depend on version. **Transitioning from plaintext to TLS requires a compatibility plan during rolling deployment**: if A demands TLS while B only speaks plaintext, nodes cannot talk. Never change `internode_encryption` on all nodes simultaneously without a rollback plan.

### CQL Authentication and Authorization

In deployments requiring security, evaluate `PasswordAuthenticator` or a supported auth mechanism paired with an appropriate authorizer and role permissions. Application roles should hold rights only on **required keyspaces/tables**, never a shared superuser account. Avoid passing passwords in `cqlsh -p ...` or URLs/CLI args where environments expose process lists and shell history.

**Whether TLS succeeded** and **whether the CQL role is authorized** are two independent checks. A passing TCP connection or TLS handshake followed by `Unauthorized` on a query may mean **authorization is working properly**, not a reason to widen firewalls.

## 6. Protecting JMX, `nodetool`, Metrics, and Backup Paths

`nodetool` usually communicates with nodes via **JMX**, not native CQL `9042`. Therefore:

- Bind JMX only to loopback/bastion/approved management planes whenever possible.
- If **remote JMX** is unavoidable, enforce authentication, TLS/tunneling, CIDR limits, and runtime-specific RMI/endpoint protection.
- Monitoring agents/exporters must have their own allowlisted sources; never expose metrics ports publicly just because they do not serve raw CQL data.
- Operations like `nodetool flush`, `snapshot`, `repair`, and `decommission` carry different impacts; scope execution rights in OS/automation per duty and audit them.

**Never grant business applications JMX/SSH access to Cassandra nodes** just because they need CQL access. The Java Driver speaks native transport. Allowing a frontend service to send management commands to nodes drastically expands the attack surface.

Backups need their own zone too: nodes or backup agents can read snapshots and upload to object storage over encrypted channels, without opening the object bucket to every app pod. KMS, immutable retention, separated read/write/delete rights, and restore drills remain essential even after network segmentation.

## 7. Inspecting Network State Without Modifying Firewalls

Before editing configurations, capture current state from **exact nodes and client subnets**. The commands below are observational—they do not open or close ports.

### 7.1. On a Cassandra Node

~~~bash
# Linux: verify node IPs/interfaces.
ip addr show

# Common TCP listeners; check actual permissions.
ss -lntp

# If using nftables:
sudo nft list ruleset

# If using iptables:
sudo iptables -S

# Cluster status; nodetool requires an appropriate admin/JMX channel.
nodetool status
nodetool netstats
~~~

An OS does not necessarily have both `nft` and `iptables`; use the platform's native toolset. Pay attention to bound addresses shown:

~~~text
10.20.10.11:7000  -> internode listener on private interface
10.30.10.11:9042  -> CQL listener on private app interface
127.0.0.1:7199   -> local-only JMX (when matching actual config)
0.0.0.0:9042     -> CQL listener on all IPv4 interfaces (must audit firewall)
~~~

This is **illustrative output**, not a snapshot of a real node. `ss` proves sockets are listening, yet **does not prove** firewalls allow remote sources, certificates are valid, or replicas have converged.

### 7.2. From an Authorized App Client

~~~bash
# TCP reachability check only; authorized lab host/IP.
nc -vz 10.30.10.11 9042
~~~

If CQL uses TLS:

~~~bash
# Test handshake and inspect server certificate; requires matching PKI/trust.
openssl s_client -connect cass-a1.internal:9042 \
  -servername cass-a1.internal
~~~

A successful `nc` only shows TCP connectivity can be established; it does **not** prove CQL handshake, authentication, authorization, latency, or consistency. `openssl s_client` prints the chain/certificate, yet is **not enough** to conclude all Java Driver PKI and hostname validation are configured properly—verify the verification status, trust anchors, and SAN entries in practice.

If the diagnostic machine runs Windows or a minimal container image, use built-in equivalents rather than installing ad-hoc tools in production.

### 7.3. Verifying Real CQL

From a `cqlsh` session configured with **TLS + secure credentials** per policy:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` describes **the node answering that query**, not the entire cluster. If it succeeds, the CQL/auth/permission path for that statement works; it does not prove all internode links or replica data have converged.

~~~bash
# On an authorized admin node, inspect membership from multiple viewpoints.
nodetool status
nodetool describecluster
nodetool netstats
~~~

**A cluster can show all nodes `UN` at a moment in time while still suffering streaming/hint errors or cross-DC replication lag.** Combine metrics, logs, and data reconciliation before declaring a network incident resolved.

## 8. Two-DC Lab: Verifying Path Separation Without Losing Data

### 8.1. Preparation and Safety Criteria

This illustrative lab has `dc_a` and `dc_b`, three nodes per DC, using `NetworkTopologyStrategy` with **RF=3 in each DC**. If your environment has only one DC, practice local bind/port/ACL checks without **interpreting them as cross-DC replication tests**.

Before running the drill:

1. Record `nodetool status` and `describecluster`; required nodes must be `UN`.
2. Verify client local DC, certs, and CQL permissions; never use superuser for the lab app.
3. Maintain an external manifest of ACKed markers **outside the cluster**.
4. Ensure policy rollback access via a management plane **independent of the port under test**.
5. Run **connectivity observation** first; test inter-DC blocking only in a lab with a verified recovery plan.

### 8.2. Create Keyspace and Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS network_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_a': 3,
    'dc_b': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS network_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    origin_dc text,
    created_at timestamp,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` is the **partition key** and `event_id` is the clustering key; the queries below read a single small partition. If the keyspace already exists, `IF NOT EXISTS` **does not alter prior RF**. Verify:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'network_lab';
~~~

Names `dc_a`/`dc_b` must match topology/snitch output rather than guessing from hostnames or geography. In this six-node RF3+3 lab, each partition should hold three replicas per DC.

### 8.3. Write and Verify Baseline

Connect `cqlsh` to **a coordinator in `dc_a`**. In `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO network_lab.events_by_run
    (run_id, event_id, marker, origin_dc, created_at)
VALUES (
    'net-demo-01',
    11111111-1111-4111-8111-111111111111,
    'BASELINE-A', 'dc_a', '2026-11-21T09:00:00Z'
);

SELECT event_id, marker, origin_dc
FROM network_lab.events_by_run
WHERE run_id = 'net-demo-01';
~~~

Record **ACK_LOCAL_QUORUM** in the manifest only when the client genuinely receives success; `WriteTimeout` yields **UNKNOWN_WRITE**, not proof that the mutation missed all replicas. When checking from `dc_b` at `LOCAL_QUORUM`, `BASELINE-A` appears after replication, though **an ACK in `dc_a` never waits for `dc_b` quorum**.

### 8.4. Traffic Verification Matrix

| Test | Source → Destination | Expected When Policy Is Right | If Failed, Check |
| --- | --- | --- | --- |
| CQL A | App A → coordinator `dc_a` TCP/9042 | TLS/auth/CQL succeed | `rpc_address`, `broadcast_rpc_address`, ACL, cert/SAN, role |
| CQL B | App B → coordinator `dc_b` TCP/9042 | TLS/auth/CQL succeed | Driver local DC, advertised endpoint, policy |
| App → internode | App A/B → Cassandra TCP/7000 | **Denied** per policy | If open, an overly broad rule exists |
| App → JMX | App A/B → JMX | **Denied** per policy | JMX bind/remote, firewall |
| Intra-DC internode | Node A1 → A2/A3, B1 → B2/B3 | Right port/config, peers healthy | Bind/broadcast, internode TLS, bidirectional ACLs |
| Inter-DC internode | Node `dc_a` ↔ node `dc_b` | Traffic flows for replication/repair | WAN, VPN, DNS, routing, TLS, and ACLs |
| Admin | Bastion → granted management channel | Only approved identities enter | Tunnels, JMX/RMI/TLS, bastion policy |

**Never run `nc` from an app pod to probe JMX with production credentials.** Denial tests only verify the connection is blocked as designed; avoid brute-force auth attempts or network scanning outside permitted lab scope.

### 8.5. Controlled Isolation Experiments in the Lab

Rather than giving risky `iptables DROP` commands that might be miscopied, use the **lab's policy/network emulator** across three scenarios, each with a verified revert step:

**Scenario A — Block CQL only from an app to one node:**

- Do not block internode and do not stop Cassandra.
- The Java Driver can route around to other nodes if topology/policy permits; a single-endpoint client will hit connection errors.
- Peer gossip/streaming stays healthy; **an app `ConnectTimeout` does not automatically equal replica loss**.

**Scenario B — Block internode paths from one node to peers:**

- Peers may mark the node down; mutations/repairs/streaming suffer.
- With RF3 in one DC, if two replicas remain healthy, `LOCAL_QUORUM` can continue serving some requests; `ALL` loses availability.
- **Abort immediately** if the lab loses too many replicas or a second fault appears.

**Scenario C — Block internode between `dc_a` and `dc_b` while keeping local app paths open:**

- Each DC's `LOCAL_QUORUM` can still serve against its healthy local replicas.
- Cross-DC replication stalls; clients failing over risk missing mutations ACKed in the source DC.
- Conclude only after **restoring ACLs**, verifying cluster stability, and reconciling markers/running repair per procedure—never just waiting for `nodetool status` to show `UN`.

Record block/unblock timestamps, rule IDs, firewall version, nodes/ports, CL, trace/request IDs, and **read/write errors**. When timeouts occur, never collapse them into "MISSING" or "data lost."

## 9. Java Driver 4.x: Local DC, TLS, and Real Coordinators

The Java Driver needs **reachable addresses**, the **right local datacenter**, and valid TLS/certificate settings. Contact points bootstrap cluster discovery; once topology is known, the driver connects to nodes advertised in metadata. Protecting only one contact-point address is therefore **insufficient**.

The Java Driver 4.x example below uses a JVM truststore or securely supplied `SSLContext` from deployment config. **Never bypass certificate validation** or hardcode usernames/passwords in code.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.metadata.Node;

import javax.net.ssl.SSLContext;
import java.net.InetSocketAddress;
import java.util.UUID;

public final class SecureCassandraProbe {
    public static CqlSession connectLab(SSLContext trustConfiguredTls)
            throws Exception {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.30.10.11", 9042))
            .addContactPoint(new InetSocketAddress("10.30.10.12", 9042))
            .withLocalDatacenter("dc_a")
            .withSslContext(trustConfiguredTls)
            // Authentication/hostname validation configured per PKI
            // and driver deployment; never hardcode secrets here.
            .build();
    }

    public static void check(CqlSession session,
                             String runId, UUID eventId) {
        PreparedStatement query = session.prepare(
            "SELECT marker FROM network_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");

        ResultSet result = session.execute(
            query.bind(runId, eventId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotence(true));

        ExecutionInfo info = result.getExecutionInfo();
        Node coordinator = info.getCoordinator();
        System.out.printf("coordinator=%s%n",
            coordinator == null
                ? "unknown"
                : coordinator.getEndPoint());
        var row = result.one();
        System.out.println(row == null
            ? "QUERY_SUCCEEDED_NO_ROW"
            : "QUERY_SUCCEEDED_WITH_ROW");
    }
}
~~~

**Required external TLS protections:** the server must enable client encryption, issue certs with SANs matching addresses/hostnames used by the driver, trust anchors must be trusted, driver policy must enforce **hostname verification**, and CQL users/roles must hold least privilege. The snippet shows only session/query structure, **not a complete production setup**.

If TLS handshakes, authentication, or CQL fail, record **CONNECT/TLS/AUTH/READ_ERROR** separately. A `ResultSet` only exists when the query succeeds; an absent row is `MISSING_AT_SELECTED_CL` to check against the manifest. Never treat a connection exception as proof of a missing partition.

### When Apps Span Multiple Datacenters

To treat `dc_b` as **local DC** during failover, update session/load-balancing config for `dc_b` and route to valid contact points—never merely swap `host` while leaving `withLocalDatacenter("dc_a")`. That affects both **coordinator routing** and what `LOCAL_QUORUM` means.

Never build logic that automatically fails over all queries to a remote DC on network errors without assessing **RPO, data convergence, write ownership, and fencing**. A CQL query succeeding in a standby DC does not prove the latest writes reached its replicas.

## 10. Monitoring and Troubleshooting Network Issues by Symptom

### Layer 1 — Client Cannot Open TCP/9042

**Signs:** TCP timeouts/refused connections; Java Driver cannot reach contact points.

Inspect `ss -lntp` on nodes, `rpc_address`/`native_transport_port`, host firewalls/SGs/network policies, routing/DNS, and advertised ports. `Connection refused` may indicate the listener is stopped; timeouts may indicate drops/routing, though not exclusively. Never open internode ports to apps to solve CQL failures.

### Layer 2 — TCP Succeeds Yet TLS/Auth Fails

**Signs:** TLS handshake failures, unknown certificates, hostname mismatches, CQL authentication errors, or unauthorized errors.

Check server/client encryption settings, CAs, SANs, cert expirations, system clocks, KMS/secret rotation, and CQL roles. **Never remediate by disabling certificate checks or opening temporary plaintext access to the Internet.**

### Layer 3 — Apps Reach CQL Yet Cluster Shows `DN`/Repair Failures

**Signs:** `nodetool status` lists nodes down, streaming/repair fails, internode TLS errors.

Check `listen_address`/`broadcast_address`, actual internode ports, **bidirectional** peer-to-peer ACLs, inter-DC routes, DNS, MTU, certificates, gossip/failure detector, and node logs. A passing `SELECT` at `LOCAL_ONE` **does not confirm internode health**.

### Layer 4 — All Nodes `UN` Yet Reads Differ Between DCs

**Signs:** write ACKed in DC A yet absent when reading in DC B; incomplete hints/repairs.

Analyze write/read CLs and local DC coordinators, log ACKed markers in an independent manifest, and check cross-DC networking, hints/repairs/streaming. **Do not prematurely assume data loss** while remote DCs lag; likewise, do not casually bring back a node that missed `DELETE`s long ago if zombie data is a risk.

### Quick Diagnostic Table

| Observation | First Hypothesis | Priority Action |
| --- | --- | --- |
| `ss` shows no 9042 | Native transport disabled/wrong bind/startup failure | Check config/logs; do not blindly open SGs |
| 9042 listening yet app sees TCP timeout | ACL/routing/DNS/NAT | Check source/dest, ingress/egress rules |
| TLS cert hostname mismatch | Wrong advertised endpoint or missing SAN | Fix PKI/hostname/advertise; never bypass verification |
| App reaches contact point, other nodes unreachable | `broadcast_rpc_address`, routing discovery | Cross-check metadata endpoints and reachability |
| CQL works, `nodetool` JMX fails | Management plane blocked or JMX auth/config | Use authorized bastion/tunnel; never expose 7199 publicly |
| Node becomes `DN` after firewall rollout | Internode blocked or mismatched TLS config | Roll back rule; verify peer communication |
| Repair/streaming fails across DCs | Inter-DC network, certs, bandwidth | Verify ports/configs and repair scope |
| `LOCAL_QUORUM` read in A fresh, B stale | Replication lag or replica divergence | Reconcile, check hints/repairs; never lower CL to hide bugs |
| CPU/network spikes after rule change | Retry storms, unintended traffic, or compaction | Rate limit, audit traffic sources, check per-node metrics |

## 11. Runbook for Safe Firewall/Binding Changes

Production procedures require **before-and-after evidence**; a firewall API returning success does not prove apps and replication still work properly.

### Before Changing

1. **Inventory:** list nodes/DCs/racks, private/public IPs, NICs, advertised endpoints, server/client TLS, JMX/exporters, and actual ports.
2. **Dependency map:** confirm which apps use CQL, which nodes speak internode, cross-DC repair/streaming, monitoring, and backups.
3. **Risk:** record RF, application consistency levels, currently down nodes, quorum tolerance for node loss, and full-DC isolation impact.
4. **Verification sources:** metrics, ACKed CQL markers, latency, logs, trace IDs—never merely write "ping succeeded."
5. **Rollback:** record current rule IDs/versions, revert method via an independent management plane, owner, and stop thresholds.
6. **Secrets/PKI:** certificates, CAs, auth, KMS, and hostname verification ready before enforcing mandatory TLS.

### During the Change

- Roll out **by individual node/zone or narrow rules** first; watch gossip, ring, CQL, and internode latency.
- For **bind/broadcast** changes, confirm the new address exists on the NIC, all peers/clients can reach it, and driver discovery does not return bad endpoints.
- For **TLS** changes, follow your version's compatibility/rolling plan so new TLS-only nodes are never stranded from plaintext-only peers.
- If a node goes `DN` or read/write timeouts breach thresholds, **halt rollout and roll back** per plan.
- Avoid running topology changes, heavy repairs, or major compactions concurrently with network changes without justification and resource headroom.

### After the Change

~~~text
CHECK 1: From app subnets, only permitted CQL endpoints are reachable.
CHECK 2: Apps cannot reach internode/JMX endpoints outside policy.
CHECK 3: TLS server certs, hostnames, auth, and CQL permissions pass.
CHECK 4: Driver discovers and picks coordinators in the right local DC.
CHECK 5: nodetool status across nodes/DCs shows no new anomalies.
CHECK 6: Inter-node messaging, hints, and streaming/repair report no errors.
CHECK 7: ACKed markers verified by CL/partition key with separate error logs.
CHECK 8: p95/p99, error rates, and retries stay within thresholds.
CHECK 9: Audit records rule/PKI change owner, timestamp, and rollback ID.
~~~

**Never use a full-table `SELECT COUNT(*)`** to prove Check 7: it is resource-heavy and equal counts do not guarantee identical event IDs. Reconcile exact primary keys/markers against your trusted manifest.

## 12. Threat Model and Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "RF=3 lets us block node-to-node traffic after writes complete." | RF relies on replicas exchanging mutations/repairs; blocking internode causes replica lag, errors, or outages. |
| "`LOCAL_QUORUM` only needs the local DC, so inter-DC can stay blocked." | Local ACKs do not wait for remote, yet cross-DC replication still needs network reachability and convergence. |
| "Setting `rpc_address` to `0.0.0.0` is safe because drivers use passwords." | Binding all NICs widens the attack surface; firewalls, TLS, and least privilege remain essential. |
| "`broadcast_rpc_address` can stay `127.0.0.1` since the contact point connects." | Drivers discover endpoints via metadata; unroutable advertised IPs leave other nodes unreachable. |
| "Opening `7000/7001` to apps makes queries faster." | Those are internode links, not the application CQL API. |
| "Port `7001` is always internode TLS in every Cassandra." | Depends on version/migration; inspect active listeners and configuration. |
| "Firewalls block the Internet, so TLS is unnecessary." | Internal traffic still faces interception, lateral movement, and credential theft. |
| "With TLS enabled, Cassandra permissions aren't needed." | TLS protects the channel; the authorizer governs what roles can do. |
| "`nc` succeeding means the client logged in safely." | TCP reachability does not verify TLS, auth, CQL, or least privilege. |
| "Node `UN` means all data/replicas are in sync." | Membership does not prove mutations, repairs, or read correctness. |
| "JMX has no user data so it can be public." | JMX exposes sensitive observation and admin actions; restrict and authenticate access. |
| "If a network policy change fails, just restart all nodes." | Can worsen outages; inspect rules, bind/advertise, TLS, and execute a controlled rollback first. |

## 13. Hands-On Exercises and Critical-Thinking Questions

**Exercise 1 — Distinguish bind and broadcast.** A node has `listen_address=10.20.10.11` and `broadcast_address=127.0.0.1`. Even if the process listens, why can't peers rely on that address? When a node has two NICs, how should bind/broadcast pairs be chosen?

**Exercise 2 — Firewall matrix.** Given two DCs, two app subnets, and one bastion, build an allowlist for CQL, internode, and management. Specify sources/destinations, ports, directions, deny policies, and how to confirm JMX/7000 are closed to apps.

**Exercise 3 — Client discovery.** Java Driver reaches `cass-a1:9042` yet times out reaching `cass-a2`. On `cass-a2`, `ss` shows a listener on 9042. How do you inspect `broadcast_rpc_address`, metadata, firewalls/routes, and cert SANs?

**Exercise 4 — Cross-DC consistency.** A keyspace sets RF3 in `dc_a` and RF3 in `dc_b`. Clients write in `dc_a` at `LOCAL_QUORUM` right before the WAN link is blocked. Why can ACKs still arrive? When failing over to `dc_b`, what must be verified before accepting new writes?

**Exercise 5 — Error classification.** One app hits `ReadTimeout` on CQL, another hits TLS handshake failure, and `nodetool status` still shows `UN`. Which layers do these symptoms belong to? Why must you never lump all three as "MISSING DATA"?

**Exercise 6 — Internode TLS rollout.** Explain the risk when half the cluster enforces TLS only while the other half speaks plaintext only. Outline a plan covering certs/truststores, compatibility phase, canary, rollback, and gossip/repair checks.

**Exercise 7 — JMX and operational rights.** A team proposes opening `7199` from all Java applications to monitor node status. Design an alternative using a metrics exporter or authenticated bastion, including privilege separation and auditing.

**Exercise 8 — Multi-NIC and containers.** A node advertises a container IP unroutable from the app subnet. Why is a load balancer forwarding to a contact point insufficient for token-aware discovery? Name at least two ways to fix the network/advertisement architecture.

**Exercise 9 — Security regression tests.** Write synthetic post-firewall-rollout checks containing one **permitted** test and one **must-be-denied** test for each of the CQL, internode, and management planes. Explain how to keep tests from touching production data.

**Exercise 10 — Data after network partitions.** A replica misses `DELETE`s while isolated too long, and tombstones risk being purged elsewhere. Why is simply reopening port 7000 unsafe? List steps to inspect `gc_grace_seconds`, repair history, and rebuild/replace options.

## Key Takeaway

**Cassandra network security means cleanly separating three traffic flows: application CQL, internode communication, and management/monitoring.** `listen_address`/`rpc_address` control where the process binds, whereas `broadcast_address`/`broadcast_rpc_address` control which addresses peers and drivers advertise and dial; both must be routable in the right network zones. Firewalls permit only **required source → destination → port paths**, keeping internode links open across replicas/DCs of the same cluster. Combine TLS, authentication, least privilege, restricted JMX, and post-change verification across **topology, driver routing, latency, and ACKed data**. Never treat a single TCP connect or an `UN` node status as proof that a cluster is both secure and converged.
