# DNS Forwarding, Peering, and Hybrid DNS Resolution

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish between **Cloud DNS private zones**, **forwarding zones**, **DNS peering zones**, and **DNS server policies**, and explain when each is needed.
2. Design bidirectional name resolution between workloads on Google Cloud and DNS systems in a data center/on-premises via **Cloud VPN** or **Cloud Interconnect**.
3. Explain why **DNS peering is not VPC Network Peering**, how to choose producer/consumer VPCs, and DNS peering hop limits.
4. Deploy and verify a hybrid DNS architecture using **gcloud** commands, **dig/nslookup** queries, DNS 53/TCP+UDP rules, and return routes to the **35.199.192.0/19** range.
5. Diagnose common errors such as **NXDOMAIN**, **SERVFAIL**, selecting the wrong DNS zone, route/region mismatches, TTL caching, and missing IAM permissions.
6. Evaluate security, reliability, observability, and cost of DNS configurations when using Compute Engine, GKE, Cloud Run, and storage/database services.

## 1. Why Does a Cloud Architecture Need Hybrid DNS Resolution?

An organization rarely migrates all systems to the cloud at once. For example:

- A Java API on **Compute Engine** or **GKE** needs to call a billing service named **billing.corp.example.com** running on-premises.
- An internal monitoring system needs to access a service on Google Cloud by name **api.gcp.example.com**.
- Multiple application projects share DNS managed by a network team in a **hub VPC**.
- A release job on **Cloud Run** needs to connect to a database over a private network and resolve enterprise-managed names.

HTTPS calls, PostgreSQL connections, or name-based pings all depend on **DNS resolution** before the transport layer can operate. Having an IP route over VPN does not guarantee the domain name resolves; having DNS return the right IP does not prove firewalls and the application allow the connection.

In the **CLOUD_PROVIDERS_GCP** module, learners study how to organize projects, IAM, and VPCs, select Compute Engine/GKE/Cloud Run, protect storage/databases, automate releases, and monitor reliability and cost. Hybrid DNS ties these concepts together: **right domain name → right IP address → right route → right access policy → available service**.

### Goal of the Running Example

Assume an enterprise has three administrative domains:

| Component | Project/VPC | Illustrative Network Range | Role |
|---|---|---|---|
| Google Cloud Hub | **net-hub-001 / vpc-hub** | **10.50.0.0/16** | Hosts Cloud VPN/Interconnect and central DNS configuration |
| Application Spoke | **app-dev-001 / vpc-app** | **10.60.0.0/16** | VMs/Java API; does not directly connect via VPN to on-premises |
| On-premises | Enterprise network | **172.16.0.0/16** | DNS resolvers **172.16.100.10** and **172.16.100.11** |

Two namespaces:

- **corp.example.com.**: authoritative DNS hosted on-premises.
- **gcp.example.com.**: private records managed in Cloud DNS.

All IDs, CIDRs, domain names, and IPs in this lesson are **training assumptions**, not pre-existing resources. In real deployments, use a domain controlled by your organization and verify existing IPs, routes, and DNS policies.

## 2. Core Concepts to Distinguish

### 2.1. DNS Resolution Is Different from Network Connectivity

A DNS lookup typically proceeds in two phases:

1. The **resolver** finds the IP address or DNS record corresponding to the domain name.
2. The **application** opens a connection to the returned IP address using TCP/UDP or the appropriate protocol.

For instance, **billing.corp.example.com → 172.16.20.25** may resolve successfully, yet the connection still fails if Cloud VPN is down, a return route is missing, or a firewall blocks TCP/443. Conversely, if the application can connect directly to **172.16.20.25** while name resolution fails, that points directly to investigating the DNS layer.

### 2.2. Authoritative Server, Recursive Resolver, and Conditional Forwarder

| Concept | Role | Example |
|---|---|---|
| **Authoritative DNS server** | Holds authoritative records for a DNS zone | Internal DNS managing **corp.example.com.** |
| **Recursive resolver** | Answers queries by finding authoritative sources or using cache | VM resolver, organization's internal DNS |
| **Forwarder** | Forwards queries to another resolver/name server | Cloud DNS forwarding zone sending **corp.example.com.** to on-prem DNS |
| **Conditional forwarding** | Only forwards names matching a specific suffix | Internal DNS forwarding **gcp.example.com.** to Cloud DNS inbound IP |
| **Private DNS zone** | Serves records scoped to authorized networks | Zone **gcp.example.com.** visible only to one or more VPCs |
| **DNS peering zone** | Allows one VPC to look up names using another VPC's DNS rules | Spoke querying hub for **corp.example.com.** |

### 2.3. The VM's Cloud DNS Resolver

Compute Engine VMs normally use the **metadata server 169.254.169.254** as their DNS resolver. Cloud DNS applies the resolution rules of the VPC to which the VM belongs to answer queries from private DNS, forwarding zones, peering zones, or public DNS depending on configuration.

~~~text
VM in VPC → DNS resolver at 169.254.169.254
                  |
                  +→ Private zone: Cloud DNS data
                  |
                  +→ Forwarding zone: query another DNS by suffix
                  |
                  +→ Peering zone: query using producer VPC resolution
                  |
                  +→ Public DNS: when not overridden by private/forwarding rules
~~~

This is a high-level diagram. Actual resolution order also depends on **response policies**, GKE cluster-scoped DNS, **longest matching suffix**, DNS server policies, and specific Cloud DNS rules. When multiple configurations overlap, consult the **VPC name resolution order** documentation and test with live queries.

## 3. Three Core Building Blocks: Forwarding Zone, Peering Zone, and Server Policy

### 3.1. Private Managed Zone: Holding Private Records

