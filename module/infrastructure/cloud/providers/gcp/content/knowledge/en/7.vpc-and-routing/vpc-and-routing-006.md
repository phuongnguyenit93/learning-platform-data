# VPC Network Peering and Route Propagation Limits

## Learning Objectives

After this lesson, learners will be able to:

1. Explain how **VPC Network Peering** connects two VPC networks in Google Cloud using internal IP addresses, and distinguish direct peering from **transitive routing**.
2. Identify which routes are exchanged by default, which require **export/import custom routes**, and which cannot be exchanged over peering.
3. Design connectivity across projects using non-overlapping IP ranges; inspect peering status, imported/exported routes, effective routes, and firewall rules.
4. Analyze limits related to CIDR conflicts, route priority, Cloud Router, on-premises, IPv6, and **peering group** quotas.
5. Select the right connectivity model for Compute Engine, GKE, Cloud Run, databases, internal services, and hybrid environments.

## 1. Real-World Problem: Two Private Networks Need to Communicate

An enterprise may split Google Cloud into multiple projects:

- **Application project** running a Java API on Compute Engine or workloads using a VPC.
- **Shared services project** hosting data-processing VMs, caches, or internal endpoints.
- **Analytics project** running jobs that access data over private connectivity.

Separating projects supports IAM delegation, budget governance, separation of responsibilities, and resource organization. However, VMs located in **two different VPC networks** do not automatically communicate over internal IP addresses just because both projects belong to the same organization.

**VPC Network Peering** establishes connectivity between **two VPC networks** in Google Cloud. Once both sides configure a valid peering connection, they can exchange supported route types so resources in one VPC can send packets to address ranges in the other VPC over Google's private network. The two VPCs remain independently administered; peering does not automatically replicate IAM or firewall rules.

In the **CLOUD_PROVIDERS_GCP** module, peering knowledge is foundational when designing networks for Compute Engine, GKE, VPC-connected Cloud Run, storage/database systems, and automated releases. Proper design helps applications find paths, scale reliably, and control security, availability, and cost risks.

### Initial Model

Suppose there are two **custom mode VPC** networks with non-overlapping subnet ranges:

| Component | Project | VPC | Illustrative IPv4 subnet range | Purpose |
|---|---|---|---|---|
| Application | app-dev-001 | vpc-app | 10.10.0.0/16 | API and application VMs |
| Shared services | shared-svc-001 | vpc-shared | 10.20.0.0/16 | Cache, internal backends |

Project IDs and CIDRs in this lesson are **hypothetical**. In production, use planned real IDs and network ranges, and check addresses across all existing peers and anticipated future connections.

~~~mermaid
flowchart LR
    subgraph P1["Project app-dev-001"]
      A["VPC app<br/>10.10.0.0/16<br/>Application VMs"]
    end
    subgraph P2["Project shared-svc-001"]
      B["VPC shared<br/>10.20.0.0/16<br/>Internal backends"]
    end
    A <-->|"VPC Network Peering<br/>subnet routes"| B
~~~

For the application to call a backend at **10.20.x.x**, you need at minimum: an **ACTIVE** peering connection, an effective destination route, firewalls allowing the traffic, and the service listening on the right IP/port. Merely creating the peering connection does not prove the application will communicate successfully.

## 2. At What Level Does VPC Network Peering Operate?

### 2.1. The Connected Entity Is the VPC, Not an Individual Subnet

A peering connection joins **two VPC networks**. Under route exchange policies, each network learns paths to the other network's subnets. This scope differs from creating a VPN tunnel between two machines or simply opening a port to a single service.

Peering can be used between VPCs in **two different projects**, even across different Google Cloud organizations if organization policies allow it. Each side manages its own peering configuration.

### 2.2. Both Sides Must Declare Corresponding Configurations

When creating peering via **gcloud/Console**, the VPC A administrator creates a peering configuration pointing to VPC B; the VPC B administrator creates a corresponding configuration pointing back to VPC A.

| Status | Meaning |
|---|---|
| **INACTIVE** | No matching configuration exists on the other side, or the connection is not yet established |
| **ACTIVE** | Both VPCs have established the peering connection |

Some infrastructure tools such as Terraform can manage both sides in a single workflow, without altering the principle that both sides must confirm the connection. **ACTIVE** status only indicates that the peering relationship is established; effective routes and firewalls must still be verified.

### 2.3. VPCs Remain Independent in Administration and Security

- **IAM roles** on VPC A are not automatically granted to VPC B administrators.
- **VPC firewall rules** and **firewall policies** are not synchronized across peering.
- A firewall rule in VPC A cannot use a **network tag** or **service account** of a VM in VPC B to identify that VM the way it works within the same VPC.
- **Compute Engine internal DNS names** generated in one VPC are not automatically resolved from a peer VPC. If cross-network name resolution is needed, design DNS separately, e.g., using appropriate Cloud DNS mechanisms.
- Peering does not automatically grant access to Google Cloud APIs, Cloud Storage buckets, or databases: those services still require authentication, IAM, and their own connectivity methods.

