# Cloud Router and BGP Route Exchange

An enterprise runs an inventory management system in its private data center and a new order service deployed on **Google Cloud**. The order service uses **Cloud Run**, some workloads run on **Compute Engine** and **GKE**, and data is stored in **Cloud SQL** and **Cloud Storage**. These workloads need to exchange data with internal systems, while the enterprise wants to keep private addressing, limit traffic over the public Internet, and support rerouting if a connection fails.

To design **hybrid** connectivity between an enterprise network and a Google Cloud **VPC**, beyond VPN or Interconnect, both ends also need a mechanism to **know which networks are reachable over which connection**. Google Cloud provides **Cloud Router**, which uses **Border Gateway Protocol (BGP)** to exchange dynamic routing information with peer devices or BGP systems. When networks are added, withdrawn, or a link fails, routing information can update without managing every path via manual static routes.

This lesson belongs to the **DNS and Hybrid Connectivity** chapter of the **CLOUD_PROVIDERS_GCP** module. The goal is to understand Cloud Router/BGP's role in VPC, VPN, and Interconnect design; know how to configure and verify connections; and connect routing with IAM, security, application releases, reliability, and operational costs.

## 1. Where Does Cloud Router Sit in a Hybrid Architecture?

### 1.1. Cloud Router Is a Managed Routing Service

**Cloud Router** is a Google Cloud-managed service for exchanging route information using BGP. A Cloud Router is created inside **one VPC** and **one region**. It can establish BGP sessions with peers over supported connections, typically:

- **HA VPN:** IPsec connections between a Cloud VPN gateway and an enterprise VPN gateway; eligible tunnels attach to interfaces/BGP peers on Cloud Router.
- **Dedicated Interconnect or Partner Interconnect:** dedicated or partner connections to Google; BGP runs over **VLAN attachments** bound to Cloud Router.
- Certain supported **Network Connectivity Center / router appliance** architectures also use Cloud Router; consult the specific solution guide.

Cloud Router **is not a virtual machine acting as a packet router**. It serves as the **control plane**: learning routes from peers, advertising routes to peers, and providing information so the VPC can program appropriate dynamic routes. The **data plane** forwards packets through Cloud VPN tunnels, Cloud Interconnect attachments, and Google Cloud's network infrastructure along the selected route.

~~~mermaid
flowchart LR
    subgraph ON["Enterprise data center"]
      DB["Internal network 172.20.0.0/16"]
      PEER["On-premises router/VPN appliance\nASN 65020"]
      DB --- PEER
    end
    subgraph GCP["Google Cloud - VPC retail-vpc"]
      TRANS["HA VPN tunnel or Interconnect VLAN attachment"]
      CR["Cloud Router\nASN 65010 - control plane"]
      VPC["VPC routes and Google data plane"]
      APP["VM / GKE / apps 10.40.0.0/16"]
      VPC --- APP
    end
    PEER <-- "BGP: advertise/learn prefixes" --> CR
    PEER <-- "Data traffic over connection" --> TRANS
    TRANS --- VPC
    CR -. "Dynamic route info" .-> VPC
~~~

The two arrows between components represent **two separate responsibilities**: BGP governs the exchange of routing information, while the tunnel/attachment carries application traffic. A BGP session in the `Established` state **does not prove** applications can connect; you must still verify routes, firewalls, DNS, permissions, and the target service.

### 1.2. What Does Cloud Router Not Replace?

| Component | Primary Role | How It Differs from Cloud Router |
| --- | --- | --- |
| **HA VPN** | Establishes IPsec tunnels and secures traffic over VPN connections. | Cloud Router does not create VPN tunnels or encrypt traffic itself. |
| **Cloud Interconnect** | Provides connectivity between the enterprise network and Google over supported interconnect infrastructure. | Cloud Router exchanges BGP over attachments; it does not provide the physical link. |
| **VPC routes** | Determines packet paths inside the VPC. | Cloud Router contributes dynamic routes, while the VPC also has subnet routes, static routes, and other path selection rules. |
| **Cloud DNS** | Resolves hostnames to IP addresses. | BGP exchanges **IP prefixes**, not DNS names or `A`, `CNAME`, `SRV` records. |
| **VPC firewall / policy** | Controls which traffic is permitted through. | Having a route does not mean TCP/UDP ports are allowed. |
| **IAM** | Controls who can administer resources or call Google APIs. | BGP does not grant IAM roles, service accounts, or database privileges. |

For example, an application uses `erp.corp.example` to call an internal API. Cloud DNS forwarding or a hybrid resolution mechanism finds IP `172.20.10.15`; Cloud Router/BGP lets Google Cloud know the path to the **prefix** containing that IP. Both must be right, and each solves a separate problem.

## 2. Mastering BGP Through Core Concepts

### 2.1. ASN, BGP Peer, and BGP Session

**Border Gateway Protocol** is a routing protocol that exchanges destination networks, called **prefixes** or **CIDRs**, between routing systems. When Cloud Router connects to an enterprise router, **eBGP** is typically used, meaning the two sides belong to different **Autonomous System Numbers (ASNs)**.

