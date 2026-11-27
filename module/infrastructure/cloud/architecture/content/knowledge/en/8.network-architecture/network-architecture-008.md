# Connecting Data Centers via VPN and Dedicated Circuits

## Learning Objectives

When designing **Cloud Architecture**, not every application can migrate completely to the public cloud in one step. Some systems still run databases, specialized hardware, accounting software, or data warehouses inside an *on-premises data center*. Cloud applications must exchange data securely and reliably with those systems. This architecture is commonly called **hybrid connectivity**.

This lesson belongs to the **Network Architecture** section and focuses on two common connectivity approaches: **IPsec-based site-to-site VPN** and **dedicated private circuits** to cloud providers. Choosing between them must weigh networking, compute, data, deployment models, reliability, security, scalability, cost, and operations under **Well-Architected** principles.

After this lesson, you will be able to:

- Explain the traffic path between an on-premises data center and a private cloud network.
- Distinguish Internet-based site-to-site VPN from dedicated private connectivity through carriers and cloud interconnect gateways.
- Design IP addressing, routing, DNS, firewalls, and encryption mechanisms for hybrid connectivity.
- Analyze trade-offs across throughput, latency, redundancy, security, cost, and complexity.
- Decide when to use VPN, dedicated circuits, or **dedicated circuits paired with VPN backup**.
- Write measurable quality scenarios and design failover, performance, and recovery tests.
- Document architectural decisions via ADRs and evaluate them under Well-Architected pillars.

## 1. Context: Why Connect a Data Center to the Cloud?

Suppose a company operates three system groups:

1. **In the data center:** ERP database, inventory management system, internal identity services, and applications not yet ready to migrate.
2. **In the cloud:** Java/Spring Boot APIs, order-processing services, data sync workers, and analytics systems.
3. **Users and partners:** Access via the Internet or corporate networks through controlled channels.

An ordering API in the cloud may need to check inventory levels in the data center. If the interconnect drops, the API can slow down or fail to confirm orders. A hybrid link therefore becomes a **critical business-flow dependency**, not merely a cable-provisioning task.

When gathering requirements, clarify:

| Business question | Architectural impact |
| --- | --- |
| Which applications must exchange data? | Allowed sources/destinations traversing the interconnect. |
| Is the data sensitive or subject to data residency regulations? | Encryption, access controls, data placement regions, and auditing. |
| What are expected change rates and traffic volumes? | Bandwidth, sync mechanisms, packet sizing, and data transfer costs. |
| When must the link remain operational? | SLOs, maintenance windows, backup channels, and on-call coverage. |
| What happens when the link slows down or drops? | Timeouts, caching, queuing, degradation modes, and RTO. |
| During an outage, can writes pause or sync later? | Data consistency model and recovery strategy. |

**Key point:** A healthy network path does not guarantee a healthy application. Measure the entire transaction journey—including DNS, authentication, cloud services, firewalls, the interconnect back to the data center, and the backend data system.

## 2. Basic Hybrid Architecture Picture

~~~mermaid
flowchart LR
    U["Users"] --> EDGE["HTTPS / Load balancer"]
    subgraph CLOUD["Cloud: private network 10.40.0.0/16"]
        EDGE --> APP["Spring Boot Application"]
        APP --> GW["Cloud VPN or private gateway"]
        APP --> DATA[("Cloud database")]
    end
    GW <-->|"Controlled hybrid channel"| ONGW
    subgraph DC["Data center: 10.20.0.0/16"]
        ONGW["Edge router / firewall"]
        ONGW --> ERP["ERP / Inventory API"]
        ONGW --> LEGACY[("Internal database")]
    end
~~~

This is a logical diagram and does not imply every database in the data center should be directly reachable. In sound designs, place a **controlled API or integration layer** in front of critical data rather than opening direct database connections from many cloud workloads.

Core components include:

- **Private cloud network:** VPC, VNet, or equivalent, with subnets and route tables.
- **Data center network edge:** Routers/firewalls supporting IPsec, BGP, segmentation, and HA.
- **Cloud termination point:** VPN gateway, virtual gateway, transit/hub gateway, or provider-specific private interconnect gateway.
- **Data plane path:** Encrypted Internet for VPN; carrier/private interconnect ports for private connections.
- **Control plane & security:** Routing, DNS, firewalls/ACLs, identity, certificates/secrets, and monitoring.
- **Application resilience:** Timeouts, retries, circuit breakers, caching, and handling unavailable downstream dependencies.

Separate the **data plane** (actual packets traversing the link) from the **control plane** (configuration, routing updates, resource management). A control-plane incident does not necessarily halt existing traffic immediately, yet can block route changes or resource provisioning during recovery.

## 3. Site-to-Site VPN: Encrypted Connectivity Over Public Networks

### 3.1. How It Works

A **site-to-site VPN** builds an encrypted tunnel between a data center network appliance and a cloud gateway. Common implementations use **IPsec** to authenticate endpoints and protect IP packets crossing untrusted networks like the public Internet.

~~~mermaid
flowchart LR
    subgraph DC["Data center"]
        DCNET["Network 10.20.0.0/16"] --> ROUTER["Router / Firewall"]
    end
    ROUTER --> TUNNEL["IPsec Tunnel over Internet"]
    TUNNEL --> VPNGW["Cloud VPN Gateway"]
    subgraph CLOUD["Cloud"]
        VPNGW --> PRIVATE["Private subnet 10.40.0.0/16"]
    end
~~~

Conceptually, a connection goes through:

1. Both endpoints verify reachability and compatible security parameters.
2. **IKE** establishes/negotiates security associations; IKEv2 can be used where both sides support it and policy permits.
3. **IPsec ESP** protects traffic matching the chosen policy/routes. Algorithms, keys, lifetimes, and PFS settings must match and satisfy security policy.
4. Routing directs traffic between authorized networks through the tunnel.
5. Gateways and edge devices continuously monitor tunnel health; routing must react appropriately when a tunnel drops.

Note that IPsec protects a network-layer transport segment. Applications handling sensitive data should still enforce **TLS, service authentication, and application-layer authorization**; never treat a VPN as end-user authentication.

### 3.2. When Is VPN Appropriate?

VPNs generally fit well for:

- Initial connectivity during hybrid rollout or phased migrations.
- Moderate traffic volumes that can tolerate Internet latency variance.
- Branch offices or data centers needing quick setup before dedicated circuits are provisioned.
- **Backup channel** when a primary private circuit is disrupted.
- Test environments, tightly scoped admin access, or non-real-time synchronization.

Advantages of VPN include relatively fast setup when Internet access already exists, usually no advance circuit lead time, and network-layer traffic encryption.

Limitations:

- Throughput can be capped by encryption/decryption appliances, gateway service limits, tunnel counts, and routing design.
- Latency, jitter, and packet loss depend on Internet paths, ISPs, and time of day.
- Depends on Internet uplinks and edge hardware; running two tunnels over the same modem/ISP does not achieve physical independence.
- IPsec encapsulation adds header overhead, shrinking effective MTU and risking fragmentation if mishandled.
- A tunnel showing “UP” does not mean internal APIs work, routes are right, or data is syncing.

**Never equate site-to-site VPN with remote-access VPN.** Remote-access VPN serves individual devices/users; site-to-site links entire networks/sites. IAM policies and user authorization still must be designed independently.

### 3.3. Tunnels, Routes, and Addressing

Example address plan:

| Zone | Illustrative CIDR | Role |
| --- | --- | --- |
| Data center | 10.20.0.0/16 | ERP, internal apps, DNS |
| Cloud production | 10.40.0.0/16 | Apps, workers, databases |
| Cloud staging | 10.50.0.0/16 | Testing; no default access to production |
| Management network | 10.60.0.0/24 | Administration via bastion/dedicated controls |

These CIDRs are private-address examples only. **Connected routing domains must avoid overlapping CIDRs**; if both sides use 10.20.0.0/16, routes become ambiguous and may force NAT or re-addressing. Cross-network NAT complicates logging, policies, DNS, and bidirectional connectivity; always prioritize non-overlapping planning upfront.

At both ends, routes must specify:

- Cloud to 10.20.0.0/16: via the hybrid gateway.
- Data center to 10.40.0.0/16: via the appropriate tunnel/circuit.
- Firewalls permit only genuinely required subnets and ports.
- Staging `10.50.0.0/16` receives no automatic access to production databases.

Configuring a route in only one direction delivers outbound packets while replies never return to the right place. This is a common error across multi-route-table environments, stateful firewalls, or backup links.

## 4. Dedicated Circuits: Connectivity Over Private Carrier Infrastructure

### 4.1. What Does Dedicated Private Connectivity Mean?

Here, “dedicated circuit” refers to a link between a data center and a cloud provider's private interconnect point or via an interconnect partner. Depending on the provider, services are called **AWS Direct Connect**, **Azure ExpressRoute**, **Google Cloud Interconnect**, or equivalents.

Distinctions to keep clear:

- **Cloud private connectivity channel:** Traffic from the data center enters the cloud via a dedicated interconnect or partner facility without necessarily traversing the public Internet like a classic site-to-site VPN.
- **Carrier leased line/Metro Ethernet/MPLS:** Transport service carrying traffic from the corporate site to the interconnect point. You may still need circuits, cross-connects, and dedicated cloud service ports.
- **Physically diverse paths:** Two logical circuits sharing the same fiber bundle or demarcation point can still fail together from one physical cut.

~~~mermaid
flowchart LR
    subgraph DC["Data center"]
        LAN["Internal network"] --> ER["Edge router"]
    end
    ER --> TELCO["Carrier / Interconnect partner"]
    TELCO --> CROSS["Interconnect facility / Cross-connect"]
    CROSS --> CLOUDGW["Private connectivity gateway"]
    subgraph CLOUD["Cloud Private Network"]
        CLOUDGW --> APP["Applications / Data"]
    end
~~~

Services differ in interface types, routing models, BGP requirements, port speeds, provisioning lead times, and regional reach. In real projects, check specs and support terms **for your exact provider**, rather than assuming every private interconnect shares identical traits.

### 4.2. Benefits

**Predictability:** A private interconnect can deliver reserved bandwidth and steadier quality than the public Internet, depending on paths and carrier SLAs. This matters for high-volume or latency-sensitive data flows.

**Path control:** Network paths and interconnect partners are explicitly defined, letting enterprises enforce tailored policies and monitoring.

**High-load bandwidth:** Several options support high port capacities suitable for scheduled data transfers, analytics, backups, or data center–cloud synchronization.

**Long-term hybrid foundation:** When many services interconnect and a dedicated network team operates the estate, private connectivity provides durable long-term infrastructure.

### 4.3. Limitations and Misconceptions