## 3. What Is Route Exchange?

A **route** specifies an IP destination and how packets are forwarded. For peering, routes originating in network A can be **exported** from A and **imported** into B; B does the same in the reverse direction.

~~~mermaid
flowchart LR
    SA["Subnet or custom route<br/>originating in VPC A"] --> EA["A: export route"]
    EA --> IB["B: import route"]
    IB --> RB{"Is route effective<br/>in VPC B?"}
    RB -->|Yes| OK["Path exists to destination prefix"]
    RB -->|Dropped or shadowed| NO["Route is not used"]
~~~

**Export** and **import** are two independent decisions made by the two sides. VPC A enabling custom route export is **not enough** if VPC B has not enabled matching import. Conversely, if VPC B enables import while VPC A does not export, B will not receive those custom routes either.

You must distinguish between **advertised / import candidate** and **installed into the effective route table**. A route may appear in the incoming list yet not be used due to duplication or conflict with another route.

## 4. Exchanged Route Types and Mandatory Limits

### 4.1. Overview Table

| Route type | Default over peering | Conditions/control flags | Important notes |
|---|---|---|---|
| **IPv4 subnet route using private ranges**: both primary and secondary ranges | **Always exported and imported** | No flag to disable specifically for this type | Subnets across the two peered VPCs must not overlap |
| **IPv4 subnet route using privately used public IPs** | **Exported by default**, import **disabled by default** | **--export-subnet-routes-with-public-ip** and **--import-subnet-routes-with-public-ip** | Must be distinguished from regular public Internet addresses |
| **IPv6 subnet route**, internal or external | **Not exchanged in IPv4-only peering** | Both sides set **--stack-type=IPV4_IPV6** | Requires IPv6-capable subnets/VMs and permitting organization policies |
| **Custom static IPv4 route** without network tags and without default Internet gateway next hop | **Disabled by default** | Source side **--export-custom-routes**; receiver side **--import-custom-routes** | Only valid next hops and route conditions are exchanged |
| **Dynamic IPv4 route** learned by Cloud Router | **Disabled by default** | Export/import custom routes on the respective sides | Affected by dynamic routing mode and route limits |
| **Supported custom IPv6 static/dynamic route** | **Disabled by default** | Dual-stack peering and export/import custom routes | Verify next-hop type, region, and IPv6 conditions |
| **Static route with network tags** | **No** | No flag to exchange | Tagged routes apply only within their defining scope |
| **Static route with default Internet gateway next hop** | **No** | No flag to exchange | Never treat peering as a way to share a default Internet gateway |
| **Policy-based route** | **No** | Peering does not support exchange | Design another appropriate routing mechanism if the app needs it |
| **Route already imported from another VPC peer** | **No** | Cannot be enabled for re-export over peering | Foundation of **non-transitivity** |

Two common points of confusion:

1. **Private IPv4 subnet routes are always exchanged.** You do not need to enable **--export-custom-routes** just for VMs in VPC A to reach private subnets of VPC B.
2. **Custom static/dynamic routes are not exchanged by default.** Enabling **--export-custom-routes** is only half the requirement; the receiving network must also enable **--import-custom-routes**.

### 4.2. When Are Custom Routes Needed?

For example, VPC B has a Cloud VPN or Cloud Interconnect link to an on-premises system **172.20.0.0/16**. Cloud Router in B learns the on-premises prefix and creates a **dynamic route**. If VMs in VPC A need to go through B to reach on-premises, B must **export custom routes** and A must **import custom routes**.

This lets A use **a route originating in B** to reach a system outside Google Cloud, subject to path and return-route conditions. It does **not** allow B to receive a route from VPC C and re-advertise that route to A.

### 4.3. Why Can't You Toggle Individual Private Subnet Routes?

VPC Network Peering provides toggles for **route groups** (privately used public subnets, custom routes, IPv6). For private IPv4 subnets, routes are exchanged by default with no per-range export/import control. If you must completely isolate prefix visibility, revisit **VPC segmentation, connectivity methods, and network policies** instead of expecting a per-subnet import filter.

## 5. The Most Important Limit: VPC Network Peering Is Non-Transitive

Suppose three VPCs are connected:

~~~mermaid
flowchart LR
    A["VPC A<br/>10.10.0.0/16"] <-->|"Peering A–B"| B["VPC B<br/>10.20.0.0/16"]
    B <-->|"Peering B–C"| C["VPC C<br/>10.30.0.0/16"]
    A -.- C
