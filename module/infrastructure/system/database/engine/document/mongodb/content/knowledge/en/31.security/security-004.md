# Network Restrictions, bindIp, Firewalls, and Atlas Access Control in MongoDB

An application can have the exact right MongoDB username and password yet still fail to connect because the database only listens on `127.0.0.1`. Conversely, an application might connect effortlessly because the database listens on every interface and the firewall lets the entire Internet reach port 27017. The second setup is convenient for brief testing, but creates a massive attack surface if left uncontrolled.

In the **Security** chapter of the **Database Engine Document MongoDB** module, this lesson on **Network Restrictions, bindIp, Firewalls, and Atlas Access Control** teaches how to protect the path from applications to MongoDB. It does not treat “can connect” as the sole criterion: a sound deployment also ensures **only the right sources, services, and identities can access it**, over an encrypted channel.

After this lesson, you will be able to distinguish `net.bindIp` from firewalls, understand localhost/private/public IPs, control replica set and sharded cluster network flows, configure the Atlas IP Access List conceptually, choose between public connections and private networking, diagnose errors by layer, and apply least privilege in deployment.

> **Scope:** all IP addresses and hostnames in examples are illustrative lab values. Never open MongoDB ports on public hosts, disable authentication, or alter production firewalls just to test these examples.

## 1. Path of a MongoDB Connection

A typical connection traverses multiple layers:

```text
Java / Node.js / mongosh Application
              |
              v
        DNS / SRV lookup
              |
              v
       Route / NAT / VPN
              |
              v
 Firewall / security group / network ACL
              |
              v
        Server IP + TCP port
              |
              v
        mongod/mongos bindIp
              |
              v
       TLS and certificate verification
              |
              v
      MongoDB authentication (AuthN)
              |
              v
       Authorization (AuthZ / RBAC)
              |
              v
       Database and collection
```

A connection only works when every relevant layer is consistent:

- DNS resolves the hostname to the right address/endpoint.
- The client has a route to the endpoint and is permitted outbound traffic.
- Server/cloud firewalls allow the appropriate source to the target port.
- MongoDB is actually listening on that IP:port.
- Client and server agree on TLS and trust the appropriate certificates.
- The client has valid credentials and sufficient database permissions.

For example, **elevating a role to `root` will not fix a TCP timeout**, and **adding an IP to a firewall will not fix a wrong password**. Identify which layer is failing before changing configurations.

### Four Frequently Conflated Questions

| Layer | Question | Example |
| --- | --- | --- |
| Listener | At **which server address** does the process accept connections? | `127.0.0.1`, `10.10.20.12` |
| Firewall | **Which client sources** are allowed to reach that destination/port? | `10.20.30.0/24` to TCP 27017 |
| Authentication | **Who** is the client? | SCRAM user, X.509 identity |
| Authorization | **What** can that identity do? | `read` or `readWrite` on a DB |

TLS is a layer protecting transit and server identity; it does not replace any item in the table above.

## 2. Build a Threat Model Before Configuring

Consider a system with a web frontend, an API backend, and MongoDB:

```text
Internet Users
       |
       v
  HTTPS API Gateway
       |
       v
Backend private subnet
  10.20.30.10, 10.20.30.11
       |
       v
MongoDB private host
      10.10.20.12
```

End users only need to call the HTTPS API—**they never need direct connections to the database port**. Only backend servers, internal cluster components, and authorized administrative hosts have a reason to reach MongoDB.

Risks to consider:

1. Exposing TCP 27017 over public IPv4/IPv6.
2. Committing passwords or URIs into repositories.
3. Granting overly broad permissions to a service credential.
4. Eavesdropping on traffic if TLS is absent.
5. A compromised application server reaching the DB because it shares the network.
6. An overly broad firewall rule or Atlas access list entry outliving its intended duration.
7. Adding cluster members or changing NAT egress IPs without updating policies.

The baseline policy is **minimize network exposure**, while **never treating being on a private network as sufficient for trust**.

## 3. What Does `net.bindIp` Mean?

In self-managed MongoDB, `net.bindIp` specifies **which local network addresses `mongod` or `mongos` listens on**. It is not a list of allowed client IPs.

Suppose the MongoDB server has:

```text
Loopback:          127.0.0.1
Private interface: 10.10.20.12
Public interface:  203.0.113.12
```

The address `203.0.113.12` belongs to a documentation range, not a real server address.

### Allow Only Applications on the Same Host

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1"
```

MongoDB listens only on IPv4 loopback. A process on the same host can connect via `mongodb://127.0.0.1:27017`. Hosts in another subnet cannot use the server's private IP to reach this listener.

### Allow Listening on a Private Interface

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.20.12"
```

MongoDB listens on loopback and the host's private NIC. Applications on other hosts **can attempt** to connect to `10.10.20.12:27017` if routing, firewalls, TLS, AuthN, and AuthZ all permit it.

### Mistake: Putting the Client IP into `bindIp`

The application has IP `10.20.30.10` and the DB server has IP `10.10.20.12`. If on the DB server you configure:

```yaml
net:
  bindIp: "10.20.30.10"