| Concept | Meaning | Illustrative Value |
| --- | --- | --- |
| **Local ASN** | ASN configured on Cloud Router. | `65010` |
| **Peer ASN** | ASN of the enterprise BGP router. | `65020` |
| **BGP session** | Routing information exchange session between two peers. | `cloud-router ↔ on-prem-router` |
| **Interface IP** | Address used for the BGP session on a supported link. | `169.254.21.1` |
| **Peer IP** | BGP address of the remote peer. | `169.254.21.2` |
| **Advertised prefix** | Address range a side announces as reachable through itself. | Google advertises `10.40.0.0/16`. |
| **Learned prefix** | Address range received from the remote side over BGP. | Google learns `172.20.0.0/16`. |
| **Route priority / MED** | Information that helps control preference among paths, depending on routing policies and peer handling. | Prefer primary over backup link per design. |

The ASNs `65010` and `65020` are examples of **private ASNs**. In real environments, choose valid ASNs that do not conflict with network/appliance topology and policies. Cloud Router's ASN and the BGP peer's ASN must differ for eBGP. Addresses `169.254.21.1/30` and `169.254.21.2/30` illustrate a **link-local BGP IP pair** for a single connection—they are **not** application subnet IPs and not addresses used to connect to Cloud SQL.

### 2.2. What Does Each Side Advertise and Learn?

Suppose:

~~~text
Google Cloud VPC:
  subnet-orders = 10.40.0.0/20
  subnet-data   = 10.40.16.0/20

On-premises:
  ERP network       = 172.20.10.0/24
  Inventory network = 172.20.20.0/24
~~~

When configured properly:

1. **Cloud Router** advertises the appropriate VPC subnet prefixes to the on-premises router, according to the active routing mode and advertisement policy.
2. **The on-premises router** advertises internal prefixes `172.20.10.0/24` and `172.20.20.0/24`.
3. **Cloud Router** receives these prefixes, and Google Cloud can install effective dynamic routes for the VPC according to route selection rules.
4. The on-premises router uses the learned routes to send traffic to Google Cloud networks.

**Important:** Do not assume every route in the VPC, every static route, or every route Cloud Router learns from another peer is automatically re-advertised to on-premises. By default, Cloud Router advertises subnet prefixes per routing mode rules; custom advertisements must be configured separately when needed. Google Cloud also does not turn a VPC into a **transit router** between two external networks by default.

### 2.3. A BGP Session Has a Lifecycle

A BGP session typically goes through TCP establishment, exchanges ASN/capabilities, transitions to **Established**, and then exchanges update and keepalive messages. When the link or peer becomes unstable, the session can go **Down**, and routes learned over that session can be withdrawn after the system detects the failure and updates.

~~~mermaid
flowchart LR
    A["Tunnel/attachment ready"] --> B["BGP session establishes"]
    B --> C["Established: exchange prefixes"]
    C --> D{"Link or peer failure?"}
    D -- "No" --> C
    D -- "Yes" --> E["BGP Down / withdraw learned routes"]
    E --> F["VPC and peer select remaining available route"]
    F --> B
~~~

Route failover is **not strictly instantaneous**: there is delay from failure detection, BGP processing, route propagation, and application reaction. If recovery targets are tight, test an actual single-tunnel/attachment outage and measure from the user's perspective.

## 3. Cloud Router and VPC Dynamic Routing Mode

### 3.1. Regional or Global?

A VPC has a **dynamic routing mode** property. This is a **VPC-network-level** decision and affects how dynamic routes are applied as well as which subnets Cloud Router advertises in default mode.

| Mode | High-Level Meaning | Example Impact |
| --- | --- | --- |
| **Regional dynamic routing** | Dynamic routes learned via Cloud Router in a region apply within that region per Google Cloud rules. Default subnet advertisements focus on subnets in that region. | VPC has workloads in Singapore and Tokyo, with hybrid link in Singapore: workloads in Tokyo do not automatically use routes learned in Singapore. |
| **Global dynamic routing** | Dynamic routes learned in one region can be used by other regions in the same VPC. Default advertisements can include subnets from all regions in the VPC per global mode rules. | Workloads across regions can use the hybrid link in Singapore, provided route design, firewalls, and link capacity allow it. |

In global mode, choosing between an intra-region route and an inter-region route is also governed by priority rules and **inter-region costs** in Google Cloud's dynamic routing mechanism. Global **does not mean every route has equal priority** or that all traffic always traverses the geographically closest link.

Illustrative diagram:

~~~text
VPC retail-vpc
  asia-southeast1: 10.40.0.0/20 (Cloud Router connected to on-premises)
  asia-northeast1: 10.50.0.0/20 (standby workload)

On-premises: 172.20.0.0/16

REGIONAL: routes learned in asia-southeast1 are scoped to the region.
GLOBAL:   routes learned in asia-southeast1 can take effect across regions.
~~~

