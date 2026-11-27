# IPv4, IPv6, Internal IPs, and External IPs on Google Cloud

> **Chapter:** VPC and Routing  
> **Lesson:** IPv4, IPv6, Internal IPs, and External IPs  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; thereby learning how to select services, protect resources, automate releases, and monitor reliability and cost. Understanding **IP addresses** is a prerequisite for building those systems: VMs need to communicate with databases over private paths, APIs need to serve internet users, and background jobs may only need to download patches and call Google APIs.

An IP address answers the question **what is the network source/destination**. The IP type, subnet, routes, firewalls, IAM, and service configuration work together to determine **whether packets reach their destination and whether requests are accepted**. This lesson distinguishes four commonly confused concepts: **IPv4**, **IPv6**, **internal IP**, and **external IP**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Recognize IPv4/IPv6 syntax, CIDR prefixes, RFC 1918 private IPv4 ranges, and internal-use IPv6.
2. Explain how a VPC is a global resource, subnets belong to regions, and IPs are assigned to VM network interfaces.
3. Distinguish **internal/external**, **private/public**, **ephemeral/static**, and **regional/global**.
4. Describe IPv4-only, dual-stack, IPv6-only, and how Google Cloud allocates IPv6 to subnets/VMs.
5. Select connectivity options: external IPs, load balancers, **Public NAT**, **Private Google Access**, and private service connectivity.
6. Read IP, route, and firewall configurations via Console/`gcloud` and investigate connectivity failures.
7. Design an IP scheme for Compute Engine, GKE, Cloud Run, and Cloud SQL with sound security, scalability, and cost.

## 2. Classification Axes Are Not Synonymous

| Axis | Values | Question |
|---|---|---|
| **Protocol version** | IPv4 / IPv6 | Which protocol family does the address belong to? |
| **Usage scope** | Internal / External | Does the address serve internal connectivity or can it be publicly routed? |
| **Address lifecycle** | Ephemeral / Static | Is the IP assigned temporarily with the resource or reserved in advance? |
| **Resource scope** | Regional / Global | Which region or global resource type is the IP bound to? |

A single VM can have an **ephemeral internal IPv4** and a **regional static external IPv4**. A load balancer can have a **global external IP**. A dual-stack VM can have an internal IPv4 and an external IPv6. Seeing an address like `10.x.x.x` is not enough to know whether that address is static or ephemeral.

**Remember:** a Google Cloud external IP is a public address routable on the internet, but **having an external IP does not mean ports are open**. Firewalls, listeners, routes, TLS, and authentication can still block access. Conversely, a VM without an external IPv4 can still reach the IPv4 internet via Public NAT.

## 3. IPv4, CIDR, and Address Range Planning

### 3.1. IPv4 Address Structure

IPv4 uses **32-bit** addresses, written as four decimal octets from 0–255, e.g., `10.24.0.10`. CIDR pairs a network address with a **prefix length**, for example:

- `10.24.0.0/24`: the first 24 bits identify the network prefix, leaving 8 bits for address values.
- `10.24.0.0/20`: a larger range with 4,096 address values.
- `10.24.0.10/32`: represents a single IPv4 address in firewalls/routing.

For example, the **primary IPv4 range** `10.24.0.0/24` on Google Cloud:

| Component | Value |
|---|---|
| CIDR | `10.24.0.0/24` |
| Total IPv4 values | `2^(32-24) = 256` |
| Network address | `10.24.0.0` |
| Virtual gateway | `10.24.0.1` |
| Last two reserved addresses | `10.24.0.254` and `10.24.0.255` |
| Assignable range in primary range | `10.24.0.2` to `10.24.0.253` |
| Number of usable addresses | **252** |

Google Cloud reserves **four addresses** in every **primary IPv4 range**: the first two and the last two addresses. This rule **does not apply in the same way** to **secondary IPv4 ranges**: per VPC documentation, all addresses in a secondary range can be used according to service mechanisms.

| Primary CIDR | Total addresses | Usable after reserving four addresses |
|---|---:|---:|
| `/28` | 16 | 12 |
| `/26` | 64 | 60 |
| `/24` | 256 | 252 |
| `/20` | 4,096 | 4,092 |

Never size a range to fit only the current number of VMs: autoscaling, GKE node/pod layers, new VMs, and reserved addresses can exhaust the subnet.

### 3.2. Private IPv4 and Special Ranges

Three **private** IPv4 ranges per RFC 1918:

| Range | Scope |
|---|---|
| `10.0.0.0/8` | Large space for enterprises |
| `172.16.0.0/12` | From `172.16.0.0` to `172.31.255.255` |
| `192.168.0.0/16` | Common in small networks, offices, labs |

Several special types:

- `127.0.0.0/8`: loopback, typically `127.0.0.1`.
- `169.254.0.0/16`: link-local, not a subnet range to arbitrarily assign to workloads.
- `198.51.100.0/24`, `203.0.113.0/24`, `192.0.2.0/24`: ranges **reserved for documentation**, not used as real internet IPs.