```

the process may fail to bind because `10.20.30.10` **does not belong to the MongoDB host**. To restrict access to client `10.20.30.10`, use a firewall/source ACL, not `bindIp`.

**Remember:** `bindIp` selects the **server's local destination address**, whereas a firewall selects the **permitted source addresses**.

## 4. Comparing Localhost, Private IPs, and Wildcards

| Address | Effect | Notes |
| --- | --- | --- |
| `127.0.0.1` | IPv4 loopback | Suitable for same-host development |
| `::1` | IPv6 loopback | Requires proper IPv6 setup |
| `10.10.20.12` | A private IPv4 assigned to the server | Suitable for private backend networking |
| `203.0.113.12` | Illustrative public IPv4 | Never expose a database publicly without necessity |
| `0.0.0.0` | All IPv4 interfaces | May include public NICs |
| `::` | IPv6 wildcard | Requires separate IPv6 exposure review |

If you configure:

```yaml
net:
  port: 27017
  bindIp: "0.0.0.0"
```

MongoDB no longer restricts itself to loopback or a specific private interface. If the host has a public NIC and network rules permit it, the MongoDB port may become reachable from the Internet.

### `net.bindIpAll`

MongoDB supports listening on all configured interfaces, e.g.:

```yaml
net:
  port: 27017
  bindIpAll: true
```

Depending on startup method, the equivalent CLI flag may be `--bind_ip_all`. **Do not arbitrarily combine `net.bindIp` and `net.bindIpAll`**: they are mutually exclusive listener-selection options.

An isolated container may need `bindIpAll` inside its container network namespace to accept traffic from other containers, but that **does not prove** the host and published container ports are safe. Always check actual exposure.

### When `bindIp` Is Omitted

In many self-managed MongoDB defaults, MongoDB listens only on localhost. However, packages, container images, Helm charts, or automation can override defaults. Therefore **inspect the running configuration and socket listeners** rather than assuming any deployment omitting `bindIp` is safe.

## 5. Watch Out for IPv6

Checking IPv4 is insufficient if the server has IPv6. A host may have:

```text
IPv4 private: 10.10.20.12
IPv6 global:  2001:db8:1234::12
```

`2001:db8::/32` is an IPv6 documentation prefix. Check:

- `net.ipv6` and MongoDB's IPv6 listener configuration.
- `::1`, `::`, or specific IPv6 addresses in the socket list.
- DNS AAAA records and IPv6 routes.
- Cloud/host firewall rules for IPv6.
- Whether client DNS resolvers prefer IPv6.

A host can block all unwanted inbound IPv4 while still leaving an IPv6 entry path open if rules are missing. **Never conclude a database is not public just because a single IPv4 probe timed out.**

## 6. How Does a Firewall Differ from `bindIp`?

Suppose the DB binds `10.10.20.12:27017` and a firewall allows source `10.20.30.10`.

```text
Client: 10.20.30.10
       |
       v
Router / subnet route
       |
       v
Firewall: allow source 10.20.30.10
       |
       v
Server interface 10.10.20.12:27017
       |
       v
mongod listener
```

If the firewall blocks it, packets never reach the listener. If the server does not bind `10.10.20.12`, even if the firewall allows it, no MongoDB socket exists there to accept the connection.

### Least-Privilege Sample Rules

| Source | Destination | Protocol | Action |
| --- | --- | --- | --- |
| `10.20.30.10/32` | `10.10.20.12:27017` | TCP | Allow |
| `10.20.30.11/32` | `10.10.20.12:27017` | TCP | Allow |
| Managed bastion | `10.10.20.12:27017` | TCP | Allow with monitoring |
| Any Internet source | `10.10.20.12:27017` | TCP | Deny |

A **new allow rule** does not necessarily remove or override broader existing allow rules. Exposure reviews must inspect the **complete set of rules** in the active firewall.

## 7. Multiple Firewall Layers: Host, Cloud, Network ACL, and Egress

A connection path can cross:

1. Host firewall: UFW/nftables/iptables on Linux, Windows Defender Firewall on Windows.
2. Cloud security group or network firewall protecting the VM/NIC.
3. Subnet network ACL, which may be stateless and require bidirectional rules.
4. Routers, VPNs, VPC/VNet peering, NAT gateways.
5. Kubernetes NetworkPolicy or service mesh when enforced by the network plugin.
6. Corporate/partner perimeter firewalls.

**Allowing traffic at one layer does not bypass a block at another layer.**

Because clients initiate MongoDB connections, you need:

- Client egress to the DB's hostname/IP and port.
- Server ingress from the source IP it observes.
- Return traffic allowed under stateful or stateless policies.

If a corporate firewall blocks outbound TCP 27017, the app still cannot reach Atlas even after adding its IP to the Atlas Project IP Access List.

### Stateful vs. Stateless Filtering

Security groups and host firewalls typically track connection state, automatically handling return packets for established connections. Some subnet-level network ACLs are **stateless**, requiring explicit rules for return traffic and ephemeral client ports. Never apply a blanket “open inbound 27017 is enough” recipe across all network layers.

## 8. MongoDB Ports, Replica Sets, and Sharded Clusters

`mongod` and `mongos` typically use **TCP 27017** unless configured otherwise. Some environments or startup modes use other ports, such as 27018/27019 in specialized setups. **Actual ports depend on the deployment**, not a single fixed diagram.

### Replica Set

```text
Application
    |
    +----> rs-a.example:27017
    +----> rs-b.example:27017
    +----> rs-c.example:27017
```

Drivers are replica-set topology aware: they discover member hosts after connecting to a seed. If the client can only reach `rs-a` while firewalls block `rs-b` and `rs-c`, connections may initially succeed and then fail once another node becomes primary.

### Sharded Cluster

```text
Application
    |
    v
  mongos endpoint
    |
    +----> shard replica set A
    +----> shard replica set B
    +----> config server replica set