~~~

When **A ↔ B** and **B ↔ C** are both ACTIVE:

| Traffic | Direct path through declared peerings? | Why? |
|---|---|---|
| VM A → subnet B | **Possible** | A receives B's subnet routes |
| VM B → subnet C | **Possible** | B receives C's subnet routes |
| VM A → subnet C **via B** | **No** | B does not re-export peering subnet routes learned from C to A |
| VM C → subnet A **via B** | **No** | B does not re-export peering subnet routes learned from A to C |
| VM A ↔ C after adding direct A–C peering | **Possible** | Direct route exchange exists, if CIDRs, firewalls, and other conditions are valid |

**Non-transitivity** is a design property. It cannot be worked around by:

- Enabling **--export-custom-routes** on B to try re-exporting routes B **imported from C**.
- Enabling **--import-custom-routes** on A and assuming A will learn C's routes.
- Simply opening firewalls across all three VPCs.
- Adjusting route priorities to force B to act as a transit router for A → C over peering.

None of those actions convert peering routes into routes originating in B.

### 5.1. When Many VPCs Need to Communicate

Consider these alternatives based on scale and goals:

| Design | Best suited for | Trade-offs to evaluate |
|---|---|---|
| **Direct peering for each pair needing communication** | Few VPCs, only a handful of clear network relationships | Managing many connections, IP ranges, firewalls, and quotas as VPC count grows |
| **Shared VPC** | Multiple projects needing to share one centrally governed network | Changes network ownership model, IAM permissions, and host/service project governance |
| **Network Connectivity Center (NCC)** | Hub-and-spoke topology or large-scale connectivity per supported NCC features | NCC-specific configuration, quotas, cost, and policies; must verify route conditions and spoke types |
| **Private Service Connect (PSC)** | Consumers only need to access a specific service rather than the VPC's entire IP space | Configured per service/endpoint; producer/consumer model differs from peering |
| **Cloud VPN / Cloud Interconnect** | Hybrid, multi-cloud, or connectivity to networks outside Google Cloud | BGP, route advertisement, bandwidth, HA, and link operations |

No single choice guarantees access and reliability on its own: every model still requires its own IAM, DNS, firewalls, routes, monitoring, and cost evaluation.

## 6. An Easily Misunderstood Exception: Reaching On-Premises via an Intermediate VPC

**Non-transitivity between peerings** does not mean VPC A cannot use **B's Cloud VPN/Interconnect path** to reach an on-premises network.

Suppose:

- **VPC A**: subnet 10.10.0.0/16, running applications.
- **VPC B**: subnet 10.20.0.0/16, owning Cloud VPN and Cloud Router.
- **On-premises**: network 172.20.0.0/16.
- **A ↔ B**: direct peering, with no VPC C in the path.

~~~mermaid
flowchart LR
    A["VPC A<br/>10.10.0.0/16"] <-->|"Peering<br/>A imports custom routes<br/>B exports custom routes"| B["VPC B<br/>10.20.0.0/16<br/>Cloud Router"]
    B <-->|"Cloud VPN or Interconnect<br/>BGP"| O["On-premises<br/>172.20.0.0/16"]
~~~

Prerequisites include:

1. **B learns 172.20.0.0/16** as a local dynamic route from Cloud Router or has a valid local custom route to on-premises.
2. **B exports custom routes**, and **A imports custom routes**, so that the 172.20.0.0/16 route can take effect in A.
3. **On-premises has a route back to 10.10.0.0/16**, typically via appropriate custom prefix advertisements on B's Cloud Router. Cloud Router does not automatically advertise peer A's subnets to on-premises arbitrarily.
4. Firewalls on all sides, routing policies, and hybrid links permit the flow.
5. Networks use non-conflicting IP ranges; deployment regions of dynamic routes align with dynamic routing mode.

Here A reaches **on-premises** because B exports one of B's **local dynamic routes**—not because B is re-exporting a peering route received from a third VPC.

If you add **VPC C** also peered with B, both A and C can learn the route to **on-premises** through B per configuration. Yet **A still cannot reach subnet C through B**, because subnet C is a peering route imported into B.

## 7. Non-Overlapping CIDRs and IP Planning

### 7.1. Two Peered Subnets Must Not Overlap

Google Cloud rejects peering creation if subnet routes have identical, enclosing, or enclosed address ranges under overlap checks.

Examples:

| VPC A | VPC B | Can peer under this IP condition? |
|---|---|---|
| 10.10.0.0/16 | 10.20.0.0/16 | **Yes**, two disjoint prefixes |
| 10.10.0.0/16 | 10.10.1.0/24 | **No**, B falls inside A |
| 10.10.0.0/16 | 10.10.0.0/16 | **No**, identical |
| 10.10.0.0/24 | 10.10.1.0/24 | **Yes**, two non-overlapping /24s |