Google Cloud also supports **privately used public IPv4**: certain valid public ranges can be configured as **internal IPv4** inside a VPC under service rules. Thus, **internal** is not always strictly synonymous with "within the three RFC 1918 ranges."

### 3.3. Duplicate Addresses and Overlapping CIDRs

Two subnets in the same VPC must not have invalidly overlapping address ranges. When connecting via **Cloud VPN**, **Cloud Interconnect**, **VPC Network Peering**, or private services access, you must also check partner/on-premises networks.

~~~text
VPC retail-vpc (global)
├── subnet-app-sg       asia-southeast1  10.24.0.0/24
├── subnet-batch-sg     asia-southeast1  10.24.1.0/24
└── subnet-app-tokyo    asia-northeast1  10.25.0.0/24
~~~

These three subnets do not overlap. If the office network already uses `10.24.0.0/16`, the conflict must be resolved before hybrid connection; routing does not automatically resolve every duplicate-address case.

## 4. VPC, Subnets, and Network Interfaces

### 4.1. Global VPC, Regional Subnets

In Google Cloud:

- A **VPC network** is a **global** resource; routes and firewalls are managed within the scope of the VPC and associated policies.
- A **subnet** is a **regional** resource, with a primary IPv4 range and, depending on configuration, secondary IPv4/IPv6 ranges.
- A **Compute Engine VM** runs in a **zone**; each network interface connects to an appropriate subnet in the same region.
- A VM's **network interface** can have a primary internal IPv4, an optional external IPv4, and IPv6 configuration when supported by the subnet/interface.

~~~mermaid
flowchart TB
    V["VPC retail-vpc (global)"]
    V --> S1["Subnet app-sg<br/>10.24.0.0/24, Singapore"]
    V --> S2["Subnet batch-sg<br/>10.24.1.0/24, Singapore"]
    V --> S3["Subnet app-tokyo<br/>10.25.0.0/24, Tokyo"]
    S1 --> A["VM app-1: 10.24.0.10"]
    S2 --> B["VM batch-1: 10.24.1.20"]
    S3 --> C["VM app-2: 10.25.0.10"]
~~~

VMs in the same VPC can communicate over internal IPs across subnets/regions when routes are valid, yet **ingress and egress firewalls** must still allow the traffic. "Same VPC" does not mean all ports are open by default.

### 4.2. Primary and Secondary IPv4 Ranges

An IPv4 subnet has a **primary range** to assign primary internal IPv4 addresses to VMs. **Secondary ranges** can serve alias IPs and services such as **VPC-native GKE**.

| Component | Common role |
|---|---|
| Primary IPv4 range | Primary addresses of VMs/nodes |
| Secondary IPv4 range | Alias IPs, Pod/Service ranges in supported GKE models |
| Alias IP | One or more additional IPv4 addresses/ranges attached to a VM interface |

GKE has multiple network modes and range allocation mechanisms; check cluster type, version, and projected Pod/node counts before planning. Do not assume every cluster uses secondary ranges in the exact same way.

### 4.3. Auto Mode or Custom Mode?

An **auto mode VPC** automatically creates IPv4 subnets for regions using Google Cloud's default ranges; convenient for exploration but hard to control in hybrid architectures. A **custom mode VPC** lets you select subnets/regions/CIDRs by plan and is much better suited when you need IPv6 control, multi-project environments, or peering.

Subnets with IPv6 are supported in a **custom mode VPC**. With an existing auto mode network, you must convert it to custom mode following the supported procedure if you want to add IPv6 subnets.

## 5. Internal and External IPs on Compute Engine

### 5.1. Internal IPv4

For IPv4-only or dual-stack interfaces, a VM has **one primary internal IPv4** from the primary subnet range. Two common allocation methods:

- **Ephemeral internal IPv4**: automatically assigned by Compute Engine or appropriately specified at VM creation; not a separate reservation held long-term.
- **Static internal IPv4**: reserved at the appropriate scope to keep a fixed address; can be assigned to compatible resources.

A static IP only preserves **address identity**; it does not ensure the VM stays running. If HA or failover is required, design load balancing, instance groups, managed services, and corresponding recovery mechanisms.

### 5.2. External IPv4

An external IPv4 is a public address usable for internet communication. Compute Engine typically maps external IPv4 via **one-to-one NAT** to the interface's primary internal IPv4; consequently, the public IP does not necessarily appear as a configured address inside the VM's OS.

- **Ephemeral external IPv4** can change upon release, reconfiguration, or VM lifecycle events.
- **Static external IPv4** is a reserved address, suitable when a fixed IP is needed for DNS, partner allowlists, or frontends.
- External IPv4 attached directly to a VM is typically **regional**. Certain load balancers have a **global external IP** frontend depending on the product type.
- External IPv4 addresses can incur **charges even while in use**; unused reserved addresses can also incur charges. Always check current pricing tables.

