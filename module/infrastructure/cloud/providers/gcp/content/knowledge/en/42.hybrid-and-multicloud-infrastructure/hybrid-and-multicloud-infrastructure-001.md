# Hybrid Cloud and Multicloud Models with Google Cloud

An enterprise rarely migrates its entire system to a single cloud all at once. Transactional data may remain in an on-premises data center, Java/Spring applications may already run on Google Kubernetes Engine (GKE), a partner may operate an API on AWS, and an analytics team may use BigQuery. When these components work together to serve a business process, the organization needs a controlled **hybrid cloud** or **multicloud** architecture.

Hybrid cloud connects on-premises infrastructure with cloud resources; multicloud uses services from two or more cloud providers. Both models can coexist. Value does not come solely from setting up a VPN or dedicated circuit, but also from **routing, DNS, identity, authorization, data, resilience, observability, operations, and cost**.

Google Cloud provides components such as Virtual Private Cloud (VPC), HA VPN, Cloud Interconnect, Cross-Cloud Interconnect, Cloud Router, Network Connectivity Center, Cloud DNS, Cloud IAM, GKE, Google Distributed Cloud, and data services. Each product addresses one layer of the architecture; no single service automatically turns distributed infrastructure into a secure and highly reliable system.

This lesson builds the model from business needs to topology, connectivity, identity, data, and operations, using an example Java/Spring application that uses both on-premises systems and Google Cloud.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between private cloud, public cloud, hybrid cloud, multicloud, and hybrid multicloud.
- Identify scenarios where each model should be used, rather than adopting multicloud for trend's sake.
- Design VPCs, IP addressing, routing, DNS, and project boundaries for interconnected systems.
- Compare HA VPN, Dedicated/Partner Interconnect, and Cross-Cloud Interconnect.
- Explain the roles of Cloud Router, BGP, and Network Connectivity Center in hub/spoke topologies.
- Apply Zero Trust, IAM, workload identity, and transport security across environments.
- Build communication and data synchronization approaches with clear RTO/RPO, latency, and consistency guarantees.
- Choose how to run Java applications, Kubernetes, and edge workloads across multiple environments.
- Design cross-cloud logging, monitoring, IaC, runbooks, and cost allocation.
- Plan verifiable migration, pilot, cutover, and rollback roadmaps.

## 1. Distinguishing Infrastructure Models

| Model | Characteristics | Example |
|---|---|---|
| On-premises/private cloud | Infrastructure owned or operated by the organization in its own data center | VMware or on-prem Kubernetes |
| Public cloud | Services on a single cloud provider | Java application running on Cloud Run |
| Hybrid cloud | Connects on-premises infrastructure and public cloud into a shared operational flow | Java API on GKE accessing an on-prem database over HA VPN |
| Multicloud | Uses resources from at least two public cloud providers | Backend on GCP and analytics on AWS |
| Hybrid multicloud | Simultaneously includes on-prem and multiple public clouds | On-prem ERP, web on GCP, partner data on Azure |

**Hybrid does not mean all components must continuously transfer data.** A company can use on-prem for data with residency requirements, the cloud for APIs, and transfer a subset of data in batches.

**Multicloud also does not require every application to be deployed on every cloud.** A multicloud strategy can partition workloads: service A runs on GCP, service B runs on AWS, while communication between them is controlled via APIs and networking.

### How do hybrid and multicloud differ?

- Hybrid focuses on the boundary between self-operated environments and the cloud.
- Multicloud focuses on the boundary between cloud providers.
- Both require managing multiple platforms, access permissions, network addresses, logs, and policies.
- The greatest risks typically lie in integration and ownership, not just connectivity technology.

## 2. When Do You Need Hybrid or Multicloud?

Several valid drivers:

1. **Incremental migration:** keeping the source ERP/database while moving Java APIs to GCP.
2. **Data residency:** data must be processed at a specific facility or within a specific legal jurisdiction.
3. **Edge latency:** processing sensor data near a factory and pushing aggregated results to Google Cloud.
4. **Mergers and acquisitions:** two businesses are already using two different clouds.
5. **Best-fit services:** a workload requires a specialized service from another provider.
6. **Business continuity:** separating certain failure domains or preparing DR per requirements.
7. **Contracts and licensing:** an application or database cannot be migrated immediately.
8. **Partner integration:** payment or logistics systems operate on another cloud.

### When should you avoid it?

- Merely to claim vendor lock-in avoidance without a concrete business requirement.
- The organization lacks foundational SLOs, on-call practices, IaC, identity governance, and network ownership.
- The application requires synchronous transactions between two clouds with ultra-low latency.
- Egress, observability, and operational costs exceed the benefits.
- Active-active is required, but the data layer has no strategy to prevent split-brain.

A single-cloud architecture across multiple zones/regions can provide better reliability and simplicity than an unverified multicloud setup. Compare options against concrete requirements.

## 3. Common Topology Patterns

### 3.1. Hybrid extension: GCP applications, on-prem data

~~~text
     Users
       |
       v
  Cloud Load Balancing
       |
       v
  Cloud Run / GKE / Compute Engine
       |
       v
   Google Cloud VPC
       |
       +--- Cloud Router (BGP control plane)
       |
       +--- HA VPN or Interconnect
                 |
                 v
        On-prem network
                 |
           +-----+-----+
           |           |
           v           v
        ERP API      Database
~~~

Pros: migrate applications incrementally, leverage GCP compute/CI/CD. Risks: the request path still depends on connectivity to on-prem and may incur higher latency.

### 3.2. Functional multicloud split

~~~text
         Public clients
               |
               v
       Checkout API on GCP
               |
       +-------+--------+
       |                |
       v                v
 Inventory GCP     Partner API on AWS
       |                |
       v                v
  Cloud SQL         Managed database
~~~

Each provider has distinct responsibilities. Communication can occur over authenticated HTTPS or private connectivity if needed. You do not have to build full network interconnectivity just because one API needs to call another provider.

### 3.3. Hub/spoke across multiple VPCs and external sources