This applies to both **primary and secondary IPv4 subnet ranges**. When expanding a VPC that is already peered, Google Cloud also checks new subnets for conflicts against existing related subnet routes. Hence the network team must maintain a **CIDR allocation registry** across all projects, including GKE Pod/Service pools and reserved expansion blocks.

### 7.2. Why Are Two Auto Mode VPCs Unsuitable for Peering?

**Auto mode VPC networks** create subnets in a default address set with identical structure; therefore **two auto mode VPCs cannot be peered**. Long-term practice favors **custom mode VPCs** with pre-planned CIDRs. If peering an auto mode VPC with a custom mode VPC, you must still verify the custom mode subnet ranges so they do not overlap with ranges used by auto mode.

### 7.3. Custom Routes and Subnet Routes Also Have Conflict Rules

It is not only subnet-vs-subnet: a custom static route in VPC A can block importing a subnet route from B if its prefix equals or falls inside that subnet route's range. Conversely, a peering custom route is also disallowed from having a destination equal to or inside a local subnet route of the receiving VPC in cases defined by Google Cloud.

**Do not try to work around it by changing priorities** when a route-type conflict causes peering/route creation to fail. Read the route interaction rules and update your IP plan or connectivity model.

## 8. Route Selection: Imported Does Not Mean Selected

Google Cloud computes **effective routes** based on local routes, peer-imported routes, destination prefixes, route types, regions, and precedence mechanisms. When troubleshooting, check which route is actually used.

### 8.1. Prefix and Route Source Matter More Than Priority Assumptions

For example, VPC A has a local route matching a destination while also importing a route from a peer. If A already has a local route with the same destination or a more specific destination under routing selection rules, the peer route may be ignored.

Another trap: A peers with B and C; **both B and C advertise the exact same most-specific custom route prefix**. In certain cases, Google Cloud uses an internal algorithm to pick one peer before considering route priority, and users **cannot configure which peer wins**. Avoid relying on two peers advertising the same prefix to engineer priority-based ordered failover.

### 8.2. Local Routes, Peering Routes, and Cloud Router Routes

| Source | Example | What to verify |
|---|---|---|
| **Local subnet route** | 10.10.0.0/16 in VPC A | Actual subnet range in A, no overlap |
| **Peering subnet route** | 10.20.0.0/16 from VPC B | Peering ACTIVE, subnet route type eligible for import |
| **Local static route** | Route to appliance in VPC A | Destination and next hop, tags, potential conflicts |
| **Peering static route** | Custom route from VPC B | Export/import custom enabled in right direction; supported next-hop type |
| **Local dynamic route** | Cloud Router A learns prefix from VPN | Regional/global dynamic routing mode and next hop |
| **Peering dynamic route** | Cloud Router B learns 172.20.0.0/16; A imports | Export/import custom, region, route conflicts, and quotas |

There is no simple rule that "lower route priority number always beats every other route." Selection also depends on route type, prefix length, and evaluation steps before priority comparison. For complex failures, consult the **VPC route selection order** docs and inspect the **Effective routes** table rather than guessing from a priority column.

### 8.3. Dynamic Routing Mode Affects Dynamic Routes

Cloud Router can learn routes via BGP, but which regions apply dynamic routes depends on the **dynamic routing mode** of the learning VPC and how Google Cloud processes dynamic routes imported over peering.

- **Regional dynamic routing**: learned routes apply within the specified regional scope.
- **Global dynamic routing**: allows learned routes to be used across multiple regions per service rules, accounting for route selection and priority values.

When VMs in another region cannot reach on-premises even though VMs in the same region can, check **dynamic routing mode**, route-receiving region, Cloud Router, and the effective routes table in each region.

## 9. Quotas and Peering Group Limits

VPC Network Peering enforces **per-VPC quotas** and **per-peering-group quotas**. For a VPC X, X's peering group consists of **X itself and the VPCs directly peered with X**; it does not automatically extend to all VPCs reachable over multiple hops.

Example:

~~~text
VPC A ↔ VPC B ↔ VPC C

Peering group from A's perspective: {A, B}
Peering group from B's perspective: {A, B, C}
Peering group from C's perspective: {B, C}
~~~

### 9.1. Quotas to Monitor

- **Peerings per network**: number of peering connections per VPC.
- **Subnet ranges per peering group**: number of local subnet ranges plus those from connected peers.
- **Static routes per peering group**: limit on total static routes across the peering group.
- **Dynamic routes per region per peering group**: number of dynamic routes that can be programmed per region.

Exact quota values depend on quota type, project, region, and effective peering group limits; **do not hardcode a fixed number** into long-term designs. Check **IAM & Admin → Quotas & System Limits**, VPC quota documentation, and live quota metrics for your environment.

