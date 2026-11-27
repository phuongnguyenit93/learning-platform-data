# Practical Design: Integrating On-Premises With GCP Services

An enterprise rarely migrates its entire estate from a data center to Google Cloud in a single move. Even after deploying Java APIs to Cloud Run or GKE, the business may still retain its ERP, Active Directory, legacy databases, and batch jobs on-premises. If the cloud application cannot reach the ERP, DNS resolves incorrectly, or network ranges overlap, a "successful deployment" does not mean the system works.

**Hybrid cloud integration** designs how on-premises systems and Google Cloud exchange data, authenticate, call APIs, and operate in a controlled manner. The design must address **networking, routing, DNS, identity, data, observability, security, resilience, and cost** simultaneously. The goal is not merely opening connectivity, but proving it works accurately and recovers when a component fails.

This lesson belongs to the **Hybrid and Multicloud Infrastructure** chapter in the **CLOUD_PROVIDERS_GCP** module. The module introduces Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment scenarios, learners select services, secure resources, automate releases, and track reliability and cost. Here we apply that knowledge to an evaluable, testable on-premises–to–GCP design.

## Learning Objectives

After this lesson, learners can:

- Catalog integration flows, owners, protocols, traffic volumes, and reliability targets.
- Distinguish HA VPN, Cloud Interconnect, Cloud Router, VPC, Private Service Connect, and private services access.
- Design CIDRs, routing/BGP, bidirectional DNS, and firewalls for a hybrid system.
- Choose appropriate access methods from on-premises to Cloud Run/GKE, Cloud SQL, and Google APIs.
- Separate network security from IAM, database permissions, and application authentication.
- Build a reference architecture with a routing matrix, port matrix, and failure-domain diagram.
- Execute a step-by-step lab using `gcloud` commands and tests from both sides.
- Verify connectivity, latency, name resolution, failover, security, and a cost baseline.
- Produce cutover/rollback runbooks and handoff checklists for network, DBA, SRE, and application teams.

## 1. Problem Statement: An Order System Operating Across Two Environments

Suppose an enterprise runs the following components:

| Component | Current location | Function |
|---|---|---|
| ERP and master customer data | On-premises | Accounting workflows and customer synchronization |
| Active Directory/LDAP | On-premises | User identities and legacy systems |
| Java Spring Boot API | Planned migration to Google Cloud | Order intake and processing |
| Cloud SQL for PostgreSQL | Google Cloud | New order data |
| Cloud Storage | Google Cloud | Attachments, reconciliation, and exports |
| Pub/Sub | Google Cloud | Asynchronous events for workers |
| Cloud Logging/Monitoring | Google Cloud | Logs, metrics, alerts, and investigation |

Sample requirements:

1. The on-prem ERP calls an internal Orders API endpoint over HTTPS without exposing it to the public internet.
2. The Orders API on GCP calls an internal on-prem API over a controlled connection.
3. GCP workers access the database and Cloud Storage.
4. An on-prem Java batch job can access an approved GCP service with appropriate IAM.
5. Connectivity must include redundancy, observability, and incident troubleshooting procedures.
6. The enterprise wants to migrate in waves while maintaining hybrid connectivity during the transition period.

**Important caveat:** the table below contains illustrative training data, not real system details. Actual regions and addresses must be approved by IPAM, Network, and Security teams.

### Example acceptance targets

| Item | Design target | Verification method |
|---|---|---|
| API from ERP to GCP | HTTPS over private connectivity | DNS, routes, TLS, and API requests |
| API from GCP to ERP | Only approved hosts/ports | Network path, firewalls, and app logs |
| WAN availability | Maintain communication when one tunnel fails | Controlled failover rehearsal |
| Latency | p95 stays within threshold set by app owner | Load tests and tracing |
| Data access | Proper IAM, DB roles, and data policies | Negative/positive authorization tests |
| Recoverability | Runbooks and rollback in place | Approved drills |
| FinOps | Identified SKUs and cost owners | Billing exports and traffic measurements |

Never quote "99.99% uptime" as an end-to-end guarantee; that may be a **conditional** SLA solely for a qualifying HA VPN configuration, excluding the ERP, DNS, applications, and partners.

## 2. Proposed Reference Architecture

Choose a model where the network team manages a Shared VPC, while a separate project hosts applications and GCP service resources. In a small lab you may use a single project, yet you should still separate network admin permissions from workload permissions.

~~~mermaid
flowchart LR
  subgraph DC["On-premises / Data center"]
    ERP[ERP / Java batch]
    DNSDC[Corporate DNS]
    FW[Firewall + VPN peer A/B]
    LDAP[IdP / AD]
    ERP --> FW
    DNSDC --> FW
    LDAP --> FW
  end
  subgraph GCP["Google Cloud / Hybrid VPC"]
    HA[HA VPN: two interfaces and tunnels]
    CR[Cloud Router / BGP]
    DNSG[Cloud DNS private zones and forwarding]
    ILB[Regional internal Application Load Balancer]
    API[Orders API: Cloud Run / GKE]
    SQL[(Cloud SQL private IP)]
    GCS[Cloud Storage via Google APIs]
    OBS[Cloud Logging + Monitoring + Trace]
    HA --- CR
    HA --> ILB --> API
    HA --> DNSG
    API --> SQL
    API --> GCS
    API --> OBS
  end
  FW <--> HA
  ERP -. HTTPS private .-> ILB
  API -. HTTPS hybrid .-> FW
~~~

This diagram shows the **logical data plane** and control plane. Cloud Router manages BGP/routes; it **does not forward individual packets like a router appliance**. Actual packets traverse Cloud VPN/VPC and corresponding network infrastructure.

In another Cloud Run scenario, on-premises sources connecting into a VPC via Cloud VPN/Interconnect may qualify as internal under certain ingress settings; however, placing a **regional internal Application Load Balancer** with a serverless NEG backend typically provides a clean private VIP, internal DNS, and clear access boundary. Cross-check exact load balancer types and current Cloud Run documentation.

### Distinguishing three primary flows

1. **On-prem → GCP private workload:** ERP calls `orders.gcp.corp.example` pointing to the internal load balancer's private VIP.
2. **GCP workload → on-prem service:** the API calls `erp.corp.example` via BGP routes, firewalls, and DNS forwarding.
3. **On-prem → Google APIs:** Java batch calls Cloud Storage/Secret Manager using supported endpoints via **Private Google Access for on-premises hosts** or an approved alternative; this is **not** routed to the internal load balancer's private VIP.

Cloud SQL private IP is a fourth path with its own connection mechanics to understand; do not lump Cloud SQL under "Google API endpoints" when designing TCP 5432 access.

