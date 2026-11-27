# Global VPC Architecture and Regional Subnets

In Google Cloud, a system may serve users from multiple regions, run Compute Engine in one region, GKE in another region, connect Cloud Run to internal services, and store data in Cloud SQL in permitted locations. For components to communicate in a controlled manner, it is essential to understand that a **Virtual Private Cloud (VPC) is a global resource**, whereas a **subnet belongs to a specific region (regional)**.

This is the foundation of the **VPC and Routing** chapter in the **CLOUD_PROVIDERS_GCP** module. By understanding this model, you will be able to design networks by environment, allocate IP addresses properly, analyze packet paths, protect resources with firewall rules, and estimate the impact of inter-region connectivity on latency, reliability, and cost.

**Learning Objectives**

1. Explain why a single VPC can contain multiple subnets across different regions, while each subnet belongs to only one region.
2. Distinguish between VPC, subnet, VM NIC, IP address, route, firewall, Cloud Router, and network connectivity services.
3. Design IPv4 ranges for multiple environments, GKE, VMs, and managed services without overlap.
4. Describe how traffic flows between subnets within the same VPC, over VPC Peering, over VPN/Interconnect, and to the Internet.
5. Inspect a network design via the Console or gcloud CLI and identify security, availability, operational, and cost risks.

## 1. Global VPC: The Logical Scope of a Private Network

A **VPC network** is a virtual network managed at the Google Cloud project level with **global** scope. A single VPC can contain multiple subnets across different regions without needing to create a new VPC for each region. Resources in the VPC use routing, network policies, and address space according to that network's configuration.

**Global** in this definition describes the *scope of the VPC resource*; it does not mean every VM, IP address, or application data is automatically replicated globally. VMs are still zonal; subnets are still regional; managed services have their own network attachment and location rules.

