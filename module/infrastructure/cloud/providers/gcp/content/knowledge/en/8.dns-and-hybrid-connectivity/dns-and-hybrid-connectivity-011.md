# Lab: Connecting On-Premises Networks to a VPC on Google Cloud

> **Chapter:** DNS and Hybrid Connectivity  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners learn how to choose services, secure resources, automate releases, and monitor reliability and cost.

An enterprise runs an order management system in its private data center (on-premises). The development team deploys a new API service on Compute Engine or GKE in Google Cloud, yet the application still needs to access internal data over private IP addresses. The goal is not merely "being able to ping": the two networks need **appropriate transport, bidirectional routing, scoped firewalls, accurate DNS resolution, redundancy, monitoring, and a cleanup plan**.

This hands-on lab walks through designing, configuring, and verifying an **on-premises ↔ Google Cloud VPC** connection using **HA VPN, Cloud Router, and BGP**, while explaining how to extend to Cloud DNS and Cloud Interconnect. The commands below describe a fictional lab environment. Execute resource creation/modification steps only when authorized on a **test project** and in coordination with the on-premises system administrator.

## Learning Objectives

After this lesson, learners will be able to:

1. Draw an end-to-end diagram of a hybrid connection and build a network parameter sheet before deployment.
2. Explain the roles of VPCs, subnets, HA VPN gateways, external peer VPN gateways, VPN tunnels, Cloud Router, and BGP.
3. Create a VPC, two HA VPN tunnels, and two BGP sessions following a reference setup, aligning matching parameters with the on-premises appliance.
4. Inspect tunnel status, BGP, learned/advertised routes, firewalls, and bidirectional connectivity tests.
5. Add bidirectional internal name resolution using Cloud DNS forwarding and inbound DNS forwarding.
6. Diagnose overlapping IPs, IKE/IPsec, routing, DNS, MTU, and security rule errors.
7. Know when to consider Dedicated/Partner Interconnect, optimize resilience, and manage costs.

## 1. Lab Scenario and Expected Outcomes

Assume an enterprise has an on-premises site with application network **172.20.50.0/24**. Google Cloud has a test VPC with subnet **10.20.10.0/24** in one region. A private VM in the VPC has IP **10.20.10.10**; an on-premises host has IP **172.20.50.20**. An on-premises DNS server uses IP **172.20.50.53**.

~~~mermaid
flowchart LR
    subgraph DC["On-premises data center"]
        PC["Client 172.20.50.20"]
        DNS["DNS 172.20.50.53"]
        PEER["VPN/BGP peer\nASN 65010\n2 public interfaces"]
        PC --- PEER
        DNS --- PEER
    end

    subgraph GCP["Google Cloud project: hybrid-lab"]
        subgraph VPC["VPC: hybrid-lab-vpc"]
            HA["HA VPN gateway\nInterface 0 + 1"]
            CR["Cloud Router\nASN 64514"]
            VM["Private VM\n10.20.10.10"]
            GCDNS["Cloud DNS private/forwarding zones"]
            HA --- CR
            CR -. "dynamic routes" .-> VM
            GCDNS -. "resolution" .-> VM
        end
    end

    PEER ==>|"IPsec tunnel 0"| HA
    PEER ==>|"IPsec tunnel 1"| HA
~~~

The diagram is **logical**—do not think Cloud Router forwards packets directly through VMs: Cloud Router is the BGP route control and exchange service; the **data plane** uses VPC routes and the corresponding tunnels.

**Expected outcomes:**

- Both HA VPN tunnels are active and both BGP sessions are established as configured.
- Google Cloud learns the route to **172.20.50.0/24**; the on-premises device learns **10.20.10.0/24**.
- A client at the on-premises site can call a test service at IP **10.20.10.10** strictly over permitted ports.
- If practicing advanced DNS: the GCP host resolves **app.corp.example.internal** via on-premises DNS; the on-premises host resolves **vm1.gcp.example.internal** via inbound DNS forwarding.
- When intentionally dropping one tunnel, traffic can shift to the surviving path as designed; this is tested under monitoring and does not automatically guarantee zero packet loss during convergence.

### 1.1. Parameter Planning Sheet

| Component | Lab Value | Notes |
|---|---|---|
| Google Cloud project | hybrid-lab-project | Replace with an authorized project |
| Region / zone | asia-southeast1 / asia-southeast1-a | Select a region with supported services |
| VPC / subnet | hybrid-lab-vpc / cloud-lab-subnet | Global VPC, regional subnet |
| VPC subnet CIDR | 10.20.10.0/24 | Example range dedicated to the lab |
| Test VM | hybrid-test-vm / 10.20.10.10 | No external IP needed |
| On-premises subnet | 172.20.50.0/24 | Must not overlap any related subnet |
| On-premises client | 172.20.50.20 | Real host must have a route via the VPN gateway |
| On-premises DNS | 172.20.50.53 | Capable of answering permitted queries |
| Cloud Router ASN | 64514 | Private ASN, distinct from on-premises ASN |
| On-premises peer ASN | 65010 | Private ASN, agreed upon by both ends |
| On-premises VPN public IP #0 | 198.51.100.10 | Documentation address, not routed on the Internet |
| On-premises VPN public IP #1 | 198.51.100.11 | Documentation address, replace with real IP |
| BGP link-local #0/#1 | Auto-allocated 169.254.x.x/30 | Record after creating Cloud Router interfaces |
| Cloud VPN public IP #0/#1 | Assigned by Google Cloud | Retrieve after creating HA VPN gateway |
| Cloud DNS | gcp.example.internal. | Private zone |
| On-premises DNS | corp.example.internal. | Forwarding zone |

The addresses **198.51.100.10/11** are **documentation** addresses and do not function as real Internet endpoints. When practicing with real equipment, replace them with **reachable public IPv4 addresses** of the on-premises appliance/Internet circuit. All other CIDRs are illustrative values; use them only if they **do not conflict with existing networks**.

