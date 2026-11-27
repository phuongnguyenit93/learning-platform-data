# Deploying Behind a Proxy, DNS, or Private Network with Correct Connection Addresses

## 1. The Deployment Problem: Runs on the Server, Yet the Application Cannot Connect

A Java service using the **Neo4j Java Driver** may work fine right next to the database, yet fail with connection errors once deployed to a new environment:

- A Java service running in Docker cannot reach `localhost:7687`.
- An application in a private subnet connects to the proxy port yet receives a **routing table** containing unreachable network addresses.
- Neo4j Browser loads on the HTTP port, while the Java Driver fails over Bolt.
- DNS points to a new load balancer, yet the server still advertises the old address.
- TCP opens, yet `neo4j+s://` connections fail because the certificate does not match the hostname.
- After moving to Kubernetes, the driver cannot resolve `*.svc.cluster.local` names from outside the cluster.

This is not merely a question of "did we open the right port?" You need to understand the **entire path** across the application, DNS, proxies, firewalls, ports, and the endpoints advertised by Neo4j.

In the DATABASE_ENGINE_GRAPH_NEO4J module, applications use a property graph to query nodes, relationships, and paths with Cypher, and may use the Java Driver or Spring Data Neo4j. Every query requires **a valid, secure, and routable Bolt connection** before discussing indexes, traversal tuning, or transactions.

> **Lesson objective:** Design and verify a Neo4j deployment behind a proxy, DNS, or private network, ensuring every address **actually used by the Java Driver** is reachable, DNS/TLS align, and access is restricted by security policy.

## 2. Understanding the Layers in a Connection Path

Example deploying a Neo4j server behind a TCP load balancer:

~~~mermaid
flowchart LR
    A["Java / Spring service"] -->|"neo4j+s://graph.example.com:7687"| D["DNS"]
    D --> L["TCP Load Balancer / Proxy"]
    L -->|"private IP:7687"| N["Neo4j Bolt listener"]
    N --> G["Property graph / Cypher"]
~~~

In practice, at least six values must align:

| Value | Illustrative Example | Question to Answer |
|---|---|---|
| Client URI | `neo4j+s://graph.example.com:7687` | Where does the app connect, and how does it use routing/TLS? |
| DNS | `graph.example.com → 203.0.113.20` | What IP does the hostname resolve to from the app's network? |
| Proxy listener | `203.0.113.20:7687` | Does the proxy/LB accept TCP Bolt traffic on that port? |
| Upstream target | `10.20.1.15:7687` | Can the proxy forward traffic to Neo4j? |
| Neo4j listen address | `0.0.0.0:7687` | Is Neo4j bound to the right interface/port in its network namespace? |
| Neo4j advertised address | `graph.example.com:7687` | Does Neo4j advertise a hostname/port the client can actually use? |

**Listen address** is where the Neo4j process accepts incoming connections. **Advertised address** is the address Neo4j hands out so external clients know how to reach the server. The address a client needs may be the proxy hostname, not the internal IP Neo4j actually binds to.

NAT example:

~~~text
Java Application                 Proxy / NAT                     Neo4j
graph.example.com:17687  --->   public:17687  ------------->  10.20.1.15:7687
                                                                      |
                                                        listen 0.0.0.0:7687
                                                        advertise graph.example.com:17687
~~~

Here, **17687** is the port seen by the client, while **7687** is the port Neo4j actually listens on. If Neo4j advertises `10.20.1.15:7687` to an external client, routing can fail because the client has no route to that private IP.

### 2.1. Three Simultaneously Mandatory Conditions

1. **Listener exists:** Neo4j actually opens Bolt where the proxy/application sends traffic.
2. **Network path works:** DNS, routes, firewalls, network policies, NAT, and proxies permit traffic.
3. **Advertised address is valid:** endpoints returned to the driver can be resolved and reached from the application's own environment.

In addition, TLS connections require **certificates matching the hostname and trust chain**, while queries require valid authentication, authorization, and database names.

### 2.2. Two Easily Confused Meanings of `0.0.0.0`

~~~properties
server.bolt.listen_address=0.0.0.0:7687
~~~

This setting allows Neo4j to bind on eligible IPv4 interfaces **within the process's network namespace**. It is not a hostname a remote client can call.

**Do NOT use**:

~~~properties
server.bolt.advertised_address=0.0.0.0:7687
~~~

as an address for routing clients. Wildcard `0.0.0.0` does not identify a concrete network destination to connect to. Use a hostname/IP routable within the client's scope.

## 3. Bolt, HTTP, and HTTPS: Choosing the Right Connector

Neo4j deployments typically use these connectors:

| Connector | Common Port | Purpose |
|---|---:|---|
| **Bolt** | 7687 | Java Driver, Spring Data Neo4j, Cypher Shell, and Cypher clients |
| **HTTP** | 7474 | Web interface/Neo4j Browser and supported HTTP features |
| **HTTPS** | 7473 | Web/HTTP over TLS when enabled and properly configured |
| **Internal cluster connectors** | Version-dependent | Server-to-server traffic, not a public Bolt client port |

Default ports **can be changed**; inspect the active configuration instead of just memorizing 7687/7474/7473.

### 3.1. Reaching Browser Does Not Prove Bolt Is Reachable

A deployment might behave like:

~~~text
GET https://graph-admin.example.com  → loads Neo4j Browser page
Neo4j Java Driver                    → times out connecting over Bolt
~~~

Browser/web and Bolt are **two distinct protocol paths**. Even if the web UI loads, running Cypher may still require a separate Bolt connection. An HTTP-only proxy will not automatically forward the Bolt protocol.

### 3.2. Do Not Substitute an HTTP Reverse Proxy for a Bolt TCP Proxy

The URI below is **not** a way to connect over Bolt via an HTTP path:

~~~text
https://example.com/neo4j/bolt
~~~

The Java Driver requires a valid Bolt endpoint, such as:

~~~text
neo4j+s://graph.example.com:7687
~~~

The proxy must support **TCP forwarding**, or a dedicated gateway configuration supported by your version/software. Declaring an HTTP path-routing rule in a web ingress is insufficient without a TCP/stream proxy for the Bolt port.

