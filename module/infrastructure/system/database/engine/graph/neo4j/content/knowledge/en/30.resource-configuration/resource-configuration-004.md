# Configuring Network Connections, Listen Addresses, and Advertised Addresses

## 1. Two Distinct Addresses in a Single Neo4j Connection

A Java application may connect to Neo4j successfully when running on the database host, yet fail with **connection refused**, **timeout**, or **routing table** errors when running from another machine. A frequent cause is confusing:

- **Listen address:** the IP/interface and port that the **Neo4j process binds** to accept incoming connections.
- **Advertised address:** the host and port that **Neo4j announces so clients or other components know where to connect**.

Both addresses may be identical in simple setups, but **they do not have to match** when Docker, NAT, load balancers, reverse proxies, multiple network interfaces, or clustering are involved.

Example of a server running inside a private network:

~~~text
Java application                             Neo4j server
neo4j+s://graph.example.com:7687               10.10.0.15
       |                                              |
       | DNS: graph.example.com -> 203.0.113.20       |
       v                                              |
Firewall/NAT: 203.0.113.20:7687 ------------------> 10.10.0.15:7687
                                                           |
                                              Listen: 0.0.0.0:7687
                                              Advertise: graph.example.com:7687
~~~

In the diagram:

- `0.0.0.0:7687` is how the server **receives** connections on applicable interfaces.
- `graph.example.com:7687` is the address **the application uses to reach it** across DNS and the network.
- `0.0.0.0` is **not** a valid hostname to hand out to remote clients.
- If NAT translates ports, the **advertised port** can differ from the internal server port.

This lesson belongs to Neo4j's **Resource Configuration** chapter, focusing on network connection configuration for property graphs and Cypher, Java Driver, and Spring Data Neo4j applications. The focus is configuring the **correct connection path**, verifying reachability, and avoiding accidentally exposing the database to the public Internet.

## 2. Three Things That Must Align: Listen, Advertise, and Network Path

A successful connection requires three conditions simultaneously:

1. **Neo4j actually listens** on the IP/interface and port where packets arrive.
2. **The address used by the client or advertised by Neo4j** resolves via DNS and points to a destination the client can reach.
3. **Intermediate networking permits traffic** across firewalls, security groups, container port mappings, Kubernetes Services, NAT, proxies, and TLS policies.

This can be visualized as:

~~~text
Client URI
  |
  v
DNS / Advertised IP
  |
  v
Firewall / Load Balancer / NAT / Proxy
  |
  v
IP:port forwarded to server
  |
  v
Neo4j listen socket
  |
  v
Authentication / TLS / Bolt or HTTP(S)
~~~

**Changing `advertised_address` does not open a port.** Nor does it configure DNS, create network routes, or add firewall rules. Conversely, opening port 7687 will not fix a routing table returning an address unreachable by the client.

### 2.1. What Is a Listen Address?

A listen address takes the form **host/IP:port** (exact syntax depends on the setting). Host/IP can be:

| Listen Host | Typical Meaning | When to Use |
|---|---|---|
| `127.0.0.1` | Accepts connections only via IPv4 loopback of the local environment | Local development, administration over SSH tunnel |
| `0.0.0.0` | Binds on all eligible IPv4 interfaces in the network namespace | Containers/servers accepting traffic from outside the namespace |
| A specific IP, e.g. `10.10.0.15` | Binds to the interface carrying that IP on the host | Multi-NIC servers needing interface isolation |
| A specific IPv6 address or wildcard | Binds over IPv6 per OS configuration | IPv6 environments; verify syntax and firewall rules |

**Note:** `127.0.0.1` inside a container is the **container's loopback**, not the host machine's loopback. `0.0.0.0` inside a container binds all **container** interfaces, but does not expose the port to external networks without explicit publish/expose rules.

Never bind to a public IP **that does not belong to an interface on the running machine**; in NAT/container environments, this can prevent Neo4j from starting because it cannot bind the socket.

### 2.2. What Is an Advertised Address?

The advertised address should be **the address connecting parties can actually use**. It is typically a hostname or IP plus port, for example:

~~~text
graph.internal.example:7687
graph.example.com:17687
neo4j-0.graph.svc.cluster.local:7687
~~~

Choose the address based on **client scope**: an app in the same VPC, a Java service in Kubernetes, a laptop over VPN, or public clients may see different network paths.

**Never use `0.0.0.0` as an advertised address for applications.** Wildcard listen describes bind interfaces; it does not tell a remote client where to send packets.

### 2.3. Do Not Confuse with a URL/URI

Settings in `neo4j.conf` hold a **host:port address**, not a URI with a scheme:

~~~properties
# Correct address format:
server.bolt.advertised_address=graph.example.com:7687
~~~

~~~text
# URI used in Java Driver:
neo4j+s://graph.example.com:7687
~~~

Do not put `neo4j+s://` into `server.bolt.advertised_address`. The scheme belongs to **client configuration**, determining routing/TLS behavior per driver capabilities.

## 3. Common Connectors and Default Ports

Neo4j serves multiple protocols. In a typical deployment:

| Protocol/Connector | Common Port | Who Uses It | Notes |
|---|---:|---|---|
| **Bolt** | **7687** | Java Driver, Spring Data Neo4j, Cypher Shell, Neo4j Browser when executing queries | Primary protocol for database operations |
| **HTTP** | **7474** | Admin UI/Browser and supported HTTP APIs | Cannot substitute for Bolt |
| **HTTPS** | **7473** | HTTP/Browser over TLS when enabled and configured with certificates | May not be enabled by default |
| **Internal cluster communication** | Version/architecture-dependent | Neo4j servers communicating with each other | Distinct from the client Bolt port |

These ports are **common defaults**, not immutable ports. They can be changed via configuration, container port mapping, or load balancers.

### 3.1. Opening Neo4j Browser Does Not Prove Bolt Works

A common scenario:

~~~text
Browser opens http://graph.example.com:7474      -> succeeds
Running Cypher inside Browser                    -> Bolt connection error
~~~

Browser can load its UI over HTTP, yet executing queries over Bolt still requires the **Bolt port and Bolt hostname** seen by the browser to be reachable. Opening only port 7474 in a firewall is not enough for Java Driver on 7687.

### 3.2. HTTP/HTTPS Should Not Be Publicly Exposed by Default

If applications only need Bolt, you can restrict or disable the HTTP connector depending on administrative needs. If Browser is needed, prefer internal/VPN access or HTTPS with proper authentication.

Never open every connector to the Internet just to solve a "cannot connect" error. First identify **which client needs which protocol** and open the minimal required scope.

## 4. Common Network Settings in Neo4j 5.x

Neo4j 5.x and newer releases use the settings below. **Setting names can differ across Neo4j generations**, especially compared to Neo4j 4.x guides using the `dbms.connector.*` prefix. Always verify configuration docs for your exact running version before applying in real environments.

| Setting | Role |
|---|---|
| `server.default_listen_address` | Default host/IP used across connectors unless overridden |
| `server.default_advertised_address` | Default advertised hostname/IP unless overridden per connector |
| `server.bolt.enabled` | Enables/disables Bolt |
| `server.bolt.listen_address` | Address/port Bolt binds to |
| `server.bolt.advertised_address` | Address/port Bolt advertises |
| `server.http.enabled` | Enables/disables HTTP |
| `server.http.listen_address` | Address/port HTTP binds to |
| `server.http.advertised_address` | Address/port HTTP advertises |
| `server.https.enabled` | Enables/disables HTTPS |
| `server.https.listen_address` | Address/port HTTPS binds to |
| `server.https.advertised_address` | Address/port HTTPS advertises |

**Design rule:** `default_*` values can reduce repetition, but when NAT, proxies, or multiple connectors use different hostnames/ports, **configure advertised addresses explicitly** per connector. Do not set a single default hostname and assume every protocol routes through it.

### 4.1. Illustrative Bolt Configuration

~~~properties
# neo4j.conf — example for Neo4j 5.x
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.bolt.advertised_address=graph.example.com:7687
~~~

Meaning:

- Bolt accepts connections on the process's IPv4 interfaces on port 7687.
- When advertising the Bolt endpoint, the hostname announced is `graph.example.com`.
- DNS for `graph.example.com`, forwarding paths to the server, and firewalls must be configured **outside Neo4j**.

**Warning:** This example is not a complete production configuration; it omits TLS, authentication, access controls, and network policies.

### 4.2. Using Default Listen/Advertised Addresses

~~~properties
server.default_listen_address=0.0.0.0
server.default_advertised_address=graph.internal.example

server.bolt.listen_address=:7687
server.bolt.advertised_address=graph.internal.example:7687
~~~

This snippet illustrates separating a **default host** from **connector ports**; leading-colon syntax and inheritance rules should be checked against your version's docs. For clarity, prefer writing explicit `IP:port` in `server.bolt.listen_address` and `host:port` in `server.bolt.advertised_address`.

`server.default_*` settings do not replace verifying which connectors are enabled and which TLS configuration is active.

### 4.3. Do Setting Changes Require a Restart?

Many settings affecting socket binding require a **server restart** for new sockets to take effect. Never assume editing `neo4j.conf` makes every client see the change immediately.

Safe procedure:

1. Confirm version and exact setting syntax.
2. Update the configuration file or managed configuration source.
3. Assess impact on live traffic and application connection pools.
4. Perform a restart/rolling restart according to deployment policy.
5. Read back **effective configuration values**, inspect listening sockets, and test connecting from a real client.

## 5. Development Environment: Listening Only on Localhost

When Neo4j and a Java service run **on the same machine without separate container networks**, Bolt and HTTP can be restricted to loopback:

~~~properties
server.bolt.enabled=true
server.bolt.listen_address=127.0.0.1:7687
server.bolt.advertised_address=localhost:7687

server.http.enabled=true
server.http.listen_address=127.0.0.1:7474
server.http.advertised_address=localhost:7474
~~~

Java Driver can connect directly:

~~~text
bolt://localhost:7687
~~~

Browser accesses the UI at:

~~~text
http://localhost:7474
~~~

When testing from **another machine**, `localhost` resolves to **that client machine**, not the database host. You must change the access path appropriately (VPN, SSH tunnel, or secured remote server access), rather than leaving the Java URI as `localhost`.

### 5.1. Localhost Inside Docker Means Something Different

