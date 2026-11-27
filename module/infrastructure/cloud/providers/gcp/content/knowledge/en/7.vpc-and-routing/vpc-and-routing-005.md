# Routes, Routing Order, and Packet Paths

> **Chapter:** VPC and Routing  
> **Module:** CLOUD_PROVIDERS_GCP

An application on Google Cloud may run on Compute Engine, GKE, or Cloud Run and need to connect to another VM, a database, an on-premises network, or the Internet. When connectivity fails, the first question is usually: **which path was the packet sent along, which next hop was selected, and why?**

In **CLOUD_PROVIDERS_GCP**, learners explore from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, release automation, reliability, and cost. The lesson **"Routes, Routing Order, and Packet Paths"** provides a mental model for reading Google Cloud VPC routing tables, explaining path selection, spotting disruptive configurations, and testing before deployment. This content sits in the **VPC and Routing** chapter; scenarios focus on the VPC data plane and connectivity to other networks.

After this lesson, you will be able to:

1. Read a route by its destination prefix, next hop, priority, route type, and applicability scope.
2. Distinguish subnet, static, dynamic, policy-based, and special routing paths.
3. Apply Google Cloud's actual routing order rather than simply remembering "lowest priority number wins."
4. Trace packet paths for VM → VM, VM → on-premises, VM → Internet, and traffic via inspection appliances.
5. Use Effective routes, Google Cloud CLI, Cloud Router, and Connectivity Tests to investigate issues.
6. Explain why having a route can still fail to connect: firewalls, NAT, addresses, regions, next hops, or return paths.

## 1. Understanding Routing Mechanisms in a VPC

A **route** describes a **destination** and a **next hop** that the network uses to forward packets. For traditional route types, the destination is represented as a CIDR prefix, such as `10.20.0.0/16` or `0.0.0.0/0`.

~~~text
Packet leaving VM:
    source IP        = 10.10.1.10
    destination IP   = 172.16.10.50
    protocol         = TCP
    destination port = 443

Candidate route:
    destination = 172.16.10.0/24
    next hop    = Cloud VPN tunnel / VLAN attachment / VM gateway ...
    priority    = numeric value if the route type has this attribute
~~~

Unlike a physical router you manage yourself, a Google Cloud VPC uses a **distributed virtual routing mechanism**. There is no single dedicated router instance assigned to the entire VPC. VMs receive applicable routes through Google's network fabric; route changes are propagated under an **eventual consistency** model, so they may take a short time to take effect uniformly.

A VPC is a **global** resource, while subnets are **regional**. Subnets in multiple regions can belong to the same VPC. Sending traffic to another subnet still depends on routes, IP addresses, and firewall rules; it does not mean all ports are open by default.

### 1.1. Core Fields When Reading a Route

| Attribute | Meaning | Example or note |
| --- | --- | --- |
| **Destination** | Destination address range of the route | `172.16.10.0/24` |
| **Next hop** | Intermediate target/infrastructure receiving the next packet | Internet gateway, VM next hop, Cloud VPN, Interconnect, internal passthrough Network Load Balancer |
| **Priority** | Preference order of certain route types when reaching the priority comparison step | `100` outranks `900`; numeric scale `0–65535` for static routes |
| **Route type** | Route category determining its position in the route selection process | Subnet, local static, local dynamic, peering, NCC, policy-based |
| **Scope/applicability** | Which resources in the VPC can use the route | A static route can apply VPC-wide or only to VMs with a network tag |
| **Region** | Effective scope of certain dynamic routes/next hops | Dynamic routing mode can be regional or global |
| **Network/VPC** | Which VPC the routing table belongs to | Do not rely on routes from an unconnected VPC |

An **applicable route** is a route that is in effect for a **specific sender**; it is a subset of the routes existing in the VPC. Two VMs in the same VPC can receive different sets of applicable routes due to network tags, region, or routing policies.

### 1.2. CIDR and "More Specific Destination"

`10.20.5.0/24` covers `10.20.5.0–10.20.5.255`; `10.20.0.0/16` covers a broader range. If a packet is destined for `10.20.5.10`, both prefixes match, but `/24` is **more specific** than `/16`.

| Prefix | Network bits | Specificity |
| --- | ---: | --- |
| `0.0.0.0/0` | 0 | Broadest in IPv4 |
| `10.0.0.0/8` | 8 | Very broad |
| `10.20.0.0/16` | 16 | Narrower than /8 |
| `10.20.5.0/24` | 24 | More specific than /16 |
| `10.20.5.10/32` | 32 | Single IPv4 address |

This is the basis of *longest prefix match* (LPM). However, **LPM is not applied ahead of every route type**. In Google Cloud, special routing paths, policy-based routes, and subnet routes are evaluated before custom static/dynamic routes.

## 2. Route Types and Paths in Google Cloud

