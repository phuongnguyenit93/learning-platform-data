# Connecting Functions to Private Networks and Dependent Services

Serverless enables deploying functions or applications without managing servers directly. However, workloads still need to communicate with databases, caches, message brokers, internal APIs, on-premises systems, or other cloud services. When dependencies are only accessible over a private network, you must design the path from the function's execution environment to the exact subnet, route, DNS, firewall, and endpoint.

A function may run successfully when calling only public services, yet fail immediately when connecting to a private database. Conversely, merely attaching a function to a VPC/VNet does not guarantee connectivity: the subnet may lack a route, a security group may block the port, DNS may resolve incorrectly, NAT may be missing, a private endpoint may not exist, or the identity may lack permissions.

This lesson focuses on connecting serverless functions to private networks and dependencies in cloud environments. You will distinguish inbound and outbound connectivity, understand VPC/VNet integration models, control egress, choose private endpoints, manage DNS and identities, and design availability, capacity, and observability for the network path.

After this lesson, you will be able to:

- Describe the network path from a function to databases, caches, internal APIs, and cloud services.
- Distinguish VPC/VNet integration, private endpoints, service endpoints, and NAT/egress gateways.
- Select appropriate subnets, route tables, security groups/firewalls, and DNS configurations.
- Explain why a function attached to a private network can still fail to reach a dependency.
- Design connectivity to on-premises or other networks via VPN/private connectivity.
- Manage identities, secrets, TLS, and access permissions following least privilege.
- Evaluate the impact of concurrency, connection pools, ephemeral ports, and IP exhaustion.
- Test and troubleshoot using logs, traces, flow logs, DNS logs, and connectivity checks.

## 1. Why Does Serverless Need Private Networking?

Serverless removes most server management work, but it does not eliminate network boundaries. Functions still execute on provider-managed infrastructure and must follow the networking model offered by the platform.

Common dependencies:

| Dependency | Example | Connectivity Requirements |
|---|---|---|
| Database | PostgreSQL, MySQL, SQL Server, managed relational database | Private IP, private DNS, TLS, database port |
| Cache | Redis or managed cache | Private subnet, TCP port, authentication/TLS |
| Internal API | Business service inside a VPC/VNet | Private load balancer, service discovery, HTTP/gRPC |
| Message broker | Kafka, RabbitMQ, or managed broker | Private endpoint, TLS, identity/credentials |
| Object/file storage | Object storage, shared file service | Private endpoint or controlled egress |
| Identity/secrets | Secret manager, token service, KMS | Private endpoint or permitted egress path |
| On-premises | ERP, legacy database, internal service | VPN, dedicated private connection, or gateway |
| Internet API | Payment gateway, SaaS API, public endpoint | NAT/egress, proxy, DNS, and allow-list if needed |

Private networking reduces exposure surface, controls access sources, and satisfies data requirements. However, private networking increases the number of components to configure and observe: subnets, routes, DNS, endpoints, firewalls, NAT, certificates, and access permissions.

### A Function Has Two Communication Directions

- **Inbound:** clients, event sources, or services calling the function. On many serverless platforms, the provider receives the request or event and dispatches it to the execution environment; the function does not necessarily need a private IP reachable directly from the Internet.
- **Outbound:** the function actively connecting to databases, APIs, or other services. This is the side that typically requires VPC/VNet integration or an equivalent egress mechanism.

Do not confuse a function's ability to receive requests from a public endpoint with the execution environment's ability to reach private resources. The two directions can be configured and secured independently.

## 2. Core Networking Concepts to Understand

### VPC and VNet

A VPC (Virtual Private Cloud) or VNet (Virtual Network) is an isolated logical network in the cloud. It contains subnets, route tables, security policies, gateways, and resources with private IP addresses.

A VPC/VNet typically includes:

- CIDR blocks and subnet address ranges.
- Route tables controlling next hops.
- Security groups, network security groups, or firewalls.
- Internet/NAT gateways or egress gateways.
- Private endpoints/service endpoints.
- DNS resolvers and private DNS zones.
- Peering, transit gateways, or hub networks to connect with other networks.

### Subnet

A subnet is an IP address range belonging to a VPC/VNet, typically bound to an availability zone or fault domain. Subnets can be designed for application workloads, databases, private endpoints, or egress gateways.

The label "public" or "private" subnet does not by itself determine reachability. What matters are the route table, public addressing, gateways, and firewalls. A subnet called private typically lacks a direct route to an Internet gateway for resources without public addresses; it may use NAT or private endpoints for outbound traffic.

### Route Table

A route table determines which next hop handles traffic destined for a given prefix. For example:

- Internal VPC/VNet CIDRs stay local within the network.
- Private database prefixes route via local routes or peering/transit.
- Internet destinations route via a NAT/egress gateway if configured.
- On-premises prefixes route via VPN or a dedicated connection.
- Service prefixes may be routed via a service endpoint depending on the provider model.

