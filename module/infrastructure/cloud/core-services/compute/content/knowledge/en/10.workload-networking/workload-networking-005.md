# DNS, Hostnames, and Inter-Machine Service Discovery

In a cloud system, applications typically run across multiple virtual machines or containers and need to connect to one another. An API must locate the database's address, workers need to find the queue, services call each other over internal networks, and load balancers must route requests to healthy active instances. If fixed IP addresses are hardcoded in source code, replacing machines, scaling replicas, or moving workloads to another subnet quickly renders configurations stale.

**DNS (Domain Name System)** maps domain names or machine names to network information such as IP addresses. A **hostname** is the name identifying a machine within an operating system or network. **Service discovery** is the process by which a component locates active instances providing a service and retrieves the information required to connect to them. These three concepts are closely related but distinct: hostnames identify machines, DNS resolves names, and service discovery locates service endpoints according to workload lifecycle and health state.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module and focuses on DNS, hostnames, and how machines discover each other's services across VM, container, and cloud environments. Topics include name resolution flows, DNS records, private DNS, hybrid DNS, service registries, Kubernetes DNS, troubleshooting, and security.

## 1. Why Do Workloads Need DNS and Service Discovery?

Suppose an e-commerce system has three APIs, a database, a cache, and multiple workers. If the API connects to the database via an IP address written directly in configuration, replacing the database or moving it to another subnet forces updates across multiple applications. If scaling out requires manually editing worker IP lists every time, deployments become slow and error-prone.

DNS and service discovery decouple logical identity from physical location:

- Applications call names like `db.internal.example` instead of depending on specific IPs.
- When instances change, the DNS management system or service registry updates the endpoints.
- A single service name can represent multiple instances.
- Workloads on different machines can use the same lookup mechanism.
- Connection configuration is centrally managed and can vary cleanly by environment.

DNS is especially useful for endpoints with relatively stable lifecycles. For workloads that change rapidly or require health checks, metadata, and application-layer load balancing, DNS is commonly paired with a service registry, load balancer, or orchestrator-native discovery.

## 2. Distinguishing Hostnames, Domain Names, and Service Names

Names appearing across a network serve different purposes:

| Concept | Meaning | Example |
|---|---|---|
| Hostname | Machine name configured in the operating system | api-01 |
| Domain name | Name within the DNS namespace | example.com |
| FQDN | Fully Qualified Domain Name, identifying position in the DNS hierarchy | api-01.prod.internal.example |
| Service name | Logical name of a function that clients call | orders-api |
| Endpoint | Details needed to connect to an instance or service | 10.20.4.15:8080 |

A hostname is typically set during VM creation or bootstrapping. The OS can use the hostname in prompts, logs, machine identification, and certain protocols. DNS records are managed by a DNS zone; changing the hostname inside a guest OS does not automatically update DNS unless a corresponding registration mechanism exists.

An FQDN (Fully Qualified Domain Name) is a complete name in DNS. For example, `api-01.prod.internal.example` can denote machine `api-01` in the `prod` environment under the `internal.example` namespace. A trailing dot, as in `api-01.prod.internal.example.`, indicates an absolute DNS name; many tools append or omit it automatically when displaying results.

A service name can point to a load balancer, a virtual IP, a set of DNS records, or an entry in a service registry. Clients typically need to know only the service name and the published protocol/port.

## 3. How Does DNS Work?

DNS is a hierarchical, distributed naming system. When an application needs to connect to a hostname, the operating system or resolver library looks up the corresponding address through a configured DNS resolver.

A typical resolution flow:

1. An application requests resolution of a name, such as `api.prod.internal.example`.
2. The stub resolver on the machine checks local caches and name-search configuration.
3. If not cached, the query goes to a configured recursive resolver, typically managed by the cloud provider, organization, or internal network.
4. The recursive resolver checks its cache; if needed, it queries the DNS hierarchy or authoritative DNS server.
5. The authoritative server returns the record for the zone it manages.
6. The resolver returns the result to the machine and caches it according to the TTL.
7. The application uses the returned address to open a network connection.