~~~text
       On-prem DC                   AWS / Azure
          |                              |
       VPN / VLAN                    VPN / VLAN
          |                              |
       Hybrid spoke                 Hybrid spoke
           \                            /
            \                          /
             v                        v
              Network Connectivity Center
                         Hub
                /         |         \
               v          v          v
           VPC Prod    VPC Shared   VPC Analytics
             spoke       spoke         spoke
~~~

Network Connectivity Center (NCC) helps organize hub/spoke topologies and route exchange based on spoke types and hub modes. NCC does not automatically create all VPN/Interconnect resources or bypass firewall/IAM controls.

## 4. Landing Zone: The Starting Point Before Connecting Networks

Before establishing connectivity, align on foundational infrastructure:

- Google Cloud organization, folder, and project boundaries.
- IAM groups, service accounts, and permission structures.
- VPC layout, subnets/secondary ranges, and IPAM.
- Logging, auditing, budgets, policies, and billing ownership.
- Regions/zones based on latency, residency, and availability.
- Terraform or a reviewed Infrastructure as Code (IaC) mechanism.
- Service perimeters, firewall policies, and egress restrictions.
- Network operations, on-call, and cross-provider escalation paths.

### Separating projects by function

| Example project | Responsibility |
|---|---|
| net-host-prod | Shared VPC, Cloud Router, VPN/Interconnect, DNS |
| app-checkout-prod | Production Java/Spring workloads |
| data-prod | Cloud SQL, Storage, BigQuery |
| ops-security | Audit, monitoring, and security operations |
| sandbox | Isolated experimentation separate from production |

Shared VPC allows multiple service projects to use subnets from a host project, but requires granting appropriate IAM roles. Do not confuse Shared VPC with peering or NCC: each technology has a different connectivity goal and scope.

### Protecting boundaries between environments

- Dev does not get default routes or access to production.
- Each project/service uses a least-privilege service account.
- Do not use a single infrastructure account with Owner across all cloud providers.
- Hybrid connections must have an inventory, owner, route policy, and review schedule.
- Do not share secrets or database credentials between test and production.

## 5. Designing IP Addressing and Subnets

**Overlapping CIDRs are one of the most common blockers in hybrid/multicloud.** If on-prem uses `10.20.0.0/16` and the GCP VPC also uses `10.20.0.0/16`, traffic between the two sides has no unambiguous routing path as intended.

Example IP plan:

| Zone | Illustrative CIDR | Notes |
|---|---|---|
| On-prem datacenter A | 10.10.0.0/16 | ERP, database |
| On-prem datacenter B | 10.11.0.0/16 | Backup/DR |
| GCP prod VPC | 10.20.0.0/16 | Separate subnets by region |
| GCP dev VPC | 10.21.0.0/16 | No routing to prod unless required |
| AWS partner VPC | 10.30.0.0/16 | Restricted connectivity per API |
| GKE Pod ranges | 10.40.0.0/16 | Check secondary ranges |
| GKE Service ranges | 10.41.0.0/20 | Check routing/NAT for each flow |

These CIDRs are illustrative only. Actual addresses must come from the organization's IP Address Management (IPAM) system.

### Steps to build an IP plan

1. Collect IPs from vSphere/CMDB, routers, firewalls, AWS VPCs, Azure VNets, and GCP VPCs.
2. Check for overlaps among networks that may exchange routes.
3. Reserve GKE Pod/service ranges and database/private service ranges.
4. Allocate subnets by region/environment/security zone.
5. Decide which routes will be advertised via BGP.
6. If renumbering is impossible, design NAT or proxies per use case and evaluate their limitations.
7. Store IP allocations in a source of truth with an owner.

### Notes on routes

Routes in a GCP VPC do not mean every service automatically has reachability. Cloud Run private connectivity, load balancers, Private Service Connect, Cloud SQL private IP, and GKE Pod IPs have distinct routing mechanisms. For each application path, verify source, destination, next hop, firewall, DNS, and the return path.

## 6. Choosing HA VPN for Flexible and Encrypted Connectivity

Cloud VPN creates IPsec VPN tunnels from a VPC to a peer network over the public internet. **HA VPN** is the recommended option when the peer supports BGP and high availability is needed; **Classic VPN** is the legacy type using static routing.

### Comparison

| Feature | HA VPN | Classic VPN |
|---|---|---|
| Routing | Dynamic BGP via Cloud Router | Static routing |
| Redundancy | Two interfaces on the HA VPN gateway, multiple tunnels | Depends on redundancy design |
| Availability SLA | Can reach 99.99% with a qualifying topology | Typically 99.9% |
| IPsec encryption | Yes | Yes |
| IPv6 | Supported based on configuration | Not supported |
| Recommendation | New hybrid connections when peer supports BGP | Only when static routing is mandatory |

The SLA level must be verified against the topology and service terms; do not assume every HA VPN configuration automatically achieves 99.99%.

### Deployment flow

1. Create the VPC/subnets in the network host project.
2. Create the HA VPN gateway.
3. Register the peer VPN gateway with appropriate IPs/interfaces.
4. Create a Cloud Router with an appropriate ASN.
5. Create the VPN tunnels and BGP peers.
6. Advertise the right prefixes, and control priorities and route filters.
7. Test connectivity and per-tunnel failover.
8. Enable monitoring and alerts for tunnel/BGP health.

### Why use BGP?

BGP allows both sides to exchange IP prefixes and update routes when topology changes. When a tunnel fails, routes are updated according to BGP and VPC routing rules, enabling failover to the remaining active path if redundancy is configured properly.

Do not just check "tunnel up"; verify received routes, advertised routes, actual next hops, and application connectivity.

## 7. Cloud Router: Control Plane, Not Data Plane

Cloud Router manages **BGP sessions** and dynamic routes. Cloud Router **does not directly forward application packets**; data forwarding is performed by the VPC network infrastructure.