For example, create **gcp.example.com.** in the hub VPC. The record **api.gcp.example.com. A 10.50.10.20** is managed by Cloud DNS. VPCs attached to the zone can query the record within the DNS visibility scope. This is not a public zone freely queryable from the Internet.

### 3.2. Forwarding Zone: Routing Queries for a Suffix to a DNS Target

A **forwarding zone** is a type of Cloud DNS private zone. It does not directly store user-created A/CNAME records. Instead, it holds a **DNS suffix** and **forwarding targets**.

Example:

~~~text
In vpc-hub:
  Forwarding zone  : corp.example.com.
  Target name server: 172.16.100.10, 172.16.100.11

VM queries billing.corp.example.com.
→ Cloud DNS selects the forwarding zone
→ Cloud DNS forwards the query to the on-prem resolver
→ Receives A 172.16.20.25 or the corresponding DNS error code
~~~

Only names within the zone's scope are forwarded under this configuration. Therefore, a forwarding zone is usually preferable to forcing **every DNS query** in the VPC through an on-premises resolver.

### 3.3. DNS Peering Zone: Sharing Resolution Across VPCs

A **DNS peering zone** creates a **consumer VPC → producer VPC** relationship for a DNS suffix.

- **Consumer** is the network containing workloads performing lookups.
- **Producer** is the network whose Cloud DNS resolution rules are used to look up names on behalf of the consumer.
- From the consumer's perspective, private records, forwarding zones, Compute Engine internal names, or applicable alternative name servers in the producer can be used according to the producer's rules.

For example, **vpc-app** is the consumer for **corp.example.com.**, while **vpc-hub** is the producer because the hub has the forwarding zone to on-premises.

**DNS peering does not require VPC Network Peering.** They are two separate capabilities: DNS peering exchanges **name resolution queries**, whereas VPC Network Peering exchanges **IP routes** between VPCs. Having a resolved name without a network path to the returned IP address still prevents the application from connecting.

### 3.4. DNS Server Policy: Inbound and Outbound at the VPC Level

A **DNS server policy** bound to a VPC can declare:

- **Inbound forwarding**: allows on-premises systems to send DNS queries to Cloud DNS **inbound forwarding entry points** in the VPC.
- **Outbound forwarding with alternative name servers**: sends most DNS queries from the VPC to specified DNS servers, following Cloud DNS's specific resolution order.
- Additional service-supported options, such as DNS logging or DNS64, subject to their own constraints.

A VPC can be associated with **at most one DNS server policy**. If you need both inbound and outbound in the same VPC, configure them in **one policy** rather than creating two competing policies.

**Design warning:** Outbound server policy alternative name servers can cause Cloud DNS to bypass resolution of many private/forwarding/peering zones and Compute Engine internal DNS under default rules. When you only need to forward a single on-prem domain, prefer a **suffix-based forwarding zone**.

### 3.5. Decision Table

| Requirement | Usually Appropriate Mechanism | Scope |
|---|---|---|
| Create private records managed in Google Cloud | **Private managed zone** | Authorized VPCs |
| VMs on Google Cloud query **corp.example.com.** names on-prem | **Forwarding zone** | Specific DNS suffix |
| A spoke VPC queries names resolved by a hub VPC | **DNS peering zone** | Consumer → producer, single DNS suffix |
| On-prem hosts query **gcp.example.com.** names in Cloud DNS | **Inbound DNS server policy** + on-prem conditional forwarding | VPC with entry points and hybrid link |
| Route all VPC queries through enterprise DNS | **Outbound server policy** with alternative name servers | Broad impact on VPC; requires careful testing |
| Multiple projects share a private zone on a Shared VPC | **Private zone on host network / cross-project binding** as appropriate | Network-level governance |
| Access only one private service in another VPC | Consider **Private Service Connect** and its accompanying DNS | Service/endpoint, different from DNS peering |

## 4. Bidirectional Hybrid DNS Architecture

### 4.1. From Google Cloud to On-Premises

~~~mermaid
flowchart LR
    A["VM in vpc-hub<br/>or VM in vpc-app"] --> B["Cloud DNS resolver"]
    B --> C{"corp.example.com.?"}
    C -->|In hub| D["Forwarding zone<br/>corp.example.com."]
    D --> E["Cloud VPN / Interconnect"]
    E --> F["On-prem DNS<br/>172.16.100.10/.11"]
    F --> G["A 172.16.20.25"]
~~~

When a VM in **vpc-app** uses a peering zone pointing to the hub, the query is evaluated according to the producer's DNS (**vpc-hub**) before reaching the on-premises forwarding targets. The hybrid link must reside in the VPC that holds the forwarding zone and supported DNS routes.

### 4.2. From On-Premises to Google Cloud

~~~mermaid
flowchart LR
    A["On-prem application"] --> B["On-prem DNS resolver"]
    B -->|"Conditional forward<br/>gcp.example.com."| C["Cloud VPN / Interconnect"]
    C --> D["Cloud DNS inbound<br/>entry point in vpc-hub"]
    D --> E["Private zone<br/>gcp.example.com."]
    E --> F["A 10.50.10.20"]
~~~

The **inbound** path uses one or more **regional internal IP addresses** allocated by Cloud DNS for a VPC with an inbound server policy. These IPs serve as DNS query entry points—they are not public name server IPs and not **169.254.169.254** that on-premises hosts can call directly.

The DNS ingress point must match the region/VPC where hybrid traffic enters. According to Cloud DNS documentation, **inbound entry points are not reachable across VPC Network Peering or NCC boundaries**; place the inbound policy in the VPC **containing the hybrid link to on-premises** or design local entry points accordingly.