~~~mermaid
sequenceDiagram
    participant A as Application / OS
    participant R as Recursive Resolver
    participant H as Root / TLD DNS
    participant N as Authoritative DNS
    A->>R: Look up api.prod.internal.example
    alt Cache hit
        R-->>A: Return cached address
    else Cache miss
        R->>H: Locate server authoritative for zone
        H-->>R: Referral to next DNS server
        R->>N: Query record
        N-->>R: Return A/AAAA or other record type
        R-->>A: Return result and TTL
    end
~~~

In cloud networks, the resolver may be the VPC/VNet's internal DNS service or a resolver forwarding to corporate DNS. VMs generally do not query root servers directly; the recursive resolver performs most of that work.

### 3.1. Stub Resolver, Recursive Resolver, and Authoritative Server

- **Stub resolver:** lightweight component on the client host that sends queries to the configured resolver.
- **Recursive resolver:** accepts queries on behalf of clients, finds the answer, and caches results.
- **Authoritative DNS server:** provides authoritative answers for the zones it manages.

Distinguishing these roles helps isolate failures. If a machine sends queries to the wrong resolver, the error lies in client configuration or DHCP. If the resolver cannot reach the authoritative server, the issue may be forwarding, firewalls, or delegation. If the authoritative server returns the wrong record, inspect the zone and DNS update pipeline.

### 3.2. Recursive Queries and Iterative Queries

Clients typically send recursive queries to a resolver: the resolver is responsible for finding the final answer or returning an error. During lookup, the resolver may send iterative queries to hierarchical DNS servers; each server returns the answer if known or a referral to where it might be found.

Do not confuse a recursive resolver with an authoritative server. A single server can perform both functions in some architectures, though in enterprise environments they are typically separated to limit scope and improve security.

## 4. Common DNS Record Types

DNS supports multiple resource record (RR) types. Key records for workloads include:

| Record type | Purpose | Example |
|---|---|---|
| A | Maps a name to an IPv4 address | api.internal.example → 10.20.4.15 |
| AAAA | Maps a name to an IPv6 address | api.internal.example → 2001:db8:20::15 |
| CNAME | Alias pointing to another DNS name | orders.internal.example → api-01.internal.example |
| PTR | Reverse lookup from an IP address to a name | 15.4.20.10.in-addr.arpa → api-01.internal.example |
| SRV | Publishes service hostname, port, priority, and weight | _grpc._tcp.internal.example |
| TXT | Holds text used for verification or policies | SPF, domain verification |
| NS | Specifies authoritative name servers for a zone | ns1.example.net |
| SOA | Administrative and zone synchronization metadata | primary server, serial, refresh |

### 4.1. A and AAAA

An `A` record returns an IPv4 address; an `AAAA` record returns an IPv6 address. A hostname can carry both record types if the service supports dual-stack operation. Clients select an address based on network policy and connection algorithms.

Do not publish `AAAA` records merely because IPv6 exists on part of the infrastructure. The entire path, firewalls, routes, and services must support IPv6; otherwise, some clients may experience timeouts or slow fallback.

### 4.2. CNAME

A `CNAME` creates an alias from one name to another. For example, `api.internal.example` can alias `api-prod-lb.internal.example`. When the load balancer address changes, only the target record needs updating.

Under standard DNS rules, an owner name with a `CNAME` should not coexist with other data record types at the same owner name. `CNAME` at a zone apex is restricted because the apex must hold `SOA` and `NS` records; some providers offer proprietary alias/flattening mechanisms to handle this case.

### 4.3. PTR and Reverse DNS

`PTR` records support reverse lookups from an IP to a name. Reverse DNS is typically managed in `in-addr.arpa` zones for IPv4 and `ip6.arpa` zones for IPv6. `PTR` records are helpful for logs, infrastructure checks, some email systems, and operational tooling. However, `PTR` does not replace identity authentication; a reverse lookup result does not prove the sending machine is trustworthy.

### 4.4. SRV