## 3. Building an Application Flow Table Before Configuring the VPC

Catalog directional dependencies matching real application behavior. Example:

| Source | Destination | Protocol/port | Purpose | Criticality | Owner |
|---|---|---|---|---|---|
| On-prem ERP | Orders API internal VIP | HTTPS 443 | Submit orders | Critical | ERP team |
| Orders API | On-prem ERP | HTTPS 8443 | Validation / code lookup | Critical | Integration team |
| Orders API | Cloud SQL | PostgreSQL 5432 | Read/write orders | Critical | DBA |
| GCP Worker | Cloud Storage | HTTPS 443 | Store export files | High | Data team |
| On-prem batch | Cloud Storage API | HTTPS 443 | Scheduled file uploads | Medium | ETL team |
| GCP workload | Corporate DNS | UDP/TCP 53 via forwarding | Resolve legacy names | High | Network |
| On-prem hosts | Cloud DNS inbound IP | UDP/TCP 53 | Resolve private GCP FQDNs | High | Network |
| App / infra | Cloud Monitoring | HTTPS 443 | Telemetry | High | SRE |

This table is **not the final firewall ruleset**. Add source CIDRs, destination IPs, identities, TLS modes, peak throughput, retries, maintenance windows, and evidence.

### Dependency discovery rules

- Inspect configs, DNS, firewall records, VPC Flow Logs, and APM/traces.
- Confirm with application owners, DBAs, Network, and Security.
- Capture nightly, month-end, or failover-only jobs.
- Distinguish "observed" from "confirmed by system owner."
- Never delete a dependency simply because no network flow appeared over a few days.

If integration requires many synchronous reads/writes over the WAN, evaluate **batching, caching, event-driven integration, or co-locating the database with the application** before buying more bandwidth.

## 4. IP Plan and DNS Namespaces

### Illustrative CIDR plan

| Zone | CIDR / IP | Role |
|---|---|---|
| On-prem user/app network | `10.60.0.0/16` | ERP, Java batch, internal hosts |
| On-prem DNS | `10.60.1.53` | Authoritative/recursive DNS |
| Google Cloud VPC | `hybrid-vpc` | Primary application network |
| App subnet on GCP | `10.80.10.0/24` | Test VMs and internal LB frontend |
| GKE Pod secondary range (if used) | `10.81.0.0/16` | Alias IPs for GKE workloads |
| GKE Services secondary range (if used) | `10.82.0.0/20` | Kubernetes Service IPs |
| Cloud SQL PSA allocation (example) | `10.90.0.0/16` | Range reserved for service producer |
| Internal API VIP (example) | `10.80.10.50` | Internal LB frontend |
| On-prem ASN | `65010` | Enterprise-managed BGP peer |
| Cloud Router ASN | `64514` | Google Cloud BGP peer |

These ranges are **standalone learning examples**. In real deployments:

1. Verify zero overlap with on-premises, AWS/Azure, VPCs, GKE secondary ranges, peered networks, or DR sites.
2. Reserve sufficient addresses for GKE, new subnets, service networking, and growth.
3. Choose a Cloud Router ASN that does not conflict with existing BGP designs.
4. Confirm reserved/advertised prefixes across all VPN/Interconnect links.
5. Never assume a GCP VPC has a single contiguous CIDR: VPCs are global, subnets are regional, and subnets/secondary ranges are explicitly assigned.
6. Where overlaps exist, prefer fixing IPAM or designing a suitable intermediate layer rather than relying on NAT to mask every routing/DNS issue.

### DNS namespaces

Proposed authority split:

- `corp.example`: on-premises DNS servers remain authoritative for ERP and legacy services.
- `gcp.corp.example`: Cloud DNS private zone manages endpoints/service identities inside the VPC.
- `orders.gcp.corp.example`: A record pointing to the internal load balancer's private VIP.
- `erp.corp.example`: A/CNAME record on on-prem DNS.
- `*.googleapis.com`: resolved using Google API private VIPs when needed, never mixed into internal domains.

The `.example` suffix is illustrative; in production, use zones under real organizational DNS control.

## 5. Choosing Connectivity: HA VPN or Cloud Interconnect?

| Criterion | HA VPN | Dedicated / Partner Interconnect |
|---|---|---|
| Transport network | IPsec tunnels over the internet | Dedicated physical or partner-provider circuit |
| Availability | Requires redundant topology matching SLA | Requires device/attachment/location redundancy per design |
| Provisioning | Generally faster if peer already exists | Requires cross-connect or partner coordination |
| Scalability | Bounded by tunnels, peers, packet sizes, and overhead | Suits high, steady bandwidth |
| Security in transit | Built-in IPsec | Not end-to-end encrypted by default; evaluate HA VPN over Interconnect if needed |
| Routing | Dynamic BGP with Cloud Router | Dynamic BGP with Cloud Router |
| Cost | Tunnel-hours, data transfer, and related charges | Ports/VLAN attachments/provider/data transfer |
| Use case | Pilots, DR, moderate traffic, rapid deployment | Long-term hybrid, large data volumes |

**HA VPN** is recommended when high-availability IPsec connectivity is required. Dual interfaces/tunnels, peer redundancy, and BGP configurations must follow supported topologies to qualify for the corresponding SLA; a single tunnel does not automatically deliver 99.99%.

**Cloud Interconnect** is worthwhile when steadier bandwidth or latency is required, yet still demands HA and transport security design. Never treat "private circuit" as synonymous with "automatically encrypted."

### How to decide

- **Pilot with 1–2 apps:** typically start with HA VPN if the peer and bandwidth fit.
- **Multi-TB/day replication:** factor in transfer duration, throughput, and Interconnect costs.
- **Tight API-to-DB latency:** measure first; if WAN RTT breaks the SLO, revisit application/data boundaries first.
- **Multicloud:** evaluate Cross-Cloud Interconnect, Network Connectivity Center, and matching routing designs rather than assuming peering/VPN transits every cloud automatically.

Never pick solely on tunnel hourly price. Compare **cost + SLOs + bandwidth + HA + operations + security requirements**.

## 6. HA VPN, Cloud Router, and BGP: Design Before Typing Commands

In this scenario, Google Cloud runs an HA VPN gateway with **two interfaces**. On-premises must also provide redundant peer devices/interfaces. Each tunnel pairs with a matching Cloud Router interface and BGP peer.

