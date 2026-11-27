# Troubleshooting DNS, BGP, and VPN Tunnel Failures on Google Cloud

> **Chapter:** DNS and Hybrid Connectivity  
> **Lesson:** Troubleshooting DNS, BGP, and VPN Tunnel Failures  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment scenarios, learners know how to select services, protect resources, automate releases, and monitor reliability and costs. Connecting an internal enterprise network (on-premises) to Google Cloud typically requires three components working simultaneously:

- **DNS:** translates application names like `orders.corp.example` into the appropriate IP address.
- **Cloud VPN/IPsec:** establishes an encrypted transport link between two networks.
- **Cloud Router/BGP:** exchanges IP prefixes so both networks know how to reach each other.

These three components are tightly coupled yet **do not substitute for one another**. A tunnel in `ESTABLISHED` state does not prove BGP has learned all routes; BGP `UP` does not prove DNS returns the right records; DNS resolving an IP does not guarantee firewalls and the application allow access.

This lesson builds a symptom-to-root-cause diagnostic methodology, prioritizing **observing and comparing configurations on both ends** before modifying the network. Addresses, domains, projects, and resource names in the examples are fictional for practice; replace them with approved real values in live environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the end-to-end path of an application request from DNS to VPN, BGP routing, firewalls, and the target service.
2. Distinguish **Cloud DNS private zones**, forwarding zones, inbound forwarding, VM resolvers, and on-premises DNS servers.
3. Use `dig`, `nslookup`, `getent`, and read-only `gcloud` commands to isolate DNS issues to the client, zone, forwarding, or return path.
4. Distinguish **IKE SA**, **IPsec/CHILD SA**, **VPN tunnel**, **BGP session**, and **learned/advertised routes** states.
5. Inspect HA VPN tunnels, HA gateway status, BGP peers, ASNs, BGP peering IPs, advertisements, and learned routes.
6. Recognize errors caused by overlapping IP ranges, asymmetric routing, route filters, ACLs/firewalls, MTU, and target services.
7. Establish an evidence-driven incident response process with rollback, alerting, and security for Compute Engine, GKE, Cloud Run, and Cloud SQL systems.

## 2. Hybrid Connectivity Model to Visualize First

Suppose an enterprise has an on-premises network `192.168.50.0/24`, and VPC `retail-vpc` on Google Cloud has subnets `10.30.10.0/24` and `10.30.20.0/24`. Both sides connect via **HA VPN** with two tunnels across both HA VPN gateway interfaces, and Cloud Router exchanges routes via BGP.

~~~mermaid
flowchart LR
    Client["On-prem ERP<br/>192.168.50.20"] --> DNSOn["On-prem DNS"]
    Client --> Peer["On-prem VPN Gateway<br/>IKE/IPsec + BGP"]
    DNSOn -. "Forwards internal domain" .-> Inbound["Cloud DNS inbound forwarding"]
    Peer == "Tunnel A / Tunnel B<br/>Encrypted IPsec" ==> VPN["HA VPN gateway on GCP"]
    VPN --> CR["Cloud Router<br/>BGP control plane"]
    VPN --> VPC["VPC retail-vpc<br/>10.30.0.0/16"]
    VPC --> LB["Internal Application Load Balancer"]
    LB --> Run["Cloud Run Orders API"]
    VPC --> DB["Private endpoint / Cloud SQL"]
    Inbound -. "DNS answer" .-> DNSOn
~~~

**What the diagram means:**

- **Data plane:** application packets traverse the VPN tunnels and Google Cloud's network routing to the target service's IP. **Cloud Router is not a packet-forwarding server** sitting between the VPN and VPC.
- **Control plane:** Cloud Router establishes BGP peers and manages learned/advertised routes; BGP session stability directly affects routing availability.
- **Name resolution:** DNS is a separate query path. For on-premises to query a Cloud DNS private zone, configure **inbound forwarding** properly; never send queries directly to the VM metadata server's DNS IP.
- **Application and security:** valid routes are not enough. Firewalls, load balancers, Cloud Run ingress, service-caller IAM/identity permissions, and database configuration must also be right.

**Cloud VPN** is a **site-to-site** IPsec service, not a client VPN for individual laptops to "dial in." **HA VPN** uses dynamic **BGP** routing; **Classic VPN** should only be considered for static/legacy setups within product capabilities. When investigating a legacy system, confirm whether the gateway is HA or Classic before applying Cloud Router procedures.

## 3. Layered Diagnostic Principles

Work from **verifiable evidence**, and avoid changing DNS, VPN, and BGP simultaneously since doing so erases diagnostic trails. Start with user symptoms, blast radius, and timeline.

~~~mermaid
flowchart TD
    A["App cannot reach hybrid service"] --> B{"Does DNS resolve to the right IP?"}
    B -->|No| D["Check resolver, zone, forwarding, ACLs, and DNS response"]
    B -->|Yes| C{"Is VPN tunnel ESTABLISHED?"}
    C -->|No| E["Check peer IP, UDP 500/4500, IKE, PSK, ciphers, CHILD SA"]
    C -->|Yes| F{"Is BGP session UP?"}
    F -->|No| G["Check tunnel-router binding, ASN, peer IP, BGP/BFD"]
    F -->|Yes| H{"Are forward + return routes right?"}
    H -->|No| I["Check route ads/learning, overlap, policies, mode, priority"]
    H -->|Yes| J["Check firewalls, ACLs, service, TLS, MTU, timeouts"]
    D --> K["Record evidence and re-test layer by layer"]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

In practice, **DNS and tunnels can be checked in parallel**: if DNS fails, test `dig` against on-premises DNS and directly on a GCP VM; if failures occur only across the hybrid path, VPN/routing/firewalls for DNS may be the culprit. The flowchart shows an **isolation order**, not an implication that DNS failures are always independent of the network.