An `SRV` record publishes a service running on a specific hostname and port along with priority and weight. Names typically follow the format `_service._proto.name`. For example, an application can query `_grpc._tcp.orders.internal.example` to locate a gRPC endpoint.

Not every client library automatically queries `SRV` records. Verify whether the library supports `SRV`; if not, the application may need a custom resolver or explicit endpoint configuration.

## 5. Hostnames and Machine Naming Configuration on VMs

Hostnames should follow a consistent, recognizable naming convention and avoid sensitive data. A hostname can encode role, environment, region, or sequence number.

Examples:

| Hostname | Meaning |
|---|---|
| api-prod-hcm-01 | Production API, HCM region, machine 01 |
| worker-dev-02 | Development worker, machine 02 |
| db-staging-01 | Staging database, machine 01 |

These are illustrative conventions only. If a system spans multiple regions or accounts, specify clearly which portion of the name guarantees uniqueness within the DNS zone. Avoid embedding personal names, account numbers, public IP addresses, or secrets in hostnames.

### 5.1. Configuring Hostnames on Linux

On systemd-based distributions, the hostname can be viewed and changed with `hostnamectl`:

~~~bash
# View current hostname
hostnamectl status

# Set static hostname
sudo hostnamectl set-hostname api-prod-hcm-01

# Verify
hostname
hostname -f
~~~

`hostname -f` returns an FQDN only if the system has appropriate name resolution configured. Setting the hostname does not automatically create an `A` record in DNS. You must update the zone or use a managed DNS registration mechanism.

### 5.2. Configuring Hostnames on Windows Server

PowerShell can inspect and rename a machine:

~~~powershell
# View current hostname
hostname

# Rename the machine and restart
Rename-Computer -NewName "api-prod-hcm-01" -Restart
~~~

In a domain, check procedures for renaming the computer account, DNS registration, and restart timing. Do not change hostnames manually if a configuration management tool or domain policy governs machine names.

### 5.3. Hostnames, DNS, and DHCP

DHCP can supply IP addresses, DNS resolvers, search domains, and certain hostname options. Some environments support clients dynamically registering DNS upon lease acquisition; others rely on the cloud control plane or management tools to update records. Behavior depends on the DHCP server, OS, cloud provider, and DNS policy.

Therefore, establish a clear source of truth for hostnames and DNS records:

- OS self-registration into DNS.
- DHCP server updating DNS when granting leases.
- Cloud control plane creating records from instance metadata.
- IaC pipelines or configuration management updating zones.
- Service registry registering endpoints at application startup.

Avoid letting multiple systems write to the same record without precedence rules, as they can overwrite each other or leave stale records.

## 6. Public and Private DNS in the Cloud

Public DNS provides names resolvable from the Internet. Private DNS resolves only within authorized network scopes, such as a VPC/VNet, corporate network, or hybrid connection.

| Criterion | Public DNS | Private DNS |
|---|---|---|
| Query scope | Internet or public resolvers | Internal networks or associated resolvers |
| Typical names | api.example.com | api.prod.internal.example |
| Target addresses | Usually public endpoints or load balancers | Private IPs, internal load balancers, or service endpoints |
| Primary risks | Endpoint exposure, spoofing, or domain hijacking | Internal name leakage, misconfigured split-horizon, cross-network access |
| Governance | Registrar, authoritative DNS provider | Cloud private zones, enterprise DNS, or internal systems |

### 6.1. Private Hosted Zones or Private DNS Zones

Cloud providers commonly offer private DNS zones that can be associated with one or more virtual networks. VMs inside associated networks can query internal names and receive private IPs or internal endpoints. Association methods, zone limits, and resolution conditions differ across platforms.

For example, the `internal.example` zone might contain:

~~~dns
api.prod.internal.example.  60  IN  A  10.20.4.15
db.prod.internal.example.   60  IN  A  10.20.8.10
cache.prod.internal.example. 60 IN  A  10.20.9.25
~~~

This is an illustrative zone file. The IPs belong to private ranges and are meaningful only inside properly routed networks. Never publish internal records into a public zone without an explicit requirement.

### 6.2. Split-Horizon DNS