## 2. Selecting Connectivity Technology Before Configuring

| Solution | Best For | Characteristics and Trade-offs |
|---|---|---|
| **HA VPN** | Labs, hybrid connectivity over the Internet, fast rollout, moderate traffic | IPsec encryption over the Internet, dual interfaces/tunnels and BGP for redundancy |
| **Dedicated Interconnect** | Enterprises needing steady throughput and direct physical links at supported facilities | Requires circuit design, infrastructure, and redundancy; different lead times/costs than VPN |
| **Partner Interconnect** | Private connectivity via a partner network provider | Depends on provider, VLAN attachments, Cloud Router, SLA, and data protection approach |
| **HA VPN over Cloud Interconnect** | Need Interconnect transport plus mandatory IPsec protection | More complex combination of components, configuration, and cost |
| **Classic Cloud VPN** | Legacy use cases requiring static routing | Less convenient for modern HA designs; HA VPN/BGP is generally preferred |
| **Authenticated public HTTPS API** | Only needing to call a few application endpoints over the Internet | Does not create private network connectivity between entire CIDRs; may suffice for small use cases |

This lab uses **HA VPN with BGP** so learners can clearly observe **tunnel encryption, route learning, and failover handling**. HA VPN currently supports IPv4 and IPv6 stack types depending on configuration; this lab intentionally uses **IPv4 only** to reduce variables.

**Note on SLAs:** per Google Cloud's topologies and conditions, HA VPN with two tunnels across two interfaces can achieve a high SLA (such as 99.99% with a qualifying topology). **A single tunnel does not satisfy those HA requirements.** Peer setups, Internet paths, and the rest of the system still need matching redundancy; you cannot infer an entire application's SLA solely from a Cloud VPN figure.

## 3. Pre-Flight Prerequisites Check

Walk through this checklist with the on-premises network team and Google Cloud administrator.

### 3.1. Addressing and Routing

- No CIDR overlaps among VPCs, on-premises, and linked networks, including **secondary ranges** for GKE Pods/Services if any.
- Clearly identify **target destinations**: internal VMs, private-IP databases, GKE workloads, or managed service endpoints.
- Confirm bidirectional routes: GCP needs a route to **172.20.50.0/24**; on-premises needs a route to **10.20.10.0/24**.
- BGP ASNs on both sides must be compatible, avoid unintended ASN collisions, and follow enterprise routing policies.
- Determine the VPC's **dynamic routing mode** (regional/global), as route applicability and advertisement scope depend on it.
- With multiple sites, establish path preferences using supported parameters such as route priority/MED, and never let two sites advertise overlapping CIDRs unintentionally.

### 3.2. On-Premises VPN Gateway

The peer appliance/software must:

- Support IPsec/IKE compatible with Cloud VPN (this lab uses **IKEv2**).
- Support **BGP dynamic routing** for HA VPN.
- Have public endpoint addresses or a NAT configuration meeting Cloud VPN restrictions.
- Be permitted to send/receive IKE and ESP/NAT-T traffic per device configuration; common checks include **UDP 500, UDP 4500, ESP**, and upstream firewall limits.
- Support two tunnels and redundancy matching the desired topology.
- Have operators able to manage peer config, routing tables, firewalls, and DNS.

Never assume a firewall allowing only TCP 443 is enough for IPsec. Specific ports/protocols depend on topology and whether NAT-T is used. With NAT on the peer side, check **one-to-one NAT** rules and restrictions around multiple gateways sharing one public IP.

### 3.3. Permissions and Costs

These operations require appropriate network admin permissions, typically roles within **roles/compute.networkAdmin** and permissions for VPCs, gateways, routers, tunnels, and firewalls; creating VMs/DNS requires separate permissions. You need a project linked to a billing account with required APIs enabled. Lab commands creating **VPN gateways/tunnels, VMs, disks, and DNS** can incur charges; even without traffic, VPN or VM resources can still generate charges.

If studying theory only, you can **read the sample outputs and simulate verification steps** without creating real resources. The commands in this lesson are examples for an administrator to deploy in an authorized lab project.

## 4. Preparing the Google Cloud Environment

The command blocks below use **Bash** in Cloud Shell or a workstation with `gcloud` CLI. Substitute every variable for your assigned environment. Create/modify commands are clearly labeled; never run them in production without reviewing configuration and impact.

### 4.1. Read-Only Commands to Verify the Environment

~~~bash
gcloud auth list
gcloud config list
gcloud projects describe YOUR_PROJECT_ID
gcloud services list --enabled --project=YOUR_PROJECT_ID

# Check existing VPC networks and routing modes.
gcloud compute networks list --project=YOUR_PROJECT_ID
gcloud compute networks subnets list --project=YOUR_PROJECT_ID
~~~

If an API is not yet enabled, handle it within your granted permissions. Never self-enable services or broaden production IAM just to run a lab.

### 4.2. Lab Environment Variables

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
ZONE="asia-southeast1-a"
VPC="hybrid-lab-vpc"
SUBNET="cloud-lab-subnet"
GW="ha-vpn-hybrid"
PEER_GW="onprem-peer"
ROUTER="cloud-router-hybrid"
TUNNEL0="hybrid-tunnel-0"
TUNNEL1="hybrid-tunnel-1"
ONPREM_ASN="65010"

# Peer public IPs are placeholders only; supply real IPs before creating.
PEER_PUBLIC_IP_0="198.51.100.10"
PEER_PUBLIC_IP_1="198.51.100.11"
~~~

**Never place pre-shared keys (PSKs)** in example config files, Git, logs, or printed environment variables. Both tunnels can use **two distinct PSKs** to limit blast radius if one secret leaks. When using the CLI, beware that values in argv, shell history, and logs can be exposed; supply secrets via an organization-approved secret management method.

## 5. Step 1 — Create the VPC and Private Subnet

~~~bash
# CREATE RESOURCE — create a VPC with operator-defined subnets.
gcloud compute networks create "$VPC" \
  --project="$PROJECT_ID" \
  --subnet-mode=custom \
  --bgp-routing-mode=REGIONAL