### 4.3. The Final DNS Answer Is Not Enough to Reach the Application

Hybrid DNS only answers **"Which address corresponds to this name?"**. Once the application receives **172.16.20.25** or **10.50.10.20**, business traffic still requires:

1. Forward and return routes over Cloud VPN/Interconnect/VPC connectivity as appropriate.
2. Firewall rules, network segmentation, and ACLs permitting the right protocol/port.
3. Appropriate IAM or application/data authentication.
4. A service actively listening on the right address and functioning.

**A DNS peering zone does not create IP connectivity.** Do not treat DNS configuration as a substitute for network design.

## 5. Forwarding Zone Details: Targets, Routes, and Return Paths

### 5.1. Which Forwarding Targets Are Supported?

Cloud DNS supports several target groups, with a choice of **standard routing** or **private routing**:

| Target Group | Example | Key Network Requirements |
|---|---|---|
| **Type 1: internal IP in a VPC authorized for the forwarding zone** | DNS VM or internal passthrough Network Load Balancer in that VPC | Cloud DNS uses subnet routes to the target; firewall allows DNS |
| **Type 2: on-premises DNS server over hybrid link** | 172.16.100.10 over VPN/Interconnect | Custom route to DNS and return route to the Cloud DNS range |
| **Type 3: public DNS target** | Resolver with a public IP on the Internet | Uses standard routing per public target rules |
| **Type 4: FQDN target** | dns.corp.example.net. resolved to IP | Single FQDN target only; IP count limits and compatible routing |

In a forwarding zone, you can specify **multiple IP targets** or **one FQDN target**, not both in the same zone. For an FQDN target, Cloud DNS resolves it to an IP before forwarding and applies specific constraints; explicit IPs are usually simpler for on-prem DNS.

**Do not use a Type 1 target that is a VM in another VPC** just because the two VPCs are peered or connected by VPN. If the DNS target is actually in the second VPC, create the forwarding zone in the target's VPC and use a **DNS peering zone** from the first VPC.

### 5.2. What Does the 35.199.192.0/19 Source Range Mean?

When Cloud DNS forwards queries to private targets over standard forwarding, queries originate from Google Cloud DNS's **35.199.192.0/19** range. This range is used by Google's forwarding infrastructure, not the querying VM's subnet.

Therefore, on-prem DNS must allow:

- **Source:** 35.199.192.0/19.
- **Destination:** on-prem resolvers, e.g., 172.16.100.10 and 172.16.100.11.
- **Protocol:** UDP **53** and TCP **53**.
- **Response:** routed back to the exact Cloud DNS source IP via the **same VPC/hybrid link where the query exited**.

On-premises must route **35.199.192.0/19** back to the **same VPC** containing the forwarding zone and VPN/Interconnect connection. With Cloud Router BGP, you can configure **custom route advertisement** for that prefix; with static routing, configure equivalent routes per supported network design.

~~~text
Google Cloud DNS 35.199.192.0/19
        |
  VPC hub → VPN/Interconnect → 172.16.100.10:53
        ^                             |
        |                             v
        +----- return route to 35.199.192.0/19
                 via the same VPC hub
~~~

**Reply from the exact target that received the query.** If DNS server **172.16.100.10** delegates to another server and that other server replies directly to Cloud DNS from its own IP, the response may be dropped because its source IP does not match the target IP Cloud DNS queried. Resolver 172.16.100.10 must return the answer from its own address.

### 5.3. Region and Limitations Across Peering

Cloud DNS selects routes from the **VPC authorized to use the forwarding zone**. For Type 2 targets, valid static/dynamic custom routes to on-prem must exist in the right VPC and region according to the service's routing rules.

Cloud DNS **does not use transitive IP connectivity across VPC Network Peering** to reach forwarding targets. A VM in a spoke may be able to **`dig` directly** to on-prem DNS because VPN routes are imported via peering, yet a **forwarding zone placed in the spoke** pointing to on-prem DNS over the hub's VPN can still fail. The right approach:

1. Place the forwarding zone in the **hub** that owns the hybrid link.
2. Place a **DNS peering zone** in the spoke pointing to the hub.
3. Verify DNS peering/region constraints, routes, and DNS targets per design.

### 5.4. Caching and Availability

Cloud DNS may cache responses returned by forwarding targets. When targets are healthy, cache duration is capped at **the lesser of the record's TTL and 60 seconds** under the documented forwarding zone model. If all targets become unreachable, cached results follow separate retention rules based on TTL.

**TTL does not replace HA.** Maintain at least two healthy, properly configured on-prem resolvers permitted to answer DNS over VPN/Interconnect. Cloud DNS selects targets using a ranking algorithm that factors in response success and latency; it **does not query targets strictly in fixed command-line order by default**.

## 6. DNS Peering Details: Consumer, Producer, and Hop Limits

### 6.1. DNS Peering Is a One-Way Relationship

If **vpc-app → vpc-hub** is configured for suffix **corp.example.com.**, workloads in vpc-app can resolve names according to vpc-hub's DNS policies. This **does not automatically** allow vpc-hub to resolve a suffix that exists only in vpc-app.

To look up names in the reverse direction, configure a separate peering zone or appropriate private zone visibility. Do not assume **bidirectional DNS peering** just because the name contains *peering*.

### 6.2. How DNS Peering Differs from VPC Network Peering in Transitivity

**VPC Network Peering does not route IP traffic transitively**: A ↔ B and B ↔ C do not allow IP packets from A to reach subnet C via B.

**Cloud DNS peering, however, supports up to one transitive hop** across **three VPCs** per official documentation. For example:

~~~mermaid
flowchart LR
    A["VPC A<br/>DNS consumer"] -->|"Peering zone A → B"| B["VPC B<br/>intermediate"]
    B -->|"Peering zone B → C"| C["VPC C<br/>final DNS producer"]
~~~

This is **DNS query forwarding** between producers/consumers, not IP packet forwarding for applications. Do not design DNS peering chains longer than supported, and still verify resolution rules for each suffix/producer.

### 6.3. DNS Peering Does Not Require IP Peering

You can configure DNS peering between two VPCs that are not directly connected via VPC Network Peering. If, after receiving an A record, the application needs to connect to an IP in the producer VPC, you must separately design:

- Direct VPC Network Peering, Shared VPC, NCC, or another supported connectivity method.
- **Private Service Connect** if you only need to consume a single service rather than an entire subnet range.
- Firewalls, routes, IAM, and DNS for the target service.

### 6.4. When the DNS Producer Has a Forwarding Zone

A valid hub/spoke design:

~~~text
VM in vpc-app
  -> DNS peering zone (corp.example.com.) in vpc-app
  -> Cloud DNS evaluates via vpc-hub
  -> forwarding zone (corp.example.com.) in vpc-hub
  -> on-prem resolver via vpc-hub VPN/Interconnect
~~~

When **global dynamic routing** on the producer VPC is disabled, Cloud DNS imposes regional constraints for forwarding across peering: the producer must have a VM, VLAN attachment, or Cloud VPN tunnel in the **same region as the querying consumer VM** to select a valid route. Therefore, if a DNS architecture works in region A but fails from region B, check the **producer's regional resources**, dynamic routing mode, and route reachability.

### 6.5. IAM Permissions for Creating a Peering Zone

The user creating a peering zone needs permission to manage DNS zones in the consumer project. To select a producer VPC, the creating principal also needs **dns.networks.targetWithPeeringZone**, typically granted via **roles/dns.peer** on the producer project under approved IAM policies.

DNS peering IAM only controls **permission to establish the resolution relationship**; it does not grant **access to resources** in the producer and does not open firewalls.

## 7. Practice: Configuring Hub-to-On-Prem with a Forwarding Zone

In the following commands, projects, networks, domains, and IPs are examples. Execute only in an authorized lab environment and substitute your real values. Before creating zones, verify the Cloud DNS API is enabled, the principal has **roles/dns.admin** or equivalent permissions, DNS targets are healthy, and the hub VPC has a valid hybrid connection.

### Step 1 — Inspect Resources

~~~bash
# Check the hub project and VPC
gcloud projects describe net-hub-001
gcloud compute networks describe vpc-hub --project=net-hub-001

# List existing DNS zones to avoid suffix collisions or model confusion
gcloud dns managed-zones list --project=net-hub-001

# Check bound DNS server policies
gcloud dns policies list --project=net-hub-001
~~~

Verify on the real network: Cloud VPN/Interconnect, routes to **172.16.100.10/11**, return routes to **35.199.192.0/19**, DNS ACLs, and firewall appliances.

### Step 2 — Create the Forwarding Zone in vpc-hub

~~~bash
gcloud dns managed-zones create corp-forward \
  --project=net-hub-001 \
  --description="Forward corp.example.com to on-prem DNS" \
  --dns-name="corp.example.com." \
  --visibility=private \
  --networks=vpc-hub \
  --forwarding-targets=172.16.100.10,172.16.100.11
~~~

**--forwarding-targets** uses **standard routing**; for RFC 1918 private IPs in hybrid setups, Cloud DNS routes from the zone's VPC to on-prem as designed. Depending on needs, **--private-forwarding-targets** can enforce private routing for special non-RFC 1918 IPs; verify target IP types and product limits before choosing.

Do not enter an application URL like **https://billing.corp.example.com** as a target. A forwarding zone target must be a **DNS name server** (a supported IP or FQDN), not a web service.

### Step 3 — Read Back the Configuration

~~~bash
gcloud dns managed-zones describe corp-forward \
  --project=net-hub-001 \
  --format="yaml(name,dnsName,visibility,privateVisibilityConfig,forwardingConfig)"
~~~

Confirm the suffix **corp.example.com.**, authorized VPCs, and list of forwarding targets. A forwarding zone does not store enterprise A records; those records reside in on-prem DNS.

### Step 4 — Test from a VM in vpc-hub

On a Linux VM with a NIC attached to vpc-hub using the default DNS resolver:

~~~bash
# Use Compute Engine's metadata resolver
dig @169.254.169.254 billing.corp.example.com. A

# Query the on-prem server directly to isolate errors (if route/ACL permits)
dig @172.16.100.10 billing.corp.example.com. A

# When testing responses over TCP instead of UDP
dig +tcp @169.254.169.254 billing.corp.example.com. A
~~~

If querying **172.16.100.10** directly succeeds while querying through the metadata resolver fails, focus on checking the forwarding zone, Cloud DNS source range, return route, and DNS target configuration. If both fail, inspect routes, firewalls, the source DNS service, and the domain name.

**Caution:** Direct `dig` from a VM uses the VM's source IP; Cloud DNS forwarding uses source **35.199.192.0/19**. Thus, a successful direct `dig` **does not prove** the on-prem firewall allows Cloud DNS.

## 8. Practice: DNS Peering from Spoke to Hub

Suppose **vpc-app** in **app-dev-001** needs to look up **corp.example.com.** via the hub's forwarding zone. In the consumer project, create a **peering zone** pointing to the producer:

~~~bash
gcloud dns managed-zones create corp-from-spoke \
  --project=app-dev-001 \
  --description="Resolve corp.example.com via hub VPC" \
  --dns-name="corp.example.com." \
  --visibility=private \
  --networks=vpc-app \
  --target-project=net-hub-001 \
  --target-network=vpc-hub