### 5.3. An External IP Does Not Automatically Expose a Service

To reach a VM from the internet, beyond an external IP you also need:

1. Routing/reachability and an **ingress firewall** permitting source, protocol, and port.
2. The application/OS **listening** on the appropriate address/port, not just `127.0.0.1`.
3. Correct DNS/TLS if using a domain name and HTTPS.
4. Application authentication/authorization, IAM for administrative actions, organization policies, or other network controls.

If a VM only needs SSH administration, consider **IAP TCP forwarding** or controlled private access rather than leaving SSH wide open to the internet by default.

## 6. IPv6: 128-Bit Addresses and Subnet Types

### 6.1. How IPv6 Is Written

IPv6 uses **128 bits**, written as hexadecimal groups separated by colons:

~~~text
2001:0db8:0001:0000:0000:0000:0000:0042
2001:db8:1::42
~~~

Both representations denote the same address. The `::` shorthand compresses a contiguous sequence of zero groups and may appear only once in an address. The prefix `2001:db8::/32` is reserved for **documentation**, not a live internet address assigned for testing.

| Range / type | Meaning |
|---|---|
| `::1/128` | IPv6 loopback |
| `fe80::/10` | Link-local |
| `fc00::/7` | Unique Local Address (ULA), used internally |
| `2001:db8::/32` | Documentation prefix |
| Validly allocated global unicast | Can be publicly routed per routes and firewalls |

IPv6 also involves DNS `AAAA` records, default route `::/0`, OS/network stack capabilities, and per-service support. You cannot use an IPv4 route to forward IPv6 packets.

### 6.2. Internal IPv6 and External IPv6

Within a custom mode VPC:

- **Internal IPv6** on a subnet uses a ULA range allocated by Google Cloud per network configuration. It serves communication within supported scopes and is **not directly routed on the internet**.
- **External IPv6** uses a public range, can route to the internet, and can also be used for communication between VMs inside the VPC; still subject to firewalls.
- **Dual-stack** allows an interface to have both IPv4 and IPv6 simultaneously.
- **IPv6-only** has only IPv6 on the interface under supported configurations; verify OS/image limitations and reachability to IPv4-only services.

### 6.3. /64 Prefix on Subnets and /96 on VMs

For IPv6-enabled subnets, Google Cloud allocates a **`/64` IPv6 range** with either **internal or external** access type. A VM network interface attached to an eligible subnet receives **a `/96` range**, internal **or** external matching the subnet. The first IPv6 address (`/128`) of the `/96` range is typically configured on the interface.

~~~text
Custom-mode VPC
└── Dual-stack subnet
    ├── Primary internal IPv4: 10.24.0.0/24
    ├── IPv6 subnet: /64, INTERNAL or EXTERNAL
    └── VM nic0:
        ├── Internal IPv4: 10.24.0.10
        ├── External IPv4: optional
        └── IPv6: one /96 matching subnet access type
~~~

**One interface cannot have both an internal `/96` and an external `/96` IPv6 simultaneously.** A VM requiring both types may need multiple interfaces subject to product rules. To use internal IPv6, the VPC must be provisioned with an appropriate internal IPv6 range before configuring the subnet.

### 6.4. IPv6 and NAT

External IPv6 enables connectivity to public IPv6 destinations per routes/firewalls; NAT44 is not needed for "IPv6 internet access." However, an **IPv6-only** source cannot talk directly to an **IPv4-only** destination. When required, check **DNS64/NAT64** configurations supported by Google Cloud for that workload type.

VPCs enforce **implied deny ingress** for IPv6 as well. Having an AAAA record or external IPv6 does not open HTTPS/SSH ports automatically. You must configure firewalls for the **IPv6 source range**, port, and target; avoid accidentally opening `::/0` to internal services.

## 7. Matrix of Interface Types and IPs

| Interface | Internal IPv4 | External IPv4 | IPv6 |
|---|---|---|---|
| **IPv4-only** | Required | Optional | None |
| **Dual-stack** | Required | Optional | One `/96` internal or external |
| **IPv6-only** | None | None | One `/96` internal or external |

This table describes **one network interface**. A VM with multiple interfaces can have more connection paths and address types; consult service limits when designing.

| Hypothetical workload | Example IP | Meaning |
|---|---|---|
| Batch VM | `10.24.1.20` internal, no external IPv4 | Background processing, outbound via NAT when needed |
| Legacy VM | `10.24.0.12` internal and external IPv4 as needed | May need partner connectivity |
| Dual-stack VM | Internal IPv4 plus one external `/96` IPv6 range | Testing IPv6 communication |
| Cloud SQL backend | Private endpoint per service configuration | Not a VM arbitrarily placed directly in the primary range |
| HTTPS load balancer | Public frontend IP per LB type | Centralized public web entry point |