Changing the routing mode is a **network-scope change** that can impact applications, firewalls, and path selection. Do not switch from `REGIONAL` to `GLOBAL` merely to resolve a connectivity gap without evaluating existing learned routes and inter-region latency/cost.

### 3.2. Checking Routing Mode

The following commands are **read-only**:

~~~bash
PROJECT_ID="retail-prod"
NETWORK="retail-vpc"

gcloud compute networks describe "$NETWORK" \
  --project="$PROJECT_ID" \
  --format="yaml(name,autoCreateSubnetworks,routingConfig)"
~~~

Illustrative output:

~~~yaml
name: retail-vpc
routingConfig:
  routingMode: GLOBAL
~~~

Real networks may show additional fields. If using **Shared VPC**, inspect the network configuration in the VPC's **host project**, not in a service project that only runs Compute Engine/GKE/Cloud Run.

### 3.3. Default Advertisement vs. Custom Advertisement

In **default advertisement mode**, Cloud Router advertises the VPC's subnet prefixes based on the dynamic routing mode. Some architectures require **custom advertised routes** to:

- Advertise only approved prefixes.
- Advertise specific additional ranges required by the network architecture.
- Apply custom selections at the router level or BGP peer level where supported.

When using custom advertisements, verify whether the configuration still includes **all subnets** or not. You can accidentally stop advertising a subnet serving production if you leave only a single custom range. Advertising a prefix that has no real path can also create a **blackhole** on the peer network.

For instance, advertising a default route `0.0.0.0/0` from either side is a major decision: it can pull far more traffic than intended across VPN/Interconnect. Only do so when the design includes appropriate egress paths, firewalls, NAT, and redundancy. Never treat a default route as a shortcut to avoid declaring needed prefixes.

## 4. BGP Route Selection, Priority, and Redundancy

### 4.1. Multiple Paths to the Same Prefix

In production designs, enterprises typically maintain two independent hybrid paths. If both peers advertise `172.20.0.0/16`, Cloud Router can learn the same prefix from multiple BGP sessions:

~~~text
Peer A over tunnel A: 172.20.0.0/16
Peer B over tunnel B: 172.20.0.0/16
~~~

When multiple routes compete, Google Cloud applies route selection rules, regional scope, prefix specificity, and effective priority. Attributes such as **MED** (*Multi-Exit Discriminator*) can factor into selection, though not all devices and traffic directions handle them identically. A more specific prefix usually overrides a broader prefix, so do not analyze routing solely via MED.

If designing active/active, verify whether links and workloads tolerate traffic across both paths. If designing active/passive, configure priorities and test failover to the standby link. **Symmetric bidirectional paths are not guaranteed** merely because two BGP peers are configured similarly: the on-premises-to-Google direction and the reverse direction are each governed by their respective side's route selection.

### 4.2. Having Two Tunnels Does Not Automatically Equal HA

HA VPN uses tunnels with BGP sessions to provide redundancy under supported topologies. However, verify:

1. Are the two tunnels placed on independent VPN gateway interfaces and connections per HA topology?
2. Does the enterprise router/VPN gateway have proper redundancy?
3. Does each tunnel have its own BGP session, valid peer addresses, and complete prefix advertisements?
4. Are routes withdrawn and re-selected properly after a failure?
5. Do firewalls, appliances, DNS, and applications continue working after a path switch?

With Interconnect, redundancy also involves the number of connections, locations, attachments, enterprise routers, and failure domains. **SLAs depend on qualifying topologies**, not simply on creating an extra Cloud Router.

### 4.3. Checking the Return Path

For example, VM `10.40.1.10` calls ERP `172.20.10.15`:

~~~text
Google → on-prem:
  VM 10.40.1.10 → route to 172.20.10.0/24 → tunnel A/B → ERP

On-prem → Google:
  ERP 172.20.10.15 → route to 10.40.0.0/20 → tunnel A/B → VM
~~~

Both sides must have return routes. If on-premises does not learn `10.40.0.0/20`, packets may reach the ERP yet the connection still times out because there is no return path. With multiple stateful firewalls or NAT, asymmetric routing can also cause reply packets to be dropped even when routes exist.

## 5. Preparing Before Configuring Cloud Router

### 5.1. Design Parameter Table

Before writing Terraform or running `gcloud`, prepare a table like this:

| Parameter | Example | Why It Must Be Clear |
| --- | --- | --- |
| Project / VPC | `retail-prod` / `retail-vpc` | Proper resource scope and IAM. |
| Region | `asia-southeast1` | Cloud Router and supported links are regional. |
| Dynamic routing mode | `REGIONAL` or `GLOBAL` | Determines cross-region route usability. |
| Local / peer ASN | `65010` / `65020` | eBGP requires valid, non-conflicting ASNs. |
| VPC subnets | `10.40.0.0/20`, `10.40.16.0/20` | Ranges to advertise to the enterprise network. |
| On-prem prefixes | `172.20.10.0/24`, `172.20.20.0/24` | Ranges Google Cloud needs to learn. |
| HA VPN / VLAN attachments | `tunnel-a`, `tunnel-b` | Data paths and failure domains. |
| BGP link IPs | `169.254.21.1/30 ↔ 169.254.21.2/30` | IP pair for one BGP session; each independent session needs its own valid pair. |
| Permitted traffic | e.g., TCP 443 to ERP API, TCP 5432 to database if truly needed. | Routes do not replace firewalls or authentication. |
| SLO and monitoring | Successful ERP calls; peer-down alerts. | Measure quality from consuming systems, not just router status. |

These example values are not a production IP allocation guide. Before deploying, check for **non-overlapping CIDRs**, available VLAN/tunnel configurations, matching regional resources, permitted BGP IP ranges, quotas, and partner equipment capabilities.

### 5.2. Avoiding Overlapping Address Ranges

Suppose on-premises uses `10.40.0.0/16` while the VPC also uses `10.40.0.0/16`. BGP cannot automatically resolve two sides owning the same IP space: routes can be misprioritized or destinations become ambiguous.

Maintain an organization-wide **IP address plan** covering VPC subnets, on-premises subnets, advertised ranges, standby environments, and networks connected via VPN/Interconnect. If CIDRs cannot be changed, evaluate supported address translation/migration approaches and application constraints rather than simply raising BGP priority.

### 5.3. Required Defense in Depth

Cloud Router requires appropriate Google Cloud resource admin permissions to configure; peer devices require separate BGP administration workflows. Because route changes have broad impact, separate infrastructure provisioning identities from application runtime service accounts.

To allow the ERP API over a hybrid connection, you still need **ingress/egress firewalls**, internal DNS, TLS certificates, and ERP authentication. If applications access **Google APIs** such as Cloud Storage or Secret Manager, that path differs from the BGP session to on-premises; check Private Google Access/egress, IAM, and corresponding service parameters.

## 6. Cloud Router Architecture with HA VPN

### 6.1. Components and Setup Flow

An HA VPN design typically includes:

1. **VPC** containing workloads and subnets.
2. Google Cloud **HA VPN gateway**.
3. **External VPN gateway / on-premises appliance** and required connections.
4. **VPN tunnels** with matching IPsec parameters.
5. **Cloud Router** in the same region and **interfaces** attached to the tunnels.
6. **BGP peers** per tunnel to learn and advertise prefixes.

~~~mermaid
flowchart LR
    subgraph DC["On-premises"]
      P1["VPN/router peer A"]
      P2["VPN/router peer B"]
    end
    subgraph GC["Google Cloud"]
      GW["HA VPN gateway"]
      T1["Tunnel A"]
      T2["Tunnel B"]
      CR["Cloud Router"]
      NET["VPC retail-vpc"]
      GW --- T1
      GW --- T2
      T1 -. "BGP peer A" .-> CR
      T2 -. "BGP peer B" .-> CR
      CR -. "Dynamic routes" .-> NET
    end
    P1 <-- "IPsec A" --> T1
    P2 <-- "IPsec B" --> T2
~~~

This is a logical diagram; when deploying, follow **Cloud VPN's** supported topologies for interfaces, peer gateways, tunnel counts, and HA/SLA eligibility. One Cloud Router can manage multiple BGP sessions, but do not think of it as a separate packet-forwarding appliance per tunnel.

### 6.2. What Happens When One Tunnel Fails?

Suppose both tunnels provide reachability to `172.20.0.0/16`. When tunnel A loses connectivity, BGP session A goes down and routes learned solely from A are withdrawn. If B continues advertising valid prefixes and VPC route selection allows, traffic can shift to B. This also depends on on-premises configuration so the return path uses B as well.

Never design applications assuming **zero packet loss** during failover. For API calls and database access, implement timeouts, controlled retries, idempotency, and handling for interrupted transactions.

## 7. Cloud Router with Dedicated/Partner Interconnect

In an Interconnect design, a **VLAN attachment** connects the on-premises environment to the VPC and runs BGP via Cloud Router. Cloud Router learns/advertises prefixes over an interface attached to the VLAN attachment; actual traffic traverses the Interconnect link.

| Aspect | HA VPN | Dedicated/Partner Interconnect |
| --- | --- | --- |
| Data connectivity | IPsec tunnels over supported VPN infrastructure. | Connectivity over Interconnect/partner infrastructure and VLAN attachments. |
| Role of BGP | Exchanges routes on BGP peers attached to VPN tunnels. | Exchanges routes on peers attached to VLAN attachments. |
| Redundancy design | Relies on gateway interfaces, tunnels, and peer appliances per HA topology. | Relies on connections, attachments, locations, and on-prem routers per redundant topology. |
| Encryption | VPN provides IPsec for tunnels. | Do not assume all Interconnect links use IPsec by default; if encryption is needed, evaluate supported solutions such as HA VPN over Cloud Interconnect. |
| Selection criteria | When flexible VPN or matching bandwidth fits needs. | When bandwidth, latency, stability, and enterprise network presence require dedicated/partner connectivity. |