- **Private does not mean encrypted.** Many private interconnect types do not encrypt payloads end-to-end automatically. Enforce TLS, IPsec overlays, or encryption suited to security needs and service support.
- **Not automatically faster than every VPN.** Real performance depends on distance, routing, ports, applications, packet sizes, and traffic handling.
- **Not automatically HA.** A single circuit, port, router, or carrier remains a single point of failure.
- **Does not bypass security controls.** Private paths still require IAM, firewalls, service identity, least privilege, and auditing.
- **Cost and provisioning lead times can be high:** Includes cloud port/connection fees, carrier circuits, cross-connects, edge hardware, installation, maintenance, and staffing.
- **May not include general Internet access.** Private circuits target configured networks/services and gateway types; never treat them as generic Internet transit.

A private circuit does not shield apps from logic bugs, database crashes, or regional outages; backups, failover, and DR must still be designed separately.

## 5. Comparing VPN and Dedicated Circuits Against Real Requirements

| Criterion | Internet site-to-site VPN | Dedicated private circuit |
| --- | --- | --- |
| Transport underlay | Existing Internet connections at both ends | Carrier network/circuit and private interconnect point to cloud |
| Encryption | Typically IPsec for the tunnel | Must verify separately; private does not mean encrypted |
| Provisioning time | Fast if network gear is already ready | May require circuit ordering, site surveys, cross-connects |
| Throughput | Bound by gateways, appliances, and Internet; may need multiple tunnels | Provisioned bandwidth matched to service/circuit |
| Latency, jitter | Can fluctuate with Internet conditions | Usually steadier on managed paths; still must measure |
| Redundancy | Needs multiple tunnels, endpoints, and independent ISPs | Needs diverse ports, interconnect sites, routers/carriers, or sites |
| Agility | Fits rapid rollouts/tests and quick config tweaks | Speed/circuit changes can involve carrier lead times |
| Cost | Gateways, Internet, appliances, egress, ops | Ports, circuits, cross-connects, gear, egress, redundancy, ops |
| Key risks | Internet variability, crypto/appliance caps | Fiber/circuit/port/carrier cuts, lead times, link lock-in |
| Typical use cases | Fast setup, moderate load, backup path | Long-term hybrid workloads, heavy loads, private-path mandates |

This table is an **evaluation framework**, not a performance guarantee for any specific product. Compare options that meet the **same** risk profile and SLOs; if a VPN option uses one Internet uplink while a private option uses two diverse circuits, cost and reliability are not apples-to-apples.

## 6. Hybrid Pattern: Private Primary, VPN Backup

For critical workloads, a strong option to evaluate uses a dedicated circuit for regular traffic and a VPN as a backup channel. This only works if **routing, backup capacity, and failover procedures** are verified end-to-end.

~~~mermaid
flowchart LR
    DC["DC Core Network"] --> R["HA Router / Firewall"]
    R --> P["Dedicated circuit - primary"]
    R --> V["IPsec VPN - backup"]
    P --> HUB["Cloud hybrid gateway / hub"]
    V --> HUB
    HUB --> APP["Private App Subnets"]
    HUB --> DB["Data services"]
~~~

When designing, verify:

1. **Route precedence:** Which path wins when both are healthy? How are static routes, metrics, BGP local preference, or equivalent attributes supported?
2. **Failure detection:** BFD/BGP sessions, tunnel health, application probes, or other checks; losing a route and losing the application are two distinct failures.
3. **Convergence time:** After the primary circuit drops, how long until traffic actually shifts to VPN and apps process requests successfully?
4. **Backup capacity:** Does the VPN hold enough bandwidth for **essential minimum load**, or must non-critical traffic be shed?
5. **Return path:** Do routes from cloud back to the data center fail over symmetrically? Do stateful firewalls or NAT drop existing sessions?
6. **Failback behavior:** When the private link recovers, does failback cause route *flapping* or tear down active sessions?

Never assume traffic switches automatically just because two links are configured. Exact route-preference behavior varies by gateway and provider. Some preference and ECMP mechanisms have limits; check vendor technical docs and drill on live testbeds.

### 6.1. Logical Redundancy vs. Physical Redundancy

Two IPsec tunnels on the same router and same ISP survive a single-tunnel drop yet still fail together if the ISP goes down. Two private circuits riding the same physical fiber conduit can still fail together during a backhoe fiber cut.

Analysis should inspect **fault domains**:

| Component | Shared failure-point questions |
| --- | --- |
| Data center edge | Are there two independent routers/firewalls, power feeds, and uplinks? |
| Carrier | Do links share the same ISP, PoP, or fiber path? |
| Cloud interconnect | Do both circuits land on the same device or same facility? |
| Cloud gateway/hub | Is the gateway deployed in a service-appropriate HA architecture? |
| DNS/identity | Does failover preserve internal DNS, identity providers, and certificates? |
| Application/data | Can cloud and on-prem actually process transactions after path switch? |
| Operations team | Do admin accounts, secrets, and runbooks exist at only a single site? |

To eliminate single points of failure, diversify components that can physically fail together; multiple logical paths are only step one.

## 7. IP Addressing and Hybrid Routing Planning

### 7.1. CIDRs, Overlaps, and Network Segmentation

Create an **IP address plan** before deploying. Budget ranges for cloud production, staging, DR regions, on-prem networks, VPN/tunnels, and future expansion. Maintainable designs keep private CIDRs non-overlapping across connected domains.

Example:

~~~text
On-prem datacenter:    10.20.0.0/16
On-prem management:    10.21.0.0/20
Cloud production:      10.40.0.0/16
Cloud staging:         10.50.0.0/16
Cloud DR:              10.60.0.0/16
~~~

A dedicated circuit or VPN **does not automatically make subnets reachable to one another**. Each path needs routes at both ends, accurate firewalls, and valid return routes.

Across multiple VPCs/VNets, a transit gateway or hub-and-spoke topology centralizes routing and security. However, a central hub can also become a bottleneck or failure point without HA and capacity planning.