~~~text
  On-prem BGP Router
          |
          | BGP route advertisements
          v
       Cloud Router
          |
          | Routes learned/advertised
          v
  GCP VPC dynamic route control
          |
          v
  VPC data plane -> Workload
~~~

### Key routing decisions

- Choose regional or global dynamic routing mode based on VPC requirements.
- Use non-conflicting ASNs across the required BGP peers.
- Advertise only authorized subnet/summary prefixes.
- Use priority/MED/route policies as supported to avoid unintended asymmetric paths.
- Configure route filtering and prevent accidental default route advertisement.
- Verify route propagation across multiple VPCs and environments.
- Maintain runbooks for BGP session down, missing routes, asymmetric paths, and MTU issues.

**Do not let a small BGP change accidentally advertise production network ranges to every spoke.** Route exchange configurations must be reviewed just like firewall and IAM changes.

## 8. Cloud Interconnect: Dedicated Circuits, Performance, and Responsibility

Cloud Interconnect connects on-prem to Google's network through a dedicated connection or via a partner.

| Type | Connection path | When appropriate |
|---|---|---|
| Dedicated Interconnect | Direct physical connection at a supported colocation facility | High bandwidth, organization already has colocation infrastructure |
| Partner Interconnect | Via a supported connectivity provider | No direct colocation presence or need flexible bandwidth tiers |
| Cross-Cloud Interconnect | Dedicated physical connectivity between Google Cloud and another cloud provider | Large, steady cross-cloud traffic |
| Partner Cross-Cloud Interconnect | Via a supported partner/cloud partner | Want private cross-cloud connectivity via a partner service |

### Cloud Interconnect does not encrypt data by default

Dedicated/partner circuits do not automatically provide IPsec encryption. If transport confidentiality is required:

- Use **HA VPN over Cloud Interconnect** to protect traffic with IPsec in a supported topology.
- Use **MACsec** on supported Cloud Interconnect circuits for link-layer protection.
- Or use TLS/mTLS at the application layer, which is generally recommended even over private networks.

Evaluate support for the specific connection type and region before choosing; regulatory requirements may mandate defense in depth.

### Why are redundant links needed?

For critical workloads:

- Ensure failure domain diversity across locations/edge availability domains.
- Design primary and redundant connections.
- Ensure on-prem routers/ISPs do not share a single point of failure.
- Have HA VPN or backup Interconnect where appropriate.
- Test route priorities and failover behavior.
- Measure throughput, MTU, egress, and actual network quality.

Do not simply buy two VLAN attachments on a single physical connection and treat it as a zero-SPOF architecture.

### Cost sources

- Port or attachment fees.
- Network provider service fees.
- Data transfer/egress by direction and location.
- VPN gateway/tunnel or encryption overlay fees when used.
- Equipment, cross-connects, and operations.
- Operations staff, monitoring, and change management.

Comparing TCO against HA VPN must be based on traffic volume, latency, SLA, and cost per GB, not just port unit price.

## 9. Cross-Cloud Interconnect and Multi-Provider Networking

Cross-Cloud Interconnect is designed for high-bandwidth connectivity between Google Cloud and supported cloud providers, such as AWS, Azure, OCI, and Alibaba Cloud per current documentation.

Example:

~~~text
        AWS VPC / Transit Gateway
                 |
         AWS-side connectivity
                 |
      Cross-Cloud Interconnect
                 |
          Google Cloud VPC
                 |
          Cloud Run / GKE
~~~

Because private connectivity does not mean encryption, plan for TLS/mTLS, MACsec, or another appropriate protection mechanism. Deployment also involves provisioning and coordination with the peer cloud provider; you cannot configure only one side and expect the circuit to work.

### Choosing VPN or Cross-Cloud Interconnect?

- Infrequent API calls, low data volume: authenticated HTTPS over the internet can be simpler and sufficiently secure.
- Moderate traffic requiring private connectivity: HA VPN between both sides may fit.
- Very high, steady traffic needing predictable network performance: consider Cross-Cloud Interconnect or a partner.
- Cross-cloud active-active: must account for data consistency, routing, failover, and egress costs, not just the circuit.

Do not turn every connection between two clouds into a full-mesh VPC; segment networks by application and least privilege.

## 10. Network Connectivity Center (NCC): Hub/Spoke Orchestration

NCC lets you create a **hub** connecting supported **spokes**:

- VPC spokes: connect multiple VPCs and exchange subnet routes per the NCC topology.
- Hybrid spokes: HA VPN tunnels, Cloud Interconnect VLAN attachments, and router appliances.
- Other spoke types such as producer VPCs and NCC Gateway for specialized scenarios.

A hub is a global management resource for multiple spokes; a spoke can have different project/network constraints and backing resource types.

### Value of NCC

- Reduces the number of point-to-point connections to operate.
- Simplifies management of multi-VPC, hybrid routes, and site-to-site topologies.
- Enables connectivity models across multiple network projects.
- Provides route exchange/filtering tools based on spoke type.
- Supports network segmentation with appropriate spoke group/route policy design.

### Misconceptions to avoid

- **NCC does not bypass firewall rules, IAM, or IP overlap.**
- VPC spokes do not advertise all route types like peering/static/dynamic routes in every situation; read export/import rules carefully.
- Hybrid spokes require configured backing resources (VPN tunnels, VLAN attachments, or router appliances).
- Certain site-to-site use cases have specific network/project prerequisites.
- A hub does not mean every service in all VPCs is automatically allowed to access every other service.

Map routes from source to destination, test network paths, and define explicit allowed prefixes/traffic flows.

## 11. How Do Shared VPC, Peering, and NCC Differ?

| Technology | Goal | Boundary |
|---|---|---|
| Shared VPC | Multiple service projects share networks/subnets of a host project | Centralized network ownership |
| VPC Network Peering | Connects two VPCs subject to routing constraints | Peering is not automatically transitive |
| NCC VPC spokes | Connects multiple VPCs via a hub with supported route exchange | Requires hub/spoke and routing configuration |
| HA VPN/Interconnect | Connects a VPC to on-prem or another cloud | Requires peers, routes, firewalls, and DNS |
| Private Service Connect | Accesses services via private endpoints in a producer/consumer model | Not a replacement for general-purpose VPC transit |