Split-horizon DNS (also called split-view DNS) returns different answers depending on the querier's location or resolver. For instance, `api.example.com` can return a public load balancer to Internet users and a private load balancer to machines inside the corporate network.

This pattern keeps internal clients on private network paths and reduces hairpinned Internet traffic. However, it requires maintaining two consistent datasets, verifying which resolver is used, and preventing internal clients from receiving public IPs when private endpoints are intended.

### 6.3. DNS Across Multiple VPCs/VNets and Corporate Networks

In multi-network architectures, private zones may need associations with multiple VPCs/VNets, or resolver forwarding to look up names across networks. Peering or transit networks provide packet routing only; DNS resolution often requires separate configuration.

In hybrid environments, DNS forwarding is commonly used to:

- Forward queries for corporate internal names from cloud resolvers to enterprise DNS.
- Forward cloud zone queries from on-premises networks to inbound cloud resolvers.
- Apply conditional forwarding per domain.
- Preserve name resolution as workloads migrate between data centers and the cloud.

Do not assume a VPN or private link automatically makes DNS visible across both sides. Configure routes, UDP/TCP port 53 firewalls, resolver endpoints, forwarding rules, and zone association permissions properly.

## 7. TTL, Caching, and DNS Propagation Time

Each DNS record typically has a TTL (Time To Live), indicating how long resolvers are allowed to cache the response. TTL is measured in seconds.

A low TTL helps clients pick up changes faster once caches expire, at the cost of higher query volume to resolvers and authoritative DNS. A high TTL reduces DNS load but causes clients to continue using old IPs longer after a record changes.

Examples:

| TTL | Typical behavior | When to consider |
|---|---|---|
| 30–60 seconds | Short cache, faster cutovers | Frequently changing endpoints requiring quick failover |
| 300 seconds | Balance between caching and update speed | Internal services with periodic changes |
| 3600 seconds | Longer cache, fewer queries | Stable names that rarely change |

TTL does not guarantee every client will update in that exact number of seconds. Applications may maintain their own DNS caches; JVMs or runtimes may enforce separate DNS caching policies; proxies, service meshes, and intermediate resolvers can also hold cached results. Some systems also perform negative caching when a name does not exist.

When changing a service's IP, a safe procedure is:

1. Lower the TTL far enough ahead of cutover so old caches expire.
2. Provision the new endpoint and verify connectivity.
3. Update the DNS record or registry.
4. Monitor queries, connections, and client errors.
5. Keep the old endpoint running during the transition window if possible.
6. Decommission the old endpoint only after confirming clients have migrated.

Do not leave TTLs permanently ultra-low if unnecessary. TTL should balance cutover speed against DNS infrastructure load.

## 8. What Is Service Discovery?

Service discovery is a mechanism that enables clients to find the addresses and connection details of a service without hardcoding individual instances. Systems can locate endpoints via DNS, registry APIs, platform metadata, or static configuration.

A service discovery system typically manages:

- Service names and instance identifiers.
- IP addresses, ports, and protocols.
- Registration status, heartbeats, or health state.
- Metadata such as region, zone, version, and load pool.
- Registration, expiration, and deregistration timing.
- Access permissions and client visibility scope.

For example, the `orders-api` service has three instances:

| Instance | Endpoint | Zone | Status |
|---|---|---|---|
| orders-01 | 10.20.4.11:8080 | zone-a | Healthy |
| orders-02 | 10.20.5.12:8080 | zone-b | Healthy |
| orders-03 | 10.20.6.13:8080 | zone-c | Unhealthy |

Clients should receive only healthy endpoints. If using pure DNS, pair it with record automation or DNS health checks; a DNS record by itself does not prove a service is healthy.

## 9. Service Discovery Models

### 9.1. Static Configuration

Clients are configured directly with service hostnames or IPs. This is simple and works for small, static endpoint sets or lab environments. When instances change, operators must update configurations and redeploy clients.

Avoid static IP lists for autoscaling or multi-zone systems whenever better discovery mechanisms exist.