| Type | Created/controlled by | Typical meaning |
| --- | --- | --- |
| **Special routing path** | Google Cloud platform; cannot be deleted from the route table | Paths for certain load balancers, health checks, IAP, Cloud DNS, etc. |
| **Policy-based route (PBR)** | Network administrator | Steers traffic through an internal passthrough Network Load Balancer by source, destination, protocol |
| **Local subnet route** | Automatically created per local subnet | Delivers packets to IPs within a VPC subnet |
| **Peering subnet route** | Imported from a peered VPC | Delivers packets to subnets advertised from a peer VPC |
| **NCC subnet route** | Imported from a Network Connectivity Center (NCC) VPC spoke | Delivers packets to subnets connected via NCC |
| **Local static route** | Created manually or via service mechanism | Sends packets to a predefined next hop, e.g., VM appliance, Classic VPN, Internet gateway |
| **Local dynamic route** | Learned/managed by Cloud Router via BGP | Sends packets to on-premises prefixes via HA VPN, Interconnect, or router appliance |
| **Peering custom route** | Imported from a peered VPC when matching exchange is enabled | Paths to custom destinations of a peer network |
| **NCC dynamic route** | Imported from an NCC hybrid spoke | Paths to prefixes dynamically learned through a hub |
| **System-generated default route** | Created by Google Cloud on VPC creation under supported conditions | `0.0.0.0/0` or `::/0` with next hop `default-internet-gateway` |
| **Private Service Connect endpoint route** | Created by an endpoint's forwarding rule, in supported cases | Path to an endpoint for Google APIs at a dedicated step in order |

### 2.1. Subnet Route

When a subnet has a primary IPv4 range, secondary range, or supported IPv6 range, Google Cloud creates corresponding subnet routes. For example:

~~~text
VPC: app-net
├── subnet-a (asia-southeast1) : 10.10.1.0/24
└── subnet-b (asia-southeast2) : 10.10.2.0/24

VM-A: 10.10.1.10
VM-B: 10.10.2.20
~~~

Packets from VM-A to VM-B match local subnet route `10.10.2.0/24`. For a **standard** subnet route, this route is selected at the subnet step, ahead of custom static/dynamic routes. If the destination address falls within the subnet range but **is not attached to a valid resource** or the target VM is stopped, the packet may be dropped; the system does not fall back to the default route to search for that IP on the Internet.

Google Cloud **does not allow creating** a static route whose destination matches or falls **inside** a standard local/peering/NCC subnet route. For instance, if subnet `10.10.2.0/24` exists, you cannot add a static route `10.10.2.128/25` to "override" half the subnet. An exception involving **hybrid subnet routing** requires consulting dedicated documentation.

### 2.2. Static Route

A static route defines a fixed destination and next hop. Common next hops include:

- `default-internet-gateway` for paths to external IPv4/IPv6 under supported conditions.
- A next-hop VM specified by name/zone or supported IP address, often serving virtual router/firewall appliances.
- **Internal passthrough Network Load Balancer** as the next hop for a pool of gateway appliances.
- **Classic VPN tunnel** when using static or policy-based VPNs.

A static route can carry a **network tag**. A tagged route applies only to **VMs with the matching network tag**, not to every source type (such as a Cloud VPN tunnel or Interconnect VLAN attachment). Tagged static routes are not exchanged over VPC Network Peering.

A smaller `priority` value means higher preference **once route selection reaches the priority comparison step**. Higher priority **does not automatically beat** a more specific prefix or route types evaluated earlier by Google Cloud.

### 2.3. Dynamic Route and Cloud Router

Cloud Router is a **control plane** component that exchanges routes via BGP or uses custom learned routes. Cloud Router **does not forward every data packet itself** like a VM router. The actual packet path may use a Cloud VPN tunnel, Interconnect VLAN attachment, or router appliance as the next hop.

Example: enterprise infrastructure advertises `172.16.0.0/16` via BGP to a Cloud Router attached to HA VPN. When the BGP session and advertisement conditions are met, the VPC can learn a dynamic route for this prefix. If BGP goes down, the route may be withdrawn.

**Dynamic routing mode** affects the regional scope that receives dynamic routes:

- **Regional:** local dynamic routes apply within the region containing the Cloud Router/next hop.
- **Global:** eligible local dynamic routes can be used across multiple regions of the VPC depending on route type, next hop, and network mechanisms.

With VPC Network Peering, the scope of exported dynamic routes also depends on the **routing mode of the exporting VPC**, not just the importing VPC. IPv6 and certain hybrid setups have specific limits; consult documentation rather than inferring from IPv4 behavior.

### 2.4. Policy-Based Routing (PBR)

A policy-based route can match **source IP**, **destination IP**, and **IP protocol**, rather than relying solely on destination prefix. A common purpose is **steering a subset of traffic through a firewall appliance** placed behind an internal passthrough Network Load Balancer.

Key properties:

- PBR is evaluated **after special routing paths but before subnet and custom routes**.
- PBR compares **priority**; it **does not use LPM** to automatically pick the route with the most specific source/destination prefix.
- PBR can apply network-wide, to tagged VMs, or to VLAN attachments per conditions; PBRs are not exchanged over VPC Peering.
- The PBR next hop is typically a valid **internal passthrough Network Load Balancer**; a special rule option allows **skipping other PBRs** and returning to default routing.
- If multiple PBRs with the same priority match, Google Cloud may choose via an internal algorithm not based on prefix specificity. Always assign **distinct** priorities to rules that could match together.
- PBR does not support filtering directly by **TCP/UDP port**, so do not write PBR examples claiming "port 443 only" as if that were a supported condition.