### 3.1. Quick Symptom Matrix

| Symptom | First Suspected Layer | Confirmatory Observation |
|---|---|---|
| GCP VM resolves private names, on-premises host cannot | Inbound forwarding, on-prem resolver, VPN/route, or DNS ACL | Compare `dig` on both sides, inbound forwarding policy, and TCP/UDP 53 path |
| A domain returns `NXDOMAIN` | Zone/record/search domain or authoritative name server | `dig +noall +answer +comments` and record management |
| `SERVFAIL` or DNS timeout from one network | Forwarder, DNS target, ACL, return route, or DNSSEC/upstream | Query each resolver directly, Cloud DNS logs, and DNS server logs |
| VPN stuck in `FIRST HANDSHAKE` or `NO INCOMING PACKETS` | Peer IP, IKE, Internet path, UDP 500/4500 | Tunnel status, Cloud VPN logs, peer appliance logs |
| VPN `ESTABLISHED`, BGP `DOWN` | ASN, peer IP, BGP interface, BFD, tunnel/Cloud Router binding | `gcloud compute routers get-status` and peer logs |
| BGP `UP`, VPC missing on-prem route | Missing prefix advertisement, route policy, limit/overlap | Learned routes, effective routes, and peer routing table |
| Packets from GCP to on-prem work, reverse direction fails | Missing return route, ACL/stateful firewall, policy | Routing tables on both sides, logs, trace same flow from both sides |
| IP reachable yet hostname fails | DNS, search domain, split-horizon, or bad record | Compare `dig` against direct IP connection test |
| DNS right, VPN/BGP healthy, TCP times out | Firewall, listener, LB, port, MTU | `nc`, `curl`, VPC Flow Logs, backend health |
| Only large transfers hang | MTU, fragmentation/PMTUD, MSS | Check tunnel MTU, test small vs. large payloads |
| Intermittent failures when one tunnel drops | Incomplete HA, failover, BGP timers, backup path | Status of both tunnels and HA VPN gateway status |

## 4. Preflight: Identifying the Exact Project, Region, and Incident Scope

Before running diagnostics, gather:

| Attribute | Illustrative Example | Question |
|---|---|---|
| Project ID | `retail-network-prod` | Who owns the network? Shared VPC host or service project? |
| VPC / subnet / region | `retail-vpc` / `subnet-app` / `asia-southeast1` | Do routes and DNS policies target the right VPC? |
| VPN gateway / tunnel | `ha-vpn-sg` / `tunnel-to-hq-a` | HA VPN or Classic VPN? What state are both redundant paths in? |
| Cloud Router / BGP peer | `router-hybrid-sg` / `peer-hq-a` | What are the ASNs, peer addresses, and status? |
| On-premises gateway | Network team appliance | Who has access to share configs/logs from both ends? |
| Source / target | `192.168.50.20` → `10.30.20.10:443` | Can the failure be reproduced using the IP directly? |
| Domain / record type | `orders.corp.example` / `A` | Which resolver does the client use? What record is expected? |
| Incident timestamp | 14:10 UTC, since new deploy | Were DNS/VPN/BGP/firewalls changed around that time? |

Verify CLI identity and context:

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="yaml(projectId,name,projectNumber)"
~~~

These commands only read or view configuration and create no resources. In **Shared VPC** environments, networks, Cloud DNS policies, VPNs, and Cloud Routers may reside in the **host project**, while workloads reside in **service projects**; check the right resource location before assuming something does not exist.

### 4.1. Identifying What Changed

Ask operators:

- When did errors start? One workload or all on-premises systems?
- Does it affect one site, one subnet, one region, or both directions?
- Were **DNS zones, DNS policies, BGP advertisements, route priorities, firewalls/ACLs, IKE ciphers, pre-shared keys, or gateway firmware** recently changed?
- Did **Cloud Router maintenance, BGP flaps, IPsec rekeys, or failovers** coincide with the timestamp?
- Are internal GCP services still working while only the hybrid path fails?

Save authorized configuration snapshots and logs before making edits. Never paste pre-shared keys, tokens, or sensitive raw configs into public tickets.

## 5. Troubleshooting Cloud DNS: Start from the Resolver the Client Actually Uses

### 5.1. DNS Types to Distinguish

| Model | Meaning | Common Errors |
|---|---|---|
| **Public managed zone** | Public DNS queried from the Internet via DNS delegation | NS delegation, cache/TTL, records, DNSSEC |
| **Private managed zone** | DNS queryable only within authorized VPCs and valid access paths | Wrong authorized network, missing zone/record |
| **Forwarding zone** | Cloud DNS forwards queries for a defined suffix to DNS targets | Broken forwarding target, return route/ACL, suffix mismatch |
| **Peering zone** | Cloud DNS forwards queries via supported DNS peering links | Wrong consumer/producer VPC, region availability, zone conflicts |
| **Inbound server policy** | Lets systems outside the VPC query Cloud DNS private resolution via forwarding entry points | Inbound forwarding disabled, endpoint in wrong region/VPC, route/ACL |
| **Outbound server policy** | Redirects VPC queries to alternative resolvers per supported config | Wrong target, forwarding loop, missing return route |

Private managed zones attach to **authorized VPC networks**, not every project by default. Cloud DNS selects zones by domain/policy rules; if multiple DNS zones and forwarding zones share overlapping suffixes, check **name resolution order and longest suffix match** in the docs instead of guessing.

### 5.2. Checking on the Source Host

On Linux, inspect resolver configuration first:

~~~bash
cat /etc/resolv.conf
getent hosts orders.corp.example
dig orders.corp.example A
dig orders.corp.example AAAA
dig orders.corp.example A +noall +answer +comments
~~~