### 9.2. What Happens When Route Quotas Are Exceeded?

In some cases, exceeding a limit causes operations to be rejected. Specifically, when hitting **dynamic routes per region per peering group**, some dynamic routes from peering **may fail to be programmed into effective routes** even though the peering connection remains up. Google Cloud uses an internal mechanism to drop excess peering dynamic routes, making it impossible to predict exactly which routes will be omitted.

Consequence: **peering is ACTIVE, yet some prefixes are unreachable**. When diagnosing, inspect quotas, regions, and suppressed routes—not just ACTIVE status.

### 9.3. Quotas and Costs Are Separate Concepts

VPC Network Peering bills data transfer under Google Cloud's network pricing policies; a private path does not mean every byte transferred between two VPCs is free. When designing multi-project and multi-environment connectivity, estimate inter-VPC traffic, geographic regions, and hybrid links; review billing/usage accordingly. Quotas primarily limit object or route counts, **not billing caps**.

## 10. Hands-On gcloud: Creating and Verifying A ↔ B Connectivity

This section assumes two existing VPCs, non-overlapping subnets, and appropriate network administration permissions. **Run create/update commands only in authorized practice environments**.

| Parameter | Assumed value |
|---|---|
| Project A | app-dev-001 |
| VPC A | vpc-app |
| Project B | shared-svc-001 |
| VPC B | vpc-shared |
| Peering on A | app-to-shared |
| Peering on B | shared-to-app |
| Illustrative region for inspecting routes | asia-southeast1 |

### Step 1 — Pre-Creation Checks

~~~bash
# Read info for both VPCs; replace with actual IDs
gcloud compute networks describe vpc-app --project=app-dev-001
gcloud compute networks describe vpc-shared --project=shared-svc-001

# Inspect subnets and IP ranges before checking overlap
gcloud compute networks subnets list --project=app-dev-001
gcloud compute networks subnets list --project=shared-svc-001

# Inspect existing peerings
gcloud compute networks peerings list --project=app-dev-001
gcloud compute networks peerings list --project=shared-svc-001
~~~

Check all **primary and secondary IP ranges**; if multiple VPC peerings exist, also check routes imported from other peers and peering group quotas. Confirm whether organization policies such as **constraints/compute.restrictVpcPeering** permit the two VPCs to connect.

### Step 2 — Create One End of Peering in VPC A

~~~bash
gcloud compute networks peerings create app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --peer-project=shared-svc-001 \
  --peer-network=vpc-shared
~~~

If B does not yet have its matching configuration, the connection is not ACTIVE yet. Do not treat this as an error if two teams are deploying on separate schedules.

### Step 3 — Create the Other End in VPC B

~~~bash
gcloud compute networks peerings create shared-to-app \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --peer-project=app-dev-001 \
  --peer-network=vpc-app
~~~

These commands create peering with **default IPv4 settings**, which suffices to exchange private IPv4 subnet routes in this example. If you want to add custom routes, configure them separately on both sides per the next section.

### Step 4 — Confirm ACTIVE

~~~bash
gcloud compute networks peerings list --project=app-dev-001
gcloud compute networks peerings list --project=shared-svc-001

gcloud compute networks describe vpc-app \
  --project=app-dev-001 \
  --format="yaml(peerings)"
~~~

Verify peer name, network, project, and status. Once ACTIVE, inspect **actual effective routes** before running connectivity tests.

### Step 5 — Inspect Imported/Exported Routes

~~~bash
# From VPC A's perspective: routes that are import candidates from B
gcloud compute networks peerings list-routes app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --region=asia-southeast1 \
  --direction=incoming

# From VPC A's perspective: routes exported from A to B
gcloud compute networks peerings list-routes app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --region=asia-southeast1 \
  --direction=outgoing
~~~

**Important:** **list-routes** outputs a list of **route exports and import candidates**; this command does not evaluate every conflict case when Google Cloud selects final routes. To see which routes are actually used or suppressed, open **VPC Network → Routes → Effective routes** in Console and select the VPC/region to inspect.

### Step 6 — Check Firewalls and Connectivity

Suppose an application VM in A needs to connect on TCP/443 to a service in B. The B administrator must create an appropriate **ingress allow rule** scoped to source range 10.10.0.0/16 and the target VMs; the A administrator must check egress rules and applicable policies.

Illustrative firewall rule in VPC B (deploy only after confirming the list of receiving machines):

~~~bash
gcloud compute firewall-rules create allow-app-to-shared-https \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=10.10.0.0/16 \
  --target-tags=shared-https
~~~

This rule selects **target VMs within VPC B itself** carrying network tag **shared-https**; **source-ranges** specifies VPC A's source IP range. Do not attempt to use a tag from a VM in A as a source tag in a firewall rule in B, because tags are not evaluated across VPCs that way.

