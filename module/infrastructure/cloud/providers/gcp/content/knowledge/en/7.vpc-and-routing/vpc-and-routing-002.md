# Custom Mode VPC and IP Address Planning

An application team creates its first VPC and picks address ranges by intuition. A few months later, the team has to connect to the office network over Cloud VPN and build a GKE cluster in another region; the network addresses overlap, Pods run out of IPs, and firewall rules and routes have to be reworked in bulk. These failures rarely stem from a single VM creation command, but rather from a lack of **IP planning at network design time**.

In Google Cloud, a **Custom mode VPC** lets the team decide which regions subnets are created in and which CIDRs they use. This is a key choice in the **VPC and Routing** chapter of the **CLOUD_PROVIDERS_GCP** module: from project organization, IAM, and VPCs to operating Compute Engine, GKE, Cloud Run, storage/databases, and deployment scenarios requiring secure, scalable, automatable, observable, and cost-controlled connectivity.

After this lesson, you will be able to:

- Distinguish between global VPCs, regional subnets, zones, and subnet creation modes.
- Read and calculate IPv4 range capacity in CIDR notation; identify IPs reserved by Google Cloud.
- Design an **IP address plan** across multiple environments, regions, and development teams.
- Reserve primary ranges for VMs/GKE nodes and secondary ranges for GKE Pods/Services when needed.
- Detect CIDR overlap risks when connecting via VPC Peering, Shared VPC, or on-premises.
- Create, inspect, and expand a Custom mode VPC using the Console, `gcloud`, and Terraform.

## 1. VPC, Subnets, and Regions in Google Cloud

A **Virtual Private Cloud (VPC)** is a virtual network that defines connectivity, routing, firewalls, and subnets for Google Cloud resources. Unlike many traditional systems that deploy networks per location, **a Google Cloud VPC network is a global resource**; **a subnet is a regional resource**.

~~~text
Project: shop-network-prod
└── VPC: prod-custom                 (global)
    ├── Subnet: prod-sg-app          (region asia-southeast1)
    │   ├── VM in zone asia-southeast1-a
    │   ├── VM in zone asia-southeast1-b
    │   └── GKE nodes/pods in appropriate zones
    └── Subnet: prod-tokyo-app       (region asia-northeast1)
        └── VMs and GKE nodes in this region
~~~

| Component | Scope | Planning implications |
|---|---|---|
| VPC network | Global | A single VPC can contain subnets across multiple regions, with no mandatory "VPC-wide CIDR" required upfront. |
| Subnet | Regional | Has a primary IPv4 range and optionally secondary IPv4 ranges; eligible resources in multiple zones of the same region can use it. |
| Compute Engine VM | Zonal | The NIC obtains its primary internal IP from a subnet in the region containing the VM's zone. |
| GKE VPC-native | Zonal or regional cluster per configuration | Nodes typically use the primary range; Pods use a subnet secondary range, while Services depend on the allocation model. |
| Cloud Run | Regional | Connects to the VPC when private resources are needed; IP usage depends on Direct VPC egress or a connector. |
| Cloud Router | Regional | Exchanges dynamic routes with other networks; the VPC's dynamic routing mode determines the scope of received dynamic routes. |

When a VPC has subnets in different regions, Google Cloud creates corresponding **subnet routes** to route the subnets' address ranges within the VPC. However, having a route is not enough for applications to communicate: firewalls and service permissions must still allow the traffic.

## 2. How Do Auto Mode and Custom Mode Differ?

Google Cloud has two subnet creation modes:

| Criterion | Auto mode VPC | Custom mode VPC |
|---|---|---|
| At VPC creation | IPv4 subnets are automatically created across regions | **No subnets are created automatically** |
| Address ranges | Auto-created subnets reside in `10.128.0.0/9` per Google Cloud conventions | The designer selects valid CIDRs for each subnet |
| When Google Cloud adds a new region | Automatically adds a new subnet per service behavior | A new subnet exists only when an administrator explicitly creates one |
| Subnet placement control | Less flexible with automatically created subnets | Flexible over regions, counts, names, and CIDRs |
| Hybrid/peering connectivity | May conflict with existing networks | Easier to assign non-conflicting address ranges when planned |
| Best suited for | Quick start, small experiments | Enterprise platforms, multiple projects/environments, long-term growth plans |

