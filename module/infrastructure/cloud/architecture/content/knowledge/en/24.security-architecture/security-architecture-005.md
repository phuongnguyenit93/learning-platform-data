# Network Segmentation and Service-to-Service Communication Control

## 1. Why Does a Cloud Architecture Need Network Segmentation?

A cloud application typically consists of many components: public frontends, API gateways, backend services, databases, queues, caches, management systems, and third-party integrations. If every component sits in a flat network and can connect freely, a single compromised workload can scan and reach many other resources. Network segmentation narrows communication paths, restricts traffic flows, and shrinks the blast radius during an incident.

In the **CLOUD_ARCHITECTURE** module, architectures are designed from business requirements through networking, compute, data, and deployment model choices, then evaluated across reliability, security, scalability, cost, and operations. Network segmentation is part of enforcing trust boundaries: every connection needs a defined source, destination, protocol, purpose, identity, and policy.

**Network segmentation** divides infrastructure into zones or communication domains with distinct trust levels and connectivity rules. **Service-to-service communication control** governs which workloads may call which workloads, over what protocols, how they authenticate, and which operations are allowed.

After this lesson, you can:

- Identify trust boundaries, ingress/egress paths, and traffic flows between components.
- Design VPCs/VNets, subnets, route tables, security groups, firewalls, and private endpoints.
- Distinguish network reachability from authentication and application authorization.
- Apply microsegmentation, service identity, and mutual TLS (mTLS).
- Control north-south, east-west, and outbound Internet/third-party egress traffic.
- Design DNS/service discovery, Kubernetes NetworkPolicies, and service meshes.
- Test policies following deny-by-default and least-privilege principles.
- Observe flows, detect anomalous connections, and operate policy changes safely.

## 2. Trust Boundaries and Traffic Flows

### 2.1. North-South and East-West Traffic

- **North-south traffic** flows between the system and external parties: the Internet, end users, partners, corporate networks, or on-premises environments.
- **East-west traffic** flows between workloads inside the environment: API gateway to services, services to databases, workers to queues, and service-to-service calls.

An architecture can protect north-south traffic well with a WAF/API gateway and still carry severe east-west risk if every backend can call every other backend and shares credentials.

### 2.2. BookingCloud Example

BookingCloud includes:

- Web/mobile clients accessing APIs via CDN, WAF, and API gateway.
- Booking service handling orders.
- Inventory service reserving equipment slots.
- Payment service connecting to a payment provider.
- Notification worker sending emails via a provider.
- Databases, caches, and message brokers inside private zones.
- Platform operators accessing administration via identity-aware access or controlled bastions.

~~~mermaid
flowchart TB
    INTERNET["Internet / clients"] --> EDGE["CDN + WAF"]
    EDGE --> GW["Public API gateway"]
    subgraph PRIVATE["Private application network"]
      GW --> BOOK["Booking service"]
      BOOK --> INV["Inventory service"]
      BOOK --> PAY["Payment service"]
      WORKER["Notification worker"]
      BOOK --> DB[("Booking DB")]
      INV --> CACHE[("Cache")]
      BOOK --> MQ[("Message broker")]
      WORKER --> MQ
    end
    PAY --> EXT["Payment provider"]
    WORKER --> EMAIL["Email provider"]
    OPS["Admin access path"] --> PRIVATE
~~~

This diagram shows logical zones. When implementing, determine whether each arrow is a direct connection or traverses a proxy/gateway; which network routes and policies permit it; which identity is authenticated; which protocol is used; and which logs prove the connection.

### 2.3. Four Questions for Every Connection

For each communication path, specify:

1. **Who:** what is the source workload or principal?
2. **Where:** which networks, subnets, namespaces, accounts/projects, or regions do source and destination belong to?
3. **What:** which protocols, ports, API operations, or resources are permitted?
4. **Why:** what is the business purpose and who owns the connection?

A rule like "allow all traffic from application subnet to database subnet" is usually too broad. Drill down to the appropriate workload, protocol, port, identity, and operation.

## 3. Core Network Segmentation Models