### 9.2. DNS-Based Discovery

Clients look up a service name via DNS and receive one or more records. This is simple and compatible with virtually all languages and operating systems. DNS can return a load balancer endpoint or multiple instance addresses.

The advantage is that clients only need a standard resolver. The limitation is that caching and TTLs prevent instant endpoint updates; DNS also lacks rich metadata and cannot guarantee health-aware routing unless the platform adds those capabilities.

### 9.3. Registry-Based Discovery

A service registry stores information about instances currently serving traffic. On startup, an instance registers its endpoint; on shutdown, it deregisters or its heartbeat expires. Clients query the registry to obtain the endpoint list.

Registries typically support health checks, metadata, and filtering by region/zone/version. In return, the team must operate the registry, secure its API, manage heartbeats, handle consistency, and account for registry failure scenarios.

Common tools offering service registry or discovery include Consul as well as orchestration platforms, service meshes, and cloud service catalogs. Choose tools suited to your environment and integration needs; avoid running a standalone registry if the platform's built-in discovery already meets requirements.

### 9.4. Load Balancers as Discovery Points

Clients call a stable load balancer hostname. The load balancer monitors target health and distributes requests to healthy instances. This is server-side discovery: clients remain unaware of individual backends.

This model fits HTTP APIs, TCP services, and many applications needing stable endpoints. Understand health checks, connection draining, timeouts, session persistence, and load balancer limits.

### 9.5. Client-Side vs. Server-Side Discovery

| Model | How it works | Advantages | Trade-offs |
|---|---|---|---|
| Client-side discovery | Client queries registry/DNS, picks an endpoint, and connects directly | Customizable instance, zone, and retry selection | Client must integrate discovery, caching, and load balancing |
| Server-side discovery | Client calls a stable endpoint; proxy/load balancer picks the backend | Simple clients, centralized policies | Adds an intermediary hop and dependency on load balancer/proxy |

A system can combine both: DNS locates the load balancer, while the load balancer consults a registry or target group to reach backends.

## 10. Service Discovery in Containers and Kubernetes

Containers are frequently created and replaced. Container IP addresses can change on restart or rescheduling, so applications should call service names instead of storing container IPs.

### 10.1. DNS in Docker Compose

In a user-defined Compose network, services can typically be reached by service name. For example, a web app connects to hostname `db` on the database port without knowing the current container IP.

~~~yaml
services:
  web:
    image: example/web:v1
    environment:
      DATABASE_HOST: db
      DATABASE_PORT: "5432"
    depends_on:
      - db
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
secrets:
  db_password:
    file: ./secrets/db_password.txt
~~~

This example illustrates using service name `db` in a Compose network. `depends_on` controls startup order at the Compose level but does not guarantee the database is ready to accept connections. Applications still need bounded connection retries and health checks. In production, provide secrets using a secret manager or appropriate platform secret mechanism.

### 10.2. Kubernetes DNS

Kubernetes provides cluster DNS through components such as CoreDNS. When a `Service` is created, cluster DNS typically creates a name of the form:

~~~text
<service>.<namespace>.svc.<cluster-domain>
~~~

For example, a `Service` named `orders-api` in the `production` namespace can be accessed via:

~~~text
orders-api.production.svc.cluster.local
~~~

The short name `orders-api` resolves within the same namespace via search domains in the Pod's DNS config. From another namespace, use the full name or at least `service.namespace` to avoid ambiguity.

Example `Service`:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
  namespace: production
spec:
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
  type: ClusterIP
~~~

A `ClusterIP` Service provides a stable in-cluster address. `EndpointSlice` tracks backend endpoints matching the selector and readiness state. Clients call the service DNS name; `kube-proxy` or the corresponding dataplane forwards traffic to backends.

### 10.3. Headless Services and StatefulSets

A headless `Service` sets `clusterIP: None`. Instead of providing a single virtual service IP, DNS can return the matching Pod addresses directly. This is useful when clients must discover individual replicas, such as database clusters or distributed systems requiring stable node identities.