If Neo4j runs in Docker while Java runs **on the host**, the client can use `localhost:7687` **if the port is published to the host**.

If Java runs in **another container**, `localhost:7687` points to the Java container itself; you typically use the service/container name on the shared Docker network, such as `neo4j:7687`, with an advertised address matching that network scope.

## 6. Internal/VPC Servers: Listen on the Appropriate Interface, Advertise via DNS

Suppose the server has private IP `10.10.0.15` and a Java service in the same VPC resolves `graph.internal.example` to this IP.

~~~properties
server.bolt.enabled=true
server.bolt.listen_address=10.10.0.15:7687
server.bolt.advertised_address=graph.internal.example:7687

# Only enable when an HTTP admin interface is needed.
server.http.enabled=false
server.https.enabled=false
~~~

Because the database only serves Bolt, HTTP/HTTPS are disabled in this example. If Browser/HTTPS is needed, design the access path and certificate configuration accordingly.

You can switch the listen IP to `0.0.0.0:7687` if the host has multiple interfaces and the environment requires broader binding, **but firewalls/security groups must still restrict allowed clients**.

### 6.1. Do Not Use a Public Hostname If DNS Does Not Match the Route

Suppose a Java host inside the VPC is only permitted to reach private IPs, yet Neo4j advertises `db-public.example.com` resolving to a public Internet IP. The client may:

- Fail to connect because the VPC lacks hairpin NAT.
- Traverse a longer or disallowed network path.
- Hit unintended firewall/TLS policies.

Inside internal systems, use a stable hostname that resolves and routes internally, such as `graph.internal.example`; if both internal and external clients exist, design DNS/proxies so endpoints match each client scope properly.

## 7. Docker: Published Port and Advertised Port Need Not Match

Docker creates a **dedicated network namespace** for each container. Neo4j can listen on `0.0.0.0:7687` inside the container while the host exposes a different port to clients.

Example:

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
~~~

This Compose snippet **only illustrates network mapping** and is not a complete secure deployment: add authentication, persistent volumes, TLS, and environment-appropriate firewall policies. Never commit plaintext production passwords into Compose files or repositories.

### 7.1. Analyzing the Port Path

~~~text
Java on external machine
neo4j+s://graph.example.com:17687
           |
           | DNS + firewall
           v
Docker host, port 17687
           |
           | Docker port mapping 17687:7687
           v
Neo4j container, port 7687
           |
           | listen = 0.0.0.0:7687
           | advertised = graph.example.com:17687
~~~

The mapping `17687:7687` means **host port 17687** forwards to **container port 7687**. Therefore, if external routing/clients rely on the advertised address, they must see **17687**, not 7687, unless another route exists.

Using the `neo4j+s://` URI assumes the Bolt endpoint is configured with valid TLS. If TLS is not configured yet, set up TLS first instead of falling back to unencrypted connections over untrusted networks.

### 7.2. Neo4j Container Environment Variable Rules

For Neo4j images supporting config-to-env mapping:

- **Dots** in a setting name map to a single underscore.
- **Existing underscores** in a setting name map to **double underscores**.

Thus:

~~~text
server.bolt.listen_address
  -> NEO4J_server_bolt_listen__address

server.bolt.advertised_address
  -> NEO4J_server_bolt_advertised__address
~~~

Verify conventions for the exact image/version you run; a misspelled variable can be silently ignored or fail to apply the intended setting.

### 7.3. When the Java Service Shares the Same Docker Network

If the Java client sits on the same Compose network, the internal endpoint might be:

~~~text
neo4j:7687
~~~

However, advertising `graph.example.com:17687` from the earlier config can cause a routing driver to receive an address **unsuitable** for the internal container network.

Options include:

- Using a single hostname whose DNS/route works from **both scopes**.
- Separating deployments/endpoints cleanly for internal versus external traffic.
- Using a supported access/proxy architecture rather than pointing the URI to an internal name while leaving a mismatched advertised address.

In a deployment where only Java clients on the same Docker network connect, you can advertise `neo4j:7687` and avoid publishing Bolt externally if unneeded.

## 8. Kubernetes: Services, Pod DNS, and Network Policies

Kubernetes provides Service names and load-balancing abstractions, yet **it does not eliminate the distinction between listen and advertised addresses**.

A Neo4j Pod typically binds the Bolt port on an appropriate interface inside the Pod. A Java application in the same cluster can connect via a Kubernetes Service, for example:

~~~text
neo4j.default.svc.cluster.local:7687
~~~

For a **single-instance** deployment or a single supported endpoint, this can be a stable internal access point. If clients run outside the cluster, `*.svc.cluster.local` hostnames are typically **neither resolvable nor routable** from the Internet.

### 8.1. In-Cluster Connection Model

~~~text
Java Pod
   |
   | neo4j.default.svc.cluster.local:7687
   v
Kubernetes Service
   |
   v
Neo4j Pod:7687
   |
   | server.bolt.listen_address=0.0.0.0:7687
~~~

Inside the cluster, verify that the address **advertised** by Neo4j/the cluster is reachable from the Java Pod. Also inspect Kubernetes **NetworkPolicy**, Service selectors, EndpointSlices, and readiness probes; Neo4j settings cannot fix a Service pointing to the wrong Pod.