```

Applications normally connect through **`mongos`** or a managed router endpoint—never directly reading sharded collections from an arbitrary shard node.

### Security Traffic Segmentation

- Client-to-router/replica-set-member traffic: only authorized app subnets/ops sources.
- Replica-set member-to-member traffic: only relevant members, with internal authentication.
- Shard/config-server/`mongos` traffic: only required cluster components.
- Admin/backup/monitoring: only from authorized admin hosts under separate policies.

Never open all internal cluster ports to the Internet simply because a cluster has multiple nodes. **HA needs proper internal network paths, not broad public exposure.**

## 9. Network Reachability Does Not Mean Data Access Is Permitted

Three layers sit behind the network:

**TLS:** encrypts traffic and verifies server certificate/hostname.

**Authentication (AuthN):** identifies which user/service the client is via SCRAM, X.509, or supported mechanisms.

**Authorization (AuthZ):** checks whether the user holds roles permitting the command on the target namespace.

Example read-only account:

```text
service: reporting-reader
MongoDB database: ordersdb
Role: read
Not granted: readWrite/root/clusterAdmin
```

An account that logs in yet gets `not authorized` on `insertOne()` shows **access control is working**, not a firewall error.

### Example `mongod.conf` with TLS and Authorization

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.20.12"
  tls:
    mode: requireTLS
    certificateKeyFile: "/etc/mongodb/tls/server.pem"
security:
  authorization: enabled
```

This is a **partial illustrative configuration**, not a full production config. You also need users/roles, certificate chains and CAs, private-key permissions, and secret rotation; replica sets and sharded clusters also require proper internal member authentication (such as keyfile or X.509). Editing `mongod.conf` may require a controlled restart or rolling rollout.

**Never use `tlsInsecure` or bypass certificate validation as a permanent fix.** On TLS hostname mismatch, fix the hostname, certificate SAN, and CA trust to match the deployment.

## 10. Lab Configurations and Private Environments

### Same-Machine Lab

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1"
```

Same-host app uses:

```text
mongodb://127.0.0.1:27017/appdb
```

A lab might not yet have production auth/TLS, but **never reuse this configuration directly on a public server or any environment holding sensitive data**. Loopback can still be accessed by malicious processes on the same host.

### Private Server

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.20.12"
  tls:
    mode: requireTLS
    certificateKeyFile: "/etc/mongodb/tls/server.pem"
security:
  authorization: enabled
```

Paired with network policy:

```text
ALLOW tcp/27017
  source: 10.20.30.10/32, 10.20.30.11/32
  destination: 10.10.20.12
DENY tcp/27017
  source: everything else
```

This illustrates combining **listener + network ACL + TLS + auth**. Internal cluster config and infrastructure management must still follow dedicated policies.

## 11. Linux and Windows Firewalls: Rule Examples

On Linux with UFW, an example allow rule:

```bash
# Sample only; verify current policy before applying.
sudo ufw allow from 10.20.30.0/24 to 10.10.20.12 port 27017 proto tcp

# Read-only rule status check.
sudo ufw status verbose
```

On Windows PowerShell:

```powershell
# Sample rule, requires appropriate privileges; do not run arbitrarily in production.
New-NetFirewallRule -DisplayName "MongoDB trusted app subnet" -Direction Inbound -Protocol TCP -LocalPort 27017 -RemoteAddress 10.20.30.0/24 -Action Allow
```

Both commands **only add an allow rule**—they do not automatically ensure the overall policy blocks other sources. Before enabling or changing default firewall policies over SSH/remote sessions, verify administrative access paths and rollback procedures so you do not lock yourself out.

## 12. Docker: Container Localhost Is Not Host Localhost

Docker creates its own network namespace:

```text
Host: 127.0.0.1
   |
   +--> Published port
             |
             v
       MongoDB container
       container's 127.0.0.1
       Container network address
```

If `mongod` binds only loopback **inside the container**, connections targeting the container's network address via NAT can fail. In a lab, you might let MongoDB listen on the container interface while publishing the port only to the host's loopback:

```bash
# Illustrates container networking only.
# No auth, persistent volume, or production TLS.
docker run --rm --name mongo-lab -p 127.0.0.1:27017:27017 mongo:7 --bind_ip_all
```

Idea: `--bind_ip_all` sets the container listener; `-p 127.0.0.1:27017:27017` binds the published host port to IPv4 loopback in supported Docker setups. **Always verify host firewalls, IPv6, Docker version, network drivers, and other access paths**: never assume one port-mapping flag secures every topology.

If the app and MongoDB run on the same Docker Compose network, use the internal service hostname and **do not publish the MongoDB port to the host**.

## 13. Kubernetes: Service and NetworkPolicy

Kubernetes involves multiple layers:

```text
Application Pod
      |
      v
   Service DNS
      |
      v
  MongoDB Pod / Endpoint
```

**Kubernetes Service** routes to pods; **NetworkPolicy** restricts traffic between endpoints when supported/enforced by the CNI; **`bindIp`** controls the socket listener inside the container; and **TLS/AuthN/AuthZ** still govern MongoDB access.

Do not assume `Service type: ClusterIP` automatically means “only one app pod can connect”. Many clusters allow unrestricted pod-to-pod traffic unless a NetworkPolicy or other control blocks it.

Avoid exposing `NodePort` or a public `LoadBalancer` for the database just because an external app cannot resolve cluster service DNS. Consider private connectivity, VPNs, bastions, or controlled gateways.