A route may exist while traffic is still blocked by firewalls, security groups, network ACLs, or policies on the target side.

### Security Groups and Network Firewalls

Security groups are typically stateful firewalls attached to network interfaces/resources; rules permit traffic based on protocol, port, and source/destination. Network ACLs or subnet firewalls on some platforms can be stateless, requiring rules for both inbound and outbound directions.

Distinguish between:

- Egress rules of the function.
- Ingress rules of the target database/cache/API.
- Network ACLs or firewalls between subnets.
- Firewalls in on-premises systems.
- Policies at the cloud endpoint or service level.

Opening a port on the function side is insufficient if the database side does not permit the corresponding source. Restrict sources by security group, subnet, or identity-aware policy rather than opening an entire CIDR when unnecessary.

## 3. VPC/VNet Integration Models for Serverless

Many platforms allow functions to access resources in a private network through an integration mechanism. Implementation details vary by provider and service type.

### Conceptual Model

~~~mermaid
flowchart LR
    E[Event source / Client] --> P[Serverless platform]
    P --> F[Function execution]
    subgraph VPC["Private network VPC / VNet"]
      S[Integration subnet]
      SG[Security policy]
      DB[(Private database)]
      C[(Private cache)]
      API[Internal API]
      S --> SG
      SG --> DB
      SG --> C
      SG --> API
    end
    F -. private network path .-> S
~~~

The platform launches the function in an execution environment and provides a connection path into the private network via the integration mechanism. Depending on the service, the provider may create network interfaces, use a connector, or manage a dedicated data plane. Users typically configure subnets, security groups, connectors, or network attachments instead of managing fixed VMs.

### Points to Verify

- Does the function support VPC/VNet integration on the chosen runtime/plan?
- Does the integration apply to all outbound traffic or only traffic to private addresses?
- Do multiple subnets/zones need to be selected?
- Where does the provider create network interfaces or connectors?
- Are there limits on network interfaces, IPs, connections, or concurrency?
- During scale-out, does IP allocation or network path provisioning increase startup latency?
- Can the function still access the Internet directly after attachment?
- Can a private DNS resolver or custom DNS be configured?
- Does the integration affect inbound invocations?

Do not infer behavior solely from a feature name. Some services use a VPC connector, some attach network interfaces into subnets, and some provide direct VPC egress. Verify the semantics of the exact product, runtime, region, and plan.

## 4. Distinguishing Function Network Integration from Private Endpoints

These two mechanisms solve opposite sides of the path:

- **VPC/VNet integration:** places the function's outbound path into or through a private network so the function can reach private resources.
- **Private endpoint/private link:** provides a private IP address or network interface so authorized clients within the network can reach a specific service.

For example, a function in a private subnet can connect to a database via private IP. If the function needs to access a managed object storage service, a private endpoint can keep traffic on a private network path instead of traversing the public Internet, depending on service support.

### Service Endpoints

A service endpoint is a routing or policy extension allowing resources in a network to access a cloud service over the provider's backbone/private routing. It differs from a private endpoint in how addresses and access paths are provisioned. Naming and semantics vary by cloud provider.

### Comparison Table

| Mechanism | Purpose | Example |
|---|---|---|
| VPC/VNet integration | Connect the execution environment to a private network | Function calls a private database |
| Private endpoint/private link | Create a private access path to a service | Function accesses storage via a private IP endpoint |
| Service endpoint | Allow a subnet to reach a provider service over supported routing/policy | Subnet accesses object storage service |
| NAT gateway | Allow private resources to initiate outbound connections to public destinations | Function calls a SaaS API |
| VPN/dedicated connectivity | Connect a VPC/VNet to an on-premises or another network | Function calls an internal ERP |

A system may require multiple mechanisms simultaneously. VPC integration does not automatically create private endpoints for every service; likewise, a private endpoint does not automatically place a function inside a VPC.

## 5. Choosing Subnets and Availability Zones

When configuring function network integration, choose subnets with sufficient IP addresses, routes, and reachability to dependencies.

### Subnet Selection

Principles:

- Choose subnets in zones that host dependencies or redundant network paths.
- Allocate a CIDR large enough for network interfaces/connectors and scale-out.
- Avoid using nearly exhausted subnets for functions with spiky concurrency.
- Do not place functions and databases in the same subnet range merely to be "close"; design subnets around security boundaries and operations.
- Inspect subnet route tables and network ACLs.
- Ensure the subnet can reach required DNS resolvers, secret managers, and telemetry endpoints.

### IP Exhaustion

Some platforms allocate network interfaces or private IP addresses per execution environment or connector. When a function scales out, the required number of IPs or network attachments can grow. A small subnet or one shared across many workloads can run out of IPs, causing scale-out failures or slow startups.

Monitor:

- Available IP addresses in each subnet.
- Used interfaces/network attachments.
- Function concurrency and scale-out rate.
- Network interface allocation errors.
- Increased retries or cold starts caused by network provisioning.