## 8. Routing: How Do IPs Find Their Paths?

### 8.1. Routes Differ from Firewalls

**Routes** determine where packets are sent toward a destination range; in a VPC, routes are especially critical for **egress**. Subnet routes enable finding paths between ranges within the VPC; the default route or learned/configured routes can direct traffic toward the internet or hybrid networks.

**Firewalls** determine permitted traffic by source/destination, protocol/port, direction, and target. A VPC has **implied deny ingress, allow egress** rules unless overridden by higher-priority policies/rules. Firewalls are stateful for allowed connections.

~~~mermaid
flowchart LR
    VM["VM 10.24.1.20<br/>no external IPv4"]
    VM --> E["Egress firewall + route"]
    E --> D{"Which destination?"}
    D -->|Internal| P["Valid private VM/DB"]
    D -->|Internet IPv4| NAT["Public NAT"]
    NAT --> NET["IPv4 Internet"]
    D -->|Google APIs| PGA["Private Google Access<br/>or private endpoint"]
    PGA --> API["Google Cloud APIs"]
~~~

This diagram shows **options that must be configured**, not implying every path is already available. Internal IPv6 and external IPv6 have their own routing rules and do not go through NAT44 by default.

### 8.2. Default Route and Subnet Routes

| Destination CIDR | Meaning |
|---|---|
| `0.0.0.0/0` | IPv4 default route |
| `::/0` | IPv6 default route |
| `10.24.1.0/24` | Route to a specific IPv4 subnet |
| Subnet IPv6 prefix | Route to IPv6 addresses within the configured range |

Google Cloud selects paths based on **route type, prefix specificity, scope, and priority** among applicable routes. Never look at a single default route and conclude all traffic must go through the internet.

### 8.3. Example: "Same Subnet, Yet Cannot Connect"

VM A `10.24.0.10` calls VM B `10.24.0.20:8080`. If VM B lacks a matching ingress allow rule or the application only listens on `127.0.0.1:8080`, the connection still fails. The diagnostic order should be:

1. Are addresses/subnets/routes and IPv4/IPv6 families correct?
2. Do egress and ingress firewalls allow source, target, protocol, and port?
3. Are the OS firewall and process listening on the right IP/port?
4. Are DNS, TLS, and application authentication working?

## 9. How Can a VM Without an External IPv4 Access External Services?

### 9.1. Public NAT for Outbound IPv4

**Public NAT** (a type of Cloud NAT) allows resources in configured subnets—such as VMs without external IPv4—to **initiate** connections to IPv4 destinations on the internet via one or more shared external IPv4 addresses. Responses for established connections are returned to the VM; Public NAT **does not** allow unsolicited inbound connections.

~~~text
Batch VM: 10.24.1.20:53000
      → Public NAT (translates source to public IPv4 + port)
      → updates.example.org:443
      ← return traffic for established connection
~~~

Cloud NAT is a managed service configured alongside a **Cloud Router** in a region and serving selected subnets/ranges. Cloud Router manages the control configuration—it is not a proxy VM that you build and route all packets through manually. Cloud NAT can serve multiple supported workload types; for Cloud Run or GKE, check each service's VPC connectivity conditions.

What to monitor: **available NAT ports, port allocation failures, dropped packets, connection count, NAT IPs, and egress cost**. When many VMs simultaneously open large numbers of connections to one destination, NAT port limits can cause failures even while CPU and RAM look normal.

### 9.2. Private Google Access for Google APIs

**Private Google Access** lets VMs without external IPs connect to **supported Google APIs/services** without assigning a public IP directly to the VM. It is enabled per **subnet**, working with appropriate DNS, routes, firewalls, and IAM permissions.

For example, VM `10.24.1.20` needs to read objects from the Cloud Storage API. Conditions to verify:

1. The subnet has **Private Google Access enabled** as required by the connection type.
2. Google API endpoints/DNS and routes are properly configured; default domains or private/restricted VIPs may be used per requirements.
3. VPC egress firewalls and network policies allow the traffic.
4. Required APIs are enabled if needed by the service; the service account has permission to read the bucket/object.
5. The destination is indeed a Google API/service supported by Private Google Access.

**Private Google Access does not grant IAM roles and is not Public NAT for arbitrary websites.** A VM might call a Google API endpoint successfully yet still fail to download a file from an internet website outside PGA's scope.

### 9.3. Private Service Connect and Private Services Access

| Mechanism | Typical need | What not to infer |
|---|---|---|
| **Public NAT** | Open **outbound** IPv4 internet connections from VMs without external IPv4 | Does not open public inbound ports |
| **Private Google Access** | Call Google APIs from VMs without external IPs | Not general Internet NAT |
| **Private Service Connect (PSC)** | Private endpoint to access Google APIs or published services per product | Having an internal IP does not mean every service is automatically usable |
| **Private services access** | Access certain managed services via private Service Networking/VPC peering connectivity | Not a service VM arbitrarily attached to your subnet |
| **VPC Network Peering** | Connect two VPCs over private address ranges per supported capabilities | Does not transitively forward across multiple VPC peerings by default |
| **Cloud VPN/Interconnect** | Connect a VPC to on-premises or another cloud | Does not automatically resolve CIDR conflicts or open firewalls |