| Component | Scope | Example | Meaning |
| --- | --- | --- | --- |
| **VPC network** | Global | \`prod-vpc\` | A virtual network that can connect subnets across multiple regions. |
| **Subnet (subnetwork)** | Regional | \`prod-app-sg\` in \`asia-southeast1\` | An IP address range used within a single region of a VPC. |
| **Compute Engine VM** | Zonal | VM in \`asia-southeast1-b\` | Network interface uses a subnet belonging to that zone's region. |
| **Static internal IPv4 address** | Typically tied to the corresponding regional/subnet scope | Internal IP of a VM | Must belong to the range and allocation rules of the associated subnet. |
| **VPC firewall rules** | Defined on the VPC (global for traditional VPC firewall rules) | Rule allowing TCP to a group of VMs | Can affect target VMs across multiple regions; appropriate targets and sources must be configured. |
| **Routes in a VPC** | Routing component of the VPC network | Subnet route, static route, dynamic route | Determines the next hop or how traffic is forwarded; each route type has its own rules for scope and effect. |
| **Cloud Router** | Regional | Router in \`asia-southeast1\` | Exchanges dynamic routing information with connected networks; the scope of route advertisement/learning depends on the routing mode. |

> It is important to distinguish **global management** from **infrastructure running in a single location**. A VPC is global; creating a VM in a VPC does not make the VM run across multiple regions, and sharing the same VPC does not eliminate the risk of losing a region.

### 1.1. Relationship Between VPC, Subnets, and VMs

Suppose there is a VPC \`prod-vpc\` with two subnets:

~~~mermaid
flowchart TB
    subgraph VPC["VPC prod-vpc — global scope"]
      subgraph SG["Region asia-southeast1"]
        SGA["Subnet prod-app-sg<br/>10.20.0.0/20"]
        VM1["VM in zone asia-southeast1-b<br/>10.20.0.10"]
        VM2["VM in zone asia-southeast1-c<br/>10.20.0.11"]
        SGA --- VM1
        SGA --- VM2
      end
      subgraph JP["Region asia-northeast1"]
        JPA["Subnet prod-app-jp<br/>10.40.0.0/20"]
        VM3["VM in a zone of the region<br/>10.40.0.10"]
        JPA --- VM3
      end
    end
    SGA -. "Cross-region internal traffic<br/>per routes and policies" .- JPA
~~~

In the diagram:

- Both subnets belong to **one VPC** but belong to **two different regions**.
- VMs in different zones of the **same region** can use the same regional subnet if the VM configuration is appropriate.
- A VM in another region **cannot** attach a NIC directly to the Singapore region's subnet; it needs a subnet belonging to the VM's region.
- The subnets have different, non-overlapping IP ranges within the same VPC.
- Having an internal route **does not guarantee** that VMs can communicate: firewall rules, organization policies, and OS/host firewalls can still block traffic.

### 1.2. One VPC Does Not Mean One Zone or One Subnet

Here are two common misconceptions:

**Misconception 1:** "Subnets are regional, so to run multi-region you must create multiple VPCs." Incorrect. A single VPC can contain separate subnets in each region where you need to deploy.

**Misconception 2:** "The VPC is global, so you only need one subnet for the entire world." Incorrect. A subnet is tied to *one region*; you cannot use the same regional subnet as the direct subnet for a VM in another region.

Instead of viewing a subnet as a subnetwork stretching across every region, think of a VPC as a **shared logical connectivity framework**, while a subnet is the **portion of address space allocated to a specific region**.

## 2. Two Subnet Creation Modes: Auto Mode and Custom Mode

When creating a VPC, Google Cloud offers two IPv4 subnet modes:

| Mode | How subnets are created | Best suited for |
| --- | --- | --- |
| **Auto mode** | Google Cloud automatically creates subnets with predefined IPv4 ranges in supported regions; it may automatically add subnets in new regions per product behavior. | Testing or getting started when strict address plan control is not needed. |
| **Custom mode** | The designer proactively creates subnets by region, IPv4 range, and required secondary ranges. | Most production, multi-region, hybrid cloud, GKE designs, and networks requiring coordinated addressing. |

Auto mode uses a predefined address scheme designed by Google Cloud. Creating an auto mode VPC can generate subnets outside the regions actually used, increasing the probability of IP range conflicts when connecting to corporate networks. When network and IP control is needed, **custom mode** is generally easier to manage.

An auto mode VPC can be converted to custom mode; the reverse conversion is not an equivalent operation that can be freely applied to any custom mode VPC. Before changing the mode of an active network, you must check product limitations and existing connections.

### 2.1. Planning Primary and Secondary IPv4 Ranges

Each subnet has a **primary IPv4 range**. Depending on the design, a subnet can have **secondary IPv4 ranges**, for example to allocate IPs for Pods and Services in a VPC-native GKE cluster.

Example of an addressing plan:

| Environment/region | Subnet | Primary range | Secondary ranges (when needed) |
| --- | --- | --- | --- |
| Production, Singapore | \`prod-app-sg\` | \`10.20.0.0/20\` | \`10.21.0.0/16\` for Pods; \`10.22.0.0/20\` for Services |
| Production, Tokyo | \`prod-app-jp\` | \`10.40.0.0/20\` | Designed separately if GKE exists in Tokyo |
| Development, Singapore | \`dev-app-sg\` on a separate dev VPC | \`10.60.0.0/20\` | Secondary ranges created only when needed |

These addresses are **learning examples**. In real-world implementation, you must cross-check against corporate networks over VPN/Interconnect, peered VPC networks, management networks, managed service locations, and growth plans.

Key principles to remember:

1. **No overlapping IPv4 ranges** between primary and secondary subnet ranges within the same VPC. When connecting between VPCs or to on-premises, you must also check for address conflicts across all networks to be connected.
2. **Reserve capacity for growth:** IPs for VMs, GKE nodes, Pods, Services, and other services are allocated differently. A small IP range can block scaling, even when CPU or quota is still sufficient.
3. **Do not infer the exact number of usable IPs directly from CIDR size:** Google Cloud reserves addresses in each primary IPv4 range for system functions; the number of usable IPs also depends on the resource type.
4. **Prefer appropriate private address ranges:** such as RFC 1918 IPv4 for typical applications; certain special ranges and features have specific conditions.
5. **Maintain an organization-wide IP plan:** showing VPCs, environments, regions, subnets, secondary ranges, peered networks, and hybrid connections, along with designated approvers.

### 2.2. IP Allocation Is a Long-Term Decision

If subnets are sized nearly full at design time, the system will struggle to scale instance groups, GKE clusters, or machine groups requiring internal IPs. Expanding a subnet's primary IPv4 range is supported under certain conditions; **you should not assume you can easily shrink, change ranges, or migrate all IPs without impacting resources**.

For example, a subnet for GKE nodes without a sufficiently large secondary Pod range can limit the number of nodes/Pods. When planning, you need to consider Pod IP allocation mechanisms by cluster mode, Pods per node, GKE ranges for Services, and upgrade headroom, rather than estimating solely from the initial node count.

## 3. How Does Routing Work in a Global VPC?

A **route** determines where to send traffic based on the destination address and the attributes evaluated by the routing system. Within a VPC, routes can come from subnets, static configurations, dynamic mechanisms, or paths provided by connectivity products.

### 3.1. Automatic Subnet Routes

When a subnet is created, Google Cloud automatically creates **subnet routes** to recognize the subnet's address range within the VPC. As a result, VMs in different subnets **within the same VPC** have an internal route to the corresponding internal addresses, even when the subnets are in different regions.

~~~mermaid
flowchart LR
    A["VM A<br/>10.20.0.10"] --> S1["Subnet Singapore<br/>10.20.0.0/20"]
    S1 --> R["VPC internal routing"]
    R --> S2["Subnet Tokyo<br/>10.40.0.0/20"]
    S2 --> B["VM B<br/>10.40.0.10"]
    F["Firewall / network policy"] -. "Can allow or block" .-> R
~~~

This path **does not require VPN or VPC Peering** because both subnets are already in the same VPC. Traffic is handled by Google Cloud's network infrastructure, though transferring data between regions still incurs latency and may incur charges. Always check pricing rules and the specific scenario.

For VM A to establish a TCP connection to VM B, all of the following conditions must be met:

- VM B has the correct destination IP and the service is listening.
- There is a valid route to the destination range.
- Applicable VPC firewall rules and network policies allow traffic to VM B (and egress if restricted).
- The OS firewall or application firewall does not block the port.

**Having a route does not mean access is permitted.** Routing decides *where packets go*, while firewalls and authorization layers decide *whether they are allowed to pass*.

### 3.2. Routes and Firewalls Are Two Independent Layers

| Component | Question addressed | Example |
| --- | --- | --- |
| Route | Which next hop or network destination should the packet be sent to? | Destination \`10.40.0.0/20\` goes to the subnet in Tokyo. |
| VPC firewall rule / firewall policy | Is traffic allowed based on direction, source, destination, protocol, port, and target? | Allow TCP 5432 only from the application VM group to the required database group. |
| Network tag / service account target | Which VMs does the firewall rule target? | Target a backend VM group instead of the entire VPC. |
| IAM | Who has permission to manage network configuration or call Google Cloud APIs? | The network team can edit firewalls; the app team can only view configuration. |
| Application/OS rules | Does the process accept the request? | PostgreSQL requires user authentication and database permissions. |

Traditional VPC firewall rules have network scope and can affect target VMs across multiple regions; they do not automatically isolate policies simply because you created two subnets in two regions. Therefore, you must proactively restrict **source**, **target**, ports, and applications. Some advanced firewall capabilities have different levels and enforcement mechanisms, so you must select the right product.

### 3.3. Static Routes, Default Route, and Dynamic Routes

In addition to subnet routes, you may encounter:

- **Static routes:** statically configured destination and next hop for purposes such as steering traffic through a virtual network appliance or a supported connection path.
- **Default route:** typically the destination \`0.0.0.0/0\` with the default Internet gateway as the next hop, depending on network configuration. This route **does not automatically grant a public IP** or guarantee that every VM can reach the Internet.
- **Dynamic routes:** learned/exchanged via **Cloud Router** from supported connections such as Cloud VPN or Cloud Interconnect, with effective scope depending on the dynamic routing mode.

In Google Cloud, **Cloud Router is regional**, while the VPC has a **dynamic routing mode** setting. With **regional** vs. **global** mode, the scope within which dynamic routes take effect and information is advertised over BGP differs. You must consult current dynamic routing documentation when deploying hybrid or multi-region setups; do not assume that because a VPC is global, every dynamic route automatically appears in all regions.

Subnet routes differ from administrator-created static routes: subnet routes are system-managed per subnet and are not objects to be arbitrarily deleted while keeping the subnet functioning normally.

## 4. Internal Traffic and the Internet: Services You Must Distinguish

A VM's internal address, its path to the Internet, and connectivity to Google Cloud services address different needs. Placing a VM in a subnet is only the first step of the design.

### 4.1. Private IP, External IP, and Cloud NAT

A VM can have an internal IP in a subnet **without an external IP**. This is a common choice for backends or processing machines that do not need to receive direct connections from the Internet. However, if the VM needs to download updates from a public repository or call an API outside Google Cloud, an appropriate egress path must exist.

**Cloud NAT** can provide address translation for eligible outbound connections from resources without external IPs. With Public NAT, a Cloud NAT design is tied to a **region**, a **Cloud Router**, and designated subnets/IP ranges. Cloud NAT does not automatically create a public endpoint for the Internet to initiate inbound connections to the VM.

~~~mermaid
flowchart LR
    VM["VM without external IP<br/>subnet region A"] --> RT["Valid egress route"]
    RT --> NAT["Public Cloud NAT<br/>region A"]
    NAT --> NET["External Internet service"]
    USER["Internet user"] -. "Does not create inbound connection via NAT" .-> VM
~~~

Cloud NAT is distinct from a firewall: address translation or having a default route is not enough if an egress policy blocks traffic. Similarly, a regional Cloud NAT in region A **does not by default** directly serve resources located in region B; you need to verify NAT configuration, subnet scope, and the appropriate product per region.

### 4.2. Private Google Access

**Private Google Access** is a capability that allows eligible resources, such as VMs with only internal IPs, to access supported Google APIs and services through a product-permitted path. This setting is associated with the subnet and also depends on DNS, routing, and firewalls.

Private Google Access **does not turn every Internet site into an internal service**. For example, allowing access to certain Google Cloud APIs does not mean a VM can download libraries from an external website without another Internet egress path. You must verify access scenarios for \`private.googleapis.com\`, \`restricted.googleapis.com\`, or corresponding product mechanisms if the organization enforces strict data/network requirements.

### 4.3. Cloud Run and GKE Use the VPC Differently

- **Compute Engine:** A VM has a NIC attached to an appropriate subnet in the region of the zone where the VM runs.
- **GKE:** Clusters and nodes use the VPC network according to the deployment model; with **VPC-native**, Pod and Service addresses are typically organized using secondary ranges, with allocation details depending on GKE configuration.
- **Cloud Run:** Cloud Run is a regional serverless service. **Do not picture a Cloud Run container as a VM with a permanent NIC in a subnet.** When egress to internal VPC addresses is needed, mechanisms such as **Direct VPC egress** or a **Serverless VPC Access connector** are available depending on supported features/regions.
- **Cloud SQL:** Can provide a private connection path depending on configuration; you must check **private services access**, the connection mechanism, and the data region. Simply creating a VPC subnet does not make Cloud SQL automatically appear inside that subnet's range.

Example: a Cloud Run service in Singapore needs to call a database over a private IP. You must determine which VPC connectivity method the service supports, configure egress networking in the appropriate region, set up firewall rules and routing, and verify how to reach the database's private IP. If the service is placed in another region, cross-region latency and traffic cost become design factors.

## 5. How Does One Multi-Region VPC Differ from Multiple Connected VPCs?

Not every application group belongs in the same VPC. When there are requirements for environment isolation, separation of duties, corporate connectivity, or separating trust zones, the designer must choose an appropriate network structure.

| Model | Strengths | Conditions and limitations |
| --- | --- | --- |
| **Single VPC, multiple regional subnets** | Shared logical network design; automatic subnet routes for ranges belonging to the VPC; easy to organize connectivity between applications in the same administrative domain. | Must control cross-region firewalls, shared IP planning, and the blast radius of VPC administrative permissions. |
| **Multiple independent VPCs** | Clearer isolation of addressing, network configuration, and administrative responsibilities. | By default, there is no direct internal IP connectivity between VPCs; integration requires a connectivity solution. |
| **VPC Network Peering** | Internal IP connectivity between two VPCs per peering rules; keeps VPCs separate. | Non-transitive; requires checking IP ranges, route exchange, quotas, and firewalls on both sides. |
| **Shared VPC** | The VPC and subnets are centrally managed in a **host project**, while resources in authorized **service projects** can use the shared network. | Requires setting up permissions, host/service project associations, governance processes, and appropriate organization structure; does not merge projects into a single project. |
| **Cloud VPN / Cloud Interconnect** | Connects to systems outside Google Cloud or networks requiring dedicated links. | Requires configuring connections, BGP/routes, security, HA, regions, and cost; unlike automatic subnet connectivity within the same VPC. |

### 5.1. When Does a Cross-Region VPC Make Sense?

For example, a company centrally manages an internal application suite with a single responsible network team and wants to run redundancy in Singapore and Tokyo. A custom mode VPC with two regional subnets helps:

1. Allocate addresses per region within a unified plan.
2. Connect workloads internally within the same VPC without building separate peering between those two subnets.
3. Apply consistent firewall policies and network operations while differentiating targets/sources by workload group.
4. Add new subnets when serving users in new regions, after reviewing IPs, security, and cost.

However, sharing a VPC can create a **large administrative blast radius**: a misconfigured firewall or route change can affect multiple regions. IAM permissions must be separated and network review processes enforced.

### 5.2. When Should You Separate VPCs?

Separating VPCs is often appropriate when environments have different trust levels, independent operating organizations, different egress control requirements, or need to isolate configuration risk. For example, an experimental research environment receiving external code should not naturally be treated as sharing the same trust domain as applications holding production data.

Do not confuse **project separation** with **network separation**. Two projects can share a network via Shared VPC; conversely, one project can contain multiple independent VPCs. IAM permissions, firewalls, connection flows, and data classifications must be explicitly defined.

### 5.3. Shared VPC for Multiple Projects

An enterprise architecture might look like this:

~~~mermaid
flowchart TB
    O["Organization"]
    O --> H["Host project: net-prod<br/>manages Shared VPC"]
    O --> S1["Service project: checkout-prod"]
    O --> S2["Service project: catalog-prod"]
    H --> V["Global Shared VPC"]
    V --> A["Subnet app-sg — region A"]
    V --> B["Subnet app-jp — region B"]
    S1 -. "Uses authorized subnet" .-> A
    S2 -. "Uses authorized subnet" .-> B
~~~

Network infrastructure belongs to the host project; workloads can reside in service projects. The network administration team controls subnets/routes/firewalls per granted permissions, while development teams are only allowed to deploy resources onto appropriate subnets. This provides **separation of duties** between network administration and workload administration while maintaining a shared addressing and network plan.

Shared VPC does not replace security principles. Someone permitted to create a VM on a subnet should not automatically be able to modify the entire VPC's firewalls or grant network permissions to others.

### 5.4. VPC Peering and Transitivity Limits

When two VPCs are peered, their subnets can be routed across the peering connection under supported conditions. However, if:

- VPC A peers with VPC B;
- VPC B peers with VPC C;

this **does not mean A can reach C through B**. VPC Network Peering does not act as an automatic transitive router between all VPCs. A system requiring A↔C connectivity must be designed with an appropriate connectivity model and have all security policies thoroughly verified.

You must check for **IP overlap** before establishing peering. You cannot rely on firewalls to fix a routing plan with incompatible network ranges. The firewalls of the two networks are also not treated as a single policy automatically shared after peering.

## 6. Designing Networks for Latency, Availability, and Cost

A global VPC architecture does not turn all cross-region traffic into local communication. For real-time workloads, choosing subnet/application placement requires balancing both the data path and recovery objectives.

### 6.1. Placing Frequently Communicating Components Together

Suppose the frontend is in Singapore, the API is in Singapore, but the database is in Tokyo. The two regions can communicate within the same VPC over private IPs if routes/firewalls are correct, yet sequential cross-region queries still incur network transmission time. If the API calls the database multiple times per request, latency accumulates.

An appropriate design may place the API close to the database for chatty operations, then distribute traffic to users using an appropriate load balancing model. This should be verified using **end-to-end p95/p99** and inter-service call counts, rather than merely measuring ping between two VMs.

### 6.2. Zonal and Regional Redundancy

Because a subnet has regional scope, it can be used by VMs in different zones within the same region. This allows a group of VMs distributed across multiple zones in the same region to operate together on the appropriate subnet.

Losing an entire region is a different class of failure: the global existence of a VPC does not automatically move VMs, GKE nodes, or data to another region. To recover in region B, you typically must prepare:

- Subnets and sufficiently large IP ranges in region B; appropriate firewall rules and connectivity paths.
- Compute/GKE/Cloud Run, load balancers, or traffic-shifting components per design.
- Data backup/replication mechanisms and data residency compliance conditions.
- Standby service startup procedures, IAM configuration, secrets, quotas, and monitoring.
- Testing of **RTO** (Recovery Time Objective) and **RPO** (Recovery Point Objective) according to business needs.

**A global VPC supports organizing multi-region connectivity; it does not automatically create a highly available multi-region application system.**

### 6.3. Understanding Network Costs

A VPC does not incur charges merely for existing in the same way a continuously running VM does, but traffic and related network services can incur costs:

| Component | Items to estimate |
| --- | --- |
| Inter-region data transfer | Traffic between backends, databases, replication, or backups; check pricing tables by specific direction and service. |
| Cloud NAT | Charges per configuration and processed data depending on NAT type, plus associated outbound data charges. |
| Load balancing | Charges for load balancing components, rules/processing, and data per specific product. |
| Cloud VPN / Interconnect | Tunnel/attachment charges, data transfer, locations, and redundancy configuration. |
| Logging, Flow Logs, monitoring | Log/metric volume and storage, processing, or analysis charges per configuration. |

Do not assume that internal IPs within a single VPC carry free data transfer between regions. You must consult current pricing tables and measure actual traffic by direction, location, and connection type.

## 7. Example: Creating a Custom Mode VPC and Regional Subnets with gcloud

This section presents a hands-on exercise applicable in an authorized test project. **Commands that create VPCs and subnets are write operations that alter network configuration**; run them only in an authorized project and after checking IP ranges against existing network plans. In this example, we design a VPC for production with subnets in Singapore and Tokyo.

### 7.1. Defining the Plan Before Creation

Assumptions:

| Parameter | Example value |
| --- | --- |
| Project | \`PROJECT_ID\` — replace with actual project ID |
| VPC | \`prod-vpc\`, subnet mode = custom |
| Dynamic routing mode | Regional, as the example does not yet require global BGP exchange |
| Subnet in Singapore | \`prod-app-sg\` — \`asia-southeast1\` — \`10.20.0.0/20\` |
| Secondary ranges for GKE in Singapore | \`pods\` = \`10.21.0.0/16\`; \`services\` = \`10.22.0.0/20\` |
| Subnet in Tokyo | \`prod-app-jp\` — \`asia-northeast1\` — \`10.40.0.0/20\` |

This diagram is for learning purposes and does not imply these two regions are the right choice for every enterprise. You must verify service location availability, data residency requirements, cost, and quotas before real-world deployment.

### 7.2. Creating a Global VPC

~~~bash
# Select the right test project (replace PROJECT_ID with actual value)
gcloud config set project PROJECT_ID

# Create a custom mode VPC without requiring Google Cloud to auto-create subnets
gcloud compute networks create prod-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=regional
~~~

The VPC \`prod-vpc\` is a global resource. At the moment of creation, **custom mode does not automatically generate regional subnets**; you need to create each subnet in the regions you plan to use.

### 7.3. Creating the Subnet in Singapore

~~~bash
gcloud compute networks subnets create prod-app-sg \
  --network=prod-vpc \
  --region=asia-southeast1 \
  --range=10.20.0.0/20 \
  --secondary-range=pods=10.21.0.0/16,services=10.22.0.0/20 \
  --enable-private-ip-google-access
~~~

Meaning:

- \`--network=prod-vpc\`: the subnet belongs to the global VPC created earlier.
- \`--region=asia-southeast1\`: specifies the regional scope of the subnet.
- \`--range=10.20.0.0/20\`: primary IPv4 range for resources assigned a primary IP from the subnet.
- \`--secondary-range=...\`: two named secondary ranges that can be used for an appropriate GKE configuration.
- \`--enable-private-ip-google-access\`: enables the corresponding Private Google Access feature for the subnet; actual effectiveness also depends on DNS, route, firewall, and target service configuration.

Creating secondary ranges **does not yet create a GKE cluster** and does not automatically allocate Pods. Mapping ranges to a cluster must be performed when configuring a VPC-native cluster per GKE documentation.

### 7.4. Creating the Subnet in Tokyo

~~~bash
gcloud compute networks subnets create prod-app-jp \
  --network=prod-vpc \
  --region=asia-northeast1 \
  --range=10.40.0.0/20
~~~

The Tokyo subnet still belongs to the **same \`prod-vpc\` network**, but has its own primary range and is a resource of the \`asia-northeast1\` region.

### 7.5. Inspecting with Read-Only Commands

~~~bash
# VPC network and subnet / routing mode
gcloud compute networks describe prod-vpc

# List of subnets in the project and corresponding regions
gcloud compute networks subnets list

# Details of the Singapore subnet
gcloud compute networks subnets describe prod-app-sg \
  --region=asia-southeast1

# Routes that the Compute Engine routes list command can display
gcloud compute routes list

# VPC firewall rules in the project
gcloud compute firewall-rules list
~~~

Verify that both \`prod-app-sg\` and \`prod-app-jp\` reference \`prod-vpc\`, yet have separate regions and primary ranges. Also verify that subnet routes have been automatically created corresponding to the subnets' IP ranges.

Do not treat \`gcloud compute routes list\` as a complete snapshot of every effective **dynamic route** in all cases. When Cloud Router/BGP is present, you must additionally check Cloud Router status information, peer configurations, dynamic routing mode, and appropriate connectivity testing tools.

### 7.6. Firewalls Must Be Configured Before Testing Communication

In a new custom VPC, **implied firewall rules** still take effect per Google Cloud mechanisms: ingress is denied unless a matching allow rule exists, while egress is allowed by default unless overridden by another rule or policy. Do not use the pre-existing rules of the **default VPC** as assumptions for a custom VPC you create.

If you want VMs in the two subnets to communicate over TCP, you need to design a restricted allow rule:

- Which sources are allowed to connect? For example, only the application subnet range in Singapore.
- Which destinations can receive traffic? For example, database VMs with a designated service account or network tag.
- Which ports and protocols? For example, TCP 5432 for a PostgreSQL application, if that is indeed the port used.
- Does communication genuinely need to cross regions? If only data replication is needed, a separate managed replication mechanism might be chosen.
- Are there organization-level policies, deny rules, OS firewalls, or application authorization mechanisms blocking the connection?

Do not create a \`0.0.0.0/0\` ingress rule for all ports just to "verify the network works." Access must be restricted to the workload groups that genuinely need to communicate.

## 8. Analyzing Common Design Errors

| Symptom | Possible cause | Troubleshooting direction |
| --- | --- | --- |
| Cannot select the Singapore subnet when creating a VM in Tokyo | Subnets are regional; a VM in a Tokyo zone cannot use a subnet in Singapore. | Check the VM's zone and the subnet's region; create/select a subnet in the same region. |
| Cannot create a subnet because the IP range overlaps | Primary/secondary CIDR conflicts with a range in the same VPC or violates product conditions. | Check all existing subnet ranges before choosing another address. |
| Two VMs in different subnets of the same VPC cannot connect over TCP | Ingress/egress firewall, OS firewall, service not listening, wrong IP, or policy. | Check routes, effective firewall policies, ports, and process configuration; try Connectivity Tests when supported. |
| A VM without an external IP cannot access the Internet | Missing egress/NAT path, default route, DNS, firewall, or NAT configured in the wrong region/subnet. | Check the access target, Public NAT, Cloud Router/NAT, routes, firewalls, and DNS. |
| A VM without an external IP fails when calling Google APIs | Private Google Access not enabled, or DNS/route/firewall/API permissions not properly configured. | Check subnet configuration, DNS for service domains, paths, and IAM/service accounts. |
| A route learned from VPN exists in one region but is not effective in another region | Dynamic routing mode or Cloud Router/BGP configuration does not meet requirements. | Check regional/global mode, BGP advertisements, and learned routes. |
| Peering A↔B, B↔C exists, but A cannot reach C | Peering is not automatically transitive. | Design an A↔C connection or an appropriate transit/routing solution. |
| GKE scales nodes up but cannot increase Pod count | Insufficient IPs in the secondary Pod range or allocation/quota limits. | Check Pod range size, Pods-per-node settings, and supported scaling capacity. |
| VPC is global, yet the service still goes down during a region outage | VMs, clusters, databases, or backends are still running solely in the impacted region. | Design workload, data, and traffic redundancy and test DR separately. |
| Network charges increase when adding a region | Cross-region traffic, backup/replication, NAT, load balancers, or VPN incur additional charges. | Analyze billing by service and data direction; measure actual traffic. |

### 8.1. Sequence for Investigating a Failing Network Flow

For a \`VM-A → VM-B\` connection, follow this order:

1. **Identify source and destination:** Project ID, VPC, subnet, region, zone, IP address, port, protocol, and listening service.
2. **Check the path:** Does the VM have a NIC in the right VPC/subnet? Does the destination range have a subnet route or supported route? Is a dynamic routing mode involved?
3. **Check policies:** Firewall rules/policies, network tags/service accounts, ingress/egress direction, and priority order.
4. **Check the destination side:** Is the VM running, is the application listening on the right IP/port, OS firewall, database user and authentication if needed.
5. **Observe with tools:** VPC Flow Logs, Firewall Rules Logging, Connectivity Tests, or supported/configured service logs.
6. **Verify after fixing:** Allow only the intended flow, then test that unauthorized destinations remain blocked.

**VPC Flow Logs** have scope, collection modes, and cost depending on configuration; logs may be sampled and should not be assumed to be a complete record of every packet. **Connectivity Tests** help analyze intended paths and certain live test scenarios depending on current features; results must be cross-checked against the target application state.

## 9. Hands-On Exercise: Network Design for an Online Learning Platform

A company is deploying a Java learning platform on Google Cloud:

- Learners are primarily in Southeast Asia, with a group accessing from Japan.
- The API runs on Cloud Run; background jobs may run on Compute Engine or GKE.
- Learning data is stored in Cloud SQL and Cloud Storage in accordance with data residency policies.
- The system needs to separate dev and prod environments, with partial redundancy if the primary region fails.
- The network team wants to centrally manage IP ranges and policies; the application team is responsible for deployment.

**Requirement 1 — Draw the architecture.** Choose one of two options: a single production VPC with subnets in two regions; or Shared VPC for service projects. Explain the **global** scope of the VPC, the **regional** scope of subnets, and the placement of VMs/GKE/Cloud Run.

**Requirement 2 — Address planning.** Use non-overlapping private IPv4 ranges for each region's application subnet, adding Pod/Service ranges if choosing VPC-native GKE. Reserve IPs for 2x growth; clearly state the rationale for CIDR sizes and limits that must be verified.

**Requirement 3 — Packet path.** For a VM in Singapore calling another VM in Tokyo, specify the routes, firewall policies, and where latency/network charges may arise. Answer whether VPN or VPC Peering is needed for two subnets in the same VPC.

**Requirement 4 — Egress.** A VM without an external IP needs to call a Google Cloud API and an external code repository on the Internet. Propose separate solutions for each need; distinguish Private Google Access from Cloud NAT.

**Requirement 5 — Availability.** Describe what happens if one Singapore zone fails, and what happens if the entire Singapore region fails. Clearly state why merely having a global VPC and a subnet in Tokyo is not enough to ensure standby API/DB availability.

**Requirement 6 — Security and operations.** Designate which team manages the VPC/firewalls, which team deploys workloads on subnets, and which team reads Flow Logs. Propose three connectivity security test cases before moving the system to production.

### Evaluation Guidelines

A well-founded proposal demonstrates that:

- A global VPC can serve multiple regions; each regional subnet has a clear, non-overlapping CIDR.
- VMs attach to subnets in the right region; GKE and Cloud Run are connected in the manner supported by each product.
- Internal routes and firewalls are distinguished; broad VPC-wide allow rules are not used merely to resolve errors.
- Internet egress is intentionally designed; Private Google Access is not confused with a general Internet outbound path.
- Redundancy design addresses workloads, data, IAM, quotas, traffic, RTO/RPO, and storage locations, beyond just the network diagram.
- Latency, bandwidth, cross-region traffic, and cost are measured/estimated from representative workloads.

### Self-Check Questions

**1. A VPC has global scope, so can one subnet contain VMs from two regions?**  
No. A subnet belongs to one region; VMs in zones within that same region can use that subnet if configured appropriately.

**2. Do two subnets in two regions within the same VPC need peering to communicate over internal IP?**  
No. The VPC has subnet routes to route between subnet ranges; actual access still depends on firewalls and other layers.

**3. Does placing a Cloud Router in one region mean dynamic routes always work automatically in every region of the VPC?**  
No. You must consider regional/global dynamic routing mode, how routes are learned/advertised, and supported limitations.

**4. Does enabling Cloud NAT allow Internet users to initiate connections to a VM without an external IP?**  
No. Public Cloud NAT serves eligible egress flows and return traffic; it is not a service for publishing inbound endpoints.

**5. Does moving from one subnet to two regional subnets already achieve multi-region availability?**  
Not yet. You must deploy/replicate workloads and data, steer traffic, test failover, and meet RTO/RPO objectives.

## Google Cloud Reference Documentation

- **VPC networks:** https://cloud.google.com/vpc/docs/vpc — VPC concepts, subnet modes, addressing, and global/regional scope.
- **VPC subnets:** https://cloud.google.com/vpc/docs/subnets — primary/secondary ranges, limits, Private Google Access, and subnet operations.
- **VPC routes:** https://cloud.google.com/vpc/docs/routes — subnet routes, static routes, and dynamic routes.
- **VPC firewall rules:** https://cloud.google.com/firewall/docs/firewalls — traffic control model and firewall principles.
- **Cloud Router:** https://cloud.google.com/network-connectivity/docs/router/concepts/overview — BGP and dynamic routing for network connectivity.
- **Cloud NAT:** https://cloud.google.com/nat/docs/overview — NAT behavior, regional nature, and outbound connectivity.
- **Shared VPC:** https://cloud.google.com/vpc/docs/shared-vpc — host/service projects and delegated network usage.
- **VPC Network Peering:** https://cloud.google.com/vpc/docs/vpc-peering — VPC connectivity and route/addressing limits.
- **Private Google Access:** https://cloud.google.com/vpc/docs/private-google-access — Google APIs access capabilities and network requirements.
- **VPC Flow Logs:** https://cloud.google.com/vpc/docs/using-flow-logs — observing network traffic.
- **Network Connectivity Tests:** https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview — path analysis and connectivity testing.
- **Network pricing:** https://cloud.google.com/vpc/network-pricing — looking up pricing tables and billing scenarios.

Addressing rules, supported region lists, dynamic routing behavior, serverless connectivity options, and pricing are subject to change. For real-world deployments, cross-check product-specific documentation, verify organization policies, and test actual paths before serving user traffic.