# CREATE RESOURCE — create a subnet in the lab region.
gcloud compute networks subnets create "$SUBNET" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --range="10.20.10.0/24"

# READ-ONLY — verify IP range and routing mode.
gcloud compute networks describe "$VPC" --project="$PROJECT_ID"
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**Explanation:**

- A VPC is a **global** resource, whereas a subnet is **regional**.
- **REGIONAL** dynamic routing mode is the right lab choice for one region. If workloads in multiple regions need hybrid routes across the VPC, evaluate **GLOBAL** mode and route advertisement/learning behavior before switching.
- A new VPC does not come with firewall rules permitting on-premises hosts to reach VMs by default.
- The **10.20.10.0/24** range must be approved beforehand; you cannot fix IP overlap by changing labels.

### 5.1. Checking for Overlapping CIDRs

Suppose on-premises already uses **10.20.0.0/16**. Then **10.20.10.0/24** is a subset of the on-premises range; both sides can pick wrong local routes and fail to connect as designed. Change the **addressing and subnet** during design, or evaluate supported NAT/routing workarounds after careful analysis. Never try to fix overlap by adding firewall rules.

## 6. Step 2 — Create HA VPN Gateway, Peer Gateway, and Cloud Router

### 6.1. Create the HA VPN Gateway

~~~bash
# CREATE RESOURCE — gateway in the lab VPC and region.
gcloud compute vpn-gateways create "$GW" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --stack-type=IPV4_ONLY

# READ-ONLY — record the 2 public IPs assigned by Google Cloud.
gcloud compute vpn-gateways describe "$GW" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(name,vpnInterfaces)"
~~~

The HA VPN gateway has **two interfaces**, each assigned a dedicated public IP. Record both addresses in the on-premises peer configuration sheet. Never invent Google Cloud IPs or use VM subnet IPs for tunnel endpoints.

### 6.2. Declare the External Peer VPN Gateway

For the lab topology, assume on-premises provides **two public IPs** (either one multi-interface appliance or two appliances per design). Google Cloud stores this under an **external VPN gateway resource**.

~~~bash
# CREATE RESOURCE — real peer IPs must replace placeholders.
gcloud compute external-vpn-gateways create "$PEER_GW" \
  --project="$PROJECT_ID" \
  --interfaces="0=$PEER_PUBLIC_IP_0,1=$PEER_PUBLIC_IP_1"

# READ-ONLY.
gcloud compute external-vpn-gateways describe "$PEER_GW" \
  --project="$PROJECT_ID"
~~~

If the site only has one public IP, use the **single-interface peer topology** and connect both tunnels to that interface per Google Cloud documentation. Never copy the dual-interface command above and put the same IP in both slots. End-to-end HA still depends on peer hardware/circuit redundancy.

### 6.3. Create Cloud Router

~~~bash
# CREATE RESOURCE — Cloud Router in the same VPC and region as HA VPN.
gcloud compute routers create "$ROUTER" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --asn=64514

# READ-ONLY.
gcloud compute routers describe "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**Cloud Router** handles the **BGP control plane** exchange. The router is not a VM you SSH into to forward packets; routes learned via BGP are programmed into VPC routing according to Google Cloud rules. This example uses ASN **64514** on GCP and **65010** on-premises; other private ASNs may be chosen as long as system constraints are respected.

## 7. Step 3 — Create Two IPsec VPN Tunnels

Before creating tunnels, administrators on both sides must align on:

- **IKE version** and cipher suites supported by the appliance; the lab uses IKEv2.
- Public IPs for Cloud VPN interfaces #0/#1 and peer interfaces #0/#1.
- Dedicated pre-shared keys for each tunnel.
- DPD, IPsec rekey, NAT-T, and peer policy parameters.
- BGP dynamic routing, avoiding static routing traffic selectors by mistake.
- Firewalls/ACLs on the appliance and upstream Internet links.

**The Bash example assumes two variables** `VPN_SHARED_SECRET_0` and `VPN_SHARED_SECRET_1` have been populated via an organization-approved secure method; never store secret values in documents. Avoid enabling **`set -x`** or logging command lines containing secrets.

~~~bash
# CREATE RESOURCE — commands pass PSKs in process parameters.
# Protect shell history/logs/argv when running in real environments.

gcloud compute vpn-tunnels create "$TUNNEL0" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --vpn-gateway="$GW" \
  --interface=0 \
  --peer-external-gateway="$PEER_GW" \
  --peer-external-gateway-interface=0 \
  --router="$ROUTER" \
  --ike-version=2 \
  --shared-secret="$VPN_SHARED_SECRET_0"

gcloud compute vpn-tunnels create "$TUNNEL1" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --vpn-gateway="$GW" \
  --interface=1 \
  --peer-external-gateway="$PEER_GW" \
  --peer-external-gateway-interface=1 \
  --router="$ROUTER" \
  --ike-version=2 \
  --shared-secret="$VPN_SHARED_SECRET_1"
~~~

**The two tunnels will not come UP immediately after creation** if the on-premises appliance has not yet been configured symmetrically. This is normal while the two teams coordinate.

~~~bash
# READ-ONLY — inspect current tunnel status.
gcloud compute vpn-tunnels describe "$TUNNEL0" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,status,detailedStatus)"

gcloud compute vpn-tunnels describe "$TUNNEL1" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,status,detailedStatus)"
~~~

A topology with only one active tunnel can still pass data, yet **does not prove the fault tolerance of an HA setup**.

## 8. Step 4 — Configure Cloud Router BGP for Both Tunnels

Each tunnel needs a **Cloud Router interface** and a **BGP peer**. This lesson uses auto-allocated link-local IPv4 BGP addresses from **169.254.0.0/16** to minimize manual errors; each session uses a distinct `/30` address pair. After creation, the on-premises admin must read the exact assigned addresses and configure them on the corresponding BGP peers.

