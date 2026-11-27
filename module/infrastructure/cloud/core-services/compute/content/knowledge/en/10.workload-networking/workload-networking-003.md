# Routes, NAT, and Outbound Connectivity for Machines Without Public IPs

Virtual machines or containers without public IP addresses may still need to download OS patches, pull images, call external APIs, ship logs, or connect to managed services. To support this, cloud networks typically place workloads in private subnets and control outbound paths using route tables, NAT gateways, firewalls, proxies, or private endpoints.

A sound design lets workloads initiate outbound connections without exposing individual machine addresses publicly. However, simply adding a default route to a NAT is not enough: you must understand both the outbound and return paths, firewall scope, DNS, NAT allocation limits, zonal availability, and traffic observability.

This lesson explains how routing and NAT work, how to organize public and private subnets, how to choose egress options for IPv4 and IPv6, and how to troubleshoot when a machine without a public IP cannot reach required destinations.

After this lesson, you will be able to:

- Explain how route tables select the next hop for outbound traffic.
- Describe how NAT translates source addresses and ports for connections from private workloads.
- Design paths from private subnets to the Internet or cloud services without assigning public IPs to machines.
- Distinguish between NAT gateways, NAT instances, proxies, firewalls, and private endpoints.
- Evaluate security, availability, cost, and connection limits for each option.
- Diagnose routing, DNS, firewall, NAT, and return-path issues.

## 1. Why Do Workloads Without Public IPs Still Need Outbound Connectivity?

Attaching a public IP directly to a machine makes that machine routable from the Internet to that address, if security layers allow it. This increases the attack surface and complicates address management, allowlisting, and host-level firewall administration.

In many systems, application machines only need to **initiate outbound connections**. For example:

- Newly provisioned machines download patches and packages from vendor repositories.
- Container runtimes pull images from registries.
- Applications call payment APIs, mapping services, or partner APIs.
- Agents send logs, metrics, and traces to monitoring platforms.
- Workers pull jobs from queues or read data from external services.
- Deployment machines download artifacts from storage repositories.

These machines can use private IPv4 addresses inside the virtual network. When Internet access is required, traffic passes through an egress component with a public address or through a managed proxy/firewall. That component represents multiple workloads and hides their private addresses from external destinations.

Having no public IP does not mean a machine is completely isolated. Connectivity depends on route tables, gateways, security policies, DNS, and destination-side policies. Conversely, having a route to the Internet does not mean all traffic is allowed: firewalls or security policies can still block unapproved destinations and ports.

## 2. How Routing Determines the Traffic Path

Routers use route tables to choose the next hop for a packet. Each route typically includes:

- **Destination prefix:** target network, written in CIDR notation.
- **Next hop/target:** where to forward the packet, such as a gateway, NAT, firewall, peering connection, or network interface.
- **Route status:** whether the route is active.
- **Scope:** which subnets or networks the route table is associated with.

When multiple routes match, routers typically choose the route with the most specific prefix—that is, longest-prefix match. For example, a route to `10.30.0.0/16` takes precedence over the default route `0.0.0.0/0` for an address inside `10.30.0.0/16`. Detailed precedence rules across route types or equal-prefix routes can vary by cloud platform; check the provider's documentation.

### Local Routes and Default Routes

Inside a virtual network, there is usually a local route enabling subnets in the same network to exchange traffic according to design. An IPv4 default route has the form `0.0.0.0/0` and matches any IPv4 address lacking a more specific route. For IPv6, the corresponding default route is `::/0`.

Example route table for a private application subnet:

| Destination | Target | Meaning |
|---|---|---|
| 10.20.0.0/16 | local | Sends traffic to addresses inside the virtual network |
| 10.40.0.0/16 | peering or transit gateway | Sends traffic to a privately connected network |
| 0.0.0.0/0 | NAT gateway | Sends all remaining IPv4 destinations through NAT |

Routes to internal networks are more specific than the default route. Therefore, machines in the private subnet can reach internal services over private connections while traffic to Internet destinations goes through NAT. Actual routes must reflect the organization's topology and policies.

### Route Tables Are Associated with Subnets

A route table applies only to the subnets or network scopes associated with it. Two subnets inside the same VPC/VNet can use different route tables:

- Public subnets have a route to an Internet gateway.
- Private subnets have a default route to a NAT gateway.
- Data subnets might have no default Internet route at all, only routes to required internal services.