~~~mermaid
flowchart LR
  subgraph DC["On-prem"]
    P0[Peer A / interface A]
    P1[Peer B / interface B]
  end
  subgraph GCP["Google Cloud"]
    I0[HA VPN interface 0]
    I1[HA VPN interface 1]
    R[Cloud Router: BGP route control]
    V[VPC 10.80.10.0/24]
  end
  P0 <--> |IPsec tunnel 0| I0
  P1 <--> |IPsec tunnel 1| I1
  I0 --- R
  I1 --- R
  I0 --> V
  I1 --> V
~~~

### BGP design

- Google Cloud uses ASN `64514`; on-premises uses ASN `65010`.
- Both tunnels use distinct BGP link-local `/30` subnets—e.g., `169.254.21.0/30` and `169.254.22.0/30`—if permitted and unused.
- Cloud Router can learn `10.60.0.0/16` from on-premises.
- On-premises receives authorized GCP advertised prefixes, e.g., `10.80.10.0/24`.
- Cloud SQL PSA, Cloud DNS forwarding, or Google API VIP ranges require **explicit custom advertisements** when needed; never assume BGP knows them automatically.
- For active-active or active-passive designs, align BGP priorities/MEDs and peer settings with the chosen topology.

Cloud Router manages BGP sessions and learned/advertised routes; **it has no packet-forwarding appliance of its own**. Even when BGP shows `ESTABLISHED`, verify bidirectional traffic, DNS, firewalls, and application TLS.

### Global vs. regional routing

Cloud Router is regional; a VPC can use regional or global dynamic routing mode. If workloads span multiple regions while on-premises connects through tunnels in one region, design dynamic route advertisement/learning, failover, and latency matching that topology. Global routing does not magically create HA or make every path equally optimal.

## 7. Practicing Foundational Infrastructure With gcloud

**The commands below are instructional guides; never run them in production without approval.** Replace `PROJECT_ID`, region, and CIDRs per IPAM, and verify org policies, billing, and IAM. Real on-premises connectivity also requires configuring peer VPN devices, tunnels, and BGP peers; this example **does not complete a working VPN by itself**.

### Step 1: Select project and enable APIs

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com dns.googleapis.com
~~~

Execution requires appropriate roles such as Compute Network Admin and Cloud DNS management permissions. Never use Owner in production just to move faster.

### Step 2: Create custom VPC and subnet

~~~bash
gcloud compute networks create hybrid-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=GLOBAL \
  --project=PROJECT_ID

gcloud compute networks subnets create hybrid-apps-sea1 \
  --network=hybrid-vpc \
  --region=asia-southeast1 \
  --range=10.80.10.0/24 \
  --project=PROJECT_ID
~~~

In this example, global dynamic routing prepares for multi-region expansion. If the system only needs regional routing and tighter route-propagation control, consider regional mode per approved design.

These commands do not yet create GKE secondary ranges or a proxy-only subnet. For VPC-native GKE or an internal Application Load Balancer, provision those dedicated subnets/ranges according to the selected architecture.

### Step 3: Create Cloud Router and HA VPN gateway

~~~bash
gcloud compute routers create hybrid-router-sea1 \
  --network=hybrid-vpc \
  --region=asia-southeast1 \
  --asn=64514 \
  --project=PROJECT_ID

gcloud compute vpn-gateways create hybrid-ha-vpn \
  --network=hybrid-vpc \
  --region=asia-southeast1 \
  --stack-type=IPV4_ONLY \
  --project=PROJECT_ID
~~~

The HA VPN gateway allocates two appropriate external interface IPs. **These are not active tunnels yet.** Next, the Network team must:

1. Create an external VPN gateway resource representing the on-premises peers.
2. Pair two peer interfaces/devices with the two Google HA VPN interfaces.
3. Create two IPsec tunnels using securely managed shared secrets.
4. Create a Cloud Router interface and BGP peer for each tunnel.
5. Configure BGP, IPsec/IKE parameters, routes, and firewalls on the on-premises devices.
6. Verify session state, received/advertised routes, and failover behavior.

Tunnel/peer creation commands depend on vendor hardware, peer IPs, keys, and BGP link-local addresses, so we omit rigid commands that could cause misconfiguration in a shared lab. Use the **HA VPN setup wizard** and your device vendor's documentation to finish setup.

### Step 4: Inspect status (read-only)

~~~bash
gcloud compute vpn-gateways describe hybrid-ha-vpn \
  --region=asia-southeast1 --project=PROJECT_ID

gcloud compute vpn-tunnels list --project=PROJECT_ID

gcloud compute routers get-status hybrid-router-sea1 \
  --region=asia-southeast1 --project=PROJECT_ID

gcloud compute routes list --project=PROJECT_ID
~~~

Check the on-premises side using your network device's tools as well: IPsec SAs, BGP state, learned routes, interface errors, bandwidth, and failover. Never declare success merely because two tunnel resources appear in the GCP Console.

## 8. Firewalls: Allow Specific Flows, Not the Entire Network

VPC firewalls address only one layer along the path. The design must cover on-prem firewalls, routes, DNS, TLS, and authentication.

Example allowing a test workload on Compute Engine to receive HTTPS **from on-premises** by network tag:

~~~bash
gcloud compute firewall-rules create allow-erp-to-test-api \
  --network=hybrid-vpc \
  --direction=INGRESS \
  --source-ranges=10.60.0.0/16 \
  --allow=tcp:443 \
  --target-tags=hybrid-api \
  --project=PROJECT_ID
~~~

This is a **VM firewall rule** example, not a complete firewall setup for an internal Application Load Balancer or Cloud Run. If the backend uses a regional internal Application Load Balancer, you also need a proxy-only subnet, backend allow rules, and health-check traffic rules matching that load balancer type. Never apply `target-tags` directly to Cloud Run assuming the service is protected.

### Minimum security matrix

| Flow | Source | Destination | Port | Controls |
|---|---|---|---|---|
| ERP → API | On-prem app subnet | Internal LB VIP | 443 | HTTPS, token/mTLS, routes, and firewalls |
| API → ERP | GCP workload egress | ERP VIP | 8443 | Bidirectional firewalls, TLS, and auth |
| App → DB | GCP subnet/identity | Cloud SQL private IP | 5432 | Private connectivity, DB roles, TLS |
| On-prem batch → Google API | On-prem subnet | Private/restricted VIP | 443 | DNS, routes, IAM, and service scope |
| Hybrid DNS | On-prem DNS / Cloud DNS | Respective DNS resolvers | UDP/TCP 53 | ACLs, forwarding, return routes |
| Monitoring | Workloads / agents | GCP telemetry APIs | 443 | IAM, egress policies, log hygiene |