~~~

This command requires the principal to have permission to create Cloud DNS zones in **app-dev-001** and **dns.networks.targetWithPeeringZone** on **vpc-hub** in the producer. If you get **403**, check IAM, project, and VPC before assuming DNS routing is broken.

~~~bash
gcloud dns managed-zones describe corp-from-spoke \
  --project=app-dev-001 \
  --format="yaml(name,dnsName,visibility,peeringConfig,privateVisibilityConfig)"
~~~

Test from a VM in **vpc-app**:

~~~bash
dig @169.254.169.254 billing.corp.example.com. A
~~~

Expected resolution path: **vpc-app → DNS peering zone → vpc-hub → forwarding zone → on-prem DNS**. Verify both the returned answer and the application's ability to **connect to the corresponding IP** over the real network. You do not have to create **VPC Network Peering** just to make DNS peering work.

## 9. Practice in the Reverse Direction: On-Premises Querying a Cloud DNS Private Zone

### Step 1 — Create a Private Zone in the Hub

~~~bash
gcloud dns managed-zones create gcp-private \
  --project=net-hub-001 \
  --description="Private service names in hub" \
  --dns-name="gcp.example.com." \
  --visibility=private \
  --networks=vpc-hub
~~~

Add an illustrative record:

~~~bash
gcloud dns record-sets transaction start \
  --project=net-hub-001 \
  --zone=gcp-private

gcloud dns record-sets transaction add 10.50.10.20 \
  --project=net-hub-001 \
  --zone=gcp-private \
  --name="api.gcp.example.com." \
  --type=A \
  --ttl=300

gcloud dns record-sets transaction execute \
  --project=net-hub-001 \
  --zone=gcp-private
~~~

Before real use, **10.50.10.20** must belong to a valid service in the network, and that service must have proper routing, firewalls, and authentication.

### Step 2 — Create an Inbound DNS Server Policy

~~~bash
gcloud dns policies create hub-inbound \
  --project=net-hub-001 \
  --description="Inbound Cloud DNS for on-prem resolvers" \
  --networks=vpc-hub \
  --enable-inbound-forwarding
~~~

If the VPC already has another server policy, **update the existing policy** instead of trying to attach a second policy to the same VPC.

### Step 3 — Find Regional Inbound DNS Entry Points

~~~bash
gcloud compute addresses list \
  --project=net-hub-001 \
  --filter='purpose = "DNS_RESOLVER"' \
  --format='table(address,region,subnetwork)'
~~~

Match the **DNS_RESOLVER** IPs to the VPC and region of your hybrid connection. These are Google-managed internal IPs for inbound forwarding. IPs may change if inbound forwarding is disabled/re-enabled or if the VPC is recreated; document them in internal DNS configuration and update procedures.

Google Cloud automatically accepts **TCP/UDP 53** at inbound entry points; you do not need to create a dedicated Google Cloud firewall rule for the inbound resolver address itself as you would for a VM. However, **on-prem routers, firewalls, and DNS forwarders** must still be configured to send queries to this IP.

### Step 4 — Configure a Conditional Forwarder On-Premises

On your internal DNS (Windows Server DNS, BIND, or enterprise DNS appliance), create a rule:

~~~text
Suffix to forward : gcp.example.com.
Target DNS server : <Cloud DNS inbound IP in the VPN/Interconnect region>
Transport         : UDP 53 and TCP 53
Fallback/HA       : Design across supported entry points and regions
~~~

Do not point the conditional forwarder at **169.254.169.254**. That address is the resolver for VMs inside Google Cloud, not a DNS endpoint reachable from on-premises.

### Step 5 — Test from On-Premises

~~~bash
# Use the actual inbound DNS IP you discovered
dig @INBOUND_DNS_IP api.gcp.example.com. A

# Check via the enterprise DNS resolver after configuring conditional forwarding
dig @ONPREM_DNS_IP api.gcp.example.com. A

# When testing over TCP
dig +tcp @INBOUND_DNS_IP api.gcp.example.com. A
~~~

Expect an A record pointing to **10.50.10.20**. Next, verify **route on-prem → 10.50.10.20**, firewalls, application ports, and response behavior; do not equate DNS success with HTTPS success.

### Step 6 — If a Spoke Also Needs to Look Up Hub Names

For example, workloads in **vpc-app** want to resolve **api.gcp.example.com.**. You can:

- Create an additional **DNS peering zone** for suffix **gcp.example.com.** in vpc-app pointing to vpc-hub.
- Or consider sharing the private zone across multiple VPCs per governance model and supported features.

Merely creating a **corp.example.com.** peering zone in vpc-app **does not automatically make every other suffix in vpc-hub available**.

## 10. Differences Between Outbound Forwarding Zones and Outbound Server Policies

This distinction determines whether a DNS setup preserves Google Cloud's internal resolution.

### 10.1. Forwarding Zone: Only Forwards Matching Names

Suppose a VPC uses two private DNS suffixes:

- **gcp.example.com.** managed by Cloud DNS.
- **corp.example.com.** needing forwarding to on-premises.

A forwarding zone for **corp.example.com.** allows both DNS sources to coexist. Queries for other names can continue following VPC resolution rules and public DNS unless blocked by other policies.

### 10.2. Outbound Server Policy: Broadly Alters the Query Path

Example configuring the entire VPC to use alternative name servers:

~~~bash
# Example only to illustrate the mechanism; analyze impact before applying
gcloud dns policies create hub-outbound \
  --project=net-hub-001 \
  --networks=vpc-hub \
  --alternative-name-servers=172.16.100.10,172.16.100.11