~~~bash
# CREATE/UPDATE — interface and BGP peer for tunnel 0.
gcloud compute routers add-interface "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --interface-name="hybrid-if-0" \
  --vpn-tunnel="$TUNNEL0"

gcloud compute routers add-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-0" \
  --peer-asn="$ONPREM_ASN" \
  --interface="hybrid-if-0"

# CREATE/UPDATE — interface and BGP peer for tunnel 1.
gcloud compute routers add-interface "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --interface-name="hybrid-if-1" \
  --vpn-tunnel="$TUNNEL1"

gcloud compute routers add-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-1" \
  --peer-asn="$ONPREM_ASN" \
  --interface="hybrid-if-1"

# READ-ONLY — view configuration and allocated BGP addresses.
gcloud compute routers describe "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(interfaces,bgpPeers)"
~~~

On the on-premises side, each BGP peer must:

1. Use **local ASN = 65010** and **remote ASN = 64514** in this lab.
2. Set the local/remote BGP IPs to the exact **169.254.x.x/30** pair just received from Cloud Router.
3. Advertise **172.20.50.0/24** to Google Cloud; do not advertise a default route or out-of-scope ranges unless intentional.
4. Accept and install the **10.20.10.0/24** route from Cloud Router per internal policy.
5. Configure path preference/route checks when one tunnel fails.

**Vendor-specific** configuration syntax varies across Cisco, Fortinet, Juniper, pfSense, or Linux/FRRouting routers. Never copy one vendor's config onto another appliance; follow the vendor documentation and actual values from Cloud Router.

### 8.1. Checking BGP Status

~~~bash
# READ-ONLY — returns BGP status, advertised routes, and learned routes.
gcloud compute routers get-status "$ROUTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml

# READ-ONLY — check subnet and VPC routes.
gcloud compute routes list \
  --project="$PROJECT_ID" \
  --filter="network:$VPC"
~~~

In the Cloud Router output, look for **BGP peer status** and routes to **172.20.50.0/24** learned on both sessions. Field names/formats can vary by API version; verify actual status via **`get-status`**, not from a "Creating peer … done" message.

**BGP session UP does not guarantee applications can connect.** Firewalls, on-premises routes, endpoints, DNS, or OS settings can still block traffic.

### 8.2. Dynamic Routing Mode and Scope

A VPC can use **REGIONAL** or **GLOBAL** dynamic routing mode:

- With **REGIONAL**, dynamic routes learned via Cloud Router apply per regional rules; subnets/advertisements outside the region may need extra configuration or another mode.
- With **GLOBAL**, routes can be distributed more broadly across the VPC, subject to advertisement policies, priorities, and topology.
- Never change a production VPC's mode just to make a lab work, as that change can affect many workloads and routing paths.

In a lab with only an **asia-southeast1** subnet, REGIONAL mode makes results straightforward to observe.

## 9. Step 5 — Create a Private VM and Open Minimal Firewalls

Only create the VM if the lab project is permitted to incur charges. A VM without an external IP lets you accurately test **on-premises → VPN → VPC → VM** without accidentally routing over the Internet.

~~~bash
# CREATE RESOURCE — test VM without a public IP.
gcloud compute instances create "hybrid-test-vm" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="e2-micro" \
  --subnet="$SUBNET" \
  --private-network-ip="10.20.10.10" \
  --no-address \
  --tags="hybrid-test" \
  --labels="environment=development,application=hybrid-lab"

# READ-ONLY.
gcloud compute instances describe "hybrid-test-vm" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,networkInterfaces,tags,labels)"
~~~

Note that a VM without an external IP may need **Cloud NAT**, Private Google Access, or another access path to update the OS or install packages. Cloud NAT is an **appropriate outbound connectivity mechanism**—not a tool for building IPsec tunnels or letting on-premises reach the VM.

Example allowing **only the on-premises source** to access **ICMP and SSH** on VMs with network tag **hybrid-test**:

~~~bash
# CREATE RESOURCE — VPC firewall applied to tagged VMs.
gcloud compute firewall-rules create "allow-onprem-hybrid-test" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --source-ranges="172.20.50.0/24" \
  --target-tags="hybrid-test" \
  --rules="icmp,tcp:22"

# READ-ONLY.
gcloud compute firewall-rules describe "allow-onprem-hybrid-test" \
  --project="$PROJECT_ID"
~~~

**Additional checks needed**: VPC hierarchical firewall policies, firewall policy rules, guest OS firewalls, IAM/OS Login, and SSH authentication. The rule above does not open access to the whole Internet, yet should still be limited to test environments since SSH needs proper authentication. In production, restrict to exact needed destinations/ports, workload identities, and additional controls.

### 9.1. Firewalls on Both Sides

On-premises must permit traffic from **172.20.50.20** to **10.20.10.10** on the test ports, as well as return/response traffic. There may be **two firewall layers**:

- **VPN appliance firewall:** permits IKE/IPsec and tunnel traffic.
- **Internal on-premises firewall:** permits the application subnet/host to reach the target service.

Opening a GCP rule does not open on-premises rules; hybrid traffic must pass **every enforcement point along the path**.

## 10. Step 6 — Test Connectivity and Isolate Each Layer

Once **tunnels are UP, BGP is Established, and bidirectional routes exist**, run tests from an authorized host on-premises.

~~~bash
# Run on host 172.20.50.20, not in Cloud Shell.
# ICMP may be blocked by hosts or firewalls.
ping -c 4 10.20.10.10

# If the VM has an active SSH daemon and the firewall allows TCP 22:
nc -vz -w 5 10.20.10.10 22

# Check the route on a Linux host at the on-premises site:
ip route get 10.20.10.10
~~~

No ping reply **does not prove the VPN is down**. Test the real service TCP port, inspect logs, packet counters, and routing on each side. On Windows, substitute **Test-NetConnection**, **tracert**, or appropriate tools.

### 10.1. Bottom-Up Verification Matrix