## 14. MongoDB Atlas: How Does It Differ from Self-Managed?

In **MongoDB Atlas**, typical users **do not directly edit `mongod.conf` or `net.bindIp` on Atlas-managed nodes**. Atlas provides project/network controls and public or private connectivity options.

Diagram for the public path:

```text
Backend app
    |
    v
DNS SRV / Atlas endpoint
    |
    v
Client egress / NAT
    |
    v
Atlas public network endpoint
    |
    v
Atlas Project IP Access List
    |
    v
TLS + MongoDB database user/roles
    |
    v
Cluster data
```

These layers are independent in purpose: **IP Access List** controls which sources can connect over the corresponding public path, **Database Access** controls login users and data privileges, and **project/organization roles** control what managers can modify in the Atlas console/API.

## 15. Atlas Project IP Access List

For clusters/public paths controlled by the Project IP Access List, Atlas lets you add **client/application public IPv4 addresses or source CIDRs**.

| Illustrative Value | Purpose | Assessment |
| --- | --- | --- |
| `198.51.100.24/32` | A static NAT IP | Narrow, good when exact source |
| `203.0.113.40/32` | App egress IP | Narrow, verify in runtime |
| `198.51.100.0/28` | A bounded public range | Use only when entire range is needed |
| `0.0.0.0/0` | Any public IPv4 source | **Never leave permanently open** |

The ranges `198.51.100.0/24` and `203.0.113.0/24` are **documentation ranges**, not real IPs to allowlist.

### Which IP Should Be Allowlisted?

Suppose:

```text
Laptop on Wi-Fi:   192.168.1.25
      |
      v
Office NAT:        198.51.100.24
      |
      v
Atlas public endpoint
```

Atlas sees the **public egress address after NAT**, not the laptop's private IP. Therefore, adding `192.168.1.25/32` to the public access list normally will not let the laptop connect over the Internet.

For an app in Kubernetes:

```text
App pod:           10.2.1.15
Cloud NAT gateway: 198.51.100.24
Atlas source seen: 198.51.100.24
```

Determine the egress IP from the **actual runtime environment** using an organization-approved method. Do not guess from pod, node, or subnet IPs.

### Why Can an IP List Work Intermittently?

- A laptop switches Wi-Fi or turns on a VPN.
- The app routes through multiple NAT gateways across availability zones.
- CI runners use dynamic public IPs per job.
- Serverless apps change egress IPs when scaling.
- A NAT gateway was replaced without updating Atlas rules.

If a workload has two valid NAT IPs, allowlist both or standardize on static egress. **Never use `0.0.0.0/0` as a quick fix for unstable egress.**

### IP Access List Does Not Grant Data Read Access

An allowlisted source IP can only **initiate connections** to the endpoint—it does not grant MongoDB credentials. Multiple services may share a NAT IP; each service still needs its own database user/role.

### Atlas Access List Management Workflow

1. Identify the **right project and cluster**.
2. Determine whether the app uses a **public endpoint** or private connectivity.
3. Gather actual public egress IPs/CIDRs.
4. Under the project's **Network Access / IP Access List**, add a narrow rule with a description and owner.
5. For temporary access, use expiry/temporary entries where supported.
6. Verify outbound egress firewalls on the app side.
7. Verify TLS, DB username/password, and roles.
8. Revoke IPs once no longer needed.

Menu names and exact options can vary by deployment; consult the active Atlas UI/documentation.

## 16. Atlas Database Access and Project Roles

Distinct permission types:

| Type | Governs | Example |
| --- | --- | --- |
| Atlas Network Access | Allowed IPs/CIDRs or private connectivity | NAT `198.51.100.24/32` |
| Atlas Database Access | Database users and authentication | `orders-service` |
| Database RBAC | Commands the user can run | `readWrite` on `ordersdb` |
| Atlas Project/Org roles | Who manages resources via Atlas UI/API | Project owner/operator |

**Permission to log in to the Atlas console does not automatically make someone a MongoDB database user.** Atlas management accounts and application data-access users must never be conflated.

Example policy:

```text
Application: orders-service
Network: static egress NAT /32 or private endpoint
Database user: orders-service
Role: readWrite on ordersdb
Do not grant: root/atlasAdmin unless required
Secrets: fetched from secret manager
Transport: TLS with certificate validation enabled
```

Never place administrative accounts inside production service URIs so an application vulnerability cannot escalate into full cluster administration.

## 17. Private Endpoints and VPC/VNet Peering on Atlas

Many organizations want to keep MongoDB traffic off the public Internet. Depending on cloud provider, region, tier, and deployment features, Atlas supports **private connectivity** options such as:

- **Private Endpoints** built on AWS PrivateLink, Azure Private Link, or equivalent mechanisms.
- **VPC/VNet peering** between the application network and the Atlas-managed network where supported.

### Private Endpoint

```text
Application VPC/VNet
        |
        v
Private DNS / Private Endpoint IP
        |
        v
Provider private connectivity
        |
        v
Atlas cluster endpoint
        |
        v
TLS + database user + roles
```

Verify the endpoint is created and approved/associated, check security groups, DNS, routing, and the official **private connection string**. Creating an endpoint **does not mean** the app is using it: if the app still resolves URIs to public hosts, traffic can still traverse the public path.

### Peering

Peering typically requires non-overlapping CIDRs, matching routes and DNS, and security group/network ACL rules on both sides. It only provides a **network path**—it does not grant database permissions.