### 8.2. Clients Outside the Cluster

An external client typically requires an Ingress/LoadBalancer/TCP proxy or a supported exposure mechanism. For Bolt, do not assume every HTTP Ingress controller supports raw TCP forwarding on port 7687.

If a client uses routing (`neo4j://` or `neo4j+s://`), the driver may receive **addresses of other servers** from the routing table. Making only the **bootstrap LoadBalancer endpoint** reachable is **insufficient** if returned member endpoints remain internal Pod DNS names.

In a Neo4j cluster, per-member advertised endpoints, DNS, and exposure type must match how Neo4j Drivers discover servers; prefer supported Helm/Operator deployments verified for your version.

### 8.3. Do Not Confuse Internal Cluster Traffic with Application Bolt

A Neo4j cluster also uses **server-to-server** connections for coordination, replication, or routing. These internal addresses/ports are configured separately per version, edition, and topology; never conflate them with `server.bolt.listen_address` or expose internal cluster ports to the Internet.

Expose only the connectors external consumers truly require; keep internal cluster traffic on controlled networks.

## 9. Direct Connections vs. Routing in the Neo4j Java Driver

The Java Driver distinguishes connection **schemes** with different routing and encryption behaviors:

| URI Scheme | Primary Meaning |
|---|---|
| `bolt://host:port` | Connects **directly** to a single Bolt endpoint |
| `neo4j://host:port` | Uses the Neo4j Driver's **routing/discovery** mechanism |
| `bolt+s://host:port` | Direct Bolt with TLS and certificate verification via trust chain |
| `neo4j+s://host:port` | Routing over Bolt with TLS and certificate verification via trust chain |
| `bolt+ssc://host:port` | Direct Bolt over TLS accepting self-signed certificates |
| `neo4j+ssc://host:port` | Routing over TLS accepting self-signed certificates |

The `+ssc` schemes are suited for controlled testing; in production, prefer `+s` with certificates and hostnames verified against a managed trust chain. Never use `+ssc` as a permanent workaround for certificate hostname mismatches.

**Important:** `neo4j://` differs from `bolt://` in how the driver **fetches and uses routing information**, not merely in URI spelling.

### 9.1. Direct Bolt

~~~text
Java Client -- bolt://graph.example.com:7687 --> Server
~~~

In direct mode, the driver directs connections to the specified endpoint per driver semantics. This model fits when intentionally targeting **one direct endpoint**.

Do not treat `bolt://` as a permanent fix for a cluster with misconfigured routing addresses if the application actually needs read/write distribution or failover via routing.

### 9.2. Routing Driver

~~~text
Java Client -- neo4j://gateway.example.com:7687 --> Bootstrap endpoint
                               |
                               | requests routing table
                               v
                    Addresses of server A / B / C
                               |
                     Java Driver opens connections
                     to the advertised endpoints
~~~

When the routing table contains `10.0.0.5:7687` while the Java app runs outside the VPC, **bootstrapping succeeds** yet subsequent query steps fail to connect.

**Key check:** every Bolt address the driver **may actually be routed to** must resolve, route, and satisfy TLS/authentication from the **driver's runtime environment**, not just from the Neo4j host.

### 9.3. Do Not Blindly Point Every Cluster Member to One Load Balancer Address

Making all cluster members advertise the same load-balancer hostname is **not** a safe universal rule. A routing driver needs to know which endpoint serves which role and typically tracks individual servers. Pointing all servers at one shared address can mask roles, break routing, or cause misdirected forwarding loops.

Choose an exposure/routing architecture officially supported for your Neo4j version and infrastructure, and test from the actual client network. Specialized routing/proxy setups exist, but never invent ad-hoc mappings for multi-node clusters.

## 10. Reverse Proxies, NAT, and Load Balancers

A reverse proxy may accept traffic on `db.example.com:443` and forward to Bolt at `10.10.0.15:7687`. In that setup:

~~~text
Bolt/TLS Client           TCP proxy/LB                  Neo4j
db.example.com:443 -----> proxy:443 -----------------> 10.10.0.15:7687
                                                       listen: 0.0.0.0:7687
                                                       advertise: db.example.com:443
~~~

The advertised address reflects the endpoint seen by the client, not necessarily the internal port. Verify:

- Does the proxy **support TCP forwarding for Bolt**, or only HTTP path routing?
- Is TLS **passed through**, terminated at the proxy, or terminated and re-encrypted?
- Does the certificate verified by the Java Driver match the hostname `db.example.com`?
- Does routing return other addresses that the proxy cannot reach or disallow?
- Are idle timeouts, connection lifetimes, and health checks compatible with Bolt?

### 10.1. Do Not Route Bolt Like HTTP

Bolt is a database connection protocol; you cannot simply place a `neo4j://` URI behind an HTTP path like:

~~~text
https://example.com/neo4j/bolt
~~~

and expect the Java Driver to treat it as a standard Bolt address. The proxy must forward the protocol properly on a supported host/port or gateway.

### 10.2. TLS Termination Determines How the Client Sees the Connection

If the proxy terminates TLS, the proxy's certificate must match the hostname used by the client. If TLS is passed through, Neo4j must be configured to accept TLS connections and present an appropriate certificate.