**TLS and IAM are never replaced by a VPN:** IPsec protects the tunnel, while application endpoints still require TLS, workload identity, and access control. For Cloud SQL, database users and IAM/network permissions are separate layers.

## 9. Bidirectional Hybrid DNS

Hybrid integrations frequently break at DNS even when BGP and TCP are healthy. The fix is keeping authoritative zones in the right place and configuring intentional forwarding.

### On-premises querying GCP names

- Cloud DNS hosts a **private zone** `gcp.corp.example` attached to `hybrid-vpc`.
- Record `orders.gcp.corp.example` resolves to the internal LB VIP.
- Create a **Cloud DNS server policy with inbound forwarding** to obtain appropriate forwarding IPs.
- On-premises DNS configures conditional forwarding for `gcp.corp.example` toward Cloud DNS inbound forwarding IPs in the hybrid link's region.
- Firewalls/routing allow UDP and TCP port 53 queries and return paths.

**Never** treat `169.254.169.254` as a DNS server reachable from on-premises; that is the GCP VM metadata resolver, not a public forwarding address for a data center.

### GCP querying on-premises names

- Create a Cloud DNS **forwarding zone** for `corp.example` or a specific subdomain pointing to on-prem DNS `10.60.1.53`.
- Never configure loops: for instance, GCP forwarding all of `corp.example` to on-prem while on-prem forwards the entire domain back to GCP.
- When forwarding targets on-premises DNS over VPN/Interconnect, Cloud DNS typically originates queries from **`35.199.192.0/19`**, not from the requesting VM's IP.
- On-prem firewalls must permit UDP/TCP 53 from `35.199.192.0/19`.
- On-prem routing needs a return path for `35.199.192.0/19` back through **the exact VPC network** that sent the query, typically via Cloud Router custom BGP advertisements.
- The target DNS server must reply honoring source-address rules rather than delegating replies asymmetrically through another host.

### DNS verification table

| Source | FQDN | Expected result |
|---|---|---|
| On-prem ERP | `orders.gcp.corp.example` | `10.80.10.50` (sample VIP) |
| GCP test VM | `erp.corp.example` | ERP internal IP, e.g., `10.60.20.20` |
| On-prem client | `storage.googleapis.com` | Endpoint matching Private Google Access policy |
| GCP worker | `corp.example` | Accurate record from on-prem authoritative DNS |

Verification commands:

~~~bash
# Run on the on-prem host
nslookup orders.gcp.corp.example
dig orders.gcp.corp.example

# Run on the GCP test VM
nslookup erp.corp.example
dig erp.corp.example
~~~

If `dig` is unavailable, use `nslookup` or an equivalent DNS tool. Check authoritative/recursive behavior, TTLs, and responses per resolver; a single failed command alone does not tell whether the fault is in IPsec or Cloud DNS.

## 10. On-Premises Calling Google APIs via Private Google Access

Cloud Storage, Secret Manager, and other GCP APIs are normally called via `googleapis.com` domains. When on-premises clients need to reach these APIs over Cloud VPN/Interconnect, use **Private Google Access for on-premises hosts**—which differs from enabling Private Google Access on a GCP VM subnet.

### Two important VIPs

| Domain | IPv4 VIP range | Scope of support |
|---|---|---|
| `private.googleapis.com` | `199.36.153.8/30` | Most eligible Google APIs/services |
| `restricted.googleapis.com` | `199.36.153.4/30` | APIs supported by VPC Service Controls |

Neither range is **routed over the public internet**. To use them from on-premises:

1. Select the domain matching your service and data-control needs.
2. Configure internal DNS to map relevant API domains to the chosen VIP.
3. Establish BGP/routes from on-premises to the VIP via tunnels or VLAN attachments.
4. On the GCP VPC, ensure routes to the VIP use the default internet gateway next hop; packets to the VIP stay within Google's network as documented.
5. Verify DNS, firewalls, and return routing, then test real API calls.
6. Grant IAM and enable APIs in the relevant project where workloads operate.

Use Cloud Router **custom advertisements** for the VIP range. Never advertise `0.0.0.0/0` from Google Cloud to on-premises merely to reach Google APIs without an explicit egress design.

### What NOT to assume

- **Not every domain** under `*.googleapis.com` or every Google service supports an arbitrary VIP.
- `restricted.googleapis.com` intentionally **excludes** many APIs outside VPC Service Controls scope.
- VIPs support HTTP-based protocols over TCP (HTTP/HTTPS/HTTP2), not arbitrary TCP/UDP services.
- Private Google Access does not automatically grant IAM permissions or alter data policies.
- Private Google Access for **on-premises hosts** does not require flipping the subnet flag used by VPC VMs; they are two separate configuration workflows.

Domains like `*.run.app`, `*.pkg.dev`, or `storage.cloud.google.com` follow specific DNS rules. Follow the **Configure Private Google Access for on-premises hosts** table to avoid overriding broad DNS namespaces and breaking other services.

## 11. On-Premises Accessing Cloud SQL Private IP

Cloud SQL for PostgreSQL supports private IP using **private services access (PSA)** or other private connectivity options in specific scenarios. With PSA, Cloud SQL runs in a service producer network connected via a private services connection; it is **not** a VM sitting directly inside `10.80.10.0/24`.

### Sample flow

~~~mermaid
flowchart LR
  A[On-prem Java batch] --> B[Cloud VPN / Interconnect]
  B --> C[Hybrid VPC]
  C --> D[Private services access connection]
  D --> E[(Cloud SQL PostgreSQL private IP)]
~~~

The actual path requires **both forward and return routing**. Key rules:

- Reserve an allocated IP range (e.g., `10.90.0.0/16`) non-overlapping with source and GCP networks.
- Create the private services access connection and attach Cloud SQL to the right network.
- Cloud Router must **advertise the required producer allocation prefixes to on-premises**; default subnet advertisements do not automatically include service producer allocations.
- Configure **export custom routes** on the service producer peering so the producer network knows the return path to on-premises prefixes where required.
- Cloud VPN/Interconnect must terminate in the exact VPC holding that private services access connection; **VPC Network Peering does not provide transitive routing** across multiple peered VPCs.
- Verify routes, TLS, DB credentials/roles, timeouts, and connection limits.

Cloud SQL documentation allows on-premises sources connected to the VPC via Cloud VPN/Interconnect to reach instances via private IP when properly configured. If choosing a **Private Service Connect endpoint for Cloud SQL** instead of PSA, follow the dedicated PSC workflow—endpoint IPs, service attachments/service connection policies, DNS, and per-network reachability—rather than copying PSA steps into PSC.

### Latency risk