**Custom mode is a subnet creation mode; it does not mean a "custom" VPC is automatically secure or has special routes.** You still need to configure firewalls, IAM, Cloud NAT, hybrid connectivity, and other protections as required.

You can **convert from Auto mode to Custom mode**, but you cannot convert Custom mode back to Auto mode. Upon conversion, subnets already created by Auto mode remain; the conversion does not automatically renumber existing CIDRs to new addresses. If a default network with unsuitable ranges is already in use, consider building a new network and migrating workloads according to plan.

**Note:** A new project may come with a `default` Auto mode VPC if the organization has not disabled default network creation. In centralized governance models, consider disabling automatic creation of the default VPC and using only approved VPCs.

## 3. CIDR: Reading IP Ranges and Calculating Capacity

CIDR (Classless Inter-Domain Routing) represents a network range in the form `address/prefix_length`, such as `10.32.0.0/20`. IPv4 has 32 bits; `/20` means 20 bits belong to the network prefix and the remaining 12 bits are for addresses within the range.

Number of IPv4 addresses in a CIDR:

\[
\text{Number of IPv4 addresses} = 2^{32-p}
\]

where `p` is the prefix length. In a standard Google Cloud **primary IPv4 subnet**, **4 addresses are unusable**: the first address, the next gateway address, the second-to-last address, and the last address of the range.

| CIDR | Total IPv4 | Usable primary IPs for standard resources | Example range |
|---|---:|---:|---|
| `/29` | 8 | 4 | `10.1.1.0–10.1.1.7` |
| `/28` | 16 | 12 | `10.1.1.0–10.1.1.15` |
| `/24` | 256 | 252 | `10.1.1.0–10.1.1.255` |
| `/20` | 4,096 | 4,092 | `10.32.0.0–10.32.15.255` |
| `/16` | 65,536 | 65,532 | `10.32.0.0–10.32.255.255` |
| `/14` | 262,144 | 262,140 | `10.40.0.0–10.43.255.255` |

Example with primary subnet `10.32.1.0/24`:

~~~text
10.32.1.0      network address          (not assigned to VMs)
10.32.1.1      virtual default gateway  (not assigned to VMs)
10.32.1.2      first standard IP
...
10.32.1.253    last standard IP
10.32.1.254    reserved by Google Cloud
10.32.1.255    broadcast address        (not assigned to VMs)
~~~

**Only apply the subtract-4 rule to primary IPv4 ranges.** Google Cloud does not reserve those four addresses in **secondary IPv4 ranges**; they are used for alias IPs rather than the same primary VM IP allocation mechanism. Actual usable capacity still needs to account for the needs and limits of the consuming service.

### CIDR Boundaries and Alignment

A CIDR must start on an exact prefix boundary. For example, `10.32.0.0/20` is valid; `10.32.5.0/20` lies *within* that range but is not the starting address of a `/20` block. When building an IPAM, represent normalized CIDRs and check for overlap using networking tools, not just string comparison.

**RFC 1918 private IPv4 ranges**:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

Google Cloud also supports several other IPv4 ranges permitted for internal use under specific conditions. However, for enterprise networks connecting multiple systems, prioritize centralized planning within RFC 1918 and avoid ranges conflicting with Docker, user VPNs, or on-premises systems. Do not treat a "private" address as proof that all machines are permitted to reach one another.

## 4. Address Planning Principles

Before creating a Custom mode VPC, gather information from **all networks that may need connectivity in the future**, including:

1. Office subnets, data centers, and partner networks via Cloud VPN/Cloud Interconnect.
2. Existing VPCs in other projects, including Shared VPC and VPC Peering.
3. Networks for development/staging/production environments and required regions.
4. Ranges used for GKE nodes, Pods, Services, and specialized components like private services access.
5. Ranges used by container runtimes or VPNs on developer machines; for instance, avoid colliding with local bridge networks if traffic must traverse a VPN.
6. Projected growth in VM count, GKE node count, Pods per node, number of regions, and services requiring private IPs.