When working with **Cloud SQL**, choose private endpoint/PSC/private services access according to the service version's supported modes and capabilities. Do not assume creating a Cloud SQL "private IP" simply means picking an address from a VM primary subnet and assigning it to the DB instance.

### 9.4. NAT64 and IPv6-Only Flows

In supported Google Cloud configurations, **DNS64/NAT64** helps IPv6-only workloads access **IPv4-only** services. Check workload support, DNS resolvers, NAT methods, routes, and product limitations.

Public external IPv6 already has a path to the IPv6 internet when routes/firewalls allow; **NAT44 is not needed** for IPv6-to-IPv6 flows. Nor can you take an external IPv6 address and expect to reach every IPv4-only API by default.

## 10. Choosing IPs by Service in the Google Cloud Module

| Workload | Starting IP/connectivity model | What to verify |
|---|---|---|
| **Compute Engine backend** | Internal IPv4 only; use NAT/PGA/PSC if needed | Outbound needs, OS, routes, firewalls, IAP, or private access |
| **Public web VM** | Prefer evaluating an HTTPS load balancer with public frontend and internal backends | TLS, WAF, health checks, HA, and DNS |
| **GKE VPC-native** | Primary range for nodes; secondary ranges/alias IPs for Pods/Services per mode | IP exhaustion, CIDR overlap, egress NAT, network policies |
| **Cloud Run web API** | HTTPS/ingress endpoint provided by Cloud Run; LB if architecture requires | Do not treat the service as a VM with a fixed public IP on a NIC |
| **Cloud Run private connectivity** | Direct VPC egress or connector per supported capabilities | Service account, routes, firewalls, private DB endpoint |
| **Cloud SQL** | Private endpoint if public connectivity is unnecessary | Private services access/PSC, database auth, network policies |
| **Cloud Storage** | Accessed via endpoints/APIs and IAM | PGA/PSC when VM has no external IP; do not confuse with placing a bucket in a subnet |
| **Load balancer frontend** | External IPv4/IPv6 depending on load balancer type | Regional/global, tier, static reservation, backend health |

**Note on Cloud Run:** a service has an HTTPS URL and its own ingress/authentication settings. Cloud Run calling an internal VPC IP (egress) does not mean other clients in the VPC can connect to a "container's internal IP" like a VM. You must use ingress/endpoints supported by Cloud Run.

## 11. Deployment Scenario: Order System in Singapore

A retail company has an **Orders API on Cloud Run**, **Cloud SQL PostgreSQL** storing orders, and a **legacy VM** processing batches. The batch VM only needs to download patches from the IPv4 internet and read objects from Cloud Storage, without receiving public inbound connections. Buyers access the API over HTTPS from IPv4 or IPv6.

~~~mermaid
flowchart TB
    Client["Internet buyers IPv4/IPv6"]
    LB["HTTPS frontend/load balancer when needed"]
    API["Cloud Run Orders API"]
    SQL[("Cloud SQL private endpoint")]
    VM["Batch VM<br/>10.24.1.20, no external IPv4"]
    NAT["Public NAT - outbound IPv4"]
    NET["Internet - software update source"]
    PGA["Private Google Access"]
    GAPI["Google APIs / Cloud Storage"]
    OBS["Cloud Logging + Monitoring"]
    Client --> LB
    LB --> API
    API -->|"Configured private connectivity"| SQL
    VM --> NAT
    NAT --> NET
    VM --> PGA
    PGA --> GAPI
    API -->|"API access + IAM"| GAPI
    API -. "Logs/metrics" .-> OBS
    VM -. "Logs/metrics" .-> OBS
~~~

This diagram is a **conceptual model**, not a direct deployment configuration. Cloud Run can serve an HTTPS endpoint without a separate load balancer; if using an LB, choose a supported product and backend connection method. A Cloud SQL private endpoint requires specific private connectivity configuration and does not necessarily carry an IP inside the VM primary subnet.

### 11.1. Illustrative CIDR Plan

| Component | Assumed value | Purpose |
|---|---|---|
| VPC | `retail-prod-vpc`, custom mode | Global network boundary |
| App subnet | `retail-app-sg`, `10.24.0.0/24`, `asia-southeast1` | Application-related workloads |
| Batch subnet | `retail-batch-sg`, `10.24.1.0/24`, `asia-southeast1` | Background VMs without public IPv4 |
| Batch VM | Internal IPv4 `10.24.1.20` | No inbound access from internet |
| Public NAT | Region `asia-southeast1`, applied to batch subnet | Outbound IPv4 |
| Private Google Access | Enabled on batch subnet if needed | Calling Google APIs |
| Public HTTPS frontend | External IP per LB/Cloud Run type | Buyers connect over HTTPS |
| IPv6 | Choose dual-stack/IPv6-only on subnet when needed | Evaluate support and firewalls before enabling |