## 4. Listen and Advertised Addresses in Neo4j

In Neo4j 5.x deployments using the corresponding setting names, you may see:

~~~properties
server.default_listen_address=0.0.0.0
server.default_advertised_address=graph.internal.example

server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.bolt.advertised_address=graph.internal.example:7687
~~~

Here:

- `server.default_listen_address` sets the default bind interface when connectors inherit it.
- `server.default_advertised_address` sets the default advertised host when not overridden.
- `server.bolt.listen_address` specifies the Bolt endpoint the server binds to.
- `server.bolt.advertised_address` specifies the Bolt endpoint advertised outward.

**Setting names must match your Neo4j version.** Neo4j 4.x documentation may use `dbms.connector.*` keys; never copy legacy settings into another version without checking migration guides and effective settings.

### 4.1. Single-Server Configuration with Internal DNS

~~~properties
server.bolt.enabled=true
server.bolt.listen_address=10.20.1.15:7687
server.bolt.advertised_address=graph.internal.example:7687

server.http.enabled=false
server.https.enabled=false
~~~

This model assumes the Java service runs inside a VPC/VPN able to resolve `graph.internal.example` to the right IP and open TCP 7687 to the server.

Binding to a specific private IP works when the host owns `10.20.1.15` on an interface. If Neo4j runs inside a container or behind NAT, **do not bind to a public IP the container does not own**, or the socket may fail to bind.

### 4.2. When the Proxy Exposes a Different External Port

~~~properties
# Neo4j accepts Bolt on the private network
server.bolt.listen_address=0.0.0.0:7687

# Clients see the port advertised by the proxy/NAT
server.bolt.advertised_address=graph.example.com:17687
~~~

This illustrates a single-server setup, assuming the proxy forwards `graph.example.com:17687` to `Neo4j:7687` and routing/TLS requirements are satisfied.

**Advertised addresses do not create DNS or NAT automatically.** Without a network route from the external hostname to Neo4j, changing settings in `neo4j.conf` fixes nothing.

### 4.3. Check Effective Settings Instead of Only Reading Files

On supported versions with appropriate privileges:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'server.default_listen_address',
  'server.default_advertised_address',
  'server.bolt.enabled',
  'server.bolt.listen_address',
  'server.bolt.advertised_address',
  'server.http.enabled',
  'server.https.enabled'
]
RETURN name, value
ORDER BY name;
~~~

Distinguish **desired configuration** in files/env vars from **effective configuration** active in the running process. Many listener changes require a restart/redeploy per version documentation. Moreover, container/Helm overrides can supersede lines an operator manually edited in a file.

## 5. Choosing the Java Driver URI: Direct vs. Routing

Common Neo4j Java Driver URI schemes:

| Scheme | Deployment Meaning |
|---|---|
| `bolt://host:port` | Direct Bolt connection, without `neo4j` routing discovery |
| `neo4j://host:port` | Uses Neo4j Driver routing/discovery |
| `bolt+s://host:port` | Direct Bolt with TLS and certificate verification via trust chain |
| `neo4j+s://host:port` | Routing with TLS and certificate verification |
| `bolt+ssc://host:port` | Direct Bolt over TLS accepting self-signed certificates |
| `neo4j+ssc://host:port` | Routing over TLS accepting self-signed certificates |

Use `+s` with valid certificates and trust chains for secure environments. `+ssc` can help controlled testing with self-signed certificates, but **must not be treated as a production fix for TLS/certificate errors**.

### 5.1. Direct Connection

~~~text
Java Driver -- bolt+s://graph.example.com:7687 --> TCP proxy --> Neo4j
~~~

This connects directly to the specified endpoint. Appropriate when the app is designed to reach a single Neo4j endpoint through a suitable proxy.

**Do not switch to `bolt://` simply to mask a cluster routing error** if the application needs automatic routing/failover. That alters connection semantics and can degrade availability.

### 5.2. Routing Connection

~~~text
Java Driver
   |
   | neo4j+s://bootstrap.example.com:7687
   v
Bootstrap server / proxy
   |
   | routing discovery
   v
Routing table: [server-a:7687, server-b:7687, server-c:7687]
   |
   v
Driver connects directly to selected endpoint
~~~

Key point: **a reachable bootstrap endpoint is not enough**. Hostnames/ports **returned in the routing table** must also be reachable from where the Java Driver runs. An external client receiving `10.20.1.15:7687` may complete bootstrap and then fail when executing queries.

### 5.3. Do Not Point All Cluster Members at an Arbitrary Shared Hostname

A Neo4j cluster can have multiple members, read/write roles, and endpoints discovered via routing. If all members advertise the same load balancer hostname without proper routing support, the driver may fail to route according to server/role information.

For clusters, use an **exposure/routing architecture supported for your exact version and environment**. Per-member DNS/port design or dedicated gateways must be evaluated holistically rather than mechanically applying single-server configs.

## 6. Designing for the Client's Network Scope

Before deploying, determine **where the client runs** and which network boundaries it crosses.

| Client | Appropriate Endpoint | What Must Be Verified |
|---|---|---|
| Java app on same VM as Neo4j | `localhost:7687` if loopback listener and deployment allow | No separate container network namespaces |
| Java app in same private subnet/VPC | `graph.internal.example:7687` | Private DNS, routes, firewall/security groups |
| App in Docker network | `neo4j:7687` by service name | Container network DNS, listener, matching advertised address |
| App in Kubernetes | Service DNS or supported internal endpoint | Namespace, Service selector, NetworkPolicy, topology |
| App outside VPC via VPN | Internal hostname when VPN provides DNS/routes | Split DNS, VPN routes, firewalls |
| App from Internet via proxy | Public FQDN and protected port | TCP proxy, TLS, authentication, exposure policy |
| Java client of Neo4j cluster | Bootstrap and member endpoints returned by routing | Every advertised Bolt address is reachable |

### 6.1. `localhost` Always Points to the Client's Own Environment

For example, if Java runs in one Pod and Neo4j in another Pod:

~~~text
bolt://localhost:7687
~~~