- `getent hosts` uses the OS resolution chain (which may include `/etc/hosts`, NSS, caching); useful to compare against a pure DNS lookup.
- `dig` queries DNS per default resolver settings, showing response code, record type, and TTL.
- `A` is IPv4, `AAAA` is IPv6. If an app prefers IPv6 while the hybrid network lacks IPv6 support, connections may behave unexpectedly.
- If `/etc/resolv.conf` points to a local stub resolver (such as `127.0.0.53`), inspect the real DNS configuration in `systemd-resolved` or the active network manager.

Query **a specific DNS server**:

~~~bash
dig @192.168.50.53 orders.corp.example A
dig @192.168.50.54 orders.corp.example A
dig @192.168.50.53 orders.corp.example A +tcp
~~~

Two on-premises DNS servers returning different answers can indicate zone config drift, split-horizon, cache/TTL, or replication lag. Try `+tcp` to detect broken TCP/53 when UDP/53 works. Avoid concluding from a single query because caching can mask errors.

### 5.3. Interpreting DNS Response Codes

| Result | Basic Meaning | Investigation Direction |
|---|---|---|
| `NOERROR` with expected record | DNS resolver answered properly | Proceed to IP/port test; still check TTL |
| `NOERROR` without requested A/AAAA | Name may exist without that record type, or valid empty answer | Check record type, CNAME, zone, and policy |
| `NXDOMAIN` | Resolver concludes the queried name does not exist in this context | Check suffix, zone/record, authorized VPC, conditional forwarder |
| `SERVFAIL` | Resolver failed to resolve | Check upstream, DNSSEC/delegation, forwarding, logs, and ACLs |
| Timeout | Client received no reply in time | UDP/TCP 53 path, firewalls, routes, resolver availability |
| Wrong IP returned | Stale record, wrong DNS zone, cache, or split-horizon | Query each DNS server, check TTL, zone/forwarding config |

**A successful `ping` to a domain name does not prove DNS records are optimal**, nor does a failed `ping` prove DNS is broken: ICMP may be blocked. Use `dig` to test resolution, then use tools targeting the application's **exact protocol/port**.

### 5.4. Google Cloud VM Resolves, On-Premises Cannot

For a Cloud DNS private zone, machines in an authorized VPC normally use Google Cloud's resolver path. On-premises hosts **do not automatically** share that private DNS path. You must enable **Cloud DNS inbound forwarding** on the appropriate VPC and configure on-premises DNS to forward specific suffixes to the allocated forwarding addresses.

Check sequence:

1. In **Cloud DNS → Zones**, verify the private zone, DNS name, A/AAAA/CNAME records, and **authorized networks**.
2. From a **GCP VM in an authorized VPC**, query the target name; note the actual DNS server the VM uses.
3. In **Cloud DNS → DNS policies**, verify **inbound forwarding** is enabled for the right VPC.
4. Locate the forwarding entry-point IP created by Google Cloud in the right subnet/region; never use a Cloud Router/BGP IP as a DNS server.
5. On on-premises DNS, configure conditional forwarding for the **exact suffix** pointing to the inbound forwarding IPs.
6. Check VPN/Interconnect paths, routes, and **both TCP and UDP port 53** ACLs/firewalls between on-premises and the forwarding entry point.
7. Query directly from on-premises with `dig @FORWARDING_IP orders.corp.example A`, then query via on-premises DNS to isolate the forwarder config.
8. Inspect on-premises resolver logs and Cloud DNS query logging (if enabled).

To list DNS server policies in an authorized project:

~~~bash
gcloud dns policies list --project=PROJECT_ID
gcloud dns managed-zones list --project=PROJECT_ID
~~~

To find Cloud DNS inbound forwarding IPs (with view permissions):

~~~bash
gcloud compute addresses list --project=PROJECT_ID --filter="purpose=DNS_RESOLVER" --format="table(name,address,subnetwork,region)"
~~~

If the expected address is missing, verify the project, VPC, subnet, and inbound forwarding policy before making changes.

### 5.5. Google Cloud Cannot Resolve On-Premises Domains

When VPC workloads need to resolve `erp.corp.example` managed by on-premises DNS, the typical model is a **Cloud DNS forwarding zone** pointing to on-premises DNS targets. Failures may lie in:

- Forwarding zone suffix not matching the queried name.
- Wrong DNS target IP, unresponsive target, or blocking ACL.
- Route to DNS target not traversing the right VPN/Interconnect path.
- Missing **return path** from on-premises back to Cloud DNS forwarding's source range.
- DNS target replying from a **different IP** than the configured forwarding target IP, causing responses to be rejected.
- Forwarding loop: Cloud DNS → on-premises DNS → Cloud DNS for the same suffix.

**Forwarding targets over VPN/Interconnect using default source behavior:** Cloud DNS may send queries from the `35.199.192.0/19` proxy range. On-premises must allow **TCP/UDP 53** DNS queries from this range to the server and have a **return route to `35.199.192.0/19` back to the same VPC** over the hybrid link. This is the DNS forwarding service source range—**not a subnet range to assign to VMs**. With newer outbound endpoint modes, source IPs and route requirements can differ; verify which configuration type is active.

Check both ends:

~~~bash
# From a VM in an authorized VPC:
dig erp.corp.example A

# On the on-premises DNS server (if authorized):
# inspect access logs or scoped TCP/UDP 53 captures per operations procedure.
~~~

Do not blindly add `35.199.192.0/19` routes to every VPC or open network-wide ACLs without confirming this is the active model. Route or firewall changes require network owner review to avoid service disruption.

### 5.6. Cloud DNS Logging and Caching

Enable **DNS query logging** within supported scope per organizational policy to analyze queried names, timestamps, and responses. Logs can expose internal service names and metadata, so restrict view permissions and retention. If applications cache in clients, proxies, or intermediate DNS servers, updating a Cloud DNS record may not take effect until caches expire their TTL. Avoid changing TTLs or deleting records experimentally before identifying which resolver is answering.