The labels "public subnet" and "private subnet" are generally based on routing paths, not solely on subnet names or whether machine addresses belong to private ranges. A subnet is considered public when it has a route to an Internet gateway and workloads have public addresses with appropriate permissive policies. If a subnet lacks such a direct path and egress flows through NAT or a proxy, it is generally considered a private subnet.

## 3. How Does NAT Work?

NAT (Network Address Translation) modifies IP address information in packets as they pass through an intermediary device or service. For private workloads accessing the IPv4 Internet, the common type is source NAT (SNAT), typically combined with source port translation (PAT/NAPT).

Suppose:

- An application machine has private IP `10.20.11.25`.
- The machine needs to call an API at `198.51.100.40` on TCP port `443`.
- The NAT gateway has public address `203.0.113.10`.

When the application opens a connection, NAT creates a mapping for that flow:

| Before NAT | After NAT |
|---|---|
| Source: 10.20.11.25:51520 | Source: 203.0.113.10:62001 |
| Destination: 198.51.100.40:443 | Destination: 198.51.100.40:443 |

The addresses and ports above are illustrative examples. NAT records the mapping state so that when responses from the API return to `203.0.113.10:62001`, it can forward the packets back to `10.20.11.25:51520`. The external destination sees the NAT's egress address instead of the application machine's private address.

### Outbound and Return Flows

~~~mermaid
sequenceDiagram
    participant VM as Private VM 10.20.11.25
    participant RT as Route table
    participant NAT as NAT gateway
    participant IGW as Internet gateway
    participant API as External API
    VM->>RT: Send TCP to API:443
    RT->>NAT: Default route points to NAT
    NAT->>NAT: Map source IP/port
    NAT->>IGW: Send packet with public egress IP
    IGW->>API: Forward to API
    API-->>IGW: Reply to NAT IP/port
    IGW-->>NAT: Forward return packet
    NAT->>NAT: Look up connection mapping
    NAT-->>VM: Deliver response to private IP
~~~

NAT typically allows connections initiated from inside and forwards return traffic belonging to those connections back to the originating machine. It does not automatically allow an arbitrary host on the Internet to initiate a new connection inbound to a private workload. If you need to expose a service to external inbound connections, use a load balancer, reverse proxy, API gateway, VPN, or a purpose-built inbound architecture.

NAT also does not replace a firewall. NAT handles address/port translation and maintains flow mappings; firewalls decide which traffic is permitted. You must combine routes, security groups, network ACLs, firewall policies, and application-level controls.

## 4. Private Subnet Architecture Pattern with a NAT Gateway

A common IPv4 architecture consists of a virtual network, a public subnet hosting a NAT gateway, and private subnets hosting workloads. The NAT gateway has a public address and a route to the Internet gateway; application machines have no public IPs assigned.

Example virtual network using `10.20.0.0/16`:

| Component | Illustrative range or address | Primary route |
|---|---|---|
| Public subnet | 10.20.1.0/24 | 10.20.0.0/16 local; 0.0.0.0/0 to Internet gateway |
| NAT gateway | 10.20.1.10 and a public egress address | Forwards traffic to Internet via Internet gateway |
| Private app subnet | 10.20.11.0/24 | 10.20.0.0/16 local; 0.0.0.0/0 to NAT gateway |
| Private data subnet | 10.20.21.0/24 | Only required internal or endpoint routes |

The ranges and addresses above are examples only. Choose CIDRs that do not overlap with on-premises networks, partner networks, or connected VPCs/VNets.

~~~mermaid
flowchart TB
    Internet["Internet / External API"]
    IGW["Internet gateway"]
    subgraph VPC["Virtual network 10.20.0.0/16"]
        subgraph Public["Public subnet 10.20.1.0/24"]
            NAT["NAT gateway\nPrivate IP + Public egress IP"]
        end
        subgraph PrivateApp["Private app subnet 10.20.11.0/24"]
            VM1["App VM A\n10.20.11.25"]
            VM2["App VM B\n10.20.11.26"]
        end
        subgraph PrivateData["Private data subnet 10.20.21.0/24"]
            DB["Database\n10.20.21.10"]
        end
        RT1["Public route table\n0.0.0.0/0 → IGW"]
        RT2["Private route table\n0.0.0.0/0 → NAT"]
    end
    VM1 --> RT2
    VM2 --> RT2
    RT2 --> NAT
    NAT --> RT1
    RT1 --> IGW
    IGW --> Internet
    VM1 --> DB
    VM2 --> DB