Core principles:

- **No overlapping** primary/secondary subnets within the same VPC. If VPC Peering is planned, subnets across the two peered VPCs must also have non-overlapping CIDRs.
- **Reserve blocks by environment** to prevent mixing dev/prod and make identification easy in logs, firewalls, and IPAM.
- **Leave intentional whitespace** for subnet expansion, new regions, Pods, or new services.
- **Size prefixes based on real demand**, rather than defaulting to `/16` for every small group; wide address space is also a resource that must be managed.
- **Separate "reserved for planning" entries from actual subnets**: reserving a supernet in IPAM does not automatically create a subnet or route in the VPC.
- **Track from a central IPAM**, recording environment, region, VPC, project, subnet, owner, and allocation status. Never create CIDRs outside the registry.

### Why Shouldn't You Just "Pick 10.0.0.0/16" for Every VPC?

Two independent VPCs can temporarily share the same private range when they do not exchange traffic. But when connecting via **VPC Network Peering**, Google Cloud requires subnet routes not to overlap. Cloud VPN/Interconnect also runs into routing issues if the on-premises network has a colliding CIDR. Today's experimental project may become tomorrow's integrated service; therefore, check interconnectivity early.

## 5. Example IP Plan for Two Environments and Two Regions

Suppose a company deploys backends in Singapore and Tokyo. Production and nonproduction use separate VPCs; the platform team reserves address space for shared services and the on-premises network.

**High-level allocation in the IPAM ledger** (not yet VPC configuration):

| Reserved scope | Block | Notes |
|---|---|---|
| Production | `10.32.0.0/11` | From `10.32.0.0` to `10.63.255.255` |
| Nonproduction | `10.64.0.0/11` | From `10.64.0.0` to `10.95.255.255` |
| Shared services | `10.96.0.0/12` | Reserved for future shared infrastructure |
| On-premises | `172.20.0.0/16` | Assumed verified as non-overlapping by the network team |

Within each VPC, allocate a **primary range for VMs/nodes**, a **secondary range for Pods**, and a **secondary range for Services if choosing user-managed allocation**:

| VPC | Region | Subnet | Primary (VM/node) | Secondary Pod | Secondary Service |
|---|---|---|---|---|---|
| `prod-custom` | Singapore: `asia-southeast1` | `prod-sg-app` | `10.32.0.0/20` | `10.40.0.0/14` | `10.44.0.0/20` |
| `prod-custom` | Tokyo: `asia-northeast1` | `prod-tokyo-app` | `10.32.16.0/20` | `10.48.0.0/14` | `10.52.0.0/20` |
| `nonprod-custom` | Singapore: `asia-southeast1` | `nonprod-sg-app` | `10.64.0.0/20` | `10.72.0.0/14` | `10.76.0.0/20` |
| `nonprod-custom` | Tokyo: `asia-northeast1` | `nonprod-tokyo-app` | `10.64.16.0/20` | `10.80.0.0/14` | `10.84.0.0/20` |

This is an **illustrative template** for learning how to organize address space, not a fixed recommendation for every application. The `/14` Pod ranges are quite large and only suitable if scaling demands match; teams should size Pod CIDRs from expected node counts and the IP allocation parameters of the GKE version in use.

~~~text
Company IPAM
├── 10.32.0.0/11  Production
│   ├── 10.32.0.0/20   SG nodes/VMs
│   ├── 10.40.0.0/14   SG Pods
│   ├── 10.44.0.0/20   SG Services (user-managed)
│   ├── 10.32.16.0/20  Tokyo nodes/VMs
│   ├── 10.48.0.0/14   Tokyo Pods
│   └── 10.52.0.0/20   Tokyo Services (user-managed)
├── 10.64.0.0/11  Nonproduction
│   └── Corresponding ranges allocated for SG and Tokyo
├── 10.96.0.0/12  Shared services (reserved)
└── 172.20.0.0/16 On-premises (assumed)
~~~