## 6. Troubleshooting Cloud VPN: Is the Tunnel Truly Established?

### 6.1. Three Distinct State Layers

| Layer | Components | What to Observe |
|---|---|---|
| **IKE** | IKE SA / Phase 1 | Is the peer responding? Are IKE version, pre-shared key/auth, and ciphers compatible? |
| **IPsec** | CHILD SA / Phase 2 and tunnel | Are SA/traffic selectors, rekeying, encryption, and ingress/egress data stable? |
| **Routing** | Cloud Router/BGP or static routes | Are remote prefixes and return routes ready? |

For **HA VPN**, routes are exchanged over BGP. **Tunnel `ESTABLISHED` is required to carry traffic**, yet routes, firewalls, and the application must still be checked. For **Classic VPN** using static routing, do not apply "BGP must be UP" as a criterion.

### 6.2. Checking Status in Google Cloud Console

1. Open **Hybrid Connectivity / VPN** (or the **VPN** page) and select the right project and region.
2. Open **Cloud VPN gateways / VPN tunnels** and select the affected tunnel.
3. Record the status, error start time, and detailed status message.
4. For **HA VPN**, inspect **both interfaces/tunnels**, the peer gateway, and high-availability status.
5. Cross-check against the on-premises VPN appliance status table.

Common states:

| Status | Interpretation | Next Step |
|---|---|---|
| `ESTABLISHED` | Tunnel is established and active at the VPN layer | Proceed to BGP, routes, and traffic tests |
| `FIRST HANDSHAKE` | Negotiating IKE, possibly retrying repeatedly | Check reachability to peer and IKE settings |
| `NO INCOMING PACKETS` | No packets received from the VPN peer | Check peer IP, Internet path, NAT, and peer device |
| `AUTHORIZATION ERROR` | Failure during authentication/negotiation | Verify shared secret and auth settings on both ends |
| `NEGOTIATION FAILURE` | Tunnel negotiation or proposal rejected | Check tunnel details, IKE/cipher logs, and supported policies |
| `WAITING FOR FULL CONFIG` | Incomplete configuration to establish tunnel | Check tunnel/route/Cloud Router bindings |
| `STOPPED` or closed state | Tunnel inactive | Check configuration or deleted/modified dependencies |

Exact status names/details can vary across API, Console, and logs by version; never guess the root cause from icon color alone.

### 6.3. Read-Only gcloud Commands

~~~bash
# List VPN tunnels in authorized project and regions.
gcloud compute vpn-tunnels list --project=PROJECT_ID

# Describe configuration and status of a specific tunnel.
gcloud compute vpn-tunnels describe TUNNEL_NAME --project=PROJECT_ID --region=REGION

# Inspect HA VPN gateway status and redundancy setup.
gcloud compute vpn-gateways get-status HA_GATEWAY_NAME --project=PROJECT_ID --region=REGION
~~~

If `get-status` does not apply to a resource, check whether it is an **HA VPN gateway** or a Classic VPN gateway. Replace placeholder tunnel/gateway names with real names. Read commands require IAM view permissions; `PERMISSION_DENIED` does not mean the tunnel is gone.

### 6.4. IKE/IPsec Errors: Comparing Both Ends

| Scenario | What to Verify |
|---|---|
| No packets from peer | Peer public IP, one-to-one NAT if used, Internet path, ACLs/NAT/firewalls, and peer device |
| IKE SA fails to form | IKE version, pre-shared key, supported proposals/ciphers, auth, matching ID/mode |
| IKE up yet CHILD SA unstable | VPN-type traffic selectors, crypto proposals, PFS/DH group, lifetimes, and rekeying |
| Tunnel drops periodically | Rekey/`SA_DELETE` logs, lifetime mismatch, ISP/peer stability, BGP/BFD flaps |
| Large connections hang | MTU/MSS, fragmentation, PMTUD, firewalls blocking required ICMP |
| Only one tunnel works | Second interface state, peer gateway, advertised routes, SLA compliance |
| BGP peer stays DOWN after tunnel is UP | Cloud Router/peer IP/ASN config, interface binding, BGP timers, and BFD |

Cloud VPN uses IPsec; paths to public VPN addresses typically require **UDP 500**, **UDP 4500** (NAT Traversal), and **ESP** depending on peer/firewall topology. For appliances behind NAT, verify **one-to-one NAT** restrictions; never assume multiple gateways can share one public IP via port NAT.

**Never paste pre-shared keys into diagnostic commands, shared logs, or public support requests.** Verify secrets through approved secrets channels. For `no-proposal-chosen` errors, verify intersecting cipher/proposal sets on both sides—never disable encryption just to "get it working."

### 6.5. Viewing IPsec Logs in Cloud Logging

In **Logging → Logs Explorer**, scope to the right project and incident window. Sample filter for VPN logs:

~~~text
resource.type="vpn_gateway"
("initiating IKE_SA" OR "generating IKE_SA_INIT request")
~~~

Filter for unresponsive peer:

~~~text
resource.type="vpn_gateway"
"establishing IKE_SA failed, peer not responding"
~~~

Search for `IKE_SA`, `CHILD_SA`, and `SA_DELETE` events to pinpoint handshake errors, rekeys, or tunnel resets. Log availability depends on service logging and permissions. Record **timestamps, tunnels, peers, and error types** without copying secrets.

## 7. Troubleshooting BGP and Cloud Router: Tunnel Is Up, Yet No Path Exists

### 7.1. What Does Cloud Router Do?

**Cloud Router** is the BGP control plane managing dynamic routes learned/advertised over VPN or Cloud Interconnect. It **does not sit on the data plane** to receive, encrypt, or forward individual packets from VMs. In HA VPN, BGP sessions attach to Cloud Router interfaces linked to tunnels, typically using **link-local** peering addresses per supported configuration.