~~~

To configure this pattern:

1. Create the virtual network and subnets with non-overlapping CIDRs.
2. Create an Internet gateway or equivalent component and attach it to the virtual network.
3. Associate the public route table with the public subnet; add a default route to the Internet gateway.
4. Create a NAT gateway in the public subnet and attach a public egress address as required by the platform.
5. Ensure the public subnet has a route to the Internet gateway so the NAT can send traffic outbound.
6. Associate the private route table with the private app subnet; add an IPv4 default route to the NAT gateway.
7. Provision application machines with private IPs only and apply security policies restricting egress.
8. Verify DNS, firewalls, outbound routes, and return routes from an application machine to an approved destination.

If the NAT gateway has no route to the Internet gateway, or the public subnet has no valid outbound path, private workloads still cannot reach the Internet. You must inspect the entire next-hop chain rather than looking only at the application subnet's route table.

## 5. Choosing NAT Gateway, NAT Instance, Proxy, or Firewall

### Managed NAT Gateway

A cloud-managed NAT gateway typically reduces the effort of installing and maintaining an OS, patching software, monitoring NAT processes, and replacing failed machines. It fits standard IPv4 egress requirements for most workloads.

Limits to check per provider:

- Availability scope: whether the gateway is bound to a single zone, multiple zones, or is a regional service.
- Limits on concurrent connections, throughput rate, source ports, and bandwidth.
- Idle connection mapping timeout duration.
- Number of egress addresses that can be attached and scaling behavior.
- Charges per runtime hour, volume of data processed, and cross-zone traffic.
- Logging, metrics, and firewall integration capabilities.

A NAT gateway is straightforward for SNAT, though it does not necessarily provide domain-based filtering, content inspection, or granular application policies. If an organization needs egress control by domain, workload identity, or data type, a dedicated firewall or proxy may be required.

### Self-Managed NAT Instance

A NAT instance is a virtual machine configured to forward traffic and perform NAT. It allows customizing firewalls, proxies, logging, or networking software as needed.

In return, the operations team is responsible for:

- Enabling forwarding and configuring SNAT/PAT properly.
- Patching the OS, kernel, and networking software.
- Monitoring CPU, memory, network throughput, and connection tracking tables.
- Designing autoscaling or replacement mechanisms when the machine fails.
- Handling source/destination checks or equivalent settings if required by the platform.
- Preventing a single instance from becoming a single point of failure.

A NAT instance can suit specialized needs or labs, but labor costs and operational risks must be accounted for. Creating a VM with a public IP and enabling IP forwarding should not be treated as a highly available egress architecture.

### Egress Proxy

A proxy acts as an intermediary at the application or protocol layer. Workloads are configured to send requests through the proxy; the proxy can authenticate workloads, filter domains, log HTTP requests, enforce TLS policies, or apply rate limits.

A proxy adds controls that pure NAT lacks, but applications or runtimes must know how to use the proxy. Not all protocols are compatible with an HTTP proxy; some applications require SOCKS or specialized proxies. Certificates, authentication, availability, and avoiding proxy bottlenecks must all be managed.

### Egress Firewall

An egress firewall centralizes outbound traffic policies by address, port, protocol, domain, or identity depending on product capabilities. The firewall can sit in front of NAT or integrate with the platform's NAT/egress service. Processing order must be clearly defined so routing and stateful inspection work properly.

| Option | Strengths | Costs/risks to consider | When appropriate |
|---|---|---|---|
| Managed NAT gateway | Minimal OS maintenance, easy SNAT setup | Gateway and data charges, connection limits, zonal scope | Workloads needing standard IPv4 egress |
| NAT instance | Deep customization, can run custom networking software | Self-managed patching, scaling, monitoring, and HA design | Labs or specialized customization needs |
| Egress proxy | Application-layer policies, richer request logging | Requires client configuration, proxy and certificate management | Domain/API control and egress auditing |
| Egress firewall | Centralized security policies, traffic filtering | Cost, latency, HA design, and rule management | Environments requiring strict traffic controls |
| Private endpoint | Service traffic stays on the private network | Dependent on service, region, and endpoint costs | Accessing supported cloud services privately |