**Important:** `10.32.0.0/11` is a **planning/IPAM reservation block**, not a subnet range to be created as a single contiguous subnet. Each primary or secondary line is a separate CIDR, non-overlapping with the others. Unused space is held for future expansion.

### Why Divide by Region and Environment?

Two subnets in the **same VPC** in Singapore and Tokyo can communicate over system routing paths, though firewalls are still required. Two production and nonproduction VPCs are not connected by default just because they belong to the same Organization. If peering or hub connectivity is needed later, these ranges are already non-overlapping, eliminating a common obstacle.

Not every application team needs its own VPC. When multiple projects share a network operated by the platform team, **Shared VPC** can be used; CIDR design lives in the host project while service projects consume subnets via IAM and policies.

## 6. IP Planning for VPC-Native GKE

In **VPC-native GKE**, the main IP types are:

| Address type | Source | Purpose |
|---|---|---|
| **Node IP** | Subnet primary range | NIC address of the VM running the node |
| **Pod IP** | Secondary range for Pods (alias IP) | Assigned to Pods, managed per node/pod range |
| **Service ClusterIP** | Secondary range for Services *or* GKE-managed service range, depending on version/configuration | Virtual address to reach a Kubernetes Service |
| **Control plane** | Depends on control plane architecture and cluster type | Cluster management, with its own addressing/connectivity requirements |
| **Internal load balancer** | Typically uses an internal IP matching the subnet and LB type | Provides an internal endpoint |

In newer GKE versions, **Services can use a GKE-managed range** such as `34.118.224.0/20` instead of a user-declared secondary range. If that option is chosen, you do not necessarily need to create a secondary Service range as in the previous section's example. Decide based on **cluster version, Autopilot/Standard mode, and usability** for your actual configuration.

### Sizing a Pod Range Cannot Just Count Running Pods

In the VPC-native IPv4 model, GKE assigns a **CIDR block per node** for Pod IPs, depending on max Pods per node and cluster mode. For example, a common GKE Standard allocation is `/24` per node under default settings; Autopilot has different rules. Using a `/20` Pod range (4,096 addresses) does not equate to running exactly 4,096 Pods, because IPs are sliced into per-node blocks.

Hypothetical example:

~~~text
Pod secondary range 10.40.0.0/20 = 4,096 addresses
Assume each node is assigned a /24 block = 256 addresses
Theoretical max /24 blocks: 4,096 / 256 = 16
=> Roughly 16 nodes under the /24 assumption, excluding GKE limits and management overhead
~~~

This calculation is an **illustration to understand block allocation**, not a substitute for GKE capacity documentation. Check `maxPodsPerNode`, node zones, node pools, cluster limits, multi-Pod CIDR features, and autoscale headroom.

Things that are hard to change after creation:

- A primary subnet can be **expanded**, but cannot be shrunk or replaced with a different CIDR in the same subnet.
- A secondary range can be replaced/deleted when **no resources are still using it**; some active GKE configurations make this impossible without migrating/recreating the cluster.
- For VPC-native clusters, a user-provided Service range has modification constraints; in some scenarios you must create a new cluster if the initial choice was too narrow.
- If GKE auto-selects a secondary range, verify compatibility with IPAM and any networks planned for peering/hybrid connections.

Therefore, **reserve IP headroom for GKE growth before creating the cluster**, especially for the Pod range.

## 7. Issues When Connecting Other Networks

### VPC Network Peering

VPC Peering exchanges subnet routes between two VPCs according to service rules. For subnets using private IPv4:

- Subnet IPv4 ranges **must not overlap or contain one another** across peered VPCs.
- Peering is **non-transitive**: if A is peered with B and B is peered with C, A does not automatically have connectivity to C.
- Each VPC's firewalls must still allow the required traffic.
- Exporting/importing custom routes must be evaluated separately per feature and configuration.

Example: if VPC A already has subnet `10.32.0.0/16`, VPC B cannot create subnet `10.32.0.0/20` and successfully peer with A, because `/20` falls inside `/16`. Renaming the subnet does not resolve this conflict.