If an on-premises network planned for connection already uses `10.24.0.0/16`, do not deploy these example ranges. Establish an **IP address plan** for all connected networks first.

### 11.2. Security Controls

- **Public API, private database:** do not expose databases on internet-routable addresses if only applications should access them.
- **Backends without external IPs:** use NAT/PGA or private endpoints; restrict ingress.
- **Port- and target-scoped firewalls:** allow HTTPS only at the frontend and DB ports only from valid workloads.
- **Workload identity:** use Cloud Run/VM service accounts with least privilege to access Google APIs.
- **DNS/TLS protection:** `A` and `AAAA` records must point to endpoints supporting the matching address family; test TLS in practice.
- **Governance:** restrict IAM permissions for modifying routes/firewalls/public IPs; log critical changes.

### 11.3. Reliability and Cost

A solid design accounts for subnet **IP exhaustion**, NAT port counts, failover capability, health checks, Cloud SQL connections, and request/traffic volume. Static IPs keep addresses stable but **do not create HA on their own**.

Costs can come from **external IPv4**, NAT gateways/traffic, load balancers, cross-region/egress, Cloud VPN/Interconnect, and logs. Teams should set **Cloud Billing budgets**, attach appropriate labels, and analyze costs by service/SKU. Budget alerts notify on spend—they do not automatically shut down all services.

## 12. Read-Only Practice on Console and Cloud Shell

**Purpose:** learners classify IPs in a sandbox project without creating new resources. Use only an authorized project, record the real `PROJECT_ID`, and never run mutating commands without approval.

### Step 1. Observe in Console

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select the sandbox project.
2. Go to **VPC network → VPC networks**. Record VPC name, auto/custom mode, and subnet list.
3. Select a subnet to view **region**, primary/secondary IPv4 ranges, stack type, IPv6 access type, and Private Google Access where present.
4. Check **Compute Engine → VM instances**: internal IPv4, external IPv4, IPv6, network interfaces, and zone.
5. Check **VPC network → Routes**, **Firewall**, and **IP addresses** to distinguish paths, policies, and static addresses.
6. If Cloud NAT exists, confirm which subnets/regions the gateway serves. Pages may be organized differently depending on the Console version.

### Step 2. Verify CLI and Identity

~~~bash
# Read-only commands.
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="yaml(projectId,name,projectNumber)"
~~~

`PROJECT_ID` is a placeholder, not a literal string to run as-is. If the CLI default project differs from the project selected in Console, pass `--project=PROJECT_ID` to queries.

### Step 3. List Networks, Subnets, and IPs

~~~bash
gcloud compute networks list --project=PROJECT_ID
gcloud compute networks subnets list --project=PROJECT_ID
gcloud compute networks subnets list --project=PROJECT_ID --format=json

gcloud compute instances list --project=PROJECT_ID --format=json
gcloud compute addresses list --project=PROJECT_ID
~~~

When reading VM JSON, look under `networkInterfaces`:

- `networkIP`: primary internal IPv4.
- `accessConfigs`/`natIP` when present: external IPv4.
- IPv6/address access type fields: depend on interface type and service version.
- `subnetwork`: path to the subnet, helping verify the region.

**Do not use `compute addresses list` to conclude that ephemeral VMs have no IPs.** The address resource list primarily shows reserved/managed IPs such as address reservations; the VM's network interface metadata is where you verify addresses directly attached to the VM.

### Step 4. Read Routes and Firewalls

~~~bash
gcloud compute routes list --project=PROJECT_ID
gcloud compute firewall-rules list --project=PROJECT_ID
~~~

Check route destination (IPv4/IPv6), next hop, network, and priority. Check firewall direction, priority, source/destination ranges, targets, ports, and enabled status. **An existing route does not prove traffic is permitted through the firewall.**

If permitted to access a sandbox Linux VM, **read-only commands inside the VM**:

~~~bash
ip -brief address
ip route
ip -6 route
getent ahosts example.com
~~~

An external IPv4 attached to a VM may not appear in `ip -brief address` due to one-to-one NAT mapping; cross-check with Console/API. **Google Cloud's primary IPv4 virtual gateway does not necessarily respond to ping**, so a failed ping to the gateway is insufficient to conclude network loss.

### Step 5. Recording Template

| Item | Values to record | Remarks |
|---|---|---|
| VPC | Name, mode | Global, how many subnets? |
| Subnet | Region, primary/secondary CIDR | Any overlap or IP shortage? |
| IPv6 | Stack type, internal/external access | Has support been verified? |
| VM | Internal/external IPv4, IPv6 | Static or ephemeral? |
| Route | Destination, next hop | Path to internal/internet? |
| Firewall | Direction, source, target, port | Follows least-privilege principle? |
| Private Google Access | On/Off | Do VMs without external IPs call required Google APIs? |
| NAT | Region, served subnets | Which VMs' outbound IPv4 depends on NAT? |