These options can be combined. For example, workloads send HTTP requests through a proxy for domain control while the proxy uses a NAT gateway to reach the Internet; requests to object storage or registries use private endpoints to avoid the public Internet path.

## 6. Private Endpoints and Private Connectivity to Cloud Services

Not all outbound connectivity needs require the Internet. If a workload only needs to access services provided within the same cloud ecosystem, evaluate using private endpoints, service endpoints, or equivalent private network connections.

Examples:

- Application machines download artifacts from object storage over a private endpoint.
- Container runtimes pull images from an internal registry.
- Workers access a message queue or database via a private address.
- Monitoring services ingest logs over a private link or internal endpoint.

Common benefits:

- Traffic does not traverse the public Internet.
- May avoid NAT fees or Internet data transfer charges on certain paths.
- Access policies can be scoped by network, endpoint, or service identity.
- Reduces reliance on public IPs and external allowlists.

A private endpoint does not automatically grant access to every service. You must verify service and region support, confirm private DNS resolves to the endpoint, check routes and security policies, and verify IAM or service permissions. A private endpoint still requires authentication and authorization at the application layer.

When a workload has both private and public egress needs, create specific routes to private endpoints or private networks; only remaining destinations should follow the default route to NAT or a proxy. Verify longest-prefix match and DNS to ensure service names resolve to the private endpoint address.

## 7. IPv6 and Egress-Only Gateways

IPv6 takes a different approach from IPv4. A workload can use a globally routable IPv6 global unicast address without IPv4-style address translation. Consequently, IPv6 egress protection typically relies on route tables, security groups, firewalls, and an egress-only gateway if provided by the platform.

An **egress-only Internet gateway** lets IPv6 workloads initiate outbound Internet connections and receive return traffic for those connections, while blocking new inbound connections initiated from the Internet through that gateway. It serves a role similar to the egress-only goal of IPv4 NAT, without translating IPv6 addresses the way standard IPv4 SNAT does.

A private IPv6 subnet's route table may contain:

| Destination | Target | Meaning |
|---|---|---|
| Virtual network IPv6 range | local | Internal traffic |
| ::/0 | Egress-only gateway | Stateful outbound IPv6 egress to Internet |

If the platform does not offer an egress-only gateway, use a firewall or equivalent IPv6 egress architecture and strictly control security policies. Global IPv6 addresses should not be considered safe simply because the machine has no public IPv4 address.

For IPv6-only environments that must call IPv4-only services, NAT64/DNS64 or an equivalent translation gateway may be needed if supported by the platform. This is a distinct translation path and should not be confused with a standard IPv4 SNAT gateway. Confirm DNS, protocol support, and destination policies.

## 8. Securing Outbound Connections

Outbound connectivity is also part of the attack surface. If a machine is compromised, an attacker may attempt to download tools, exfiltrate data, or control the machine via a remote server. Therefore, egress should be governed by the principle of least privilege.

### Restricting Destinations and Ports

- Allow workloads to call only required services, such as HTTPS to approved APIs or registries.
- Prefer private endpoints for supported cloud services.
- Use a proxy or firewall when domain filtering, request logging, or advanced policy checks are needed.
- Avoid opening egress for all protocols to all addresses when workloads only need specific destinations.
- Verify both IPv4 and IPv6; locking down IPv4 while leaving IPv6 open can create unexpected egress paths.

Security groups are usually stateful filters: when an outbound connection is allowed, return traffic for that flow is typically permitted automatically. Network ACLs are often stateless subnet-level filters; both outbound and inbound directions must be permitted, including the ephemeral port ranges used by the operating system.

Stateful firewalls also track connection state. If the return path passes through a different firewall or misses the recorded state, the connection can be dropped. Asymmetric routing designs require careful review when using multiple firewalls or NATs.

### Do Not Confuse NAT with Access Control

NAT hides private addresses and lets multiple machines share an egress IP, but it is not an application authentication mechanism. A workload can call numerous Internet addresses through NAT if firewalls permit it. You still need:

- TLS to protect data in transit.
- API authentication and secret management.
- IAM or workload identity for cloud services.
- Egress policies, logs, and alerts.
- DNS controls to prevent workloads from arbitrarily using unapproved resolvers.