`StatefulSet` assigns stable network identities to Pods by ordinal index and is commonly paired with a headless `Service`. For example, a Pod can be named `orders-db-0.orders-db.production.svc.cluster.local`. This name helps peers locate specific members, though it does not guarantee a member is healthy; applications still need health checks and cluster membership mechanisms.

### 10.4. SRV Records in Kubernetes

For a `Service` with named ports, Kubernetes DNS can publish `SRV` records for clients that need to discover ports and protocols. Clients must support `SRV` lookups; otherwise, configure ports explicitly.

### 10.5. Pod DNS Policies

Pods can use the cluster's default DNS policy, use host networking with appropriate configuration, or specify custom nameservers and search domains. Fields `dnsPolicy` and `dnsConfig` customize this behavior. Modifying DNS policies can prevent Pods from resolving internal services or external domains; test carefully before broad rollout.

## 11. Service Registries and Instance Lifecycles

A registry must handle instances starting, becoming healthy, losing connectivity, and shutting down. A typical lifecycle:

1. The instance starts and checks required dependencies.
2. The instance registers its service name, endpoint, and metadata.
3. Health checks confirm the instance is ready to serve traffic.
4. Clients or proxies retrieve the list of eligible endpoints.
5. The instance sends heartbeats or undergoes periodic health checks.
6. During shutdown, the instance stops accepting new load and deregisters.
7. If an instance vanishes abruptly, its lease or health check expires so the registry removes the endpoint.

If heartbeat timeouts are too short, transient network blips can falsely mark healthy instances unhealthy. If timeouts are too long, failed endpoints linger in the registry. Tune timeouts based on failure-detection speed and jitter tolerance.

### 11.1. Registration and Deregistration Must Be Idempotent

An instance may restart or emit duplicate registration events. The registry should handle repeated registrations without creating duplicate entries. Similarly, repeated deregistrations should not corrupt state. Use an instance ID or service instance ID that remains consistent across the process lifecycle.

### 11.2. Coordinating Discovery with Graceful Shutdown

When an instance is about to stop, transition it to draining or deregister it before termination. This ties directly into graceful shutdown: discovery must stop advertising an endpoint that has stopped accepting requests. However, keep the endpoint alive long enough for in-flight requests to finish and account for client-side caching.

## 12. Load Balancing and Endpoint Selection

DNS can return multiple addresses for one name, but it is not always a complete load balancer. Resolvers may reorder or cache address lists; clients may connect only to the first address; some clients try addresses sequentially or randomly.

When controlled traffic distribution is required, consider:

- Network-layer or application-layer load balancers.
- Service mesh proxies.
- Client-side load balancing backed by a health-aware registry.
- DNS weighted/latency routing if appropriate for the architecture.

Simple DNS round-robin does not guarantee even distribution, does not automatically detect failing backends, and does not track active connection counts. For critical services, use health-aware routing and connection draining.

## 13. Diagnosing DNS and Service Discovery Issues

When an application cannot reach a service name, inspect layer by layer instead of immediately assuming DNS is broken.

### 13.1. Checking on Linux

~~~bash
# View hostname and FQDN
hostnamectl status
hostname -f

# View configured DNS resolvers
cat /etc/resolv.conf

# Query A/AAAA records
dig api.prod.internal.example A
dig api.prod.internal.example AAAA

# View concise answer
dig +short api.prod.internal.example

# Query a specific resolver
dig @10.20.0.2 api.prod.internal.example

# Test TCP connectivity to endpoint
nc -vz api.prod.internal.example 443

# Test resolution via NSS
getent hosts api.prod.internal.example
~~~

On some distributions, `/etc/resolv.conf` is managed by `systemd-resolved` or `NetworkManager` and may point to a local stub resolver. Direct edits to that file may be overwritten. Use the appropriate network management tools instead.

### 13.2. Checking on Windows

~~~powershell
# View network interface DNS settings
Get-DnsClientServerAddress

# Resolve a name
Resolve-DnsName api.prod.internal.example

# View local DNS cache
Get-DnsClientCache

# Clear local resolver cache when retesting
Clear-DnsClientCache