### Cloud VPN / Cloud Interconnect and On-Premises

When connecting on-premises via **Cloud VPN** or **Cloud Interconnect**, you must check both routes on Cloud Router and the peer's network. If the on-premises network already uses `10.40.0.0/16` and you allocate `10.40.0.0/14` for GKE Pods, traffic can collide severely even though node subnets do not overlap.

**Cloud Router** uses BGP to exchange dynamic routes in supported models. The **regional/global dynamic routing mode** setting governs how the network applies dynamic routes learned by Cloud Router. It does **not** determine whether subnets in two regions within the same VPC can connect; VPC subnet routes are a separate mechanism.

In hybrid designs, plan ahead for:

- Current and future subnet ranges on both sides.
- GKE Pod/Service ranges, systems using alias IPs, and Google-managed service addresses.
- Addresses used for Private Service Access, Private Service Connect, proxy-only subnets, or managed services if applicable.
- Routes advertised/learned via BGP, route priority, return paths, firewalls on both sides, and DNS.
- Availability when a tunnel or network region fails.

### Shared VPC

In the **Shared VPC** model, the *host project* holds the VPC/subnets while *service projects* use the shared subnets. CIDR management must be centralized in the host project; do not let each service project create its own subnet with the same range and assume they are sharing a network.

The network team can allocate a subnet to multiple teams and govern `roles/compute.networkUser` permissions on the subnet as needed. For workloads requiring production data protection, IAM, firewalls, and network configuration must still restrict traffic even within a shared VPC.

## 8. Guide to Creating a Custom Mode VPC via Console

Before taking action:

1. Select the appropriate **network project** and confirm billing and required APIs.
2. Confirm the VPC name, regions, subnet names, and CIDRs allocated from IPAM.
3. Verify CIDRs do not overlap with other subnets, peers, or on-premises.
4. Identify GKE, firewall, NAT, and Google API access requirements.
5. Ensure you have network/subnet management permissions in the target project; if using Shared VPC, follow the host project's governance process.

In **Google Cloud Console → VPC network → VPC networks → Create VPC network**:

1. Name the network, e.g. `prod-custom`.
2. Select **Subnet creation mode: Custom**.
3. Add subnet `prod-sg-app`, region `asia-southeast1`, primary IPv4 range `10.32.0.0/20`.
4. If preparing for VPC-native GKE with user-managed ranges, add secondary ranges `prod-sg-pods = 10.40.0.0/14` and `prod-sg-services = 10.44.0.0/20`.
5. Enable Private Google Access on the subnet when VMs without external IPs need to reach supported Google APIs/services.
6. Choose dynamic routing mode based on hybrid design; keep an appropriate setting if no Cloud Router exists yet.
7. Review firewall configuration. A Custom mode VPC does not include default "allow internal" firewall rules like the `default` VPC.
8. Create the VPC, then inspect the subnet list and system routes.

When creating a subnet for another region, choose **add subnet within the same VPC**—you do not need to create another VPC just to support the Tokyo region.

## 9. Hands-On `gcloud`: Creating and Verifying the VPC

The snippet below is a **Bash template**; run it only in an authorized test project. Commands creating VPCs/subnets and subsequent resources may incur usage charges when connected to billable services.

~~~bash
PROJECT_ID="my-network-project"
VPC="prod-custom"

gcloud config set project "$PROJECT_ID"

# Create a Custom mode VPC: no pre-generated subnets.
gcloud compute networks create "$VPC" \
  --subnet-mode=custom \
  --bgp-routing-mode=regional

# Subnet in Singapore; secondary ranges are for GKE
# when choosing user-managed Pod and Service ranges.
gcloud compute networks subnets create prod-sg-app \
  --network="$VPC" \
  --region=asia-southeast1 \
  --range=10.32.0.0/20 \
  --secondary-range=prod-sg-pods=10.40.0.0/14,prod-sg-services=10.44.0.0/20 \
  --enable-private-ip-google-access