BGP can be `UP` while applications still cannot reach destinations when:

- The peer fails to advertise required prefixes, or Cloud Router drops/ignores them due to policies/limits.
- Effective routing picks another next hop due to priority, route type, or prefix specificity.
- On-premises lacks a **return route** to Google Cloud subnets.
- IP ranges overlap, firewalls block, peer ACLs block, or the app is not listening.
- BGP advertises routes to a region different from where traffic actually originates per design.

### 7.2. Inspecting Peer Configuration and Status

~~~bash
# Cloud Router config: ASN, interfaces, and bgpPeers.
gcloud compute routers describe ROUTER_NAME --project=PROJECT_ID --region=REGION

# Live status: BGP session status, learned and advertised routes.
gcloud compute routers get-status ROUTER_NAME --project=PROJECT_ID --region=REGION

# List Cloud Routers in the project.
gcloud compute routers list --project=PROJECT_ID
~~~

Key fields to read:

| Field / Info | Interpretation | Diagnostic Question |
|---|---|---|
| `bgp.asn` | Cloud Router's ASN | Does it collide improperly with peer ASN? |
| `bgpPeers[].peerAsn` | Configured peer ASN | Does it match the actual ASN on the on-premises device? |
| `bgpPeers[].ipAddress` | Cloud Router's local BGP peering IP | Is the on-prem peer configured with this IP as remote neighbor? |
| `bgpPeers[].peerIpAddress` | Peer-side BGP IP | Does it match the local IP on the peer router? |
| `interfaces[].linkedVpnTunnel` | Cloud Router interface bound to VPN tunnel | Does it point to the right tunnel in the same region? |
| BGP peer `status/state/statusReason` | API-reported session status/reason | Is session `UP` or `DOWN`, and why? |
| `bestRoutes` / learned routes | Prefixes learned from peer and selected routes | Is `192.168.50.0/24` present? |
| Advertised routes | Prefixes Cloud Router advertises to peer | Are `10.30.10.0/24` / `10.30.20.0/24` advertised? |

**Both ASN and peering IPs must match on both ends.** BGP peering addresses are not DNS servers, service IPs, or default routes for VMs. Never change ASNs or peering IP ranges without cross-checking the peer's configuration.

### 7.3. BGP Is DOWN Even Though VPN Is ESTABLISHED

Check sequence:

1. Is the tunnel truly `ESTABLISHED` and bound to the expected Cloud Router interface?
2. Are Cloud Router and the tunnel in the same region and right VPC?
3. Is the BGP peer `disabled` or showing an error state in `get-status`?
4. Do local/peer peering IPs and ASNs match on both ends without conflicts?
5. Does the on-premises device have the BGP neighbor on the right tunnel, right ASN, session, and authentication (if used)?
6. Is an on-prem device policy blocking **BGP TCP/179 inside the tunnel**? Never open TCP/179 from the public Internet to the public VPN gateway.
7. If **Bidirectional Forwarding Detection (BFD)** is enabled, are status and timers valid on both sides?
8. Inspect Cloud Router logs, on-premises logs, and maintenance/rekey timelines for resets or flaps.

Cloud Router may briefly reset sessions during background maintenance/migrations; a single BGP flap does not prove the gateway is broken. Check frequency, **graceful restart**, hold timers, and real traffic impact. If a peer advertises too many prefixes, Cloud Router can drop the session per active limits; check logs and limit documentation rather than assuming a quota increase fixes everything.

### 7.4. BGP Is UP Yet Routes Are Missing

Check both directions simultaneously:

~~~text
Google Cloud:
  Remote prefix to learn from on-prem: 192.168.50.0/24
  Expected local prefixes to advertise: 10.30.10.0/24, 10.30.20.0/24

On-premises:
  Receive Google Cloud prefixes: 10.30.10.0/24, 10.30.20.0/24
  Advertise on-prem prefix:      192.168.50.0/24
~~~

Items to verify:

- **BGP advertisements:** is Cloud Router using default or custom mode? Are subnets in other regions missing when the VPC is in **regional dynamic routing mode** vs. needing **global dynamic routing mode**?
- **BGP route policies/filters** on Cloud Router or on-premises: are prefixes dropped, re-prioritized, or modified?
- **Cloud Router learned routes and VPC effective routes:** are learned routes actually installed in the VPC and chosen by route selection rules?
- **Route priority/MED and prefix length:** is another tunnel or next hop winning unexpectedly?
- **CIDR overlap:** on-prem ranges overlapping GCP subnets or other routes; longest-prefix match or route type can misdirect traffic.
- **Return path:** do remote routers/firewalls have a return path to GCP prefixes?
- **VPC Peering is not transitive by default:** never assume VPN in VPC A automatically routes peered VPC B through A without supported mechanisms and policies.

**Example:** Cloud Router receives `192.168.50.0/24` from the peer, yet VMs can only reach `192.168.60.10`? Check whether DNS records point to the wrong subnet, or whether the peer forgot to advertise `192.168.60.0/24`. Never tweak firewalls when the routing table proves no route exists to the destination.

## 8. Troubleshooting the Data Plane Once DNS, Tunnels, and BGP Are Healthy

### 8.1. Testing by IP and Exact Port

~~~bash
# From an authorized test VM, check DNS.
dig orders.corp.example A +noall +answer

# Test TCP to the expected IP/port; run only if tools are installed.
nc -vz -w 5 10.30.20.10 443

# Check HTTP/TLS using the right hostname.
curl -v --connect-timeout 5 https://orders.corp.example/health
~~~