# Test connectivity to service port
Test-NetConnection api.prod.internal.example -Port 443
~~~

Clearing the cache affects only the local machine's resolver cache; it does not clear recursive resolvers or application caches. Do not treat flushing caches as a default fix without diagnosing the underlying cause.

### 13.3. Diagnostic Tree

~~~mermaid
flowchart TD
    A["Application cannot connect to service name"] --> B{"Does the name resolve?"}
    B -- "No" --> C["Check hostname, search domain, and resolver"]
    C --> D["Check zone, records, forwarding, and association permissions"]
    B -- "Yes" --> E{"Does IP match expected endpoint?"}
    E -- "No" --> F["Check TTL, caches, split DNS, and stale records"]
    E -- "Yes" --> G{"Does TCP connect to port succeed?"}
    G -- "No" --> H["Check routes, firewalls, security groups, and listener"]
    G -- "Yes" --> I["Check TLS, protocol, health, and application"]
~~~

### 13.4. Common Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| NXDOMAIN | Name does not exist in the queried zone | Spelling, zone, search suffix, and records |
| SERVFAIL | Resolver could not obtain a valid answer | Authoritative server, DNSSEC, forwarding, and network |
| Query timeout | Resolver unreachable or blocked by firewall | Routes, UDP/TCP 53, and resolver address |
| Returns stale IP | Cache TTL not expired or application caching | TTL at each layer and cache policies |
| Internal host receives public IP | Split-horizon or private zone not applied | Resolver and private zone associations |
| Name resolves but connection fails | Route, firewall, port, or service not listening | Use `nc`/`Test-NetConnection` and inspect backend |
| Some Pods fail to resolve | DNS policy, CoreDNS, NetworkPolicy, or node issue | Pod `resolv.conf`, CoreDNS, and `EndpointSlice` |

## 14. Securing DNS and Service Discovery

DNS and service registries can expose topology, system names, deployment regions, and internal services. If modified without authorization, clients may connect to attacker-controlled endpoints or spoofed services.

Controls to consider:

- Separate public zones and private zones.
- Restrict record creation, modification, and deletion by zone and role.
- Protect DNS management APIs with IAM/RBAC and MFA.
- Monitor changes to records, delegations, and resolver rules.
- Use DNSSEC when data integrity verification across supported resolution paths is required.
- Use TLS/mTLS to authenticate service endpoints; DNS does not replace application authentication.
- Restrict access to recursive resolvers to prevent open resolvers and DNS amplification.
- Monitor anomalous queries, tunneling, or DNS exfiltration.
- Never place sensitive data inside hostnames, TXT records, or service metadata.

### 14.1. DNSSEC, DoT, and DoH

DNSSEC uses digital signatures to authenticate the integrity and origin of DNS data across the validation chain. DNSSEC does not encrypt query contents and does not guarantee the returned endpoint runs a secure application.

DNS over TLS (DoT) and DNS over HTTPS (DoH) encrypt the channel between client and resolver. They reduce on-path eavesdropping and tampering, though resolvers, policies, and logging must be properly governed. In corporate networks, unmanaged DoH can bypass DNS filtering or internal split-horizon resolution.

### 14.2. DNS Is Not an Authentication Mechanism

An `A` or `CNAME` record merely states that a name maps to an address or another name. It does not prove the server holds the genuine identity of the service. For sensitive communication, use TLS certificates, mTLS, workload identity, or appropriate authentication mechanisms.

## 15. Designing DNS for Multi-Environment Systems

An organization may run dev, staging, and production across separate VPCs/VNets. Establish clear naming rules and resolution scopes:

| Environment | Example zone | Service name |
|---|---|---|
| Development | dev.internal.example | orders-api.dev.internal.example |
| Staging | staging.internal.example | orders-api.staging.internal.example |
| Production | prod.internal.example | orders-api.prod.internal.example |

You can use one shared private zone with environment labels or separate zones per environment. Separate zones create clearer administrative boundaries; a shared zone reduces configuration count but demands strict naming conventions and access controls.