There is no universal rule that "Interconnect is always faster than VPN in every case." Performance depends on geography, hardware, capacity, load, actual paths, and partner architecture. Base decisions on measurements, security needs, availability, and total cost.

## 8. Working with Cloud Router Using gcloud

The following examples use sample values. **`list`, `describe`, and `get-status` are read operations. `create`, `add-interface`, and `add-bgp-peer` create or modify real configurations.** Only run mutating commands in a test project or under an approved infrastructure plan once HA VPN tunnels/Interconnect attachments and the on-premises side are ready.

### 8.1. Inspecting VPC and Cloud Routers

~~~bash
PROJECT_ID="retail-prod"
REGION="asia-southeast1"
NETWORK="retail-vpc"
ROUTER="cr-retail-hybrid"

# Check the current dynamic routing mode of the VPC.
gcloud compute networks describe "$NETWORK" \
  --project="$PROJECT_ID" \
  --format="yaml(name,routingConfig)"

# List Cloud Routers in the project.
gcloud compute routers list \
  --project="$PROJECT_ID" \
  --format="table(name,region.basename(),network.basename(),bgp.asn)"

# View interface, BGP peer, and route advertisement configuration.
gcloud compute routers describe "$ROUTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"

# View BGP peers and current route status.
gcloud compute routers get-status "$ROUTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"
~~~

In `describe`, pay attention to `bgp.asn`, `interfaces`, `bgpPeers`, and advertised route configuration. In `get-status`, inspect the status of each BGP peer, learned prefixes, best/selected routes, and the status fields actually returned by the API. Exact field names can vary by format and CLI version; use `--format=yaml`/`json` to inspect structure before filtering columns.

### 8.2. Example of Creating a Cloud Router

~~~bash
# Illustrative write command; VPC retail-vpc must already exist.
gcloud compute routers create cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --network=retail-vpc \
  --asn=65010
~~~

Creating a Cloud Router **does not establish a hybrid link by itself**. For BGP to operate, you need interfaces/BGP peers attached to **configured tunnels or VLAN attachments**, valid BGP session IPs, compatible ASNs, and matching configuration on the peer side.

### 8.3. Attaching an Interface and BGP Peer to an Existing Tunnel

Suppose the organization has **already created** a VPN tunnel named `tunnel-retail-a`, and the on-premises side is configured with BGP IP `169.254.21.2` and ASN `65020`:

~~~bash
# Write command: use after verifying tunnel/region/IP pair.
gcloud compute routers add-interface cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --interface-name=if-retail-a \
  --vpn-tunnel=tunnel-retail-a \
  --ip-address=169.254.21.1 \
  --mask-length=30

# Create a BGP peer for the newly attached interface.
gcloud compute routers add-bgp-peer cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --peer-name=peer-retail-a \
  --interface=if-retail-a \
  --peer-ip-address=169.254.21.2 \
  --peer-asn=65020
~~~

`if-retail-a` and `peer-retail-a` are example identifiers. Both IPs must form a valid BGP pair per tunnel requirements without colliding with other sessions. These commands do not create the VPN tunnel, do not configure IKE/IPsec on the on-premises appliance, and do not complete an HA topology. Path B typically needs its own interface and peer with another IP pair, such as `169.254.22.1/30` and `169.254.22.2/30`.

For an **Interconnect VLAN attachment**, the Cloud Router interface uses the corresponding attachment option instead of `--vpn-tunnel`. Do not copy HA VPN commands verbatim to configure Interconnect.

### 8.4. Verifying After Configuration

~~~bash
gcloud compute routers describe cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="yaml"

gcloud compute routers get-status cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="yaml"
~~~

Check the following:

1. **BGP session:** which peers are active, and which are not `Established`/`UP` in the API response.
2. **Learned routes:** is on-premises properly advertising `172.20.10.0/24` and `172.20.20.0/24`?
3. **Advertised routes:** is Cloud Router advertising the VPC subnets that on-premises needs for return traffic?
4. **Effective routes:** are learned routes active in the region of the VMs that need connectivity?
5. **Data plane:** does application traffic from the right VM/pod to the right IP/port succeed, and is the return path working?

Do not rely solely on `gcloud compute routes list` to draw conclusions about **all effective dynamic routes**; use Cloud Router status and the appropriate effective-routes inspection methods for the VPC/resource in current tooling. The routing table inside a guest VM OS also does not necessarily show how Google Cloud VPC selects dynamic routes.

### 8.5. Sample Status Output to Read

Fictional example:

~~~yaml
bgpPeers:
  - name: peer-retail-a
    localAsn: 65010
    peerAsn: 65020
    status: UP
    learnedPrefixes:
      - 172.20.10.0/24
      - 172.20.20.0/24
  - name: peer-retail-b
    localAsn: 65010
    peerAsn: 65020
    status: UP
    learnedPrefixes:
      - 172.20.10.0/24
      - 172.20.20.0/24