### 7.2. Static Routing and BGP

- **Static routes:** Fairly straightforward for small, rarely changing networks. Must manage manual updates or automated failover when links drop; never assume static routes detect application-level failures.
- **BGP (Border Gateway Protocol):** Both networks advertise/withdraw prefixes and converge when links change. Generally suits multi-path setups or larger environments.
- **BGP ASN:** Use compliant Autonomous System Numbers per organizational and provider rules; private ASNs can be used when connectivity requirements allow.
- **Route filtering:** Advertise only permitted prefixes; avoid leaking full internal routing tables or unintended default routes.
- **Route priority:** Pick primary/backup via supported policy; test both data center → cloud and cloud → data center directions.

**A BGP session showing UP does not guarantee APIs are working.** Add application-level probes and monitor critical paths. Likewise, health probes do not replace actual routing mechanics.

### 7.3. Asymmetric Routing and Stateful Firewalls

With multiple circuits, outbound packets might cross the private link while return packets traverse the VPN. A stateful firewall that never saw the initial session handshake can drop return packets. Designs must therefore check:

- Forward path and return path.
- Whether firewall and NAT state are shared/synchronized.
- When routes shift, whether active TCP sessions must reconnect or stay alive.
- Whether per-traffic routing policies introduce asymmetry.

Never test with `ping` alone. Test real application connections, long-lived requests, high concurrency, and mid-session failover.

## 8. DNS and Service Discovery Across Both Environments

Applications normally use hostnames like **inventory.internal.example** rather than static IPs. For internal hostnames to work across hybrid links, deploy controlled DNS resolvers/forwarders between cloud and on-prem with clear zones and access policies.

Issues to address:

- **Split-horizon DNS:** The same name can return different IPs per environment; ensure callers get the right answer.
- **Conditional forwarding:** Forward only required zones; prevent A ↔ B resolver loops.
- **DNS over hybrid:** When VPN/circuits drop, do DNS queries stall on long timeouts? Are backup resolvers available on each side?
- **Caching and TTL:** Low TTLs do not guarantee every client refreshes instantly, especially apps holding persistent connection pools.
- **Prevent internal leaks:** Private hostnames and IPs must never be leaked to public resolvers.

For Java applications, tune DNS caching, connection pooling, and connection lifetimes during endpoint failovers. Even with healthy redundant links, apps can suffer extended outages if DNS caches or connection pools cling to stale IPs.

## 9. Security: VPN and Private Links Are Only Part of the System

### 9.1. Layered Security Controls

| Control layer | Key question | Example |
| --- | --- | --- |
| Network segmentation | Which subnets may talk to which subnets? | Only sync workers call Inventory API on required ports |
| Transport protection | How is data protected in transit? | IPsec over Internet, TLS between services; encrypt private circuits if required |
| Identity | Who is calling the API and how are they authenticated? | mTLS, OAuth2/client identity, or approved auth mechanism |
| Authorization | Which actions may the caller execute? | Sync service account may read only a scoped inventory subset |
| Data protection | Is personal/secret data scoped and encrypted? | Data classification, key management, no plaintext secrets in logs |
| Audit and incident response | Can unauthorized changes or anomalous access be detected? | Flow logs, gateway logs, audit events, alerts |

“Putting the database in a private subnet” narrows the attack surface, yet proves nothing about DB security posture; still verify permissions, patching, secrets, backups, encryption, and auditing.

### 9.2. VPN Key Management and Edge Appliances

- Prefer organization-approved authentication methods and cipher suites; verify support on both edge gear and cloud gateways.
- Protect keys/PSKs, certificates, and gateway admin access; maintain rotation schedules and recovery plans.
- Separate log-reading permissions from route or security-policy modification rights wherever possible.
- Restrict allowed peer endpoint IPs; alert on unapproved config changes.
- Keep network appliances patched and configs backed up.
- Redact sensitive data and auth secrets in logs.

Never commit live keys or PSKs into source code, training docs, or ticketing systems. Configuration examples in this lesson use illustrative addresses and parameters only.

### 9.3. Shared Responsibility and Compliance

Cloud providers secure underlying infrastructure within their service scope, while enterprises generally manage connectivity policies, IAM, firewall rules, data, on-prem endpoints, and operational processes. Exact boundaries depend on the service and contract.

**Data residency:** Moving data from a data center to the cloud for analytics, backups, or sync must account for storage regions and compliance policies. A private channel does not by itself make cross-border or regulated transfers compliant.

## 10. Performance: Bandwidth, Latency, Jitter, MTU, and Bottlenecks

### 10.1. Do Not Confuse Bandwidth with Response Time

- **Bandwidth/throughput:** Volume of data transferable per unit of time.
- **Latency:** Time for a packet or request to cross the network and be processed.
- **Jitter:** Variation in packet delay, critical for voice/video or time-sensitive apps.
- **Packet loss:** Dropped packets force TCP retransmissions, stretching transaction times.
- **p95/p99:** Latency percentiles crucial for evaluating tail experience under high load.

A 1 Gbps circuit does not guarantee a 10 ms API call, because requests also depend on databases, app processing, round trips, queues, TLS, and downstream dependencies.

### 10.2. Estimating Required Bandwidth

Suppose an application syncs **200 transactions/second**, each exchanging an average of **150 KiB** across the hybrid link (combined request/response payload):

~~~text
Payload throughput = 200 transactions/s × 150 KiB/transaction
                   = 30,000 KiB/s
                   = 30,000 × 1,024 × 8 bit/s
                   = 245,760,000 bit/s
                   ≈ 245.76 Mbps