~~~

When a VM still uses the metadata resolver while the VPC has alternative name servers configured, Cloud DNS sends most queries to the alternative name servers under the outbound server policy mechanism. This can prevent VMs from **resolving private zones, peering zones, forwarding zones, and Compute Engine internal DNS** along the default path. It is a broad change that can easily break workloads.

Moreover, a VPC can have only **one DNS server policy**. If **hub-inbound** already exists, you cannot create a second **hub-outbound** policy for vpc-hub. You must update **hub-inbound** into a single policy containing both inbound and outbound settings if the design truly requires both.

**Recommendation:** Deploy **suffix-based forwarding zones** when querying on-premises domains, and use an outbound server policy only when you understand all DNS requirements and have alternative name servers responsible for resolving every needed name.

## 11. DNS Resolution Order, Overlapping Zones, and Split-Horizon

### 11.1. Longest Suffix Match

Suppose you have:

- Private zone **example.com.**
- Forwarding zone **corp.example.com.**

When a VM queries **app.corp.example.com.**, Cloud DNS evaluates the best-matching zone according to resolution order, and the more specific suffix takes precedence. Precedence rules also depend on zone types and active policies. Always check **VPC name resolution order**, especially when overlapping suffixes, peering zones, or response policies exist.

### 11.2. Split-Horizon DNS

A domain name can have a **private** record when queried from an authorized VPC and a **public** record when queried from the Internet. For example:

~~~text
api.example.com. from VPC VM:   10.50.10.20 (private)
api.example.com. from Internet: 203.0.113.20 (public example)
~~~

These addresses are illustrative only. Ensure each namespace is governed clearly; a private zone can shadow public information beneath its suffix for authorized VPCs. If a record does not exist in the selected private zone, do not assume the resolver will automatically look up the same name in public DNS.

### 11.3. What Do NXDOMAIN, SERVFAIL, and Timeouts Indicate?

| Result | Basic Meaning | Investigation Hints |
|---|---|---|
| **NOERROR + ANSWER** | Resolver returned a record | Check IP accuracy and TTL; then check IP connectivity |
| **NOERROR with no A record** | The name may exist, but not for the queried record type | Try AAAA/CNAME; inspect zone data and application expectations |
| **NXDOMAIN** | Resolver could not find the name in the selected data source | Wrong name, wrong suffix/zone, private zone shadowing public zone, missing record |
| **SERVFAIL** | Resolver hit a processing error or could not get an upstream answer | Forwarding target unreachable, timeout, DNSSEC/upstream/route error |
| **Timeout** | No response received within the timeout window | Route/firewall/TCP-UDP 53 issue, DNS server down, response dropped |
| **REFUSED** | DNS server rejected the query | DNS ACL, resolver policy, unauthorized query source |

**Do not randomly tweak IAM or firewalls based solely on NXDOMAIN.** Determine which resolver received the query, which zone was selected, which target was contacted, and which response code was returned.

## 12. Security and Reliability in Hybrid DNS

### 12.1. Controlling DNS Paths

- Permit only **UDP/TCP 53** between approved source/destination resolvers; do not open entire network ranges unnecessarily.
- For forwarding to private targets, on-prem must allow source **35.199.192.0/19**. This is the Cloud DNS forwarding source range, not a requirement to allow that range to all internal services.
- Restrict **roles/dns.admin** and **roles/dns.peer** under least privilege; review all changes to zones, server policies, and peering.
- Scope private zones to the exact networks that need them; do not grant resolution visibility broader than business scope.
- Protect on-prem DNS against open recursion and configure it to prevent **corp → gcp → corp** forwarding loops.
- DNS resolves names; it **does not replace** IAM, TLS encryption, or application network segmentation.

### 12.2. High Availability

Dependencies include **Cloud DNS**, VPN/Interconnect, Cloud Router/routes, on-prem networks, and external resolvers. To eliminate single points of failure:

1. Use multiple on-prem DNS targets across appropriate failure domains.
2. Design redundant hybrid connectivity and clear return routes.
3. Test the impact if one region loses its hybrid link or if an inbound policy is modified.
4. Set balanced TTLs—not so low that query volume spikes, and not so high that record updates become difficult.
5. Test failover when an upstream resolver or VPN tunnel goes down.
6. Monitor resolution quality **from actual workload locations** rather than only from an admin machine.

### 12.3. Observability and Operations

Cloud DNS supports logging and monitoring within its feature set and scope. Combine:

- **Cloud DNS query logging** or logging suitable for private DNS and policies, taking sensitive data in queried names into account.
- **Cloud Monitoring** for supported DNS metrics, VPN/Interconnect, latency, error rates, and availability.
- **VPC Flow Logs/firewall logs** or network telemetry where enabled and aligned with the traffic path.
- **On-prem DNS logs** to confirm whether Cloud DNS queries from **35.199.192.0/19** reach the targets.
- **Synthetic tests** run periodically from a VM in the hub, a VM in the spoke, and an on-prem host; verify A/AAAA/CNAME or other required record types.

### 12.4. Cost

Cloud DNS may charge per **managed zone**, **query volume**, record/feature type, and logging according to current pricing. Cloud VPN/Interconnect connections, egress, and on-prem DNS infrastructure also carry separate costs. Forwarding DNS queries over hybrid links does not mean application data transferred afterward is free. Track budgets by project and service, and check current pricing before estimating.

## 13. Diagnostic Workflow When Hybrid DNS Fails