Do not build topologies assuming peering A-B and B-C automatically lets A reach C. With hub/spoke, verify which route types are exported/imported and the policies of each component.

## 12. Hybrid DNS: Name Resolution Is Part of Connectivity

A Java request to **erp.corp.example.com** can fail even when the VPN is up if GCP does not know how to resolve internal names. Similarly, on-prem needs a way to resolve service names in Cloud DNS private zones.

Reference model:

~~~text
GCP workload
     |
     v
Cloud DNS private/forwarding zones
     |
     +-- gcp.example.com -> Cloud DNS authoritative
     |
     +-- corp.example.com -> On-prem DNS server
                                   ^
                                   |
           On-prem DNS conditional forwarding
                    -> GCP inbound DNS forwarder
~~~

### Two common components

- **Outbound forwarding zone:** GCP forwards queries for `corp.example.com` to on-prem authoritative DNS.
- **Inbound forwarding policy:** on-prem can query Cloud DNS for configured private zones via the forwarding IP.

### Items to verify

1. Private zones are authorized for the correct VPCs.
2. DNS forwarding targets and UDP/TCP port 53 firewall rules work.
3. On-prem DNS is reachable over VPN/Interconnect.
4. Return paths and special routes for Cloud DNS forwarders are configured properly.
5. TTLs, split-horizon DNS, and negative caching fit the cutover plan.
6. Cloud and on-prem names do not create forwarding loops.
7. DNS query logs are enabled during troubleshooting, noting cost and sensitive data.

Cloud DNS documentation for outbound forwarding to on-prem describes the IP source range **35.199.192.0/19** and requires matching routes/firewalls. Do not apply this range to every DNS type or every application; verify against the exact topology and current documentation.

### Example DNS check from a workload

~~~bash
nslookup erp.corp.example.com
nslookup checkout.gcp.example.com
~~~

When errors occur, distinguish between DNS NXDOMAIN, timeout, route unavailable, and firewall denied. Never hardcode IP addresses in Java source code as a temporary fix.

## 13. Identity and Zero Trust Across Environments

Private connectivity only solves reachability. A service inside a VPC or on-prem still needs to verify identity and access permissions.

### Separating security layers

| Layer | Question | Mechanism |
|---|---|---|
| Network | Which source can connect to the destination? | Firewalls, routes, Cloud VPN/Interconnect, network policies |
| Transport | Is data protected in transit? | TLS/mTLS, IPsec, or MACsec as required |
| Workload authentication | Which service is calling? | Service accounts, OIDC ID tokens, mTLS identities |
| Authorization | What is the caller allowed to do? | IAM, application RBAC/ABAC, resource/tenant policies |
| Data protection | What data is accessed and stored? | Encryption, KMS, classification, DLP |
| Audit | Who changed or accessed what? | Cloud Audit Logs, workload logs, SIEM |

### Service accounts and credentials

- GCP workloads use runtime service accounts and ADC.
- External workloads on-prem or on AWS/Azure can use **Workload Identity Federation** with an appropriate identity provider to obtain short-lived credentials, rather than holding long-lived service account JSON keys.
- Some flows require IAM service account impersonation and associated permissions.
- GKE workloads have their own Workload Identity Federation for GKE mechanism.
- For service-to-service Cloud Run, use Google-signed ID tokens with the proper audience and Invoker role; do not treat VPN as authentication.
- Manage certificate and secret rotation per policy, avoiding credentials in ConfigMaps or source control.

### Distinguishing external WIF from GKE WIF

External Workload Identity Federation allows workloads outside GCP to use their source environment's identity to access Google Cloud APIs. GKE Workload Identity Federation uses Kubernetes identities on GKE to interact with IAM. The two models are related but have different trust configurations and principal formats.

**Never grant `roles/owner` just to test federation.** Create specific principals, audiences, attribute mappings/conditions, and least-privilege roles; test both valid and invalid identity cases.

## 14. Firewalls, Segmentation, and Transport Protection

A network topology may allow a route yet still be blocked by a firewall. In hybrid/multicloud:

- Define network zones: user-facing, app, data, management, DR.
- Open only required ports/protocols for specific sources/destinations.
- Use hierarchical firewall policies where appropriate at the organization level.
- Do not advertise `0.0.0.0/0` over BGP just to fix a connectivity issue.
- Do not open all of RFC 1918 from on-prem to the production VPC.
- Check GCP firewalls, on-prem firewalls, and security groups/NSGs on the peer cloud.
- Use TLS/mTLS for APIs handling sensitive data, even over private links.
- Apply egress policies to reduce data exfiltration risk.
- Define traffic inspection points, IDS/IPS, and logging as appropriate.

**VPC Service Controls** can reduce exfiltration risks through supported Google Cloud APIs within a service perimeter, but it is not a general firewall for all TCP/IP flows. Design perimeters and exceptions clearly.

## 15. Application Platforms: Cloud Run, GKE, and Google Distributed Cloud

### Cloud Run

Fits containerized, stateless Java services or those whose state is externalized to a database/queue. If the application needs to access private on-prem resources, you must configure private network egress and the corresponding VPC path; services do not get datacenter routes by default simply because the project has a VPN.

Pros:

- Reduced cluster operations.
- Autoscaling by requests and concurrency.
- Integration with IAM, Secret Manager, Cloud Logging, and CI/CD.

Constraints:

- Startup/shutdown, CPU allocation, and background work.
- Concurrency and connection pools multiply by the number of instances.
- Latency to on-prem dependencies directly impacts requests.
- For workloads requiring reliable background execution, consider Pub/Sub, Cloud Tasks, or Cloud Run jobs.

### GKE

Fits when you need Kubernetes orchestration, advanced networking, sidecars, service mesh, and lifecycle control. Use VPC-native GKE, Pod/service IP planning, and Workload Identity Federation. Do not assume Pod IPs are always routable from on-prem; verify network policies, masquerading, node routing, and connectivity requirements.