| Layer | Evidence to Check | If Failing |
|---|---|---|
| Public reachability | Peer public IPs and Cloud VPN IPs right; UDP/IKE/ESP pass | Check ISP, NAT, outside firewalls |
| IKE/IPsec | Both tunnels established with packet counters | Check PSK, IKEv2, ciphers, peer interfaces |
| BGP | Sessions Established; ASNs and link-local IPs match | Check BGP on peer, tunnels, `/30` addresses |
| GCP routes | Cloud Router learns **172.20.50.0/24** | Check peer prefix advertisements, filters, VPC mode |
| On-prem routes | Peer/site learns **10.20.10.0/24** | Check advertised prefixes, route install, local gateway |
| Firewall | Permits exact source/destination/port across layers | Check GCP firewalls, policies, and on-prem firewalls |
| Host/service | VM has right IP, service listening | Check OS firewall, daemon, service status |
| DNS | Name resolves to appropriate IP | Check Cloud DNS policies/forwarding and on-prem DNS |
| Application | TLS, IAM, auth, and business responses | Check app logs and permissions; don't tweak VPN blindly |

### 10.2. Bidirectional Packet Path

~~~mermaid
sequenceDiagram
    participant H as On-prem client 172.20.50.20
    participant P as VPN/BGP Peer
    participant G as HA VPN / VPC
    participant V as VM 10.20.10.10
    H->>P: TCP SYN to 10.20.10.10
    P->>G: IPsec tunnel selected by route
    G->>V: Firewall allows?
    V-->>G: TCP SYN-ACK
    G-->>P: Return route to 172.20.50.0/24
    P-->>H: Return to client
~~~

A missing **return route** causes one-way connection failure even when the initial packet reaches the VM. In multi-gateway environments, inspect return path selection, NAT, and anti-spoofing filters.

## 11. Step 7 — Bidirectional Hybrid DNS Resolution

IP connectivity does not mean internal hostnames resolve automatically. If applications use **api.corp.example.internal** or **vm1.gcp.example.internal**, design DNS.

### 11.1. Cloud → On-Premises: Forwarding Zone

Suppose GCP hosts need to query on-premises DNS **172.20.50.53** for names in **corp.example.internal.**. Create a private forwarding zone attached to the VPC:

~~~bash
# CREATE RESOURCE — forward internal zone queries to on-premises DNS.
gcloud dns managed-zones create "corp-onprem-forward" \
  --project="$PROJECT_ID" \
  --description="Forward corp.example.internal to on-prem DNS" \
  --dns-name="corp.example.internal." \
  --visibility=private \
  --networks="$VPC" \
  --forwarding-targets="172.20.50.53"

# READ-ONLY.
gcloud dns managed-zones describe "corp-onprem-forward" \
  --project="$PROJECT_ID"
~~~

**Often-missed detail:** Cloud DNS queries the **on-premises DNS server** over the hybrid link from a source range that can belong to **35.199.192.0/19** (under the documented forwarding mechanism). The on-premises site must:

- Permit **UDP/TCP 53** from the appropriate source range to the DNS server.
- Have a **return route to 35.199.192.0/19** via the same VPC and valid Cloud VPN/Interconnect path.
- Allow the target DNS server to reply directly, matching the expected responder IP requirement.
- Avoid replying from a different DNS server IP that Cloud DNS will reject.

If the site's DNS server lacks a return route to **35.199.192.0/19**, VPN and BGP to application subnets may still work while DNS forwarding times out or returns `SERVFAIL`.

### 11.2. Advertising the DNS Return Route via Cloud Router

In this BGP lab, **custom advertisement** is needed so on-premises learns the return path to **35.199.192.0/19**. On a **dedicated lab Cloud Router**, you can configure **both BGP peers**, keeping normal subnet advertisements via **ALL_SUBNETS**:

~~~bash
# UPDATE BGP ADVERTISEMENTS — use only after reviewing
# prefixes and confirming this router serves no other workloads.
gcloud compute routers update-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-0" \
  --advertisement-mode=CUSTOM \
  --set-advertisement-groups=ALL_SUBNETS \
  --set-advertisement-ranges="35.199.192.0/19"

gcloud compute routers update-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-1" \
  --advertisement-mode=CUSTOM \
  --set-advertisement-groups=ALL_SUBNETS \
  --set-advertisement-ranges="35.199.192.0/19"
~~~

**Operational warning:** changing advertisements on a router serving real systems can wipe out prior custom routes when using **`--set`**. The commands above are samples solely for a **new lab-only router**. On live systems, read current configuration first, preserve all valid prefixes, and test failover.

### 11.3. On-Premises → Cloud DNS Private Zone: Inbound Forwarding

Suppose you want on-premises hosts to resolve **vm1.gcp.example.internal** to **10.20.10.10**.

Create a **Cloud DNS private zone** and A record:

~~~bash
# CREATE RESOURCE — private managed zone.
gcloud dns managed-zones create "gcp-private-zone" \
  --project="$PROJECT_ID" \
  --dns-name="gcp.example.internal." \
  --description="Private names in hybrid lab" \
  --visibility=private \
  --networks="$VPC"

# CREATE RECORD — A record pointing only to the lab VM address.
gcloud dns record-sets create "vm1.gcp.example.internal." \
  --project="$PROJECT_ID" \
  --zone="gcp-private-zone" \
  --type=A \
  --ttl=300 \
  --rrdatas="10.20.10.10"

# READ-ONLY.
gcloud dns record-sets list \
  --project="$PROJECT_ID" --zone="gcp-private-zone"
~~~

To let **on-premises DNS** query names in the private zone, enable **inbound DNS forwarding** for the VPC:

~~~bash
# CREATE RESOURCE — DNS policy bound to the VPC.
gcloud dns policies create "hybrid-inbound-dns" \
  --project="$PROJECT_ID" \
  --description="Allow inbound DNS from on-prem over hybrid connectivity" \
  --networks="$VPC" \
  --enable-inbound-forwarding