~~~

This is a **logical illustration**, not a verbatim JSON/YAML schema guarantee of `gcloud compute routers get-status`. When writing monitoring scripts, use the actual fields from the Cloud Router API/CLI and handle missing fields safely rather than parsing from this illustrative snippet.

## 9. Hybrid Connectivity Is More Than BGP

### 9.1. DNS and IP Routing Solve Two Different Problems

If a Cloud Run application via VPC needs to call `erp.corp.example`, answer:

- **DNS:** what address does this name resolve to? Is Cloud DNS forwarding, inbound policy, or private zone properly designed across environments?
- **Routing:** is the prefix containing that IP advertised over BGP and effective in the workload's VPC/region?
- **Firewall:** are source and destination IPs, protocols, and ports permitted on both sides?
- **Application:** are the endpoint, TLS, tokens, timeouts, and database credentials valid?

BGP does not exchange DNS records, and DNS returning the right address does not mean a route exists.

### 9.2. IAM, VPC Firewalls, and Data

Cloud Router uses Google Cloud resource management and appropriate admin permissions; BGP runs between network devices. Once the hybrid link is up:

- **VPC firewalls** still control traffic to VMs and applicable resources.
- **GKE** applications may also be subject to Kubernetes NetworkPolicies and workload identity mechanisms.
- **Cloud Run** must be configured with the right VPC egress mode so traffic to on-premises addresses uses the hybrid path; never assume every Cloud Run request traverses the VPC.
- **Cloud SQL** has its own connectivity options and database authentication; learning routes to on-premises does not replace Cloud SQL private IP/connector configuration.
- Accessing **Cloud Storage** and **Google APIs** requires appropriate Google API paths and IAM, separate from learning internal ERP prefixes.

Never grant `Owner` or open wide ports just to mask a routing issue. Separating each diagnostic layer helps fix the root cause while preserving least privilege.

## 10. Deployment Scenario: From Retail VPC to On-Premises ERP

### 10.1. Requirements

A retail enterprise has:

- **VPC `retail-vpc`**, application subnet `10.40.0.0/20`, data subnet `10.40.16.0/20`.
- **On-premises ERP** in `172.20.10.0/24`, inventory system in `172.20.20.0/24`.
- **Compute Engine/GKE** workloads needing to call an ERP API over HTTPS.
- A **Cloud Run** backend with a flow that must route through the VPC to reach the ERP.
- Google Cloud transactional data in **Cloud SQL**; files stored in **Cloud Storage**.
- Operational goal: no prolonged outage when one VPN tunnel fails; operations can monitor BGP status and link costs.

These CIDRs are illustrative and assumed to be **non-overlapping**.

### 10.2. Proposed Design

| Item | Design | Rationale |
| --- | --- | --- |
| Cloud Router | One Cloud Router in `asia-southeast1`, ASN `65010`. | Manages BGP peers in the region hosting the hybrid link. |
| On-premises appliance | ASN `65020`, designed with VPN redundancy. | Distinct ASN enabling dynamic learning/advertising. |
| Transport | Dual-tunnel HA VPN per supported topology. | Provides path failover if one tunnel drops. |
| BGP sessions | One peer and dedicated link-local IP pair per tunnel. | Track and withdraw routes per connection. |
| Google-advertised prefixes | VPC subnets needed by on-premises for return traffic. | Prevents on-premises from lacking return routes. |
| On-premises-advertised prefixes | `172.20.10.0/24`, `172.20.20.0/24`. | Scopes learned destinations to actual needs. |
| Dynamic routing mode | Choose `REGIONAL` if only using connectivity in that region; consider `GLOBAL` when multi-region workloads need the routes. | Avoids unintentionally expanding cross-region paths and increasing latency/cost. |
| DNS | Resolve `erp.corp.example` to internal ERP IP via an appropriate hybrid DNS setup. | Avoids hardcoding IPs in applications. |
| Firewall and identity | Open only required ports/ranges; keep IAM/service accounts independent. | Reduces attack surface. |
| Monitoring | BGP status, VPN tunnels, routes, and ERP call success rate. | Control-plane and application-plane failures must be detected separately. |

### 10.3. Request Flow

~~~mermaid
sequenceDiagram
    participant APP as Workload in VPC
    participant DNS as Hybrid DNS
    participant ROUTE as VPC routing
    participant VPN as HA VPN tunnel
    participant ERP as On-premises ERP
    APP->>DNS: erp.corp.example?
    DNS-->>APP: 172.20.10.15
    APP->>ROUTE: TCP 443 to 172.20.10.15
    Note over ROUTE: Prefix 172.20.10.0/24 learned via BGP
    ROUTE->>VPN: Forward via selected dynamic route
    VPN->>ERP: Deliver request
    ERP-->>VPN: Reply via route to VPC
    VPN-->>APP: Return across Google Cloud network
~~~