### GKE Multi-Cloud

Google Cloud offers solutions to manage Kubernetes clusters in AWS/Azure environments or attach eligible clusters. Capabilities and management models vary by cluster option; verify the latest service support, regions, APIs, and lifecycle before standardizing.

**Kubernetes provides a relatively consistent API, but storage, load balancing, identity, networking, and control-plane operations still differ across cloud providers.** Do not conclude that containers can move between providers without testing underlying infrastructure dependencies.

### Google Distributed Cloud

Some workloads must run at the edge or facilities with low latency, strict on-site data requirements, or unstable connectivity. Google Distributed Cloud offers options tailored to environments, such as connected or air-gapped, with different management/synchronization models. Choose it only when there is a real edge/data locality requirement and you accept the hardware, lifecycle, connectivity, and support commitments.

## 16. Designing Java/Spring Applications in Hybrid Cloud

Example: `checkout-service` on Cloud Run needs to call an on-prem ERP API.

### Synchronous call architecture

~~~text
Frontend
   |
   v
Spring Boot Checkout on Cloud Run
   |
   | HTTPS + application identity
   v
VPC egress / HA VPN or Interconnect
   |
   v
ERP API on-prem
   |
   v
ERP database
~~~

Proper workflow:

1. The ERP API has a clear contract, TLS, and authentication.
2. Cloud Run has a route to the ERP via VPC egress and the hybrid connection.
3. Cloud DNS resolves the ERP hostname.
4. Firewalls allow only approved sources/workloads.
5. The Java client enforces connect timeouts, read timeouts, and bounded retries.
6. The ERP API supports idempotency keys for operations with side effects.
7. Distributed traces/logs include a correlation ID across both environments.
8. When the ERP fails, Checkout responds according to business rules rather than waiting indefinitely.

### Example Spring RestClient configuring timeouts

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class ErpClientConfig {

    @Bean
    RestClient erpRestClient() {
        var httpClient = java.net.http.HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        var requestFactory = new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(Duration.ofSeconds(5));

        return RestClient.builder()
            .baseUrl("https://erp.corp.example.com")
            .requestFactory(requestFactory)
            .build();
    }
}
~~~

This snippet illustrates timeouts for Java/Spring Boot versions supporting `RestClient`; it does not yet include mutual TLS, auth, retries, error mapping, or per-environment endpoint configuration. In production, read the base URL from validated `@ConfigurationProperties` and use an approved secret/certificate manager without hardcoding credentials.

### Why do timeouts matter?

If a Checkout request has a 3-second deadline while the ERP read timeout is 30 seconds, the request thread can breach its SLO, hold connections open, and build up queues. Set overall deadlines, retry budgets, and bulkhead/concurrency limits matched to actual cross-network latency.

### When to switch to asynchronous?

If the ERP only needs to learn about a new order within a few seconds, use Pub/Sub or a task queue to remove direct coupling. On-prem can run a connector/worker with its own access path, authentication, and retries. Design idempotency, dead-letter queues, and monitoring because messages may be redelivered.

## 17. Cross-Environment Data: Choosing the Right Flow

Data is often the hardest part of operating hybrid/multicloud:

| Need | Pattern to consider | Risk |
|---|---|---|
| One-time database migration | Export/import, appropriate database migration tool | Downtime, version incompatibility |
| Continuous database sync | CDC/replication per engine capabilities | Lag, ordering, schema drift |
| Periodic file transfer | Storage Transfer Service or supported pipeline | Egress, checksums, ACLs, retention |
| Event streaming | Pub/Sub, Kafka/connector, Dataflow | At-least-once delivery, duplicates |
| Cross-cloud analytics data | Batch export/ELT or supported query solution | Cost, latency, governance |
| DR replication | Database/storage replication per RPO | Split-brain, failover, and failback |

### Ownership and system of record

Establish which system is the **source of truth** for each dataset. Never let both an on-prem database and Cloud SQL accept independent writes without a conflict-resolution protocol.

Principles:

- Define the schema owner and versioning approach.
- Maintain data classification, retention, encryption, and key ownership.
- Measure replication lag and checkpoints.
- Verify consistency using checksums, counts, or reconciliation queries.
- Define RPO on failover and criteria for failback.
- Avoid copying all raw sensitive data across multiple clouds if the use case only needs aggregates.
- Account for egress, storage, transfer, and operational costs for continuous sync.

### When should data stay close to compute?

If an API requires many synchronous round trips to a database over VPN, latency grows rapidly. Options:

- Move compute closer to the data.
- Migrate the database together with its application group.
- Use read replicas/caches with an explicit consistency policy.
- Shift critical paths to event-driven flows when business semantics allow.
- Separate analytics from the transaction path.

Do not adopt simple caching when the system requires strong consistency for financial or inventory data without invalidation/reconciliation mechanisms.

## 18. Reliability and Disaster Recovery

Hybrid/multicloud adds dependency links and failure modes. A single broken link can impact multiple services even when all VMs/pods are healthy.

### Availability models

| Model | Idea | Complexity |
|---|---|---|
| Active-passive | One site serves traffic while the other stands ready | Moderate, requires failover plan |
| Active-active | Both environments serve simultaneously | High, requires global routing/data consistency |
| Split-by-domain | Each environment handles a distinct business domain | Lower than active-active, depends on integration |
| Edge autonomy | Edge processes offline, syncs upon reconnection | High for conflict/reconciliation |

### RTO and RPO

- **RTO**: maximum acceptable time to restore functionality after an incident.
- **RPO**: maximum acceptable data loss, typically measured as a time interval.

For example, an on-prem ERP has a 30-minute RTO and 5-minute RPO. Having redundant HA VPN alone does not prove you meet this RTO/RPO: you must also account for database replication, application warm-up, DNS failover, credentials, network routes, and business validation.

### Active-active is not simple