Test from an authorized VM in A to the **actual internal address** of backend B, then verify:

1. Are DNS/destination address correct?
2. Is the route to B's prefix effective where the packet originates?
3. Do ingress firewalls in B and egress firewalls in A allow it?
4. Is the backend listening on TCP/443 with matching certificates or authentication policies?
5. If still failing, do **Connectivity Tests**, VPC Flow Logs (if enabled), and application logs reveal the cause?

## 11. Hands-On Custom Routes: Letting VPC A Reach On-Premises via B

In this example, **VPC B already has Cloud VPN/Interconnect and Cloud Router**, and has learned the route to **172.20.0.0/16**. We only illustrate the peering commands; **they do not create VPN/Cloud Router automatically**.

### Step 1 — B Exports Custom Routes

~~~bash
gcloud compute networks peerings update shared-to-app \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --export-custom-routes
~~~

### Step 2 — A Imports Custom Routes

~~~bash
gcloud compute networks peerings update app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --import-custom-routes
~~~

### Step 3 — Verify in A

~~~bash
gcloud compute networks peerings list-routes app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --region=asia-southeast1 \
  --direction=incoming
~~~

Then inspect **Effective routes** in the region containing VM A. Prefix **172.20.0.0/16** must be validly selected without being discarded by conflict or quota. If missing, check whether Cloud Router in B learned the route, whether B exports, whether A imports, dynamic routing mode, and route suppressions.

### Step 4 — Don't Forget the Return Path

On-premises must know the path back to **10.10.0.0/16**. If using Cloud Router with custom advertisements, configure B's Cloud Router to advertise A's approved prefixes to on-premises. Ensure the on-premises router accepts and uses the return route, policies permit it, and firewalls on both sides are valid.

**Complete testing must verify both directions.** Seeing the outbound route in VPC A does not prove on-premises machines have a return route or matching permissions.

### Step 5 — If Both Sides Need Custom Routes

Only when custom routes must be shared **bidirectionally** should both sides configure **--export-custom-routes** and **--import-custom-routes**. Do not enable broadly when only one direction is needed; importing extra prefixes can alter effective routes and increase quota consumption.

## 12. Limits Beyond Route Exchange

### 12.1. IPv6 Must Be Enabled Properly

Peering defaults to **IPv4-only stack type**. To exchange IPv6 subnet routes, both sides must configure dual-stack (**IPV4_IPV6**) and subnets/VMs must have appropriate IPv6 addresses. Exchanging **IPv6 custom routes** also requires enabling custom route export/import in the appropriate direction.

~~~bash
# Illustrative update on side A
gcloud compute networks peerings update app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --stack-type=IPV4_IPV6

# Illustrative update on side B
gcloud compute networks peerings update shared-to-app \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --stack-type=IPV4_IPV6
~~~

Do not apply this operation before checking organization IPv6 policies, CIDRs and subnet types, firewall rules, and administrative permissions.

### 12.2. DNS Does Not Propagate Over Peering

A machine in A reaching IP **10.20.0.5** yet failing to resolve the Compute Engine internal DNS name of VM B is a normal occurrence. That is a **DNS** issue, not proof that peering failed to exchange routes.

If shared service names are needed, design Cloud DNS private zones, DNS peering, or appropriate resolution policies scoped to the system. Never assume peering automatically shares all hostnames or private zones.

### 12.3. Internet Egress or Cloud NAT Is Not Automatically Shared

Static routes pointing to the **default Internet gateway** are not exported over VPC Network Peering. Never expect a VPC with Cloud NAT or an Internet gateway to automatically serve as an Internet egress point for a peer simply because they are peered.

If the architecture needs centralized egress, evaluate specific routing models, appliances, load balancing, NAT, and supported networking products. That is a separate problem from exchanging default subnet routes.

### 12.4. Matching Peering Names Do Not Imply Shared Policy

The two sides maintain separate configurations and separate route-exchange flags. One side changing **import custom routes** or **stack type** can alter connectivity. Manage them with IaC, reviews, and drift alerts rather than relying solely on manual Console changes.

## 13. Diagnostics: Peering Is ACTIVE Yet Traffic Fails