## 13. Setting Up a Sample Subnet in a Practice Environment (Optional)

This is an **illustration of resource creation**, distinct from the read-only steps in section 12. Perform only in an authorized sandbox; check CIDR ranges and permissions before running. Even though a VPC/subnet alone may not incur separate charges, attached resources and traffic can still incur costs.

~~~bash
# Create a custom VPC.
gcloud compute networks create training-vpc --subnet-mode=custom --project=PROJECT_ID

# Create a primary IPv4 subnet in the Singapore region.
gcloud compute networks subnets create training-app-sg --network=training-vpc --region=asia-southeast1 --range=10.40.0.0/24 --project=PROJECT_ID

# Read back the status.
gcloud compute networks subnets describe training-app-sg --region=asia-southeast1 --project=PROJECT_ID
~~~

This example **does not yet create VMs, external IPs, permissive firewalls, or Cloud NAT**. If you need to deploy IPv6, go to Console, select **dual-stack/IPv6-only** on a custom VPC, choose **IPv6 access type INTERNAL/EXTERNAL**, and follow the supported IPv6 range workflow. For internal IPv6, prepare an internal IPv6 range for the VPC. Never invent an address from the documentation prefix `2001:db8::/32` to assign to real VMs.

If resources were created purely for practice, clean them up only when certain the network is not used by any other workload, you have granted permissions, and you follow sandbox procedures:

~~~bash
# Run only on training subnet/VPC truly belonging to this lab.
gcloud compute networks subnets delete training-app-sg --region=asia-southeast1 --project=PROJECT_ID
gcloud compute networks delete training-vpc --project=PROJECT_ID
~~~

Deletion commands can fail if the network is still used by resources. Never pass `--quiet` to skip verification in a lab requiring explicit confirmation.

## 14. Common Errors and Troubleshooting

| Symptom | Likely cause | How to check |
|---|---|---|
| VM has `10.x.x.x` but cannot reach IPv4 internet | No external IPv4, Public NAT not serving subnet, blocked by route/egress | Interface, NAT subnet/region, default route, firewall |
| VM has public IPv4 but SSH/HTTP times out | Blocked by ingress rule, wrong OS listener, VM not running | Source/target/port, OS firewall, app status |
| VM without external IP cannot call Cloud Storage API | PGA/DNS/route/firewall/IAM not properly configured | Subnet config, API endpoint, `PERMISSION_DENIED` errors |
| Two VMs in same VPC cannot communicate | Firewall, specific route, or app bound to localhost | Inspect packets, IPs, ingress/egress, listener |
| Cannot create VM due to lack of addresses | Subnet primary range out of usable IPs | CIDR and used/reserved IPs |
| Public IPv4 not visible in `ip addr` | Google uses one-to-one NAT for external IPv4 | Check network interface in Compute API |
| DNS AAAA exists but IPv6 fails | Missing IPv6 frontend/route/firewall, TLS, or app support | Test IPv4 and IPv6 separately, check logs |
| IPv6-only cannot reach IPv4 target | Missing DNS64/NAT64 per supported capabilities | Check resolver, NAT64, routes, and service |
| Cannot add IPv6 subnet | Auto mode VPC or missing suitable IPv6 configuration | Check VPC mode, access type, and internal range |
| Peering or VPN fails | CIDR overlap, route/BGP/firewall | Compare ranges on both sides, learned routes |
| Public NAT fails under load | Exhausted NAT ports or IPs, too many connections | NAT metrics, drops, source ports |
| Costs rise after opening public frontend | External IPv4, LB, NAT, egress, or reserved IP | Cloud Billing reports by service/SKU |

A useful diagnostic sequence: verify **project → VPC/subnet → source/destination addresses → routes → firewalls → DNS/listener → IAM/application → logging/metrics**. Avoid "quick fixes" that allow all traffic from `0.0.0.0/0` or `::/0`.

## 15. Design Exercise and Self-Assessment Questions

### 15.1. Problem Statement

A company needs to deploy:

- A public Web API for IPv4 and IPv6 users over HTTPS.
- A background processing VM calling an IPv4 update website and Cloud Storage API, receiving no inbound internet traffic.
- An orders database reachable only by authorized API/VMs.
- An office network already using `192.168.10.0/24`, to be connected later via Cloud VPN.
- An operations team wanting minimal public IPs, cost monitoring, and enough IPs for scaling.

**Questions:**