points to the Java Pod's own loopback, **not the Neo4j Pod**. Similarly, Java inside a Docker container cannot reach another database container via `localhost` unless a special shared network-namespace setup was explicitly designed.

Before editing Neo4j configs, confirm **which namespace/container/host the client runs in**.

### 6.2. One FQDN Working from Multiple Locations

If both internal and external-VPC clients must use `graph.example.com`, consider **split-horizon DNS**:

~~~text
Java inside VPC:
graph.example.com → private proxy IP

Java outside VPC:
graph.example.com → public proxy IP
~~~

This works only if both paths reach compatible endpoints sharing the same hostname/port and TLS policy. Split DNS is a DNS/infrastructure feature, not something Neo4j generates from advertised settings.

## 7. Deploying Behind a TCP Proxy or Load Balancer

A TCP load balancer can sit between the Java service and Neo4j to hide private IPs, enforce firewalls, and provide a stable endpoint.

~~~mermaid
flowchart LR
  A["Java Service"] -->|"graph.example.com:17687"| B["TCP Load Balancer"]
  B -->|"10.20.1.15:7687"| C["Neo4j Server"]
  C --> D["Graph database"]
~~~

A minimal design includes:

1. **Frontend listener:** hostname/IP and port called by clients.
2. **Backend target:** Neo4j IP/port to which the LB forwards.
3. **Health check:** assesses whether the server can accept requests via LB-supported checks.
4. **TLS:** defines passthrough/termination/re-encryption.
5. **Firewall:** allows authorized sources to frontend and restricts backend to LB only.
6. **Idle timeout/connection lifetime:** suited for relatively long-lived Bolt connections.
7. **Advertised endpoint:** advertised hostnames/ports aligned with the path the driver uses.

### 7.1. TCP Proxy Differs from HTTP Proxy

An HTTP reverse proxy serving websites typically routes requests by HTTP host/path. Bolt uses its own binary protocol over TCP; you must use **TCP stream/forwarding** or a supported gateway solution.

Illustrative NGINX stream example for a single Neo4j instance (applicable only if NGINX includes the `stream` module):

~~~nginx
stream {
    upstream neo4j_bolt {
        server 10.20.1.15:7687;
    }

    server {
        listen 17687;
        proxy_pass neo4j_bolt;
        proxy_connect_timeout 5s;
        proxy_timeout 1h;
    }
}
~~~

This is an **illustrative snippet**, missing IP allowlists, connection limits, TLS, monitoring, and system tuning. Never copy verbatim into production without security and cluster topology review.

### 7.2. TLS Passthrough vs. TLS Termination

| Mode | Who Terminates Client TLS? | What to Check |
|---|---|---|
| **Passthrough** | Neo4j backend | Neo4j has Bolt TLS and a certificate matching client FQDN |
| **Termination at proxy** | TCP proxy | Proxy holds valid cert; upstream protected by private network or separate TLS |
| **Termination + re-encryption** | Proxy and backend across two TLS legs | Trust, hostnames, and policies on both segments |

If the client uses `neo4j+s://graph.example.com:17687`, whichever TLS endpoint the client connects to must present a trusted certificate for `graph.example.com`. Successful TCP connection **does not prove the TLS handshake will succeed**.

### 7.3. Load Balancers Do Not Fix Wrong Routing Tables

If the proxy only handles bootstrap while Neo4j advertises private endpoints like `10.20.1.15:7687` or internal Pod names, an external routing driver will still fail. Fix this by designing advertised endpoints and reachability for **every server the driver selects**, not just the frontend proxy.

### 7.4. Health Checks Must Answer the Right Question

A TCP connect probe detects if a backend isn't listening on a socket, yet **does not prove**:

- The database is ready to execute Cypher.
- Client authentication/TLS is valid.
- The server holds the right role for write queries.
- The routing table contains reachable endpoints.
- Real query workloads will meet SLOs.

Depending on infrastructure, combine TCP readiness with Bolt/Driver checks in a dedicated monitoring pipeline; avoid expensive health checks on every user request.

## 8. Docker Compose: Distinguishing Host Ports and Container Ports

Suppose Neo4j runs in Docker and an external Java service outside the Docker host connects on port `17687`.

~~~yaml
services:
  neo4j:
    image: neo4j:5
    ports:
      - "127.0.0.1:17474:7474"
      - "17687:7687"
    environment:
      NEO4J_server_bolt_listen__address: "0.0.0.0:7687"
      NEO4J_server_bolt_advertised__address: "graph.example.com:17687"
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
~~~

This example shows only part of the network/volume configuration. Real deployments must manage auth, secrets, TLS, volume permissions, network policies, and backups; **do not use this snippet as a complete production Docker Compose**.

### 8.1. Mapping Rules

~~~text
Java Client
  graph.example.com:17687
          |
Docker host:17687
          |
Docker port mapping 17687:7687
          |
Neo4j container:7687
listen 0.0.0.0:7687
~~~

In Docker Compose, `17687:7687` means **host port → container port**. If Java is outside the container network, use the external port. If Java is in the same Docker network, it can use the service name and container port `neo4j:7687` when routing and configs are designed for internal clients.

### 8.2. Environment Variables and Underscores

Under the Neo4j Docker image's environment variable rules:

~~~text
server.bolt.listen_address
    → NEO4J_server_bolt_listen__address

server.bolt.advertised_address
    → NEO4J_server_bolt_advertised__address
~~~

Each dot in a setting name becomes one underscore, while underscores already in the setting name are escaped as **double underscores**. Verify against your exact image/tag; a typo causes the setting to be ignored.

### 8.3. Docker Port Mapping Does Not Restrict Source Access

The line:

~~~yaml
ports:
  - "17687:7687"
~~~

can publish across host interfaces per Docker rules. If you do not want public exposure, specify an explicit host bind address, use private networks/firewalls, and avoid opening ports to the Internet.

Example binding only to host loopback:

~~~yaml
ports:
  - "127.0.0.1:17687:7687"
~~~

This suits apps **on the same host** or over tunnels, blocking direct connections from remote hosts by default.

### 8.4. When Both Internal and External Docker Clients Exist