### Private Access and Public IP Lists

Do not assume every private endpoint obeys the exact same rules as the public IP Access List, or that enabling private connectivity automatically deletes all public connection paths. Exact behavior depends on endpoint/deployment type. Verify the **actual connection path**, which endpoints are enabled, and their respective access controls.

**Goal:** not just “add a private path”, but also ensure unnecessary public paths do not remain open.

## 18. `mongodb+srv://`, DNS, and Firewalls

Atlas commonly provides URIs formatted as:

```text
mongodb+srv://<cluster-hostname>/<database>
```

Placeholder example:

```text
mongodb+srv://cluster.example.mongodb.net/ordersdb
```

When using `mongodb+srv://`, the driver queries DNS SRV/TXT records per specification to discover hosts and connection options. Therefore:

- Client DNS must resolve the required records.
- Firewalls must permit outbound access to the **actual advertised hosts/ports**, not just a single temporarily copied IP.
- Clients must trust a valid TLS certificate for the hostname.
- Network proxies/DNS firewalls must not block the required lookups.

If DNS SRV lookup fails, broadening the Atlas access list **will not fix DNS**. If SRV succeeds yet TCP to member hosts is blocked, the driver will still report a server selection timeout.

Never replace an Atlas SRV URI with a random static IP returned by DNS, because topology, certificate names, and endpoints can change.

## 19. Inspecting Listeners on Self-Managed MongoDB

On Linux:

```bash
# Inspect listening sockets; makes no system changes.
ss -lntp | grep 27017
```

Illustrative output:

```text
LISTEN ... 127.0.0.1:27017 ...
```

This means the listener is on IPv4 loopback only.

Another output:

```text
LISTEN ... 10.10.20.12:27017 ...
```

means a listener exists on the private IP. **It does not prove firewalls allow the client source**, TLS is valid, or the user has permissions.

On Windows:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 27017
```

If no listener appears, check whether `mongod` is running, inspect startup logs, verify the active config file, check for port conflicts, and confirm the IP in `bindIp` actually belongs to the host.

## 20. Testing TCP from an Authorized Application Host

From the **actual application host** or an authorized runtime environment:

Linux/macOS:

```bash
nc -vz db.internal.example 27017
```

Windows:

```powershell
Test-NetConnection db.internal.example -Port 27017
```

These commands only test **DNS/routing/TCP**—they do not verify TLS, authentication, or collection read permissions. Use them only against your own or authorized endpoints; never scan external IP ranges.

If TCP fails:

1. Are the hostname and port correct?
2. Is DNS resolving a private or public IP?
3. Are client egress and routing correct?
4. Is the server listener bound to the target IP?
5. Do host firewalls, security groups, and network ACLs allow the source?
6. For Atlas, is the public egress IP in the project IP list, or is the private endpoint configured properly?

Only after TCP succeeds should you focus on MongoDB protocol, TLS, and database authentication.

## 21. Testing with `mongosh` Without Exposing Passwords

Self-managed example with TLS enabled and `authSource` set to `admin`:

```bash
mongosh "mongodb://db.internal.example:27017/appdb?tls=true" --username appReader --authenticationDatabase admin --password
```

Atlas example with placeholders:

```bash
mongosh "mongodb+srv://cluster.example.mongodb.net/appdb" --username appReader --password
```

Adjust hostnames and users to match the real environment. Certain auth/certificate mechanisms require additional options. Never put passwords directly on the command line or in source code where they can leak into shell history, process metadata, or logs.

After connecting:

```javascript
db.adminCommand({ ping: 1 })
```

A successful `ping` confirms MongoDB can respond to that command—**it does not mean the user can read/write every collection**. Test an actual permitted operation to confirm the service's RBAC.

## 22. Classifying Connection Errors by Layer

| Symptom | Check First | Interpretation |
| --- | --- | --- |
| `ENOTFOUND`, SRV lookup error | DNS | Resolver/hostname/SRV/TXT or private DNS |
| `ECONNREFUSED` | Listener/port | No listening socket or host reset |
| `ETIMEDOUT` | Route/firewall | Packets dropped, bad NAT/route, unresponsive target |
| Server selection timeout | Topology/network | One or more members/routers unreachable |
| TLS handshake/certificate error | TLS | CA, SAN/hostname, expired cert, or policy mismatch |
| `Authentication failed` | AuthN | Username, password, `authSource`, or mechanism |
| `not authorized` | AuthZ | User logged in, missing role |
| Fails only in Docker | Container network | Loopback namespace, service DNS, port mapping |
| Fails only in CI | Egress IP/network | Runner has a different source IP than laptop |
| Fails on replica set failover | Member reachability | Only seed node was firewall-allowed |
| Fails only in one availability zone | NAT/routing | One egress IP missing from Atlas list |

These messages are **diagnostic hints**, not one-to-one mappings. Drivers often surface a generic server selection timeout wrapping nested causes; always inspect endpoint details and root errors.

### Investigation Flowchart

```text
Application cannot connect
       |
       v
Does DNS/SRV resolve?
    |            |
   No           Yes
    |            |
    v            v
 Fix DNS     Route/TCP open?
                 |         |
                No        Yes
                 |         |
                 v         v
          bindIp/firewall  TLS valid?
                            |      |
                           No     Yes
                            |      |
                            v      v
                       CA/cert   AuthN OK?
                                  |     |
                                 No    Yes
                                  |     |
                                  v     v
                              Credentials  AuthZ OK?
                                             |    |
                                            No   Yes
                                             |    |
                                             v    v
                                           Roles Success