### 3.1. VPCs/VNets and Subnets

A VPC (Virtual Private Cloud) or VNet is a private logical network inside a cloud account/subscription/project. Subnets partition IP ranges and typically attach to route tables, network ACLs, or security policies.

A common organization:

| Zone | Components | Access Characteristics |
|---|---|---|
| Edge/public | Load balancers, NAT gateways, public ingress | Accepts published traffic, restricts inbound |
| Application/private | Backend services, workers | Receives no direct Internet connections |
| Data/private | Databases, caches, brokers | Accepts connections only from required workloads |
| Management | Bastions, management agents, monitoring | Dedicated to approved administrative paths |

Names like "public" or "private" do not guarantee security on their own. A subnet with a public route where instances lack public IPs may not be directly reachable; conversely, a private subnet can still send outbound Internet egress via NAT. Inspect actual route tables, address assignments, firewalls, and policies.

### 3.2. Availability Zones and Failure Domains

Subnets typically map to an Availability Zone or failure domain within a region. Spreading application and data planes across multiple zones improves resilience, provided policies remain consistent:

- Every zone must have equivalent routes and security policies.
- Health checks/load balancers direct traffic only to healthy targets.
- Cross-zone traffic, replication, and failover still traverse controlled connections.
- Do not widen rules overly just to simplify failover.
- Check DNS/private endpoint dependencies when a zone fails.

### 3.3. Route Tables and Traffic Paths

Route tables determine which target handles traffic for a given CIDR/prefix: local routes, internet gateways, NAT gateways, transit gateways, VPNs, peering, or private endpoints. Firewalls/security policies then determine whether traffic is allowed.

Diagram both forward and return paths. Stateful firewalls automatically track connections; stateless ACLs require rules in both directions including ephemeral ports. An existing route does not mean a connection is allowed; an allow rule likewise cannot pass traffic if no route exists.

~~~mermaid
flowchart LR
    USER["Client"] --> IGW["Internet gateway"]
    IGW --> LB["Public load balancer"]
    LB --> APP["Private application subnet"]
    APP --> DB["Private data subnet"]
    APP --> NAT["NAT / controlled egress"]
    NAT --> EXT["Approved external APIs"]
    OPS["Admin network"] --> VPN["VPN / identity-aware gateway"]
    VPN --> MGMT["Management subnet"]
~~~

## 4. Ingress: Controlling Inbound Traffic

Ingress is traffic entering from outside a workload or network boundary. Common layers include:

- DNS and CDN: route to the right edge and reduce origin exposure.
- DDoS protection: absorb or filter malicious traffic at the right layer.
- WAF: inspect HTTP requests against rules, signatures, and application context.
- Load balancer/API gateway: TLS termination, routing, authentication, rate limiting, and request validation.
- Network firewall/security group: constrain source, destination, protocol, and port.
- Application authorization: verify which resources/operations the user/client may invoke.

Never expose databases, caches, brokers, or management ports directly to the Internet. Public entry points should be components built to receive external traffic and forward only to specific backends.

### 4.1. TLS Termination and Next Hops

If TLS terminates at a CDN or load balancer, payloads are decrypted there. The hop from load balancer to backend must be protected according to the threat model, typically with internal TLS or mTLS. Backend identity should also be verified if the proxy acts as a trust boundary.

### 4.2. Headers and Client Identity

Do not trust headers such as `X-Forwarded-For`, `X-User`, or `X-Tenant-ID` from raw clients. Trust only metadata overwritten/normalized by a trusted proxy, and still have the application authenticate principals via tokens/sessions. Headers can assist routing/observability but never replace authentication or authorization.

## 5. Egress: Controlling Outbound Traffic

Egress is often overlooked because applications "need the Internet to function." However, a compromised workload can use unrestricted outbound access to fetch payloads, exfiltrate data, or reach command-and-control servers.

### 5.1. Egress Control

Measures include:

- Do not allow unrestricted outbound access from all workloads.
- Allow only necessary destinations/services by hostname, IP range, port, or identity-aware proxy where appropriate.
- Use NAT gateways or egress proxies to centralize logging, filtering, and quotas.
- Block direct Internet connectivity if workloads only need private endpoints.
- Apply DNS filtering, domain allowlists, and monitoring for newly observed/unusual domains.
- Control metadata service and cloud control-plane endpoints; workloads may only access what they need.
- Restrict uploads/data transfers to public storage or external services.

### 5.2. IP and Hostname Allowlists

IP allowlists can be hard to maintain when providers rotate addresses or use CDNs/anycast. Hostname allowlists require proxy/DNS-aware enforcement; a standard L3/L4 firewall often only inspects IPs. Avoid resolving a hostname once and caching the IP indefinitely.

For third-party APIs, use official endpoints, TLS validation, scoped credentials, quotas, and auditing. An egress allowlist does not replace server certificate validation.

### 5.3. Private Endpoints

Private endpoints/private links let workloads reach cloud services over private network paths or private addresses, depending on the provider. Benefits include reduced public exposure and tighter path control. However:

- Proper private DNS zones/records are required.
- Routes, endpoint policies, and resource policies must align.
- Private network reachability still requires IAM/service authentication.
- Cross-account/project access still requires authorization.
- Endpoint hourly, data-processing, and cross-zone/region traffic costs must be accounted for.

## 6. Security Groups, Network ACLs, and Firewalls

Cloud providers use distinct names and semantics. General concepts include:

| Component | Typical Scope | Characteristics |
|---|---|---|
| Security group | Network interface/instance/workload | Usually stateful; allow rules by source/destination, protocol, port |
| Network ACL | Subnet | Can be stateless; requires explicit inbound/outbound rules and ordering |
| Network firewall | VPC/VNet or transit path | May filter L3/L4/L7, domains, or intrusion signals depending on product |
| Host firewall | OS/container node | Protects traffic to specific processes/hosts |
| Kubernetes NetworkPolicy | Pod/namespace selector | Restricts pod-level ingress/egress; requires CNI enforcement |
| Service mesh policy | Workload identity/HTTP/gRPC | Can enforce identity, service, and operation controls at L7 |

Do not duplicate identical rules across layers without clear ownership. Define which layer is the primary enforcement point, which provides defense in depth, and who keeps them synchronized.

### 6.1. Sample Rule Matrix

| Source | Destination | Protocol/Port | Action | Reason |
|---|---|---|---|---|
| Public edge LB | API gateway | TCP 443 | Allow | Client API ingress |
| API gateway | Booking service | TCP 8443 | Allow | Internal API routing |
| Booking service | Inventory service | TCP 8443 | Allow | Hold/release slots |
| Booking service | Booking DB | TCP 5432 | Allow | Database access |
| Inventory service | Cache | TCP 6379/TLS per config | Allow | Cache operations |
| Application subnets | Database admin port | Any | Deny | Do not expose general admin access |
| Backend workloads | Internet | Any | Deny by default | Egress only through approved paths |

Ports in this table are examples only. Always verify actual listeners, TLS modes, database versions, and service configurations.

### 6.2. Stateful vs. Stateless

Stateful rules track connection state and typically allow return traffic for permitted connections. Stateless ACLs evaluate each packet/direction independently, requiring matching rules for ephemeral return ports. A common mistake is configuring outbound rules correctly while return responses drop because the stateless ACL lacks the reverse rule.

### 6.3. Rule Ordering and Implicit Behavior

Some firewalls evaluate first-match, others use priorities or implicit default-deny. Verify:

- Are any rules broader than intended?
- Is the default allow or deny?
- Do IPv4 and IPv6 have consistent policies?
- Are rules inherited from organization/account levels?
- Are there bypass paths via peering, VPN, or public IPs?
- Do rules expire or undergo periodic review?

## 7. Microsegmentation

Traditional segmentation splits subnets by tier. **Microsegmentation** narrows policies down to specific workloads, services, processes, or identities to curb lateral movement if one component is compromised.

For example, instead of "every pod in the app subnet can call every other pod," policy specifies:

- Booking service calls only Inventory API and Booking DB.
- Notification worker consumes only the notification queue and calls the email provider via an egress proxy.
- Payment service accepts commands only from Booking service and calls the payment provider.
- Analyst workloads reach only read-only reporting endpoints.

Microsegmentation can be implemented with host firewalls, per-workload security groups, Kubernetes NetworkPolicies, service meshes, or distributed firewalls.

### 7.1. Benefits and Trade-Offs

| Benefits | Trade-Offs |
|---|---|
| Reduces lateral movement and blast radius | More policies to manage; requires catalogs/automation |
| Clarifies service dependencies | Can accidentally block traffic when dependencies change |
| Supports least privilege | Harder to debug when policies are distributed |
| Easier to prove permitted flows | Requires accurate inventory and policy lifecycle |

Do not hand-craft hyper-granular policies that become unmaintainable. Use governed identities/labels/selectors, templates, and automated reviews.

## 8. Service Identity and Mutual TLS

Network location only shows a workload can reach an endpoint. It does not prove who the workload is. When services run inside the same cluster/VPC, an attacker inside a compromised workload can try calling other internal endpoints.

### 8.1. Service Identity

Every workload should have a distinct identity, such as a service account, workload identity, or certificate subject. Identities can be issued by the platform control plane with a defined lifecycle:

- Provision identity when deploying the workload.
- Bind identity to service, environment, namespace, or workload attributes.
- Issue short-lived credentials/certificates.
- Rotate automatically.
- Revoke when the workload is deleted or suspected compromised.
- Audit issuance, usage, and identity changes.

Avoid sharing one static API key across multiple microservices. If leaked, you cannot identify the caller and revocation has a huge blast radius.

### 8.2. TLS and mTLS

- TLS authenticates the server to the client and encrypts the channel; depending on configuration, clients may authenticate with tokens or application credentials.
- mTLS requires both client and server to present certificates/identities, providing mutual workload authentication at the transport layer.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Booking service
    participant B as Inventory service
    A->>B: TLS ClientHello + client certificate
    B->>B: Validate client cert and trust chain
    B-->>A: Server certificate
    A->>A: Validate server cert and identity
    A->>B: Encrypted HTTP request
    B->>B: Authenticate workload identity
    B->>B: Authorize requested operation
    B-->>A: Protected response
~~~

mTLS protects identity and the transport channel, but does not automatically grant the client access to every API. Applications still need authorization by service identity, API operation, tenant/resource scope, and business policy.

### 8.3. Certificate Lifecycle

- Use a governed CA/trust bundle and verify the chain and SAN/identity.
- Issue short-lived certificates or automate rotation.
- Maintain revocation/rotation procedures if a workload or CA is compromised.
- Monitor expiring certificates and handshake failures.
- Never disable certificate validation as a "quick fix" during an incident.
- Periodically audit trust bundles when multiple CAs or clusters communicate.

## 9. The Network Layer Does Not Replace L7 Authorization

L3/L4 policies generally answer: which IP may connect to which IP/port? L7 policies answer: which identity may invoke which method/path/operation?

For example, Booking service may be allowed to open TCP connections to Inventory service on port 8443. That network allowance does not mean Booking service should call every route such as admin, export, or delete. Restrict further using:

- OAuth 2.0 client credentials or workload identity tokens.
- API-specific audience/scopes.
- mTLS identity paired with authorization policies.
- API gateway/service mesh authorization policies.
- Application-level RBAC/ABAC on business resources.

### 9.1. Logical Policy Example

~~~yaml
service: booking-service
identity: spiffe://bookingcloud/prod/booking
allowedDestinations:
  - service: inventory-service
    protocol: https
    port: 8443
    allowedOperations:
      - POST /internal/holds
      - DELETE /internal/holds/{holdId}
  - service: booking-db
    protocol: tcp
    port: 5432
denied:
  - service: payment-admin
  - destination: public-internet
conditions:
  requireMutualTLS: true
  requireWorkloadToken: true
  tokenAudience: inventory-api
  environment: production