Do not assume one invocation always requires exactly one IP. The mapping between concurrency, execution environments, ENIs/connectors, and IPs depends on the provider.

### Multi-Zone

If functions and databases must tolerate zone failures:

- Configure integration across multiple subnets/zones where supported by the platform.
- Ensure dependencies have endpoints or replicas in the required zones.
- Avoid routes or firewalls that only operate in a single zone.
- Check cross-zone latency and data transfer fees.
- Rehearse losing a zone and verify the function can still reach dependencies.

Simply adding subnets across multiple zones does not achieve HA if the database, NAT, DNS, or endpoint still exists in only one zone.

## 6. Routing and Egress: Where Does Function Traffic Go?

When a function calls a dependency, you must know what type of destination it is and how traffic is routed.

### Private Destinations in the Same VPC/VNet

If the database or API has a private IP in the same network, internal routing is usually provided automatically. However, security groups/firewalls must permit the exact port and source.

Example:

- Function integration subnet: `10.20.10.0/24`.
- Database subnet: `10.20.30.0/24`.
- Database listener: TCP `5432`.
- Database security rule permits source from the function's security group on TCP `5432`.

These addresses are illustrative only. In production, prefer referencing security groups/resource identities where supported by the provider to reduce dependence on changing CIDRs.

### Public Destinations via NAT

A function placed in a private subnet that needs to call public APIs typically requires a NAT or egress gateway unless the platform provides another Internet egress path.

Flow:

~~~mermaid
flowchart LR
    F[Function] --> S[Private subnet]
    S --> R[Route table]
    R --> N[NAT / egress gateway]
    N --> I[Internet API]
    I --> N
    N --> F
~~~

NAT typically allows outbound connections from private resources while masking private addresses behind an egress IP. NAT does not by itself allow new inbound connections from the Internet to the function.

Verify:

- Does the NAT gateway have valid routes and sufficient capacity?
- Does a single NAT in one zone create a single point of failure?
- Is the public egress IP stable for allow-listing?
- Are there port mapping or concurrent connection limits?
- Are hourly and per-GB transfer costs acceptable?
- Does DNS resolution succeed before connecting?

### No NAT Does Not Mean No Outbound

If the workload only needs to reach private resources or cloud services via private endpoints/service endpoints, NAT may not be required for those paths. List all destinations and select the network path for each type rather than assuming all traffic must traverse the Internet.

### Egress Allow-Listing

Some organizations only allow functions to call approved destinations. This can be enforced with firewalls, NAT egress IPs, proxies, or network policies depending on platform capabilities.

Do not filter only by IP if a firewall lacks hostname awareness; SaaS endpoints can change IPs. Select an appropriate mechanism such as an FQDN-aware firewall, proxy, or service tags if supported by the provider.

## 7. DNS and Private Name Resolution

A function may have a valid route to a database and still fail if the hostname does not resolve properly.

### Private DNS Zones

A private DNS zone maps internal hostnames to private addresses. For example:

- `db.orders.internal` → `10.20.30.15`
- `cache.orders.internal` → `10.20.31.12`
- `api.inventory.internal` → private load balancer address

The function must use a resolver that can see that private zone. If the VPC/VNet is not associated with the zone or forwarding rule, the function may receive a public address or `NXDOMAIN`.

### Split-Horizon DNS

A single hostname may return different addresses depending on where the query originates. Inside the VPC it returns a private IP; outside it returns a public IP or fails to resolve. This is a useful pattern, but it must be tested from the actual execution environment.

### Hybrid DNS

When accessing on-premises resources, DNS may require conditional forwarding to the organization's DNS resolvers. Determine:

- Which zones are authoritative in the cloud?
- Which zones are authoritative on-premises?
- Which resolvers receive the queries?
- Could forwarding create loops?
- Is UDP/TCP `53` or DNS over TLS/HTTPS blocked by firewalls?
- Do DNS caches/TTLs slow down failover?

### Testing DNS

From a runtime or test environment sharing the same network path, verify:

- Does the hostname resolve?
- Does the result return the expected private IP?
- Is the resolver reliable across multiple subnets/zones?
- After failover, do TTLs and caches update appropriately?

Do not hardcode IP addresses in the application as a permanent workaround for broken DNS. Fix the private zone, resolver, or forwarding configuration properly.

## 8. Connecting to Private Databases

Databases are the most common dependency for serverless functions and also the easiest place to overload during sudden concurrency spikes.

### Connection Path

1. The function receives an event or request.
2. DNS resolves the database hostname.
3. Routing selects the private path to the database subnet/endpoint.
4. Firewalls/security groups permit the source and port.
5. TLS handshake and authentication occur.
6. The driver acquires a connection from a pool or opens a new connection.
7. The query executes and returns the response to the function.

Each step can introduce its own latency or failure. A timeout error is not necessarily a routing issue; it could be DNS, TLS, connection limits, or database overload.

### Connection Storms

Serverless platforms can scale execution environments rapidly. If each environment opens a large connection pool, total database connections can exceed limits.