An on-premises Java service reading/writing Cloud SQL over a WAN can trigger hundreds of round trips per transaction. Even with TCP 5432 open, p95 latency and transaction timeouts can breach SLOs. When this happens:

- Optimize query count, batching, and connection pooling.
- Eliminate N+1 queries and chatty app-to-DB interactions.
- Consider migrating the app together with its DB in the same wave, or using an integration API instead of direct JDBC over WAN.
- Test failover, connection reuse, transaction retries, and data consistency.

**Never treat direct JDBC over VPN as a default long-term design** when an API/service boundary fits better.

## 12. On-Premises Calling Cloud Run or GKE Private APIs

There are multiple ways to publish an internal Google Cloud API:

| Backend | Suitable pattern | Additional requirements |
|---|---|---|
| Compute Engine VM/instance group | Internal passthrough or internal Application Load Balancer | Firewalls, health checks, TLS, backend pools |
| GKE workload | Internal LoadBalancer Service or internal Application Load Balancer/Ingress/Gateway | Cluster networking, NEGs, backend policies |
| Cloud Run | Internal Application Load Balancer with serverless NEG, or supported internal path | Cloud Run ingress, IAM auth, TLS, and DNS |
| Managed service with PSC | PSC endpoint where supported by product | Endpoint IPs, connection/consumer policies, quotas |

### With Cloud Run

For internal-only APIs, review `ingress=internal` per Cloud Run documentation. Cloud Run documentation classifies requests from on-premises sources connected via Cloud VPN/Interconnect as **internal** under certain setups, though exact behavior depends on access path, VPC setup, and supported ingress rules.

If using an internal Application Load Balancer:

1. Create a regional internal Application Load Balancer and a serverless NEG backed by the Cloud Run service.
2. Restrict Cloud Run ingress to allow only the intended internal path.
3. Assign an internal VIP and DNS name `orders.gcp.corp.example`.
4. Configure a client-trusted TLS certificate; add mTLS or application-level authentication if needed.
5. Grant **run.invoker / IAM** to the caller per Cloud Run's auth model, or place an approved auth-enforcing proxy layer in front.
6. Verify that requests from the public internet cannot reach the backend unexpectedly.

**Network ingress and IAM are two distinct security gates.** Setting internal ingress does not mean every resource on the network is allowed to invoke the API with arbitrary business permissions.

### With GKE

GKE additionally requires:

- Pod/service CIDRs and node subnets that do not overlap on-premises.
- Workload scheduling, service exposure, and firewalls.
- An internal load balancer matching TCP/HTTP requirements.
- Network policies, service accounts, and workload identity.
- DNS resolution, readiness/health checks, and rolling deployments.
- Clarifying how Pod/service IPs are routed or abstracted behind load balancers; do not assume on-premises needs direct routes to every Pod CIDR.

### When to use API integration instead of network-level DB access?

If on-premises only needs to invoke specific order workflows, prefer an **HTTPS API with authentication, idempotency, and retries** over granting direct SQL access across the WAN. An API boundary scopes permissions and decouples schemas across systems.

## 13. Identity, Authentication, and Zero Trust

IPsec/Interconnect connectivity does not answer "which application is permitted to read this data?" Divide security into at least four layers:

| Layer | Controls | Example |
|---|---|---|
| Network | Routes, firewalls, segmentation, private endpoints | Only the ERP subnet can call API VIP:443 |
| Transport | TLS/mTLS and certificate validation | HTTPS with a trusted CA |
| Identity | Workload identity, OIDC, or service accounts | ERP client obtains a valid signed JWT |
| Authorization | IAM, app roles, and DB grants | Service reads only the permitted bucket or DB schema |

### On-premises workloads needing Google Cloud IAM

Avoid embedding **long-lived service account JSON keys** inside Java applications, Docker images, or batch scripts. Where supported, use **Workload Identity Federation** for external workloads to exchange external IdP credentials for short-lived Google Cloud tokens. Verify providers/issuers, audiences, attribute mappings, and permission bindings.

Application Default Credentials (ADC) is a mechanism Google client libraries can use; on-premises, configure a suitable credential source (such as federation) rather than expecting a GCE metadata server.

### Data to protect

- API tokens, session cookies, DB passwords, certificate private keys, and IPsec pre-shared secrets.
- Personal data, financial data, customer IDs, or ERP payloads.
- VPN peer public IPs and real network diagrams outside internal scope.
- Trace/log attributes must never contain secrets or unauthorized data.

**Principle:** routing determines where packets can travel; identity and authorization determine who may perform an action.

## 14. End-to-End Observability for Hybrid Integrations

A hybrid link can report "UP" while applications still fail due to DNS, certificates, database locks, or timeouts. Measure both **network** and **application** layers.

### Network layer

Track:

- VPN tunnel status, bytes in/out, packet drops, and retransmissions.
- BGP session states, route counts, route changes, and failover events.
- Cloud Router advertised/learned routes.
- Latency/packet loss and bandwidth per tunnel/Interconnect.
- Cloud DNS query errors, latency, and forwarding failures.
- Firewall-denied traffic and route reachability tests.

### Application layer

- HTTP/gRPC request rates, p95/p99 latency, and status codes.
- JDBC connection acquisition times, active/idle connections, and SQL errors.
- Retry counts, circuit breaker states, queue age, and dead-letters.
- End-to-end transaction success (e.g., ERP receiving order acknowledgments).
- Trace context propagated across ERP gateway, Java API, and DB/integration workers where instrumented.
- Batch completion times and data reconciliation drift.

### Suggested monitoring and alerts

| Alert | Principle-based trigger | Impact |
|---|---|---|
| VPN tunnel down | One tunnel drops in a dual-tunnel topology | Degraded redundancy warning |
| All hybrid paths unreachable | Zero remaining available paths | P1/P0 depending on business impact |
| BGP peer lost | BGP session leaves established state | Risk of route loss |
| DNS forwarding errors | Sustained query failures | Broken service discovery |
| API p95 latency spike | Breaches SLO for sustained window | Investigate WAN/app/DB |
| Repeated auth errors | 401/403 spikes, TLS cert errors | Misconfigured identity/cert policy |
| DB connections exhausted | Rising pool wait times and connection errors | Check sizing and WAN retries |
| Cost increase | Hybrid egress/Interconnect SKUs surge | Investigate workloads or batch jobs |

Set alerts using **benchmarked thresholds** instead of arbitrary numbers that trigger noisy false positives. Every alert needs an owner, dashboard link, and explicit runbook.

### Investigation tools