~~~

Adding **30% headroom on payload throughput**, the reference target is roughly:

~~~text
245.76 Mbps × 1.30 ≈ 319.49 Mbps
~~~

This is an illustrative exercise; buying a 320 Mbps link is not guaranteed sufficient. Factor in transport/IPsec overhead, peak bursts, concurrent flows, retransmissions, QoS, backup traffic, and how the carrier meters bandwidth. In particular, if responses are much larger than requests or periodic batch syncs run, size **each traffic direction** separately.

### 10.3. MTU/MSS and Fragmentation

IPsec adds encapsulation headers that reduce the safe payload size across a path. If one side sends packets larger than the path MTU, fragmentation or silent drops cause mysterious timeouts. These bugs often appear only on large responses while small pings succeed.

Checks to apply:

- Path MTU discovery and appropriate ICMP policies.
- MSS clamping or tunnel/interface MTU tuning per supported configurations.
- Test large payloads, real requests, and concurrent load—not just small probe packets.
- Monitor retransmissions, fragmentation/drops, and tunnel errors.

There is no universal optimal MTU number for every path; measure and verify against appliance/service specs.

### 10.4. Applications and Databases: Reducing Round-Trip Dependencies

If one cloud ordering request makes five sequential calls to an on-prem API for small payloads, network latency multiplies fivefold. Consider:

1. **Batch APIs** instead of chatty individual calls.
2. **Cloud-side caches or read models** for data tolerating slight staleness.
3. **Async sync via queues/events** for flows not requiring immediate synchronous answers.
4. **Co-locating logic near data** when policy and business goals allow.
5. **Timeouts, bounded retries, and circuit breakers** to prevent amplifying network faults.

Switching to async sync introduces **eventual consistency**; define acceptable data lag and reconciliation procedures for extended outages. Never sacrifice business correctness solely to shave latency.

## 11. High Availability and Recovery Strategies When Links Fail

### 11.1. Fault-Domain Analysis

Never treat a single “VPN down” scenario as representative of all outages. Distinguish:

- One IPsec tunnel expires/drops while Internet remains up.
- One on-prem router/firewall appliance dies.
- One carrier or fiber link drops.
- A cloud gateway or interconnect facility is impaired.
- Internal DNS stops resolving.
- Misconfigured routing or overlapping prefixes cause a blackhole.
- Link stays up while latency/packet loss breaches thresholds.
- Link is healthy while the on-prem ERP API/database fails.
- Control plane outage blocks config changes needed for recovery.

Each failure behaves differently and demands tailored **quality scenarios** and tests.

### 11.2. RTO and RPO in Network Architecture

**RTO** is the acceptable time limit to restore business functionality after a defined outage. For hybrid network failures, measure RTO until **users complete the required business journey**, not merely until the BGP session returns to established.

**RPO** is the maximum acceptable time window of data loss. RPO stems from data replication/write patterns; swapping VPN for a dedicated circuit **does not automatically make RPO zero**. If events sit in queues during a link drop, verify zero loss, zero duplicates, and proper ordering upon recovery.

### 11.3. Degradation Modes During Link Loss

Some features can keep serving when on-prem connectivity drops:

| Feature | Degradation behavior options | Conditions to verify |
| --- | --- | --- |
| Read catalog | Serve from latest cache/read model | Data freshness limits and status messaging |
| Create booking | Pause writes or accept as pending | Prevent overselling; enforce idempotency |
| Report sync | Buffer events in queue for later processing | Sufficient queue capacity and retention |
| Login | Accept valid session tokens if policy permits | Token lifetime, revocation checks, risk controls |
| Sensitive data admin | Deny until channel recovers | Clear error messages; zero unauthorized bypasses |

These choices require business sign-off. For instance, allowing bookings against stale inventory risks double-booking; without consistent reservation controls, pausing critical writes may be safer.

## 12. Designing Monitoring and SLOs for Hybrid Connectivity

Do not rely solely on **UP/DOWN** tunnel status. Mature observability spans multiple layers:

| Layer | Metrics | Meaning |
| --- | --- | --- |
| Circuit/Internet | Link state, interface errors, bandwidth, drops | Physical link health and saturation |
| Tunnel/IPsec | IKE/IPsec SA status, rekey times, negotiation errors | Encrypted tunnel health |
| Routing | BGP neighbors, prefix counts, route churn, convergence | Route exchange and path selection |
| Network quality | RTT, loss, jitter, throughput, retransmissions | Actual transport quality |
| DNS | Resolution success rate and lookup latency | Cross-environment name dependency |
| Application | API p95/p99, error rate, transaction success, timeouts | Real user impact |
| Data integration | Replication lag, queue age, processing errors/duplicates | Data quality and consistency |
| Cost | Bytes transferred, port/circuit/egress, cost per transaction | Budget sustainability |

### 12.1. SLIs, SLOs, and Error Budgets

An **illustrative** example for inventory sync:

- **SLI:** Proportion of valid Inventory API requests from the cloud app returning accurate results within 2 seconds.
- **SLO:** At least 99.9% of valid requests satisfy the SLI over a rolling 30-day window.
- **Error budget:** At a 99.9% SLO, 0.1% of measured requests are allowed to miss the target per period; error inclusions/exclusions must be agreed upfront.

The **network link** SLO and the **end-to-end Inventory API** SLO are distinct targets. The network may meet packet-loss goals while the API still fails due to the database or application code.

### 12.2. Six-Part Quality Scenarios

A complete scenario defines **stimulus source, stimulus, environment, artifact, response, and response measure**.

**Scenario QA-NET-01 — Failover from Private Circuit to VPN:**