**Note:** `curl -k` skips certificate verification and should never become a default fix. If certificates fail, inspect SANs, hostname, chain, and system time. Testing by IP isolates routing, yet HTTPS still needs proper **SNI/Host**; hitting an IP directly can trigger TLS errors even when the network works.

### 8.2. Firewalls and Bidirectional Routes

| Checkpoint | Question |
|---|---|
| VPC firewall ingress | Permits on-prem source `192.168.50.0/24` to target port 443? |
| VPC firewall egress | Do rules/policies restrict outbound or reply paths? |
| On-prem firewall/ACL | Permits source/destination and stateful return traffic? |
| OS firewall/listener | Is the service listening on the exact IP/port? |
| Cloud Load Balancer | Are frontend, forwarding rule, backend health, and policies working? |
| Cloud Run | Are ingress, authentication, and service URL/Load Balancer integration right? |
| Cloud SQL | Are private connection, IP/network, DB user, and connection permissions right? |
| Route/priority | Is forward/return traffic balanced or asymmetric across two tunnels? |
| MTU/MSS | IPsec reduces usable MTU; are large packets hanging or dropping? |

**VPC Flow Logs** help observe traffic for supported subnets or resource types, but use sampling and do not replace peer packet captures. **Firewall Rules Logging** must also be enabled on the relevant rules; absence of logs **does not** always prove zero packets arrived.

### 8.3. Network Intelligence Center / Connectivity Tests

**Connectivity Tests** can trace paths using Google Cloud topology and configuration, surfacing many route/firewall errors. For hybrid paths and components outside Google Cloud's control, simulated results **cannot confirm all on-premises appliance behavior**. Combine with peer logs/tables and safe live traffic tests.

### 8.4. MTU and Rekeying

IPsec adds packet overhead, so usable MTU differs from plain Ethernet. MTU issues typically show up as:

- Small DNS queries succeed while large queries or TCP/HTTPS time out.
- TCP handshake completes yet bulk data transfer hangs.
- One tunnel performs well while failover to the other tunnel degrades.

Check **path MTU**, **TCP MSS clamping**, and fragmentation handling per peer hardware and Cloud VPN documentation. Never try to "fix" this by disabling all firewalls or permitting unrestricted traffic. Also watch **CHILD_SA rekey** logs when brief outages repeat periodically.

## 9. Practice Scenario A: On-Premises Cannot Resolve Private DNS

**Assumed architecture:** an ERP app in `192.168.50.0/24` needs to call `orders.corp.example`. The name resides in a **Cloud DNS private managed zone** pointing to an internal Application Load Balancer in Google Cloud at frontend `10.30.20.10`, backed by the Cloud Run Orders API.

**Symptom:** VMs in the VPC resolve the record, while on-premises ERP gets a DNS timeout; connecting directly to IP `10.30.20.10:443` from an on-premises test host succeeds.

### Step 1 — Capture Evidence

~~~bash
# On a VM inside the Google Cloud VPC.
dig orders.corp.example A +noall +answer

# On an on-premises host.
dig @192.168.50.53 orders.corp.example A +noall +answer +comments

# If the DNS inbound forwarding IP is already known:
dig @FORWARDING_IP orders.corp.example A +noall +answer +comments
~~~

**Interpretation:** GCP returns `10.30.20.10`, while on-premises times out. Working IP TCP confirms a data-plane path to the frontend, so focus on the **DNS forwarding** path instead of changing BGP indiscriminately.

### Step 2 — Isolate

1. Does on-premises DNS have a conditional forwarder for `corp.example`?
2. Is inbound forwarding enabled on the right VPC with an appropriate forwarding IP?
3. Does on-premises have routes and ACLs for UDP/TCP 53 to the forwarding IP?
4. Does the Cloud DNS private zone authorize the VPC used by the forwarding policy?
5. If querying the forwarding IP directly succeeds while querying `192.168.50.53` fails, inspect the on-premises DNS server and forwarder rule.
6. If both queries from on-premises fail, check VPN/routes/ACLs to the forwarding IP, then logs on both sides.

### Step 3 — Verify After Fixing

Re-test from multiple clients sharing the DNS policy; test A/AAAA if the app uses IPv4/IPv6, check TTL, and run `curl` against the hostname. Document the change, timestamp, outcome, and API connectivity impact. **Never delete the private zone or make the service public** just to avoid troubleshooting DNS.

## 10. Practice Scenario B: VPN Is Up, Yet BGP Does Not Learn Routes

**Assumed architecture:** two HA VPN tunnels connect to two interfaces on a peer gateway. Tunnel A is `ESTABLISHED` and tunnel B is `ESTABLISHED`. Yet VM `10.30.10.20` cannot reach host `192.168.50.20` at headquarters.

### Step 1 — Inspect HA VPN and Cloud Router

~~~bash
gcloud compute vpn-tunnels describe TUNNEL_A --project=PROJECT_ID --region=REGION
gcloud compute vpn-tunnels describe TUNNEL_B --project=PROJECT_ID --region=REGION
gcloud compute vpn-gateways get-status HA_GATEWAY_NAME --project=PROJECT_ID --region=REGION
gcloud compute routers get-status ROUTER_NAME --project=PROJECT_ID --region=REGION
~~~

**Assumed output:** BGP session A is `UP`, BGP session B is `DOWN`. Router A learns `192.168.60.0/24` but not `192.168.50.0/24`. The peer has a prefix filter exporting only `192.168.60.0/24`.

### Step 2 — Separate the Two Issues

- **Target route issue:** even BGP A being `UP` is insufficient if `192.168.50.0/24` is not advertised and installed in the VPC.
- **Availability issue:** BGP B being `DOWN` breaks intended path redundancy; separately investigate ASN, peering IP, peer status, tunnel binding, and BFD.

### Step 3 — Coordinate Fixes on the Right Sides