# READ-ONLY — inspect current policy.
gcloud dns policies describe "hybrid-inbound-dns" \
  --project="$PROJECT_ID"
~~~

Then, in the Cloud DNS console or appropriate tooling, retrieve the **inbound forwarding resolver IP** allocated by Google Cloud in the relevant region. On the on-premises DNS server, configure a **conditional forwarder** for **gcp.example.internal.** pointing to that inbound IP, ensuring VPN routes and firewalls permit **TCP/UDP 53**. Use the service-provided **inbound forwarding IP**—not the VM metadata server **169.254.169.254** or a VM IP.

**Never attach multiple conflicting DNS policies to the same VPC** without assessing the impact on existing name resolution.

### 11.4. Testing DNS

Run from an authorized GCP host:

~~~bash
# From the GCP VM, using the environment's configured resolver.
dig app.corp.example.internal A
~~~

Run from an on-premises host:

~~~bash
# Query via the local DNS server with the conditional forwarder.
dig @172.20.50.53 vm1.gcp.example.internal A

# If you already know the actual inbound forwarding IP:
dig @INBOUND_FORWARDING_IP vm1.gcp.example.internal A
~~~

DNS returning **10.20.10.10** is a prerequisite for using the name; still verify TCP/HTTPS connectivity to that IP. A valid DNS record does not prove firewalls, routes, or the application are working.

## 12. Connecting to Managed Services: Different from VMs

This lab uses a VM so packet paths are easy to see, whereas production apps may call Cloud SQL, GKE, Cloud Run, or Google APIs.

| Service | Network Approach to Evaluate | What Not to Assume |
|---|---|---|
| **Compute Engine VM** | Internal IP in subnet plus VPC/OS firewalls | That a VM without an external IP can reach everything automatically |
| **GKE** | Nodes/subnets, secondary ranges for Pods/Services, network policies, routes, cluster connectivity | That a route to nodes reaches every Pod/Service |
| **Cloud SQL private IP** | Private services access or supported private connection design, DNS/TLS/IAM/DB auth | That Cloud SQL sits directly in the VPC like a normal VM |
| **Cloud Run** | HTTPS URL, ingress, IAM, direct VPC egress/connector if needed, supported private access mechanisms | That Cloud Run has a default VPC internal IP for on-premises to call directly |
| **Cloud Storage / Google APIs** | Private Google Access for on-premises / Private Service Connect and documented DNS/routes | That every API endpoint automatically traverses the tunnel via private IPs |
| **BigQuery** | Appropriate endpoints/APIs/private paths, IAM, and data policies | That BGP to a VPC subnet suffices for all BigQuery requests |

**Routing and authentication are two separate layers.** Reaching an endpoint from on-premises does not grant IAM permissions. For authenticated Cloud Run services, callers may need a Google-signed ID token with the right audience and Invoker role; for Cloud Storage/BigQuery APIs, access tokens and service-scoped IAM are typically required.

### 12.1. Cloud SQL Private IP Case

Suppose on-premises needs to reach Cloud SQL via private IP. Beyond VPN/BGP, you need to:

1. Identify how the Cloud SQL instance receives its private IP and the supported **Private Services Access / Private Service Connect** architecture.
2. Check whether a route exists to the managed service IP range; custom route advertisements/route exchange may be required per product docs.
3. Verify return connectivity, DNS, database TCP port, TLS, and database authentication.
4. Choose Cloud SQL Auth Proxy/connectors or an appropriate connection method; never open a public IP without an explicit requirement.

Never create an "allow all" firewall rule just to troubleshoot a database connection failure.

## 13. Methodical HA and Failover Testing

An HA VPN lab is only complete when you prove what happens if one tunnel goes down. However, taking down a tunnel is an **impactful change** and must only be executed in a test project/peer according to plan.

### 13.1. Pre-Test Prerequisites

- Tunnels 0 and 1 are active and BGP sessions are in the expected state.
- Both directions have routes to the required subnets.
- Baseline latency and service success-rate measurements exist.
- Operators are watching both the peer VPN and Cloud Router.
- A configuration recovery plan and approved test window are in place.

### 13.2. Scenario

1. From on-premises, send steady requests to the test service at **10.20.10.10**.
2. Record initial status of tunnels 0/1 and BGP peers.
3. In the lab environment, **in a controlled manner, disable one path/tunnel on the peer device** or use a vendor-supported test method.
4. Observe the corresponding BGP session drop while routes persist via the surviving tunnel.
5. Measure outage duration, failed requests, and route state; never assume zero-downtime instantaneous failover.
6. Restore the tunnel and verify both sessions stabilize.
7. Record results and items needing tuning (BGP timers/BFD if supported by peer, routing priority, topology).

~~~text
Failover Test Results (Template)
--------------------------------
Start time:
Baseline: tunnel0=UP, tunnel1=UP; BGP0=UP, BGP1=UP
Event: tunnel0 brought down via approved method
BGP0:
BGP1:
Route 172.20.50.0/24 still present:
Successful requests / total:
Observed disruption duration:
Recovery time:
Issues encountered:
Verified by:
~~~

**The VPN service SLA does not replace end-to-end failover testing.** ISPs, peer appliances, firewalls, DNS, backends, and service architecture can introduce extra single points of failure.

## 14. Symptom-Based Troubleshooting