For example: concurrency of 200 where each environment opens a pool of up to 10 connections creates a potential 2,000 connections. Actual numbers depend on environment reuse, pool lifecycle, and concurrency, so plan capacity across the entire fleet rather than a single invocation.

Mitigations:

- Cap pool size based on database capacity.
- Reuse connections across invocations within an execution environment when supported by the runtime.
- Set appropriate connection timeouts and idle timeouts.
- Use a managed database proxy or connection pooling service when appropriate.
- Cap function concurrency.
- Use queues/buffers to smooth bursts.
- Avoid opening a new connection per query or per invocation whenever possible.
- Monitor active connections, pool wait times, connection errors, and query latency.

### Connection Reuse

In runtimes that support reusing execution environments, initializing the client/connection pool outside the handler reduces overhead across invocations. However, an environment can be terminated at any time; stale connections may expire or break during database failover. The application must detect stale connections and reconnect safely.

### TLS and Authentication

- Enable TLS to the database where supported by the service.
- Verify the certificate chain and hostname.
- Retrieve credentials from a secret manager or use IAM/database authentication when appropriate.
- Rotate secrets without forcing all functions to reconnect simultaneously.
- Never log connection strings containing passwords.
- Scope database users to the required schemas, tables, and actions.

## 9. Connecting to Caches and Message Brokers

### Private Caches

Caches typically reside in private subnets. Functions require the proper routes, ports, security rules, DNS, and authentication.

Evaluate:

- Does the cache cluster have separate primary and reader endpoints?
- Does failover change the DNS record or endpoint?
- How are TLS and authentication enabled?
- How are connection pools and idle timeouts configured?
- Can a cache miss stampede overload the database?
- Do concurrency bursts create too many client connections?

If the cache holds regenerable data, a cache outage can be handled with bounded fallback. Do not let every invocation fall back directly to the database simultaneously when the cache goes down; apply concurrency controls or load shedding.

### Message Brokers

Kafka, RabbitMQ, and managed queues can use private endpoints. Beyond network reachability, check protocols, TLS, SASL/identity, certificates, topic/queue permissions, and DNS.

A consumer function can scale with message or event volume. If each execution environment opens multiple broker connections, the broker can also become overloaded. Limit concurrency and connections, batch messages appropriately, and apply retry/backoff.

### Preventing Retry Storms

When a broker or database experiences transient errors, hundreds of invocations retrying simultaneously can prolong an outage. Use:

- Exponential backoff with jitter.
- Retry caps and deadlines.
- Queue redrive/DLQs.
- Circuit breakers or pausing consumers.
- Concurrency limits.
- Alerts on queue age and dependency error rates.

## 10. Connecting to Internal APIs and Service Discovery

Functions can call internal services through private load balancers, service registries, or private DNS.

### Private Load Balancers

Internal load balancers expose endpoints reachable only from permitted networks. The function integration subnet needs a route to the load balancer, and the backend needs rules permitting the corresponding source.

Verify:

- Listener port/protocol.
- Backend health and readiness.
- TLS termination and certificates.
- Host header/SNI if using virtual hosting.
- Idle timeouts and keep-alive settings.
- DNS records pointing to the correct endpoint.
- Network policies between the function and backend.

### Service Mesh and Service Discovery

Some architectures use a service mesh, proxies, or service registries. Serverless functions may not support sidecar models like long-lived containers; verify integration support. Calling through a gateway or managed internal API endpoint is often a clean option.

### End-to-End Timeouts

If a function timeout is 30 seconds while an internal API has a 60-second timeout, the function may be terminated before the dependency finishes. Order timeouts cleanly:

- Short DNS/connect timeout.
- Appropriate TLS/connection timeout.
- Request timeout shorter than the function deadline.
- Total retry budget within the invocation deadline.
- Buffer time for cleanup and returning the response.

Do not let a function time out while the dependency continues executing side effects without the client knowing the outcome. Use idempotency keys for retryable operations.

## 11. Connecting to On-Premises or Other Networks

A function may need to access an ERP, file server, or database in a data center. Connectivity can run over site-to-site VPN, dedicated private connections, transit gateways, or hub-and-spoke networks.

### Components to Prepare

- Non-overlapping VPC/VNet address ranges with on-premises networks.
- VPN gateway or private circuit.
- Appropriate route propagation/static routes.
- Firewalls on both sides.
- DNS forwarding and private zones.
- MTU, fragmentation, and throughput considerations.
- Tunnel/circuit redundancy.
- Monitoring for tunnels, BGP routes, and packet loss.

### CIDR Overlap

If a VPC/VNet shares IP ranges with on-premises networks, routing cannot unambiguously reach destinations. Plan IP address management before deployment, especially across multiple accounts/projects and regions.

### Latency and Availability

VPNs or dedicated circuits can drop connectivity. Functions need timeouts, bounded retries, and business-appropriate fallbacks. For long-running jobs, queuing work and retrying when connectivity recovers is usually safer than holding invocations open too long.