- Cloud Monitoring for VPN, Cloud Router, load balancer, and service metrics.
- Cloud Logging for Cloud DNS/VPC firewalls/applications when those log types are enabled.
- Network Intelligence Center Connectivity Tests for analyzing supported network paths.
- VPC Flow Logs/Flow Analyzer for observing recorded traffic flows.
- Cloud Trace/OpenTelemetry for pinpointing Java request bottlenecks.

Flow Logs do not capture every packet; sampling and aggregation affect reconciliation. Combine them with metrics and logs from the on-premises side.

## 15. Lab Runbook: Verifying From Both Sides

**Labs should use sandboxes and VPN appliances or simulated environments managed by your organization.** Never configure production peers or alter live routing/firewalls without formal approval.

### Step 1: Prepare inventory

1. Record project ID, region, VPC/subnets, IPAM, and DNS zones.
2. Record on-prem CIDRs, peer public IPs, vendor, BGP ASN, and owner.
3. Document test endpoints (containing no secrets).
4. Obtain approval for security/routing/failover policies and lab windows.
5. Set budgets and a cleanup plan.

### Step 2: Provision foundational networking

Follow Section 7 to create the VPC, subnet, Cloud Router, and HA VPN gateway. Complete tunnels/BGP peers following product documentation and your enterprise device guides.

### Step 3: Stand up an independent test backend

To verify baseline connectivity before deploying Cloud Run/SQL, use a **Compute Engine test VM with an internal IP and an approved HTTPS service**, or an existing internal test service. Attach tag `hybrid-api` if using the illustrative firewall rule, and deploy a valid certificate.

Never expose the test backend to the open internet. Use mock data—never real customer records.

### Step 4: Verify routes

From on-premises:

~~~bash
# On-prem Linux: choose commands appropriate for your OS
ip route get 10.80.10.50
traceroute 10.80.10.50

# Test TCP connectivity; timeouts are not always caused by firewalls
nc -vz 10.80.10.50 443
~~~

From the GCP test VM:

~~~bash
ip route get 10.60.20.20
nc -vz 10.60.20.20 8443
~~~

`traceroute` over VPN/private paths may drop hops if ICMP is suppressed. Never treat missing hops as proof of missing routes; rely on BGP route tables and real TCP/HTTP probes.

### Step 5: Verify DNS

~~~bash
# From on-premises:
nslookup orders.gcp.corp.example

# From the GCP VM:
nslookup erp.corp.example
~~~

Cross-check returned IPs against IPAM and confirm no unexpected resolver responded. If DNS fails while direct TCP to the IP works, inspect forwarding zones, inbound DNS policies, return routes, and UDP/TCP 53 firewalls.

### Step 6: Verify HTTPS and authentication

~~~bash
curl -v --connect-timeout 5 --max-time 15 \
  https://orders.gcp.corp.example/health
~~~

Use a hostname matching the TLS certificate. **Never use `curl -k` as security validation.** If the API requires tokens, supply valid authentication rather than disabling auth for production. Inspect HTTP status codes, certificates, latency, and application logs.

### Step 7: Verify Cloud SQL / Private Google APIs (if in scope)

- For Cloud SQL: verify TCP 5432, TLS, database identity/permissions, minimal queries, and transactions.
- For Google APIs: verify DNS for `storage.googleapis.com`, VIP routes, API responses, and caller IAM.
- Never start with production writes or deletes; use test environments and least privilege.

### Step 8: Controlled failover rehearsal

1. Capture baseline: API p95, TCP errors, BGP routes, and traffic distribution across tunnels.
2. Disable **one** tunnel or peer within the lab maintenance window.
3. Verify routes converge and transactions continue within target criteria.
4. Measure actual disruption duration rather than assuming SLA numbers.
5. Restore the tunnel and verify redundant state returns.
6. Where feasible, also test losing a DNS forwarding target or one backend instance.
7. Record events, results, issues, and architectural decisions.

Never cut the entire production WAN just to benchmark HA VPN.

## 16. Java/Spring Boot Integration With Internal APIs

Java applications should communicate via **stable FQDNs** with timeouts, retry policies, idempotency, and telemetry. Never hardcode a server's private IP in source code.

### Java 17 HTTP client example

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HybridApiCheck {
    public static void main(String[] args) throws Exception {
        String endpoint = "https://orders.gcp.corp.example/health";

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP status: " + response.statusCode());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "Hybrid API did not pass health check"
            );
        }
    }
}
~~~

This is a **smoke test** for an authorized health endpoint. Real systems require OIDC/tokens or mTLS, structured logging, and tracing; never print sensitive request bodies or tokens. `HttpClient` validates TLS against the JVM trust store; install corporate CAs per policy without disabling hostname verification.

### Spring application configuration

Partial configuration example:

~~~yaml
hybrid:
  erp:
    base-url: "https://erp.corp.example:8443"
    connect-timeout-ms: 3000
    read-timeout-ms: 10000

spring:
  datasource:
    url: "jdbc:postgresql://CLOUD_SQL_PRIVATE_IP:5432/orders"
    username: "DB_USER"
    # Never put real passwords in source; read from an appropriate secret/environment.
~~~

This example does not represent all Spring Framework properties. Timeout settings must be wired into the actual HTTP client/connection pool used by the app. For Cloud SQL, evaluate Cloud SQL connectors/Auth Proxy per scenario, identity, TLS, and instance connection limits.

### Retries and circuit breakers

Over hybrid links, transient network errors can occur during route convergence:

- Retry only safe/idempotent operations or those carrying idempotency keys.
- Use exponential backoff with jitter and cap the retry budget.
- Never retry infinitely during a network outage.
- Use circuit breakers or queues to protect downstream dependencies.
- Log trace IDs and error types, never bearer tokens.
- Run canaries and verify transaction semantics.

Changing a timeout arbitrarily can grow queue lengths and breach SLOs. Measure p95/p99 and confirm timeouts/retries do not amplify traffic into retry storms.

## 17. Data Transfer and Synchronization Patterns

Not every integration needs synchronous WAN queries. Pick patterns according to consistency, latency, and RPO:

| Scenario | Suggested integration pattern | Risks to manage |
|---|---|---|
| ERP needs immediate response | Synchronous HTTPS/gRPC | WAN latency, timeouts, auth |
| End-of-day state sync | Verifiable batch files / Cloud Storage | Scheduling, checksums, encryption |
| Order events | Pub/Sub via authorized producer | Duplicates/out-of-order, idempotency |
| Continuously changing DB data | CDC/migration/replication per scenario | Lag, schema compatibility, RPO |
| Reporting/analytics | Scheduled ETL/ELT or streaming pipeline | Transfer costs, schema evolution |
| Legacy file shares | Suitable transfer pipeline or storage bridge | File semantics, locks, permissions |