| Element | Description |
| --- | --- |
| Stimulus source | Carrier fault cuts primary private circuit |
| Stimulus | Primary link stops passing data |
| Environment | Peak hours, Inventory API serving 100 req/s |
| Artifact | On-prem router/firewall, cloud gateway, routes, Inventory API |
| Response | Fault detected, traffic shifts to VPN, non-critical sync throttled if needed |
| Response measure | Within 5 minutes of fault injection, ≥ 99% of valid business requests succeed across the 10-minute post-recovery window; zero duplicate writes in test suite |

Thresholds here are **hypothetical learning targets** and must be negotiated from business impact. Also measure the actual blackout interval from failover start to transaction completion, failed request counts, and how much load the backup VPN sustains.

**Scenario QA-NET-02 — Sustaining Data Sync Load:**

When workers exchange an average of 250 Mbps of payload continuously for 30 minutes between cloud and data center under normal conditions, the link must sustain required throughput, keep packet loss within agreed thresholds, and keep queue lag within target. Measure both directions, protocol overhead, and competing traffic.

**Scenario QA-NET-03 — Access Restriction:**

When a staging workload sends requests to the production ERP database over the hybrid network, firewalls and authorization controls must reject 100% of unauthorized attempts in the defined test suite, leak zero data, and emit traceable audit events.

### 12.3. Actionable Alerting

- Alert on link/tunnel down and route changes with context on which path was affected.
- Alert on sustained high latency, packet loss, and saturation—avoid paging on fleeting micro-spikes.
- Alert when Inventory API actually misses its SLO, even if tunnels report UP.
- Alert when running on backup VPN longer than operational policy allows or when backup nears capacity.
- Link every alert to dashboards, runbooks, and an accountable owner.

## 13. TCO: Costs of VPN, Dedicated Circuits, and Hybrid Backup

Cloud VM pricing alone cannot guide hybrid networking decisions. **Total Cost of Ownership (TCO)** must include:

- Cloud gateways, VPN tunnels, private connection ports, and hub/transit processing.
- Internet/leased lines, carrier fees, cross-connects, edge gear, and maintenance.
- Cloud outbound data transfer (*egress*) and per-service processing fees.
- Redundancy costs: secondary routers, ports, ISPs, circuits, and diverse sites.
- Encryption, monitoring, logs, security controls, DNS, and engineering labor.
- Setup, site survey, installation fees, and provisioning lead time.
- Failover drills, performance testing, vendor support, and contract changes.

### 13.1. Hypothetical Cost Comparison Example

The table below uses **illustrative numbers created for this lesson**, not vendor quotes or commitments. Unit: **million VND/month**. Assumes options serve the same workload and data volume, though you must still verify whether they meet equivalent SLOs.

| Line item | VPN-only | Two private circuits | Private + VPN backup |
| --- | ---: | ---: | ---: |
| Cloud VPN gateway/tunnels | 8 | 0 | 8 |
| Cloud private port/circuit | 0 | 45 | 45 |
| Carrier, cross-connect | 0 | 35 | 35 |
| Second backup private path | 0 | 45 | 45 |
| Assumed data transfer/egress | 12 | 12 | 12 |
| Allocated monitoring and ops | 18 | 22 | 24 |
| **Monthly total** | **38** | **159** | **169** |

For example, recurring TCO for Private + VPN in the table above is:

~~~text
8 + 45 + 35 + 45 + 12 + 24 = 169 million VND/month
~~~

If there is a **240 million VND** one-time setup fee amortized over 24 months:

~~~text
240 / 24 = 10 million VND/month
Amortized TCO of Private + VPN = 169 + 10 = 179 million VND/month
~~~

**Note for fair comparison:** The two-private-circuits column already includes two dedicated paths, whereas VPN-only did not specify two physically diverse ISPs. This table shows illustrative cost structure, not a claim that all three deliver identical reliability. To decide fairly, match fault domains, backup capacity, and SLOs first, then recalculate costs.

### 13.2. Business Unit Economics

You can add:

~~~text
Hybrid connectivity cost per successful transaction
    = Total connectivity cost in period / Successful business transactions in period
~~~

With an amortized TCO of 179 million VND/month and 500,000 completed valid transactions, the allocated hybrid connectivity cost is **358 VND/transaction**. This excludes app compute/database costs if accounted separately.

Decision models must weigh **cost of downtime** (lost revenue, delayed transactions, data risk, contractual penalties) alongside TCO. A cheaper circuit that violates SLOs is not an equivalent alternative.

## 14. Case Study: Moving Ordering to Cloud While Keeping ERP in the Data Center

### 14.1. Input Requirements

An enterprise deploys a Spring Boot ordering API in the cloud while its ERP and inventory database remain in the data center. In Phase 1:

- Cloud API serves external users, authenticating at the cloud layer.
- During order creation, it checks ERP inventory; certain cases write reservations into ERP.
- Average traffic is 100 req/s, peaking at 300 req/s; each transaction exchanges small payloads that must be accurate.
- Reporting sync pushes batch data, tolerating several minutes of delay.
- ERP permits connections only from registered app subnets.
- Business targets restoring app communication within 5 minutes of a primary link failure, sustaining critical transactions at agreed capacity.

Numbers are learning examples, not universal cloud standards.

### 14.2. Option Comparison

**Option A — Site-to-site VPN:** Fast to deploy, convenient for testing business flows and phased cutover. Must verify peak-hour bandwidth, Internet variance, failover, and tunnel config. Using a single ISP risks losing all connectivity on an ISP outage.