| Symptom | Possible Causes | Priority Checks |
|---|---|---|
| Hub VM resolves **corp.example.com** but spoke VM fails | Missing/wrong DNS peering zone, consumer network permission, regional forwarding limits | Consumer/producer zones, DNS suffix, region, and routes |
| Spoke VM can **`dig` on-prem directly**, but lookup via forwarding zone fails | Forwarding zone placed in wrong VPC / unsupported transitive path | Move forwarding zone to hub; create peering zone in spoke |
| On-prem queries for **gcp.example.com** time out | Inbound forwarding disabled, wrong entry point IP/region, missing route/ACL | DNS policy, `DNS_RESOLVER` IPs, Cloud VPN/Interconnect |
| Forwarding zone returns **SERVFAIL** | Target down, unroutable, DNS firewall blocking Cloud DNS source, wrong reply source IP | Target health, **35.199.192.0/19**, UDP/TCP 53, return routes |
| Queries via on-prem DNS return **NXDOMAIN** | Conditional forwarder wrong suffix or authoritative zone missing record | Check zone and records at the source |
| DNS name resolves, but application fails to connect | IP routing/firewall/TLS or application error | Forward/return routes, TCP ports, IAM, and service logs |
| After changing server policy, Compute Engine internal names stop resolving | Alternative name servers override private DNS | Review outbound DNS policy and name resolution order |
| Fails only from VMs in region B | Missing producer regional resource when dynamic routing is not global | Producer VPC, Cloud Router, and consumer VM region |
| Name works intermittently after changing A record | Cache/TTL, different resolvers across clients | TTL, per-resolver responses, forwarding logs |
| **403** error creating DNS peering zone | Missing permission on producer VPC or consumer project | **roles/dns.peer**, **roles/dns.admin**, exact principal |
| A name resolves differently between on-prem and VPC | Split-horizon, private zone override, suffix conflict | Compare outputs per resolver and zone associations |
| DNS client receives **REFUSED** | DNS ACL or upstream policy | Check request source, DNS server logs, IP allowlist |

### Step-by-Step Isolation

1. **Identify the origin:** Hub VM, spoke VM, GKE pod, Cloud Run service, or on-prem host? Each environment's DNS can differ.
2. **Query the active resolver directly** and record FQDN, record type, response code, TTL, and answer section.
3. **Identify the zone matching the suffix** and active policies on the VPC.
4. **If DNS peering:** check producer/consumer, regional conditions, and hop limits.
5. **If forwarding:** check DNS targets, **35.199.192.0/19** source, return routes, Cloud VPN/Interconnect, and UDP/TCP 53.
6. **If inbound:** check policy, exact regional entry point, conditional forwarder, on-prem routes/ACLs, and hybrid region.
7. **If DNS returns the right result:** shift investigation to IP connectivity, firewalls, the service, and application authentication.

Example of an easy comparison pair:

~~~bash
# Inside a Google Cloud VM, check per the VPC's DNS rules
dig @169.254.169.254 billing.corp.example.com. A

# From a VM with a direct route to on-prem DNS, verify the authoritative record
dig @172.16.100.10 billing.corp.example.com. A
~~~

Record **QUERY TIME, status, ANSWER, TTL, and SERVER** before and after changes. When multiple DNS targets exist, query each target directly to detect out-of-sync data.

## 14. Capstone Scenario: Java API, Database, and On-Prem ERP System

**Hoa Binh** company is gradually migrating services to Google Cloud:

- **Java/Spring API** running on Compute Engine in **vpc-app**.
- **Cloud Run** running an inventory worker, integrated with the VPC over an appropriate private network path.
- **Cloud SQL** storing order data on Google Cloud.
- **On-prem ERP** holding historical data and exposing **erp.corp.example.com.**
- **On-prem operations system** needing to call **orders.gcp.example.com.** over private connectivity.

The network team manages **vpc-hub**, Cloud VPN, and on-prem DNS; the application team manages only **vpc-app**.

### 14.1. Appropriate Design

~~~mermaid
flowchart LR
    APP["Java API / worker<br/>vpc-app"] -->|"DNS peering for corp.example.com."| HUB["Cloud DNS in vpc-hub"]
    HUB -->|"Forwarding zone"| ONDNS["On-prem DNS"]
    ONDNS -->|"erp.corp.example.com."| ERP["ERP private IP"]
    OPS["On-prem operations"] -->|"Conditional forwarding<br/>gcp.example.com."| IN["Cloud DNS inbound hub"]
    IN --> ZONE["Private zone<br/>gcp.example.com."]
    ZONE --> ORD["orders.gcp.example.com."]
~~~

The design consists of two independent DNS directions:

1. **GCP → on-prem:** spoke peering zone for **corp.example.com.**; hub forwarding zone to on-prem DNS.
2. **On-prem → GCP:** on-prem conditional forwarding for **gcp.example.com.** to hub inbound entry points; hub private zone stores records.

The IP paths for ERP data and the API must still be verified separately, such as routes/VPC connectivity, firewalls, IAM, and TLS.

### 14.2. Acceptance Criteria

| Test | Check Point | Expectation |
|---|---|---|
| Hub VM queries **erp.corp.example.com.** | Hub | Returns accurate on-prem A record |
| Spoke VM queries the same name | Spoke | Returns A record via producer hub |
| Spoke VM connects to ERP using returned IP | Spoke → on-prem | Valid route/firewall/port |
| On-prem queries **orders.gcp.example.com.** | Conditional forwarder | Returns A record from Cloud DNS private zone |
| On-prem connects to returned address | On-prem → Google Cloud | Routes and policies allow |
| Shut down one on-prem DNS server | Hub/spoke | Resolution still succeeds via remaining healthy DNS target under HA design |
| Inspect DNS request source at on-prem target | On-prem firewall/logs | Shows expected Cloud DNS source range |
| One region loses its hybrid link | Affected region | Understand expected degradation/failover behavior per design |
| Update DNS record | Both directions | Appropriate TTL/cache behavior; no premature conclusions before TTL expires |
| Audit IAM and logs | Hub/consumer | Zones and peering managed only by authorized teams |