Never toggle encryption at one layer without checking the other two. A TCP connection can open cleanly yet fail during the **TLS handshake** or **Bolt handshake**.

### 10.3. Single Hostname for Internal and External Clients

In mixed environments, the same hostname `graph.example.com` can be served via **split-horizon DNS**: internal clients resolve to private IPs while external clients resolve to the public proxy. Both paths must genuinely reach endpoints supporting the same host/port and a valid certificate.

This is an **infrastructure strategy**, not a feature provided automatically by `server.bolt.advertised_address`. Do not use it if network policies or proxies cannot support it.

## 11. HTTPS and TLS: Having a Listener Is Not Enough

Separate two concerns:

- **Listen/advertise:** which host and port does the application contact?
- **Channel security:** is connection traffic encrypted and is server identity verified properly?

Enabling HTTPS typically requires more than just `server.https.enabled=true`. You must configure an **SSL policy**, certificate, and private key matching your Neo4j version and TLS design. Similarly, requiring TLS on Bolt requires configuring the appropriate SSL policy and TLS mode, or using a supported TLS proxy.

### 11.1. Security-Oriented Example

~~~properties
# Listener illustration, not a complete TLS configuration.
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.bolt.advertised_address=graph.example.com:7687

server.http.enabled=false
server.https.enabled=true
server.https.listen_address=0.0.0.0:7473
server.https.advertised_address=graph-admin.example.com:7473
~~~

**For this snippet to operate as a secured HTTPS service**, add certificate/SSL policy settings per your version. Never copy it and assume HTTPS is active without checking startup logs and TLS handshakes.

### 11.2. Certificates Must Match the Name the Client Uses

If Java Driver connects to `neo4j+s://graph.example.com:7687`, the TLS endpoint certificate must be issued and trusted for **graph.example.com** under the driver's hostname verification rules.

A certificate issued only for `localhost` or `db.internal` is not valid for `graph.example.com`. Switching the client URI to an IP can also trigger hostname mismatch errors if the certificate lacks a SAN for that IP.

### 11.3. 0.0.0.0 Is Not a Security Control

Listening on `0.0.0.0` can be reasonable inside a container or private network, but it:

- Does not define **who** is permitted access.
- Does not replace authentication/authorization.
- Does not replace TLS.
- Does not restrict source IPs on its own.
- Does not guarantee firewalls block public traffic.

Protect the server with authentication, firewalls/security groups, TLS, network policies, and the principle of **least privilege**. Avoid exposing administrative database access to the Internet without an approved security design.

## 12. Checking Effective Configuration in Neo4j

A common operational mistake is **editing the right file on the wrong instance**: for example, editing `neo4j.conf` on the host while Neo4j runs in a container with another volume/config, or setting environment variables that override file settings.

Where Neo4j version and privileges allow, inspect effective settings:

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
  'server.http.listen_address',
  'server.http.advertised_address',
  'server.https.enabled',
  'server.https.listen_address',
  'server.https.advertised_address'
]
RETURN name, value
ORDER BY name;
~~~

**Note:** `SHOW SETTINGS` availability, output columns, and permissions depend on version/edition and admin privileges. If you lack permissions, ask an operator to inspect effective settings or authorized monitoring tools.

### 12.1. Comparing Expected vs. Running Configuration

Maintain a verification table:

| Item | Expected | Observed |
|---|---|---|
| Bolt enabled | true | from SHOW SETTINGS/logs |
| Bolt listen | 0.0.0.0:7687 | actual socket inside container/host |
| Bolt advertise | graph.example.com:17687 | value returned by Neo4j |
| DNS for hostname | matching gateway IP | tested from Java host |
| Port mapping | 17687 → 7687 | NAT/Compose/Service config |
| TLS | valid certificate for hostname | tested via client handshake |
| Firewall | allowed sources only | verified rules and network path |

Seeing `graph.example.com:17687` in `SHOW SETTINGS` **does not prove external clients can reach it**. Network verification from the client is mandatory.

### 12.2. Checking for Legacy Setting Names

If applying Neo4j 4.x instructions to Neo4j 5.x, names like `dbms.connector.bolt.listen_address` may no longer apply to the newer version. Never add both old and new settings "just in case," as that can cause startup errors, warnings, or unpredictable behavior.

Choose **one version-matched set of settings** and check startup logs along with effective values. When upgrading, consult Neo4j's migration guide before bulk-renaming settings.

## 13. Testing from the Client's Actual Location

A test run on the Neo4j server does not represent a Java service running in another container, subnet, or across the Internet. Always test from **where the application actually runs**.

### 13.1. Checking DNS and Ports

In environments with standard network tools:

~~~bash
# On a Linux/macOS client host, if available:
getent hosts graph.example.com
nc -vz graph.example.com 7687
~~~

`getent` is not available on every OS; substitute an appropriate DNS tool such as `nslookup` or `dig`. `nc` only verifies opening a TCP connection to the port; it **does not** prove authentication, TLS, or Bolt routing succeeds.

On Windows PowerShell:

~~~powershell
Resolve-DnsName graph.example.com
Test-NetConnection -ComputerName graph.example.com -Port 7687
~~~