For databases, **Database Migration Service** supports eligible source–target pairs; it is not a default bidirectional active-active sync engine. If both environments write data, design explicit conflict resolution and ownership.

### Sensitive data

Every flow must specify:

- Data owner and classification.
- Storage location and retention.
- Encryption in transit and at rest.
- IAM and application authorization.
- DLP/validation if required.
- Reconciliation, retry, and dead-letter plans.
- Hourly data volume, peak spikes, and cost caps.

## 18. Reliability, RTO/RPO, and Failure Domains

A hybrid system introduces dependencies on WANs, DNS, and peer devices. Designs must map explicit failure domains:

| Failure | Impact | Mitigation |
|---|---|---|
| Loss of one VPN tunnel | Reduced redundancy / possible capacity drop | Remaining tunnel and BGP convergence |
| Loss of on-prem peer | Total path loss if peer is a single point of failure | Dual peer devices/locations |
| On-prem DNS outage | GCP cannot resolve legacy names | Multiple DNS targets/forwarders |
| Cloud DNS forwarding failure | Lookups fail, APIs unreachable | Verify return paths and DNS ACLs |
| Cloud SQL unavailable | Transactions fail | HA/backups/DR, sensible retries |
| Hybrid WAN congestion | API p95 spikes, DB timeouts | Caching, queues, circuit breakers, boundary redesign |
| GCP region unavailable | Internal LB/API/DB impacted | Regional DR matching verified RTO/RPO |
| Token issuer/IdP outage | Cannot mint new tokens | Cache/token TTL design and recovery plan |

HA VPN protects part of the network link; **it does not protect the source ERP, DNS servers, or a region**. Maintain end-to-end error budgets/SLOs and run real failover tests.

### Region failover

If the application has a DR plan in another region, verify:

1. Matching VPC routing mode and BGP/Interconnect routes.
2. DNS failover or traffic routing with realistic TTLs/convergence windows.
3. Verified database replication/restores and RPO.
4. Consistent IAM, secrets, certificates, and network policies.
5. Tests proving on-premises clients can reach the backup region.
6. Backup link operational costs budgeted upfront.

Never treat "Cloud Router global routing" as automatic traffic balancing to a DR-region deployment without service-level failover.

## 19. Cost Model and FinOps for Hybrid Connectivity

**Hybrid costs** go far beyond VM or VPN tunnel charges:

- HA VPN tunnel-hours and data transfer charges.
- Cloud Interconnect ports/attachments/provider fees, if used.
- Data egress between GCP and on-premises.
- DNS queries/forwarding charges where billable.
- Internal Application Load Balancer data processing and resource charges.
- VPC Flow Logs/Cloud Logging and Monitoring telemetry.
- Cloud SQL, Cloud Storage, and Pub/Sub operations/data transfer.
- On-premises network hardware, support, and maintenance.
- Duplicate workloads running during migration/DR periods.

### Sample estimation table

| Cost line | Quantity to measure | Source |
|---|---|---|
| VPN tunnels | Tunnel count × running hours | Cloud Billing / VPN pricing |
| VPN data transfer | GiB by direction and region | Billing SKUs |
| Internal LB | Hours/processing/traffic per product | Load balancing pricing |
| Cloud DNS | Queries/zones/policies per SKU | Cloud DNS pricing |
| Database | Instance size, storage, backups/HA | Cloud SQL pricing |
| Logging | GiB ingested/retained | Cloud Logging billing |
| Storage/APIs | Operations and transfer by bucket location | Cloud Storage pricing |
| On-prem network | Ports, hardware, circuits, support | Provider/internal network team |

Never assume one fixed price across every region. Pull exact SKUs and billing account rates when planning. For transactional ERP-to-API calls, measure **cost per successful transaction**, not just total monthly GiB.

### Controlled optimization

- Eliminate N+1 WAN queries via API boundaries and batching.
- Co-locate services and databases in the same region when data residency permits.
- Cache read-heavy, infrequently changing data.
- Avoid full-dataset exports/imports where delta/CDC fits.
- Move long-running transfers off tunnels onto approved data pipelines where appropriate.
- Never sacrifice HA merely to cut one redundant link.

## 20. Layered Troubleshooting

When an integration breaks, step methodically from network to application.

| Symptom | Suspected cause | Verification step |
|---|---|---|
| IPsec tunnel DOWN | Peer IP, IKE/IPsec settings, key, firewall | Tunnel logs, peer logs, crypto policies |
| Tunnel UP, BGP DOWN | ASN, link-local, BGP MD5, timers | Cloud Router status and peer config |
| BGP UP, ping/TCP fails | Prefix not advertised, missing return route, firewall | Routes on both sides, packet paths, TCP |
| GCP cannot resolve ERP | Unreachable forwarding zone/DNS target | DNS ACLs, `35.199.192.0/19` return route |
| On-prem cannot resolve GCP | Missing inbound Cloud DNS forwarding | Server policy/IPs, conditional forwarding |
| On-prem Storage API call fails | DNS/VIP route or IAM/API scope | VIP resolution, routes, 401/403/timeouts |
| Cloud SQL private IP times out | Missing PSA allocation/route, peering return, or firewall | VPC peering, Cloud Router advertisements |
| Cloud Run returns 403 | Ingress or invoker IAM/app auth | Ingress config, caller identity, logs |
| Internal LB returns 502/503 | Backend/NEG/health check or proxy firewall | Backend health, proxy-only subnet, logs |
| Intermittent failures | Tunnel asymmetry, DNS TTL, retries, route flaps | BGP MED/priority, per-path testing |
| API slow while VPN is UP | WAN RTT, packet loss, DB round trips | Traces, p95, retransmissions, pool waits |
| DR failover still hits old site | DNS caching, connection pools | TTLs, JVM caches, deployment config |
| Unexpected bill spike | Egress/log volume/repeated batch runs | Cloud Billing SKUs, flow attribution |

**Never make network-wide firewall openings or disable TLS validation as a default troubleshooting step.** If a temporary exception is needed for testing, scope it tightly with an owner and expiration, then remove it.

## 21. Architecture Decision Record (ADR) Template

After a workshop, document the rationale behind choices rather than keeping only a network diagram.

~~~yaml
adr_id: ADR-HYBRID-001
title: "On-premises ERP integrated with Orders API on Google Cloud"
status: proposed
context:
  source_cidr: "10.60.0.0/16"
  gcp_vpc: "hybrid-vpc"
  app_region: "asia-southeast1"