**Option B — Private connection:** Steady and suited to long-term sync. Must assess provisioning lead time, circuit/port fees, HA, and encryption. A single private circuit remains a single point of failure.

**Option C — Private primary + VPN backup:** Uses the private link under normal operations and VPN during outages. Must verify the backup can carry at least critical order-creation flows; heavy batch reporting can pause during failover.

**Illustrative decision:** Start with VPN for early integration and testing. Once traffic, budget, and operational commitments are confirmed, deploy a private connection as primary while retaining VPN as backup. Phase transitions require an ADR and real measurements rather than assuming “private is always better”.

### 14.3. Proposed Architecture

~~~mermaid
flowchart TB
    USERS["Internet users"] --> WAF["WAF / Public API"]
    WAF --> APP["Cloud Order API - multi AZ"]
    APP --> CLOUDGW["Hybrid gateway"]
    CLOUDGW --> PRIVATE["Private circuit"]
    CLOUDGW --> VPN["VPN backup"]
    PRIVATE --> DCEDGE["DC HA edge routers"]
    VPN --> DCEDGE
    DCEDGE --> FW["ERP segment firewall"]
    FW --> ERP["Inventory service / ERP"]
    APP --> QUEUE[("Reporting queue")]
    QUEUE --> SYNC["Async worker"]
    SYNC --> CLOUDGW
~~~

Principles:

1. **Never expose the ERP database directly** to Internet clients or broad cloud subnets.
2. Service-to-service calls enforce dedicated identity/authorization, encryption, and auditing.
3. Set timeouts on Inventory API calls; avoid unbounded retries during link outages.
4. Inventory mutation calls carry transaction IDs/idempotency and reconcile after client timeouts.
5. Batch reporting stays queued when backup links run at reduced capacity.
6. Routing is tested bidirectionally, including failback to primary.

### 14.4. Acceptance Testing

- **Connectivity tests:** Ping and TCP/TLS to valid endpoints; verify routes and DNS; confirm staging cannot reach production.
- **Load tests:** Generate 100/300 req/s with representative payloads; measure order-creation p95/p99, bidirectional bandwidth, and error rates.
- **Failover tests:** Cut the private path in a controlled environment; measure time until order API succeeds via VPN, error counts, and latency increase.
- **Correctness tests:** Intentionally drop responses after ERP writes a reservation; client retries must not create duplicate reservations.
- **Backup capacity tests:** Over VPN, pause batch reporting and confirm critical order flows meet minimum targets.
- **DNS/security tests:** Verify backup resolvers, certificate/secret rotation, access controls, and audit logs.
- **Failback tests:** Restore private circuit; verify route stability, active sessions, throughput, and ordered backlog drain.

Test reports must record configs, timestamps, load levels, measurements, and pass/fail outcomes. A tunnel showing UP is never enough for sign-off.

## 15. Step-by-Step Implementation Workflow

A real project can follow this sequence:

1. **Gather requirements:** Business flows, data types, bidirectional throughput, latency, security, SLOs, and RTO/RPO.
2. **Survey existing networks:** CIDRs, WAN links, firewalls, ISPs, HA appliances, DNS, and on-prem app dependencies.
3. **Map data flows:** Define exact sources, destinations, ports, protocols, identities, and owners.
4. **Select connectivity model:** VPN, private, or hybrid; map fault domains and redundancy plans.
5. **Plan addressing/routing:** Non-overlapping CIDRs, BGP/static routing, prefix filters, primary/backup rules, and failback.
6. **Design security:** IPsec/TLS, firewalls, IAM, key management, sensitive data handling, logging, and least privilege.
7. **Deploy in controlled stages:** Verify individual links, DNS, routes, and return paths before opening business traffic.
8. **Load test and fault-inject:** Measure throughput, p95/p99, packet loss, MTU, failover, queue lag, and data correctness.
9. **Hand over to operations:** Dashboards, alerts, runbooks, carrier/cloud support contacts, change processes, and drill schedules.
10. **Record ADRs and review:** Revisit when traffic, pricing, data placement, or risk profiles shift.

### 15.1. Conceptual YAML Connectivity Plan Sample

This example is an **architecture documentation template**, not a configuration runnable directly against appliances or cloud APIs.

~~~yaml
id: HYBRID-NET-008
owner: Network_and_Platform_Team
on_prem_cidr: 10.20.0.0/16
cloud_prod_cidr: 10.40.0.0/16
connectivity:
  primary: dedicated_private_circuit
  backup: site_to_site_ipsec_vpn
routing:
  method: bgp
  allowed_prefixes:
    - 10.20.0.0/16
    - 10.40.0.0/16
security:
  network_policy: least_privilege
  service_to_service: tls_with_identity
  encryption_on_private_link: validate_requirement
observability:
  - circuit_state
  - tunnel_state
  - bgp_route_state
  - latency_p95
  - packet_loss
  - inventory_api_success_rate
failover_validation:
  drill_id: TEST-NET-FAILOVER-01
  service_rto_target_minutes: 5
  backup_capacity: critical_workload_only
status: proposed
~~~

In production systems, add exact subnets, appliances, terminations, ASNs, route advertisements, rollback triggers, SLO owners, and test methods. Never put VPN keys in this descriptor file.

## 16. Common Design Pitfalls