Never assume private connectivity always has low latency or unlimited bandwidth. Measure RTT, throughput, and packet loss along the actual network path.

## 12. Protecting Networks with Least Privilege

Private networking reduces public exposure, but it does not replace authorization. A function inside a private subnet can still be compromised or abused if its role is overly broad.

### Security Groups/Firewalls

- Allow functions to reach only required dependencies.
- Restrict database ingress to specific sources.
- Do not open entire subnets or entire VPCs unnecessarily.
- Use security group references or resource identities when supported by the provider.
- Separate subnets/SGs by workload role and environment.
- Review egress rules; default allow-all rules undermine egress controls.

### Identity and Secrets

- Use a dedicated execution role/managed identity/service account per function.
- Grant read access only to the exact secrets and resources needed.
- Prefer workload identities or short-lived credentials.
- Plan secret/certificate rotations to avoid simultaneous fleet restarts.
- Never embed credentials in source code, environment files, or deployment artifacts when a secret manager is available.
- Audit secret reads and key operations.

### TLS

Use TLS for connections to databases, brokers, and internal APIs when appropriate. Check certificate expiration, trust stores, and hostname validation. Never disable certificate verification to work around environment errors.

### Network Segmentation

Segment functions by permission group:

- Order-processing functions can reach the order database and payment queue.
- Report-generation functions can only read reporting data and write objects to the reporting bucket.
- Notification-sending functions can reach email/SMS providers but need no business database access.

Segmentation limits the blast radius if a single function is exploited.

## 13. Concurrency, Ephemeral Ports, and IP Capacity

Serverless concurrency directly affects simultaneous network connections. Raising concurrency increases throughput, but also increases sockets, NAT ports, connection pools, DNS queries, and pressure on dependencies.

### Estimating Potential Connections

A simple estimation formula:

~~~text
Potential dependency connections
  ≈ concurrent execution environments
    × connections per environment
~~~

This is a capacity-planning estimate, not an exact mapping formula between invocation concurrency and network interfaces. One environment may handle multiple concurrent invocations depending on the runtime, and providers may share or manage network attachments in platform-specific ways.

### Ephemeral Ports and NAT

Outbound TCP connections require ephemeral source ports. NAT gateways/proxies have port-mapping and connection-tracking limits. Too many short-lived connections, lack of reuse, or many distinct destinations can cause port exhaustion or connection failures.

Mitigations:

- Reuse connections when supported by the runtime.
- Use keep-alive and bounded pools.
- Reduce unnecessary distinct destinations/connections.
- Limit concurrency and batch requests.
- Monitor NAT port allocations, active connections, and errors.
- Split egress paths or increase capacity per provider guidance.

### Subnet IP Exhaustion

If the platform allocates IPs/interfaces as the workload scales, subnets can run out of addresses. Reserve IP space for functions, private endpoints, databases, nodes, and other resources. Do not count only VMs; count network interfaces created by service-managed integrations as well.

### Backpressure

When a dependency lacks capacity, functions should not continue scaling without bound. Use queues, reserved/max concurrency, rate limits, or load shedding to regulate incoming work. Monitor queue age and completion time to prevent silent backlog growth.

## 14. Availability and Resilience of the Network Path

A function may execute across many environments while still depending on a single NAT gateway, a single DNS resolver, or a single database endpoint.

Check:

- Does function integration support multiple subnets/zones?
- Are NAT/egress gateways redundant across zones?
- Do private endpoints span zones or support failover?
- Does the database have multi-AZ/replicas and a stable endpoint?
- Do DNS resolvers have redundant paths?
- Do VPNs/circuits have multiple tunnels or backup routes?
- Are firewall policies consistent across zones?
- When a dependency fails, does the function have proper timeouts/fallbacks?

### Failure Domains

Analyze failures by layer:

1. Execution environment or function runtime.
2. Integration connector/network interface.
3. Subnet or availability zone.
4. Route table, NAT, firewall, or private endpoint.
5. DNS resolver/private zone.
6. Dependency service.
7. VPN/transit or on-premises network.

Testing only that a function invocation succeeds may leave these failure domains unverified.

### Circuit Breakers and Fallbacks

For non-essential dependencies, use a circuit breaker to stop calling after repeated failures and retry after a cooldown period. Fallbacks can use caches, queues, or degraded status responses. For mandatory dependencies such as an order-writing database, do not pretend success when commits fail; return controlled errors and preserve idempotent retryability.

## 15. Observing the Network Path and Dependencies

Monitoring must answer why a function cannot connect: DNS, routing, firewall, TLS, identity, capacity, or the dependency itself?

### Metrics

- Invocation count, error rate, duration, and timeouts.
- Cold start/init duration.
- Concurrent executions and throttling.
- DNS lookup latency/failures.
- Connection establishment latency and TLS handshake time.
- Database active connections, pool wait, and query latency.
- Cache latency, hit ratio, and connection errors.
- Broker connections, publish/consume errors, and queue age.
- NAT gateway bytes, active connections, and port allocations/errors where provided.
- Subnet IP availability and network interface counts.
- VPN tunnel state, BGP routes, RTT, packet loss, and throughput.
- Private endpoint health and accepted/rejected flows.