# Second subnet in Tokyo within the SAME global VPC.
gcloud compute networks subnets create prod-tokyo-app \
  --network="$VPC" \
  --region=asia-northeast1 \
  --range=10.32.16.0/20 \
  --secondary-range=prod-tokyo-pods=10.48.0.0/14,prod-tokyo-services=10.52.0.0/20 \
  --enable-private-ip-google-access

# Read back the configuration.
gcloud compute networks describe "$VPC"
gcloud compute networks subnets list --network="$VPC"
gcloud compute networks subnets describe prod-sg-app \
  --region=asia-southeast1
gcloud compute routes list --filter="network:$VPC"
~~~

The values above are illustrative only. Check existing VPCs, subnets, and CIDRs before running to avoid duplicates or conflicts. `gcloud compute networks subnets list` and `describe` assist with post-verification, but checking overlap with **networks outside GCP** still requires an IPAM ledger and coordination with the network team.

### Firewall: Having a Route Does Not Guarantee Connectivity

A Custom mode VPC has implied firewall rules: **deny ingress** and **allow egress** at their respective scopes. Consequently, two VMs in the same VPC have routes to each other, yet ingress packets can still be dropped.

Example allowing only TCP port 8080 traffic from the Singapore subnet to VMs with the `app-server` network tag:

~~~bash
gcloud compute firewall-rules create allow-sg-app-8080 \
  --network=prod-custom \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=10.32.0.0/20 \
  --target-tags=app-server
~~~

This is an illustrative rule, not a complete production security configuration. Target VMs must carry the matching tag, and **hierarchical/global/regional firewall policies** can also affect the final verdict. Never open `0.0.0.0/0` for SSH or all ports just to test connectivity.

### Expanding a Subnet When Running Out of Addresses

Google Cloud allows **expanding the primary IPv4 range** of a subnet to a valid supernet if it does not conflict with other ranges. For instance, you might want to expand `10.32.0.0/20` to `10.32.0.0/19`, but that operation would encompass `10.32.16.0/20` already allocated to Tokyo in our example. **Therefore, such an expansion is invalid.**

To preserve expansion capability, leave an unused **adjacent block** at planning time. If ranges were packed tightly together, you may have to create another subnet and migrate or add resources appropriately rather than expanding the active subnet.

**A primary range cannot be shrunk** once expanded. Firewall rules, authorized networks, or external routes referencing the old CIDR must also be reviewed. Thus, resizing a subnet is a network change requiring review, not an ad-hoc experiment.

## 10. Declaring a Custom Mode VPC with Terraform

Infrastructure as Code keeps networks consistent across environments, allows reviewing CIDR changes in pull requests, and reduces the risk of manual subnet mistakes. Minimal example for a production VPC and one Singapore subnet:

~~~hcl
terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

variable "project_id" {
  type = string
}

resource "google_compute_network" "prod" {
  project                 = var.project_id
  name                    = "prod-custom"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "prod_sg_app" {
  project                  = var.project_id
  name                     = "prod-sg-app"
  region                   = "asia-southeast1"
  network                  = google_compute_network.prod.id
  ip_cidr_range            = "10.32.0.0/20"
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "prod-sg-pods"
    ip_cidr_range = "10.40.0.0/14"
  }

  secondary_ip_range {
    range_name    = "prod-sg-services"
    ip_cidr_range = "10.44.0.0/20"
  }
}
~~~

Before applying in a real environment:

- Run `terraform fmt`, `terraform validate`, and `terraform plan`.
- Cross-check every CIDR against the registry/IPAM and allocation history.
- Review subnet changes carefully, especially replace or delete operations that can cause outages.
- Protect Terraform state and use a pipeline identity with least-privilege IAM.
- With Shared VPC, place network resources in the host project and let service projects consume them via IAM; do not duplicate networks just because the application project changes.
- Keep firewall, Cloud NAT, Cloud Router/Hybrid connectivity, and monitoring configurations in separately managed or clearly linked modules.

Do not let multiple independent Terraform states manage the same network/subnet without clear resource ownership rules; that easily causes drift and conflicting changes.

## 11. Routing, NAT, and Service Access After Having an IP Plan

**Having an IP plan** does not mean resources can reach every destination. After creating subnets, distinguish between:

| Component | What does it solve? | Does not replace |
|---|---|---|
| **Subnet routes** | Routing between subnets within the same VPC | Firewalls and access permissions |
| **Static routes** | Selecting a next hop for specified destinations per GCP rules | DNS service and NAT mechanism |
| **Cloud Router/BGP** | Learning/advertising dynamic routes for supported hybrid connections | Firewall policies |
| **Cloud NAT** | Outbound NAT for eligible workloads without external IPs | A new route to the Internet or firewall allow rules |
| **Private Google Access** | Enables VMs without external IPs to reach supported Google APIs and services | General Internet connectivity |
| **Cloud DNS** | Resolving service names, including private zones | Network permissions and routing paths |

For example, a VM in `prod-sg-app` has no external IP but needs to download dependencies from the Internet. Enabling **Private Google Access** alone may not suffice; you need to evaluate **Cloud NAT**, the default route, egress firewalls, and DNS depending on the destination type. Conversely, if only reaching a Google API via a supported endpoint, Private Google Access/DNS configuration may satisfy the need without an external IP.

Do not create a static route overlapping a subnet route to "fix connectivity"; Google Cloud enforces priority rules and protects subnet routes. When traffic fails, check routes, firewalls, IAM/target service, and return paths in order.

## 12. Inspecting and Troubleshooting IP Issues

| Symptom | Common cause | How to check |
|---|---|---|
| Subnet creation reports CIDR overlap | Overlaps primary/secondary in the VPC or a peered VPC's subnet | List subnets/peerings, check IPAM |
| VM cannot be created due to lack of IPs | Primary range nearly exhausted or service quota reached | Check subnet utilization, request valid expansion |
| GKE cannot add nodes | Node primary range or Pod range insufficient for per-node IP allocation | Check Pod CIDR, maxPodsPerNode, cluster autoscaler |
| Cannot connect to a VM in the same VPC | Blocked by ingress firewall or another policy | Connectivity Tests, effective firewall, VM tags/service accounts |
| Cloud VPN connection has abnormal routes | Overlapping CIDR or misconfigured route advertisement/import | Cloud Router BGP status, route tables on both sides |
| Calling Google APIs fails from a private VM | Private Google Access, DNS, route, egress, or IAM | Check API endpoint, subnet config, and API permissions |
| Cannot access the Internet from a private VM | Missing appropriate NAT/route/egress configuration | Cloud NAT logs, default route, firewall |
| GKE Services IP conflict | User-managed Service range or unsuitable cluster config | Check the cluster's IP allocation policy |

Useful post-verification commands:

~~~bash
gcloud compute networks subnets list --network=prod-custom
gcloud compute networks subnets describe prod-sg-app \
  --region=asia-southeast1 \
  --format="yaml(ipCidrRange,secondaryIpRanges,privateIpGoogleAccess)"

gcloud compute routes list \
  --filter="network:prod-custom"

# If an associated GKE cluster exists:
gcloud container clusters describe CLUSTER_NAME \
  --region=asia-southeast1 \
  --format="yaml(ipAllocationPolicy)"
~~~

**Connectivity Tests** in Network Intelligence Center can help analyze expected paths and many traffic-blocking causes. Combine with VPC Flow Logs, Firewall Rules Logging, and Cloud Monitoring as needed, since looking at a CIDR table does not show where actual packets went.

## 13. Comprehensive Scenario: Expanding a Java Service from One Region to Two

An e-commerce application uses Cloud Run for a Java API, GKE for background processing jobs, and Cloud Storage for data. Initially it operates in only one region in Singapore; later the business adds Tokyo and connects an internal CRM via Cloud VPN. The operations team wants to keep staging and production environments independent.

**Proposed design:**