| Claim or mistake | Why it causes problems | Remediation |
| --- | --- | --- |
| “Private links automatically encrypt data.” | Private paths do not necessarily encrypt payloads. | Assess security needs and apply TLS/IPsec or suitable encryption. |
| “Two VPN tunnels guarantee HA.” | Both tunnels may share one router, ISP, or power source. | Evaluate independence by physical fault domain. |
| “BGP UP means the app works.” | Routes may exist while DNS, DB, app, or firewalls fail. | Monitor synthetic transactions and end-to-end SLOs. |
| “VPN has enough bandwidth because ping is fast.” | Small pings hide throughput, MTU, and real-load behavior. | Load test, measure both directions, and check packet loss. |
| “With a private circuit, no VPN backup is needed.” | A single circuit still drops from fiber cuts, port faults, or carrier outages. | Design redundancy from risk and RTO. |
| “Any private CIDRs can interconnect.” | Overlapping CIDRs cause ambiguity and routing failures. | Plan addressing, filter prefixes, and avoid messy NAT. |
| “Only cloud-to-DC routes are needed.” | Missing return paths cause request timeouts. | Check both directions, firewall state, and NAT. |
| “Open all internal ports for easy integration.” | Widens blast radius of outages and breaches. | Enforce segmentation, allowlists, and least privilege. |
| “A 1 Gbps link means the API is fast.” | Latency and app/DB processing can still dominate. | Measure end-to-end p95/p99 and optimize cross-network calls. |
| “Failover completion equals consistent data.” | Retries and in-flight transactions risk duplicates or drops. | Enforce idempotency, queues/outbox, and reconciliation. |
| “Switching to private links cuts all costs.” | Introduces port, carrier, cross-connect, and ops expenses. | Calculate TCO across matching quality and risk scopes. |

## 17. Practice Exercise

**Scenario:** A hypothetical bank runs customer management and a transactional database across two on-premises data centers. The cloud hosts web apps and reporting services. Normal internal-data traffic is 150 req/s, peaking at 500 req/s. Data is highly sensitive; every write transaction must verify permissions and prevent duplicate processing. Budget is constrained, and critical connectivity recovery is targeted within 5 minutes.

Deliverables:

1. **Flow design:** Diagram on-prem and cloud including CIDRs, DNS, firewalls, app subnets, data subnets, and hybrid termination points.
2. **Option comparison:** Compare VPN-only, two private circuits, and private + VPN backup; build a pros/cons table covering security, throughput, latency, HA, operations, and TCO.
3. **Write three six-part quality scenarios:** One link-loss scenario, one high-load scenario, and one unauthorized-access scenario; set illustrative thresholds and measurement methods.
4. **IP planning:** Assign non-overlapping CIDRs across environments; describe forward/return routes and BGP or static routing.
5. **Bandwidth sizing:** At 500 req/s and 120 KiB exchanged per request, compute payload throughput, add 25% headroom, and explain factors making real bandwidth requirements differ.
6. **Failover testing:** Describe how to simulate private-link loss and prove VPN carries critical transactions; define policy for deprioritized reporting.
7. **Data reconciliation:** Specify how to handle client timeouts after the on-prem system has already committed a transaction.
8. **TCO calculation:** Use realistic assumptions for circuits, egress, gateways, hardware, labor, and drills; compare options meeting the same target.
9. **Write an ADR:** Select an option and state residual risks, metrics to gather, and review triggers.

**Self-check hints:** Never judge an interconnect solely by tunnel uptime. Passing designs include **concrete applications, measurable SLIs, bidirectional network paths, security controls, failure modes, and end-to-end test results**.

## 18. Pre-Approval Design Checklist

- [ ] Systems and data exchanged between data centers and cloud are clearly documented.
- [ ] Choice of VPN, private circuit, or hybrid is backed by real workload and risk profiles.
- [ ] Non-overlapping CIDR plan, IPAM, and expansion rules are established.
- [ ] Routes, BGP/static routing, prefix filters, primary/backup preferences, and return paths are defined.
- [ ] Diagram covers all appliances, circuits, ISPs, PoPs, and shared failure points.
- [ ] TLS/IPsec and access-control policies match data sensitivity.
- [ ] Internal DNS, timeouts, and link-loss degradation behavior are verified.
- [ ] MTU/MSS, packet loss, latency, jitter, throughput, and bidirectional peak load are measured.
- [ ] SLIs/SLOs cover business transactions, not merely tunnel state.
- [ ] Failover and failback drills verify RTO/RPO, queue lag, and idempotency.
- [ ] Backup VPN or standby channel holds sufficient capacity for priority flows.
- [ ] TCO includes circuits, gateways, egress, hardware, monitoring, support, and labor.
- [ ] Runbooks, alerts, owners, change processes, and ADRs with review triggers exist.
- [ ] Reliability, security, performance, cost, operations, and sustainability are evaluated under Well-Architected.

## 19. Alignment with Well-Architected

| Pillar | Questions when reviewing hybrid connectivity |
| --- | --- |
| **Operational Excellence** | Are owners, cross-env monitoring, IaC, runbooks, and drills in place? |
| **Security** | Are encryption, segmentation, identity, least privilege, and auditing enforced across both environments? |
| **Reliability** | Are fault domains independent, does failover meet RTO, and is data consistent after outages? |
| **Performance Efficiency** | Do bandwidth, p95/p99, packet loss, MTU, and app round trips handle real load? |
| **Cost Optimization** | How does VPN/private/hybrid TCO compare against risk reduction and business volume? |
| **Sustainability** | Are redundant transfers, over-provisioned standby links, and unnecessary processing avoided? |

**Conclusion:** Site-to-site VPN and dedicated circuits are two tools for connecting data centers to the cloud, each with distinct strengths and constraints. Architectural quality is determined by **data correctness, security, fault tolerance, measured performance, lifecycle cost, and operational capability**. Sound decisions start from business scenarios, validate through load and failover tests, and are revisited whenever requirements evolve.