| Symptom | Possible Cause | First Step to Take |
|---|---|---|
| Tunnel stays down | Wrong public IP/peer interface, PSK mismatch, IKE mismatch, UDP/ESP blocked | Compare peer config, tunnel status, and IKE/IPsec logs |
| Only tunnel 0 works | Tunnel 1 misconfigured on peer or blocked by firewall/NAT | Check interface 1 mapping and dedicated PSK |
| Tunnel UP yet BGP DOWN | Wrong ASN, link-local `/30`, BGP policy/port, or peer config | Read Cloud Router `get-status` and peer BGP logs |
| BGP UP yet on-prem route missing | Peer not advertising prefix, or filter/routing mode issue | Check received BGP table and advertised prefixes |
| Route works one way only | Missing return advertisement/route or wrong next-hop | Check routing tables on both ends |
| Ping fails, TCP service works | ICMP blocked | Test using the actual application port |
| TCP connection times out | Firewall/VPC policy, OS firewall, route, service not listening | Use Connectivity Tests, logs, packet counters |
| Fails only on large packets | MTU, MSS, PMTUD, fragmentation | Measure MTU and check TCP MSS clamping on peer |
| DNS GCP → on-prem `SERVFAIL` | Cannot reach DNS or missing return route to `35.199.192.0/19` | Check UDP/TCP 53, routes, Cloud DNS forwarding config |
| DNS on-prem → GCP fails | Missing inbound DNS policy, wrong resolver IP, missing conditional forwarder | Check policy and on-prem DNS configuration |
| Cloud SQL still unreachable | Missing private service route, auth/TLS, or database firewall | Consult specific Cloud SQL connectivity architecture |
| VPC in another region cannot reach on-prem | `REGIONAL` dynamic routing mode, missing advertisements/routes | Check routing mode and regional layout |
| BGP switches routes unexpectedly | Multiple sites advertising overlapping prefixes, different priority/MED | Inspect `bestRoutes`, advertisements, and route policies |
| Network costs spike unexpectedly | Egress, tunnel traffic, cross-region/backend paths | Compare Cloud Billing Reports with network metrics |

### 14.1. Using Connectivity Tests and Network Intelligence Center

**Connectivity Tests** analyze paths based on supported Google Cloud network configurations. It is useful for spotting route/firewall issues, though it cannot always inspect the entire external network or physical on-premises appliance state. Final conclusions require logs and metrics from both sides.

To investigate:

1. Identify the exact **source/destination IP/port** of the failing request.
2. Check tunnels/BGP before reading application logs.
3. Read **VPC firewall logs** and Cloud VPN logs/metrics if configured.
4. Check on-premises appliances for the same timestamp and IP tuple.
5. If DNS is failing, test the IP directly to isolate name resolution.
6. If only large packets fail, measure MSS/MTU rather than changing IAM.

### 14.2. Routing Errors from VPC Peering or Multiple Networks

If a workload sits in **another VPC** connected via VPC Network Peering, it cannot automatically use VPN routes through the first VPC as a transit network. Google Cloud VPC peering has **transitive routing** limits and custom route import/export rules. Design Shared VPC, Network Connectivity Center, or another supported topology to fit the architecture.

Similarly, multiple on-premises sites with identical CIDRs require dedicated NAT/route policies. Never leave two overlapping subnets and try to fix everything by tuning BGP priority alone.

## 15. Securing Hybrid Connectivity

VPN encrypts traffic **between the two VPN endpoints**, but does not replace all other security layers.

### 15.1. Deployment Rules

- Advertise **only genuinely needed prefixes**; never push `0.0.0.0/0` across a site unless required by architecture.
- Assign least-privilege IAM for VPC, Cloud Router, VPN, and DNS administrators.
- Manage PSKs via a secrets tool and rotate per policy; avoid pasting plaintext secrets into IaC.
- Restrict firewalls by source, destination, protocol, and port; prefer environment segmentation.
- Never treat "already on a private network" as justification to skip application TLS/IAM authentication.
- Enable needed logs/metrics; protect logs so hostnames, topology, or sensitive data are not leaked.
- Use labels for owner/environment and record prefix/permission diagrams in operational docs.
- Apply route/advertisement changes through pull requests or change tickets with impact review.

### 15.2. Division of Responsibilities

| Team | Responsibilities |
|---|---|
| On-premises network | VPN appliances, peer public IPs, BGP ASNs, LAN routes, site DNS, firewalls |
| Cloud platform | VPC, subnets, Cloud VPN, Cloud Router, firewalls, private DNS policies |
| Application | Endpoints, TLS/auth, timeouts/retries, SLOs, database/secret access |
| Security | Least-privilege reviews, network segmentation, PSKs, logging, auditing |
| FinOps | Tunnel, transfer, test compute, monitoring, and Interconnect costs if used |

All teams must work from the **same parameter sheet**. A small mismatch in peer ASN, IKE PSK, or subnet CIDR can prevent the entire system from communicating.

## 16. Reliability, Monitoring, and Cost

### 16.1. Monitoring

Signals to watch:

- **Tunnel status** and count of active tunnels.
- **BGP session status**, learned/advertised route counts, unexpected best-route changes.
- **Byte/packet throughput** per tunnel and proximity to throughput limits.
- **Latency and packet loss** between test endpoints, plus DNS resolution times.
- **Application errors** over the hybrid connection, retry errors, and timeouts.
- **Convergence time** after losing a path.

Use Cloud Monitoring for metrics emitted by Cloud VPN/Cloud Router alongside on-premises peer monitoring. Distinguish a "tunnel0 down" alert from "both tunnels down and application unreachable."

### 16.2. Cost Components

Never assume VPN is free because it uses private IPs. Total costs can come from:

| Component | How Costs Arise |
|---|---|
| HA VPN/tunnels | Tunnel/gateway resource fees per current pricing |
| Network egress | Traffic leaving Google Cloud by direction, destination, and service type |
| Test VM and disk | Compute/storage runtime usage |
| Cloud DNS | Managed zones, queries, or related features per applicable pricing |
| Logging/Monitoring | Log/metric ingestion and retention exceeding free allowances |
| Interconnect | Ports/attachments, provider fees, and transfer if used |
| Redundancy | Dual tunnels/circuits for HA can increase operating costs |

**Cloud Billing Reports** help break down costs by service/SKU, while the **Cost table** supports invoice reconciliation. When comparing VPN and Interconnect, include data transfer, peer/ISP equipment, operations, and reliability targets—not just the unit price of one tunnel.

## 17. Lab Cleanup Without Impacting Other Systems

Clean up only if **resources were created exclusively for the lab** and no other apps or teams use them. Deleting network resources can sever connectivity; verify dependencies and deletion order first.