| Symptom | Common cause | Practical check |
|---|---|---|
| Cannot create peering | Overlapping subnet CIDRs, org policy forbids peering, wrong network/project name | Primary/secondary ranges, **restrictVpcPeering**, VPC object |
| Peering stays **INACTIVE** | Missing reciprocal configuration or pointing to wrong network | Both peering ends, project, and VPC |
| ACTIVE yet A cannot reach B's subnet | Firewall, route conflict, wrong target IP, workload not listening | Effective routes, firewall, connectivity test |
| A reaches B, A to C via B fails | **Peering is non-transitive** | Check topology; do not expect B to re-export C's peering routes |
| A cannot reach on-prem via B | B hasn't exported custom, A hasn't imported, B hasn't learned route, missing return route | BGP/Cloud Router, incoming routes, effective routes, return route |
| One region reaches on-prem, another does not | Dynamic routing mode and per-region route applicability | Effective routes per region, Cloud Router |
| list-routes shows prefix yet traffic still fails | Imported route is a candidate but suppressed or shadowed by another route | Console **Effective routes**, suppression status, conflicts |
| Some prefixes disappear after adding a peer | Peering group quota or route conflicts | Quota metrics, dynamic routes per region, peering group |
| VM connects by IP yet name fails to resolve | Internal DNS is not automatically shared over peering | DNS configuration, private zones, DNS peering |
| Enabled custom export/import yet Internet does not go through B | Default Internet gateway route is not exchanged | Egress/NAT architecture, route next-hop type |
| Thought A's VM tag/SA works in B's firewall | Network tags/service accounts are not referenced across VPCs | Source IP range, B's internal target tag, separate policy |
| Enabled IPv6 yet no IPv6 routes | One side not dual-stack, missing IPv6 subnet, blocked by policy | Stack type on both sides, IPv6 subnets, and effective routes |

### Layer-by-Layer Investigation Process

1. **Topology:** should traffic go A→B or A→C via B? If transitive transit is needed, stop and redesign.
2. **IP:** do any prefixes overlap? Do local subnets and custom routes conflict?
3. **Peering:** are both sides ACTIVE? Are export/import options set properly per route type?
4. **Routing:** does the prefix appear in incoming? Is it selected in **effective routes** in the right region?
5. **Quotas:** have dynamic/static routes or peering group limits been reached?
6. **Security:** ingress/egress firewalls, authentication, and destination service policies.
7. **End-to-end:** DNS, listeners, return routes, logs, and application tests.

Every change requires **before/after test evidence**. Never rush to enable all custom routes or open 0.0.0.0/0 firewalls just to make a test pass.

## 14. Design Scenario: Shared Services, Data, and On-Premises Network

Enterprise **An Khang** has:

- **VPC app**, 10.10.0.0/16: sales API on VMs and several VPC-connected Cloud Run workloads.
- **VPC shared**, 10.20.0.0/16: internal backends; Cloud Router connected to on-premises 172.20.0.0/16.
- **VPC analytics**, 10.30.0.0/16: isolated data-processing workloads.

Requirements:

1. App API calls backends in shared over private IPs.
2. Analytics calls backends in shared, but **must not** access app.
3. Both app and analytics need access to an on-premises system already connected through shared's Cloud VPN.
4. All communication must have clear firewall policies, logging, and administrative accountability.

### 14.1. Proposed Topology for Current Requirements

~~~mermaid
flowchart LR
    APP["VPC app<br/>10.10.0.0/16"] <-->|"Peering"| SH["VPC shared<br/>10.20.0.0/16<br/>Cloud Router"]
    AN["VPC analytics<br/>10.30.0.0/16"] <-->|"Peering"| SH
    SH <-->|"VPN / BGP"| ON["On-premises<br/>172.20.0.0/16"]
    APP -.- AN
~~~

In this model:

- Both app and analytics learn shared's **private subnet routes**, so they can reach backend B if firewalls permit.
- Shared learns app and analytics subnets through **two direct peerings**.
- Shared can export its **local dynamic route** to 172.20.0.0/16 to app and analytics. Each receiving network must import custom routes.
- Cloud Router in shared advertises **necessary app and analytics prefixes** to on-premises per appropriate rules and route advertisements; firewalls and BGP must allow return traffic.
- App and analytics **cannot automatically communicate directly through shared**. This matches the current isolation requirement.

### 14.2. Pre-Production Verification Matrix

| Check | Expected result |
|---|---|
| App/shared/analytics subnets do not overlap | PASS |
| Both app–shared and analytics–shared peerings ACTIVE | PASS |
| App → shared backend; analytics → shared backend | Succeeds on permitted ports |
| App → analytics via shared | **No transitive peering route** |
| On-premises prefix in app/analytics effective routes | Present when custom routes are configured properly |
| On-premises → app/analytics prefixes | Return routes and firewalls valid |
| Resources in each project maintain separate IAM | No unintended cross-project privilege grants |
| Route/peering group quotas at shared have headroom | Growth capacity reserved |
| Cloud Monitoring/VPC logs and connectivity tests | Clear owner assigned for incident response |
| Inter-VPC and on-premises traffic estimates | Included in cost budget |

### 14.3. If Requirements Change to "App Must Talk to Analytics"