~~~

This is pseudoconfiguration, not syntax directly executable on a cloud provider or service mesh. During implementation, map exact identities, selectors, ports, paths, methods, trust domains, and enforcement points, and test that all bypass paths are blocked.

## 10. DNS and Service Discovery

In dynamic architectures, pods, tasks, or VMs can change IP addresses after deployments, scaling, or failovers. Service discovery provides a way to locate services via stable names instead of hardcoded IPs.

Components may include:

- Private DNS zones/service names.
- Kubernetes Services and cluster DNS.
- Service registries/control planes.
- Load balancers or service mesh endpoint discovery.
- Health checks and endpoint readiness.

### 10.1. DNS Is Not Authorization

Failing to resolve a name can block a connection path, but knowing a DNS name does not grant permission to access it. Private DNS only reduces exposure; identity, network policies, and application authorization are still mandatory.

### 10.2. DNS and Failover

TTL, caching, negative DNS responses, and resolver behavior affect endpoint switchover times. A client may retain an old IP after a record changes. Coordinate DNS TTLs with connection pools, retries, health checks, and deadlines.

Do not assume lowering DNS TTL to a tiny value always speeds up failover; resolvers, application caches, and connection reuse may continue holding old endpoints.

## 11. Kubernetes NetworkPolicy

Kubernetes NetworkPolicy lets you define pod ingress and egress using namespace/pod selectors, IP blocks, and ports, depending on the CNI plugin. Verify that your CNI actually enforces NetworkPolicies; merely creating the resource does not mean policies are active.

### 11.1. Default Deny Example

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: booking
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

This policy selects all pods in the `booking` namespace and denies ingress/egress not permitted by other policies, subject to the CNI's NetworkPolicy semantics.

### 11.2. Allowing Only Booking to Call Inventory

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: booking-to-inventory
  namespace: booking
spec:
  podSelector:
    matchLabels:
      app: booking-service
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: inventory
          podSelector:
            matchLabels:
              app: inventory-service
      ports:
        - protocol: TCP
          port: 8443
~~~

This example illustrates selectors and ports; namespace labels must actually be configured, and DNS egress may require an explicit rule to `kube-dns`/NodeLocal DNS depending on the environment. Connections to databases, telemetry, metadata services, and external endpoints also require intentional policies.

### 11.3. Limitations to Understand

- Standard NetworkPolicies focus on L3/L4; they do not inspect HTTP paths/methods.
- Policies are typically additive: multiple policies combine permitted flows; read CNI semantics and avoid overly broad rules.
- `hostNetwork`, node traffic, ingress controllers, and node-originated/node-bound traffic can behave specially.
- Egress to DNS, metadata endpoints, the control plane, and external services must be checked separately.
- Weak label selectors or labels that workloads can self-assign undermine boundaries.
- NetworkPolicy does not replace Kubernetes RBAC, Pod Security, secret management, or service identity.

## 12. Service Mesh

A service mesh deploys a proxy/data plane alongside workloads and a control plane managing configuration, identity, and policies. Depending on the product, a mesh can support mTLS, service discovery, traffic routing, retries, timeouts, circuit breakers, telemetry, and L7 authorization.

### 12.1. When Is a Mesh Useful?

- Many services need consistent mTLS and automated certificate rotation.
- Identity-based service-to-service policies are required.
- Unified observability/traffic management is needed.
- Canary rollouts, controlled retries, or fault injection across services are needed.

### 12.2. Trade-Offs

- Sidecar/ambient data planes add hops and latency.
- The control plane, proxies, and certificate authority become operational dependencies.
- Policies can fragment across mesh, gateway, application, and network firewalls.
- Debugging handshake/routing/authz issues requires specialized expertise.
- Resource consumption and telemetry costs increase.

A mesh does not protect traffic automatically if services can bypass proxies or workloads are not properly injected/attached. Enforce strict mTLS/authorization and verify direct bypass paths are closed.

## 13. Securing Connections to Databases and Data Planes

Databases, caches, and brokers usually store critical data or state; do not rely on a private subnet as the sole control.