### 14.3. Options to Consider

- If multiple service projects share a **Shared VPC**, you can attach a private zone directly to the host network and reduce the number of DNS peering zones.
- If you only want to expose **a single service** to another application, consider **Private Service Connect** and its corresponding DNS endpoint instead of exposing an entire subnet.
- If there are multiple data centers, evaluate where authoritative DNS lives, how records synchronize, failover strategies, and the risk of conditional forwarding loops.
- If applications use GKE or Cloud Run, verify the actual DNS resolver/networking context of each product; do not assume every container uses the same nameserver or egress path as a VM.

## 15. Practice Exercises

### Exercise A — Choose the Right Mechanism

Given these requirements:

1. A VM on Google Cloud wants to resolve **ldap.corp.example.com.** managed by on-prem DNS.
2. A VM in a spoke wants to use the hub's resolver to look up enterprise names.
3. An office server wants to resolve **db.gcp.example.com.** in a Cloud DNS private zone.
4. The infrastructure team wants to force all VPC DNS queries through a filtering enterprise resolver.
5. Two VPCs have VPC Network Peering, but VPC B's DNS cannot automatically resolve internal VM names from VPC A.

**Guidance:** (1) forwarding zone; (2) DNS peering zone; (3) inbound DNS server policy and on-prem conditional forwarding; (4) outbound server policy if the impact is well understood; (5) add DNS peering or an appropriate zone visibility model, because VPC Network Peering does not automatically share DNS.

### Exercise B — Find the Cause of SERVFAIL

In the hub, a VM running **dig @169.254.169.254 billing.corp.example.com.** receives **SERVFAIL**, whereas **dig @172.16.100.10 billing.corp.example.com.** returns an A record.

List at least five items to check. Hints: zone suffix, target config, source **35.199.192.0/19**, UDP/TCP 53, return route via the same VPC, source IP of reply packets, DNS target availability, and logs.

### Exercise C — DNS Transitivity Limits

There are three VPCs: A, B, and C. A creates a DNS peering zone pointing to B; B has a DNS peering zone pointing to C.

1. Can this work under Cloud DNS?
2. If you add D after C, can you chain A→B→C→D?
3. Does DNS returning the IP of a VM in C mean A can automatically connect to that VM?
4. Why can a DNS peering zone in A pointing to B's forwarding zone work, while a forwarding zone in A relying on a VPN path through B can fail?

**Guidance:** (1) Yes, DNS peering supports at most one intermediate hop; (2) No, exceeds the limit; (3) No, IP routing and firewalls are separate; (4) Cloud DNS forwarding does not support transitive IP routing to targets, whereas DNS peering delegates resolution to the producer that has direct hybrid connectivity.

### Exercise D — Write an Operations Runbook

Write a one-page runbook for **ERP name resolution down** covering: detection signals, test queries from hub/spoke, commands to inspect forwarding and peering zones, on-prem DNS logs, VPN/Cloud Router checks, the **35.199.192.0/19** source range, who approves DNS policy changes, and rollback steps. Distinguish between **DNS broken** and **DNS working but ERP API unreachable**.

## 16. Key Takeaways and References

**Six core takeaways:**

1. **Forwarding zones** send queries matching a DNS suffix to DNS targets; **private zones** hold records; **peering zones** let a consumer VPC look up names via a producer VPC's DNS.
2. **Inbound forwarding** lets on-prem systems query Cloud DNS via regional entry points; **outbound server policies** broadly alter a VPC's query path and must be evaluated carefully.
3. **DNS peering is different from VPC Network Peering**: IP peering is not required to query DNS; Cloud DNS peering supports up to one intermediate hop, whereas VPC Network Peering does not allow transitive IP routing.
4. For private forwarding targets, Cloud DNS uses source **35.199.192.0/19** under standard forwarding; on-prem DNS must allow **UDP/TCP 53** and have a **return route to the right VPC**.
5. **Working DNS does not equal successful application connectivity.** Check routes, firewalls, TLS/IAM, and listeners after verifying the IP is right.
6. DNS choices affect **security, reliability, caching, observability, and cost**; test from the hub, spoke, and on-prem.

**Official Google Cloud Documentation:**

1. [Cloud DNS overview](https://docs.cloud.google.com/dns/docs/overview) — private DNS, forwarding, and hybrid architecture.
2. [DNS zones overview](https://docs.cloud.google.com/dns/docs/zones/zones-overview) — forwarding zones, peering zones, transit limitations, and caching.
3. [Create a forwarding zone](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones) — gcloud syntax, target types, source 35.199.192.0/19, and return routes.
4. [Create a peering zone](https://docs.cloud.google.com/dns/docs/zones/peering-zones) — producer/consumer, gcloud, and roles/dns.peer.
5. [DNS server policies](https://docs.cloud.google.com/dns/docs/server-policies-overview) — inbound/outbound, DNS forwarding entry points, and resolution order.
6. [Configure DNS server policies](https://docs.cloud.google.com/dns/docs/policies) — creating inbound forwarding policies and finding DNS_RESOLVER addresses.
7. [Cloud DNS best practices](https://docs.cloud.google.com/dns/docs/best-practices) — hybrid DNS design, firewalls, BGP advertisement, and HA.
8. [Troubleshoot Cloud DNS](https://docs.cloud.google.com/dns/docs/troubleshooting) — diagnosing SERVFAIL, ACLs, forward targets, and return routes.