A request succeeds only when bidirectional paths work, firewalls allow it, the ERP is serving, and TLS/authentication match. When one tunnel fails, verify that BGP withdraws the failed route and selects the remaining path. Application teams must still handle timeouts and retries during convergence.

### 10.4. Failover Drill Scenario

1. Record baseline status of both BGP sessions, learned prefixes, and ERP request success rate.
2. In an approved test/drill environment, safely simulate the loss of one connection path.
3. Observe tunnel state, BGP session state, learned/best routes, and time until application calls succeed again.
4. Check forward/return paths, DNS, and firewalls; measure impact on in-flight transactions.
5. Restore the link, confirm routes return to expected state without loops or asymmetric breakage.
6. Document lessons for runbooks, alerts, capacity, and infrastructure change processes.

Measured recovery time is a metric of the **deployed architecture**, and should not be attributed solely to Cloud Router without corresponding measurements and service terms.

## 11. Common Issues and Isolation Steps

| Symptom | Possibilities | Priority Checks |
| --- | --- | --- |
| BGP peer stays down | Tunnel/attachment inactive, ASN mismatch, wrong BGP IP pair, unattached interface, or peer unconfigured. | `describe` router/tunnel, `get-status`, inspect BGP config on peer. |
| BGP `UP` but missing internal prefix | On-premises not advertising, BGP policy/filter blocking, route dropped, or limit exceeded. | Check advertised routes on-premises and learned routes on Cloud Router. |
| On-premises does not see VPC subnet | Cloud Router default/custom advertisement omits prefix; wrong routing mode or BGP policy. | Check `describe` and routes received at peer. |
| VM in another region cannot reach on-premises | VPC in regional mode; dynamic routes not active in that region. | Check `routingConfig.routingMode`; inspect effective routes. |
| Route exists yet `curl` times out | Firewall, ACL, NAT, missing return route, ERP down, or asymmetric routing. | Check both directions, ports, and network/application logs. |
| Internal name fails to resolve | Cloud DNS / on-prem DNS forwarding not configured. | Inspect resolvers, DNS zones, forwarding rules. |
| One tunnel fails and app stops | Missing standby peer/route or backup path not actually working. | Check A/B BGP status and run path failover drill. |
| Prefix "disappears" after changing advertisements | Custom advertisement accidentally omitted a subnet or advertised wrong prefix. | Compare before/after config and prefix lists on peer. |
| Traffic traverses a farther region than expected | Global routing mode, route priority, prefix specificity, or unexpected peer policy. | Inspect route selection and measure RTT and actual egress/cost. |
| Google API access returns `403` | Missing IAM/token or API restriction; unlikely related to BGP. | Check identity, IAM, and path to Google APIs. |

### 11.1. Layered Investigation Procedure

**Layer 1 — Connectivity:** Is the VPN tunnel or Interconnect VLAN attachment active? Is the peer appliance reaching Google as designed?

**Layer 2 — BGP:** Is the session `UP/Established`? Do ASN, BGP IPs, interface, and peer match? Are the expected prefixes received?

**Layer 3 — VPC routes:** Is the learned route active in the workload's region? Is a more specific prefix or policy selecting another route?

**Layer 4 — Return path:** Does the on-premises router know the Google Cloud subnet CIDR? Are NAT or stateful firewalls dropping return traffic?

**Layer 5 — DNS and security:** Does the hostname resolve to the right IP? Do firewalls permit the protocol/port? Are application identity and certificates valid?

**Layer 6 — Application:** If TCP/TLS succeeds yet the app errors out, inspect HTTP status codes, database credentials, timeouts, retries, quotas, and workload logs.

Do not modify BGP routes when evidence points to a DNS or IAM issue. Route changes can affect many other services sharing the hybrid connection.

## 12. Reliability Observability, Automation, and Cost

### 12.1. Signals to Monitor

- Status of each **BGP peer** and **VPN tunnel / Interconnect attachment**.
- Sets of **advertised/learned** prefixes and unexpected changes.
- Traffic, packet loss, latency, or link errors via available metrics.
- Application-layer SLIs such as **ERP request success rate** and p95/p99 latency.
- Configuration change events on networks, routers, firewalls, DNS, or policies.

Cloud Monitoring and service logs provide technical visibility; application SLOs must also be measured from real workloads. A peer can remain `UP` while the ERP API returns `500`, leaving users impacted.

### 12.2. Managing Configuration as Code

With multiple VPCs and regions, Cloud Routers, interfaces, BGP peers, route advertisements, tunnels/attachments, and policies should be managed in a controlled way using **Terraform** or an appropriate Infrastructure as Code tool. Because a BGP change can affect both Google Cloud and on-premises equipment, the release workflow should:

1. Identify network owners on both sides and agree on a maintenance window.
2. Review changes to CIDRs, ASNs, advertisements, priorities, and regions.
3. Validate the plan before applying, with a rollback plan ready.
4. Monitor BGP and application health immediately after applying.
5. Update diagrams, runbooks, and permitted prefix lists.