The on-premises team updates the prefix filter and advertises the required range per approved policy; the GCP team verifies learned/effective routes. At the same time, diagnose and restore BGP B per both configs. Then test **bidirectionally**, verify on-prem's route to `10.30.10.0/24`, test failover, and close only when both connectivity and redundancy meet goals.

**Never** inject a default route `0.0.0.0/0` or open `0.0.0.0/0` in firewalls when the target is strictly `192.168.50.0/24`.

## 11. Practice Scenario C: Tunnel Flapping or Periodic Performance Drops

**Symptom:** every few dozen minutes or at recurring intervals, bulk transfers drop for 10–30 seconds and then recover. Dashboards show IKE/CHILD SA rekeys coinciding with BGP session resets.

Procedure:

1. Build a 24-hour timeline from Cloud VPN logs, Cloud Router logs, and peer devices, normalized to UTC.
2. Check for `SA_DELETE`, cipher mismatches, lifetime mismatches, NAT timeouts, gateway switches, or maintenance at the exact timestamps.
3. Verify compatible IKE/IPsec parameters on both sides; during rekey, the peer should support establishing the new SA before the old SA expires per device behavior.
4. Check BGP graceful restart, hold timers, BFD, and failover policies; note that Cloud Router can experience brief control-plane restarts during maintenance **without necessarily dropping traffic** if recovery works properly.
5. Measure packet loss and throughput per tunnel; inspect MTU/MSS and peer CPU/crypto capacity.
6. When making changes, modify **one tunnel at a time** while keeping the backup path live within a change window; roll back if metrics worsen.
7. Verify post-fix: fewer resets, acceptable latency/packet loss, and uninterrupted app behavior across a full rekey cycle.

A single reset log entry does not prove Google Cloud is faulty; correlate both ends and traffic telemetry to establish true impact.

## 12. Monitoring, Alerting, and Operations Runbooks

### 12.1. Signals to Track

| Signal Group | Metrics or Events | Action |
|---|---|---|
| VPN | Per-tunnel status, ingress/egress packets, dropped packets, failed handshakes | Alert if a tunnel drops or traffic plunges abnormally |
| HA | Both interfaces/tunnels and HA gateway status | Evaluate failover readiness, not just "one tunnel UP" |
| BGP | Session status, learned/advertised prefix changes, flaps/restarts | Inspect routes, peering, and peer device |
| DNS | `SERVFAIL`/timeout rate, forwarding targets, query latency | Investigate resolvers/forwarders/return routes |
| VPC | Firewall denies, flow logs, unusual egress/ingress | Isolate policies, routes, or targets |
| Application | p95/p99 latency, HTTP 5xx, database connection errors | Tie network health to user experience |
| Cost | Tunnel/VPN traffic, logging, egress, Monitoring | Set budgets/alerts; balance log retention |

Set severity-tiered alerts—for example, "both critical tunnels down," "one tunnel down reducing redundancy," "critical BGP route missing," and "DNS timeouts above threshold." Each alert needs an **assigned owner, on-premises contact, and runbook**.

### 12.2. Incident Record Template

~~~text
Incident ID:
Start time (UTC) / Time zone:
Reporter / Impact severity:
Project / VPC / Region:
Cloud DNS zone + authorized VPC:
On-prem resolver / Cloud DNS forwarding:
Source IP:port / Destination FQDN, IP:port:
Tunnel A / Tunnel B status:
Cloud Router and BGP peer status:
Learned routes / advertised routes:
dig / getent / nc / curl results:
Firewall / ACL / LB / application state:
Recent changes / log timestamps:
Hypotheses and evidence:
Approved change / rollback plan:
Bidirectional and failover test results:
Owner / Preventive actions:
~~~

### 12.3. Phased Incident Response Workflow

1. **Assess impact:** classify as isolated DNS issue, route loss, redundancy loss, or total outage.
2. **Restore safely:** if a pre-designed backup path exists, follow the runbook and approvals; avoid sweeping changes.
3. **Preserve evidence:** configs, learned routes, tunnel state, IKE/BGP logs, DNS responses, and app test results.
4. **Isolate the right layer:** use the symptom matrix; avoid random trials or "open all ports."
5. **Apply approved changes:** one variable at a time; log timestamps and before/after diffs with rollback ready.
6. **Verify live:** DNS accurate on both sides, bidirectional BGP routes valid, app traffic and failover working.
7. **Post-incident review:** explain root cause from evidence, add alerts, and document preventive actions.

## 13. Common Mistakes

| Mistake | Why It Is Wrong | Right Practice |
|---|---|---|
| "Green tunnel means apps definitely work" | Does not prove BGP routes, firewalls, DNS, or backend health | Check each layer and both directions |
| "BGP UP means every on-prem subnet is learned" | Prefix filters, advertisements, or route selection can exclude prefixes | Inspect learned/advertised/effective routes |
| Using BGP peering IP as a DNS server | BGP IPs do not serve DNS | Use supported resolvers or forwarding entry points |
| Having on-prem query private zones without inbound forwarding | Private zones are scoped to VPC boundaries | Configure DNS inbound forwarding |
| Opening only UDP 53 | DNS can require TCP 53 | Check both TCP/UDP 53 across networks and resolvers |
| Forgetting return route to `35.199.192.0/19` for default on-prem forwarding targets | DNS server receives queries yet replies over the wrong path | Check bidirectional routes/ACLs and outbound endpoint type |
| Tweaking all VM firewalls while IKE tunnel is DOWN | Wrong layer | Fix peer/IKE connectivity first |
| Opening TCP/179 to the Internet to "fix BGP" | HA VPN BGP runs inside the hybrid context; exposing it increases risk | Check BGP inside the tunnel and relevant ACLs |
| Changing ASN or peer IP without syncing both ends | Can sever the entire connection | Reconcile Cloud Router and on-prem router configs |
| Deleting a route experimentally during production | Can drop paths or cause asymmetric traffic | Test in sandbox, maintenance window, with rollback |
| Using `ping` as the sole pass/fail test | ICMP can be blocked while DNS/TCP work independently | Use `dig` + test actual protocol/port |
| Lumping all errors into "VPN is slow" | DNS timeouts, MTU, BGP flaps, and peer CPU have distinct signatures | Correlate logs/metrics along a timeline |
| Monitoring only tunnel A | Misses a broken backup path | Monitor both tunnels and HA topology |
| Gathering logs using an Owner account | Over-privileged and higher risk | Grant read-only roles and protect log data |