Conceptual order:

1. Verify no tests/traffic still need the setup and save lab results.
2. Remove **DNS policies/private/forwarding zones** created for the lab after confirming no clients use them.
3. Delete the **test VM** and related firewall rules.
4. Remove **BGP peers/Cloud Router interfaces** on lab tunnels and verify routing impact.
5. Delete **VPN tunnels**, then **Cloud Router**, **HA VPN gateway**, and **external peer gateway** once dependencies are gone.
6. Delete the lab-only subnet and VPC last, after confirming no resources remain.
7. Check Cloud Billing / Resource Inventory for any leftover billable resources.

**Read-only** inventory commands before cleanup:

~~~bash
gcloud compute vpn-tunnels list --project="$PROJECT_ID"
gcloud compute vpn-gateways list --project="$PROJECT_ID"
gcloud compute routers list --project="$PROJECT_ID"
gcloud compute instances list --project="$PROJECT_ID"
gcloud compute firewall-rules list --project="$PROJECT_ID"
gcloud dns managed-zones list --project="$PROJECT_ID"
gcloud dns policies list --project="$PROJECT_ID"
~~~

This lesson **does not provide a bulk delete script** because individual resources may be shared with other workloads; operators must confirm owners, scope, dependencies, and recovery paths. If a VPN link serves production, decommission it only under an approved change plan.

## 18. Post-Lab Assessment Exercises

### 18.1. Exercise A — Reading a Network Diagram

A system has:

- VPC subnet **10.20.10.0/24**.
- On-premises subnet **172.20.50.0/24**.
- Tunnels 0/1 are both UP; BGP peer 0 is UP, peer 1 is DOWN.
- An on-premises client cannot connect to the VM, even though Cloud Router sees the route to **172.20.50.0/24**.

Answer:

1. Does this state meet HA expectations? Why or why not?
2. Does Google Cloud seeing the route to on-premises prove on-premises knows the route to **10.20.10.0/24**?
3. Where should firewalls and hosts be inspected?
4. Should you test ping or the application's TCP port before drawing conclusions?
5. If traffic works only one way, what else should be checked?

**Guidance:** The second BGP peer is down, so HA is incomplete; GCP's route does not prove the return route exists; check peer routes/firewalls/OS, test the actual service port, and inspect the return traffic path.

### 18.2. Exercise B — Incomplete DNS Behavior

A Google Cloud VM gets `SERVFAIL` resolving **app.corp.example.internal**, yet **ping 172.20.50.53** from the application network succeeds. Give at least four hypotheses.

**Guidance:** misconfigured forwarding zone; on-premises DNS rejecting UDP/TCP 53; missing return route to **35.199.192.0/19**; DNS server replying from a different IP; firewall/ACL blocking requests; DNS service missing record or server error. **Pinging the DNS server does not validate the full DNS forwarding path.**

### 18.3. Exercise C — Technology Selection

An enterprise transfers high volumes of steady data, needs predictable transit times, and has a policy requiring dedicated physical links. Is HA VPN over the Internet sufficient? Compare **HA VPN**, **Partner Interconnect**, and **Dedicated Interconnect**, weighing throughput, redundancy, lead time, cost, encryption, and network providers.

**Guidance:** do not choose based on price alone. With dedicated-circuit and high-scale requirements, evaluate Interconnect and add IPsec when encryption in transit is mandated.

### 18.4. Lab Completion Report Template

~~~text
Project / VPC / Region:
Test timestamp (UTC):
GCP subnet / On-prem subnet:
Cloud VPN interface 0/1: [redacted public addresses]
Tunnel 0/1: [UP/DOWN + timestamp]
BGP peer 0/1: [ESTABLISHED/DOWN]
GCP learned routes:
On-prem learned routes:
Firewall source/destination/port:
TCP / ICMP results:
DNS GCP -> on-prem results:
DNS on-prem -> GCP results:
Failover results:
Cost or budget alerts:
Open issues:
Owner and remediation date:
~~~

The report should record **steps actually executed and observed outcomes**, not "completed" merely because resources were created. Never include pre-shared keys, tokens, or private keys in exercise submissions.

## 19. Google Cloud References

Useful official documentation for verifying commands, SLA conditions, and network requirements:

- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Create an HA VPN gateway to a peer VPN gateway](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/creating-ha-vpn)
- [Configure a peer VPN gateway](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/configuring-peer-gateway)
- [HA VPN topologies](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/topologies)
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices)
- [View Cloud Router details and BGP state](https://docs.cloud.google.com/network-connectivity/docs/router/how-to/viewing-router-details)
- [VPC dynamic routing mode and best path selection](https://docs.cloud.google.com/network-connectivity/docs/router/how-to/create-network-set-modes)
- [Cloud DNS forwarding zones](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones)
- [Cloud DNS best practices](https://docs.cloud.google.com/dns/docs/best-practices)
- [Cloud DNS server policies](https://docs.cloud.google.com/dns/docs/policies)
- [Cloud VPN troubleshooting](https://docs.cloud.google.com/network-connectivity/docs/vpn/support/troubleshooting)
- [Cloud VPN pricing](https://cloud.google.com/network-connectivity/pricing)

Command names, CLI flags, product configs, pricing, and SLA terms may be updated by Google Cloud. In real deployments, always check documentation for your CLI version and peer hardware, and align with organizational policy.

---

**Connecting to the CLOUD_PROVIDERS_GCP track:** connecting on-premises to a VPC is an integrated exercise combining **project/IAM, VPC/subnets, HA VPN/BGP, Cloud DNS, firewalls, Compute Engine, and access paths to managed services**. When extending to GKE, Cloud Run, storage, and databases, maintain a mindset spanning from **addressing and routing** to **identity, security, automation, monitoring, cost, and resilience**. A hybrid connection is considered healthy when it can **demonstrate bidirectional flow, enforce least-privilege access, detect faults, and recover as designed**.