If orders are received simultaneously in GCP and AWS and both write to separate data stores, you need rules for:

- Ownership partitioning by tenant/order or a single-writer model.
- Conflict resolution and ordering.
- Idempotency and replay.
- When a commit is considered successful.
- Recovery after a network partition.
- Managing global IDs, clocks, and timestamps.

If data semantics are not yet solved, active-passive or domain split is usually safer.

### Failover drills

You must test:

1. One VPN tunnel down.
2. BGP neighbor down or lost prefix.
3. On-prem DNS server unresponsive.
4. Loss of a region/zone.
5. Another provider degraded or throttling APIs.
6. Increasing replication lag.
7. Expired credentials or revoked service account.
8. Traffic shifted over and shifted back (failback).

Measure time-to-detect, time-to-failover, time-to-recover, and affected data. Do not just check ping or gateway UP status.

## 19. Observability Across GCP, On-Prem, and Other Clouds

A single request may traverse Cloud Run, VPN, ERP, and an AWS payment API. When errors happen, no single dashboard automatically explains the entire path.

### Critical signals

| Layer | Metrics/logs | Tools/sources |
|---|---|---|
| VPC/network | Throughput, drops, firewall denied, flow logs | Cloud Monitoring, VPC Flow Logs |
| VPN/Interconnect | Tunnel state, BGP sessions, link utilization, errors | Cloud VPN/Interconnect monitoring |
| DNS | Query latency, NXDOMAIN, forwarding failures | Cloud DNS logs and on-prem DNS |
| Applications | Request rate, 5xx, p95/p99, queue depth | Cloud Monitoring/Logging, OpenTelemetry |
| IAM/security | Permission denied, policy changes, token failures | Cloud Audit Logs and SIEM |
| Data pipeline | Replication lag, checksum mismatches, retries | Database/transfer tooling |
| Billing | Egress by region/provider, interconnect/VPN, storage | Cloud Billing/BigQuery export |

### Using trace correlation

Java/Spring can use OpenTelemetry trace/span IDs. For downstream ERP calls, propagate trace context via HTTP headers when both sides support it; never include bearer tokens in telemetry. If the other system uses a different trace format, a gateway or explicit logging correlation may be needed.

### 503 investigation scenario

1. Check service 503 rate and when it started.
2. Correlate with change logs/deploys and IAM changes.
3. Verify DNS resolution to the ERP.
4. Check firewall/routing/BGP/tunnel health.
5. Measure latency, packet loss, and MTU.
6. Check ERP availability and connection limits.
7. If a link failed, trigger failover or degraded mode per the runbook.
8. Verify business requests completed or retried properly after recovery.

## 20. IaC, Governance, and Multi-Environment Operations

### Infrastructure as Code

Terraform can manage VPCs, Cloud Router, VPN, firewalls, IAM, and other GCP resources. For multicloud, multiple provider plugins can be used, but you must enforce:

- Separate state and permissions aligned with ownership boundaries.
- Never give a single pipeline admin permissions across all clouds unless strictly necessary.
- Version pinning and reviews for routing/permission changes.
- Tested production change plans and rollbacks.
- Never store state or credentials publicly.
- Separate the network platform layer from the application layer appropriately.

### Network changes have a large blast radius

A misconfigured route advertisement or firewall policy can cut off the entire ERP connection. Therefore:

- Require peer review by network owners on both sides.
- Schedule maintenance windows for significant changes.
- Maintain out-of-band management accounts/paths in case connectivity is lost.
- Back up BGP/router configurations and route sets before changes.
- Have a rollback plan and verification criteria.
- Establish a communication channel and incident commander during critical system changes.

### Multi-provider governance

Use shared policy-as-code, inventory, organization-level constraints, and approval workflows. However, **do not assume a policy written on GCP automatically applies on AWS/Azure**. Map control objectives to each native IAM/network/data service and verify effectiveness separately.

### Ownership model

| Component | Owner |
|---|---|
| Enterprise IPAM, BGP policies | Network team |
| VPC/Shared VPC/NCC | Cloud platform |
| Cloud VPN/Interconnect | Network + provider/carrier |
| Service account federation | Security/IAM |
| Java API contract, timeouts | Application team |
| Database replication and schema | Data/DBA |
| Business cutover and RTO/RPO | Product/business owner |
| Monitoring, incident response | SRE/Operations |
| Billing, egress cost | FinOps |

A cross-cloud circuit typically requires coordination across at least two teams/platforms. Document clearly who handles incidents at each end of the link.

## 21. FinOps for Hybrid and Multicloud

A hybrid system can incur costs across multiple places simultaneously:

- VM/Cloud Run/GKE usage in GCP.
- VPN tunnels, Interconnect ports/attachments, and partner circuits.
- Data egress from GCP, the other provider, and ISPs.
- Cloud Storage/BigQuery, snapshots, and replication.
- Database licenses, on-prem staffing, colocation, and hardware.
- Duplicated monitoring/SIEM/observability tooling.
- Inter-region or cross-cloud traffic.
- Redundant architecture and failover drill costs.

### Costing principles

Do not just add up VM prices across two clouds. Build a **cost per successful transaction** or **cost per GB processed** model that accounts for latency and recovery capability.

Illustrative example:

| Item | Monthly cost |
|---|---:|
| GCP app compute | 1,200 USD |
| On-prem ERP operation allocation | 700 USD |
| Network links and VPN/Interconnect | 450 USD |
| Cross-cloud egress | 300 USD |
| Monitoring, logs, and transfer | 150 USD |
| Illustrative total | 2,800 USD |

These figures are illustrative, not GCP pricing. Actual costs depend on SKUs, regions, traffic, discounts, partners, and commitments.

### Cost optimization strategies

- Place compute near data when egress/latency is a primary factor.
- Reduce synchronous API round trips across multiple clouds.
- Use batch/async processing for data that does not require real-time delivery.
- Compress/filter data before transfer where appropriate.
- Do not transfer raw sensitive data if only aggregates are needed.
- Track owner/cost center labels and actual egress.
- Compare Interconnect vs. VPN based on actual throughput/SLA.
- Do not maintain DR/standby resources without reviewing RTO/RPO and utilization.