If a partner requires source IP allowlisting, provide the stable public egress addresses of the NAT or firewall. Do not give the application machine's private IP because the partner cannot see it across the Internet. When using multiple NAT gateways or regions, provide all egress IPs that may be used.

## 9. NAT Availability and Scaling

NAT sits in the path of every egress connection routed through it. If NAT fails, saturates, or loses connectivity to the Internet gateway, multiple workloads can simultaneously lose the ability to fetch packages, call APIs, or send telemetry. NAT is therefore an infrastructure component requiring HA design.

### Zonal Design

If the NAT service is zonally scoped, a common pattern is deploying a NAT gateway in every zone with workloads and routing private subnets in that zone to the same-zone NAT. This reduces cross-zone dependencies and can avoid cross-zone data transfer charges. If one zone's NAT fails, workloads in other zones retain their own egress paths.

Routing all zones centrally through a NAT in one zone can save gateway costs, but introduces a single point of failure and increases cross-zone traffic. If choosing a centralized design, implement route failover mechanisms, test zone failover, and account for data transfer charges.

Not every provider implements NAT with the same model. Some NAT services are regional or handle underlying availability automatically. Verify actual failure domains, SLAs, scaling behavior, and failover mechanisms before duplicating gateways.

### Connection and Source Port Limits

NAT/PAT uses a set of addresses and source ports to distinguish connection flows. As concurrent connections grow, a NAT can hit limits on bandwidth, active connections, connection setup rate, or available source ports.

Possible symptoms include:

- Some new connections fail or time out while existing connections continue working.
- Errors spike when multiple workers concurrently call the same API.
- Error rates vary by destination or during peak traffic periods.
- NAT metrics show connection counts, port usage, or throughput approaching limits.

Mitigation measures:

- Reuse HTTP/TCP connections rather than opening a new connection per request.
- Use connection pooling and appropriate keep-alive settings.
- Reduce synchronized retries; use exponential backoff and jitter to avoid connection storms.
- Spread workloads across multiple NATs or multiple egress addresses if supported by the service and architecture.
- Use private endpoints for traffic to eligible cloud services.
- Monitor active connections, port allocation errors, bytes/packets, and throughput.

Do not add more NATs based purely on guesswork. Measure actual limits and determine whether the bottleneck is source ports, bandwidth, NAT instance CPU, firewall throughput, or the destination API.

## 10. Cost and Egress Path Selection

Egress costs can include hourly NAT gateway fees, per-GB processing fees, cross-zone data transfer fees, Internet data transfer fees, firewall/proxy fees, and operational overhead. Pricing models vary by provider and region.

One evaluation approach is classifying traffic:

| Traffic type | Path to consider | Reason |
|---|---|---|
| Public partner API | NAT or egress proxy | Requires stable source IP and connection control |
| Same-cloud object storage | Private endpoint/service endpoint if available | Reduces Internet dependency and can reduce NAT fees |
| Internal container registry | Private endpoint or private network | Avoids pulling images over the Internet |
| Service in another virtual network | Peering, transit gateway, or private link | Controlled internal routing |
| Data center systems | VPN or dedicated connection | Private connectivity and bidirectional routing policy |
| General Internet | NAT gateway combined with firewall/proxy per policy | Centrally manageable egress point |

For example, a group of workers downloads 2 TB of data per month from same-region object storage. If every byte goes through NAT, the team may pay NAT processing fees and possibly cross-zone charges. If the service supports a private endpoint and routes/DNS are configured properly, traffic can stay on the private network and reduce NAT egress costs. Check actual pricing schedules, as private endpoints may also carry hourly or data charges.

Factor in indirect costs as well: a single NAT lowers gateway fees but raises downtime risk; multiple NATs increase fixed cost but improve fault isolation. Decisions should reflect workload criticality, actual traffic volume, and recovery requirements.

## 11. Workflow for Designing Private Workload Egress

Use the following workflow when building a new network or moving an existing workload into a private subnet:

1. **List required destinations.** Document domains/IPs, ports, protocols, regions, and business purpose. Separate cloud services, internal networks, and the public Internet.
2. **Classify flows.** Identify which flows need the Internet and which can use private endpoints, peering, VPN, or dedicated connections.
3. **Select CIDRs and topology.** Avoid overlapping address ranges; define subnets by workload, zone, and trust level.
4. **Design route tables.** Add specific internal routes, private network routes, and a default route to the appropriate NAT/firewall/proxy.
5. **Design security.** Restrict security groups, network ACLs, firewalls, DNS, and application permissions per least privilege.
6. **Design HA and capacity.** Determine zone/region scope, NAT count, egress addresses, connection limits, and failover strategy.
7. **Verify outbound and return paths.** Confirm NAT has a route to the Internet gateway; verify return routes, ephemeral ports, and stateful inspection.
8. **Observe and optimize.** Enable flow logs, NAT/firewall metrics, and DNS logs where appropriate; track traffic, errors, and costs.

Architecture verification checklist:

- [ ] The workload does not need a public IP and has only an appropriate private address.
- [ ] The private subnet's route table points to the right NAT/firewall or endpoint.
- [ ] The NAT has a valid path to an Internet gateway or upstream egress.
- [ ] Specific routes to internal networks and private endpoints take proper precedence.
- [ ] Security groups, network ACLs, and firewalls allow both outbound and return traffic.
- [ ] DNS resolves service names to the right public or private endpoint addresses.
- [ ] Sufficient stable egress addresses exist for partner allowlists.
- [ ] Zonal HA and capacity match expected connection counts.
- [ ] Logs, metrics, alerts, and budgets are configured for egress traffic.
- [ ] IPv6 is controlled at parity with IPv4 if enabled.

## 12. Troubleshooting When a Private Machine Cannot Connect

Do not start by assigning a public IP to the machine for a quick test. Doing so alters the security posture and masks the real root cause. Inspect layer by layer from source machine to destination.

### Step 1: Check DNS

Verify that the domain name resolves and returns the address matching the intended path. If using a private endpoint, DNS may require a private hosted zone or resolver rule. If the domain returns a public IP when a private endpoint was intended, traffic may route mistakenly through NAT.

Common diagnostic commands:

~~~bash
dig api.example.com
getent hosts api.example.com
~~~

The domain and commands are examples only; your OS or container environment may provide different DNS tools.

### Step 2: Check Host Routes and Subnet Route Tables

Confirm the machine has a default route, an appropriate gateway, and the right route table associated with its subnet. Check whether traffic to the destination address is being steered by a more specific prefix toward peering, VPN, or a different firewall.

~~~bash
ip route
ip route get 198.51.100.40
~~~

The second command shows which interface and next hop the kernel plans to use for the example destination. The OS routing table is only part of the picture; you must still check the cloud virtual network's route tables.

### Step 3: Check Security Policies

Inspect egress rules in security groups, network ACLs, firewall policies, and the host firewall. With stateless ACLs, confirm return traffic allows ephemeral ports. If a proxy is used, verify proxy environment variables or settings and authentication credentials.

### Step 4: Check NAT and Upstream

Confirm the NAT gateway is active, has an egress address, has a route to the Internet gateway, and has not hit connection limits. If using a NAT instance, check IP forwarding, SNAT rules, connection tracking, CPU, and network interfaces. Also check upstream firewalls or gateways.

### Step 5: Check TCP/TLS Connectivity and the Destination

~~~bash
nc -vz api.example.com 443
curl -v --connect-timeout 5 https://api.example.com/health
~~~

If TCP fails to establish, the issue may lie in routing, firewalls, NAT, or the destination side. If TCP succeeds but TLS or HTTP fails, inspect certificates, SNI, proxies, authentication, allowlists, and service health. A failed ping alone does not prove the network path is broken, because ICMP may be blocked while TCP works.

### Step 6: Use Logs and Metrics to Pinpoint Packet Loss

Network interface/subnet flow logs, NAT metrics, firewall logs, DNS query logs, and application logs help locate where traffic is being rejected. Search by timestamp, private source IP, destination IP, port, and protocol. If the destination only sees the NAT IP, correlate timestamps and translated source ports.

| Symptom | Layer to check first |
|---|---|
| Domain name fails to resolve | DNS resolver, private zone, outbound DNS |
| Has IP but no matching route | Subnet route table, default route, next hop |
| TCP timeout to all Internet destinations | NAT, Internet gateway, firewall, return route |
| Only one API is unreachable | Source IP allowlist, destination firewall, DNS, and API policy |
| Connections fail under high load | NAT limits, source ports, connection pools, bandwidth |
| Accessing private endpoint but routed through NAT | Private DNS, specific routes, endpoint policy |
| IPv4 works while IPv6 fails or vice versa | `::/0` route, egress-only gateway, firewall, and AAAA DNS |
| Connection opens but app reports TLS errors | Certificates, system clock, SNI, proxy, and TLS policy |