A connector normally has only **one effective advertised address** at runtime. If internal clients only resolve `neo4j` while external clients only resolve `graph.example.com`, routing may not work simultaneously for both.

Solutions include a shared FQDN with DNS/routing working in both scopes, or a supported split endpoint/deployment architecture. **Never arbitrarily advertise Docker's internal hostname and expect external clients to resolve it.**

## 9. Kubernetes: Services, Private DNS, and Bolt Connectivity

In Kubernetes, a Java service typically reaches Neo4j via a **Kubernetes Service**, e.g.:

~~~text
neo4j.graph.svc.cluster.local:7687
~~~

However, `*.svc.cluster.local` hostnames normally resolve and route only inside the cluster (or via specialized DNS/network setups). External clients must not receive these internal names in routing tables if they have no path to them.

### 9.1. Internal Service Example for a Single-Server Deployment

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: neo4j-bolt
  namespace: graph
spec:
  type: ClusterIP
  selector:
    app: neo4j
  ports:
    - name: bolt
      protocol: TCP
      port: 7687
      targetPort: 7687
~~~

This example assumes the Neo4j Pod actually carries label `app: neo4j` and listens for Bolt on port 7687. A Kubernetes Service does not initialize Neo4j, volume data, certificates, or user privileges.

Path:

~~~text
Java Pod
   |
   | neo4j-bolt.graph.svc.cluster.local:7687
   v
ClusterIP Service
   |
   v
Neo4j Pod Bolt listener:7687
~~~

Check the Service selector/EndpointSlice/Pod readiness and **NetworkPolicy**. If the Service has no endpoints, editing `server.bolt.advertised_address` in Neo4j will not fix Java Pod routing through the Service.

### 9.2. Advertised Address for Internal Clients

With a single server in-cluster, if internal clients use a compatible Service FQDN and routing, advertising a hostname reachable by those clients can work. However, cluster topologies and Service load balancing often require per-member configuration.

In a cluster, never assume a single shared ClusterIP Service is a valid advertised address for **all members**.

### 9.3. Clients Outside Kubernetes

If Java runs outside the cluster, decide whether access is permitted and use a supported exposure architecture:

- VPN/private interconnect into the VPC/VNet with private DNS where applicable.
- TCP LoadBalancer or TCP proxy.
- Dedicated per-member exposure when cluster routing requires it.
- Matching TLS certificates and firewall rules.

A standard HTTP Ingress controller does not forward Bolt merely because a path rule was added. Configure a stream-capable TCP proxy/Ingress or an appropriate gateway/controller.

### 9.4. Avoid Advertising Ephemeral Pod IPs

Pod IPs change on restart or rescheduling. If external clients receive Pod IPs from the routing table, connections drop when Pods move or because those IPs are unroutable.

For topologies needing stable member identities, architectures typically require stable hostnames/services aligned with supported StatefulSet/cluster deployments. Never assume an ephemeral Pod IP is a durable endpoint.

## 10. Neo4j Cluster: Routing and Per-Member Addresses

For clusters, Java Driver connections add a **topology discovery** step. Applications typically use `neo4j://` or `neo4j+s://` so the driver fetches routing information.

~~~mermaid
flowchart LR
  J["Java Driver"] -->|"Bootstrap"| B["Gateway / bootstrap"]
  B --> R["Routing table"]
  R --> A["Member A: Bolt endpoint"]
  R --> C["Member B: Bolt endpoint"]
  R --> D["Member C: Bolt endpoint"]
~~~

When deploying:

1. Choose a bootstrap hostname/port reachable by Java.
2. Ensure Neo4j members advertise Bolt addresses reachable on the client's network.
3. Ensure DNS for each endpoint is stable per topology.
4. With TLS, certificates and proxy routing must be valid for the hostnames clients use.
5. Test both **reads** and **writes**, not just bootstrap connectivity.
6. Test role changes, failover, and membership changes.
7. Restrict **server-to-server** ports to internal networks; never expose them externally just because Bolt clients need routing.

### 10.1. Every Advertised Endpoint Must Be Reachable

Suppose the routing table returns:

~~~text
server-a.internal:7687
server-b.internal:7687
server-c.internal:7687
~~~

If Java outside the network reaches bootstrap via `graph.example.com` yet cannot resolve those hostnames, queries will fail right after discovery.

A valid exposure plan must address **all three endpoints** or use a product-supported gateway/routing architecture. **Do not just create public DNS for bootstrap and stop.**

### 10.2. Internal Cluster Addresses Differ from Client Bolt Addresses

A Neo4j cluster uses server-to-server addresses for coordination and replication depending on version and architecture. These internal addresses do not have to match `server.bolt.advertised_address`.

Never copy public Bolt settings blindly into all cluster settings, and never expose internal cluster ports to the Internet without explicit requirements and approved security controls.

### 10.3. Routing Tables Change Over Time

In an active cluster, servers change roles or membership changes. Testing should cover:

- Cold-starting clients after deployment.
- Reconnecting when a proxy/LB is replaced.
- Failover of the server handling writes.
- DNS updates with realistic TTLs.
- Connection pool and retry behavior in the Java Driver.

A single `RETURN 1` succeeding right after deployment does not prove routing remains stable during failover.

## 11. VPN, Private DNS, and Private Networks

Not every database should be exposed to the Internet. For enterprise apps, Neo4j is usually placed in a **private subnet/VPC/VNet** accessible only to approved services.

Example:

~~~text
Java Service subnet A                 Neo4j subnet B
10.30.1.0/24                         10.30.2.0/24
       |                                    |
       | private DNS graph.internal.example|
       +---------- private route ---------->|
                                             |
                                 listen 10.30.2.15:7687
                                 advertise graph.internal.example:7687
~~~

Items to verify:

- Private DNS resolves from the **client's subnet**.
- Routes between subnets/VPCs, NAT, or peering are configured.
- Firewalls/security groups allow Java sources to Bolt 7687.
- The database needs no unnecessary public ports.
- External apps use approved VPN/private links or proxies.
- Certificates match the internal or unified DNS names per design.