1. Choose auto or custom VPC? Propose two non-overlapping IPv4 subnets and explain why.
2. How many total IPv4 addresses and how many usable addresses does primary subnet `10.40.0.0/24` have?
3. Does the batch VM need an external IPv4? Choose how it reaches the IPv4 internet and calls Google APIs.
4. How do you provide an HTTPS entry point for both IPv4/IPv6? What DNS and firewall configurations are needed?
5. Compare a dual-stack **internal IPv6** subnet with a dual-stack **external IPv6** subnet.
6. Why does a private database endpoint still require IAM/database auth and proper firewalls/connectivity paths?
7. Pick two metrics to detect IP/NAT issues and two network cost sources to monitor.
8. If a VM cannot ping the virtual gateway, is that enough to conclude the subnet has lost connectivity?
9. If an application publishes an AAAA record but the backend does not support IPv6, what might users experience?
10. When connecting via VPN to a network with an overlapping CIDR, why is a default route insufficient to solve it?

### 15.2. Reference Answer Guide

A well-founded solution typically starts with a **custom VPC** using sufficiently large CIDRs that do not overlap with the office or planned connected networks. For instance, `10.40.0.0/24` and `10.40.1.0/24` can be considered if the entire related IP plan is non-overlapping.

A `/24` primary subnet has **256 addresses**; Google Cloud reserves **4** addresses, leaving **252** usable addresses. The batch VM can use only internal IPv4, going through **Public NAT** to reach the IPv4 internet and **Private Google Access** to call Google APIs under appropriate configuration. The HTTP frontend should use an endpoint or load balancer supporting both address families, with DNS A/AAAA, TLS, health checks, and matching firewalls.

Internal IPv6 is not directly routed on the internet; external IPv6 can be internet-routable but does not automatically open ports. A private database still requires **proper network paths, firewalls, and authentication/authorization**—a private IP alone is not sufficient security. Metrics should include **available IPs, NAT dropped packets/ports, and connection errors**, while monitoring **external IPv4, NAT, load balancing, and network egress**. The virtual gateway not responding to ICMP can occur normally and is not proof of network failure.

## 16. Pre-Production Deployment Checklist

- [ ] Choose appropriate auto/custom VPC; compute CIDRs and avoid overlap with hybrid/peered networks.
- [ ] Plan primary IPv4, secondary ranges, alias IPs, GKE nodes/pods, and autoscaling headroom.
- [ ] Distinguish internal/external, static/ephemeral, and regional/global for every endpoint.
- [ ] Assign external IPs only when necessary; prefer appropriate private access for backends/databases.
- [ ] If using IPv6: define dual-stack/IPv6-only, access type, OS/service support, DNS, and firewalls.
- [ ] Verify IPv4/IPv6 routes, ingress/egress firewalls, OS listeners, TLS, and application IAM.
- [ ] VMs without external IPv4 have Public NAT, Private Google Access, or private endpoints per actual needs.
- [ ] Have connectivity test evidence, logs, NAT port usage, IP availability metrics, and alerts.
- [ ] Accounted for external IPv4, NAT, load balancers, network egress, and related network charges.
- [ ] Defined network configuration owner, approval process, and rollback plan when changing routes/firewalls/IPs.

## 17. Official Reference Documentation

IPv6 capabilities, IP allocation methods, product limits, and pricing are subject to change. When deploying to real projects, verify current documentation:

- [VPC networks](https://docs.cloud.google.com/vpc/docs/vpc) — global scope of VPCs and regional subnets.
- [Subnets](https://docs.cloud.google.com/vpc/docs/subnets) — primary/secondary IPv4, IPv6 `/64`, and the four reserved IPv4 addresses.
- [IP addresses in VPC](https://docs.cloud.google.com/vpc/docs/ip-addresses) — internal/external, private/public.
- [Compute Engine IP addresses](https://docs.cloud.google.com/compute/docs/ip-addresses) — interfaces and IPv6 `/96`.
- [Configure IPv6 addresses](https://docs.cloud.google.com/compute/docs/ip-addresses/configure-ipv6-address) — dual-stack, IPv6-only, and network interfaces.
- [VPC routes](https://docs.cloud.google.com/vpc/docs/routes) — paths and default routes.
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls) — ingress/egress and implied rules.
- [Cloud NAT overview](https://docs.cloud.google.com/nat/docs/overview) — outbound NAT, NAT44/NAT64.
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access) — Google APIs from VMs without external IPs.
- [Private access options](https://docs.cloud.google.com/vpc/docs/private-access-options) — PSC, private services access, and private options.
- [IPv6 support in Google Cloud](https://docs.cloud.google.com/vpc/docs/ipv6-support) — per-service support matrix.

**Key takeaway:** **IPv4/IPv6** describes the address family; **internal/external** describes connectivity scope; **static/ephemeral** describes lifecycle; **regional/global** describes resource scope. Secure Google Cloud design must combine **IP + subnet + route + firewall + identity/access permissions + service configuration**. Mastering these layers helps teams choose Compute Engine, GKE, Cloud Run, and data services aligned with security, reliability, scalability, and cost requirements.