## 14. Self-Assessment Exercises

### Exercise 1 — DNS

VM `10.30.10.20` in the VPC queries `erp.corp.example` through a forwarding zone and times out. On-prem DNS server `192.168.50.53` logs the request from source IP `35.199.194.10`, yet sends the reply toward its Internet default gateway. Tunnels are `ESTABLISHED` and BGP is `UP`.

**Question:** Which layer is suspect? Which route must be checked on-premises? Why shouldn't you edit CNAME/A records first?

**Hint:** The return path for default Cloud DNS forwarding targets back to `35.199.192.0/19` is not returning to the VPC along the right path; since the DNS server already received the query, records are not the strongest hypothesis. Check the active outbound forwarding type before adding routes.

### Exercise 2 — VPN

The tunnel reports `NO INCOMING PACKETS`, and the peer appliance has no IKE logs from the HA VPN gateway address. Cloud Router BGP is also `DOWN`.

**Question:** What is the ordered check sequence? Should you change the BGP ASN immediately?

**Hint:** Check peer IP, Internet path, NAT, ACLs / UDP 500/4500/ESP, and appliance health first; without a working tunnel, there is no evidence justifying an ASN change.

### Exercise 3 — BGP

The HA VPN tunnel is `ESTABLISHED` and BGP is `UP`. Cloud Router learns `192.168.60.0/24`; the application needs `192.168.50.20`.

**Question:** Why is the destination still unreachable with BGP UP? What must both ends check?

**Hint:** There is no learned/effective route for `192.168.50.0/24`; inspect prefix advertisements/filters, route selection, and the return path.

### Exercise 4 — Application

`dig orders.corp.example A` returns `10.30.20.10` on both ends. Both HA VPN tunnels are `ESTABLISHED` and BGP has learned all routes. `curl` times out, yet `nc` connects to `10.30.20.10:443`.

**Question:** Which failures remain possible? Why doesn't a successful `nc` confirm application health?

**Hint:** TCP handshake can complete while TLS/SNI, HTTP routing, backend health, app logic, authentication, or large-payload MTU still fail. Inspect `curl -v`, LB, and backend logs.

### Exercise 5 — Loss of Redundancy

One of two HA VPN tunnels fails after a peer upgrade while the other passes traffic normally.

**Question:** Can this be considered "everything is fine"? What must be done before claiming SLA and fault tolerance?

**Hint:** Traffic may not be disrupted yet, but redundancy is degraded. Check topology, HA gateway status, BGP/routes on both paths, failover capability, and specific SLA criteria.

## 15. End-of-Lesson Diagnostic Checklist

- [ ] Identified project, VPC, region, subnet, source/destination, DNS name, and incident timestamp.
- [ ] Separated DNS resolution from IP/TCP connectivity and application permissions.
- [ ] Compared `dig` from VPC and on-premises; checked resolvers, records, zones, and forwarding policies.
- [ ] Verified inbound or outbound Cloud DNS forwarding per model, TCP/UDP 53, and return routes.
- [ ] Verified status of **every** VPN tunnel along with peer IPs, IKE/IPsec, and rekey logs.
- [ ] Verified HA topology rather than checking only one green tunnel.
- [ ] Checked Cloud Router `describe` and `get-status`: ASNs, peering IPs, interfaces, and BGP state.
- [ ] Verified learned routes, advertised routes, effective routes, and return paths on both sides.
- [ ] Ruled out CIDR overlaps, firewalls/ACLs, LB/backend issues, service listeners, and MTU.
- [ ] Protected shared secrets, sensitive routing details, and log access permissions.
- [ ] Tested post-fix using the exact hostname/IP/port in both directions and across backup paths.
- [ ] Documented evidence, owner, rollback plan, and monitoring/preventive actions.

## 16. Official Google Cloud Documentation

The documentation below presents states, CLI syntax, and product scope that can change by version. Verify the relevant sections before modifying live environments:

- [Troubleshoot Cloud DNS](https://docs.cloud.google.com/dns/docs/troubleshooting)
- [Create a Cloud DNS forwarding zone](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones)
- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Check Cloud VPN status](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/checking-vpn-status)
- [Cloud VPN troubleshooting](https://docs.cloud.google.com/network-connectivity/docs/vpn/support/troubleshooting)
- [Troubleshoot BGP sessions](https://docs.cloud.google.com/network-connectivity/docs/router/support/troubleshoot-bgp-sessions)
- [Troubleshoot BGP routes and route selection](https://docs.cloud.google.com/network-connectivity/docs/router/support/troubleshoot-bgp-routes)
- [View Cloud Router details](https://docs.cloud.google.com/network-connectivity/docs/router/how-to/viewing-router-details)
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices)

**Key takeaway:** Effective hybrid connectivity troubleshooting requires separating **naming (DNS)**, **encrypted transport (IPsec/VPN)**, **routing (BGP/routes)**, and **application serving (firewalls/LB/services)**. Diagnose using status and telemetry from **both Google Cloud and on-premises**, test traffic **bidirectionally**, fix the exact failing layer, and verify **backup paths**. This approach keeps Compute Engine, GKE, Cloud Run, and data systems stable, secure, and cost-controlled.