## 22. Step-by-Step Hybrid Cloud Implementation Roadmap

A migration from on-prem to GCP should typically follow structured waves:

| Wave | Work items | Exit criteria |
|---|---|---|
| 0 – Assessment | Inventory, IPAM, dependency map, SLA, ownership | No major connectivity blockers remaining |
| 1 – Landing zone | Organization/projects/VPC/IAM/logging/policy | Guardrails operational |
| 2 – Connectivity pilot | HA VPN/BGP, DNS, firewall, test apps | Reachability, failover, and security tests pass |
| 3 – Application pilot | Java/Spring container running on GCP, calling on-prem ERP | SLO, auth, and rollback validated |
| 4 – Data migration/sync | CDC, transfer, or coexistence | Consistency and RPO within thresholds |
| 5 – Production cutover | Load balancing/DNS/traffic shift | Business transactions and telemetry meet targets |
| 6 – Optimization | Rightsizing, data placement, decommission | Realized savings, legacy dependencies retired |

### When to choose Interconnect over VPN?

Start with requirements: bandwidth, latency, security, SLA, locations, and traffic forecast. VPN works well for fast pilots, but is not always the long-term choice for heavy data movement. Interconnect requires provisioning lead time and carrier/colocation coordination; plan early ahead of cutover.

### Rollback in hybrid differs from code rollback

Rolling back an application version can be straightforward, whereas switching database writers or reversing large routing/DNS changes is harder. Define rollback points, data reconciliation, and cutback/failback decisions before running the migration.

## 23. Lab 1: Connecting a Java API on GCP to an On-Prem ERP

**Scenario:** `checkout-service` is containerized on Cloud Run. The ERP database remains in the data center, accessed through an ERP HTTPS API. Requirements:

- Do not assign a public IP to the ERP.
- Checkout accesses the ERP only over private hybrid connectivity.
- The ERP enforces TLS and service-to-service authentication.
- The network path must survive one tunnel failure.
- p95 latency to the ERP must stay below the threshold approved by the application owner.
- Fallbacks and runbooks exist when the ERP is unavailable.

### Step A – Design the topology

~~~text
Cloud Run Checkout
     |
 Direct VPC egress / supported connector
     |
 Shared VPC prod
     |
 HA VPN + Cloud Router/BGP
    / \
 Tunnel A  Tunnel B
    \ /
 On-prem VPN gateways
     |
 ERP API over HTTPS
~~~

### Step B – Inspect existing resources

Read-only commands (replace placeholders and verify the right project):

~~~bash
gcloud compute networks list --project=PROJECT_ID

gcloud compute networks subnets list --project=PROJECT_ID

gcloud compute routers list --project=PROJECT_ID

gcloud compute vpn-gateways list --project=PROJECT_ID

gcloud compute vpn-tunnels list --project=PROJECT_ID
~~~

To check the status of a Cloud Router/BGP session:

~~~bash
gcloud compute routers get-status ROUTER_NAME \
  --project=PROJECT_ID \
  --region=REGION
~~~

Requires permissions to view network resources. These commands do not create VPNs or alter routes; learners must work with the network owner to confirm the approved topology.

### Step C – DNS and authentication

- Create a forwarding zone for `corp.example.com` on the appropriate network.
- Verify DNS resolution from the GCP workload to `erp.corp.example.com`.
- Configure TLS, CA trust, mTLS, or token identity per the ERP system.
- Do not put credentials in `application.yml` in Git.
- Use Secret Manager or an appropriate workload identity mechanism.

### Step D – Testing

| Test | Expected result |
|---|---|
| DNS query to ERP | Resolves to the correct internal IP |
| TCP/TLS handshake | Succeeds when auth/trust is valid |
| Call with valid identity | Succeeds within latency budget |
| Call with invalid identity | Rejected |
| Disable tunnel A | Tunnel B continues routing if topology is correct |
| On-prem DNS down | Alert/runbook triggers, does not hang indefinitely |
| ERP returns 503 | Checkout applies retry budget/degraded mode |
| Deploy new revision | Egress/IAM configuration is preserved |

### Step E – Handoff

Documentation must include source/destination diagrams, route prefixes, DNS policies, SLOs, on-call contacts for both sides, rollback procedures, and dashboard links. Do not end a pilot just because ping works.

## 24. Lab 2: Integrating an API on AWS with GCP

**Scenario:** An Orders API on GCP needs to call a partner's Risk Scoring API hosted on AWS. Volume is a few thousand requests per day; payloads are small and encrypted.

### Choosing connectivity

The architecture team compares:

| Option | Pros | Trade-off |
|---|---|---|
| HTTPS public endpoint with OIDC/mTLS and appropriate allowlists | Fast, minimal network components | Depends on internet/public endpoint controls |
| Cross-cloud HA VPN | Private IPsec connectivity, dynamic routing | Peer/BGP design, throughput, and operations |
| Cross-Cloud Interconnect | Network performance for high traffic | Higher provisioning effort and fixed cost |

If traffic is small, private networking is not strictly mandated, and the API has strong authentication, HTTPS is usually simpler. Do not design Cross-Cloud Interconnect solely because two clouds are involved.

### Required tests

- Identity and authorization do not rely solely on source IP.
- TLS certificate validation and rotation.
- Audience, token expiry, and replay protections if using OIDC.
- Risk Scoring API SLA and retry semantics.
- Orders API timeouts when the AWS endpoint is slow.
- Classification of data allowed to leave for another provider.
- Corresponding cost/egress and observability.
- Fail-closed/fail-open behavior per business policy, never accidental defaults.

If traffic grows significantly later, re-evaluate VPN or Interconnect using actual data.