```

Never widen IP ranges or disable TLS validation before identifying which layer is failing.

## 23. Case A: Java App on the Same Host as MongoDB

```text
Developer laptop:
  Java app
  mongod: 127.0.0.1:27017
```

If the app shares the network namespace with MongoDB, a `localhost` URI makes sense. **You do not need `bindIpAll` or to open ports to the LAN.** However, if the Java app runs inside one container while MongoDB runs on the host or another container, `127.0.0.1` inside the Java container is no longer MongoDB's loopback.

The fix is proper network topology, not changing MongoDB's password.

## 24. Case B: App VM and MongoDB VM in Different Subnets

```text
App VM: 10.20.30.10
       |
       | TCP 27017, TLS
       v
DB VM: 10.10.20.12
```

Design:

- `mongod` binds `10.10.20.12` (and optionally `127.0.0.1` for local needs).
- Firewall allows source `10.20.30.10/32` to destination TCP 27017.
- Cloud routing/security groups permit the private path.
- MongoDB enables TLS and authentication.
- The service user has only the required DB role.

If connections fail, inspect actual listeners and rules. **Do not reflexively change `bindIp` to `0.0.0.0`.**

## 25. Case C: Atlas with Static NAT Egress

```text
App private IP: 10.2.1.15
NAT public IP: 198.51.100.24
Atlas public endpoint
```

Steps:

1. Allow public source `198.51.100.24/32` in the right Atlas project for the public path.
2. Verify app outbound traffic to Atlas hosts/ports.
3. Use the official SRV URI and TLS.
4. Provision a dedicated database user and limited role.
5. With multiple zones/NATs, verify all valid egress IPs.
6. Monitor if egress IPs change.

Adding the private IP `10.2.1.15` to the public allowlist does not replace the NAT IP.

## 26. Case D: Atlas Private Endpoint

```text
App VPC/VNet
      |
Private DNS + Private Endpoint
      |
Atlas
```

Checklist:

- Endpoint created and approved/associated with the right deployment.
- DNS resolves the right hostnames and addresses for the private connection.
- Network routes and security groups permit traffic.
- The application uses the **private endpoint URI**, not accidentally a public URI.
- Database users/TLS/roles remain properly configured.
- No unintended broad public path remains open.

Private connectivity **does not prevent a compromised app from reading every database**; credentials and RBAC remain mandatory boundaries.

## 27. Case E: Mobile App Connecting Directly to Atlas

A mobile app across thousands of users has IPs changing with Wi-Fi, carriers, and VPNs. Embedding a MongoDB password in the app package and having mobile clients connect directly to Atlas causes:

- Inability to maintain narrow public allowlists per device.
- High risk of extracting database credentials.
- Difficulty enforcing business rules and rate limits at a backend tier.
- Clients reaching DB APIs beyond UI intent if roles are broad.

Appropriate architecture:

```text
Mobile app
     |
HTTPS API (user authentication/authorization)
     |
Backend server with static egress/private endpoint
     |
MongoDB Atlas with service user and DB RBAC
```

End users never need the MongoDB URI or database credentials. The API backend enforces tenant/role checks, business validation, and connection pooling.

## 28. Least Privilege End-to-End

| Layer | Least-Privilege Policy |
| --- | --- |
| Listener | Only genuinely required interfaces |
| Routes | Only authorized network paths |
| Firewall | Narrow source/destination/port |
| Atlas public IP list | Smallest valid egress IP/CIDR |
| Private connectivity | Only VPCs/VNets/services needing access |
| TLS | Valid certificates, never bypass verification |
| Database credentials | One distinct identity per application |
| RBAC | Scoped DB/action roles, never `root` |
| Secret management | Only runtime permitted to read secrets |
| Logging/Audit | Track policy changes and access failures |

Example read-only reporting job:

```text
reporting-job
Network: analytics subnet
DB user: reporting-reader
DB role: read on ordersdb
Do not grant: readWrite/root
```

Even if the reporting server is compromised, network restrictions and RBAC bound the impact.

## 29. HA and Network Access

Security policies must not break replica set availability:

```text
App subnet
  |
  +--> rs-a:27017  [allow]
  +--> rs-b:27017  [blocked]
  +--> rs-c:27017  [blocked]