The simplest option with a small number of VPCs is creating a **direct app–analytics peering** after checking CIDRs, quotas, and firewalls. If VPC count grows sharply or you need a central connectivity architecture with policy-controlled transit, consider **NCC/Shared VPC/PSC** depending on workload type and access scope, rather than trying to force B into a peering transit hub.

## 15. Practice Exercises

### Exercise A — Predict Route Exchange

There are three VPCs:

| VPC | Subnet route | Custom route |
|---|---|---|
| A | 10.1.0.0/16 | None |
| B | 10.2.0.0/16 | Dynamic 172.16.40.0/24 learned from Cloud VPN |
| C | 10.3.0.0/16 | None |

Peerings **A–B** and **B–C** are ACTIVE, but **A–C has no peering**. B exports custom routes on both connections; A and C import custom routes.

**Answer:**

1. Does A learn B's subnet route 10.2.0.0/16?
2. Does A automatically learn C's subnet route 10.3.0.0/16 through B?
3. Can A learn 172.16.40.0/24? Besides the outbound route, what else must be checked to reach on-premises?
4. If B disables custom route export, does A still have a path to 172.16.40.0/24 over peering?
5. If A and C want to talk directly, what architectural options exist?

**Guided answers:** (1) Yes, for non-conflicting private IPv4 subnets; (2) No, because peering is non-transitive; (3) Possibly, if B's dynamic route is eligible and not suppressed, along with return routes, firewalls, and BGP/region alignment; (4) No, not via this custom route exchange; (5) direct A–C peering or evaluating another suitable network model.

### Exercise B — Spot Errors in a Production Change

An engineer writes in a change request:

> "Both peerings are ACTIVE. I enabled custom export on B, so all of C's subnets will be exported via B to A. No need to check firewalls or return routes because peering is bidirectional."

Point out at least **four flaws** in this reasoning and rewrite the verification plan.

**Hint:** distinguish B's own routes from routes imported from C, verify import on A, route applicability by region, each VPC's firewalls, return routes from the destination network, prefix conflicts, and quotas. The bidirectional nature of a peering relationship does not mean all custom routes are exchanged both ways or that all services open automatically.

### Exercise C — Write Inspection Commands

For peering **app-to-shared** in VPC **vpc-app**, project **app-dev-001**, and region **asia-southeast1**, write:

1. Command to list peerings in the project.
2. Command to view the network and peering state.
3. Command to list **incoming route candidates**.
4. Where in Console to view **effective routes** and suppressed routes.
5. How to investigate why prefix **172.20.0.0/16** is not effective.

**Hint:** use **gcloud compute networks peerings list**, **gcloud compute networks describe**, **gcloud compute networks peerings list-routes ... --direction=incoming**; then check effective routes, Cloud Router, custom export/import, dynamic routing mode, route conflicts, and quotas.

## 16. Key Takeaways and References

**Principles to remember:**

1. VPC Network Peering connects **two VPCs**; each side has independent administrative configuration and requires **ACTIVE** peering.
2. **Private IPv4 subnet routes are exchanged by default**; **custom static/dynamic routes** are exchanged only if the source exports and the receiver imports appropriately.
3. **Peering is non-transitive**: A–B and B–C do not allow A to reach C through B via route exchange; B cannot re-export routes imported from C.
4. **IPv6, privately used public IPv4, tagged static routes, default Internet gateway, and policy-based routes** follow distinct rules; never assume every route is shared.
5. **CIDR overlap, route conflicts, peering group quotas, dynamic routing mode, and firewalls** can leave peering ACTIVE while traffic still fails.
6. **List-routes shows export/import candidates**, whereas **Effective routes** reveals which routes are actually used or suppressed.
7. Reaching on-premises through a peer requires **valid custom routes plus a return path**; this differs from peering transit among three VPCs.

**Official Google Cloud Documentation:**

1. [VPC Network Peering — Overview, routes and limitations](https://docs.cloud.google.com/vpc/docs/vpc-peering) — peering principles, route exchange, non-transitivity, and route interactions.
2. [Set up and manage VPC Network Peering](https://docs.cloud.google.com/vpc/docs/using-vpc-peering) — gcloud commands to create, update, and list incoming/outgoing routes.
3. [About peering connections](https://docs.cloud.google.com/vpc/docs/about-peering-connections) — ACTIVE/INACTIVE states and two-sided management.
4. [VPC routes](https://docs.cloud.google.com/vpc/docs/routes) — route classification, route selection, and route conflicts.
5. [VPC quotas and limits](https://docs.cloud.google.com/vpc/docs/quota) — peering group, static/dynamic route limits, and effective quotas.
6. [VPC network overview](https://docs.cloud.google.com/vpc/docs/overview) — comparing VPC Network Peering and Shared VPC.