PBR is a powerful tool, but you must test forward and return paths, firewall backend availability, IP forwarding, and impact on GKE control plane, Private Service Connect, and special flows.

### 2.5. Default Route and Internet Connectivity

When creating a VPC, Google Cloud typically creates a local static default route `0.0.0.0/0` with next hop `default-internet-gateway`. For subnets with an external IPv6 range, a corresponding `::/0` may exist.

**Having a default route does not guarantee a VM can reach the Internet.** For IPv4, check:

1. Does the packet go to the default Internet gateway, or is it diverted by a more specific route/PBR to another next hop?
2. Does the VM have an external IPv4, or does the subnet/VM have an active **Public Cloud NAT** covering that traffic?
3. Do egress firewalls/policies allow the connection?
4. Are DNS, destination address, guest OS configuration, and the external service working?
5. For Google APIs, **Private Google Access** or Private Service Connect may establish a different connectivity path from public Internet access.

**Cloud NAT is an address translation service, not a selectable next-hop type in a static route.** Public Cloud NAT normally uses the VPC's `default-internet-gateway` path; if traffic to a destination is steered to a custom VPN/gateway, do not assume NAT will apply automatically.

## 3. Google Cloud's Actual Routing Order

Within a VPC, multiple routes may match a packet simultaneously. Google Cloud uses an **ordered evaluation process**, rather than sorting all routes by a single priority field.

### 3.1. High-Level Decision Flowchart

~~~mermaid
flowchart TD
    START["Packet leaves source in VPC"] --> S{"Special routing path matches?"}
    S -- "Yes" --> SPECIAL["Use special path"]
    S -- "No" --> P{"Valid PBR matches?"}
    P -- "Yes, next hop ILB" --> ILB["Forward to internal passthrough NLB"]
    P -- "Yes, skip PBR" --> SUB
    P -- "No" --> SUB{"Subnet route matches?"}
    SUB -- "Yes, standard" --> SR["Use subnet route"]
    SUB -- "No" --> PSC{"PSC endpoint for global Google APIs matches?"}
    PSC -- "Yes" --> PS["Use forwarding-rule route"]
    PSC -- "No" --> LPM["Filter static/dynamic by most specific prefix"]
    LPM --> TYPE["Select most favorable custom route type"]
    TYPE --> NEXT["Discard unusable next hops"]
    NEXT --> PRI["Select lowest priority number"]
    PRI --> PREF["Handle preference category and ECMP"]
    PREF --> END["Send to next hop or drop"]
~~~