If DNS does not return the expected IP, fix **DNS/hostname**. If DNS is right but the port will not open, check **port mapping, firewall, listener, and network policy** before changing Neo4j usernames/passwords.

### 13.2. Checking Sockets on the Host or Inside a Container

On Linux with sufficient privileges:

~~~bash
ss -lnt
~~~

Look for listeners matching ports 7687, 7474, and 7473 and their bound IPs. If Neo4j runs in a container, inspect sockets **inside the target network namespace/container** as well as host port mappings; checking host sockets alone is insufficient.

### 13.3. Testing the Actual Protocol

Once TCP opens, test with **Cypher Shell** or Java Driver using the intended URI:

~~~bash
cypher-shell -a "neo4j+s://graph.example.com:7687" -u neo4j
~~~

This example assumes the server has Bolt TLS and a valid trust chain; the tool will prompt for a password securely. **Never place production passwords directly on the command line or in logs** where they may persist in shell history or process lists.

If TCP succeeds but Cypher Shell fails, inspect error messages for:

- Certificate, TLS version, and hostname issues.
- Authentication/authorization failures.
- Client/server version compatibility and Bolt handshake issues.
- Routing discovery failures when using the `neo4j://` scheme.
- Target database name and access privileges.

### 13.4. Separating Direct vs. Routing Errors to Isolate Root Cause

If permitted and supported by the architecture, test both URIs against the same endpoint:

~~~text
bolt+s://graph.example.com:7687    (direct)
neo4j+s://graph.example.com:7687   (routing)
~~~

If direct succeeds while routing fails, inspect the **routing table and advertised endpoints** instead of merely concluding port 7687 is open. Never use direct mode long-term to "dodge" a cluster configuration bug if the application truly requires routing.

## 14. Java Driver: URIs, Sessions, Connection Pools, and Connectivity Checks

In Java applications, connection URIs should be managed via environment configuration or a secret manager. `Driver` is typically created **once** and reused, while `Session` objects are short-lived per operation.

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jNetworkCheck {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        if (uri == null || user == null || password == null) {
            throw new IllegalArgumentException(
                "NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD are required"
            );
        }

        Config config = Config.builder()
            .withConnectionTimeout(5, TimeUnit.SECONDS)
            .withMaxConnectionPoolSize(30)
            .build();

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password), config)) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase("neo4j"))) {
                int value = session.executeRead(tx ->
                    tx.run("RETURN 1 AS ok")
                      .single()
                      .get("ok")
                      .asInt()
                );
                System.out.println("Neo4j query ok = " + value);
            }
        }
    }
}
~~~

This example uses common APIs from **Neo4j Java Driver 5.x**; when upgrading versions, check config signatures and environment requirements. Run the program **in the exact Java service environment** to verify end-to-end connectivity.

### 14.1. Analyzing `verifyConnectivity()`

`verifyConnectivity()` asks the driver to verify it can connect using the configured settings. It is useful at application startup or in health-check tooling.

However:

- One successful check does not guarantee every future connection will succeed.
- With routing/clustering, failover or alternate endpoints may only be exercised under real conditions.
- `RETURN 1` proves basic query execution works; it does not benchmark deep path queries, write privileges, or access to all databases.

Never instantiate a new `Driver` per request to "ensure connectivity": doing so defeats connection pooling and adds heavy overhead. Pool limits, timeouts, and transaction retries should be tuned for real load, not used as band-aids for broken DNS or advertised addresses.

### 14.2. Impact of Connection Pools and Network Ports

If many concurrent requests fail because they **cannot acquire a connection from the pool**, the cause may be an undersized pool, transactions holding connections too long, or server overload—distinct from `Connection refused` caused by listeners/ports.

Symptoms to distinguish:

| Symptom | Likely Cause |
|---|---|
| Immediate `Connection refused` | No matching listener, wrong port mapping, or active reject rule |
| TCP connection timeout | Firewall drop, bad route, or unresponsive endpoint |
| Cannot resolve hostname | DNS issue or invalid advertised name |
| TLS certificate mismatch | Certificate/SAN does not match hostname |
| Unusable routing table | Advertised endpoints unreachable, wrong topology or discovery |
| Pool acquisition timeout | Pool saturated/too small or long-running transactions |
| Authentication failed | Invalid credentials or security policy |
| Slow queries after connecting | Query plan, indexes, data volume, or contention; not necessarily network |

Rely on exact error messages, server/driver logs, and per-stage timing instead of blindly changing pool, timeout, and listener settings all at once.

## 15. Spring Data Neo4j: Configuring Addresses at the Application Layer

In Spring Boot applications using Spring Data Neo4j, common configuration goes through application properties:

~~~properties
# application.properties — directional example
spring.neo4j.uri=neo4j+s://graph.example.com:7687
spring.neo4j.authentication.username=app_user
spring.neo4j.authentication.password=... 
~~~

**Never commit real passwords to a repository.** Use environment variables, a secret manager, or an approved secrets backend. Spring Boot property names can vary across versions; verify against your application dependencies and documentation.

`spring.neo4j.*` properties configure the **client** inside the Java application. They **do not replace** `server.bolt.listen_address` or `server.bolt.advertised_address` on the Neo4j server. If the server advertises the wrong endpoint, fixing the bootstrap URI in Spring only fixes part of the path.