## 13. Practical Example: Private Workers Pulling Images and Calling APIs

An order-processing system runs 12 workers across two zones. The workers have no public IPs. They need to:

- Pull container images from the organization's registry.
- Read messages from a queue and write results to an internal database.
- Call a partner API over HTTPS.
- Send logs and metrics to an observability service.

The team can design the paths as follows:

1. The queue, database, and registry with private endpoint support are accessed via private endpoints or the internal network.
2. Route tables contain specific routes to the private networks and endpoints.
3. Only traffic calling the partner API or required public services traverses NAT/egress proxy.
4. Each zone has its own NAT if the NAT service is zonally scoped, and worker routes prefer the same-zone NAT.
5. Firewalls permit HTTPS to approved partner domains/IPs; security groups permit only required egress.
6. Private DNS resolves the registry and internal services to their private endpoints.
7. Logs and metrics track connection counts, NAT errors, API latency, and egress costs.

If the partner requires source IP allowlisting, the team supplies the stable public egress addresses of the NAT or firewall in both zones. When one zone fails and workers shift to the other zone, the egress IP can change; therefore, the allowlist and failover runbook must include all usable egress IPs.

This design keeps workers on private networks, avoids routing internal cloud traffic over the Internet, and centralizes control over truly necessary public connections.

## 14. Common Design Mistakes

1. **Adding only a default route to NAT:** NAT lacks a route to the Internet gateway or upstream, so connections still fail.
2. **Placing NAT in a private subnet:** NAT has no valid egress path to the Internet gateway, causing routing loops or blackholed traffic.
3. **Treating NAT as a firewall:** NAT does not replace filtering by destination, port, identity, or content.
4. **Forgetting the return path:** stateless ACLs or firewalls block ephemeral ports/responses, preventing TCP connections from completing.
5. **Using one NAT for all zones without assessing risk:** creates a single point of failure and may incur cross-zone data transfer fees.
6. **Overlooking DNS:** private endpoints exist, yet service names still resolve to public addresses.
7. **Ignoring source port limits:** too many short-lived connections can exhaust NAT mapping resources.
8. **Incomplete egress IP allowlist:** partner only allowlists one NAT while workloads can exit through multiple NATs or zones.
9. **Controlling only IPv4:** IPv6 can create an unintended egress path outside policy.
10. **Routing every service through NAT:** internal traffic or cloud services with private endpoints traverse NAT unnecessarily, increasing cost and latency.

## 15. Practice Exercise

An application runs in a private subnet with CIDR `10.50.10.0/24`. The virtual network uses `10.50.0.0/16`. Application machines have no public IPs and must call a partner API over HTTPS. The team created a NAT gateway in public subnet `10.50.1.0/24` and attached a public egress address to the NAT.

1. Which routes does the private subnet's route table need for internal traffic and Internet traffic?
2. What path do the public subnet and NAT gateway need for packets to reach the Internet?
3. Why does the partner API see the NAT's egress IP instead of the application machine's private IP?
4. If TCP times out even though DNS resolves correctly, name at least four layers to inspect.
5. If there are two zones and workloads must continue running when one zone fails, how should the NAT design and allowlist change?
6. If the application downloads large amounts of data from same-cloud object storage, how can a private endpoint help?

Hint: the private subnet needs a local route for `10.50.0.0/16` and a default route `0.0.0.0/0` to the NAT. The public subnet needs a default route to the Internet gateway; the NAT must run in that subnet with a public egress address. When scaling multi-zone, consider per-zone NATs, corresponding routes, and all usable egress addresses. For object storage, evaluate private endpoints, DNS, and endpoint policies before routing through NAT.

## Conclusion

Workloads without public IPs can still connect outbound by routing through NAT, proxies, firewalls, or private endpoints. A reliable design requires configuring accurate route tables and next hops, understanding NAT mappings and return paths, scoping egress to actual needs, managing DNS and IPv6, and ensuring HA and capacity. When failures occur, inspect layer by layer—from DNS, routes, security policies, and NAT to the destination—using logs and metrics to locate the exact point of failure.