This diagram **simplifies** peering/NCC selection steps and **hybrid subnet** cases, which are analyzed next. It is meant to show the overall flow; for complex cases, consult [Routes: Routing order](https://docs.cloud.google.com/vpc/docs/routes#routing_order).

### 3.2. Twelve Steps in the Routing Documentation

| Step | Name in Google Cloud docs | Meaning |
| ---: | --- | --- |
| 1 | **Special routing paths** | Checks special paths, typically not shown in the standard route table. Stops if matched. |
| 2 | **Policy-based routes** | Evaluates PBR based on packet attributes and **priority**. A skip-PBR rule returns to the standard branch. |
| 3 | **Subnet routes** | Checks local/peering/NCC subnet routes; for standard subnets, uses this route if matched. |
| 4 | **PSC endpoints for global Google APIs** | Checks applicable Private Service Connect endpoint forwarding rules. |
| 5 | **Most specific destination** | Among remaining **static/dynamic** routes, keeps the most specific destination prefix (LPM). |
| 6 | **Most favorable custom route type** | For the same prefix, prefers **local custom** before **NCC dynamic**, then **peering custom**. |
| 7 | **Peering custom routes from one VPC** | If multiple peers provide the same destination, selects next hops from one peer VPC via an internal algorithm. |
| 8 | **Disregard unusable next hops** | Discards static/dynamic routes whose next hop is invalid or unusable per Google Cloud criteria. |
| 9 | **Disregard low-priority routes** | Keeps routes with the **lowest priority number** in the remaining set. |
| 10 | **NCC dynamic routes from one routing VPC** | If applicable, selects NCC next hops from one routing VPC network. |
| 11 | **Most favorable preference category** | For the same prefix/priority, prefers next-hop types according to Google Cloud's hierarchy. |
| 12 | **Send or drop packet** | One route sends; multiple eligible routes may ECMP; no remaining route drops the packet. |

**Why does this order matter?** A static route with `priority=100` can **lose** to a dynamic route with `priority=900` if the dynamic route has a more specific prefix and both are in the appropriate static/dynamic branch. Conversely, a matching **standard subnet route** is evaluated ahead of both. A matching PBR can send packets via its dedicated next hop even when the destination lies inside a subnet.

### 3.3. Note on "Hybrid" Subnets

Most subnets use standard subnet route logic: a destination matching the subnet range follows the subnet route, or is dropped if the IP does not exist or the VM is stopped. With explicitly configured **hybrid subnet routing**, when an IP is not bound to a running VM or internal forwarding rule, Google Cloud can proceed through another evaluation path to find a route to the destination.

**Do not cite hybrid subnets as a general rule** to claim that packets to unused IPs in a default subnet automatically fall back to VPN. This is a conditional exception with strict scope and next-hop constraints in official documentation.

### 3.4. Comparing Prefix and Priority in the Right Order

Imagine a VM at `10.10.1.10` sending to `172.16.10.25`; no PBR, subnet, or special path matches the destination.

| Route | Destination | Priority | Next hop | Outcome |
| --- | --- | ---: | --- | --- |
| Route A | `0.0.0.0/0` | 10 | Internet gateway | Eliminated at step 5 as too broad |
| Route B | `172.16.0.0/16` | 100 | VPN A | Eliminated at step 5 as too broad |
| Route C | `172.16.10.0/24` | 900 | VPN B | **Retained** because `/24` is most specific |

**Conclusion:** `/24` beats `/16` and `/0` in the custom route branch even with a priority of 900. Only when eligible routes share the **exact same destination prefix** do evaluation steps move on to route type and priority selection.

### 3.5. Same Prefix: Route Source and Next Hop Still Matter

Suppose multiple routes share destination `172.16.10.0/24`:

- There is a **local dynamic route** and a **peering custom route** for the same prefix: the custom route type selection step can pick the local route **before** comparing priorities with the peer.
- There are two **local** routes with the same prefix in the same comparison group: the route with the lower priority number is generally kept after discarding unusable next hops.
- If multiple routes remain with the same prefix, same priority, and eligible next-hop type, Google Cloud can perform **ECMP**.
- If next hops belong to different **preference categories** at step 11, **no ECMP happens across categories**.

The preference categories at step 11, in order:

1. Static route with a VM or Classic VPN tunnel next hop.
2. Dynamic route of an applicable type.
3. Static route to an internal passthrough Network Load Balancer.
4. Static route to `default-internet-gateway`.

This step occurs **after** filtering by prefix, custom route type, unusable next hops, and priority. Do not use the preference category list to override earlier steps in the evaluation order.

### 3.6. Does a Broken Next Hop Fall Back to a Broader Route?

**Fallback does not always happen.** For example:

~~~text
Destination: 192.168.50.10

Route X: 192.168.50.0/24 → stopped VM next hop
Route Y: 192.168.0.0/16  → running VM next hop
~~~

Route X is chosen at the LPM step and Route Y is eliminated for having a broader prefix. If X's next hop is deemed unusable in a later step, the packet may be **dropped** rather than reverting to Route Y.

However, if **two routes have the same destination prefix**, the route with an unusable next hop can be discarded **before** priority comparison, allowing another route with the same prefix and a valid next hop to be used. This explains why you must check both **prefix** and **next-hop health** when designing redundancy.

## 4. How Do Packets Travel in Common Scenarios?

### 4.1. VM to VM in the Same Subnet

~~~text
VM-A: 10.10.1.10
VM-B: 10.10.1.20
Subnet: 10.10.1.0/24
~~~

1. VM-A sends a packet to `10.10.1.20`; the guest OS decides to send it out the appropriate network interface.
2. VPC infrastructure applies the network path, typically via the local subnet route.
3. Google Cloud evaluates firewalls/policies applicable to the flow.
4. If VM-B is running, has a valid IP, firewalls allow it, and the service is listening, the packet is delivered.
5. Return traffic follows applicable routing rules and connection state; stateful firewalls can allow reply packets for an accepted connection.

**There is no user-configured "hop up to a default physical router"** per Google Cloud subnet.

### 4.2. VM Between Two Subnets/Regions of the Same VPC

~~~mermaid
flowchart LR
  A["VM-A · 10.10.1.10 · asia-southeast1"] --> R["Google Cloud distributed VPC routing"]
  R --> B["VM-B · 10.10.2.20 · asia-southeast2"]
  R -. "Network policies" .- FW["Firewall / Hierarchical firewall policies"]
~~~

If subnet `10.10.2.0/24` belongs to the VPC, a standard local subnet route carries packets to the right region. Whether traffic succeeds still depends on firewalls, IPs at both ends, and the destination service; crossing regions can also incur inter-region data transfer charges. You do not need to manually create static routes just to connect two subnets in the same VPC.

### 4.3. VM to On-Premises via HA VPN/Interconnect

~~~mermaid
flowchart LR
  VM["VM in VPC · 10.10.1.10"] --> VR["VPC route selection"]
  VR --> TUN["HA VPN tunnel / Interconnect VLAN attachment"]
  TUN --> ON["On-premises router"]
  ON --> APP["Server · 172.16.10.25"]
  CR["Cloud Router · BGP control plane"] -. "Learn/advertise prefixes" .-> VR
  CR -. "BGP" .-> ON
~~~

Suppose on-premises advertises `172.16.0.0/16` and Cloud Router learns a dynamic route via BGP. When the VM sends to `172.16.10.25`, with no matching subnet/PBR or special path, the dynamic route can be selected and direct packets via the VPN/Interconnect next hop.

Items to verify:

- Is the BGP peer up and has the VPC **learned** the required prefix?
- Does the dynamic route apply in the source VM's region?
- Is there a more specific route sending packets to a different next hop?
- Does the on-premises network have a **return route** back to `10.10.1.0/24`?
- Do firewalls on both sides allow the traffic, and is any NAT/ACL altering addresses?
- Are tunnels/Interconnect actually forwarding packets, not just showing control-plane up?

**Bidirectional** connectivity requires a valid return path. A BGP status of "Established" is a positive signal, but it is not enough to prove an application TCP connection will succeed.

### 4.4. VM Without a Public IP Reaching the Internet

~~~text
VM: 10.10.1.10 (internal IPv4 only)
       |
       | 0.0.0.0/0 → default-internet-gateway
       v
VPC / Cloud NAT (Public NAT configured for eligible source)
       |
       v
Internet public endpoint
~~~

Typical prerequisites: a default IPv4 route with Internet gateway next hop, Public Cloud NAT configured for the right source, egress firewalls, and a reachable destination service. Cloud NAT **translates addresses**, it is not a next hop in the route table.

If you replace the default route with a static route through a VM appliance or VPN, traffic follows that corresponding next hop; Public Cloud NAT does not automatically apply to arbitrary alternate paths.

### 4.5. Inserting a Firewall Appliance with PBR

~~~mermaid
flowchart LR
  APP["Application VM"] --> PBR["Policy-based route matching IP/protocol"]
  PBR --> ILB["Internal passthrough Network Load Balancer"]
  ILB --> FWA["Firewall VM / network appliance"]
  FWA --> DEST["Intended destination"]
~~~

PBR can steer a subset of traffic through a firewall VM for inspection. Because PBR is evaluated before subnet routes, misconfiguration can disrupt even internal connectivity. You must verify that the backend firewall has **IP forwarding** enabled, check return paths, network tags, higher-priority skip-PBR rules for sources or destinations requiring exceptions, and high availability of the internal passthrough load balancer.

**Reasoning example:** a PBR at priority 100 matching source `10.10.1.0/24` and destination `0.0.0.0/0` will be evaluated ahead of the subnet route to `10.10.2.0/24`, unless a higher-priority special path or skip-PBR rule applies. Never assume "internal destinations always bypass the firewall appliance."

### 4.6. VPC Peering and NCC Connectivity

When two VPCs are peered, Google Cloud can import **peering subnet routes** and certain **custom routes** if matching import/export is enabled. However, **VPC Network Peering does not support transit routing between two peers solely through an intermediate peer**. Connectivity A↔B and B↔C **does not** mean A↔C has a direct transit path.

With **Network Connectivity Center**, VPC spokes and hybrid spokes follow subnet/dynamic route exchange rules depending on topology, export filters, and applicable conditions. Never deduce NCC route selection solely from priority numbers without checking the precedence step **local custom → NCC dynamic → peering custom**.

## 5. Reading the Routing Table and Checking Effective Routes

### 5.1. Google Cloud Console: Effective Routes

To evaluate paths, open **VPC network → Routes → Effective routes** in Google Cloud Console:

1. Select the right **VPC network**.
2. Select the **region** relevant to the sender (especially when dynamic routes exist).
3. Inspect route types, destinations, next hops, and applicability status.
4. Toggle **suppressed routes** on if you need to understand why a route was bypassed.
5. Verify network tag/PBR scope, paths to on-premises, and bidirectional reachability.

**Important:** **Route management** shows manageable route configurations, whereas **Effective routes** helps reveal routes actually in effect for a given scope. Always inspect for the specific source VM/region rather than drawing conclusions from an uncontextualized route list.

### 5.2. Read-Only Google Cloud CLI Commands

The following commands inspect existing resources. Replace `PROJECT_ID`, `NETWORK_NAME`, `ROUTER_NAME`, and `REGION` with your system's real values:

~~~bash
# Verify active project
gcloud config get-value project

# List VPCs
gcloud compute networks list --project=PROJECT_ID

# List subnets
gcloud compute networks subnets list --project=PROJECT_ID

# List subnet routes and static routes
gcloud compute routes list --project=PROJECT_ID

# Describe an existing static route by name
gcloud compute routes describe ROUTE_NAME --project=PROJECT_ID

# View BGP and associated Cloud Router status (if present)
gcloud compute routers get-status ROUTER_NAME \
  --region=REGION \
  --project=PROJECT_ID

# List existing Connectivity Tests
gcloud network-management connectivity-tests list \
  --project=PROJECT_ID
~~~

**Limitation of `gcloud compute routes list`:** Per current documentation, the `gcloud compute routes` command group displays **subnet routes and static routes**, and **does not fully display** policy-based, dynamic, and peering routes. When analyzing complete path selection, use **Effective routes** in the Console combined with Cloud Router/BGP status and related data. Do not conclude "no dynamic route exists" simply because it does not appear in `gcloud compute routes list`.

Listing Connectivity Tests requires the relevant API and permissions to be configured. These commands do not create or modify resources. Querying status does not replace live connectivity testing.

### 5.3. Illustrative Static Route Configuration Example

Suppose you have an approved gateway appliance in the VPC and want to send traffic for lab network `192.168.50.0/24` through the next-hop VM. The example syntax below **creates a route**; use it only in an authorized lab after verifying CIDRs, VPC, next hop, and return paths:

~~~bash
gcloud compute routes create lab-to-remote \
  --network=LAB_NETWORK \
  --destination-range=192.168.50.0/24 \
  --next-hop-instance=LAB_GATEWAY_VM \
  --next-hop-instance-zone=LAB_GATEWAY_ZONE \
  --priority=800 \
  --project=LAB_PROJECT_ID
~~~

After verification, if this route was created purely for the lab and is no longer needed, you can delete it in a controlled manner:

~~~bash
gcloud compute routes delete lab-to-remote \
  --project=LAB_PROJECT_ID
~~~

**Never copy create/delete commands into a production project.** A route can alter paths for many VMs and cause connectivity outages. Before applying, review impact and prepare a rollback plan.

### 5.4. Guest OS Routes Differ from VPC Routes

On a Linux VM, `ip route` shows the default gateway and OS-level routes. This list is **not the full** VPC route table. The VPC fabric decides the next hop once a packet leaves the VM into Google's network. You must combine guest OS, network interface, VPC Effective routes, and firewall information to understand the complete path.

## 6. Diagnosing Connectivity Failures

**Inability to ping** or a service port timeout does not prove the route is wrong. The fault may lie in DNS, source/destination, firewalls, guest OS, routes, NAT, organization policies, or return paths.

### 6.1. Layer-by-Layer Checklist

| Layer | Question | Appropriate tool |
| --- | --- | --- |
| **Source/destination address** | Are the IPs right? Which VPC/region/network interface is the source on? | Compute Engine interface details, DNS records |
| **Applicable routes** | Which route matches? Is there a special path/PBR/subnet/PSC? | Effective routes, Google Cloud Routes docs |
| **Prefix and priority** | Is there a more specific destination? Higher-preference custom route type? Valid next hop? | Effective routes, route details |
| **Dynamic control plane** | Is the BGP session up? Are prefixes learned/advertised and applied in the right region? | Cloud Router status, BGP routes |
| **Next-hop data plane** | Is the tunnel, appliance VM, or ILB healthy and actually forwarding? | VPN/Interconnect monitoring, appliance logs |
| **Firewall/policy** | Do ingress and egress rules allow the exact IP/protocol/port? | Firewall rules, firewall policies, Firewall Rules Logging |
| **NAT/Internet** | Does it have an external IP or Public NAT? Is the default gateway path still applicable? | Cloud NAT status/logs, routes |
| **Return path** | Does the destination have a route back to the source? Any asymmetric path or NAT rewriting addresses? | Effective routes on both sides, on-prem routes |
| **Application** | Is the service listening on the port, are TLS/DNS valid, are timeouts suitable? | VM logs, application logs, metrics |

### 6.2. Connectivity Tests

[Network Intelligence Center – Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) lets you simulate a connection flow from **source to destination** and analyze network configurations such as routes, firewalls, VPNs, and load balancers. Certain scenarios also support **live data plane analysis** and packet loss/latency metrics.

How to use in Console:

1. Select **Network Intelligence Center → Connectivity Tests**.
2. Create a test with a specific source (e.g., VM-A), destination IP or resource, protocol, and port.
3. Read the **trace** to pinpoint which hop is blocked, which route type was used, and firewall conditions.
4. Cross-check configurations immediately after edits against live state; the tool has a slight propagation delay for configuration updates.
5. If analysis reports reachable yet the application still fails, inspect the guest OS, service listener, DNS, TLS, and dependencies.

**Note:** Creating a Connectivity Test creates a diagnostic resource; it requires permissions and may incur charges/API requirements. Existing tests can be listed with the read-only command in section 5.2.

### 6.3. VPC Flow Logs and Firewall Rules Logging

- **VPC Flow Logs** let you observe samples/metadata of flows on subnets or supported resources, depending on configuration. This is not full packet capture and may involve sampling/aggregation.
- **Firewall Rules Logging** shows connections matching rules with logging enabled, helping identify allow/deny verdicts.
- **Cloud Router logs/metrics** show BGP session status and learned/advertised routes; this is different from validating an end-to-end TCP session.

A packet's absence from one type of log is insufficient to conclude it never traversed the network. You must understand collection scope, sampling, permissions, and logging delays.

## 7. Very Common Reasoning Mistakes

1. **"Priority 100 always beats priority 900."** False when comparing two different prefixes or route types at different tiers. Evaluate *routing order* first.
2. **"A 0.0.0.0/0 route can override a subnet."** Standard subnet routes are selected before custom routes.
3. **"Having a route means TCP can connect."** Firewalls, NAT, permissions, target appliances, ports, and return paths also matter.
4. **"Cloud Router is the router receiving and forwarding every packet."** Cloud Router manages BGP/routes; the data plane traverses the corresponding next hop.
5. **"Having a default route means a private VM can reach the Internet."** You also need NAT or a supported access path, firewalls, and policies.
6. **"PBR uses longest prefix match just like static routes."** PBR evaluates priority and match criteria; ties at the same priority may be resolved by an internal algorithm.
7. **"A static route with a network tag applies to all sources in the same VPC."** A tagged route applies only to VMs carrying the matching tag.
8. **"Two VPCs peered through an intermediate VPC automatically have transit."** VPC Network Peering is not arbitrary transitive connectivity.
9. **"BGP up means application connectivity succeeds."** Application routes, tunnels, firewalls, destinations, and valid return paths are still required.
10. **"A failed next hop falls back to the /0 route."** The more specific route already eliminated broader routes at an earlier step; packets may drop instead of falling back.
11. **"Route changes take effect instantaneously on all VMs."** Google Cloud propagates updates under eventual consistency.
12. **"`gcloud compute routes list` shows all route types completely."** Console Effective routes is needed to see types omitted by that command.
13. **"Same prefix and priority always ECMPs across all next hops."** Google Cloud also applies custom route type selection, next-hop network selection, and preference categories.
14. **"GKE or Cloud Run automatically uses all VPC routes identically to VMs."** Traffic paths depend on network mode, VPC egress/connectivity settings, Pod/alias ranges, and service type; check workload documentation.

## 8. Route Table Analysis Exercises (No Infrastructure Needed)

**Shared assumptions:** A VM has source IP `10.10.1.10` in VPC `lab-net`, region `asia-southeast1`. No special paths and no PBR exist unless stated otherwise. Remote destinations are outside the VPC's subnets.

### Scenario A — More Specific Prefix

| Route | Destination | Priority | Next hop |
| --- | --- | ---: | --- |
| A1 | `0.0.0.0/0` | 100 | default internet gateway |
| A2 | `172.16.0.0/16` | 200 | Cloud VPN-A |
| A3 | `172.16.20.0/24` | 800 | Cloud VPN-B |

**Question:** Which next hop does a packet to `172.16.20.15` take? What about a packet to `172.16.30.15`?

**Hint:** The packet to `172.16.20.15` selects A3 because `/24` is more specific. The packet to `172.16.30.15` does not fall within `/24`, so it selects A2. Priority values do not alter the LPM result in this example.

### Scenario B — Subnet with Unassigned IP

| Component | Value |
| --- | --- |
| Local subnet | `10.10.2.0/24` |
| Target packet | `10.10.2.199` |
| Target IP | Not assigned to any VM or forwarding rule |
| Default route | `0.0.0.0/0` to internet gateway |

**Question:** Does the packet fall back to the Internet?

**Hint:** With a standard subnet route, no. The subnet route matches and is selected; because no valid destination resource exists, the packet is dropped. Explicitly configured hybrid subnets are a separate exception.

### Scenario C — Same Prefix, Stopped Next Hop

| Route | Destination | Priority | Next hop |
| --- | --- | ---: | --- |
| C1 | `192.168.50.0/24` | 100 | Stopped Gateway VM |
| C2 | `192.168.50.0/24` | 300 | Running Gateway VM |
| C3 | `192.168.0.0/16` | 10 | Running Gateway VM |

**Question:** Which path can be selected for `192.168.50.5`?

**Hint:** C3 is eliminated during LPM. If C1 is discarded at the unusable next-hop step, C2 with the same prefix can be selected despite priority 300. The next hop's guest OS state still needs verification: a running VM does not guarantee the router/firewall software is forwarding packets.

### Scenario D — PBR Intervening on a Subnet

A PBR matches source `10.10.1.0/24` and destination `0.0.0.0/0`, priority 100, next hop internal passthrough NLB. A subnet route `10.10.2.0/24` exists. Will a packet to `10.10.2.20` necessarily go straight over the subnet?

**Hint:** No. If the PBR matches and no higher-priority special path or skip-PBR applies, it is evaluated before the subnet route and can steer packets through the NLB/appliance. The design must verify return paths and the firewall appliance to avoid blackholing.

### Scenario E — VPN and Internet

A VM has no external IPv4. The VPC has default route `0.0.0.0/0` to the internet gateway and dynamic route `172.16.0.0/16` over HA VPN. Cloud NAT is not configured.

**Question:** Do packets to `172.16.1.10` and `8.8.8.8` behave the same way?

**Hint:** No. Destination `172.16.1.10` matches the more specific dynamic route and traverses the VPN if paths and firewalls allow. Destination `8.8.8.8` matches the default gateway; a VM with only internal IPv4 and no Public NAT or appropriate public path typically cannot use that path for general Internet access. Egress policies must also be considered.

## 9. Design Scenario: Separating Application Environments and Enterprise Network

**Context:** An application team runs APIs on Cloud Run, processes jobs on GKE, maintains a legacy Java system on Compute Engine, and needs access to an on-premises database via HA VPN. The VPC has two regional subnets, an Internet egress path, and dynamic routes via Cloud Router. The security team requires certain flows to pass through a firewall appliance, while the operations team wants incident and cost observability.

A design document must clearly specify:

- **Addressing and boundaries:** non-overlapping subnet CIDRs distinguishing production and development networks.
- **On-premises path:** which ranges Cloud Router learns, which regions BGP peers reside in, and regional/global routing mode.
- **Policy-based routes:** which sources/destinations/protocols traverse the appliance, skip-PBR priorities if needed, and whether the ILB operates across regions.
- **Cloud Run egress:** appropriate VPC connectivity configuration and scope of traffic routed into the VPC.
- **GKE:** how Pods/Nodes use IP ranges, potential PBR conflicts, and route applicability scope.
- **Return path:** confirmation that on-premises has routes back to VPC ranges over the same or permitted paths.
- **Firewalls:** rules based on source/destination/port, network tags or service accounts, plus organization-level policies.
- **Observability:** Cloud Router status, VPN health, Connectivity Tests, and appropriate logging.
- **Cost:** Internet egress, inter-region data transfer, VPN/Interconnect, and appliance processing (if any).

**Example of a concise architecture decision record:**

~~~text
Problem: VM/GKE needs to access on-prem DB 172.16.20.10:5432.
Source: app subnet 10.10.1.0/24, worker subnet 10.10.2.0/24.
Expected path: dynamic route 172.16.0.0/16 over HA VPN.
Rationale: Cloud Router receives BGP advertisements and controls hybrid connectivity.
Security: restrict TCP/5432, service accounts, and firewalls on both sides.
Assumptions: route applies in the right region; on-prem has return routes.
Verification: Effective routes, Cloud Router status, Connectivity Tests.
Risks: BGP down, wrong more-specific prefix, asymmetric route, appliance down.
Recovery: tunnel monitoring and tested failover/rollback procedures.
Optimization: monitor bandwidth, latency, and data transfer cost.
~~~

Every decision should be backed by **evidence**, not just a box-and-arrow diagram. Routes are one part of network design; reliability also requires testing and observability.

## 10. Review Questions and Guided Answers

1. **Does priority 50 always beat priority 200?** No; special/PBR/subnet/PSC, LPM, and custom route type come before priority comparison.
2. **When does Google Cloud create a subnet route?** When a subnet or its address range is created or modified through supported lifecycle operations; you do not manually create a static route for each subnet.
3. **Does Cloud Router forward packets like a VM router?** No. Cloud Router participates in BGP/dynamic route exchange and management; the data plane uses the corresponding next hop.
4. **Is a packet to an IP inside a subnet without a VM sent to the default route?** Not with a standard subnet route.
5. **Why doesn't PBR use LPM like custom routes?** PBR has its own match criteria and priority order ahead of subnet/custom routes.
6. **Does having a default route mean a VM without a public IP can reach the Internet?** No; NAT or a supported access path, firewalls, and network conditions are also required.
7. **Why can TCP still time out when BGP is Established?** Actual routes, firewalls, return paths, target services, or next-hop data plane forwarding may be missing or blocked.
8. **Does a static route with a network tag apply to a Cloud VPN tunnel?** No; tags restrict applicability only to VMs with matching tags.
9. **Does VPC Peering A–B and B–C create A–C transit?** There is no automatic transitive Peering.
10. **When two routes have the same prefix and priority, do they always ECMP across all next hops?** No; next-hop filtering, route type, preference categories, and ECMP eligibility still apply.
11. **Why must you inspect Effective routes by region?** Because dynamic routes and certain next hops have regional scope.
12. **Why can a running next-hop VM still drop packets?** The guest OS may lack IP forwarding, the appliance may not process them, or return firewalls/routes may be wrong; VM state does not prove end-to-end forwarding.

## 11. Pre-Change Checklist for Production Routes

- [ ] Confirmed the exact project/VPC/region and packet source.
- [ ] Identified source IP, destination IP, protocol, port, and forward/return directions.
- [ ] Checked special paths, PBRs, and subnet routes before evaluating custom routes.
- [ ] Applied LPM, custom route type, next hop, and priority in the exact order.
- [ ] Checked network tags and regional/global scope of dynamic routes.
- [ ] Verified BGP/tunnels/Interconnect and live next-hop health.
- [ ] Checked ingress/egress firewalls, NAT, and return paths.
- [ ] Verified source/destination routes using Console Effective routes.
- [ ] Used Connectivity Tests or appropriate tests for critical flows.
- [ ] Prepared a rollback plan and an appropriate change window.
- [ ] Evaluated reliability, network cost, and IAM permissions for the change.

## 12. Official Reference Documentation

Google Cloud may update routing rules, especially around Network Connectivity Center, hybrid subnets, and Policy-based routes. In production work, prioritize official documentation and the current **Routing order** section.

- [Routes overview & routing order](https://docs.cloud.google.com/vpc/docs/routes) — route types, applicability scopes, and the 12 route selection steps.
- [Static routes](https://docs.cloud.google.com/vpc/docs/static-routes) — next hops, priorities, tags, and conflict rules.
- [Use routes & Effective routes](https://docs.cloud.google.com/vpc/docs/using-routes) — how to view configurations and effective routes.
- [Policy-based routes](https://docs.cloud.google.com/vpc/docs/policy-based-routes) — source/destination/protocol, priority, next hops, and exceptions.
- [Use policy-based routes](https://docs.cloud.google.com/vpc/docs/use-policy-based-routes) — configuration operations, listing, and IAM/API requirements.
- [Cloud Router overview](https://docs.cloud.google.com/network-connectivity/docs/router/concepts/overview) — BGP control plane, regional/global mode, and learned routes.
- [VPC Network Peering](https://docs.cloud.google.com/vpc/docs/vpc-peering) — subnet/custom route exchange, transit limits.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — path simulation and diagnostics.
- [Create and run Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests) — hands-on guide, API/IAM prerequisites.
- [Cloud NAT overview](https://docs.cloud.google.com/nat/docs/overview) — NAT and Internet traffic for private resources.
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) — observing traffic metadata.
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls) — access control independent of routing.

**Key takeaway:** Google Cloud routes traffic using a **specific selection order**, in which special paths, PBRs, and subnet routes come ahead of custom route prefix/priority comparisons. Learning the true order, checking **next hops and return paths**, and verifying with Effective routes/Connectivity Tests will help you explain packet behavior and operate VPCs safely.