Do not allow dev resolvers to query or update production records unnecessarily. Manage private zone associations, record change permissions, and network access permissions together.

## 16. Practical Example: Services in an E-Commerce Application

An e-commerce system has an API gateway, catalog API, orders API, database, and cache. Components run in multiple private subnets and scale independently.

Reference design:

| Service | Logical name | Published endpoint | Discovery method |
|---|---|---|---|
| API gateway | api.example.com | Public load balancer | Public DNS |
| Catalog API | catalog.prod.internal.example | Internal load balancer | Private DNS |
| Orders API | orders.prod.internal.example | Internal load balancer | Private DNS |
| Database | db.prod.internal.example | Private database endpoint | Service-managed Private DNS |
| Cache | cache.prod.internal.example | Private cache endpoint | Private DNS or registry |

Clients call `catalog` and `orders` by service name. Load balancers select healthy backends. Databases and caches are not exposed to the Internet; security groups allow only required workloads to connect on the respective ports.

When an `orders` API instance scales in, it transitions to draining and is removed from the backend pool. The DNS name `orders.prod.internal.example` does not need to change because it points to a stable internal load balancer. When a database endpoint moves to a new address, the private DNS record or provider-managed endpoint updates; clients must handle DNS caching, connection retries, and reconnects.

This design separates three responsibilities: DNS provides stable names, load balancers distribute traffic to healthy backends, and applications manage timeouts, retries, and connection authentication.

## 17. DNS and Service Discovery Implementation Checklist

Use the following process:

1. **Inventory services:** identify service names, ports, protocols, owners, environments, and dependencies.
2. **Define naming conventions:** establish hostnames, FQDNs, private/public zones, and search domains.
3. **Choose discovery models:** static DNS, dynamic DNS, registry, load balancer, or orchestrator-native discovery.
4. **Design record lifecycles:** define who registers, updates, health-checks, and deregisters endpoints.
5. **Select TTLs:** balance caching, cutover speed, and resolver load.
6. **Configure network paths:** routes, firewalls, private zone associations, and DNS forwarding.
7. **Secure permissions:** enforce access controls on zones, resolvers, and registries; use TLS for service connections.
8. **Test:** resolve names from every subnet/namespace, verify ports, failover, and caching behavior.
9. **Monitor:** track DNS errors, query latency, stale records, and anomalous changes.
10. **Operate:** prune unused records, keep documentation current, and audit periodically.

## 18. Common Mistakes

- **Hardcoding IPs in applications:** increases toil during machine replacement or scaling.
- **Assuming changing a hostname updates DNS automatically:** an explicit registration or record update mechanism is required.
- **Using public DNS for internal services:** can leak topology or create unintended access paths.
- **Setting excessively long TTLs for frequently changing endpoints:** clients may keep using stale IPs.
- **Setting ultra-low TTLs on every record:** increases query traffic and resolver load needlessly.
- **Treating DNS round-robin as health-aware load balancing:** DNS does not check backend health without additional mechanisms.
- **Assuming VPN/peering automatically connects DNS:** network routing and name resolution must be configured separately.
- **Ignoring application-level caching:** records update while clients continue holding old addresses.
- **Failing to deregister instances on shutdown:** clients may keep connecting to terminating endpoints.
- **Using DNS as authentication:** a properly resolved name does not prove a server is trustworthy.
- **Letting multiple systems write the same record:** causes stale data or unexpected overwrites.

## 19. Takeaways

Hostnames identify machines; FQDNs position names within the DNS hierarchy; DNS resolves names to addresses or service metadata; service discovery locates active endpoints for clients to connect to. In the cloud, private DNS, resolver forwarding, service registries, and container orchestrator DNS help workloads find each other as VMs or containers come and go.

For reliable operation, establish consistent naming conventions, manage records and TTLs along the workload lifecycle, separate public and private DNS, configure forwarding across networks, coordinate discovery with health checks and graceful shutdown, and use TLS or workload identity to authenticate services. When troubleshooting, inspect name resolution, returned addresses, routes, firewalls, ports, and application state in order.