### 15.1. Verifying the Target Deployment Environment

In Kubernetes, a Spring service may inject `spring.neo4j.uri` from a ConfigMap/Secret or environment variable. Running locally on a laptop, `localhost` may work; inside a Pod, that same value points to the application Pod itself.

Never share a local config containing `localhost:7687` with a production container without overriding it. Verify the **effective value after Spring loads profiles/env** (without logging passwords), then run a `RETURN 1` test from the actual Pod.

## 16. Choosing an Advertised Address by Client Scope

Suppose a single database serves three client groups:

| Client Group | Access Path | Candidate Address |
|---|---|---|
| Java service on same host | Loopback | `localhost:7687` |
| Java service in same VPC | Internal DNS | `graph.internal.example:7687` |
| External client via proxy | Public FQDN + NAT | `graph.example.com:17687` |

The catch is that **a connector typically has one effective advertised address per configuration**. You cannot supply three different values to three client groups merely by setting three different bootstrap URIs.

Design approaches:

1. **Use one FQDN reachable from all groups** via split DNS and appropriate routing.
2. **Separate access paths by supported deployment/endpoint** rather than varying advertised addresses ad hoc per client.
3. **Consolidate clients** onto a unified network such as VPN/VPC and advertise the internal hostname.
4. For **clusters**, use per-member exposure/routing designs or supported proxies ensuring every endpoint returned to routing drivers is reachable.

Editing local `hosts` files on every client machine is not recommended as a long-term production solution: it is hard to govern, hides DNS problems, and breaks easily when IPs change.

## 17. Pre-Production Configuration Checklist

### 17.1. Neo4j Server

- [ ] Confirmed Neo4j version and **exact setting names** for that version.
- [ ] Enabled only required Bolt/HTTP/HTTPS connectors.
- [ ] `listen_address` binds to a real interface and port in the runtime environment.
- [ ] `advertised_address` uses a client-reachable hostname/port; never wildcard `0.0.0.0`.
- [ ] Understood inheritance from `server.default_listen_address` and `server.default_advertised_address`.
- [ ] Applied planned restarts/rolling restarts for settings requiring restart.
- [ ] Configured authentication, TLS/certificates, and authorization appropriately.
- [ ] If clustered, verified all member addresses returned to routing drivers.

### 17.2. DNS, Proxy, and Firewall

- [ ] DNS resolves accurately **from where the Java client runs**.
- [ ] Firewalls/security groups permit only required traffic.
- [ ] Docker port mappings or Kubernetes Services/Ingresses target the correct destination port.
- [ ] Reverse proxy supports **TCP Bolt**, not HTTP alone.
- [ ] If NAT translates ports, advertised port matches the client-facing port.
- [ ] TLS termination/passthrough aligns with client `+s`/`+ssc` schemes.
- [ ] Certificates are valid for the exact hostname used by clients.
- [ ] Private-network-only endpoints never leak into routing tables returned to external clients.

### 17.3. Java Application

- [ ] `bolt://` or `neo4j://` URI matches topology and routing needs.
- [ ] TLS is enabled with certificate verification for protected environments.
- [ ] `Driver` is reused; `Session` lifetimes are short.
- [ ] Target database name and credentials have appropriate privileges.
- [ ] `verifyConnectivity()` and `RETURN 1` pass from the **actual Pod/container/host**.
- [ ] Logs/tracing distinguish DNS, TCP, TLS, auth, routing, and pool failures.
- [ ] Timeouts/pools/retries are tuned after confirming network paths are healthy.

## 18. Common Errors and Troubleshooting Guide

| Symptom | Possible Cause | Inspection/Fix Step |
|---|---|---|
| Works locally, fails from another host | Listening only on `127.0.0.1` or firewall blocked | Inspect listen sockets, network, and rules; avoid opening publicly without controls |
| Docker publishes 17687 but Java tries 7687 | Confused host port with container port | Check port mapping, URI, and advertised port |
| Browser loads UI but Cypher fails | HTTP open, Bolt blocked | Test port 7687 from browser/client location |
| External Java receives `*.svc.cluster.local` | Routing table returns internal Pod/Service hostnames | Design advertised endpoints/exposure for external clients |
| Direct connects but routing fails | Routing table endpoint unreachable | Check each server's advertised address |
| "Cannot bind address" on startup | Listen IP not on local interface or port in use | Use valid local IP; inspect bound sockets/ports |
| Changed advertised address with no effect | Restart pending or config overridden | Check `SHOW SETTINGS` and startup logs |
| TLS handshake fails | Proxy TLS, certificate, or policy mismatch | Check scheme, cert/SAN, and termination layer |
| Raising pool size still gives connection refused | Pool tuning cannot fix listener/firewall | Check TCP reachability and listen address |
| HTTP port 7474 open to Internet | Admin connector needlessly exposed | Restrict or disable HTTP; use HTTPS/VPN as needed |
| Set `advertised=0.0.0.0:7687` | Used wildcard bind as client address | Use a client-routable FQDN/IP |
| Neo4j 4.x config placed in Neo4j 5.x | Deprecated/wrong setting names | Check exact version docs and effective settings |
| Multi-NIC server, DNS points to wrong NIC | DNS/listen interface mismatch | Align bind address, routing, and DNS |
| Timeouts spike under heavy queries | Query, pool, or DB contention | Inspect query plans, pool wait, CPU/locks—not just network |