### 11.1. DNS Resolves Correctly, Yet Routing Can Still Fail

`graph.internal.example` may return the right IP while the client has no route to the target subnet. That is a **network routing** failure, not Neo4j authentication.

Distinguish:

1. DNS resolution.
2. Opening TCP to IP:port.
3. Completing TLS/Bolt handshake.
4. Authentication.
5. Routing/discovery.
6. Executing Cypher.

Each layer has distinct diagnostics; increasing connection timeouts masks symptoms without creating a missing route.

### 11.2. Split-Horizon DNS Enables a Single Hostname

One FQDN can resolve to a private IP internally and a public proxy externally. However, this design requires testing TLS, advertised ports, and routing in both scopes; never rely on temporary `hosts` file entries on individual machines in production.

## 12. Security: DNS and Proxies Do Not Replace TLS and Authentication

Placing Neo4j behind a proxy or private subnet controls **network reachability**, but does not provide full application security on its own.

Consider:

- **TLS encryption for Bolt**, verifying hostnames and trust chains.
- **Authentication** for Neo4j accounts.
- **Authorization** by database, role, and required privileges.
- **Network segmentation** restricting allowed sources to listeners.
- **Secrets management** for passwords, tokens, certificates/private keys.
- **Log redaction** so credentials, Cypher parameters, and node/relationship data never leak.
- **Backup/restore** and recovery testing on fresh infrastructure.

### 12.1. TLS Hostname Must Match Where Java Connects

If the client uses:

~~~text
neo4j+s://graph.example.com:7687
~~~

the TLS endpoint seen by the client must present a valid certificate for `graph.example.com`. If the certificate is issued only for `db.internal`, hostname verification fails.

Do not switch to `neo4j+ssc://` or disable certificate validation just to get past a production error. Fix the certificate, FQDN, or TLS termination point to match the design.

### 12.2. Two TLS Segments Through a Proxy

For proxy termination:

~~~text
Java --TLS--> Proxy --private TCP/TLS--> Neo4j
~~~

Explicitly decide whether upstream traffic from proxy to Neo4j is encrypted, whether the backend network is trusted, and what auth/authorization is enforced. **Client→proxy TLS does not automatically encrypt proxy→database.**

### 12.3. Do Not Expose Admin HTTP When Only Bolt Is Needed

If Java services only connect via Bolt, there is no reason to expose HTTP/HTTPS admin ports to the Internet by default.

Directional configuration:

~~~properties
server.bolt.enabled=true
server.http.enabled=false
server.https.enabled=false
~~~

If operations need Neo4j Browser, provide a separate admin access path over VPN, HTTPS, or a controlled network. These settings only enable/disable connectors; they do not replace database auth policies.

### 12.4. Keep Secrets Out of URIs and Logs

Never put passwords in logs or source code:

~~~text
# Do not store or log in this form:
neo4j://user:actual-password@graph.example.com:7687
~~~

Keep only the endpoint in the URI, supplying username/password via the Driver's auth mechanism and secret manager. When debugging, log **operation name, error category, and latency** rather than full connection strings and secrets.

## 13. Java Driver: Verifying Connectivity from the Application Environment

A Cypher Shell test on the Neo4j server does not prove a Java Pod or app container has a working network path.

Java Driver example verifying connectivity and running a minimal query:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jConnectivitySmokeTest {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        if (uri == null || uri.isBlank()
                || username == null || username.isBlank()
                || password == null || password.isBlank()) {
            throw new IllegalArgumentException(
                "Neo4j connection environment is incomplete"
            );
        }

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase("neo4j"))) {
                int one = session.executeRead(tx ->
                    tx.run("RETURN 1 AS value")
                      .single()
                      .get("value")
                      .asInt()
                );
                if (one != 1) {
                    throw new IllegalStateException(
                        "Unexpected Neo4j smoke-test value"
                    );
                }
                System.out.println("Neo4j Bolt smoke test succeeded");
            }
        }
    }
}
~~~

This snippet illustrates standard Java Driver APIs. In real apps, **reuse the Driver across the application lifecycle**, rather than opening/closing it per request. This `main` smoke test is separate for one-off checks.

### 13.1. Layered Testing

- `verifyConnectivity()`: confirms the Driver can establish a connection using the URI and auth.
- `RETURN 1`: verifies a minimal read Cypher query executes.
- Representative business query: verifies privileges, target database, and designed paths.
- Routing clusters: test both read and write transactions per topology and allowed failover.
- TLS: verify certificate matches URI without skipping hostname validation.

One passing check does not guarantee every future connection or cluster member remains healthy. Maintain monitoring and sensible application-layer retries.

### 13.2. Managed Transactions and Retries Do Not Fix DNS

`session.executeRead` and `session.executeWrite` retry transient errors classified as retryable by the Driver. They **cannot fix**:

- Non-existent DNS records.
- Unroutable IPs.
- Permanently blocking firewalls.
- Invalid certificates.
- Advertised endpoints unreachable from the client network.
- Unauthorized databases or users.

Do not raise retry budgets or pool sizes indefinitely when the root cause is networking/configuration. Excessive retries slow down requests and add load.

### 13.3. Parameterize Queries and Keep Results Small

In post-deploy query checks, always use Cypher parameters:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN c.customerId AS customerId,
       c.status AS status
LIMIT 1;
~~~

Avoid logging sensitive `$customerId` values, emails, tokens, or graph records. Fetch minimal data for smoke tests and operations; never run deep traversals just to prove Bolt is open.

## 14. Spring Data Neo4j: Separating Client URI and Server Topology

For Spring Boot using Spring Data Neo4j, sample app config:

~~~properties
# application.properties — illustrative; never store real passwords in repos.
spring.neo4j.uri=neo4j+s://graph.example.com:7687
spring.neo4j.authentication.username=app_user
spring.neo4j.authentication.password=USE_SECRET_PROVIDER
~~~

This shows the **client URI**, not the server setting where Neo4j binds ports. In real deployments, fetch passwords from a secret manager/managed env var, and verify property names against your Spring Boot version.

### 14.1. Configuration Per Environment