Cloud Router updates routes automatically based on BGP information, but it does not replace **configuration drift** management or active change control.

### 12.3. Cost Components to Account For

Cloud Router is a control-plane component; hybrid solution costs also depend on **VPN tunnels, Cloud Interconnect connections/VLAN attachments, data transfer, cross-region traffic, and related network services** under current pricing/terms. If global routing mode sends applications to a link in a farther region, account for extra latency and potential charges. Logs, metrics, redundant links, and capacity also require budgeting.

Never conclude "BGP dynamic routing is free so hybrid connectivity is free" or "adding another peer always guarantees a higher SLA." Total cost and reliability depend on **topology, measured traffic, redundancy setup, and service terms**.

## 13. Practice Exercises

### Exercise 1 — Distinguish Control Plane and Data Plane

A Cloud Router has an `UP` BGP session, yet the ERP API still does not respond from a VM. List four non-BGP causes and how to check them.

**Hint:** firewalls, return routes, DNS, ERP application/TLS. Cloud Router does not forward data packets directly like a proxy.

### Exercise 2 — Regional and Global

A VPC has VMs in `asia-southeast1` and `asia-northeast1`; only the Cloud Router in `asia-southeast1` learns `172.20.0.0/16`. In **regional mode**, what must be considered if Tokyo VMs need to call this system? If switched to **global mode**, what impacts must be tested?

**Hint:** dynamic route scope, route selection, latency, firewalls, return paths, and inter-region cost.

### Exercise 3 — Diagnose a Missing Route

A Cloud Router peer is `UP`, yet prefix `172.20.20.0/24` is not learned. Outline a brief investigation sequence.

**Hint:** check whether the on-premises peer advertises the prefix, BGP policies/filters, route limits, the exact connected session, and learned routes via `get-status`.

### Exercise 4 — Design BGP Redundancy

With two VPN tunnels, design two BGP peers with dedicated link-local IP pairs. Explain why two peers advertising the same network do not automatically guarantee failover meets SLO.

**Hint:** bidirectional routing, tunnel state, priority policies, failure domains, convergence time, and end-to-end application request testing.

### Exercise 5 — Choose the Right Tool

For each requirement, pick the primary component:

| Requirement | Appropriate Component |
| --- | --- |
| Exchange on-premises and VPC CIDRs dynamically. | Cloud Router + BGP over supported VPN/Interconnect. |
| IPsec transport between two systems. | HA VPN. |
| Resolve `erp.corp.example` to an internal IP. | Hybrid DNS mechanism, such as appropriate Cloud DNS forwarding. |
| Block TCP to a VM. | Firewalls/policies at the corresponding layers. |
| Grant Cloud Storage read access to a service account. | IAM on the target service. |

## 14. Design Checklist and Official Documentation

| Design Question | Required Before Deployment |
| --- | --- |
| Checked CIDRs on both sides? | Non-overlapping prefixes, IP plan, and list of advertised networks. |
| Valid ASNs and BGP peers? | Correct local/peer ASNs, matching link IPs/interfaces, no collisions across sessions. |
| Data paths ready? | HA VPN tunnels or Interconnect attachments in right topology and region. |
| Appropriate dynamic routing mode? | Understood regional/global scope and impact across all VPC workloads. |
| Accurate advertisements? | No missing subnets needed for replies; no overly broad or blackholed prefixes. |
| Redundancy included? | Two or more independent paths as needed, with measured failover and return paths. |
| Firewalls and DNS complete? | Verified hostnames, IPs, bidirectional routes, ports, certificates, and authentication. |
| Monitoring in place? | Track peer/tunnel state, traffic, learned routes, app SLIs, and incident runbooks. |
| Governance established? | IaC, peer review, least-privilege IAM, and owners on both cloud and on-premises sides. |
| Cost plan ready? | Estimated VPN/Interconnect, data transfer, redundancy, observability, and inter-region costs. |

Google Cloud documentation for verifying the latest architecture and syntax:

- [Cloud Router overview](https://cloud.google.com/network-connectivity/docs/router/concepts/overview)
- [Cloud Router BGP routes](https://cloud.google.com/network-connectivity/docs/router/concepts/bgp-routing)
- [Cloud Router advertised routes](https://cloud.google.com/network-connectivity/docs/router/concepts/advertised-routes)
- [Cloud Router best path selection](https://cloud.google.com/network-connectivity/docs/router/concepts/best-path-selection)
- [VPC dynamic routing mode](https://cloud.google.com/vpc/docs/vpc#dynamic-routing-mode)
- [HA VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [gcloud compute routers reference](https://cloud.google.com/sdk/gcloud/reference/compute/routers)

**Core takeaway:** **Cloud Router exchanges routing information via BGP, while VPN/Interconnect carries packets.** A stable hybrid design simultaneously requires accurate prefixes, effective routes in the right region, bidirectional reachability, proper firewalls/DNS, monitoring, and tested redundancy.