### 18.1. Suggested Triage Flow

~~~mermaid
flowchart TD
    A["Java Driver cannot connect"] --> B{"Does DNS resolve accurately?"}
    B -->|No| C["Fix hostname/DNS for client network"]
    B -->|Yes| D{"Can TCP connect to host:port?"}
    D -->|No| E["Check listener, firewall, NAT, Service"]
    D -->|Yes| F{"Does TLS/Bolt handshake succeed?"}
    F -->|No| G["Check certificate, scheme, proxy"]
    F -->|Yes| H{"Does authentication succeed?"}
    H -->|No| I["Check credentials/privileges"]
    H -->|Yes| J{"Is routing endpoint reachable?"}
    J -->|No| K["Check advertised address/cluster"]
    J -->|Yes| L["Inspect database, pool, query, and load"]
~~~

This flowchart is a triage workflow, not a strict protocol ordering across all handshake/routing versions. A single issue can manifest across multiple layers; detailed logs confirm causes instead of guessing.

## 19. Practice Exercises

### Exercise 1 — Different Listen and Advertised Addresses

Neo4j runs in a container listening on `0.0.0.0:7687`. Docker publishes `17687:7687`. A Java service outside Docker connects using hostname `db.example.com`.

**Question:** What Bolt host:port should be advertised?

**Answer:** If `db.example.com:17687` resolves via DNS and forwards into the container, the appropriate advertised address is `db.example.com:17687`. The internal listen address can remain `0.0.0.0:7687`.

### Exercise 2 — Cannot Connect from Another Machine

The config contains:

~~~properties
server.bolt.listen_address=127.0.0.1:7687
server.bolt.advertised_address=graph.internal.example:7687
~~~

A Java app running on another host in the same VPC times out.

**Question:** Is changing only the advertised address enough?

**Answer:** No. The server only binds Bolt on loopback, so other hosts cannot reach it directly. Configure the listener on an appropriate network interface or use a tunnel/proxy, and check firewall rules. Do not expose all interfaces to the Internet unnecessarily.

### Exercise 3 — Browser Loads UI but Cypher Fails

HTTP 7474 is open; Bolt 7687 is blocked by a firewall.

**Question:** Why does the UI load while queries fail?

**Answer:** HTTP serves the web interface and does not replace the Bolt connection required for database operations. Test Bolt reachability from the browser/driver location and open it only to authorized scopes.

### Exercise 4 — Cluster Bootstrap Succeeds, Queries Fail

An external client connects to Kubernetes via `db.example.com`, but the routing table returns `neo4j-1.svc.cluster.local:7687`.

**Question:** Where is the problem?

**Answer:** The advertised endpoint for cluster members is not reachable from outside the cluster. Design per-member exposure/routing or a supported proxy instead of just tweaking the bootstrap URI.

### Exercise 5 — Wildcard Advertised Address

A configuration sets:

~~~properties
server.bolt.advertised_address=0.0.0.0:7687
~~~

**Question:** Why is this configuration wrong?

**Answer:** `0.0.0.0` specifies binding across interfaces, not a concrete hostname/IP a client can connect to. The advertised address must be routable from the client's network scope.

### Exercise 6 — TLS URI and Certificate

Java Driver uses `neo4j+s://graph.example.com:7687`, but the endpoint certificate only has a SAN for `db.internal`.

**Question:** Should you switch to `neo4j+ssc://` to silence the production error?

**Answer:** That should not be used as a production solution. Provision a valid certificate for `graph.example.com` or update the endpoint to match the certified name while preserving trust-chain and hostname verification.

### Exercise 7 — Java Service Inside Docker

In a Compose network, the Java service uses `bolt://localhost:7687`, while Neo4j runs in another container named `neo4j`.

**Question:** Why is `localhost` wrong?

**Answer:** `localhost` inside the Java container refers to the **Java container itself**. Use the endpoint visible to the Java container—typically `neo4j:7687` on the shared Docker network—along with matching advertised/routing configuration.

### Exercise 8 — Edited neo4j.conf Yet Error Persists

An operator updated `server.bolt.advertised_address` without restarting. Java still receives the old routing endpoint.

**Question:** What verification steps should follow?

**Answer:** Confirm the right instance, config file, and environment variables, check effective settings, perform a restart if required by the setting, and re-test from the client. Never assume file edits take effect immediately.

## 20. Key Takeaways

The **listen address** answers **"which interface/port does the Neo4j process accept connections on?"**; the **advertised address** answers **"which hostname/port should clients contact?"**. They can differ due to NAT, Docker, Kubernetes, reverse proxies, or clustering. `0.0.0.0` is often right for binding, but it is **never a reachable advertised address**.

Reliable network configuration must be verified **from the exact runtime environment of the Java Driver/Spring Data Neo4j app**, layer by layer across DNS, TCP, firewalls, proxies, TLS, authentication, and routing. When using `neo4j://`, every member address returned by routing must also be reachable—not just the bootstrap endpoint. Always use **exact setting names for your Neo4j version**, protect connectors with least-privilege networking/TLS/auth, and verify effective settings after deployment.