| Environment | Candidate URI | Notes |
|---|---|---|
| Local on dev machine | `bolt://localhost:7687` | Use only with local server or proper tunnel |
| Java Docker on same network | `bolt://neo4j:7687` | Service DNS, aligned advertised/routing setup |
| Java Pod in same cluster | `neo4j+s://neo4j-bolt.graph.svc.cluster.local:7687` | DNS, TLS cert, and topology must align |
| Java service in VPC | `neo4j+s://graph.internal.example:7687` | Private routes, internal DNS |
| External Java via proxy | `neo4j+s://graph.example.com:17687` | TCP/TLS proxy, all routing endpoints reachable |

These values are **conditional candidates**, not universal defaults for every topology. Using `neo4j+s` assumes the server/proxy supports TLS with valid certificates. Unencrypted `bolt://` locally should stay strictly within protected test scopes.

### 14.2. Keep `localhost` Out of Container Profiles

A service running locally on a dev laptop may use `localhost:7687`. Deployed into a Pod/container, that same address resolves to **the container's own loopback**, usually not Neo4j.

Verify **effective configuration after the app loads profiles, env vars, and secrets**. Do not inspect only `application.properties` in the repo while ignoring runtime overrides.

### 14.3. Database and Privileges Are Distinct from Networking

A request may open Bolt yet fail when selecting a database or running Cypher due to privileges. Separate:

- Network/TLS.
- Authentication.
- Database name.
- Authorization.
- Queries/schema/indexes and performance.

Avoid changing listen/advertised addresses to solve an authorization failure after the handshake already succeeded.

## 15. Controlled Deployment Process

A practical workflow needs clear stages.

### 15.1. Step 1 — Map the Topology Before Making Changes

Document:

| Component | Required Information |
|---|---|
| Client | Host/Pod/container, subnet, DNS resolver, URI |
| Neo4j | Version, server count, edition/topology, database |
| Listen | IP/interface and port per connector |
| Advertised | FQDN/IP and port received by driver |
| Proxy/LB | Frontend listener, backend target, protocol, health check |
| DNS | Zone, records, TTL, split DNS if used |
| Network | Routes, firewalls, security groups, VPN/private link |
| TLS | Termination point, cert/SAN, and trust chain |
| Driver | Version, direct/routing scheme, timeouts, pool |
| Security | Service accounts, roles, secrets, log retention |

Draw a **network path diagram** for each client group. If you cannot explain where a URI connects at every hop, you are not ready to finalize configuration.

### 15.2. Step 2 — Build Configuration for the Exact Topology

- Single server: pick listen in host/network namespace and reachable advertised FQDN/port.
- Container: add host port mappings and avoid `localhost` confusion.
- Kubernetes: check Service, selector, endpoints, and private DNS.
- Cluster: ensure **every endpoint** returned by routing is reachable.
- Proxy: use TCP forwarding and decide TLS passthrough/termination.
- Private network: align internal firewalls/routes/DNS.

Never copy an entire config file from local to production without adjusting hostnames, ports, secrets, and public exposure.

### 15.3. Step 3 — Pre-Traffic Checks

At minimum:

1. Confirm the Neo4j process starts and opens its listener.
2. Read back effective runtime configuration.
3. Verify DNS from **where Java will run**.
4. Verify TCP reachability to the client endpoint.
5. Verify TLS certificate/hostname.
6. Test Driver, authentication, and `RETURN 1`.
7. For routing, verify member endpoints and read/write paths.
8. Verify safe metrics/logging and pre-change backups.
9. Confirm privileges are no broader than designed.

### 15.4. Step 4 — Cutover and Observation

When switching DNS or load balancers:

- Record change timestamps and before/after DNS values.
- Account for DNS TTLs, client caches, and connection pools.
- Maintain overlap between old and new endpoints when planned.
- Monitor connection errors, TLS errors, routing failures, timeouts, and p95/p99.
- Test representative business read/write flows.
- Increase traffic only after acceptance criteria pass.

Do not use "one test request passed" as proof that all clients/clusters have cut over cleanly.

### 15.5. Step 5 — Prepared Rollback

Before deploying, define:

- Pre-change listen/advertised and DNS/proxy configs.
- How to roll back load balancer targets, Services, or config versions.
- Mandatory stop-traffic triggers.
- Effects of DNS TTL and connection pools during rollback.
- How to verify zero data loss and continued transaction success.

Rolling back network paths does not roll back data. If deployment includes schema migrations, maintain a separate migration/backup plan; never conflate it with changing connection addresses.

## 16. Diagnosing Errors from DNS to Cypher

Test **from the actual client environment**, not just from the Neo4j host.

### 16.1. Step A: DNS

On an OS with standard tools:

~~~bash
# Available in many Linux environments:
getent hosts graph.example.com

# Or equivalent DNS utility if installed:
nslookup graph.example.com
~~~

Fix DNS issues before tweaking Neo4j authentication or database names. With split-horizon DNS, run from **each subnet/client context** to spot differences.

### 16.2. Step B: TCP

~~~bash
nc -vz graph.example.com 7687
~~~

If the external port is 17687, test that exact port:

~~~bash
nc -vz graph.example.com 17687
~~~

A passing TCP connect **does not prove** Neo4j Bolt/TLS/auth works. Refused or timed-out TCP points to firewalls, routes, proxy listeners, port mappings, or an unlistening server.

### 16.3. Step C: TLS, Authentication, and Bolt

In an environment with Cypher Shell and proper privileges:

~~~bash
cypher-shell -a "neo4j+s://graph.example.com:7687" -u app_user
~~~

This assumes the endpoint has Bolt TLS with a valid certificate and an authorized user. Never pass production passwords on the command line where shell history/process lists can record them; use secure secret input methods.

If TLS fails, check certificate SANs, hostname, trust chain, and termination point. If auth fails, check user/secret/roles rather than changing DNS "to test."

### 16.4. Step D: Routing

If direct works while `neo4j+s://` fails, inspect the endpoints returned by routing and the topology seen by the client. This **does not mean** you should switch permanently to direct in a cluster that requires routing.

### 16.5. Step E: Query

Once the network path works, run:

~~~cypher
RETURN 1 AS ok;
~~~