### 13.1. Databases

- Accept traffic only from security groups/identities of services that require access.
- Enforce TLS and server certificate validation.
- Use dedicated DB accounts per service with minimal table/schema privileges.
- Never allow direct Internet client connections.
- Separate administrative connections from application traffic.
- Audit connections, privilege changes, and sensitive queries as supported by the database.
- Use appropriate private endpoints/routes; avoid public endpoints when unnecessary.

### 13.2. Caches

- Allow connections only from required workloads.
- Enforce authentication/ACLs by user/service and command scope where supported.
- Apply TLS, secret rotation, and memory/data retention policies.
- Never share an admin credential across all services.

### 13.3. Message Brokers

- Separate producer and consumer permissions per topic/queue.
- Never grant read access to all topics just because a service needs one queue.
- Protect broker protocols with TLS and dedicated workload identities/credentials.
- Control DLQs, replay, schema registries, and management consoles.
- Isolate networks and quotas so noisy-neighbor tenants/services do not impact the whole cluster.

## 14. Egress to Third Parties and Data Exfiltration

BookingCloud has Payment service and Notification worker making outbound calls. These paths can carry sensitive data across trust boundaries.

### 14.1. Explicit Egress Design

| Workload | Destination | Allowed Data | Controls |
|---|---|---|---|
| Payment service | Payment provider API | Required payment token/reference and amount | TLS, endpoint validation, scoped secrets, egress allowlist |
| Notification worker | Email provider | Recipient and filtered content | TLS, rate/quota limits, PII minimization, auditing |
| Backend service | KMS/private cloud APIs | Key operation metadata | Private endpoint, workload identity, policy |
| Monitoring agent | Telemetry collector | Redacted metrics/traces | TLS, destination allowlist, write-only identity |

Never send full customer records or entire request contexts to external providers when only a few fields are needed.

### 14.2. Preventing Data Exfiltration

- Control DNS and outbound destinations.
- Use proxies with logging, classification, or DLP where appropriate.
- Restrict large uploads, unnecessary protocols, and direct egress.
- Detect anomalous traffic volumes, domains, or regions.
- Constrain read/export permissions at application and storage layers.
- Separate roles and require approvals for bulk exports.
- Audit cloud storage public access and cross-account policies.

Network firewalls cannot fully inspect TLS-encrypted payloads without appropriate inspection. Never rely on deep packet inspection alone; combine identity, application auditing, DLP at authorized endpoints, and data minimization.

## 15. Deny-by-Default Policies and Rule Lifecycles

A firewall rule or NetworkPolicy should never be set once and forgotten.

### 15.1. Rule Governance Process

1. Record owner, source, destination, protocol, port, purpose, and data classification.
2. Define expiration or review conditions.
3. Author rules as infrastructure as code whenever possible.
4. Perform peer reviews and automated policy validation.
5. Deploy per environment or via staged rollout.
6. Test both allow paths and deny paths.
7. Observe flow logs and application telemetry.
8. Remove unused/deprecated rules; update the dependency map.

### 15.2. Preventing Temporary Broad Rules from Becoming Permanent

If an incident requires temporarily opening a port, the rule must have an owner, ticket, minimal scope, and expiration. Alert if temporary rules persist past their planned date. Never resolve a failing deployment by opening `0.0.0.0/0` or all ports in production.

### 15.3. Policy as Code

Static validation can detect:

- `0.0.0.0/0` or `::/0` open to management/database ports.
- Unrestricted egress from namespaces/data tiers.
- Security groups using wildcard ports.
- Duplicate or shadowed rules.
- Workloads lacking identities or policies.
- Routes/peering creating bypass paths.

Alerts must be evaluated in context; a public HTTPS listener may be intentional, whereas public SSH/RDP/database ports usually warrant strict scrutiny.

## 16. Observing and Investigating Network Flows

### 16.1. Telemetry Sources