```

When `rs-b` becomes primary, the app loses access even if the URI previously worked via `rs-a`. Therefore:

1. Verify client paths to **all member endpoints advertised by the topology**.
2. Allow replica-set members to communicate internally per rules and internal authentication.
3. Confirm DNS hostnames resolve from the app.
4. Test read/write behavior after failover in a suitable environment.
5. Scope rules to the exact members/zones rather than making internal cluster ports public.

For sharded clusters, apps use router/managed endpoints; shard/config member networking should be designed separately for cluster roles.

## 30. Change Management and Drift

Every network access entry should record:

```text
Rule ID:
Owner:
Environment/project:
Business reason:
Source IP/CIDR:
Destination/port:
Created:
Review/expiry:
Approved by:
Rollback method:
```

Practices:

- Never keep `0.0.0.0/0` permanently just because developer IPs change.
- Set expirations on temporary maintenance access.
- Revoke retired NAT/IPs, vendors, or decommissioned CI runners.
- Audit changes to security groups, host firewalls, Atlas IP lists, and database roles.
- Separate production, staging, and development network policies.
- Test configs from the **actual application runtime**, not only an operator's laptop.
- Keep backups and out-of-band admin access in case a firewall rollout locks access.

### Metrics and Alerts

| Signal | Meaning |
| --- | --- |
| Listener switches to wildcard | Public exposure risk |
| New rule allowing TCP 27017 from Internet | Unwanted access risk |
| `0.0.0.0/0` appears in Atlas IP list | Requires immediate review |
| Spike in auth failures | Wrong password, credential attack, or rotation issue |
| Spike in TLS handshake errors | CA/certificate/hostname mismatch |
| Connection attempts from unfamiliar subnet | Unusual workload or network path |
| Spike in replica-set selection timeouts | Topology, firewall, or routing issue |
| Service role elevated to admin | Privilege escalation |
| Private Endpoint DNS changed | Risk of traffic falling onto wrong public/private path |

Do not review only after an incident; run scheduled configuration reviews to catch drift.

## 31. Common Misconceptions

| Misconception | Why It's Wrong | Correct Understanding |
| --- | --- | --- |
| “`bindIp` is the client IP” | It is MongoDB's local listener address | Use firewalls to restrict client sources |
| “Setting `0.0.0.0` is the standard fix” | May expose public interfaces | Bind only needed interfaces |
| “Strong password makes public ports fine” | Expands brute-force and attack surface | Private network + TLS + auth |
| “Firewall allow = permission to read DB” | Firewalls only pass packets | RBAC is independent |
| “`127.0.0.1` in Docker is host loopback” | Separate network namespace | Use proper service DNS/networks |
| “ClusterIP Service blocks other pods” | Requires NetworkPolicy | Enforce explicit CNI/network policies |
| “Atlas IP list needs private pod IP” | Public path sees NAT egress | Allowlist real public source |
| “`0.0.0.0/0` is safe because auth is on” | Anyone can attempt TCP/handshakes | Use narrow CIDRs |
| “Atlas project role is a MongoDB user” | UI management differs from DB identity | Separate management and data permissions |
| “Private Endpoint means no TLS needed” | Private path doesn't verify identity | Still require TLS/AuthN/AuthZ |
| “Creating an endpoint forces private traffic” | DNS/URI/routes might still be public | Verify the actual path |
| “SRV URI only needs one IP open” | Drivers discover multiple hosts | Permit all required topology endpoints |
| “Opening only the seed node suffices” | Failover must reach other members | Test HA paths |
| “TCP success means queries will succeed” | TLS/AuthN/AuthZ still remain | Verify every layer |
| “Disabling TLS cert checks fixes errors” | Loses server identity verification | Fix CA/hostname/certificate |
| “`not authorized` is a firewall error” | It is post-connection RBAC | Fix roles, not network rules |
| “IPv4 blocked means no public exposure” | IPv6 may still be open | Check both stacks |
| “A new allow rule deletes old rules” | Rules can remain additive | Review the entire rule set |

## 32. Practice Exercises and Answers

### Exercise 1. Filling `bindIp`

DB VM is `10.10.20.12`; App VM is `10.20.30.10`. What should `net.bindIp` be on the DB?

**Answer:** Bind `10.10.20.12` (optionally adding `127.0.0.1`). Restrict the App VM source via firewall allowing `10.20.30.10/32` to TCP 27017.

### Exercise 2. Public Exposure

A VM has a public NIC, MongoDB binds `0.0.0.0`, and the security group allows TCP 27017 from `0.0.0.0/0`. What must be fixed?

**Answer:** Restrict the listener to required private/loopback interfaces and narrow firewall sources; remove broad Internet exposure. TLS/AuthN/RBAC remain required.

### Exercise 3. TCP Succeeds, Auth Fails

`Test-NetConnection` succeeds, yet `mongosh` reports `Authentication failed`. Should you open more firewall ports?

**Answer:** No. TCP already works; check username/password, `authSource`, authentication mechanism, and secret rotation.

### Exercise 4. NAT with Atlas

App pod IP `10.2.1.15` exits to the Internet through NAT `198.51.100.24`. Which source does the Atlas public endpoint see?

**Answer:** Normally public egress `198.51.100.24`. The access list must specify that source, not the private pod IP.

### Exercise 5. Multiple NATs

Two zones route through NAT A and NAT B. The access list only includes NAT A. Why does the app fail intermittently?

**Answer:** Workloads running in zone B egress from an unallowed IP. Inventory all valid egress IPs or configure unified static egress.

### Exercise 6. Atlas Console Role

A user can log into the Atlas UI and view a cluster. Does that guarantee they have a MongoDB database account to read `orders`?

**Answer:** No. Project/organization management roles differ from MongoDB Database Access/roles.

### Exercise 7. Private Endpoint DNS

A Private Endpoint was created, yet the app still resolves the MongoDB URI to public hosts. Can we claim traffic is private?

**Answer:** Not yet. Verify the private URI, DNS routing, endpoint state, and actual traffic path.

### Exercise 8. SRV Lookup

`mongodb+srv://...` throws a DNS lookup error even though TCP 27017 is allowed by the firewall. What should you check first?

**Answer:** DNS SRV/TXT resolvers, hostnames, and private DNS if applicable. Never widen the Atlas IP list to fix DNS.

### Exercise 9. Replica Set Failover

The app reaches `rs-a`, but cannot reach `rs-b`/`rs-c`. After failover it cannot find a primary. Why?