Then execute a read-only business query with synthetic parameters and proper privileges. Only if queries are slow should you inspect indexes, `EXPLAIN`/`PROFILE` in a permitted environment, and graph load—instead of continuing to tweak ports.

## 17. Common Failure Reference Table

| Symptom | Possible Cause | Priority Check |
|---|---|---|
| Java in container fails with `localhost` | Calling the Java container itself | Use valid DNS/service name on the network |
| Proxy 17687 forwards to Neo4j 7687 yet driver calls 7687 | Confused internal vs. external port | Compare frontend listener, mapping, and URI |
| Neo4j cannot bind public IP | IP not on process's interface | Bind internal IP or scoped wildcard |
| DNS valid yet TCP times out | Wrong route/firewall/NAT/Service | Check from client subnet and proxy target |
| `Connection refused` | No listener or explicit reject rule | Sockets/listeners/port mappings |
| TCP opens yet TLS fails | Wrong certificate, scheme, or termination | Hostname, SAN, trust, passthrough |
| HTTP Browser loads yet Cypher fails | Bolt closed or unreachable | Check Bolt independently |
| Cluster bootstrap reachable, queries fail | Advertised member address unreachable | Compare routing table and client network |
| Driver outside K8s gets `*.svc.cluster.local` | Internal address advertised externally | Fix exposure/routing design |
| Edited `neo4j.conf` with no effect | Not restarted, config overridden | `SHOW SETTINGS`, startup logs, config sources |
| Spring profile still uses `localhost` | Wrong environment override | Check effective URI inside Pod |
| Connection pool timeout | Many transactions/pool cap or overloaded server | Pool wait, transaction latency, query plans |
| Authentication failed | Wrong credentials/role | Secrets and privileges, don't tweak firewalls |
| Routing fails only after failover | New endpoint unreachable/bad TLS | Test new member from client context |
| Only `+ssc` connects | Non-standard cert/trust | Fix cert/trust instead of skipping validation |
| Proxy health OK yet queries fail | Only TCP readiness passes | Bolt/routing/read-write smoke test |
| DNS changed yet clients hit old IP | Stale TTL/cache/connection pool | Inspect DNS and connection lifecycle |

### 17.1. Do Not Change Multiple Layers at Once

Changing URI, advertised address, TLS policy, proxy listener, and firewall simultaneously makes it impossible to tell which change fixed or broke things. Change **one hypothesis-backed layer at a time**, record before/after states, and verify step by step.

## 18. SLOs and Post-Deployment Monitoring

A properly connected deployment means more than "zero Connection refused errors." The app must sustain query and transaction quality.

| Monitoring Group | Example Metrics |
|---|---|
| Connectivity | Bolt connection success rate, timeouts |
| Routing | Routing table errors, unreachable endpoints |
| TLS | Handshake/certificate failures |
| Authentication | Login/privilege errors |
| Driver pool | Connection count, pool wait, acquisition timeouts |
| Database | Transaction latency, deadlocks, query errors |
| Performance | p50/p95/p99 query/API latency, completed RPS |
| Proxy/LB | Frontend connections, backend failures, idle timeouts |
| DNS/Network | Resolution failures, connections to wrong IP/port |
| Availability | Readiness status, role switches/failovers |
| Data correctness | Read/write results and basic business checks |

### 18.1. Never Log Sensitive Data When Debugging Networks

A connection or Cypher error can cause application logs to print URIs with sensitive info, parameters, or node results. When setting up monitoring:

- Log **operation name, error category, duration, and approved endpoint alias**.
- Never log passwords, tokens, or parameter maps.
- Never write full graph results into APM/traces.
- Restrict log access and retention.
- Use synthetic canary data to verify redaction policies.

Network debugging never requires real customer emails or account numbers.

### 18.2. Separate Connection Errors from Query Errors

If `RETURN 1` succeeds while relationship traversal queries remain slow, the cause likely lies in indexes, fan-out, cardinality, or contention. Do not blame proxies for all high latency before measuring network time, pool wait, and database execution separately.

## 19. Three Environment Design Examples

### 19.1. Local Environment

~~~text
Java desktop → bolt://localhost:7687 → Neo4j local
~~~

Characteristics:

- Can bind Neo4j on loopback if no external connections are needed.
- No public DNS, NAT, or proxy required.
- Do not use this setup to validate production TLS/routing.

### 19.2. Staging Environment in a Private VPC

~~~text
Java Service private subnet
     |
     | neo4j+s://graph.staging.internal:7687
     v
Private TCP endpoint
     |
     v
Neo4j server private IP:7687
~~~

Conditions:

- Internal DNS resolves properly.
- Firewalls allow only application sources.
- TLS holds a certificate for the staging FQDN.
- Advertised address suits the staging network.
- Concurrent read/write tests run and logs are verified secret-free.

### 19.3. Production Cluster Behind a Proxy

~~~text
Java Service / Client network
     |
     | neo4j+s://graph.prod.example.com:7687
     v
Approved bootstrap endpoint
     |
     v
Routing discovery
     |
     +--> Member A externally reachable endpoint
     +--> Member B externally reachable endpoint
     +--> Member C externally reachable endpoint
~~~

Core conditions:

- Routing is designed **for the actual cluster topology**.
- Every endpoint received by the Driver has DNS and routes to the right server.
- Certificates match each hostname/TLS termination point.
- Firewalls/secrets/roles are locked down.
- Failover, cutover, rollback, and monitoring plans exist.

Do not treat the production cluster example as a recipe saying "just put an LB in front of three nodes"; exposure details depend on Neo4j version, edition, and deployment platform.

## 20. Applied Exercises

### Exercise 1 — Port-Translating NAT

Neo4j listens on `10.20.1.15:7687`. The proxy listens on `graph.example.com:17687` and forwards to that port. The Java app runs outside the internal network.

**Question:** Which URI and advertised address fit a single instance with supported routing/TLS?

**Answer:** Provided the proxy supports Bolt/TLS and the hostname is valid, Java can use `neo4j+s://graph.example.com:17687`; the advertised Bolt endpoint should also be `graph.example.com:17687`. Listen remains the internal address/port. Verify actual routing conditions rather than merely matching strings.