- VPC/VNet flow logs or network flow telemetry.
- Firewall/WAF/load balancer logs.
- DNS query logs.
- Kubernetes CNI/NetworkPolicy events.
- Service mesh access logs, metrics, and distributed traces.
- Certificate issuance/rotation/handshake logs.
- Cloud audit logs for route, security group, firewall, and endpoint changes.

### 16.2. Key Metrics

| Metric | Meaning | What to Detect |
|---|---|---|
| Allowed/denied connection count | Traffic volume and policy denials | Unusual connections or misconfigured rules |
| East-west service traffic | Which service calls which service | New dependencies or lateral movement |
| Egress bytes/destinations | Outbound traffic volume | Data exfiltration or unfamiliar destinations |
| TLS/mTLS handshake failures | Trust/certificate health | Expired certificates or identity mismatches |
| DNS NXDOMAIN/new domains | Name resolution activity | Unfamiliar domains, typosquatting, or misconfiguration |
| Policy changes | Network access changes | Privilege expansion outside change windows |
| Connection latency/retransmits | Network path quality | Congestion, routing issues |

Flow logs may lack packet-level detail or have delivery lag depending on the service. Do not use them as a substitute for packet captures/traces when deeper investigation is required.

### 16.3. Correlation

Correlate network flows with workload identities, deployment versions, namespaces, request trace IDs, and change records where supported. Avoid placing user tokens or sensitive payloads into network logs.

## 17. Testing Segmentation and Service Communication

### 17.1. Positive and Negative Testing

| Test | Expectation |
|---|---|
| Booking → Inventory 8443 | Allow + mTLS/authz passes |
| Booking → Booking DB designated port | Allow |
| Booking → Payment admin endpoint | Deny |
| Notification worker → Database | Deny if no dependency exists |
| Internet → Database | Deny |
| Pod in another namespace → Booking pod | Deny unless explicitly permitted by policy |
| Workload without valid client cert → internal API | TLS/authentication rejects |
| Booking identity calls Inventory admin operation | Network may be reachable, but L7 authorization denies |
| Backend → unapproved Internet destination | Egress denied or rejected by proxy |
| DNS/route failover | Only healthy, policy-permitted endpoints receive traffic |

### 17.2. Connectivity Tests Are Not Enough

A successful `curl` only proves one path and one request worked at test time. Also test:

- Valid and invalid identities.
- Expired certificates or mismatched SANs.
- Wrong token audiences/scopes.
- Disallowed HTTP methods/paths.
- Egress to unapproved domains.
- Policy enforcement after rolling deployments.
- Pod restarts and IP address changes.
- Zone/region failovers.

### 17.3. Chaos / Fault Injection

Run exercises for certificate revocation, DNS resolver loss, misconfigured firewall updates, unresolvable private endpoints, service mesh proxy restarts, or zone connectivity loss. Verify the system fails closed at sensitive boundaries, recovers within SLOs, and avoids creating uncontrolled temporary bypasses.

## 18. Well-Architected Evaluation

| Perspective | Review Questions | Required Evidence |
|---|---|---|
| **Operational Excellence** | Who owns network rules, service identities, and egress policies? Are changes traceable/rollbackable? | Network inventory, IaC, change reviews, flow logs, and runbooks |
| **Security** | Are default deny, microsegmentation, mTLS, and L7 authorization enforced? | Threat model, policy tests, certificate lifecycle, deny events |
| **Reliability** | Can firewall/DNS/mesh/endpoint failures break critical paths or create bypasses? | Multi-zone design, health checks, failure drills, rollback |
| **Performance Efficiency** | How do proxies, inspection, mesh, and cross-zone traffic affect latency/throughput? | p95/p99 latency, handshake metrics, flow volume, load tests |
| **Cost Optimization** | Do firewall/endpoint/egress/mesh logging costs scale with traffic? | Egress bills, endpoint hourly/data costs, proxy resource usage |
| **Sustainability** | Is there hairpinned traffic, redundant routes, or unnecessary refreshes/telemetry? | Flow inventory, utilization, rule cleanup, and traffic optimization |