**Answer:** Network policies, routes, or DNS to the remaining replica-set endpoints do not match the topology; allow the required paths without making nodes public.

### Exercise 10. Docker Localhost

An app container calls `mongodb://127.0.0.1:27017`, while the DB runs in another container. Where is the bug?

**Answer:** `127.0.0.1` inside the app container points to the app container itself. Use controlled service hostnames and shared container networking.

### Exercise 11. IPv6

A host has listener `:::27017` and an IPv4 firewall blocking the entire Internet. Is it safe?

**Answer:** Not yet. Check IPv6 routing, DNS AAAA records, and the IPv6 firewall.

### Exercise 12. TLS Mismatch

A client reports certificate hostname mismatch. The team wants to enable `tlsInsecure` permanently.

**Answer:** Do not do that. Fix the URI hostname, certificate SAN, or CA trust/rotation instead of disabling verification.

### Exercise 13. Least Privilege

A reporting job only needs `find()` on `ordersdb`, yet holds the `root` role.

**Answer:** Give it a dedicated database user with appropriate read privileges, restrict allowed source networks, and enforce TLS.

### Exercise 14. Dynamic CI Runner IPs

CI runners change IPs on every job, so a developer proposes permanently adding `0.0.0.0/0` in Atlas.

**Answer:** Prefer static NAT egress, self-hosted runners with private networking, or temporary access list entries with expiration; never permanently open all IPv4 space.

### Exercise 15. `bindIp` Not on Host

The server does not have `10.10.20.99`, yet the config binds that address and fails to start.

**Answer:** Inspect the DB host's actual interface addresses and fix the listener to a valid IP; firewalls cannot fix a socket bind error.

### Exercise 16. Atlas Projects

The team added the right NAT IP to the staging project, while the app URI points to the production cluster.

**Answer:** Staging's access list does not apply to the production project. Verify the target project/cluster and follow production change policy.

### Exercise 17. Shared NAT

Two services share one allowlisted public NAT. Does that mean service B can read service A's data?

**Answer:** No. Each service still needs valid MongoDB credentials and roles. IP allowlists do not replace database authorization.

### Exercise 18. Mobile App

A mobile app embeds MongoDB credentials and connects straight to Atlas from user networks.

**Answer:** Risks secret extraction, dynamic client IPs, and missing business controls. Route through an HTTPS backend using a service identity and controlled network paths.

### Exercise 19. `not authorized` Error

The app logs in successfully, yet `insertOne()` is rejected. Does `bindIp` need changing?

**Answer:** No. AuthN succeeded and the command failed at **AuthZ**. Fix the DB/action roles following least privilege.

### Exercise 20. Configuration Review

A new rule opens `0.0.0.0/0` to 27017, though MongoDB still requires authentication. Should this raise an alert?

**Answer:** Yes. Network exposure increased, so review and close the unnecessary rule. Authentication does not eliminate risks from exposing a listener broadly.

## 33. Production Checklist

1. Identify exact MongoDB endpoints, IPs, ports, and topology.
2. Bind only required loopback/private interfaces; never use wildcards reflexively.
3. Verify IPv4/IPv6, Docker/Kubernetes port exposure, and actual active listeners.
4. Restrict inbound/outbound traffic by source/destination/port across every firewall layer.
5. For replica sets/sharded clusters, allow required internal HA and client paths; never make internal endpoints public.
6. Enable TLS with certificate validation and proper authentication.
7. Grant least-privilege roles and separate credentials per service; never use `root` for apps.
8. Manage secrets via appropriate tools; never put passwords in code or logs.
9. For Atlas public paths, use Project IP Access Lists with real public egress IPs and narrow CIDRs.
10. For Atlas private paths, verify private endpoints/peering, DNS, routing, and absence of unintended public exposure.
11. Use official deployment-provided connection strings rather than hardcoding temporary discovered IPs.
12. Test from the actual application/runner runtime, not only a developer laptop.
13. Diagnose errors in order: DNS → route/TCP → TLS → AuthN → AuthZ.
14. Test failover/topology paths and IPv6 if present.
15. Record owner, purpose, expiry, review, and rollback for every sensitive network rule.
16. Monitor listener changes, Atlas IP list drift, auth failures, and permission changes.

## 34. Summary

In self-managed MongoDB, **`net.bindIp` controls which local interfaces the server listens on**, whereas **firewalls, security groups, and network ACLs** control which sources can reach those interfaces. For same-host development, `127.0.0.1` is typically sufficient. For multi-host systems, choose **private interfaces and narrow firewalls scoped to application subnets** instead of opening `0.0.0.0` across all interfaces.

With **MongoDB Atlas**, the **Project IP Access List** governs sources for applicable public connections, **Database Access** governs database users and roles, and **Private Endpoints/peering** provide private networking options where supported. NAT egress, DNS SRV, private DNS, cluster topology, and TLS all impact connectivity.

A secure deployment does not merely connect—it guarantees **right source – right network path – right identity – right data permissions**. When errors occur, diagnose layer by layer instead of widening IP Access Lists, disabling certificate validation, or granting unnecessary administrative privileges.

### Official References

- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Atlas — Configure IP Access List Entries](https://www.mongodb.com/docs/atlas/security/ip-access-list/)
- [MongoDB Atlas — Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [MongoDB Atlas — Private Endpoints](https://www.mongodb.com/docs/atlas/security-private-endpoint/)
- [MongoDB Atlas — Network Peering](https://www.mongodb.com/docs/atlas/security-vpc-peering/)