### Exercise 2 — Container `localhost`

Java and Neo4j run in two containers on the same Docker network. Java is configured with `bolt://localhost:7687`.

**Question:** Why does it fail and what should you check?

**Answer:** `localhost` resolves to the Java container itself. Use Neo4j's DNS/service name on the shared network, and check listeners/container ports and matching advertised/routing settings.

### Exercise 3 — TCP Open Without Bolt

A proxy accepts connections on port 7687 yet is configured only as an HTTP reverse proxy.

**Question:** What must change?

**Answer:** Configure TCP forwarding/streaming for Bolt or a supported gateway; never treat an HTTP path as a Bolt endpoint.

### Exercise 4 — Routing Table Returning Wrong Network

Java from the Internet connects to bootstrap successfully, yet the Neo4j cluster returns `10.20.1.15:7687` and `10.20.1.16:7687`.

**Question:** What is the likely cause?

**Answer:** The Driver must connect to endpoints from the routing table, yet the client has no route to those private IPs. Design advertised endpoints/exposure for all members per supported topology.

### Exercise 5 — TLS Certificate Mismatch

The application uses `neo4j+s://graph.example.com:7687`, while the certificate returned to the client is valid only for `db.internal`.

**Question:** Should you switch to `neo4j+ssc` in production?

**Answer:** Not as a long-term solution. Provision a certificate matching the hostname/trust chain, or use a hostname that has a valid certificate and matching DNS/routes.

### Exercise 6 — Browser vs. Java Driver

Neo4j Browser loads over HTTP port 7474, yet Java Driver times out on 7687.

**Question:** Does Browser loading prove Neo4j Bolt is ready?

**Answer:** No. Those are two separate connectors; inspect the Bolt listener, firewall, proxy, and TLS independently.

### Exercise 7 — Kubernetes Service Without Endpoints

Inside the cluster, the Java Pod resolves `neo4j-bolt.graph.svc.cluster.local`, yet the Service has no matching EndpointSlice.

**Question:** Will changing the advertised address alone solve it?

**Answer:** Usually no. Check the Service selector, Pod labels, readiness, and backend Service first. Advertised address operates at a different layer.

### Exercise 8 — DNS Cutover and Connection Pools

After switching DNS from an old proxy to a new proxy, some Java instances still hit the old IP.

**Question:** Which factors must be considered?

**Answer:** DNS TTL/caching, existing Bolt connections pooled prior to cutover, whether the old proxy endpoint still serves traffic, and traffic draining plans. Switching DNS does not automatically close existing connections.

### Exercise 9 — Misinterpreted Quick Check

`nc -vz graph.example.com 7687` succeeds, yet Cypher Shell fails to authenticate.

**Question:** Is that enough to prove the system works?

**Answer:** No. TCP only proves the port is open. You must verify TLS, Bolt handshake, username/password, database, and authorization.

### Exercise 10 — Scaling a Single Server into a Cluster

An operations team keeps the single-hostname advertised config from a standalone deployment, then expands Neo4j into multiple cluster members.

**Question:** Can the old configuration be assumed valid for the cluster?

**Answer:** No. Redesign topology, per-server/gateway endpoints, routing tables, and Java Driver access paths for the cluster version.

## 21. Deployment Acceptance Checklist

### 21.1. Database and Configuration

- [ ] Verified Neo4j/Driver versions and single-server vs. cluster topology.
- [ ] Enabled connectors based on actual need; admin HTTP not exposed indiscriminately.
- [ ] Neo4j bound to the right listen address and port in its network namespace.
- [ ] Advertised Bolt hostname/port aligns with client network paths.
- [ ] Inspected effective runtime settings, not just config files.
- [ ] Prepared migrations/backups if deployment modifies data.

### 21.2. Network and Proxy

- [ ] DNS resolves properly from the actual Java host/container/Pod.
- [ ] Firewalls/security groups/NetworkPolicies permit required sources and block others.
- [ ] Proxy supports TCP Bolt with accurate frontend/backend port mappings.
- [ ] Host ports, container ports, Service ports, and `targetPort` are not confused.
- [ ] With TLS, certificates/trust/hostnames match at the termination point.
- [ ] Proxy health checks and timeouts suit Bolt connections.

### 21.3. Routing and Cluster

- [ ] Bootstrap endpoint is reachable.
- [ ] Every endpoint in the routing table selectable by the driver is reachable.
- [ ] Clients outside the VPC/Kubernetes do not receive unresolvable private names.
- [ ] Read/write routing and failover tested in an appropriate environment.
- [ ] Internal cluster ports are not confused with client Bolt ports.

### 21.4. Java/Spring and Operations

- [ ] URIs configured per environment without `localhost` in the wrong namespace.
- [ ] Secrets never hard-coded or printed in logs.
- [ ] Driver reused with proper session/transaction lifecycles.
- [ ] `verifyConnectivity()` and `RETURN 1` succeed from application runtime.
- [ ] Representative business query tested with proper privileges.
- [ ] Monitoring covers TLS/routing/timeouts/pool wait and SLOs.
- [ ] Plans exist for DNS/proxy cutover, rollback, TTLs, and connection pools.
- [ ] All assumptions regarding private networks, proxies, and topology documented.

## 22. Key Takeaways

**Deploying Neo4j behind a proxy, DNS, or private network** requires simultaneously ensuring **valid listeners, reachable network paths, and accurate advertised addresses**. Listen addresses tell Neo4j where to accept connections; advertised addresses tell clients where to connect, which is especially critical when using the **Neo4j Java Driver in routing mode**. In Docker, Kubernetes, or NAT, external hostnames/ports often differ from internal process binds.

When debugging, inspect **DNS → TCP → proxy/NAT → TLS → authentication → routing → Cypher** from the client environment itself. For clusters, a working bootstrap endpoint **does not prove** every server returned via routing is reachable. Combining version-matched settings, valid TLS/certificates, least privilege, Java Driver smoke tests, monitoring, and rollback plans keeps Neo4j queries and writes stable after deployment.