A sound design blocks unnecessary traffic while keeping essential business flows and failovers working. Network rules that are too broad weaken security; rules that are too narrow without a dependency map increase outages and operational toil.

## 19. Hands-On Exercise: Network Segmentation for BookingCloud

Current state:

- All services run in one VPC and one subnet.
- Every backend can call every other backend on any port.
- The database has a private IP but accepts traffic from the entire subnet.
- Backends have direct outbound Internet egress via NAT.
- Kubernetes lacks a default-deny NetworkPolicy.
- Services share one internal API key.
- Admins SSH into nodes over a broad VPN range.

Complete the following:

**Task 1 — Threat model:** identify at least six lateral movement or exfiltration paths if one pod is compromised.

**Task 2 — Network zones:** diagram edge, application, data, management, and egress zones. Specify required subnets, routes, and private endpoints.

**Task 3 — Allow matrix:** build a source/destination/protocol/port/purpose table for gateway, Booking, Inventory, Payment, worker, DB, cache, broker, and KMS.

**Task 4 — Identity:** replace the shared API key with workload identities/certificates; design mTLS and L7 authorization for each API.

**Task 5 — Kubernetes:** create default-deny ingress/egress and a policy allowing only Booking to call Inventory; handle DNS and telemetry.

**Task 6 — Egress:** design NAT/egress proxies, destination allowlists, and controls over data sent to payment/email providers.

**Task 7 — Admin:** replace broad-VPN SSH with identity-aware/bastion/short-lived access; restrict the management subnet.

**Task 8 — Testing/observability:** write positive/negative tests, flow logs/metrics, and drills for misconfigured blocking or zone loss.

### Self-Check Framework

| Current State | Risk | Improvement Direction |
|---|---|---|
| Flat single subnet | Easy lateral movement | Separate edge/app/data/management and microsegment |
| Backends call all backends | Large blast radius | Dependency-driven allow matrix |
| DB accepts entire subnet | Unrelated workloads can probe connections | Allow only required service identities/SGs |
| Direct egress | Hard to control exfiltration/C2 | Egress proxy/allowlist/private endpoints |
| No NetworkPolicy | Broad pod-to-pod communication | Default deny and label/workload policies |
| Shared API key | No service attribution, hard to revoke | Workload identity and mTLS |
| Broad VPN + SSH | High management exposure | JIT, MFA, bastion/identity-aware access, and auditing |

Your solution must specify allowed flows, blocked flows, authenticated identities, and how enforcement is verified.

## 20. Pre-Production Network Segmentation Checklist

- [ ] A network/data-flow map exists with owners and trust boundaries.
- [ ] North-south and east-west traffic are explicitly distinguished.
- [ ] Edge, application, data, and management zones have appropriate routes/policies.
- [ ] Ingress passes only through approved entry points.
- [ ] Egress is deny-by-default or governed by managed destination policies.
- [ ] Private endpoints/DNS/routes are verified alongside resource/IAM policies.
- [ ] Security groups/NACLs/firewalls have narrow rules, owners, purposes, and review dates.
- [ ] Microsegmentation is applied to sensitive workloads.
- [ ] Separate service identities exist; credentials/certificates have lifecycles and rotation.
- [ ] mTLS/TLS validation is enabled on hops requiring protection.
- [ ] L7 authorization restricts operations; network reachability is never treated as permission.
- [ ] Kubernetes CNI genuinely enforces NetworkPolicy; default-deny and DNS/telemetry rules are tested.
- [ ] Databases/caches/brokers are non-public and accept only required workloads.
- [ ] Admin access uses MFA, just-in-time grants, auditing, and narrow blast radius.
- [ ] Flow logs and DNS/firewall/mesh telemetry have retention and alerts.
- [ ] Positive/negative tests, fault injection, and policy rollback plans exist.

Network segmentation creates bounded communication zones; service identity identifies which workload is calling; TLS/mTLS secures channels and authenticates peers; L7 authorization restricts operations and resources. Combining these layers with egress controls, DNS/service discovery, policy as code, and observability curtails lateral movement, protects data, and keeps critical communication paths stable as the system evolves.