1. Use a **Custom mode VPC** managed by the platform team for production and a separate VPC for nonproduction.
2. Allocate primary subnets by region; use secondary ranges when VPC-native GKE needs user-managed Pod/Service IPs.
3. Keep production addresses inside `10.32.0.0/11` and nonproduction inside `10.64.0.0/11` per IPAM, reserving `10.96.0.0/12` for shared services.
4. Cross-check on-prem CRM ranges and VPN regions before assigning CIDRs; check GKE Pod ranges as well, not just primary subnets.
5. Use Shared VPC if multiple application projects need standardized subnets, with separate IAM for host/service projects.
6. Scope permissions and firewalls to actual flows: Cloud Run → backend, GKE → database, VM → Google APIs; keep production data isolated from dev.
7. Configure Cloud NAT/Private Google Access, hybrid routes, DNS, and monitoring as required.
8. Store network configuration in Terraform; review CIDR changes and verify before deploying new workloads.

**An illustrative mistake:** the network team assigned `10.32.16.0/20` to Tokyo. Later someone wants to expand the Singapore subnet from `10.32.0.0/20` to `10.32.0.0/19`. The new range would encompass the Tokyo subnet; the request conflicts. The initial design should leave free space right after the primary subnet if in-place expansion is desired, or pick a larger block and place subnets in separate slots from the start.

**Trade-off:** reserving generous spare IPs helps scaling, but in environments with many interconnected networks, oversized blocks can exhaust RFC 1918 space. The solution is to measure forecasted demand, maintain a clear registry, allocate intentionally, and audit changes over time.

## 14. Checklist Before Approving CIDRs for a Custom Mode VPC

- [ ] Confirm which VPC, project/host project, and regions need deployment.
- [ ] Maintain an IPAM inventory covering the entire organization, on-prem, peered VPCs, and future connections.
- [ ] Primary and secondary ranges do not overlap; CIDRs align cleanly on prefix boundaries.
- [ ] Estimate VM/node, Pod, and Service IP counts with growth headroom.
- [ ] Leave appropriate free space if **primary subnet expansion** is anticipated.
- [ ] Verify whether GKE-managed or user-managed Service ranges are required.
- [ ] Separate VPCs/subnets by environment and group according to actual security needs.
- [ ] Design firewalls, routes, Cloud Router/BGP, Cloud NAT, Private Google Access, and DNS as needed.
- [ ] Do not assume "creating a subnet means all VMs can communicate"; include a firewall verification plan.
- [ ] CIDRs, owners, allocation dates, and rationales are recorded in IPAM and Terraform.
- [ ] Any subnet resizing or hybrid connectivity change goes through review and post-verification.

**Applied Exercise:** You are tasked with designing a Custom mode VPC for a team running Compute Engine VMs and GKE in Singapore, needing to add Tokyo after six months. The network team reports that on-premises already uses `10.40.0.0/16` and a partner VPC uses `10.64.0.0/16`. (1) Propose non-overlapping IP blocks, (2) split primary and secondary ranges for each region, (3) prove the number of usable primary addresses in each subnet, (4) verify peering and Cloud VPN conditions, (5) write `gcloud` commands to create the VPC/subnets, and (6) describe an expansion plan if GKE node count is expected to triple. Explain why you must check the Pod range as well, not just node addresses.

## Official Reference Documentation

- [VPC networks](https://cloud.google.com/vpc/docs/vpc) — global networks, Auto/Custom mode, and routing.
- [Subnets](https://cloud.google.com/vpc/docs/subnets) — primary/secondary IPv4 ranges, reserved addresses, overlap limits.
- [Create and modify VPC networks](https://cloud.google.com/vpc/docs/create-modify-vpc-networks) — creating Custom mode and expanding subnets.
- [VPC Network Peering](https://cloud.google.com/vpc/docs/vpc-peering) — connectivity conditions and non-overlapping subnets.
- [VPC firewall rules](https://cloud.google.com/firewall/docs/firewalls) — firewall policies and traffic in a VPC.
- [Cloud Router overview](https://cloud.google.com/network-connectivity/docs/router/concepts/overview) — dynamic routing/BGP.
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview) — NAT for outbound workloads.
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access) — accessing Google APIs from private VMs.
- [GKE VPC-native clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips) — alias IPs and Pod/Service ranges.
- [GKE networking best practices](https://cloud.google.com/kubernetes-engine/docs/best-practices/networking) — planning GKE capacity.