## 25. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Two environments use overlapping CIDRs | Ambiguous routes, cannot connect | Perform IPAM before creating networks |
| Using a single VPN tunnel for critical production | Single point of failure | HA VPN/BGP with a qualifying SLA topology |
| Thinking Cloud Router is the traffic router | Misunderstood data path and metrics | Separate control plane from VPC forwarding |
| Assuming Interconnect encrypts by default | Data exposure on transport | TLS/mTLS, MACsec, or HA VPN over Interconnect |
| Assuming VPN up means the app works | DNS, firewalls, or auth may still fail | Test end-to-end along business flows |
| Assuming NCC connects every network automatically | Routes/policies are not automatically right | Verify hub/spokes, exports/imports, and filters |
| Using VPC Peering as automatic transit | A does not automatically route through B to C | Choose NCC/Router appliance topologies as appropriate |
| Putting the same service account across all clouds | Credential exposure and overly broad access | Federation, least privilege, and rotation |
| Making too many cross-cloud database round trips | High p99 latency/egress | Co-locate, cache with policy, or go async |
| Active-active without conflict resolution | Split-brain, inconsistent data | Single-writer/partitioning/reconciliation |
| Lacking a hybrid DNS strategy | Name resolution failures | Tested forwarding zones/inbound policies |
| Letting Dev route across the entire prod network | Expanded blast radius | Network segmentation, IAM, and policies |
| Ignoring egress/provider costs | Inaccurate TCO estimates | Billing analytics by direction and source |
| Not testing BGP/DNS failover | Outage when a single link fails | Chaos/failover drills and runbooks |
| Choosing multicloud for lock-in slogans | Team suffers extra cost/complexity | Decide based on business case and SLOs |

## 26. Production Design Checklist

### Needs and architecture

- [ ] Clear business justification for hybrid/multicloud.
- [ ] RTO, RPO, SLOs, and latency budgets defined.
- [ ] Inventory of applications, data, dependencies, and owners completed.
- [ ] Active-passive, domain split, or active-active chosen with justification.
- [ ] Not assuming workloads must run on every cloud.

### Networking and DNS

- [ ] IP ranges do not overlap across networks that need to communicate.
- [ ] VPC/Shared VPC/subnets/secondary ranges reviewed.
- [ ] HA VPN or Interconnect chosen based on throughput, SLA, and cost.
- [ ] True redundancy across routers/links/zones and route failover verified.
- [ ] BGP advertisements/route imports/exports have explicit policies.
- [ ] NCC hub/spokes do not create unintended connectivity.
- [ ] Cloud DNS forwarding, split-horizon, and TTLs verified.
- [ ] Network ingress/egress and firewalls verified in both directions.
- [ ] TLS/IPsec/MACsec applied according to data sensitivity and compliance.

### Identity, applications, and data

- [ ] Each workload has its own identity and least-privilege IAM.
- [ ] External WIF or GKE WIF configured properly for each use case.
- [ ] No static service account keys stored in source code or images.
- [ ] API authorization enforced at service boundaries.
- [ ] Java clients enforce deadlines, retry budgets, bulkheads, and telemetry.
- [ ] Asynchronous flows have idempotency and dead-letter handling.
- [ ] Data owners, source of truth, and consistency models are clear.
- [ ] CDC/replication has lag monitoring, checksums, and rollback plans.
- [ ] Secrets, encryption, access audits, and data residency meet requirements.

### Operations and finance

- [ ] IaC and policy reviews apply to network/IAM changes.
- [ ] Dashboards exist for network, DNS, app, data, and billing.
- [ ] Cross-provider on-call, escalation, and runbooks are in place.
- [ ] Tunnel failover, DNS outage, and provider disruption drills completed.
- [ ] Change management covers migration/cutover/failback.
- [ ] Network egress, interconnect, replication, and logging costs tracked.
- [ ] Budgets, owners, and cost allocation defined across teams/platforms.
- [ ] End-to-end tests prove business transactions succeed.

## Conclusion

Hybrid cloud and multicloud with Google Cloud is a multi-layered integration challenge: **VPC and routing**, **Cloud VPN/Interconnect**, **DNS**, **workload identity**, **access control**, **data movement**, **reliability**, and **operations**. HA VPN suits flexible IPsec connectivity; Dedicated/Partner/Cross-Cloud Interconnect fit different networking needs; Cloud Router handles BGP; and NCC helps organize hub/spoke topologies. However, a working network path does not guarantee secure applications or consistent data. Good design starts from business goals and failure modes, picks just-enough connectivity, validates end-to-end, maintains clear ownership, and tracks both SLOs and costs across environments.

## References

- [Google Cloud: Network Connectivity overview](https://docs.cloud.google.com/network-connectivity/docs/concepts)
- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices)
- [Cloud Router overview](https://docs.cloud.google.com/network-connectivity/docs/router/concepts/overview)
- [Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [Dedicated Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/dedicated-overview)
- [Partner Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/partner-overview)
- [Cross-Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview)
- [Network Connectivity Center overview](https://docs.cloud.google.com/network-connectivity/docs/network-connectivity-center/concepts/overview)
- [NCC VPC spokes](https://docs.cloud.google.com/network-connectivity/docs/network-connectivity-center/concepts/vpc-spokes-overview)
- [Cloud DNS hybrid best practices](https://docs.cloud.google.com/dns/docs/best-practices)
- [Shared VPC overview](https://docs.cloud.google.com/vpc/docs/shared-vpc)
- [VPC Network Peering overview](https://docs.cloud.google.com/vpc/docs/vpc-peering)
- [Private Service Connect documentation](https://docs.cloud.google.com/vpc/docs/private-service-connect)
- [Google Cloud IAM Workload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation)
- [GKE Multi-Cloud overview](https://docs.cloud.google.com/kubernetes-engine/multi-cloud/docs)
- [Google Distributed Cloud overview](https://docs.cloud.google.com/distributed-cloud/docs/overview)
- [Cloud Run: Private networking](https://docs.cloud.google.com/run/docs/securing/private-networking)
- [Cloud Billing cost management](https://docs.cloud.google.com/billing/docs/how-to/cost-management)