### Logs and Traces

Logs should record destination service name, operation, connect duration, error class, and correlation ID. Never log passwords, tokens, session cookies, or full connection strings containing secrets.

Distributed tracing helps isolate:

- Function initialization.
- DNS/connect/TLS.
- Connection pool wait.
- Dependency request duration.
- Retries/backoff.
- Serialization and application processing.

Not every runtime/provider automatically generates DNS/connect spans. Client-library instrumentation or custom metrics may be needed.

### Flow Logs and DNS Logs

VPC/VNet flow logs help identify accepted/rejected flows, source/destination IPs, ports, and protocols depending on service capabilities. DNS query logs show what hostname queries returned or whether they failed.

Flow logs do not necessarily contain full details on why a firewall rule rejected traffic or application payloads. Correlate them with security rules, route tables, DNS logs, and traces during investigations.

## 16. Workflow for Configuring a Function to Connect to a Private Database

Suppose an order-processing function needs to access a private PostgreSQL database inside a VPC/VNet.

### Step 1: Map Dependencies

Document:

- Function name/runtime/region.
- Database hostname, private IP range, and port.
- Database subnet/zone and security policy.
- Secret or identity authentication method.
- DNS zone/resolver.
- Database RPO/RTO or availability requirements.
- Expected concurrency and connection limits.

### Step 2: Prepare the Network

- Choose integration subnets with sufficient IPs.
- Configure routes to the database subnets.
- Ensure network ACLs/firewalls allow TCP `5432`.
- Database ingress allows only the function security group or approved sources.
- Associate private DNS zones or resolvers.
- If Internet/external API access is required, add NAT/egress per policy; do not open broad egress unnecessarily.

### Step 3: Configure Function Integration

- Attach the function to the appropriate subnets/connectors.
- Assign a dedicated security group/NSG.
- Verify the function runtime can reach DNS and private endpoints.
- Set appropriate timeouts and concurrency limits.
- Verify execution role/managed identity permissions.

### Step 4: Connect Securely

- Retrieve credentials from the secret manager or use database IAM authentication.
- Enable TLS and verify certificates.
- Create a small, bounded connection pool.
- Reuse clients when supported by the runtime.
- Handle stale connections and database failover.

### Step 5: Test

- Resolve the hostname from the actual network environment.
- Verify the TCP handshake to the port.
- Verify the TLS handshake/certificate.
- Authenticate to the database.
- Run read-only queries first.
- Test with increasing concurrency.
- Simulate database failover or network interruption in staging.
- Verify function timeouts/retries do not create duplicate transactions.

### Flow Diagram

~~~mermaid
sequenceDiagram
    participant E as Event source
    participant F as Serverless function
    participant D as Private DNS
    participant N as VPC route/security
    participant DB as Private database
    participant SM as Secret manager
    E->>F: Invoke
    F->>SM: Get credential using workload identity
    SM-->>F: Short-lived/managed secret
    F->>D: Resolve database hostname
    D-->>F: Private address
    F->>N: TCP + TLS connection
    N->>DB: Allow approved source and port
    DB-->>F: Query result
    F-->>E: Result/acknowledgement
~~~

## 17. Conceptual Configuration Example

The configuration below illustrates what needs to be declared. It is not a schema used directly by any specific cloud provider.

~~~yaml
function:
  name: orders-handler
  runtime: python
  timeout_seconds: 20
  max_concurrency: 40
  network:
    integration: vpc
    subnets:
      - private-app-zone-a
      - private-app-zone-b
    security_groups:
      - sg-orders-function
  dependencies:
    database:
      hostname: db.orders.internal
      port: 5432
      tls: required
      credential_source: secret-manager
    internal_api:
      hostname: inventory.internal
      port: 443
      tls: required
  egress:
    internet:
      enabled: false
    private_endpoints:
      - object-storage
      - secret-manager
  observability:
    metrics: enabled
    tracing: enabled
    network_flow_logs: enabled
~~~

Subnet, security group, and endpoint values must be replaced with actual environment resources. Disabling Internet egress is appropriate only when every required dependency has a private path and the runtime can still reach necessary control/telemetry endpoints as required by the provider.

### Example Security Rules

| Target Resource | Inbound Rule | Source |
|---|---|---|
| PostgreSQL | TCP 5432 | Function's security group |
| Redis | Configured TLS TCP port | Function's security group |
| Internal HTTPS API | TCP 443 | Approved function subnet/SG |
| DNS resolver | UDP/TCP 53 or resolver endpoint | Permitted network |
| Secret manager private endpoint | TCP 443 | Function SG/subnet |

Do not copy this table into rules open to all sources. Use specific sources, exact ports, and environment-scoped policies.