decision:
  connectivity: "HA VPN with dual tunnels and BGP"
  routing: "Cloud Router with controlled prefix advertisements"
  dns: "Cloud DNS private zone + inbound/outbound forwarding"
  api: "Regional internal Application Load Balancer -> API"
  database: "Cloud SQL private IP; do not expose database directly unless required"
  identity: "Workload identity / OIDC, TLS, and least privilege"
alternatives:
  - "Dedicated / Partner Interconnect when long-term bandwidth is high"
  - "Asynchronous Pub/Sub/file sync instead of synchronous API"
risks:
  - "WAN latency and on-premises DNS dependency"
  - "Cloud SQL PSA return routes and cross-network dependencies"
acceptance:
  - "Positive/negative auth tests pass"
  - "Bidirectional DNS and TCP/HTTPS verified"
  - "Failover rehearsal completed within approved window"
owners:
  network: "network-team"
  security: "security-team"
  application: "orders-team"
  sre: "sre-team"
~~~

This is an **ADR template for discussion**, not an apply-ready Google Cloud configuration file.

### Handoff deliverables

1. Network/data flow diagram with failure domains.
2. IPAM and DNS zone ownership.
3. BGP advertisements, expected routes, and tunnel pairings.
4. Firewall/port matrix and IAM/auth matrix.
5. Cloud SQL/Cloud Run/private API connectivity decisions.
6. Monitoring dashboards and alert ownership.
7. Performance, load, and cost baselines.
8. Cutover/rollback/failover runbooks.
9. Test evidence and open issues list.
10. ADR signed off by Network, Security, DBA, SRE, and application owners.

## 22. Practical Acceptance Checklist

- [ ] Inventory of applications and on-prem ↔ GCP flows covers both requests and responses.
- [ ] On-prem/GCP/PSA/GKE CIDRs approved by IPAM with zero overlap.
- [ ] HA VPN/Interconnect designed with proper topology and peer redundancy.
- [ ] Cloud Router BGP sessions use matching ASNs, prefixes, and route priorities.
- [ ] Return routing and bidirectional network-level firewalls verified.
- [ ] Inbound DNS forwarding for GCP names works from on-premises.
- [ ] Outbound DNS forwarding for ERP names works from GCP.
- [ ] If using Cloud DNS outbound forwarding, DNS ACLs and `35.199.192.0/19` return routes are accurate.
- [ ] Google API calls from on-premises use proper VIPs/DNS/routes and IAM.
- [ ] Cloud SQL private IP has matching producer allocation and return routes.
- [ ] Internal APIs accept only approved ingress with valid authentication/mTLS/TLS.
- [ ] Java HTTP/JDBC timeouts, retries, and connection pooling verified.
- [ ] Baselines captured for p95 latency, throughput, error rates, and traffic costs.
- [ ] Rehearsed failover of at least one tunnel and verified recovery.
- [ ] Dashboards, alerts, owners, on-call rotations, and runbooks in place.
- [ ] Security test results documented (both positive and negative tests).
- [ ] Diagrams, port matrices, ADRs, cost models, cleanup, and changes recorded.

## Review Questions

1. Why are two HA VPN tunnels and Cloud Router BGP alone insufficient to prove end-to-end application availability?
2. Does Cloud Router perform per-packet forwarding across a VPN?
3. Why must on-premises CIDRs never overlap with GKE Pod/Service secondary ranges?
4. Can on-premises reach a Cloud SQL private IP? Which routing/PSA prerequisites must be checked?
5. With Cloud DNS forwarding from GCP to on-premises DNS, why must `35.199.192.0/19` be considered?
6. How does `private.googleapis.com` differ from `restricted.googleapis.com`?
7. How do an internal Application Load Balancer and Cloud Run IAM address different parts of security?
8. How do VPN and Interconnect differ regarding default data encryption?
9. Why can a Java API calling a database directly over a WAN trigger latency failures even when TCP and BGP work?
10. If one tunnel drops and the API keeps running, what else must be checked to validate real HA?
11. How does a DNS forwarding loop break applications even when routes and firewalls are right?
12. Why run a pilot with rollback plans and cost tracking before scaling a hybrid integration?

## Conclusion

Designing on-premises integration with Google Cloud requires **multi-layered evidence**: accurate application dependencies, clean IPAM and routing, bidirectional DNS, dedicated endpoints per service, authentication and authorization, telemetry, HA, and cost controls. HA VPN with Cloud Router provides a flexible connectivity foundation; Cloud DNS solves service discovery; and internal load balancers, Cloud SQL private connectivity, and Private Google Access serve **distinct** paths that cannot be swapped arbitrarily.

With a flow table, ADR, runbooks, positive/negative tests, failover drills, and a cost baseline, teams can progressively migrate Java APIs, data, and workers to GCP while operating safely alongside ERP and legacy systems. The outcome of this practice is not merely "VPN is UP," but **a verifiable hybrid architecture with clear owners and an actionable recovery plan**.

## References

- [Google Cloud — Hybrid and multicloud networking](https://cloud.google.com/architecture/hybrid-multicloud-networking)
- [Cloud VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [HA VPN topologies](https://cloud.google.com/network-connectivity/docs/vpn/concepts/topologies)
- [Create HA VPN gateways to a peer gateway](https://cloud.google.com/network-connectivity/docs/vpn/how-to/creating-ha-vpn)
- [Cloud Router overview](https://cloud.google.com/network-connectivity/docs/router/concepts/overview)
- [Cloud Router best practices](https://cloud.google.com/network-connectivity/docs/router/concepts/best-practices)
- [Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [Cloud DNS best practices for hybrid environments](https://cloud.google.com/dns/docs/best-practices)
- [Cloud DNS forwarding zones](https://cloud.google.com/dns/docs/zones/forwarding-zones)
- [Cloud DNS server policies](https://cloud.google.com/dns/docs/policies)
- [Private Google Access for on-premises hosts](https://cloud.google.com/vpc/docs/private-google-access-hybrid)
- [Configure Private Google Access for on-premises hosts](https://cloud.google.com/vpc/docs/configure-private-google-access-hybrid)
- [Private services access configuration](https://cloud.google.com/vpc/docs/configure-private-services-access)
- [Cloud SQL for PostgreSQL private IP](https://cloud.google.com/sql/docs/postgres/configure-private-ip)
- [Cloud Run ingress restrictions](https://cloud.google.com/run/docs/securing/ingress)
- [Internal Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/l7-internal)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Network Intelligence Center connectivity tests](https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview)
- [Cloud Billing export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