## 18. Differences Across Cloud Platforms

Feature names and configuration details vary by provider. Consult the documentation for the exact service and plan before deploying.

| Platform | Common Network Integration Approaches | What to Verify |
|---|---|---|
| AWS Lambda | VPC configuration with subnets and security groups; outbound to private resources; public Internet egress typically requires NAT or an appropriate private path | ENI/IP capacity, subnet AZs, routes, NAT, endpoints, execution role, and cold start/network provisioning |
| Azure Functions | Regional VNet integration for outbound; private endpoints for inbound access to the app or to dependency services | Supported hosting plans, subnet delegation/sizing, route-all behavior, NSG/UDR, DNS, and NAT/egress |
| Google Cloud Functions/Cloud Run functions | Serverless VPC Access connector or direct VPC egress depending on product/runtime/region | Connector capacity or direct egress settings, subnets/IPs, routes, firewalls, DNS, and Internet egress |
| Cloud Run | Direct VPC egress or connector depending on service configuration | Network tags/service identity, subnet sizing, startup/scale behavior, and egress mode |

This table is a conceptual guide and does not replace version-specific configuration documentation. Features and limits can vary by product generation, region, and plan.

### Questions to Answer Before Selecting a Provider Feature

- Does it support private inbound, private outbound, or both?
- Can multiple subnets and zones be selected?
- Does Internet traffic go through NAT?
- Is there route-all or private-prefix-only routing?
- How are custom/private DNS zones supported?
- Does it require subnet delegation or interface creation permissions?
- Does the connector have throughput/concurrency/IP limits?
- Are cold starts affected when provisioning the network path?
- Are private endpoints available for secrets, storage, logging, and telemetry?

## 19. Layer-by-Layer Network Troubleshooting

When a function fails to connect, verify in order from target name resolution up to the application layer.

### DNS Failures

Symptoms: hostname fails to resolve, resolves to a wrong public IP, or resolves intermittently.

Checks:

- Is the private zone associated with the VPC/VNet?
- Which resolver is the function using?
- Is conditional forwarding configured correctly?
- Are the proper A/AAAA or alias records present?
- Are TTLs and caches holding stale records?
- Are DNS firewalls/policies blocking queries?

### TCP Connection Timeouts

Symptoms: connect timeout or SYN never completes.

Checks:

- Does the function actually have network integration enabled?
- Does the subnet route reach the destination prefix?
- Do security groups/NSGs/ACLs/firewalls permit traffic on both sides?
- Is the database/listener listening on the expected IP/port?
- Do peering/transit/VPN links have bidirectional routes?
- Is the NAT/egress gateway healthy and properly routed?
- Is there CIDR overlap or a blackhole route?

### Connection Refused

Symptoms: the IP is reachable, but the port returns RST/refused.

Checks:

- Is the target service running and listening on the right port?
- Does the endpoint point to the correct backend?
- Is a security policy or proxy actively rejecting rather than dropping packets?
- Has the database hit a limit or paused its listener?

### TLS Handshake/Certificate Failures

Checks:

- Has the certificate expired?
- Does the hostname/SAN match?
- Does the function runtime trust the appropriate CA?
- Are TLS versions/ciphers compatible?
- Is the runtime clock accurate?
- Is a proxy substituting certificates or requiring a client certificate?

Never disable certificate verification just to make a connection "work".

### Authentication/Authorization Failures

If TCP and TLS succeed but you receive `401`/`403` or a database authentication error:

- Verify the correct workload identity.
- Check secret versions/rotation.
- Check roles, database grants, and resource policies.
- Verify token audience/expiration.
- Check clock skew and permissions on the private endpoint.

### Failures That Appear Only at Scale

Checks:

- Subnet IP exhaustion.
- Connector/ENI capacity.
- NAT port exhaustion or connection tracking limits.
- Database max connections and pool sizes.
- DNS query rate or resolver capacity.
- Concurrency limits and burst scaling.
- Cold start/network provisioning times.

### Test Commands in a Diagnostic Environment

Some utilities may not exist inside managed serverless runtimes. You can run checks from a VM/debug container placed in the same subnet, security group, and DNS path:

~~~bash
# DNS lookup
nslookup db.orders.internal

# TCP reachability (if nc is available)
nc -vz db.orders.internal 5432

# TLS handshake (if openssl is available)
openssl s_client -connect db.orders.internal:5432 -servername db.orders.internal

# HTTP dependency timing
curl -sS -o /dev/null -w 'connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' https://inventory.internal/health
~~~

Testing from a VM in the same subnet only proves that VM's network path. The function may use a different connector, security group, identity, or DNS context; verify from the function itself using a safe diagnostic invocation, or inspect the network attachment with provider tools.

## 20. Performance and Cost of Private Connectivity

Private network integration can increase both cost and latency depending on the architecture.

Cost drivers:

- Hourly NAT gateway charges and data processing fees.
- Hourly private endpoint charges, endpoint usage, or data fees.
- Cross-zone/cross-region traffic.
- VPN/dedicated connectivity.
- Connector capacity or network appliances.
- Logging/flow log ingestion.
- Data transfer to on-premises or SaaS.

Latency drivers:

- DNS lookup and connection setup.
- TLS handshake.
- NAT/proxy hops.
- Cross-zone/region routing.
- Connector throughput contention.
- Connection pool wait times.
- Database/cache saturation.

### Optimization Approaches

- Use private endpoints for critical cloud services when appropriate.
- Reuse connections and enable keep-alive.
- Co-locate functions and dependencies in nearby regions/zones aligned with HA design.
- Batch requests to reduce connections and round trips.
- Use caching properly to reduce dependency calls.
- Limit payload sizes and avoid sequential dependency calls when safe parallelism is possible.
- Match concurrency limits to database and NAT capacity.
- Track NAT, endpoint, and cross-zone transfer costs per workload.
- Avoid creating duplicate private endpoints when a securely managed shared network service can be used.

Do not optimize costs by removing NAT or endpoints if doing so exposes dependencies or violates security boundaries. Compare total cost, risk, and latency across options.

## 21. Checklist for Deploying Functions into Private Networks

### Design and Dependencies

- [ ] Listed all database, cache, API, broker, storage, secret, and on-premises dependencies.
- [ ] Identified inbound and outbound flows separately.
- [ ] Identified private vs. public destinations and required protocols/ports.
- [ ] Selected VPC/VNet integration, private endpoints, service endpoints, or NAT appropriately.
- [ ] Verified CIDRs do not overlap with other networks.

### Subnets, Routing, and DNS

- [ ] Subnets have sufficient IPs for expected scale and network attachments.
- [ ] Redundant subnets/zones are configured when HA is required.
- [ ] Route tables have valid next hops for all dependencies.
- [ ] Security groups/NSGs/firewalls permit exact sources, destinations, protocols, and ports.
- [ ] Private DNS zones/resolvers/forwarding are configured and tested.
- [ ] NAT/egress IPs and partner allow-lists are ready if Internet outbound is needed.
- [ ] VPN/private circuits and bidirectional routes are verified if connecting on-premises.

### Identity and Data

- [ ] Function uses a dedicated workload identity/managed identity.
- [ ] Secrets are retrieved from a secret manager with rotation enabled.
- [ ] TLS and certificate validation are enabled.
- [ ] Database roles and service permissions follow least privilege.
- [ ] No secrets or tokens are written to logs.
- [ ] Dependencies have appropriate timeouts, retries, and idempotency.

### Capacity and Availability

- [ ] Function concurrency is capped according to dependency capacity.
- [ ] Connection pools and connection reuse are configured.
- [ ] NAT ports, subnet IPs, and connector capacity are monitored.
- [ ] Databases/caches/brokers have HA and appropriate failover endpoints.
- [ ] Egress paths and DNS have redundancy across failure domains.
- [ ] Backpressure, DLQs, or load shedding are in place when dependencies overload.

### Observability and Testing

- [ ] Invocation, duration, error, concurrency, and cold start metrics are collected.
- [ ] Dependency latency, pool wait, and connection failure metrics are collected.
- [ ] Flow logs, DNS logs, or equivalent tools are enabled.
- [ ] Tested actual DNS, TCP, TLS, authentication, and queries.
- [ ] Tested burst scaling, IP exhaustion, and connection limits in staging.
- [ ] Tested loss of a zone, NAT, VPN, or dependency within permitted scope.
- [ ] Runbooks and owners exist for network incidents.

## 22. Self-Check

1. What two different problems do VPC/VNet integration and private endpoints solve?
2. Why can a function attached to a private subnet still fail to connect to a database?
3. When does a function need a NAT gateway, and when can a private endpoint replace the Internet path?
4. What symptoms can occur if a private DNS zone is not associated with the VPC/VNet?
5. Why must security groups on both the function and the database be checked?
6. How can serverless concurrency cause a database connection storm?
7. How do subnet IP exhaustion and NAT ephemeral port exhaustion differ?
8. Why does testing from a VM in the same subnet not prove the function has the exact same network path?
9. What components must be prepared for a function to access an on-premises system?
10. Design a secure connectivity path from an order-processing function to private PostgreSQL, Redis, and an internal inventory API.
11. When a dependency is slow, how should timeouts, retries, circuit breakers, and concurrency limits be combined?
12. Which metrics and logs help distinguish DNS, routing, firewall, TLS, and authentication failures?

Connecting serverless to private networks is an end-to-end problem. The function needs proper network integration, subnets need available addresses, routes need valid next hops, DNS must return the right endpoints, firewalls must permit the exact flows, and dependencies must have sufficient capacity. Identities, secrets, and TLS protect access; concurrency limits, connection reuse, and backpressure keep the system stable at scale. By testing from the actual execution environment and observing each network layer, teams can place functions into private architectures while maintaining control over security, performance, availability, and cost.
